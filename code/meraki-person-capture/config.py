"""
Configuration for the Meraki person-detection snapshot capture tool.

Secrets (API key, org id, camera serials) are NOT stored here. They live in a
`.env` file next to this script and are loaded at runtime. See `.env.example`.

Everything below is a plain tunable you can safely edit.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env that sits in the same folder as this file (works no matter what the
# current working directory is when the program is launched).
PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")


# ---------------------------------------------------------------------------
# Secrets (read from .env)
# ---------------------------------------------------------------------------
MERAKI_API_KEY = os.getenv("MERAKI_API_KEY", "").strip()
MERAKI_ORG_ID = os.getenv("MERAKI_ORG_ID", "").strip()

# MERAKI_SERIALS in .env is a comma-separated list, e.g.
#   MERAKI_SERIALS=Q2XX-AAAA-BBBB,Q2XX-CCCC-DDDD,Q2XX-EEEE-FFFF
MERAKI_SERIALS = [
    s.strip() for s in os.getenv("MERAKI_SERIALS", "").split(",") if s.strip()
]


# ---------------------------------------------------------------------------
# Capture behaviour
# ---------------------------------------------------------------------------
# Target seconds between the START of one capture cycle and the next, per camera.
CAPTURE_INTERVAL_SECONDS = 5

# Active window (local time, 24h). Captures only happen when
# ACTIVE_START_HOUR <= current hour < ACTIVE_END_HOUR. Outside it the program idles.
ACTIVE_START_HOUR = 7   # 07:00
ACTIVE_END_HOUR = 18    # 18:00 (captures stop the instant the clock hits 18:00)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
# Primary model weight to use. yolo26n = YOLO26 "nano" (fast). If this weight
# can't be loaded/downloaded, the code falls back to MODEL_FALLBACK.
MODEL_NAME = "yolo26n.pt"
MODEL_FALLBACK = "yolo11n.pt"

# Confidence threshold. Lower = catches more people but more false positives.
# 0.25 = "high recall" as requested.
CONFIDENCE_THRESHOLD = 0.25

# COCO class id for "person" is 0. We only care about people.
PERSON_CLASS_ID = 0


# ---------------------------------------------------------------------------
# Output / limits
# ---------------------------------------------------------------------------
# Root folder for saved photos. One flat sub-folder per camera serial is created
# inside it at runtime. The space in the name is intentional (matches the ask).
OUTPUT_DIR = PROJECT_DIR / "photo saved"

# When ANY camera's folder reaches this many photos, the whole program stops.
MAX_PHOTOS_PER_FOLDER = 1200

# Manual "end now" trigger: create a file with this name in the project folder.
STOP_FILE = PROJECT_DIR / "STOP"

# Log file (rotates so it can't grow without bound over multi-day runs).
LOG_FILE = PROJECT_DIR / "capture.log"


# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------
MERAKI_BASE_URL = "https://api.meraki.com/api/v1"

# The Meraki snapshot URL isn't ready the instant it's generated; it takes a few
# seconds to populate on their side. We poll it up to this long before giving up.
SNAPSHOT_FETCH_TIMEOUT_SECONDS = 15

# Per-HTTP-request timeout.
HTTP_TIMEOUT_SECONDS = 20


def validate() -> None:
    """Fail fast with a clear message if required secrets are missing."""
    missing = []
    if not MERAKI_API_KEY:
        missing.append("MERAKI_API_KEY")
    if not MERAKI_ORG_ID:
        missing.append("MERAKI_ORG_ID")
    if not MERAKI_SERIALS:
        missing.append("MERAKI_SERIALS")
    if missing:
        raise SystemExit(
            "Missing required setting(s): "
            + ", ".join(missing)
            + f"\nEdit the .env file at: {PROJECT_DIR / '.env'}\n"
            "(Copy .env.example to .env and fill in your values.)"
        )
