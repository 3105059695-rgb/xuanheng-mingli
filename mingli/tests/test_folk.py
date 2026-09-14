import importlib.util
import itertools
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "folk.py"
spec = importlib.util.spec_from_file_location("folk", SCRIPT)
folk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(folk)


class FolkTests(unittest.TestCase):
    def test_stage_contract_cannot_silently_truncate_or_consume_generator(self):
        with self.assertRaises(ValueError):
            folk.three_stages([3, 5, 5], ["月", "日"], "audit")
        with self.assertRaises(ValueError):
            folk.three_stages([3, 5], ["月", "日", "时"], "audit")
        result = folk.three_stages((v for v in [3, 5, 5]), (v for v in ["月", "日", "时"]), "audit")
        self.assertEqual(result["input_numbers"], [3, 5, 5])
        self.assertEqual(result["final_palace"], folk.PALACES[result["arithmetic_check"]["zero_based_index"]])

    def test_every_same_lot_confirmation_sequence(self):
        # One lot ends at the first non-holy throw; three holy throws confirm it.
        face_pairs = [("flat", "flat"), ("flat", "convex"), ("convex", "flat"), ("convex", "convex")]
        for length in range(1, 4):
            for throws in itertools.product(face_pairs, repeat=length):
                failures = [i for i, (first, second) in enumerate(throws) if first == second]
                if failures and failures[0] != length - 1:
                    with self.subTest(throws=throws), self.assertRaises(ValueError):
                        folk.longshan_lot_attempt(throws)
                else:
                    expected = "redraw-lot" if failures else "confirmed" if length == 3 else "await-next-throw"
                    self.assertEqual(folk.longshan_lot_attempt(throws)["status"], expected)

    def test_1936_printed_example(self):
        result = folk.xiaoliuren_time(3, 5, "辰")
        self.assertEqual([s["end"] for s in result["stages"]], ["速喜", "大安", "小吉"])
        self.assertEqual(result["source"]["pdf_pages"], [66, 67])

    def test_every_stage_includes_start_as_one(self):
        self.assertEqual(folk.xiaoliuren_time(1, 1, 1)["final_palace"], "大安")
        for start in range(6):
            self.assertEqual(folk.count_stage(start, 1, "x")["end_index"], start)
            self.assertEqual(folk.count_stage(start, 7, "x")["end_index"], start)
            self.assertEqual(folk.count_stage(start, 6, "x")["end_index"], (start + 5) % 6)

    def test_all_month_day_hour_inputs_against_manual_walking(self):
        for values in itertools.product(range(1, 13), range(1, 31), range(1, 13)):
            expected = 0
            expected_stages = []
            for count in values:
                for _ in range(count - 1):
                    expected = 0 if expected == 5 else expected + 1
                expected_stages.append(folk.PALACES[expected])
            result = folk.xiaoliuren_time(*values)
            self.assertEqual([s["end"] for s in result["stages"]], expected_stages)
            self.assertEqual(result["final_palace"], folk.PALACES[expected])

    def test_number_variant_published_example(self):
        result = folk.xiaoliuren_numbers(3, 3, 3)
        self.assertEqual([s["end"] for s in result["stages"]], ["速喜", "小吉", "大安"])
        self.assertNotEqual(result["rule_version"], folk.TIME_RULE)

    def test_number_large_input_uses_bounded_trace(self):
        result = folk.xiaoliuren_numbers(10**12, 1, 1)
        self.assertEqual(result["final_palace"], "赤口")
        self.assertEqual(len(result["stages"][0]["trace"]), 30)
        self.assertTrue(result["stages"][0]["trace_truncated"])

    def test_leap_month_requires_visible_choice(self):
        with self.assertRaises(ValueError):
            folk.xiaoliuren_time(6, 3, 5, is_leap=True)
        result = folk.xiaoliuren_time(6, 3, 5, is_leap=True, leap_policy="repeat-month")
        self.assertEqual(result["final_palace"], folk.xiaoliuren_time(6, 3, 5)["final_palace"])
        self.assertTrue(result["calendar"]["is_leap"])

    def test_day_boundary_is_recorded_not_secretly_converted(self):
        result = folk.xiaoliuren_time(12, 30, "子", day_boundary="zi-start")
        self.assertEqual(result["calendar"]["day"], 30)
        self.assertEqual(result["calendar"]["day_boundary"], "zi-start")
        self.assertFalse(result["calendar"]["conversion_performed"])

    def test_invalid_calendar_inputs(self):
        invalid = [(0, 1, 1), (13, 1, 1), (1, 0, 1), (1, 31, 1), (1, 1, 0), (1, 1, 13), (True, 1, 1), (1, 1, "23:30")]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                folk.xiaoliuren_time(*args)
        for options in [{"leap_policy": "next-month"}, {"day_boundary": "guess"}, {"is_leap": "no"}, {"calendar_source": ""}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                folk.xiaoliuren_time(1, 1, 1, **options)

    def test_invalid_number_inputs(self):
        for value in (0, -1, 0.5, True, "3", 10**12 + 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                folk.xiaoliuren_numbers(value, 1, 1)

    def test_all_physical_cup_combinations(self):
        expected = {("flat", "flat"): "笑筊", ("convex", "convex"): "怒筊", ("flat", "convex"): "圣筊", ("convex", "flat"): "圣筊"}
        for faces, name in expected.items():
            self.assertEqual(folk.jiaobei(*faces)["name"], name)
        with self.assertRaises(ValueError):
            folk.jiaobei("阴", "阳")

    def test_lot_attempt_lifecycle(self):
        holy = ("flat", "convex")
        laugh = ("flat", "flat")
        self.assertEqual(folk.longshan_lot_attempt([holy])["status"], "await-next-throw")
        self.assertEqual(folk.longshan_lot_attempt([holy, holy])["required_remaining"], 1)
        self.assertEqual(folk.longshan_lot_attempt([holy] * 3)["status"], "confirmed")
        self.assertEqual(folk.longshan_lot_attempt([holy, laugh])["status"], "redraw-lot")
        with self.assertRaises(ValueError):
            folk.longshan_lot_attempt([holy, laugh, holy])

    def test_simulation_label_survives_every_record(self):
        self.assertEqual(folk.xiaoliuren_numbers(2, 4, 6, provenance="simulated")["provenance"], "simulated")
        result = folk.longshan_lot_attempt([("flat", "convex")], provenance="simulated")
        self.assertEqual(result["throws"][0]["provenance"], "simulated")

    def test_cli_invalid_zero_exits_with_error(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "xiaoliuren-numbers", "0", "2", "3"], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("first must be an integer", result.stderr)


if __name__ == "__main__":
    unittest.main()
