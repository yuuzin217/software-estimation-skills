"""サンプル案件の方式選択と出力項目。"""

import json
import unittest
from decimal import Decimal
from pathlib import Path

from estimator.engine import calculate
from estimator.render import render_markdown

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
HEADINGS = ["## 基本情報", "## スコープ", "## 網羅性", "## WBS", "## 工数サマリー", "## 費用", "## 開発期間", "## リスク", "## 根拠", "## 補足"]


def load_case(name: str) -> dict:
    path = EXAMPLES / name / "request.json"
    return calculate(json.loads(path.read_text(encoding="utf-8")), base_dir=path.parent)


class ScenarioTest(unittest.TestCase):
    def test_case_a_new_web_without_history(self) -> None:
        result = load_case("case-a-new-web")
        self.assertEqual(result["method"]["primary"], "cold-start")
        self.assertEqual(result["benchmark"]["status"], "not_applied")
        self.assertEqual(result["cost"]["status"], "calculated")
        self.assertEqual(result["schedule"]["status"], "provisional_lower_bound")
        self.assertFalse(result["schedule"]["confirmed"])
        phases = {line["phase"] for line in result["wbs"]["lines"]}
        self.assertTrue({"ui_implementation", "api_implementation", "db", "auth", "project_management"} <= phases)
        self.assertEqual(result["summary"]["primary_basis"], "AI_ESTIMATE")
        self.assertIn("WBS-004", [line["id"] for line in result["wbs"]["lines"]])
        linked = next(line for line in result["wbs"]["lines"] if line["id"] == "WBS-006")
        self.assertIn("F-001", linked["requirement_ids"])

    def test_case_b_similar_history_is_not_added_to_wbs(self) -> None:
        result = load_case("case-b-similar-history")
        self.assertEqual(result["method"]["primary"], "historical")
        self.assertEqual(result["summary"]["expected"], "38.27")
        self.assertNotEqual(result["summary"]["planned_exact"], result["wbs"]["expected_exact"])
        self.assertTrue(result["wbs"]["cross_check_only"])
        self.assertTrue(result["historical_estimate"]["provisional"])
        self.assertIn("架空", render_markdown(result))

    def test_case_c_ambiguous_keeps_a_range(self) -> None:
        result = load_case("case-c-ambiguous")
        self.assertEqual(result["method"]["primary"], "cold-start")
        self.assertGreaterEqual(len(result["scope"]["unknowns"]), 2)
        self.assertEqual(result["unestimated_items"][0]["id"], "WBS-002")
        self.assertEqual(result["coverage"]["status"], "partial")
        self.assertFalse(result["coverage"]["is_total_estimate"])
        self.assertEqual(result["summary"]["estimate_scope"], "partial")
        self.assertEqual(result["cost"]["status"], "not_calculated")
        self.assertEqual(result["schedule"]["status"], "not_calculated")
        line = result["wbs"]["lines"][0]
        self.assertGreaterEqual(Decimal(line["pessimistic_exact"]) / Decimal(line["optimistic_exact"]), Decimal(5))
        self.assertTrue(line["provisional"])

    def test_case_d_dissimilar_history_is_not_scaled(self) -> None:
        result = load_case("case-d-dissimilar-history")
        self.assertEqual(result["method"]["primary"], "cold-start")
        self.assertEqual(result["historical_estimate"]["status"], "not_calculated")
        record = result["history_evaluation"]["records"][0]
        self.assertLess(Decimal(record["similarity"]), Decimal("0.60"))
        self.assertFalse(record["usable_for_scaling"])
        self.assertTrue(record["exclusion_reasons"])
        self.assertEqual(result["summary"]["primary_basis"], "AI_ESTIMATE")

    def test_case_e_omits_cost_and_duration(self) -> None:
        result = load_case("case-e-missing-rate")
        self.assertEqual(result["summary"]["status"], "calculated")
        self.assertEqual(result["cost"]["status"], "not_calculated")
        self.assertNotIn("total", result["cost"])
        self.assertEqual(result["schedule"]["status"], "not_calculated")
        self.assertNotIn("elapsed_days", result["schedule"])

    def test_case_f_non_functional_and_separate_reserve(self) -> None:
        result = load_case("case-f-non-functional")
        security = next(line for line in result["wbs"]["lines"] if line["phase"] == "security")
        self.assertIn("NF-002", security["requirement_ids"])
        self.assertEqual(result["summary"]["planned_differs_from_expected"], True)
        self.assertEqual(
            Decimal(result["summary"]["planned_exact"]),
            Decimal(result["summary"]["expected_exact"]) + Decimal(result["contingency"]["effort_exact"]),
        )
        self.assertEqual(result["contingency"]["covered_risk_ids"], ["R-002"])
        self.assertTrue(result["risks"][0]["already_in_three_point"])

    def test_case_g_enhancement_includes_impact_and_regression(self) -> None:
        result = load_case("case-g-enhancement")
        phases = {line["phase"] for line in result["wbs"]["lines"]}
        self.assertIn("impact_analysis", phases)
        self.assertIn("regression_test", phases)
        self.assertNotIn("infrastructure", phases)
        self.assertEqual(result["benchmark"]["status"], "not_applied")
        self.assertTrue(any("再設計" in item for item in result["scope"]["out_of_scope"]))

    def test_rendered_sections_and_committed_outputs(self) -> None:
        for request_path in sorted(EXAMPLES.glob("case-*/request.json")):
            result = calculate(json.loads(request_path.read_text(encoding="utf-8")), base_dir=request_path.parent)
            markdown = render_markdown(result)
            for heading in HEADINGS:
                self.assertIn(heading, markdown, request_path.parent.name)
            committed_json = request_path.parent / "estimate.json"
            committed_md = request_path.parent / "estimate.md"
            self.assertTrue(committed_json.is_file(), f"{committed_json} がありません")
            self.assertEqual(json.loads(committed_json.read_text(encoding="utf-8")), result)
            self.assertEqual(committed_md.read_text(encoding="utf-8"), markdown)


if __name__ == "__main__":
    unittest.main()
