import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys
import unittest

spec = importlib.util.spec_from_file_location("liuyao", Path(__file__).parents[1] / "scripts" / "liuyao.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# Independent textual fixtures from 增删卜易 八宫图 (not from PALACE_MASKS).
PALACES = {
    "乾": "乾 姤 遁 否 观 剥 晋 大有",
    "坎": "坎 节 屯 既济 革 丰 明夷 师",
    "艮": "艮 贲 大畜 损 睽 履 中孚 渐",
    "震": "震 豫 解 恒 升 井 大过 随",
    "巽": "巽 小畜 家人 益 无妄 噬嗑 颐 蛊",
    "离": "离 旅 鼎 未济 蒙 涣 讼 同人",
    "坤": "坤 复 临 泰 大壮 夬 需 比",
    "兑": "兑 困 萃 咸 蹇 谦 小过 归妹",
}


def calculate(values, day="甲子", month="寅", **kwargs):
    return module.chart(values, day_ganzhi=day, month_branch=month, **kwargs)


class LiuyaoTests(unittest.TestCase):
    def test_day_relation_direction_is_explicit(self):
        self.assertEqual(module.branch_relation("申", "丑")["direction_sentence"], "丑土生申金")
        self.assertEqual(module.branch_relation("申", "亥")["direction_sentence"], "申金生亥水")
        self.assertEqual(module.branch_relation("辰", "亥")["direction_sentence"], "辰土克亥水")

    def test_independent_64_palace_and_shi_ying_fixture(self):
        seen = set()
        for bits in itertools.product((0, 1), repeat=6):
            result = calculate([7 if b else 8 for b in bits])
            name = result["original"]["name"]
            expected_palace, stage = next((p, names.split().index(name)) for p, names in PALACES.items()
                                          if name in names.split())
            self.assertEqual(result["palace"]["name"], expected_palace, name)
            shi = [6, 1, 2, 3, 4, 5, 4, 3][stage]
            self.assertEqual(result["palace"]["shi"], shi, name)
            self.assertEqual(result["palace"]["ying"], shi + 3 if shi <= 3 else shi - 3, name)
            self.assertEqual(sum(line["shi"] for line in result["lines"]), 1)
            self.assertEqual(sum(line["ying"] for line in result["lines"]), 1)
            seen.add(name)
        self.assertEqual(len(seen), 64)

    def test_all_64_najia_inner_outer_orientation(self):
        # Independently transcribed 浑天甲子章; all tuples are bottom to top.
        expected = {
            "乾": ("子寅辰", "午申戌"), "坎": ("寅辰午", "申戌子"),
            "艮": ("辰午申", "戌子寅"), "震": ("子寅辰", "午申戌"),
            "巽": ("丑亥酉", "未巳卯"), "离": ("卯丑亥", "酉未巳"),
            "坤": ("未巳卯", "丑亥酉"), "兑": ("巳卯丑", "亥酉未"),
        }
        stems = {"乾": ("甲", "壬"), "坤": ("乙", "癸"), "坎": ("戊", "戊"),
                 "艮": ("丙", "丙"), "震": ("庚", "庚"), "巽": ("辛", "辛"),
                 "离": ("己", "己"), "兑": ("丁", "丁")}
        for bits in itertools.product((0, 1), repeat=6):
            result = calculate([7 if b else 8 for b in bits])
            lower, upper = result["original"]["lower"], result["original"]["upper"]
            expected_branches = expected[lower][0] + expected[upper][1]
            self.assertEqual("".join(line["branch"] for line in result["lines"]), expected_branches)
            self.assertEqual("".join(line["ganzhi"][0] for line in result["lines"]),
                             stems[lower][0] * 3 + stems[upper][1] * 3)
            for row in result["lines"]:
                module.ganzhi_index(row["ganzhi"])

    def test_zengshan_dongbian_xu_to_song(self):
        # 动变章第七: 水天需之天水讼，初、三、四、上动。日月为测试补入。
        result = calculate([9, 7, 9, 6, 7, 6])
        self.assertEqual((result["original"]["name"], result["changed"]["name"]), ("需", "讼"))
        self.assertEqual(result["palace"]["name"], "坤")
        self.assertEqual(result["changed_palace_for_identification_only"]["name"], "离")
        self.assertEqual((result["palace"]["shi"], result["palace"]["ying"]), (4, 1))
        self.assertEqual([r["relative"] + r["branch"] for r in result["lines"]],
                         ["妻财子", "官鬼寅", "兄弟辰", "子孙申", "兄弟戌", "妻财子"])
        self.assertEqual([r["transformation"]["relative"] + r["transformation"]["branch"]
                          for r in result["lines"] if r["moving"]],
                         ["官鬼寅", "父母午", "父母午", "兄弟戌"])
        self.assertIsNone(result["lines"][1]["transformation"])

    def test_zengshan_chen_wushen_qian_xiaoxu(self):
        # 用神元神忌神仇神章第九: 辰月戊申日，乾之小畜。
        result = calculate([7, 7, 7, 9, 7, 7], "戊申", "辰", use_relative="父母")
        self.assertEqual(result["changed"]["name"], "小畜")
        self.assertEqual(result["calendar"]["xunkong"]["branches"], ["寅", "卯"])
        self.assertEqual(result["use_selection"]["visible_positions"], [3, 6])
        self.assertTrue(result["lines"][5]["temporal"]["month_break"])
        self.assertTrue(result["lines"][1]["temporal"]["day_clash"])
        self.assertIn("冲空", result["lines"][1]["day_clash_assessment"])
        self.assertEqual(result["lines"][3]["transformation"]["branch"], "未")
        self.assertTrue(result["lines"][3]["transformation"]["return_effect"]["six_combination"])
        self.assertEqual([r["spirit"] for r in result["lines"]],
                         ["勾陈", "螣蛇", "白虎", "玄武", "青龙", "朱雀"])

    def test_zengshan_hidden_gou_and_dun(self):
        gou = calculate([8, 7, 7, 7, 7, 7], "甲子", "辰", use_relative="妻财")
        self.assertEqual([(r["position"], r["ganzhi"], r["relative"]) for r in gou["hidden_spirits"]],
                         [(2, "甲寅", "妻财")])
        self.assertEqual(gou["hidden_spirits"][0]["flying_branch"], "亥")
        self.assertEqual(gou["hidden_spirits"][0]["flying_effect"]["element_effect"], "生")
        dun = calculate([8, 8, 7, 7, 7, 7], use_relative="子孙")
        self.assertEqual([(r["position"], r["ganzhi"], r["relative"]) for r in dun["hidden_spirits"]],
                         [(1, "甲子", "子孙"), (2, "甲寅", "妻财")])
        self.assertEqual(dun["hidden_spirits"][0]["flying_effect"]["element_effect"], "克")

    def test_document_hidden_original_case(self):
        # 飞伏神章：卯月壬辰日候文书，贲；二爻下父母午火伏而旬空。
        result = calculate([7, 8, 7, 8, 8, 7], "壬辰", "卯", topic="document")
        self.assertEqual(result["original"]["name"], "贲")
        parent = next(row for row in result["hidden_spirits"] if row["relative"] == "父母")
        self.assertEqual((parent["position"], parent["ganzhi"], parent["flying_branch"]), (2, "丙午", "丑"))
        self.assertTrue(parent["temporal"]["xunkong"])
        self.assertEqual(result["use_selection"]["hidden_positions_if_absent"], [2])

    def test_every_sexagenary_day_xunkong(self):
        expected = [("甲子", "戌亥"), ("甲戌", "申酉"), ("甲申", "午未"),
                    ("甲午", "辰巳"), ("甲辰", "寅卯"), ("甲寅", "子丑")]
        for i in range(60):
            gz = module.STEMS[i % 10] + module.BRANCHES[i % 12]
            empty = module.xunkong(gz)
            self.assertEqual((empty["xun_start"], "".join(empty["branches"])), expected[i // 10])
            self.assertNotIn(gz[1], empty["branches"])
            self.assertEqual(empty["days_until_next_xun"], 10 - i % 10)

    def test_all_4096_changes_keep_original_palace(self):
        for values in itertools.product((6, 7, 8, 9), repeat=6):
            result = calculate(values)
            element = result["palace"]["element"]
            for row in result["lines"]:
                change = row["transformation"]
                self.assertEqual(change is not None, row["moving"])
                if change:
                    self.assertEqual(change["relative"], module.six_relative(element, change["element"]))
            self.assertTrue(all(edge["source_position"] in result["moving_lines"] for edge in result["moving_relations"]))

    def test_all_palaces_have_all_five_relatives_when_pure(self):
        for _, bits in module._divination.TRIGRAMS:
            result = calculate([7 if b else 8 for b in bits + bits])
            self.assertEqual(set(r["relative"] for r in result["lines"]), set(module.RELATIVES))
            self.assertEqual(result["hidden_spirits"], [])

    def test_independent_six_clash_and_six_combination_sets(self):
        clashes, combinations = set(), set()
        for bits in itertools.product((0, 1), repeat=6):
            result = calculate([7 if b else 8 for b in bits])
            if result["hexagram_relations"]["original"]["six_clash"]:
                clashes.add(result["original"]["name"])
            if result["hexagram_relations"]["original"]["six_combination"]:
                combinations.add(result["original"]["name"])
        self.assertEqual(clashes, set("乾 坤 震 巽 坎 离 艮 兑 无妄 大壮".split()))
        self.assertEqual(combinations, set("否 泰 复 豫 旅 贲 节 困".split()))

    def test_month_break_not_all_day_clashes_are_day_breaks(self):
        result = calculate([7] * 6, "甲午", "午")
        self.assertTrue(result["lines"][0]["temporal"]["month_break"])
        self.assertTrue(result["lines"][0]["temporal"]["day_clash"])
        self.assertNotIn("day_break", result["lines"][0]["temporal"])

    def test_use_selectors_and_roles(self):
        result = calculate([7] * 6, topic="wealth")
        self.assertEqual(result["use_selection"]["visible_positions"], [2])
        self.assertEqual(result["use_selection"]["role_elements"],
                         {"用神同类": "木", "元神": "水", "忌神": "金", "仇神": "土"})
        self.assertIsNone(calculate([7] * 6, topic="relationship")["use_selection"])
        result = calculate([7] * 6, topic="relationship", use_relative="应爻")
        self.assertEqual(result["use_selection"]["visible_positions"], [3])
        result = calculate([8, 7, 7, 7, 7, 7], "甲寅", "卯", use_relative="妻财")
        self.assertEqual(result["use_selection"]["day_month_substitutes_if_absent"], ["month", "day"])

    def test_all_ten_day_stems_spirit_starts(self):
        expected = "青龙 青龙 朱雀 朱雀 勾陈 螣蛇 白虎 白虎 玄武 玄武".split()
        for i, spirit in enumerate(expected):
            result = calculate([7] * 6, module.STEMS[i] + module.BRANCHES[i])
            self.assertEqual(result["lines"][0]["spirit"], spirit)
            self.assertEqual(set(row["spirit"] for row in result["lines"]), set(module.SPIRITS))

    def test_position_selector_keeps_its_change_when_relative_changes(self):
        # 日辰章：申月戊午日，遁之姤，世二午火化亥水回头克。
        result = calculate([8, 6, 7, 7, 7, 7], "戊午", "申", use_relative="世爻")
        self.assertEqual(result["palace"]["shi"], 2)
        self.assertEqual(result["lines"][1]["transformation"]["relative"], "子孙")
        self.assertEqual(result["use_selection"]["moving_change_positions"], [2])
        self.assertEqual(result["lines"][1]["transformation"]["return_effect"]["direction_sentence"],
                         "亥水克午火")

    def test_position_selector_does_not_collect_other_same_relative_changes(self):
        # 大壮上爻独动成大有：世四午火父母静，上六变巳火父母不属世位。
        values = [7, 7, 7, 7, 8, 6]
        self_use = calculate(values, use_relative="世爻")
        self.assertEqual(self_use["use_selection"]["visible_positions"], [4])
        self.assertEqual(self_use["use_selection"]["moving_change_positions"], [])
        parent_use = calculate(values, use_relative="父母")
        self.assertEqual(parent_use["use_selection"]["moving_change_positions"], [6])
        # 同一问题选择应爻时，同样保留固定爻位，不能转成六亲类别检索。
        response_use = calculate([7, 7, 9, 7, 7, 7], use_relative="应爻")
        self.assertEqual(response_use["use_selection"]["visible_positions"], [3])
        self.assertEqual(response_use["use_selection"]["moving_change_positions"], [3])

    def test_day_clash_of_empty_line_preserves_chongkong_branch(self):
        # 甲子旬己巳日，姤二亥水静而空，又被巳日冲；不能只给暗动/日破二选一。
        result = calculate([8, 7, 7, 7, 7, 7], "己巳", "寅")
        row = result["lines"][1]
        self.assertTrue(row["temporal"]["xunkong"])
        self.assertTrue(row["temporal"]["day_clash"])
        self.assertIn("冲空", row["day_clash_assessment"])
        self.assertFalse(row["moving"])

    def test_zengshan_kun_to_jin_return_and_horizontal_relations(self):
        # 动变生克冲合章：子月卯日，坤四、上动之晋；己卯补齐日干。
        result = calculate([8, 8, 8, 6, 8, 6], "己卯", "子")
        self.assertEqual((result["original"]["name"], result["changed"]["name"]), ("坤", "晋"))
        upper_change = result["lines"][5]["transformation"]
        self.assertEqual((upper_change["branch"], upper_change["relative"]), ("巳", "父母"))
        self.assertEqual(upper_change["return_effect"]["direction_sentence"], "巳火克酉金")
        self.assertEqual(upper_change["temporal"]["month"]["direction_sentence"], "子水克巳火")
        fourth_change = result["lines"][3]["transformation"]
        self.assertTrue(fourth_change["temporal"]["day_clash"])
        edge = next(e for e in result["moving_relations"]
                    if (e["source_position"], e["target_position"]) == (4, 6))
        self.assertEqual((edge["source_branch"], edge["target_branch"]), ("丑", "酉"))
        self.assertTrue(all(e["source_branch"] == result["lines"][e["source_position"] - 1]["branch"]
                            and e["target_branch"] == result["lines"][e["target_position"] - 1]["branch"]
                            for e in result["moving_relations"]))

    def test_zengshan_jin_to_bo_static_changed_context_is_not_use(self):
        # 飞伏章晋之剥：之卦五爻旁列子水，但只有四爻动，子孙仍取初爻伏神。
        result = calculate([8, 8, 8, 9, 8, 7], "戊申", "寅", use_relative="子孙")
        self.assertEqual((result["original"]["name"], result["changed"]["name"]), ("晋", "剥"))
        self.assertEqual(result["changed_chart_context"][4]["relative"], "子孙")
        self.assertEqual(result["use_selection"]["moving_change_positions"], [])
        self.assertEqual(result["use_selection"]["hidden_positions_if_absent"], [1])

    def test_simulated_coin_record_keeps_provenance_in_najia(self):
        record = module._divination.from_coins(["223", "233", "333", "233", "223", "222"],
                                              provenance="simulated")
        values = [row["value"] for row in record["lines"]]
        result = calculate(values, provenance=record["provenance"])
        self.assertEqual(result["provenance"], "simulated")
        self.assertEqual(result["input_values"], values)
        self.assertEqual(result["original"], record["original"])
        self.assertEqual(result["changed"], record["changed"])
        self.assertEqual(result["moving_lines"], record["moving_lines"])
        with self.assertRaises(ValueError):
            calculate(values, provenance="witnessed")

    def test_advance_retreat_seven_pair_textual_fixture(self):
        # 增删第二十九章（维基/识典转录）：七组；不把异本多出的戌丑组默认为通例。
        pairs = ["亥子", "寅卯", "巳午", "申酉", "丑辰", "辰未", "未戌"]
        for original, changed in pairs:
            advance = module.advance_retreat_pair(original, changed)
            retreat = module.advance_retreat_pair(changed, original)
            self.assertEqual(advance["classification"], "进神配对")
            self.assertEqual(retreat["classification"], "退神配对")
            self.assertEqual(advance["effectiveness"], "未判定")
            self.assertEqual(retreat["rule_version"], "zengshan-seven-pairs-v1")
        for original, changed in ("戌丑", "丑戌", "辰戌", "丑未", "子子", "午未"):
            self.assertIsNone(module.advance_retreat_pair(original, changed))

    def test_original_heng_daguo_only_moving_line_gets_pair(self):
        # 申月癸卯日恒之大过：五爻申化酉为进；上爻戌旁列未，静而不作退。
        result = calculate([8, 7, 7, 7, 6, 8], "癸卯", "申", topic="career")
        self.assertEqual((result["original"]["name"], result["changed"]["name"]), ("恒", "大过"))
        change = result["lines"][4]["transformation"]
        self.assertEqual((result["lines"][4]["branch"], change["branch"]), ("申", "酉"))
        self.assertEqual(change["advance_retreat_pair"]["classification"], "进神配对")
        self.assertEqual(change["advance_retreat_pair"]["effectiveness"], "未判定")
        self.assertIsNone(result["lines"][5]["transformation"])
        self.assertNotIn("advance_retreat_pair", result["changed_chart_context"][5])

    def test_retreat_pair_does_not_assert_effect_in_near_term(self):
        # 进退章反例：申月辛卯日夬之大壮，酉化申；原文以旺而近事不退。
        result = calculate([7, 7, 7, 7, 9, 8], "辛卯", "申", use_relative="世爻")
        self.assertEqual((result["original"]["name"], result["changed"]["name"]), ("夬", "大壮"))
        row = result["lines"][4]
        self.assertEqual(row["temporal"]["month"]["element_effect"], "比和")
        self.assertTrue(row["transformation"]["temporal"]["month"]["same_branch"])
        pair = row["transformation"]["advance_retreat_pair"]
        self.assertEqual(pair["classification"], "退神配对")
        self.assertEqual(pair["effectiveness"], "未判定")
        self.assertNotIn("auspicious", pair)

    def test_empty_broken_advance_pair_preserves_waiting_conditions(self):
        # 酉月庚戌日屯之节：寅旬空、化卯空破；原章论待时，不删除配对或预判生效。
        result = calculate([7, 6, 8, 8, 7, 8], "庚戌", "酉", use_relative="子孙")
        self.assertEqual((result["original"]["name"], result["changed"]["name"]), ("屯", "节"))
        row = result["lines"][1]
        self.assertTrue(row["temporal"]["xunkong"])
        change = row["transformation"]
        self.assertTrue(change["temporal"]["xunkong"])
        self.assertTrue(change["temporal"]["month_break"])
        self.assertEqual(change["advance_retreat_pair"]["classification"], "进神配对")
        self.assertEqual(change["advance_retreat_pair"]["effectiveness"], "未判定")

    def test_existing_cli_and_explicit_simulated_source(self):
        command = [sys.executable, str(Path(module.__file__)), "7", "7", "7", "9", "7", "7",
                   "--day-ganzhi", "戊申", "--month-branch", "辰", "--use-relative", "父母"]
        for flags, provenance in (([], "user-reported"), (["--provenance", "simulated"], "simulated")):
            with self.subTest(provenance=provenance):
                process = subprocess.run(command + flags, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(process.returncode, 0, process.stderr)
                result = json.loads(process.stdout)
                self.assertEqual(result["provenance"], provenance)
                self.assertEqual((result["original"]["name"], result["changed"]["name"]), ("乾", "小畜"))
                self.assertEqual(result["moving_lines"], [4])
                self.assertEqual(result["use_selection"]["visible_positions"], [3, 6])

    def test_invalid_inputs(self):
        for day in ("甲丑", "子", "甲子日", "", None, 12):
            with self.assertRaises(ValueError):
                calculate([7] * 6, day)
        for month in ("正月", "寅月", "", None, 1):
            with self.assertRaises(ValueError):
                calculate([7] * 6, month=month)
        for values in ([7] * 5, [True] * 6, [5] * 6):
            with self.assertRaises(ValueError):
                calculate(values)
        with self.assertRaises(ValueError):
            calculate([7] * 6, use_relative="偏财")
        with self.assertRaises(ValueError):
            calculate([7] * 6, topic="unknown")


if __name__ == "__main__":
    unittest.main()
