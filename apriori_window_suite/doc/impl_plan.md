# 実装方針

課題・方向性の詳細は [new_change.md](./new_change.md) を参照。

---

## 設計上の決定事項

| 問題 | 決定内容 |
|------|---------|
| バスケット分割情報の出所 | **入力データ側で保持**（パーサーで読み取る） |
| ε（時間的許容誤差）の決め方 | **`settings.json` にパラメータとして追加** |
| d_0（Overlaps 最小重複長）の決め方 | **`settings.json` にパラメータとして追加** |
| Phase 1 と Phase 2 の順序 | **Phase 1 を完全実装してから Phase 2 に着手** |
| 実装言語 | **Pythonでプロトタイプ → Rust移植** |

---

## Phase 1：バスケット構造対応（課題①）

### 入力フォーマット変更

```
# 現状（1行=1トランザクション、スペース区切りアイテム）
1 2 3

# 新フォーマット（バスケットを "|" で区切る）
1 2 | 3

# 複数バスケットの例
1 2 | 3 4 | 5
```

バスケット分割情報は入力データ側で保持し、パーサーで読み取る。

### データ構造

```
# バスケットID → トランザクションIDのマップ（配列で実装）
basket_to_transaction: List[TransactionId]

# アイテム → 出現バスケットIDリスト（ソート済み・一意）
item_basket_map: Dict[Item, List[BasketId]]

# アイテムセットの共起タイムスタンプ = basket_id リストの積集合
# → basket_to_transaction で変換 → transaction_id リスト（重複あり・バスケット粒度）

# アイテム → 出現トランザクションIDリスト（重複なし・単体アイテムの密集区間用）
item_transaction_map: Dict[Item, List[TransactionId]]
```

### 変更が必要なコンポーネント

1. **入力パーサー**（`read_text_file_as_2d_vec_of_integers`）
   - 1行をバスケットリスト（`Vec<Vec<i64>>`）に変換する形式に変更

2. **タイムスタンプマップ構築**（`compute_item_timestamps_map` → `compute_item_basket_map`）
   - `item_basket_map`, `basket_to_transaction`, `item_transaction_map` を一括生成

3. **共起タイムスタンプの計算**（`intersect_sorted_lists` の呼び出し箇所）
   - 現状: 各アイテムの「出現トランザクションID」リストの積集合
   - 新手法: 各アイテムの「バスケットID」リストの積集合 → transaction_id に変換（重複保持）

4. **ストライド調整**（`compute_dense_intervals` / `compute_dense_intervals_with_candidates`）
   - count > threshold のとき `window_occurrences[surplus] == l` になるスタックケースが発生しうる
   - スタック時は `l += 1`（count == threshold と同じ処理）にフォールバック
   - 重複タイムスタンプ（バスケット粒度）を正しく扱うために必要

### 実装ステップ

1. [ ] パーサー実装（サブバスケット分離 → `List[List[List[int]]]`）
2. [ ] バスケットID採番（グローバル連番）とマップ構築（`compute_item_basket_map`）
3. [ ] `basket_ids_to_transaction_ids` 実装（重複保持）
4. [ ] `compute_dense_intervals` / `compute_dense_intervals_with_candidates` のスタックケース修正
5. [ ] `find_dense_itemsets` 内の共起タイムスタンプ計算を変更
6. [ ] テストデータ（バスケット構造あり）の作成・動作確認（Python）
7. [ ] Rust移植

---

## Phase 2：イベント関連付け（課題②）

### イベントデータの入力フォーマット

```json
[
  {"event_id": "live_2024_01", "name": "アイドルライブ", "start": 100, "end": 105},
  {"event_id": "promo_001",    "name": "ガム棚配置",    "start": 200, "end": 300}
]
```

### settings.json 拡張（Phase 2 以降）

```json
{
  "input_file": { "dir": "...", "file_name": "..." },
  "event_file": { "dir": "...", "file_name": "..." },
  "output_files": { "dir": "...", "patterns_output_file_name": "..." },
  "apriori_parameters": {
    "window_size": 10,
    "min_support": 3,
    "max_length": 5
  },
  "temporal_relation_parameters": {
    "epsilon": 2,
    "d_0": 3
  }
}
```

### アルゴリズム（ブルートフォース）

```
for each (itemset, dense_intervals) in frequents:
  for each dense_interval (ts_i, te_i):
    for each event (ts_j, te_j):
      for each relation_type in [Follows, Contains, Overlaps]:
        if satisfies_relation(ts_i, te_i, ts_j, te_j, ε, d_0):
          output(itemset, dense_interval, event, relation_type)
```

**計算量**: O(|frequents| × |dense_intervals_per_itemset| × |events|) → イベント数が少なければ実用的

### 出力フォーマット

```csv
pattern_components,dense_interval,event_id,relation_type,epsilon
"{1, 2}","(100,200)","live_2024_01","Follows",5
"{3}","(200,300)","promo_001","Contains",0
```

### 実装ステップ

1. [ ] イベントデータパーサー実装
2. [ ] 時間的関係判定ロジック（`satisfies_follows`, `satisfies_contains`, `satisfies_overlaps`）実装
3. [ ] ブルートフォースマッチング実装（全密集区間 × 全イベント）
4. [ ] 出力フォーマット実装・動作確認（Python）
5. [ ] Rust移植

---

## 全体ロードマップ

```
Phase 1: バスケット構造対応
  ├── パーサー実装（Python）
  ├── 共起タイムスタンプ計算の変更（Python）
  ├── テスト・動作確認
  └── Rust移植

Phase 2: イベント関連付け
  ├── イベントデータパーサー（Python）
  ├── 時間的関係判定ロジック（Python）
  ├── ブルートフォースマッチング（Python）
  ├── 動作確認
  └── Rust移植

Phase 3: 実データ検証
  ├── 公開データセットの調査・選定
  ├── 擬似データセットでの動作確認
  └── 澪標ECデータへの適用

Future Work
  ├── 有意性評価（統計検定 / permutation test）
  ├── 大規模データへの近似解法
  └── イベント自動検出（異常検知との統合）
```
