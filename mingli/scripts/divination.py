#!/usr/bin/env python3
"""Deterministic hexagram mechanics; no interpretation or prediction."""
import argparse
import json
import secrets
import sys

# Bits and all incoming lines are bottom to top. Matrix rows are LOWER trigrams.
# Names/order cross-checked against Wikisource 周易 六十四卦速查表, 2026-09-14.
TRIGRAMS = [
    ("乾", (1, 1, 1)), ("兑", (1, 1, 0)),
    ("离", (1, 0, 1)), ("震", (1, 0, 0)),
    ("巽", (0, 1, 1)), ("坎", (0, 1, 0)),
    ("艮", (0, 0, 1)), ("坤", (0, 0, 0)),
]
KING_WEN = [
    [1, 43, 14, 34, 9, 5, 26, 11],
    [10, 58, 38, 54, 61, 60, 41, 19],
    [13, 49, 30, 55, 37, 63, 22, 36],
    [25, 17, 21, 51, 42, 3, 27, 24],
    [44, 28, 50, 32, 57, 48, 18, 46],
    [6, 47, 64, 40, 59, 29, 4, 7],
    [33, 31, 56, 62, 53, 39, 52, 15],
    [12, 45, 35, 16, 20, 8, 23, 2],
]
NAMES = "乾 坤 屯 蒙 需 讼 师 比 小畜 履 泰 否 同人 大有 谦 豫 随 蛊 临 观 噬嗑 贲 剥 复 无妄 大畜 颐 大过 坎 离 咸 恒 遁 大壮 晋 明夷 家人 睽 蹇 解 损 益 夬 姤 萃 升 困 井 革 鼎 震 艮 渐 归妹 丰 旅 巽 兑 涣 节 中孚 小过 既济 未济".split()
BIT_INDEX = {bits: index for index, (_, bits) in enumerate(TRIGRAMS)}
LINE_NAMES = {6: "老阴", 7: "少阳", 8: "少阴", 9: "老阳"}
ELEMENTS = {"乾": "金", "兑": "金", "离": "火", "震": "木", "巽": "木", "坎": "水", "艮": "土", "坤": "土"}
GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
PROVENANCE = ("user-reported", "simulated", "derived")


def check_provenance(value):
    if value not in PROVENANCE:
        raise ValueError("来源须为user-reported、simulated或derived。")
    return value


def describe(bits):
    bits = tuple(bits)
    if len(bits) != 6 or any(type(v) is not int or v not in (0, 1) for v in bits):
        raise ValueError("卦画必须是自下而上的六个0或1。")
    lower, upper = BIT_INDEX[bits[:3]], BIT_INDEX[bits[3:]]
    number = KING_WEN[lower][upper]
    return {"number": number, "name": NAMES[number - 1],
            "symbol": chr(0x4DC0 + number - 1),
            "lower": TRIGRAMS[lower][0], "upper": TRIGRAMS[upper][0],
            "bits_bottom_to_top": list(bits)}


def from_lines(values, *, provenance="user-reported"):
    check_provenance(provenance)
    values = list(values)
    if len(values) != 6 or any(type(v) is not int or v not in LINE_NAMES for v in values):
        raise ValueError("提供六个6/7/8/9，依次为初爻至上爻。")
    bits = [v % 2 for v in values]
    moving = [i + 1 for i, v in enumerate(values) if v in (6, 9)]
    changed = [1 - b if i + 1 in moving else b for i, b in enumerate(bits)]
    return {
        "method": "six-line-values", "input_order": "bottom_to_top", "provenance": provenance,
        "lines": [{"position": i + 1, "value": v, "type": LINE_NAMES[v],
                   "moving": v in (6, 9)} for i, v in enumerate(values)],
        "original": describe(bits), "moving_lines": moving,
        "changed": describe(changed),
        "status": "仅起卦结构；未生成纳甲、六亲、世应或六神。",
    }


def from_coins(groups, *, provenance="user-reported"):
    check_provenance(provenance)
    try:
        groups = list(groups)
    except TypeError as exc:
        raise ValueError("钱币记录须为六组三位2/3字符串。") from exc
    if len(groups) != 6 or any(not isinstance(g, str) or len(g) != 3 or any(c not in "23" for c in g) for g in groups):
        raise ValueError("提供六组三位数，每位仅为2或3，例如233；先约定钱币两面的赋值。")
    result = from_lines([sum(int(c) for c in group) for group in groups], provenance=provenance)
    result.update(method="three-coins", coins_bottom_to_top=groups,
                  scoring="每枚已按约定赋2或3分；三枚相加。物理面的命名不由程序推断。")
    return result


def relation_to_body(body, other):
    """Five-element direction, relative to the original body throughout."""
    b, o = ELEMENTS[body], ELEMENTS[other]
    if b == o:
        relation, reading = "比和", "同气相应"
    elif GENERATES[o] == b:
        relation, reading = "用生体", "外部生助"
    elif GENERATES[b] == o:
        relation, reading = "体生用", "自身付出与耗泄"
    elif CONTROLS[b] == o:
        relation, reading = "体克用", "可制约对象，须有承载力量"
    else:
        relation, reading = "用克体", "承受外部制约"
    return {"body": body, "body_element": b, "other": other,
            "other_element": o, "relation": relation, "traditional_tendency": reading}


def meihua_structure(upper_number, lower_number, moving_number, mutual_policy="changed-for-pure"):
    for value in (upper_number, lower_number, moving_number):
        if type(value) is not int or value <= 0:
            raise ValueError("起卦数必须为正整数。")
    if mutual_policy not in ("changed-for-pure", "mechanical"):
        raise ValueError("未知互卦口径。")
    upper, lower, moving = (upper_number - 1) % 8, (lower_number - 1) % 8, (moving_number - 1) % 6 + 1
    bits = list(TRIGRAMS[lower][1] + TRIGRAMS[upper][1])
    values = [7 if b else 8 for b in bits]
    values[moving - 1] = 9 if bits[moving - 1] else 6
    result = from_lines(values, provenance="derived")
    mechanical = describe(bits[1:4] + bits[2:5])
    pure = len(set(bits)) == 1
    mutual_bits = result["changed"]["bits_bottom_to_top"] if pure and mutual_policy == "changed-for-pure" else bits
    mutual = describe(mutual_bits[1:4] + mutual_bits[2:5])
    body = TRIGRAMS[upper if moving <= 3 else lower][0]
    use = TRIGRAMS[lower if moving <= 3 else upper][0]
    changed_use = result["changed"]["lower" if moving <= 3 else "upper"]
    result.update(
        method="meihua-structure",
        arithmetic={"upper_number": upper_number, "lower_number": lower_number,
                    "moving_number": moving_number, "upper_index": upper + 1,
                    "lower_index": lower + 1, "moving_line": moving},
        body=body, use=use, body_position="upper" if moving <= 3 else "lower",
        use_position="lower" if moving <= 3 else "upper",
        mutual=mutual, mechanical_mutual=mechanical,
        mutual_policy={"selected": mutual_policy, "pure_qian_kun": pure,
                       "used_changed_hexagram": pure and mutual_policy == "changed-for-pure"},
        relations={"original_use": relation_to_body(body, use),
                   "mutual_lower": relation_to_body(body, mutual["lower"]),
                   "mutual_upper": relation_to_body(body, mutual["upper"]),
                   "changed_use": relation_to_body(body, changed_use)},
        source="https://zh.wikisource.org/zh/梅花易數/卷一",
        status="已算体用与生克方向；旺衰、问事类别和断法须结合参考规则研判。",
    )
    return result


def meihua_time(year_branch, month, day, hour_branch, leap_month, mutual_policy="changed-for-pure",
                *, calendar_source="user-supplied", day_boundary="supplied-lunar-date"):
    for label, value, maximum in [("年支", year_branch, 12), ("月", month, 12),
                                   ("日", day, 30), ("时支", hour_branch, 12)]:
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"{label}必须是1至{maximum}的整数。")
    if leap_month != "no":
        raise ValueError("闰月取数存在口径差异，本脚本不自动选定；先核实版本后另算。")
    if not isinstance(calendar_source, str) or not calendar_source.strip():
        raise ValueError("须记录农历输入来源。")
    if day_boundary not in ("supplied-lunar-date", "midnight", "zi-start"):
        raise ValueError("日界须为supplied-lunar-date、midnight或zi-start。")
    subtotal = year_branch + month + day
    total = subtotal + hour_branch
    result = meihua_structure(subtotal, total, total, mutual_policy)
    result.update(
        method="meihua-lunar-time", rule_version="meihua-lunar-time-v1",
        inputs={"year_branch_index": year_branch, "lunar_month": month,
                "lunar_day": day, "hour_branch_index": hour_branch, "leap_month": False},
        arithmetic={**result["arithmetic"], "year_month_day_sum": subtotal, "total_with_hour": total},
        calendar={"source": calendar_source, "day_boundary": day_boundary,
                  "conversion_performed": False,
                  "validation_scope": "仅校验取数范围；实际农历年月日和年支须前置校历。",
                  "boundary_note": "所传月日须已经符合声明日界；该参数不平移日期。"},
        status="输入农历日期有效性须先校历；程序校验取数与卦画，未验证预测效果。",
    )
    return result


def meihua_sounds(first, second, hour_branch, mutual_policy="changed-for-pure", *, provenance="user-reported"):
    check_provenance(provenance)
    if any(type(v) is not int or v <= 0 for v in (first, second, hour_branch)) or hour_branch > 12:
        raise ValueError("两段声数须为正整数，时支序数须为1至12。")
    result = meihua_structure(first, second, first + second + hour_branch, mutual_policy)
    result.update(method="meihua-two-sound-groups",
                  provenance=provenance, rule_version="meihua-two-sound-groups-raw-v1",
                  inputs={"first_group": first, "second_group": second, "hour_branch_index": hour_branch},
                  rule="依卷一邻夜扣门借物占例上下分取、加时定爻；超过八声时本版明确用原声数，原例未区分约数变体。两段划分须先记录。")
    return result


def meihua_objects(count, hour_branch, moving_basis="raw", mutual_policy="changed-for-pure", *, provenance="user-reported"):
    check_provenance(provenance)
    if type(count) is not int or count <= 0 or type(hour_branch) is not int or not 1 <= hour_branch <= 12:
        raise ValueError("物数须为正整数，时支序数须为1至12。")
    if moving_basis not in ("raw", "reduced"):
        raise ValueError("动爻取数口径应为raw或reduced。")
    object_component = count if moving_basis == "raw" else (count - 1) % 8 + 1
    total = object_component + hour_branch
    result = meihua_structure(count, hour_branch, total, mutual_policy)
    result.update(method="meihua-object-count",
                  provenance=provenance, rule_version=f"meihua-object-{moving_basis}-plus-hour-v2",
                  inputs={"object_count": count, "hour_branch_index": hour_branch, "moving_number_basis": moving_basis},
                  arithmetic={**result["arithmetic"], "moving_object_component": object_component,
                              "moving_hour_component": hour_branch},
                  rule="卷一物数占例；raw用原物数，reduced用约后物卦序，两者均加原时支序数。卦数一词有解释空间，本版显式记口径。")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    lines = sub.add_parser("lines", help="输入初爻至上爻的6/7/8/9")
    lines.add_argument("values", type=int, nargs=6)
    coins = sub.add_parser("coins", help="每面预先赋2或3分，输入初爻至上爻的六组三枚结果")
    coins.add_argument("groups", nargs=6)
    sub.add_parser("simulate", help="用户要求数字模拟起卦时使用；非实体投掷")
    mei = sub.add_parser("meihua-time", help="原典年月日时取数；农历输入须事先核实")
    mei.add_argument("--year-branch", type=int, required=True)
    mei.add_argument("--lunar-month", type=int, required=True)
    mei.add_argument("--lunar-day", type=int, required=True)
    mei.add_argument("--hour-branch", type=int, required=True)
    mei.add_argument("--leap-month", choices=["yes", "no"], required=True)
    mei.add_argument("--calendar-source", default="user-supplied")
    mei.add_argument("--day-boundary", choices=["supplied-lunar-date", "midnight", "zi-start"], default="supplied-lunar-date")
    sounds = sub.add_parser("meihua-sounds", help="两段声音分取上下卦，加时定爻")
    sounds.add_argument("first", type=int)
    sounds.add_argument("second", type=int)
    sounds.add_argument("--hour-branch", type=int, required=True)
    objects = sub.add_parser("meihua-objects", help="可数物作上卦，时支作下卦")
    objects.add_argument("count", type=int)
    objects.add_argument("--hour-branch", type=int, required=True)
    objects.add_argument("--moving-basis", choices=["raw", "reduced"], default="raw")
    for command in (lines, coins, sounds, objects):
        command.add_argument("--provenance", choices=PROVENANCE, default="user-reported", help="输入来源；标记simulated不会自行生成随机数")
    for command in (mei, sounds, objects):
        command.add_argument("--mutual-policy", choices=["changed-for-pure", "mechanical"], default="changed-for-pure", help="默认对乾坤采用互其变卦；机械互卦另列")
    args = parser.parse_args()
    try:
        if args.command == "lines":
            result = from_lines(args.values, provenance=args.provenance)
        elif args.command == "coins":
            result = from_coins(args.groups, provenance=args.provenance)
        elif args.command == "simulate":
            result = from_coins(["".join(str(2 + secrets.randbelow(2)) for _ in range(3))
                                 for _ in range(6)], provenance="simulated")
            result.update(method="digital-three-coins-simulation",
                          simulation_note="计算机随机模拟；每枚2/3等概率，非本人实体投掷。")
        elif args.command == "meihua-time":
            result = meihua_time(args.year_branch, args.lunar_month, args.lunar_day,
                                 args.hour_branch, args.leap_month, args.mutual_policy,
                                 calendar_source=args.calendar_source, day_boundary=args.day_boundary)
        elif args.command == "meihua-sounds":
            result = meihua_sounds(args.first, args.second, args.hour_branch, args.mutual_policy, provenance=args.provenance)
        else:
            result = meihua_objects(args.count, args.hour_branch, args.moving_basis, args.mutual_policy, provenance=args.provenance)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ValueError as exc:
        print(json.dumps({"error": str(exc), "status": "未起卦"}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    from _cli import configure_output
    configure_output()
    sys.exit(main())
