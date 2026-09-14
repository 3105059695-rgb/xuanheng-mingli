#!/usr/bin/env python3
"""核验并转换明确的公农历日期；不生成出生时刻或完整命盘。Python 3.9+。"""

import argparse
from datetime import date
from importlib import metadata
import json
import re
import sys

LIBRARY_VERSION = "1.4.8"
SCRIPT_VERSION = "2.3.0"
BRANCHES = tuple("子丑寅卯辰巳午未申酉戌亥")
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MIN_SOLAR = date(1901, 1, 1)
MAX_SOLAR = date(2100, 12, 31)


def load_library():
    try:
        installed = metadata.version("lunar-python")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError("缺少历法依赖；在隔离环境安装本 skill 的 requirements.txt 后重试。") from exc
    if installed != LIBRARY_VERSION:
        raise RuntimeError("历法版本不符：需要 %s，实际 %s；停止转换。" % (LIBRARY_VERSION, installed))
    from lunar_python import Lunar, LunarMonth, Solar
    return Lunar, LunarMonth, Solar


def parse_solar(value):
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        raise ValueError("公历日期必须明确写为 YYYY-MM-DD；此助手只接收日期，不截取或改写时间戳。")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("公历日期不存在。") from exc
    if not MIN_SOLAR <= parsed <= MAX_SOLAR:
        raise ValueError("仅支持公历 1901-01-01 至 2100-12-31；农历输入也按换算后的公历范围检查。")
    return parsed


def check_context(time_basis, hour_branch):
    if time_basis != "utc8-standard":
        raise ValueError("必须明确采用 utc8-standard 日期口径；海外当地日期、历史时区、夏令时及太阳时不自动换算。")
    if hour_branch is not None and hour_branch not in BRANCHES:
        raise ValueError("时支只可记录明确的子丑寅卯辰巳午未申酉戌亥之一；未知则省略，不推算时刻。")


def lunar_tuple(lunar):
    signed_month = lunar.getMonth()
    return (lunar.getYear(), abs(signed_month), lunar.getDay(), signed_month < 0)


def checked_month(LunarMonth, year, month, day, leap):
    for label, value in (("农历年", year), ("月", month), ("日", day)):
        if type(value) is not int:
            raise ValueError("%s须为明确整数；不接受布尔值、文字歧义或小数。" % label)
    # 农历1900年末覆盖公历1901年初；最终边界按换算后的公历判断。
    if not 1900 <= year <= 2100:
        raise ValueError("农历年份须在 1900—2100 内，且最终公历日期须在 1901—2100 内。")
    if not 1 <= month <= 12:
        raise ValueError("农历月须为 1—12 的正整数，闰月通过 leap 参数单独声明。")
    if type(leap) is not bool:
        raise ValueError("必须明确是否闰月：leap=True/False，命令行使用 --leap yes/no；不默认非闰月。")
    signed_month = -month if leap else month
    lunar_month = LunarMonth.fromYm(year, signed_month)
    if lunar_month is None:
        raise ValueError("农历 %d 年不存在%s%d月，请核对年份及是否闰月。" % (year, "闰" if leap else "", month))
    if (lunar_month.getYear(), lunar_month.getMonth()) != (year, signed_month):
        raise RuntimeError("历法库返回的年月与输入不一致；停止转换。")
    days = lunar_month.getDayCount()
    if days not in (29, 30):
        raise RuntimeError("历法库返回异常的农历月天数；停止转换。")
    if not 1 <= day <= days:
        raise ValueError("农历 %d 年%s%d月只有 %d 天，不能使用第 %d 日。" % (year, "闰" if leap else "", month, days, day))
    return lunar_month


def result_data(source, solar, lunar, lunar_month, time_basis, hour_branch, expected_solar):
    y, m, d, leap = lunar_tuple(lunar)
    return {
        "status": "date_converted",
        "date_only": True,
        "bazi_ready": False,
        "engine": {"script_version": SCRIPT_VERSION, "library": "lunar-python", "library_version": LIBRARY_VERSION},
        "input": {**source, "time_basis": time_basis, "hour_branch": hour_branch, "expected_solar": expected_solar},
        "solar_date": solar.toYmd(),
        "lunar_date": {"year": y, "month": m, "day": d, "leap_month": leap, "month_days": lunar_month.getDayCount(), "label": lunar.toString()},
        "lunar_year_label": {"ganzhi": lunar.getYearInGanZhi(), "branch": lunar.getYearZhi(), "branch_number": BRANCHES.index(lunar.getYearZhi()) + 1, "basis": "农历正月初一换年；仅作农历年标签，不能替代八字立春年柱。"},
        "recorded_hour_branch": None if hour_branch is None else {"branch": hour_branch, "branch_number": BRANCHES.index(hour_branch) + 1, "source": "user_supplied", "note": "原样记录所给时支；没有核验具体时刻，子时跨日仍须澄清。"},
        "verification": {"round_trip": "passed_same_library", "independent_check": "not_performed_for_this_input", "expected_solar_match": None if expected_solar is None else True, "note": "往返使用同一历法库，仅检查内部一致性；不等于独立历书验证或用户生日已经确认。"},
        "handoff": "只将 solar_date 作为已声明口径下的日期结果。生成八字前另取已确认的出生时刻、换日口径及误差；不得从日期 API 的内部时刻补出生日时间。",
    }


def convert_solar(solar_date, *, time_basis, hour_branch=None):
    check_context(time_basis, hour_branch)
    parsed = parse_solar(solar_date)
    Lunar, LunarMonth, Solar = load_library()
    solar = Solar.fromYmd(parsed.year, parsed.month, parsed.day)
    lunar = solar.getLunar()
    y, m, d, leap = lunar_tuple(lunar)
    lunar_month = checked_month(LunarMonth, y, m, d, leap)
    back = Lunar.fromYmd(y, -m if leap else m, d).getSolar()
    if back.toYmd() != solar_date or lunar_tuple(back.getLunar()) != (y, m, d, leap):
        raise RuntimeError("公农历回读不一致；停止转换，改查权威历书。")
    return result_data({"calendar": "solar", "date": solar_date}, solar, lunar, lunar_month, time_basis, hour_branch, None)


def convert_lunar(year, month, day, leap, *, time_basis, hour_branch=None, expected_solar=None):
    check_context(time_basis, hour_branch)
    if expected_solar is not None:
        parse_solar(expected_solar)
    Lunar, LunarMonth, Solar = load_library()
    lunar_month = checked_month(LunarMonth, year, month, day, leap)
    lunar = Lunar.fromYmd(year, -month if leap else month, day)
    solar = lunar.getSolar()
    parsed = parse_solar(solar.toYmd())
    # 重新实例化公历对象，避免把原对象自报的农历视作回读核对。
    back = Solar.fromYmd(parsed.year, parsed.month, parsed.day).getLunar()
    if lunar_tuple(back) != (year, month, day, leap) or back.getSolar().toYmd() != solar.toYmd():
        raise RuntimeError("农历转公历后回读的年月日或闰月标志不一致；停止转换。")
    if expected_solar is not None and expected_solar != solar.toYmd():
        raise ValueError("所给公历 %s 与该农历转换结果 %s 不一致；保留原始记录，先核历，不能择一默认。" % (expected_solar, solar.toYmd()))
    return result_data({"calendar": "lunar", "year": year, "month": month, "day": day, "leap_month": leap}, solar, lunar, lunar_month, time_basis, hour_branch, expected_solar)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="calendar", required=True)
    solar_parser = subparsers.add_parser("solar", help="明确公历日期转农历")
    solar_parser.add_argument("--date", required=True, help="YYYY-MM-DD；不接收时刻")
    lunar_parser = subparsers.add_parser("lunar", help="明确农历日期转公历")
    lunar_parser.add_argument("--year", type=int, required=True)
    lunar_parser.add_argument("--month", type=int, required=True, help="1—12；正数，闰月另声明")
    lunar_parser.add_argument("--day", type=int, required=True)
    lunar_parser.add_argument("--leap", choices=("yes", "no"), required=True, help="必须明确是否闰月")
    lunar_parser.add_argument("--expected-solar", help="若已有公历记录，填 YYYY-MM-DD 做一致性比对；不符即停止")
    for child in (solar_parser, lunar_parser):
        child.add_argument("--time-basis", required=True, help="必须明确 utc8-standard；不自动换算时区")
        child.add_argument("--hour-branch", choices=BRANCHES, help="可选：仅记录明确给出的时支，不生成时刻")
    args = parser.parse_args(argv)
    try:
        if args.calendar == "solar":
            result = convert_solar(args.date, time_basis=args.time_basis, hour_branch=args.hour_branch)
        else:
            result = convert_lunar(args.year, args.month, args.day, args.leap == "yes", time_basis=args.time_basis, hour_branch=args.hour_branch, expected_solar=args.expected_solar)
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "error": str(exc), "action": "停止转换及下游排盘，先核实输入或依赖。"}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    from _cli import configure_output
    configure_output()
    sys.exit(main())
