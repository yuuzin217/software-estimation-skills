"""公開ベンチマークとの照合。

条件が揃ったときだけ、人時の幅を参考として計算する。
WBSや実績見積もりの計画工数には加算も置換もしない。
"""

from decimal import Decimal

from estimator.catalog import SOURCE, find_entry
from estimator.errors import EstimationError
from estimator.numbers import exact_str, parse_decimal
from estimator.policy import SMALL_SAMPLE_N


def evaluate_benchmark(spec: dict | None) -> dict:
    if spec is None:
        return {"status": "not_requested", "reason": "外部ベンチマーク照合は依頼されていません。"}
    if not isinstance(spec, dict):
        raise EstimationError(["benchmark はオブジェクトである必要があります。"])
    catalog_id = spec.get("catalog_id")
    if not catalog_id:
        return {"status": "not_requested", "reason": "catalog_id が空のため照合しません。"}
    entry = find_entry(str(catalog_id))
    if entry is None:
        return {
            "status": "not_applied",
            "reason": f"目録に無い catalog_id です（{catalog_id}）。架空の標準値では補いません。",
            "catalog_id": catalog_id,
        }
    if not entry.get("calculable"):
        return {
            "status": "not_applied",
            "catalog_id": catalog_id,
            "reason": entry.get("not_calculable_reason") or "この項目は工数換算に使えません。",
            "source": _source(entry),
        }

    reasons = []
    development_type = spec.get("development_type")
    if development_type != entry.get("development_type"):
        reasons.append(
            "development_type が資料の層別と一致しません。"
            f"（依頼 {development_type}、資料 {entry.get('development_type')}）"
        )
    if spec.get("size_unit") != entry.get("size_unit"):
        reasons.append(
            "size_unit が資料の測定単位と一致しません。"
            f"（依頼 {spec.get('size_unit')}、資料 {entry.get('size_unit')}）"
        )
    phases = spec.get("confirmed_phases")
    if sorted(phases or []) != sorted(entry.get("phases") or []):
        reasons.append(
            "confirmed_phases が資料の開発5工程と一致しません。"
            "工程範囲が違う数値を係数で補正することはしません。"
        )
    if spec.get("acknowledge_population_limits") is not True:
        reasons.append("acknowledge_population_limits が true ではありません。母集団の限界を確認してください。")
    note = spec.get("population_note")
    if not isinstance(note, str) or len(note.strip()) < 20:
        reasons.append("population_note に、この母集団と比較する理由を20文字以上で書いてください。")

    if spec.get("target_size") is None:
        reasons.append("target_size が無いため、規模から工数へ換算しません。")
        size = None
    else:
        try:
            size = parse_decimal(spec.get("target_size"), "benchmark.target_size")
        except EstimationError as exc:
            reasons.extend(exc.errors)
            size = None
    if size is not None and size <= 0:
        reasons.append("benchmark.target_size は0より大きい必要があります。")
        size = None
    band = entry.get("size_band")
    if size is not None and isinstance(band, dict):
        minimum = Decimal(band["min_inclusive"])
        maximum = Decimal(band["max_exclusive"])
        if not (minimum <= size < maximum):
            reasons.append(
                f"規模 {exact_str(size)} は資料の規模帯 [{band['min_inclusive']}, {band['max_exclusive']}) に入りません。"
            )

    source = _source(entry)
    if reasons or size is None:
        return {
            "status": "not_applied",
            "catalog_id": catalog_id,
            "reason": "適合条件を満たさないため、工数へ換算しません。",
            "rejection_reasons": reasons,
            "source": source,
            "limitations": entry.get("limitations") or [],
        }

    p25 = Decimal(entry["p25"])
    median = Decimal(entry["median"])
    p75 = Decimal(entry["p75"])
    if min(p25, median, p75) <= 0:
        return {
            "status": "not_applied",
            "catalog_id": catalog_id,
            "reason": "生産性の分位に0以下が含まれ、工数へ除算できません。",
            "source": source,
        }
    # 生産性が高いほど工数は小さい。P75が楽観、P25が悲観。
    optimistic = size / p75
    most_likely = size / median
    pessimistic = size / p25
    small = bool(entry.get("small_sample")) or int(entry["n"]) < SMALL_SAMPLE_N
    status = "reference_only_small_sample" if small else "cross_check_only"
    return {
        "status": status,
        "catalog_id": catalog_id,
        "reason": (
            "公開資料のP25・中央・P75から人時の幅を照合しました。"
            "計画工数には加算も置換もしません。保証値ではありません。"
        ),
        "effort_unit": "person_hour",
        "optimistic_exact": exact_str(optimistic),
        "most_likely_exact": exact_str(most_likely),
        "pessimistic_exact": exact_str(pessimistic),
        "productivity": {"p25": entry["p25"], "median": entry["median"], "p75": entry["p75"], "unit": entry["metric"]},
        "n": entry["n"],
        "small_sample": small,
        "source": source,
        "limitations": entry.get("limitations") or [],
        "applied_to_plan": False,
    }


def _source(entry: dict) -> dict:
    return {
        "title": SOURCE["title"],
        "publisher": SOURCE["publisher"],
        "published": SOURCE["published"],
        "table": entry.get("table"),
        "url": SOURCE["url"],
        "landing_url": SOURCE["landing_url"],
        "period": entry.get("period"),
        "population": entry.get("population"),
        "n": entry.get("n"),
    }
