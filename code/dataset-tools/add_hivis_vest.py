#!/usr/bin/env python3
"""
Batch-add a bright yellow hi-vis vest to people in photos using Google's
Gemini "Nano Banana" image model (gemini-2.5-flash-image).

For each image in INPUT_DIR:
  1. Classify it (gemini-2.5-flash): is a person present? is any of their body
     visible? is the body fully or only partially in frame?
  2. Skip rules:
       - no person detected          -> skip
       - person but no body visible   -> skip  (e.g. headshot / face only)
       - half / partial body visible  -> edit, fitting the vest to what's shown
       - full body visible            -> edit
  3. Edit (gemini-2.5-flash-image): add a bright yellow hi-vis vest to the
     person, changing nothing else in the image.
  4. Save the result to OUTPUT_DIR.

Requirements:
    pip install google-genai
    set an API key in the environment variable GEMINI_API_KEY

Usage:
    python add_hivis_vest.py
    python add_hivis_vest.py --input ./photos --output ./done
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    sys.exit(
        "The google-genai package is not installed.\n"
        "Install it with:  pip install google-genai"
    )

# --- Defaults ---------------------------------------------------------------
DEFAULT_INPUT = "feed"          # folder to read photos from
DEFAULT_OUTPUT = "output"       # folder to write edited photos to
CLASSIFY_MODEL = "gemini-2.5-flash"
IMAGE_MODEL = "gemini-2.5-flash-image"   # "Nano Banana"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds, multiplied by attempt number

# --- Prompts ----------------------------------------------------------------
CLASSIFY_PROMPT = """You are analysing a single photo. Respond with ONLY a JSON object, no prose.

Fields:
- "person_present": true if at least one human person is visible, else false.
- "body_visible": true if any part of a person's torso/upper body is visible
  (shoulders, chest, or back). false if only a face/head, only hands, or only
  legs/feet are shown, or no person at all.
- "coverage": one of "none", "partial", "full".
    - "none"    : no usable body visible.
    - "partial" : only part of the body/torso is in frame (e.g. waist-up,
                  cropped, or turned away).
    - "full"    : the full or nearly-full body is visible.

Example: {"person_present": true, "body_visible": true, "coverage": "partial"}
"""

EDIT_PROMPT = (
    "Add a bright yellow high-visibility safety vest (hi-vis vest) onto the "
    "person in this image, worn correctly over their existing clothing on the "
    "torso. The vest must be vivid safety yellow with realistic reflective "
    "silver stripes, fitting naturally to the person's body, pose and lighting. "
    "If only part of the person's body is visible in the frame, only add the "
    "portion of the vest that fits within the visible area and matches the crop. "
    "Do NOT change anything else in the image: keep the background, other "
    "objects, the person's face, hair, skin, pose, and all non-torso clothing "
    "exactly as they are. Preserve the original image resolution and framing. "
    "Return only the edited image."
)


def log(msg: str) -> None:
    print(msg, flush=True)


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def classify_image(client: genai.Client, img_bytes: bytes, mime: str) -> dict:
    """Return a dict with person_present, body_visible, coverage."""
    resp = client.models.generate_content(
        model=CLASSIFY_MODEL,
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type=mime),
            CLASSIFY_PROMPT,
        ],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    text = (resp.text or "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Be conservative: if we cannot parse, treat as unusable so we skip.
        log(f"    ! could not parse classifier output: {text!r}")
        return {"person_present": False, "body_visible": False, "coverage": "none"}
    return {
        "person_present": bool(data.get("person_present", False)),
        "body_visible": bool(data.get("body_visible", False)),
        "coverage": str(data.get("coverage", "none")).lower(),
    }


def edit_image(client: genai.Client, img_bytes: bytes, mime: str):
    """Call Nano Banana to add the vest; return (out_bytes, out_mime) or None."""
    resp = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type=mime),
            EDIT_PROMPT,
        ],
    )
    candidates = getattr(resp, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return inline.data, (inline.mime_type or "image/png")
    return None


def with_retries(fn, *args, what: str = "call"):
    """Run fn with simple retry/backoff on transient errors."""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001 - surface any API/network error
            last_err = e
            wait = RETRY_BACKOFF * attempt
            log(f"    ! {what} failed (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                log(f"      retrying in {wait}s...")
                time.sleep(wait)
    raise last_err


def output_path_for(src: Path, out_dir: Path, out_mime: str) -> Path:
    ext = mimetypes.guess_extension(out_mime) or ".png"
    if ext == ".jpe":
        ext = ".jpg"
    return out_dir / f"{src.stem}_hivis{ext}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Add hi-vis vests to people in photos.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="input folder (default: %(default)s)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="output folder (default: %(default)s)")
    parser.add_argument("--overwrite", action="store_true", help="re-process images even if an output already exists")
    parser.add_argument("--limit", type=int, default=0, help="process at most N images (0 = no limit)")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("Set your API key first, e.g.:\n  setx GEMINI_API_KEY \"your-key\"   (then reopen the terminal)")

    in_dir = Path(args.input)
    out_dir = Path(args.output)
    if not in_dir.is_dir():
        sys.exit(f"Input folder not found: {in_dir.resolve()}")
    out_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=api_key)

    images = sorted(p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not images:
        log(f"No images found in {in_dir.resolve()}")
        return 0

    if args.limit and args.limit > 0:
        images = images[: args.limit]
        log(f"Limiting to first {len(images)} image(s).")

    log(f"Found {len(images)} image(s) to process in {in_dir.resolve()}\n")
    stats = {"edited": 0, "skipped": 0, "errors": 0}

    for i, src in enumerate(images, 1):
        log(f"[{i}/{len(images)}] {src.name}")

        # Skip if already done (unless --overwrite).
        existing = list(out_dir.glob(f"{src.stem}_hivis.*"))
        if existing and not args.overwrite:
            log("    - already processed, skipping (use --overwrite to redo)")
            stats["skipped"] += 1
            continue

        try:
            img_bytes = src.read_bytes()
            mime = guess_mime(src)

            verdict = with_retries(classify_image, client, img_bytes, mime, what="classify")
            log(f"    classify: {verdict}")

            if not verdict["person_present"]:
                log("    - no person detected -> skip")
                stats["skipped"] += 1
                continue
            if not verdict["body_visible"] or verdict["coverage"] == "none":
                log("    - person's body not visible -> skip")
                stats["skipped"] += 1
                continue

            # partial or full -> edit (the prompt handles fitting to the crop).
            result = with_retries(edit_image, client, img_bytes, mime, what="edit")
            if not result:
                log("    ! model returned no image -> skip")
                stats["errors"] += 1
                continue

            out_bytes, out_mime = result
            dest = output_path_for(src, out_dir, out_mime)
            dest.write_bytes(out_bytes)
            log(f"    + saved {dest.name}")
            stats["edited"] += 1

        except Exception as e:  # noqa: BLE001
            log(f"    ! error processing {src.name}: {e}")
            stats["errors"] += 1

    log(f"\nDone. edited={stats['edited']} skipped={stats['skipped']} errors={stats['errors']}")
    log(f"Output folder: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
