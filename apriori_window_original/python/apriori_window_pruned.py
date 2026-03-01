import json
import math
import sys
import time
from bisect import bisect_left, bisect_right
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def compute_item_timestamps_map(
    transactions: Sequence[Iterable[int]],
) -> Dict[int, List[int]]:
    """各アイテムの出現位置列を作成する。"""
    item_map: Dict[int, List[int]] = {}
    for idx, transaction in enumerate(transactions):
        # トランザクション内では重複を1回として数える（Rust版と同じ）。　
        # つまり、Aが同一トランザクションで2回出てきてたとしても、それは１とカウント。
        seen = set()
        for item in transaction:
            if item in seen:
                continue
            seen.add(item)
            item_map.setdefault(item, []).append(idx)
    return item_map


def intersect_sorted_lists(lists: Sequence[Sequence[int]]) -> List[int]:
    """昇順リストの積集合を求める。"""
    if not lists:
        return []
    result = list(lists[0])
    for current in lists[1:]:
        # 2ポインタで積集合を取り、昇順のまま保つ。
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


def compute_dense_intervals(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
) -> List[Tuple[int, int]]:
    """requirements.md に基づいて密集区間を計算する。"""
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

    # 二分探索で窓内件数を数え、密なら余剰分だけ l を飛ばす。
    while l is not None and l <= ts[-1]:
        start_idx = bisect_left(ts, l)
        end_idx = bisect_right(ts, l + window_size)
        count = end_idx - start_idx
        window_occurrences = ts[start_idx:end_idx]

        if count < threshold:
            # 密集区間を終了し、次のタイムスタンプへジャンプする。
            if in_dense and start is not None and end is not None:
                intervals.append((start, end))
            in_dense = False
            start = None
            end = None
            next_idx = bisect_right(ts, l)
            l = ts[next_idx] if next_idx < len(ts) else None
            continue

        if count == threshold:
            # 1つずつ進めて密集区間を延長する。
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

        # count > threshold（閾値より大きい）
        if not in_dense:
            in_dense = True
            surplus = count - threshold
            right_from = window_occurrences[count - 1 - surplus]
            start = right_from - window_size
            end = l
        else:
            if end is not None:
                end = max(end, l)

        # 余剰分だけ飛ばして、1ステップずつの移動を避ける。
        surplus = count - threshold
        l = window_occurrences[surplus]

    if in_dense and start is not None and end is not None:
        intervals.append((start, end))

    return intervals


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


def _find_covering_interval(intervals: Sequence[Tuple[int, int]], point: int) -> Optional[Tuple[int, int]]:
    for start, end in intervals:
        if start <= point <= end:
            return (start, end)
    return None


def _is_interval_covered(intervals: Sequence[Tuple[int, int]], start: int, end: int) -> bool:
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


def compute_dense_intervals_with_candidates(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
    candidate_ranges: Sequence[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    """候補区間ごとに密集区間を評価する。"""
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

            if not in_dense:
                in_dense = True
                surplus = count - threshold
                right_from = window_occurrences[count - 1 - surplus]
                start = right_from - window_size
                end = l
            else:
                if end is not None:
                    end = max(end, l)

            surplus = count - threshold
            l = window_occurrences[surplus]

        if in_dense and start is not None and end is not None:
            if not _is_interval_covered(recorded, start, end):
                intervals.append((start, end))
                _insert_and_merge_interval(recorded, (start, end))

    return intervals


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
            # k>2 のときは prefix が一致する組だけ結合する。
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
        # (k-1)部分集合がすべて頻出であることが条件。
        all_subsets = combinations(candidate, len(candidate) - 1)
        if all(tuple(subset) in prev_frequents_set for subset in all_subsets):
            pruned.append(candidate)
    return pruned


def find_dense_itemsets(
    transactions: Sequence[Iterable[int]],
    window_size: int,
    threshold: int,
    max_length: int,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """Apriori 性質を用いて密集区間を持つアイテムセットを探索する。"""
    item_timestamps = compute_item_timestamps_map(transactions)
    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]] = {}

    current_level: List[Tuple[int, ...]] = []
    singleton_intervals: Dict[int, List[Tuple[int, int]]] = {}
    for item in sorted(item_timestamps.keys()):
        timestamps = item_timestamps[item]
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

    k = 2
    while current_level and k <= max_length:
        # 候補生成→剪定→評価の順で次レベルを作る。
        candidates = generate_candidates(current_level, k)
        candidates = prune_candidates(candidates, set(current_level))
        next_level: List[Tuple[int, ...]] = []

        for candidate in candidates:
            # 単一アイテムの密集区間の積集合が空なら探索不要。
            allowed_ranges = intersect_interval_lists(
                [singleton_intervals[item] for item in candidate]
            )
            allowed_ranges = [
                (s, e) for (s, e) in allowed_ranges if e - s >= window_size
            ]
            if not allowed_ranges:
                continue
            lists = [item_timestamps[item] for item in candidate]
            timestamps = intersect_sorted_lists(lists)
            intervals = compute_dense_intervals_with_candidates(
                timestamps, window_size, threshold, allowed_ranges
            )
            if intervals:
                frequents[candidate] = intervals
                next_level.append(candidate)

        current_level = next_level
        k += 1

    return frequents


def format_output(
    itemset: Iterable[int],
    intervals: Sequence[Tuple[int, int]],
) -> List[str]:
    """apriori_window の出力形式に合わせて整形する。"""
    # 旧形式の「アイテム集合 + 区間」のテキスト行を作る。
    itemset_str = "[" + ", ".join(str(item) for item in itemset) + "]"
    return [f"{itemset_str} {start} {end}" for start, end in intervals]


def write_output(
    output_path: str,
    lines: Sequence[str],
) -> None:
    """整形済みの出力行を指定パスに書き込む。"""
    # ヘッダ行を含むCSV文字列をそのまま書き出す。
    with open(output_path, "w", encoding="utf-8") as output_file:
        for line in lines:
            output_file.write(f"{line}\n")


def read_text_file_as_2d_vec_of_integers(path: str) -> List[List[int]]:
    """apriori_window と同じ形式の入力ファイルを読み込む。"""
    # 1行=1トランザクション、空行は空集合として扱う。
    transactions: List[List[int]] = []
    with open(path, "r", encoding="utf-8") as input_file:
        for line in input_file:
            line = line.strip()
            if not line:
                transactions.append([])
                continue
            transactions.append([int(item) for item in line.split()])
    return transactions


def min_support_to_threshold(window_size: int, min_support: int) -> int:
    """min_support(%) を出現回数閾値に変換する。"""
    return min_support


def run_from_settings(settings_path: str) -> str:
    """apriori_window と同じ settings.json を読み込んで実行する。"""
    # settings.json を読み込んで入出力パスとパラメータを決定する。
    settings_text = Path(settings_path).read_text(encoding="utf-8")
    settings = json.loads(settings_text)

    input_dir = settings["input_file"]["dir"]
    input_name = settings["input_file"]["file_name"]
    output_dir = settings["output_files"]["dir"]
    output_name = settings["output_files"]["patterns_output_file_name"]
    window_size = int(settings["apriori_parameters"]["window_size"])
    min_support = int(settings["apriori_parameters"]["min_support"])
    max_length = int(settings["apriori_parameters"]["max_length"])

    # 入力ファイルの読み込み。
    input_path = Path(input_dir) / input_name
    transactions = read_text_file_as_2d_vec_of_integers(str(input_path))

    # しきい値へ変換して探索を実行する。
    threshold = min_support_to_threshold(window_size, min_support)
    frequents = find_dense_itemsets(transactions, window_size, threshold, max_length)

    # 出力ディレクトリを用意する。
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    out_file = output_path / output_name

    # CSVヘッダを含めて出力行を組み立てる。
    lines: List[str] = []
    lines.append("pattern_components,pattern_gaps,pattern_size,intervals_count,intervals")

    for itemset, intervals in sorted(
        frequents.items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        if len(itemset) <= 1:
            continue
        # Rust版と同じCSV形式で1行に整形する。
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

    # CSVを書き出す。
    write_output(str(out_file), lines)
    return str(out_file)


def main() -> None:
    default_settings = (
        Path(__file__).resolve().parents[1] / "data" / "settings.json"
    )
    settings_path = str(default_settings)
    if len(sys.argv) > 1:
        settings_path = sys.argv[1]

    # settings.json の指定があればそれを使って実行する。
    start = time.perf_counter()
    output_path = run_from_settings(settings_path)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    print(f"結果を {output_path} に出力しました。")
    print(f"Elapsed time: {elapsed_ms:.3f} ms")


if __name__ == "__main__":
    main()
