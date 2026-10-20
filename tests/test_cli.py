"""コマンドラインの終了コードと実績CSV。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import minimal_request


ROOT = Path(__file__).resolve().parents[1]


class CliTest(unittest.TestCase):
    def test_calculate_writes_json_and_rejects_bad_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory / "request.json"
            source.write_text(json.dumps(minimal_request()), encoding="utf-8")
            markdown = directory / "estimate.md"
            payload = directory / "estimate.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "estimator",
                    "calculate",
                    "--input",
                    str(source),
                    "--output",
                    str(markdown),
                    "--json-output",
                    str(payload),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            saved = json.loads(payload.read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"]["expected"], "2.00")
            self.assertIn("見積もり結果", markdown.read_text(encoding="utf-8"))

            source.write_text("{}", encoding="utf-8")
            failed = subprocess.run(
                [sys.executable, "-m", "estimator", "calculate", "--input", str(source)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failed.returncode, 2)

    def test_validate_history_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.csv"
            path.write_text(
                "\n".join(
                    [
                        "project_id,project_type,technology_stack,project_scope,work_category,estimated_effort,actual_effort,effort_unit,fictional,notes",
                        "P-001,new_web_app,python|fastapi,new,implementation|test,10,12,person_day,true,架空",
                        "P-002,new_web_app,python,new,implementation,10,,person_day,true,欠損",
                    ]
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, "-m", "estimator", "validate-history", "--input", str(path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["loaded_count"], 2)
            self.assertTrue(report["has_invalid_records"])
            self.assertFalse(report["records"][1]["valid"])

    def test_estimator_imports_are_stdlib_only(self) -> None:
        import ast

        for path in (ROOT / "estimator").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module.split(".")[0]]
                else:
                    continue
                for module in modules:
                    if module == "estimator":
                        continue
                    self.assertIn(module, sys.stdlib_module_names, f"{path.name}: {module}")


if __name__ == "__main__":
    unittest.main()
