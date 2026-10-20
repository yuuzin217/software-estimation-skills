"""WBSの検証、割合項目の展開、三点見積もりの集計。"""

import unicodedata
from decimal import Decimal

from estimator.errors import ErrorBag, EstimationError
from estimator.numbers import exact_str, parse_decimal

PHASES = {
    "requirements",
    "basic_design",
    "detailed_design",
    "implementation",
    "ui_implementation",
    "api_implementation",
    "test",
    "db",
    "external_integration",
    "auth",
    "security",
    "unit_test",
    "integration_test",
    "system_test",
    "review",
    "defect_fix",
    "cicd",
    "infrastructure",
    "documentation",
    "release",
    "handover",
    "project_management",
    "impact_analysis",
    "regression_test",
    "data_migration",
    "other",
}
BASIS_KINDS = {"SOURCE", "HISTORICAL", "ASSUMPTION", "AI_ESTIMATE"}
UNCERTAINTY = {"low", "medium", "high"}
UNSCOPED = "UNSCOPED"


def prepare_wbs(
    items: list[dict],
    *,
    known_requirement_ids: set[str],
    effort_unit: str,
    known_history_ids: set[str],
    catalog_ids: set[str],
) -> list[dict]:
    """検証済みのWBS行を入力順で返す。工数はexact文字列。"""
    bag = ErrorBag()
    if not isinstance(items, list):
        raise EstimationError(["wbs は配列である必要があります。"])

    normalized = []
    ids = []
    for index, raw in enumerate(items):
        prefix = f"wbs[{index}]"
        if not isinstance(raw, dict):
            bag.add(f"{prefix}: オブジェクトである必要があります。")
            continue
        item = _normalize_item(
            raw,
            prefix,
            bag,
            known_requirement_ids=known_requirement_ids,
            effort_unit=effort_unit,
            known_history_ids=known_history_ids,
            catalog_ids=catalog_ids,
        )
        if item is not None:
            normalized.append(item)
            ids.append(item["id"])
    bag.raise_if_any()

    _reject_duplicate_ids(normalized)
    _reject_duplicate_work(normalized)
    _reject_dependency_errors(normalized)
    _apply_derivations(normalized)
    return normalized


def summarize_wbs(items: list[dict], effort_unit: str) -> dict:
    estimable = [item for item in items if item["estimable"]]
    if not estimable:
        return {
            "status": "not_calculated",
            "reason": "算定できるWBS項目がありません。",
            "effort_unit": effort_unit,
            "lines": items,
        }
    optimistic = sum(Decimal(item["optimistic_exact"]) for item in estimable)
    most_likely = sum(Decimal(item["most_likely_exact"]) for item in estimable)
    pessimistic = sum(Decimal(item["pessimistic_exact"]) for item in estimable)
    expected = sum(Decimal(item["expected_exact"]) for item in estimable)
    kinds = {item["basis"]["kind"] for item in estimable}
    return {
        "status": "calculated",
        "reason": "",
        "effort_unit": effort_unit,
        "optimistic_exact": exact_str(optimistic),
        "most_likely_exact": exact_str(most_likely),
        "pessimistic_exact": exact_str(pessimistic),
        "expected_exact": exact_str(expected),
        "primary_basis": next(iter(kinds)) if len(kinds) == 1 else "MIXED",
        "provenance_totals": _provenance(estimable),
        "lines": items,
    }


def _normalize_item(
    raw: dict,
    prefix: str,
    bag: ErrorBag,
    *,
    known_requirement_ids: set[str],
    effort_unit: str,
    known_history_ids: set[str],
    catalog_ids: set[str],
) -> dict | None:
    item_id = _require_id(raw.get("id"), f"{prefix}.id", bag)
    name = _require_text(raw.get("name"), f"{prefix}.name", bag)
    description = _require_text(raw.get("description"), f"{prefix}.description", bag)
    phase = raw.get("phase")
    if phase not in PHASES:
        bag.add(f"{prefix}.phase: 未対応の工程区分です（{phase}）。")
        phase = "other"
    requirement_ids = raw.get("requirement_ids")
    if not isinstance(requirement_ids, list) or not requirement_ids:
        bag.add(f"{prefix}.requirement_ids: 1件以上の要件IDが必要です。横断作業は UNSCOPED を使います。")
        requirement_ids = []
    else:
        for req in requirement_ids:
            if req != UNSCOPED and req not in known_requirement_ids:
                bag.add(f"{prefix}.requirement_ids: 未知の要件IDです（{req}）。")
    estimable = raw.get("estimable", True)
    if not isinstance(estimable, bool):
        bag.add(f"{prefix}.estimable: true または false で指定してください。")
        estimable = False

    depends_on = raw.get("depends_on") or []
    if not isinstance(depends_on, list) or not all(isinstance(value, str) for value in depends_on):
        bag.add(f"{prefix}.depends_on: 文字列の配列である必要があります。")
        depends_on = []
    prerequisites = raw.get("prerequisites") or ""
    if not isinstance(prerequisites, str):
        bag.add(f"{prefix}.prerequisites: 文字列である必要があります。")
        prerequisites = ""

    line_unit = raw.get("effort_unit", effort_unit)
    if line_unit != effort_unit:
        bag.add(f"{prefix}.effort_unit: meta.effort_unit（{effort_unit}）と一致させてください。単位換算は行いません。")

    derivation = raw.get("derivation")
    if derivation is not None and not isinstance(derivation, dict):
        bag.add(f"{prefix}.derivation: オブジェクトである必要があります。")
        derivation = None

    blocked_reason = ""
    optimistic = most_likely = pessimistic = None
    if not estimable:
        blocked_reason = _require_text(raw.get("blocked_reason"), f"{prefix}.blocked_reason", bag, minimum=4)
        if any(raw.get(key) is not None for key in ("optimistic", "most_likely", "pessimistic", "derivation")):
            bag.add(f"{prefix}: 算定不能な項目に工数や割合導出を入れないでください。")
        basis = None
    else:
        basis = _normalize_basis(
            raw.get("basis"),
            prefix,
            bag,
            known_history_ids=known_history_ids,
            catalog_ids=catalog_ids,
            provisional=raw.get("provisional"),
        )
        uncertainty = raw.get("uncertainty")
        if uncertainty not in UNCERTAINTY:
            bag.add(f"{prefix}.uncertainty: low、medium、high のいずれかです。")
        if not isinstance(raw.get("provisional"), bool):
            bag.add(f"{prefix}.provisional: true または false で指定してください。")
        if derivation is None:
            optimistic = _read_point(raw.get("optimistic"), f"{prefix}.optimistic", bag)
            most_likely = _read_point(raw.get("most_likely"), f"{prefix}.most_likely", bag)
            pessimistic = _read_point(raw.get("pessimistic"), f"{prefix}.pessimistic", bag)
            if None not in (optimistic, most_likely, pessimistic):
                _check_order(optimistic, most_likely, pessimistic, prefix, bag)
        else:
            if any(raw.get(key) is not None for key in ("optimistic", "most_likely", "pessimistic")):
                bag.add(f"{prefix}: 割合導出と手入力の三点を同時に指定できません。")
            _validate_derivation(derivation, f"{prefix}.derivation", bag)

    if item_id is None or name is None or description is None:
        return None
    return {
        "id": item_id,
        "requirement_ids": list(requirement_ids),
        "name": name,
        "description": description,
        "phase": phase,
        "prerequisites": prerequisites,
        "depends_on": list(depends_on),
        "estimable": estimable,
        "blocked_reason": blocked_reason,
        "uncertainty": raw.get("uncertainty") if estimable else None,
        "provisional": raw.get("provisional") if estimable else None,
        "basis": basis,
        "derivation": derivation if estimable else None,
        "optimistic_exact": None if optimistic is None else exact_str(optimistic),
        "most_likely_exact": None if most_likely is None else exact_str(most_likely),
        "pessimistic_exact": None if pessimistic is None else exact_str(pessimistic),
        "expected_exact": None
        if None in (optimistic, most_likely, pessimistic)
        else exact_str(_pert(optimistic, most_likely, pessimistic)),
        "effort_unit": effort_unit,
    }


def _apply_derivations(items: list[dict]) -> None:
    by_id = {item["id"]: item for item in items}
    pending = [item for item in items if item["estimable"] and item["derivation"] is not None]
    resolved: set[str] = {item["id"] for item in items if item["estimable"] and item["derivation"] is None}
    guard = 0
    while pending:
        guard += 1
        if guard > len(items) + 1:
            raise EstimationError(["割合導出に循環参照があります。"])
        progress = False
        next_pending = []
        for item in pending:
            base_ids = item["derivation"]["base_ids"]
            if any(base_id not in resolved for base_id in base_ids):
                if any(base_id not in by_id or not by_id[base_id]["estimable"] for base_id in base_ids):
                    missing = [base_id for base_id in base_ids if base_id not in by_id or not by_id[base_id]["estimable"]]
                    raise EstimationError(
                        [f"{item['id']}: 割合の基準に算定不能または未知の項目があります（{', '.join(missing)}）。"]
                    )
                next_pending.append(item)
                continue
            percent = Decimal(item["derivation"]["percent_exact"]) / Decimal(100)
            optimistic = sum(Decimal(by_id[base_id]["optimistic_exact"]) for base_id in base_ids) * percent
            most_likely = sum(Decimal(by_id[base_id]["most_likely_exact"]) for base_id in base_ids) * percent
            pessimistic = sum(Decimal(by_id[base_id]["pessimistic_exact"]) for base_id in base_ids) * percent
            item["optimistic_exact"] = exact_str(optimistic)
            item["most_likely_exact"] = exact_str(most_likely)
            item["pessimistic_exact"] = exact_str(pessimistic)
            item["expected_exact"] = exact_str(_pert(optimistic, most_likely, pessimistic))
            resolved.add(item["id"])
            progress = True
        if not progress and next_pending:
            raise EstimationError(["割合導出に循環参照があります。"])
        pending = next_pending

    derived = [item for item in items if item["derivation"] is not None]
    for left_index, left in enumerate(derived):
        left_bases = set(left["derivation"]["base_ids"])
        for right in derived[left_index + 1 :]:
            if left_bases & set(right["derivation"]["base_ids"]):
                left.setdefault("warnings", []).append(
                    f"{right['id']} と割合の基準WBSが重なっています。二重計上でないか確認してください。"
                )


def _validate_derivation(derivation: dict, prefix: str, bag: ErrorBag) -> None:
    if derivation.get("type") != "percent_of":
        bag.add(f"{prefix}.type: percent_of のみ対応しています。")
        return
    base_ids = derivation.get("base_ids")
    if not isinstance(base_ids, list) or not base_ids or not all(isinstance(value, str) for value in base_ids):
        bag.add(f"{prefix}.base_ids: 1件以上のWBS IDが必要です。")
    else:
        derivation["base_ids"] = list(base_ids)
    try:
        percent = parse_decimal(derivation.get("percent"), f"{prefix}.percent")
    except EstimationError as exc:
        bag.errors.extend(exc.errors)
        return
    if percent < 0:
        bag.add(f"{prefix}.percent: 0以上である必要があります。")
        return
    derivation["percent_exact"] = exact_str(percent)


def _normalize_basis(
    basis: object,
    prefix: str,
    bag: ErrorBag,
    *,
    known_history_ids: set[str],
    catalog_ids: set[str],
    provisional: object,
) -> dict | None:
    if not isinstance(basis, dict):
        bag.add(f"{prefix}.basis: 算定根拠オブジェクトが必要です。")
        return None
    kind = basis.get("kind")
    if kind not in BASIS_KINDS:
        bag.add(f"{prefix}.basis.kind: SOURCE、HISTORICAL、ASSUMPTION、AI_ESTIMATE のいずれかです。")
        return None
    explanation = _require_text(basis.get("explanation"), f"{prefix}.basis.explanation", bag, minimum=8)
    record_ids = basis.get("historical_record_ids") or []
    if not isinstance(record_ids, list) or not all(isinstance(value, str) for value in record_ids):
        bag.add(f"{prefix}.basis.historical_record_ids: 文字列の配列である必要があります。")
        record_ids = []
    source_id = basis.get("source_id")
    citation = basis.get("citation")
    if kind == "AI_ESTIMATE":
        if provisional is not True:
            bag.add(f"{prefix}: AI_ESTIMATE は provisional を true にしてください。確定値として扱えません。")
        if source_id or citation or record_ids:
            bag.add(f"{prefix}.basis: AI_ESTIMATE に出典IDや実績IDを付けて公的値のように見せないでください。")
    elif kind == "SOURCE":
        if source_id and source_id not in catalog_ids:
            bag.add(f"{prefix}.basis.source_id: 目録に無い出典です（{source_id}）。")
        if citation is not None:
            _validate_citation(citation, f"{prefix}.basis.citation", bag)
        if not source_id and not isinstance(citation, dict):
            bag.add(f"{prefix}.basis: SOURCE には source_id か citation が必要です。")
    elif kind == "HISTORICAL":
        if not record_ids:
            bag.add(f"{prefix}.basis.historical_record_ids: 実績IDが必要です。")
        missing = [record_id for record_id in record_ids if record_id not in known_history_ids]
        if missing:
            bag.add(f"{prefix}.basis.historical_record_ids: 実績に無いIDです（{', '.join(missing)}）。")
    return {
        "kind": kind,
        "explanation": explanation or "",
        "source_id": source_id,
        "citation": citation if isinstance(citation, dict) else None,
        "historical_record_ids": list(record_ids),
    }


def _validate_citation(citation: object, prefix: str, bag: ErrorBag) -> None:
    if not isinstance(citation, dict):
        bag.add(f"{prefix}: オブジェクトである必要があります。")
        return
    for key in ("title", "publisher", "year", "url"):
        if not isinstance(citation.get(key), str) or not citation[key].strip():
            bag.add(f"{prefix}.{key}: 必須です。")
    url = citation.get("url")
    if isinstance(url, str) and not url.startswith("https://"):
        bag.add(f"{prefix}.url: https:// で始まるURLを指定してください。")


def _reject_duplicate_ids(items: list[dict]) -> None:
    seen = set()
    errors = []
    for item in items:
        if item["id"] in seen:
            errors.append(f"WBS IDが重複しています（{item['id']}）。")
        seen.add(item["id"])
    if errors:
        raise EstimationError(errors)


def _reject_duplicate_work(items: list[dict]) -> None:
    seen = {}
    errors = []
    for item in items:
        if not item["estimable"]:
            continue
        key = (
            _normalize_name(item["name"]),
            item["phase"],
            tuple(sorted(item["requirement_ids"])),
        )
        if key in seen:
            errors.append(
                f"{item['id']} は {seen[key]} と作業名・工程・要件が重なっています。二重計上の可能性があります。"
            )
        else:
            seen[key] = item["id"]
    if errors:
        raise EstimationError(errors)


def _reject_dependency_errors(items: list[dict]) -> None:
    ids = {item["id"] for item in items}
    errors = []
    graph = {item["id"]: item["depends_on"] for item in items}
    for item_id, deps in graph.items():
        for dep in deps:
            if dep == item_id:
                errors.append(f"{item_id}: 自分自身を依存先にできません。")
            elif dep not in ids:
                errors.append(f"{item_id}: 依存先 {dep} がWBSにありません。")
    if errors:
        raise EstimationError(errors)
    visiting = set()
    visited = set()

    def walk(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise EstimationError([f"{node}: 依存関係が循環しています。"])
        visiting.add(node)
        for dep in graph.get(node, []):
            if dep in graph:
                walk(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        walk(node)


def _provenance(items: list[dict]) -> dict[str, str]:
    totals = {kind: Decimal(0) for kind in BASIS_KINDS}
    for item in items:
        totals[item["basis"]["kind"]] += Decimal(item["expected_exact"])
    return {kind: exact_str(value) for kind, value in totals.items() if value != 0}


def _pert(optimistic: Decimal, most_likely: Decimal, pessimistic: Decimal) -> Decimal:
    return (optimistic + (Decimal(4) * most_likely) + pessimistic) / Decimal(6)


def _check_order(
    optimistic: Decimal, most_likely: Decimal, pessimistic: Decimal, prefix: str, bag: ErrorBag
) -> None:
    if optimistic < 0:
        bag.add(f"{prefix}.optimistic: 0以上である必要があります。")
    if not optimistic <= most_likely <= pessimistic:
        bag.add(f"{prefix}: 楽観値 <= 最頻値 <= 悲観値 を満たす必要があります。")


def _read_point(value: object, field: str, bag: ErrorBag) -> Decimal | None:
    try:
        return parse_decimal(value, field)
    except EstimationError as exc:
        bag.errors.extend(exc.errors)
        return None


def _require_text(value: object, field: str, bag: ErrorBag, minimum: int = 1) -> str | None:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        bag.add(f"{field}: {minimum}文字以上の文字列が必要です。")
        return None
    return value.strip()


def _require_id(value: object, field: str, bag: ErrorBag) -> str | None:
    if not isinstance(value, str) or not value.strip():
        bag.add(f"{field}: 必須です。")
        return None
    text = value.strip()
    if len(text) > 40 or not text[0].isascii() or not text[0].isalpha():
        bag.add(f"{field}: 先頭は英字、全体は40文字以内にしてください。")
        return None
    if any(not (char.isascii() and (char.isalnum() or char in "_-")) for char in text):
        bag.add(f"{field}: 英数字、ハイフン、アンダースコアのみ使えます。")
        return None
    return text


def _normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).casefold()
    return " ".join(normalized.split())
