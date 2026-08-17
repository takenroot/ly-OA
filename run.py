"""exe 打包入口:崩溃兜底——异常写运行日志 + errors.log,不让 exe 静默失败.

无参数或 --gui 时启动配置界面;其余参数走 CLI.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from src.config import Config, base_dir, ensure_resources
from src.log import log_run


CLI_HELP_TEXT = (
    "ly-OA 命令行参数\n\n"
    "ly-oa.exe\n"
    "  无参数时打开配置界面。\n\n"
    "ly-oa.exe --day YYYY-MM-DD\n"
    "  手动跑指定日期，扫描 config.ini 中所有数据源。\n\n"
    "ly-oa.exe --auto\n"
    "  跑昨天，用于 Windows 定时任务。\n\n"
    "ly-oa.exe --input <目录> [--date YYYY-MM-DD]\n"
    "  单目录调试，日期优先用 --date，否则从目录名解析。\n\n"
    "ly-oa.exe --gui\n"
    "  强制打开配置界面。\n\n"
    "ly-oa.exe --help\n"
    "  显示本帮助。"
)


def _show_help_window() -> int:
    """windowed exe 模式下用 tk 弹窗显示 --help."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("ly-OA 帮助", CLI_HELP_TEXT)
        root.destroy()
    except Exception:
        # 如果连 tk 都起不来，尽力写到 errors.log
        err = base_dir() / "errors.log"
        with err.open("a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} =====\n")
            f.write(CLI_HELP_TEXT)
    return 0


def _crash_log() -> None:
    err = base_dir() / "errors.log"
    with err.open("a", encoding="utf-8") as f:
        f.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} =====\n")
        f.write(traceback.format_exc())
    try:  # config 本身可能也坏了,尽力而为
        log_run(Config.load().log_file, "unknown", "-", "-",
                status="异常(见 errors.log)")
    except Exception:
        pass


def _hide_console() -> None:
    """Windows 下双击 exe 启动 GUI 时隐藏命令行窗口,CLI 模式不调用."""
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def _attach_console() -> None:
    """windowed exe 被命令行调用时,附加到父控制台,让 print 输出可见."""
    try:
        import ctypes
        import os
        kernel32 = ctypes.windll.kernel32
        # ATTACH_PARENT_PROCESS = -1
        if kernel32.AttachConsole(-1):
            # 重定向 stdout/stderr 到控制台
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
            sys.stderr = sys.stdout
    except Exception:
        pass


def _launch_gui() -> int:
    from src.gui import main as gui_main
    _hide_console()
    try:
        gui_main()
        return 0
    except Exception:
        _crash_log()
        traceback.print_exc()
        return 1


def _launch_cli(argv: list[str] | None = None) -> int:
    from src.main import main
    try:
        return main(argv)
    except Exception:
        _crash_log()
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # windowed exe 模式下 stdout 不可用，--help 用弹窗显示
    if "--help" in sys.argv or "-h" in sys.argv:
        if getattr(sys, "frozen", False):
            sys.exit(_show_help_window())
        # 非打包模式让 argparse 自己打印帮助

    # 无参数(双击 exe)或显式 --gui 启动配置界面
    gui_mode = len(sys.argv) == 1 or "--gui" in sys.argv
    if gui_mode:
        _hide_console()  # 在窗口创建前隐藏,避免黑框闪烁

    # exe 首次运行时,从打包资源释放 config.ini / template.json / 参考 xlsx
    ensure_resources()

    if gui_mode:
        sys.exit(_launch_gui())

    # windowed exe 被命令行调用时,附加到父控制台,恢复日志输出
    if getattr(sys, "frozen", False):
        _attach_console()
    sys.exit(_launch_cli(sys.argv[1:]))
