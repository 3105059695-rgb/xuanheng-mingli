import importlib.util
import itertools
import json
import subprocess
import sys
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("divination", Path(__file__).parents[1] / "scripts" / "divination.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DivinationTests(unittest.TestCase):
    def test_object_reduced_basis_keeps_original_you_hour(self):
        raw = module.meihua_objects(17, 10, "raw")
        reduced = module.meihua_objects(17, 10, "reduced")
        self.assertEqual(raw["original"], reduced["original"])
        self.assertEqual(raw["moving_lines"], [3])
        self.assertEqual(reduced["moving_lines"], [5])
        self.assertEqual(reduced["arithmetic"]["moving_number"], 11)
        self.assertEqual(reduced["arithmetic"]["moving_hour_component"], 10)

    def test_body_and_mutual_for_all_hexagrams_and_each_moving_line(self):
        for upper, lower, moving in itertools.product(range(1, 9), range(1, 9), range(1, 7)):
            result = module.meihua_structure(upper, lower, moving)
            original = result["original"]["bits_bottom_to_top"]
            changed = result["changed"]["bits_bottom_to_top"]
            body_position = "upper" if moving <= 3 else "lower"
            self.assertEqual(result["body_position"], body_position)
            self.assertEqual(result["body"], result["changed"][body_position])
            self.assertTrue(all(relation["body"] == result["body"] for relation in result["relations"].values()))
            pure = upper == lower and upper in (1, 8)
            source = changed if pure else original
            expected_mutual = [source[1], source[2], source[3], source[2], source[3], source[4]]
            self.assertEqual(result["mutual"]["bits_bottom_to_top"], expected_mutual)
            mechanical = module.meihua_structure(upper, lower, moving, "mechanical")
            self.assertEqual(mechanical["mutual"]["bits_bottom_to_top"], [original[1], original[2], original[3], original[2], original[3], original[4]])

    def test_pure_qian_kun_outer_line_mutual_may_remain_pure(self):
        for trigram, expected_number in [(1, 1), (8, 2)]:
            for moving in (1, 6):
                result = module.meihua_structure(trigram, trigram, moving)
                self.assertTrue(result["mutual_policy"]["used_changed_hexagram"])
                self.assertEqual(result["mutual"]["number"], expected_number)

    def test_supplied_records_retain_simulation_identity(self):
        groups = ["223", "233", "333", "233", "223", "222"]
        self.assertEqual(module.from_coins(groups, provenance="simulated")["provenance"], "simulated")
        self.assertEqual(module.from_lines([7] * 6, provenance="simulated")["provenance"], "simulated")
        self.assertEqual(module.meihua_sounds(9, 13, 10, provenance="simulated")["provenance"], "simulated")
        self.assertEqual(module.meihua_objects(17, 10, provenance="simulated")["provenance"], "simulated")
        self.assertEqual(module.meihua_sounds(9, 13, 10)["arithmetic"]["moving_number"], 32)
        with self.assertRaises(ValueError):
            module.meihua_sounds(1, 5, 10, provenance="guessed-but-claimed-observed")

    def test_coin_input_snapshot_does_not_change_after_call(self):
        groups = ["223"] * 6
        result = module.from_coins(groups)
        groups[0] = "333"
        self.assertEqual(result["coins_bottom_to_top"][0], "223")
        self.assertEqual(result["lines"][0]["value"], 7)
        with self.assertRaises(ValueError):
            module.from_coins([223] * 6)

    def test_calendar_source_and_boundary_remain_explicit(self):
        result = module.meihua_time(5, 12, 17, 9, "no", calendar_source="已核历表", day_boundary="zi-start")
        self.assertEqual(result["calendar"]["day_boundary"], "zi-start")
        self.assertEqual(result["calendar"]["source"], "已核历表")
        self.assertFalse(result["calendar"]["conversion_performed"])
        self.assertEqual(result["inputs"]["lunar_day"], 17)
        with self.assertRaises(ValueError):
            module.meihua_time(5, 12, 17, 9, "no", day_boundary="silently-guess")

    def test_simulator_cli_returns_a_replayable_coin_record(self):
        script = Path(__file__).parents[1] / "scripts" / "divination.py"
        run = subprocess.run([sys.executable, str(script), "simulate"], capture_output=True, text=True, encoding="utf-8", check=True)
        result = json.loads(run.stdout)
        replay = module.from_coins(result["coins_bottom_to_top"], provenance="simulated")
        self.assertEqual(result["provenance"], "simulated")
        self.assertEqual(result["original"], replay["original"])
        self.assertEqual(result["changed"], replay["changed"])

    def test_guan_mei_original_text_example(self):
        result = module.meihua_time(5, 12, 17, 9, "no")
        self.assertEqual(result["original"]["number"], 49)
        self.assertEqual(result["changed"]["number"], 31)
        self.assertEqual(result["moving_lines"], [1])
        self.assertEqual(result["mutual"]["number"], 44)
        self.assertEqual((result["body"], result["use"]), ("兑", "离"))

    def test_direction_tai_and_pi(self):
        self.assertEqual(module.from_lines([7, 7, 7, 8, 8, 8])["original"]["name"], "泰")
        self.assertEqual(module.from_lines([8, 8, 8, 7, 7, 7])["original"]["name"], "否")

    def test_all_4096_line_combinations(self):
        for values in itertools.product((6, 7, 8, 9), repeat=6):
            result = module.from_lines(values)
            original = result["original"]["bits_bottom_to_top"]
            changed = result["changed"]["bits_bottom_to_top"]
            flipped = [i + 1 for i, pair in enumerate(zip(original, changed)) if pair[0] != pair[1]]
            self.assertEqual(flipped, [i + 1 for i, v in enumerate(values) if v in (6, 9)])

    def test_all_64_distinct_hexagrams(self):
        numbers = {module.describe(bits)["number"] for bits in itertools.product((0, 1), repeat=6)}
        self.assertEqual(numbers, set(range(1, 65)))

    def test_all_moving_and_static(self):
        self.assertEqual(module.from_lines([9] * 6)["changed"]["name"], "坤")
        self.assertEqual(module.from_lines([6] * 6)["changed"]["name"], "乾")
        self.assertEqual(module.from_lines([8] * 6)["moving_lines"], [])

    def test_coin_sums(self):
        result = module.from_coins(["222", "223", "233", "333", "323", "232"])
        self.assertEqual([x["value"] for x in result["lines"]], [6, 7, 8, 9, 8, 7])

    def test_exact_division(self):
        result = module.meihua_time(1, 1, 6, 4, "no")
        self.assertEqual(result["original"]["upper"], "坤")
        self.assertEqual(result["original"]["lower"], "震")
        self.assertEqual(result["moving_lines"], [6])

    def test_knocking_case_from_text(self):
        result = module.meihua_sounds(1, 5, 10)
        self.assertEqual([result[x]["number"] for x in ("original", "changed", "mutual")], [44, 57, 1])
        self.assertEqual(result["moving_lines"], [4])
        self.assertEqual(result["relations"]["original_use"]["relation"], "用克体")
        self.assertEqual(result["relations"]["changed_use"]["relation"], "比和")

    def test_guan_mei_relations(self):
        result = module.meihua_time(5, 12, 17, 9, "no")
        self.assertEqual(result["relations"]["original_use"]["relation"], "用克体")
        self.assertEqual(result["relations"]["changed_use"]["relation"], "用生体")

    def test_peony_case_from_text(self):
        result = module.meihua_time(6, 3, 16, 4, "no")
        self.assertEqual([result[x]["number"] for x in ("original", "changed", "mutual")], [44, 50, 1])
        self.assertEqual(result["moving_lines"], [5])

    def test_pure_hexagram_mutual_convention(self):
        classical = module.meihua_structure(1, 1, 2)
        mechanical = module.meihua_structure(1, 1, 2, "mechanical")
        self.assertTrue(classical["mutual_policy"]["used_changed_hexagram"])
        self.assertEqual(classical["mechanical_mutual"]["number"], 1)
        self.assertNotEqual(classical["mutual"]["number"], mechanical["mutual"]["number"])

    def test_object_count_variants_are_visible(self):
        raw = module.meihua_objects(17, 3, "raw")
        reduced = module.meihua_objects(17, 3, "reduced")
        self.assertEqual(raw["original"], reduced["original"])
        self.assertEqual(raw["moving_lines"], [2])
        self.assertEqual(reduced["moving_lines"], [4])

    def test_relation_direction_all_five(self):
        self.assertEqual([module.relation_to_body("震", other)["relation"] for other in ["巽", "坎", "离", "坤", "乾"]], ["比和", "用生体", "体生用", "体克用", "用克体"])

    def test_reject_unsupported_sound_and_object_inputs(self):
        for args in [(0, 1, 2), (1, 1, 13), (1, True, 2)]:
            with self.assertRaises(ValueError):
                module.meihua_sounds(*args)
        with self.assertRaises(ValueError):
            module.meihua_objects(0, 1)
        with self.assertRaises(ValueError):
            module.meihua_objects(1, 1, "undisclosed")

    def test_invalid_inputs(self):
        for values in ([7] * 5, [7] * 7, [5, 7, 7, 7, 7, 7], [True] * 6):
            with self.assertRaises(ValueError):
                module.from_lines(values)
        with self.assertRaises(ValueError):
            module.from_coins(["heads"] * 6)
        for args in [(0, 1, 1, 1, "no"), (1, 13, 1, 1, "no"), (1, 1, 31, 1, "no"),
                     (1, 1, 1, 13, "no"), (1, 1, 1, 1, "yes")]:
            with self.assertRaises(ValueError):
                module.meihua_time(*args)


if __name__ == "__main__":
    unittest.main()
