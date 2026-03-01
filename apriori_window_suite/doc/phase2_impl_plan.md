# Phase 2 実装設計書：密集区間 × 外部イベント 時間的関係付け

上位方針: [doc/impl_plan.md](../../doc/impl_plan.md)
課題背景: [doc/new_change.md](../../doc/new_change.md)
Phase 1 設計: [phase1_impl_plan.md](../../phase1_impl_plan.md)

---

## 1. 概要とスコープ

Phase 1 で得た「アイテムセットの密集区間」を入力とし、
別途与えられる「外部イベントリスト」と照合して **時間的関係**（Follows / Contains / Overlaps）を列挙する。

```
【Phase 1 出力】                   【Phase 2 出力】
{1,2} → [(100,200), (300,400)]  ─┐
{3}   → [(200,300)]               ├─ event_correlator ─→ relations.csv
                                  │
【外部イベントファイル】          ─┘
live_2024_01: [100, 105]
promo_001:    [200, 300]
```

### スコープ外
- 有意性の統計検定（Future Work）
- イベントの自動検出
- Phase 1 のアルゴリズム改変

---

## 2. 設計上の決定事項

| 問題 | 決定内容 |
|------|---------|
| Phase 1 との結合方式 | Python は `import` 直結（関数再利用）、Rust はワークスペース化 |
| 関係の方向性 | 密集区間（I）とイベント（J）の両方向を個別に判定（6 種類） |
| ε の適用対象 | Follows の「ギャップ」、Contains の「右端マージン」、Overlaps の「重複長マージン」 |
| 複数関係の重複 | 同一ペアで複数関係が成立する場合は全て出力（排他にしない） |
| トランザクションID の単位 | イベントの start/end も同じトランザクション ID 軸で与える |

---

## 3. 時間的関係の厳密な定義

### 3.1 記号の定義

| 記号 | 意味 |
|------|------|
| `I = (ts_i, te_i)` | 密集区間（Phase 1 の出力）。単位はトランザクション ID |
| `J = (ts_j, te_j)` | 外部イベント。単位は同じトランザクション ID 軸 |
| ε | 非負の許容誤差。端点のずれを吸収する |
| d_0 | Overlaps の最小重複長。重複が d_0 未満なら偶発的とみなす |

### 3.2 Follows（追随）

I の直後に J が始まる（または J の直後に I が始まる）。

```
I:  ──────────|
              ↕ ε
J:            |──────────
```

**条件（DenseFollowsEvent）**:

```
te_i - ε  ≤  ts_j  ≤  te_i + ε
```

実用的解釈: I が終わってから ε トランザクション以内に J が開始する。
ε > 0 の場合、I と J がわずかに重なっていても（あるいはわずかにギャップがあっても）成立。

**条件（EventFollowsDense）**:

```
te_j - ε  ≤  ts_i  ≤  te_j + ε
```

I と J を入れ替えたもの。J が終わった直後に I が始まる。

---

### 3.3 Contains（包含）

I が J を包含する（または J が I を包含する）。

```
I:  ──────────────────────────────
J:       |───────────────|
```

**条件（DenseContainsEvent）**:

```
ts_i  ≤  ts_j   ∧   te_i + ε  ≥  te_j
```

実用的解釈: I は J の開始以前（または同時）に始まり、
J の終了から ε 以内（または以降）に終わる。
ε により「ほぼ包含」も許容できる。

**条件（EventContainsDense）**:

```
ts_j  ≤  ts_i   ∧   te_j + ε  ≥  te_i
```

I と J を入れ替えたもの。J が I を包含する。

---

### 3.4 Overlaps（部分重複）

I と J が部分的に重なる。重複長は d_0 以上必要。

```
パターン A（DenseOverlapsEvent）:     パターン B（EventOverlapsDense）:
I:  ─────────────|                   I:       |─────────────────
J:       |─────────────────          J:  ─────────────|
         ← 重複長 →                           ← 重複長 →
```

**条件（DenseOverlapsEvent）**: I が先に始まり J と部分的に重なる。

```
ts_i < ts_j                          # I が先に始まる
te_i - ts_j  ≥  d_0 - ε             # 重複長 ≥ d_0（許容誤差あり）
te_i  <  te_j + ε                   # I は J より先に終わる（完全包含でない）
```

**条件（EventOverlapsDense）**: J が先に始まり I と部分的に重なる。

```
ts_j < ts_i                          # J が先に始まる
te_j - ts_i  ≥  d_0 - ε             # 重複長 ≥ d_0（許容誤差あり）
te_j  <  te_i + ε                   # J は I より先に終わる（完全包含でない）
```

---

### 3.5 関係種別の命名規則

| 定数名 | 略称 | 意味 |
|--------|------|------|
| `DenseFollowsEvent` | DFE | 密集→イベントの順（密集が先） |
| `EventFollowsDense` | EFD | イベント→密集の順（イベントが先） |
| `DenseContainsEvent` | DCE | 密集区間がイベントを包含 |
| `EventContainsDense` | ECD | イベントが密集区間を包含 |
| `DenseOverlapsEvent` | DOE | 密集区間が先に始まり部分重複 |
| `EventOverlapsDense` | EOD | イベントが先に始まり部分重複 |

1 つの (I, J) ペアに対して複数の関係が成立する場合は全て出力する。

### 3.6 ε と d_0 のパラメータ指針

| パラメータ | 値が 0 のとき | 値が大きいとき |
|-----------|-------------|--------------|
| ε | 端点が厳密に一致する必要あり | 端点の誤差を大きく許容 |
| d_0 | Overlaps の最小重複長なし（1 でも成立） | 重複長が短い偶発的重複を除外 |

ε と d_0 はドメインの「トランザクション 1 件が何日/時間に相当するか」に合わせて設定する。

---

## 4. 入力フォーマット

### 4.1 イベントファイル（JSON）

```json
[
  {
    "event_id": "live_2024_01",
    "name": "アイドルライブ",
    "start": 100,
    "end": 105
  },
  {
    "event_id": "promo_001",
    "name": "ガム棚配置",
    "start": 200,
    "end": 300
  }
]
```

| フィールド | 型 | 必須 | 説明 |
|------------|-----|------|------|
| `event_id` | string | ✓ | イベントの一意識別子 |
| `name` | string | ✓ | 可読名称（出力に含める） |
| `start` | int | ✓ | イベント開始トランザクション ID（inclusive） |
| `end` | int | ✓ | イベント終了トランザクション ID（inclusive） |

**制約**:
- `start ≤ end`
- `event_id` はファイル内で一意
- `start` / `end` の単位はトランザクションファイルの行番号（0-indexed）と一致すること

### 4.2 settings.json 拡張（Phase 2 用）

```json
{
  "input_file": {
    "dir": "/path/to/data",
    "file_name": "transactions.txt"
  },
  "event_file": {
    "dir": "/path/to/data",
    "file_name": "events.json"
  },
  "output_files": {
    "dir": "/path/to/output",
    "patterns_output_file_name": "patterns.csv",
    "relations_output_file_name": "relations.csv"
  },
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

Phase 1 との差分:

| フィールド | 変更 | 説明 |
|-----------|------|------|
| `event_file` | **新規** | イベントファイルのパス |
| `output_files.relations_output_file_name` | **新規** | 時間的関係の出力ファイル名 |
| `temporal_relation_parameters.epsilon` | **新規** | ε パラメータ |
| `temporal_relation_parameters.d_0` | **新規** | d_0 パラメータ |

`event_file` が設定されていない場合は Phase 1 のみ実行（後退互換）。

---

## 5. 出力フォーマット

### 5.1 relations.csv

```
pattern_components,dense_start,dense_end,event_id,event_name,relation_type,overlap_length,epsilon,d_0
"[{1, 2}]",100,200,"live_2024_01","アイドルライブ","DenseFollowsEvent",,2,3
"[{3}]",200,300,"promo_001","ガム棚配置","EventContainsDense",100,2,3
"[{1, 2}]",50,110,"promo_001","ガム棚配置","DenseOverlapsEvent",10,2,3
```

| カラム | 型 | 説明 |
|--------|----|------|
| `pattern_components` | string | アイテムセット（Phase 1 と同じ形式） |
| `dense_start` | int | 密集区間の開始トランザクション ID |
| `dense_end` | int | 密集区間の終了トランザクション ID |
| `event_id` | string | イベント識別子 |
| `event_name` | string | イベント名称 |
| `relation_type` | string | DFE / EFD / DCE / ECD / DOE / EOD のいずれか |
| `overlap_length` | int or empty | DOE / EOD のみ: 実際の重複長（`te_i - ts_j` または `te_j - ts_i`）|
| `epsilon` | int | 使用した ε |
| `d_0` | int | 使用した d_0 |

### 5.2 ソート順

`pattern_components`（アイテム数降順）→ `dense_start` 昇順 → `event_id` 昇順 → `relation_type` 昇順

---

## 6. データ構造

```python
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict

@dataclass
class Event:
    event_id: str
    name: str
    start: int           # inclusive
    end: int             # inclusive

@dataclass
class RelationMatch:
    itemset: Tuple[int, ...]
    dense_start: int
    dense_end: int
    event: Event
    relation_type: str   # "DenseFollowsEvent" 等
    overlap_length: Optional[int]  # Overlaps 系のみ、他は None

# Phase 1 からの入力型（そのまま流用）
Frequents = Dict[Tuple[int, ...], List[Tuple[int, int]]]
```

---

## 7. 関数一覧と仕様

### 7.1 新規追加

#### `read_events(path: str) -> List[Event]`

```python
def read_events(path: str) -> List[Event]:
    """
    JSON 形式のイベントファイルを読み込む。

    バリデーション:
        - event_id の一意性を確認
        - start <= end を確認
    エラー:
        - 重複 event_id: ValueError を送出
        - start > end: ValueError を送出
    """
```

#### `satisfies_follows(te_i, ts_j, epsilon) -> bool`

```python
def satisfies_follows(te_i: int, ts_j: int, epsilon: int) -> bool:
    """
    Follows(I, J) 条件: te_i - epsilon <= ts_j <= te_i + epsilon
    """
    return te_i - epsilon <= ts_j <= te_i + epsilon
```

#### `satisfies_contains(ts_i, te_i, ts_j, te_j, epsilon) -> bool`

```python
def satisfies_contains(
    ts_i: int, te_i: int, ts_j: int, te_j: int, epsilon: int
) -> bool:
    """
    Contains(I ⊇ J) 条件: ts_i <= ts_j かつ te_i + epsilon >= te_j
    """
    return ts_i <= ts_j and te_i + epsilon >= te_j
```

#### `satisfies_overlaps(ts_i, te_i, ts_j, te_j, epsilon, d_0) -> Tuple[bool, Optional[int]]`

```python
def satisfies_overlaps(
    ts_i: int, te_i: int,
    ts_j: int, te_j: int,
    epsilon: int, d_0: int,
) -> Tuple[bool, Optional[int]]:
    """
    Overlaps(I ⊙ J) 条件（I が先に始まる）:
        ts_i < ts_j
        かつ te_i - ts_j >= d_0 - epsilon  （重複長 >= d_0）
        かつ te_i < te_j + epsilon           （完全包含でない）

    返り値: (成立するか, 重複長 te_i - ts_j) 。不成立なら (False, None)
    """
    if ts_i >= ts_j:
        return False, None
    overlap = te_i - ts_j
    if overlap < d_0 - epsilon:
        return False, None
    if te_i >= te_j + epsilon:
        return False, None
    return True, overlap
```

#### `match_all(frequents, events, epsilon, d_0) -> List[RelationMatch]`

```python
def match_all(
    frequents: Frequents,
    events: List[Event],
    epsilon: int,
    d_0: int,
) -> List[RelationMatch]:
    """
    全密集区間 × 全イベントの総当たりマッチング。

    計算量: O(|frequents| × avg_intervals × |events|)
    """
```

#### `write_relations_csv(path: str, results: List[RelationMatch], epsilon: int, d_0: int) -> None`

#### `run_from_settings(settings_path: str) -> Tuple[str, str]`

Phase 1 の `run_from_settings` を拡張。
`event_file` があれば Phase 2 まで実行し `(patterns_path, relations_path)` を返す。
`event_file` がなければ Phase 1 のみ実行し `(patterns_path, "")` を返す。

---

## 8. アーキテクチャ（Phase 1 との連携）

### 8.1 Python

Phase 2 は Phase 1 の関数を直接 import して使う。
ファイル間の結合は行わず、メモリ上でデータを受け渡す。

```
phase2/src/event_correlator.py
  └── import から phase1/src/apriori_window_basket.py
        ├── read_transactions_with_baskets
        └── find_dense_itemsets
```

```python
# phase2/src/event_correlator.py の先頭
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "phase1" / "src"))
from apriori_window_basket import (
    read_transactions_with_baskets,
    find_dense_itemsets,
)
```

### 8.2 Rust

Phase 1 の `phase1/` を **ライブラリクレート** に昇格し、
Phase 2 はそれを依存として追加する。ルートに Cargo workspace を設ける。

```
SPM_busket/
  Cargo.toml          ← workspace 定義
  phase1/
    Cargo.toml        ← [lib] + [bin] に変更
    src/
      lib.rs          ← pub fn 群をエクスポート
      main.rs         ← lib.rs を呼び出す thin wrapper
  phase2/
    Cargo.toml        ← phase1 = { path = "../phase1" } を依存に追加
    src/
      main.rs         ← Phase 2 実装
```

**workspace Cargo.toml**:
```toml
[workspace]
members = ["phase1", "phase2"]
resolver = "2"
```

**phase1/Cargo.toml の変更点**:
```toml
[lib]
name = "apriori_window_basket"
path = "src/lib.rs"

[[bin]]
name = "apriori_window_basket"
path = "src/main.rs"
```

---

## 9. アルゴリズム詳細と計算量

### 9.1 総当たりマッチング（ブルートフォース）

```python
results = []
for itemset, intervals in frequents.items():
    for (ts_i, te_i) in intervals:
        for event in events:
            ts_j, te_j = event.start, event.end

            # --- Follows 系（2方向）---
            if satisfies_follows(te_i, ts_j, epsilon):
                results.append(RelationMatch(..., "DenseFollowsEvent", None))
            if satisfies_follows(te_j, ts_i, epsilon):
                results.append(RelationMatch(..., "EventFollowsDense", None))

            # --- Contains 系（2方向）---
            if satisfies_contains(ts_i, te_i, ts_j, te_j, epsilon):
                results.append(RelationMatch(..., "DenseContainsEvent", None))
            if satisfies_contains(ts_j, te_j, ts_i, te_i, epsilon):
                results.append(RelationMatch(..., "EventContainsDense", None))

            # --- Overlaps 系（2方向）---
            ok, ovl = satisfies_overlaps(ts_i, te_i, ts_j, te_j, epsilon, d_0)
            if ok:
                results.append(RelationMatch(..., "DenseOverlapsEvent", ovl))
            ok, ovl = satisfies_overlaps(ts_j, te_j, ts_i, te_i, epsilon, d_0)
            if ok:
                results.append(RelationMatch(..., "EventOverlapsDense", ovl))
```

### 9.2 計算量

- ブルートフォースの時間計算量: `O(F × K × E)`
  - `F` = 頻出アイテムセット数
  - `K` = 1 アイテムセットあたり平均密集区間数
  - `E` = イベント数
- イベント数は通常数十〜数百程度であり実用上問題なし

### 9.3 将来の最適化余地

イベント数 E が大きくなる場合は以下の最適化が有効:

| 最適化 | 条件 | 方法 |
|--------|------|------|
| イベントのソート済み探索 | E が大きい | イベントを start でソートし binary search で候補を絞る |
| 区間木（Interval Tree） | F × K が大きく E も大きい | イベントを区間木に入れてクエリ最適化 |

Phase 2 では当面ブルートフォースで実装し、実データで計測後に最適化を検討する。

---

## 10. テスト計画

### 10.1 単体テスト

#### TC-U1: `satisfies_follows`

| ケース | te_i | ts_j | ε | 期待値 |
|--------|------|------|---|--------|
| ちょうど隣接 | 10 | 10 | 0 | True |
| ε 以内のギャップ | 10 | 12 | 2 | True |
| ε を超えるギャップ | 10 | 13 | 2 | False |
| ε 以内の重複（逆向き） | 10 | 8 | 2 | True |
| ε を超える重複 | 10 | 7 | 2 | False |

#### TC-U2: `satisfies_contains`

| ケース | ts_i | te_i | ts_j | te_j | ε | 期待値 |
|--------|------|------|------|------|---|--------|
| 完全包含 | 0 | 100 | 10 | 90 | 0 | True |
| 右端ちょうど一致 | 0 | 100 | 10 | 100 | 0 | True |
| 右端が ε 超過 | 0 | 100 | 10 | 103 | 2 | True |
| 右端が ε 超過（不成立） | 0 | 100 | 10 | 103 | 2 | True |
| 右端が ε+1 超過 | 0 | 100 | 10 | 104 | 2 | False |
| J が先に始まる | 5 | 100 | 0 | 90 | 0 | False |

#### TC-U3: `satisfies_overlaps`

| ケース | ts_i | te_i | ts_j | te_j | ε | d_0 | 期待値 | 重複長 |
|--------|------|------|------|------|---|-----|--------|--------|
| 正常重複 | 0 | 15 | 10 | 25 | 0 | 5 | True | 5 |
| 重複長ちょうど d_0 | 0 | 15 | 10 | 25 | 0 | 5 | True | 5 |
| 重複長 d_0 未満 | 0 | 14 | 10 | 25 | 0 | 5 | False | - |
| ε で救済 | 0 | 14 | 10 | 25 | 1 | 5 | True | 4 |
| I が先に始まらない | 10 | 20 | 0 | 25 | 0 | 5 | False | - |
| 完全包含（Contains と区別） | 0 | 30 | 10 | 25 | 0 | 5 | False | - |

### 10.2 統合テスト（E2E）

#### TC-E1: Follows（Dense → Event）

```
transactions: 3行、{1,2} が dense になる区間 (0, 2)
events: [{"event_id": "E1", "start": 4, "end": 10}]
ε = 2: DenseFollowsEvent が検出される（te_i=2, ts_j=4, 差=2 ≤ ε）
ε = 1: 検出されない（差=2 > ε=1）
```

#### TC-E2: Follows（Event → Dense）

```
events: [{"event_id": "E2", "start": 0, "end": 3}]
dense: (5, 8)
ε = 2: EventFollowsDense が検出される（te_j=3, ts_i=5, 差=2 ≤ ε）
```

#### TC-E3: Contains（Dense ⊇ Event）

```
dense: (0, 100)
events: [{"event_id": "E3", "start": 10, "end": 90}]
ε = 0: DenseContainsEvent が検出される
```

#### TC-E4: Contains（Event ⊇ Dense）

```
events: [{"event_id": "E4", "start": 0, "end": 200}]
dense: (10, 100)
ε = 0: EventContainsDense が検出される
```

#### TC-E5: Overlaps（Dense ⊙ Event）

```
dense: (0, 15)
events: [{"event_id": "E5", "start": 10, "end": 25}]
d_0 = 5, ε = 0: DenseOverlapsEvent が検出される（重複長=5）
```

#### TC-E6: Overlaps（Event ⊙ Dense）

```
events: [{"event_id": "E6", "start": 0, "end": 15}]
dense: (10, 25)
d_0 = 5, ε = 0: EventOverlapsDense が検出される（重複長=5）
```

#### TC-E7: 関係なし

```
dense: (0, 5)
events: [{"event_id": "E7", "start": 100, "end": 200}]
ε = 2, d_0 = 5: どの関係も成立しない → results が空
```

#### TC-E8: 複数関係の同時成立

```
dense: (100, 200)
events: [{"event_id": "E8", "start": 200, "end": 300}]
ε = 5: DenseFollowsEvent かつ DenseContainsEvent（ts_i ≤ ts_j ∧ te_i+ε ≥ te_j=200が境界）
→ 両方出力されること
```

#### TC-E9: 後退互換性（event_file なし）

```
settings.json に event_file なし
→ Phase 1 のみ実行。relations.csv は生成されない（エラーにならない）
```

#### TC-E10: イベントファイルのバリデーション

```
重複 event_id → ValueError
start > end → ValueError
```

---

## 11. Rust 移植方針

Phase 2 Python で動作確認後に着手する。

### 11.1 ディレクトリ構成

```
phase2/
  Cargo.toml
  src/
    main.rs        ← Phase 2 Rust 実装（Phase 1 を lib として使用）
```

### 11.2 型定義（Rust）

```rust
#[derive(Debug, Deserialize)]
struct Event {
    event_id: String,
    name: String,
    start: i64,
    end: i64,
}

#[derive(Debug)]
struct RelationMatch {
    itemset: Vec<i64>,
    dense_start: i64,
    dense_end: i64,
    event_id: String,
    event_name: String,
    relation_type: &'static str,
    overlap_length: Option<i64>,
}
```

### 11.3 並列化の方針

- `match_all` のマッチングループは `par_iter()` で並列化可能
  - `frequents` の各エントリを並列処理し、結果を `collect` して結合
- ただし `results.sort()` は並列化後に行うため逐次

### 11.4 settings.json 拡張（Rust 構造体）

```rust
#[derive(Deserialize)]
struct Settings {
    input_file: InputFile,
    event_file: Option<EventFile>,          // 省略可能
    output_files: OutputFiles,
    apriori_parameters: AprioriParameters,
    temporal_relation_parameters: Option<TemporalRelationParameters>,
}

#[derive(Deserialize)]
struct EventFile {
    dir: String,
    file_name: String,
}

#[derive(Deserialize)]
struct TemporalRelationParameters {
    epsilon: i64,
    d_0: i64,
}
```

---

## 12. 実装チェックリスト

### Python 実装

- [ ] `phase2/src/event_correlator.py` の作成
- [ ] `read_events` の実装（JSON パース + バリデーション）
- [ ] `satisfies_follows` の実装
- [ ] `satisfies_contains` の実装
- [ ] `satisfies_overlaps` の実装（重複長を返す）
- [ ] `match_all` の実装（6 方向総当たり）
- [ ] `write_relations_csv` の実装
- [ ] `run_from_settings` の実装（Phase 1 関数の import + 拡張）
- [ ] サンプルイベントファイル `phase2/data/sample_events.json` の作成
- [ ] Phase 2 用 `phase2/data/settings.json` の作成

### テスト

- [ ] TC-U1〜U3: 各 `satisfies_*` の単体テスト
- [ ] TC-E1: DenseFollowsEvent の検出
- [ ] TC-E2: EventFollowsDense の検出
- [ ] TC-E3: DenseContainsEvent の検出
- [ ] TC-E4: EventContainsDense の検出
- [ ] TC-E5: DenseOverlapsEvent の検出
- [ ] TC-E6: EventOverlapsDense の検出
- [ ] TC-E7: 関係なし（空結果）
- [ ] TC-E8: 複数関係の同時出力
- [ ] TC-E9: event_file なし（後退互換）
- [ ] TC-E10: イベントファイルのバリデーション

### Rust 移植

- [ ] Cargo workspace の設定（ルートの `Cargo.toml`）
- [ ] `phase1/` を lib クレートに昇格（`src/lib.rs` 作成）
- [ ] `phase2/Cargo.toml` の作成
- [ ] `read_events` の移植
- [ ] `satisfies_follows` / `satisfies_contains` / `satisfies_overlaps` の移植
- [ ] `match_all` の移植（並列化）
- [ ] `write_relations_csv` の移植
- [ ] `main` / `run_from_settings` の移植
- [ ] Rust テスト追加・動作確認

---

## 付録: ε・d_0 の設定例

| ドメイン | トランザクション単位 | 推奨 ε | 推奨 d_0 |
|---------|-------------------|--------|----------|
| ECサイト（1行=1日） | 1日 | 3〜7日分 | 7〜14日分 |
| コンビニ（1行=1時間） | 1時間 | 24〜48 | 72〜168 |
| スーパー（1行=1週間） | 1週間 | 1〜2 | 2〜4 |

ε と d_0 を変えながら結果の変化を観察し、最終的にはドメイン専門家の知識で決定する。
