"""Stable object IDs across frames.

Association score = IoU bonus (same camera only) + label/color/text similarity
+ spatial gate. Cross-camera matches (rover turning 90 degrees) are allowed
when the world position agrees within the gate and the description matches.

Events emitted per update: 'new' when an ID is created, 'moved' when its
geotagged position jumps, 'gone' when unseen for GONE_AFTER_S. Plain 'seen'
is throttled by events.py; the tracker only emits state changes.
"""
from __future__ import annotations
import json
import math
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

import config
from config import GONE_AFTER_S, MOVE_MIN_M, MATCH_IOU_MIN, MATCH_TEXT_MIN, OUTBOX_DIR
from isaac_detector import Detection

STATE_PATH = OUTBOX_DIR / "tracks.json"


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1, ix2, iy2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


def _text_sim(a: str, b: str) -> float:
    ta = {w for w in (a or "").lower().replace(",", " ").split() if len(w) > 2}
    tb = {w for w in (b or "").lower().replace(",", " ").split() if len(w) > 2}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


@dataclass
class Track:
    object_id: str
    label: str
    description: str
    color: str
    bbox_norm: list[float]
    confidence: float
    camera_idx: int
    world_x: float
    world_y: float
    geotag: dict
    first_seen_t: float          # sim time
    first_seen_utc: str
    last_seen_t: float
    last_seen_utc: str
    event: str = "new"           # last state change new|moved|seen|gone
    age_updates: int = 0


class Tracker:
    def __init__(self):
        self.tracks: dict[str, Track] = {}
        self.retired: set[str] = set()
        self._seq = 0
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        self._load_state()

    # ---------------- state persistence ----------------
    def _load_state(self):
        try:
            data = json.loads(STATE_PATH.read_text())
            for t in data.get("active", []):
                self.tracks[t["object_id"]] = Track(**t)
            self.retired = set(data.get("retired", []))
            self._seq = int(data.get("seq", 0))
        except (OSError, ValueError, TypeError, KeyError):
            self.tracks, self.retired, self._seq = {}, set(), 0

    def save_state(self):
        data = {
            "active": [asdict(t) for t in self.tracks.values()],
            "retired": sorted(self.retired),
            "seq": self._seq,
            "saved_utc": datetime.now(timezone.utc).isoformat(),
        }
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(STATE_PATH)

    # ---------------- ID allocation ----------------
    def _new_id(self) -> str:
        self._seq += 1
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        return f"OBJ-{stamp}-{self._seq}"

    # ---------------- association ----------------
    def _score(self, track: Track, det: Detection, det_world: dict) -> float:
        same_cam = track.camera_idx == det.camera_idx
        iou = _iou(track.bbox_norm, det.bbox_norm) if same_cam else 0.0
        label = 1.0 if track.label == det.label else 0.0
        color = 1.0 if track.color and track.color == det.color else 0.0
        text = _text_sim(track.description, det.description)

        # Spatial gate: same spot within a few seconds keeps identity even across cameras.
        dtz = det.sim_time_s - track.last_seen_t
        dist2d = math.hypot(det_world["x"] - track.world_x, det_world["y"] - track.world_y)
        spatial = 1.0 if (dist2d < 1.2 and dtz < 10.0) else 0.0
        if not spatial:
            return -1.0  # hard gate: the object cannot teleport

        score = 0.45 * iou + 0.25 * label + 0.10 * color + 0.20 * text
        if same_cam and iou < MATCH_IOU_MIN and label == 0 and text < MATCH_TEXT_MIN:
            return -1.0
        return score

    # ---------------- main update ----------------
    def update(
        self,
        sim_time_s: float,
        dets_with_geo: list[tuple[Detection, dict]],
    ) -> list[tuple[str, Track, Detection, dict]]:
        """Returns (event, track, detection, geotag) state changes to persist."""
        events: list[tuple[str, Track, Detection, dict]] = []
        unmatched = list(dets_with_geo)
        touched: list[Track] = []

        # 1) association greed: highest score first per existing track
        for oid, track in list(self.tracks.items()):
            best, best_det, best_geo = -1.0, None, None
            for det, geo in unmatched:
                s = self._score(track, det, geo)
                if s > best:
                    best, best_det, best_geo = s, det, geo
            if best_det is not None and best > 0.2:
                moved = math.hypot(best_geo["x"] - track.world_x, best_geo["y"] - track.world_y)
                track.description = best_det.description
                track.bbox_norm = best_det.bbox_norm
                track.confidence = round(0.7 * track.confidence + 0.3 * best_det.confidence, 3)
                moved_event = moved > MOVE_MIN_M
                if moved_event:
                    track.world_x, track.world_y = best_geo["x"], best_geo["y"]
                    track.geotag = best_geo
                    events.append(("moved", track, best_det, best_geo))
                else:
                    # position EMA keeps geotag stable against noisy range estimates
                    track.world_x = round(0.8 * track.world_x + 0.2 * best_geo["x"], 3)
                    track.world_y = round(0.8 * track.world_y + 0.2 * best_geo["y"], 3)
                    track.geotag = {**best_geo, "x": track.world_x, "y": track.world_y}
                track.last_seen_t = best_det.sim_time_s
                track.last_seen_utc = datetime.now(timezone.utc).isoformat()
                track.age_updates += 1
                unmatched.remove((best_det, best_geo))
                touched.append(track)

        # 2) leftovers become new tracks, unless the same physical object was
        #    already folded into a track this tick (e.g. visible to two cameras
        #    at the same sim moment) -> then just consolidate, no duplicate ID.
        for det, geo in unmatched:
            ghost = next(
                (t for t in touched if t.label == det.label
                 and math.hypot(geo["x"] - t.world_x, geo["y"] - t.world_y) < 1.2),
                None,
            )
            if ghost is not None:
                ghost.last_seen_t = det.sim_time_s
                ghost.last_seen_utc = datetime.now(timezone.utc).isoformat()
                continue
            track = Track(
                object_id=self._new_id(),
                label=det.label,
                description=det.description,
                color=det.color,
                bbox_norm=det.bbox_norm,
                confidence=det.confidence,
                camera_idx=det.camera_idx,
                world_x=geo["x"],
                world_y=geo["y"],
                geotag=geo,
                first_seen_t=det.sim_time_s,
                first_seen_utc=datetime.now(timezone.utc).isoformat(),
                last_seen_t=det.sim_time_s,
                last_seen_utc=datetime.now(timezone.utc).isoformat(),
            )
            self.tracks[track.object_id] = track
            events.append(("new", track, det, geo))

        # 3) missed tracks -> 'gone'
        for oid in list(self.tracks.keys()):
            t = self.tracks[oid]
            if sim_time_s - t.last_seen_t > GONE_AFTER_S:
                self.tracks.pop(oid)
                self.retired.add(oid)
                gone = dict(t.geotag)
                gone["event_note"] = "not seen again"
                events.append(("gone", t, None, gone))
        return events
