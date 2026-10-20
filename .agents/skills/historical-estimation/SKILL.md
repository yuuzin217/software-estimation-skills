---
name: historical-estimation
description: "CSVまたはJSONの開発実績を検証し、類似案件の実績工数で見積もりを作るか補助する。件数が少なくても高度な統計モデルは使わない。類似性が低い実績は補正しない。実績がある見積もり、見積もりと実績の差分、実績の記録形式の確認に使う。"
license: MIT
compatibility: "Python 3.11以上の標準ライブラリだけで計算できる。リポジトリルートで python -m estimator を実行する。ネットワークは不要。"
metadata:
  author: datsuryoku
  version: "0.1.0"
---

# 実績を使う見積もり

開発実績があるときの品質確認と、類似案件による規模按分。実績が少ないことだけを理由に回帰や機械学習へ進まない。

## 依存関係

記録形式と採用条件はこのSkillで理解できる。計算はリポジトリ全体の `estimator` が必要である。規則の正本は [calculation-rules.md](../software-estimation/references/calculation-rules.md)。

実績が条件を満たさないときは [cold-start-estimation](../cold-start-estimation/SKILL.md) を主方式にする。

## 入力

CSVまたはJSON。必須は `project_id`、`actual_effort`、`effort_unit`。按分には加えて、案件種別、新規・改修の区分、技術、工程、同じ種類の規模が必要である。

形式は [references/data-quality.md](references/data-quality.md)。書式見本は [assets/history.sample.json](assets/history.sample.json) と [assets/history.sample.csv](assets/history.sample.csv)。見本は架空であり、見積もりの入力にしない。

個人情報、顧客名、機密の原価をリポジトリへ置かない。

## 手順

1. 実績ファイルを検証する。

```bash
python -m estimator validate-history --input history.json
```

2. 欠損、単位、0以下の工数、重複IDを直す。異常値（実績が見積の5倍以上または0.2倍未満）は既定で按分から外れる。外す理由を結果に残し、黙って削除したことにしない。
3. 人時と人日が混在する実績には、その実績自身の `hours_per_person_day` を書く。8時間や160時間を補わない。
4. 対象案件の `comparison_profile` と `target_size` を書く。`project_scope`（新規、改修など）の一致を必須とする。規模の種類が実績と違う場合は按分しない。
5. [references/similarity.md](references/similarity.md) の採用条件を満たすか確認する。満たさない実績を係数で寄せない。
6. 採用できる類似実績が3件未満、または規模按分できない場合は、WBSを [cold-start-estimation](../cold-start-estimation/SKILL.md) で作り、実績は補助にする。
   対象と各有効実績の規模比を個別に確認し、上下2倍を超える実績は除外する。除外後に3件未満となる場合はcold-startへ切り替える。この倍率は本ツール独自の方針で、公式基準ではない。
7. 3件以上が規模按分できる場合だけ historical を主方式にできる。WBSを併記してもよいが、合計へは足さない。
8. リポジトリルートで `python -m estimator calculate --input request.json --json-output estimate.json --output estimate.md --csv-output wbs.csv` を実行し、終了コード0の出力を結果にする。

historical方式は案件全体の見積もりであり、併記するWBSは照合用である。WBSが未算定または未網羅でも、historical主見積もりの工数・費用・期間は変えない。ただし照合用WBSの状態は結果に表示する。

## 完了後の記録

案件完了後は、見本と同じ列で1行追加できる。`fictional` は実データでは false。顧客や個人が識別できる値は入れない。

## 禁止

- 架空見本を `allow_fictional: true` のまま本番の根拠にすること。このフラグはデモンストレーション専用
- 種別が違う実績を、低い類似度のまま補正して採用すること
- 1件の実績から信頼区間を作ること。1件のときは幅が無く、暫定の一点として補助表示になる
- 10件未満の按分を確定値と呼ぶこと
