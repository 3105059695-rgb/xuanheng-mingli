"""一手时区样例、缺失/重叠边界、同一瞬间和现有排盘口径衔接。"""

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("time_normalize", SCRIPTS / "time_normalize.py")
normalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalizer)
spec_bazi = importlib.util.spec_from_file_location("bazi_time_test", SCRIPTS / "bazi.py")
bazi = importlib.util.module_from_spec(spec_bazi)
spec_bazi.loader.exec_module(bazi)


class PublishedTimezoneSamples(unittest.TestCase):
    def test_python_documented_los_angeles_fold_retains_both_instants(self):
        # Python zoneinfo 文档示例：2020-11-01 01:00 对应 -07:00 和 -08:00。
        result = normalizer.normalize("2020-11-01T01:00", "America/Los_Angeles", adopt_utc8=True)
        self.assertEqual("needs_fold_resolution", result["status"])
        self.assertFalse(result["bazi_ready"])
        self.assertIsNone(result["bazi_input"])
        self.assertEqual(["2020-11-01T08:00:00+00:00", "2020-11-01T09:00:00+00:00"], [row["utc_instant"] for row in result["candidates"]])
        self.assertEqual([0, 1], [row["fold"] for row in result["candidates"]])

    def test_fold_choice_and_original_record_are_retained(self):
        result = normalizer.normalize("2020-11-01T01:00", "America/Los_Angeles", fold=1, adopt_utc8=True)
        self.assertTrue(result["original_wall_time_was_ambiguous"])
        self.assertEqual("2020-11-01T01:00", result["input"]["local_original"])
        self.assertEqual("2020-11-01T17:00:00+08:00", result["bazi_input"]["solar"])
        self.assertTrue(result["bazi_ready"])

    def test_offset_from_record_can_disambiguate_without_guessing_fold(self):
        result = normalizer.normalize("2020-11-01T01:00", "America/Los_Angeles", recorded_offset="-07:00")
        self.assertEqual(0, result["candidates"][0]["fold"])
        self.assertEqual(1, len(result["candidates"]))
        self.assertFalse(result["bazi_ready"])

    def test_prc_1991_summer_clock_is_not_already_standard_time(self):
        # IANA asia 的 PRC 1987—1991 四月/九月规则；不是对用户出生证的证明。
        result = normalizer.normalize("1991-07-01T12:00", "Asia/Shanghai", adopt_utc8=True)
        row = result["candidates"][0]
        self.assertEqual(9 * 3600, row["utc_offset_seconds"])
        self.assertEqual(3600, row["dst_adjustment_seconds"])
        self.assertEqual("1991-07-01T11:00:00+08:00", row["utc8_same_instant"])
        self.assertEqual("1991-07-01T03:00:00+00:00", row["utc_instant"])

    def test_prc_1991_backward_transition_has_two_candidates(self):
        result = normalizer.normalize("1991-09-15T01:30", "Asia/Shanghai")
        self.assertEqual([9 * 3600, 8 * 3600], [row["utc_offset_seconds"] for row in result["candidates"]])

    def test_prc_1991_forward_transition_does_not_invent_time(self):
        for fold in (None, 0, 1):
            with self.subTest(fold=fold), self.assertRaises(ValueError):
                normalizer.normalize("1991-04-14T02:30", "Asia/Shanghai", fold=fold)

    def test_lord_howe_half_hour_fold_does_not_assume_one_hour(self):
        result = normalizer.normalize("2020-04-05T01:45", "Australia/Lord_Howe")
        first, second = [datetime.fromisoformat(row["utc_instant"]) for row in result["candidates"]]
        self.assertEqual(timedelta(minutes=30), second - first)
        self.assertEqual([1800, 0], [row["dst_adjustment_seconds"] for row in result["candidates"]])

    def test_samoa_skipped_entire_date_is_rejected(self):
        # IANA australasia: Pacific/Apia 2011-12-29 24:00 从 −11 标准偏移改到 +13。
        with self.assertRaises(ValueError):
            normalizer.normalize("2011-12-30T12:00", "Pacific/Apia")

    def test_overseas_conversion_preserves_date_rollover_and_instant(self):
        result = normalizer.normalize("2024-01-01T23:30", "America/New_York", adopt_utc8=True)
        self.assertEqual("2024-01-02T12:30:00+08:00", result["bazi_input"]["solar"])
        row = result["candidates"][0]
        self.assertEqual(datetime.fromisoformat(row["civil_local"]), datetime.fromisoformat(row["utc8_same_instant"]))

    def test_fractional_standard_offset_is_retained(self):
        result = normalizer.normalize("2024-01-01T12:00", "Asia/Kathmandu")
        row = result["candidates"][0]
        self.assertEqual(20700, row["utc_offset_seconds"])
        self.assertEqual("2024-01-01T14:15:00+08:00", row["utc8_same_instant"])


class InputAndAuditContracts(unittest.TestCase):
    def test_invalid_or_incomplete_clock_records_are_rejected(self):
        for value in (None, True, "2024-02-30T10:00", "2024-01-01", "2024-1-1T10:00", "2024-01-01T10:00+08:00", "2024-01-01T23:59:60", "1900-12-31T12:00", "2101-01-01T12:00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalizer.normalize(value, "Asia/Shanghai")

    def test_zone_abbreviations_unknown_paths_and_leap_second_data_rejected(self):
        for key in ("CST", "Asia/Beijing", "../Asia/Shanghai", "/Asia/Shanghai", "Asia//Shanghai", "right/UTC", "posix/Asia/Shanghai", None):
            with self.subTest(key=key), self.assertRaises(ValueError):
                normalizer.normalize("2024-01-01T10:00", key)

    def test_conflicting_offset_or_fold_is_not_silently_ignored(self):
        cases = ({"recorded_offset": "+08:00"}, {"fold": 0, "recorded_offset": "-08:00"}, {"fold": True}, {"fold": 2})
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                normalizer.normalize("2020-11-01T01:00", "America/Los_Angeles", **kwargs)
        with self.assertRaises(ValueError):
            normalizer.normalize("2024-01-01T10:00", "Asia/Shanghai", fold=1)

    def test_nonsensical_numeric_parameters_rejected(self):
        for field, values in (("uncertainty_minutes", (True, -1, float("nan"), 1441)), ("longitude", (True, -181, float("inf"), "116.4")), ("adopt_utc8", (1, "yes")), ("day_boundary", (None, "midnight"))):
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    normalizer.normalize("2024-01-01T10:00", "Asia/Shanghai", **{field: value})

    def test_offset_syntax_and_unknown_negative_zero_rejected(self):
        for value in ("CST", "-00:00", "+24:00", "+08:60", "+08:00:60", 8):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalizer.normalize("2024-01-01T10:00", "Asia/Shanghai", recorded_offset=value)

    def test_normalization_alone_does_not_choose_bazi_time_basis(self):
        result = normalizer.normalize("2024-01-01T10:00", "Asia/Tokyo")
        self.assertEqual("normalized_clock_only", result["status"])
        self.assertFalse(result["bazi_ready"])
        self.assertIsNone(result["bazi_input"])
        self.assertIsNone(result["candidates"][0]["bazi_input"])

    def test_pre1970_is_flagged_even_when_convertible(self):
        result = normalizer.normalize("1920-01-01T10:00", "Asia/Shanghai")
        self.assertTrue(any("1970" in note for note in result["warnings"]))

    def test_converted_date_outside_bazi_range_cannot_be_fed_to_bazi(self):
        result = normalizer.normalize("2100-12-31T23:30", "America/New_York", adopt_utc8=True)
        self.assertFalse(result["bazi_ready"])
        self.assertIsNone(result["bazi_input"])

    def test_exact_loaded_tzif_bytes_are_fingerprinted(self):
        result = normalizer.normalize("2024-01-01T10:00", "Asia/Shanghai")
        evidence = result["engine"]["timezone_data"]
        self.assertEqual(64, len(evidence["tzif_sha256"]))
        if evidence["provider"] == "system":
            self.assertEqual(hashlib.sha256(Path(evidence["path"]).read_bytes()).hexdigest(), evidence["tzif_sha256"])

    def test_birth_uncertainty_is_elapsed_time_around_each_candidate(self):
        result = normalizer.normalize("2020-11-01T01:30", "America/Los_Angeles", uncertainty_minutes=45)
        for row in result["candidates"]:
            window = row["uncertainty_window_utc8"]
            self.assertEqual(timedelta(minutes=90), datetime.fromisoformat(window["until"]) - datetime.fromisoformat(window["from"]))

    def test_missing_timezone_runtime_does_not_make_up_offset(self):
        with patch.object(normalizer.zoneinfo, "TZPATH", ()), patch.object(normalizer.resources, "files", side_effect=ModuleNotFoundError), self.assertRaises(ValueError):
            normalizer.normalize("2024-01-01T10:00", "Asia/Shanghai")


class SolarClockAndIntegration(unittest.TestCase):
    def test_longitude_shift_changes_mean_clock_by_four_minutes_per_degree(self):
        instant = datetime(2024, 1, 1, 0, tzinfo=timezone.utc)
        west = normalizer.solar_review(instant, -75, "00")
        east = normalizer.solar_review(instant, 120, "00")
        w = datetime.fromisoformat(west["mean_solar_clock"]["clock"])
        e = datetime.fromisoformat(east["mean_solar_clock"]["clock"])
        self.assertEqual(timedelta(hours=13), e - w)
        self.assertEqual("2023-12-31T19:00:00", west["mean_solar_clock"]["clock"])

    def test_equation_of_time_uses_same_instant_across_timezones(self):
        utc = datetime(2024, 2, 29, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(normalizer.equation_of_time(utc), normalizer.equation_of_time(utc.astimezone(normalizer.UTC8)))
        self.assertLess(normalizer.equation_of_time(utc), 0)

    def test_solar_sensitivity_changes_hour_without_creating_fake_bazi_input(self):
        result = normalizer.normalize("1991-07-01T12:00", "Asia/Shanghai", adopt_utc8=True, longitude=116.4)
        row = result["candidates"][0]
        self.assertEqual("午", row["clock_comparison"]["utc8"]["hour_branch"])
        solar = row["solar_clock_review"]
        self.assertEqual("巳", solar["mean_solar_clock"]["hour_branch"])
        self.assertFalse(solar["bazi_ready"])
        self.assertIsNone(datetime.fromisoformat(solar["mean_solar_clock"]["clock"]).tzinfo)
        self.assertEqual("1991-07-01T11:00:00+08:00", result["bazi_input"]["solar"])

    def test_selected_day_boundary_only_changes_clock_day_label(self):
        wall = datetime(2024, 1, 1, 23, 30)
        self.assertEqual("2024-01-01", normalizer.clock_label(wall, "00")["day_label_under_selected_boundary"])
        self.assertEqual("2024-01-02", normalizer.clock_label(wall, "23")["day_label_under_selected_boundary"])

    def test_overseas_lichun_keeps_the_same_absolute_term_boundary(self):
        # 库的 2024 立春是 UTC+8 16:27:07；外部资料只核到分钟。
        # 一秒前后是集成回归，不是秒级天文精度证明。
        before = normalizer.normalize("2024-02-04T17:27:06", "Asia/Tokyo", adopt_utc8=True)
        after = normalizer.normalize("2024-02-04T17:27:08", "Asia/Tokyo", adopt_utc8=True)
        earlier = bazi.calculate(**before["bazi_input"])
        later = bazi.calculate(**after["bazi_input"])
        self.assertEqual("癸卯", earlier["chart"]["pillars"]["year"])
        self.assertEqual("甲辰", later["chart"]["pillars"]["year"])
        self.assertNotEqual(earlier["chart"]["pillars"]["month"], later["chart"]["pillars"]["month"])

    def test_cli_gap_is_error_without_partial_output(self):
        process = subprocess.run([sys.executable, str(SCRIPTS / "time_normalize.py"), "--local", "1991-04-14T02:30", "--zone", "Asia/Shanghai", "--day-boundary", "00", "--adopt-utc8"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(2, process.returncode)
        self.assertEqual("", process.stdout)
        self.assertEqual("error", json.loads(process.stderr)["status"])

    def test_cli_ambiguous_input_outputs_candidates_without_selected_chart(self):
        process = subprocess.run([sys.executable, str(SCRIPTS / "time_normalize.py"), "--local", "1991-09-15T01:30", "--zone", "Asia/Shanghai", "--day-boundary", "00", "--adopt-utc8"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, process.returncode, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(2, len(result["candidates"]))
        self.assertFalse(result["bazi_ready"])


if __name__ == "__main__":
    unittest.main()
