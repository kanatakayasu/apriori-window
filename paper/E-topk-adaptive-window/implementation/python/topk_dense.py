"""
Top-k Dense Pattern Mining with Branch-and-Bound pruning.

Finds the k patterns with highest Multi-Scale Dense Coverage Scores
using Apriori candidate generation + B&B pruning on the itemset lattice.
"""

from __future__ import annotations

import heapq
import math
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Set, Tuple

from adaptive_window import (
    compute_dense_coverage_score,
    compute_dense_intervals,
    compute_multiscale_dcs,
)
from scale_space import detect_scale_space_ridges


def intersect_sorted(a: Sequence[int], b: Sequence[int]) -> List[int]:
    """Intersect two sorted integer lists."""
    result: List[int] = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            result.append(a[i])
            i += 1
            j += 1
        elif a[i] < b[j]:
            i += 1
        else:
            j += 1
    return result


def build_item_timestamps(
    transactions: List[List[int]],
) -> Dict[int, List[int]]:
    """
    Build item -> sorted list of transaction indices.

    Args:
        transactions: list of transactions, each a list of item IDs.

    Returns:
        dict mapping item -> sorted list of transaction indices
    """
    item_ts: Dict[int, List[int]] = {}
    for t_idx, txn in enumerate(transactions):
        seen: Set[int] = set()
        for item in txn:
            if item not in seen:
                seen.add(item)
                item_ts.setdefault(item, []).append(t_idx)
    return item_ts


def compute_itemset_timestamps(
    itemset: Tuple[int, ...],
    item_timestamps: Dict[int, List[int]],
) -> List[int]:
    """Get co-occurrence timestamps for an itemset."""
    if not itemset:
        return []
    lists = [item_timestamps.get(item, []) for item in itemset]
    if any(not lst for lst in lists):
        return []
    result = list(lists[0])
    for lst in lists[1:]:
        result = intersect_sorted(result, lst)
        if not result:
            break
    return result


class TopKResult:
    """Min-heap maintaining top-k results."""

    def __init__(self, k: int):
        self.k = k
        self.heap: List[Tuple[float, Tuple[int, ...]]] = []
        self.threshold = 0.0

    def try_insert(self, score: float, pattern: Tuple[int, ...]) -> bool:
        """Insert if score exceeds current k-th best. Returns True if inserted."""
        if score <= 0:
            return False
        if len(self.heap) < self.k:
            heapq.heappush(self.heap, (score, pattern))
            if len(self.heap) == self.k:
                self.threshold = self.heap[0][0]
            return True
        if score > self.threshold:
            heapq.heapreplace(self.heap, (score, pattern))
            self.threshold = self.heap[0][0]
            return True
        return False

    def get_results(self) -> List[Tuple[Tuple[int, ...], float]]:
        """Return results sorted by score descending."""
        results = [(pat, score) for score, pat in self.heap]
        results.sort(key=lambda x: x[1], reverse=True)
        return results


def mine_topk_dense(
    transactions: List[List[int]],
    k: int,
    w0: int,
    theta0: int,
    max_length: int = 5,
    weights: Optional[Sequence[float]] = None,
) -> List[Tuple[Tuple[int, ...], float, Dict[int, List[Tuple[int, int]]]]]:
    """
    Mine top-k dense patterns using branch-and-bound.

    Args:
        transactions: list of transactions (each a list of items)
        k: number of top patterns to return
        w0: base window size
        theta0: base support threshold
        max_length: maximum itemset length
        weights: per-scale-level weights for MSDCS

    Returns:
        List of (pattern, msdcs_score, {level: intervals}) sorted by score desc.
    """
    if k < 1:
        raise ValueError("k must be >= 1.")
    if w0 < 1 or theta0 < 1:
        raise ValueError("w0 and theta0 must be >= 1.")

    n = len(transactions)
    if n == 0:
        return []

    item_ts = build_item_timestamps(transactions)
    topk = TopKResult(k)

    # Cache for MSDCS scores and intervals
    score_cache: Dict[Tuple[int, ...], Tuple[float, Dict[int, List[Tuple[int, int]]]]] = {}

    def get_msdcs(pattern: Tuple[int, ...]) -> Tuple[float, Dict[int, List[Tuple[int, int]]]]:
        if pattern in score_cache:
            return score_cache[pattern]
        ts = compute_itemset_timestamps(pattern, item_ts)
        score, intervals = compute_multiscale_dcs(ts, w0, theta0, n, weights)
        score_cache[pattern] = (score, intervals)
        return score, intervals

    # Phase 1: Evaluate singletons
    singleton_scores: List[Tuple[float, int]] = []
    for item in sorted(item_ts.keys()):
        pattern = (item,)
        score, intervals = get_msdcs(pattern)
        if score > 0:
            topk.try_insert(score, pattern)
            singleton_scores.append((score, item))

    # Sort singletons by score descending for better pruning
    singleton_scores.sort(reverse=True)
    frequent_singletons = [item for _, item in singleton_scores if _ > 0]

    if max_length < 2:
        results = []
        for pattern, score in topk.get_results():
            _, intervals = score_cache[pattern]
            results.append((pattern, score, intervals))
        return results

    # Phase 2: Enumerate multi-item patterns with B&B
    current_level_patterns: List[Tuple[int, ...]] = [(item,) for item in frequent_singletons]

    for length in range(2, max_length + 1):
        if not current_level_patterns:
            break

        next_level: List[Tuple[int, ...]] = []
        candidates = _generate_candidates(current_level_patterns, length)

        for candidate in candidates:
            # B&B pruning: check if any subset has score <= threshold
            # Use the minimum subset score as upper bound
            upper_bound = float('inf')
            skip = False
            for item in candidate:
                subset = tuple(i for i in candidate if i != item)
                subset_score, _ = get_msdcs(subset)
                if subset_score <= 0:
                    skip = True
                    break
                upper_bound = min(upper_bound, subset_score)

            if skip:
                continue

            # Prune if upper bound <= current k-th threshold
            if len(topk.heap) >= k and upper_bound <= topk.threshold:
                continue

            # Evaluate candidate
            score, intervals = get_msdcs(candidate)
            if score > 0:
                topk.try_insert(score, candidate)
                next_level.append(candidate)

        current_level_patterns = next_level

    # Assemble results
    results = []
    for pattern, score in topk.get_results():
        _, intervals = score_cache[pattern]
        results.append((pattern, score, intervals))
    return results


def _generate_candidates(
    prev_patterns: List[Tuple[int, ...]],
    k: int,
) -> List[Tuple[int, ...]]:
    """Generate k-item candidates from (k-1)-item patterns using Apriori join."""
    prev_sorted = sorted(prev_patterns)
    prev_set = set(prev_patterns)
    candidates: List[Tuple[int, ...]] = []
    seen: Set[Tuple[int, ...]] = set()

    for i in range(len(prev_sorted)):
        for j in range(i + 1, len(prev_sorted)):
            a = prev_sorted[i]
            b = prev_sorted[j]
            if k > 2 and a[:k-2] != b[:k-2]:
                break
            merged = set(a) | set(b)
            if len(merged) == k:
                candidate = tuple(sorted(merged))
                if candidate not in seen:
                    # Apriori pruning: all (k-1)-subsets must be frequent
                    all_valid = True
                    for item in candidate:
                        subset = tuple(x for x in candidate if x != item)
                        if subset not in prev_set:
                            all_valid = False
                            break
                    if all_valid:
                        seen.add(candidate)
                        candidates.append(candidate)

    return sorted(candidates)


def mine_topk_with_ridges(
    transactions: List[List[int]],
    k: int,
    w0: int,
    theta0: int,
    max_length: int = 5,
    min_ridge_levels: int = 2,
) -> List[Dict]:
    """
    Mine top-k patterns and enrich with scale-space ridge information.

    Returns list of dicts:
      {
        'pattern': tuple of ints,
        'msdcs': float,
        'intervals': {level: [(start, end), ...]},
        'ridges': [ridge_dict, ...],
      }
    """
    n = len(transactions)
    item_ts = build_item_timestamps(transactions)

    topk_results = mine_topk_dense(
        transactions, k, w0, theta0, max_length
    )

    enriched = []
    for pattern, score, intervals in topk_results:
        ts = compute_itemset_timestamps(pattern, item_ts)
        ridges = detect_scale_space_ridges(ts, w0, theta0, n, min_ridge_levels)
        enriched.append({
            'pattern': pattern,
            'msdcs': score,
            'intervals': intervals,
            'ridges': ridges,
        })

    return enriched
