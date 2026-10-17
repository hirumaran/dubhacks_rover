"""Perception bridge: optional controller add-on that mirrors the rover's
cameras into the Isaac perception service inbox (default 5s cadence).

Activation: set PERCEPTION_INBOX to the perception inbox dir before launching
Webots. Without the env var this module is never imported and the rover
controller behaves exactly as before.

Contract written per tick (one seq = one Webots sim moment):
  frame_<seq:07d>_c<i>.png   full camera image (RGB PNG)
  frame_<seq:07d>.json       {"sim_time_s","gps","heading_rad","cameras":[
                              {"idx":i,"objects":[{"model","position"[camera frame],
                               "position_on_image","size_on_image","distance"}]}]}
The perception service consumes, tracks, geotags and uploads; the controller
(months of stdlib-only discipline included) writes only, never blocks driving.
"""
import json
import math
import os
import struct
import zlib
from pathlib import Path

INTERVAL_S = float(os.environ.get("FRAME_INTERVAL_S", "5.0"))


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xffffffff)


def encode_full_frame(camera) -> bytes:
    """Encode the whole camera image as RGB PNG (same stdlib-only trick as the
    gallery crop encoder, extended to the full frame)."""
    w, h = camera.getWidth(), camera.getHeight()
    raw = camera.getImage()
    if not raw:
        return b""
    rows = bytearray()
    for y in range(h):
        rows.append(0)  # PNG filter: none
        for x in range(w):
            k = (y * w + x) * 4
            rows.extend((raw[k + 2], raw[k + 1], raw[k]))  # BGRA -> RGB
    ihdr = struct.pack("!2I5B", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(rows), 5))
        + _png_chunk(b"IEND", b"")
    )


class PerceptionHook:
    def __init__(self, cameras, gps, compass, inbox_path):
        self.cameras = cameras
        self.gps = gps
        self.compass = compass
        self.inbox = Path(inbox_path)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.next_at = 0.0
        self.seq = 0
        self.clean_inbox()
        print(f"PERCEPTION_BRIDGE ACTIVE -> {self.inbox} every {INTERVAL_S}s", flush=True)

    def clean_inbox(self):
        for p in self.inbox.iterdir():
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass

    def maybe(self, now: float):
        if now < self.next_at:
            return
        self.next_at = now + INTERVAL_S
        p = self.gps.getValues()
        if any(not math.isfinite(q) for q in p):
            return
        north = self.compass.getValues()
        heading = math.atan2(north[0], north[1])
        self.seq += 1
        seq = self.seq

        cam_entries = []
        for i, cam in enumerate(self.cameras):
            data = encode_full_frame(cam)
            if not data:
                continue
            (self.inbox / f"frame_{seq:07d}_c{i}.png").write_bytes(data)
            objects = []
            for obj in cam.getRecognitionObjects():
                model = obj.getModel()
                if not model:
                    continue
                pos = obj.getPosition()
                objects.append({
                    "model": model,
                    "position": [round(float(pos[0]), 3), round(float(pos[1]), 3), round(float(pos[2]), 3)],
                    "position_on_image": [int(v) for v in obj.getPositionOnImage()],
                    "size_on_image": [int(v) for v in obj.getSizeOnImage()],
                    "distance": round(math.dist(pos, [0, 0, 0]), 3),
                })
            cam_entries.append({"idx": i, "objects": objects})

        meta = {
            "sim_time_s": round(float(now), 2),
            "gps": [round(v, 4) for v in p],
            "heading_rad": round(heading, 4),
            "seq": seq,
            "cameras": cam_entries,
        }
        meta_path = self.inbox / f"frame_{seq:07d}.json"
        tmp = self.inbox / f".meta_{seq}.tmp"
        tmp.write_text(json.dumps(meta, indent=1))
        os.replace(tmp, meta_path)  # atomic: service never reads half-written meta
        print(f"PERCEPTION_BRIDGE seq {seq} | 4 cams -> inbox | sim {now:.1f}s", flush=True)
