"""图像预处理:用水平线密度找出表格所在的 y 范围,作为模板裁剪的锚点."""
from __future__ import annotations

import cv2
import numpy as np


def find_table_zone(img: np.ndarray) -> tuple[int, int] | None:
    """返回表格 y 范围 (y_top, y_bottom). 用 Canny + Hough 找水平线,
    投影到 y 轴找连续高密度区,跳过 y<0.20*H 的标题区.
    """
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=60, minLineLength=80, maxLineGap=20,
    )
    if lines is None:
        return None
    proj = np.zeros(H, dtype=np.float64)
    for ln in lines:
        if ln.ndim == 2:
            x1, y1, x2, y2 = int(ln[0][0]), int(ln[0][1]), int(ln[0][2]), int(ln[0][3])
        else:
            x1, y1, x2, y2 = int(ln[0]), int(ln[1]), int(ln[2]), int(ln[3])
        length = float(np.hypot(x2 - x1, y2 - y1))
        if abs(x2 - x1) > abs(y2 - y1) * 2:  # 横向线
            proj[y1] += length
    # 平滑
    proj_smooth = np.convolve(proj, np.ones(20) / 20, mode="same")
    max_val = proj_smooth.max()
    if max_val <= 0:
        return None
    valid = proj_smooth > max_val * 0.3
    # 跳过 y < 0.20*H 和 y > 0.85*H
    valid[: int(0.20 * H)] = False
    valid[int(0.85 * H):] = False
    ys = np.where(valid)[0]
    if len(ys) == 0:
        return None
    return int(ys[0]), int(ys[-1])


def _auto_rotate(img: np.ndarray) -> np.ndarray:
    """检测表格水平线,若整体倾斜则旋转校正."""
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=100, maxLineGap=20)
    if lines is None or len(lines) < 3:
        return img
    angles = []
    for ln in lines:
        x1, y1, x2, y2 = (int(ln[0][0]), int(ln[0][1]), int(ln[0][2]), int(ln[0][3])) if ln.ndim == 2 else (int(ln[0]), int(ln[1]), int(ln[2]), int(ln[3]))
        if abs(x2 - x1) > 20:
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if abs(angle) < 10:  # 只考虑小角度倾斜
                angles.append(angle)
    if not angles:
        return img
    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:
        return img
    center = (W // 2, H // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(255, 255, 255))
    return rotated


def _enhance_contrast(img: np.ndarray) -> np.ndarray:
    """CLAHE 局部对比度增强,对阴影/光线不均有效."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def rotate_image(img: np.ndarray, angle: int) -> np.ndarray:
    """按 0/90/180/270 度旋转图片,用于尝试不同方向 OCR."""
    if angle == 0:
        return img
    if angle == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"不支持的角度: {angle}(只支持 0/90/180/270)")


def preprocess_image(img: np.ndarray) -> np.ndarray:
    """OCR 前预处理:旋转校正 + 对比度增强 + 适当放大."""
    img = _auto_rotate(img)
    img = _enhance_contrast(img)
    H, W = img.shape[:2]
    if H < 1200:
        scale = 1200 / H
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    return img


# 兼容旧 API: find_table_top_y
def find_table_top_y(img: np.ndarray) -> int | None:
    zone = find_table_zone(img)
    return zone[0] if zone else None
