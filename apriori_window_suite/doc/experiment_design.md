# 実験設計書

> 対象フェーズ: Phase 3（実データ検証）
> 目的: 学術論文への投稿
> 作成: 2026-03-01
> 対象 Stage: A（合成データ）+ B（UCI Online Retail II）
> ※ Stage C（Dunnhumby）は別途実施

---

## 0. 研究問い（Research Questions）

| RQ | 問い | 対応 Stage |
|----|------|-----------|
| **RQ1** | バスケット構造を考慮すると、偽共起（異なるバスケット間の誤った共起検出）はどの程度抑制されるか？ | A |
| **RQ2** | 偽共起の抑制は、密集区間の質（検出される意味ある区間の割合）をどう変えるか？ | A |
| **RQ3** | 実購買データ（UCI Online Retail II）において、Phase 1 の適用で検出パターンがどう変化するか？ | B |
| **RQ4** | Rust 実装は大規模データ（〜100万トランザクション）において実用的な速度で動作するか？ | A, B |

---

## 1. Stage A：合成データ実験

### 1.1 偽共起の発生モデル（Q1=B に基づく）

**設定**: 1 トランザクション = 1 顧客の 1 日分の購買記録
同一顧客が同日に**複数回**購買し、それが 1 トランザクションに集約されることで偽共起が生じる。

```
顧客が1日に3回来店:
  来店1（バスケット B1）: {牛乳, パン}
  来店2（バスケット B2）: {ビール, ポテチ}
  来店3（バスケット B3）: {シャンプー}

→ トランザクション T: {牛乳, パン, ビール, ポテチ, シャンプー}

従来法: 牛乳-ビール, 牛乳-ポテチ, パン-ビール … すべてが「共起」とみなされる（偽共起）
Phase1:  牛乳-パン のみが「共起」（バスケット B1 内）
```

### 1.2 生成モデルの仕様

#### 1.2.1 アイテムモデル

アイテムを **G カテゴリ** に分類する。各カテゴリ内で共起が強く、カテゴリ間では共起が弱い。

| パラメータ | 記号 | 説明 |
|-----------|------|------|
| 総アイテム数 | `N_items` | 全アイテムの語彙サイズ |
| カテゴリ数 | `G` | アイテムをグループ化するカテゴリ数 |
| アイテム人気度 | Zipf(α) | 人気アイテムほど頻繁に出現（α=1.2 程度） |
| カテゴリ内集中度 | `p_same` | バスケット内で同一カテゴリから選ぶ確率 |

#### 1.2.2 トランザクション生成プロセス

```
for t in 1..N_transactions:
    M ~ Poisson(λ_visits)  # 1日の来店回数（バスケット数）
    M = max(M, 1)

    for m in 1..M:  # 各バスケット
        K ~ Poisson(λ_basket_size)  # バスケット内アイテム数
        K = max(K, 1)

        # メインカテゴリを選択
        c_main ~ Categorical(customer_preference)

        # アイテムをサンプリング（p_same の確率で同一カテゴリから）
        for k in 1..K:
            if random() < p_same:
                item ~ Categorical(items_in_category[c_main], weights=Zipf)
            else:
                item ~ Categorical(all_items, weights=Zipf)
```

#### 1.2.3 Ground Truth の定義

生成過程から正確に計算できる:

```
true_support(S)  = バスケット単位での {S の全アイテムが共起} の回数
txn_support(S)   = トランザクション単位での {S の全アイテムが共起} の回数
spurious(S)      = true_support(S) < min_support ≤ txn_support(S)
                   （従来法では検出されるが、実際はバスケット横断の偽共起）
```

### 1.3 評価指標（Q2 の候補・検討中）

#### 候補 M1: 偽共起パターン率（Spurious Pattern Rate, SPR）

```
SPR = |{S : spurious(S) = true}| / |{S : txn_support(S) ≥ min_support}|
    = 従来法が検出するパターンのうち、偽共起パターンの割合
```

- **解釈**: SPR が高いほど従来法は信頼できない
- **Phase 1 の SPR**: 定義上 = 0（常に basket-level support で判定するため）
- **論文での使い方**: λ_visits を上げると SPR が単調増加することを示す

#### 候補 M2: 真パターン再現率（True Pattern Recall, TPR）

```
TPR = |{S : true_support(S) ≥ min_support かつ Phase1 が検出}|
    / |{S : true_support(S) ≥ min_support}|
    = Phase 1 が真に頻出なパターンをどれだけ拾えているか
```

- **解釈**: Phase 1 の「漏れ」を測る
- **期待値**: 理論上 1.0（Phase 1 は true_support で判定するため）
- **論文での使い方**: Phase 1 がパターンを見落とさないことの確認

#### 候補 M3: 密集区間の純度（Interval Purity）

```
basin_count(I, S)  = 区間 I 内でのバスケット単位の支持度カウント
Purity(I, S)       = basin_count(I, S) / txn_count(I, S)

Interval Purity    = 検出全区間の Purity の平均
```

- **解釈**: 密集区間を構成する共起がどの程度「本物」か
- **論文での使い方**: 従来法の区間は Purity < 1（混入あり）、Phase 1 は Purity = 1

**※ M1 と M3 を中心指標として採用することを推奨（Q2 として要確認）**

### 1.4 実験設計マトリクス

#### 実験 A1：λ_visits の影響（RQ1 の主実験）

| 固定パラメータ | 値 |
|--------------|---|
| `N_transactions` | 10,000 |
| `N_items` | 200 |
| `G` | 10 |
| `min_support` | 50 |
| `window_size` | 500 |
| `max_length` | 4 |
| random seeds | 5本（安定性確認） |

| 変化パラメータ | 設定値 |
|--------------|-------|
| `λ_visits` | 1.0, 1.5, 2.0, 3.0, 5.0 |

**期待される結果**:

```
λ=1.0: SPR = 0（全員が1回のみ来店 → 従来法でも偽共起なし）
λ=2.0: SPR > 0（偽共起が発生し始める）
λ=5.0: SPR が顕著に上昇（従来法の問題が明確化）
Phase 1: SPR = 0 を λ に関わらず維持
```

#### 実験 A2：カテゴリ構造の影響（RQ1 の補足実験）

λ_visits=2.0 に固定し、カテゴリ数 G を変化させる。
G が小さい（カテゴリ境界が曖昧）ほど偽共起が増えることを示す。

| 変化パラメータ | 設定値 |
|--------------|-------|
| `G` | 3, 5, 10, 20, 50 |

#### 実験 A3：スケーラビリティ（RQ4）

λ_visits=2.0、G=10 に固定し、データ規模を変化させる。

| 変化パラメータ | 設定値 |
|--------------|-------|
| `N_transactions` | 1,000 / 10,000 / 100,000 / 1,000,000 |

**計測対象**:
- Rust `--release` での実行時間
- Python での実行時間（10万まで）
- Python vs Rust のスピードアップ比

### 1.5 合成データファイル構成

```
dataset/
  synthetic/
    gen_synthetic.py           ← 生成スクリプト（実装予定）
    gen_config_A1.json         ← 実験 A1 用パラメータ設定
    gen_config_A2.json         ← 実験 A2 用パラメータ設定
    gen_config_A3.json         ← 実験 A3 用パラメータ設定
    output/
      A1_lambda_1.0_seed0.txt
      A1_lambda_2.0_seed0.txt
      ...
    ground_truth/
      A1_lambda_1.0_seed0_gt.json   ← true_support / txn_support の記録
      ...
```

#### ground_truth フォーマット（案）

```json
{
  "n_transactions": 10000,
  "lambda_visits": 2.0,
  "true_frequent_patterns": [
    {"itemset": [1, 5, 12], "true_support": 73, "txn_support": 95},
    ...
  ],
  "spurious_patterns": [
    {"itemset": [1, 8], "true_support": 30, "txn_support": 55},
    ...
  ]
}
```

---

## 2. Stage B：UCI Online Retail II 実験

### 2.1 データ概要

| 項目 | 内容 |
|------|------|
| URL | https://archive.uci.edu/dataset/502/online+retail+ii |
| 期間 | 2009-12〜2011-12（約2年） |
| 行数 | 約 100 万行 |
| 主要列 | InvoiceNo, StockCode, Quantity, InvoiceDate, CustomerID |
| ライセンス | CC BY 4.0（引用可） |

### 2.2 前処理方針（入力フォーマット変換）

**バスケットの定義**: `InvoiceNo`（1回の購買）
**トランザクションの定義**: `CustomerID × 日付`（同一顧客・同日の全購買を1トランザクションに集約）

```
前処理ステップ:
1. キャンセル行を除外（InvoiceNo が 'C' で始まる行）
2. CustomerID が欠損の行を除外
3. Quantity ≤ 0 の行を除外
4. InvoiceDate から 日付（date）を抽出
5. グループキー = (CustomerID, date) → トランザクションID を採番
6. InvoiceNo をバスケットID として採番（グローバル連番）
7. バスケット構造付き入力形式に変換:
   CustomerID=12345, date=2010-01-05, baskets=[
     InvoiceNo=536365 → {85123A, 71053, ...}
     InvoiceNo=536366 → {84406B, ...}
   ]
   → 出力行: "85123A 71053 | 84406B ..."
8. タイムスタンプ = トランザクションIDの連番（整数）
```

**注意点**:
- 同一顧客・同日に複数 InvoiceNo がある場合 → バスケットが複数 → 偽共起の源泉
- InvoiceNo が1件のみの場合 → バスケット1個 → 従来法と Phase 1 で差が出ない

### 2.3 実験設計マトリクス

#### 実験 B1：パラメータ感度（Phase 1 のみ）

| 変化パラメータ | 設定値 |
|--------------|-------|
| `min_support` | 10, 20, 50, 100, 200 |
| `window_size` | 30, 90, 180（日数換算） |

**計測対象**:
- 検出パターン数（items ≥ 2）
- 密集区間の総数
- 実行時間（Rust）

#### 実験 B2：従来法 vs Phase 1 の比較

固定パラメータ（`min_support=50, window_size=90`）で両手法を実行。

**比較内容**:
- 従来法が検出した追加パターン数（Phase 1 では検出されない）
- 代表的な「追加パターン」を人手で確認（偽共起か否かの妥当性確認）
- Stage A の SPR と対応させた考察

#### 実験 B3：スケーラビリティ（RQ4 の実データ版）

データを期間で切り取り、規模を変えて計測。

| 設定 | トランザクション数（概算） |
|------|------------------------|
| 1ヶ月分 | 〜4万 |
| 6ヶ月分 | 〜24万 |
| 12ヶ月分 | 〜48万 |
| 全期間 | 〜96万 |

### 2.4 前処理スクリプト構成

```
dataset/
  uci_retail/
    preprocess_uci.py          ← 前処理スクリプト（実装予定）
    online_retail_II.xlsx      ← 元データ（ダウンロード後に配置）
    output/
      uci_basket.txt           ← 変換後の入力ファイル
      uci_basket_metadata.json ← 件数・期間・バスケット統計など
    settings/
      settings_B1_minsup10_w30.json
      ...
    results/
      B1_minsup10_w30/
        patterns.csv
      ...
    log.md                     ← 実験ログ
```

---

## 3. 全体の実験順序

```
Step 1  gen_synthetic.py の実装・動作確認（合成小規模データ）
Step 2  ground_truth 計算ロジックの実装・単体テスト
Step 3  実験 A1（λ_visits sweep, N=10K）の実行と SPR 計測
Step 4  実験 A2（G sweep）の実行
Step 5  実験 A3（スケール, 〜100万）の実行
Step 6  preprocess_uci.py の実装・UCI データの前処理
Step 7  実験 B1（パラメータ感度）の実行
Step 8  実験 B2（従来法 vs Phase 1 比較）の実行
Step 9  実験 B3（スケーラビリティ）の実行
Step 10 結果の図表化・考察
```

---

## 4. 未決定事項（要確認）

| 項目 | 現状 | 決める必要があるタイミング |
|------|------|--------------------------|
| **Q2: 主要評価指標** | M1(SPR) + M3(Interval Purity) を推奨 | Stage A 実装前 |
| **Q4: 乱数シード数** | 5本を想定 | Stage A 実装前 |
| `p_same`（カテゴリ内集中度）の値 | 0.7〜0.9 程度を想定 | 生成スクリプト実装前 |
| `λ_basket_size`（バスケット内アイテム数の平均）の値 | 3〜5 程度を想定 | 生成スクリプト実装前 |
| UCI の `window_size` の時間単位 | 日数で管理（30/90/180 日）を想定 | B1 実装前 |

---

## 5. 論文上の位置づけ

| 実験 | 論文セクション（想定） | 主張 |
|------|---------------------|------|
| A1 | 提案手法の評価（合成） | Phase 1 は λ に関わらず偽共起を排除する |
| A2 | 提案手法の評価（合成） | カテゴリ構造が明確なほど偽共起抑制の恩恵が大きい |
| A3 | スケーラビリティ | Rust 実装は 100 万トランザクションでも実用的 |
| B1 | 実データ評価 | パラメータ感度と出力特性 |
| B2 | 実データ評価 | 従来法との比較（定性）+ SPR の実データでの推定 |
| B3 | スケーラビリティ（実データ） | 実購買データでの実行時間 |
