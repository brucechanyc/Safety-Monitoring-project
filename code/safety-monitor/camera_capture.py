"""
Captures a still image from the Meraki camera.

Important: /camera/analytics/recent (used elsewhere in this project for
person detection) is a deprecated ANALYTICS endpoint - it only returns
zone person-counts, never image data. Getting an actual photo requires a
separate, two-step call to a DIFFERENT endpoint:

  1. POST /devices/{serial}/camera/generateSnapshot
     -> Meraki starts rendering a snapshot and immediately replies with
        202 Accepted + a JSON body: {"url": "...", "expiry": "..."}
        The url is NOT the image yet - it's a link to where the image
        will be once Meraki finishes generating it (usually a few
        seconds later).

  2. GET that url
     -> May 404 / not resolve for the first few seconds. Poll it with a
        short delay until it returns the actual JPEG.

Docs: https://developer.cisco.com/meraki/api-v1/generate-device-camera-snapshot/
"""

import time
from datetime import datetime
from pathlib import Path

import requests

import config


def request_snapshot() -> dict:
    """Step 1: ask Meraki to generate a snapshot. Returns {"url": ..., "expiry": ...}."""
    resp = requests.post(
        config.MERAKI_SNAPSHOT_URL,
        headers={"X-Cisco-Meraki-API-Key": config.MERAKI_API_KEY},
        timeout=config.REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def download_snapshot(snapshot_url: str) -> bytes:
    """Step 2: poll the snapshot url until the image is actually ready."""
    last_error = None
    for attempt in range(1, config.SNAPSHOT_MAX_RETRIES + 1):
        time.sleep(config.SNAPSHOT_RETRY_DELAY_SECONDS)
        try:
            resp = requests.get(snapshot_url, timeout=config.REQUEST_TIMEOUT)
            if resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("image/"):
                return resp.content
            last_error = f"HTTP {resp.status_code} (attempt {attempt}/{config.SNAPSHOT_MAX_RETRIES})"
        except requests.RequestException as e:
            last_error = f"{e} (attempt {attempt}/{config.SNAPSHOT_MAX_RETRIES})"

    raise RuntimeError(f"Snapshot never became available: {last_error}")


def capture_snapshot() -> Path:
    """
    Full flow: trigger a snapshot, wait for it, save it to SNAPSHOT_DIR.
    Returns the path of the saved image.
    """
    snapshot_info = request_snapshot()
    image_bytes = download_snapshot(snapshot_info["url"])

    out_dir = Path(config.SNAPSHOT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    out_path = out_dir / filename
    out_path.write_bytes(image_bytes)

    return out_path


if __name__ == "__main__":
    # Quick manual test: run `python camera_capture.py` on its own to confirm
    # your MERAKI_API_KEY / MERAKI_SERIAL in .env are correct before wiring
    # this into main.py's detection loop.
    print("Requesting snapshot...")
    try:
        path = capture_snapshot()
        print(f"Saved: {path}")
    except Exception as e:
        print(f"Failed: {e}")
