"""
MDL-based Dense Interval Summarization.

Paper F: 最小記述長原理による密集区間要約

概要:
  - Temporal Code Table (TCT): 時間的コードテーブル
  - Time-Scoped Code Length: 時間スコープ付き符号長
  - Dense Interval Compression: 密集区間圧縮

KRIMP/SLIM をベースに、密集区間の時間的構造を活用して
パターンセットを圧縮要約する。
"""

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

# Phase 1 の密集区間検出を再利用
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python"))
from apriori_window_basket import (  # noqa: E402
    compute_dense_intervals,
    compute_item_basket_map,
    find_dense_itemsets,
    read_transactions_with_baskets,
)


# ---------------------------------------------------------------------------
# 1. 基本符号長計算
# ---------------------------------------------------------------------------

def universal_integer_code_length(n: int) -> float:
    """
    Rissanen の汎整数符号 L_N(n) を計算する。
    L_N(n) = log2*(n) + log2(c_0)
    ここでは c_0 ≈ 2.865 の近似値を使用。
    """
    if n <= 0:
        return 0.0
    c0 = 2.865064
    length = math.log2(c0)
    val = float(n)
    while val > 1.0:
        val = math.log2(val)
        if val > 0:
            length += val
        else:
            break
    return length


def log2_binomial(n: int, k: int) -> float:
    """log2(C(n, k)) を計算する（対数空間で安定）。"""
    if k < 0 or k > n:
        return 0.0
    if k == 0 or k == n:
        return 0.0
    k = min(k, n - k)
    result = 0.0
    for i in range(k):
        result += math.log2(n - i) - math.log2(i + 1)
    return result


def prequential_code_length(counts: Sequence[int]) -> float:
    """
    Prequential plug-in 符号長を計算する。

    L_pcl(data | model) = log2(Gamma(alpha)) - log2(Gamma(alpha + N))
                        + sum_k [log2(Gamma(alpha_k + n_k)) - log2(Gamma(alpha_k))]

    ここでは Laplace 推定（alpha_k = 1/2）の近似として
    NML (Normalized Maximum Likelihood) 的な計算を使用。

    Parameters:
        counts: 各シンボルの出現回数

    Returns:
        符号長（ビット）
    """
    total = sum(counts)
    if total == 0:
        return 0.0

    num_symbols = len(counts)
    if num_symbols <= 1:
        return 0.0

    # Multinomial NML approximation
    length = 0.0
    for c in counts:
        if c > 0:
            length -= c * math.log2(c / total)

    # パラメータ複雑度（Rissanen の parametric complexity）
    length += (num_symbols - 1) / 2.0 * math.log2(total / (2.0 * math.pi))
    if length < 0:
        length = 0.0

    return length


# ---------------------------------------------------------------------------
# 2. Temporal Code Table (TCT)
# ---------------------------------------------------------------------------

class TemporalCodeEntry:
    """コードテーブルの1エントリ: パターン + 有効区間 + 使用回数。"""

    def __init__(
        self,
        pattern: FrozenSet[int],
        intervals: List[Tuple[int, int]],
        usage_count: int = 0,
    ):
        self.pattern = pattern
        self.intervals = intervals  # 密集区間リスト [(start, end), ...]
        self.usage_count = usage_count

    def __repr__(self) -> str:
        items = sorted(self.pattern)
        return f"TCE({items}, intervals={self.intervals}, usage={self.usage_count})"


class TemporalCodeTable:
    """
    Temporal Code Table: 密集区間を考慮したコードテーブル。

    KRIMP のコードテーブルを拡張し、各パターンに時間的有効区間を持たせる。
    符号長は区間内での使用頻度に基づいて計算される。
    """

    def __init__(self, num_items: int, num_transactions: int):
        self.num_items = num_items
        self.num_transactions = num_transactions
        self.entries: List[TemporalCodeEntry] = []
        # Standard Code Table (SCT): 単体アイテムのみ
        self.sct_entries: Dict[int, int] = {}  # item -> usage_count

    def add_entry(self, entry: TemporalCodeEntry) -> None:
        """エントリを追加（Standard Cover Order: |X| desc, support desc）。"""
        self.entries.append(entry)
        self._sort_entries()

    def _sort_entries(self) -> None:
        """Standard Cover Order でソート。"""
        self.entries.sort(key=lambda e: (-len(e.pattern), -e.usage_count))

    def compute_cover(
        self,
        transactions: List[List[List[int]]],
    ) -> Dict[FrozenSet[int], int]:
        """
        Standard Cover アルゴリズムで各トランザクションをカバーする。

        Returns:
            各パターンの使用回数
        """
        usage: Dict[FrozenSet[int], int] = defaultdict(int)

        for t_idx, baskets in enumerate(transactions):
            # トランザクション内の全アイテムを集める
            items_in_t = set()
            for basket in baskets:
                items_in_t.update(basket)

            uncovered = set(items_in_t)

            # Standard Cover Order で走査
            for entry in self.entries:
                if entry.pattern.issubset(uncovered):
                    # 時間スコープチェック: このトランザクションが密集区間内か
                    in_scope = False
                    for s, e in entry.intervals:
                        if s <= t_idx <= e:
                            in_scope = True
                            break

                    if in_scope:
                        usage[entry.pattern] += 1
                        uncovered -= entry.pattern

            # 残りは単体アイテムでカバー
            for item in uncovered:
                usage[frozenset([item])] += 1

        return dict(usage)

    def compute_description_length(self) -> float:
        """
        コードテーブル自体の記述長 L(CT) を計算する。

        各エントリのコスト:
          - パターンの符号化: Standard Code Table での符号長
          - 区間の符号化: 区間数 + 各区間の (start, end)
        """
        length = 0.0

        for entry in self.entries:
            if entry.usage_count == 0:
                continue

            # パターン符号化コスト（SCT での符号長）
            for item in entry.pattern:
                sct_usage = self.sct_entries.get(item, 1)
                total_sct = sum(self.sct_entries.values()) if self.sct_entries else 1
                if sct_usage > 0 and total_sct > 0:
                    length -= math.log2(sct_usage / total_sct)

            # 区間符号化コスト
            num_intervals = len(entry.intervals)
            length += universal_integer_code_length(num_intervals)
            for s, e in entry.intervals:
                # 各区間は (start, length) で符号化
                length += universal_integer_code_length(max(1, s))
                length += universal_integer_code_length(max(1, e - s + 1))

        return length

    def compute_data_length(self, usage: Dict[FrozenSet[int], int]) -> float:
        """
        データの記述長 L(D|CT) を計算する。

        各トランザクションはカバーで使用されたパターンの符号で表現される。
        符号長は usage-based: L(X|CT) = -log2(usage(X) / sum_usages)
        """
        total_usage = sum(usage.values())
        if total_usage == 0:
            return 0.0

        length = 0.0
        for pattern, count in usage.items():
            if count > 0:
                code_len = -math.log2(count / total_usage)
                length += count * code_len

        return length

    def total_compressed_length(
        self,
        transactions: List[List[List[int]]],
    ) -> Tuple[float, float, float]:
        """
        L(CT) + L(D|CT) を計算する。

        Returns:
            (total, ct_length, data_length)
        """
        usage = self.compute_cover(transactions)

        # usage を各エントリに反映
        for entry in self.entries:
            entry.usage_count = usage.get(entry.pattern, 0)

        ct_length = self.compute_description_length()
        data_length = self.compute_data_length(usage)
        total = ct_length + data_length

        return total, ct_length, data_length


# ---------------------------------------------------------------------------
# 3. Dense Interval Compression (DIC)
# ---------------------------------------------------------------------------

def build_standard_code_table(
    transactions: List[List[List[int]]],
) -> Dict[int, int]:
    """全トランザクションでの各アイテムの出現回数を返す（SCT 用）。"""
    counts: Dict[int, int] = Counter()
    for baskets in transactions:
        seen = set()
        for basket in baskets:
            for item in basket:
                if item not in seen:
                    seen.add(item)
                    counts[item] += 1
    return dict(counts)


def compute_baseline_length(
    transactions: List[List[List[int]]],
) -> float:
    """
    Standard Code Table のみでの圧縮長（ベースライン）。
    各トランザクションを単体アイテム符号でカバーした場合の L(D|SCT)。
    """
    sct = build_standard_code_table(transactions)
    total_usage = sum(sct.values())
    if total_usage == 0:
        return 0.0

    length = 0.0
    for baskets in transactions:
        seen = set()
        for basket in baskets:
            for item in basket:
                if item not in seen:
                    seen.add(item)
                    count = sct.get(item, 1)
                    length -= math.log2(count / total_usage)

    # SCT 記述長（アイテム数の符号化）
    num_items = len(sct)
    ct_length = universal_integer_code_length(num_items)
    # 各アイテムの ID 符号化
    ct_length += num_items * math.log2(max(1, num_items))

    return ct_length + length


def mine_temporal_patterns(
    transactions: List[List[List[int]]],
    window_size: int,
    min_support: int,
    max_pattern_length: int = 4,
) -> List[TemporalCodeEntry]:
    """
    密集区間付きパターンを抽出する。

    Phase 1 の find_dense_itemsets を使って密集パターンを取得し、
    TemporalCodeEntry に変換する。

    Parameters:
        transactions: トランザクションデータ
        window_size: ウィンドウサイズ
        min_support: 最小サポート
        max_pattern_length: パターンの最大長

    Returns:
        TemporalCodeEntry のリスト
    """
    # Phase 1 のマップ構築
    item_basket_map, basket_to_transaction, item_transaction_map = \
        compute_item_basket_map(transactions)

    num_transactions = len(transactions)

    # 密集区間の閾値
    threshold = min_support

    # 各アイテムの密集区間を計算
    item_intervals: Dict[int, List[Tuple[int, int]]] = {}
    for item, t_ids in item_transaction_map.items():
        intervals = compute_dense_intervals(t_ids, window_size, threshold)
        if intervals:
            item_intervals[item] = intervals

    # Phase 1 の find_dense_itemsets を呼ぶ
    dense_result = find_dense_itemsets(
        transactions=transactions,
        window_size=window_size,
        threshold=threshold,
        max_length=max_pattern_length,
    )

    entries: List[TemporalCodeEntry] = []

    # dense_result: Dict[Tuple[int,...], List[Tuple[int,int]]]
    for itemset, intervals in dense_result.items():
        if len(itemset) < 2:
            continue  # 単体アイテムはスキップ

        pattern = frozenset(itemset)
        if intervals:
            entries.append(TemporalCodeEntry(pattern, list(intervals), usage_count=0))

    return entries


def greedy_mdl_selection(
    transactions: List[List[List[int]]],
    candidates: List[TemporalCodeEntry],
    sct_counts: Dict[int, int],
) -> List[TemporalCodeEntry]:
    """
    貪欲法で MDL 最適なパターンセットを選択する。

    KRIMP の Cover-based 選択:
    1. 候補を Standard Cover Order でソート
    2. 各候補を TCT に追加
    3. L(CT) + L(D|CT) が改善すれば採用、さもなくば除去

    Parameters:
        transactions: トランザクションデータ
        candidates: 候補パターン
        sct_counts: Standard Code Table のアイテム出現回数

    Returns:
        選択されたパターンのリスト
    """
    num_items = len(sct_counts)
    num_transactions = len(transactions)

    # ベースライン（SCT のみ）
    tct = TemporalCodeTable(num_items, num_transactions)
    tct.sct_entries = dict(sct_counts)
    best_total, _, _ = tct.total_compressed_length(transactions)

    selected: List[TemporalCodeEntry] = []

    # 候補を Standard Cover Order でソート
    candidates_sorted = sorted(
        candidates,
        key=lambda e: (-len(e.pattern), -e.usage_count),
    )

    for candidate in candidates_sorted:
        # 候補を追加してみる
        tct_trial = TemporalCodeTable(num_items, num_transactions)
        tct_trial.sct_entries = dict(sct_counts)
        for e in selected:
            tct_trial.add_entry(TemporalCodeEntry(e.pattern, e.intervals))
        tct_trial.add_entry(
            TemporalCodeEntry(candidate.pattern, candidate.intervals)
        )

        trial_total, ct_len, data_len = tct_trial.total_compressed_length(transactions)

        if trial_total < best_total:
            best_total = trial_total
            selected.append(candidate)

    return selected


# ---------------------------------------------------------------------------
# 4. Time-Scoped Code Length
# ---------------------------------------------------------------------------

def time_scoped_code_length(
    entry: TemporalCodeEntry,
    num_transactions: int,
) -> float:
    """
    時間スコープ付き符号長を計算する。

    区間外でのパターン出現はペナルティを受ける:
      L_ts(X) = L_in(X) + lambda * L_out(X)

    ここで lambda > 1 は区間外ペナルティ係数。

    Parameters:
        entry: TCT エントリ
        num_transactions: 総トランザクション数

    Returns:
        時間スコープ付き符号長
    """
    if not entry.intervals:
        return 0.0

    # 区間内の総トランザクション数
    scope_size = sum(e - s + 1 for s, e in entry.intervals)
    outside_size = num_transactions - scope_size

    if scope_size <= 0:
        return 0.0

    # 区間内密度
    in_density = entry.usage_count / scope_size if scope_size > 0 else 0.0

    # 符号長
    if in_density > 0:
        in_length = -math.log2(in_density) * entry.usage_count
    else:
        in_length = 0.0

    # 区間外は高コスト
    out_penalty = math.log2(max(1, outside_size)) if outside_size > 0 else 0.0

    return in_length + out_penalty


# ---------------------------------------------------------------------------
# 5. 圧縮率メトリクス
# ---------------------------------------------------------------------------

def compression_ratio(
    transactions: List[List[List[int]]],
    selected_patterns: List[TemporalCodeEntry],
    sct_counts: Dict[int, int],
) -> Dict[str, float]:
    """
    圧縮率と関連メトリクスを計算する。

    Returns:
        {
            "baseline_length": SCT のみの記述長,
            "compressed_length": TCT での記述長,
            "compression_ratio": 圧縮率 (compressed / baseline),
            "num_patterns": 選択されたパターン数,
            "ct_length": コードテーブルの記述長,
            "data_length": データの記述長,
        }
    """
    baseline = compute_baseline_length(transactions)

    num_items = len(sct_counts)
    num_transactions = len(transactions)

    tct = TemporalCodeTable(num_items, num_transactions)
    tct.sct_entries = dict(sct_counts)
    for entry in selected_patterns:
        tct.add_entry(TemporalCodeEntry(entry.pattern, entry.intervals))

    total, ct_len, data_len = tct.total_compressed_length(transactions)

    return {
        "baseline_length": baseline,
        "compressed_length": total,
        "compression_ratio": total / baseline if baseline > 0 else 1.0,
        "num_patterns": len(selected_patterns),
        "ct_length": ct_len,
        "data_length": data_len,
    }


# ---------------------------------------------------------------------------
# 6. メインパイプライン
# ---------------------------------------------------------------------------

def run_mdl_summary(
    data_path: str,
    window_size: int = 10,
    min_support: int = 3,
    max_pattern_length: int = 4,
) -> Dict[str, Any]:
    """
    MDL Summary パイプラインを実行する。

    1. データ読み込み
    2. 密集パターン抽出
    3. 貪欲 MDL 選択
    4. 圧縮率計算

    Returns:
        結果辞書
    """
    # データ読み込み
    transactions = read_transactions_with_baskets(data_path)
    num_transactions = len(transactions)

    # SCT 構築
    sct_counts = build_standard_code_table(transactions)
    num_items = len(sct_counts)

    # 密集パターン抽出
    candidates = mine_temporal_patterns(
        transactions, window_size, min_support, max_pattern_length
    )

    # 貪欲 MDL 選択
    selected = greedy_mdl_selection(transactions, candidates, sct_counts)

    # 圧縮率
    metrics = compression_ratio(transactions, selected, sct_counts)

    # 結果
    result = {
        "num_transactions": num_transactions,
        "num_items": num_items,
        "num_candidates": len(candidates),
        "num_selected": len(selected),
        "selected_patterns": [
            {
                "pattern": sorted(e.pattern),
                "intervals": e.intervals,
                "usage_count": e.usage_count,
            }
            for e in selected
        ],
        "metrics": metrics,
    }

    return result


if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print("Usage: python mdl_summary.py <data_path> [window_size] [min_support]")
        sys.exit(1)

    data_path = sys.argv[1]
    window_size = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    min_support = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    result = run_mdl_summary(data_path, window_size, min_support)
    print(json.dumps(result, indent=2, ensure_ascii=False))
