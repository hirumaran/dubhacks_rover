#!/usr/bin/env python3
"""Print this rover's last known WGS84 position.

Reads state/rover_pose.json (written every perception tick) or the newest
inbox frame_*.json from the Webots GPS hook. Use this to verify geotag origin
alignment before a demo.

  python tools/rover_locate.py
  python tools/rover_locate.py --fake-xy 14.5 -153.0
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import INBOX_DIR, OUTBOX_DIR, ROVER_ID
from geotag import RoverPose, world_xy_to_wgs84, load_origin
from rover_geo import pose_to_geo


def from_inbox() -> dict | None:
    metas = sorted(INBOX_DIR.glob("frame_*.json"))
    if not metas:
        return None
    meta = json.loads(metas[-1].read_text())
    gx, gy, gz = meta.get("gps", [0, 0, 0])
    pose = RoverPose(
        x=float(gx), y=float(gy), z=float(gz),
        heading_rad=float(meta.get("heading_rad", 0)),
        sim_time_s=float(meta.get("sim_time_s", 0)),
    )
    return {"source": metas[-1].name, **pose_to_geo(pose)}


def from_state() -> dict | None:
    path = OUTBOX_DIR / "rover_pose.json"
    if not path.exists():
        return None
    row = json.loads(path.read_text())
    row["source"] = str(path)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fake-xy", nargs=2, type=float, metavar=("X", "Y"),
                    help="Convert a Webots (x,y) meter pair to lat/lon and exit")
    args = ap.parse_args()
    if args.fake_xy:
        lat, lon = world_xy_to_wgs84(args.fake_xy[0], args.fake_xy[1])
        print(json.dumps({
            "rover_id": ROVER_ID,
            "origin": load_origin(),
            "x": args.fake_xy[0], "y": args.fake_xy[1],
            "lat": lat, "lon": lon,
        }, indent=2))
        return
    row = from_state() or from_inbox()
    if not row:
        print("No rover_pose.json and no inbox meta yet. Run run_service.py + Webots, or pass --fake-xy.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"rover_id": ROVER_ID, **row}, indent=2))


if __name__ == "__main__":
    main()
