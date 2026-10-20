# WBS

各項目は次を持つ。

- WBS ID（例: `WBS-001`）
- 要件ID。横断作業は `UNSCOPED`
- 作業名と作業内容
- 工程区分
- 前提
- 楽観、最頻、悲観、期待（期待はスクリプトが計算）
- 算定根拠の区分と説明
- 不確実性（`low`、`medium`、`high`）
- 依存先が分かるときだけ `depends_on`

依存関係は記録するが、人員配置が項目ごとに無いため、クリティカルパスの日数には換算しない。

機能要件と非機能要件の全IDが、少なくとも1つの算定可能WBSに現れることを確認する。未対応要件または未算定WBSがあれば、見積もり結果は部分見積もりとして扱い、全体の費用・期間を示さない。

## 工程区分

使う可能性がある区分は次のとおり。本件に不要なら項目を作らず、対象外へ理由を書く。

- `requirements` 要件整理
- `basic_design` 基本設計
- `detailed_design` 詳細設計
- `ui_implementation` UI
- `api_implementation` API
- `implementation` 上の区分に分けない実装
- `db` データ設計・実装
- `external_integration` 外部連携
- `auth` 認証・認可
- `security` セキュリティ対策
- `unit_test` 単体テスト
- `integration_test` 結合テスト
- `system_test` システムテスト
- `test` 上の区分に分けないテスト
- `review` レビュー
- `defect_fix` 不具合修正
- `cicd` CI/CD
- `infrastructure` インフラ
- `documentation` ドキュメント
- `release` リリース準備
- `handover` 運用引き継ぎ
- `project_management` プロジェクト管理
- `impact_analysis` 改修の影響調査
- `regression_test` 回帰テスト
- `data_migration` データ移行
- `other` 上記に当てはまらない作業

## 漏れやすい作業

機能の実装工数だけを合計しない。該当するものは独立項目にする。

- 非機能の検証（性能、可用性、監査、セキュリティ）
- 認証・認可
- 移行とロールバック
- レビューと手戻り
- テストデータと検証環境
- リリースと引き継ぎ
- 進行管理

すでに項目へ含めた作業を、別項目として繰り返さない。

## 粒度

レビュー参加者が、前提と三点の幅に異議を出せる大きさを保つ。画面の部品や日々の作業まで割らない。
