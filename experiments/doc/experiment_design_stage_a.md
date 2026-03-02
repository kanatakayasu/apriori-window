# Stage A 実験設計（合成データ）

> 対象フェーズ: Phase 3
> 目的: Phase 1（Basket-aware Apriori-Window）の評価
> 更新: 2026-03-02
> 備考: 本ドキュメントは Stage A 専用。Stage B は `experiment_design_stage_b.md` を参照。
> 実行手順ベースライン: `experiments/doc/stage_a_runbook.md`

---

## 0. 研究問い（Stage A）

| RQ | 問い |
|----|------|
| **RQ1-A** | バスケット構造を考慮すると、偽共起（異なるバスケット間の誤共起検出）はどの程度抑制されるか？ |
| **RQ2-A** | 偽共起抑制は、検出される密集区間の質（純度）をどう変えるか？ |
| **RQ4-A** | Rust 実装は大規模データ（〜100万トランザクション）で実用速度か？ |

---

## 1. 方針: パターン同定と区間検出を分離する

Stage A は以下の2タスクを分けて評価する。

1. **パターン同定（Pattern Identification）**
- 「どのアイテム集合を検出するか」を評価する。
- 区間そのものは使わない。
- この設定では、全体支持度系（Apriori, FP-Growth, Eclat, LCM）も比較対象に含められる。

2. **区間検出（Interval Detection）**
- 「密集している時間区間をどれだけ正しく出せるか」を評価する。
- 区間を出力できる手法のみ比較対象にする（Phase 1 / 従来Apriori-window / LPFIM / LPPM）。

この分離により、
- パターン集合の誤検出（偽共起）
- 区間境界の誤検出
を混同せずに議論できる。

---

## 2. 合成データ生成（共通）

### 2.1 偽共起の発生モデル

1 トランザクション（時間帯）に複数の独立バスケットを含める。

- バスケット内共起: 真の共起
- バスケット横断共起: 偽共起（従来フラット化で混入）

例:
- B1 = {牛乳, パン}, B2 = {ビール, ポテチ}
- フラット化 `T={牛乳, パン, ビール, ポテチ}` では `牛乳-ビール` が偽共起として混入
- Phase 1 はバスケット境界を保持し、偽共起を除外

### 2.2 生成パラメータ

| パラメータ | 記号 | 既定値 |
|-----------|------|--------|
| トランザクション数 | `N_transactions` | 10,000（A1/A2/A3）、1,000〜1,000,000（A4） |
| 総アイテム数 | `N_items` | 200 |
| カテゴリ数 | `G` | 10（A2で可変） |
| 同カテゴリ選択確率 | `p_same` | 0.8 |
| バスケット数平均 | `λ_baskets` | 2.0（A1で可変） |
| バスケットサイズ平均 | `λ_basket_size` | 4.0 |
| 最小支持度 | `min_support` | 50 |
| window サイズ | `window_size` | 500 |
| 最大長 | `max_length` | 4 |
| 乱数 seed | `seeds` | 5（A3は3） |
| 生成モデル | - | Poisson のみ |

### 2.3 Ground Truth（GT）

#### 2.3.1 パターン同定用 GT

- `true_support(S)`: バスケット単位の支持度
- `txn_support(S)`: フラット化トランザクション単位の支持度
- `spurious(S)`: `true_support(S) < min_support <= txn_support(S)`

#### 2.3.2 区間検出用 GT

- `true_dense_intervals(S)`: バスケット単位時系列で定義される真の密集区間
- 区間は `[start, end]` の離散区間として保持

---

## 3. 比較手法

### 3.1 パターン同定実験（区間は使わない）

| 区分 | 手法 | 位置づけ |
|------|------|----------|
| 同一タスク比較（主） | **Phase 1（提案）** | バスケット対応・厳密 |
| 同一タスク比較（主） | **従来Apriori-window（フラット化）** | バスケット非対応・厳密 |
| 参考比較（異タスク） | Apriori | 全体支持度ベース |
| 参考比較（異タスク） | FP-Growth | 全体支持度ベース |
| 参考比較（異タスク） | Eclat | 全体支持度ベース |
| 参考比較（異タスク） | LCM | 全体支持度ベース |

注意:
- 全体支持度系は「密集区間」を直接扱わないため、**パターン集合の比較のみ**行う。
- 論文では「reference baseline（task-mismatch）」として明記する。

### 3.2 区間検出実験（区間出力必須）

| 区分 | 手法 | 位置づけ |
|------|------|----------|
| 同一タスク比較（主） | **Phase 1（提案）** | バスケット対応 |
| 同一タスク比較（主） | **従来Apriori-window（フラット化）** | バスケット非対応 |
| 参考比較（近接タスク） | LPFIM | ギャップベース区間検出 |
| 参考比較（近接タスク） | LPPM | ギャップベース区間検出 |

注意:
- PFPM/PPFPM は区間出力の比較軸が不揃いになりやすいため、Stage A の区間検出実験では外す。

---

## 4. 評価指標

### 4.1 パターン同定指標

#### 主指標（RQ1-A）

1. `SPR`（Spurious Pattern Rate）

```
SPR = |{S : spurious(S)=true}| / |{S : txn_support(S) >= min_support}|
```

2. `Spurious Count`
- 偽共起パターン数（絶対値）

3. `True Pattern Recall`（検証指標）
- `true_support` を満たすパターンをどれだけ回収できるか
- Phase 1 では自明に高くなるため補助指標扱い

#### 基本性能（必須）

4. 検出パターン数（全体・長さ別）
5. 実行時間（総時間）
6. peak memory

### 4.2 区間検出指標

#### 主指標（RQ2-A）

1. `Interval Purity`

```
Purity(I,S) = basket_count(I,S) / txn_count(I,S)
Interval Purity = mean_{(I,S)} Purity(I,S)
```

2. `Mean Jaccard`（GT区間との一致）

```
J(S) = |I_true(S) ∩ I_pred(S)| / |I_true(S) ∪ I_pred(S)|
```

#### 基本性能（必須）

3. 検出区間数
4. 区間長統計（平均・中央値）
5. 実行時間、peak memory

### 4.3 報告形式

- 各条件で `mean ± 95% CI`（seed平均）
- 主要比較は改善率（%）も併記

---

## 5. 実験マトリクス

### A1: パターン同定（λ_baskets sweep, 主実験）

- 目的: RQ1-A
- 可変: `λ_baskets = {1.0, 1.5, 2.0, 3.0, 5.0}`
- 固定: `N_transactions=10,000, G=10, min_support=50, window_size=500, max_length=4`
- 比較手法:
  - 主: Phase 1, 従来Apriori-window
  - 参考: Apriori, FP-Growth, Eclat, LCM
- 期待:
  - `λ_baskets=1.0` では従来法とPhase 1の差は小さい
  - `λ_baskets` 増加で従来法の `SPR` が増加、Phase 1 は低水準維持

### A2: 区間検出（λ_baskets sweep）

- 目的: RQ2-A
- 可変: `λ_baskets = {1.0, 1.5, 2.0, 3.0, 5.0}`
- 固定: A1と同一
- 比較手法:
  - 主: Phase 1, 従来Apriori-window
  - 参考: LPFIM, LPPM
- 指標: Interval Purity, Mean Jaccard, 区間数, 区間長
- 期待:
  - `λ_baskets` 増加時に従来法のPurity低下
  - Phase 1は高Purityを維持

### A3: 構造感度（カテゴリ数 sweep）

- 目的: RQ1-A 補足
- 可変: `G = {3, 5, 10, 20, 50}`
- 固定: `λ_baskets=2.0`、他はA1準拠
- 比較手法: Phase 1, 従来Apriori-window（必要に応じて LPFIM/LPPM を追加）
- 指標: SPR, Spurious Count, Interval Purity

### A4: スケーラビリティ

- 目的: RQ4-A
- 可変: `N_transactions = {1k, 10k, 100k, 1M}`
- 固定: `λ_baskets=2.0, G=10`
- 比較手法: Phase 1, 従来Apriori-window（Rust主、Pythonは10万まで）
- 指標: 実行時間、peak memory、throughput

---

## 6. 実行順序（Stage A）

1. `gen_synthetic.py` のPoisson生成確認
2. GT計算（パターン同定/区間検出）実装と単体テスト
3. A1（パターン同定・λ sweep）
4. A2（区間検出・λ sweep）
5. A3（カテゴリ構造感度）
6. A4（スケーラビリティ）
7. 図表化（主図: A1, A2 / 補助図: A3, A4）

---

## 7. 出力ファイル（Stage A）

```
experiments/results/
  A1_pattern_identification.csv
  A2_interval_detection.csv
  A3_category_sensitivity.csv
  A4_scalability.csv
  summary_stage_a.md
```

CSV列（例）:
- `experiment,method,seed,lambda_baskets,G,n_transactions`
- `spr,spurious_count,true_recall,pattern_count,time_sec,peak_mem_mb`
- `interval_purity,mean_jaccard,interval_count,interval_len_mean`
