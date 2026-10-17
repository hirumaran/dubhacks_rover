"""Central configuration for the perception pipeline. All secrets come from .env."""
from dataclasses import dataclass, field
from pathlib import Path
import os

PERCEPTION_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PERCEPTION_ROOT.parent

_ENV_PATH = PERCEPTION_ROOT / ".env"
if _ENV_PATH.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_PATH)
    except ImportError:
        for line in _ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Supabase (REQUIRED for real pushes; everything else degrades gracefully)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "sightings-crops")

# Isaac model
ISAAC_HF_PATH = os.environ.get("ISAAC_HF_PATH", "PerceptronAI/Isaac-0.2-1B")
ISAAC_BACKEND = os.environ.get("ISAAC_BACKEND", "auto")  # auto|transformers|sdk|mock
ISAAC_MAX_SIDE = int(os.environ.get("ISAAC_MAX_SIDE", "640"))  # downscale before VLM (pixels)
ISAAC_DEVICE = os.environ.get("ISAAC_DEVICE", "auto")  # auto|mps|cuda|cpu
ISAAC_ENABLE_THINKING = os.environ.get("ISAAC_ENABLE_THINKING", "0") == "1"

# Ingest cadence (the flowchart's "camera every 5s")
FRAME_INTERVAL_S = float(os.environ.get("FRAME_INTERVAL_S", "5.0"))
INBOX_POLL_S = float(os.environ.get("INBOX_POLL_S", "1.0"))

# Tracker tuning
GONE_AFTER_S = float(os.environ.get("GONE_AFTER_S", "8.0"))       # unseen => Gone style event
MOVE_MIN_M = float(os.environ.get("MOVE_MIN_M", "0.15"))         # moved threshold
MATCH_IOU_MIN = float(os.environ.get("MATCH_IOU_MIN", "0.20"))
MATCH_TEXT_MIN = float(os.environ.get("MATCH_TEXT_MIN", "0.35"))
MAX_RANGE_M = float(os.environ.get("MAX_RANGE_M", "6.0"))        # sanity clamp on geotag range

# Webots -> perception bridge
# Overridable so tests / second instances never share runtime state:
#   PERCEPTION_INBOX_DIR, PERCEPTION_STATE_DIR, PERCEPTION_REPORTS_DIR
INBOX_DIR = Path(os.environ.get("PERCEPTION_INBOX_DIR", PERCEPTION_ROOT / "inbox"))
OUTBOX_DIR = Path(os.environ.get("PERCEPTION_STATE_DIR", PERCEPTION_ROOT / "state"))
REPORTS_DIR = Path(os.environ.get("PERCEPTION_REPORTS_DIR", PERCEPTION_ROOT / "reports"))

# Where the controller-side writer looks (teammate's machine).
# Controller only activates when PERCEPTION_INBOX env var is set to the inbox path.
CONTROLLER_HOOK_ENV = "PERCEPTION_INBOX"

# Fleet identity + student kiosk (QR codes land on PUBLIC_APP_URL)
ROVER_ID = os.environ.get("ROVER_ID", "mk1")
ROVER_DISPLAY_NAME = os.environ.get("ROVER_DISPLAY_NAME", "Campus Scout MK1")
PUBLIC_APP_URL = os.environ.get("PUBLIC_APP_URL", "http://localhost:8787").rstrip("/")
KIOSK_PORT = int(os.environ.get("KIOSK_PORT", "8787"))
HEARTBEAT_STALE_S = float(os.environ.get("HEARTBEAT_STALE_S", "45"))
LOST_ITEMS_BUCKET = os.environ.get("LOST_ITEMS_BUCKET", "lost-item-queries")
KIOSK_DIR = PERCEPTION_ROOT / "kiosk"
# Minimum match_agent score before a report is auto-marked 'matched'.
MATCH_MIN_SCORE = float(os.environ.get("MATCH_MIN_SCORE", "0.3"))


@dataclass
class CameraSpec:
    idx: int
    mount_yaw: float            # rotation about z in the rover body frame (rad)
    width: int = 320
    height: int = 240
    hfov: float = 1.64
    local_offset: tuple = (-0.015, 0.0, 0.21)   # mounting point on rover (m)


def cameras() -> "list[CameraSpec]":
    proto_mounts = [0.0, 1.57079632679, 3.14159265359, 4.71238898]
    return [CameraSpec(idx=i, mount_yaw=y) for i, y in enumerate(proto_mounts)]


def supabase_ready() -> bool:
    return bool(SUPABASE_URL and (SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY))
