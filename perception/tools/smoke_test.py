"""End-to-end smoke test WITHOUT Webots (and optionally without Isaac).

Modes:
  --archive  run the full pipeline over the saved validation captures
             (simulation/validation/capture_archives/*/captures/*.png)
             using the mock detector + synthetic patrol pose. Verifies:
             detector interface, tracking, geotag math, event shaping,
             dry-run persistence.
  --inbox    process one real bridge pair from perception/inbox (if the
             teammate already ran Webots with PERCEPTION_INBOX set).

  --supabase actually push rows (requires .env); default is dry-run to
             reports/sightings_dry_run.jsonl.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import math
import os

from config import INBOX_DIR, REPORTS_DIR, cameras
from geotag import RoverPose, locate, area_hint
from isaac_detector import MockDetector, build_detector
from frames import load_png, crop_norm
from tracker import Tracker
from events import EventShaper
from run_service import Service

REPO = Path(__file__).resolve().parents[2]


def _archive_pose(idx: int, total: int) -> RoverPose:
    """Synthetic patrol pose: arc around the route start, heading tangent."""
    t = 10.0 + idx * 15.0  # plausible sim times spread out
    x = 10.0 * math.cos(0.1 * t)
    y = 10.0 * math.sin(0.1 * t)
    return RoverPose(x=x, y=y, z=0.05, heading_rad=0.1 * t + math.pi / 2, sim_time_s=t)


def run_archive(supabase: bool):
    captures = sorted((REPO / "simulation" / "validation" / "capture_archives").glob("*/captures/*.png"))
    if not captures:
        print("No archive captures found - run simulation once first.")
        return 1
    if not supabase:
        os.environ.setdefault("SUPABASE_URL", "")
        os.environ["SUPABASE_URL"] = ""
    svc = Service()
    if supabase and not svc.store.enabled:
        print("SUPABASE requested but not configured; aborting push.")
        return 1
    cam = cameras()[0]
    print(f"[smoke] {len(captures)} archive captures via mock detector")
    for i, png in enumerate(captures):
        img = load_png(png)
        pose = _archive_pose(i, len(captures))
        sim_t = pose.sim_time_s
        dets = svc.detector.detect(img, 0, sim_t)
        geo_dets = []
        for d in dets:
            geo = locate(d.bbox_norm, cam, pose)
            geo["area_hint"] = area_hint(geo["x"], geo["y"])
            geo_dets.append((d, geo))
        for event, track, det, geo in svc.tracker.update(sim_t, geo_dets):
            for row in svc.shaper.shape(event, track, det, geo, pose, backend=svc.detector.name):
                crop = None
                if det is not None and event != "gone":
                    crop_dir = config.OUTBOX_DIR / "crops"
                    crop_dir.mkdir(parents=True, exist_ok=True)
                    crop = crop_dir / f"{track.object_id}_{i}.png"
                    crop_norm(img, det.bbox_norm).save(crop)
                svc._commit(row, crop)
        svc.tracker.save_state()
    svc.store.flush_due(min_interval_s=0)
    print("[smoke] done - see perception/reports/sightings_dry_run.jsonl (dry-run) or Supabase")
    return 0


def run_inbox(supabase: bool):
    svc = Service()
    ticks = {}
    for p in INBOX_DIR.glob("frame_*_c*.png"):
        if not p.with_name(f"frame_{p.stem.split('_')[1]}.json").exists():
            continue
        seq = int(p.stem.split("_")[1])
        idx = int(p.stem.rsplit("_c", 1)[1])
        ticks.setdefault(seq, {})[idx] = p
    if not ticks or not svc:
        print("No bridge tick in perception/inbox. Start Webots with "
              "PERCEPTION_INBOX set so the rover hook drops frames there.")
        return 1
    if supabase and not svc.store.enabled:
        print("SUPABASE requested but not configured; aborting push.")
        return 1
    seq = max(ticks)
    n = svc.process_tick(seq, ticks[seq], INBOX_DIR / f"frame_{seq:07d}.json")
    print(f"[smoke] inbox tick seq {seq}: {n} events")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["archive", "inbox"], default="archive")
    ap.add_argument("--supabase", action="store_true", help="actually push (needs .env)")
    args = ap.parse_args()
    if args.mode == "inbox":
        sys.exit(run_inbox(args.supabase))
    sys.exit(run_archive(args.supabase))


if __name__ == "__main__":
    main()
