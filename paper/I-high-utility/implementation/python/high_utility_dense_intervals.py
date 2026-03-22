"""
High-Utility Dense Intervals: Joint Frequency-Utility Temporal Mining

This module extends the dense interval framework (apriori_window_basket.py)
to incorporate item utilities, enabling detection of time intervals where
itemsets are both frequent AND high-utility.

Key concepts:
  - Utility-Dense Interval: A time interval where an itemset satisfies
    both a minimum frequency threshold AND a minimum utility threshold.
  - Window Utility: The total utility of an itemset within a sliding window.
  - TWU (Transaction Weighted Utilization) in Window: An upper bound on
    itemset utility within a window, used for pruning.

Author: Paper I pipeline
Date: 2026-03-22
"""

import json
import math
import sys
import time
from bisect import bisect_left, bisect_right
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# Import Phase 1 utilities
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python"))
from apriori_window_basket import (
    compute_dense_intervals,
    compute_dense_intervals_with_candidates,
    generate_candidates,
    intersect_interval_lists,
    intersect_sorted_lists,
    prune_candidates,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class UtilityTransaction:
    """A transaction with item quantities and external utilities."""
    __slots__ = ("tid", "items", "quantities", "transaction_utility")

    def __init__(self, tid: int, items: List[int], quantities: List[int],
                 transaction_utility: float):
        self.tid = tid
        self.items = items
        self.quantities = quantities
        self.transaction_utility = transaction_utility


class UtilityDenseResult:
    """Result of utility-dense interval mining."""
    __slots__ = ("itemset", "intervals", "interval_utilities")

    def __init__(self, itemset: Tuple[int, ...],
                 intervals: List[Tuple[int, int]],
                 interval_utilities: List[float]):
        self.itemset = itemset
        self.intervals = intervals
        self.interval_utilities = interval_utilities


# ---------------------------------------------------------------------------
# I/O: Read utility transaction data
# ---------------------------------------------------------------------------

def read_utility_transactions(path: str) -> Tuple[List[UtilityTransaction], Dict[int, float]]:
    """
    Read transactions with utility information.

    Format (per line):
        items : quantities : transaction_utility
        e.g., "1 3 5 : 2 1 3 : 18"

    Returns:
        transactions: list of UtilityTransaction
        external_utilities: dict mapping item -> external utility (profit per unit)
            If not provided in a separate file, defaults to 1.0 for all items.
    """
    transactions: List[UtilityTransaction] = []
    all_items: Set[int] = set()

    with open(path, "r", encoding="utf-8") as f:
        for tid, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            parts = line.split(":")
            if len(parts) < 3:
                # Fallback: treat as simple items with quantity=1
                items = [int(x) for x in parts[0].split()]
                quantities = [1] * len(items)
                tu = float(len(items))
            else:
                items = [int(x) for x in parts[0].split()]
                quantities = [int(x) for x in parts[1].split()]
                tu = float(parts[2].strip())
            all_items.update(items)
            transactions.append(UtilityTransaction(tid, items, quantities, tu))

    # Default external utilities = 1.0 (internal utility model)
    external_utilities = {item: 1.0 for item in all_items}
    return transactions, external_utilities


def read_external_utilities(path: str) -> Dict[int, float]:
    """
    Read external utility table.

    Format (per line):
        item_id utility_value
        e.g., "3 5.0"
    """
    utilities: Dict[int, float] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            utilities[int(parts[0])] = float(parts[1])
    return utilities


# ---------------------------------------------------------------------------
# Core: Utility computation
# ---------------------------------------------------------------------------

def compute_item_utility(transaction: UtilityTransaction, item: int,
                         external_utilities: Dict[int, float]) -> float:
    """Compute the utility of an item in a transaction: q(item, T) * p(item)."""
    for i, it in enumerate(transaction.items):
        if it == item:
            return transaction.quantities[i] * external_utilities.get(item, 1.0)
    return 0.0


def compute_itemset_utility(transaction: UtilityTransaction,
                            itemset: Tuple[int, ...],
                            external_utilities: Dict[int, float]) -> float:
    """Compute the utility of an itemset in a transaction."""
    item_set = set(itemset)
    if not item_set.issubset(set(transaction.items)):
        return 0.0
    total = 0.0
    for i, it in enumerate(transaction.items):
        if it in item_set:
            total += transaction.quantities[i] * external_utilities.get(it, 1.0)
    return total


def compute_twu(transactions: List[UtilityTransaction],
                item: int) -> float:
    """Compute Transaction Weighted Utilization for a single item."""
    total = 0.0
    for t in transactions:
        if item in t.items:
            total += t.transaction_utility
    return total


# ---------------------------------------------------------------------------
# Core: Window Utility and TWU-in-Window
# ---------------------------------------------------------------------------

def compute_window_utility(transactions: List[UtilityTransaction],
                           itemset: Tuple[int, ...],
                           external_utilities: Dict[int, float],
                           window_start: int,
                           window_end: int) -> float:
    """
    Compute the total utility of an itemset in window [window_start, window_end].
    """
    total = 0.0
    for t in transactions:
        if window_start <= t.tid <= window_end:
            total += compute_itemset_utility(t, itemset, external_utilities)
    return total


def compute_window_twu(transactions: List[UtilityTransaction],
                       itemset: Tuple[int, ...],
                       window_start: int,
                       window_end: int) -> float:
    """
    Compute TWU upper bound for an itemset in window [window_start, window_end].
    TWU(X, W) = sum of TU(T) for all T in W where X is a subset of T.
    """
    item_set = set(itemset)
    total = 0.0
    for t in transactions:
        if window_start <= t.tid <= window_end:
            if item_set.issubset(set(t.items)):
                total += t.transaction_utility
    return total


# ---------------------------------------------------------------------------
# Precomputation: Build maps for efficient access
# ---------------------------------------------------------------------------

def build_item_transaction_map(
    transactions: List[UtilityTransaction],
) -> Dict[int, List[int]]:
    """Map each item to its sorted list of transaction IDs."""
    item_map: Dict[int, List[int]] = {}
    for t in transactions:
        for item in set(t.items):
            item_map.setdefault(item, []).append(t.tid)
    return item_map


def build_transaction_index(
    transactions: List[UtilityTransaction],
) -> Dict[int, UtilityTransaction]:
    """Map tid -> transaction for O(1) lookup."""
    return {t.tid: t for t in transactions}


def compute_prefix_twu(
    transactions: List[UtilityTransaction],
    itemset: Tuple[int, ...],
    item_tx_map: Dict[int, List[int]],
    tx_index: Dict[int, UtilityTransaction],
    n_transactions: int,
) -> List[float]:
    """
    Compute prefix sum of TWU values for an itemset.
    prefix_twu[i] = sum of TU(T_j) for j < i where itemset is in T_j.

    This enables O(1) window TWU queries:
        TWU(itemset, [s, e]) = prefix_twu[e+1] - prefix_twu[s]
    """
    # Find transactions containing all items in itemset
    if len(itemset) == 1:
        containing_tids = set(item_tx_map.get(itemset[0], []))
    else:
        tid_lists = [set(item_tx_map.get(item, [])) for item in itemset]
        containing_tids = tid_lists[0]
        for tl in tid_lists[1:]:
            containing_tids = containing_tids.intersection(tl)

    prefix = [0.0] * (n_transactions + 1)
    for i in range(n_transactions):
        prefix[i + 1] = prefix[i]
        if i in containing_tids:
            prefix[i + 1] += tx_index[i].transaction_utility
    return prefix


def compute_prefix_utility(
    transactions: List[UtilityTransaction],
    itemset: Tuple[int, ...],
    external_utilities: Dict[int, float],
    item_tx_map: Dict[int, List[int]],
    tx_index: Dict[int, UtilityTransaction],
    n_transactions: int,
) -> List[float]:
    """
    Compute prefix sum of actual itemset utilities.
    prefix_util[i] = sum of u(itemset, T_j) for j < i.
    """
    if len(itemset) == 1:
        containing_tids = set(item_tx_map.get(itemset[0], []))
    else:
        tid_lists = [set(item_tx_map.get(item, [])) for item in itemset]
        containing_tids = tid_lists[0]
        for tl in tid_lists[1:]:
            containing_tids = containing_tids.intersection(tl)

    prefix = [0.0] * (n_transactions + 1)
    for i in range(n_transactions):
        prefix[i + 1] = prefix[i]
        if i in containing_tids:
            prefix[i + 1] += compute_itemset_utility(
                tx_index[i], itemset, external_utilities
            )
    return prefix


# ---------------------------------------------------------------------------
# Core: Utility-Dense Interval Detection
# ---------------------------------------------------------------------------

def find_utility_dense_intervals(
    itemset: Tuple[int, ...],
    timestamps: List[int],
    prefix_util: List[float],
    prefix_twu: List[float],
    window_size: int,
    freq_threshold: int,
    util_threshold: float,
    n_transactions: int,
) -> Tuple[List[Tuple[int, int]], List[float]]:
    """
    Find intervals where an itemset is both frequent and high-utility.

    Algorithm:
    1. Use frequency-based dense interval detection (Phase 1) to find
       candidate intervals where the itemset is frequent.
    2. For each dense interval, sweep a window and check the utility
       condition using prefix sums.
    3. Merge consecutive windows satisfying both conditions.

    Returns:
        intervals: list of (start, end) utility-dense intervals
        interval_utilities: list of total utility in each interval
    """
    # Step 1: Get frequency-dense intervals
    freq_intervals = compute_dense_intervals(timestamps, window_size, freq_threshold)
    if not freq_intervals:
        return [], []

    # Step 2: Filter by utility condition
    utility_intervals: List[Tuple[int, int]] = []
    interval_utilities: List[float] = []

    for f_start, f_end in freq_intervals:
        # Sweep windows within this dense interval
        ud_start: Optional[int] = None
        ud_end: Optional[int] = None
        accumulated_util = 0.0

        for l in range(f_start, f_end + 1):
            w_start = l
            w_end = min(l + window_size, n_transactions - 1)

            # O(1) utility query via prefix sum
            window_util = prefix_util[w_end + 1] - prefix_util[w_start]

            if window_util >= util_threshold:
                if ud_start is None:
                    ud_start = l
                ud_end = l
                accumulated_util = max(accumulated_util, window_util)
            else:
                if ud_start is not None and ud_end is not None:
                    utility_intervals.append((ud_start, ud_end))
                    interval_utilities.append(accumulated_util)
                    ud_start = None
                    ud_end = None
                    accumulated_util = 0.0

        if ud_start is not None and ud_end is not None:
            utility_intervals.append((ud_start, ud_end))
            interval_utilities.append(accumulated_util)

    return utility_intervals, interval_utilities


# ---------------------------------------------------------------------------
# Main Mining Algorithm
# ---------------------------------------------------------------------------

def mine_high_utility_dense_itemsets(
    transactions: List[UtilityTransaction],
    external_utilities: Dict[int, float],
    window_size: int,
    freq_threshold: int,
    util_threshold: float,
    max_length: int,
    use_twu_pruning: bool = True,
) -> Tuple[List[UtilityDenseResult], Dict[str, Any]]:
    """
    Main algorithm: Find all itemsets with utility-dense intervals.

    Algorithm (Apriori-style level-wise):
    1. Compute single-item TWU values; prune items with TWU < util_threshold.
    2. For each level k:
       a. Generate candidates from (k-1)-frequent itemsets.
       b. Prune using Apriori property (all subsets must be frequent).
       c. For each candidate:
          - Check TWU upper bound (if enabled): skip if TWU in all windows < threshold.
          - Compute frequency-dense intervals.
          - Within frequency-dense intervals, find utility-dense sub-intervals.
       d. Retain itemsets with non-empty utility-dense intervals.
    3. Return results with statistics.

    Returns:
        results: list of UtilityDenseResult
        stats: dict with mining statistics
    """
    n_transactions = len(transactions)
    item_tx_map = build_item_transaction_map(transactions)
    tx_index = build_transaction_index(transactions)

    stats: Dict[str, Any] = {
        "candidates_generated": 0,
        "candidates_pruned_apriori": 0,
        "candidates_pruned_twu": 0,
        "candidates_evaluated": 0,
        "results_found": 0,
        "total_time_ms": 0.0,
    }

    start_time = time.perf_counter()
    results: List[UtilityDenseResult] = []

    # --- Phase 1: Single items ---
    # Compute global TWU for each item
    item_twu: Dict[int, float] = {}
    for item in item_tx_map:
        item_twu[item] = sum(
            tx_index[tid].transaction_utility
            for tid in item_tx_map[item]
        )

    # Prune items with TWU < util_threshold (TWU is anti-monotone upper bound)
    if use_twu_pruning:
        valid_items = sorted(
            item for item, twu in item_twu.items()
            if twu >= util_threshold
        )
        stats["candidates_pruned_twu"] += len(item_tx_map) - len(valid_items)
    else:
        valid_items = sorted(item_tx_map.keys())

    current_level: List[Tuple[int, ...]] = []
    singleton_freq_intervals: Dict[int, List[Tuple[int, int]]] = {}

    for item in valid_items:
        timestamps = item_tx_map[item]
        if not timestamps:
            continue

        # Frequency-dense intervals
        freq_intervals = compute_dense_intervals(
            timestamps, window_size, freq_threshold
        )
        singleton_freq_intervals[item] = freq_intervals

        if not freq_intervals:
            continue

        itemset = (item,)

        # Compute prefix utility and TWU
        prefix_util = compute_prefix_utility(
            transactions, itemset, external_utilities,
            item_tx_map, tx_index, n_transactions
        )
        prefix_twu = compute_prefix_twu(
            transactions, itemset, item_tx_map, tx_index, n_transactions
        )

        # Find utility-dense intervals
        ud_intervals, ud_utilities = find_utility_dense_intervals(
            itemset, timestamps, prefix_util, prefix_twu,
            window_size, freq_threshold, util_threshold, n_transactions
        )

        stats["candidates_evaluated"] += 1

        if ud_intervals:
            results.append(UtilityDenseResult(itemset, ud_intervals, ud_utilities))
            current_level.append(itemset)

    # --- Phase 2+: Multi-item candidates ---
    k = 2
    while current_level and k <= max_length:
        candidates = generate_candidates(current_level, k)
        stats["candidates_generated"] += len(candidates)

        candidates = prune_candidates(candidates, set(current_level))
        stats["candidates_pruned_apriori"] += (
            stats["candidates_generated"] - len(candidates)
        )

        next_level: List[Tuple[int, ...]] = []

        for candidate in candidates:
            # Check all items are valid
            if not all(item in singleton_freq_intervals for item in candidate):
                continue

            # Intersect singleton frequency intervals for candidate range
            allowed_ranges = intersect_interval_lists(
                [singleton_freq_intervals[item] for item in candidate]
            )
            allowed_ranges = [
                (s, e) for s, e in allowed_ranges if e - s >= window_size
            ]
            if not allowed_ranges:
                continue

            # TWU pruning: check if any window can reach util_threshold
            if use_twu_pruning:
                prefix_twu = compute_prefix_twu(
                    transactions, candidate, item_tx_map, tx_index, n_transactions
                )
                # Check max TWU in any allowed window
                max_twu = 0.0
                for r_start, r_end in allowed_ranges:
                    for l in range(r_start, r_end + 1):
                        w_end = min(l + window_size, n_transactions - 1)
                        w_twu = prefix_twu[w_end + 1] - prefix_twu[l]
                        max_twu = max(max_twu, w_twu)
                        if max_twu >= util_threshold:
                            break
                    if max_twu >= util_threshold:
                        break

                if max_twu < util_threshold:
                    stats["candidates_pruned_twu"] += 1
                    continue

            # Compute co-occurrence timestamps
            tid_lists = [item_tx_map.get(item, []) for item in candidate]
            co_tids = intersect_sorted_lists(tid_lists)
            if not co_tids:
                continue

            # Find frequency-dense intervals in co-occurrence
            freq_intervals = compute_dense_intervals_with_candidates(
                co_tids, window_size, freq_threshold, allowed_ranges
            )
            if not freq_intervals:
                continue

            # Compute prefix utility for candidate
            prefix_util = compute_prefix_utility(
                transactions, candidate, external_utilities,
                item_tx_map, tx_index, n_transactions
            )
            prefix_twu_candidate = compute_prefix_twu(
                transactions, candidate, item_tx_map, tx_index, n_transactions
            )

            # Find utility-dense intervals
            ud_intervals, ud_utilities = find_utility_dense_intervals(
                candidate, co_tids, prefix_util, prefix_twu_candidate,
                window_size, freq_threshold, util_threshold, n_transactions
            )

            stats["candidates_evaluated"] += 1

            if ud_intervals:
                results.append(
                    UtilityDenseResult(candidate, ud_intervals, ud_utilities)
                )
                next_level.append(candidate)

        current_level = next_level
        k += 1

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    stats["total_time_ms"] = elapsed_ms
    stats["results_found"] = len(results)

    return results, stats


# ---------------------------------------------------------------------------
# Synthetic data generation for experiments
# ---------------------------------------------------------------------------

def generate_synthetic_utility_data(
    n_transactions: int = 1000,
    n_items: int = 20,
    max_items_per_tx: int = 8,
    max_quantity: int = 5,
    seed: int = 42,
    inject_pattern: Optional[Dict[str, Any]] = None,
) -> Tuple[List[UtilityTransaction], Dict[int, float]]:
    """
    Generate synthetic utility transaction data.

    Args:
        inject_pattern: Optional dict with keys:
            - "itemset": list of items forming the pattern
            - "interval": (start, end) transaction range
            - "frequency": probability of pattern appearing in interval
            - "high_quantity": quantity boost factor for pattern items
    """
    import random
    rng = random.Random(seed)

    # Generate external utilities (profit per unit)
    external_utilities = {i: rng.uniform(1.0, 10.0) for i in range(n_items)}

    transactions: List[UtilityTransaction] = []
    for tid in range(n_transactions):
        # Random items
        n_items_in_tx = rng.randint(1, max_items_per_tx)
        items = sorted(rng.sample(range(n_items), min(n_items_in_tx, n_items)))
        quantities = [rng.randint(1, max_quantity) for _ in items]

        # Inject pattern if specified
        if inject_pattern is not None:
            p_start, p_end = inject_pattern["interval"]
            if p_start <= tid <= p_end:
                if rng.random() < inject_pattern["frequency"]:
                    for p_item in inject_pattern["itemset"]:
                        if p_item not in items:
                            items.append(p_item)
                            quantities.append(
                                rng.randint(1, max_quantity)
                                * inject_pattern.get("high_quantity", 1)
                            )
                        else:
                            idx = items.index(p_item)
                            quantities[idx] *= inject_pattern.get("high_quantity", 1)
                    # Re-sort
                    paired = sorted(zip(items, quantities))
                    items = [p[0] for p in paired]
                    quantities = [p[1] for p in paired]

        # Compute transaction utility
        tu = sum(
            q * external_utilities.get(item, 1.0)
            for item, q in zip(items, quantities)
        )
        transactions.append(UtilityTransaction(tid, items, quantities, tu))

    return transactions, external_utilities


def write_utility_transactions(
    path: str,
    transactions: List[UtilityTransaction],
) -> None:
    """Write transactions in utility format: items : quantities : TU."""
    with open(path, "w", encoding="utf-8") as f:
        for t in transactions:
            items_str = " ".join(str(i) for i in t.items)
            quant_str = " ".join(str(q) for q in t.quantities)
            f.write(f"{items_str}:{quant_str}:{t.transaction_utility:.2f}\n")


def write_external_utilities(path: str, utilities: Dict[int, float]) -> None:
    """Write external utility table."""
    with open(path, "w", encoding="utf-8") as f:
        for item in sorted(utilities.keys()):
            f.write(f"{item} {utilities[item]:.4f}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run a demo with synthetic data."""
    print("=" * 60)
    print("High-Utility Dense Interval Mining")
    print("=" * 60)

    # Generate synthetic data with injected pattern
    inject = {
        "itemset": [1, 3, 5],
        "interval": (200, 400),
        "frequency": 0.8,
        "high_quantity": 3,
    }
    transactions, ext_utils = generate_synthetic_utility_data(
        n_transactions=1000, n_items=15, max_items_per_tx=6,
        seed=42, inject_pattern=inject,
    )

    print(f"Transactions: {len(transactions)}")
    print(f"Items: {len(ext_utils)}")
    print(f"Injected pattern: {inject['itemset']} in [{inject['interval'][0]}, {inject['interval'][1]}]")
    print()

    # Mine
    results, stats = mine_high_utility_dense_itemsets(
        transactions, ext_utils,
        window_size=50, freq_threshold=10, util_threshold=100.0,
        max_length=4, use_twu_pruning=True,
    )

    print(f"Results: {stats['results_found']}")
    print(f"Candidates generated: {stats['candidates_generated']}")
    print(f"Pruned (Apriori): {stats['candidates_pruned_apriori']}")
    print(f"Pruned (TWU): {stats['candidates_pruned_twu']}")
    print(f"Evaluated: {stats['candidates_evaluated']}")
    print(f"Time: {stats['total_time_ms']:.1f} ms")
    print()

    for r in results:
        if len(r.itemset) >= 2:
            print(f"  Itemset {r.itemset}: {len(r.intervals)} utility-dense intervals")
            for iv, ut in zip(r.intervals, r.interval_utilities):
                print(f"    [{iv[0]}, {iv[1]}] utility={ut:.1f}")


if __name__ == "__main__":
    main()
