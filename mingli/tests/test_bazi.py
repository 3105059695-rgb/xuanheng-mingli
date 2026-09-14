"""外部历法抽查、上游样例回归与输入边界分开验证。"""

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bazi.py"
spec = importlib.util.spec_from_file_location("bazi", SCRIPT)
bazi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bazi)


def calc(value, **kwargs):
    options = {"time_basis": "utc8-standard", "day_boundary": "00", "uncertainty_minutes": 0}
    options.update(kwargs)
    return bazi.calculate(value, **options)


class ExternalCalendarChecks(unittest.TestCase):
    def test_hko_new_year_2024(self):
        # HKO T2024e.txt: 2024/2/10 是正月初一。12:00 为测试时刻。
        result = calc("2024-02-10T12:00:00+08:00")
        date = result["lunar_date"]
        self.assertEqual((2024, 1, 1, False), (date["year"], date["month"], date["day"], date["leap_month"]))

    def test_hko_leap_month_2023(self):
        # HKO T2023c.txt: 2023年3月22日是闰二月初一。
        result = calc("2023-03-22T12:00:00+08:00")
        date = result["lunar_date"]
        self.assertEqual((2023, 2, 1, True), (date["year"], date["month"], date["day"], date["leap_month"]))

    def test_hko_lichun_2024_minute_precision(self):
        # HKO 2024 年历二月：2月4日16:27。外部仅核到分钟，绝非秒级真值。
        result = calc("2024-02-04T16:20:00+08:00")
        term = result["adjacent_solar_terms"][1]
        self.assertEqual("立春", term["name"])
        self.assertEqual("2024-02-04T16:27", term["time"][:16])


class UpstreamRegressionChecks(unittest.TestCase):
    def test_upstream_golden_examples(self):
        # 6tail/lunar-python/test/EightCharTest.py: test_gan_zhi、test7、test10。
        # 这是上游回归样例，不是独立命盘验证。
        examples = (
            ("2005-12-23T08:37:00+08:00", ["乙酉", "戊子", "辛巳", "壬辰"]),
            ("2022-08-28T01:50:00+08:00", ["壬寅", "戊申", "癸丑", "癸丑"]),
            ("1988-02-15T23:30:00+08:00", ["戊辰", "甲寅", "庚子", "戊子"]),
        )
        for date, pillars in examples:
            with self.subTest(date=date):
                self.assertEqual(pillars, list(calc(date)["chart"]["pillars"].values()))


class DocumentationRegressionChecks(unittest.TestCase):
    def test_documented_teaching_charts_and_all_relations(self):
        # bazi.md 两个教学盘：防止资料表与排盘脱节，不验证格局或预测。
        examples = (
            ("1983-09-23T22:00:00+08:00", ["癸亥", "辛酉", "甲寅", "乙亥"],
             ["正印", "正官", "日主", "劫财"],
             [[("壬", "偏印"), ("甲", "比肩")], [("辛", "正官")],
              [("甲", "比肩"), ("丙", "食神"), ("戊", "偏财")], [("壬", "偏印"), ("甲", "比肩")]]),
            ("1981-09-14T22:00:00+08:00", ["辛酉", "丁酉", "乙未", "丁亥"],
             ["七杀", "食神", "日主", "食神"],
             [[("辛", "七杀")], [("辛", "七杀")],
              [("己", "偏财"), ("丁", "食神"), ("乙", "比肩")], [("壬", "正印"), ("甲", "劫财")]]),
        )
        for date, pillars, relations, hidden in examples:
            with self.subTest(date=date):
                chart = calc(date, details=True)["chart"]
                self.assertEqual(pillars, list(chart["pillars"].values()))
                columns = list(chart["details"].values())
                self.assertEqual(relations, [column["stem_relation"] for column in columns])
                self.assertEqual(hidden, [
                    [(item["stem"], item["relation"]) for item in column["hidden_stems"]]
                    for column in columns
                ])


class BoundaryChecks(unittest.TestCase):
    def test_supported_range_endpoints_have_adjacent_terms(self):
        for value in ("1901-01-01T00:00:00+08:00", "2100-12-31T23:59:59+08:00"):
            with self.subTest(value=value):
                result = calc(value)
                self.assertEqual(2, len(result["adjacent_solar_terms"]))
                self.assertEqual(4, len(result["chart"]["pillars"]))

    def test_late_zi_keeps_both_schools_and_recomputes_relations(self):
        result = calc("1988-02-15T23:30:00+08:00", details=True)
        chosen, alternate = result["chart"], result["other_day_boundary"]
        self.assertEqual("庚子", chosen["pillars"]["day"])
        self.assertEqual("辛丑", alternate["pillars"]["day"])
        self.assertEqual("戊子", alternate["pillars"]["time"])
        self.assertEqual(["day"], alternate["different_pillars"])
        self.assertNotEqual(chosen["details"]["year"]["stem_relation"], alternate["details"]["year"]["stem_relation"])

    def test_explicit_23_boundary(self):
        before = calc("1988-02-15T22:59:59+08:00", day_boundary="23")
        after = calc("1988-02-15T23:00:00+08:00", day_boundary="23")
        self.assertNotEqual(before["chart"]["pillars"]["day"], after["chart"]["pillars"]["day"])
        self.assertTrue(any("day" in event["affects"] for event in after["boundary_review"]["events"]))

    def test_midnight_changes_day_but_not_late_zi_hour(self):
        before = calc("1988-02-15T23:59:59+08:00")
        after = calc("1988-02-16T00:00:00+08:00")
        self.assertNotEqual(before["chart"]["pillars"]["day"], after["chart"]["pillars"]["day"])
        self.assertEqual(before["chart"]["pillars"]["time"], after["chart"]["pillars"]["time"])

    def test_library_lichun_transition_is_not_claimed_external_second_truth(self):
        before = calc("2024-02-04T16:27:06+08:00")
        after = calc("2024-02-04T16:27:07+08:00")
        self.assertEqual(("癸卯", "乙丑"), (before["chart"]["pillars"]["year"], before["chart"]["pillars"]["month"]))
        self.assertEqual(("甲辰", "丙寅"), (after["chart"]["pillars"]["year"], after["chart"]["pillars"]["month"]))
        self.assertTrue(any(set(event["affects"]) == {"year", "month"} for event in after["boundary_review"]["events"]))

    def test_zhongqi_does_not_switch_month(self):
        before = calc("2024-02-19T12:13:11+08:00")
        after = calc("2024-02-19T12:13:12+08:00")
        self.assertEqual(before["chart"]["pillars"]["month"], after["chart"]["pillars"]["month"])
        events = [event for event in after["boundary_review"]["events"] if event["kind"] == "solar_term"]
        self.assertEqual([], events[0]["affects"])

    def test_uncertainty_window_detects_distant_hour_boundary(self):
        result = calc("2005-12-23T08:37:00+08:00", uncertainty_minutes=30)
        self.assertEqual(30, result["boundary_review"]["window_minutes"])
        self.assertTrue(any(event["name"] == "09:00" for event in result["boundary_review"]["events"]))

    def test_unknown_precision_is_not_certainty(self):
        result = calc("2005-12-23T08:37+08:00", uncertainty_minutes=None)
        self.assertIsNone(result["input"]["uncertainty_minutes"])
        self.assertEqual("computed_requires_time_review", result["status"])
        self.assertGreaterEqual(len(result["warnings"]), 2)


class YunChecks(unittest.TestCase):
    def test_upstream_yun_golden_is_algorithm_regression(self):
        # 6tail/lunar-python/test/YunTest.py test/test3/test4/test5/test6.
        # 公开上游样例，不是独立外部排运验证。
        examples = (
            ("1981-01-29T23:37:00+08:00", "female", 1, "1989-02-18"),
            ("2020-01-06T11:22:00+08:00", "male", 1, "2020-02-06"),
            ("2022-03-09T20:51:00+08:00", "male", 1, "2030-12-19"),
            ("2022-03-09T20:51:00+08:00", "male", 2, "2030-12-12"),
            ("2018-06-11T09:30:00+08:00", "female", 2, "2020-03-21"),
        )
        for date, gender, sect, expected in examples:
            with self.subTest(date=date, gender=gender, sect=sect):
                yun = calc(date, gender=gender, yun_sect=sect)["yun"]
                self.assertEqual(expected, yun["start_solar"][:10])
        yun = calc("2022-03-09T20:51:00+08:00", gender="male", yun_sect=2)["yun"]
        self.assertEqual((8, 9, 2), tuple(yun["start_offset"][key] for key in ("years", "months", "days")))

    def test_all_four_direction_combinations_and_jie_selection(self):
        for date, yinyang, male_forward in (
            ("2024-06-10T12:30:00+08:00", "阳", True),
            ("2023-06-10T12:30:00+08:00", "阴", False),
        ):
            for gender in ("male", "female"):
                with self.subTest(date=date, gender=gender):
                    yun = calc(date, gender=gender, yun_sect=2)["yun"]
                    forward = male_forward if gender == "male" else not male_forward
                    self.assertEqual(yinyang, yun["direction_basis"]["year_yinyang"])
                    self.assertEqual("forward" if forward else "reverse", yun["direction"])
                    self.assertEqual("节", yun["target_jie"]["kind"])
                    self.assertEqual(forward, yun["target_jie"]["seconds_from_birth"] > 0)

    def test_lichun_changes_direction_using_exact_year_not_civil_year(self):
        before = calc("2024-02-04T16:27:06+08:00", gender="male", yun_sect=2)["yun"]
        after = calc("2024-02-04T16:27:07+08:00", gender="male", yun_sect=2)["yun"]
        self.assertEqual(("癸", "reverse"), (before["direction_basis"]["year_stem"], before["direction"]))
        self.assertEqual(("甲", "forward"), (after["direction_basis"]["year_stem"], after["direction"]))

    def test_day_boundary_and_yun_sect_are_independent(self):
        a = calc("1988-02-15T23:30:00+08:00", gender="male", yun_sect=2, day_boundary="00")
        b = calc("1988-02-15T23:30:00+08:00", gender="male", yun_sect=2, day_boundary="23")
        self.assertNotEqual(a["chart"]["pillars"]["day"], b["chart"]["pillars"]["day"])
        self.assertEqual(a["yun"]["start_solar"], b["yun"]["start_solar"])
        self.assertEqual(a["yun"]["dayun"], b["yun"]["dayun"])

    def test_minutes_algorithm_ignores_seconds_in_conversion(self):
        a = calc("2022-03-09T20:51:00+08:00", gender="male", yun_sect=2)["yun"]
        b = calc("2022-03-09T20:51:59+08:00", gender="male", yun_sect=2)["yun"]
        self.assertEqual(a["start_offset"], b["start_offset"])
        # 公历加偏移仍保留原生秒数；这不是按秒折算了起运。
        self.assertEqual("59+08:00", b["start_solar"][-8:])

    def test_exact_jie_uses_strict_next_and_inclusive_previous(self):
        # 固定库惊蛰秒数仅是算法边界，未声称外部秒级验证。
        before = "2024-03-05T10:22:44+08:00"
        instant = "2024-03-05T10:22:45+08:00"
        for sect in (1, 2):
            with self.subTest(sect=sect):
                forward_before = calc(before, gender="male", yun_sect=sect)["yun"]
                forward_at = calc(instant, gender="male", yun_sect=sect)["yun"]
                reverse_before = calc(before, gender="female", yun_sect=sect)["yun"]
                reverse_at = calc(instant, gender="female", yun_sect=sect)["yun"]
                self.assertEqual("惊蛰", forward_before["target_jie"]["name"])
                self.assertEqual("清明", forward_at["target_jie"]["name"])
                self.assertEqual("立春", reverse_before["target_jie"]["name"])
                self.assertEqual("惊蛰", reverse_at["target_jie"]["name"])
                self.assertEqual(0, reverse_at["target_jie"]["seconds_from_birth"])
                self.assertEqual({"years": 0, "months": 0, "days": 0, "hours": 0}, reverse_at["start_offset"])
                self.assertEqual(instant, reverse_at["start_solar"])
                self.assertEqual(instant, reverse_at["pre_start_phase"]["until_exclusive"])

    def test_dayun_from_month_plus_or_minus_one_and_liunian_labels(self):
        forward = calc("2022-03-09T20:51:00+08:00", gender="male", yun_sect=2, dayun_count=2, liunian=True)["yun"]
        reverse = calc("2022-03-09T20:51:00+08:00", gender="female", yun_sect=2, dayun_count=2)["yun"]
        # 月柱癸卯；顺走甲辰、乙巳，逆走壬寅、辛丑。
        self.assertEqual(["甲辰", "乙巳"], [row["ganzhi"] for row in forward["dayun"]])
        self.assertEqual(["壬寅", "辛丑"], [row["ganzhi"] for row in reverse["dayun"]])
        self.assertIsNone(forward["pre_start_phase"]["ganzhi"])
        self.assertEqual([1, 2], [row["index"] for row in forward["dayun"]])
        self.assertEqual((2030, 2039, 9, 18), tuple(forward["dayun"][0][key] for key in ("start_year_label", "end_year_label", "start_nominal_age", "end_nominal_age")))
        years = forward["dayun"][0]["liunian"]
        self.assertEqual(10, len(years))
        self.assertEqual({"year_label": 2030, "nominal_age": 9, "ganzhi": "庚戌"}, years[0])
        self.assertNotIn("liunian", reverse["dayun"][0])

    def test_zero_year_start_does_not_make_empty_ganzhi_a_dayun(self):
        yun = calc("2020-01-06T11:22:00+08:00", gender="male", yun_sect=1)["yun"]
        self.assertEqual(0, yun["start_offset"]["years"])
        self.assertTrue(all(len(row["ganzhi"]) == 2 for row in yun["dayun"]))
        self.assertEqual(1, yun["dayun"][0]["start_nominal_age"])

    def test_default_chart_requires_no_gender_and_does_not_guess_yun(self):
        self.assertNotIn("yun", calc("2024-06-10T12:30:00+08:00"))

    def test_invalid_or_incomplete_yun_parameters_stop(self):
        invalid = (
            {"gender": "male"}, {"yun_sect": 2}, {"gender": "unknown", "yun_sect": 1},
            {"gender": "male", "yun_sect": True}, {"gender": "female", "yun_sect": 0},
            {"gender": "male", "yun_sect": 1, "dayun_count": 0},
            {"gender": "male", "yun_sect": 1, "dayun_count": 13},
            {"gender": "male", "yun_sect": 1, "dayun_count": 1.5},
            {"gender": "male", "yun_sect": 1, "liunian": 1},
            {"liunian": True}, {"dayun_count": 3},
        )
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(ValueError):
                calc("2024-06-10T12:30:00+08:00", **options)


class FailClosedChecks(unittest.TestCase):
    def test_missing_time_invalid_dates_foreign_zone_and_range(self):
        invalid = ["2000-01-01", "农历二月初一", "2024-02-30T08:00+08:00", "2024-02-10T24:00+08:00", "2024-02-10T08:00-05:00", "2024-02-10T08:00", "1900-12-31T08:00+08:00", "2101-01-01T08:00+08:00"]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                calc(value)

    def test_unsupported_basis_or_school(self):
        for options in ({"time_basis": "true-solar"}, {"day_boundary": "unknown"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                calc("2024-02-10T08:00+08:00", **options)

    def test_invalid_uncertainty(self):
        for value in (-1, 1441, float("nan"), float("inf"), True, "unknown"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calc("2024-02-10T08:00+08:00", uncertainty_minutes=value)

    def test_dependency_version_mismatch_stops(self):
        with patch.object(bazi.metadata, "version", return_value="0.0.0"), self.assertRaises(RuntimeError):
            calc("2024-02-10T08:00+08:00")

    def test_missing_dependency_stops(self):
        with patch.object(bazi.metadata, "version", side_effect=bazi.metadata.PackageNotFoundError), self.assertRaises(RuntimeError):
            calc("2024-02-10T08:00+08:00")

    def test_cli_failure_never_emits_chart(self):
        process = subprocess.run([sys.executable, str(SCRIPT), "--solar", "2024-02-10", "--time-basis", "utc8-standard", "--day-boundary", "00"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(2, process.returncode)
        self.assertEqual("", process.stdout)
        self.assertIn('"status": "error"', process.stderr)


if __name__ == "__main__":
    unittest.main()
