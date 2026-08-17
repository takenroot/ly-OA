"""车间配置：不同车间的小票版式（标签别名、边界、编号格式、日期来源）."""
from __future__ import annotations

import json
from pathlib import Path

from .config import base_dir

DEFAULT_PROFILE = {
    "name": "默认",
    "aliases": {
        "编号": ["编号"],
        "车号": ["车号"],
        "物资": ["物资"],
        "毛重": ["毛重"],
        "检毛": ["检毛"],
        "皮重": ["皮重"],
        "检皮": ["检皮"],
        "净重": ["净重"],
    },
    "boundaries": ["发货", "收货"],
    "number_format": "xmg",
    "date_field": "编号",
}


class WorkshopProfile:
    """车间版式配置，供 locate / validate 使用."""

    def __init__(self, data: dict) -> None:
        self.name: str = data.get("name", "未命名")
        self.aliases: dict[str, list[str]] = data.get("aliases", {})
        self.boundaries: list[str] = data.get("boundaries", [])
        self.number_format: str = data.get("number_format", "xmg")
        self.date_field: str = data.get("date_field", "编号")

    def labels(self) -> tuple[str, ...]:
        return tuple(self.aliases.keys())

    def all_label_texts(self) -> list[str]:
        """所有可能出现在小票上的标签文本（含边界）."""
        texts: list[str] = []
        for ts in self.aliases.values():
            texts.extend(ts)
        texts.extend(self.boundaries)
        return texts


def load_profile(workshop_name: str) -> WorkshopProfile:
    """按车间名加载配置文件；找不到时回退默认配置."""
    path = base_dir() / "workshops" / f"{workshop_name}.json"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return WorkshopProfile(data)
    # 回退默认配置：打印可见警告,帮助排查打包/部署时 workshops/ 目录缺失
    import warnings
    warnings.warn(
        f"未找到车间版式配置 {path}，将使用默认配置。"
        f"如 {workshop_name} 小票格式特殊,请检查 workshops/ 目录是否随 exe 释放。",
        stacklevel=2,
    )
    return WorkshopProfile(DEFAULT_PROFILE)
