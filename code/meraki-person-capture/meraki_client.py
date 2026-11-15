"""
Thin Meraki Dashboard API client for grabbing a single camera snapshot.

Meraki's snapshot flow is two steps:
  1. POST .../camera/generateSnapshot  -> returns JSON with a temporary image URL
  2. GET that URL                       -> the image (hosted on S3). It is NOT
     ready the instant it's generated, so we poll it with a short backoff until
     it returns HTTP 200.

Every call is defensive: on any error it logs and returns None instead of
raising, so the capture loop can just skip a frame and continue.
"""

import logging
import time

import requests

import config

log = logging.getLogger("meraki")


def _headers() -> dict:
    return {
        "X-Cisco-Meraki-API-Key": config.MERAKI_API_KEY,
        "Accept": "application/json",
    }


def _generate_snapshot_url(serial: str) -> str | None:
    """Ask Meraki to generate a snapshot; return the temporary image URL or None."""
    url = f"{config.MERAKI_BASE_URL}/devices/{serial}/camera/generateSnapshot"
    try:
        resp = requests.post(
            url, headers=_headers(), timeout=config.HTTP_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        log.warning("[%s] generateSnapshot request failed: %s", serial, exc)
        return None

    if resp.status_code == 429:
        # Rate limited. Honour Retry-After if present, else brief pause.
        retry_after = float(resp.headers.get("Retry-After", "2"))
        log.warning("[%s] rate limited (429); backing off %.1fs", serial, retry_after)
        time.sleep(retry_after)
        return None

    if resp.status_code not in (200, 201, 202):
        log.warning(
            "[%s] generateSnapshot HTTP %s: %s",
            serial,
            resp.status_code,
            resp.text[:200],
        )
        return None

    try:
        snapshot_url = resp.json().get("url")
    except ValueError:
        log.warning("[%s] generateSnapshot returned non-JSON body", serial)
        return None

    if not snapshot_url:
        log.warning("[%s] generateSnapshot response had no 'url'", serial)
        return None

    return snapshot_url


def _fetch_image(serial: str, snapshot_url: str) -> bytes | None:
    """Poll the snapshot URL until the image is available, then return its bytes."""
    deadline = time.monotonic() + config.SNAPSHOT_FETCH_TIMEOUT_SECONDS
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            resp = requests.get(snapshot_url, timeout=config.HTTP_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            log.debug("[%s] image fetch attempt %d failed: %s", serial, attempt, exc)
            time.sleep(1)
            continue

        if resp.status_code == 200 and resp.content:
            ctype = resp.headers.get("Content-Type", "")
            if "image" in ctype or resp.content[:3] == b"\xff\xd8\xff":
                return resp.content
            log.debug("[%s] fetched non-image content-type '%s'", serial, ctype)

        # 404 while the snapshot is still being produced is normal; wait and retry.
        time.sleep(1)

    log.warning(
        "[%s] snapshot image not ready within %ss",
        serial,
        config.SNAPSHOT_FETCH_TIMEOUT_SECONDS,
    )
    return None


def capture_snapshot(serial: str) -> bytes | None:
    """
    Full capture for one camera: generate + fetch.
    Returns the JPEG bytes, or None if anything went wrong (already logged).
    """
    snapshot_url = _generate_snapshot_url(serial)
    if not snapshot_url:
        return None
    return _fetch_image(serial, snapshot_url)
