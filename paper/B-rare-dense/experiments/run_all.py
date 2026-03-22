"""
Experiments E1-E4 for Paper B: Rare Dense Patterns

E1: Recovery rate of rare dense patterns (vs Apriori-Window, vs baseline rare mining)
E2: Pruning efficiency (candidate count, runtime)
E3: Scalability (N = 1K to 1M)
E4: Real-data case study (using retail.txt)
"""

import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

# Setup imports
_repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_repo_root / "paper" / "B-rare-dense" / "implementation" / "python"))
sys.path.insert(0, str(_repo_root / "apriori_window_suite" / "python"))

from rare_dense_miner import (
    mine_rare_dense_patterns,
    mine_rare_dense_patterns_detailed,
    phase1_find_locally_dense,
    compute_global_support,
)
from apriori_window_basket import find_dense_itemsets


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------

def generate_synthetic_data(
    n_transactions: int,
    n_items: int = 50,
    base_density: float = 0.05,
    rare_dense_patterns: List[dict] = None,
    seed: int = 42,
) -> Tuple[List[List[int]], List[dict]]:
    """
    Generate synthetic transaction data with embedded rare dense patterns.

    Args:
        n_transactions: total number of transactions
        n_items: number of distinct items
        base_density: probability of each item appearing in a random transaction
        rare_dense_patterns: list of dicts with keys:
            - "items": list of items in the pattern
            - "start": burst start transaction
            - "end": burst end transaction
        seed: random seed

    Returns:
        (transactions, ground_truth)
    """
    rng = random.Random(seed)
    if rare_dense_patterns is None:
        rare_dense_patterns = []

    txns = []
    for t in range(n_transactions):
        txn = set()
        # Background noise
        for item in range(1, n_items + 1):
            if rng.random() < base_density:
                txn.add(item)

        # Embed rare dense patterns
        for rdp in rare_dense_patterns:
            if rdp["start"] <= t < rdp["end"]:
                for item in rdp["items"]:
                    txn.add(item)

        txns.append(sorted(txn))

    return txns, rare_dense_patterns


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def baseline_apriori_window(
    transactions: List[List[int]],
    window_size: int,
    threshold: int,
    max_length: int,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """Standard Apriori-Window (finds frequent dense patterns, not rare ones)."""
    # Convert to basket format (single basket per transaction)
    basket_txns = [[txn] for txn in transactions]
    return find_dense_itemsets(basket_txns, window_size, threshold, max_length)


def baseline_rare_mining_naive(
    transactions: List[List[int]],
    max_sup: float,
    max_length: int,
) -> List[Tuple[int, ...]]:
    """
    Naive rare pattern mining: enumerate all itemsets and keep those with gsupp < max_sup.
    Only feasible for small datasets. Limited to pairs for tractability.
    """
    from itertools import combinations as combos

    items = set()
    for txn in transactions:
        items.update(txn)
    items = sorted(items)

    rare_patterns = []
    # Singletons
    for item in items:
        gs = compute_global_support(transactions, (item,))
        if gs < max_sup:
            rare_patterns.append((item,))

    # Pairs (limit to tractable size)
    if max_length >= 2:
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                gs = compute_global_support(transactions, (a, b))
                if gs < max_sup and gs > 0:
                    rare_patterns.append((a, b))

    return rare_patterns


# ---------------------------------------------------------------------------
# E1: Recovery Rate
# ---------------------------------------------------------------------------

def run_e1(seeds: List[int] = None) -> dict:
    """E1: Recovery rate of rare dense patterns on synthetic data."""
    if seeds is None:
        seeds = [42, 123, 456, 789, 1024]

    results = []
    for seed in seeds:
        gt_patterns = [
            {"items": [80, 81], "start": 200, "end": 220},
            {"items": [82, 83, 84], "start": 500, "end": 515},
            {"items": [85, 86], "start": 800, "end": 812},
        ]
        txns, gt = generate_synthetic_data(
            n_transactions=1000, n_items=50, base_density=0.05,
            rare_dense_patterns=gt_patterns, seed=seed,
        )

        W, theta, max_sup, max_len = 10, 4, 0.05, 4

        # Our method
        rdp_result = mine_rare_dense_patterns(txns, W, theta, max_sup, max_len)
        rdp_itemsets = set(rdp_result.keys())

        # Standard Apriori-Window (high threshold = frequent patterns only)
        aw_result = baseline_apriori_window(txns, W, theta, max_len)
        aw_itemsets = set(aw_result.keys())

        # Ground truth itemsets
        gt_itemsets = set()
        for p in gt_patterns:
            gt_itemsets.add(tuple(sorted(p["items"])))

        # Recovery rate
        rdp_recovered = gt_itemsets & rdp_itemsets
        aw_recovered = gt_itemsets & aw_itemsets

        # Multi-item only for GT comparison
        rdp_multi = {k for k in rdp_itemsets if len(k) >= 2}
        aw_multi = {k for k in aw_itemsets if len(k) >= 2}

        results.append({
            "seed": seed,
            "rdp_recovery": len(rdp_recovered) / len(gt_itemsets) if gt_itemsets else 0,
            "aw_recovery": len(aw_recovered) / len(gt_itemsets) if gt_itemsets else 0,
            "rdp_total_patterns": len(rdp_multi),
            "aw_total_patterns": len(aw_multi),
            "gt_patterns": len(gt_itemsets),
            "rdp_recovered": len(rdp_recovered),
            "aw_recovered": len(aw_recovered),
        })

    return {"experiment": "E1_recovery_rate", "results": results}


# ---------------------------------------------------------------------------
# E2: Pruning Efficiency
# ---------------------------------------------------------------------------

def run_e2(seeds: List[int] = None) -> dict:
    """E2: Pruning efficiency comparison."""
    if seeds is None:
        seeds = [42, 123, 456, 789, 1024]

    results = []
    for seed in seeds:
        gt_patterns = [
            {"items": [80, 81], "start": 200, "end": 220},
            {"items": [85, 86], "start": 600, "end": 618},
        ]
        txns, _ = generate_synthetic_data(
            n_transactions=1000, n_items=30, base_density=0.08,
            rare_dense_patterns=gt_patterns, seed=seed,
        )

        W, theta, max_sup, max_len = 10, 4, 0.05, 3

        # Two-Phase (our method) with timing
        t0 = time.perf_counter()
        detail = mine_rare_dense_patterns_detailed(txns, W, theta, max_sup, max_len)
        t_rdp = time.perf_counter() - t0

        # Standard Apriori-Window with timing
        t0 = time.perf_counter()
        aw_result = baseline_apriori_window(txns, W, theta, max_len)
        t_aw = time.perf_counter() - t0

        results.append({
            "seed": seed,
            "rdp_time_ms": t_rdp * 1000,
            "aw_time_ms": t_aw * 1000,
            "rdp_phase1_candidates": detail["stats"]["n_locally_dense"],
            "rdp_final_patterns": detail["stats"]["n_rare_dense"],
            "rdp_filtered_out": detail["stats"]["n_filtered_out"],
            "aw_patterns": len(aw_result),
        })

    return {"experiment": "E2_pruning_efficiency", "results": results}


# ---------------------------------------------------------------------------
# E3: Scalability
# ---------------------------------------------------------------------------

def run_e3() -> dict:
    """E3: Scalability test (N = 1K, 5K, 10K, 50K, 100K)."""
    sizes = [1000, 5000, 10000, 50000, 100000]
    results = []

    for n in sizes:
        gt_patterns = [
            {"items": [80, 81], "start": int(n * 0.3), "end": int(n * 0.3) + 20},
            {"items": [85, 86], "start": int(n * 0.7), "end": int(n * 0.7) + 15},
        ]
        txns, _ = generate_synthetic_data(
            n_transactions=n, n_items=30, base_density=0.05,
            rare_dense_patterns=gt_patterns, seed=42,
        )

        W, theta, max_sup, max_len = 10, 4, 0.05, 3

        t0 = time.perf_counter()
        result = mine_rare_dense_patterns(txns, W, theta, max_sup, max_len)
        elapsed = time.perf_counter() - t0

        results.append({
            "n_transactions": n,
            "time_ms": elapsed * 1000,
            "n_patterns": len(result),
        })
        print(f"  N={n:>7d}: {elapsed*1000:.1f}ms, {len(result)} patterns")

    return {"experiment": "E3_scalability", "results": results}


# ---------------------------------------------------------------------------
# E4: Real Data Case Study
# ---------------------------------------------------------------------------

def run_e4() -> dict:
    """E4: Real data case study using retail.txt if available."""
    retail_path = _repo_root / "dataset" / "retail.txt"
    if not retail_path.exists():
        return {
            "experiment": "E4_real_data",
            "status": "SKIPPED",
            "reason": f"retail.txt not found at {retail_path}",
        }

    # Read retail.txt
    txns = []
    with open(retail_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                txns.append([int(x) for x in line.split()])

    # Limit to first 10000 transactions for speed
    txns = txns[:10000]

    W, theta, max_sup, max_len = 20, 5, 0.02, 3

    t0 = time.perf_counter()
    detail = mine_rare_dense_patterns_detailed(txns, W, theta, max_sup, max_len)
    elapsed = time.perf_counter() - t0

    # Collect top patterns by number of dense intervals
    rdp = detail["rare_dense"]
    top_patterns = sorted(rdp.items(), key=lambda kv: len(kv[1]), reverse=True)[:10]
    top_info = []
    for itemset, intervals in top_patterns:
        gs = compute_global_support(txns, itemset)
        top_info.append({
            "itemset": list(itemset),
            "n_intervals": len(intervals),
            "global_support": round(gs, 6),
            "intervals": [(s, e) for s, e in intervals[:3]],  # first 3
        })

    return {
        "experiment": "E4_real_data",
        "status": "OK",
        "n_transactions": len(txns),
        "time_ms": elapsed * 1000,
        "stats": detail["stats"],
        "top_patterns": top_info,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("Paper B: Rare Dense Patterns — Experiments")
    print("=" * 60)

    # E1
    print("\n[E1] Recovery Rate...")
    e1 = run_e1()
    with open(out_dir / "e1_recovery.json", "w") as f:
        json.dump(e1, f, indent=2)
    avg_rdp = sum(r["rdp_recovery"] for r in e1["results"]) / len(e1["results"])
    avg_aw = sum(r["aw_recovery"] for r in e1["results"]) / len(e1["results"])
    print(f"  RDP avg recovery: {avg_rdp:.2%}")
    print(f"  A-W avg recovery: {avg_aw:.2%}")

    # E2
    print("\n[E2] Pruning Efficiency...")
    e2 = run_e2()
    with open(out_dir / "e2_pruning.json", "w") as f:
        json.dump(e2, f, indent=2)
    avg_rdp_t = sum(r["rdp_time_ms"] for r in e2["results"]) / len(e2["results"])
    avg_aw_t = sum(r["aw_time_ms"] for r in e2["results"]) / len(e2["results"])
    print(f"  RDP avg time: {avg_rdp_t:.1f}ms")
    print(f"  A-W avg time: {avg_aw_t:.1f}ms")

    # E3
    print("\n[E3] Scalability...")
    e3 = run_e3()
    with open(out_dir / "e3_scalability.json", "w") as f:
        json.dump(e3, f, indent=2)

    # E4
    print("\n[E4] Real Data Case Study...")
    e4 = run_e4()
    with open(out_dir / "e4_realdata.json", "w") as f:
        json.dump(e4, f, indent=2)
    print(f"  Status: {e4.get('status', 'N/A')}")
    if e4.get("status") == "OK":
        print(f"  Patterns found: {e4['stats']['n_rare_dense']}")
        print(f"  Time: {e4['time_ms']:.1f}ms")

    print("\n" + "=" * 60)
    print("All experiments completed. Results in:", out_dir)
    print("=" * 60)


if __name__ == "__main__":
    main()
