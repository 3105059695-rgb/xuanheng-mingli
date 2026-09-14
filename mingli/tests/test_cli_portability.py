"""Exercise CLI output and timezone fallback without a UTF-8 host locale."""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def run_cli(script, *args, **extra_env):
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "ascii", **extra_env}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, encoding="utf-8", env=env,
    )


class CliPortabilityTests(unittest.TestCase):
    def test_hexagram_json_preserves_unicode_with_ascii_host(self):
        commands = (
            ("divination.py", "lines", "7", "7", "7", "7", "7", "7"),
            ("liuyao.py", "7", "7", "7", "7", "7", "7", "--day-ganzhi", "甲子", "--month-branch", "寅"),
        )
        for command in commands:
            with self.subTest(script=command[0]):
                result = run_cli(*command)
                self.assertEqual(0, result.returncode, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual("乾", data["original"]["name"])
                self.assertEqual("䷀", data["original"]["symbol"])

    def test_timezone_falls_back_to_installed_package(self):
        result = run_cli(
            "time_normalize.py", "--local", "1991-07-01T12:00",
            "--zone", "Asia/Shanghai", "--day-boundary", "00", "--adopt-utc8",
            PYTHONTZPATH="",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual("tzdata-package", data["engine"]["timezone_data"]["provider"])
        self.assertEqual("1991-07-01T11:00:00+08:00", data["bazi_input"]["solar"])

    def test_invalid_input_returns_readable_json_error(self):
        result = run_cli(
            "bazi.py", "--solar", "2024-02-30T12:00:00+08:00",
            "--time-basis", "utc8-standard", "--day-boundary", "00",
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        data = json.loads(result.stderr)
        self.assertEqual("error", data["status"])
        self.assertIn("公历", data["error"])


if __name__ == "__main__":
    unittest.main()
