# 開発エージェント向けの指示

このリポジトリは、ソフトウェア開発の工数・費用・期間を見積もる Agent Skills の正本です。利用者向けの導入は [README.md](README.md)、出典は [docs/references.md](docs/references.md)、手法の採否は [docs/method.md](docs/method.md) を参照してください。

## ディレクトリ

- `.agents/skills/`: Skillの正本。`software-estimation`、`cold-start-estimation`、`historical-estimation`
- `estimator/`: 検証と計算。Python標準ライブラリのみ
- `estimator/data/benchmarks.json`: 引用した外部統計の目録
- `examples/`: ケースAからGの入力、期待の説明、再計算した出力
- `tests/`: 計算、方式選択、Skill構成、サンプル出力の一致
- `docs/`: 出典と手法選定

同じ `SKILL.md` を別ディレクトリへコピーしないでください。

## Skillの変更

[Agent Skills Specification](https://agentskills.io/specification) に合わせます。

- `name` はディレクトリ名と一致し、小文字・数字・ハイフンだけを使う
- `description` は1024文字以内で、何をするSkillかと、いつ使うかを書く
- 公式 frontmatter 以外のキーを足さない。Cursor固有のキーは `skills-ref` が拒否する
- `SKILL.md` は500行以内。詳細は `references/`、雛形は `assets/`、実行は `scripts/`
- 参照リンクは実在する相対パスにする
- 計算式を変えたら `estimator` とテストを同じ変更で更新する。文書と実装が矛盾する場合は、テストされている実装を優先して文書を直す

## 工数と出典

- 人日と人時を混ぜない。換算には、その入力に書かれた `hours_per_person_day` だけを使う
- 単価が無い費用、人数または稼働率が無い確定期間、を出力へ足さない
- 根拠は `SOURCE`、`HISTORICAL`、`ASSUMPTION`、`AI_ESTIMATE` のいずれかにし、説明を空にしない
- `SOURCE` は目録のIDか、題名・発行元・年・https URLがある引用だけ
- IPAの値を目録へ追加する場合は、表番号、標本数、単位、工程、母集団、使わない条件を `docs/references.md` と目録の両方へ書く
- 外部資料のPDFや本文をリポジトリへコピーしない

## 数値を作らない

公開統計や実績が無い項目について、標準人日、標準リスク係数、標準の1人日時間を補完しないでください。幅を広げるか、未算定にして不足事項を残します。`AI_ESTIMATE` は `provisional: true` の暫定値であり、IPAやSIerの値として書きません。

PERT期待値と悲観値を、信頼区間や保証値と説明しないでください。三点に含めた不確実性を予備工数へ重ねないでください。

## テスト

```bash
python -m unittest discover -s tests -v
python -m estimator validate-skills
```

サンプル出力を更新するときは、依頼JSONを変更したうえで `python -m estimator calculate` により再生成し、手編集しないでください。

## 品質基準

- 同じ依頼JSONから同じJSONが得られる
- 無効な三点、負数、非数、重複WBS、単位の不一致は計算前に拒否する
- 実績の類似性が下限未満なら、計画工数へ使わない
- ベンチマーク照合は計画工数を変えない
- 新しい実行時依存を足さない

## 禁止

- 顧客の機密や個人情報を含む実績の追加
- 架空見本を本番の根拠にすること
- force push、ライセンスの変更、リリース、デプロイ
- 見積もり精度を実際より高く見せる説明
