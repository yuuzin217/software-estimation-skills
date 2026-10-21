"""フォルダ調査後の構造化入力と見積結果の結合試験。

自然言語からの要件抽出はagent側の責務であり、本テストはそのE2E実行を代替しない。
"""

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from estimator.engine import calculate
from estimator.errors import EstimationError
from tests.helpers import comparison_profile, history_record, minimal_request


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/folder-demo-request.json"
DOCS = ROOT / "examples/folder-input-demo"


def _priced_request() -> dict:
    req = minimal_request()
    req["cost"] = {
        "rate": "80000",
        "rate_unit": "per_person_day",
        "currency": "JPY",
        "rate_basis": {"kind": "ASSUMPTION", "explanation": "テスト用に指定された単価"},
    }
    req["schedule"] = {"team_size": "2", "utilization": "0.6"}
    return req


class SourceReviewTest(unittest.TestCase):
    def test_incomplete_source_review_prevents_total_cost_schedule(self) -> None:
        req = _priced_request()
        req["source_review"] = {
            "status": "incomplete",
            "blockers": ["screens.pdf が未読で、要件の全体像を確認できない"],
        }
        result = calculate(req)
        self.assertEqual(result["wbs"]["status"], "calculated")
        self.assertEqual(result["coverage"]["wbs_status"], "complete")
        self.assertEqual(result["coverage"]["status"], "partial")
        self.assertFalse(result["coverage"]["is_total_estimate"])
        self.assertEqual(result["summary"]["estimate_scope"], "partial")
        self.assertEqual(result["cost"]["status"], "not_calculated")
        self.assertEqual(result["schedule"]["status"], "not_calculated")
        self.assertIn("screens.pdf", result["warnings"][1])

    def test_source_review_blocks_historical_whole_project_claim(self) -> None:
        req = _priced_request()
        req["comparison_profile"] = comparison_profile()
        req["target_size"] = {"kind": "feature_count", "value": "4"}
        req["history"] = {
            "allow_fictional": True,
            "records": [history_record(project_id=f"P-{i}", actual_effort=str(12+i)) for i in range(3)],
        }
        req["source_review"] = {
            "status": "incomplete",
            "blockers": ["UIの重要資料が未確認"],
        }
        result = calculate(req)
        self.assertEqual(result["method"]["primary"], "historical")
        self.assertEqual(result["historical_estimate"]["status"], "calculated")
        self.assertEqual(result["coverage"]["status"], "partial")
        self.assertFalse(result["coverage"]["is_total_estimate"])
        self.assertEqual(result["summary"]["estimate_scope"], "partial")
        self.assertEqual(result["cost"]["status"], "not_calculated")
        self.assertEqual(result["schedule"]["status"], "not_calculated")

    def test_complete_source_review_keeps_existing_calculation(self) -> None:
        req = _priced_request()
        req["source_review"] = {"status": "complete", "blockers": []}
        result = calculate(req)
        self.assertEqual(result["coverage"]["status"], "complete")
        self.assertEqual(result["source_review"]["status"], "complete")
        self.assertEqual(result["cost"]["status"], "calculated")
        self.assertIn(result["schedule"]["status"], {"calculated", "provisional"})

    def test_invalid_review_declaration_is_rejected(self) -> None:
        for review in (
            {"status": "incomplete", "blockers": []},
            {"status": "complete", "blockers": ["未読資料がある"]},
            {"status": "complete", "blockers": [""]},
            {"status": "unknown", "blockers": []},
        ):
            with self.subTest(review=review):
                req = minimal_request()
                req["source_review"] = review
                with self.assertRaises(EstimationError):
                    calculate(req)

    def test_cli_rejects_missing_source_review_in_folder_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            path = d / "request.json"
            path.write_text(json.dumps(minimal_request(), ensure_ascii=False), encoding="utf-8")
            target = d / "estimate.json"
            proc = subprocess.run(
                [sys.executable, "-m", "estimator", "calculate",
                 "--input", str(path), "--require-source-review", "--json-output", str(target)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn("source_review", proc.stderr)
            self.assertFalse(target.exists())
            # 既存の直接JSON見積もりのCLI互換性は維持する。
            proc = subprocess.run(
                [sys.executable, "-m", "estimator", "calculate",
                 "--input", str(path), "--json-output", str(target)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(target.is_file())

    def test_demo_post_extraction_pipeline_produces_all_five_artifacts(self) -> None:
        """既知のエージェント作成JSON fixtureから、CLIと5成果物までを検証する。"""
        doc_files = sorted(DOCS.glob("*.md"))
        originals = {p: p.read_bytes() for p in doc_files}
        docs = "\n".join(p.read_text(encoding="utf-8") for p in doc_files)
        structured = json.loads(FIXTURE.read_text(encoding="utf-8"))
        ids = {x["id"] for key in ("functions", "non_functional") for x in structured["scope"][key]}
        for req_id in ids:
            self.assertIn(req_id, docs)
        mapped = {req_id for line in structured["wbs"] for req_id in line["requirement_ids"]}
        self.assertEqual(ids, mapped)
        self.assertEqual(structured["source_review"]["status"], "incomplete")

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            req_path = d / "request.json"
            req_path.write_text(json.dumps(structured, ensure_ascii=False), encoding="utf-8")
            sources = d / "sources.md"
            sources.write_text(
                "# Sources (テスト用の台帳)\n\n"
                + "\n".join(f"- 確認済み: {p.relative_to(ROOT)}" for p in doc_files)
                + "\n- 未確定: 認証基盤と受入条件\n",
                encoding="utf-8",
            )
            paths = [d / name for name in ("request.json", "sources.md", "estimate.json", "estimate.md", "wbs.csv")]
            result = subprocess.run(
                [sys.executable, "-m", "estimator", "calculate",
                 "--input", str(req_path), "--require-source-review",
                 "--json-output", str(d / "estimate.json"),
                 "--output", str(d / "estimate.md"), "--csv-output", str(d / "wbs.csv")],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(all(p.is_file() and p.stat().st_size > 0 for p in paths))
            output = json.loads((d / "estimate.json").read_text(encoding="utf-8"))
            self.assertEqual(output["coverage"]["status"], "partial")
            self.assertEqual(output["cost"]["status"], "not_calculated")
            self.assertEqual(output["schedule"]["status"], "not_calculated")
            markdown = (d / "estimate.md").read_text(encoding="utf-8")
            self.assertIn("認証方式と受入条件", markdown)
            rows = list(csv.DictReader(io.StringIO(
                (d / "wbs.csv").read_text(encoding="utf-8-sig"), newline=""
            )))
            self.assertEqual(len(rows), len(structured["wbs"]))
            self.assertEqual({row["WBS ID"] for row in rows}, {w["id"] for w in output["wbs"]["lines"]})
            self.assertEqual(originals, {p: p.read_bytes() for p in doc_files})


if __name__ == "__main__":
    unittest.main()
