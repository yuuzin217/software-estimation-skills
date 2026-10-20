"""JSON、Markdown、CSV出力の整合性とCSVの安全性。"""

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from estimator.engine import calculate
from estimator.render import render_csv
from tests.helpers import minimal_request


ROOT = Path(__file__).resolve().parents[1]


class OutputTest(unittest.TestCase):
    def test_csv_uses_same_display_values_as_json_and_markdown(self) -> None:
        request = minimal_request()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory / "request.json"
            source.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            markdown_path = directory / "estimate.md"
            json_path = directory / "estimate.json"
            csv_path = directory / "wbs.csv"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "estimator",
                    "calculate",
                    "--input",
                    str(source),
                    "--json-output",
                    str(json_path),
                    "--output",
                    str(markdown_path),
                    "--csv-output",
                    str(csv_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
            csv_text = csv_path.read_text(encoding="utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(csv_text, newline="")))
            line = result["wbs"]["lines"][0]
            self.assertIn(line["id"], markdown)
            self.assertIn(line["expected"], markdown)
            self.assertEqual(rows[0]["WBS ID"], line["id"])
            self.assertEqual(rows[0]["期待工数"], line["expected"])
            self.assertEqual(rows[0]["工数単位"], line["effort_unit"])
            self.assertEqual(rows[0]["算定状態"], "算定済み")

    def test_csv_escapes_formulas_after_leading_whitespace_and_controls(self) -> None:
        result = calculate(minimal_request())
        line = result["wbs"]["lines"][0]
        prefixes = ["=", "+", "-", "@", " =", "\t=", "\n+", "\r-", "\ufeff@"]
        copied = []
        for index, prefix in enumerate(prefixes, start=1):
            item = dict(line)
            item["id"] = f"WBS-{index:03d}"
            item["name"] = prefix + "SUM(A1:A2)"
            item["description"] = '日本語, "引用"\n次の行'
            copied.append(item)
        result["wbs"]["lines"] = copied
        rendered = render_csv(result)
        self.assertTrue(rendered.startswith("\ufeff"))
        rows = list(csv.DictReader(io.StringIO(rendered.removeprefix("\ufeff"), newline="")))
        self.assertEqual(len(rows), len(prefixes))
        for row in rows:
            self.assertTrue(row["作業名"].startswith("'"), row["作業名"])
            self.assertEqual(row["作業内容"], '日本語, "引用"\n次の行')

    def test_unestimated_rows_have_blank_effort_and_reason(self) -> None:
        request = minimal_request()
        request["wbs"] = [
            {
                "id": "WBS-001",
                "requirement_ids": ["F-001"],
                "name": "仕様確認",
                "description": "外部仕様の確認",
                "phase": "requirements",
                "estimable": False,
                "blocked_reason": "外部仕様が未提示",
            }
        ]
        result = calculate(request)
        rows = list(csv.DictReader(io.StringIO(render_csv(result).removeprefix("\ufeff"), newline="")))
        self.assertEqual(rows[0]["算定状態"], "未算定")
        self.assertEqual(rows[0]["期待工数"], "")
        self.assertEqual(rows[0]["未算定理由"], "外部仕様が未提示")

    def test_duplicate_output_paths_do_not_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory / "request.json"
            source.write_text(json.dumps(minimal_request()), encoding="utf-8")
            target = directory / "existing.txt"
            target.write_text("keep this", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "estimator",
                    "calculate",
                    "--input",
                    str(source),
                    "--output",
                    str(target),
                    "--json-output",
                    str(target),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep this")

    def test_staging_failure_keeps_all_existing_outputs_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory / "request.json"
            source.write_text(json.dumps(minimal_request()), encoding="utf-8")
            markdown_path = directory / "estimate.md"
            markdown_path.write_text("old markdown", encoding="utf-8")
            json_path = directory / "json-is-a-directory"
            json_path.mkdir()
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "estimator",
                    "calculate",
                    "--input",
                    str(source),
                    "--output",
                    str(markdown_path),
                    "--json-output",
                    str(json_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(markdown_path.read_text(encoding="utf-8"), "old markdown")


if __name__ == "__main__":
    unittest.main()
