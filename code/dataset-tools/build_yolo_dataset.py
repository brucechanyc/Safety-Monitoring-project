#!/usr/bin/env python3
"""
Build a YOLO training dataset from the vested and non-vested photos.

Classes (whole-person boxes):
    0 = person_no_vest   (from the `original/` folder)
    1 = person_vest      (from the `output/`  folder, hi-vis added)

Person boxes are auto-detected with a pretrained Ultralytics YOLO model
(COCO 'person' class, id 0). Each detected person in an image is written as a
YOLO label line, tagged with the class implied by the image's source folder.
Images where no person is detected are kept with an empty label file
(valid YOLO "background" samples).

Output layout (Ultralytics standard):
    yolo_dataset/
        images/train/  images/val/
        labels/train/  labels/val/
        data.yaml

Usage:
    python build_yolo_dataset.py
    python build_yolo_dataset.py --model yolo11s.pt --conf 0.3 --val-frac 0.2
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    sys.exit("ultralytics not installed. Run:  pip install ultralytics")


def pick_device() -> str:
    """Use Apple Silicon GPU (mps) or CUDA if available, else CPU."""
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
CLASS_NAMES = ["person_no_vest", "person_vest"]  # index == class id
COCO_PERSON = 0  # 'person' class id in the pretrained COCO model


def collect(folder: Path, class_id: int) -> list[tuple[Path, int]]:
    if not folder.is_dir():
        print(f"  ! source folder missing, skipping: {folder}")
        return []
    items = [
        (p, class_id)
        for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in IMG_EXTS
    ]
    print(f"  {folder.name}: {len(items)} images -> class {class_id} ({CLASS_NAMES[class_id]})")
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vest-dir", default="output", help="hi-vis (person_vest) images")
    ap.add_argument("--novest-dir", default="original", help="no-vest (person_no_vest) images")
    ap.add_argument("--out", default="yolo_dataset", help="dataset output folder")
    ap.add_argument("--model", default="yolo11m.pt", help="pretrained detector for person boxes")
    ap.add_argument("--conf", type=float, default=0.35, help="person detection confidence threshold")
    ap.add_argument("--batch", type=int, default=16, help="images per inference batch (lower if you hit GPU memory errors)")
    ap.add_argument("--val-frac", type=float, default=0.2, help="fraction held out for validation")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print("Collecting source images:")
    items = collect(Path(args.novest_dir), 0) + collect(Path(args.vest_dir), 1)
    if not items:
        sys.exit("No source images found.")

    # Reproducible, stratified-ish split (shuffle whole set; folders are balanced enough).
    random.seed(args.seed)
    random.shuffle(items)
    n_val = int(len(items) * args.val_frac)
    val_items = items[:n_val]
    train_items = items[n_val:]
    print(f"\nTotal {len(items)} images -> train {len(train_items)} / val {len(val_items)}")

    out = Path(args.out)
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    device = pick_device()
    print(f"\nLoading detector: {args.model}  (device: {device})")
    model = YOLO(args.model)

    stats = {"train": [0, 0, 0], "val": [0, 0, 0]}  # [images, persons, empty]

    def run_split(split_items, split_name):
        done = 0
        total = len(split_items)
        for i in range(0, total, args.batch):
            batch = split_items[i:i + args.batch]
            paths = [str(p.resolve()) for p, _ in batch]
            # Results are returned in the same order as the input paths.
            results = model.predict(
                source=paths, conf=args.conf,
                classes=[COCO_PERSON], device=device, verbose=False,
            )
            for (src, cls), r in zip(batch, results):
                dst_img = out / f"images/{split_name}" / src.name
                shutil.copy(src, dst_img)

                lines = []
                if r.boxes is not None and len(r.boxes) > 0:
                    for xc, yc, w, h in r.boxes.xywhn.tolist():
                        lines.append(f"{cls} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
                label_path = out / f"labels/{split_name}" / (src.stem + ".txt")
                label_path.write_text("\n".join(lines))

                stats[split_name][0] += 1
                stats[split_name][1] += len(lines)
                if not lines:
                    stats[split_name][2] += 1
                done += 1
            print(f"  [{split_name}] {done}/{total} processed")
        print(f"  [{split_name}] finished: {done} images")

    print("\nDetecting persons and writing labels...")
    run_split(train_items, "train")
    run_split(val_items, "val")

    # data.yaml
    yaml_path = out / "data.yaml"
    yaml_path.write_text(
        f"path: {out.resolve().as_posix()}\n"
        f"train: images/train\n"
        f"val: images/val\n\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names:\n"
        + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASS_NAMES))
    )

    print("\n=== Dataset summary ===")
    for split in ("train", "val"):
        imgs, persons, empty = stats[split]
        print(f"  {split}: {imgs} images, {persons} person boxes, {empty} background (no person)")
    print(f"\ndata.yaml -> {yaml_path.resolve()}")
    print(f"Dataset root -> {out.resolve()}")
    print("\nTrain with:\n  yolo detect train data="
          f"{yaml_path.resolve().as_posix()} model=yolo11m.pt epochs=100 imgsz=640")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
