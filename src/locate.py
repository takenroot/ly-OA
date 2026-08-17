"""标签锚定字段提取:整图 OCR 一次,靠单据上印刷的 label 定位值.

为什么不用 template.json 比例坐标:
  - 编号行可能在表格上方,比例坐标够不到
  - 表格下边界检测不稳定,比例整体漂移
label 锚定对这两个结构性问题免疫。template.json 裁剪降级为 label 找不到时的兜底。
"""
from __future__ import annotations

import numpy as np

from .ocr import get_engine
from .workshop import WorkshopProfile

# 保留旧版默认标签,供未传 profile 时回退
_DEFAULT_LABELS = ("编号", "车号", "物资", "毛重", "检毛", "皮重", "检皮", "净重")
_DEFAULT_BOUNDARIES = ("发货", "收货")


def _norm(s: str) -> str:
    return s.replace(" ", "").replace(":", "").replace("：", "")


def _props(box) -> dict:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return {
        "x0": min(xs), "x1": max(xs),
        "yc": sum(ys) / len(ys), "h": max(ys) - min(ys),
    }


def extract_fields(img: np.ndarray,
                   profile: WorkshopProfile | None = None) -> dict[str, tuple[str, float]]:
    """整图 OCR → {标准字段名: (text, conf)}.

    若传入 workshop profile,则按该车间的标签别名与边界提取；否则回退默认标签。
    """
    engine = get_engine()
    result, _ = engine(img)
    if not result:
        return {}
    items = []
    for box, text, conf in result:
        it = {"text": str(text), "conf": float(conf)}
        it.update(_props(box))
        items.append(it)

    if profile is None:
        labels = {k: (k,) for k in _DEFAULT_LABELS}
        boundaries = _DEFAULT_BOUNDARIES
    else:
        labels = profile.aliases
        boundaries = tuple(profile.boundaries)

    # 每标准字段选一个 label 框:在所有别名中找规范化后含别名文本,且残余字符最少、conf 最高的
    label_items: dict[str, dict] = {}
    for std_name, alias_list in labels.items():
        cands: list[dict] = []
        for alias in alias_list:
            cands.extend(it for it in items if alias in _norm(it["text"]))
        if cands:
            def _residual_len(it: dict) -> int:
                norm = _norm(it["text"])
                return min(
                    len(norm.replace(a, ""))
                    for a in alias_list if a in norm
                )
            cands.sort(key=lambda it: (_residual_len(it), -it["conf"]))
            label_items[std_name] = cands[0]

    # 边界 label 只用于右边界,不输出
    boundary_items: dict[str, dict] = {}
    for boundary in boundaries:
        cands = [it for it in items if boundary in _norm(it["text"])]
        if cands:
            cands.sort(key=lambda it: (len(_norm(it["text"]).replace(boundary, "")), -it["conf"]))
            boundary_items[boundary] = cands[0]

    all_labels = {**label_items, **boundary_items}

    out: dict[str, tuple[str, float]] = {}
    for std_name in labels.keys():
        li = label_items.get(std_name)
        if li is None:
            continue
        band = max(li["h"], 1.0)
        # 值的左界:OCR 框常与 label 框轻微重叠,按 label 高度回退 0.8 容忍重叠
        x_left = li["x1"] - 0.8 * li["h"]
        same_row = [it for it in items if abs(it["yc"] - li["yc"]) <= band]
        # 右侧同行最近的下一个 label(含边界) = 值的右边界,防止吞掉隔壁列
        right_labels = [
            l for n, l in all_labels.items()
            if n != std_name and l in same_row and l["x0"] > x_left
        ]
        x_right = min((l["x0"] for l in right_labels), default=float("inf"))
        right_ids = {id(l) for l in right_labels}
        vals = [
            it for it in same_row
            if it is not li and id(it) not in right_ids
            and it["x0"] > x_left and it["x1"] <= x_right + 5
        ]
        vals.sort(key=lambda it: it["x0"])
        parts = []
        # label 框自身可能吞了值,如 "毛重48560" → 残余 "48560"
        matched_alias = next((a for a in labels[std_name] if a in _norm(li["text"])), "")
        remainder = _norm(li["text"]).replace(matched_alias, "") if matched_alias else ""
        if remainder:
            parts.append(remainder)
        parts.extend(v["text"] for v in vals)
        text = " ".join(parts)
        conf = sum(v["conf"] for v in vals) / len(vals) if vals else li["conf"]
        out[std_name] = (text, float(conf))
    return out
