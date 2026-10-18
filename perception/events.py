"""Event shaping: turns tracker state changes into Supabase-ready rows with
rate limiting so the sightings table does not flood on every frame.
"""
from __future__ import annotations
import time
from config import OUTBOX_DIR

SEEN_EVERY_S = 10.0  # plain 'seen' heartbeat per object


class EventShaper:
    def __init__(self):
        self._last_seen: dict[str, float] = {}  # object_id -> wall time of last 'seen' row

    def shape(self, event: str, track, det, geotag, pose, backend: str) -> list[dict]:
        """Return 0..2 rows: the state-change row plus (throttled) seen row for 'moved'."""
        now = time.time()
        rows: list[dict] = []

        def row(ev: str) -> dict:
            return {
                "object_id": track.object_id,
                "label": track.label,
                "description": track.description,
                "color": track.color,
                "confidence": track.confidence,
                "bbox_norm": track.bbox_norm,
                "camera_idx": track.camera_idx,
                "event": ev,
                "geotag": geotag,
                "rover_pose": {
                    "x": round(pose.x, 3), "y": round(pose.y, 3),
                    "heading_rad": round(pose.heading_rad, 4),
                    "sim_time_s": round(pose.sim_time_s, 2),
                },
                "sim_time_s": round(getattr(det, "sim_time_s", pose.sim_time_s) if det else pose.sim_time_s, 2),
                "model_backend": backend,
            }

        if event == "gone":
            row_ = row("gone")
            row_["description"] = (track.description or "") + " | not seen again"
            rows.append(row_)
            return rows

        if event == "new":
            rows.append(row("new"))
        elif event == "moved":
            rows.append(row("moved"))
            if now - self._last_seen.get(track.object_id, 0.0) > SEEN_EVERY_S:
                rows.append(row("seen"))
        if rows:
            self._last_seen[track.object_id] = now
        return rows
