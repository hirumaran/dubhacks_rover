"""Perception bridge: optional controller add-on that mirrors the rover's
cameras into the perception bridge inbox (default 5s cadence).

Activation: set PERCEPTION_INBOX to the inbox dir before launching Webots.
Without the env var this module is never imported and the rover controller
behaves exactly as before.

Contract written per tick (one seq = one Webots sim moment):
  frame_<seq:07d>_c<i>.jpg   camera image (JPEG, written natively by Webots); i = 1 left, 3 right
  frame_<seq:07d>.json       {"sim_time_s","gps","heading_rad","seq","cameras":[{"idx":i}]}
Only what a real rover could sense is exported: camera pixels and its own GPS
and compass pose. Simulator ground truth (Recognition objects) is deliberately
left out, so everything downstream is pure vision. The bridge service
(simulation/perception_bridge) does the rest; the controller writes only and
never blocks driving.
"""
import json
import math
import os
import uuid
from pathlib import Path

INTERVAL_S = float(os.environ.get("FRAME_INTERVAL_S", "5.0"))
JPEG_QUALITY = int(os.environ.get("FRAME_JPEG_QUALITY", "90"))
WARMUP_S = 1.0


class PerceptionHook:
    def __init__(self, cameras, gps, compass, inbox_path, mounts=None):
        self.mounts = mounts or {}
        self.cameras = cameras  # {camera index: Camera}; 1 = left, 3 = right, as the bridge numbers them
        self.gps = gps
        self.compass = compass
        self.inbox = Path(inbox_path)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.next_at = INTERVAL_S
        self.sample_ms=int(gps.getSamplingPeriod()) or 64
        self.armed=False
        # Arm the high-resolution cameras shortly before each scheduled snapshot, at the
        # GPS/compass sampling rate. An old 256 ms frame paired with a current heading is
        # inaccurate during turns and corrupts triangulation.
        for camera in self.cameras.values():camera.disable()
        self.seq = 0
        self.session_id=uuid.uuid4().hex
        self.clean_inbox()
        print(f"PERCEPTION_BRIDGE ACTIVE -> {self.inbox} every {INTERVAL_S}s", flush=True)

    def clean_inbox(self):
        for p in self.inbox.iterdir():
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass

    def maybe(self, now: float):
        if now < self.next_at-max(.256,self.sample_ms*.003):return
        if not self.armed:
            for camera in self.cameras.values():camera.enable(self.sample_ms)
            self.armed=True
            return
        if now+1e-7 < self.next_at:return
        self.next_at += INTERVAL_S
        p = self.gps.getValues()
        if any(not math.isfinite(q) for q in p):
            return
        north = self.compass.getValues()
        heading = math.atan2(north[0], north[1])
        self.seq += 1
        seq = self.seq

        cam_entries = []
        for i, cam in self.cameras.items():
            # Webots encodes natively; a pure-Python encoder would stall the controller at 1280x960.
            if cam.saveImage(str(self.inbox / f"frame_{seq:07d}_c{i}.jpg"), JPEG_QUALITY) != 0:
                continue
            cam_entries.append({"idx": i, "width": cam.getWidth(), "height": cam.getHeight(), "hfov": cam.getFov(), "offset_m": self.mounts.get(str(i), [0,0,0])})

        for camera in self.cameras.values():camera.disable()
        self.armed=False
        meta = {
            "sim_time_s": round(float(now), 2),
            "gps": [round(v, 4) for v in p],
            "heading_rad": round(heading, 4),
            "seq": seq,
            "session_id": self.session_id,
            "sampling_period_ms": self.sample_ms,
            "cameras": cam_entries,
        }
        meta_path = self.inbox / f"frame_{seq:07d}.json"
        tmp = self.inbox / f".meta_{seq}.tmp"
        tmp.write_text(json.dumps(meta, indent=1))
        os.replace(tmp, meta_path)  # atomic: service never reads half-written meta
        print(f"PERCEPTION_BRIDGE seq {seq} | {len(cam_entries)} cams -> inbox | sim {now:.1f}s", flush=True)
