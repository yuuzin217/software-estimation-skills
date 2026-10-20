# 実績データの品質

## JSON

```json
{
  "fictional": false,
  "records": [
    {
      "project_id": "P-001",
      "project_type": "new_web_app",
      "project_scope": "new",
      "technology_stack": ["python", "fastapi"],
      "work_categories": ["implementation", "test"],
      "estimated_effort": "10",
      "actual_effort": "12",
      "effort_unit": "person_day",
      "hours_per_person_day": null,
      "team_size": "3",
      "duration": "20",
      "duration_unit": "calendar_day",
      "completion_date": "2024-03-31",
      "size": {"kind": "feature_count", "value": "4"},
      "fictional": false,
      "notes": ""
    }
  ]
}
```

`project_scope` は `new`、`enhancement`、`redevelopment`、`other`。`effort_unit` は `person_day` または `person_hour`。期間は参考情報であり、工数の計算には使わない。

## CSV

ヘッダーは次を含む。

```text
project_id,project_type,technology_stack,project_scope,work_category,estimated_effort,actual_effort,effort_unit,hours_per_person_day,team_size,duration,duration_unit,completion_date,size_kind,size_value,fictional,notes
```

技術と工程は `|` 区切り。カンマを含む値はJSONを使う。

## 検証で落とすもの

- `project_id` の重複
- 実績工数が無い、0以下、数値でない
- 単位が人日でも人時でもない
- 見積工数と実績工数の単位がレコード内で違う
- 日付が `YYYY-MM-DD` でない

無効なレコードは按分に使わない。ファイル全体が壊れているときは計算を中止する。

## 異常値

実績÷見積が5以上、または0.2未満のレコードは異常値としてフラグを立て、既定では按分から外す。これは本ツールのルールであり、IPAが外れ値を恣意的に除外しないと説明している方針とは別である。`include_anomalies: true` のときだけ数値に戻せる。その場合も出力で分かるようにする。

## 架空データ

`fictional: true` のレコードは、依頼側の `allow_fictional: true` が無い限り使わない。見本ファイルは架空である。
