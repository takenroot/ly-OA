"""按 template.json 切 ROI,坐标基于"表格 y 范围"的比例(0-1)."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .preprocess import find_table_zone


def load_template(path: Path) -> dict:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def crop_cells(img: np.ndarray, template: dict) -> dict[str, np.ndarray]:
    """每个字段坐标:
      - y_th, h_th: 相对表格 y 范围的比例 (0-1, 0=表格顶, 1=表格底)
      - x_w, w_w: 相对图片宽度的比例 (0-1)
    """
    H, W = img.shape[:2]
    zone = find_table_zone(img)
    if zone is None:
        return {}
    y_top, y_bot = zone
    zone_h = y_bot - y_top
    if zone_h <= 0:
        return {}
    out: dict[str, np.ndarray] = {}
    for name, f in template["fields"].items():
        y_center = y_top + int(f["y_th"] * zone_h)
        h_px = int(f["h_th"] * zone_h)
        x_center = int(f["x_w"] * W)
        w_px = int(f["w_w"] * W)
        x0 = max(0, x_center - w_px // 2)
        y0 = max(0, y_center - h_px // 2)
        x1 = min(W, x0 + w_px)
        y1 = min(H, y0 + h_px)
        if x1 <= x0 or y1 <= y0:
            out[name] = np.zeros((1, 1, 3), dtype=np.uint8)
        else:
            out[name] = img[y0:y1, x0:x1].copy()
    return out
