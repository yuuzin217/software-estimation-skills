"""費用と開発期間。条件が揃わないときは算定しない。"""

from decimal import Decimal

from estimator.errors import EstimationError
from estimator.numbers import exact_str, parse_decimal

RATE_UNITS = {"per_person_day": "person_day", "per_person_hour": "person_hour"}


def calculate_cost(cost: dict | None, planned_exact: str | None, effort_unit: str, hours: Decimal | None) -> dict:
    if planned_exact is None:
        return {"status": "not_calculated", "reason": "計画工数が無いため費用を計算しません。"}
    if cost is None:
        return {"status": "not_calculated", "reason": "人日単価または人時単価が指定されていません。"}
    rate_value = cost.get("rate")
    if rate_value is None:
        if cost.get("extra_costs"):
            return {
                "status": "not_calculated",
                "reason": "単価が無いため労務費を計算しません。経費だけを開発費として扱いません。",
            }
        return {"status": "not_calculated", "reason": "単価が指定されていません。工数のみを出力します。"}

    rate_unit = cost.get("rate_unit")
    if rate_unit not in RATE_UNITS:
        raise EstimationError(["cost.rate_unit は per_person_day または per_person_hour です。"])
    basis = cost.get("rate_basis")
    if not isinstance(basis, dict):
        raise EstimationError(["cost.rate_basis が必要です。単価を根拠なく決めないでください。"])
    kind = basis.get("kind")
    if kind == "AI_ESTIMATE":
        raise EstimationError(["単価を AI_ESTIMATE で埋めないでください。不明なら費用は算定しません。"])
    if kind not in {"ASSUMPTION", "SOURCE"}:
        raise EstimationError(["cost.rate_basis.kind は ASSUMPTION または SOURCE です。"])
    explanation = basis.get("explanation")
    if not isinstance(explanation, str) or len(explanation.strip()) < 8:
        raise EstimationError(["cost.rate_basis.explanation を8文字以上で書いてください。"])
    if kind == "SOURCE":
        citation = basis.get("citation")
        if not isinstance(citation, dict) or not str(citation.get("url", "")).startswith("https://"):
            raise EstimationError(["単価を SOURCE にする場合は citation.url が必要です。"])

    rate = parse_decimal(rate_value, "cost.rate")
    if rate < 0:
        raise EstimationError(["cost.rate は0以上である必要があります。"])
    currency = cost.get("currency")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
        raise EstimationError(["cost.currency は ISO 4217 の3文字（例: JPY）で指定してください。"])

    effort_in_rate_unit, conversion = _effort_for_rate(
        Decimal(planned_exact), effort_unit, RATE_UNITS[rate_unit], hours
    )
    if effort_in_rate_unit is None:
        return {
            "status": "not_calculated",
            "reason": "工数単位と単価単位が異なり、hours_per_person_day が無いため換算しません。",
        }
    labor = effort_in_rate_unit * rate
    extras, extra_total = _extras(cost.get("extra_costs") or [])
    total = labor + extra_total
    return {
        "status": "calculated",
        "reason": "開発費用 = 計画工数 × 単価。経費は別行です。",
        "currency": currency,
        "rate": exact_str(rate),
        "rate_unit": rate_unit,
        "rate_basis": {"kind": kind, "explanation": explanation.strip()},
        "labor_exact": exact_str(labor),
        "extra_costs": extras,
        "extra_total_exact": exact_str(extra_total),
        "total_exact": exact_str(total),
        "conversion": conversion,
        "provisional": kind == "ASSUMPTION",
    }


def calculate_schedule(schedule: dict | None, planned_exact: str | None, effort_unit: str, hours: Decimal | None) -> dict:
    limitations = [
        "タスク依存を考慮したクリティカルパスではありません。",
        "レビュー待ちや外部回答待ちを含みません。",
        "非稼働日は calendar_factor を指定した場合だけ、その仮定として含みます。",
        "確定した開発期間ではありません。",
    ]
    if planned_exact is None:
        return {"status": "not_calculated", "reason": "計画工数が無いため期間を計算しません。", "limitations": limitations}
    if schedule is None or (schedule.get("team_size") is None and schedule.get("utilization") is None):
        return {
            "status": "not_calculated",
            "reason": "稼働人数または稼働率が指定されていません。工数÷人数の確定期間は出しません。",
            "limitations": limitations,
        }
    if schedule.get("team_size") is None or schedule.get("utilization") is None:
        raise EstimationError(["schedule.team_size と schedule.utilization は両方指定してください。片方だけでは期間にしません。"])
    if schedule.get("calendar_factor") is not None and schedule.get("team_size") is None:
        raise EstimationError(["期間係数だけが指定されています。"])

    team_size = parse_decimal(schedule.get("team_size"), "schedule.team_size")
    utilization = parse_decimal(schedule.get("utilization"), "schedule.utilization")
    if team_size <= 0:
        raise EstimationError(["schedule.team_size は0より大きい必要があります。"])
    if not (Decimal(0) < utilization <= Decimal(1)):
        raise EstimationError(["schedule.utilization は0より大きく1以下である必要があります。"])

    person_days, conversion = _to_person_days(Decimal(planned_exact), effort_unit, hours)
    if person_days is None:
        return {
            "status": "not_calculated",
            "reason": "人時を人日にする hours_per_person_day が無いため、期間を計算しません。",
            "limitations": limitations,
        }
    lower_bound = person_days / (team_size * utilization)
    factor = schedule.get("calendar_factor")
    if factor is None:
        return {
            "status": "provisional_lower_bound",
            "reason": "人数と稼働率だけから求めた経過日数の下限です。確定期間ではありません。",
            "elapsed_days_exact": exact_str(lower_bound),
            "team_size": exact_str(team_size),
            "utilization": exact_str(utilization),
            "calendar_factor": None,
            "conversion": conversion,
            "limitations": limitations,
        }
    factor_number = parse_decimal(factor, "schedule.calendar_factor")
    if factor_number < 1:
        raise EstimationError(["schedule.calendar_factor は1以上にしてください。期間を縮める係数は使いません。"])
    basis = schedule.get("calendar_factor_basis")
    if not isinstance(basis, str) or len(basis.strip()) < 8:
        raise EstimationError(["schedule.calendar_factor_basis に、暦日係数の仮定を8文字以上で書いてください。"])
    elapsed = lower_bound * factor_number
    return {
        "status": "provisional_with_calendar_factor",
        "reason": "下限日数に、指定された暦日係数を掛けた暫定値です。確定期間ではありません。",
        "lower_bound_days_exact": exact_str(lower_bound),
        "elapsed_days_exact": exact_str(elapsed),
        "team_size": exact_str(team_size),
        "utilization": exact_str(utilization),
        "calendar_factor": exact_str(factor_number),
        "calendar_factor_basis": {"kind": "ASSUMPTION", "explanation": basis.strip()},
        "conversion": conversion,
        "limitations": limitations,
    }


def _extras(items: object) -> tuple[list[dict], Decimal]:
    if not isinstance(items, list):
        raise EstimationError(["cost.extra_costs は配列である必要があります。"])
    extras = []
    total = Decimal(0)
    for index, raw in enumerate(items):
        prefix = f"cost.extra_costs[{index}]"
        if not isinstance(raw, dict):
            raise EstimationError([f"{prefix}: オブジェクトである必要があります。"])
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise EstimationError([f"{prefix}.name: 必須です。"])
        amount = parse_decimal(raw.get("amount"), f"{prefix}.amount")
        if amount < 0:
            raise EstimationError([f"{prefix}.amount: 0以上である必要があります。"])
        kind = raw.get("basis_kind")
        if kind not in {"ASSUMPTION", "SOURCE", "HISTORICAL"}:
            raise EstimationError([f"{prefix}.basis_kind: ASSUMPTION、SOURCE、HISTORICAL のいずれかです。"])
        explanation = raw.get("explanation")
        if not isinstance(explanation, str) or len(explanation.strip()) < 8:
            raise EstimationError([f"{prefix}.explanation: 8文字以上で書いてください。"])
        extras.append(
            {
                "name": name.strip(),
                "amount_exact": exact_str(amount),
                "basis_kind": kind,
                "explanation": explanation.strip(),
            }
        )
        total += amount
    return extras, total


def _effort_for_rate(
    planned: Decimal, effort_unit: str, rate_effort_unit: str, hours: Decimal | None
) -> tuple[Decimal | None, str | None]:
    if effort_unit == rate_effort_unit:
        return planned, None
    converted = _convert(planned, effort_unit, rate_effort_unit, hours)
    if converted is None:
        return None, None
    return converted, f"{effort_unit} を hours_per_person_day={exact_str(hours)} で {rate_effort_unit} に換算しました。"


def _to_person_days(planned: Decimal, effort_unit: str, hours: Decimal | None) -> tuple[Decimal | None, str | None]:
    if effort_unit == "person_day":
        return planned, None
    if hours is None:
        return None, None
    return planned / hours, f"人時を hours_per_person_day={exact_str(hours)} で人日に換算しました。"


def _convert(effort: Decimal, from_unit: str, to_unit: str, hours: Decimal | None) -> Decimal | None:
    if hours is None:
        return None
    if from_unit == "person_hour" and to_unit == "person_day":
        return effort / hours
    if from_unit == "person_day" and to_unit == "person_hour":
        return effort * hours
    return None
