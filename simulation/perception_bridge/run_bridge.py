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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

import config
from change_gate import ChangeGate
from confirm import Confirmer
from pose import Pose
from uploader import Uploader

TICK_RE = re.compile(r"^frame_(\d+)\.json$")
CAM_RE = re.compile(r"^frame_(\d+)_c(\d+)\.(?:jpg|png)$")
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
        self.confirmer = Confirmer() if config.CONFIRM_VIEWS >= 2 else None
        cols, _, rows = config.DETECT_TILES.partition("x")
        self.tiles = {} if config.DETECT_TILES == "1x1" else {
            "detect_tiles": {"cols": int(cols), "rows": int(rows or 1), "band": config.DETECT_BAND}}
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
            # With two-view confirmation, detection never lists; confirmed items are listed separately.
            "dry_run": config.DRY_RUN or self.confirmer is not None,
            "min_box_px": config.MIN_BOX_PX,
            **self.tiles,
        }

    def process_tick(self, seq: int, meta_path: Path) -> int:
        meta = json.loads(meta_path.read_text())
        pose = Pose.from_meta(meta)
        captured_at = datetime.fromtimestamp(meta_path.stat().st_mtime, timezone.utc).isoformat()
        pngs = sorted(
            (int(m.group(2)), p)
            for p in config.INBOX_DIR.glob(f"frame_{seq:07d}_c*")
            if (m := CAM_RE.match(p.name))
        )
        to_send = []
        for cam, png in pngs:
            if cam not in config.SEND_CAMERAS:
                continue
            with Image.open(png) as img:
                img.load()
            send, reason = self.gate.check(cam, pose, img)
            if send:
                to_send.append((cam, png, reason))
                self.gate.mark_sent(cam, pose, img)
            else:
                log({"seq": seq, "camera": cam, "skipped": reason})
        # Cameras face different directions, so they never see the same item: send them together.
        with ThreadPoolExecutor(max_workers=max(1, len(to_send))) as pool:
            results = pool.map(
                lambda c: self.uploader.send(self.payload(c[1], pose, captured_at), key=f"{seq:07d}_c{c[0]}"), to_send)
            results = list(results)
        for (cam, png, reason), result in zip(to_send, results):
            where = [round(pose.x, 2), round(pose.y, 2), round(pose.heading_rad, 4)]
            if self.confirmer is None:
                print(f"[bridge] seq {seq} cam {cam} ({reason}) -> {summarize(result)}", flush=True)
                log({"seq": seq, "camera": cam, "reason": reason, "pose": where, "result": result})
                continue
            seen = result.get("identified") or [] if result["status"] == "ok" else []
            names = ", ".join(i.get("title", "?") for i in seen)
            print(f"[bridge] seq {seq} cam {cam} ({reason}) -> "
                  f"{'saw ' + names if seen else summarize(result)}", flush=True)
            log({"seq": seq, "camera": cam, "reason": reason, "pose": where, "result": result})
            with Image.open(png) as img:
                width = img.width
            for frame, item in self.confirmer.observe(pose, cam, png, width, seen):
                listing = self.uploader.send(
                    {**self.payload(frame, pose, captured_at), "dry_run": config.DRY_RUN,
                     "items": [{k: item[k] for k in ("box", "title", "description", "category", "color")}]},
                    key=f"{seq:07d}_c{cam}_confirmed")
                print(f"[bridge] seq {seq} cam {cam} confirmed '{item.get('title')}' in two views -> "
                      f"{summarize(listing)}", flush=True)
                log({"seq": seq, "camera": cam, "confirmed": item.get("title"), "pose": where, "result": listing})
        sent = len(to_send)
        for _, png in pngs:
            png.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        self.gate.save()
        return sent

    def drop_tick(self, seq: int, meta_path: Path) -> None:
        for p in config.INBOX_DIR.glob(f"frame_{seq:07d}_c*"):
            p.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)

    def run(self, once: bool = False) -> None:
        while True:
            ticks = self.pending_ticks()
            # When behind, only the newest view matters: older ticks show where the rover was.
            if config.SKIP_STALE and len(ticks) > 1:
                for seq, meta_path in ticks[:-1]:
                    self.drop_tick(seq, meta_path)
                    log({"seq": seq, "skipped": "stale tick"})
                print(f"[bridge] behind: skipped {len(ticks) - 1} stale tick(s), processing seq {ticks[-1][0]}", flush=True)
                ticks = ticks[-1:]
            for seq, meta_path in ticks:
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
