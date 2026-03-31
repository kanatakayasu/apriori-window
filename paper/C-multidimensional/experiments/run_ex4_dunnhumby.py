"""
EX4: Semi-synthetic experiment using Dunnhumby real retail data.

Approach:
- Use real Dunnhumby transactions (subset for tractability)
- Assign synthetic spatial locations (20 stores)
- Inject spatial events with known patterns and spatial scopes
- Evaluate ST pipeline's ability to detect injected events in real data

This tests the pipeline on realistic item distributions and co-occurrence patterns
while retaining ground truth for quantitative evaluation.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Set

import numpy as np

# Add implementation dir to path
_impl_dir = str(Path(__file__).resolve().parent.parent / "implementation" / "python")
if _impl_dir not in sys.path:
    sys.path.insert(0, _impl_dir)

from st_event_attribution import (
    STAttributionConfig,
    SpatialEvent,
    run_st_attribution_pipeline,
    run_1d_baseline_pipeline,
)
from run_st_experiments import find_frequent_pairs, evaluate


# Navigate from experiments/ -> C-multidimensional/ -> paper/ -> repo root -> dataset/
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "dataset" / "dunnhumby"
RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex4"


def load_dunnhumby_subset(n_transactions: int = 20000) -> List[Set[int]]:
    """Load first N transactions from Dunnhumby dataset."""
    txn_path = DATA_DIR / "transactions.txt"
    if not txn_path.exists():
        raise FileNotFoundError(f"{txn_path} not found. Run preprocess_dunnhumby.py first.")

    txns = []
    with open(txn_path) as f:
        for i, line in enumerate(f):
            if i >= n_transactions:
                break
            items = set(int(x) for x in line.strip().split() if x)
            txns.append(items)
    return txns


def find_common_pairs(transactions: List[Set[int]], top_k: int = 20) -> List[tuple]:
    """Find the most common item pairs in the dataset."""
    pair_counts = defaultdict(int)
    for txn in transactions:
        items = sorted(txn)
        if len(items) > 30:
            items = items[:30]
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                pair_counts[(items[i], items[j])] += 1

    sorted_pairs = sorted(pair_counts.items(), key=lambda x: -x[1])
    return [(p, c) for p, c in sorted_pairs[:top_k]]


def inject_spatial_signals(
    transactions: List[Set[int]],
    locations: List[int],
    signals: List[dict],
    rng: np.random.Generator,
) -> None:
    """Inject spatial signals into transactions (in-place)."""
    N = len(transactions)
    for sig in signals:
        pattern = sig["pattern"]
        start, end = sig["start"], sig["end"]
        scope = set(sig["spatial_scope"])
        beta = sig["boost_factor"]

        for t in range(max(0, start), min(N, end + 1)):
            if locations[t] in scope:
                if rng.random() < beta:
                    for item in pattern:
                        transactions[t].add(item)


def run_ex4():
    """Run semi-synthetic Dunnhumby experiment."""
    print("=" * 60)
    print("EX4: Semi-Synthetic Dunnhumby Experiment")
    print("=" * 60)

    N = 20000
    n_locations = 20
    window_t = 200
    threshold = 3
    seed = 42
    rng = np.random.default_rng(seed)

    # Load real transactions
    print(f"\nLoading {N} Dunnhumby transactions...")
    txns = load_dunnhumby_subset(N)
    actual_n = len(txns)
    print(f"  Loaded: {actual_n} transactions")

    # Find common pairs to use as injection targets (using vocabulary items)
    common_pairs = find_common_pairs(txns, top_k=10)
    print(f"  Top 5 common pairs:")
    for (a, b), c in common_pairs[:5]:
        print(f"    ({a}, {b}): {c} co-occurrences")

    # Assign random spatial locations
    locations = [int(rng.integers(0, n_locations)) for _ in range(actual_n)]

    # Choose injection patterns from RARE pairs (not in top common pairs)
    # Use items from the vocabulary but pairs that are rare
    # This ensures the boost is detectable but not trivially so
    all_items = set()
    for txn in txns:
        all_items.update(txn)
    item_list = sorted(all_items)

    # Pick items that appear moderately (not too frequent, not too rare)
    item_freq = defaultdict(int)
    for txn in txns:
        for item in txn:
            item_freq[item] += 1

    moderate_items = [it for it in item_list if 50 < item_freq[it] < 500]
    if len(moderate_items) < 10:
        moderate_items = [it for it in item_list if 20 < item_freq[it] < 1000]

    rng.shuffle(moderate_items)
    inject_items = moderate_items[:6]  # 3 pairs

    # Define injected signals
    signals = [
        {
            "pattern": [inject_items[0], inject_items[1]],
            "event_id": "INJ_LOCAL",
            "event_name": "injected_local_campaign",
            "start": 4000, "end": 8000,
            "spatial_scope": list(range(0, 10)),  # half the stores
            "boost_factor": 0.4,
        },
        {
            "pattern": [inject_items[2], inject_items[3]],
            "event_id": "INJ_GLOBAL",
            "event_name": "injected_global_campaign",
            "start": 12000, "end": 16000,
            "spatial_scope": list(range(0, 20)),  # all stores
            "boost_factor": 0.4,
        },
    ]

    # Unrelated dense pattern (no event)
    unrelated_signal = {
        "pattern": [inject_items[4], inject_items[5]],
        "start": 2000, "end": 3500,
        "spatial_scope": list(range(5, 15)),
        "boost_factor": 0.3,
    }

    # Decoy event (no pattern change)
    decoy_event = {
        "event_id": "DECOY",
        "event_name": "decoy_campaign",
        "start": 9000, "end": 11000,
        "spatial_scope": list(range(15, 20)),
    }

    print(f"\n  Injection items: {inject_items}")
    print(f"  Signal 1 (local): items {signals[0]['pattern']}, locs 0-9, t=[4000,8000]")
    print(f"  Signal 2 (global): items {signals[1]['pattern']}, all locs, t=[12000,16000]")
    print(f"  Unrelated: items {unrelated_signal['pattern']}, locs 5-14, t=[2000,3500]")

    # Inject signals
    inject_spatial_signals(txns, locations, signals, rng)
    inject_spatial_signals(txns, locations, [unrelated_signal], rng)

    # Build events list
    events = []
    for s in signals:
        events.append(SpatialEvent(
            event_id=s["event_id"], name=s["event_name"],
            start=s["start"], end=s["end"],
            spatial_scope=set(s["spatial_scope"]),
        ))
    events.append(SpatialEvent(
        event_id=decoy_event["event_id"], name=decoy_event["event_name"],
        start=decoy_event["start"], end=decoy_event["end"],
        spatial_scope=set(decoy_event["spatial_scope"]),
    ))

    # Write ground truth and unrelated for evaluation
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    gt = [{"pattern": sorted(s["pattern"]), "event_id": s["event_id"]} for s in signals]
    with open(RESULTS_DIR / "ground_truth.json", "w") as f:
        json.dump(gt, f, indent=2)

    unrelated = [{"pattern": sorted(unrelated_signal["pattern"])}]
    with open(RESULTS_DIR / "unrelated_patterns.json", "w") as f:
        json.dump(unrelated, f, indent=2)

    # Find frequent pairs
    frequents = find_frequent_pairs(txns, locations, window_t, threshold, n_locations)
    print(f"\n  Candidate patterns: {len(frequents)}")

    # Check injection patterns in candidates
    for s in signals:
        pat = frozenset(s["pattern"])
        present = pat in frequents
        print(f"    {sorted(s['pattern'])}: {'YES' if present else 'NO'}")

    # Pipeline config
    config = STAttributionConfig(
        min_support_range=5,
        sigma_s=3.0,
        n_permutations=1000,
        alpha=0.10,
        correction_method="bh",
        deduplicate_overlap=True,
        seed=seed,
    )

    # ST pipeline
    print("\n  Running ST pipeline...")
    t0 = time.perf_counter()
    st_results = run_st_attribution_pipeline(
        txns, locations, n_locations, frequents, events,
        window_t, threshold, config,
    )
    st_time = (time.perf_counter() - t0) * 1000

    st_eval = evaluate(
        st_results,
        str(RESULTS_DIR / "ground_truth.json"),
        str(RESULTS_DIR / "unrelated_patterns.json"),
    )
    print(f"  ST: F1={st_eval['f1']:.3f} P={st_eval['precision']:.3f} "
          f"R={st_eval['recall']:.3f} FAR={st_eval['far']:.2f} "
          f"#pred={st_eval['n_predicted']} time={st_time:.0f}ms")
    for r in st_results:
        print(f"    {r.pattern} -> {r.event_name} (adj_p={r.adjusted_p_value:.4f})")

    # 1D baseline
    print("\n  Running 1D baseline...")
    t0 = time.perf_counter()
    bl_results = run_1d_baseline_pipeline(
        txns, locations, n_locations, frequents, events,
        window_t, threshold, config,
    )
    bl_time = (time.perf_counter() - t0) * 1000

    bl_eval = evaluate(
        bl_results,
        str(RESULTS_DIR / "ground_truth.json"),
        str(RESULTS_DIR / "unrelated_patterns.json"),
    )
    print(f"  1D: F1={bl_eval['f1']:.3f} P={bl_eval['precision']:.3f} "
          f"R={bl_eval['recall']:.3f} FAR={bl_eval['far']:.2f} "
          f"#pred={bl_eval['n_predicted']} time={bl_time:.0f}ms")
    for r in bl_results:
        print(f"    {r.pattern} -> {r.event_name} (adj_p={r.adjusted_p_value:.4f})")

    # Save results
    results = {
        "n_transactions": actual_n,
        "n_locations": n_locations,
        "n_candidates": len(frequents),
        "injected_patterns": [sorted(s["pattern"]) for s in signals],
        "st": {**st_eval, "time_ms": st_time},
        "baseline_1d": {**bl_eval, "time_ms": bl_time},
        "st_attributions": [
            {"pattern": list(r.pattern), "event": r.event_name,
             "score": r.attribution_score, "adj_p": r.adjusted_p_value}
            for r in st_results
        ],
        "bl_attributions": [
            {"pattern": list(r.pattern), "event": r.event_name,
             "score": r.attribution_score, "adj_p": r.adjusted_p_value}
            for r in bl_results
        ],
    }
    with open(RESULTS_DIR / "ex4_results.json", "w") as f:
        json.dump(results, f, indent=2, default=float)

    print("\n" + "=" * 60)
    print("EX4 Complete")
    print("=" * 60)

    return results


if __name__ == "__main__":
    run_ex4()
