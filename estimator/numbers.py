"""十進数の読み取りと丸め。

浮動小数は受け付けない。合計は丸める前の値で行い、表示の直前に一度だけ丸める。
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from estimator.errors import EstimationError
from estimator.policy import EFFORT_PLACES, MONEY_PLACES, SCORE_PLACES


def parse_decimal(value: object, field: str) -> Decimal:
    """整数または十進文字列を Decimal にする。"""
    if isinstance(value, bool) or value is None:
        raise EstimationError([f"{field}: 数値として解釈できません。"])
    if isinstance(value, float):
        raise EstimationError(
            [f"{field}: 浮動小数は受け付けません。文字列の十進数で指定してください。"]
        )
    if isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if text == "":
            raise EstimationError([f"{field}: 空の数値です。"])
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise EstimationError([f"{field}: 数値として解釈できません（{text}）。"]) from exc
    else:
        raise EstimationError([f"{field}: 数値として解釈できません。"])
    if not number.is_finite():
        raise EstimationError([f"{field}: 有限の数値である必要があります。"])
    return number


def optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None or value == "":
        return None
    return parse_decimal(value, field)


def require_non_negative(number: Decimal, field: str) -> None:
    if number < 0:
        raise EstimationError([f"{field}: 0以上である必要があります。"])


def require_positive(number: Decimal, field: str) -> None:
    if number <= 0:
        raise EstimationError([f"{field}: 0より大きい必要があります。"])


def round_effort(number: Decimal) -> Decimal:
    return number.quantize(EFFORT_PLACES, rounding=ROUND_HALF_UP)


def round_money(number: Decimal) -> Decimal:
    return number.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def round_score(number: Decimal) -> Decimal:
    return number.quantize(SCORE_PLACES, rounding=ROUND_HALF_UP)


def exact_str(number: Decimal) -> str:
    return format(number, "f")


def effort_str(number: Decimal) -> str:
    return format(round_effort(number), "f")


def money_str(number: Decimal) -> str:
    return format(round_money(number), "f")


def score_str(number: Decimal) -> str:
    return format(round_score(number), "f")
