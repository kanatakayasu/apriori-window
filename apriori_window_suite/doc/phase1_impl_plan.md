# Phase 1 実装計画：バスケット構造対応

上位方針: [doc/impl_plan.md](./doc/impl_plan.md) / 課題背景: [doc/new_change.md](./doc/new_change.md)

---

## 密集の意味論：バスケット粒度での計数

### 重複タイムスタンプは「バグ」ではなく「設計」

バスケット拡張後、`basket_ids_to_transaction_ids` を経由して得られる
多アイテム共起のタイムスタンプリストには、同一 transaction_id が複数回出現しうる。

```
例: トランザクション5 に 5つのバスケットがあり、全てで {1,2} が共起する場合
  basket_ids = [0, 1, 2, 3, 4]  (全てトランザクション5に属する)
  basket_to_transaction = [5, 5, 5, 5, 5]
  → co_occurrence_timestamps = [5, 5, 5, 5, 5]  ← 重複あり・これが正しい
```

これは「密集 = 多バスケットでの共起が集中している」というバスケット粒度の定義を
そのまま反映したものである。重複除去して1回にしてしまうと、
「同一トランザクション内で複数バスケットにまたがって共起する」という情報が失われる。

### ストライド調整の問題と修正方針

現状の `compute_dense_intervals` のストライド調整は、
タイムスタンプが一意であることを暗黙の前提としている。

```python
# count > threshold のとき
surplus = count - threshold
l = window_occurrences[surplus]   # ← 一意でないと l が前進しない場合がある
```

重複タイムスタンプがある場合の「スタック」シナリオ：

```
timestamps = [5, 5, 5, 5, 5, 8, 12]  (transaction_id=5 が5回)
threshold = 3, window_size = 10

l=5 のとき:
  window_occurrences = [5, 5, 5, 5, 5, 8, 12], count=7, surplus=4
  l = window_occurrences[4] = 5  ← l が動かない → 無限ループ
```

スタックが起きる条件：左端の transaction_id の出現数 k が surplus を超えるとき
（= `window_occurrences[surplus] == l`）。
これは「窓の右側にある共起バスケット数が threshold を下回る」状態を意味する。

**修正方針：スタック時は `l += 1`（count == threshold と同じ処理）にフォールバック**

```
l += 1 にすると:
  - 左端の transaction_id = 5 に属するバスケット(5個)が全て窓外に落ちる
  - 右端から新たなバスケットが入れば密集継続、入らなければ次イテレーションで区間終了
  - l は必ず前進する → 無限ループ解消
```

検証：

```
timestamps = [5, 5, 5, 5, 5, 8, 12]  threshold=3, window_size=10

l=5: count=7, surplus=4, window_occurrences[4]=5 → スタック → l += 1 → l=6
l=6: window=[6,16], occurrences=[8,12], count=2 < threshold → 密集区間終了 ✓

timestamps = [5, 5, 5, 5, 5, 8, 12, 16]  threshold=3, window_size=10

l=5: count=7, surplus=4, スタック → l += 1 → l=6
l=6: window=[6,16], occurrences=[8,12,16], count=3 == threshold → 密集継続 ✓
     (右端から16が入り密集が続く)
```

### 各ケースの変更要否まとめ

| ケース | 処理 | 変更 | 理由 |
|--------|------|------|------|
| count < threshold | `l = bisect_right` で次へジャンプ | 不要 | `bisect_right` が左端の重複を全スキップ |
| count == threshold | `l += 1` | 不要 | 左端の全バスケットが窓外へ落ち次イテレーションで判定 |
| count > threshold（非スタック） | `l = window_occurrences[surplus]` | 不要 | `window_occurrences[surplus] > l` が保証される |
| count > threshold（スタック） | ~~`l = window_occurrences[surplus]`~~ | **必要** | `l += 1` にフォールバック |

この修正は `compute_dense_intervals` と `compute_dense_intervals_with_candidates` の両方に適用する。
修正はタイムスタンプが一意の場合（旧フォーマット）にも無害（スタック条件が成立しないため）。

---

## 変更の全体像

### 変更の本質

現状の「同一トランザクションに出現 = 共起」を「同一バスケットに出現 = 共起」に変える。
合わせて `compute_dense_intervals` 系関数のストライド調整にスタックケースの場合分けを追加する。

### 変更前後のデータフロー対比

```
【変更前】
入力ファイル（1行=1トランザクション=アイテムID列）
  ↓ read_text_file_as_2d_vec_of_integers
transactions: List[List[int]]
  ↓ compute_item_timestamps_map
item_timestamps: Dict[item, List[transaction_id]]  ← 一意
  ↓ intersect_sorted_lists（multi-itemの場合）
co_occurrence_timestamps: List[transaction_id]     ← 一意
  ↓ compute_dense_intervals_with_candidates
dense_intervals

【変更後】
入力ファイル（1行=1トランザクション、"|"でバスケット区切り）
  ↓ read_transactions_with_baskets  ★新規
transactions: List[List[List[int]]]
  ↓ compute_item_basket_map  ★新規
item_basket_map:      Dict[item, List[basket_id]]         ← 共起判定に使う
basket_to_transaction: List[transaction_id]                ← basket_id → transaction_id
item_transaction_map: Dict[item, List[transaction_id]]     ← 一意・単体アイテムの密集区間用
  ↓ intersect_sorted_lists（multi-itemの場合）★呼び出し対象を変更
co_basket_ids: List[basket_id]
  ↓ basket_ids_to_transaction_ids  ★新規（重複あり・バスケット粒度を保持）
co_occurrence_timestamps: List[transaction_id]             ← 重複あり（バスケット粒度）
  ↓ compute_dense_intervals_with_candidates  ★ストライド調整を修正
dense_intervals
```

---

## 入力フォーマット仕様（確定版）

```
# 1行 = 1トランザクション
# バスケット区切り = " | "（スペース付きパイプ）
# アイテムID = 整数（スペース区切り）

# 例1: バスケットなし（旧フォーマット互換、単一バスケットとして扱う）
1 2 3

# 例2: 2バスケット
1 2 | 3

# 例3: 3バスケット
1 2 | 3 4 | 5

# 例4: 空行（空トランザクション、現状同様に許容）
（空行）
```

`|` を含まない行は **バスケット数=1のトランザクション** として解釈する。
旧フォーマットのファイルをそのまま読み込んでも動作する。

---

## データ構造

### 新規追加

```python
basket_to_transaction: List[int]
# basket_to_transaction[basket_id] = transaction_id
# basket_id の採番順 = トランザクション順 × バスケット順 なので単調非減少

item_basket_map: Dict[int, List[int]]
# item → 出現basket_idリスト（ソート済み・一意）
# multi-item共起タイムスタンプ算出の基盤

item_transaction_map: Dict[int, List[int]]
# item → 出現transaction_idリスト（重複なし・ソート済み）
# 単体アイテムの密集区間算出・singleton_intervals に使う（旧 item_timestamps_map 相当）
```

### 変更なし

```python
dense_intervals: List[Tuple[int, int]]               # (transaction_id, transaction_id) のまま
frequents: Dict[Tuple[int,...], List[Tuple[int,int]]] # 出力フォーマット変わらず
```

---

## 関数一覧

### 新規追加

| 関数名 | 役割 |
|--------|------|
| `read_transactions_with_baskets` | バスケット構造付きトランザクションファイルを読み込む |
| `compute_item_basket_map` | `item_basket_map`, `basket_to_transaction`, `item_transaction_map` を一括生成 |
| `basket_ids_to_transaction_ids` | basket_idリスト → transaction_idリストへ変換（重複あり・バスケット粒度を保持） |

### 変更あり

| 関数名 | 変更内容 |
|--------|---------|
| `compute_dense_intervals` | count > threshold のスタックケース（`l += 1`）を追加 |
| `compute_dense_intervals_with_candidates` | 同上 |
| `find_dense_itemsets` | 引数変更・multi-item共起タイムスタンプ計算を置き換え |

### 変更なし（そのまま流用）

| 関数名 | 理由 |
|--------|------|
| `intersect_sorted_lists` | basket_idリストの積集合にも同様に使える |
| `intersect_interval_lists` | 変更なし |
| `generate_candidates` | 変更なし |
| `prune_candidates` | 変更なし |

---

## 各関数の詳細仕様

### `read_transactions_with_baskets`

```python
def read_transactions_with_baskets(path: str) -> List[List[List[int]]]:
    """
    バスケット構造付きトランザクションファイルを読み込む。

    入力形式:
        1行 = 1トランザクション
        " | " でバスケットを区切る
        空行 = 空トランザクション（バスケット数0）

    返り値:
        transactions[t][b][i]
            t: トランザクションインデックス
            b: バスケットインデックス（トランザクション内）
            i: アイテムインデックス（バスケット内）

    後退互換:
        "|" を含まない行は単一バスケットのトランザクションとして扱う
    """
```

### `compute_item_basket_map`

```python
def compute_item_basket_map(
    transactions: List[List[List[int]]],
) -> Tuple[Dict[int, List[int]], List[int], Dict[int, List[int]]]:
    """
    アイテムのバスケット情報マップを構築する。

    basket_id 採番規則:
        トランザクション順 × バスケット順でグローバル連番
        → basket_to_transaction は単調非減少になる

    返り値:
        item_basket_map: Dict[item, List[basket_id]]
            アイテム → 出現basket_idリスト（ソート済み・一意）
            ※ 同一バスケット内に同じアイテムが複数あっても1回のみ記録

        basket_to_transaction: List[int]
            basket_to_transaction[basket_id] = transaction_id

        item_transaction_map: Dict[item, List[int]]
            アイテム → 出現transaction_idリスト（重複なし・ソート済み）
            ※ 単体アイテムの dense interval 計算と singleton_intervals に使う
            ※ 複数バスケットで同一アイテムが同一トランザクションに出ても1回のみ記録
    """
```

### `basket_ids_to_transaction_ids`

```python
def basket_ids_to_transaction_ids(
    basket_ids: List[int],
    basket_to_transaction: List[int],
) -> List[int]:
    """
    basket_idリストをtransaction_idリストに変換する（重複を保持）。

    前提:
        basket_ids はソート済み
        basket_to_transaction は単調非減少
        → 結果も自動的にソート済みになる

    重複の扱い:
        同一トランザクションの複数バスケットで共起する場合、
        transaction_id は出現バスケット数だけ繰り返す。
        これはバスケット粒度の密集計数を実現するための意図的な設計。
        → 重複除去は行わない

    compute_dense_intervals との連携:
        重複タイムスタンプを受け取った compute_dense_intervals は
        スタックケース（l += 1）によって正しく動作する。
    """
```

### `compute_dense_intervals` / `compute_dense_intervals_with_candidates`（変更箇所のみ）

count > threshold のブロック末尾のストライド調整部分を修正する。

```python
# 変更前:
surplus = count - threshold
l = window_occurrences[surplus]

# 変更後:
surplus = count - threshold
next_l = window_occurrences[surplus]
if next_l > l:
    l = next_l   # 非スタック：surplus分スキップして前進
else:
    l += 1       # スタック：window_occurrences[surplus] == l
                 # → count == threshold と同じく1トランザクション前進
                 # → 左端 transaction_id の全バスケットが窓外へ落ちる
                 # → 次イテレーションで count を再評価
```

この修正はタイムスタンプが一意の場合（旧フォーマット・単体アイテム計算）も無害。
一意タイムスタンプでは `window_occurrences[surplus] > l` が常に成り立つため
スタックケースが発火することはない。

### `find_dense_itemsets`（変更箇所のみ）

```python
# シグネチャ変更
# 変更前:
def find_dense_itemsets(
    transactions: Sequence[Iterable[int]], ...

# 変更後:
def find_dense_itemsets(
    transactions: List[List[List[int]]], ...  # ← ネスト1層増加
```

内部の変更は3箇所：

```python
# ① マップ構築（旧 compute_item_timestamps_map を置き換え）
# 変更前:
item_timestamps = compute_item_timestamps_map(transactions)

# 変更後:
item_basket_map, basket_to_transaction, item_transaction_map = compute_item_basket_map(transactions)

# ② multi-item候補のタイムスタンプ計算
# 変更前:
lists = [item_timestamps[item] for item in candidate]
timestamps = intersect_sorted_lists(lists)

# 変更後:
basket_id_lists = [item_basket_map[item] for item in candidate]
co_basket_ids = intersect_sorted_lists(basket_id_lists)
timestamps = basket_ids_to_transaction_ids(co_basket_ids, basket_to_transaction)
# ↑ 重複ありの transaction_id リスト（バスケット粒度）

# ③ 単体アイテムのタイムスタンプ
# 変更前:
timestamps = item_timestamps[item]

# 変更後:
timestamps = item_transaction_map[item]
# ↑ 重複なし（単体アイテムはトランザクション粒度のまま）
```

---

## テスト計画

### テストケース1：後退互換性（バスケット区切りなし）

```
# 入力（旧フォーマット）
1 2 3
1 2
2 3
1 2 3

# 期待値: 旧 apriori_window_pruned.py と同一の出力
# （旧フォーマット = 全行が単一バスケット = 重複タイムスタンプなし = スタック不発）
```

### テストケース2：バスケット分割で偽共起が消えること

```
# 入力
1 2 | 3
1 2 | 3
1 2 | 3

# 期待値:
# {1,2}: dense_intervals あり  ← 同一バスケット内共起
# {1,3}: dense_intervals なし  ← 別バスケットなので共起しない ★重要
# {2,3}: dense_intervals なし  ← 同上
```

### テストケース3：多バスケット共起でストライド調整のスタックケースが正しく動くこと

スタックケース（`window_occurrences[surplus] == l`）が発生し、
`l += 1` のフォールバックによって正しく処理されることを確認する。

```
# 入力: 各トランザクションに5バスケット、全バスケットで{1,2}が共起
1 2 | 1 2 | 1 2 | 1 2 | 1 2   ← transaction_id=0, basket_id=0..4
1 2 | 1 2 | 1 2 | 1 2 | 1 2   ← transaction_id=1, basket_id=5..9
1 2 | 1 2 | 1 2 | 1 2 | 1 2   ← transaction_id=2, basket_id=10..14

# {1,2} の co_occurrence_timestamps = [0,0,0,0,0, 1,1,1,1,1, 2,2,2,2,2]
# threshold=3, surplus=12とすると window_occurrences[12]=0 → スタック発生
# → l += 1 でフォールバック → 正常に区間計算が進む

# 期待値:
# テストがタイムアウトせずに完了すること
# {1,2} の dense_intervals が正しく返ること（無限ループにならないこと）
```

### テストケース4：スタックケース後に右端から新バスケットが入るケース

スタックから `l += 1` で抜けた後、右端からバスケットが入り密集継続する場合。

```
# {1,2} の co_occurrence_timestamps = [5,5,5,5,5, 8, 12, 16]
# threshold=3, window_size=10

# l=5: count=7, surplus=4, window_occurrences[4]=5 → スタック → l=6
# l=6: window=[6,16], occurrences=[8,12,16], count=3 == threshold → 密集継続
# → dense_intervals に (5付近, 16付近) が含まれること
```

### テストケース5：空行・空バスケットのエッジケース

```
（空行）
1 2
1 2

# 期待値: 旧アルゴリズムと同様に空トランザクションとして扱われる
```

### テストケース6：既存テストデータとの照合

`apriori_window_original/data/` 配下の既存テストデータを旧フォーマット（`|`なし）で読み込み、
`apriori_window_pruned.py` と同一の結果が得られることを確認する。

---

## 成果物

| ファイル | 内容 |
|---------|------|
| `apriori_window_original/src/apriori_window_basket.py` | バスケット構造対応の新実装（Python） |
| `apriori_window_original/tests/test_basket.py` | 上記テストケースの自動テスト |
| `apriori_window_original/data/sample_basket.txt` | バスケット構造付きサンプルデータ |

Rust移植（`main.rs` の変更）は Python での動作確認後に着手する。

---

## 実装チェックリスト

### Python実装

- [ ] `read_transactions_with_baskets` の実装
- [ ] `compute_item_basket_map` の実装
- [ ] `basket_ids_to_transaction_ids` の実装（重複保持）
- [ ] `compute_dense_intervals` のスタックケース修正（`l += 1` フォールバック）
- [ ] `compute_dense_intervals_with_candidates` の同修正
- [ ] `find_dense_itemsets` の修正（3箇所）
- [ ] `run_from_settings` の修正（パーサー切り替え）
- [ ] サンプルデータ `sample_basket.txt` の作成

### テスト

- [ ] テストケース1（後退互換性）
- [ ] テストケース2（偽共起の排除）
- [ ] テストケース3（スタックケース・無限ループにならないこと）★重要
- [ ] テストケース4（スタック後に右端からバスケットが入り密集継続）
- [ ] テストケース5（空行・エッジケース）
- [ ] テストケース6（既存データとの照合）

### Rust移植

- [ ] `read_transactions_with_baskets` の移植
- [ ] `compute_item_basket_map` の移植
- [ ] `basket_ids_to_transaction_ids` の移植（重複保持）
- [ ] `compute_dense_intervals` のスタックケース修正
- [ ] `compute_dense_intervals_with_candidates` の同修正
- [ ] `find_dense_itemsets` の修正
- [ ] Rustテスト追加・動作確認
