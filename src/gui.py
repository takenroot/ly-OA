"""极简配置 GUI:双击 exe 打开,配置数据源根目录、定时任务与手动执行.

日报默认输出到各数据源目录(车间/日期)下;centralized 日报_dir 在配置中保留但不在 UI 暴露."""
from __future__ import annotations

import configparser
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .config import Config, base_dir
from .notify import notify

DEFAULT_TASK_NAME = "收料单日报"
DEFAULT_TASK_TIME = "08:30"


class ConfigApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ly-OA 配置")
        self.root.geometry("600x720")
        self.root.resizable(False, False)

        self.cfg_path = base_dir() / "config.ini"
        self.cp = configparser.ConfigParser()
        self._load_config()

        # 手动运行相关的状态
        self._running_proc: subprocess.Popen | None = None
        self._running_lock = threading.Lock()

        self._build_ui()
        self._refresh_inputs()

    def _load_config(self) -> None:
        if self.cfg_path.exists():
            self.cp.read(self.cfg_path, encoding="utf-8")
        else:
            self._create_default_config()

    def _create_default_config(self) -> None:
        self.cp["paths"] = {
            "reference_xlsx": "./参考模板/固废填埋日统计表0809.xlsx",
            "template": "./template.json",
            "log_dir": "./logs",
            "input_roots": "./示例车间A, ./示例车间B",
        }
        self.cp["ocr"] = {"confidence_threshold": "0.85"}
        self.cp["driver"] = {"default_driver_name": ""}

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}

        # 标题
        tk.Label(self.root, text="ly-OA 配置", font=("Microsoft YaHei", 14, "bold")).pack(pady=12)

        # 数据源根目录
        frame = tk.LabelFrame(self.root, text="数据源根目录", font=("Microsoft YaHei", 9))
        frame.pack(fill="both", expand=False, **pad)

        self.input_list = tk.Listbox(frame, height=4, font=("Microsoft YaHei", 9))
        self.input_list.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=self.input_list.yview)
        scrollbar.pack(side="right", fill="y", pady=8)
        self.input_list.config(yscrollcommand=scrollbar.set)

        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill="x", padx=8, pady=(0, 4))
        tk.Button(btn_frame, text="添加", command=self._add_input_root).pack(side="left", padx=(0, 6))
        tk.Button(btn_frame, text="删除", command=self._remove_input_root).pack(side="left")

        tk.Label(
            frame,
            text="提示:程序会扫描每个根目录下的 \"2026年8月11日\" 这类子目录,每天一个文件夹。",
            fg="gray", font=("Microsoft YaHei", 8), anchor="w", justify="left",
        ).pack(fill="x", padx=8, pady=(0, 8))

        # 保存按钮 + 使用说明 + 帮助
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="保存配置", command=self._save_config, bg="#4a90d9", fg="white",
                  font=("Microsoft YaHei", 10, "bold"), width=14).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="使用说明", command=self._open_help,
                  font=("Microsoft YaHei", 10), width=12).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="帮助", command=self._show_cli_help,
                  font=("Microsoft YaHei", 10), width=10).pack(side="left")

        # 定时任务
        task_frame = tk.LabelFrame(self.root, text="定时任务", font=("Microsoft YaHei", 9))
        task_frame.pack(fill="x", **pad)

        self.task_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(task_frame, text="启用定时任务", variable=self.task_enabled,
                       font=("Microsoft YaHei", 9)).pack(anchor="w", padx=8, pady=(8, 0))

        time_frame = tk.Frame(task_frame)
        time_frame.pack(fill="x", padx=8, pady=6)
        tk.Label(time_frame, text="执行时间:", font=("Microsoft YaHei", 9)).pack(side="left")
        self.task_hour = ttk.Combobox(time_frame, values=[f"{h:02d}" for h in range(24)], width=5, state="readonly")
        self.task_hour.pack(side="left", padx=(6, 2))
        tk.Label(time_frame, text=":", font=("Microsoft YaHei", 9)).pack(side="left")
        self.task_minute = ttk.Combobox(time_frame, values=[f"{m:02d}" for m in range(0, 60, 5)], width=5, state="readonly")
        self.task_minute.pack(side="left", padx=(2, 6))

        tk.Button(task_frame, text="应用", command=self._apply_task).pack(anchor="w", padx=8, pady=(0, 8))

        # 手动执行
        manual_frame = tk.LabelFrame(self.root, text="手动执行", font=("Microsoft YaHei", 9))
        manual_frame.pack(fill="x", **pad)

        date_frame = tk.Frame(manual_frame)
        date_frame.pack(fill="x", padx=8, pady=(8, 6))
        tk.Label(date_frame, text="日期:", font=("Microsoft YaHei", 9)).pack(side="left")
        self.date_entry = tk.Entry(date_frame, font=("Microsoft YaHei", 9), width=14)
        self.date_entry.pack(side="left", padx=(6, 6))
        self.date_entry.insert(0, (date.today() - timedelta(days=1)).isoformat())
        tk.Label(date_frame, text="格式:2026-08-11", fg="gray",
                 font=("Microsoft YaHei", 8)).pack(side="left")

        run_btn_frame = tk.Frame(manual_frame)
        run_btn_frame.pack(fill="x", padx=8, pady=(0, 6))
        self.run_yesterday_btn = tk.Button(
            run_btn_frame, text="跑昨天", command=self._run_yesterday,
            bg="#5cb85c", fg="white", font=("Microsoft YaHei", 9, "bold"), width=12,
        )
        self.run_yesterday_btn.pack(side="left", padx=(0, 8))
        self.run_day_btn = tk.Button(
            run_btn_frame, text="跑指定日期", command=self._run_selected_day,
            bg="#5cb85c", fg="white", font=("Microsoft YaHei", 9, "bold"), width=14,
        )
        self.run_day_btn.pack(side="left")

        # 实时日志显示
        tk.Label(manual_frame, text="运行日志(最近 80 行):", fg="gray",
                 font=("Microsoft YaHei", 8), anchor="w").pack(fill="x", padx=8)
        self.log_text = ScrolledText(
            manual_frame, height=8, state="disabled",
            font=("Consolas", 9), wrap=tk.WORD,
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.root, textvariable=self.status_var, anchor="w", font=("Microsoft YaHei", 9),
                 fg="gray").pack(fill="x", side="bottom", padx=12, pady=(0, 8))

        # 初始化时间
        hour, minute = DEFAULT_TASK_TIME.split(":")
        self.task_hour.set(hour)
        self.task_minute.set(minute)
        self._refresh_task_status()

    def _refresh_inputs(self) -> None:
        self.input_list.delete(0, "end")
        roots = [p.strip() for p in self.cp["paths"].get("input_roots", "").split(",") if p.strip()]
        for r in roots:
            self.input_list.insert("end", r)

    def _to_config_path(self, abs_path: str) -> str:
        """把用户选择的绝对路径尽量转成 ./相对路径,便于移植."""
        try:
            p = Path(abs_path).resolve()
            base = base_dir().resolve()
            rel = p.relative_to(base)
            return f"./{rel.as_posix()}"
        except ValueError:
            return abs_path

    def _add_input_root(self) -> None:
        d = filedialog.askdirectory(title="选择数据源根目录")
        if not d:
            return
        path = self._to_config_path(d)
        self.input_list.insert("end", path)

    def _remove_input_root(self) -> None:
        idx = self.input_list.curselection()
        if idx:
            self.input_list.delete(idx)

    def _save_config(self) -> None:
        roots = [self.input_list.get(i) for i in range(self.input_list.size())]
        self.cp["paths"]["input_roots"] = ", ".join(roots)
        # 日报_dir 不在 UI 暴露，保留原值（若存在）

        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cfg_path.open("w", encoding="utf-8") as f:
            self.cp.write(f)
        self.status_var.set(f"配置已保存到 {self.cfg_path}")

    def _open_help(self) -> None:
        help_path = base_dir() / "使用说明.txt"
        if not help_path.exists():
            messagebox.showwarning("提示", f"未找到 {help_path}")
            return
        try:
            os.startfile(str(help_path))
        except Exception as e:
            messagebox.showerror("错误", f"无法打开使用说明: {e}")

    def _show_cli_help(self) -> None:
        """弹出命令行参数帮助."""
        help_text = (
            "ly-OA 命令行参数\n\n"
            "ly-oa.exe\n"
            "  无参数时打开本配置界面。\n\n"
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
        messagebox.showinfo("帮助", help_text)

    def _refresh_task_status(self) -> None:
        exists = self._task_exists()
        self.task_enabled.set(exists)
        status = "已启用" if exists else "未启用"
        self.status_var.set(f"定时任务状态: {status}")

    def _task_exists(self) -> bool:
        try:
            result = subprocess.run(
                ["schtasks", "/query", "/tn", DEFAULT_TASK_NAME, "/fo", "list"],
                capture_output=True, text=True, encoding="gbk", check=False,
            )
            return result.returncode == 0 and DEFAULT_TASK_NAME in result.stdout
        except Exception:
            return False

    def _apply_task(self) -> None:
        exe_path = self._get_exe_path()
        if self.task_enabled.get():
            time_str = f"{self.task_hour.get()}:{self.task_minute.get()}"
            cmd = [
                "schtasks", "/create", "/tn", DEFAULT_TASK_NAME,
                "/tr", f'"{exe_path}" --auto',
                "/sc", "daily", "/st", time_str, "/f",
            ]
            action = "创建"
        else:
            cmd = ["schtasks", "/delete", "/tn", DEFAULT_TASK_NAME, "/f"]
            action = "删除"

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="gbk", check=False)
            if result.returncode == 0:
                self.status_var.set(f"定时任务{action}成功")
            else:
                err = result.stderr.strip() or result.stdout.strip()
                self.status_var.set(f"定时任务{action}失败: {err}")
                messagebox.showerror("错误", f"定时任务{action}失败:\n{err}")
        except Exception as e:
            self.status_var.set(f"定时任务{action}失败: {e}")
            messagebox.showerror("错误", str(e))

    def _get_exe_path(self) -> str:
        if getattr(sys, "frozen", False):
            return str(Path(sys.executable).resolve())
        # 开发模式:定位到打包后的 exe 或当前解释器脚本
        exe = base_dir() / "dist" / "ly-oa.exe"
        if exe.exists():
            return str(exe.resolve())
        return str((base_dir() / "run.py").resolve())

    # ------------------------------------------------------------------
    # 手动执行逻辑
    # ------------------------------------------------------------------

    def _is_running(self) -> bool:
        with self._running_lock:
            return self._running_proc is not None and self._running_proc.poll() is None

    def _set_running(self, running: bool) -> None:
        """切换按钮可用状态."""
        state = "disabled" if running else "normal"
        self.run_yesterday_btn.config(state=state)
        self.run_day_btn.config(state=state)

    def _append_log(self, text: str) -> None:
        """线程安全地追加日志到显示区."""
        def _do():
            self.log_text.config(state="normal")
            self.log_text.insert("end", text)
            self.log_text.see("end")
            # 限制最大行数
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 80:
                self.log_text.delete("1.0", f"{lines - 80}.0")
            self.log_text.config(state="disabled")
        self.root.after(0, _do)

    def _clear_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _run_yesterday(self) -> None:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, yesterday)
        self._run_for_date(yesterday)

    def _run_selected_day(self) -> None:
        date_str = self.date_entry.get().strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            messagebox.showwarning("提示", "日期格式应为 YYYY-MM-DD，例如 2026-08-11")
            return
        self._run_for_date(date_str)

    def _run_for_date(self, date_str: str) -> None:
        if self._is_running():
            messagebox.showwarning("提示", "已有任务正在运行，请等待完成")
            return

        # 先保存配置，确保用最新配置跑
        self._save_config()

        exe_path = self._get_exe_path()
        if getattr(sys, "frozen", False):
            cmd = [exe_path, "--day", date_str, "--no-notify"]
        else:
            # 开发模式：用当前解释器跑模块
            if exe_path.endswith("run.py"):
                cmd = [sys.executable, "-m", "src.main", "--day", date_str, "--no-notify"]
            else:
                cmd = [exe_path, "--day", date_str, "--no-notify"]

        self._clear_log()
        self._append_log(f"开始执行: {' '.join(cmd)}\n")
        self.status_var.set(f"正在识别 {date_str} ...")
        self._set_running(True)

        def _reader():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                with self._running_lock:
                    self._running_proc = proc
                for line in proc.stdout:
                    self._append_log(line)
                proc.wait()
            except Exception as e:
                self._append_log(f"\n启动失败: {e}\n")
            finally:
                self.root.after(0, lambda: self._finish_run(date_str))

        threading.Thread(target=_reader, daemon=True).start()

    def _finish_run(self, date_str: str) -> None:
        with self._running_lock:
            proc = self._running_proc
            self._running_proc = None

        self._set_running(False)

        # 尝试从日志文件读取汇总
        summary = ""
        try:
            cfg = Config.load()
            log_path = cfg.log_dir / f"ly-oa_{date_str.replace('-', '')}.log"
            if log_path.exists():
                with log_path.open("r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    if "[RUN]" in line and "总计" not in line:
                        # 找包含总计的 RUN 行或最后一条 RUN 汇总
                        pass
                    if "总计:" in line:
                        summary = line.strip()
                        break
                if not summary and lines:
                    summary = lines[-1].strip()
        except Exception as e:
            summary = f"无法读取日志汇总: {e}"

        if summary:
            self.status_var.set(f"{date_str} 完成: {summary}")
            self._append_log(f"\n完成: {summary}\n")
            messagebox.showinfo("运行完成", f"日期: {date_str}\n{summary}")
            notify("ly-OA 识别完成", f"{date_str}\n{summary}", duration="long")
        else:
            self.status_var.set(f"{date_str} 运行结束")
            self._append_log("\n运行结束\n")
            messagebox.showinfo("运行完成", f"日期: {date_str}\n运行已结束，请查看日志或输出目录。")
            notify("ly-OA 运行结束", f"{date_str} 运行已结束，请查看日志或输出目录。")


def main() -> None:
    root = tk.Tk()
    app = ConfigApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
