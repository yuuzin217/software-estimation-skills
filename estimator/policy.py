"""本ツール固有の判定方針。

これらの数値はIPAや他の公的機関が定めた基準ではない。
出力では常に tool_policy として説明し、SOURCE には分類しない。
"""

from decimal import Decimal

# 類似度の採用下限。種別が一致しない案件は TYPE_MISMATCH_CAP で頭打ちになる。
SIMILARITY_THRESHOLD = Decimal("0.60")
TYPE_MISMATCH_CAP = Decimal("0.40")

# 類似実績を主方式にできる最少件数。これを下回る場合は cold-start を主方式にする。
HISTORICAL_PRIMARY_MIN_RECORDS = 3

# 各実績と対象の規模比の上限。本ツール独自の安全策であり、公的基準ではない。
MAX_SIZE_EXTRAPOLATION_FACTOR = Decimal("2")

# 工程集合のJaccard係数がこの値未満の実績は、規模按分に使わない。
CATEGORY_JACCARD_MIN = Decimal("0.50")

# 実績が見積の5倍以上、または0.2倍未満なら異常値として既定では按分から外す。
ANOMALY_RATIO_HIGH = Decimal("5")
ANOMALY_RATIO_LOW = Decimal("0.2")

# この件数未満の按分結果は暫定とする。最小・最大は信頼区間ではない。
PROVISIONAL_BELOW_RECORDS = 10

# カタログ標本数がこの値未満なら、照合結果を計画工数に使わない参考値にする。
SMALL_SAMPLE_N = 30

SIMILARITY_WEIGHTS = {
    "project_type": Decimal("0.35"),
    "project_scope": Decimal("0.20"),
    "technology": Decimal("0.25"),
    "work_categories": Decimal("0.20"),
}

EFFORT_PLACES = Decimal("0.01")
MONEY_PLACES = Decimal("0.01")
SCORE_PLACES = Decimal("0.0001")

POLICY_NOTE = "これらは本ツールの方針であり、IPA等の公的基準ではない。"
