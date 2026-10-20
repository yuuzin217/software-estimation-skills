"""見積もり計算のコマンドライン入口。"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from estimator.catalog import list_entries
from estimator.engine import calculate
from estimator.errors import EstimationError
from estimator.history import evaluate_history, load_history_document
from estimator.render import render_csv, render_markdown
from estimator.skills_check import validate_skills


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="estimator", description="ソフトウェア開発見積もりの検証と計算")
    sub = parser.add_subparsers(dest="command", required=True)

    calc = sub.add_parser("calculate", help="依頼JSONを検証し、Markdown・JSON・CSVを出力する")
    calc.add_argument("--input", required=True, help="依頼JSONのパス")
    calc.add_argument("--output", help="Markdownの出力先。省略時は標準出力")
    calc.add_argument("--json-output", help="機械可読JSONの出力先")
    calc.add_argument("--csv-output", help="WBS明細CSVの出力先")

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
    protected_paths = [("依頼JSON", input_path)]
    history_spec = data.get("history") if isinstance(data, dict) else None
    history_path_value = history_spec.get("path") if isinstance(history_spec, dict) else None
    if isinstance(history_path_value, str) and history_path_value:
        history_path = Path(history_path_value)
        if not history_path.is_absolute():
            history_path = input_path.parent / history_path
        protected_paths.append(("参照実績ファイル", history_path))
    output_targets = [
        Path(path)
        for path in (args.output, args.json_output, args.csv_output)
        if path
    ]
    _validate_output_paths(output_targets, protected_paths)
    result = calculate(data, base_dir=input_path.parent)
    markdown = render_markdown(result)
    outputs: list[tuple[Path, str]] = []
    if args.output:
        outputs.append((Path(args.output), markdown))
    if args.json_output:
        outputs.append((Path(args.json_output), json.dumps(result, ensure_ascii=False, indent=2) + "\n"))
    if args.csv_output:
        outputs.append((Path(args.csv_output), render_csv(result)))
    _write_output_files(outputs, protected_paths=protected_paths)
    if not args.output:
        print(markdown)
    return 0


def _validate_output_paths(
    targets: list[Path], protected_paths: list[tuple[str, Path]] | None = None
) -> None:
    resolved = [path.resolve(strict=False) for path in targets]
    if len(set(resolved)) != len(resolved):
        raise EstimationError(["Markdown、JSON、CSVの出力先は別々のファイルにしてください。"])

    for target in targets:
        for label, protected in protected_paths or []:
            if _paths_refer_to_same_file(target, protected):
                raise EstimationError(
                    [f"出力先 {target} は {label} ({protected}) と同じファイルを指すため、上書きを拒否しました。"]
                )


def _paths_refer_to_same_file(first: Path, second: Path) -> bool:
    if first.resolve(strict=False) == second.resolve(strict=False):
        return True
    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _write_output_files(
    outputs: list[tuple[Path, str]],
    *,
    protected_paths: list[tuple[str, Path]] | None = None,
) -> None:
    """Stage every output first, then atomically replace targets with rollback on failure."""
    targets = [target for target, _ in outputs]
    _validate_output_paths(targets, protected_paths)

    originals: dict[Path, bytes | None] = {}
    staged: list[tuple[Path, Path]] = []
    replaced: list[Path] = []
    try:
        for target, content in outputs:
            target.parent.mkdir(parents=True, exist_ok=True)
            originals[target] = target.read_bytes() if target.exists() else None
            fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temp_path = Path(temp_name)
            staged.append((target, temp_path))
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        _validate_output_paths(targets, protected_paths)
        for target, temp_path in staged:
            os.replace(temp_path, target)
            replaced.append(target)
    except OSError:
        for target in reversed(replaced):
            previous = originals[target]
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                fd, rollback_name = tempfile.mkstemp(
                    prefix=f".{target.name}.", suffix=".rollback", dir=target.parent
                )
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(previous)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(rollback_name, target)
                finally:
                    Path(rollback_name).unlink(missing_ok=True)
        raise
    finally:
        for _, temp_path in staged:
            temp_path.unlink(missing_ok=True)


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
