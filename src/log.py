"""统一日志:单文件文本日志,包含每次运行汇总与每张图片明细."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def _ensure_logger(path: Path) -> logging.Logger:
    """为指定日志文件创建一个 logger(不带默认 handler,避免重复输出到控制台)."""
    # 用日志文件路径做 logger 名,保证同一文件复用同一 logger
    name = f"lyoa_{path.resolve()}"
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 已添加过 handler 直接复用
    if logger.handlers:
        return logger

    logger.propagate = False
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return logger


def log_run(
    log_file: Path,
    mode: str,
    target: str,
    src_dirs: list[Path] | str,
    n_img: int | str = "",
    ok: int | str = "",
    fail: int | str = "",
    n_yellow: int | str = "",
    out: str = "",
    status: str = "OK",
) -> None:
    """记录一次运行的汇总信息."""
    src = ";".join(str(d) for d in src_dirs) if isinstance(src_dirs, list) else src_dirs
    msg = (
        f"[RUN] mode={mode} date={target} src=\"{src}\" "
        f"images={n_img} ok={ok} fail={fail} yellow={n_yellow} "
        f"out=\"{out}\" status={status}"
    )
    _ensure_logger(log_file).info(msg)


def log_image(
    log_file: Path,
    image: str,
    status: str,
    message: str = "",
    manual_path: str = "",
) -> None:
    """记录单张图片的处理结果."""
    parts = [f"[IMG] {image} {status}"]
    if message:
        parts.append(message)
    if manual_path:
        parts.append(f"-> \"{manual_path}\"")
    _ensure_logger(log_file).info(" ".join(parts))


def log_error(log_file: Path, message: str) -> None:
    """记录异常或错误信息."""
    _ensure_logger(log_file).error(f"[ERR] {message}")
