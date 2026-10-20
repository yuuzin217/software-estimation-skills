"""実績データの読み込み、品質確認、類似案件の抽出。"""

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from estimator.errors import ErrorBag, EstimationError
from estimator.numbers import exact_str, optional_decimal, parse_decimal
from estimator.policy import (
    ANOMALY_RATIO_HIGH,
    ANOMALY_RATIO_LOW,
    CATEGORY_JACCARD_MIN,
    HISTORICAL_PRIMARY_MIN_RECORDS,
    SIMILARITY_THRESHOLD,
)
from estimator.similarity import score_similarity

EFFORT_UNITS = {"person_day", "person_hour"}
SCOPES = {"new", "enhancement", "redevelopment", "other"}


def load_history_document(history: dict | None, base_dir: Path) -> tuple[list[dict], bool]:
    """実績レコードと、ファイル全体が架空かどうかのフラグを返す。"""
    if history is None:
        return [], False
    path = history.get("path")
    inline = history.get("records")
    if path and inline:
        raise EstimationError(["history.path と history.records は同時に指定できません。"])
    if path:
        return _load_path(Path(path), base_dir)
    if inline is None:
        return [], False
    if not isinstance(inline, list):
        raise EstimationError(["history.records は配列である必要があります。"])
    file_fictional = bool(history.get("fictional", False))
    return inline, file_fictional


def _load_path(path: Path, base_dir: Path) -> tuple[list[dict], bool]:
    resolved = path if path.is_absolute() else base_dir / path
    if not resolved.is_file():
        raise EstimationError([f"実績ファイルが見つかりません: {path}"])
    suffix = resolved.suffix.lower()
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise EstimationError([f"実績ファイルを読めません: {exc}"]) from exc
    if suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise EstimationError([f"実績JSONの形式が不正です: {exc}"]) from exc
        if isinstance(data, list):
            return data, False
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return data["records"], bool(data.get("fictional", False))
        raise EstimationError(["実績JSONは records 配列、またはレコードの配列である必要があります。"])
    if suffix == ".csv":
        return _load_csv(text), False
    raise EstimationError(["実績ファイルは .json または .csv である必要があります。"])


def _load_csv(text: str) -> list[dict]:
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise EstimationError(["実績CSVにヘッダーがありません。"])
    required = {"project_id", "actual_effort", "effort_unit"}
    missing = required - set(reader.fieldnames)
    if missing:
        raise EstimationError([f"実績CSVに必須列がありません: {', '.join(sorted(missing))}"])
    records = []
    for line_no, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        records.append(_csv_row(row, line_no))
    return records


def _csv_row(row: dict, line_no: int) -> dict:
    def cell(name: str) -> str:
        return (row.get(name) or "").strip()

    record = {
        "project_id": cell("project_id"),
        "project_type": cell("project_type"),
        "project_scope": cell("project_scope"),
        "technology_stack": _split_pipe(cell("technology_stack")),
        "work_categories": _split_pipe(cell("work_category") or cell("work_categories")),
        "estimated_effort": cell("estimated_effort") or None,
        "actual_effort": cell("actual_effort") or None,
        "effort_unit": cell("effort_unit"),
        "hours_per_person_day": cell("hours_per_person_day") or None,
        "team_size": cell("team_size") or None,
        "duration": cell("duration") or None,
        "duration_unit": cell("duration_unit") or None,
        "completion_date": cell("completion_date") or None,
        "fictional": cell("fictional") or None,
        "notes": cell("notes"),
    }
    size_kind = cell("size_kind")
    size_value = cell("size_value")
    if size_kind or size_value:
        record["size"] = {"kind": size_kind, "value": size_value or None}
    record["_line"] = line_no
    return record


def _split_pipe(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def evaluate_history(
    records: list[dict],
    *,
    file_fictional: bool,
    allow_fictional: bool,
    include_anomalies: bool,
    profile: dict | None,
    target_size: dict | None,
    effort_unit: str,
) -> dict:
    """品質、類似度、規模按分への採用可否をレコードごとに判定する。"""
    bag = ErrorBag()
    seen_ids: set[str] = set()
    evaluated = []
    for index, raw in enumerate(records):
        prefix = f"history.records[{index}]"
        if not isinstance(raw, dict):
            bag.add(f"{prefix}: オブジェクトである必要があります。")
            continue
        project_id = str(raw.get("project_id") or "").strip()
        if not project_id:
            bag.add(f"{prefix}: project_id は必須です。")
            continue
        if project_id in seen_ids:
            bag.add(f"{prefix}: project_id が重複しています（{project_id}）。")
            continue
        seen_ids.add(project_id)
        evaluated.append(
            _evaluate_record(
                raw,
                prefix=prefix,
                project_id=project_id,
                file_fictional=file_fictional,
                allow_fictional=allow_fictional,
                include_anomalies=include_anomalies,
                profile=profile,
                target_size=target_size,
                effort_unit=effort_unit,
            )
        )
    bag.raise_if_any()

    usable = [item for item in evaluated if item["usable_for_scaling"]]
    similar = [item for item in evaluated if item["above_threshold"] and item["valid"]]
    return {
        "loaded_count": len(evaluated),
        "valid_count": sum(1 for item in evaluated if item["valid"]),
        "similar_count": len(similar),
        "usable_for_scaling_count": len(usable),
        "allow_fictional": allow_fictional,
        "include_anomalies": include_anomalies,
        "fictional_records_present": any(item["fictional"] for item in evaluated),
        "records": evaluated,
        "can_be_primary": len(usable) >= HISTORICAL_PRIMARY_MIN_RECORDS,
    }


def _evaluate_record(
    raw: dict,
    *,
    prefix: str,
    project_id: str,
    file_fictional: bool,
    allow_fictional: bool,
    include_anomalies: bool,
    profile: dict | None,
    target_size: dict | None,
    effort_unit: str,
) -> dict:
    issues: list[str] = []
    record_unit = raw.get("effort_unit")
    if record_unit not in EFFORT_UNITS:
        issues.append(f"{prefix}: effort_unit は person_day または person_hour です。")
        record_unit = None

    actual = _optional_positive(raw.get("actual_effort"), f"{prefix}.actual_effort", issues, required=True)
    estimated = _optional_positive(
        raw.get("estimated_effort"), f"{prefix}.estimated_effort", issues, required=False
    )
    hours = _optional_positive(
        raw.get("hours_per_person_day"),
        f"{prefix}.hours_per_person_day",
        issues,
        required=False,
    )
    team_size = raw.get("team_size")
    if team_size not in (None, ""):
        _optional_positive(team_size, f"{prefix}.team_size", issues, required=False)
    duration = raw.get("duration")
    if duration not in (None, ""):
        _optional_positive(duration, f"{prefix}.duration", issues, required=False)

    completion = raw.get("completion_date")
    if completion not in (None, ""):
        try:
            date.fromisoformat(str(completion))
        except ValueError:
            issues.append(f"{prefix}.completion_date: YYYY-MM-DD で指定してください。")

    scope = raw.get("project_scope") or ""
    if scope and scope not in SCOPES:
        issues.append(
            f"{prefix}.project_scope: new、enhancement、redevelopment、other のいずれかです。"
        )

    technology = _string_list(raw.get("technology_stack"), f"{prefix}.technology_stack", issues)
    categories = _string_list(
        raw.get("work_categories", raw.get("work_category")),
        f"{prefix}.work_categories",
        issues,
    )
    size = _parse_size(raw.get("size"), f"{prefix}.size", issues)
    fictional = _parse_fictional(raw.get("fictional"), file_fictional, f"{prefix}.fictional", issues)

    anomaly = False
    anomaly_reason = ""
    if actual is not None and estimated is not None and not issues:
        ratio = actual / estimated
        if ratio > ANOMALY_RATIO_HIGH or ratio < ANOMALY_RATIO_LOW:
            anomaly = True
            anomaly_reason = (
                f"実績/見積が {exact_str(ratio)} であり、"
                f"方針上の範囲 {exact_str(ANOMALY_RATIO_LOW)}〜{exact_str(ANOMALY_RATIO_HIGH)} を外れます。"
                "IPAの外れ値除外方針とは別の、本ツールの按分ルールです。"
            )

    valid = not issues
    exclusion: list[str] = []
    if not valid:
        exclusion.extend(issues)
    if fictional and not allow_fictional:
        exclusion.append("架空データのため、allow_fictional が無い見積もりには使いません。")
    if anomaly and not include_anomalies:
        exclusion.append("異常値のため、include_anomalies が無い見積もりには使いません。")

    similarity = None
    if profile is not None:
        similarity = score_similarity(
            profile,
            {
                "project_type": raw.get("project_type") or "",
                "project_scope": scope,
                "technology_stack": technology,
                "work_categories": categories,
            },
        )
        if Decimal(similarity["similarity"]) < SIMILARITY_THRESHOLD:
            exclusion.append(
                f"類似度 {similarity['similarity']} が方針上の下限 {exact_str(SIMILARITY_THRESHOLD)} 未満です。"
            )
    elif valid:
        exclusion.append("comparison_profile が無いため類似度を計算できません。")

    converted = None
    if valid and actual is not None and record_unit is not None:
        converted = _convert(actual, record_unit, effort_unit, hours)
        if converted is None:
            exclusion.append(
                "工数単位を換算できません。実績側に hours_per_person_day を明示してください。"
            )

    category_jaccard = None if similarity is None else similarity.get("category_jaccard")
    if category_jaccard is None or Decimal(category_jaccard) < CATEGORY_JACCARD_MIN:
        exclusion.append(
            "工程区分の重なりが不足するため、規模按分には使いません。"
            f"（下限 {exact_str(CATEGORY_JACCARD_MIN)}）"
        )

    if target_size is None or size is None:
        exclusion.append("同じ種類の規模指標が無いため、規模按分には使いません。")
    elif size["kind"] != target_size["kind"]:
        exclusion.append(
            f"規模指標が一致しません（実績 {size['kind']}、対象 {target_size['kind']}）。"
        )

    usable = valid and not exclusion and converted is not None and size is not None
    rate = None
    if usable and size is not None and converted is not None:
        rate = converted / size["value"]

    return {
        "project_id": project_id,
        "valid": valid,
        "validity_issues": issues,
        "fictional": fictional,
        "anomaly": anomaly,
        "anomaly_reason": anomaly_reason,
        "similarity": None if similarity is None else similarity["similarity"],
        "similarity_components": None if similarity is None else similarity["components"],
        "similarity_notes": [] if similarity is None else similarity["notes"],
        "type_cap_applied": False if similarity is None else similarity["type_cap_applied"],
        "above_threshold": bool(
            similarity is not None and Decimal(similarity["similarity"]) >= SIMILARITY_THRESHOLD
        ),
        "usable_for_scaling": usable,
        "exclusion_reasons": exclusion,
        "converted_actual_effort": None if converted is None else exact_str(converted),
        "unit_rate": None if rate is None else exact_str(rate),
        "size": None
        if size is None
        else {"kind": size["kind"], "value": exact_str(size["value"])},
        "effort_unit": record_unit,
        "work_categories": categories,
        "notes": raw.get("notes") or "",
    }


def build_historical_estimate(evaluation: dict, target_size: dict | None, effort_unit: str) -> dict:
    """採用レコードの単位工数から三点見積もりを作る。幅は信頼区間ではない。"""
    used = [item for item in evaluation["records"] if item["usable_for_scaling"]]
    if target_size is None or not used:
        return {
            "status": "not_calculated",
            "reason": "類似し、規模指標と工程が対応する実績が不足しています。",
            "used_record_ids": [item["project_id"] for item in used],
            "effort_unit": effort_unit,
        }
    rates = sorted(Decimal(item["unit_rate"]) for item in used)
    size = Decimal(target_size["value_exact"])
    optimistic = rates[0] * size
    pessimistic = rates[-1] * size
    most_likely = _median(rates) * size
    expected = (optimistic + (Decimal(4) * most_likely) + pessimistic) / Decimal(6)
    provisional = len(rates) < 10
    return {
        "status": "calculated",
        "reason": (
            "類似実績の単位工数（実績工数÷規模）の最小・中央・最大に対象規模を掛けました。"
            "最小と最大は統計的な信頼区間ではありません。"
        ),
        "used_record_ids": [item["project_id"] for item in used],
        "size_kind": target_size["kind"],
        "size_value": target_size["value_exact"],
        "unit_rates": [
            {"project_id": item["project_id"], "rate": item["unit_rate"], "effort_unit": effort_unit}
            for item in used
        ],
        "optimistic_exact": exact_str(optimistic),
        "most_likely_exact": exact_str(most_likely),
        "pessimistic_exact": exact_str(pessimistic),
        "expected_exact": exact_str(expected),
        "provisional": provisional or len(rates) < 10,
        "provisional_reason": (
            f"按分に使った実績は {len(rates)} 件です。"
            "10件未満のため暫定値です。PERT期待値は保証値ではありません。"
        ),
        "single_point": len(rates) == 1,
        "effort_unit": effort_unit,
    }


def _median(values: list[Decimal]) -> Decimal:
    count = len(values)
    if count == 0:
        raise EstimationError(["中央値を計算する実績がありません。"])
    if count % 2 == 1:
        return values[count // 2]
    return (values[count // 2 - 1] + values[count // 2]) / Decimal(2)


def _convert(
    effort: Decimal, from_unit: str, to_unit: str, hours_per_person_day: Decimal | None
) -> Decimal | None:
    if from_unit == to_unit:
        return effort
    if hours_per_person_day is None:
        return None
    if from_unit == "person_hour" and to_unit == "person_day":
        return effort / hours_per_person_day
    if from_unit == "person_day" and to_unit == "person_hour":
        return effort * hours_per_person_day
    return None


def _optional_positive(
    value: object, field: str, issues: list[str], *, required: bool
) -> Decimal | None:
    if value is None or value == "":
        if required:
            issues.append(f"{field}: 必須です。")
        return None
    try:
        number = parse_decimal(value, field)
    except EstimationError as exc:
        issues.extend(exc.errors)
        return None
    if number <= 0:
        issues.append(f"{field}: 0より大きい必要があります。")
        return None
    return number


def _string_list(value: object, field: str, issues: list[str]) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return _split_pipe(value)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        issues.append(f"{field}: 文字列の配列である必要があります。")
        return []
    return value


def _parse_size(value: object, field: str, issues: list[str]) -> dict | None:
    if value is None or value == "":
        return None
    if not isinstance(value, dict):
        issues.append(f"{field}: オブジェクトである必要があります。")
        return None
    kind = str(value.get("kind") or "").strip()
    if not kind:
        issues.append(f"{field}.kind: 必須です。")
        return None
    try:
        number = optional_decimal(value.get("value"), f"{field}.value")
    except EstimationError as exc:
        issues.extend(exc.errors)
        return None
    if number is None or number <= 0:
        issues.append(f"{field}.value: 0より大きい必要があります。")
        return None
    return {"kind": kind, "value": number}


def _parse_fictional(
    value: object, file_fictional: bool, field: str, issues: list[str]
) -> bool:
    if value is None or value == "":
        return file_fictional
    if isinstance(value, bool):
        return value or file_fictional
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return file_fictional
    issues.append(f"{field}: true または false で指定してください。")
    return file_fictional
