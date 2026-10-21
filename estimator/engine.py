"""見積もり依頼を検証し、方式選択と集計を行う。"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from estimator.version import __version__
from estimator.benchmark import evaluate_benchmark
from estimator.catalog import list_entries
from estimator.cost_schedule import calculate_cost, calculate_schedule
from estimator.errors import ErrorBag, EstimationError
from estimator.history import build_historical_estimate, evaluate_history, load_history_document
from estimator.numbers import effort_str, exact_str, money_str, optional_decimal
from estimator.policy import (
    CATEGORY_JACCARD_MIN,
    HISTORICAL_PRIMARY_MIN_RECORDS,
    MAX_SIZE_EXTRAPOLATION_FACTOR,
    POLICY_NOTE,
    SIMILARITY_THRESHOLD,
    SIMILARITY_WEIGHTS,
)
from estimator.wbs import prepare_wbs, summarize_wbs

EFFORT_UNITS = {"person_day", "person_hour"}
SCOPES = {"new", "enhancement", "redevelopment", "other"}


def calculate(data: dict, *, base_dir: Path | None = None) -> dict:
    """依頼JSONから機械可読な見積もり結果を作る。"""
    if not isinstance(data, dict):
        raise EstimationError(["依頼はJSONオブジェクトである必要があります。"])
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    bag = ErrorBag()
    unknown = sorted(set(data) - _ALLOWED_TOP)
    if unknown:
        bag.add("未知のキーがあります: " + ", ".join(unknown))
    if data.get("schema_version") != "1.0":
        bag.add("schema_version は 1.0 である必要があります。")
    meta = _meta(data.get("meta"), bag)
    scope = _scope(data.get("scope"), bag)
    assumptions = _assumptions(data.get("assumptions", []), bag)
    risks = _risks(data.get("risks", []), bag)
    source_review = _source_review(data.get("source_review"), bag)
    hours = meta.get("hours_per_person_day") if meta else None
    effort_unit = meta.get("effort_unit") if meta else "person_day"
    history_spec = data.get("history")
    records, file_fictional = ([], False)
    allow_fictional = False
    include_anomalies = False
    if history_spec is not None:
        if not isinstance(history_spec, dict):
            bag.add("history はオブジェクトである必要があります。")
        else:
            allow_fictional = bool(history_spec.get("allow_fictional", False))
            include_anomalies = bool(history_spec.get("include_anomalies", False))
            if "allow_fictional" in history_spec and not isinstance(history_spec["allow_fictional"], bool):
                bag.add("history.allow_fictional は true または false です。")
            if "include_anomalies" in history_spec and not isinstance(history_spec["include_anomalies"], bool):
                bag.add("history.include_anomalies は true または false です。")
            try:
                records, file_fictional = load_history_document(history_spec, base)
            except EstimationError as exc:
                bag.errors.extend(exc.errors)
    profile = _profile(data.get("comparison_profile"), bool(records), bag)
    target_size = _target_size(data.get("target_size"), bag)
    bag.raise_if_any()

    assert meta is not None
    evaluation = evaluate_history(
        records,
        file_fictional=file_fictional,
        allow_fictional=allow_fictional,
        include_anomalies=include_anomalies,
        profile=profile,
        target_size=target_size,
        effort_unit=effort_unit,
    )
    known_history_ids = {item["project_id"] for item in evaluation["records"]}
    catalog_ids = {entry["id"] for entry in list_entries()}
    requirement_ids = {item["id"] for item in scope["functions"]} | {item["id"] for item in scope["non_functional"]}
    wbs = prepare_wbs(
        data.get("wbs", []),
        known_requirement_ids=requirement_ids,
        effort_unit=effort_unit,
        known_history_ids=known_history_ids,
        catalog_ids=catalog_ids,
    )
    wbs_summary = summarize_wbs(wbs, effort_unit)
    historical = build_historical_estimate(evaluation, target_size, effort_unit)
    contingency = _contingency(data.get("contingency"), effort_unit, risks, bag)
    bag.raise_if_any()

    method = _select_method(
        data.get("method_override"),
        evaluation,
        wbs_summary,
        historical,
        contingency,
    )
    coverage = _estimate_coverage(scope, wbs_summary, method, historical, source_review)
    warnings = _warnings(wbs, wbs_summary, evaluation, historical, method, assumptions, risks, contingency, coverage)
    summary = _primary_summary(method, wbs_summary, historical, contingency, effort_unit)
    summary["estimate_scope"] = "project" if coverage["is_total_estimate"] else "partial"
    if summary["status"] != "calculated" and not any(not item["estimable"] for item in wbs):
        raise EstimationError(
            [summary["reason"] or "見積もり可能なWBSも、採用できる実績もありません。"]
        )
    benchmark = evaluate_benchmark(data.get("benchmark"))
    total_effort = summary.get("planned_exact") if coverage["is_total_estimate"] else None
    cost = calculate_cost(
        data.get("cost"),
        total_effort,
        effort_unit,
        Decimal(hours) if hours else None,
    )
    schedule = calculate_schedule(
        data.get("schedule"),
        total_effort,
        effort_unit,
        Decimal(hours) if hours else None,
    )
    if not coverage["is_total_estimate"]:
        reason = "資料の確認またはWBSの網羅性が不完全なため、対象全体の費用・期間は算出しません。"
        cost = {"status": "not_calculated", "reason": reason}
        schedule = {"status": "not_calculated", "reason": reason}
    return _present(
        meta=meta,
        scope=scope,
        assumptions=assumptions,
        risks=risks,
        source_review=source_review,
        method=method,
        evaluation=evaluation,
        benchmark=benchmark,
        wbs_summary=wbs_summary,
        historical=historical,
        summary=summary,
        coverage=coverage,
        cost=cost,
        schedule=schedule,
        warnings=warnings,
        contingency=contingency,
    )


_ALLOWED_TOP = {
    "schema_version",
    "meta",
    "scope",
    "assumptions",
    "risks",
    "wbs",
    "contingency",
    "cost",
    "schedule",
    "history",
    "comparison_profile",
    "target_size",
    "benchmark",
    "method_override",
    "source_review",
}


def _source_review(value: object, bag: ErrorBag) -> dict:
    """資料の監査宣言。旧入力との互換性のため、省略時は未評価とする。"""
    if value is None:
        return {"status": "not_assessed", "blockers": []}
    if not isinstance(value, dict):
        bag.add("source_review はオブジェクトである必要があります。")
        return {"status": "not_assessed", "blockers": []}
    unexpected = sorted(set(value) - {"status", "blockers"})
    if unexpected:
        bag.add("source_review に未知のキーがあります: " + ", ".join(unexpected))
    status = value.get("status")
    if status not in ("complete", "incomplete"):
        bag.add("source_review.status は complete または incomplete です。")
        status = "incomplete"
    blockers = value.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(x, str) or not x.strip() for x in blockers):
        bag.add("source_review.blockers は空でない文字列の配列にしてください。")
        blockers = []
    if status == "complete" and blockers:
        bag.add("source_review.status が complete のとき blockers は空である必要があります。")
    if status == "incomplete" and not blockers:
        bag.add("source_review.status が incomplete のときは blockers に未読資料や重要な未解決事項を記録してください。")
    return {"status": status, "blockers": list(blockers)}


def _meta(meta: object, bag: ErrorBag) -> dict | None:
    if not isinstance(meta, dict):
        bag.add("meta はオブジェクトである必要があります。")
        return None
    system_name = _text(meta.get("system_name"), "meta.system_name", bag)
    purpose = _text(meta.get("purpose"), "meta.purpose", bag)
    input_summary = _text(meta.get("input_summary"), "meta.input_summary", bag, minimum=4)
    effort_unit = meta.get("effort_unit")
    if effort_unit not in EFFORT_UNITS:
        bag.add("meta.effort_unit は person_day または person_hour です。")
        effort_unit = "person_day"
    estimation_date = meta.get("estimation_date")
    try:
        date.fromisoformat(str(estimation_date))
    except ValueError:
        bag.add("meta.estimation_date は YYYY-MM-DD で指定してください。")
    hours = None
    if "hours_per_person_day" in meta and meta["hours_per_person_day"] is not None:
        try:
            hours_number = optional_decimal(meta["hours_per_person_day"], "meta.hours_per_person_day")
        except EstimationError as exc:
            bag.errors.extend(exc.errors)
            hours_number = None
        if hours_number is not None and hours_number <= 0:
            bag.add("meta.hours_per_person_day は0より大きい必要があります。")
        elif hours_number is not None:
            hours = exact_str(hours_number)
    return {
        "system_name": system_name or "",
        "purpose": purpose or "",
        "estimation_date": estimation_date,
        "input_summary": input_summary or "",
        "effort_unit": effort_unit,
        "hours_per_person_day": hours,
    }


def _scope(scope: object, bag: ErrorBag) -> dict:
    if not isinstance(scope, dict):
        bag.add("scope はオブジェクトである必要があります。")
        return {"functions": [], "non_functional": [], "out_of_scope": [], "unknowns": []}
    functions = _scope_items(scope.get("functions"), "scope.functions", bag)
    non_functional = _scope_items(scope.get("non_functional"), "scope.non_functional", bag)
    ids = [item["id"] for item in functions + non_functional]
    if len(ids) != len(set(ids)):
        bag.add("scope: 要件IDが重複しています。")
    return {
        "functions": functions,
        "non_functional": non_functional,
        "out_of_scope": _string_list(scope.get("out_of_scope", []), "scope.out_of_scope", bag),
        "unknowns": _string_list(scope.get("unknowns", []), "scope.unknowns", bag),
    }


def _scope_items(value: object, field: str, bag: ErrorBag) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        bag.add(f"{field}: 配列である必要があります。")
        return []
    items = []
    for index, raw in enumerate(value):
        prefix = f"{field}[{index}]"
        if not isinstance(raw, dict):
            bag.add(f"{prefix}: オブジェクトである必要があります。")
            continue
        item_id = _text(raw.get("id"), f"{prefix}.id", bag)
        name = _text(raw.get("name"), f"{prefix}.name", bag)
        description = _text(raw.get("description"), f"{prefix}.description", bag)
        if item_id and name and description:
            items.append({"id": item_id, "name": name, "description": description})
    return items


def _assumptions(value: object, bag: ErrorBag) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        bag.add("assumptions は配列である必要があります。")
        return []
    items = []
    seen = set()
    for index, raw in enumerate(value):
        prefix = f"assumptions[{index}]"
        if not isinstance(raw, dict):
            bag.add(f"{prefix}: オブジェクトである必要があります。")
            continue
        item_id = _text(raw.get("id"), f"{prefix}.id", bag)
        statement = _text(raw.get("statement"), f"{prefix}.statement", bag, minimum=4)
        impact = _text(raw.get("impact"), f"{prefix}.impact", bag, minimum=1)
        if item_id in seen:
            bag.add(f"{prefix}.id: 重複しています。")
        if item_id:
            seen.add(item_id)
        if item_id and statement and impact:
            items.append({"id": item_id, "statement": statement, "impact": impact})
    return items


def _risks(value: object, bag: ErrorBag) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        bag.add("risks は配列である必要があります。")
        return []
    items = []
    seen = set()
    for index, raw in enumerate(value):
        prefix = f"risks[{index}]"
        if not isinstance(raw, dict):
            bag.add(f"{prefix}: オブジェクトである必要があります。")
            continue
        item_id = _text(raw.get("id"), f"{prefix}.id", bag)
        if item_id in seen:
            bag.add(f"{prefix}.id: 重複しています。")
        if item_id:
            seen.add(item_id)
        included = raw.get("already_in_three_point")
        if not isinstance(included, bool):
            bag.add(f"{prefix}.already_in_three_point: true または false です。")
            included = False
        description = _text(raw.get("description"), f"{prefix}.description", bag, minimum=4)
        trigger = _text(raw.get("trigger"), f"{prefix}.trigger", bag, minimum=2)
        impact_area = _text(raw.get("impact_area"), f"{prefix}.impact_area", bag, minimum=2)
        estimation_impact = _text(raw.get("estimation_impact"), f"{prefix}.estimation_impact", bag, minimum=4)
        response = _text(raw.get("response"), f"{prefix}.response", bag, minimum=2)
        if item_id and description and trigger and impact_area and estimation_impact and response:
            items.append(
                {
                    "id": item_id,
                    "description": description,
                    "trigger": trigger,
                    "impact_area": impact_area,
                    "estimation_impact": estimation_impact,
                    "response": response,
                    "already_in_three_point": included,
                }
            )
    return items


def _profile(value: object, required: bool, bag: ErrorBag) -> dict | None:
    if value is None:
        if required:
            bag.add("実績を照合するには comparison_profile が必要です。")
        return None
    if not isinstance(value, dict):
        bag.add("comparison_profile はオブジェクトである必要があります。")
        return None
    project_type = _text(value.get("project_type"), "comparison_profile.project_type", bag)
    project_scope = value.get("project_scope")
    if project_scope not in SCOPES:
        bag.add("comparison_profile.project_scope は new、enhancement、redevelopment、other のいずれかです。")
    technology = value.get("technology_stack")
    categories = value.get("work_categories")
    if not isinstance(technology, list) or not all(isinstance(item, str) for item in technology):
        bag.add("comparison_profile.technology_stack は文字列の配列です。")
        technology = []
    if not isinstance(categories, list) or not all(isinstance(item, str) for item in categories):
        bag.add("comparison_profile.work_categories は文字列の配列です。")
        categories = []
    return {
        "project_type": project_type or "",
        "project_scope": project_scope,
        "technology_stack": technology,
        "work_categories": categories,
    }


def _target_size(value: object, bag: ErrorBag) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        bag.add("target_size はオブジェクトである必要があります。")
        return None
    kind = _text(value.get("kind"), "target_size.kind", bag)
    try:
        number = optional_decimal(value.get("value"), "target_size.value")
    except EstimationError as exc:
        bag.errors.extend(exc.errors)
        return None
    if number is None or number <= 0:
        bag.add("target_size.value は0より大きい必要があります。")
        return None
    return {"kind": kind or "", "value": number, "value_exact": exact_str(number)}


def _contingency(value: object, effort_unit: str, risks: list[dict], bag: ErrorBag) -> dict:
    empty = {"effort_exact": "0", "effort_unit": effort_unit, "reason": "", "covered_risk_ids": []}
    if value is None:
        return empty
    if not isinstance(value, dict):
        bag.add("contingency はオブジェクトである必要があります。")
        return empty
    try:
        effort = optional_decimal(value.get("effort"), "contingency.effort")
    except EstimationError as exc:
        bag.errors.extend(exc.errors)
        return empty
    if effort is None or effort == 0:
        return empty
    if effort < 0:
        bag.add("contingency.effort は0以上である必要があります。")
        return empty
    if value.get("effort_unit", effort_unit) != effort_unit:
        bag.add("contingency.effort_unit は meta.effort_unit と一致させてください。")
    if value.get("independent_of_three_point") is not True:
        bag.add("三点見積もりと独立でない予備工数は加算できません。independent_of_three_point を確認してください。")
    reason = value.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 8:
        bag.add("contingency.reason に、三点見積もりへ含めなかった理由を書いてください。")
        reason = ""
    covered = value.get("covered_risk_ids")
    if not isinstance(covered, list) or not covered:
        bag.add("contingency.covered_risk_ids に、この予備が対応するリスクIDを指定してください。")
        covered = []
    risk_by_id = {risk["id"]: risk for risk in risks}
    for risk_id in covered:
        risk = risk_by_id.get(risk_id)
        if risk is None:
            bag.add(f"contingency.covered_risk_ids: 未知のリスクです（{risk_id}）。")
        elif risk["already_in_three_point"]:
            bag.add(f"{risk_id}: 三点見積もりに含めたリスクを予備工数へ重ねられません。")
    return {
        "effort_exact": exact_str(effort),
        "effort_unit": effort_unit,
        "reason": reason.strip() if isinstance(reason, str) else "",
        "covered_risk_ids": list(covered),
    }


def _select_method(
    override: object,
    evaluation: dict,
    wbs_summary: dict,
    historical: dict,
    contingency: dict,
) -> dict:
    if override not in (None, "cold-start", "historical"):
        raise EstimationError(["method_override は cold-start、historical、または null です。"])
    historical_ready = historical.get("status") == "calculated" and evaluation["can_be_primary"]
    cold_ready = wbs_summary.get("status") == "calculated"
    if override == "historical" and not historical_ready:
        raise EstimationError(
            [
                "method_override が historical ですが、類似実績による規模按分の条件を満たしません。"
                "件数、類似度、工程、規模指標、単位を確認してください。"
            ]
        )
    if override == "cold-start":
        primary = "cold-start"
        reason = "method_override により cold-start を主方式にしました。"
    elif override == "historical" or historical_ready:
        primary = "historical"
        reason = (
            f"類似し規模按分できる実績が {evaluation['usable_for_scaling_count']} 件あり、"
            f"方針の {HISTORICAL_PRIMARY_MIN_RECORDS} 件以上を満たすため historical を主方式にしました。"
        )
    elif evaluation["usable_for_scaling_count"] >= 1:
        primary = "cold-start"
        reason = (
            "利用できる実績はありますが、主方式に必要な件数または規模の対応が不足するため、"
            "cold-start を主方式とし、実績は補助参照にします。"
        )
    elif evaluation["similar_count"] >= 1:
        primary = "cold-start"
        reason = (
            "類似度の下限を満たす実績はありますが、project_scope、規模範囲、工程、単位など"
            "按分条件を満たさないため、cold-start を主方式にしました。"
        )
    else:
        primary = "cold-start"
        reason = "採用できる類似実績が無いため、cold-start を主方式にしました。"

    if primary == "historical" and Decimal(contingency["effort_exact"]) != 0:
        raise EstimationError(
            ["実績を主方式にする場合、WBS向け予備工数は加算しません。cold-start を主方式にするか、予備を外してください。"]
        )
    if primary == "historical":
        auxiliary = "cold-start" if cold_ready else "none"
    elif historical.get("status") == "calculated":
        auxiliary = "historical"
    else:
        auxiliary = "none"
    if primary == "cold-start" and not cold_ready and auxiliary != "historical":
        reason = "算定できるWBSが無く、主方式に使える実績もありません。"
    return {
        "primary": primary,
        "auxiliary": auxiliary,
        "reason": reason,
        "override": override is not None,
        "policy": {
            "similarity_threshold": exact_str(SIMILARITY_THRESHOLD),
            "minimum_records_for_historical_primary": HISTORICAL_PRIMARY_MIN_RECORDS,
            "minimum_category_jaccard_for_scaling": exact_str(CATEGORY_JACCARD_MIN),
            "maximum_size_extrapolation_factor": exact_str(MAX_SIZE_EXTRAPOLATION_FACTOR),
            "similarity_weights": {key: exact_str(value) for key, value in SIMILARITY_WEIGHTS.items()},
            "note": POLICY_NOTE,
        },
    }


def _primary_summary(method: dict, wbs_summary: dict, historical: dict, contingency: dict, effort_unit: str) -> dict:
    if method["primary"] == "historical" and historical.get("status") == "calculated":
        source = historical
        planned = Decimal(source["expected_exact"])
        difference_reason = ""
        return _summary_dict(
            status="calculated",
            reason="主方式は類似実績の規模按分です。WBS合計は加算していません。",
            effort_unit=effort_unit,
            optimistic=Decimal(source["optimistic_exact"]),
            most_likely=Decimal(source["most_likely_exact"]),
            pessimistic=Decimal(source["pessimistic_exact"]),
            expected=Decimal(source["expected_exact"]),
            contingency=Decimal(0),
            planned=planned,
            difference_reason=difference_reason,
            primary_basis="HISTORICAL",
        )
    if wbs_summary.get("status") != "calculated":
        return {
            "status": "not_calculated",
            "reason": wbs_summary.get("reason") or "計画工数を計算できません。",
            "effort_unit": effort_unit,
            "planned_exact": None,
        }
    expected = Decimal(wbs_summary["expected_exact"])
    reserve = Decimal(contingency["effort_exact"]) if method["primary"] == "cold-start" else Decimal(0)
    planned = expected + reserve
    difference_reason = ""
    if reserve != 0:
        difference_reason = "三点見積もりに含めなかったリスクの予備工数を、独立項目として計画工数へ加算しました。 " + contingency["reason"]
    return _summary_dict(
        status="calculated",
        reason="主方式はWBSの三点見積もりです。補助の実績見積もりは加算していません。",
        effort_unit=effort_unit,
        optimistic=Decimal(wbs_summary["optimistic_exact"]),
        most_likely=Decimal(wbs_summary["most_likely_exact"]),
        pessimistic=Decimal(wbs_summary["pessimistic_exact"]),
        expected=expected,
        contingency=reserve,
        planned=planned,
        difference_reason=difference_reason,
        primary_basis=wbs_summary["primary_basis"],
    )


def _estimate_coverage(scope: dict, wbs_summary: dict, method: dict, historical: dict, source_review: dict) -> dict:
    """WBS coverage is required for cold-start; historical estimates cover the project independently."""
    requirements = scope["functions"] + scope["non_functional"]
    required_ids = [item["id"] for item in requirements]
    lines = wbs_summary.get("lines", [])
    required_set = set(required_ids)
    mapped: set[str] = set()
    estimated: set[str] = set()
    unestimated_ids: list[str] = []
    unscoped_unestimated_ids: list[str] = []
    for item in lines:
        linked = {req for req in item["requirement_ids"] if req in required_set}
        mapped.update(linked)
        if item["estimable"]:
            estimated.update(linked)
        else:
            unestimated_ids.append(item["id"])
            if not linked:
                unscoped_unestimated_ids.append(item["id"])
    uncovered = [req for req in required_ids if req not in mapped]
    unestimated_requirements = [req for req in required_ids if req in mapped and req not in estimated]
    mapped_ids = [req for req in required_ids if req in mapped]
    estimated_ids = [req for req in required_ids if req in estimated]
    if not lines:
        wbs_status = "not_provided"
    elif not uncovered and not unestimated_ids and wbs_summary.get("status") == "calculated":
        wbs_status = "complete"
    else:
        wbs_status = "partial"

    historical_primary = method["primary"] == "historical" and historical.get("status") == "calculated"
    if historical_primary:
        status = "historical_project_estimate"
        is_total = True
        note = "主方式は案件全体を対象にするhistorical見積もりです。WBSは照合用で、WBS網羅性は主見積もりを制限しません。"
        basis = "historical"
    elif wbs_status == "complete":
        status = "complete"
        is_total = True
        note = "機能要件・非機能要件が算定可能なWBSに対応し、未算定WBSもありません。"
        basis = "wbs"
    elif lines or required_ids:
        status = "partial"
        is_total = False
        note = "WBSの網羅性が不完全です。計画工数は算定済み項目だけの部分見積もりです。"
        basis = "wbs"
    else:
        status = "not_assessed"
        is_total = False
        note = "要件とWBSがないため、見積もり範囲の網羅性を評価できません。"
        basis = "wbs"
    if source_review["status"] == "incomplete":
        status = "partial"
        is_total = False
        note = "重要資料の未読・未解決事項があるため、算定済み工数は部分見積もりとして扱います。"
    return {
        "status": status,
        "basis": basis,
        "is_total_estimate": is_total,
        "source_review_status": source_review["status"],
        "source_review_blockers": source_review["blockers"],
        "wbs_status": wbs_status,
        "required_requirement_ids": required_ids,
        "mapped_requirement_ids": mapped_ids,
        "estimated_requirement_ids": estimated_ids,
        "uncovered_requirement_ids": uncovered,
        "unestimated_requirement_ids": unestimated_requirements,
        "unestimated_wbs_ids": unestimated_ids,
        "unscoped_unestimated_wbs_ids": unscoped_unestimated_ids,
        "note": note,
    }


def _summary_dict(
    *,
    status: str,
    reason: str,
    effort_unit: str,
    optimistic: Decimal,
    most_likely: Decimal,
    pessimistic: Decimal,
    expected: Decimal,
    contingency: Decimal,
    planned: Decimal,
    difference_reason: str,
    primary_basis: str,
) -> dict:
    return {
        "status": status,
        "reason": reason,
        "effort_unit": effort_unit,
        "optimistic": effort_str(optimistic),
        "most_likely": effort_str(most_likely),
        "pessimistic": effort_str(pessimistic),
        "expected": effort_str(expected),
        "contingency": effort_str(contingency),
        "planned": effort_str(planned),
        "optimistic_exact": exact_str(optimistic),
        "most_likely_exact": exact_str(most_likely),
        "pessimistic_exact": exact_str(pessimistic),
        "expected_exact": exact_str(expected),
        "contingency_exact": exact_str(contingency),
        "planned_exact": exact_str(planned),
        "planned_differs_from_expected": planned != expected,
        "planned_difference_reason": difference_reason,
        "primary_basis": primary_basis,
        "rounding": {
            "mode": "ROUND_HALF_UP",
            "effort_places": 2,
            "money_places": 2,
            "note": "合計は丸める前の値を加算し、最後に一度だけ丸めます。",
        },
    }


def _warnings(
    wbs: list[dict],
    wbs_summary: dict,
    evaluation: dict,
    historical: dict,
    method: dict,
    assumptions: list[dict],
    risks: list[dict],
    contingency: dict,
    coverage: dict,
) -> list[str]:
    warnings = []
    if evaluation.get("fictional_records_present"):
        warnings.append("実績に架空データが含まれます。本番の見積根拠にしないでください。")
    if method["primary"] == "cold-start" and wbs_summary.get("primary_basis") in {"AI_ESTIMATE", "MIXED"}:
        warnings.append("主方式の工数にはAIによる暫定推定が含まれます。精度が高い見積もりではありません。")
    if historical.get("status") == "calculated" and historical.get("provisional"):
        warnings.append(historical["provisional_reason"])
    if coverage["status"] == "partial":
        details = []
        if coverage["uncovered_requirement_ids"]:
            details.append("WBS未対応要件: " + ", ".join(coverage["uncovered_requirement_ids"]))
        if coverage["unestimated_wbs_ids"]:
            details.append("未算定WBS: " + ", ".join(coverage["unestimated_wbs_ids"]))
        if coverage["source_review_blockers"]:
            details.append("資料未確認・未解決: " + ", ".join(coverage["source_review_blockers"]))
        suffix = "（" + "、".join(details) + "）" if details else ""
        warnings.append("網羅性が部分的です。工数は全体の確定値ではありません。費用・期間も算出していません。" + suffix)
    elif coverage["basis"] == "historical" and coverage["wbs_status"] != "complete":
        warnings.append("historical方式は案件全体の見積もりです。照合用WBSは未提示または不完全で、主方式の工数には加算していません。")
    if not assumptions and any(item.get("provisional") for item in wbs):
        warnings.append("暫定の工数がありますが、前提条件が空です。")
    for risk in risks:
        if risk["already_in_three_point"] is False and Decimal(contingency["effort_exact"]) == 0:
            warnings.append(
                f"{risk['id']} は三点見積もりに含まれていませんが、独立した予備工数もありません。"
            )
            break
    for item in wbs:
        for message in item.get("warnings", []):
            warnings.append(f"{item['id']}: {message}")
    if method["primary"] == "cold-start" and method["auxiliary"] == "historical":
        historical_ids = set()
        for item in wbs:
            if item.get("basis") and item["basis"]["kind"] == "HISTORICAL":
                historical_ids.update(item["basis"]["historical_record_ids"])
        used = set(historical.get("used_record_ids") or [])
        if historical_ids & used:
            warnings.append("同じ実績がWBS根拠と補助見積もりの両方に出ています。合計はWBSのみです。")
    return warnings


def _present(
    *,
    meta: dict,
    scope: dict,
    assumptions: list[dict],
    risks: list[dict],
    source_review: dict,
    method: dict,
    evaluation: dict,
    benchmark: dict,
    wbs_summary: dict,
    historical: dict,
    summary: dict,
    coverage: dict,
    cost: dict,
    schedule: dict,
    warnings: list[str],
    contingency: dict,
) -> dict:
    return {
        "schema_version": "1.0",
        "calculator_version": __version__,
        "meta": meta,
        "scope": scope,
        "assumptions": assumptions,
        "risks": risks,
        "source_review": source_review,
        "method": method,
        "history_evaluation": _public_history(evaluation),
        "historical_estimate": _public_historical(historical),
        "benchmark": _public_benchmark(benchmark),
        "wbs": _public_wbs(wbs_summary, cross_check_only=method["primary"] != "cold-start"),
        "contingency": {
            "effort": effort_str(Decimal(contingency["effort_exact"])),
            "effort_exact": contingency["effort_exact"],
            "effort_unit": contingency["effort_unit"],
            "reason": contingency["reason"],
            "covered_risk_ids": contingency["covered_risk_ids"],
        },
        "summary": summary,
        "coverage": coverage,
        "cost": _public_cost(cost),
        "schedule": _public_schedule(schedule),
        "warnings": warnings,
        "unestimated_items": [
            {"id": item["id"], "name": item["name"], "reason": item["blocked_reason"]}
            for item in wbs_summary.get("lines", [])
            if not item["estimable"]
        ],
    }


def _public_history(evaluation: dict) -> dict:
    records = []
    for item in evaluation["records"]:
        records.append(
            {
                "project_id": item["project_id"],
                "valid": item["valid"],
                "validity_issues": item["validity_issues"],
                "fictional": item["fictional"],
                "anomaly": item["anomaly"],
                "anomaly_reason": item["anomaly_reason"],
                "similarity": item["similarity"],
                "similarity_components": item["similarity_components"],
                "project_scope_match": item["project_scope_match"],
                "type_cap_applied": item["type_cap_applied"],
                "above_threshold": item["above_threshold"],
                "usable_for_scaling": item["usable_for_scaling"],
                "exclusion_reasons": item["exclusion_reasons"],
                "unit_rate": item["unit_rate"],
                "notes": item["notes"],
            }
        )
    return {
        "loaded_count": evaluation["loaded_count"],
        "valid_count": evaluation["valid_count"],
        "similar_count": evaluation["similar_count"],
        "usable_for_scaling_count": evaluation["usable_for_scaling_count"],
        "fictional_records_present": evaluation["fictional_records_present"],
        "can_be_primary": evaluation["can_be_primary"],
        "size_extrapolation": evaluation["size_extrapolation"],
        "records": records,
    }


def _public_historical(historical: dict) -> dict:
    if historical.get("status") != "calculated":
        return {
            "status": "not_calculated",
            "reason": historical.get("reason", ""),
            "used_record_ids": historical.get("used_record_ids", []),
            "effort_unit": historical.get("effort_unit"),
        }
    return {
        "status": "calculated",
        "reason": historical["reason"],
        "used_record_ids": historical["used_record_ids"],
        "size_kind": historical["size_kind"],
        "size_value": historical["size_value"],
        "unit_rates": historical["unit_rates"],
        "optimistic": effort_str(Decimal(historical["optimistic_exact"])),
        "most_likely": effort_str(Decimal(historical["most_likely_exact"])),
        "pessimistic": effort_str(Decimal(historical["pessimistic_exact"])),
        "expected": effort_str(Decimal(historical["expected_exact"])),
        "optimistic_exact": historical["optimistic_exact"],
        "most_likely_exact": historical["most_likely_exact"],
        "pessimistic_exact": historical["pessimistic_exact"],
        "expected_exact": historical["expected_exact"],
        "provisional": historical["provisional"],
        "provisional_reason": historical["provisional_reason"],
        "single_point": historical["single_point"],
        "effort_unit": historical["effort_unit"],
        "applied_note": "この値をWBSへ加算しません。主方式が historical のときだけ計画工数になります。",
    }


def _public_benchmark(benchmark: dict) -> dict:
    public = dict(benchmark)
    for key in ("optimistic_exact", "most_likely_exact", "pessimistic_exact"):
        if key in public:
            label = key.removesuffix("_exact")
            public[label] = effort_str(Decimal(public[key]))
    public["applied_to_plan"] = False
    return public


def _public_wbs(summary: dict, *, cross_check_only: bool) -> dict:
    lines = []
    for item in summary.get("lines", []):
        line = {
            "id": item["id"],
            "requirement_ids": item["requirement_ids"],
            "name": item["name"],
            "description": item["description"],
            "phase": item["phase"],
            "prerequisites": item["prerequisites"],
            "depends_on": item["depends_on"],
            "estimable": item["estimable"],
            "blocked_reason": item["blocked_reason"],
            "uncertainty": item["uncertainty"],
            "provisional": item["provisional"],
            "basis": item["basis"],
            "effort_unit": item["effort_unit"],
        }
        if item["estimable"]:
            line.update(
                {
                    "optimistic": effort_str(Decimal(item["optimistic_exact"])),
                    "most_likely": effort_str(Decimal(item["most_likely_exact"])),
                    "pessimistic": effort_str(Decimal(item["pessimistic_exact"])),
                    "expected": effort_str(Decimal(item["expected_exact"])),
                    "optimistic_exact": item["optimistic_exact"],
                    "most_likely_exact": item["most_likely_exact"],
                    "pessimistic_exact": item["pessimistic_exact"],
                    "expected_exact": item["expected_exact"],
                }
            )
        lines.append(line)
    public = {
        "status": summary["status"],
        "reason": summary.get("reason", ""),
        "effort_unit": summary["effort_unit"],
        "lines": lines,
        "cross_check_only": cross_check_only,
        "estimable_count": summary.get("estimable_count", 0),
        "unestimated_count": summary.get("unestimated_count", 0),
    }
    if summary["status"] == "calculated":
        public.update(
            {
                "optimistic": effort_str(Decimal(summary["optimistic_exact"])),
                "most_likely": effort_str(Decimal(summary["most_likely_exact"])),
                "pessimistic": effort_str(Decimal(summary["pessimistic_exact"])),
                "expected": effort_str(Decimal(summary["expected_exact"])),
                "optimistic_exact": summary["optimistic_exact"],
                "most_likely_exact": summary["most_likely_exact"],
                "pessimistic_exact": summary["pessimistic_exact"],
                "expected_exact": summary["expected_exact"],
                "primary_basis": summary["primary_basis"],
                "provenance_totals_exact": summary["provenance_totals"],
            }
        )
    return public


def _public_cost(cost: dict) -> dict:
    if cost.get("status") != "calculated":
        return {"status": "not_calculated", "reason": cost.get("reason", "")}
    return {
        "status": "calculated",
        "reason": cost["reason"],
        "currency": cost["currency"],
        "rate": money_str(Decimal(cost["rate"])),
        "rate_exact": cost["rate"],
        "rate_unit": cost["rate_unit"],
        "rate_basis": cost["rate_basis"],
        "labor": money_str(Decimal(cost["labor_exact"])),
        "labor_exact": cost["labor_exact"],
        "extra_costs": [
            {
                "name": item["name"],
                "amount": money_str(Decimal(item["amount_exact"])),
                "amount_exact": item["amount_exact"],
                "basis_kind": item["basis_kind"],
                "explanation": item["explanation"],
            }
            for item in cost["extra_costs"]
        ],
        "extra_total": money_str(Decimal(cost["extra_total_exact"])),
        "total": money_str(Decimal(cost["total_exact"])),
        "total_exact": cost["total_exact"],
        "conversion": cost["conversion"],
        "provisional": cost["provisional"],
    }


def _public_schedule(schedule: dict) -> dict:
    if schedule.get("status") == "not_calculated":
        return {
            "status": "not_calculated",
            "reason": schedule.get("reason", ""),
            "limitations": schedule.get("limitations", []),
        }
    elapsed = Decimal(schedule["elapsed_days_exact"])
    public = {
        "status": schedule["status"],
        "reason": schedule["reason"],
        "elapsed_days": effort_str(elapsed),
        "elapsed_days_exact": schedule["elapsed_days_exact"],
        "team_size": schedule["team_size"],
        "utilization": schedule["utilization"],
        "calendar_factor": schedule.get("calendar_factor"),
        "calendar_factor_basis": schedule.get("calendar_factor_basis"),
        "conversion": schedule.get("conversion"),
        "limitations": schedule["limitations"],
        "confirmed": False,
    }
    if schedule.get("lower_bound_days_exact"):
        public["lower_bound_days"] = effort_str(Decimal(schedule["lower_bound_days_exact"]))
        public["lower_bound_days_exact"] = schedule["lower_bound_days_exact"]
    return public


def _text(value: object, field: str, bag: ErrorBag, minimum: int = 1) -> str | None:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        bag.add(f"{field}: {minimum}文字以上の文字列が必要です。")
        return None
    return value.strip()


def _string_list(value: object, field: str, bag: ErrorBag) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        bag.add(f"{field}: 文字列の配列である必要があります。")
        return []
    return value
