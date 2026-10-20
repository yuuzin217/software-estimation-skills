"""見積もり計算のコマンドライン入口。"""

import argparse
import json
import sys
from pathlib import Path

from estimator.catalog import list_entries
from estimator.engine import calculate
from estimator.errors import EstimationError
from estimator.history import evaluate_history, load_history_document
from estimator.render import render_markdown
from estimator.skills_check import validate_skills


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="estimator", description="ソフトウェア開発見積もりの検証と計算")
    sub = parser.add_subparsers(dest="command", required=True)

    calc = sub.add_parser("calculate", help="依頼JSONを検証し、MarkdownとJSONを出力する")
    calc.add_argument("--input", required=True, help="依頼JSONのパス")
    calc.add_argument("--output", help="Markdownの出力先。省略時は標準出力")
    calc.add_argument("--json-output", help="機械可読JSONの出力先")

    history = sub.add_parser("validate-history", help="実績CSV/JSONの品質だけを確認する")
    history.add_argument("--input", required=True)

    skills = sub.add_parser("validate-skills", help="Skillディレクトリの構成と参照を確認する")
    skills.add_argument("--root", default=".")

    sub.add_parser("list-benchmarks", help="同梱した外部ベンチマークの一覧")

    args = parser.parse_args(argv)
    try:
        if args.command == "calculate":
            return _calculate(args)
        if args.command == "validate-history":
            return _validate_history(args)
        if args.command == "validate-skills":
            return _validate_skills(args)
        if args.command == "list-benchmarks":
            return _list_benchmarks()
    except EstimationError as exc:
        for message in exc.errors:
            print(message, file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ファイルを処理できません: {exc}", file=sys.stderr)
        return 1
    return 1


def _calculate(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    result = calculate(data, base_dir=input_path.parent)
    markdown = render_markdown(result)
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


def _validate_history(args: argparse.Namespace) -> int:
    path = Path(args.input)
    records, fictional = load_history_document({"path": str(path)}, path.parent)
    evaluation = evaluate_history(
        records,
        file_fictional=fictional,
        allow_fictional=True,
        include_anomalies=True,
        profile=None,
        target_size=None,
        effort_unit="person_day",
    )
    payload = {
        "loaded_count": evaluation["loaded_count"],
        "valid_count": evaluation["valid_count"],
        "fictional_file": fictional,
        "has_invalid_records": evaluation["valid_count"] != evaluation["loaded_count"],
        "records": [
            {
                "project_id": item["project_id"],
                "valid": item["valid"],
                "validity_issues": item["validity_issues"],
                "fictional": item["fictional"],
                "anomaly": item["anomaly"],
                "anomaly_reason": item["anomaly_reason"],
            }
            for item in evaluation["records"]
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _validate_skills(args: argparse.Namespace) -> int:
    errors = validate_skills(Path(args.root))
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        return 2
    print("Skillの構成検証に合格しました。")
    return 0


def _list_benchmarks() -> int:
    payload = [
        {
            "id": entry["id"],
            "calculable": entry["calculable"],
            "table": entry.get("table"),
            "n": entry.get("n"),
            "metric": entry.get("metric"),
        }
        for entry in list_entries()
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
