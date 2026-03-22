"""
Dense prescription pattern detection.

Uses the apriori_window sliding window algorithm to find time intervals
where co-prescription patterns are unusually frequent.
"""

import sys
from bisect import bisect_left, bisect_right
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Core dense interval computation (re-implemented from apriori_window_basket)
# ---------------------------------------------------------------------------

def compute_dense_intervals(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
) -> List[Tuple[int, int]]:
    """
    Compute dense intervals using the sliding window algorithm.

    A dense interval [s, e] indicates that for every window starting
    position t in [s, e], the pattern occurs >= threshold times
    within [t, t+window_size].

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

        # Stride adjustment (stack-case fix)
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
# Itemset co-occurrence and candidate generation
# ---------------------------------------------------------------------------

def compute_item_transaction_map(
    transactions: List[List[int]],
) -> Dict[int, List[int]]:
    """Build item -> sorted transaction ID list mapping."""
    item_map: Dict[int, List[int]] = {}
    for t_id, txn in enumerate(transactions):
        seen: set = set()
        for item in txn:
            if item not in seen:
                seen.add(item)
                item_map.setdefault(item, []).append(t_id)
    return item_map


def intersect_sorted_lists(lists: Sequence[Sequence[int]]) -> List[int]:
    """Intersect multiple sorted integer lists."""
    if not lists:
        return []
    result = list(lists[0])
    for current in lists[1:]:
        merged: List[int] = []
        i, j = 0, 0
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


def generate_candidates(
    prev_frequents: Sequence[Tuple[int, ...]],
    k: int,
) -> List[Tuple[int, ...]]:
    """Generate k-itemset candidates from (k-1)-itemset frequents."""
    prev_sorted = sorted(prev_frequents)
    candidates_set: set = set()
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
    """Prune candidates using Apriori property."""
    pruned: List[Tuple[int, ...]] = []
    for candidate in candidates:
        all_subsets = combinations(candidate, len(candidate) - 1)
        if all(tuple(subset) in prev_frequents_set for subset in all_subsets):
            pruned.append(candidate)
    return pruned


# ---------------------------------------------------------------------------
# Main mining function
# ---------------------------------------------------------------------------

def find_dense_prescription_patterns(
    transactions: List[List[int]],
    window_size: int,
    threshold: int,
    max_length: int = 4,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """
    Find prescription patterns with dense intervals.

    Args:
        transactions: List of integer-coded transactions
        window_size: Sliding window size
        threshold: Minimum support count within window
        max_length: Maximum itemset size

    Returns:
        Dictionary mapping itemsets to their dense intervals
    """
    item_map = compute_item_transaction_map(transactions)
    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]] = {}
    current_level: List[Tuple[int, ...]] = []
    singleton_intervals: Dict[int, List[Tuple[int, int]]] = {}

    # Single items
    for item in sorted(item_map.keys()):
        timestamps = item_map[item]
        if not timestamps:
            continue
        intervals = compute_dense_intervals(timestamps, window_size, threshold)
        singleton_intervals[item] = intervals
        if intervals:
            key = (item,)
            frequents[key] = intervals
            current_level.append(key)

    # Multi-item candidates
    k = 2
    while current_level and k <= max_length:
        candidates = generate_candidates(current_level, k)
        candidates = prune_candidates(candidates, set(current_level))
        next_level: List[Tuple[int, ...]] = []

        for candidate in candidates:
            # Check singleton interval overlap
            interval_lists = [singleton_intervals.get(item, []) for item in candidate]
            if any(not il for il in interval_lists):
                continue

            # Co-occurrence timestamps
            id_lists = [item_map[item] for item in candidate]
            co_timestamps = intersect_sorted_lists(id_lists)

            intervals = compute_dense_intervals(co_timestamps, window_size, threshold)
            if intervals:
                frequents[candidate] = intervals
                next_level.append(candidate)

        current_level = next_level
        k += 1

    return frequents


def compute_support_time_series(
    timestamps: Sequence[int],
    n_transactions: int,
    window_size: int,
) -> List[int]:
    """
    Compute the support time series for a pattern.

    s_P(t) = number of occurrences in [t, t + window_size)

    Returns a list of length (n_transactions - window_size + 1).
    """
    if window_size < 1 or n_transactions < window_size:
        return []

    ts = list(timestamps)
    series = []
    for t in range(n_transactions - window_size + 1):
        start_idx = bisect_left(ts, t)
        end_idx = bisect_left(ts, t + window_size)
        series.append(end_idx - start_idx)

    return series
