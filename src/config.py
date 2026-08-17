"""读 config.ini,得到路径/阈值.路径一律解析到 base_dir(exe 所在目录或仓库根),
与 cwd 无关——任务计划程序启动时 cwd 不可控."""
from __future__ import annotations

import configparser
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


def base_dir() -> Path:
    """exe(PyInstaller frozen)→ exe 所在目录;开发模式 → 仓库根(src 的上一级)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def ensure_resources() -> None:
    """exe 打包模式下,若 exe 同目录缺少配置文件/模板/参考 xlsx,从打包资源中释放.

    这样部署时只需要复制 ly-oa.exe,第一次运行会自动生成所需文件.
    """
    if not getattr(sys, "frozen", False):
        return
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return

    base = base_dir()
    resources = [
        ("config.ini", "config.ini"),
        ("template.json", "template.json"),
        ("使用说明.txt", "使用说明.txt"),
        ("参考模板/固废填埋日统计表0809.xlsx", "参考模板/固废填埋日统计表0809.xlsx"),
    ]
    for dst_rel, src_rel in resources:
        dst = base / dst_rel
        if dst.exists():
            continue
        src = Path(meipass) / src_rel
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))

    # 拷贝 workshops/ 目录（车间配置文件）
    src_dir = Path(meipass) / "workshops"
    dst_dir = base / "workshops"
    if src_dir.exists() and not dst_dir.exists():
        shutil.copytree(str(src_dir), str(dst_dir))


@dataclass
class Config:
    日报_dir: Path | None       # centralized 输出目录,默认隐藏/不启用
    reference_xlsx: Path
    template_path: Path
    log_dir: Path
    log_file: Path             # 运行时按日期覆盖为 log_dir/ly-oa_YYYYMMDD.log
    input_roots: list[Path]
    confidence_threshold: float
    default_driver_name: str

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        base = base_dir()
        path = path or base / "config.ini"
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}(应放在 exe 同目录)")
        cp = configparser.ConfigParser()
        cp.read(path, encoding="utf-8")
        p = cp["paths"]

        def rel(key: str, default: Path | None = None) -> Path | None:
            if key not in p or not p[key].strip():
                return default
            v = Path(p[key].strip())
            return v if v.is_absolute() else base / v

        log_dir = rel("log_dir", base / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        日报_dir = rel("日报_dir")
        cfg = cls(
            日报_dir=日报_dir,
            reference_xlsx=rel("reference_xlsx"),
            template_path=rel("template"),
            log_dir=log_dir,
            log_file=log_dir / "ly-oa.log",
            input_roots=[rel_part for part in p["input_roots"].split(",")
                         if part.strip()
                         for rel_part in [Path(part.strip()) if Path(part.strip()).is_absolute()
                                          else base / part.strip()]],
            confidence_threshold=float(cp["ocr"]["confidence_threshold"]),
            default_driver_name=cp["driver"].get("default_driver_name", "").strip(),
        )
        if not cfg.reference_xlsx.exists():
            raise FileNotFoundError(f"参考模板不存在: {cfg.reference_xlsx}")
        return cfg
