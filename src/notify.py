"""Windows 桌面通知封装.

用于:
- GUI 手动跑完弹出完成通知
- 定时任务(--auto)跑完弹出通知

不依赖额外系统服务,winotify 是纯 Python 实现,可随 PyInstaller 打包.
"""
from __future__ import annotations

import logging
from pathlib import Path


logger = logging.getLogger(__name__)


# 缓存图标路径,避免重复查找
_icon_path: Path | None | object = object()  # type: ignore[assignment]


def _find_icon() -> Path | None:
    """尝试找一个.ico文件作为通知图标,没有就用默认."""
    global _icon_path
    if _icon_path is not object():
        return _icon_path  # type: ignore[return-value]

    # PyInstaller 打包后 exe 同目录优先
    meipass = getattr(__import__("sys"), "_MEIPASS", None)
    if meipass:
        candidates = [Path(meipass) / "ly-oa.ico", Path(meipass) / "icon.ico"]
    else:
        base = Path(__file__).resolve().parent.parent
        candidates = [base / "ly-oa.ico", base / "icon.ico"]

    icon = None
    for c in candidates:
        if c.exists():
            icon = c
            break
    _icon_path = icon
    return icon


def notify(title: str, message: str, duration: str = "short") -> None:
    """发送 Windows  toast 通知.

    :param title: 通知标题
    :param message: 通知正文
    :param duration: short / long
    """
    try:
        from winotify import Notification
    except Exception as e:
        logger.debug("winotify 未安装或导入失败: %s", e)
        return

    try:
        toast = Notification(
            app_id="ly-OA",
            title=title,
            msg=message,
            duration=duration,
            icon=str(_find_icon()) if _find_icon() else None,
        )
        toast.show()
    except Exception as e:
        logger.debug("发送通知失败: %s", e)
