"""Main service loop: watch inbox -> Isaac -> tracker -> geotag -> Supabase.

Flow (matches the architecture flowchart):
  [Webots controller hook]  --frame_<seq>_c<i>.png (4 cameras) + frame_<seq>.json-->  [inbox]
  This service groups everything with the same seq into ONE tick, ingests at
  most one tick every FRAME_INTERVAL_S, runs the local detector on each camera
  frame, geotags, updates tracks, pushes meaningful events to Supabase
  (crop to storage, row to sightings), with an offline outbox as fallback.

Run FIRST (this service), then Webots with PERCEPTION_INBOX set (see README).
Dry-run mode (.env missing Supabase) writes everything to reports/ instead.
"""
from __future__ import annotations
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import config
from config import (
    FRAME_INTERVAL_S, INBOX_POLL_S, INBOX_DIR, REPORTS_DIR, OUTBOX_DIR, cameras,
)
from geotag import RoverPose, locate, area_hint
from isaac_detector import build_detector
from frames import load_png, crop_norm
from tracker import Tracker
from events import EventShaper
from supabase_store import SupabaseStore

EVENTS_JSONL = REPORTS_DIR / "events.jsonl"
SIGHTINGS_JSONL = REPORTS_DIR / "sightings_dry_run.jsonl"


def _pose_from_meta(meta: dict) -> RoverPose:
    gx, gy, gz = meta.get("gps", [0.0, 0.0, 0.0])
    return RoverPose(
        x=float(gx), y=float(gy), z=float(gz),
        heading_rad=float(meta.get("heading_rad", 0.0)),
        sim_time_s=float(meta.get("sim_time_s", 0.0)),
    )


def _fake_pose(sim_time_s: float) -> RoverPose:
    """Used when no Webots meta is available (archive smoke tests)."""
    t = sim_time_s
    return RoverPose(
        x=10.0 * math.cos(0.1 * t),
        y=10.0 * math.sin(0.1 * t),
        z=0.05, heading_rad=0.1 * t + math.pi / 2,
        sim_time_s=t,
    )


class Service:
    def __init__(self):
        self.cams = {c.idx: c for c in cameras()}
        self.detector = build_detector()
        self.store = SupabaseStore()
        self.tracker = Tracker()
        self.shaper = EventShaper()
        self.last_wall = 0.0
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        backend = getattr(self.detector, "name", type(self.detector).__name__)
        sb_mode = "live" if self.store.enabled else "dry-run"
        print(f"[service] backend={backend} supabase={sb_mode} interval={FRAME_INTERVAL_S}s", flush=True)

    # ---------------- ingest ----------------
    def pending_ticks(self) -> list[tuple[int, Path, Path]]:
        """All complete (camera-png, meta-json) pairs in the inbox."""
        out = []
        for png in sorted(INBOX_DIR.glob("frame_*_c*.png")):
            try:
                seq = int(png.stem.split("_")[1])
            except (ValueError, IndexError):
                continue
            jsn = INBOX_DIR / f"frame_{seq:07d}.json"
            if jsn.exists():
                out.append((seq, png, jsn))
        return out

    @staticmethod
    def _cam_index(png: Path) -> int:
        return int(png.stem.rsplit("_c", 1)[1])

    def process_tick(self, seq: int, pngs: dict[int, Path], jsn: Path) -> int:
        """One Webots sim moment: all camera frames + the pose/recognition meta."""
        meta = json.loads(jsn.read_text())
        sim_t = float(meta.get("sim_time_s", seq))
        pose = _pose_from_meta(meta)

        n_events = 0
        geo_dets: list[tuple] = []
        for idx, cam in self.cams.items():
            png = pngs.get(idx)
            if png is None:
                continue
            img = load_png(png)
            ref = next(
                (c.get("objects") or [] for c in meta.get("cameras", []) if c.get("idx") == idx),
                [],
            )
            for det in self.detector.detect(img, idx, sim_t, ref_dets=ref):
                geo = locate(det.bbox_norm, cam, pose, recog_x=det.recog_x)
                geo["area_hint"] = area_hint(geo["x"], geo["y"])
                geo_dets.append((det, geo))
        if not geo_dets:
            return 0

        for event, track, det, geo in self.tracker.update(sim_t, geo_dets):
            rows = self.shaper.shape(
                event, track, det, geo, pose,
                backend=getattr(self.detector, "name", "unknown"),
            )
            for row in rows:
                crop = None
                if det is not None and event != "gone":
                    src_png = pngs.get(det.camera_idx)
                    if src_png is not None:
                        crop_path = OUTBOX_DIR / "crops" / f"{track.object_id}_{int(time.time() * 1000)}.png"
                        crop_path.parent.mkdir(parents=True, exist_ok=True)
                        crop_norm(load_png(src_png), det.bbox_norm).save(crop_path)
                        crop = crop_path
                self._commit(row, crop)
                n_events += 1
        return n_events

    def _commit(self, row: dict, crop: Path | None):
        evt = {
            "persisted": self.store.push_event(row, crop),
            "public_image_url": self.store.public_url(row.get("image_url", "")) if row.get("image_url") else None,
            "committed_utc": datetime.now(timezone.utc).isoformat(),
            **row,
        }
        with EVENTS_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evt, default=str) + "\n")
        if not self.store.enabled:
            with SIGHTINGS_JSONL.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, default=str) + "\n")
        print(
            f"[event] {row['event']:>5} {row['object_id']} {row['label']:>9} "
            f"@ ({row['geotag']['x']:.2f}, {row['geotag']['y']:.2f}) "
            f"range {row['geotag']['range_m']:.1f}m conf {row['confidence']:.2f}",
            flush=True,
        )

    # ---------------- main ----------------
    def run(self, once: bool = False):
        print(f"[service] watching {INBOX_DIR} ...", flush=True)
        seen: set[int] = set()
        while True:
            pending = self.pending_ticks()
            if pending:
                last_seq = max(s for s, _, _ in pending)
                if last_seq not in seen and (time.time() - self.last_wall >= FRAME_INTERVAL_S or not seen):
                    pngs = {self._cam_index(p): p for s, p, _ in pending if s == last_seq}
                    jsn = INBOX_DIR / f"frame_{last_seq:07d}.json"
                    self.process_tick(last_seq, pngs, jsn)
                    seen.add(last_seq)
                    self.last_wall = time.time()
                    self.tracker.save_state()
                    self.store.flush_due()
                    # inbox hygiene: drop every file of consumed seqs
                    for s, png, _ in pending:
                        if s <= last_seq:
                            try:
                                png.unlink()
                                (INBOX_DIR / f"frame_{s:07d}.json").unlink()
                            except OSError:
                                pass
            self.store.flush_due(min_interval_s=5.0 if once else 30.0)
            if once:
                break
            time.sleep(INBOX_POLL_S)


def main(once: bool = False):
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    Service().run(once=once)


if __name__ == "__main__":
    import sys
    main(once="--once" in sys.argv)
