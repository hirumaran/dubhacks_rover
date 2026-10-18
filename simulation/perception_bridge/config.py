"""Settings for the perception bridge. Secrets come from simulation/perception_bridge/.env."""
from __future__ import annotations

import math
import os
from pathlib import Path

BRIDGE_ROOT = Path(__file__).resolve().parent
SIM_ROOT = BRIDGE_ROOT.parent

_ENV_PATH = BRIDGE_ROOT / ".env"
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


# identify-found-items endpoint and its shared secret (see edge-functions/README.md)
IDENTIFY_URL = os.environ.get(
    "IDENTIFY_URL", "https://salsusdncqbtrkcqxdkg.supabase.co/functions/v1/identify-found-items"
)
INGEST_SECRET = os.environ.get("ROVER_INGEST_SECRET", "")
ROVER_ID = os.environ.get("ROVER_ID", "")            # rovers.id of this rover
IS_DEMO = _flag("IS_DEMO", "true")                   # simulator finds stay out of real listings
DRY_RUN = _flag("DRY_RUN", "false")                  # identify only; nothing is listed
LOCATION_LABEL = os.environ.get("LOCATION_LABEL", "UW Seattle campus, rover patrol")
# Cameras whose images are sent. Benches sit beside the route, so the side cameras (1 = left,
# 3 = right; the rover's narrow perception cameras) look straight at them; "0,1,2,3" sends all four.
SEND_CAMERAS = {int(c) for c in os.environ.get("SEND_CAMERAS", "1,3").split(",") if c.strip()}
# Detections whose longer side is under this many pixels are ignored as too far away. On the
# 1920x1440 perception cameras a bench item 2-3 m off the route is ~65-250 px.
MIN_BOX_PX = int(os.environ.get("MIN_BOX_PX", "48"))
# Detection tiles: "<cols>x<rows>" over the band of the image where items on benches and the
# ground appear (fractions of the height). The rover's narrow 1920x1440 perception cameras make a
# bench item ~70x250 px; tiling still gives the detector a closer look. "1x1" = whole frame, one call.
DETECT_TILES = os.environ.get("DETECT_TILES", "2x1")
DETECT_BAND = [float(v) for v in os.environ.get("DETECT_BAND", "0.15,0.85").split(",")]

# Change gate: a camera image is sent only when its view has changed this much since that
# camera last sent one.
MOVE_MIN_M = float(os.environ.get("MOVE_MIN_M", "1.5"))
TURN_MIN_DEG = float(os.environ.get("TURN_MIN_DEG", "20"))
IMAGE_DIFF_MIN = int(os.environ.get("IMAGE_DIFF_MIN", "12"))  # bits differing in a 64-bit image hash

INBOX_POLL_S = float(os.environ.get("INBOX_POLL_S", "1.0"))
# When behind, jump to the newest view (live use). false = process every view in order, falling
# behind but never missing one (scoring runs, or a rover that outpaces the detector).
SKIP_STALE = _flag("SKIP_STALE", "true")
RETRY_EVERY_S = float(os.environ.get("RETRY_EVERY_S", "30"))
REQUEST_TIMEOUT_S = float(os.environ.get("REQUEST_TIMEOUT_S", "120"))

INBOX_DIR = Path(os.environ.get("PERCEPTION_INBOX", str(BRIDGE_ROOT / "inbox")))
STATE_DIR = Path(os.environ.get("PERCEPTION_STATE", str(BRIDGE_ROOT / "state")))
REPORTS_DIR = Path(os.environ.get("PERCEPTION_REPORTS", str(BRIDGE_ROOT / "reports")))
MISSION_PATH = Path(os.environ.get("PERCEPTION_MISSION", str(SIM_ROOT / "maps" / "mission.json")))

# Camera mounts on CampusScout: camera_i faces heading + i * 90 degrees.
CAMERA_MOUNT_YAW = [0.0, math.pi / 2, math.pi, 3 * math.pi / 2]
