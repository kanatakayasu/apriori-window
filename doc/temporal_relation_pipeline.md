# Temporal Relation Pipeline — 設計ドキュメント

> **作成日**: 2026-03-17
> **ステータス**: 設計段階（Draft）
> **対象**: Phase 2 相当 — 密集区間と外部イベントの時間的関係抽出

---

## 1. 背景と動機

Phase 1（Basket-aware Apriori-Window）により、偽共起を排除した密集パターンとその密集区間が得られる。次の課題は、これらの密集区間と外部イベント（セールイベント、祝日、キャンペーン等）との**時間的関係**を効率的かつ意味のある形で抽出することである。

### 現状の問題

現行の `match_all` は全ペア総当たり O(N × M × 6) で時間的関係を判定する（N=密集区間数, M=イベント数）。

| 問題 | 詳細 |
|------|------|
| **計算コスト** | 実データ規模（N=10万, M=50）で約 3,000万回の関係チェック |
| **偶然の一致** | 統計的有意性を考慮しないため、偶然の時間的重複も出力に含まれる |
| **出力過多** | すべてのマッチが無差別に出力され、解釈が困難 |

---

## 2. 提案: 4 段パイプライン

Stage 0（現行）を基盤として、Stage 1 → 2 → 3 を積み重ねることで、計算効率と出力品質を段階的に向上させる。

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1 出力: 密集パターン P と密集区間 {(s_i, e_i)}           │
│  外部入力:     イベント集合 {(ts_j, te_j, name_j)}             │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ Stage 0: Brute-Force Baseline ─────────────────────────────────┐
│  全ペア総当たりで 6 種の Allen 関係を判定                        │
│  計算量: O(N × M × 6)                                          │
│  → ベースライン（正解集合の生成・検証用に保持）                  │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ Stage 1: MI Pre-filter（候補刈り込み）─────────────────────────┐
│  相互情報量による事前スクリーニング                              │
│  密集区間・イベント → 二値時系列 → MI(X; Y) 計算                │
│  MI > θ_MI のペアのみ次段へ                                     │
│  計算量: O((N + M) × T)  ← T: 時間軸の離散長                   │
│  効果: 大半の無関係ペアを安価に除外                              │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ Stage 2: Sweep Line Matching（高速マッチング）─────────────────┐
│  候補ペアに対して走査線アルゴリズムで Allen 関係を判定           │
│  ソート済み区間リスト + アクティブセットで効率的に走査           │
│  計算量: O((n + m) log(n + m) + K)  ← K: 出力数                │
│  オプション: HINT インデックスで ε 許容付き Allen 関係に拡張     │
│  効果: Stage 1 通過ペアを高速に判定                              │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ Stage 3: Statistical Significance（有意性検定）────────────────┐
│  置換検定で偶然の一致を除去                                      │
│  (1) 各 (パターン, イベント, 関係タイプ) の出現回数 c_obs を集計 │
│  (2) イベント時刻をランダムシャッフル × J 回（e.g., J=1000）    │
│  (3) 各置換で関係マッチ数 c_perm を計算                          │
│  (4) p 値 = |{c_perm ≥ c_obs}| / J                              │
│  (5) 多重検定補正（Westfall-Young / Bonferroni）                 │
│  効果: 統計的に有意な関係のみを最終出力                          │
│  付加価値: p 値・効果量付きの出力で新たな示唆を導出              │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─ 最終出力 ──────────────────────────────────────────────────────┐
│  relations_significant.csv                                      │
│  columns: pattern, dense_interval, event, relation_type,        │
│           overlap_length, p_value, adjusted_p_value,             │
│           effect_size, MI_score                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 各 Stage の詳細設計

### 3.1 Stage 0: Brute-Force Baseline

**目的**: 正解集合の生成。Stage 1–2 の最適化が正しいことを検証するリファレンス。

- 既存の `match_all` 実装をそのまま使用
- 6 種の Allen 関係: DFE / EFD / DCE / ECD / DOE / EOD
- パラメータ: ε（隣接許容幅）, d_0（最小重複長）
- **保持理由**: 最適化の正当性検証（Stage 2 の出力が Stage 0 と一致することをテストで保証）

### 3.2 Stage 1: Mutual Information Pre-filter

**目的**: 時間的に無関係なペアを安価に除外し、後段の計算量を削減する。

#### アルゴリズム

1. **二値時系列への変換**:
   - 密集区間 (s, e) に対して、時間軸上のインジケータ関数 $X(t) = \mathbb{1}[s \leq t \leq e]$ を構築
   - 同一パターンの複数密集区間は OR で統合: $X_P(t) = \max_i \mathbb{1}[s_i \leq t \leq e_i]$
   - イベント (ts, te) に対して同様に $Y_E(t) = \mathbb{1}[ts \leq t \leq te]$ を構築
2. **相互情報量の計算**:
   $$
   I(X_P; Y_E) = \sum_{x \in \{0,1\}} \sum_{y \in \{0,1\}} p(x, y) \log \frac{p(x, y)}{p(x) \cdot p(y)}
   $$
   - 同時確率 $p(x, y)$ は二値時系列の共起頻度から直接計算
   - 計算量: O(T) per pair（T = 時間軸長）
3. **閾値フィルタリング**: $I(X_P; Y_E) > \theta_{MI}$ のペアのみ Stage 2 へ

#### パラメータ

| パラメータ | 意味 | デフォルト |
|-----------|------|-----------|
| `mi_threshold` (θ_MI) | MI の下限閾値 | 0.01（要チューニング） |
| `time_resolution` | 時間軸の離散化粒度 | 1（トランザクション単位） |

#### 計算量分析

- パターン数 P_count, イベント数 M, 時間軸長 T に対して: O(P_count × M × T)
- T は通常 N（トランザクション数）と同程度
- Stage 0 の O(N_intervals × M × 6) と比較して、**パターン単位で集約**するため N_intervals → P_count に削減
- MI = 0 のペア（完全独立）を即座に除外可能

#### 研究的意義

- Ho et al. (VLDB 2022) の MI による時系列ペア事前フィルタリングを、頻出パターンマイニングの時間的関係判定に応用
- 「密集区間の時間的共起」を情報理論的に定量化する枠組みは先行研究に見られない

### 3.3 Stage 2: Sweep Line Matching

**目的**: Stage 1 を通過したペアに対して、Allen 関係を効率的に判定する。

#### アルゴリズム

1. 密集区間リストとイベントリストをそれぞれ開始時刻でソート
2. 走査線を左から右へ移動しながら、アクティブセット（現在重複している区間）を管理
3. 各 Allen 関係の判定条件を走査線上で効率的に評価

```
Sort dense_intervals by start time
Sort events by start time

active_set = {}
event_ptr = 0

for each dense_interval (s_i, e_i) in sorted order:
    // Remove expired intervals from active_set
    remove intervals from active_set where end < s_i - ε

    // Add new events that start before e_i + ε
    while event_ptr < |events| and events[event_ptr].start ≤ e_i + ε:
        add events[event_ptr] to active_set
        event_ptr++

    // Check Allen relations with active events
    for each event in active_set:
        check_and_emit_relations(dense_interval, event)
```

#### 計算量

- ソート: O((n + m) log(n + m))
- 走査: O(n + m + K)（K = 出力マッチ数）
- 合計: **O((n + m) log(n + m) + K)**
- Stage 0 の O(n × m) から大幅改善（特に K << n × m のとき）

#### ε 許容付き Allen 関係への拡張（HINT 適用）

- HINT (Christodoulou et al., SIGMOD 2022) は Allen の 13 関係をインデックスベースで高速判定
- 本研究では ε 許容付き 6 関係への適応が必要（未発表の拡張）
- 実装優先度: Sweep Line を先に実装し、性能が不足する場合に HINT へ移行

### 3.4 Stage 3: Permutation-based Significance Testing

**目的**: 偶然の時間的一致を統計的に除去し、有意な関係のみを出力する。

#### アルゴリズム

1. **観測統計量の計算**: 各 (パターン P, イベント E, 関係タイプ R) の出現回数 $c_{\text{obs}}(P, E, R)$ を集計
2. **帰無分布の構築**:
   - J 回（例: J = 1000）イベント時刻をランダムシャッフル（イベント間隔の分布を保持 or 一様シャッフル）
   - 各置換 j に対して Stage 2 を再実行し、$c_{\text{perm}}^{(j)}$ を計算
3. **p 値の計算**:
   $$
   p(P, E, R) = \frac{|\{j : c_{\text{perm}}^{(j)} \geq c_{\text{obs}}\}| + 1}{J + 1}
   $$
4. **多重検定補正**:
   - **Bonferroni**: $p_{\text{adj}} = \min(1, p \times |\text{hypotheses}|)$（保守的）
   - **Westfall-Young stepdown**: 置換ごとの最大統計量を用いて FWER を制御（推奨）
5. **有意性判定**: $p_{\text{adj}} < \alpha$（例: α = 0.05）のトリプルのみ出力

#### シャッフル戦略

| 戦略 | 方法 | 帰無仮説 |
|------|------|---------|
| **時刻一様シャッフル** | イベント開始時刻を [1, N] から一様サンプリング | イベントの発生時刻は密集区間と独立 |
| **循環シフト** | 全イベントを同一オフセットで循環シフト | イベント間の時間構造は保持しつつ、密集区間との位置関係がランダム |
| **ブロックシャッフル** | 時間軸をブロック分割し、ブロック単位で並べ替え | 局所的な時間依存性を保持 |

推奨: **循環シフト**（イベント間の相対構造を壊さないため、検出力が高い）

#### 計算量

- J × Stage 2 の計算量: O(J × ((n + m) log(n + m) + K))
- J = 1000, n + m = 10,000 の場合: 約 10^7 回の操作（十分高速）
- **早期終了最適化**: $c_{\text{perm}} \geq c_{\text{obs}}$ が $\alpha \times J$ 回に達した時点でそのトリプルを棄却（Westfall-Young Light）

#### 研究的意義

- Westfall-Young Light (KDD 2015) の再マイニング不要な枝刈りアイデアを、Allen 関係の有意性検定に初めて適用
- 「偽共起パターンの排除」（Phase 1）に続いて「偽時間的関係の排除」（Phase 2）という一貫した研究ストーリーを構成

---

## 4. 出力仕様

### 最終出力: `relations_significant.csv`

| カラム | 型 | 説明 |
|--------|-----|------|
| `pattern_components` | string | アイテムセット（例: `"[{1, 2}]"`） |
| `dense_start` | int | 密集区間の開始トランザクション |
| `dense_end` | int | 密集区間の終了トランザクション |
| `event_id` | string | イベント ID |
| `event_name` | string | イベント名 |
| `relation_type` | string | Allen 関係タイプ（DFE/EFD/DCE/ECD/DOE/EOD） |
| `overlap_length` | int? | 重複長（DOE/EOD のみ） |
| `mi_score` | float | Stage 1 の相互情報量 |
| `p_value` | float | Stage 3 の未補正 p 値 |
| `adjusted_p_value` | float | Stage 3 の補正済み p 値 |
| `effect_size` | float | 効果量（c_obs / E[c_perm]） |

### 中間出力

| Stage | ファイル | 内容 |
|-------|---------|------|
| Stage 0 | `relations_brute_force.csv` | 全ペアマッチ結果（検証用） |
| Stage 1 | `mi_scores.csv` | (パターン, イベント, MI) のスコア表 |
| Stage 2 | `relations_filtered.csv` | MI フィルタ + Sweep Line の結果 |
| Stage 3 | `relations_significant.csv` | 最終出力（有意なもののみ） |

---

## 5. 設定ファイル拡張

```json
{
  "temporal_relation_parameters": {
    "epsilon": 2,
    "d_0": 1,
    "pipeline": {
      "stage1_mi": {
        "enabled": true,
        "mi_threshold": 0.01,
        "time_resolution": 1
      },
      "stage2_sweep": {
        "enabled": true,
        "algorithm": "sweep_line"
      },
      "stage3_significance": {
        "enabled": true,
        "n_permutations": 1000,
        "shuffle_strategy": "cyclic_shift",
        "alpha": 0.05,
        "correction_method": "westfall_young",
        "early_termination": true
      }
    }
  }
}
```

各 Stage は `enabled: false` で無効化可能。Stage 0 のみの実行も可能（後方互換性）。

---

## 6. 実装ロードマップ

| 順序 | タスク | 実装先 | 工数 |
|------|--------|--------|------|
| 1 | Stage 0 を独立関数として切り出し | Python → Rust | 小 |
| 2 | Stage 1: MI 計算 + フィルタ | Python prototype | 中 |
| 3 | Stage 2: Sweep Line | Python prototype | 中 |
| 4 | Stage 3: 置換検定 | Python prototype | 中 |
| 5 | 統合テスト（Stage 0 と Stage 1+2 の出力一致確認） | pytest | 小 |
| 6 | Stage 3 の検出力検証（合成データ） | Python | 中 |
| 7 | Rust 移植（Stage 1–3） | Rust | 大 |
| 8 | 論文 Section 4 への追記 | LaTeX | 中 |

---

## 7. 論文への位置づけ

### ストーリー

> Phase 1 で「偽共起パターン」を排除し、Phase 2 で「偽時間的関係」を排除する。
> 2 段階の偽陽性排除により、意味のある密集パターンとその外部イベントとの関係のみを抽出する。

### 論文構成への影響

| セクション | 追加内容 |
|-----------|---------|
| §3 問題定義 | 時間的関係の形式的定義、有意な時間的関係の定義 |
| §4 提案手法 | 4 段パイプラインの記述、MI フィルタの理論的根拠、Sweep Line の計算量解析 |
| §5 実験 | Stage 別の計算時間比較、置換検定による偽陽性排除の効果、MI 閾値の感度分析 |
| §6 結論 | 偽共起 + 偽時間的関係の二重排除フレームワークとしての位置づけ |

### 引用すべき先行研究

| 研究 | 関連する Stage | 引用理由 |
|------|---------------|---------|
| Ho et al. (VLDB 2022) | Stage 1 | MI による時系列ペア事前フィルタリング |
| Christodoulou et al. (SIGMOD 2022) | Stage 2 | HINT: Allen 関係の高速インデックス |
| Bouros & Mamoulis (VLDB 2017) | Stage 2 | Sweep Line による区間結合 |
| Westfall-Young Light (KDD 2015) | Stage 3 | 再マイニング不要な置換検定 |
| Allen (1983) | 全体 | 時間的関係の理論的基盤 |

---

## 8. 評価計画

### 8.1 効率性評価

- **指標**: 各 Stage の実行時間、Stage 1 通過率（= 残存ペア / 全ペア）
- **期待**: Stage 1 で 80-95% のペアを除外、Stage 2 で O(n×m) → O((n+m) log(n+m) + K)
- **実験**: N_intervals × M_events を変化させた計算時間の比較（Stage 0 vs Stage 0+1+2）

### 8.2 品質評価

- **指標**: Stage 3 通過率（= 有意なトリプル / 全トリプル）、False Discovery Rate
- **実験**: 合成データで既知の時間的関係を埋め込み、Stage 3 の検出力（TPR）と FDR を測定
- **ベースライン**: Stage 0（フィルタなし）の出力に対する Stage 3 の精度向上

### 8.3 ケーススタディ

- **データ**: UCI Online Retail II（密集パターン + セールイベント）
- **評価**: Stage 3 で有意と判定された関係の解釈可能性を定性的に評価
