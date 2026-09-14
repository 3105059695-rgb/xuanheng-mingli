#!/usr/bin/env python3
"""核验民用钟表时间，并保留同一时刻的时制候选；Python 3.9+，运行时不联网。"""

import argparse
import calendar
from datetime import datetime, timedelta, timezone
import hashlib
from importlib import metadata, resources
import io
import json
import math
from pathlib import Path
import re
import sys
import zoneinfo

SCRIPT_VERSION = "1.0.0"
UTC8 = timezone(timedelta(hours=8))
LOCAL_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2})?")
OFFSET_PATTERN = re.compile(r"([+-])([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?")
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"


def parse_local(value):
    if not isinstance(value, str) or not LOCAL_PATTERN.fullmatch(value):
        raise ValueError("local 须为完整公历 YYYY-MM-DDTHH:MM[:SS]，不要附时区、补时辰或先扣夏令时。")
    moment = datetime.fromisoformat(value)
    if not 1901 <= moment.year <= 2100:
        raise ValueError("本工具限公历 1901—2100 年；早期时制另需原始记录核实。")
    return moment


def parse_offset(value):
    match = OFFSET_PATTERN.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("recorded_offset 须为记录实际注明的 ±HH:MM[:SS]，不得用 CST 等缩写猜测。")
    sign, hour, minute, second = match.groups()
    hour, minute, second = int(hour), int(minute), int(second or 0)
    if hour >= 24 or minute >= 60 or second >= 60 or (sign == "-" and hour == minute == second == 0):
        raise ValueError("recorded_offset 无效；未知偏移不能写成 -00:00。")
    return (1 if sign == "+" else -1) * (hour * 3600 + minute * 60 + second)


def database_version(root):
    for name in ("+VERSION", "tzdata.zi", "version"):
        path = root / name
        if path.is_file():
            first = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if first:
                return {"label": first[0].removeprefix("# version "), "evidence": str(path)}
    return {"label": None, "evidence": None}


def load_zone(key):
    # Read the exact bytes subsequently used by ZoneInfo, avoiding cache/provenance mismatch.
    if (not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_+./-]+", key)
            or any(part in ("", ".", "..") for part in key.split("/"))
            or key.split("/")[0] in ("right", "posix") or ("/" not in key and key not in ("UTC", "GMT"))):
        raise ValueError("zone 须为明确的 IANA 地区键（如 Asia/Shanghai）；不接受时区缩写、路径或含闰秒的 right 数据。")
    for root_name in zoneinfo.TZPATH:
        root = Path(root_name)
        path = root / key
        if path.is_file():
            data = path.read_bytes()
            version = database_version(root)
            provenance = {"provider": "system", "path": str(path.resolve()), "tzdb_version": version["label"], "version_evidence": version["evidence"]}
            break
    else:
        try:
            resource = resources.files("tzdata.zoneinfo")
            for part in key.split("/"):
                resource = resource.joinpath(part)
            data = resource.read_bytes()
            import tzdata
            provenance = {"provider": "tzdata-package", "package_version": metadata.version("tzdata"), "tzdb_version": getattr(tzdata, "IANA_VERSION", None), "resource": "tzdata.zoneinfo/" + key}
        except (ImportError, ModuleNotFoundError, FileNotFoundError, metadata.PackageNotFoundError) as exc:
            raise ValueError("找不到该 IANA 时区；先核实地区键，或准备系统时区库 / Python 官方 tzdata 包。") from exc
    provenance["tzif_sha256"] = hashlib.sha256(data).hexdigest()
    return zoneinfo.ZoneInfo.from_file(io.BytesIO(data), key=key), provenance


def valid_candidates(wall, zone):
    # Merely attaching tzinfo permits nonexistent times. UTC round-trip detects them.
    candidates = []
    seen = set()
    for fold in (0, 1):
        local = wall.replace(tzinfo=zone, fold=fold)
        instant = local.astimezone(timezone.utc)
        returned = instant.astimezone(zone)
        if returned.replace(tzinfo=None) != wall or instant in seen:
            continue
        seen.add(instant)
        candidates.append(returned)
    return sorted(candidates, key=lambda item: item.astimezone(timezone.utc))


def finite_number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("%s 须为 %s—%s 的有限数值。" % (name, minimum, maximum))


def clock_label(moment, day_boundary):
    day = moment.date()
    if day_boundary == "23" and moment.hour >= 23:
        day += timedelta(days=1)
    return {"clock": moment.isoformat(timespec="seconds"), "hour_branch": BRANCHES[((moment.hour + 1) // 2) % 12], "day_label_under_selected_boundary": day.isoformat()}


def equation_of_time(instant):
    """NOAA fractional-year approximation; use UTC consistently for date/hour."""
    instant = instant.astimezone(timezone.utc)
    hours = instant.hour + instant.minute / 60 + instant.second / 3600
    gamma = 2 * math.pi / (366 if calendar.isleap(instant.year) else 365) * (instant.timetuple().tm_yday - 1 + (hours - 12) / 24)
    return 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma) - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))


def solar_review(instant, longitude, day_boundary):
    utc_clock = instant.astimezone(timezone.utc).replace(tzinfo=None)
    mean = utc_clock + timedelta(minutes=4 * longitude)
    eot = equation_of_time(instant)
    apparent = mean + timedelta(minutes=eot)
    mean_label, apparent_label = clock_label(mean, day_boundary), clock_label(apparent, day_boundary)
    for label in (mean_label, apparent_label):
        label["clock_is_not_an_iso_instant"] = True
    return {
        "scope": "clock_sensitivity_only",
        "longitude_east_degrees": longitude,
        "mean_solar_clock": mean_label,
        "approx_apparent_solar_clock": apparent_label,
        "equation_of_time_minutes": round(eot, 6),
        "equation_sign": "近似视太阳钟面 = 地方平太阳钟面 + 均时差",
        "formula": "NOAA fractional-year equation; γ uses UTC date/hour, leap-year denominator 366; east longitude positive",
        "source": "https://gml.noaa.gov/grad/solcalc/solareqns.PDF",
        "bazi_ready": False,
        "precision": "太阳钟面显示到秒只便于复算；该近似未获本工具的秒级或固定分钟误差校准，未改正 UT1−UTC。接近时辰/换日边界须外部天文核验。",
        "do_not_feed_to_bazi": "两项是同一瞬间的太阳钟面，不是新的 UTC+8 民用时刻。不得加 +08:00 后送入 bazi.py；那会移动绝对时刻并错配交节。",
    }


def normalize(local, zone_key, fold=None, recorded_offset=None, adopt_utc8=False,
              longitude=None, day_boundary="00", uncertainty_minutes=None):
    wall = parse_local(local)
    if fold is not None and (type(fold) is not int or fold not in (0, 1)):
        raise ValueError("fold 仅接受 0（前一次）或 1（后一次）。")
    if type(adopt_utc8) is not bool:
        raise ValueError("adopt_utc8 须为布尔值；它表示明确选择固定 UTC+8 排盘口径。")
    if day_boundary not in ("00", "23"):
        raise ValueError("day_boundary 须为 00 或 23。")
    if uncertainty_minutes is not None:
        finite_number(uncertainty_minutes, "uncertainty_minutes", 0, 1440)
    if longitude is not None:
        finite_number(longitude, "longitude", -180, 180)
    offset_seconds = parse_offset(recorded_offset) if recorded_offset is not None else None
    zone, provenance = load_zone(zone_key)
    possible = valid_candidates(wall, zone)
    if not possible:
        raise ValueError("这个当地钟面时刻在所选 IANA 时区不存在（可能处于拨快的缺失区间）。停止排盘，核实原记录；不得自动平移成另一个出生时刻。")
    was_ambiguous = len(possible) == 2
    if fold is not None:
        if not was_ambiguous:
            raise ValueError("该时刻不重叠，无须 fold；请移除它，避免把错误的消歧信息写入记录。")
        possible = [item for item in possible if item.fold == fold]
    if offset_seconds is not None:
        possible = [item for item in possible if int(item.utcoffset().total_seconds()) == offset_seconds]
        if not possible:
            raise ValueError("记录注明的 UTC 偏移与所选地区/日期/fold 不符。保留冲突，不能覆盖原记录或默选另一个偏移。")
    candidates = []
    for item in possible:
        instant = item.astimezone(timezone.utc)
        utc8 = instant.astimezone(UTC8)
        in_bazi_range = 1901 <= utc8.year <= 2100
        row = {
            "fold": item.fold,
            "civil_local": item.isoformat(),
            "utc_offset_seconds": int(item.utcoffset().total_seconds()),
            "dst_adjustment_seconds": int(item.dst().total_seconds()),
            "zone_abbreviation_for_display_only": item.tzname(),
            "utc_instant": instant.isoformat(),
            "utc8_same_instant": utc8.isoformat(),
            "clock_comparison": {"civil": clock_label(item, day_boundary), "utc8": clock_label(utc8, day_boundary)},
            "bazi_input": None,
        }
        if adopt_utc8 and in_bazi_range:
            row["bazi_input"] = {"solar": utc8.isoformat(), "time_basis": "utc8-standard", "day_boundary": day_boundary, "uncertainty_minutes": uncertainty_minutes}
        if uncertainty_minutes is not None:
            delta = timedelta(minutes=uncertainty_minutes)
            row["uncertainty_window_utc8"] = {"from": (utc8 - delta).isoformat(), "until": (utc8 + delta).isoformat(), "basis": "围绕此候选绝对时刻的 ± 实际流逝分钟；不能据此消除原钟表记录的重叠或误记。"}
        if longitude is not None:
            row["solar_clock_review"] = solar_review(instant, longitude, day_boundary)
        candidates.append(row)
    unique = len(candidates) == 1
    warnings = []
    if wall.year < 1970:
        warnings.append("1970 年以前的地区历史记录不完整；tzdb 换算不是当地医院/家庭当年实际用时的证明，需查出生地点和原始时间制度。")
    if wall.year >= datetime.now(timezone.utc).year:
        warnings.append("当年及未来民用时间按此次 tzdb 规则计算；规则变化后须重新核对并保留本版原结果。")
    if len(local[11:]) == 5:
        warnings.append("原输入只到分钟；输出秒 00 是复现约定，出生秒数未提供。")
    if not unique:
        warnings.append("原钟面时间对应两个绝对时刻。保留两候选；用记录的 UTC 偏移或前/后一次确认，不能挑更合经历的一盘。")
    if not adopt_utc8:
        warnings.append("已换算同一时刻，尚未选择命理时制。仅在明确采用固定 UTC+8 排盘后提供 bazi_input。")
    if not all(1901 <= datetime.fromisoformat(row["utc8_same_instant"]).year <= 2100 for row in candidates):
        warnings.append("换算后的 UTC+8 日期越出现有 bazi.py 支持范围；该候选不能送入排盘。")
    return {
        "status": "needs_fold_resolution" if not unique else ("normalized_for_selected_utc8" if candidates[0]["bazi_input"] else "normalized_clock_only"),
        "engine": {"script_version": SCRIPT_VERSION, "python": sys.version.split()[0], "timezone_data": provenance},
        "input": {"local_original": local, "iana_zone": zone_key, "fold_supplied": fold, "recorded_offset_supplied": recorded_offset, "adopt_utc8": adopt_utc8, "day_boundary": day_boundary, "longitude_east_degrees": longitude, "uncertainty_minutes": uncertainty_minutes},
        "original_wall_time_was_ambiguous": was_ambiguous,
        "candidates": candidates,
        "bazi_ready": unique and candidates[0]["bazi_input"] is not None,
        "bazi_input": candidates[0]["bazi_input"] if unique else None,
        "warnings": warnings,
        "conventions": {
            "instant_vs_clock": "时区换算保留同一绝对时刻；选用固定 UTC+8、当地标准时或太阳时是另一个命理口径决定。此工具只为第一项生成现有排盘参数。",
            "solar_term_comparison": "固定 UTC+8 的候选原样送入 bazi.py，出生与库节气仍处于同一时标；太阳钟面只作日/时敏感性对照，不重定年、月或起运。",
            "calendar": "公历钟表记录；不识别儒略历、农历、闰秒或已被人工校正但未注明的时间。",
            "verification": "核实换算算法及使用的数据文件；不证明所选地区键与原出生记录相符，也不证明命理预测有效。",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", required=True, help="原始当地公历钟表时间 YYYY-MM-DDTHH:MM[:SS]，不先扣夏令时")
    parser.add_argument("--zone", required=True, help="已核实的 IANA 地区键，如 Asia/Shanghai")
    parser.add_argument("--fold", type=int, choices=(0, 1), help="重叠时前一次为 0，后一次为 1；未确定则保留两候选")
    parser.add_argument("--recorded-offset", help="原始记录明确写出的 UTC 偏移，例 +09:00；负数用 --recorded-offset=-04:00")
    parser.add_argument("--adopt-utc8", action="store_true", help="明确采用固定 UTC+8 排盘，输出相应 bazi_input")
    parser.add_argument("--day-boundary", required=True, choices=("00", "23"), help="采用的换日口径；用于钟面敏感性对照及排盘参数")
    parser.add_argument("--longitude", type=float, help="实测/有出处的出生地点经度，东正西负；只添加太阳钟面敏感性核对")
    parser.add_argument("--uncertainty-minutes", type=float, help="原始记录已评估的 ± 流逝分钟；省略表示未知")
    args = parser.parse_args(argv)
    try:
        result = normalize(args.local, args.zone, args.fold, args.recorded_offset, args.adopt_utc8, args.longitude, args.day_boundary, args.uncertainty_minutes)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "error": str(exc), "action": "停止排盘并核实原时间记录，不自动改时刻。"}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    from _cli import configure_output
    configure_output()
    sys.exit(main())
