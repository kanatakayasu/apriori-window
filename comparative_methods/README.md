# Comparative Methods

このディレクトリは Stage A 比較手法の実装仕様と実行基盤を管理する。

## 構成

- `methods/`: 手法ごとの実装仕様
- `DECISIONS.md`: 未確定仕様の意思決定ログ
- `specs/`: 調査レポートのスナップショット
- `runner/`: 比較手法の実行・前処理・集計CLI

## 実装状況

- 実装済み: `apriori`, `fp_growth`, `eclat`, `lcm`, `pfpm`, `ppfpm_gpf_growth`, `lpfim`, `lppm`
- マイニング実装: Rust（`apriori_window_suite` の `comparative_mining` バイナリ）
- Python runner: 入出力変換・実行管理・集計
- 並列化: `comparative_mining` 側で Rayon により候補評価を並列化（全手法）

## 注意

- Stage A の主比較は `Phase 1 vs 従来Apriori-window`。
- 外部比較手法は task mismatch を明記して評価する。
- SPMF / PAMI は現行runnerの実行バックエンドではなく、仕様確認・oracle比較用途。
- GPLv3 実装（SPMF / PAMI）を参照する場合は配布形態に注意。
- 実装上の未確定点は `DECISIONS.md` で管理し、現時点の主要3項目は決定済み。
- 実行手順は `runner/README.md` を参照。
