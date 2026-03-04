# Stage A Runbook (Execution Baseline)

> 更新日: 2026-03-02
> 目的: Stage A 比較実験を開始する前に、実験条件と実行手順を固定する

## 1. 固定する実験条件

### 1.1 対象実験と優先順

1. A1（パターン同定, `lambda_baskets` sweep）
2. A2（区間検出, `lambda_baskets` sweep）
3. A3（構造感度, `G` sweep）
4. A4（スケーラビリティ, `N_transactions` sweep）

### 1.2 共通パラメータ（Stage A baseline）

- `minsup_count`: `50`
- `max_length`: `4`
- `window_size`（Phase1系）: `500`
- `seed`:
  - A1/A2: `0..4`（5 seeds）
  - A3: `0..2`（3 seeds）
  - A4: `0..2`（3 seeds）

### 1.3 比較手法（comparative_methods 側）

- パターン同定系: `apriori`, `fp_growth`, `eclat`, `lcm`
- 周期系（参考）: `pfpm`, `ppfpm_gpf_growth`
- 区間系: `lpfim`, `lppm`

補足:
- 主比較は `Phase1 vs 従来Apriori-window`。
- 上記比較手法は reference baseline として扱う（task mismatch を明記）。

### 1.4 出力先

- comparative methods の出力:
  - `baselines/results/`
- Stage A 実験結果（Phase1系）:
  - `experiments/results/`

## 2. 実行前チェック（Step2）

### 2.1 Rust バイナリのビルド確認

```bash
cd apriori_window_suite
cargo build --release --offline --bin comparative_mining
```

### 2.2 小規模スモーク（1データ × 全比較手法）

```bash
cd /Users/kanata/Documents/GitHub/apriori-window
python3 -m comparative_methods.runner.run_stage_a_suite \
  --input-basket apriori_window_suite/data/sample_basket.txt \
  --out-dir baselines/results/smoke_20260302 \
  --backend auto \
  --minsup-count 1 \
  --max-length 3
```

期待される完了条件:
- `baselines/results/smoke_20260302/` に各手法JSONが出力される
- `sample_basket_suite_summary.csv` が生成される
- 全手法で実行が完了し、例外終了しない

## 3. 次アクション（Step3以降）

1. A1本番（lambda sweep, seed=5）
2. A2本番（interval評価）
3. `aggregate_stage_a.py` によるCSV集計
4. 図表化（A1/A2を主図）
