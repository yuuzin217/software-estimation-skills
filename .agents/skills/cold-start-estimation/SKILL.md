---
name: cold-start-estimation
description: "過去実績がない、または実績が少なく類似性が低いときに、WBS・ボトムアップ・三点見積もり・PERTで開発工数を見積もる。外部ベンチマークは工程・母集団・単位が合うときだけ照合する。実績なしの新規見積もり、曖昧な要件の幅見積もり、非機能要件を含む見積もりに使う。"
license: MIT
compatibility: "Python 3.11以上の標準ライブラリだけで計算できる。リポジトリルートで python -m estimator を実行する。ネットワークは不要。"
metadata:
  author: datsuryoku
  version: "0.1.0"
---

# 実績が無いときの見積もり

過去実績が無い案件の主方式。実績があっても、類似性が低い、件数が足りない、規模や工程が対応しないときは、このSkillを主方式にする。

## 依存関係

WBSの作り方はこのファイルと `references/` で完結する。数値の検証と集計はリポジトリ全体が必要である。計算規則の正本は [calculation-rules.md](../software-estimation/references/calculation-rules.md)。

入口が未実行なら、先に [software-estimation](../software-estimation/SKILL.md) の依頼JSON形式を使う。

## 手順

1. 機能、非機能、対象外、未確定、前提を分ける。
2. [references/wbs.md](references/wbs.md) の工程一覧から、本件に必要な作業だけを選ぶ。全工程を必須にしない。不要な工程は対象外へ理由とともに書く。
3. レビューできる粒度でWBSを作る。1機能をファイル単位まで割らない。目安は5〜30項目。40項目を超えそうなら粒度を戻す。
4. 各項目を要件IDへ結び付ける。横断作業は `UNSCOPED`。
5. [references/three-point.md](references/three-point.md) に従い O、M、P を置く。根拠が弱い項目は幅を広げ、`provisional: true` と `AI_ESTIMATE` にする。精密な一点にはしない。
6. 非機能、セキュリティ、移行、外部連携、テスト、レビュー、不具合修正、プロジェクト管理を、該当するものだけ独立項目にする。機能実装の中へ隠さない。
7. [references/uncertainty.md](references/uncertainty.md) の形でリスクを書く。一律の予備率は使わない。
8. [references/benchmark.md](references/benchmark.md) の条件を満たすときだけベンチマーク照合を依頼する。満たさなければ `benchmark` を空にするか、不一致のまま計算させて不採用理由を残す。架空の標準生産性で埋めない。
9. リポジトリルートで計算する。

```bash
python -m estimator calculate --input request.json --output estimate.md --json-output estimate.json
```

10. 終了コード0のMarkdownを結果にする。数値を暗算で修正しない。

## 算定不能

外部仕様が無い、受入条件が無いなど、幅さえ置けない作業は `estimable: false` と `blocked_reason` を付ける。残りの項目は計算する。重要な前提が欠けていることは、未確定事項として先頭に書く。

## 禁止

- 公開統計が無いことを理由に、標準人日や標準係数を作ること
- IPAの中央値を、小規模WebやAI支援開発の目標値にすること
- 管理工数や予備を、説明のないパーセントで足すこと。割合を使うときは利用者または実績が指定した値だけを `percent_of` にし、`ASSUMPTION` または `HISTORICAL` と説明を付ける
- 三点の悲観値に入れたリスクを予備へ重ねること
