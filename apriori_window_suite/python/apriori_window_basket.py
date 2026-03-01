import json
import math
import sys
import time
from bisect import bisect_left, bisect_right
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# 入力パーサー（新規）
# ---------------------------------------------------------------------------

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
    transactions: List[List[List[int]]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                transactions.append([])
                continue
            basket_strs = line.split(" | ")
            baskets: List[List[int]] = []
            for bs in basket_strs:
                bs = bs.strip()
                if bs:
                    baskets.append([int(x) for x in bs.split()])
                else:
                    baskets.append([])
            transactions.append(baskets)
    return transactions


# ---------------------------------------------------------------------------
# バスケットマップ構築（新規）
# ---------------------------------------------------------------------------

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
    """
    item_basket_map: Dict[int, List[int]] = {}
    basket_to_transaction: List[int] = []
    item_transaction_map: Dict[int, List[int]] = {}

    basket_id = 0
    for t_id, baskets in enumerate(transactions):
        seen_in_transaction: set = set()
        for basket in baskets:
            seen_in_basket: set = set()
            basket_to_transaction.append(t_id)
            for item in basket:
                if item not in seen_in_basket:
                    seen_in_basket.add(item)
                    item_basket_map.setdefault(item, []).append(basket_id)
                if item not in seen_in_transaction:
                    seen_in_transaction.add(item)
                    item_transaction_map.setdefault(item, []).append(t_id)
            basket_id += 1

    return item_basket_map, basket_to_transaction, item_transaction_map


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
    """
    return [basket_to_transaction[bid] for bid in basket_ids]


# ---------------------------------------------------------------------------
# ユーティリティ（参照実装から流用）
# ---------------------------------------------------------------------------

def intersect_sorted_lists(lists: Sequence[Sequence[int]]) -> List[int]:
    """昇順リストの積集合を求める。"""
    if not lists:
        return []
    result = list(lists[0])
    for current in lists[1:]:
        merged: List[int] = []
        i = 0
        j = 0
        while i < len(result) and j < len(current):
            if result[i] == current[j]:
                merged.append(result[i])
                i += 1
                j += 1
            elif result[i] < current[j]:
                i += 1
            else:
                j += 1
        result = merged
        if not result:
            break
    return result


def intersect_interval_lists(
    intervals_list: Sequence[Sequence[Tuple[int, int]]],
) -> List[Tuple[int, int]]:
    """複数の区間リストの積集合を求める。"""
    if not intervals_list:
        return []
    result = list(intervals_list[0])
    for other in intervals_list[1:]:
        merged: List[Tuple[int, int]] = []
        i = 0
        j = 0
        while i < len(result) and j < len(other):
            a_start, a_end = result[i]
            b_start, b_end = other[j]
            start = max(a_start, b_start)
            end = min(a_end, b_end)
            if start <= end:
                merged.append((start, end))
            if a_end < b_end:
                i += 1
            else:
                j += 1
        result = merged
        if not result:
            break
    return result


def _find_covering_interval(
    intervals: Sequence[Tuple[int, int]], point: int
) -> Optional[Tuple[int, int]]:
    for start, end in intervals:
        if start <= point <= end:
            return (start, end)
    return None


def _is_interval_covered(
    intervals: Sequence[Tuple[int, int]], start: int, end: int
) -> bool:
    return any(start >= s and end <= e for s, e in intervals)


def _insert_and_merge_interval(
    intervals: List[Tuple[int, int]], new_interval: Tuple[int, int]
) -> None:
    intervals.append(new_interval)
    intervals.sort()
    merged: List[Tuple[int, int]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    intervals[:] = merged


# ---------------------------------------------------------------------------
# 密集区間計算（スタックケース修正を追加）
# ---------------------------------------------------------------------------

def compute_dense_intervals(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
) -> List[Tuple[int, int]]:
    """
    密集区間を計算する。

    変更点（バスケット拡張対応）:
        count > threshold のストライド調整にスタックケース処理を追加。
        window_occurrences[surplus] == l のとき l += 1 にフォールバック。
        タイムスタンプが一意の場合（旧フォーマット）は無害。
    """
    if window_size < 1 or threshold < 1:
        raise ValueError("window_size and threshold must be >= 1.")

    if not timestamps:
        return []

    ts = list(timestamps)
    intervals: List[Tuple[int, int]] = []

    l: Optional[int] = ts[0]
    in_dense = False
    start: Optional[int] = None
    end: Optional[int] = None

    while l is not None and l <= ts[-1]:
        start_idx = bisect_left(ts, l)
        end_idx = bisect_right(ts, l + window_size)
        count = end_idx - start_idx
        window_occurrences = ts[start_idx:end_idx]

        if count < threshold:
            if in_dense and start is not None and end is not None:
                intervals.append((start, end))
            in_dense = False
            start = None
            end = None
            next_idx = bisect_right(ts, l)
            l = ts[next_idx] if next_idx < len(ts) else None
            continue

        if count == threshold:
            if not in_dense:
                in_dense = True
                surplus = count - threshold
                right_from = window_occurrences[count - 1 - surplus]
                start = right_from - window_size
                end = l
            else:
                if end is not None:
                    end = max(end, l)
            l += 1
            continue

        # count > threshold
        if not in_dense:
            in_dense = True
            surplus = count - threshold
            right_from = window_occurrences[count - 1 - surplus]
            start = right_from - window_size
            end = l
        else:
            if end is not None:
                end = max(end, l)

        # ストライド調整（スタックケース修正）
        surplus = count - threshold
        next_l = window_occurrences[surplus]
        if next_l > l:
            l = next_l   # 非スタック：surplus分スキップして前進
        else:
            l += 1       # スタック：window_occurrences[surplus] == l
                         # → count == threshold と同じく1トランザクション前進

    if in_dense and start is not None and end is not None:
        intervals.append((start, end))

    return intervals


def compute_dense_intervals_with_candidates(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
    candidate_ranges: Sequence[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    """
    候補区間ごとに密集区間を評価する。

    変更点（バスケット拡張対応）:
        compute_dense_intervals と同様にスタックケース処理を追加。
    """
    if not candidate_ranges:
        return []
    if window_size < 1 or threshold < 1:
        raise ValueError("window_size and threshold must be >= 1.")
    if not timestamps:
        return []

    ts = list(timestamps)
    intervals: List[Tuple[int, int]] = []
    ts_last = ts[-1]
    recorded: List[Tuple[int, int]] = []

    for c_start, c_end in sorted(candidate_ranges):
        l = c_start
        in_dense = False
        start: Optional[int] = None
        end: Optional[int] = None

        while l <= c_end and l <= ts_last:
            covering = _find_covering_interval(recorded, l)
            if covering is not None:
                next_l = covering[1] + 1
                if next_l > c_end:
                    break
                l = next_l
                continue
            start_idx = bisect_left(ts, l)
            end_idx = bisect_right(ts, l + window_size)
            count = end_idx - start_idx
            window_occurrences = ts[start_idx:end_idx]

            if count < threshold:
                if in_dense and start is not None and end is not None:
                    if not _is_interval_covered(recorded, start, end):
                        intervals.append((start, end))
                        _insert_and_merge_interval(recorded, (start, end))
                in_dense = False
                start = None
                end = None
                next_idx = bisect_right(ts, l)
                if next_idx >= len(ts):
                    break
                l = ts[next_idx]
                continue

            if count == threshold:
                if not in_dense:
                    in_dense = True
                    surplus = count - threshold
                    right_from = window_occurrences[count - 1 - surplus]
                    start = right_from - window_size
                    end = l
                else:
                    if end is not None:
                        end = max(end, l)
                l += 1
                continue

            # count > threshold
            if not in_dense:
                in_dense = True
                surplus = count - threshold
                right_from = window_occurrences[count - 1 - surplus]
                start = right_from - window_size
                end = l
            else:
                if end is not None:
                    end = max(end, l)

            # ストライド調整（スタックケース修正）
            surplus = count - threshold
            next_l = window_occurrences[surplus]
            if next_l > l:
                l = next_l
            else:
                l += 1

        if in_dense and start is not None and end is not None:
            if not _is_interval_covered(recorded, start, end):
                intervals.append((start, end))
                _insert_and_merge_interval(recorded, (start, end))

    return intervals


# ---------------------------------------------------------------------------
# 候補生成・剪定（参照実装から流用）
# ---------------------------------------------------------------------------

def generate_candidates(
    prev_frequents: Sequence[Tuple[int, ...]],
    k: int,
) -> List[Tuple[int, ...]]:
    """k-1 項目集合から k 項目候補を生成する。"""
    prev_sorted = sorted(prev_frequents)
    candidates_set = set()
    for i in range(len(prev_sorted)):
        for j in range(i + 1, len(prev_sorted)):
            left = prev_sorted[i]
            right = prev_sorted[j]
            if k > 2 and left[: k - 2] != right[: k - 2]:
                break
            candidate_items = list(left)
            for item in right:
                if item not in candidate_items:
                    candidate_items.append(item)
            candidate_items.sort()
            if len(candidate_items) == k:
                candidates_set.add(tuple(candidate_items))
    return sorted(candidates_set)


def prune_candidates(
    candidates: Sequence[Tuple[int, ...]],
    prev_frequents_set: set,
) -> List[Tuple[int, ...]]:
    """Apriori 性質で候補を剪定する。"""
    pruned: List[Tuple[int, ...]] = []
    for candidate in candidates:
        all_subsets = combinations(candidate, len(candidate) - 1)
        if all(tuple(subset) in prev_frequents_set for subset in all_subsets):
            pruned.append(candidate)
    return pruned


# ---------------------------------------------------------------------------
# メイン探索（バスケット対応版）
# ---------------------------------------------------------------------------

def find_dense_itemsets(
    transactions: List[List[List[int]]],
    window_size: int,
    threshold: int,
    max_length: int,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """
    Apriori 性質を用いて密集区間を持つアイテムセットを探索する。

    変更点（バスケット拡張対応）:
        ① compute_item_basket_map で item_basket_map / basket_to_transaction /
          item_transaction_map を一括生成
        ② 単体アイテムの密集区間は item_transaction_map（重複なし）を使う
        ③ multi-item候補の共起タイムスタンプは basket_id の積集合 →
          basket_ids_to_transaction_ids で transaction_id（重複あり）に変換
    """
    item_basket_map, basket_to_transaction, item_transaction_map = compute_item_basket_map(
        transactions
    )
    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]] = {}

    current_level: List[Tuple[int, ...]] = []
    singleton_intervals: Dict[int, List[Tuple[int, int]]] = {}

    # --- 単体アイテムの処理 ---
    for item in sorted(item_transaction_map.keys()):
        timestamps = item_transaction_map[item]
        if not timestamps:
            continue
        full_range = [(timestamps[0], timestamps[-1])]
        intervals = compute_dense_intervals_with_candidates(
            timestamps, window_size, threshold, full_range
        )
        singleton_intervals[item] = compute_dense_intervals(
            timestamps, window_size, threshold
        )
        if intervals:
            key = (item,)
            frequents[key] = intervals
            current_level.append(key)

    # --- multi-item 候補の処理 ---
    k = 2
    while current_level and k <= max_length:
        candidates = generate_candidates(current_level, k)
        candidates = prune_candidates(candidates, set(current_level))
        next_level: List[Tuple[int, ...]] = []

        for candidate in candidates:
            # 単体アイテムの密集区間の積集合が空なら探索不要
            allowed_ranges = intersect_interval_lists(
                [singleton_intervals[item] for item in candidate]
            )
            allowed_ranges = [
                (s, e) for (s, e) in allowed_ranges if e - s >= window_size
            ]
            if not allowed_ranges:
                continue

            # バスケット粒度での共起タイムスタンプを計算
            basket_id_lists = [item_basket_map[item] for item in candidate]
            co_basket_ids = intersect_sorted_lists(basket_id_lists)
            timestamps = basket_ids_to_transaction_ids(co_basket_ids, basket_to_transaction)

            intervals = compute_dense_intervals_with_candidates(
                timestamps, window_size, threshold, allowed_ranges
            )
            if intervals:
                frequents[candidate] = intervals
                next_level.append(candidate)

        current_level = next_level
        k += 1

    return frequents


# ---------------------------------------------------------------------------
# 出力・設定読み込み（参照実装から流用・パーサー切り替えのみ変更）
# ---------------------------------------------------------------------------

def format_output(
    itemset,
    intervals: Sequence[Tuple[int, int]],
) -> List[str]:
    itemset_str = "[" + ", ".join(str(item) for item in itemset) + "]"
    return [f"{itemset_str} {start} {end}" for start, end in intervals]


def write_output(output_path: str, lines: Sequence[str]) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(f"{line}\n")


def min_support_to_threshold(window_size: int, min_support: int) -> int:
    return min_support


def run_from_settings(settings_path: str) -> str:
    """settings.json を読み込んで実行する。バスケット対応パーサーを使用。"""
    settings_text = Path(settings_path).read_text(encoding="utf-8")
    settings = json.loads(settings_text)

    input_dir = settings["input_file"]["dir"]
    input_name = settings["input_file"]["file_name"]
    output_dir = settings["output_files"]["dir"]
    output_name = settings["output_files"]["patterns_output_file_name"]
    window_size = int(settings["apriori_parameters"]["window_size"])
    min_support = int(settings["apriori_parameters"]["min_support"])
    max_length = int(settings["apriori_parameters"]["max_length"])

    input_path = Path(input_dir) / input_name
    # バスケット対応パーサーで読み込む（旧フォーマットも後退互換）
    transactions = read_transactions_with_baskets(str(input_path))

    threshold = min_support_to_threshold(window_size, min_support)
    frequents = find_dense_itemsets(transactions, window_size, threshold, max_length)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    out_file = output_path / output_name

    lines: List[str] = []
    lines.append("pattern_components,pattern_gaps,pattern_size,intervals_count,intervals")

    for itemset, intervals in sorted(
        frequents.items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        if len(itemset) <= 1:
            continue
        components_body = ", ".join(str(item) for item in itemset)
        pattern_components = f"\"[{{{components_body}}}]\""
        pattern_gaps = "\"[]\""
        intervals_count = len(intervals)
        if intervals_count == 0:
            intervals_str = "\"\""
        else:
            joined = ";".join(f"({start},{end})" for start, end in intervals)
            intervals_str = f"\"{joined}\""
        lines.append(
            f"{pattern_components},{pattern_gaps},{len(itemset)},{intervals_count},{intervals_str}"
        )

    write_output(str(out_file), lines)
    return str(out_file)


def main() -> None:
    default_settings = (
        Path(__file__).resolve().parents[1] / "data" / "settings_phase1.json"
    )
    settings_path = str(default_settings)
    if len(sys.argv) > 1:
        settings_path = sys.argv[1]

    start = time.perf_counter()
    output_path = run_from_settings(settings_path)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    print(f"結果を {output_path} に出力しました。")
    print(f"Elapsed time: {elapsed_ms:.3f} ms")


if __name__ == "__main__":
    main()
