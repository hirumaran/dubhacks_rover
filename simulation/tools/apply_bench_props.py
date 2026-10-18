#!/usr/bin/env python3
"""Replace the lost items in worlds/uw_autonomous.wbt with benches and random real items on them.

Re-run to re-roll the items (pass --seed to reproduce a layout). The full campus generator,
build_project.py, uses the same bench_props module, so a regenerated world gets the same kind
of layout. Writes the ground-truth layout to maps/lost_items.json for checking detections.

    python tools/apply_bench_props.py [--seed N] [--benches 6] [--max-items 2]
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

import bench_props

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "worlds" / "uw_autonomous.wbt"
MISSION = ROOT / "maps" / "mission.json"
LAYOUT = ROOT / "maps" / "lost_items.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=random.SystemRandom().randrange(1_000_000))
    ap.add_argument("--benches", type=int, default=6)
    ap.add_argument("--max-items", type=int, default=2)
    args = ap.parse_args()

    text = WORLD.read_text()
    route = [tuple(p) for p in json.loads(MISSION.read_text())["waypoints"]]
    # Old props: the coloured-box items and any benches from a previous run (one node per line).
    text = re.sub(r"(?m)^DEF (ITEM|BENCH)_\d+ .*\n\n?", "", text)

    nodes, benches, summary = bench_props.render(
        route, bench_props.campus_blocked(text), random.Random(args.seed),
        bench_count=args.benches, max_items_per_bench=args.max_items)

    # Model declarations from earlier runs that the current item pool no longer uses.
    text = re.sub(r'(?m)^EXTERNPROTO "' + re.escape(bench_props.PROTO_BASE) + r'/[^"]+"\n', "", text)
    for url in bench_props.EXTERNPROTOS:
        line = f'EXTERNPROTO "{url}"'
        if line not in text:
            text = text.replace('EXTERNPROTO "../protos/CampusScout.proto"',
                                f'EXTERNPROTO "../protos/CampusScout.proto"\n{line}', 1)
    anchor = "DEF MISSION_MONITOR "
    if anchor not in text:
        raise SystemExit(f"{WORLD.name}: could not find {anchor.strip()} to insert before")
    text = text.replace(anchor, "\n\n".join(nodes) + "\n\n" + anchor, 1)
    WORLD.write_text(text)

    LAYOUT.write_text(json.dumps({"seed": args.seed, "benches": [
        {"id": i, "x": round(x, 2), "y": round(y, 2), "yaw": round(yaw, 3)} for i, (x, y, yaw) in enumerate(benches, 1)
    ], "items": summary}, indent=2) + "\n")
    print(f"seed {args.seed}: {len(benches)} benches, {len(summary)} items "
          f"({', '.join(sorted(s['kind'] for s in summary)) or 'none'}) -> {WORLD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
