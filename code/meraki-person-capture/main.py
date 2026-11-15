"""
Meraki person-detection snapshot capture.

Runs one worker thread per camera. During the active window (07:00-18:00 local)
each thread grabs a snapshot every ~5s, runs YOLO person detection, and saves the
original image only when a person is found. One flat folder per camera.

The whole program stops cleanly when ANY of these happens:
  * a camera's folder reaches MAX_PHOTOS_PER_FOLDER (1200) photos,
  * you press Ctrl-C,
  * you create a file named STOP in this folder.

Saves are atomic (temp file -> os.replace), so stopping at any instant never
leaves a half-written image and never loses an already-saved photo.

Usage:
    python main.py            # run the scheduler (7am-6pm) until a stop condition
    python main.py --test     # one snapshot per camera right now, then exit
"""

import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import config
import detector
from meraki_client import capture_snapshot

# Single event every thread watches. Setting it = "shut everything down cleanly".
stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)-8s %(message)s")

    file_handler = RotatingFileHandler(
        config.LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console)


log = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def camera_folder(serial: str) -> Path:
    """Return (creating if needed) the flat output folder for one camera."""
    folder = config.OUTPUT_DIR / serial
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def count_photos(folder: Path) -> int:
    """Number of .jpg files currently in a camera folder."""
    return sum(1 for _ in folder.glob("*.jpg"))


def save_atomically(folder: Path, image_bytes: bytes) -> Path:
    """
    Write image_bytes to a uniquely named .jpg in `folder` atomically.
    Returns the final path.
    """
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    final_path = folder / f"{stamp}.jpg"
    tmp_path = folder / f".{stamp}.jpg.tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(image_bytes)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, final_path)  # atomic on Windows and macOS/Linux
    return final_path


def within_active_window(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return config.ACTIVE_START_HOUR <= now.hour < config.ACTIVE_END_HOUR


def seconds_until_active(now: datetime | None = None) -> float:
    """Seconds to sleep until the active window next begins."""
    now = now or datetime.now()
    target = now.replace(
        hour=config.ACTIVE_START_HOUR, minute=0, second=0, microsecond=0
    )
    # If we're already at or past today's start hour, the next start is tomorrow.
    if now >= target:
        target = target + timedelta(days=1)
    return max((target - now).total_seconds(), 0)


def interruptible_sleep(seconds: float) -> None:
    """Sleep, but wake immediately if a stop is requested."""
    stop_event.wait(timeout=max(seconds, 0))


# ---------------------------------------------------------------------------
# Per-camera worker
# ---------------------------------------------------------------------------
def camera_worker(serial: str) -> None:
    folder = camera_folder(serial)
    log.info("[%s] worker started -> %s", serial, folder)
    idle_logged = False

    # If this camera's folder is already full on startup, stop everything.
    if count_photos(folder) >= config.MAX_PHOTOS_PER_FOLDER:
        log.warning(
            "[%s] folder already has >= %d photos; requesting stop.",
            serial,
            config.MAX_PHOTOS_PER_FOLDER,
        )
        stop_event.set()

    while not stop_event.is_set():
        cycle_start = time.monotonic()

        if not within_active_window():
            if not idle_logged:
                wait = seconds_until_active()
                log.info(
                    "[%s] outside active window (%02d:00-%02d:00); sleeping ~%.0f min.",
                    serial,
                    config.ACTIVE_START_HOUR,
                    config.ACTIVE_END_HOUR,
                    wait / 60,
                )
                idle_logged = True
            # Re-check every 30s so we don't oversleep past the window start,
            # and so a stop request is honoured promptly.
            interruptible_sleep(30)
            continue

        idle_logged = False

        try:
            image_bytes = capture_snapshot(serial)
            if image_bytes and detector.detect_person(image_bytes):
                path = save_atomically(folder, image_bytes)
                n = count_photos(folder)
                log.info("[%s] person detected -> saved %s (%d total)", serial, path.name, n)
                if n >= config.MAX_PHOTOS_PER_FOLDER:
                    log.warning(
                        "[%s] reached %d photos; requesting program stop.",
                        serial,
                        config.MAX_PHOTOS_PER_FOLDER,
                    )
                    stop_event.set()
                    break
        except Exception as exc:  # noqa: BLE001 - one bad cycle must not kill the thread
            log.exception("[%s] unexpected error in cycle: %s", serial, exc)

        # Pace the loop to the target interval, accounting for time already spent.
        elapsed = time.monotonic() - cycle_start
        interruptible_sleep(config.CAPTURE_INTERVAL_SECONDS - elapsed)

    log.info("[%s] worker stopped. Final photo count: %d", serial, count_photos(folder))


# ---------------------------------------------------------------------------
# STOP-file watcher
# ---------------------------------------------------------------------------
def stop_file_watcher() -> None:
    while not stop_event.is_set():
        if config.STOP_FILE.exists():
            log.warning("STOP file detected; requesting program stop.")
            stop_event.set()
            break
        interruptible_sleep(1)


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------
def install_signal_handlers() -> None:
    def handler(signum, _frame):
        log.warning("Received signal %s; requesting program stop.", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, handler)
    try:
        signal.signal(signal.SIGTERM, handler)
    except (ValueError, AttributeError):
        pass  # SIGTERM may be unavailable on some Windows setups


# ---------------------------------------------------------------------------
# Test mode: one snapshot per camera, then exit
# ---------------------------------------------------------------------------
def run_test() -> None:
    log.info("TEST MODE: one snapshot per camera.")
    for serial in config.MERAKI_SERIALS:
        image_bytes = capture_snapshot(serial)
        if not image_bytes:
            log.error("[%s] FAILED to fetch snapshot (check key/serial/network).", serial)
            continue
        person = detector.detect_person(image_bytes)
        log.info(
            "[%s] snapshot OK (%d bytes); person detected: %s",
            serial,
            len(image_bytes),
            person,
        )
        if person:
            path = save_atomically(camera_folder(serial), image_bytes)
            log.info("[%s] saved test image -> %s", serial, path)
    log.info("TEST MODE complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    setup_logging()
    config.validate()

    # Clear a stale STOP file from a previous run so we don't stop instantly.
    if config.STOP_FILE.exists():
        try:
            config.STOP_FILE.unlink()
            log.info("Removed stale STOP file from a previous run.")
        except OSError:
            pass

    loaded = detector.load_model()
    log.info(
        "Ready. Cameras: %s | interval: %ds | window: %02d:00-%02d:00 | conf: %.2f | cap: %d | model: %s",
        ", ".join(config.MERAKI_SERIALS),
        config.CAPTURE_INTERVAL_SECONDS,
        config.ACTIVE_START_HOUR,
        config.ACTIVE_END_HOUR,
        config.CONFIDENCE_THRESHOLD,
        config.MAX_PHOTOS_PER_FOLDER,
        loaded,
    )

    if "--test" in sys.argv:
        run_test()
        return

    install_signal_handlers()

    threads = [threading.Thread(target=stop_file_watcher, name="stop-watch", daemon=True)]
    for serial in config.MERAKI_SERIALS:
        threads.append(
            threading.Thread(target=camera_worker, args=(serial,), name=f"cam-{serial}", daemon=True)
        )
    for t in threads:
        t.start()

    # Keep the main thread alive until a stop is requested, then join workers.
    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=1)
    except KeyboardInterrupt:
        stop_event.set()

    log.info("Stopping... waiting for camera threads to finish their current cycle.")
    for t in threads:
        t.join(timeout=config.SNAPSHOT_FETCH_TIMEOUT_SECONDS + 5)

    # Tidy up the STOP file if that's what triggered the shutdown.
    if config.STOP_FILE.exists():
        try:
            config.STOP_FILE.unlink()
        except OSError:
            pass

    log.info("All stopped. Goodbye.")


if __name__ == "__main__":
    main()
