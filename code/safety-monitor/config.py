import os
from dotenv import load_dotenv

load_dotenv()

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678").rstrip("/")
PPE_WEBHOOK_PATH = os.getenv("PPE_WEBHOOK_PATH", "/webhook/ppe-check").rstrip("/")
HAZARD_WEBHOOK_PATH = os.getenv("HAZARD_WEBHOOK_PATH", "/webhook/hazard-check").rstrip("/")
CHECKS_WEBHOOK_PATH = os.getenv("CHECKS_WEBHOOK_PATH", "/webhook/checks").rstrip("/")
REPORT_WEBHOOK_PATH = os.getenv("REPORT_WEBHOOK_PATH", "/webhook-test/send-report").rstrip("/")


MERAKI_API_KEY = os.getenv("MERAKI_API_KEY", "")
MERAKI_SERIAL = os.getenv("MERAKI_SERIAL", "")
MERAKI_URL = f"https://api.meraki.com/api/v1/devices/{MERAKI_SERIAL}/camera/analytics/recent"

# Snapshot capture (POST triggers a photo; response gives a URL to fetch it from)
MERAKI_SNAPSHOT_URL = f"https://api.meraki.com/api/v1/devices/{MERAKI_SERIAL}/camera/generateSnapshot"

# Where captured images get saved
SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "snapshots")

# The snapshot image isn't ready the instant generateSnapshot returns -
# Meraki needs a few seconds to render and upload it. These control how
# long we're willing to wait/retry before giving up on one capture.
SNAPSHOT_MAX_RETRIES = 6
SNAPSHOT_RETRY_DELAY_SECONDS = 3

# Full URL 
PPE_URL = N8N_BASE_URL + PPE_WEBHOOK_PATH
HAZARD_URL = N8N_BASE_URL + HAZARD_WEBHOOK_PATH
CHECKS_URL = N8N_BASE_URL + CHECKS_WEBHOOK_PATH
REPORT_URL = N8N_BASE_URL + REPORT_WEBHOOK_PATH

# Time before it stops waiting for response
REQUEST_TIMEOUT = 50

# Time between scans:
SCAN_INTERVAL_SECONDS = 5

# Working Hours
WORK_START = 9
WORK_END = 18