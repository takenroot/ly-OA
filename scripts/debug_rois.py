"""诊断:把表格区域 + 字段 ROI + OCR 结果画到图上,肉眼区分"框切错"vs"OCR 读错".

用法:
  uv run python scripts/debug_rois.py --input ./示例车间A/2026年8月11日
  uv run python scripts/debug_rois.py --input ... --out ./debug_out
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from PIL import Image, ImageDraw

from src.config import Config
from src.image_io import imread, imwrite
from src.ocr import recognize_cells
from src.preprocess import find_table_zone
from src.template import crop_cells, load_template

GREEN = (0, 200, 0)
RED = (0, 0, 230)
BLUE = (230, 160, 0)


def annotate(img: np.ndarray, template: dict, zone, raw, threshold: float) -> np.ndarray:
    H, W = img.shape[:2]
    vis = img.copy()
    if zone:
        y_top, y_bot = zone
        cv2.line(vis, (0, y_top), (W, y_top), BLUE, 3)
        cv2.line(vis, (0, y_bot), (W, y_bot), BLUE, 3)
        zone_h = y_bot - y_top
        for name, f in template["fields"].items():
            y_center = y_top + int(f["y_th"] * zone_h)
            h_px = int(f["h_th"] * zone_h)
            x_center = int(f["x_w"] * W)
            w_px = int(f["w_w"] * W)
            x0, y0 = x_center - w_px // 2, y_center - h_px // 2
            x1, y1 = x0 + w_px, y0 + h_px
            text, conf = raw.get(name, ("", 0.0))
            color = GREEN if conf >= threshold and text else RED
            cv2.rectangle(vis, (x0, y0), (x1, y1), color, 2)
    # cv2.putText 不支持中文,转 PIL 写字段名 + OCR 文本
    pil = Image.fromarray(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    if zone:
        y_top, y_bot = zone
        zone_h = y_bot - y_top
        for name, f in template["fields"].items():
            y_center = y_top + int(f["y_th"] * zone_h)
            h_px = int(f["h_th"] * zone_h)
            x_center = int(f["x_w"] * W)
            w_px = int(f["w_w"] * W)
            x0, y0 = x_center - w_px // 2, y_center - h_px // 2
            text, conf = raw.get(name, ("", 0.0))
            color = GREEN if conf >= threshold and text else RED
            # PIL 是 RGB,cv2 颜色是 BGR,换一下
            rgb = (color[2], color[1], color[0])
            draw.text((x0, max(0, y0 - 28)), f"{name} {conf:.2f}", fill=rgb)
            draw.text((x0, y0 + int(f['h_th'] * zone_h) + 4), text[:24], fill=rgb)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("./debug_rois"))
    args = ap.parse_args()

    cfg = Config.load()
    template = load_template(cfg.template_path)
    args.out.mkdir(parents=True, exist_ok=True)

    images = sorted(
        f for f in args.input.iterdir()
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
    )
    for p in images:
        img = imread(p)
        if img is None:
            print(f"{p.name}: 读图失败")
            continue
        zone = find_table_zone(img)
        if zone is None:
            print(f"{p.name}: 表格区域未检出")
            imwrite(str(args.out / f"{p.stem}_nozone.jpg"), img)
            continue
        cells = crop_cells(img, template)
        raw = recognize_cells(cells)
        vis = annotate(img, template, zone, raw, cfg.confidence_threshold)
        out = args.out / f"{p.stem}_roi.jpg"
        imwrite(str(out), vis)
        print(f"{p.name}: zone_y={zone[0]}~{zone[1]} → {out.name}")
        for name, (text, conf) in raw.items():
            mark = " " if conf >= cfg.confidence_threshold and text else "X"
            print(f"  {mark} {name}: {text!r} ({conf:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
