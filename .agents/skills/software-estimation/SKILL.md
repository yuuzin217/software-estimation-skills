---
name: software-estimation
description: "要件資料フォルダ、要件定義、機能一覧、ユーザーストーリー、非機能要件から開発工数・費用・開発期間を見積もる入口。過去実績の有無と類似性を見て、cold-start-estimation か historical-estimation を主方式にする。資料フォルダを指定した見積もり、ソフトウェア見積もり、工数、費用、工期、WBSを求められたときに使う。数値は python -m estimator で計算し、暗算で置き換えない。"
license: MIT
compatibility: "Python 3.11以上の標準ライブラリだけで計算できる。リポジトリルートで python -m estimator を実行する。ネットワークは不要。"
metadata:
  author: datsuryoku
  version: "0.1.0"
---

# ソフトウェア見積もり

統合入口。要件の読み分けと方式選択を行い、数値はリポジトリの計算パッケージに渡す。

## 依存関係

手順はこのファイルだけでも追える。数値計算はリポジトリ全体の `estimator` が必要であり、このディレクトリだけをコピーしても計算は動かない。

正本は `.agents/skills/`。`.cursor/skills/` や `.codex/skills/` へコピーしない。

## 資料フォルダから見積もる（推奨）

ユーザーが要件定義書・設計書・画面一覧・API仕様などの**フォルダパスを指定した場合**、まず [references/folder-input.md](references/folder-input.md) に従う。エージェントが読み取り可能な範囲でフォルダを再帰的に調査し、要件と出典を整理して `request.json` を作り、既存の計算CLIで `estimate.json`、`estimate.md`、`wbs.csv` を生成する。

例：`software-estimation Skillで /path/to/project-docs を見積もって`。

- **ユーザーが手動でrequest.jsonを作る必要はない**。ただしエージェントがフォルダにアクセスできることが前提。
- PDF・Word・Excel・図表などは、エージェント環境で対応する読み取り機能がある場合にだけ内容を確認する。未読資料や矛盾を隠さない。
- 元資料は読み取り専用。生成物は既定でこのリポジトリの `.estimates/<フォルダ名>/` に保存し、Gitに含めない。
- 資料フォルダから作る `request.json` には `source_review` を必ず記録し、`--require-source-review` で検証する。重要資料が未読または重大な矛盾がある場合は `incomplete` として、historical方式でも対象全体の工数・費用・期間として扱わない。
- **計算CLIはフォルダパスを直接受け取らない**。フォルダ調査とJSON作成はエージェント、検証と数値計算はPythonの役割である。

## 手順

1. Markdownまたはテキストの要件を読む。PDFやWordは、いま使っているエージェントの既存機能でテキスト化する。独自の文書パーサーは作らない。
2. 対象、機能、非機能、対象外、未確定、前提に分ける。cold-startでは全要件がWBSに対応しているか確認し、未算定作業や対応漏れがあれば部分見積もりとして明示する。
3. 過去実績が無い、またはCSV/JSONが無い場合は [cold-start-estimation](../cold-start-estimation/SKILL.md) に従いWBSを作る。
4. 実績がある場合は [historical-estimation](../historical-estimation/SKILL.md) に従い、品質と類似性を依頼JSONへ書く。類似性が低い実績を補正して採用しない。
5. `assets/request.minimal.json` を土台に依頼JSONを作る。工数は整数か十進文字列にする。`1.5` のようなJSON数値は拒否される。
6. リポジトリルートで計算する。

```bash
python -m estimator calculate --input request.json --json-output estimate.json --output estimate.md --csv-output wbs.csv
```

7. 終了コードが0のときだけ、出力Markdownの数値を結果にする。終了コードが2のときはメッセージを直して再実行する。手計算で数値を置き換えない。
8. スクリプトが選んだ `method.primary` を方式として説明する。理由を省かない。

## 方式

スクリプトの判定を採用する。閾値は外部標準ではない。

- 類似し、規模と工程が対応する実績が3件以上: 主方式 `historical`。WBSがあっても合計には加算しない。
- 実績が少ない、または規模が対応しない: 主方式 `cold-start`。実績は補助。
- 類似度が下限未満: `cold-start`。その実績は数値に使わない。

`method_override` は、条件を満たさない historical への上書きをスクリプトが拒否する。

## 出力

JSONを正本とし、MarkdownとCSVは同じ計算結果から作る。利用者向けの本文はスクリプトのMarkdownを使う。要約しても、楽観・最頻・悲観・期待・計画・費用・期間の数値はJSONと一致させる。

`coverage.status` が `partial` のcold-startは部分見積もりである。計画工数を対象全体の値として扱わず、対象全体の費用・期間を出さない。historical方式では案件全体を実績から見積もり、WBSは照合用なので、WBSの網羅性で主見積もりを制限しない。

費用は単価があるときだけ、期間は人数と稼働率があるときだけ出す。期間を確定値と呼ばない。

## 禁止

- IPAやSIerの保証値であるように書くこと
- 根拠のない生産性、リスク係数、人日換算（8時間や160時間）を補うこと
- 単価が無いのに費用を出すこと
- 工数÷人数だけを確定期間にすること
- 三点見積もりの幅と予備工数を同じ不確実性へ重ねること
- PERT期待値や悲観値を信頼区間として説明すること
- 補助見積もりを主方式の合計へ足すこと

## 詳細

条件分岐の正本は [references/routing.md](references/routing.md)。計算規則の正本は [references/calculation-rules.md](references/calculation-rules.md)。
