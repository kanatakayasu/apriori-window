# 実験実装計画 — (P, I, E) 帰属設計 × N=100K

作成日: 2026-04-04

---

## 0. 前提・設計方針

### 新設計の要点
- **仮説単位**: `(P, E)` → **`(P, I, E)`**（パターン・密集区間・イベントの三つ組）
- **振幅フィルタ廃止**: `min_support_range` / `min_magnitude` を削除済み
- **評価粒度**: `(P, I, E)` 三つ組での正解照合

### 正解データの生成方針（重要）

Phase 1（Apriori-window）は**厳密解**である。boost が十分で support ≥ θ が成立する期間は、Phase 1 が必ず正確な密集区間を抽出する。

したがって正解区間の取得は以下の2段階フローで行う：

```
1. 合成データ生成（トランザクション + イベント）
       ↓
2. Phase 1 実行（厳密解）
       ↓
3. 各植え込みシグナル (P, event_id) に対して、
   P の密集区間のうち event window [event_start, event_end] と
   重なるものを正解区間 I* として確定
       ↓
4. ground_truth.json に (P, I*, E) 三つ組として保存
```

#### 正解なし seed の扱い
boost が弱く Phase 1 が区間を検出しない場合、その seed の正解は空（Recall = 0）。
これは**正しい挙動**——密集していないのに帰属は不正解。

#### 正解区間の照合基準
Phase 1 は厳密解なので、評価時の区間照合は**完全一致**とする（tolerance 不要）。

---

## 1. パラメータ設計（N=100K）

5K → 100K の比率（×20）を基本として比例スケール。

| パラメータ | 旧（5K） | 新（100K） | 根拠 |
|---|---|---|---|
| `N` | 5,000 | **100,000** | — |
| ウィンドウ `W` | 50 | **1,000** | N の 1% |
| イベント持続 | 300 | **6,000** | N の 6% |
| SHORT 持続 | 80 | **1,600** | N の 1.6% |
| `min_support` θ | 3–5 | **5** | E[support]=W×β≈300 ≫ θ=5 |
| `sigma` σ | W=50 | **W=1,000** | σ=W を維持 |
| `n_items` | 200 | **200** | 変更なし |
| `p_base` | 0.03 | **0.03** | 変更なし |
| β スイープ | 0.1, 0.2, 0.3, 0.5 | **0.2, 0.3, 0.5** | β=0.1 は検出不安定のため除外 |
| `B`（置換回数） | 5,000 | **5,000** | 変更なし |
| seeds | 5 | **5** | 変更なし |

### β=0.1 除外の根拠
振幅フィルタ廃止により、β=0.1 は置換検定に入るようになったが、
E[support 増加] = W × β = 1000 × 0.1 = 100 とはいえ確率的変動により
Phase 1 が密集区間を検出しない seed が発生しやすい。
実験の安定性のため β ≥ 0.2 を対象とする。

---

## 2. 正解データフォーマット変更

### 変更前（旧 ground_truth.json）
```json
[
  {"pattern": [5, 15], "event_id": "E1"},
  {"pattern": [25, 35], "event_id": "E2"}
]
```

### 変更後（新 ground_truth.json）
```json
[
  {"pattern": [5, 15], "interval_start": 1250, "interval_end": 6800, "event_id": "E1"},
  {"pattern": [25, 35], "interval_start": 31250, "interval_end": 36800, "event_id": "E2"}
]
```

`interval_start` / `interval_end` はウィンドウ左端インデックス（Phase 1 出力と同じ座標系）。

---

## 3. 変更ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `experiments/src/gen_synthetic.py` | 全 `make_ex1_*` / `make_ex6_*` / `make_null_*` 関数の N・イベント持続スケール。`generate_synthetic` に Phase 1 実行と正解区間確定ロジックを追加 |
| `experiments/src/evaluate.py` | 照合キーを `(pattern, event_id)` → `(pattern, interval_start, interval_end, event_id)` に変更。`evaluate_with_event_name_mapping` も同様に更新 |
| `experiments/src/run_experiment.py` | `min_support_range` 削除。`AttributionConfig` 呼び出しを新シグネチャに合わせる。`ExperimentResult` の `significant_attributions` に `interval_start` / `interval_end` を追加 |
| `experiments/run_ex1.py` | `window_size=1000`, `min_support=5`。β=0.1 条件を削除。`AttributionConfig` から `min_support_range` を除去 |
| `experiments/run_ex2.py` | 全シナリオの N・パラメータスケール。`min_support_range` 除去 |
| `experiments/run_method_comparison.py` | `COMMON_PARAMS` の `window_size=1000`, `min_support=5`。`min_support_range` 除去 |
| `experiments/run_null_fdr.py` | N=100K に更新 |
| `experiments/run_baseline_comparison.py` | パラメータスケール |
| `apriori_window_suite/src/main.rs` | EX1 コマンドのデフォルトパラメータ更新（W=1000 等） |

---

## 4. gen_synthetic.py の変更詳細

### 4-1. generate_synthetic 関数の拡張

現状は「データ生成 → 正解 JSON 書き出し」の1段階。
新設計では「データ生成 → Phase 1 実行 → 正解区間確定 → 正解 JSON 書き出し」の2段階。

```python
def generate_synthetic(config: SyntheticConfig, out_dir: str) -> Dict:
    # ... 既存のトランザクション生成 ...

    # Phase 1 実行（Rust バイナリ or Python 実装）
    frequents = find_dense_itemsets(transactions, window_size, min_support, ...)

    # 正解区間の確定
    ground_truth = []
    for sig in config.planted_signals:
        pat_key = tuple(sorted(sig.pattern))
        if pat_key in frequents:
            for (iv_start, iv_end) in frequents[pat_key]:
                # 植え込みイベント窓と重なる密集区間を正解とする
                if iv_start <= sig.event_end and iv_end >= sig.event_start:
                    ground_truth.append({
                        "pattern": sorted(sig.pattern),
                        "interval_start": iv_start,
                        "interval_end": iv_end,
                        "event_id": sig.event_id,
                    })
    # ...
```

**注意点**: `window_size` / `min_support` は実験設定から受け取る必要があるため、
`generate_synthetic` の引数に追加する。

### 4-2. 各 make_ex1_* 関数のスケール

```python
# 旧
n_transactions=5000
event_duration=300
# 新
n_transactions=100_000
event_duration=6_000
```

全ての構造条件設定関数（OVERLAP / CONFOUND / DENSE / SHORT）を同様にスケール。

---

## 5. evaluate.py の変更詳細

### 照合キーの変更

```python
# 旧
gt_set: Set[Tuple[Tuple[int,...], str]]
# (pattern_tuple, event_id)

# 新
gt_set: Set[Tuple[Tuple[int,...], int, int, str]]
# (pattern_tuple, interval_start, interval_end, event_id)
```

### 変換ロジック

```python
for entry in gt_raw:
    pat = _pattern_key(entry["pattern"])
    iv_s = entry["interval_start"]
    iv_e = entry["interval_end"]
    gt_set.add((pat, iv_s, iv_e, entry["event_id"]))
```

予測側も `SignificantAttribution` の `interval_start` / `interval_end` を使って同様に構築。

---

## 6. EX 別の適合方針

### EX1：コア帰属精度

- **条件**: β ∈ {0.2, 0.3, 0.5} × 5 seeds + 構造条件（OVERLAP, CONFOUND, DENSE, SHORT）× 5 seeds
  - 計 7 条件 × 5 seeds = **35 runs**
- **評価**: `(P, I, E)` 完全一致で P/R/F1/FAR

### EX2：アブレーション

既存の ablation_mode はそのまま流用。

| 条件 | 内容 |
|---|---|
| `Full (prox*mag)` | 提案手法（変更なし） |
| `mag_only` | proximity を除去 |
| `prox_only` | magnitude を除去 |

**振幅フィルタのアブレーション条件は削除**（実装から廃止済み）。

EX2 の設計（Scenario A: prox が必要、Scenario B: mag が必要）は `(P, I, E)` 設計と相性が良い。
特に Scenario A は「同一パターンの複数密集区間のうち、イベント近傍のものだけを正しく帰属できるか」という `(P, I, E)` 設計の本質を直接検証する。

### EX3：手法比較

- 比較手法（Wilcoxon, CausalImpact, ITS, EventStudy, ECA）は `(P, E)` 粒度で動作するため、評価を `(P, E)` に折りたたんで統一する
  - 提案手法の出力 `(P, I, E)` → `(P, E)` に dedup して比較
  - この折りたたみは EX3 専用の評価パスとして実装
- `COMMON_PARAMS` から `min_support_range` を削除

### Null FDR 検証

- N=100K、帰無条件（植え込みシグナルなし）で FDR ≤ α を確認
- 仮説数が大幅増加（`(P, I, E)` 三つ組）するため BH 補正の挙動確認として重要
- 20 seeds で全 seeds 偽発見数 ≤ α × M を確認

---

## 7. Rust バイナリとの接続方針

### 現状
`run_experiment.py` は Python 実装（`event_attribution.py`）を呼んでいる。
Rust 実装（`correlator.rs`）が最新設計を反映しており、Python 実装との乖離を確認する必要がある。

### 方針
1. `main.rs` の EX コマンド（`cargo run -- ex1` 等）のデフォルトパラメータを 100K 版に更新
2. Python ランナー（`run_ex1.py` 等）は当面 Python 実装を呼び続けるが、Python 実装を Rust 実装と同期させる
3. 実行速度が問題になる場合は Rust バイナリを subprocess 経由で呼び出す形に移行

---

## 8. 実装順序（推奨）

1. **`gen_synthetic.py`**: N・パラメータスケール + Phase 1 組み込みによる正解区間確定
2. **`evaluate.py`**: `(P, I, E)` 照合に変更
3. **`run_experiment.py`**: `AttributionConfig` シグネチャ更新、`interval_start/end` を戻り値に追加
4. **`run_ex1.py`**: パラメータ更新、β=0.1 削除
5. **`run_ex2.py`**: パラメータスケール、振幅フィルタ条件削除
6. **`run_method_comparison.py`**: パラメータ更新、EX3 用 `(P,E)` 折りたたみ評価パス追加
7. **`run_null_fdr.py`**: N=100K 更新
8. **動作確認**: 1 seed で EX1 を試走し、正解 JSON・評価結果が正しく出力されることを確認

---

## 9. 懸念事項

1. **Phase 1 の計算量**: N=100K, W=1000 ではパターン数・密集区間数が増加する可能性がある。θ=5 以上に引き上げることで制御する。試走時に `n_patterns` / `n_dense_intervals` を確認する。

2. **Python 実装の同期**: `event_attribution.py` の Python 実装が Rust 実装と同期されているかを確認する。特に `AttributionConfig` の `min_support_range` / `min_magnitude` フィールドが削除されているかを要確認。

3. **EX2 の正解形式**: EX2 の Scenario A（同一パターンの複数密集区間）では、植え込み窓と重なる区間が複数の場合がある。この場合は重複のある全区間を正解として記録する。
