"""Offline self-test: fake rover ticks -> bridge -> local mock of identify-found-items.

Checks the change gate (what gets sent and what is skipped), the request the edge function
receives, and the offline queue. No network, no Webots, no Perceptron credits.

    python tools/selftest.py      # expects "[selftest] PASS"
"""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

received: list[dict] = []
fail_next = {"n": 0}


class MockIdentify(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if fail_next["n"] > 0:
            fail_next["n"] -= 1
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"error":"temporarily unavailable"}')
            return
        received.append({"secret": self.headers.get("x-ingest-secret"), **body})
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"dry_run": False, "listed": [], "duplicates": [], "skipped": []}).encode())

    def log_message(self, *_):
        pass


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), MockIdentify)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    tmp = Path(tempfile.mkdtemp(prefix="bridge_selftest_"))
    os.environ.update({
        "IDENTIFY_URL": f"http://127.0.0.1:{server.server_port}/",
        "ROVER_INGEST_SECRET": "test-secret",
        "ROVER_ID": "00000000-0000-0000-0000-000000000001",
        "IS_DEMO": "true",
        "DRY_RUN": "false",
        "SEND_CAMERAS": "0,1,2,3",
        "MOVE_MIN_M": "6.0",
        "DETECT_TILES": "3x1",
        "DETECT_BAND": "0.25,0.75",
        "PERCEPTION_INBOX": str(tmp / "inbox"),
        "PERCEPTION_STATE": str(tmp / "state"),
        "PERCEPTION_REPORTS": str(tmp / "reports"),
    })
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PIL import Image

    import run_bridge
    from pose import DEG_PER_M_LAT, DEG_PER_M_LON, LAT0, LON0

    rng = random.Random(7)

    def scene() -> Image.Image:
        small = Image.new("RGB", (40, 30))
        small.putdata([(rng.randrange(256),) * 3 for _ in range(40 * 30)])
        return small.resize((320, 240))  # blocky, so the image hash sees real structure

    views = [scene() for _ in range(4)]
    inbox = tmp / "inbox"
    inbox.mkdir(parents=True)
    seq = 0

    def tick(x: float, y: float, heading: float):
        nonlocal seq
        seq += 1
        for i, img in enumerate(views):
            img.save(inbox / f"frame_{seq:07d}_c{i}.png")
        (inbox / f"frame_{seq:07d}.json").write_text(json.dumps(
            {"sim_time_s": seq * 5.0, "gps": [x, y, 0.1], "heading_rad": heading, "seq": seq,
             "cameras": [{"idx": i} for i in range(4)]}))

    bridge = run_bridge.Bridge()
    checks: list[tuple[str, bool]] = []

    def step(name: str, expected: int, x: float, y: float, heading: float):
        before = len(received)
        tick(x, y, heading)
        bridge.run(once=True)
        got = len(received) - before
        checks.append((f"{name}: sent {got}, expected {expected}", got == expected))

    step("first views", 4, 0.0, 0.0, 0.0)
    step("parked, same views", 0, 0.0, 0.0, 0.0)
    views[0] = scene()
    step("parked, camera 0 view changed", 1, 0.0, 0.0, 0.0)
    step("drove 3 m (under 6 m)", 0, 3.0, 0.0, 0.0)
    step("drove 7 m", 4, 7.0, 0.0, 0.0)
    step("turned 30 deg in place", 4, 7.0, 0.0, math.radians(30))

    # Behind: three ticks waiting -> only the newest is processed.
    before = len(received)
    tick(20.0, 0.0, math.radians(30))
    tick(30.0, 0.0, math.radians(30))
    tick(40.0, 0.0, math.radians(30))
    bridge.run(once=True)
    sent_seqs = {r["discovered_at"] for r in received[before:]}
    checks.append((f"behind: sent {len(received) - before} from {len(sent_seqs)} tick(s), expected 4 from 1",
                   len(received) - before == 4 and len(sent_seqs) == 1 and not any(inbox.iterdir())))

    # Server outage: the request is queued, then delivered on the next pass.
    fail_next["n"] = 1
    before = len(received)
    tick(50.0, 0.0, math.radians(30))
    bridge.run(once=True)  # camera 0 hits the 503 and is queued; the next pass retries it
    queued_ok = len(received) - before == 4 and bridge.uploader.pending() == 0
    checks.append((f"outage: {len(received) - before}/4 delivered after retry, {bridge.uploader.pending()} queued",
                   queued_ok))

    # The request itself: pure vision + pose, correct location, demo flag, secret.
    r = received[-1]
    lat, lon = LAT0 + 0.0 * DEG_PER_M_LAT, LON0 + 50.0 * DEG_PER_M_LON
    checks += [
        ("secret header sent", r["secret"] == "test-secret"),
        ("only image + pose fields", set(r) == {"secret", "image_base64", "approximate_location", "latitude",
                                                "longitude", "source", "rover_id", "is_demo", "discovered_at",
                                                "dry_run", "min_box_px", "detect_tiles"}),
        ("lat/lon from GPS", abs(r["latitude"] - lat) < 1e-9 and abs(r["longitude"] - lon) < 1e-9),
        ("demo + rover source", r["is_demo"] is True and r["source"] == "rover"),
        ("detection tiles requested", r["detect_tiles"] == {"cols": 3, "rows": 1, "band": [0.25, 0.75]}),
        ("inbox emptied", not any(inbox.iterdir())),
    ]

    # Two-view confirmation: an item 3 m to the left of the route, seen from x=0 and x=1.
    import math as _m
    from confirm import Confirmer
    from pose import Pose
    W = 1920
    def box_for(px, py, item_x, item_y, hfov=0.87):  # box centred on the item's bearing, camera 1 (left)
        theta = _m.atan2(item_y - py, item_x - px) - _m.pi / 2
        cx = W * (0.5 - _m.tan(theta) / (2 * _m.tan(hfov / 2)))
        return {"x1": cx - 30, "y1": 600, "x2": cx + 30, "y2": 760}
    duck = {"title": "Yellow rubber duck", "category": "Other", "color": "Yellow", "description": "d"}
    frame = tmp / "frame.jpg"
    Image.new("RGB", (W, 1440)).save(frame)
    c = Confirmer()
    first = c.observe(Pose(0, 0, 0, 0), 1, frame, W, [{**duck, "box": box_for(0, 0, 0, 3)}])
    same_spot = c.observe(Pose(0.2, 0, 0, 5), 1, frame, W, [{**duck, "box": box_for(0.2, 0, 0, 3)}])
    other = c.observe(Pose(1, 0, 0, 10), 1, frame, W,
                      [{"title": "Black wallet", "category": "Accessories", "color": "Black", "description": "d",
                        "box": box_for(1, 0, 0, 3)}])
    second = c.observe(Pose(1.2, 0, 0, 15), 1, frame, W, [{**duck, "box": box_for(1.2, 0, 0, 3)}])
    checks += [
        ("one view never lists", first == [] and same_spot == []),
        ("different item at the same spot doesn't confirm", other == []),
        ("second view from 1.2 m away confirms", len(second) == 1 and second[0][1]["title"] == duck["title"]),
    ]

    server.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)
    for name, ok in checks:
        print(f"[selftest] {'ok  ' if ok else 'FAIL'} {name}")
    passed = all(ok for _, ok in checks)
    print(f"[selftest] {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
