"""字段校验:把 OCR 原始文本解析为标准格式,失败的字段标黄."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time

from .workshop import WorkshopProfile


@dataclass
class Record:
    """识别出的一条收料单记录,字段缺失时为 None."""

    编号: str | None = None
    装车日期: datetime | None = None  # 装车日期 + 装车时间合在一起
    货品名称: str | None = None
    车牌号: str | None = None
    司机姓名: str | None = None
    皮重_吨: float | None = None
    毛重_吨: float | None = None
    净重_吨: float | None = None
    检毛时间: datetime | None = None
    检皮时间: datetime | None = None
    备注: str | None = None


@dataclass
class ParseResult:
    record: Record
    warnings: list[str] = field(default_factory=list)
    low_conf_fields: list[str] = field(default_factory=list)
    # 黄色填充标记:{列字母: 原因},例如 {"A": "编号格式不对"}
    yellow_marks: dict[str, str] = field(default_factory=dict)


# Excel 列字母
COL_序号 = "A"
COL_装车日期 = "B"
COL_装车时间 = "C"
COL_货品 = "D"
COL_车牌 = "E"
COL_司机 = "F"
COL_皮重 = "G"
COL_毛重 = "H"
COL_净重 = "I"
COL_备注 = "J"


# 物资名(印章盖住的部分)统一映射;用户已确认货品名称固定为石膏废渣
MATERIAL_MAP = {
    "石渣": "石膏废渣",
    "石膏": "石膏废渣",
    "渣石膏": "石膏废渣",
    "石膏废渣": "石膏废渣",
    "": "石膏废渣",  # 印章全盖时 OCR 识别为空的兜底
}


def _norm_num(s: str) -> int | None:
    """把 OCR 出来的数字字符串标准化.优先取最长数字串(因为可能含 label 干扰)."""
    if not s:
        return None
    s = s.replace(",", "").replace("O", "0").replace("o", "0")
    # 去掉常见中文 label 干扰字符后再找数字
    for ch in "毛重皮净检录编号车号物资kg吨":
        s = s.replace(ch, "")
    # 找所有数字串,取最长的
    nums = re.findall(r"\d+", s)
    if not nums:
        return None
    nums.sort(key=lambda x: -len(x))
    return int(nums[0])


def _parse_dt(s: str) -> datetime | None:
    """从可能含 label 的字符串里解析完整日期时间."""
    if not s:
        return None
    s = s.strip()
    # 先修复 OCR 常见的 "日期时间" 连写: 2026-08-1209:05:04 -> 2026-08-12 09:05:04
    s = re.sub(r"(\d{4}-\d{2}-\d{2})(\d{2}:\d{2}:\d{2})", r"\1 \2", s)
    s = re.sub(r"(\d{4}-\d{2}-\d{2})(\d{2}:\d{2})", r"\1 \2", s)
    s = re.sub(r"(\d{4}/\d{2}/\d{2})(\d{2}:\d{2}:\d{2})", r"\1 \2", s)
    s = re.sub(r"(\d{4}/\d{2}/\d{2})(\d{2}:\d{2})", r"\1 \2", s)
    s = re.sub(r"(\d{4}\d{2}\d{2})(\d{2}:\d{2}:\d{2})", r"\1 \2", s)
    # 优先:完整时间戳(日期在前或时间在前)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%H:%M:%S %Y-%m-%d", "%H:%M %Y-%m-%d",
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # 兜底:取所有数字串
    nums = re.findall(r"\d+", s)
    if len(nums) >= 6:
        yy, mo, dd, hh, mi, ss = nums[:6]
        try:
            return datetime(int(yy), int(mo), int(dd), int(hh), int(mi), int(ss))
        except (ValueError, TypeError):
            pass
    if len(nums) >= 5:
        yy, mo, dd, hh, mi = nums[:5]
        try:
            return datetime(int(yy), int(mo), int(dd), int(hh), int(mi), 0)
        except (ValueError, TypeError):
            pass
    return None


def _parse_time_only(s: str) -> time | None:
    """从字符串里只解析时间部分(如 09:34:12)."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    # 兜底:取数字串
    nums = re.findall(r"\d+", s)
    if len(nums) >= 3:
        try:
            return time(int(nums[0]), int(nums[1]), int(nums[2]))
        except (ValueError, TypeError):
            pass
    if len(nums) == 2:
        try:
            return time(int(nums[0]), int(nums[1]), 0)
        except (ValueError, TypeError):
            pass
    return None


def _parse_no(s: str) -> str | None:
    """编号: XMG + 8位日期 + 6位时间秒. 印章可能盖住尾几位或前缀,尽量兜底."""
    if not s:
        return None
    s = s.strip().upper().replace(" ", "")
    # 正常: XMG + 12-14 位数字
    m = re.search(r"(XMG\d{12,14})", s)
    if m:
        return m.group(1)
    # 兜底:前缀被污渍/印章破坏,但后面跟着完整日期时间,如 "MG20260812155600" 或 "G20260812155600"
    m = re.search(r"([MX]?G?\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", s)
    if m:
        g = m.group(0)
        # 确保看起来像编号:至少 14 位数字 + 可能的前缀残字
        if len(re.sub(r"[^0-9]", "", g)) >= 14:
            # 统一补成 XMG 前缀
            digits = re.sub(r"[^0-9]", "", g)
            return f"XMG{digits[:14]}"
    return None


def _parse_plate(s: str) -> str | None:
    if not s:
        return None
    s = s.strip().upper().replace(" ", "")
    # 严格:蒙A12345D
    m = re.match(r"^蒙[A-Z]\d{5}[A-Z]$", s)
    if m:
        return s
    # 兜底1:常见完整格式
    m = re.search(r"(蒙[A-Z]\d{5}[A-Z])", s)
    if m:
        return m.group(1)
    # 兜底2:允许 4-5 位数字,如蒙A1234D、蒙A12345
    m = re.search(r"(蒙[A-Z]\d{4,5}[A-Z]?)", s)
    if m:
        return m.group(1)
    return None


def parse_and_check(
    raw: dict[str, tuple[str, float]],
    conf_threshold: float = 0.85,
    default_driver: str = "admin",
    profile: WorkshopProfile | None = None,
    target_date: date | None = None,
) -> ParseResult:
    """raw: {字段名: (text, conf)};返回 Record + warnings + 标黄标记.

    target_date: 从输入目录名解析出的日期,作为装车日期兜底."""
    if profile is None:
        profile = WorkshopProfile({})

    r = Record()
    w: list[str] = []
    yellow: dict[str, str] = {}
    pr_low_conf_fields: list[str] = []

    # 编号 → 备注(仅在需要编号的车间处理)
    if "编号" in profile.labels():
        no_text, no_conf = raw.get("编号", ("", 0.0))
        no = _parse_no(no_text) if profile.number_format == "xmg" else None
        if no is None:
            if no_text:
                w.append(f"编号格式异常: {no_text!r}")
            yellow[COL_备注] = "编号未识别"
        else:
            m = re.match(r"^XMG(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$", no)
            if m:
                yy, mo, dd, _hh, _mi, _ss = m.groups()
                try:
                    datetime(int(yy), int(mo), int(dd))
                except (ValueError, TypeError):
                    w.append(f"编号日期非法: {no}")
            r.备注 = no
        # 编号完整匹配 = 结构自证正确,低置信多为印章碎片拖低,不再标黄
        if no is None and no_conf < conf_threshold and no_text:
            yellow[COL_备注] = f"编号低置信({no_conf:.2f})"
            pr_low_conf_fields.append("编号")

    # 装车时间:固定优先从 检毛 取,取不到再用 检皮 兜底,与 date_field 解耦
    time_fields = ["检毛", "检皮"]

    record_time = time.min
    time_conf = 0.0
    time_field_used = ""
    time_parsed_from = ""
    parsed_full_dt: datetime | None = None
    for fld in time_fields:
        txt, conf = raw.get(fld, ("", 0.0))
        if not txt:
            continue
        dt = _parse_dt(txt)
        if dt is not None:
            record_time = dt.time()
            parsed_full_dt = dt
            time_conf = conf
            time_field_used = fld
            time_parsed_from = txt
            break
        # 只有时间(如 09:34:12)时也接受
        t_only = _parse_time_only(txt)
        if t_only is not None:
            record_time = t_only
            time_conf = conf
            time_field_used = fld
            time_parsed_from = txt
            break

    # 装车日期:优先用 target_date(输入目录日期);无 target_date 时从时间字段的完整日期推导
    if target_date is not None:
        r.装车日期 = datetime.combine(target_date, record_time)
        if time_field_used == "":
            yellow[COL_装车时间] = "装车时间未识别,日期按文件夹"
    elif parsed_full_dt is not None:
        r.装车日期 = parsed_full_dt
    else:
        r.装车日期 = datetime.combine(date.today(), record_time)
        yellow[COL_装车时间] = "仅识别到时间,日期按今天"

    if time_field_used and time_conf < conf_threshold:
        yellow[COL_装车时间] = f"{time_field_used}低置信({time_conf:.2f})"
        pr_low_conf_fields.append(time_field_used)

    # 检皮时间
    jp_text, jp_conf = raw.get("检皮", ("", 0.0))
    jp = _parse_dt(jp_text)
    if jp is None:
        if jp_text:
            w.append(f"检皮时间解析失败: {jp_text!r}")
    else:
        r.检皮时间 = jp
    if jp_conf < conf_threshold and jp_text:
        pr_low_conf_fields.append("检皮")

    # 物资
    mz_text, mz_conf = raw.get("物资", ("", 0.0))
    mz_clean = mz_text.replace("(", "").replace(")", "").replace("（", "").replace("）", "").strip()
    r.货品名称 = MATERIAL_MAP.get(mz_clean, None)
    if r.货品名称 is None:
        r.货品名称 = "石膏废渣"  # 兜底
        if mz_text and mz_clean not in MATERIAL_MAP:
            w.append(f"物资字段未知: {mz_text!r},按'石膏废渣'填")
    # 物资固定填"石膏废渣",不依赖 OCR,无需低置信标黄

    # 车牌
    cp_text, cp_conf = raw.get("车号", ("", 0.0))
    cp = _parse_plate(cp_text)
    if cp is None:
        if cp_text:
            w.append(f"车牌号格式异常: {cp_text!r}")
        yellow[COL_车牌] = "车牌未识别"
    else:
        r.车牌号 = cp
    if cp_conf < conf_threshold and cp_text:
        yellow[COL_车牌] = f"车牌低置信({cp_conf:.2f})"
        pr_low_conf_fields.append("车号")

    # 司机姓名(源单无,固定填)
    r.司机姓名 = default_driver

    # 毛/皮/净重: OCR 出来是 kg 整数,转吨
    for src, dst_field, col in [
        ("毛重", "毛重_吨", COL_毛重),
        ("皮重", "皮重_吨", COL_皮重),
        ("净重", "净重_吨", COL_净重),
    ]:
        t, c = raw.get(src, ("", 0.0))
        n = _norm_num(t)
        if n is None:
            if t:
                w.append(f"{src}解析失败: {t!r}")
            yellow[col] = f"{src}未识别"
        else:
            setattr(r, dst_field, n / 1000.0)
        if c < conf_threshold and t:
            yellow[col] = f"{src}低置信({c:.2f})"
            pr_low_conf_fields.append(src)

    # 一致性校验: 净重 ≈ 毛重 - 皮重(允许 1% 误差)
    if r.毛重_吨 is not None and r.皮重_吨 is not None and r.净重_吨 is not None:
        expected = r.毛重_吨 - r.皮重_吨
        if abs(expected - r.净重_吨) > 0.05:  # 50kg 误差
            w.append(f"净重 {r.净重_吨} 与 毛-皮={expected:.2f} 偏差大")
            yellow[COL_净重] = f"净重不匹配(差 {r.净重_吨 - expected:+.2f})"

    return ParseResult(record=r, warnings=w, yellow_marks=yellow, low_conf_fields=pr_low_conf_fields)


def make_failed_record(target_date: date, reason: str = "识别失败") -> ParseResult:
    """生成一张识别失败图片的空记录,所有数据列标黄,等待人工补录."""
    r = Record(
        装车日期=datetime.combine(target_date, time.min),
        货品名称="石膏废渣",
    )
    yellow = {
        COL_装车时间: reason,
        COL_车牌: reason,
        COL_皮重: reason,
        COL_毛重: reason,
        COL_净重: reason,
        COL_备注: reason,
    }
    return ParseResult(
        record=r,
        warnings=[reason],
        yellow_marks=yellow,
        low_conf_fields=[],
    )
