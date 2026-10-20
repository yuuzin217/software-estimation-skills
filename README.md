# software-estimation-skills

**言語 / Language:** **日本語** | [English](README.en.md)

ソフトウェア開発の要件から、工数・費用・開発期間を分けて見積もるための Agent Skills です。過去の開発実績が無い段階でも、WBSと明示した仮定から見積もりを作れます。実績が増えたあとは、同じ入口のまま類似案件の実績を主方式に切り替えられます。

計算は Python 標準ライブラリの十進演算で行います。LLMは要件の分解と三点の起草を担当し、楽観値・最頻値・悲観値・期待値・費用・期間の計算はスクリプトが検証します。

## 目的

見積もりの数値について、次が後から追えるようにします。

- どの要件の、どの作業か
- 楽観・最頻・悲観のどれから期待値を計算したか
- 公開資料、実績、仮定、AIの暫定推定のどれに基づくか
- 費用と期間を計算したか、条件不足で計算しなかったか

## 解決する課題

実績が無い案件では、根拠の見えない標準工数やリスク係数が入りやすい一方、公開統計を条件の違う案件へそのまま使うと、精度が高く見えてしまいます。このリポジトリは、幅と未算定を残したまま見積もりを出し、条件が合わない統計は計画工数へ入れません。

## Skill一覧

| Skill | 役割 |
| --- | --- |
| `software-estimation` | 入口。方式を選び、計算結果を見積もりとして出す |
| `cold-start-estimation` | 実績が無い、または類似性が低いときの WBS・三点見積もり |
| `historical-estimation` | CSV/JSONの実績を検証し、類似案件から規模按分する |

正本は `.agents/skills/` です。同じ `SKILL.md` を `.cursor/skills/` や `.codex/skills/` へ複製しません。Cursor と Codex は、この配置をそれぞれのドキュメントに従って読みます。

Skillの手順は各ディレクトリだけでも読めます。数値計算にはリポジトリ全体の `estimator` パッケージが必要です。

## 見積もり方式

1. 要件を機能、非機能、対象外、未確定、前提に分ける。
2. 必要な工程だけを WBS にする。全工程は必須ではない。
3. 各作業に楽観値 O、最頻値 M、悲観値 P を置く。
4. 期待値は `E = (O + 4M + P) / 6`。保証値ではなく、悲観値は信頼区間の上限でもない。
5. 実績が無いときは cold-start を主方式にする。
6. 類似し、工程と規模指標が対応する実績が3件以上あるときは historical を主方式にする。WBSと実績を合計しない。
7. 件数が足りない、または類似性が低いときは cold-start を主方式にし、実績は補助にする。類似しない実績は補正しない。
8. 公開統計は、開発種別・測定単位・工程範囲・母集団が一致するときだけ照合する。計画工数の置換には使わない。

3件、類似度0.60、工程の重なり0.50は、このツールの方針です。IPAやCoBRA法の規定ではありません。方式の背景は [docs/method.md](docs/method.md)、計算規則は [calculation-rules.md](.agents/skills/software-estimation/references/calculation-rules.md) にあります。

## インストール

Python 3.11以上が必要です。追加の実行時パッケージはありません。

```bash
git clone https://github.com/yuuzin217/software-estimation-skills.git
cd software-estimation-skills
python -m estimator --help
```

## 資料フォルダを指定して見積もる（おすすめ）

要件定義書や設計書を1つのフォルダにまとめておけば、**Codex／Cursorへフォルダパスだけを指定して**見積もりを依頼できます。ユーザーが計算用JSONを手動で書く必要はありません。

例えば、リポジトリをCodexで開いて次のように依頼します。

```text
software-estimation Skillを使って、
/Users/me/work/project-docs/ にある資料から工数を見積もってください。
資料は変更せず、見積もり結果と参照資料の一覧を出力してください。
```

このリポジトリだけで試す場合は、架空の資料フォルダ `examples/folder-input-demo/` を指定できます。

```text
software-estimation Skillで examples/folder-input-demo/ を見積もってください。
```

エージェントがフォルダ内の資料を再帰的に確認し、要件・非機能要件・不明点・根拠を整理して `request.json` を作成します。工数計算は従来どおりPythonが実行します。

既定の保存場所（指定資料フォルダは変更しません）：

```text
.estimates/<資料フォルダ名>/
├── request.json     # エージェントが作成した計算入力
├── sources.md       # 参照資料の一覧・確認状況・矛盾・未確認事項
├── estimate.json    # 正本
├── estimate.md      # レポート
└── wbs.csv          # WBS明細
```

`.estimates/` はGitから除外しています。既存の結果は、依頼がない限り上書きしません。**必要条件：** エージェントが指定フォルダを読み取れること、計算エンジンのあるこのリポジトリを利用できること。PDF・Word・Excel・図表の読み取りはエージェント環境の対応機能に依存し、未読資料は明示します。秘密情報を成果物に転記しません。

**重要：** `python -m estimator calculate --input /path/to/folder` は未対応です。フォルダ読取・要件抽出はCodex／Cursorが担当し、Pythonにはエージェントが生成した `request.json` を渡します。詳細は[資料フォルダ入力ワークフロー](.agents/skills/software-estimation/references/folder-input.md)を参照してください。

## Cursorでの利用方法

Cursorのドキュメントでは、プロジェクトの `.agents/skills/` にある `SKILL.md` を Agent Skills として検出し、チャットの `/` からSkill名を選べると説明されています。このリポジトリはその配置です。

利用時は、要件のMarkdownまたはテキストとともに、見積もりを依頼します。PDFやWordは、Cursor側の既存機能でテキスト化します。独自の文書パーサーはありません。

例:

```text
examples/case-e-missing-rate/request.json の入力を、software-estimation の手順で見積もってください。
```

エージェントは依頼JSONを作り、リポジトリルートで次を実行します。

```bash
python -m estimator calculate \
  --input request.json \
  --json-output estimate.json \
  --output estimate.md \
  --csv-output wbs.csv
```

終了コードが0の出力を結果にします。JSONを正本とし、その計算結果からMarkdownとCSVを生成します。

この作業環境では、Cursorの画面上でSkillが一覧に出ることまでは確認していません。確認したのは、公式の `skills-ref` 0.1.1 による frontmatter 検証と、上記コマンドによる計算です。

## Codexでの利用方法

Codexのドキュメントでは、リポジトリ内の `.agents/skills` をSkillとして読みます。配置はそれに合わせています。Codexの画面上での起動は、この作業では未確認です。

計算コマンドはCursorと同じです。ネットワークと追加パッケージは不要です。

## 入力例

最小の書式は `.agents/skills/software-estimation/assets/request.minimal.json` です。案件の例は `examples/` にあります。

| 例 | 内容 |
| --- | --- |
| `examples/case-a-new-web` | 実績がない新規Web。統計の条件が合わず照合しない |
| `examples/case-b-similar-history` | 類似する架空実績が3件。実績を主方式にする |
| `examples/case-c-ambiguous` | 要件が曖昧。未算定を残し、部分見積もりとして示す |
| `examples/case-d-dissimilar-history` | 実績はあるが種別が違う。按分しない |
| `examples/case-e-missing-rate` | 単価と人数が不明。工数だけ出す |
| `examples/case-f-non-functional` | 非機能を独立項目にし、予備を三点と分離する |
| `examples/case-g-enhancement` | 既存システムの改修。影響調査と回帰テストを含む |

各ディレクトリの `scenario.md` に、入力、期待結果、検証観点を書いてあります。実績の書式見本は `.agents/skills/historical-estimation/assets/` にあり、架空データです。本番の見積もりには使わないでください。

単価と人数が不明な入力の抜粋:

```json
{
  "meta": {
    "system_name": "既存APIへの項目追加",
    "effort_unit": "person_day"
  },
  "wbs": [
    {
      "id": "WBS-001",
      "optimistic": "1",
      "most_likely": "2",
      "pessimistic": "4",
      "basis": {"kind": "AI_ESTIMATE", "explanation": "既存項目の追加パターンに似せた暫定幅である"}
    }
  ]
}
```

工数は整数か十進文字列で指定します。JSONの浮動小数は拒否します。完全な入力は `examples/case-e-missing-rate/request.json` です。

## 出力例

ケースEの計算結果は、計画工数 2.17 人日、費用は未算定、開発期間は未算定です。単価と人数が無いため、費用と期間は作りません。全文は [examples/case-e-missing-rate/estimate.md](examples/case-e-missing-rate/estimate.md) です。

ケースAは、実績が無い新規Webの例です。計画工数は 27.17 人日、指定単価 80,000 円での費用は 2,173,333.33 円、人数2・稼働率0.6から求めた経過日数の下限は 22.64 日です。この日数は確定期間ではありません。費用は、表示上の 27.17 人日ではなく、丸める前の計画工数に単価を掛けてから丸めています。三点の人日は AI の暫定推定であり、標準生産性でもIPAの値でもありません。全文は [examples/case-a-new-web/estimate.md](examples/case-a-new-web/estimate.md) です。

機械可読な結果は、各例の `estimate.json` です。JSONには、対象範囲、前提、要件、WBS、O/M/P、PERT期待値、丸め前と表示用の計画工数、網羅性、未算定項目、リスク、費用、期間、方式、実績の採否を含めます。MarkdownとCSVはこの構造化結果を表示するだけで、工数を再計算しません。

### 出力ファイル

- `estimate.json`: 見積もりデータの正本。`*_exact` は丸め前、表示用の値は最後に小数第2位へ丸めます。
- `estimate.md`: 概要、対象範囲、前提、網羅性、WBS、工数、費用、期間、リスク、根拠、未算定項目、再見積もり条件を含むレポートです。
- `wbs.csv`: WBS ID、要件ID、工程、作業名・内容、O/M/P/PERT、単位、算定状態、根拠、不確実性、採用区分を含みます。工数はJSONと同じ表示値です。未算定工数は空欄で、理由を別列に記録します。

CSVの列:

| 列 | 内容 |
| --- | --- |
| WBS ID / 要件ID | 作業IDと対応要件ID |
| 工程 / 作業名 / 作業内容 | WBSの分類と明細 |
| 楽観工数 / 最頻工数 / 悲観工数 / 期待工数 | JSONと同じ表示用工数 |
| 工数単位 / 算定状態 | `person_day` または `person_hour`、算定済みまたは未算定 |
| 根拠区分 / 算定根拠 / 不確実性 | 根拠の種類、説明、low・medium・high |
| 採用区分 / 未算定理由 | 計画工数対象または照合用、未算定の場合の理由 |

CSVはUTF-8（BOM付き）です。Excelで直接開くと日本語が読みやすくなります。CSVのクォートはカンマ、引用符、改行を保つための書式で、数式の実行防止とは別です。ユーザー由来の文字列は、先頭の空白・制御文字を除いて `=`, `+`, `-`, `@` で始まる場合に先頭へアポストロフィを付け、Excelが数式として解釈しないようにします。

出力先には依頼JSONや `history.path` の実績ファイルを指定できません。相対パスやシンボリックリンクを解決して同じファイルを指す場合も上書きを拒否します。

WBSを積み上げるcold-start方式では、機能要件と非機能要件が算定可能なWBSに対応し、未算定WBSがない場合だけ全体見積もりになります。対応要件が抜けている、または未算定WBSがある場合、網羅性を `partial` とし、部分見積もり工数だけを表示します。対象全体の費用と期間は算出しません。historical方式は案件全体を対象にするため、WBSは照合用として扱い、網羅性の判定で主見積もりを狭めません。

実績による規模按分は、`project_scope` が一致することを必須にします。対象と各実績の規模を個別に比べ、どれか一件でも上下2倍を超える実績は除外します。採用可能な実績が3件未満になればhistoricalを主方式にせず、cold-startへ切り替えます。この2倍は本ツール独自の安全策で、IPAなどの公式基準ではありません。

## 見積もり根拠の扱い

各数値は次のどれかです。

| 区分 | 意味 |
| --- | --- |
| SOURCE | 検証できる外部資料 |
| HISTORICAL | 入力された開発実績 |
| ASSUMPTION | 明示した仮定 |
| AI_ESTIMATE | AIの暫定推定。確定値にはしない |

目録に無い値は SOURCE にしません。人日単価が無いときは費用を出しません。1人日の時間数は、変換が必要なときだけ入力し、8時間や160時間を補いません。

IPA『ソフトウェア開発分析データ集2022』のSLOC生産性とFP生産性は、開発5工程・測定単位・開発種別・規模帯が一致するときの照合幅です。計画工数へは加算も置換もしません。同書の回帰式は実装していません。引用した値、母集団、制約は [docs/references.md](docs/references.md) と `estimator/data/benchmarks.json` にあります。

## 制約事項

- 要件の分解と三点の幅は入力の判断です。スクリプトはその検証と集計を行い、自然文から工数を推定しません。
- PERT期待値は三点の加重平均であり、統計的な予測区間ではありません。
- 類似実績が10件未満の按分は暫定です。3件未満は主方式にしません。
- サンプルの実績は架空です。`allow_fictional` はデモ専用です。
- 顧客の機密や個人情報を実績ファイルとしてリポジトリへ追加しないでください。
- IPAの統計は、2016年度から2021年度を主な対象としたエンタプライズ系プロジェクトの集計です。現代の小規模クラウド開発やAI支援開発へ無条件には使いません。
- このリポジトリのライセンスはMITです。IPAおよびJISAの資料の著作権はそれぞれの権利者に残り、PDFは同梱していません。

## 参考資料

- [IPA ソフトウェア開発分析データ集2022](https://www.ipa.go.jp/digital/software-survey/metrics/metrics2022.html)
- [IPA ソフトウェア開発見積りガイドブック](https://www.ipa.go.jp/archive/publish/secbooks20060425.html)（書誌のみ。本文は転載していない）
- [IPA ソフトウェア改良開発見積りガイドブック](https://www.ipa.go.jp/archive/publish/secbooks20071025.html)（書誌のみ）
- [IPA CoBRA法に基づく見積り支援ツール](https://www.ipa.go.jp/archive/digital/tools/cobra.html)（手法は未実装。公開ページの件数の目安だけを設計メモで参照）
- [Agent Skills Specification](https://agentskills.io/specification)
- [Cursor Agent Skills](https://cursor.com/docs/skills)

出典、利用目的、適用条件、転載しなかった理由は [docs/references.md](docs/references.md) にまとめています。

## 開発・テスト方法

リポジトリルートで実行します。

```bash
python -m unittest discover -s tests -v
python -m estimator validate-skills
```

`validate-skills` は、`SKILL.md` の frontmatter、500行以内、参照先の実在を確認します。`skills-ref` がインストールされているときは、公式バリデータも続けて実行します。未インストールのときは、その公式検証をスキップします。

```bash
python -m pip install skills-ref==0.1.1
python -m estimator validate-skills
```

PR #1 の最新 GitHub Actions では単体テスト62件と、`skills-ref` 0.1.1 による公式検証が成功しています。Cursor／Codex上でのSkill起動は未確認です。GitHub Actions の設定は `.github/workflows/test.yml` にあります。

例の `estimate.md` と `estimate.json` は、依頼JSONから再計算した結果とテストで比較します。数値を手で直した場合、テストが失敗します。
