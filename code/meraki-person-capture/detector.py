"""
Person detection with Ultralytics YOLO.

The model is loaded once and shared across all camera threads. Ultralytics
inference is not guaranteed thread-safe, so `detect_person` serialises calls
with a lock. For three cameras every ~5s the cost of serialising is negligible.
"""

import io
import logging
import threading

from PIL import Image
from ultralytics import YOLO

import config

log = logging.getLogger("detector")

_model = None
_model_lock = threading.Lock()


def load_model() -> str:
    """
    Load the YOLO model once. Tries MODEL_NAME first, then MODEL_FALLBACK.
    Returns the name of the weight that actually loaded. Raises if none work.
    """
    global _model
    last_err = None
    for name in (config.MODEL_NAME, config.MODEL_FALLBACK):
        try:
            log.info("Loading YOLO model '%s'...", name)
            _model = YOLO(name)
            log.info("Loaded YOLO model '%s'.", name)
            return name
        except Exception as exc:  # noqa: BLE001 - want to try the fallback on anything
            last_err = exc
            log.warning("Could not load model '%s': %s", name, exc)
    raise SystemExit(f"Failed to load any YOLO model. Last error: {last_err}")


def detect_person(image_bytes: bytes) -> bool:
    """
    Return True if the image contains at least one 'person' above the configured
    confidence threshold. Any failure is logged and treated as 'no detection'
    so a bad frame never crashes the caller.
    """
    if _model is None:
        raise RuntimeError("Model not loaded; call load_model() first.")

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not decode snapshot image: %s", exc)
        return False

    try:
        with _model_lock:
            results = _model.predict(
                source=image,
                classes=[config.PERSON_CLASS_ID],
                conf=config.CONFIDENCE_THRESHOLD,
                verbose=False,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("YOLO inference failed: %s", exc)
        return False

    for result in results:
        if result.boxes is not None and len(result.boxes) > 0:
            return True
    return False
