#!/usr/bin/env python3
"""Reproducible folk-method records; no calendar conversion or outcome prediction."""

import argparse
import json


PALACES = ("大安", "留连", "速喜", "赤口", "小吉", "空亡")
BRANCHES = tuple("子丑寅卯辰巳午未申酉戌亥")
TIME_RULE = "wanbao-yuxia-1936-inclusive-v1"
NUMBER_RULE = "mingli-three-positive-numbers-inclusive-v1"
JIAOBEI_RULE = "taiwan-tourism-upward-faces-v1"
LOT_RULE = "lungshan-guanyin-three-consecutive-v1"
SCAN_URL = "https://commons.wikimedia.org/wiki/File:NLC416-15jh007692-106641_萬寶玉匣記.pdf"
NUMBER_URL = "https://goldenloong.github.io/Liu_Ren_divination/"
JIAOBEI_URL = "https://www.tad.gov.tw/m1.aspx?sNo=0027010"
LOT_URL = "https://lungshan.org.tw/Tour_Guide/search"


def integer(value, name, minimum, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        limit = f"{minimum}..{maximum}" if maximum is not None else f">={minimum}"
        raise ValueError(f"{name} must be an integer in {limit}")
    return value


def hour_number(value):
    if isinstance(value, str) and value in BRANCHES:
        return BRANCHES.index(value) + 1
    return integer(value, "hour (子=1..亥=12)", 1, 12)


def count_stage(start, count, label):
    """Count the occupied palace as 1, then move count - 1 places."""
    integer(start, "start", 0, 5)
    integer(count, "count", 1, 10**12)
    end = (start + count - 1) % 6
    preview_count = min(count, 30)
    trace = [{"count": i, "palace": PALACES[(start + i - 1) % 6]}
             for i in range(1, preview_count + 1)]
    return {
        "stage": label, "count": count, "start": PALACES[start],
        "start_counted_as": 1, "forward_moves": count - 1,
        "complete_six_move_laps": (count - 1) // 6,
        "remaining_moves": (count - 1) % 6,
        "end": PALACES[end], "end_index": end,
        "trace": trace, "trace_truncated": count > preview_count,
    }


def three_stages(values, labels, rule_version):
    try:
        values, labels = tuple(values), tuple(labels)
    except TypeError as exc:
        raise ValueError("three stages require three counts and three labels") from exc
    if len(values) != 3 or len(labels) != 3:
        raise ValueError("three stages require exactly three counts and three labels")
    stages = []
    start = 0
    for count, label in zip(values, labels):
        stage = count_stage(start, count, label)
        stages.append(stage)
        start = stage["end_index"]
    return {
        "rule_version": rule_version, "palace_order": list(PALACES),
        "input_numbers": list(values), "stages": stages,
        "final_palace": PALACES[start],
        "arithmetic_check": {
            "zero_based_index": (sum(values) - 3) % 6,
            "formula": "(first + second + third - 3) mod 6",
        },
    }


def xiaoliuren_time(month, day, hour, *, is_leap=False, leap_policy="reject",
                    day_boundary="supplied-lunar-date", calendar_source="user-supplied"):
    integer(month, "lunar month", 1, 12)
    integer(day, "lunar day", 1, 30)
    hour = hour_number(hour)
    if type(is_leap) is not bool:
        raise ValueError("is_leap must be a boolean")
    if leap_policy not in ("reject", "repeat-month"):
        raise ValueError("leap_policy must be reject or repeat-month")
    if is_leap and leap_policy == "reject":
        raise ValueError("leap month requires explicit repeat-month convention; this is an implementation choice")
    if day_boundary not in ("supplied-lunar-date", "midnight", "zi-start"):
        raise ValueError("day_boundary must be supplied-lunar-date, midnight, or zi-start")
    if not isinstance(calendar_source, str) or not calendar_source.strip():
        raise ValueError("calendar_source must identify the supplied lunar date or calendar")
    result = three_stages((month, day, hour), ("月上起日的月定位", "月位起初一", "日位起子时"), TIME_RULE)
    result.update({
        "method": "小六壬月日时", "source": {"url": SCAN_URL, "pdf_pages": [66, 67], "printed_pages": "卷下二十五、二十六"},
        "calendar": {
            "month": month, "day": day, "hour_number": hour, "hour_branch": BRANCHES[hour - 1],
            "is_leap": is_leap, "leap_policy": leap_policy, "day_boundary": day_boundary,
            "source": calendar_source, "conversion_performed": False,
            "validation_scope": "numeric ranges only; actual lunar date, leap month and month length must be verified upstream",
            "boundary_note": "month and day must already reflect the declared boundary; this script does not shift dates",
        },
        "interpretation_scope": "final hour palace is the traditional result; intermediate palaces are calculation records",
    })
    return result


def xiaoliuren_numbers(first, second, third, *, provenance="user-reported"):
    for name, value in zip(("first", "second", "third"), (first, second, third)):
        integer(value, name, 1, 10**12)
    if provenance not in ("user-reported", "simulated"):
        raise ValueError("provenance must be user-reported or simulated")
    result = three_stages((first, second, third), ("第一数", "第二数", "第三数"), NUMBER_RULE)
    result.update({
        "method": "报数小六壬（现代工作变体）", "provenance": provenance,
        "source": {"url": NUMBER_URL, "publisher": "GoldenLoong public project"},
        "rule_choice": "positive integer counts; every new stage includes its starting palace as 1",
        "interpretation_scope": "start/process/result is an optional modern reading, not attributed to the 1936 text",
    })
    return result


def jiaobei(first_face, second_face, *, provenance="user-reported"):
    faces = (first_face, second_face)
    if any(face not in ("flat", "convex") for face in faces):
        raise ValueError("faces must be flat or convex, describing the upward-facing side")
    if provenance not in ("user-reported", "simulated"):
        raise ValueError("provenance must be user-reported or simulated")
    if first_face != second_face:
        name, meaning = "圣筊", "该习俗中的肯定/允诺"
    elif first_face == "flat":
        name, meaning = "笑筊", "该习俗中的未定"
    else:
        name, meaning = "怒筊", "该习俗中的否定；龙山寺求签说明称阴筊"
    return {"method": "筊杯", "rule_version": JIAOBEI_RULE, "source": JIAOBEI_URL,
            "upward_faces": list(faces), "name": name, "traditional_meaning": meaning,
            "provenance": provenance}


def longshan_lot_attempt(throws, *, provenance="user-reported"):
    """Evaluate one drawn lot's confirmation attempt, not initial permission."""
    if not isinstance(throws, (list, tuple)) or not 1 <= len(throws) <= 3:
        raise ValueError("one lot confirmation attempt requires 1..3 throws")
    records = []
    for i, pair in enumerate(throws):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("each throw must contain exactly two upward faces")
        record = jiaobei(*pair, provenance=provenance)
        records.append(record)
        if record["name"] != "圣筊":
            if i != len(throws) - 1:
                raise ValueError("a non-holy throw ends this lot attempt; later throws require a new drawn lot")
            status = "redraw-lot"
            break
    else:
        status = "confirmed" if len(records) == 3 else "await-next-throw"
    return {"method": "艋舺龙山寺观音签号确认", "rule_version": LOT_RULE, "source": LOT_URL,
            "throws": records, "status": status,
            "required_remaining": 3 - len(records) if status == "await-next-throw" else 0,
            "scope": "one lot number; initial permission to draw is a separate stage"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="method", required=True)
    time = sub.add_parser("xiaoliuren-time", help="already verified lunar month/day/hour")
    time.add_argument("--month", type=int, required=True)
    time.add_argument("--day", type=int, required=True)
    time.add_argument("--hour", required=True, help="子..亥 or 1..12")
    time.add_argument("--leap-month", action="store_true")
    time.add_argument("--leap-policy", choices=("reject", "repeat-month"), default="reject")
    time.add_argument("--day-boundary", choices=("supplied-lunar-date", "midnight", "zi-start"), default="supplied-lunar-date")
    time.add_argument("--calendar-source", default="user-supplied")
    numbers = sub.add_parser("xiaoliuren-numbers", help="explicit modern three-number variant")
    numbers.add_argument("numbers", nargs=3, type=int)
    numbers.add_argument("--provenance", choices=("user-reported", "simulated"), default="user-reported")
    cups = sub.add_parser("jiaobei", help="classify two upward faces; does not toss cups")
    cups.add_argument("faces", nargs=2, choices=("flat", "convex"))
    cups.add_argument("--provenance", choices=("user-reported", "simulated"), default="user-reported")
    lot = sub.add_parser("longshan-lot", help="one drawn lot confirmation; ff=two flat, fc=mixed, cc=two convex")
    lot.add_argument("throws", nargs="+", choices=("ff", "fc", "cf", "cc"))
    lot.add_argument("--provenance", choices=("user-reported", "simulated"), default="user-reported")
    args = parser.parse_args()
    try:
        if args.method == "xiaoliuren-time":
            hour = int(args.hour) if args.hour.isascii() and args.hour.isdigit() else args.hour
            result = xiaoliuren_time(args.month, args.day, hour, is_leap=args.leap_month,
                leap_policy=args.leap_policy, day_boundary=args.day_boundary, calendar_source=args.calendar_source)
        elif args.method == "xiaoliuren-numbers":
            result = xiaoliuren_numbers(*args.numbers, provenance=args.provenance)
        elif args.method == "jiaobei":
            result = jiaobei(*args.faces, provenance=args.provenance)
        else:
            faces = {"f": "flat", "c": "convex"}
            result = longshan_lot_attempt([[faces[c] for c in pair] for pair in args.throws], provenance=args.provenance)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    from _cli import configure_output
    configure_output()
    main()
