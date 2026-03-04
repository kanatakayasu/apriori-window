# Runner Scaffold

比較手法の実行インターフェース。

## 目的

- 手法ごとの入出力差を吸収して共通 JSON で結果を保存
- 実装中でも CLI/設定ファイルの形を先に固定

## 使い方

```bash
python -m baselines.runner.run_method \
  --config comparative_methods/runner/configs/example_apriori.json
```

比較手法のマイニング部分は Rust バイナリ `comparative_mining` で実行する。
Python 側 runner は入出力変換・実行管理・集計のみを担当する。

```bash
# 入力変換（basket -> flat/timestamped/lppm）
python -m baselines.runner.preprocess_inputs \
  --input apriori_window_suite/data/sample_basket.txt \
  --input-format basket \
  --out-dir baselines/inputs \
  --stem sample_basket
```

```bash
# 集計（複数結果JSON -> CSV）
python -m baselines.runner.aggregate_stage_a \
  --results-glob 'baselines/results/*.json' \
  --gt-dir dataset/synthetic/ground_truth \
  --out-csv baselines/results/stage_a_summary.csv
```

```bash
# Stage A 比較手法を一括実行（入力1ファイル）
python -m baselines.runner.run_stage_a_suite \
  --input-basket apriori_window_suite/data/sample_basket.txt \
  --out-dir baselines/results \
  --backend auto
```

`runner/configs/example_*.json` は雛形なので、`dataset_path` は手元データに合わせて更新してから実行する。

## 入力フォーマット

- `flat`: `item item item ...`
- `basket`: `item item | item ...`（本プロジェクト形式）
- `timestamped`: `ts item item ...`

## 現在の状態

- 実装済み（Rust mining backend）:
  - `apriori`
  - `fp_growth`
  - `eclat`
  - `lcm`
  - `pfpm`
  - `ppfpm_gpf_growth`
  - `lpfim`
  - `lppm`

## 並列化状況

- `comparative_mining` で Rayon 並列化を有効化
- 並列化対象:
  - トランザクションごとの候補列挙
  - 候補ごとの支持度/周期性/区間評価
- 時系列依存手法（`pfpm`, `ppfpm_gpf_growth`, `lpfim`, `lppm`）は、並列reduce後に `ts` 列をソートして評価

## 次の実装順

1. Rust 実装の論文忠実度改善（特に `lpfim` / `lppm` / `ppfpm`）
2. `pfpm` / `ppfpm` の返却統計を論文定義に合わせて拡張
3. SPMF/PAMI との差分検証（回帰テスト化）

## メソッド別注意

- `lppm` は `params.maxPer/minDur/maxSoPer` が必須。
- Rust バイナリは `apriori_window_suite` クレートの `--bin comparative_mining` としてビルドされる。
- `--backend` 引数は互換性のため残しているが、現行実装では Rust backend を使用する。
