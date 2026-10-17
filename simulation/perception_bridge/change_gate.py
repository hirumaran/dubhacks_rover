"""Decides which camera images are worth sending to Perceptron.

Uses only the rover's own sensors: the camera image and the rover's GPS/compass pose. A camera's
image is sent when that camera has never sent one, or since its last sent image the rover has
moved MOVE_MIN_M, the camera has turned TURN_MIN_DEG, or the picture itself has changed (an
item dropped or picked up while the rover is parked). Everything else is skipped, which keeps a
parked or slow rover from paying for the same view again and again.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image

from config import IMAGE_DIFF_MIN, MOVE_MIN_M, STATE_DIR, TURN_MIN_DEG
from pose import Pose, angle_diff_deg

STATE_PATH = STATE_DIR / "gate.json"


def dhash(img: Image.Image) -> int:
    """64-bit difference hash: robust to noise and small exposure changes, sensitive to content."""
    g = img.convert("L").resize((9, 8), Image.BILINEAR)
    px = list(g.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits


class ChangeGate:
    def __init__(self, state_path: Path = STATE_PATH):
        self.state_path = state_path
        self.last: dict[str, dict] = {}
        try:
            self.last = json.loads(state_path.read_text())
        except (OSError, ValueError):
            pass

    def check(self, camera_idx: int, pose: Pose, img: Image.Image) -> tuple[bool, str]:
        """Returns (send, reason)."""
        prev = self.last.get(str(camera_idx))
        if prev is None:
            return True, "first view"
        moved = math.hypot(pose.x - prev["x"], pose.y - prev["y"])
        if moved >= MOVE_MIN_M:
            return True, f"moved {moved:.1f} m"
        turned = angle_diff_deg(pose.camera_yaw(camera_idx), prev["yaw"])
        if turned >= TURN_MIN_DEG:
            return True, f"turned {turned:.0f} deg"
        changed = bin(dhash(img) ^ int(prev["hash"])).count("1")
        if changed >= IMAGE_DIFF_MIN:
            return True, f"image changed ({changed}/64)"
        return False, f"same view (moved {moved:.1f} m, turned {turned:.0f} deg, image {changed}/64)"

    def mark_sent(self, camera_idx: int, pose: Pose, img: Image.Image) -> None:
        self.last[str(camera_idx)] = {"x": pose.x, "y": pose.y, "yaw": pose.camera_yaw(camera_idx), "hash": dhash(img)}

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.last, indent=1))
        tmp.replace(self.state_path)
