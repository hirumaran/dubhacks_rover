"""Frames (Webots camera PNG -> PIL/local) shared by the service and tools."""
from __future__ import annotations
from pathlib import Path
from PIL import Image


def load_png(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def downscale_for_vlm(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    scale = max(1.0, max_side / max(w, h))
    if scale == 1.0:
        return img
    return img.resize((int(w / scale), int(h / scale)), Image.LANCZOS)


def crop_norm(img: Image.Image, bbox_norm: list[float], pad_frac: float = 0.05) -> Image.Image:
    """Crop [x1,y1,x2,y2] in normalized coords; a bit of padding."""
    w, h = img.size
    x1, y1, x2, y2 = bbox_norm
    pw, ph = (x2 - x1) * pad_frac, (y2 - y1) * pad_frac
    px1 = max(0.0, x1 - pw) * w
    py1 = max(0.0, y1 - ph) * h
    px2 = min(1.0, x2 + pw) * w
    py2 = min(1.0, y2 + ph) * h
    return img.crop((int(px1), int(py1), int(px2), int(py2)))
