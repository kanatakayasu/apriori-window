# 実装ログ (impl_log.md)

実装完了後に追記する変更履歴。1エントリ = 1コミット意図。

## フォーマット

```
### YYYY-MM-DD — <変更タイトル>
- **対象**: 変更したファイル / モジュール
- **内容**: 何を変更したか（1〜3行）
- **テスト**: 追加・変更したテスト名
- **関連コミット**: <git short hash>
```

---

## ログ

### 2026-04-04 — RunEx4 サブコマンド追加 (Dunnhumby 実データ帰属)
- **対象**: `src/main.rs`, `Cargo.toml`
- **内容**:
  1. `Cargo.toml` に `csv = "1"` 依存を追加。
  2. `src/main.rs` に `RunEx4` CLIサブコマンドを追加（`--data-dir`, `--out-dir`, `--sensitivity` オプション）。
  3. `run_ex4()` 関数を実装: `product_id_map.json` / `product.csv` から commodity マップ構築、`coupon.csv` からキャンペーン別クーポン対象品目マップ構築、TypeA イベントのみフィルタして `run_attribution_pipeline` を呼び出し、クーポン整合性チェック、各設定の結果を `ex4_{label}.json` に保存、感度分析サマリを `ex4_sensitivity.json` に保存。
  4. `is_coupon_consistent()` ヘルパー関数を追加。
  5. `use std::collections::HashSet;` を imports に追加。
- **テスト**: lib 62 tests + main 1 test（全 pass）
- **関連コミット**: (pending)

### 2026-04-04 — 全実験実行 (EX1/EX2/EX3/NullFDR)・min_support=100スケーリング・RunNullFdr追加
- **対象**: `src/main.rs`, `src/synth.rs`, `experiments/run_ex2.py`
- **内容**:
  1. **min_support スケーリング**: N=100K, W=1000 環境で secondary pattern（非植付パターン）の期待サポート ≈9.9 << 100 となるよう、`run_ex3` の `min_support` を 5 → 100 に更新（EX1 は前セッションで完了済み）。`run_ex2.py` も同様に 5 → 100 に更新。
  2. **RunNullFdr サブコマンド追加**: `src/main.rs` に `run-null-fdr` CLI サブコマンドを追加。`make_null_fdr_config` を `synth.rs` に追加（N=100K、4つの unrelated dense interval + 5つの decoy event が重ならない位置に配置）。
  3. **全実験結果**:
     - EX1 (8条件×5seeds): F1=0.65〜0.80 (beta_0.3=0.75, SHORT=0.79, OVERLAP=0.80, CONFOUND=0.69, DENSE=0.65)
     - EX3 (6手法×5条件×5seeds, N=100K): Proposed F1=0.66〜0.71; Wilcoxon/CausalImpact/ITS/EventStudy/ECA F1=0.00 (全条件)
     - EX2 ablation: Scenario A — Full/No_mag F1=1.00, No_prox F1=0.00; Scenario B — Full F1=0.54, No_mag F1=0.60, No_prox F1=0.00
     - NullFDR (20seeds, N=100K): mean per-seed FDR=0.05 ≤ α=0.10 ✓ (1/20 seeds に1 FP)
- **テスト**: 63 lib+main tests（全 pass）
- **関連コミット**: (pending)

### 2026-04-04 — 帰属単位を (P,I,E) に変更・N=100K スケール対応
- **対象**: `src/evaluate.rs`, `src/synth.rs`, `src/main.rs`
- **内容**: `PredictedAttribution` / `GtEntry` に `interval_start` / `interval_end` フィールド追加（`#[serde(default)]`）。`evaluate_with_event_name_mapping` の照合キーを `(pattern, event_id)` から `(pattern, interval_start, interval_end, event_id)` の4-tupleに変更（旧形式GT互換: interval=0,0の場合はlegacyモード）。`generate_synthetic` に `window_size` / `min_support` 引数を追加し、Phase 1 実行後に重複区間でフィルタした (P,I,E) トリプルをGTとして出力。`run_ex1` / `run_ex3` の `window_size=1000`, `min_support=5`, `max_length=2` に更新。
- **テスト**: 全63テスト pass（lib: 62, main: 1）
- **関連コミット**: (main branch)

### 2026-04-02 — Rust完全移行: ベースライン・合成データ生成・評価モジュール追加 + CLIサブコマンド
- **対象**: `src/baselines.rs`（新規）, `src/synth.rs`（新規）, `src/evaluate.rs`（新規）, `src/main.rs`（clap CLI再設計）, `src/lib.rs`（モジュール登録）, `Cargo.toml`（clap依存追加）
- **内容**: 5手法ベースライン（Wilcoxon/CausalImpact/ITS/EventStudy/ECA）をRustで実装（rayon並列化・O(N) two-pointer）。合成データ生成・評価指標もRust移植。CLIにphase1/run-experiment/run-ex1/run-ex3サブコマンド追加。N=1,000,000 × 10 seeds での実験が2255秒で完了確認。
- **テスト**: 63 lib/main tests（全pass）
- **関連コミット**: (main branch)

### 2026-03-01 — Phase 1 + Phase 2 統合クレート初期実装
- **対象**: `apriori_window_suite/` クレート全体
- **内容**: Phase 1（バスケット対応 Apriori-window）と Phase 2（イベント時間的関係）を統合
- **テスト**: 54 lib tests + 4 E2E tests
- **関連コミット**: (dev_takayasu ブランチ初期)
