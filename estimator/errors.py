"""見積もり入力の検証エラー。"""


class EstimationError(Exception):
    """入力が計算条件を満たさないときに送出する。

    終了コード2に対応する。メッセージは利用者とエージェントが修正できる粒度にする。
    """

    def __init__(self, errors: list[str]):
        if not errors:
            errors = ["不明な検証エラー"]
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


class ErrorBag:
    """複数の検証エラーをまとめて返す。"""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def add(self, message: str) -> None:
        self.errors.append(message)

    def raise_if_any(self) -> None:
        if self.errors:
            raise EstimationError(self.errors)
