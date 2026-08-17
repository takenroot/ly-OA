"""兼容中文路径的 OpenCV 图片读写封装.

Windows 上 cv2.imread/imwrite 对非 ASCII 路径容易失败,
改用 np.fromfile + cv2.imdecode / cv2.imencode + ndarray.tofile.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def imread(path: str | Path) -> np.ndarray | None:
    """读取图片,支持中文路径."""
    buf = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def imwrite(path: str | Path, img: np.ndarray) -> bool:
    """写入图片,支持中文路径."""
    ext = Path(path).suffix.lower() or ".jpg"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        return False
    buf.tofile(str(path))
    return True
