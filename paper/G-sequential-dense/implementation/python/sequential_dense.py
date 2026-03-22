"""
Sequential Dense Pattern Mining
================================

系列密集パターン（Sequential Dense Pattern）のマイニング実装。

概念:
  - Sequential Dense Pattern: アイテム間に時間順序制約を持つ密集パターン
  - In-Window Sequential Support: ウィンドウ内で系列が出現する回数
  - Sequential Anti-Monotonicity: 系列の反単調性（super-sequence のサポートは
    sub-sequence 以下）

既存の apriori_window_basket.py を拡張し、同一トランザクション内の共起（集合）
ではなく、トランザクション間の順序付き出現（系列）を検出する。
"""

from __future__ import annotations

import json
import sys
import time
from bisect import bisect_left, bisect_right
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------

def read_transactions(path: str) -> List[List[int]]:
    """
    トランザクションファイルを読み込む。

    1行 = 1トランザクション（時刻 t に対応）。
    各行はスペース区切りのアイテム列。
    空行は空トランザクション。
    """
    transactions: List[List[int]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                transactions.append([])
            else:
                # "|" がある場合はバスケット区切りだが、フラットに扱う
                line = line.replace(" | ", " ")
                transactions.append([int(x) for x in line.split()])
    return transactions


# ---------------------------------------------------------------------------
# アイテム出現マップ構築
# ---------------------------------------------------------------------------

def build_item_occurrence_map(
    transactions: List[List[int]],
) -> Dict[int, List[int]]:
    """
    各アイテムの出現トランザクション ID リスト（ソート済み・一意）を構築する。
    """
    item_map: Dict[int, List[int]] = {}
    for t_id, items in enumerate(transactions):
        seen: set = set()
        for item in items:
            if item not in seen:
                seen.add(item)
                item_map.setdefault(item, []).append(t_id)
    return item_map


# ---------------------------------------------------------------------------
# 密集区間計算（apriori_window_basket.py と同一ロジック）
# ---------------------------------------------------------------------------

def compute_dense_intervals(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
) -> List[Tuple[int, int]]:
    """
    密集区間を計算する。

    スタックケース修正（window_occurrences[surplus] == l → l += 1）を含む。
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

        surplus = count - threshold
        next_l = window_occurrences[surplus]
        if next_l > l:
            l = next_l
        else:
            l += 1

    if in_dense and start is not None and end is not None:
        intervals.append((start, end))

    return intervals


# ---------------------------------------------------------------------------
# 系列サポート計算
# ---------------------------------------------------------------------------

def compute_sequential_occurrences(
    item_occ_map: Dict[int, List[int]],
    sequence: Tuple[int, ...],
    max_gap: int,
) -> List[int]:
    """
    系列 (a, b, c, ...) の出現タイムスタンプ（系列の最後の要素の出現時刻）を返す。

    系列出現の定義:
      sequence = (e1, e2, ..., ek) に対し、
      t1 < t2 < ... < tk かつ各 t_{i+1} - t_i <= max_gap を満たす
      (t1, ..., tk) が存在するとき、tk を「系列出現のタイムスタンプ」とする。

    max_gap: 連続する要素間の最大ギャップ（トランザクション数）
             0 の場合はギャップ制約なし（t_i < t_{i+1} のみ）

    返り値: ソート済みの出現タイムスタンプリスト（重複なし）
    """
    if not sequence:
        return []

    # 単一アイテムの場合
    if len(sequence) == 1:
        return list(item_occ_map.get(sequence[0], []))

    # 系列の各アイテムの出現位置を取得
    occ_lists = []
    for item in sequence:
        occs = item_occ_map.get(item, [])
        if not occs:
            return []
        occ_lists.append(occs)

    # 動的計画法: 系列の接頭辞 (e1, ..., ei) の出現末尾位置を追跡
    # current_ends[j] = sequence[0:i] が時刻 occ_lists[i-1][j] で終わる出現が存在するか
    # → 実際には、各段階で「到達可能な末尾時刻」のリストを管理
    reachable = occ_lists[0][:]  # sequence[0] の出現位置 = 1要素系列の末尾

    for step in range(1, len(sequence)):
        next_occs = occ_lists[step]
        next_reachable: List[int] = []
        r_idx = 0  # reachable のポインタ

        for t in next_occs:
            # reachable のうち t より前（厳密に小さい）で、ギャップ制約を満たすもの
            while r_idx < len(reachable) and reachable[r_idx] < t:
                r_idx += 1
            # r_idx は reachable[r_idx] >= t の最初のインデックス
            # reachable[r_idx - 1] が t より前の最後の到達可能時刻
            if r_idx > 0:
                prev_t = reachable[r_idx - 1]
                if prev_t < t:
                    gap_ok = (max_gap == 0) or (t - prev_t <= max_gap)
                    if gap_ok:
                        next_reachable.append(t)

        reachable = next_reachable
        if not reachable:
            return []

    # 重複除去（すでにソート済み）
    if reachable:
        unique = [reachable[0]]
        for v in reachable[1:]:
            if v != unique[-1]:
                unique.append(v)
        return unique
    return []


def compute_in_window_sequential_support(
    item_occ_map: Dict[int, List[int]],
    sequence: Tuple[int, ...],
    window_start: int,
    window_size: int,
    max_gap: int,
) -> int:
    """
    ウィンドウ [window_start, window_start + window_size] 内での系列サポートを計算する。
    """
    occs = compute_sequential_occurrences(item_occ_map, sequence, max_gap)
    window_end = window_start + window_size
    left = bisect_left(occs, window_start)
    right = bisect_right(occs, window_end)
    return right - left


# ---------------------------------------------------------------------------
# 系列候補生成（PrefixSpan 風）
# ---------------------------------------------------------------------------

def generate_length2_candidates(
    freq_items: List[int],
) -> List[Tuple[int, ...]]:
    """
    頻出単一アイテムから長さ2の系列候補を生成する。
    (a, b) と (b, a) は異なる系列として扱う（順序あり）。
    """
    candidates: List[Tuple[int, ...]] = []
    for a in freq_items:
        for b in freq_items:
            # a == b も許容（同一アイテムの連続出現）
            candidates.append((a, b))
    return candidates


def generate_sequential_candidates(
    prev_frequents: List[Tuple[int, ...]],
    k: int,
) -> List[Tuple[int, ...]]:
    """
    長さ k-1 の頻出系列から長さ k の候補系列を生成する。

    接頭辞・接尾辞結合: seq1[1:] == seq2[:-1] のとき、
    seq1 + (seq2[-1],) を候補とする。
    """
    candidates_set: set = set()
    suffix_map: Dict[Tuple[int, ...], List[Tuple[int, ...]]] = {}

    for seq in prev_frequents:
        prefix = seq[:-1]
        suffix_map.setdefault(prefix, []).append(seq)

    for seq in prev_frequents:
        suffix_key = seq[1:]  # この系列の接尾辞
        if suffix_key in suffix_map:
            for extendable in suffix_map[suffix_key]:
                new_seq = seq + (extendable[-1],)
                candidates_set.add(new_seq)

    return sorted(candidates_set)


def prune_sequential_candidates(
    candidates: List[Tuple[int, ...]],
    prev_frequents_set: set,
) -> List[Tuple[int, ...]]:
    """
    系列反単調性による剪定。
    長さ k の候補系列の全ての長さ k-1 の連続部分系列が頻出でなければ除去。
    """
    pruned: List[Tuple[int, ...]] = []
    for candidate in candidates:
        k = len(candidate)
        all_subseqs_frequent = True
        for i in range(k):
            subseq = candidate[:i] + candidate[i + 1:]
            if subseq not in prev_frequents_set:
                all_subseqs_frequent = False
                break
        if all_subseqs_frequent:
            pruned.append(candidate)
    return pruned


# ---------------------------------------------------------------------------
# メイン探索
# ---------------------------------------------------------------------------

def find_sequential_dense_patterns(
    transactions: List[List[int]],
    window_size: int,
    threshold: int,
    max_length: int,
    max_gap: int = 0,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """
    系列密集パターンを探索する。

    Parameters:
      transactions: トランザクションリスト
      window_size: スライディングウィンドウサイズ
      threshold: 密集判定閾値（ウィンドウ内最低出現回数）
      max_length: 系列の最大長
      max_gap: 系列要素間の最大ギャップ（0=無制限）

    Returns:
      Dict[系列, 密集区間リスト]
    """
    item_occ_map = build_item_occurrence_map(transactions)
    result: Dict[Tuple[int, ...], List[Tuple[int, int]]] = {}

    # --- Phase 1: 単一アイテムの密集区間 ---
    freq_items: List[int] = []
    item_intervals: Dict[int, List[Tuple[int, int]]] = {}

    for item in sorted(item_occ_map.keys()):
        timestamps = item_occ_map[item]
        intervals = compute_dense_intervals(timestamps, window_size, threshold)
        if intervals:
            freq_items.append(item)
            item_intervals[item] = intervals
            result[(item,)] = intervals

    if max_length < 2:
        return result

    # --- Phase 2: 長さ2の系列候補 ---
    candidates = generate_length2_candidates(freq_items)
    current_level: List[Tuple[int, ...]] = []

    for seq in candidates:
        # 系列の全アイテムが頻出でなければスキップ
        if any(item not in item_intervals for item in seq):
            continue

        # 系列出現タイムスタンプを計算
        occ_timestamps = compute_sequential_occurrences(item_occ_map, seq, max_gap)
        if not occ_timestamps:
            continue

        intervals = compute_dense_intervals(occ_timestamps, window_size, threshold)
        if intervals:
            result[seq] = intervals
            current_level.append(seq)

    # --- Phase 3+: 長さ3以上の系列 ---
    k = 3
    while current_level and k <= max_length:
        candidates = generate_sequential_candidates(current_level, k)
        candidates = prune_sequential_candidates(candidates, set(current_level))
        next_level: List[Tuple[int, ...]] = []

        for seq in candidates:
            occ_timestamps = compute_sequential_occurrences(item_occ_map, seq, max_gap)
            if not occ_timestamps:
                continue

            intervals = compute_dense_intervals(occ_timestamps, window_size, threshold)
            if intervals:
                result[seq] = intervals
                next_level.append(seq)

        current_level = next_level
        k += 1

    return result


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

def format_sequential_pattern(
    sequence: Tuple[int, ...],
    intervals: List[Tuple[int, int]],
) -> str:
    """系列パターンと密集区間をフォーマットする。"""
    seq_str = " -> ".join(str(item) for item in sequence)
    intervals_str = "; ".join(f"({s},{e})" for s, e in intervals)
    return f"<{seq_str}> [{intervals_str}]"


def write_results(
    output_path: str,
    results: Dict[Tuple[int, ...], List[Tuple[int, int]]],
) -> None:
    """結果をCSV形式で出力する。"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("sequence,seq_length,intervals_count,intervals\n")
        for seq, intervals in sorted(
            results.items(), key=lambda kv: (len(kv[0]), kv[0])
        ):
            if len(seq) < 2:
                continue
            seq_str = " -> ".join(str(item) for item in seq)
            intervals_str = ";".join(f"({s},{e})" for s, e in intervals)
            f.write(f'"{seq_str}",{len(seq)},{len(intervals)},"{intervals_str}"\n')


# ---------------------------------------------------------------------------
# 設定ファイル駆動の実行
# ---------------------------------------------------------------------------

def run_from_settings(settings_path: str) -> str:
    """settings.json を読み込んで実行する。"""
    settings_text = Path(settings_path).read_text(encoding="utf-8")
    settings = json.loads(settings_text)

    input_dir = settings["input_file"]["dir"]
    input_name = settings["input_file"]["file_name"]
    output_dir = settings["output_files"]["dir"]
    output_name = settings["output_files"].get(
        "patterns_output_file_name", "sequential_dense_patterns.csv"
    )
    window_size = int(settings["apriori_parameters"]["window_size"])
    min_support = int(settings["apriori_parameters"]["min_support"])
    max_length = int(settings["apriori_parameters"]["max_length"])
    max_gap = int(settings.get("sequential_parameters", {}).get("max_gap", 0))

    input_path = Path(input_dir) / input_name
    transactions = read_transactions(str(input_path))

    results = find_sequential_dense_patterns(
        transactions, window_size, min_support, max_length, max_gap
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    out_file = output_path / output_name

    write_results(str(out_file), results)
    return str(out_file)


def main() -> None:
    if len(sys.argv) > 1:
        settings_path = sys.argv[1]
    else:
        print("Usage: python sequential_dense.py <settings.json>")
        sys.exit(1)

    start = time.perf_counter()
    output_path = run_from_settings(settings_path)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    print(f"結果を {output_path} に出力しました。")
    print(f"Elapsed time: {elapsed_ms:.3f} ms")


if __name__ == "__main__":
    main()
