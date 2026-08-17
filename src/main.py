"""入口:纸质收料单照片 → 每日 Excel 日报.

三种模式:
  --auto              定时任务用:跑昨天,扫描 config.ini 所有 input_roots
  --day YYYY-MM-DD    手动补跑/复现:跑指定日期,同样扫描所有 input_roots
  --input <目录>      单目录调试,日期从目录名或 --date 解析

每个数据源(车间)单独生成一份 Excel,默认输出到该数据源日期目录下。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from .config import Config
from .excel_io import create_daily_xlsx, date_to_filename
from .image_io import imread
from .locate import extract_fields
from .log import log_image, log_run
from .notify import notify
from .ocr import recognize_cells
from .preprocess import preprocess_image, rotate_image
from .template import crop_cells, load_template
from .validate import (
    COL_装车时间,
    ParseResult,
    Record,
    make_failed_record,
    parse_and_check,
)
from .workshop import WorkshopProfile, load_profile

IMG_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


_DATE_DIR_PATTERNS = [
    # 2026年08月12日 / 2026年8月12日
    (re.compile(r"^(\d{4})年0?(\d{1,2})月0?(\d{1,2})日$"), "%Y年%m月%d日"),
    # 2026-08-12 / 2026.08.12 / 2026/08/12
    (re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$"), None),
    # 20260812
    (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), None),
]


def _parse_dir_date(name: str) -> date | None:
    """从目录名解析日期,支持中文、-./、纯数字等多种格式."""
    for pat, _fmt in _DATE_DIR_PATTERNS:
        m = pat.match(name)
        if m:
            try:
                return date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                continue
    return None


def _workshop_name(src_dir: Path) -> str:
    """数据源日期目录的父目录名即为车间名,如 示例车间A / 示例车间B."""
    return src_dir.parent.name


def _score_result(pr: ParseResult) -> float:
    """给一次识别结果打分,用于在多个旋转方向中选最优."""
    r = pr.record
    score = 0.0
    if r.装车日期 is not None:
        score += 3
    if r.车牌号:
        score += 3
    if r.毛重_吨 is not None:
        score += 2
    if r.皮重_吨 is not None:
        score += 2
    if r.净重_吨 is not None:
        score += 2
    score -= len(pr.yellow_marks) * 0.5
    score -= len(pr.warnings) * 0.2
    return score


def _good_enough(pr: ParseResult) -> bool:
    """0° 结果足够完整且无误,无需再尝试其它旋转方向."""
    if pr is None:
        return False
    r = pr.record
    return (
        r.装车日期 is not None
        and r.车牌号
        and r.毛重_吨 is not None
        and r.皮重_吨 is not None
        and r.净重_吨 is not None
        and not pr.yellow_marks
        and not pr.warnings
    )


def _try_orientation(img: np.ndarray, angle: int, cfg: Config,
                     template: dict, profile: WorkshopProfile,
                     target_date: date | None = None) -> ParseResult:
    """对指定旋转角度做一次完整识别;OCR 崩溃时返回空结果,不影响其它方向."""
    try:
        rot = rotate_image(img, angle)
        rot = preprocess_image(rot)
        raw = extract_fields(rot, profile)
        labels = profile.labels()
        missing = [k for k in labels if not raw.get(k, ("", 0.0))[0]]
        if missing:
            cells = crop_cells(rot, template)
            for k, v in recognize_cells({k: cells[k] for k in missing if k in cells}).items():
                if v[0]:
                    raw.setdefault(k, v)
        return parse_and_check(raw, cfg.confidence_threshold,
                               cfg.default_driver_name, profile=profile,
                               target_date=target_date)
    except Exception as e:
        return ParseResult(record=Record(), warnings=[f"{angle}度OCR异常: {e}"],
                           yellow_marks={})


def process_one(image_path: Path, cfg: Config, template: dict,
                profile: WorkshopProfile, target_date: date | None = None) -> ParseResult | None:
    img = imread(image_path)
    if img is None:
        log_image(cfg.log_file, image_path.name, "FAIL", "读图失败")
        return None

    best_pr: ParseResult | None = None
    best_score = -1.0
    best_angle = 0
    for angle in (0, 90, 180, 270):
        pr = _try_orientation(img, angle, cfg, template, profile, target_date)
        score = _score_result(pr)
        if score > best_score:
            best_score = score
            best_pr = pr
            best_angle = angle
        # 优化 A:0° 已经完整无误,直接跳过其它方向
        if angle == 0 and _good_enough(pr):
            break

    # 放宽失败判定:只有 4 个方向都崩溃(返回空 Record)才算完全失败;
    # 否则保留已识别的部分字段,缺失字段已在 validate.py 中标黄
    if best_pr is None:
        log_image(cfg.log_file, image_path.name, "FAIL",
                  "0/90/180/270 度均无法识别")
        return None

    rec = best_pr.record
    # 兜底:若 target_date 存在但 date 仍为空,强制补上
    if rec.装车日期 is None and target_date is not None:
        from datetime import time as dt_time
        rec.装车日期 = datetime.combine(target_date, dt_time.min)
        best_pr.yellow_marks.setdefault(COL_装车时间, "日期未识别,按文件夹兜底")

    angle_hint = f"[旋转{best_angle}度] " if best_angle != 0 else ""
    print(f"  {angle_hint}{image_path.name}: 日期={rec.装车日期.date()} "
          f"车牌={rec.车牌号 or '?'} 毛={rec.毛重_吨}t 皮={rec.皮重_吨}t 净={rec.净重_吨}t")
    for w in best_pr.warnings:
        print(f"    WARN: {w}")
    return best_pr


def _find_date_dirs(cfg: Config, target: date) -> list[Path]:
    """在每个 input_root 下找目标日期目录(兼容多种日期格式)."""
    return sorted(
        d for root in cfg.input_roots if root.exists()
        for d in root.iterdir() if d.is_dir() and _parse_dir_date(d.name) == target
    )


def _run_batch(images: list[Path], target_date: date, cfg: Config,
               template: dict, out_path: Path,
               profile: WorkshopProfile) -> tuple[int, int, int]:
    """逐张识别 + 写日报.返回 (成功, 失败, 标黄行数)."""
    records: list[Record] = []
    yellows: list[dict[str, str]] = []
    ok = fail = 0
    for img_path in images:
        pr = process_one(img_path, cfg, template, profile, target_date)
        if pr is None:
            # 完全识别失败:写入一行空记录,备注带超链接,方便人工补录
            pr = make_failed_record(target_date, "识别失败")
            log_image(cfg.log_file, img_path.name, "FAIL",
                      "已写入空行,请点备注照片超链接核对")
            fail += 1
        else:
            if pr.yellow_marks:
                log_image(cfg.log_file, img_path.name, "YELLOW",
                          "字段需人工核对,请点备注照片超链接查看原图")
            else:
                log_image(cfg.log_file, img_path.name, "OK",
                          f"车牌={pr.record.车牌号} 毛={pr.record.毛重_吨} "
                          f"皮={pr.record.皮重_吨} 净={pr.record.净重_吨}")
            ok += 1
        records.append(pr.record)
        yellows.append(pr.yellow_marks)
    n_yellow = sum(1 for y in yellows if y)
    create_daily_xlsx(records, yellows, out_path, cfg.reference_xlsx,
                      image_paths=images, workshop_name=profile.name)
    return ok, fail, n_yellow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="纸质收料单 → Excel 日报")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--auto", action="store_true", help="跑昨天(定时任务用)")
    mode.add_argument("--day", metavar="YYYY-MM-DD", help="跑指定日期(手动补跑)")
    mode.add_argument("--input", type=Path, help="单目录调试")
    parser.add_argument("--date", help="仅配合 --input:覆盖目录名日期解析")
    parser.add_argument("--output-dir", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--no-notify", action="store_true",
                        help="不发送 Windows 完成通知(供 GUI 调用子进程时使用)")
    args = parser.parse_args(argv)

    cfg = Config.load()
    template = load_template(cfg.template_path)

    # 确定模式、目标日期、源目录
    if args.input:
        run_mode = "input"
        if not args.input.exists():
            print(f"输入目录不存在: {args.input}")
            return 1
        if args.date:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        else:
            target_date = _parse_dir_date(args.input.name)
            if target_date is None:
                print(f"目录名格式无法解析: {args.input.name} "
                      f"(期望形如 2026年8月11日、2026-08-11、2026.08.11)")
                return 1
        src_dirs = [args.input]
    else:
        run_mode = "auto" if args.auto else "day"
        target_date = (date.today() - timedelta(days=1)) if args.auto \
            else datetime.strptime(args.day, "%Y-%m-%d").date()
        src_dirs = _find_date_dirs(cfg, target_date)
        if not src_dirs:
            print(f"{target_date} 无任何源目录({';'.join(str(r) for r in cfg.input_roots)})")
            log_run(cfg.log_file, run_mode, str(target_date), "-", status="无输入")
            return 0

    # 按目标日期生成日志文件
    cfg.log_file = cfg.log_dir / f"ly-oa_{target_date:%Y%m%d}.log"
    cfg.log_file.parent.mkdir(parents=True, exist_ok=True)

    total_ok = total_fail = total_yellow = 0
    processed = 0
    for src_dir in src_dirs:
        profile = load_profile(_workshop_name(src_dir))
        images = sorted(
            f for f in src_dir.iterdir()
            if f.suffix.lower() in IMG_SUFFIXES
        )
        if not images:
            print(f"无图片: {src_dir}")
            continue
        processed += 1

        out_dir = args.output_dir or src_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / date_to_filename(
            datetime.combine(target_date, datetime.min.time()))

        print(f"\n[{profile.name}] 输入 {len(images)} 张,目标日期 {target_date},"
              f"输出 {out_path}")

        ok, fail, n_yellow = _run_batch(images, target_date, cfg, template, out_path, profile)
        total_ok += ok
        total_fail += fail
        total_yellow += n_yellow

    if processed == 0:
        print(f"无图片: {';'.join(str(d) for d in src_dirs)}")
        log_run(cfg.log_file, run_mode, str(target_date), src_dirs, n_img=0, status="无输入")
        return 0

    summary = f"成功 {total_ok} / 失败 {total_fail} / 标黄 {total_yellow}"
    print(f"\n总计: {summary}")
    log_run(cfg.log_file, run_mode, str(target_date), src_dirs,
            total_ok + total_fail, total_ok, total_fail, total_yellow,
            "-", status="完成")
    # 完成时发送 Windows 通知;--no-notify 时跳过(避免 GUI 调用子进程时重复通知)
    if not args.no_notify:
        notify(f"ly-OA {target_date} 完成", summary, duration="long")
    return 0 if total_fail == 0 and total_yellow == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
