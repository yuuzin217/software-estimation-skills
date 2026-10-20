"""ソフトウェア開発見積もりの決定的な計算パッケージ。

LLMの暗算に依存せず、同じ入力から同じ工数・費用・期間を返す。
"""

from estimator.engine import calculate
from estimator.version import __version__

__all__ = ["__version__", "calculate"]
