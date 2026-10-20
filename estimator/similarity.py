"""説明可能な類似度。

重みは tool_policy であり、学習モデルや公的な係数ではない。
"""

from decimal import Decimal

from estimator.numbers import round_score, score_str
from estimator.policy import SIMILARITY_WEIGHTS, TYPE_MISMATCH_CAP


def normalize_token(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def normalize_tokens(values: list[str]) -> list[str]:
    tokens = []
    for value in values:
        token = normalize_token(value)
        if token:
            tokens.append(token)
    return tokens


def jaccard(left: list[str], right: list[str]) -> Decimal | None:
    """双方が空なら比較不能として None を返す。"""
    left_set = set(normalize_tokens(left))
    right_set = set(normalize_tokens(right))
    if not left_set and not right_set:
        return None
    if not left_set or not right_set:
        return Decimal(0)
    return Decimal(len(left_set & right_set)) / Decimal(len(left_set | right_set))


def score_similarity(profile: dict, record: dict) -> dict:
    """0から1の類似度と、内訳・頭打ちの有無を返す。"""
    components: dict[str, str] = {}
    notes: list[str] = []
    score = Decimal(0)

    type_match = _exact_match(profile.get("project_type", ""), record.get("project_type", ""))
    components["project_type"] = "1" if type_match else "0"
    if type_match:
        score += SIMILARITY_WEIGHTS["project_type"]
    else:
        notes.append("案件種別が一致しないため、類似度は0.40を超えません。")

    scope_match = _exact_match(profile.get("project_scope", ""), record.get("project_scope", ""))
    components["project_scope"] = "1" if scope_match else "0"
    if scope_match:
        score += SIMILARITY_WEIGHTS["project_scope"]
    else:
        notes.append("project_scope が一致しない実績は規模按分に使いません。")

    technology = jaccard(
        list(profile.get("technology_stack") or []),
        list(record.get("technology_stack") or []),
    )
    if technology is None:
        components["technology"] = "0"
        notes.append("技術スタックが双方とも空のため、技術の類似度は加点しません。")
    else:
        components["technology"] = score_str(technology)
        score += SIMILARITY_WEIGHTS["technology"] * technology

    categories = jaccard(
        list(profile.get("work_categories") or []),
        list(record.get("work_categories") or []),
    )
    if categories is None:
        components["work_categories"] = "0"
        notes.append("工程区分が双方とも空のため、工程の類似度は加点しません。")
        category_score = None
    else:
        components["work_categories"] = score_str(categories)
        score += SIMILARITY_WEIGHTS["work_categories"] * categories
        category_score = categories

    capped = False
    if not type_match and score > TYPE_MISMATCH_CAP:
        score = TYPE_MISMATCH_CAP
        capped = True
    elif not type_match:
        capped = True

    return {
        "similarity": score_str(round_score(score)),
        "similarity_exact": score_str(round_score(score)),
        "components": components,
        "category_jaccard": None if category_score is None else score_str(category_score),
        "project_scope_match": scope_match,
        "type_cap_applied": capped,
        "notes": notes,
    }


def _exact_match(left: str, right: str) -> bool:
    if not str(left).strip() or not str(right).strip():
        return False
    return normalize_token(str(left)) == normalize_token(str(right))
