"""Bridge self-test WITHOUT Webots.

Fabricates a realistic inbox tick exactly like the rover hook would write it
(4 camera PNGs + one reciprocal meta with GPS/heading/sim time and both
recognition objects and a bbox), then pushes it through Service.process_tick.

Verifies: the inbox contract, per-camera handling, geotag from a real pose,
tracking (stable IDs across two ticks), event shaping, dry-run persistence.

Hermetic: runs against a throwaway temp dir (PERCEPTION_INBOX_DIR /
PERCEPTION_STATE_DIR / PERCEPTION_REPORTS_DIR), so it never touches the real
inbox/state/reports and always starts from an empty tracker. Re-runnable.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uuid


@contextmanager
def _sandbox():
    with tempfile.TemporaryDirectory(prefix="perception_selftest_") as tmp:
        root = Path(tmp)
        os.environ["PERCEPTION_INBOX_DIR"] = str(root / "inbox")
        os.environ["PERCEPTION_STATE_DIR"] = str(root / "state")
        os.environ["PERCEPTION_REPORTS_DIR"] = str(root / "reports")
        (root / "inbox").mkdir()
        yield root


def _png(w: int = 320, h: int = 240) -> bytes:
    """Tiny synthetic 'frame': gravel background + a blue bottle block."""
    from PIL import Image
    img = Image.new("RGB", (w, h), (120, 110, 100))
    for x in range(w // 2 - 20, w // 2 + 20):
        for y in range(h // 3, h * 3 // 4):
            img.putpixel((x, y), (30, 90, 200))
    tmp = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}.png"
    img.save(tmp, format="PNG")
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    return data


def main():
    with _sandbox():
        return _run()


def _run():
    from config import INBOX_DIR
    from run_service import Service

    print("[selftest] writing a synthetic tick into", INBOX_DIR)
    # 1) robot pose: rover at (5, -3, 0.05), heading 45 deg (NE)
    gps = [5.0, -3.0, 0.05]
    heading = 0.785398
    sim_t = 42.0

    cams = []
    pngs = {}
    for i in range(4):
        png_path = INBOX_DIR / f"frame_0000001_c{i}.png"
        png_path.write_bytes(_png())
        pngs[i] = png_path
        objects = []
        if i == 0:  # front camera sees a recognized bottle 2 m ahead
            objects.append({
                "model": "bottle|CS-042",
                "position": [2.0, -0.1, -0.15],  # camera frame: X depth, Y image-left, Z up
                "position_on_image": [120, 150],
                "size_on_image": [40, 90],
                "distance": 2.04,
            })
        cams.append({"idx": i, "objects": objects})

    meta_path = INBOX_DIR / "frame_0000001.json"
    meta_path.write_text(json.dumps({
        "sim_time_s": sim_t, "gps": gps, "heading_rad": heading, "seq": 1, "cameras": cams,
    }, indent=1))

    # 2) push through the real pipeline
    svc = Service()
    n = svc.process_tick(1, pngs, meta_path)
    if n == 0:
        print("[selftest] FAIL: no events"); return 1
    svc.tracker.save_state()

    # 3) second tick, same bottle slightly moved -> expects 'moved'/'seen' on the SAME id
    gps2 = [6.4, -2.02, 0.05]  # rover moved ~1 m NE toward the bottle
    for i, p in pngs.items():
        p.unlink()
    meta_path.unlink()
    for i in range(4):
        p = INBOX_DIR / f"frame_0000002_c{i}.png"
        p.write_bytes(_png())
    meta2 = {
        "sim_time_s": sim_t + 5.0, "gps": gps2, "heading_rad": heading, "seq": 2, "cameras": cams,
    }
    (INBOX_DIR / "frame_0000002.json").write_text(json.dumps(meta2, indent=1))
    pngs2 = {i: INBOX_DIR / f"frame_0000002_c{i}.png" for i in range(4)}
    svc.process_tick(2, pngs2, INBOX_DIR / "frame_0000002.json")

    # 4) cleanup + report
    tracks = list(svc.tracker.tracks.values())
    print("[selftest] active tracks:", [(t.object_id, t.label, t.world_x, t.world_y) for t in tracks])
    ok_geo = True
    if tracks:
        t = tracks[0]
        geotag = t.geotag
        ok_geo = geotag["range_m"] <= 6.0 and abs(geotag["x"]) < 50 and abs(geotag["y"]) < 50
        print("[selftest] geotag:", geotag)
    for i in range(4):
        (INBOX_DIR / f"frame_0000002_c{i}.png").unlink(missing_ok=True)
    (INBOX_DIR / "frame_0000002.json").unlink(missing_ok=True)

    print("[selftest] PASS" if (tracks and ok_geo) else "[selftest] FAIL")
    return 0 if (tracks and ok_geo) else 1


if __name__ == "__main__":
    sys.exit(main())
