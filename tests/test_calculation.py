"""PERT、検証、集計、費用、期間、丸め。"""

import json
import unittest
from decimal import Decimal

from estimator.engine import calculate
from estimator.errors import EstimationError
from estimator.numbers import round_effort
from estimator.render import render_markdown
from tests.helpers import minimal_request, wbs_item


class PertAndValidationTest(unittest.TestCase):
    def test_pert_expected_value(self) -> None:
        result = calculate(minimal_request())
        # (1 + 8 + 3) / 6 = 2
        self.assertEqual(result["summary"]["expected_exact"], "2")
        self.assertEqual(result["summary"]["expected"], "2.00")
        self.assertEqual(result["summary"]["planned"], "2.00")
        self.assertFalse(result["summary"]["planned_differs_from_expected"])

    def test_pert_rounds_half_up_after_sum(self) -> None:
        request = minimal_request()
        request["wbs"] = [
            wbs_item(id="WBS-001", optimistic="1", most_likely="2", pessimistic="5"),
            wbs_item(id="WBS-002", name="レビュー", phase="review", optimistic="1", most_likely="2", pessimistic="5"),
        ]
        result = calculate(request)
        self.assertEqual(result["wbs"]["lines"][0]["expected"], "2.33")
        summed = Decimal(result["wbs"]["lines"][0]["expected_exact"]) + Decimal(
            result["wbs"]["lines"][1]["expected_exact"]
        )
        self.assertEqual(Decimal(result["summary"]["expected_exact"]), summed)
        self.assertEqual(result["summary"]["expected"], "4.67")
        self.assertNotEqual(result["summary"]["expected"], "4.66")

    def test_half_up_policy(self) -> None:
        self.assertEqual(round_effort(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(round_effort(Decimal("1.004")), Decimal("1.00"))

    def test_rejects_negative_and_order(self) -> None:
        request = minimal_request()
        request["wbs"][0]["optimistic"] = "-1"
        with self.assertRaises(EstimationError):
            calculate(request)
        request = minimal_request()
        request["wbs"][0]["optimistic"] = "3"
        request["wbs"][0]["most_likely"] = "2"
        with self.assertRaises(EstimationError) as caught:
            calculate(request)
        self.assertTrue(any("楽観値" in message for message in caught.exception.errors))

    def test_rejects_non_finite_float_and_bool(self) -> None:
        request = minimal_request()
        request["wbs"][0]["most_likely"] = 1.5
        with self.assertRaises(EstimationError) as caught:
            calculate(request)
        self.assertTrue(any("浮動小数" in message for message in caught.exception.errors))
        request = minimal_request()
        request["wbs"][0]["most_likely"] = True
        with self.assertRaises(EstimationError):
            calculate(request)
        request = minimal_request()
        request["wbs"][0]["pessimistic"] = "NaN"
        with self.assertRaises(EstimationError):
            calculate(request)

    def test_duplicate_work_and_unknown_requirement(self) -> None:
        request = minimal_request()
        request["wbs"].append(wbs_item(id="WBS-002"))
        with self.assertRaises(EstimationError) as caught:
            calculate(request)
        self.assertTrue(any("重なって" in message for message in caught.exception.errors))
        request = minimal_request()
        request["wbs"][0]["requirement_ids"] = ["F-404"]
        with self.assertRaises(EstimationError):
            calculate(request)

    def test_unscoped_and_blocked_item(self) -> None:
        request = minimal_request()
        request["wbs"].append(
            {
                "id": "WBS-002",
                "requirement_ids": ["UNSCOPED"],
                "name": "外部連携",
                "description": "仕様未提示の連携",
                "phase": "external_integration",
                "estimable": False,
                "blocked_reason": "外部仕様が未提示",
            }
        )
        result = calculate(request)
        self.assertEqual(result["summary"]["expected"], "2.00")
        self.assertEqual(result["unestimated_items"][0]["id"], "WBS-002")
        self.assertEqual(result["coverage"]["status"], "partial")
        self.assertEqual(result["coverage"]["unestimated_wbs_ids"], ["WBS-002"])
        self.assertEqual(result["summary"]["estimate_scope"], "partial")

    def test_percent_derivation_and_overlap_warning(self) -> None:
        request = minimal_request()
        request["wbs"].append(
            {
                "id": "WBS-PM",
                "requirement_ids": ["UNSCOPED"],
                "name": "進行管理",
                "description": "指定割合の進行管理",
                "phase": "project_management",
                "estimable": True,
                "uncertainty": "high",
                "provisional": True,
                "basis": {"kind": "ASSUMPTION", "explanation": "利用者指定の10パーセントであり標準係数ではない"},
                "derivation": {"type": "percent_of", "base_ids": ["WBS-001"], "percent": "10"},
            }
        )
        result = calculate(request)
        derived = result["wbs"]["lines"][1]
        self.assertEqual(derived["expected_exact"], "0.2")
        self.assertEqual(result["summary"]["expected_exact"], "2.2")

    def test_derivation_cycle_is_rejected(self) -> None:
        request = minimal_request()
        request["wbs"] = [
            {
                "id": "WBS-001",
                "requirement_ids": ["F-001"],
                "name": "管理A",
                "description": "循環A",
                "phase": "project_management",
                "estimable": True,
                "uncertainty": "high",
                "provisional": True,
                "basis": {"kind": "ASSUMPTION", "explanation": "循環を検出するテスト項目"},
                "derivation": {"type": "percent_of", "base_ids": ["WBS-002"], "percent": "10"},
            },
            {
                "id": "WBS-002",
                "requirement_ids": ["F-001"],
                "name": "管理B",
                "description": "循環B",
                "phase": "documentation",
                "estimable": True,
                "uncertainty": "high",
                "provisional": True,
                "basis": {"kind": "ASSUMPTION", "explanation": "循環を検出するテスト項目"},
                "derivation": {"type": "percent_of", "base_ids": ["WBS-001"], "percent": "10"},
            },
        ]
        with self.assertRaises(EstimationError) as caught:
            calculate(request)
        self.assertTrue(any("循環" in message for message in caught.exception.errors))

    def test_effort_unit_must_match(self) -> None:
        request = minimal_request()
        request["wbs"][0]["effort_unit"] = "person_hour"
        with self.assertRaises(EstimationError):
            calculate(request)

    def test_cost_and_missing_rate(self) -> None:
        request = minimal_request()
        request["wbs"][0]["optimistic"] = "10"
        request["wbs"][0]["most_likely"] = "10"
        request["wbs"][0]["pessimistic"] = "10"
        without_rate = calculate(request)
        self.assertEqual(without_rate["cost"]["status"], "not_calculated")
        self.assertNotIn("total", without_rate["cost"])
        request["cost"] = {
            "rate": "50000",
            "rate_unit": "per_person_day",
            "currency": "JPY",
            "rate_basis": {"kind": "ASSUMPTION", "explanation": "利用者が指定したテスト単価"},
            "extra_costs": [
                {
                    "name": "検証環境",
                    "amount": "1000",
                    "basis_kind": "ASSUMPTION",
                    "explanation": "利用者が指定した環境費",
                }
            ],
        }
        result = calculate(request)
        self.assertEqual(result["cost"]["labor_exact"], "500000")
        self.assertEqual(result["cost"]["total"], "501000.00")

    def test_ai_rate_is_rejected(self) -> None:
        request = minimal_request()
        request["cost"] = {
            "rate": "50000",
            "rate_unit": "per_person_day",
            "currency": "JPY",
            "rate_basis": {"kind": "AI_ESTIMATE", "explanation": "相場を推測した単価"},
        }
        with self.assertRaises(EstimationError):
            calculate(request)

    def test_schedule_requires_both_inputs_and_is_not_confirmed(self) -> None:
        request = minimal_request()
        request["wbs"][0]["optimistic"] = "10"
        request["wbs"][0]["most_likely"] = "10"
        request["wbs"][0]["pessimistic"] = "10"
        missing = calculate(request)
        self.assertEqual(missing["schedule"]["status"], "not_calculated")
        request["schedule"] = {"team_size": "2", "utilization": "0.5"}
        result = calculate(request)
        self.assertEqual(result["schedule"]["status"], "provisional_lower_bound")
        self.assertEqual(result["schedule"]["elapsed_days_exact"], "10")
        self.assertFalse(result["schedule"]["confirmed"])
        request["schedule"] = {
            "team_size": "2",
            "utilization": "0.5",
            "calendar_factor": "1.4",
            "calendar_factor_basis": "週末を含む暦日への換算という仮定",
        }
        with_factor = calculate(request)
        self.assertEqual(with_factor["schedule"]["elapsed_days_exact"], "14")
        self.assertEqual(with_factor["schedule"]["status"], "provisional_with_calendar_factor")

    def test_schedule_rejects_partial_and_shrinking_factor(self) -> None:
        request = minimal_request()
        request["schedule"] = {"team_size": "2"}
        with self.assertRaises(EstimationError):
            calculate(request)
        request["schedule"] = {"team_size": "0", "utilization": "1"}
        with self.assertRaises(EstimationError):
            calculate(request)
        request["schedule"] = {"team_size": "1", "utilization": "1.2"}
        with self.assertRaises(EstimationError):
            calculate(request)
        request["schedule"] = {
            "team_size": "1",
            "utilization": "1",
            "calendar_factor": "0.8",
            "calendar_factor_basis": "期間を縮める不適切な係数",
        }
        with self.assertRaises(EstimationError):
            calculate(request)

    def test_contingency_is_separate_and_cannot_double_count(self) -> None:
        request = minimal_request()
        request["risks"] = [
            {
                "id": "R-001",
                "description": "仕様の追加",
                "trigger": "画面が増える",
                "impact_area": "実装",
                "estimation_impact": "悲観値に含む",
                "response": "三点の幅で見る",
                "already_in_three_point": True,
            }
        ]
        request["contingency"] = {
            "effort": "1",
            "effort_unit": "person_day",
            "reason": "三点に含めたリスクへ重ねる",
            "independent_of_three_point": True,
            "covered_risk_ids": ["R-001"],
        }
        with self.assertRaises(EstimationError):
            calculate(request)
        request["risks"][0]["already_in_three_point"] = False
        request["risks"][0]["estimation_impact"] = "三点に含めない環境待ち"
        request["contingency"]["reason"] = "検証環境の払い出し待ちだけを予備にする"
        result = calculate(request)
        self.assertEqual(result["summary"]["expected_exact"], "2")
        self.assertEqual(result["summary"]["planned_exact"], "3")
        self.assertTrue(result["summary"]["planned_differs_from_expected"])

    def test_person_hour_schedule_requires_explicit_hours(self) -> None:
        request = minimal_request()
        request["meta"]["effort_unit"] = "person_hour"
        missing = calculate(request)
        missing_schedule = dict(request)
        missing_schedule["schedule"] = {"team_size": "1", "utilization": "1"}
        result = calculate(missing_schedule)
        self.assertEqual(result["schedule"]["status"], "not_calculated")
        request["meta"]["hours_per_person_day"] = "8"
        request["schedule"] = {"team_size": "1", "utilization": "1"}
        converted = calculate(request)
        self.assertEqual(converted["schedule"]["elapsed_days_exact"], "0.25")

    def test_result_is_json_serializable_and_reproducible(self) -> None:
        first = calculate(minimal_request())
        second = calculate(minimal_request())
        self.assertEqual(first, second)
        json.dumps(first, ensure_ascii=False)

    def test_all_blocked_items_still_render(self) -> None:
        request = minimal_request()
        request["wbs"] = [
            {
                "id": "WBS-001",
                "requirement_ids": ["F-001"],
                "name": "未確定機能",
                "description": "仕様がなく算定できない",
                "phase": "requirements",
                "estimable": False,
                "blocked_reason": "受入条件が未提示",
            }
        ]
        result = calculate(request)
        self.assertEqual(result["summary"]["status"], "not_calculated")
        self.assertEqual(result["coverage"]["status"], "partial")
        self.assertEqual(result["coverage"]["unestimated_requirement_ids"], ["F-001"])
        markdown = render_markdown(result)
        self.assertIn("## 工数サマリー", markdown)
        self.assertIn("未算定", markdown)

    def test_ai_estimate_must_stay_provisional(self) -> None:
        request = minimal_request()
        request["wbs"][0]["provisional"] = False
        with self.assertRaises(EstimationError):
            calculate(request)


if __name__ == "__main__":
    unittest.main()
