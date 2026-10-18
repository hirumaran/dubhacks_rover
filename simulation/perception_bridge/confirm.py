"""Two-view confirmation: an item is listed only once it has been seen from two rover positions.

The first sighting of an item is kept as pending (with a copy of its frame). A later sighting
confirms it when it has the same category, a matching color or a shared name word, was seen at
least MIN_BASELINE_M away, and the two sight lines cross 0.3-MAX_RANGE_M in front of both
cameras, i.e. both views agree on where the object is. One-off misreads (a blurry bench leg, a
"rectangular object" that only exists from one angle) rarely repeat at a consistent spot, so they
stay pending and expire.

Only camera pixels and the rover's pose are used: bearings come from the box position in the frame.
"""
from __future__ import annotations

import math
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from config import CAMERA_MOUNT_YAW, PERCEPTION_HFOV, STATE_DIR
from pose import Pose

PENDING_DIR = STATE_DIR / "pending"
MIN_BASELINE_M = 0.8      # views closer than this can't triangulate
MAX_RANGE_M = 8.0         # farther than this, the camera is guessing
EXPIRE_M = 12.0           # pending sightings this far behind the rover are dropped
CONFIRMED_RADIUS_M = 1.0  # one listing per object position
STOPWORDS = {"the", "and", "with", "small", "large", "object", "item", "on", "of", "a", "an", "dark", "light"}


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 3 and w not in STOPWORDS}


@dataclass
class Sighting:
    x: float
    y: float
    bearing: float
    item: dict
    image: Path
    words: set[str] = field(default_factory=set)


def bearing_of(pose: Pose, camera: int, box: dict, image_width: int) -> float:
    cx = (box["x1"] + box["x2"]) / 2
    theta = math.atan((0.5 - cx / image_width) * 2 * math.tan(PERCEPTION_HFOV / 2))  # + = image left = CCW
    return pose.heading_rad + CAMERA_MOUNT_YAW[camera % len(CAMERA_MOUNT_YAW)] + theta


def intersect(a: Sighting, b: Sighting) -> tuple[float, float] | None:
    """Point where the two sight lines cross, if both look toward it from 0.3-MAX_RANGE_M."""
    dax, day = math.cos(a.bearing), math.sin(a.bearing)
    dbx, dby = math.cos(b.bearing), math.sin(b.bearing)
    denom = dax * dby - day * dbx
    if abs(denom) < 1e-3:
        return None  # parallel lines
    ex, ey = b.x - a.x, b.y - a.y
    ta = (ex * dby - ey * dbx) / denom
    tb = (ex * day - ey * dax) / denom
    if not (0.3 <= ta <= MAX_RANGE_M and 0.3 <= tb <= MAX_RANGE_M):
        return None
    return a.x + ta * dax, a.y + ta * day


class Confirmer:
    def __init__(self):
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        for old in PENDING_DIR.iterdir():
            old.unlink(missing_ok=True)
        self.pending: list[Sighting] = []
        self.confirmed: list[tuple[float, float]] = []
        self._n = 0

    def _same_item(self, a: Sighting, b: Sighting) -> bool:
        return a.item["category"] == b.item["category"] and (
            a.item["color"] == b.item["color"] or bool(a.words & b.words))

    def observe(self, pose: Pose, camera: int, image: Path, image_width: int, items: list[dict]) -> list[tuple[Path, dict]]:
        """Feeds one frame's identified items; returns (frame, item) pairs that are now confirmed."""
        for p in [p for p in self.pending if math.dist((p.x, p.y), (pose.x, pose.y)) > EXPIRE_M]:
            p.image.unlink(missing_ok=True)
            self.pending.remove(p)
        confirmed: list[tuple[Path, dict]] = []
        keep_frame = False
        for item in items:
            s = Sighting(pose.x, pose.y, bearing_of(pose, camera, item["box"], image_width), item, image,
                         words(f"{item.get('title', '')} {item.get('what_it_is', '')}"))
            match = None
            for p in self.pending:
                if math.dist((p.x, p.y), (s.x, s.y)) < MIN_BASELINE_M or not self._same_item(p, s):
                    continue
                point = intersect(p, s)
                if point:
                    match = (p, point)
                    break
            if match:
                p, point = match
                self.pending.remove(p)
                p.image.unlink(missing_ok=True)
                if any(math.dist(point, c) < CONFIRMED_RADIUS_M for c in self.confirmed):
                    continue  # already listed from earlier views
                self.confirmed.append(point)
                confirmed.append((image, item))
            else:
                self.pending.append(s)
                keep_frame = True
        if keep_frame:  # the inbox frame is about to be deleted; pending sightings need their own copy
            self._n += 1
            copy = PENDING_DIR / f"{self._n:06d}_{image.name}"
            shutil.copy(image, copy)
            for p in self.pending:
                if p.image == image:
                    p.image = copy
        return confirmed
