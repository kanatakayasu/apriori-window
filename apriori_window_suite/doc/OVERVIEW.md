# apriori_window_suite — バスケット構造対応 Apriori ウィンドウ法

Phase 1（密集区間検出）と Phase 2（イベント時間的関係付け）を統合した実装スイート。

上位ドキュメント: [`README.md`](../../README.md)
詳細設計書: [`phase1_impl_plan.md`](./phase1_impl_plan.md) / [`phase2_impl_plan.md`](./phase2_impl_plan.md)

---

## プロジェクト概要

### 何をするシステムか

トランザクション列（購買履歴等）に Apriori + スライディングウィンドウを適用し、
**「どのアイテムセットが、いつ集中して出現していたか」** を密集区間として出力する。
さらに、その密集区間を外部イベント（セール・キャンペーン等）と時間的に照合し、
どのような関係（直前・包含・重複など）にあるかを列挙する。

### 解決している 2 つの課題

**課題① (Phase 1)：バスケット構造の無視による偽共起**

従来手法は「同一トランザクション内にあれば共起」とみなすが、
1 トランザクション内に複数の独立した購入単位（バスケット）が混在する場合、
異なるバスケットのアイテム間に偽の共起関係が生まれる。

→ 共起定義を「**同一バスケット内での共起**」に変更して解決。

`1 2 | 3` というトランザクションでは、{1,2} は共起するが {1,3} と {2,3} は共起しない。

**課題② (Phase 2)：密集区間と外部イベントの関連付け**

密集区間が「なぜ生じたか」を外部から説明できない。

→ 外部イベントリスト（JSON）と照合し、以下 6 種の時間的関係を列挙して解決。

---

## ファイル構成

```
apriori_window_suite/
  Cargo.toml                         ← Rust クレート設定（[lib] + [[bin]]）
  src/
    lib.rs                           ← Rust ライブラリ（pub use ハブ）
    main.rs                          ← Rust CLI（cargo run --release -- phase1|phase2）
    apriori.rs                       ← Apriori 探索（find_dense_itemsets）
    basket.rs                        ← バスケットマップ構築
    correlator.rs                    ← Phase 2 時間的関係マッチング
    interval.rs                      ← 密集区間計算（スタックケース修正済み）
    io.rs                            ← 入出力
    util.rs                          ← ユーティリティ（二分探索・積集合）
  python/
    apriori_window_basket.py         ← Python Phase 1 実装
    event_correlator.py              ← Python Phase 2 実装
    tests/
      test_basket.py                 ← Phase 1 pytest テスト（24件）
      test_correlator.py             ← Phase 2 pytest テスト（40件）
  data/
    sample_basket.txt                ← サンプル入力データ（バスケット構造付き）
    sample_events.json               ← サンプルイベントファイル
    settings.json                    ← Rust CLI デフォルト設定（Phase 1）
    settings_phase1.json             ← Python Phase 1 デフォルト設定
    settings_phase2.json             ← Python Phase 2 デフォルト設定
  doc/
    README.md                        ← このファイル
    impl_log.md                      ← 実装ログ（セッション引き継ぎ用）
    phase1_impl_plan.md              ← Phase 1 詳細設計書
    phase2_impl_plan.md              ← Phase 2 詳細設計書
```

---

## 実装言語

各フェーズとも **Python（プロトタイプ）→ Rust（高速化移植）** の二段構成。

| | Python | Rust |
|--|--------|------|
| Phase 1 | `python/apriori_window_basket.py` | `src/apriori.rs` + `src/basket.rs` 等 |
| Phase 2 | `python/event_correlator.py` | `src/correlator.rs` |

### Rust の高速化ポイント

- **二分探索**（lower_bound / upper_bound）でウィンドウカウントを O(log n) に削減
- **rayon** による並列処理（単体アイテム評価・multi-item 候補評価・match_all）
- **BufWriter** による高速出力
- **候補区間スキップ**（recorded 区間によるループ削減）

---

## 入力ファイル形式

### トランザクションファイル（`.txt`）

1 行 = 1 トランザクション。` | `（スペース付きパイプ）でバスケットを区切る。

| 形式 | 例 | 意味 |
|------|----|------|
| バスケットなし（旧フォーマット互換） | `1 2 3` | 1つのバスケットに 1, 2, 3 |
| 2バスケット | `1 2 \| 3 4` | バスケット1: {1,2}、バスケット2: {3,4} |
| 3バスケット | `1 2 \| 3 \| 4 5` | バスケット1: {1,2}、バスケット2: {3}、バスケット3: {4,5} |
| 空行 | | 空トランザクション |

`|` を含まない行は単一バスケットとして扱う（旧フォーマット後退互換）。

**サンプル (`data/sample_basket.txt`)**:
```
1 2 | 3 4
1 2 | 3 4
1 2 | 3 4
2 3 | 1 4
2 3 | 1 4
```

### イベントファイル（`.json`）

```json
[
  {"event_id": "event_A", "name": "イベントA", "start": 3, "end": 4},
  {"event_id": "event_B", "name": "イベントB", "start": 6, "end": 10}
]
```

`start`/`end` はトランザクション ID（0-indexed）と同じ軸。`event_id` は一意であること。

### 設定ファイル（`settings.json`）

**Phase 1 のみ**（`event_file` を省略）:

```json
{
  "input_file": { "dir": "/path/to/data", "file_name": "transactions.txt" },
  "output_files": {
    "dir": "/path/to/output",
    "patterns_output_file_name": "result.csv"
  },
  "apriori_parameters": { "window_size": 3, "min_support": 2, "max_length": 3 }
}
```

**Phase 2 も含む**（`event_file` を追加）:

```json
{
  "input_file": { "dir": "/path/to/data", "file_name": "transactions.txt" },
  "event_file": { "dir": "/path/to/data", "file_name": "events.json" },
  "output_files": {
    "dir": "/path/to/output",
    "patterns_output_file_name": "patterns.csv",
    "relations_output_file_name": "relations.csv"
  },
  "apriori_parameters": { "window_size": 3, "min_support": 2, "max_length": 3 },
  "temporal_relation_parameters": { "epsilon": 2, "d_0": 1 }
}
```

| パラメータ | 型 | 説明 |
|------------|-----|------|
| `window_size` | 整数 | スライディングウィンドウの幅（トランザクション数） |
| `min_support` | 整数 | 密集区間とみなす最低共起回数 |
| `max_length` | 整数 | 探索するアイテムセットの最大要素数 |
| `epsilon` | 整数 | 時間的関係の許容誤差（トランザクション数） |
| `d_0` | 整数 | Overlaps の最小重複長 |

---

## 実行方法

### Rust CLI

```bash
cd /path/to/apriori_window/apriori_window_suite

# Phase 1（デフォルト設定: data/settings.json）
cargo run --release -- phase1

# Phase 2（settings_phase2.json を指定）
cargo run --release -- phase2 data/settings_phase2.json

# リリースビルド後に実行
cargo build --release
./target/release/apriori_window_suite phase1 path/to/settings.json
```

性能比較時は `debug`（`cargo run`）を混ぜず、必ず `--release` で揃えること。

### Python

標準ライブラリのみ使用（追加インストール不要）。

```bash
cd /path/to/apriori_window

# Phase 1（デフォルト設定: data/settings_phase1.json）
python3 apriori_window_suite/python/apriori_window_basket.py

# Phase 2（デフォルト設定: data/settings_phase2.json）
python3 apriori_window_suite/python/event_correlator.py

# 設定ファイルを明示指定
python3 apriori_window_suite/python/apriori_window_basket.py path/to/settings.json
python3 apriori_window_suite/python/event_correlator.py path/to/settings.json
```

---

## テスト

### Rust

```bash
cd /path/to/apriori_window/apriori_window_suite
cargo test
# → 58 passed（lib: 54、main E2E: 4）
```

### Python

```bash
cd /path/to/apriori_window
python3 -m pytest apriori_window_suite/python/tests/ -v
# → Phase 1: 24 passed、Phase 2: 40 passed
```

### テストケース概要

| 対象 | テストクラス / モジュール | 件数 | 内容 |
|------|--------------------------|------|------|
| Phase 1 (Python) | `TestReadTransactionsWithBaskets` | 5 | パーサー単体テスト |
| | `TestComputeItemBasketMap` | 3 | マップ構築テスト |
| | `TestBasketIdsToTransactionIds` | 3 | basket→transaction 変換 |
| | `TestComputeDenseIntervalsStackCase` | 3 | スタックケース直接テスト |
| | `TestBackwardCompatibility` | 1 | 旧フォーマット後退互換 |
| | `TestFalseCooccurrenceEliminated` | 2 | 偽共起の排除 |
| | `TestStackCaseViaFindDenseItemsets` | 1 | スタックケース（E2E） |
| | `TestStackThenContinue` | 2 | スタック後に密集継続 |
| | `TestEdgeCases` | 3 | 空行・エッジケース |
| | `TestExistingDataConsistency` | 1 | 既存データとの照合 |
| Phase 2 (Python) | `TestSatisfiesFollows/Contains/Overlaps` | 20 | 判定ロジック単体 |
| | `TestMatchAll` | 10 | match_all 総当たり |
| | `TestReadEvents` / `TestWriteRelationsCsv` | 6 | I/O テスト |
| | `TestRunFromSettings` | 4 | E2E テスト |
| Phase 1 (Rust) | `basket`, `apriori`, `interval`, `io` | 54 | ライブラリ単体テスト |
| Phase 2 (Rust) | `correlator`, `io` | （上記に含む） | — |
| E2E (Rust) | `main::tests` | 4 | run_phase1 / run_phase2 |

---

## 出力ファイル形式

### patterns.csv（Phase 1 出力）

要素数 ≥ 2 のアイテムセットのみ出力する。

```
pattern_components,pattern_gaps,pattern_size,intervals_count,intervals
"[{1, 2}]","[]",2,1,"(0,2)"
"[{1, 2, 3}]","[]",3,2,"(0,3);(5,8)"
```

| カラム | 説明 |
|--------|------|
| `pattern_components` | アイテムセット（`[{a, b}]` 形式） |
| `pattern_gaps` | 将来拡張用（現状は常に `[]`） |
| `pattern_size` | アイテムセットの要素数 |
| `intervals_count` | 密集区間の個数 |
| `intervals` | 密集区間リスト `(start,end)` のセミコロン区切り |

密集区間 `(start, end)` の `start`/`end` はトランザクション ID（0-indexed）。

### relations.csv（Phase 2 出力）

```
pattern_components,dense_start,dense_end,event_id,event_name,relation_type,overlap_length,epsilon,d_0
"[{1, 2}]",0,5,event_A,イベントA,DenseFollowsEvent,,2,1
"[{1, 2}]",0,5,event_B,イベントB,DenseOverlapsEvent,3,2,1
```

---

## 時間的関係の定義（Phase 2）

密集区間を `I = (ts_i, te_i)`、外部イベントを `J = (ts_j, te_j)`、
許容誤差を ε、最小重複長を d_0 とする。

| 関係名 | 略称 | 条件 |
|--------|------|------|
| DenseFollowsEvent | DFE | `te_i − ε ≤ ts_j ≤ te_i + ε`（密集直後にイベント開始） |
| EventFollowsDense | EFD | `te_j − ε ≤ ts_i ≤ te_j + ε`（イベント直後に密集開始） |
| DenseContainsEvent | DCE | `ts_i ≤ ts_j ∧ te_i + ε ≥ te_j`（密集がイベントを包含） |
| EventContainsDense | ECD | `ts_j ≤ ts_i ∧ te_j + ε ≥ te_i`（イベントが密集を包含） |
| DenseOverlapsEvent | DOE | `ts_i < ts_j ∧ te_i − ts_j ≥ d_0 − ε ∧ te_i < te_j + ε` |
| EventOverlapsDense | EOD | `ts_j < ts_i ∧ te_j − ts_i ≥ d_0 − ε ∧ te_j < te_i + ε` |

同一ペアで複数の関係が成立する場合は全て出力する（排他にしない）。

---

## アルゴリズム概要

### データフロー

```
入力ファイル（" | " でバスケット区切り）
  ↓ read_transactions_with_baskets
transactions[t][b][i]
  ↓ compute_item_basket_map
  ├─ item_basket_map      # item → basket_id リスト（共起判定）
  ├─ basket_to_transaction # basket_id → transaction_id
  └─ item_transaction_map  # item → transaction_id リスト（単体密集区間）
  ↓ intersect_sorted_lists（basket_id で積集合）
co_basket_ids
  ↓ basket_ids_to_transaction_ids（重複を保持）
co_occurrence_timestamps   # 重複あり（バスケット粒度）
  ↓ compute_dense_intervals_with_candidates（スタックケース修正済み）
dense_intervals
  ↓ match_all（Phase 2 のみ）
relations
```

### スタックケース（重要な修正点）

バスケット粒度でカウントするため、同一トランザクション ID が複数回出現しうる。
これを naive にストライド調整すると無限ループが発生する。

```python
# count > threshold のとき
surplus = count - threshold
next_l = window_occurrences[surplus]
if next_l > l:
    l = next_l   # 通常：surplus 分ジャンプ
else:
    l += 1       # スタック：window_occurrences[surplus] == l → 1トランザクション前進
```

スタックが起きる条件：左端の transaction_id の出現数が surplus 以上のとき
（= 窓の右側にある共起バスケット数が threshold を下回る状態）。

---

## 全体ロードマップ

```
Phase 1: バスケット構造対応          ✅ 完了
  ├── Python 実装・テスト（24 passed）
  └── Rust 移植・テスト（54 passed）

Phase 2: イベント関連付け             ✅ 完了
  ├── Python 実装・テスト（40 passed）
  └── Rust 移植・テスト（上記に含む）

Phase 3: 実データ検証                 🔲 未着手
  ├── 公開データセットの選定（→ doc/dataset.md）
  ├── 擬似データでの動作確認
  └── 実データへの適用

Future Work                           🔲 未着手
  ├── 有意性評価（統計検定 / permutation test）
  ├── 大規模データへの近似解法
  └── イベント自動検出（異常検知との統合）
```

---

## 推奨データセット

詳細は [`doc/dataset.md`](../../doc/dataset.md) を参照。

| 優先度 | データセット | 理由 |
|--------|-------------|------|
| 第1推薦 | **Dunnhumby Complete Journey** | basket_id・2年間・プロモーション情報あり |
| 第2推薦 | **UCI Online Retail II** | 登録不要・即ダウンロード・約100万行 |
| イベント重視 | **IJCAI-15 Tmall** | Double 11（独身の日）前後データあり |
