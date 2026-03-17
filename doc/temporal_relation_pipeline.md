# Event Attribution Pipeline — 設計ドキュメント

> **作成日**: 2026-03-17
> **改訂日**: 2026-03-17（方向 E: 密集区間の動態 × 外部イベント帰属に全面改訂）
> **ステータス**: 設計段階（Draft）
> **対象**: Phase 2 — サポート変動の変化点検出と外部イベントへの帰属

---

## 1. 背景と動機

Phase 1（Apriori-Window）により、頻出アイテムセットの密集区間（サポートが閾値を超える時間区間）が得られる。次の課題は、**密集区間の出現・消失・伸縮がどの外部イベントに起因するか**を統計的に特定することである。

### 旧設計の問題点

旧 Phase 2（Allen 関係マッチング）は密集区間とイベントの「時間的位置関係」を列挙するだけであり、以下の限界があった：

| 問題 | 詳細 |
|------|------|
| **既存手法の適用** | Allen 関係マッチング、MI フィルタ、Sweep Line、置換検定はすべて既存手法の直接的応用であり、新規性が不足 |
| **静的な記述** | 密集区間の「存在」を記述するだけで、「変化」（出現・消失・伸縮）を扱わない |
| **帰属の欠如** | 位置関係の列挙であり、「どのイベントがサポート変動を引き起こしたか」には答えない |

### 新設計の方向性

密集区間の**動態**（サポート時系列の構造的変化）に着目し、その変化を外部イベントに**帰属**させる。

**研究ギャップ**: 先行研究調査（`doc/related_work_survey.md`）により、以下の組合せを扱った研究は存在しないことを確認：

- Emerging Patterns (Dong & Li 1999): サポート変動を検出するが、外部イベントへの帰属は行わない
- CausalImpact (Brodersen+ 2015): 時系列への介入効果を推定するが、パターンサポートには適用されていない
- Haiminen+ (2008): バースト系列の共起検定だが、バーストの「変化」ではなく「存在」を対象

---

## 2. 提案: 4 ステップ Event Attribution Pipeline

Phase 1 の中間出力（サポート時系列）を活用し、4 ステップで外部イベントへの帰属を行う。

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1 出力:                                                  │
│    frequents: Dict[itemset → List[(start, end)]]               │
│    support_series: Dict[itemset → List[int]]  ← 新規公開       │
│  外部入力:                                                      │
│    events: List[(start, end, name)]                             │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ Step 1: Support Time Series Construction ─────────────────────┐
│  Phase 1 のウィンドウ走査で各位置 t のサポート s_P(t) を記録     │
│  → 各パターン P について長さ N の整数時系列を得る                │
│  計算量: Phase 1 と同時に算出（追加コストなし）                  │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ Step 2: Change Point Detection ───────────────────────────────┐
│  s_P(t) の構造的変化点 τ を検出                                 │
│  (a) 閾値交差法: 密集区間の開始/終了 = 最も単純な変化点          │
│  (b) CUSUM 法: レベルシフトの逐次検出                           │
│  各変化点に方向（上昇/下降）と変化量 Δ を付与                    │
│  計算量: O(N) per pattern                                       │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ Step 3: Event Attribution Scoring ────────────────────────────┐
│  各変化点 τ_k と各イベント e_j の帰属スコアを計算               │
│  (a) 時間的近接度: proximity(τ_k, e_j) = exp(-|τ_k - t_e| / σ) │
│  (b) 方向整合性: サポート上昇 × イベント開始 → 正の帰属          │
│                  サポート下降 × イベント終了 → 正の帰属          │
│  (c) 変化量の大きさ: |Δ| が大きいほど帰属スコアが高い            │
│  候補トリプル (pattern, change_point, event) を生成              │
│  計算量: O(C × M)  ← C: 変化点数, M: イベント数                │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ Step 4: Statistical Significance Testing ─────────────────────┐
│  各候補トリプルの帰属が偶然でないことを検定                      │
│  帰無仮説: 変化点の位置はイベントと独立                          │
│  (1) 観測統計量: 変化点-イベント距離 d_obs を集計               │
│  (2) 円形シフト × J 回 (e.g., J=1000):                         │
│      イベント時刻を一様にシフトし d_perm を計算                  │
│  (3) p 値 = |{j: d_perm ≤ d_obs}| / (J + 1)                   │
│  (4) 多重検定補正（Bonferroni / Westfall-Young）                │
│  効果: 統計的に有意な帰属のみを最終出力                          │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ 最終出力 ──────────────────────────────────────────────────────┐
│  attributions.csv                                               │
│  columns: pattern, change_time, change_direction, change_mag,   │
│           event_name, proximity, attribution_score,             │
│           p_value, adjusted_p_value                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 各 Step の詳細設計

### 3.1 Step 1: Support Time Series Construction

**目的**: Phase 1 の中間計算結果を公開し、後続ステップの入力とする。

Phase 1 の `compute_dense_intervals` は内部でウィンドウ位置ごとのサポートを計算している。現行実装ではこれを閾値比較後に破棄するが、Step 1 ではこの時系列を保持する。

#### 出力

```python
support_series: Dict[Tuple[int, ...], List[int]]
# 例: {(1, 2): [0, 1, 2, 3, 3, 2, 1, 0, 0, 3, 4, 3, ...]}
```

#### 計算量

Phase 1 のウィンドウ走査と同時に算出可能。追加コストは O(N) のメモリのみ。

### 3.2 Step 2: Change Point Detection

**目的**: サポート時系列 s_P(t) の構造的変化点を検出する。

#### 手法 (a): 閾値交差法

密集区間の開始/終了は「サポートが閾値を上回った/下回った時点」。Phase 1 が既に計算済み。

#### 手法 (b): CUSUM（累積和管理図）

閾値に依存しない、より一般的な変化点検出。レベルシフトを逐次的に検出する。

#### パラメータ

| パラメータ | 意味 | デフォルト |
|-----------|------|-----------|
| `method` | 変化点検出手法 | `"threshold_crossing"` |
| `threshold` | 閾値交差法の閾値 | Phase 1 の min_support |
| `cusum_drift` | CUSUM のドリフト許容量 | 0.5 |
| `cusum_h` | CUSUM の判定閾値 | 4.0 |

### 3.3 Step 3: Event Attribution Scoring

**目的**: 各変化点と各イベントの帰属関係をスコアリングする。

帰属スコア A(τ_k, e_j) = proximity × direction_match × |Δ_k|

- **時間的近接度**: proximity(τ, e) = exp(-min(|τ - start_e|, |τ - end_e|) / σ)
- **方向整合性**: 上昇×開始後=1.0, 下降×終了後=1.0, 不整合=0.0, 予兆=0.5
- **変化量**: |Δ_k| = 変化点前後のサポート差の絶対値

#### パラメータ

| パラメータ | 意味 | デフォルト |
|-----------|------|-----------|
| `sigma` | 近接度の減衰幅 | `window_size` |
| `max_distance` | 最大距離 | `2 * window_size` |
| `attribution_threshold` | 最小帰属スコア | 0.1 |

### 3.4 Step 4: Permutation-based Significance Testing

**目的**: 変化点とイベントの近接が偶然でないことを統計的に検定する。

- **帰無仮説**: 変化点の位置はイベントと独立
- **円形シフト**: イベント間の相対構造を保存しつつ位置関係のみランダム化
- **多重検定補正**: Bonferroni（保守的）または Westfall-Young（推奨）

#### パラメータ

| パラメータ | 意味 | デフォルト |
|-----------|------|-----------|
| `n_permutations` | 置換回数 | 1000 |
| `alpha` | 有意水準 | 0.05 |
| `correction_method` | 多重検定補正法 | `"bonferroni"` |

---

## 4. 出力仕様

### 最終出力: `attributions.csv`

| カラム | 型 | 説明 |
|--------|-----|------|
| `pattern` | string | アイテムセット |
| `change_time` | int | 変化点のトランザクション時刻 |
| `change_direction` | string | `"up"` or `"down"` |
| `change_magnitude` | float | サポート変化量 |
| `event_name` | string | 帰属先イベント名 |
| `event_start` | int | イベント開始時刻 |
| `event_end` | int | イベント終了時刻 |
| `proximity` | float | 時間的近接度 |
| `attribution_score` | float | 帰属スコア |
| `p_value` | float | 未補正 p 値 |
| `adjusted_p_value` | float | 補正済み p 値 |

---

## 5. 設定ファイル

```json
{
  "event_attribution_parameters": {
    "change_detection": {
      "method": "threshold_crossing",
      "cusum_drift": 0.5,
      "cusum_h": 4.0
    },
    "attribution": {
      "sigma": null,
      "max_distance": null,
      "attribution_threshold": 0.1
    },
    "significance": {
      "n_permutations": 1000,
      "alpha": 0.05,
      "correction_method": "bonferroni"
    }
  }
}
```

`sigma` と `max_distance` が `null` の場合、Phase 1 の `window_size` から自動設定。

---

## 6. 実装ロードマップ

| 順序 | タスク | 実装先 | 工数 |
|------|--------|--------|------|
| 1 | Step 1: サポート時系列公開 | Python | 小 |
| 2 | Step 2: 変化点検出（閾値交差 + CUSUM） | Python | 小 |
| 3 | Step 3: 帰属スコアリング | Python | 中 |
| 4 | Step 4: 置換検定 | Python | 中 |
| 5 | 統合テスト（合成データ） | pytest | 中 |
| 6 | Rust 移植 | Rust | 大 |
| 7 | 論文 Section 4 への追記 | LaTeX | 中 |

---

## 7. 論文への位置づけ

### ストーリー

> 頻出パターンのサポートは時間とともに変動するが、既存手法はこの変動を外部イベントに帰属させる枠組みを持たない。
> 本研究は、サポート時系列の変化点検出とイベント帰属を統合し、統計的に有意な帰属のみを出力するフレームワークを提案する。

### 新規性

1. **問題設定**: パターンのサポート変動を外部イベントに帰属させる問題を明示的に定式化
2. **Emerging Patterns との差異**: EP は 2 データセット間の静的比較、本研究は連続時間軸上の動的変化 × イベント帰属
3. **CausalImpact との差異**: 一般時系列ではなくパターンサポート時系列への適用

### 引用すべき先行研究

| 研究 | 引用理由 |
|------|---------|
| Dong & Li (KDD 1999) Emerging Patterns | サポート変動検出の先行研究 |
| Brodersen et al. (AoAS 2015) CausalImpact | 時系列介入効果推定 |
| Haiminen et al. (BMC Bioinf. 2008) | バースト系列共起検定 |
| Kleinberg (KDD 2002) | バースト検出 |
| Khan et al. (KBS 2009) DSAT | スライディングウィンドウ上 EP |
| WY-light (KDD 2015) | 置換検定の効率化 |
