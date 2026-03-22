"""
Dense alarm pattern detection for manufacturing fault diagnosis.

Uses the apriori_window sliding window algorithm to find time intervals
where alarm co-occurrence patterns are unusually frequent, indicating
equipment degradation or systematic faults.
"""

import sys
from bisect import bisect_left, bisect_right
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Core dense interval computation (from apriori_window_basket)
# ---------------------------------------------------------------------------

def compute_dense_intervals(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
) -> List[Tuple[int, int]]:
    """
    Compute dense intervals using the sliding window algorithm.

    Includes stack-case fix: when window_occurrences[surplus] == l,
    fall back to l += 1.
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

        # Stack-case fix
        surplus = count - threshold
        next_l = window_occurrences[surplus]
        if next_l > l:
            l = next_l
        else:
            l += 1

    if in_dense and start is not None and end is not None:
        intervals.append((start, end))

    return intervals


def compute_dense_intervals_with_candidates(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
    candidate_ranges: Sequence[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    """Compute dense intervals restricted to candidate ranges."""
    if not candidate_ranges or not timestamps:
        return []
    if window_size < 1 or threshold < 1:
        raise ValueError("window_size and threshold must be >= 1.")

    ts = list(timestamps)
    intervals: List[Tuple[int, int]] = []
    ts_last = ts[-1]

    for c_start, c_end in sorted(candidate_ranges):
        l = c_start
        in_dense = False
        start: Optional[int] = None
        end: Optional[int] = None

        while l <= c_end and l <= ts_last:
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
# Utility functions
# ---------------------------------------------------------------------------

def intersect_sorted_lists(lists: Sequence[Sequence[int]]) -> List[int]:
    """Compute intersection of sorted lists."""
    if not lists:
        return []
    result = list(lists[0])
    for current in lists[1:]:
        merged: List[int] = []
        i = j = 0
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
    """Compute intersection of interval lists."""
    if not intervals_list:
        return []
    result = list(intervals_list[0])
    for other in intervals_list[1:]:
        merged: List[Tuple[int, int]] = []
        i = j = 0
        while i < len(result) and j < len(other):
            start = max(result[i][0], other[j][0])
            end = min(result[i][1], other[j][1])
            if start <= end:
                merged.append((start, end))
            if result[i][1] < other[j][1]:
                i += 1
            else:
                j += 1
        result = merged
        if not result:
            break
    return result


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

def generate_candidates(
    prev_frequents: Sequence[Tuple[int, ...]],
    k: int,
) -> List[Tuple[int, ...]]:
    """Generate k-item candidates from (k-1)-item frequent sets."""
    prev_sorted = sorted(prev_frequents)
    candidates_set = set()
    for i in range(len(prev_sorted)):
        for j in range(i + 1, len(prev_sorted)):
            left = prev_sorted[i]
            right = prev_sorted[j]
            if k > 2 and left[:k - 2] != right[:k - 2]:
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
    """Prune candidates using Apriori property."""
    pruned: List[Tuple[int, ...]] = []
    for candidate in candidates:
        all_subsets = combinations(candidate, len(candidate) - 1)
        if all(tuple(subset) in prev_frequents_set for subset in all_subsets):
            pruned.append(candidate)
    return pruned


# ---------------------------------------------------------------------------
# Transaction map computation
# ---------------------------------------------------------------------------

def compute_item_transaction_map(
    transactions: List[List[List[int]]],
) -> Dict[int, List[int]]:
    """
    Build item -> transaction_id mapping.

    Args:
        transactions: Basket-format transactions

    Returns:
        Dict mapping item_id -> sorted list of transaction indices
    """
    item_map: Dict[int, List[int]] = {}
    for t_id, baskets in enumerate(transactions):
        seen: set = set()
        for basket in baskets:
            for item in basket:
                if item not in seen:
                    seen.add(item)
                    item_map.setdefault(item, []).append(t_id)
    return item_map


# ---------------------------------------------------------------------------
# Support time series
# ---------------------------------------------------------------------------

def compute_support_time_series(
    timestamps: Sequence[int],
    n_transactions: int,
    window_size: int,
) -> List[int]:
    """
    Compute support count for each sliding window position.

    Returns list of length n_transactions where entry t is the count
    of timestamps in [t, t + window_size].
    """
    ts = list(timestamps)
    result = []
    for t in range(n_transactions):
        lo = bisect_left(ts, t)
        hi = bisect_right(ts, t + window_size)
        result.append(hi - lo)
    return result


# ---------------------------------------------------------------------------
# Main mining function
# ---------------------------------------------------------------------------

def find_dense_alarm_patterns(
    transactions: List[List[List[int]]],
    window_size: int,
    threshold: int,
    max_length: int,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """
    Find dense alarm co-occurrence patterns using Apriori-window.

    Args:
        transactions: Basket-format transactions (alarm IDs per time bin)
        window_size: Sliding window size
        threshold: Minimum support count within window
        max_length: Maximum pattern length

    Returns:
        Dict mapping pattern -> list of dense intervals
    """
    item_map = compute_item_transaction_map(transactions)
    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]] = {}

    current_level: List[Tuple[int, ...]] = []
    singleton_intervals: Dict[int, List[Tuple[int, int]]] = {}

    # --- Singleton items ---
    for item in sorted(item_map.keys()):
        timestamps = item_map[item]
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

    # --- Multi-item candidates ---
    k = 2
    while current_level and k <= max_length:
        candidates = generate_candidates(current_level, k)
        candidates = prune_candidates(candidates, set(current_level))
        next_level: List[Tuple[int, ...]] = []

        for candidate in candidates:
            allowed_ranges = intersect_interval_lists(
                [singleton_intervals[item] for item in candidate]
            )
            allowed_ranges = [
                (s, e) for (s, e) in allowed_ranges if e - s >= window_size
            ]
            if not allowed_ranges:
                continue

            co_timestamps = intersect_sorted_lists(
                [item_map[item] for item in candidate]
            )

            intervals = compute_dense_intervals_with_candidates(
                co_timestamps, window_size, threshold, allowed_ranges
            )
            if intervals:
                frequents[candidate] = intervals
                next_level.append(candidate)

        current_level = next_level
        k += 1

    return frequents
