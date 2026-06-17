"""
RoyaleBot — YOLOv8 Training Script
===================================
Run this ONCE on a machine with a GPU (or Google Colab) after you have
labelled your dataset on Roboflow.

Quick-start
-----------
1.  Install deps:
        pip install ultralytics roboflow

2.  Export your Roboflow dataset as "YOLOv8" format and download it:
        from roboflow import Roboflow
        rf = Roboflow(api_key="YOUR_KEY")
        project = rf.workspace("YOUR_WORKSPACE").project("clash-royale-troops")
        dataset = project.version(1).download("yolov8")

3.  Run this script:
        python train_yolo.py --data path/to/data.yaml

4.  Copy the best weights to your VPS:
        C:\\models\\royale.pt

5.  The bot auto-loads it on next run — no other changes needed.

Recommended hardware
--------------------
- Google Colab (free T4 GPU) for training
- CPU inference is fine in the bot (YOLOv8-nano ~15ms on modern CPU)

Data collection
---------------
Set COLLECT_TRAINING_DATA = True in royale_bot_mumu.py.
The bot will save raw battle frames to C:\\yolo_dataset\\images\\train\\
Every 30 battle ticks (~6 seconds at normal loop speed).
Upload those frames to Roboflow for annotation.
Aim for 200+ labelled frames covering all troops you want to detect.

Roboflow annotation tips
------------------------
- Use the "Smart Polygon" tool (SAM-powered) — draws bounding boxes in 1 click
- Enable "Auto-Label" for troops that appear repeatedly
- Augmentations to enable: flip horizontal, ±15° rotation, brightness ±25%
- Split: 80% train / 10% val / 10% test
"""

import argparse
import os
from pathlib import Path


def train(data_yaml: str, epochs: int = 100, imgsz: int = 640,
          batch: int = 16, model: str = "yolov8n.pt", project: str = "runs/royale"):
    """Train YOLOv8-nano on the Clash Royale troop dataset."""
    from ultralytics import YOLO

    print(f"[train] Loading base model: {model}")
    yolo = YOLO(model)

    print(f"[train] Starting training — {epochs} epochs, imgsz={imgsz}, batch={batch}")
    results = yolo.train(
        data    = data_yaml,
        epochs  = epochs,
        imgsz   = imgsz,
        batch   = batch,
        project = project,
        name    = "royale_nano",
        # Good defaults for a small custom dataset
        patience    = 20,       # early stop if no improvement for 20 epochs
        lr0         = 0.01,
        lrf         = 0.01,
        momentum    = 0.937,
        weight_decay = 0.0005,
        warmup_epochs = 3,
        augment     = True,
        hsv_h       = 0.015,
        hsv_s       = 0.7,
        hsv_v       = 0.4,
        flipud      = 0.0,      # CR maps don't flip vertically
        fliplr      = 0.5,
        mosaic      = 1.0,
        mixup       = 0.0,
    )

    best = Path(project) / "royale_nano" / "weights" / "best.pt"
    print(f"\n[train] Done! Best weights: {best}")
    print(f"[train] Copy to VPS:  C:\\models\\royale.pt")
    return results


def export(weights: str, format: str = "onnx"):
    """Export a trained model (optional — PyTorch .pt works fine in the bot)."""
    from ultralytics import YOLO
    yolo = YOLO(weights)
    yolo.export(format=format, imgsz=640, simplify=True)
    print(f"[export] Exported {weights} → {format}")


def validate(weights: str, data_yaml: str):
    """Run validation metrics on the trained model."""
    from ultralytics import YOLO
    yolo = YOLO(weights)
    metrics = yolo.val(data=data_yaml)
    print(f"[val] mAP50={metrics.box.map50:.3f}  mAP50-95={metrics.box.map:.3f}")
    return metrics


def collect_check(data_dir: str = r"C:\yolo_dataset\images\train"):
    """Show how many training frames have been collected so far."""
    p = Path(data_dir)
    if not p.exists():
        print(f"[collect] No frames yet — set COLLECT_TRAINING_DATA = True in the bot")
        return
    frames = list(p.glob("*.png")) + list(p.glob("*.jpg"))
    print(f"[collect] {len(frames)} frames in {data_dir}")
    if len(frames) < 200:
        print(f"[collect] Recommended: at least 200 labelled frames before training")
    else:
        print(f"[collect] Ready to label! Upload to Roboflow for annotation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RoyaleBot YOLO trainer")
    sub = parser.add_subparsers(dest="cmd")

    t = sub.add_parser("train", help="Train the model")
    t.add_argument("--data",   required=True, help="Path to data.yaml from Roboflow")
    t.add_argument("--epochs", type=int, default=100)
    t.add_argument("--imgsz",  type=int, default=640)
    t.add_argument("--batch",  type=int, default=16)
    t.add_argument("--model",  default="yolov8n.pt", help="Base weights (nano by default)")

    v = sub.add_parser("val", help="Validate a trained model")
    v.add_argument("--weights", required=True)
    v.add_argument("--data",    required=True)

    e = sub.add_parser("export", help="Export to ONNX or other format")
    e.add_argument("--weights", required=True)
    e.add_argument("--format",  default="onnx")

    sub.add_parser("check", help="Count collected training frames")

    args = parser.parse_args()

    if args.cmd == "train":
        train(args.data, args.epochs, args.imgsz, args.batch, args.model)
    elif args.cmd == "val":
        validate(args.weights, args.data)
    elif args.cmd == "export":
        export(args.weights, args.format)
    elif args.cmd == "check":
        collect_check()
    else:
        parser.print_help()
