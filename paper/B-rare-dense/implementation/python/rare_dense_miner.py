"""
Rare Dense Pattern Miner: Two-Phase Algorithm

Discovers itemsets that are globally rare (gsupp < max_sup)
but locally dense (at least one dense interval with lsup >= theta).

Phase 1: Use sliding-window Apriori to find all locally dense itemsets
Phase 2: Filter to retain only globally rare patterns
"""

import sys
from pathlib import Path
from bisect import bisect_left, bisect_right
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

# Import core functions from existing apriori_window_basket
_repo_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_repo_root / "apriori_window_suite" / "python"))

from apriori_window_basket import (  # noqa: E402
    compute_dense_intervals,
    compute_dense_intervals_with_candidates,
    generate_candidates,
    intersect_interval_lists,
    intersect_sorted_lists,
    prune_candidates,
)


# ---------------------------------------------------------------------------
# Transaction I/O
# ---------------------------------------------------------------------------

def read_flat_transactions(path: str) -> List[List[int]]:
    """Read transactions as flat lists (one transaction per line, space-separated items)."""
    transactions: List[List[int]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                transactions.append([])
                continue
            transactions.append([int(x) for x in line.split()])
    return transactions


# ---------------------------------------------------------------------------
# Support computation
# ---------------------------------------------------------------------------

def compute_global_support(
    transactions: List[List[int]],
    itemset: Tuple[int, ...],
) -> float:
    """Compute global support of an itemset as fraction of total transactions."""
    if not transactions:
        return 0.0
    count = sum(1 for t in transactions if all(item in t for item in itemset))
    return count / len(transactions)


def compute_global_support_count(
    transactions: List[List[int]],
    itemset: Tuple[int, ...],
) -> int:
    """Compute global support count of an itemset."""
    return sum(1 for t in transactions if all(item in t for item in itemset))


# ---------------------------------------------------------------------------
# Item maps (simplified: no basket structure, flat transactions)
# ---------------------------------------------------------------------------

def compute_item_transaction_map(
    transactions: List[List[int]],
) -> Dict[int, List[int]]:
    """Build item -> sorted list of transaction IDs."""
    item_map: Dict[int, List[int]] = {}
    for t_id, txn in enumerate(transactions):
        seen: set = set()
        for item in txn:
            if item not in seen:
                seen.add(item)
                item_map.setdefault(item, []).append(t_id)
    return item_map


# ---------------------------------------------------------------------------
# Phase 1: Dense interval discovery (Apriori with local density pruning)
# ---------------------------------------------------------------------------

def phase1_find_locally_dense(
    transactions: List[List[int]],
    window_size: int,
    theta: int,
    max_length: int,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """
    Phase 1: Find all itemsets that have at least one dense interval.

    Uses Apriori pruning based on local density (Weak Anti-Monotonicity):
    if an itemset has no dense interval, all its supersets are pruned.

    Returns:
        dict mapping itemset -> list of dense intervals
    """
    item_map = compute_item_transaction_map(transactions)
    result: Dict[Tuple[int, ...], List[Tuple[int, int]]] = {}

    current_level: List[Tuple[int, ...]] = []
    singleton_intervals: Dict[int, List[Tuple[int, int]]] = {}

    # --- Singletons ---
    for item in sorted(item_map.keys()):
        timestamps = item_map[item]
        if not timestamps:
            continue
        intervals = compute_dense_intervals(timestamps, window_size, theta)
        singleton_intervals[item] = intervals
        if intervals:
            key = (item,)
            result[key] = intervals
            current_level.append(key)

    # --- Multi-item candidates ---
    k = 2
    while current_level and k <= max_length:
        candidates = generate_candidates(current_level, k)
        candidates = prune_candidates(candidates, set(current_level))
        next_level: List[Tuple[int, ...]] = []

        for candidate in candidates:
            # Intersect singleton dense intervals to get candidate ranges
            sub_intervals = []
            skip = False
            for item in candidate:
                if item not in singleton_intervals or not singleton_intervals[item]:
                    skip = True
                    break
                sub_intervals.append(singleton_intervals[item])
            if skip:
                continue

            allowed_ranges = intersect_interval_lists(sub_intervals)
            allowed_ranges = [
                (s, e) for s, e in allowed_ranges if e - s >= window_size
            ]
            if not allowed_ranges:
                continue

            # Compute co-occurrence timestamps
            ts_lists = [item_map[item] for item in candidate]
            co_timestamps = intersect_sorted_lists(ts_lists)

            intervals = compute_dense_intervals_with_candidates(
                co_timestamps, window_size, theta, allowed_ranges
            )
            if intervals:
                result[candidate] = intervals
                next_level.append(candidate)

        current_level = next_level
        k += 1

    return result


# ---------------------------------------------------------------------------
# Phase 2: Global rarity filtering
# ---------------------------------------------------------------------------

def phase2_filter_rare(
    locally_dense: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    transactions: List[List[int]],
    max_sup: float,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """
    Phase 2: Filter locally dense patterns to retain only globally rare ones.

    Args:
        locally_dense: output of Phase 1
        transactions: full transaction list
        max_sup: maximum global support threshold (patterns with gsupp >= max_sup are removed)

    Returns:
        dict mapping rare dense pattern -> dense intervals
    """
    result: Dict[Tuple[int, ...], List[Tuple[int, int]]] = {}
    n = len(transactions)
    if n == 0:
        return result

    for itemset, intervals in locally_dense.items():
        gsupp = compute_global_support(transactions, itemset)
        if gsupp < max_sup:
            result[itemset] = intervals

    return result


# ---------------------------------------------------------------------------
# Main entry point: Two-Phase Mining
# ---------------------------------------------------------------------------

def mine_rare_dense_patterns(
    transactions: List[List[int]],
    window_size: int,
    theta: int,
    max_sup: float,
    max_length: int = 10,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """
    Two-Phase Rare Dense Pattern Mining.

    Args:
        transactions: list of transactions (each a list of item IDs)
        window_size: sliding window size W
        theta: local density threshold (min occurrences in window)
        max_sup: maximum global support (rarity threshold)
        max_length: maximum itemset size

    Returns:
        dict mapping each Rare Dense Pattern to its list of dense intervals
    """
    # Phase 1: Find locally dense patterns
    locally_dense = phase1_find_locally_dense(
        transactions, window_size, theta, max_length
    )

    # Phase 2: Filter by global rarity
    rare_dense = phase2_filter_rare(locally_dense, transactions, max_sup)

    return rare_dense


def mine_rare_dense_patterns_detailed(
    transactions: List[List[int]],
    window_size: int,
    theta: int,
    max_sup: float,
    max_length: int = 10,
) -> dict:
    """
    Two-Phase Mining with detailed output for analysis.

    Returns dict with:
        - "rare_dense": the RDP results
        - "locally_dense": Phase 1 results (before rarity filter)
        - "stats": summary statistics
    """
    locally_dense = phase1_find_locally_dense(
        transactions, window_size, theta, max_length
    )
    rare_dense = phase2_filter_rare(locally_dense, transactions, max_sup)

    # Compute stats
    n = len(transactions)
    stats = {
        "n_transactions": n,
        "n_locally_dense": len(locally_dense),
        "n_rare_dense": len(rare_dense),
        "n_filtered_out": len(locally_dense) - len(rare_dense),
        "window_size": window_size,
        "theta": theta,
        "max_sup": max_sup,
    }

    return {
        "rare_dense": rare_dense,
        "locally_dense": locally_dense,
        "stats": stats,
    }
