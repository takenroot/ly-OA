"""RapidOCR 包装:把每个字段子图识别成 (text, confidence) 元组."""
from __future__ import annotations

import os

# 优化 B:限制 ONNX Runtime 线程数,避免单张 OCR 占满所有 CPU 核心
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

import numpy as np
from rapidocr_onnxruntime import RapidOCR


_engine: RapidOCR | None = None


def get_engine() -> RapidOCR:
    global _engine
    if _engine is None:
        _engine = RapidOCR()
    return _engine


def recognize_cells(cells: dict[str, np.ndarray]) -> dict[str, tuple[str, float]]:
    """对每个字段子图跑 OCR,返回 {字段名: (识别文本, 置信度)}.

    若字段无识别结果,返回 ("", 0.0).同格子内多段文字合并(从左到右拼接),
    取整体置信度(各段平均).
    """
    engine = get_engine()
    out: dict[str, tuple[str, float]] = {}
    for name, crop in cells.items():
        if crop is None or crop.size == 0:
            out[name] = ("", 0.0)
            continue
        result, _elapsed = engine(crop)
        if not result:
            out[name] = ("", 0.0)
            continue
        # 按 x 坐标排序(从左到右)
        def x_center(r):
            box = r[0]
            xs = [p[0] for p in box]
            return sum(xs) / len(xs)
        sorted_result = sorted(result, key=x_center)
        # 拼接所有文字
        text = " ".join(str(r[1]).strip() for r in sorted_result if str(r[1]).strip())
        conf = sum(float(r[2]) for r in sorted_result) / len(sorted_result)
        out[name] = (text, float(conf))
    return out
