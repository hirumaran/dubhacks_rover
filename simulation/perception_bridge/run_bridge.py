"""Perception bridge: rover camera frames -> identify-found-items -> found_items.

The rover controller (controllers/campus_rover/perception_hook.py) writes, every few seconds,
one PNG per camera plus a JSON sidecar with the rover's GPS position and compass heading. This
service picks those up, keeps only the images whose view has changed (change_gate.py), and sends
each one to the identify-found-items edge function with the rover's location. Perceptron does
all detection and description server-side, and the server skips items that are already listed.

Only vision data and the rover's own pose are used; nothing from the simulator's scene graph.

    python run_bridge.py          # run until stopped
    python run_bridge.py --once   # process what is in the inbox now, then exit
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

import config
from change_gate import ChangeGate
from pose import Pose
from uploader import Uploader

TICK_RE = re.compile(r"^frame_(\d+)\.json$")
CAM_RE = re.compile(r"^frame_(\d+)_c(\d+)\.png$")
EVENTS_LOG = config.REPORTS_DIR / "events.jsonl"


def log(event: dict) -> None:
    EVENTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_LOG.open("a") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), **event}) + "\n")


def summarize(result: dict) -> str:
    if result["status"] != "ok":
        return f"{result['status']}: {result.get('error', '')}"
    listed = result.get("listed") or result.get("identified") or []
    names = ", ".join(i.get("title", i.get("label", "?")) for i in listed) or "nothing new"
    extra = []
    if result.get("duplicates"):
        extra.append(f"{len(result['duplicates'])} already listed")
    if result.get("skipped"):
        extra.append(f"{len(result['skipped'])} skipped")
    verb = "would list" if result.get("dry_run") else "listed"
    return f"{verb} {names}" + (f" ({', '.join(extra)})" if extra else "")


class Bridge:
    def __init__(self):
        if not config.INGEST_SECRET:
            sys.exit("ROVER_INGEST_SECRET is not set (simulation/perception_bridge/.env)")
        if not config.ROVER_ID:
            sys.exit("ROVER_ID is not set: register this rover in the `rovers` table and put its id in .env")
        config.INBOX_DIR.mkdir(parents=True, exist_ok=True)
        self.gate = ChangeGate()
        self.uploader = Uploader()
        mode = "DRY RUN" if config.DRY_RUN else "live"
        print(f"[bridge] {mode} | demo={config.IS_DEMO} | inbox {config.INBOX_DIR} -> {config.IDENTIFY_URL}", flush=True)

    def pending_ticks(self) -> list[tuple[int, Path]]:
        ticks = []
        for p in config.INBOX_DIR.iterdir():
            m = TICK_RE.match(p.name)
            if m:
                ticks.append((int(m.group(1)), p))
        return sorted(ticks)

    def payload(self, png: Path, pose: Pose, captured_at: str) -> dict:
        lat, lon = pose.lat_lon()
        return {
            "image_base64": base64.b64encode(png.read_bytes()).decode(),
            "approximate_location": f"{config.LOCATION_LABEL} ({lat:.4f}, {lon:.4f})",
            "latitude": lat,
            "longitude": lon,
            "source": "rover",
            "rover_id": config.ROVER_ID,
            "is_demo": config.IS_DEMO,
            "discovered_at": captured_at,
            "dry_run": config.DRY_RUN,
        }

    def process_tick(self, seq: int, meta_path: Path) -> int:
        meta = json.loads(meta_path.read_text())
        pose = Pose.from_meta(meta)
        captured_at = datetime.fromtimestamp(meta_path.stat().st_mtime, timezone.utc).isoformat()
        pngs = sorted(
            (int(m.group(2)), p)
            for p in config.INBOX_DIR.glob(f"frame_{seq:07d}_c*.png")
            if (m := CAM_RE.match(p.name))
        )
        sent = 0
        for cam, png in pngs:
            with Image.open(png) as img:
                img.load()
            send, reason = self.gate.check(cam, pose, img)
            if send:
                result = self.uploader.send(self.payload(png, pose, captured_at), key=f"{seq:07d}_c{cam}")
                self.gate.mark_sent(cam, pose, img)
                sent += 1
                print(f"[bridge] seq {seq} cam {cam} ({reason}) -> {summarize(result)}", flush=True)
                log({"seq": seq, "camera": cam, "reason": reason, "result": result})
            else:
                log({"seq": seq, "camera": cam, "skipped": reason})
        for _, png in pngs:
            png.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        self.gate.save()
        return sent

    def run(self, once: bool = False) -> None:
        while True:
            for seq, meta_path in self.pending_ticks():
                try:
                    self.process_tick(seq, meta_path)
                except (OSError, ValueError, KeyError) as e:  # a half-written or malformed tick
                    print(f"[bridge] seq {seq} unreadable ({e}); dropping", flush=True)
                    meta_path.unlink(missing_ok=True)
            for key, result in self.uploader.retry_due(force=once):
                print(f"[bridge] retry {key} -> {summarize(result)}", flush=True)
            if once:
                if self.uploader.pending():
                    print(f"[bridge] {self.uploader.pending()} request(s) still queued in state/outbox", flush=True)
                return
            time.sleep(config.INBOX_POLL_S)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--once", action="store_true", help="process the current inbox and exit")
    Bridge().run(once=ap.parse_args().once)


if __name__ == "__main__":
    main()
