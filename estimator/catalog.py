"""外部ベンチマーク目録の読み込み。"""

import json
from functools import lru_cache
from pathlib import Path

from estimator.errors import EstimationError

CATALOG_PATH = Path(__file__).resolve().parent / "data" / "benchmarks.json"

SOURCE = {
    "title": "ソフトウェア開発分析データ集2022",
    "publisher": "独立行政法人情報処理推進機構（IPA）",
    "published": "2022-09-26",
    "updated": "2025-08-28",
    "url": "https://www.ipa.go.jp/digital/software-survey/metrics/hjuojm000000c6it-att/000102171.pdf",
    "landing_url": "https://www.ipa.go.jp/digital/software-survey/metrics/metrics2022.html",
}


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EstimationError([f"ベンチマーク目録を読めません: {exc}"]) from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise EstimationError(["ベンチマーク目録の形式が不正です。"])
    return data


def find_entry(catalog_id: str) -> dict | None:
    for entry in load_catalog()["entries"]:
        if entry.get("id") == catalog_id:
            return entry
    return None


def list_entries() -> list[dict]:
    return list(load_catalog()["entries"])
