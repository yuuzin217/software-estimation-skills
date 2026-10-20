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


    def test_folder_input_workflow_and_examples_are_present(self) -> None:
        skill_dir = ROOT / ".agents/skills/software-estimation"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        guide = (skill_dir / "references/folder-input.md").read_text(encoding="utf-8")
        self.assertIn("references/folder-input.md", skill)
        for phrase in ("request.json", "sources.md", "estimate.json", "estimate.md", "wbs.csv"):
            self.assertIn(phrase, guide)
        self.assertIn("python -m estimator calculate", guide)
        self.assertIn(".estimates/", (ROOT / ".gitignore").read_text(encoding="utf-8"))

        docs_dir = ROOT / "examples/folder-input-demo"
        requirements = (docs_dir / "requirements.md").read_text(encoding="utf-8")
        architecture = (docs_dir / "architecture.md").read_text(encoding="utf-8")
        self.assertIn("F-001", requirements)
        self.assertIn("NF-001", requirements)
        self.assertIn("Cloudflare D1", architecture)

    def test_readmes_explain_folder_input_limitations(self) -> None:
        for name in ("README.md", "README.en.md"):
            with self.subTest(name=name):
                content = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("examples/folder-input-demo/", content)
                self.assertIn(".estimates/", content)
                self.assertIn("references/folder-input.md", content)
                self.assertIn("request.json", content)


if __name__ == "__main__":
    unittest.main()
