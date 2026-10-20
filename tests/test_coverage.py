"""要件とWBSの網羅性および部分見積もりの扱い。"""

import unittest

from estimator.engine import calculate
from estimator.render import render_markdown
from tests.helpers import minimal_request, wbs_item


def _priced_request() -> dict:
    request = minimal_request()
    request["cost"] = {
        "rate": "80000",
        "rate_unit": "per_person_day",
        "currency": "JPY",
        "rate_basis": {"kind": "ASSUMPTION", "explanation": "テスト用に指定した単価"},
    }
    request["schedule"] = {"team_size": "2", "utilization": "0.6"}
    return request


class CoverageTest(unittest.TestCase):
    def test_all_functional_and_non_functional_requirements_are_covered(self) -> None:
        request = minimal_request()
        request["scope"]["non_functional"] = [
            {"id": "NF-001", "name": "性能", "description": "応答時間を確認する"}
        ]
        request["wbs"].append(
            wbs_item(
                id="WBS-002",
                requirement_ids=["NF-001"],
                name="性能確認",
                description="代表操作の応答時間を測る",
                phase="system_test",
            )
        )
        result = calculate(request)
        self.assertEqual(result["coverage"]["status"], "complete")
        self.assertTrue(result["coverage"]["is_total_estimate"])
        self.assertEqual(result["coverage"]["uncovered_requirement_ids"], [])
        self.assertEqual(result["coverage"]["estimated_requirement_ids"], ["F-001", "NF-001"])

    def test_requirement_missing_from_wbs_produces_only_partial_effort(self) -> None:
        request = _priced_request()
        request["scope"]["functions"].append(
            {"id": "F-002", "name": "検索", "description": "条件を指定して検索する"}
        )
        result = calculate(request)
        self.assertEqual(result["coverage"]["status"], "partial")
        self.assertFalse(result["coverage"]["is_total_estimate"])
        self.assertEqual(result["coverage"]["uncovered_requirement_ids"], ["F-002"])
        self.assertEqual(result["summary"]["estimate_scope"], "partial")
        self.assertEqual(result["cost"]["status"], "not_calculated")
        self.assertEqual(result["schedule"]["status"], "not_calculated")
        markdown = render_markdown(result)
        self.assertIn("部分見積もり工数", markdown)
        self.assertIn("F-002", markdown)


if __name__ == "__main__":
    unittest.main()
