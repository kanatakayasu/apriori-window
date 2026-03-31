"""
EX5c: Semi-synthetic Online Retail experiment.

Uses real UCI Online Retail transactions (already preprocessed in dataset/original/)
with synthetic spatial labels (10 "regions") and injected spatial signals.

Complements EX4 (Dunnhumby) by testing on a different real-world retail distribution.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Set

import numpy as np

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

# Paths
DATASET_DIR = Path(__file__).resolve().parent.parent.parent.parent / "dataset" / "original"
RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex5c"


def load_onlineretail(max_n: int = 30000) -> List[Set[int]]:
    """Load Online Retail transactions."""
    path = DATASET_DIR / "onlineretail.txt"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")

    txns = []
    with open(path) as f:
        for i, line in enumerate(f):
            if i >= max_n:
                break
            items = set(int(x) for x in line.strip().split() if x)
            if len(items) >= 2:
                txns.append(items)
    return txns


def run_ex5c():
    print("=" * 60)
    print("EX5c: Semi-Synthetic Online Retail Experiment")
    print("=" * 60)

    N = 30000
    n_locations = 10
    window_t = 200
    threshold = 3
    seed = 42
    rng = np.random.default_rng(seed)

    # Load transactions
    print(f"\nLoading Online Retail transactions (max {N})...")
    txns = load_onlineretail(N)
    actual_n = len(txns)
    print(f"  Loaded: {actual_n} transactions")

    # Assign synthetic spatial locations
    locations = [int(rng.integers(0, n_locations)) for _ in range(actual_n)]

    # Find moderate-frequency items for injection
    item_freq = defaultdict(int)
    for txn in txns:
        for item in txn:
            item_freq[item] += 1

    moderate_items = [it for it in sorted(item_freq.keys())
                      if 30 < item_freq[it] < 300]
    if len(moderate_items) < 6:
        moderate_items = [it for it in sorted(item_freq.keys())
                          if 10 < item_freq[it] < 500]

    rng.shuffle(moderate_items)
    inject_items = moderate_items[:6]

    print(f"  Vocabulary size: {len(item_freq)}")
    print(f"  Moderate-freq items: {len(moderate_items)}")
    print(f"  Injection items: {inject_items}")

    # Define signals
    signals = [
        {
            "pattern": [inject_items[0], inject_items[1]],
            "event_id": "INJ_LOCAL",
            "event_name": "local_promotion",
            "start": 5000, "end": 10000,
            "spatial_scope": list(range(0, 5)),
            "boost_factor": 0.4,
        },
        {
            "pattern": [inject_items[2], inject_items[3]],
            "event_id": "INJ_REGIONAL",
            "event_name": "regional_campaign",
            "start": 15000, "end": 20000,
            "spatial_scope": list(range(3, 8)),
            "boost_factor": 0.35,
        },
    ]

    # Unrelated dense pattern
    unrelated_signal = {
        "pattern": [inject_items[4], inject_items[5]],
        "start": 2000, "end": 4000,
        "spatial_scope": list(range(2, 7)),
        "boost_factor": 0.3,
    }

    # Decoy event
    decoy_event = {
        "event_id": "DECOY",
        "event_name": "decoy_event",
        "start": 11000, "end": 14000,
        "spatial_scope": list(range(7, 10)),
    }

    # Inject signals
    for sig in signals + [unrelated_signal]:
        for t in range(max(0, sig["start"]), min(actual_n, sig["end"] + 1)):
            if locations[t] in set(sig["spatial_scope"]):
                if rng.random() < sig["boost_factor"]:
                    for item in sig["pattern"]:
                        txns[t].add(item)

    print(f"  Signal 1 (local): items {signals[0]['pattern']}, locs 0-4")
    print(f"  Signal 2 (regional): items {signals[1]['pattern']}, locs 3-7")

    # Build events
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

    # Save ground truth
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

    # Config
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
    print("  Running ST pipeline...")
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
    print("  Running 1D baseline...")
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

    # Save
    results = {
        "dataset": "uci_online_retail",
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
    with open(RESULTS_DIR / "ex5c_results.json", "w") as f:
        json.dump(results, f, indent=2, default=float)

    print(f"\n{'='*60}")
    print("EX5c Complete")
    print("=" * 60)

    return results


if __name__ == "__main__":
    run_ex5c()
