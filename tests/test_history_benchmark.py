"""実績の品質、類似性、ベンチマーク照合、方式選択。"""

import unittest
from decimal import Decimal

from estimator.engine import calculate
from estimator.errors import EstimationError
from tests.helpers import comparison_profile, history_record, minimal_request, wbs_item


def _similar(project_id: str, actual: str, size: str) -> dict:
    return history_record(project_id=project_id, actual_effort=actual, estimated_effort=actual, size={"kind": "feature_count", "value": size})


class HistoryAndBenchmarkTest(unittest.TestCase):
    def test_three_similar_records_become_primary_and_do_not_add_wbs(self) -> None:
        request = minimal_request()
        request["wbs"] = [wbs_item(optimistic="1", most_likely="1", pessimistic="1")]
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "8"}
        request["history"] = {
            "allow_fictional": True,
            "records": [
                _similar("P-001", "30", "6"),
                _similar("P-002", "48", "10"),
                _similar("P-003", "36", "8"),
            ],
        }
        result = calculate(request)
        self.assertEqual(result["method"]["primary"], "historical")
        self.assertEqual(result["method"]["auxiliary"], "cold-start")
        self.assertTrue(result["wbs"]["cross_check_only"])
        self.assertEqual(result["summary"]["primary_basis"], "HISTORICAL")
        expected = (Decimal(36) + Decimal(4) * Decimal("38.4") + Decimal(40)) / Decimal(6)
        self.assertEqual(result["summary"]["expected_exact"], format(expected, "f"))
        self.assertEqual(result["summary"]["expected"], "38.27")
        self.assertNotEqual(result["summary"]["planned_exact"], result["wbs"]["expected_exact"])
        self.assertTrue(result["historical_estimate"]["provisional"])
        self.assertTrue(result["history_evaluation"]["fictional_records_present"])

    def test_low_similarity_stays_on_cold_start(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "8"}
        request["history"] = {
            "allow_fictional": True,
            "records": [
                history_record(
                    project_id="EMB-001",
                    project_type="embedded",
                    project_scope="new",
                    technology_stack=["c"],
                    work_categories=["implementation", "test"],
                    actual_effort="100",
                    size={"kind": "feature_count", "value": "8"},
                )
            ],
        }
        result = calculate(request)
        self.assertEqual(result["method"]["primary"], "cold-start")
        self.assertEqual(result["summary"]["expected_exact"], "2")
        self.assertEqual(result["historical_estimate"]["status"], "not_calculated")
        self.assertFalse(result["history_evaluation"]["records"][0]["usable_for_scaling"])
        self.assertTrue(result["history_evaluation"]["records"][0]["type_cap_applied"])
        self.assertLess(Decimal(result["history_evaluation"]["records"][0]["similarity"]), Decimal("0.60"))

    def test_project_scope_mismatch_is_a_hard_gate(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "8"}
        request["history"] = {
            "allow_fictional": True,
            "records": [
                _similar(f"P-{index}", "30", str(size)) | {"project_scope": "enhancement"}
                for index, size in enumerate((6, 8, 10), start=1)
            ],
        }
        result = calculate(request)
        self.assertEqual(result["method"]["primary"], "cold-start")
        self.assertEqual(result["method"]["auxiliary"], "none")
        self.assertEqual(result["history_evaluation"]["similar_count"], 3)
        self.assertEqual(result["history_evaluation"]["usable_for_scaling_count"], 0)
        for record in result["history_evaluation"]["records"]:
            self.assertFalse(record["project_scope_match"])
            self.assertTrue(any("project_scope" in reason for reason in record["exclusion_reasons"]))

    def test_historical_scale_gate_compares_each_record_to_target(self) -> None:
        cases = [
            ("8", ("6", "8", "10")),
            ("12", ("6", "8", "10")),
            ("6", ("3", "6", "12")),
        ]
        for target, sizes in cases:
            with self.subTest(target=target, sizes=sizes):
                request = minimal_request()
                request["comparison_profile"] = comparison_profile()
                request["target_size"] = {"kind": "feature_count", "value": target}
                request["history"] = {
                    "allow_fictional": True,
                    "records": [
                        _similar(f"P-{index:03}", str(30 + index * 10), size)
                        for index, size in enumerate(sizes, start=1)
                    ],
                }
                result = calculate(request)
                self.assertEqual(result["method"]["primary"], "historical")
                self.assertEqual(result["history_evaluation"]["size_extrapolation"]["status"], "within_range")
                self.assertEqual(result["history_evaluation"]["usable_for_scaling_count"], 3)

    def test_mixed_size_outlier_is_excluded_and_insufficient_records_fall_back(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "20000"}
        request["history"] = {
            "allow_fictional": True,
            "records": [
                _similar("P-002", "20", "2"),
                _similar("P-009", "90", "9"),
                _similar("P-10000", "100000", "10000"),
            ],
        }
        result = calculate(request)
        extrapolation = result["history_evaluation"]["size_extrapolation"]
        self.assertEqual(result["method"]["primary"], "cold-start")
        self.assertEqual(extrapolation["status"], "filtered")
        self.assertEqual(extrapolation["accepted_record_ids"], ["P-10000"])
        self.assertEqual(extrapolation["excluded_record_ids"], ["P-002", "P-009"])
        self.assertEqual(result["history_evaluation"]["usable_for_scaling_count"], 1)
        for record in result["history_evaluation"]["records"][:2]:
            self.assertFalse(record["usable_for_scaling"])
            self.assertTrue(any("規模比" in reason for reason in record["exclusion_reasons"]))

    def test_distant_record_is_filtered_when_three_nearby_records_remain(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "8000"}
        request["history"] = {
            "allow_fictional": True,
            "records": [
                _similar("P-002", "20", "2"),
                _similar("P-8000", "80000", "8000"),
                _similar("P-9000", "90000", "9000"),
                _similar("P-10000", "100000", "10000"),
            ],
        }
        result = calculate(request)
        self.assertEqual(result["method"]["primary"], "historical")
        self.assertEqual(result["history_evaluation"]["usable_for_scaling_count"], 3)
        self.assertEqual(
            result["historical_estimate"]["used_record_ids"], ["P-8000", "P-9000", "P-10000"]
        )
        self.assertEqual(result["history_evaluation"]["size_extrapolation"]["excluded_record_ids"], ["P-002"])

    def test_extreme_scale_extrapolation_falls_back_to_cold_start(self) -> None:
        for target in ("8000", "1", "2.99", "20.01"):
            with self.subTest(target=target):
                request = minimal_request()
                request["comparison_profile"] = comparison_profile()
                request["target_size"] = {"kind": "feature_count", "value": target}
                request["history"] = {
                    "allow_fictional": True,
                    "records": [_similar("P-001", "30", "6"), _similar("P-002", "40", "8"), _similar("P-003", "50", "10")],
                }
                result = calculate(request)
                self.assertEqual(result["method"]["primary"], "cold-start")
                self.assertEqual(result["history_evaluation"]["size_extrapolation"]["status"], "rejected")
                self.assertEqual(result["history_evaluation"]["usable_for_scaling_count"], 0)
                self.assertEqual(result["historical_estimate"]["status"], "not_calculated")
                self.assertTrue(any("規模比" in reason for reason in result["history_evaluation"]["records"][0]["exclusion_reasons"]))

    def test_historical_primary_coverage_is_independent_of_cross_check_wbs(self) -> None:
        request = minimal_request()
        request["scope"]["non_functional"] = [
            {"id": "NF-001", "name": "可用性", "description": "夜間も利用できる"}
        ]
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "8"}
        request["history"] = {
            "allow_fictional": True,
            "records": [_similar("P-001", "30", "6"), _similar("P-002", "40", "8"), _similar("P-003", "50", "10")],
        }
        request["cost"] = {
            "rate": "80000",
            "rate_unit": "per_person_day",
            "currency": "JPY",
            "rate_basis": {"kind": "ASSUMPTION", "explanation": "テスト用に指定した単価"},
        }
        request["schedule"] = {"team_size": "2", "utilization": "0.6"}
        result = calculate(request)
        self.assertEqual(result["method"]["primary"], "historical")
        self.assertEqual(result["coverage"]["status"], "historical_project_estimate")
        self.assertTrue(result["coverage"]["is_total_estimate"])
        self.assertEqual(result["coverage"]["wbs_status"], "partial")
        self.assertEqual(result["coverage"]["uncovered_requirement_ids"], ["NF-001"])
        self.assertEqual(result["cost"]["status"], "calculated")
        self.assertNotEqual(result["schedule"]["status"], "not_calculated")

    def test_one_similar_record_is_auxiliary_only(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "8"}
        request["history"] = {"allow_fictional": True, "records": [_similar("P-001", "30", "6")]}
        result = calculate(request)
        self.assertEqual(result["method"]["primary"], "cold-start")
        self.assertEqual(result["method"]["auxiliary"], "historical")
        self.assertEqual(result["summary"]["expected_exact"], "2")
        self.assertEqual(result["historical_estimate"]["status"], "calculated")
        self.assertTrue(result["historical_estimate"]["single_point"])

    def test_fictional_records_are_ignored_unless_allowed(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "8"}
        request["history"] = {"allow_fictional": False, "records": [_similar(f"P-{i}", "30", "6") for i in range(3)]}
        result = calculate(request)
        self.assertEqual(result["method"]["primary"], "cold-start")
        self.assertEqual(result["history_evaluation"]["usable_for_scaling_count"], 0)

    def test_anomaly_is_excluded_by_default(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "4"}
        record = history_record(estimated_effort="10", actual_effort="80")
        request["history"] = {"allow_fictional": True, "records": [record]}
        result = calculate(request)
        self.assertTrue(result["history_evaluation"]["records"][0]["anomaly"])
        self.assertFalse(result["history_evaluation"]["records"][0]["usable_for_scaling"])

    def test_hour_conversion_requires_record_factor(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "2"}
        record = _similar("P-001", "16", "2")
        record["effort_unit"] = "person_hour"
        request["history"] = {"allow_fictional": True, "records": [record, _similar("P-002", "10", "2"), _similar("P-003", "12", "2")]}
        without = calculate(request)
        self.assertFalse(without["history_evaluation"]["records"][0]["usable_for_scaling"])
        record["hours_per_person_day"] = "8"
        with_factor = calculate(request)
        self.assertTrue(with_factor["history_evaluation"]["records"][0]["usable_for_scaling"])
        self.assertEqual(with_factor["history_evaluation"]["records"][0]["unit_rate"], "1")

    def test_duplicate_project_id_is_rejected(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["history"] = {"allow_fictional": True, "records": [_similar("P-001", "10", "2"), _similar("P-001", "12", "2")]}
        with self.assertRaises(EstimationError):
            calculate(request)

    def test_historical_override_without_evidence_is_rejected(self) -> None:
        request = minimal_request()
        request["method_override"] = "historical"
        with self.assertRaises(EstimationError):
            calculate(request)

    def test_historical_primary_rejects_wbs_contingency(self) -> None:
        request = minimal_request()
        request["comparison_profile"] = comparison_profile()
        request["target_size"] = {"kind": "feature_count", "value": "8"}
        request["history"] = {
            "allow_fictional": True,
            "records": [_similar("P-001", "30", "6"), _similar("P-002", "48", "10"), _similar("P-003", "36", "8")],
        }
        request["risks"] = [
            {
                "id": "R-009",
                "description": "環境待ち",
                "trigger": "環境が来ない",
                "impact_area": "期間",
                "estimation_impact": "予備が必要",
                "response": "別途確保",
                "already_in_three_point": False,
            }
        ]
        request["contingency"] = {
            "effort": "2",
            "reason": "実績方式に重ねないことを確認する",
            "independent_of_three_point": True,
            "covered_risk_ids": ["R-009"],
        }
        with self.assertRaises(EstimationError):
            calculate(request)

    def test_benchmark_cross_check_does_not_replace_plan(self) -> None:
        request = minimal_request()
        request["benchmark"] = {
            "catalog_id": "ipa-2022-sloc-productivity-new-under-40ksloc",
            "development_type": "new",
            "size_unit": "sloc",
            "target_size": "2950",
            "confirmed_phases": [
                "basic_design",
                "detailed_design",
                "implementation",
                "integration_test",
                "system_test_vendor",
            ],
            "acknowledge_population_limits": True,
            "population_note": "開発5工程のSLOC生産性との照合であり、WBSの置換には使わない。",
        }
        result = calculate(request)
        self.assertEqual(result["benchmark"]["status"], "cross_check_only")
        self.assertEqual(result["benchmark"]["most_likely_exact"], "1000")
        self.assertEqual(result["benchmark"]["applied_to_plan"], False)
        self.assertEqual(result["summary"]["expected_exact"], "2")
        optimistic = Decimal(2950) / Decimal("5.14")
        pessimistic = Decimal(2950) / Decimal("1.97")
        self.assertEqual(Decimal(result["benchmark"]["optimistic_exact"]), optimistic)
        self.assertEqual(Decimal(result["benchmark"]["pessimistic_exact"]), pessimistic)

    def test_benchmark_rejects_mismatched_population_and_profile_metrics(self) -> None:
        request = minimal_request()
        request["benchmark"] = {
            "catalog_id": "ipa-2022-sloc-productivity-new-overall",
            "development_type": "enhancement",
            "size_unit": "fp",
            "target_size": "100",
            "confirmed_phases": ["implementation"],
            "acknowledge_population_limits": False,
            "population_note": "短い",
        }
        result = calculate(request)
        self.assertEqual(result["benchmark"]["status"], "not_applied")
        self.assertGreaterEqual(len(result["benchmark"]["rejection_reasons"]), 3)
        self.assertNotIn("most_likely_exact", result["benchmark"])

    def test_small_fp_sample_is_reference_only(self) -> None:
        request = minimal_request()
        request["benchmark"] = {
            "catalog_id": "ipa-2022-fp-productivity-new-overall",
            "development_type": "new",
            "size_unit": "fp",
            "target_size": "151",
            "confirmed_phases": [
                "basic_design",
                "detailed_design",
                "implementation",
                "integration_test",
                "system_test_vendor",
            ],
            "acknowledge_population_limits": True,
            "population_note": "調整前FPの参考照合であり、件数不足のため計画値にはしない。",
        }
        result = calculate(request)
        self.assertEqual(result["benchmark"]["status"], "reference_only_small_sample")
        self.assertEqual(result["summary"]["planned_exact"], "2")

    def test_profile_entry_cannot_be_used_as_effort(self) -> None:
        request = minimal_request()
        request["benchmark"] = {"catalog_id": "ipa-2022-profile-project-effort"}
        result = calculate(request)
        self.assertEqual(result["benchmark"]["status"], "not_applied")
        self.assertIn("プロファイル", result["benchmark"]["reason"])

    def test_unknown_benchmark_does_not_invent_a_number(self) -> None:
        request = minimal_request()
        request["benchmark"] = {"catalog_id": "ipa-2022-does-not-exist"}
        result = calculate(request)
        self.assertEqual(result["benchmark"]["status"], "not_applied")
        self.assertNotIn("most_likely", result["benchmark"])


if __name__ == "__main__":
    unittest.main()
