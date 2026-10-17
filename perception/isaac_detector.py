"""Detector layer: Isaac-0.2-1B via transformers (primary), Perceptron SDK
(fallback), or a deterministic mock (no model needed - used for smoke tests
and bridge verification).

The detector receives a frame (PIL image) plus optional reference detections
from the simulator's Recognition node, and returns a normalized Detection list.
"""
from __future__ import annotations
import json
import random
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import config
from config import ISAAC_HF_PATH, ISAAC_BACKEND, ISAAC_DEVICE, ISAAC_MAX_SIDE, ISAAC_ENABLE_THINKING

# Classes a student can lose on campus; keeps the label space tight for matching.
TARGET_CLASSES = [
    "backpack", "book", "notebook", "bottle", "umbrella", "phone", "keys",
    "wallet", "headphones", "jacket", "hat", "lunchbox", "sunglasses",
    "laptop", "charger", "bag", "bicycle", "toy", "other",
]

SYSTEM_PROMPT = (
    "You are the vision system of a small campus rover. You look at single camera "
    "frames and report objects that a student could have LOST. You always answer "
    "with ONLY a JSON array, no prose, no markdown fences."
)

USER_PROMPT = """Task: list every distinct lost-item-looking object visible in this camera frame.

Allowed labels (pick closest): {classes}.

For each object output one JSON object with exactly these keys:
- "label": one of the allowed labels
- "description": max 12 words describing the object (include main color and where it sits, e.g. "on gravel")
- "color": main color, lower-case
- "bbox_xyxy_norm": [x1, y1, x2, y2] with floats in 0..1, image-normalized
- "confidence": 0..1 float

Rules:
- Only genuinely visible, distinct physical objects. No duplicates for the same item.
- Ignore buildings, people, roads, and empty ground.
- If nothing matches, return [].

Answer with the JSON array only."""


@dataclass
class Detection:
    label: str
    description: str
    color: str
    bbox_norm: list[float]          # [x1,y1,x2,y2] normalized 0..1
    confidence: float
    camera_idx: int
    sim_time_s: float               # sim time (or wall time in mock/offline use)
    recog_x: Optional[float] = None  # recognition depth (camera frame X) if available
    source: str = "unknown"          # isaac_transformers | isaac_sdk | mock | recognition

    def to_row(self) -> dict:
        return asdict(self)


def _is_bbox(b) -> bool:
    return (
        isinstance(b, (list, tuple)) and len(b) == 4
        and all(isinstance(v, (int, float)) for v in b)
    )


def _clamp_bbox(b) -> list[float]:
    x1, y1, x2, y2 = [float(v) for v in b]
    x1, x2 = sorted((min(1.0, max(0.0, x1)), min(1.0, max(0.0, x2))))
    y1, y2 = sorted((min(1.0, max(0.0, y1)), min(1.0, max(0.0, y2))))
    if x2 - x1 < 0.01 or y2 - y1 < 0.01:  # degenerate -> tiny center box
        x1, y1, x2, y2 = 0.45, 0.45, 0.55, 0.55
    return [x1, y1, x2, y2]


def _extract_json_array(text: str):
    if not text:
        return None
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return None
    raw = m.group(0)
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else None
    except json.JSONDecodeError:
        return None


class TransformersIsaac:
    """Isaac-0.2-1B loaded from a local HF cache with trust_remote_code=True.

    Device map per hardware: cuda -> bfloat16 (+flash_attention_2 when the HF
    card's recommended extra is present), mps -> float16, cpu -> float32.
    """

    name = "isaac-0.2-1B[transformers]"

    def __init__(self):
        import torch
        self._torch = torch
        self.device = self._pick_device()
        self.dtype = {
            "cuda": torch.bfloat16,
            "mps": torch.float16,
            "cpu": torch.float32,
        }[self.device.type]
        self._load()

    def _pick_device(self):
        t = self._torch
        pref = ISAAC_DEVICE
        if pref == "cuda" and t.cuda.is_available():
            return t.device("cuda")
        if pref in ("mps", "auto") and getattr(t.backends, "mps", None) and t.backends.mps.is_available():
            return t.device("mps")
        if pref in ("cuda", "auto") and t.cuda.is_available():
            return t.device("cuda")
        return t.device("cpu")

    def _load(self):
        from transformers import AutoProcessor, AutoModelForCausalLM
        t = self._torch
        kwargs = dict(trust_remote_code=True, torch_dtype=self.dtype)
        if self.device.type == "cuda":
            kwargs["vision_attn_implementation"] = "flash_attention_2"  # per HF card
            kwargs["attn_implementation"] = "sdpa"
        else:
            kwargs["attn_implementation"] = "sdpa"
        self.processor = AutoProcessor.from_pretrained(ISAAC_HF_PATH, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(ISAAC_HF_PATH, **kwargs)
        self.model = self.model.to(device=self.device, dtype=self.dtype)
        self.model.eval()

    def _build_inputs(self, image, user_text: str):
        from PIL import Image as PILImage
        img = image if isinstance(image, PILImage.Image) else PILImage.fromarray(image)
        prompt_text = (
            f"<|im_start|>system\\n{SYSTEM_PROMPT}<|im_end|>\\n"
            f"<|im_start|>user\\n{user_text}<|im_end|>\\n"
            f"<|im_start|>assistant\\n"
        )
        inputs = self.processor(text=prompt_text, images=img, return_tensors="pt")
        return {k: v.to(self.device) for k, v in inputs.items()}

    def detect(self, image, camera_idx: int, sim_time_s: float, ref_dets=None) -> list[Detection]:
        from frames import downscale_for_vlm
        small = downscale_for_vlm(image, ISAAC_MAX_SIDE)
        user_text = USER_PROMPT.format(classes=", ".join(TARGET_CLASSES[:-1]))
        inputs = self._build_inputs(small, user_text)
        with self._torch.inference_mode():
            out = self.model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
                temperature=None,
                top_p=None,
            )
        text = self.processor.batch_decode(out, skip_special_tokens=True)[0]
        items = _extract_json_array(text)
        if not isinstance(items, list):
            return []
        dets = []
        for it in items:
            if not isinstance(it, dict):
                continue
            bbox = it.get("bbox_xyxy_norm") or it.get("bbox") or it.get("box")
            if not _is_bbox(bbox):
                continue
            label = str(it.get("label", "other")).lower().strip()
            if label not in TARGET_CLASSES:
                label = "other"
            dets.append(Detection(
                label=label,
                description=str(it.get("description", "")).strip(),
                color=str(it.get("color", "unknown")).lower().strip(),
                bbox_norm=_clamp_bbox(bbox),
                confidence=float(it.get("confidence", 0.5) or 0.5),
                camera_idx=camera_idx,
                sim_time_s=sim_time_s,
                source="isaac_transformers",
            ))
        return dets


class SDKIsaac:
    """Adapter for the `perceptron` local SDK (detect operation, per the
    FiftyOne integration docs). Kept deliberately thin: the transformers path
    is the verified primary; use this only if your teammate installed the SDK.
    """

    name = "isaac-0.2-1B[sdk]"

    def __init__(self):
        try:
            from perceptron import Perceptron  # noqa
        except ImportError as e:
            raise RuntimeError(
                "ISAAC_BACKEND=sdk requires `pip install perceptron` "
                "(check current SDK API on https://docs.perceptron.inc)."
            ) from e
        self._client = Perceptron(model="isaac-0.2-1b", local=True)

    def detect(self, image, camera_idx: int, sim_time_s: float, ref_dets=None) -> list[Detection]:
        raise NotImplementedError(
            "Perceptron SDK local API differs between releases; verify at "
            "https://docs.perceptron.inc and finish this adapter, or use "
            "ISAAC_BACKEND=transformers.")


class MockDetector:
    """No-model detector.

    * With reference detections (simulator Recognition sidecar) it converts
      them 1:1 into Detections - exercises the true bridge path.
    * Without them (archive captures) it emits deterministic pseudo detections
      so tracker/geotag/storage can be tested end to end.
    """

    name = "mock"

    def __init__(self):
        self._rng = random.Random(2026)
        self._fake = [
            ("backpack", "red backpack on the ground", "red"),
            ("bottle", "blue water bottle standing near path", "blue"),
            ("book", "closed yellow notebook", "yellow"),
        ]

    def detect(self, image, camera_idx: int, sim_time_s: float, ref_dets=None) -> list[Detection]:
        if ref_dets:
            out = []
            for r in ref_dets:
                u, v = r["position_on_image"]
                bw, bh = r["size_on_image"]
                w, h = image.size
                bbox = [
                    (u - bw / 2) / w, (v - bh / 2) / h,
                    (u + bw / 2) / w, (v + bh / 2) / h,
                ]
                model = r.get("model", "")
                kind = model.split("|", 1)[0] if "|" in model else "other"
                out.append(Detection(
                    label=kind if kind in TARGET_CLASSES else "other",
                    description=f"{model.split('|', 1)[1] if '|' in model else 'recognition object'} (recognition ref)",
                    color="unknown",
                    bbox_norm=_clamp_bbox(bbox),
                    confidence=0.99,
                    camera_idx=camera_idx,
                    sim_time_s=sim_time_s,
                    recog_x=float(r["position"][0]),
                    source="recognition",
                ))
            return out

        # Deterministic archive mode: one object per frame, cycling the fake list.
        idx = int(sim_time_s) % len(self._fake)
        label, desc, color = self._fake[idx]
        cx = 0.35 + 0.3 * ((int(sim_time_s) // 7) % 3)
        bbox = [cx - 0.09, 0.55, cx + 0.09, 0.85]
        return [Detection(
            label=label, description=desc, color=color,
            bbox_norm=_clamp_bbox(bbox), confidence=0.62,
            camera_idx=camera_idx, sim_time_s=sim_time_s, source="mock",
        )]


def build_detector():
    """ISAAC_BACKEND=auto: transformers -> sdk -> mock. Explicit values honored."""
    if ISAAC_BACKEND == "mock":
        return MockDetector()
    attempts = {
        "transformers": TransformersIsaac,
        "sdk": SDKIsaac,
    }
    if ISAAC_BACKEND == "auto":
        order = ["transformers", "sdk"]
    elif ISAAC_BACKEND in attempts:
        order = [ISAAC_BACKEND]
    else:
        order = []
    errs = []
    for key in order:
        try:
            det = attempts[key]()
            print(f"[detector] backend={key} ready", flush=True)
            return det
        except Exception as e:  # noqa: BLE001 - loader errors are data, not bugs
            errs.append(f"{key}: {e}")
    print("[detector] no real backend available -> mock", flush=True)
    for e in errs:
        print(f"           {e}", flush=True)
    return MockDetector()
