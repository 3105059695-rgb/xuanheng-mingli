#!/usr/bin/env python3
"""Six-line Na-jia chart and auditable relations; explicit day/month, no prediction."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

_spec = importlib.util.spec_from_file_location("mingli_divination", Path(__file__).with_name("divination.py"))
_divination = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_divination)

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ELEMENTS = "木火土金水"  # generating cycle
BRANCH_ELEMENT = dict(zip(BRANCHES, "水土木木土火火土金金土水"))
PALACE_ELEMENT = dict(zip("乾兑离震巽坎艮坤", "金金火木木水土土"))
RELATIVES = ("兄弟", "子孙", "妻财", "官鬼", "父母")
SPIRITS = ("青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武")
SPIRIT_START = (0, 0, 1, 1, 2, 3, 4, 4, 5, 5)
# Both inner and outer tuples are strictly bottom to top. References/liuyao.md.
NAJIA = {
    "乾": ("甲子 甲寅 甲辰".split(), "壬午 壬申 壬戌".split()),
    "兑": ("丁巳 丁卯 丁丑".split(), "丁亥 丁酉 丁未".split()),
    "离": ("己卯 己丑 己亥".split(), "己酉 己未 己巳".split()),
    "震": ("庚子 庚寅 庚辰".split(), "庚午 庚申 庚戌".split()),
    "巽": ("辛丑 辛亥 辛酉".split(), "辛未 辛巳 辛卯".split()),
    "坎": ("戊寅 戊辰 戊午".split(), "戊申 戊戌 戊子".split()),
    "艮": ("丙辰 丙午 丙申".split(), "丙戌 丙子 丙寅".split()),
    "坤": ("乙未 乙巳 乙卯".split(), "癸丑 癸亥 癸酉".split()),
}
PALACE_STAGES = ("本宫", "一世", "二世", "三世", "四世", "五世", "游魂", "归魂")
PALACE_MASKS = (0, 1, 3, 7, 15, 31, 23, 16)
SHI_POSITIONS = (6, 1, 2, 3, 4, 5, 4, 3)
SIX_COMBINATIONS = {frozenset(pair) for pair in ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")}
# Seven pairs in 增删卜易 chapter 29 (Wikisource/Shidianguji transcription).
# Some modern layouts add 戌→丑; that textual variant is not silently adopted.
ADVANCE_PAIRS = {tuple(pair) for pair in ("亥子", "寅卯", "巳午", "申酉", "丑辰", "辰未", "未戌")}
ADVANCE_RETREAT_RULE = "zengshan-seven-pairs-v1"
TOPICS = {
    "career": {"default": "官鬼", "support": ["父母", "世爻"],
               "note": "求职、职位以官鬼为主；录用文书另看父母。若问工资，改用妻财。"},
    "wealth": {"default": "妻财", "support": ["子孙", "世爻"],
               "note": "财物以妻财为主，子孙为财源；兄弟是否有效克财须查动静和日月。"},
    "relationship": {"default": None, "support": ["世爻", "应爻"],
                     "note": "先明对象和关系：一般双方互动看世应；传统妻财/官鬼配偶取用须说明口径并显式选择。"},
    "lost-property": {"default": None, "support": ["世爻"],
                      "note": "先按失物类别显式选择：钱物妻财、证件衣物父母、宠物子孙；不能从玄武断有人偷窃。"},
    "document": {"default": "父母", "support": ["世爻", "官鬼"], "note": "证件、契约、文书以父母为主。"},
    "self": {"default": "世爻", "support": [], "note": "明确属于本人处境的问题，以世爻为主。"},
}


def ganzhi_index(value):
    if not isinstance(value, str) or len(value) != 2 or value[0] not in STEMS or value[1] not in BRANCHES:
        raise ValueError("日干支须为两个汉字的有效六十甲子，如甲子、戊申；不能只给日支。")
    for index in range(60):
        if STEMS[index % 10] + BRANCHES[index % 12] == value:
            return index
    raise ValueError("日干支阴阳不配，不在六十甲子中。")


def xunkong(day_ganzhi):
    index = ganzhi_index(day_ganzhi)
    start = (index // 10) * 10
    return {"xun_start": STEMS[start % 10] + BRANCHES[start % 12],
            "branches": [BRANCHES[(start + 10) % 12], BRANCHES[(start + 11) % 12]],
            "days_until_next_xun": 10 - index % 10}


def six_relative(palace_element, line_element):
    return RELATIVES[(ELEMENTS.index(line_element) - ELEMENTS.index(palace_element)) % 5]


def element_relation(source, target):
    """Named from the source's effect upon the target, not from the target's view."""
    return ("比和", "生", "克", "受克", "受生")[(ELEMENTS.index(target) - ELEMENTS.index(source)) % 5]


def branch_relation(source, target):
    effect = element_relation(BRANCH_ELEMENT[source], BRANCH_ELEMENT[target])
    s, t = source + BRANCH_ELEMENT[source], target + BRANCH_ELEMENT[target]
    sentence = {"比和": f"{s}与{t}同类", "生": f"{s}生{t}", "克": f"{s}克{t}",
                "受克": f"{t}克{s}", "受生": f"{t}生{s}"}[effect]
    return {"source_branch": source, "target_branch": target,
            "element_effect": effect, "direction_sentence": sentence,
            "same_branch": source == target,
            "six_combination": frozenset((source, target)) in SIX_COMBINATIONS,
            "clash": (BRANCHES.index(source) - BRANCHES.index(target)) % 12 == 6}


def palace_for(bits):
    bits = tuple(bits)
    _divination.describe(bits)  # validate before bit arithmetic
    for name, trigram_bits in _divination.TRIGRAMS:
        base = trigram_bits + trigram_bits
        for stage, mask in enumerate(PALACE_MASKS):
            if tuple(bit ^ ((mask >> i) & 1) for i, bit in enumerate(base)) == bits:
                shi = SHI_POSITIONS[stage]
                return {"name": name, "element": PALACE_ELEMENT[name],
                        "stage": PALACE_STAGES[stage], "shi": shi,
                        "ying": (shi + 2) % 6 + 1,
                        "pure_bits_bottom_to_top": list(base)}
    raise ValueError("未找到八宫归属。")


def dress(bits, palace_element):
    description = _divination.describe(bits)
    ganzhis = NAJIA[description["lower"]][0] + NAJIA[description["upper"]][1]
    return [{"position": i + 1, "ganzhi": gz, "branch": gz[1],
             "element": BRANCH_ELEMENT[gz[1]],
             "relative": six_relative(palace_element, BRANCH_ELEMENT[gz[1]])}
            for i, gz in enumerate(ganzhis)]


def temporal_flags(branch, day_branch, month_branch, empty):
    month = branch_relation(month_branch, branch)
    day = branch_relation(day_branch, branch)
    return {"xunkong": branch in empty, "month_break": month["clash"],
            "day_clash": day["clash"], "month": month, "day": day}


def hexagram_relations(rows):
    pairs = [branch_relation(rows[i]["branch"], rows[i + 3]["branch"]) for i in range(3)]
    return {"six_clash": all(pair["clash"] for pair in pairs),
            "six_combination": all(pair["six_combination"] for pair in pairs)}


def advance_retreat_pair(original_branch, changed_branch):
    """Match a textual pair only; strength, time horizon and efficacy stay unassessed."""
    if (original_branch, changed_branch) in ADVANCE_PAIRS:
        label = "进神配对"
    elif (changed_branch, original_branch) in ADVANCE_PAIRS:
        label = "退神配对"
    else:
        return None
    return {"classification": label, "effectiveness": "未判定",
            "rule_version": ADVANCE_RETREAT_RULE}


def use_candidates(result, selector):
    if selector in ("世爻", "应爻"):
        position = result["palace"]["shi" if selector == "世爻" else "ying"]
        chosen = result["lines"][position - 1]
        relative, element = chosen["relative"], chosen["element"]
        visible = [position]
        # A positional use stays on that line even when its changed relative differs.
        changed = [position] if chosen["transformation"] else []
    else:
        relative = selector
        element = ELEMENTS[(ELEMENTS.index(result["palace"]["element"]) + RELATIVES.index(relative)) % 5]
        visible = [line["position"] for line in result["lines"] if line["relative"] == relative]
        changed = [line["position"] for line in result["lines"]
                   if line["transformation"] and line["transformation"]["relative"] == relative]
    hidden = [line["position"] for line in result["hidden_spirits"] if line["relative"] == relative]
    outside = [label for label in ("month", "day")
               if result["calendar"][label]["relative"] == relative]
    elements = {"用神同类": element, "元神": ELEMENTS[(ELEMENTS.index(element) - 1) % 5],
                "忌神": ELEMENTS[(ELEMENTS.index(element) - 2) % 5],
                "仇神": ELEMENTS[(ELEMENTS.index(element) + 2) % 5]}
    return {"selector": selector, "relative": relative, "element": element,
            "visible_positions": visible, "moving_change_positions": changed,
            "day_month_substitutes_if_absent": outside if not visible else [],
            "hidden_positions_if_absent": hidden if not visible else [],
            "role_elements": elements,
            "role_positions": {role: [line["position"] for line in result["lines"] if line["element"] == el]
                               for role, el in elements.items()},
            "selection_status": "候选集合；多现、动变、日月及伏神的取舍按研判规则说明，未自动断吉凶。"}


def chart(values, *, day_ganzhi, month_branch, topic=None, use_relative=None,
          provenance="user-reported"):
    if not isinstance(month_branch, str) or len(month_branch) != 1 or month_branch not in BRANCHES:
        raise ValueError("月建须为单个地支；按节交月，由上层已核实的历法传入。")
    day_index = ganzhi_index(day_ganzhi)
    if topic is not None and topic not in TOPICS:
        raise ValueError("不支持的问题类别。")
    if use_relative is not None and use_relative not in RELATIVES + ("世爻", "应爻"):
        raise ValueError("用神选择须为六亲类别、世爻或应爻。")
    structure = _divination.from_lines(values, provenance=provenance)
    palace = palace_for(structure["original"]["bits_bottom_to_top"])
    p_element = palace["element"]
    empty = xunkong(day_ganzhi)
    day_branch = day_ganzhi[1]
    rows = dress(structure["original"]["bits_bottom_to_top"], p_element)
    # Critical invariant: changed relatives stay relative to the ORIGINAL palace.
    changed_rows = dress(structure["changed"]["bits_bottom_to_top"], p_element)
    for i, row in enumerate(rows):
        row.update(value=values[i], moving=values[i] in (6, 9),
                   shi=i + 1 == palace["shi"], ying=i + 1 == palace["ying"],
                   spirit=SPIRITS[(SPIRIT_START[day_index % 10] + i) % 6],
                   temporal=temporal_flags(row["branch"], day_branch, month_branch, empty["branches"]))
        row["transformation"] = None
        if row["moving"]:
            change = changed_rows[i].copy()
            change.update(temporal=temporal_flags(change["branch"], day_branch, month_branch, empty["branches"]),
                          return_effect=branch_relation(change["branch"], row["branch"]),
                          advance_retreat_pair=advance_retreat_pair(row["branch"], change["branch"]))
            row["transformation"] = change
        row["day_clash_assessment"] = (
            "旬空爻日冲：先查冲空条件及旺衰救应，不套普通静爻暗动/日破二分；保留旬空与原动静，程序不预判。"
            if row["temporal"]["day_clash"] and row["temporal"]["xunkong"]
            else "静爻日冲：须结合旺衰判暗动或日破，程序不预判。" if row["temporal"]["day_clash"] and not row["moving"]
            else "动爻日冲：保留发动，查旺衰及动变；不一律标日破。" if row["temporal"]["day_clash"]
            else None)
    visible_relatives = {row["relative"] for row in rows}
    hidden = []
    for pure_row in dress(palace["pure_bits_bottom_to_top"], p_element):
        if pure_row["relative"] not in visible_relatives:
            flying = rows[pure_row["position"] - 1]
            pure_row.update(temporal=temporal_flags(pure_row["branch"], day_branch, month_branch, empty["branches"]),
                            flying_branch=flying["branch"],
                            flying_effect=branch_relation(flying["branch"], pure_row["branch"]))
            hidden.append(pure_row)
    edges = []
    for source in rows:
        if source["moving"]:
            for target in rows:
                if target["position"] != source["position"]:
                    edges.append({"source_position": source["position"], "target_position": target["position"],
                                  **branch_relation(source["branch"], target["branch"])})
    result = {
        "schema_version": "2.0", "method": "liuyao-najia-zengshan",
        "input_order": "bottom_to_top", "input_values": list(values),
        "provenance": structure["provenance"],
        "provenance_notice": "来源由调用者声明；user-reported不表示程序目击实投。模拟输入须声明simulated，并保留原始模拟记录。",
        "calendar": {"input_source": "explicit_day_ganzhi_and_solar_month_branch",
                     "day": {"ganzhi": day_ganzhi, "branch": day_branch,
                             "relative": six_relative(p_element, BRANCH_ELEMENT[day_branch])},
                     "month": {"branch": month_branch,
                               "relative": six_relative(p_element, BRANCH_ELEMENT[month_branch])},
                     "xunkong": empty,
                     "notice": "本脚本不从时钟推定月日；时区、节交月、换日设置须由上层校历。"},
        "original": structure["original"], "changed": structure["changed"],
        "hexagram_relations": {"original": hexagram_relations(rows),
                               "changed": hexagram_relations(changed_rows)},
        "palace": palace, "changed_palace_for_identification_only": palace_for(structure["changed"]["bits_bottom_to_top"]),
        "moving_lines": structure["moving_lines"], "lines": rows,
        "changed_chart_context": changed_rows,
        "advance_retreat_rule": {"version": ADVANCE_RETREAT_RULE,
                                 "notice": "只记录本位动变的七组进退配对，未判实际生效；戌丑互化有版本分歧，本表不标进退。"},
        "changed_chart_notice": "变卦全表仅作装卦核对；静爻旁变化不算发动。按动变生克冲合章，变爻只回作用本位动爻，本位及旁爻不能反向生克变爻；日月可以作用变爻。return_effect中的受生/受克只记五行方向，不表示本爻能生克变爻。",
        "missing_relatives": [r for r in RELATIVES if r not in visible_relatives],
        "hidden_spirits": hidden,
        "moving_relations": edges,
        "relations_notice": "关系表表示结构，诸爻不能伤日月；施力是否有效须检查元忌旺衰、空破、合绊及回头生克；无自动加减分。",
        "boundaries": ["进退配对不等于实际进退；未自动认定暗动、真空、合化、墓绝、三合成局或应期。",
                       "六神只辅助取象；用神的现实对应及传统预测效果不由算法确认。"],
    }
    if topic:
        result["topic"] = {"name": topic, **TOPICS[topic]}
    selector = use_relative or (TOPICS[topic]["default"] if topic else None)
    result["use_selection"] = use_candidates(result, selector) if selector else None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("values", nargs=6, type=int, help="初爻至上爻，6/7/8/9")
    parser.add_argument("--day-ganzhi", required=True)
    parser.add_argument("--month-branch", required=True)
    parser.add_argument("--topic", choices=TOPICS)
    parser.add_argument("--use-relative", choices=RELATIVES + ("世爻", "应爻"))
    parser.add_argument("--provenance", choices=_divination.PROVENANCE, default="user-reported",
                        help="输入来源；simulated仅标明模拟，不重新起卦")
    args = parser.parse_args()
    try:
        result = chart(args.values, day_ganzhi=args.day_ganzhi, month_branch=args.month_branch,
                       topic=args.topic, use_relative=args.use_relative, provenance=args.provenance)
    except ValueError as exc:
        print(json.dumps({"error": str(exc), "status": "未排纳甲"}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    from _cli import configure_output
    configure_output()
    sys.exit(main())
