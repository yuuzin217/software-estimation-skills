"""Skillの構成と公式バリデータの代替検証。"""

import json
import unittest
from pathlib import Path

from estimator.engine import calculate
from estimator.skills_check import validate_skills

ROOT = Path(__file__).resolve().parents[1]


class SkillLayoutTest(unittest.TestCase):
    def test_skill_layout(self) -> None:
        errors = validate_skills(ROOT)
        self.assertEqual(errors, [])

    def test_minimal_template_calculates(self) -> None:
        path = ROOT / ".agents/skills/software-estimation/assets/request.minimal.json"
        result = calculate(json.loads(path.read_text(encoding="utf-8")), base_dir=path.parent)
        self.assertEqual(result["summary"]["expected"], "2.00")

    def test_history_sample_is_marked_fictional(self) -> None:
        sample = json.loads(
            (ROOT / ".agents/skills/historical-estimation/assets/history.sample.json").read_text(encoding="utf-8")
        )
        self.assertTrue(sample["fictional"])
        self.assertTrue(all(record["fictional"] for record in sample["records"]))
        csv_text = (ROOT / ".agents/skills/historical-estimation/assets/history.sample.csv").read_text(encoding="utf-8")
        self.assertIn("true", csv_text)
        self.assertIn("架空", csv_text)


if __name__ == "__main__":
    unittest.main()
