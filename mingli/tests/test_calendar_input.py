"""日期输入的外部抽查、内部往返一致性与拒绝条件。"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "calendar_input.py"
spec = importlib.util.spec_from_file_location("calendar_input", SCRIPT)
calendar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calendar)


def solar(value, **kwargs):
    return calendar.convert_solar(value, time_basis="utc8-standard", **kwargs)


def lunar(year, month, day, leap, **kwargs):
    return calendar.convert_lunar(year, month, day, leap, time_basis="utc8-standard", **kwargs)


class HkoExternalSamples(unittest.TestCase):
    # 独立期望来自香港天文台原表（2026-09-14 核查）：
    # https://www.hko.gov.hk/tc/gts/time/calendar/text/files/T2023c.txt
    # https://www.hko.gov.hk/tc/gts/time/calendar/text/files/T2024c.txt
    # https://www.hko.gov.hk/tc/gts/time/calendar/text/files/T2025c.txt
    def test_2023_regular_and_leap_second_month_are_different(self):
        regular = lunar(2023, 2, 1, False)
        leap = lunar(2023, 2, 1, True)
        self.assertEqual("2023-02-20", regular["solar_date"])
        self.assertEqual("2023-03-22", leap["solar_date"])
        self.assertEqual((30, 29), (regular["lunar_date"]["month_days"], leap["lunar_date"]["month_days"]))
        self.assertEqual("2023-03-21", lunar(2023, 2, 30, False)["solar_date"])
        self.assertEqual("2023-04-19", lunar(2023, 2, 29, True)["solar_date"])
        with self.assertRaises(ValueError):
            lunar(2023, 2, 30, True)

    def test_2024_spring_festival_both_directions(self):
        converted = solar("2024-02-10")["lunar_date"]
        self.assertEqual((2024, 1, 1, False), tuple(converted[key] for key in ("year", "month", "day", "leap_month")))
        self.assertEqual("2024-02-10", lunar(2024, 1, 1, False)["solar_date"])
        self.assertEqual("2024-02-09", lunar(2023, 12, 30, False)["solar_date"])

    def test_2024_gregorian_leap_day_is_accepted(self):
        converted = solar("2024-02-29")["lunar_date"]
        self.assertEqual((2024, 1, 20, False), tuple(converted[key] for key in ("year", "month", "day", "leap_month")))

    def test_2025_new_year_boundary_after_29_day_last_month(self):
        before = lunar(2024, 12, 29, False)
        after = lunar(2025, 1, 1, False)
        self.assertEqual("2025-01-28", before["solar_date"])
        self.assertEqual("2025-01-29", after["solar_date"])
        self.assertEqual(29, before["lunar_date"]["month_days"])
        self.assertEqual((2024, 12, 29), tuple(solar("2025-01-28")["lunar_date"][key] for key in ("year", "month", "day")))
        with self.assertRaises(ValueError):
            lunar(2024, 12, 30, False)


class InputContractChecks(unittest.TestCase):
    def test_no_time_or_bazi_in_date_only_result(self):
        result = solar("2024-02-10")
        self.assertTrue(result["date_only"])
        self.assertFalse(result["bazi_ready"])
        self.assertIsNone(result["recorded_hour_branch"])
        self.assertEqual("not_performed_for_this_input", result["verification"]["independent_check"])
        text = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("T00:00", text)
        self.assertNotIn('"pillars"', text)
        self.assertNotIn('"chart"', text)

    def test_year_label_uses_lunar_new_year_and_is_not_lichun_year(self):
        # 2024-02-09 已过立春而未过农历新年；年标签仍为癸卯。
        before = solar("2024-02-09")["lunar_year_label"]
        after = solar("2024-02-10")["lunar_year_label"]
        self.assertEqual(("癸卯", "卯", 4), tuple(before[key] for key in ("ganzhi", "branch", "branch_number")))
        self.assertEqual(("甲辰", "辰", 5), tuple(after[key] for key in ("ganzhi", "branch", "branch_number")))

    def test_recording_hour_branch_does_not_create_exact_birth_time(self):
        result = lunar(2023, 2, 1, True, hour_branch="子")
        record = result["recorded_hour_branch"]
        self.assertEqual(("子", 1, "user_supplied"), (record["branch"], record["branch_number"], record["source"]))
        self.assertFalse(result["bazi_ready"])
        self.assertNotIn("T00:00", json.dumps(result, ensure_ascii=False))

    def test_given_solar_record_must_match_lunar_date(self):
        result = lunar(2023, 2, 1, True, expected_solar="2023-03-22")
        self.assertTrue(result["verification"]["expected_solar_match"])
        with self.assertRaises(ValueError):
            lunar(2023, 2, 1, True, expected_solar="2023-02-20")

    def test_supported_range_is_the_solar_range(self):
        first = solar("1901-01-01")["lunar_date"]
        self.assertEqual(1900, first["year"])
        self.assertEqual("1901-01-01", lunar(first["year"], first["month"], first["day"], first["leap_month"])["solar_date"])
        last = solar("2100-12-31")["lunar_date"]
        self.assertEqual("2100-12-31", lunar(last["year"], last["month"], last["day"], last["leap_month"])["solar_date"])
        with self.assertRaises(ValueError):
            lunar(1900, 1, 1, False)
        with self.assertRaises(ValueError):
            lunar(2100, 12, 2, False)


class RejectionChecks(unittest.TestCase):
    def test_missing_or_ambiguous_leap_is_never_assumed_regular(self):
        for leap in (None, 0, 1, "no", "false", "未知", [], {}):
            with self.subTest(leap=leap), self.assertRaises(ValueError):
                lunar(2023, 2, 1, leap)

    def test_nonexistent_leap_month_is_rejected(self):
        for year, month in ((2024, 2), (2023, 3), (2025, 2)):
            with self.subTest(year=year, month=month), self.assertRaises(ValueError):
                lunar(year, month, 1, True)

    def test_month_and_day_bounds_and_boolean_integers(self):
        cases = (
            (True, 2, 1, False), (2023, True, 1, False), (2023, 2, True, False),
            (2023.0, 2, 1, False), (2023, 2.0, 1, False), (2023, 2, 1.0, False),
            (2023, -2, 1, True), (2023, 0, 1, False), (2023, 13, 1, False),
            (2023, 2, 0, False), (2023, 2, 31, False), (1899, 12, 1, False), (2101, 1, 1, False),
        )
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                lunar(*args)

    def test_solar_dates_must_be_real_complete_dates_only(self):
        values = ("2023-02-29", "2024-04-31", "2024-2-10", "2024-02", "2024-02-10T00:00:00+08:00", "1900-12-31", "2101-01-01", "二月初一", None, True)
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                solar(value)

    def test_unsupported_basis_and_ambiguous_hour_branch_stop(self):
        for basis in (None, "Asia/Shanghai", "utc-5", "true-solar"):
            with self.subTest(basis=basis), self.assertRaises(ValueError):
                calendar.convert_solar("2024-02-10", time_basis=basis)
        for branch in ("", "夜里", "子或丑", 1, True):
            with self.subTest(branch=branch), self.assertRaises(ValueError):
                solar("2024-02-10", hour_branch=branch)

    def test_dependency_missing_or_wrong_version_stops_both_directions(self):
        for operation in (lambda: solar("2024-02-10"), lambda: lunar(2024, 1, 1, False)):
            with patch.object(calendar.metadata, "version", return_value="1.4.7"), self.assertRaises(RuntimeError):
                operation()
            with patch.object(calendar.metadata, "version", side_effect=calendar.metadata.PackageNotFoundError), self.assertRaises(RuntimeError):
                operation()

    def test_round_trip_disagreement_stops_instead_of_publishing_date(self):
        from lunar_python import Lunar, Solar
        wrong_lunar = Lunar.fromYmd(2024, 1, 2)
        wrong_solar = Solar.fromYmd(2024, 2, 11)
        with patch.object(Lunar, "fromYmd", return_value=wrong_lunar), self.assertRaises(RuntimeError):
            solar("2024-02-10")
        with patch.object(Solar, "fromYmd", return_value=wrong_solar), self.assertRaises(RuntimeError):
            lunar(2024, 1, 1, False)

    def test_cli_missing_leap_and_invalid_date_emit_no_partial_output(self):
        examples = (
            ["lunar", "--year", "2023", "--month", "2", "--day", "1"],
            ["lunar", "--year", "2024", "--month", "12", "--day", "30", "--leap", "no"],
            ["solar", "--date", "2024-02-30"],
        )
        for args in examples:
            with self.subTest(args=args):
                process = subprocess.run([sys.executable, str(SCRIPT), *args, "--time-basis", "utc8-standard"], capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(2, process.returncode)
                self.assertEqual("", process.stdout)
                self.assertTrue(process.stderr)

    def test_cli_valid_lunar_date_outputs_only_date_scope(self):
        process = subprocess.run([sys.executable, str(SCRIPT), "lunar", "--year", "2023", "--month", "2", "--day", "1", "--leap", "yes", "--time-basis", "utc8-standard"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, process.returncode, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual("2023-03-22", result["solar_date"])
        self.assertFalse(result["bazi_ready"])


if __name__ == "__main__":
    unittest.main()
