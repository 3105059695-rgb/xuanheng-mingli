#!/usr/bin/env python3
"""计算可复核的四柱数据；不推断命运。Python 3.9+，运行时不联网。"""

import argparse
from datetime import datetime, timedelta
from importlib import metadata
import json
import math
import re
import sys

LIBRARY_VERSION = "1.4.8"
SCRIPT_VERSION = "2.0.0"
PILLARS = ("Year", "Month", "Day", "Time")
JIE = {"立春", "惊蛰", "清明", "立夏", "芒种", "小暑", "立秋", "白露", "寒露", "立冬", "大雪", "小寒"}
SOLAR_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2})?\+08:00")


def parse_solar(value):
    if not isinstance(value, str) or not SOLAR_PATTERN.fullmatch(value):
        raise ValueError("仅接受明确公历 YYYY-MM-DDTHH:MM[:SS]+08:00；缺时辰、农历、其他时区须先核实，不能补中午或直接改时区标签。")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("公历日期或时刻无效。") from exc
    if not 1901 <= moment.year <= 2100:
        raise ValueError("本助手的保守支持范围为公历 1901—2100 年。范围外请用可信历书核盘。")
    return moment


def load_library():
    try:
        installed = metadata.version("lunar-python")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError("缺少历法依赖；请在隔离环境安装本 skill 的 requirements.txt 后重试。") from exc
    if installed != LIBRARY_VERSION:
        raise RuntimeError("历法依赖版本不符：需要 %s，实际 %s；停止计算。" % (LIBRARY_VERSION, installed))
    from lunar_python import Solar
    return Solar


def chart_data(lunar, sect, details):
    chart = lunar.getEightChar()
    chart.setSect(sect)
    pillars = {name.lower(): getattr(chart, "get" + name)() for name in PILLARS}
    result = {"sect": sect, "pillars": pillars}
    if details:
        result["details"] = {}
        for name in PILLARS:
            stems = getattr(chart, "get" + name + "HideGan")()
            relations = getattr(chart, "get" + name + "ShiShenZhi")()
            result["details"][name.lower()] = {
                "stem_relation": getattr(chart, "get" + name + "ShiShenGan")(),
                "hidden_stems": [
                    {"stem": stem, "relation": relation}
                    for stem, relation in zip(stems, relations)
                ],
            }
    return result


def term_data(term, moment):
    if term is None:
        raise RuntimeError("历法库未返回邻近节气，停止计算。")
    instant = datetime.fromisoformat(term.getSolar().toYmdHms()).replace(tzinfo=moment.tzinfo)
    name = term.getName()
    return {
        "name": name,
        "time": instant.isoformat(),
        "kind": "节" if name in JIE else "中气",
        "seconds_from_birth": int((instant - moment).total_seconds()),
        "precision_note": "库计算值；显示到秒不表示已获秒级外部核验。",
    }


def boundary_checks(moment, terms, minutes, day_boundary):
    """报告操作窗口内的切换，不把窗口大小冒充历法误差。"""
    events = []
    window = minutes * 60
    for term in terms:
        if abs(term["seconds_from_birth"]) <= window:
            affects = []
            if term["kind"] == "节":
                affects.append("month")
            if term["name"] == "立春":
                affects.append("year")
            events.append({"kind": "solar_term", "name": term["name"], "time": term["time"], "affects": affects})
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    for offset in (-1, 0, 1, 2):
        day = midnight + timedelta(days=offset)
        for hour in (0,) + tuple(range(1, 24, 2)):
            instant = day + timedelta(hours=hour)
            if abs((instant - moment).total_seconds()) > window:
                continue
            affects = ["time"] if hour % 2 == 1 else []
            if hour == (23 if day_boundary == "23" else 0):
                affects.append("day")
            if affects:
                events.append({"kind": "clock_boundary", "name": "%02d:00" % hour, "time": instant.isoformat(), "affects": affects})
    return sorted(events, key=lambda event: event["time"])


def yun_data(lunar, moment, gender, sect, count, include_liunian):
    """Expose the pinned library's Yun conventions; year rows are not dated boundaries."""
    chart = lunar.getEightChar()
    yun = chart.getYun(1 if gender == "male" else 0, sect)
    forward = yun.isForward()
    start_solar = yun.getStartSolar()
    start = datetime.fromisoformat(start_solar.toYmdHms()).replace(tzinfo=moment.tzinfo)
    jie = term_data(lunar.getNextJie() if forward else lunar.getPrevJie(), moment)
    periods = yun.getDaYun(count + 1)
    rows = []
    for period in periods[1:]:
        row = {
            "index": period.getIndex(), "ganzhi": period.getGanZhi(),
            "start_year_label": period.getStartYear(), "end_year_label": period.getEndYear(),
            "start_nominal_age": period.getStartAge(), "end_nominal_age": period.getEndAge(),
        }
        if include_liunian:
            row["liunian"] = [
                {"year_label": year.getYear(), "nominal_age": year.getAge(), "ganzhi": year.getGanZhi()}
                for year in period.getLiuNian()
            ]
        rows.append(row)
    return {
        "gender_parameter": gender,
        "gender_api_value": 1 if gender == "male" else 0,
        "direction_basis": {
            "year_pillar": lunar.getYearInGanZhiExact(),
            "year_stem": lunar.getYearGanExact(),
            "year_yinyang": "阳" if lunar.getYearGanIndexExact() % 2 == 0 else "阴",
            "rule": "以立春年干分阴阳：阳年男、阴年女顺；阴年男、阳年女逆。gender 是本次采用的传统排运参数。",
        },
        "direction": "forward" if forward else "reverse",
        "yun_sect": sect,
        "algorithm": (
            "库 sect 1：公历日差和时辰序差折算，三日一年、一日四个月、一时辰十天；23时按序号11处理，不逐秒折算。"
            if sect == 1 else
            "库 sect 2：两端各忽略秒后算分钟差；4320分钟折一年、360分钟折一月、12分钟折一天、余1分钟折2小时。"
        ),
        "target_jie": jie,
        "start_offset": {"years": yun.getStartYear(), "months": yun.getStartMonth(), "days": yun.getStartDay(), "hours": yun.getStartHour()},
        "start_solar": start.isoformat(),
        "start_date_convention": "起运偏移依次加公历年、月、日、小时；年/月加法按库截到有效月末。此为库算法日期，未作外部独立交运核验。",
        "pre_start_phase": {"from": moment.isoformat(), "until_exclusive": start.isoformat(), "ganzhi": None, "note": "尚未进入第一步大运；不把库 index 0 的空干支当成十年大运。"},
        "dayun": rows,
        "table_convention": "年份是库按起运公历年生成的十年标签；虚岁标签=所在公历年-出生公历年+1，不是周岁。交运当年可能前后两运并存，不能按表把整年归入一运。本表不提供各十年交运的精确时刻。",
        "liunian_convention": "流年干支为所列公历年份立春起的干支年标签；不代表1月1日换干支。表内归组只随库年份标签，不能判断交运当日属于哪运。",
        "verification": "固定 lunar-python 1.4.8 算法输出；上游样例回归不是独立命盘校验。",
    }


def calculate(solar, time_basis, day_boundary, uncertainty_minutes=None, details=False,
              gender=None, yun_sect=None, dayun_count=8, liunian=False):
    moment = parse_solar(solar)
    if time_basis != "utc8-standard":
        raise ValueError("仅支持已确认的 UTC+08:00 标准时口径；夏令时、海外当地时、地方平太阳时或真太阳时请先校时或外部核盘。")
    if day_boundary not in ("23", "00"):
        raise ValueError("必须明确选择日柱换日口径 23 或 00。")
    if (gender is None) != (yun_sect is None):
        raise ValueError("计算大运须同时明确 gender=male/female 与 yun_sect=1/2；不可从姓名、称呼或其他参数猜测。")
    if gender is not None and gender not in ("male", "female"):
        raise ValueError("gender 仅接受本次采用的传统排运参数 male 或 female。")
    if yun_sect is not None and (type(yun_sect) is not int or yun_sect not in (1, 2)):
        raise ValueError("yun_sect 仅接受整数 1（天数时辰折算）或 2（分钟折算），与日柱换日 sect 分开。")
    if type(dayun_count) is not int or not 1 <= dayun_count <= 12:
        raise ValueError("dayun_count 必须为 1—12 的整数步数，不包括起运前区段。")
    if not isinstance(liunian, bool):
        raise ValueError("liunian 必须为布尔值。")
    if gender is None and (liunian or dayun_count != 8):
        raise ValueError("流年表或自选大运步数需要先明确 gender 与 yun_sect。")
    if uncertainty_minutes is not None:
        if isinstance(uncertainty_minutes, bool) or not isinstance(uncertainty_minutes, (int, float)) or not math.isfinite(uncertainty_minutes) or not 0 <= uncertainty_minutes <= 1440:
            raise ValueError("出生时间误差须为 0—1440 的有限分钟数；未知可省略，大于一天请先核实日期。")
    Solar = load_library()
    lunar = Solar.fromYmdHms(moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second).getLunar()
    sect = 1 if day_boundary == "23" else 2
    chosen = chart_data(lunar, sect, details)
    alternate = chart_data(lunar, 3 - sect, details)
    differing = [name for name in chosen["pillars"] if chosen["pillars"][name] != alternate["pillars"][name]]
    terms = [term_data(lunar.getPrevJieQi(), moment), term_data(lunar.getNextJieQi(), moment)]
    window_minutes = max(5, uncertainty_minutes or 0)
    boundaries = boundary_checks(moment, terms, window_minutes, day_boundary)
    warnings = []
    if uncertainty_minutes is None:
        warnings.append("出生时间误差未评估；当前盘仅对应输入时刻，不能据此声称时柱已确定。")
    if len(solar[11:].split("+")[0]) == 5:
        warnings.append("输入仅精确到分钟；秒字段按 00 计算用于复现，实际出生秒数未知。")
    if differing:
        warnings.append("晚子时换日存在流派差异；保留双盘，涉及日主及十神的解读须随日柱分别计算。")
    if boundaries:
        warnings.append("输入附近存在时间或节气边界；请查看每项 affects。窗口触及相关柱时，先核实时间，再分别重排边界两侧。中气本身不换月柱。")
    if moment.year >= 2050:
        warnings.append("远期节气或朔日计算存在不确定性，临界日期应再次查权威历书。")
    lunar_month = lunar.getMonth()
    result = {
        "status": "computed_requires_time_review" if warnings else "computed",
        "verification": "本次结果为固定算法计算；未自动取得独立历书或外部命盘核验。",
        "engine": {"script_version": SCRIPT_VERSION, "library": "lunar-python", "library_version": LIBRARY_VERSION},
        "input": {"solar": solar, "normalized_solar": moment.isoformat(), "time_basis": time_basis, "uncertainty_minutes": uncertainty_minutes},
        "conventions": {
            "year": "立春交接时刻换年柱，不用春节或公历元旦换年柱。",
            "month": "十二节交接时刻换月柱，不按农历初一或每个中气换月。",
            "day_boundary": day_boundary,
            "sect": sect,
            "late_zi_hour": "采用库的两派：sect 1 日柱 23 时换日；sect 2 日柱 0 时换日。两派晚子时时柱均按翌日日干起时；未涵盖全部子时流派。",
            "clock": "显式 UTC+08:00 标准时；不做夏令时、经度或均时差校正。",
        },
        "lunar_date": {"year": lunar.getYear(), "month": abs(lunar_month), "day": lunar.getDay(), "leap_month": lunar_month < 0, "label": lunar.toString(), "basis": "输入公历民用日期对应的农历日，独立于八字日柱换日流派。"},
        "chart": chosen,
        "other_day_boundary": {"day_boundary": "00" if day_boundary == "23" else "23", **alternate, "different_pillars": differing},
        "adjacent_solar_terms": terms,
        "boundary_review": {"window_minutes": window_minutes, "window_note": "操作检查窗口取 max(5 分钟, 已提供的出生误差)，不是统计置信区间，也不是历法库误差承诺。", "events": boundaries},
        "warnings": warnings,
        "not_calculated": ["真太阳时", "历史时区自动校正", "各十年交运精确时刻", "格局自动判定或喜用神打分", "流年吉凶", "命运预测"],
    }
    if gender is not None:
        result["yun"] = yun_data(lunar, moment, gender, yun_sect, dayun_count, liunian)
        if boundaries:
            warnings.append("大运也须复核边界：跨立春可能改变顺逆，跨节可能改变起运取节；起运算法还会放大出生时刻差异。")
        result["yun"]["birth_time_review"] = "仅对应输入时刻；有出生误差或日节边界候选时，分别重算起运，不能只改四柱。"
    else:
        result["not_calculated"].append("大运与流年表（未提供排运参数）")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solar", required=True, help="公历 YYYY-MM-DDTHH:MM[:SS]+08:00")
    parser.add_argument("--time-basis", required=True, help="明确采用 utc8-standard；其他时间口径先校时")
    parser.add_argument("--day-boundary", required=True, choices=("23", "00"), help="日柱换日；两派晚子时时干均按翌日日干计算")
    parser.add_argument("--uncertainty-minutes", type=float, help="已知出生时间误差 ± 分钟；省略表示未知，0 仅在明确评估后使用")
    parser.add_argument("--details", action="store_true", help="包含各柱藏干与相对日主的十神")
    parser.add_argument("--gender", choices=("male", "female"), help="本次采用的传统排运性别参数；不提供则不计算大运")
    parser.add_argument("--yun-sect", type=int, choices=(1, 2), help="起运算法：1按日数时辰数，2按分钟数；须与 gender 同时提供")
    parser.add_argument("--dayun-count", type=int, default=8, help="输出 1—12 步大运，默认 8；不含起运前区段")
    parser.add_argument("--liunian", action="store_true", help="在每步大运中附十个流年干支标签，不预测吉凶")
    args = parser.parse_args(argv)
    try:
        result = calculate(args.solar, args.time_basis, args.day_boundary, args.uncertainty_minutes, args.details,
                           args.gender, args.yun_sect, args.dayun_count, args.liunian)
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "error": str(exc), "action": "停止解读，修复输入、校时或依赖后重试；不得凭记忆补盘。"}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    from _cli import configure_output
    configure_output()
    sys.exit(main())
