"""
EX5: Real-data validation using Dunnhumby store-level data with real display events.

Uses actual store-specific in-store product displays from causal_data.csv
as ground-truth spatial events. No synthetic injection — purely exploratory.

Strategy:
- Use SINGLE-ITEM patterns (not pairs) because display events affect individual
  product purchase rates, and pair co-occurrence is too sparse at store level
- Use smaller window to capture weekly display effects
- Evaluate whether the pipeline detects support surface changes aligned with
  real in-store display campaigns

Evaluates:
- How many display events produce detectable support surface changes
- Whether ST pipeline attributes patterns to the correct display events
- ST vs 1D comparison on real spatial structure
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Set, Tuple

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

DATA_DIR = Path(__file__).resolve().parent / "data" / "dunnhumby_st"
RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex5"


def load_data() -> Tuple[List[Set[int]], List[int], int, List[dict]]:
    """Load preprocessed Dunnhumby ST data."""
    txns = []
    with open(DATA_DIR / "transactions.txt") as f:
        for line in f:
            items = set(int(x) for x in line.strip().split() if x)
            txns.append(items)

    locations = []
    with open(DATA_DIR / "locations.txt") as f:
        for line in f:
            locations.append(int(line.strip()))

    with open(DATA_DIR / "metadata.json") as f:
        meta = json.load(f)

    with open(DATA_DIR / "events.json") as f:
        events_raw = json.load(f)

    return txns, locations, meta["n_stores"], events_raw


def build_single_item_candidates(
    transactions: List[Set[int]],
    event_products: Set[int],
    min_occurrences: int = 50,
) -> Dict[FrozenSet[int], List]:
    """Build single-item pattern candidates from event-related products.

    For real display events, we use single-item patterns because:
    1. Display events boost individual product purchase rates
    2. Pair co-occurrence is too sparse at per-store granularity
    3. Single items give higher support density for meaningful detection
    """
    item_counts = defaultdict(int)
    for txn in transactions:
        for item in txn:
            if item in event_products:
                item_counts[item] += 1

    frequents = {}
    for item, count in item_counts.items():
        if count >= min_occurrences:
            frequents[frozenset([item])] = []

    return frequents


def run_ex5():
    """Run real-data Dunnhumby experiment."""
    print("=" * 60)
    print("EX5: Dunnhumby Real-Data Validation")
    print("  (Single-item patterns + real display events)")
    print("=" * 60)

    # Load data
    print("\nLoading preprocessed Dunnhumby ST data...")
    txns, locations, n_locations, events_raw = load_data()
    print(f"  Transactions: {len(txns):,}")
    print(f"  Locations: {n_locations}")
    print(f"  Events: {len(events_raw)}")

    # Use all data (84K baskets is tractable for single-item patterns)
    N = len(txns)

    # Filter events
    valid_events = [e for e in events_raw if e["start"] < N and e["end"] < N]
    print(f"  Events within data: {len(valid_events)}")

    # Build SpatialEvent objects
    events = []
    event_products = set()
    for e in valid_events:
        events.append(SpatialEvent(
            event_id=e["event_id"],
            name=e["name"],
            start=e["start"],
            end=e["end"],
            spatial_scope=set(e["spatial_scope"]),
        ))
        event_products.add(e["product_id"])

    print(f"  Event-related products: {len(event_products)}")

    # Also add top co-occurring pairs for event products (small set)
    # First: single-item candidates
    frequents_single = build_single_item_candidates(
        txns, event_products, min_occurrences=30,
    )
    print(f"  Single-item candidates: {len(frequents_single)}")

    # Also find a few frequent pairs for comparison
    pair_counts = defaultdict(int)
    for t in range(N):
        ev_items = sorted(txns[t] & event_products)
        for i in range(len(ev_items)):
            for j in range(i + 1, min(len(ev_items), i + 5)):
                pair_counts[frozenset([ev_items[i], ev_items[j]])] += 1

    frequents_pairs = {}
    for pair, count in pair_counts.items():
        if count >= 30:
            frequents_pairs[pair] = []

    print(f"  Pair candidates: {len(frequents_pairs)}")

    # Combine
    frequents = {**frequents_single, **frequents_pairs}
    print(f"  Total candidates: {len(frequents)}")

    if len(frequents) == 0:
        print("  ERROR: No candidates found. Aborting.")
        return None

    # Window size: ~1 week of baskets (~84K/102weeks ≈ 826 baskets/week)
    # Display events span 2 weeks, so window = ~1600 baskets
    window_t = 800
    min_support = 2  # Lower threshold for real data

    # Pipeline config — relaxed for real data
    config = STAttributionConfig(
        min_support_range=2,
        sigma_s=3.0,
        n_permutations=500,
        alpha=0.10,
        correction_method="bh",
        deduplicate_overlap=True,
        max_cps_per_location=3,
        seed=42,
    )

    # ST pipeline
    print(f"\n  Running ST pipeline (window={window_t}, threshold={min_support})...")
    t0 = time.perf_counter()
    st_results = run_st_attribution_pipeline(
        txns, locations, n_locations, frequents, events,
        window_t, min_support, config,
    )
    st_time = (time.perf_counter() - t0) * 1000

    print(f"  ST results: {len(st_results)} significant attributions ({st_time:.0f}ms)")
    for r in st_results[:20]:
        print(f"    {r.pattern} -> {r.event_name} "
              f"(score={r.attribution_score:.4f}, adj_p={r.adjusted_p_value:.4f})")
    if len(st_results) > 20:
        print(f"    ... and {len(st_results) - 20} more")

    # 1D baseline
    print("\n  Running 1D baseline...")
    t0 = time.perf_counter()
    bl_results = run_1d_baseline_pipeline(
        txns, locations, n_locations, frequents, events,
        window_t, min_support, config,
    )
    bl_time = (time.perf_counter() - t0) * 1000

    print(f"  1D results: {len(bl_results)} significant attributions ({bl_time:.0f}ms)")
    for r in bl_results[:20]:
        print(f"    {r.pattern} -> {r.event_name} "
              f"(score={r.attribution_score:.4f}, adj_p={r.adjusted_p_value:.4f})")
    if len(bl_results) > 20:
        print(f"    ... and {len(bl_results) - 20} more")

    # Analyze results
    print("\n" + "-" * 60)
    print("Analysis")
    print("-" * 60)

    # Which events got attributions?
    st_event_ids = set(r.event_id for r in st_results)
    bl_event_ids = set(r.event_id for r in bl_results)

    print(f"\n  Events with ST attributions: {len(st_event_ids)}/{len(events)}")
    print(f"  Events with 1D attributions: {len(bl_event_ids)}/{len(events)}")
    print(f"  ST-only events: {st_event_ids - bl_event_ids}")
    print(f"  1D-only events: {bl_event_ids - st_event_ids}")
    print(f"  Both: {st_event_ids & bl_event_ids}")

    # Check if attributed patterns involve the event's product
    def check_product_match(results, valid_events):
        correct = 0
        for r in results:
            for e in valid_events:
                if e["event_id"] == r.event_id:
                    if e["product_id"] in r.pattern:
                        correct += 1
                    break
        return correct

    st_correct = check_product_match(st_results, valid_events)
    bl_correct = check_product_match(bl_results, valid_events)

    if st_results:
        print(f"\n  ST: {st_correct}/{len(st_results)} attributions match event product "
              f"({st_correct/len(st_results)*100:.0f}%)")
    if bl_results:
        print(f"  1D: {bl_correct}/{len(bl_results)} attributions match event product "
              f"({bl_correct/len(bl_results)*100:.0f}%)")

    # Pattern type breakdown
    st_single = sum(1 for r in st_results if len(r.pattern) == 1)
    st_pair = sum(1 for r in st_results if len(r.pattern) == 2)
    bl_single = sum(1 for r in bl_results if len(r.pattern) == 1)
    bl_pair = sum(1 for r in bl_results if len(r.pattern) == 2)
    print(f"\n  ST pattern types: {st_single} single-item, {st_pair} pairs")
    print(f"  1D pattern types: {bl_single} single-item, {bl_pair} pairs")

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "dataset": "dunnhumby_complete_journey",
        "description": "Real store-level data with real in-store display events",
        "n_transactions": N,
        "n_locations": n_locations,
        "n_events": len(events),
        "n_candidates_single": len(frequents_single),
        "n_candidates_pair": len(frequents_pairs),
        "n_candidates_total": len(frequents),
        "window_t": window_t,
        "min_support": min_support,
        "st": {
            "n_attributions": len(st_results),
            "n_events_attributed": len(st_event_ids),
            "n_single_item": st_single,
            "n_pair": st_pair,
            "product_match_rate": st_correct / len(st_results) if st_results else 0,
            "time_ms": st_time,
            "attributions": [
                {"pattern": list(r.pattern), "event_id": r.event_id,
                 "event_name": r.event_name, "score": float(r.attribution_score),
                 "adj_p": float(r.adjusted_p_value)}
                for r in st_results
            ],
        },
        "baseline_1d": {
            "n_attributions": len(bl_results),
            "n_events_attributed": len(bl_event_ids),
            "n_single_item": bl_single,
            "n_pair": bl_pair,
            "product_match_rate": bl_correct / len(bl_results) if bl_results else 0,
            "time_ms": bl_time,
            "attributions": [
                {"pattern": list(r.pattern), "event_id": r.event_id,
                 "event_name": r.event_name, "score": float(r.attribution_score),
                 "adj_p": float(r.adjusted_p_value)}
                for r in bl_results
            ],
        },
    }
    with open(RESULTS_DIR / "ex5_results.json", "w") as f:
        json.dump(results, f, indent=2, default=float)

    print(f"\n  Results saved to {RESULTS_DIR / 'ex5_results.json'}")
    print("\n" + "=" * 60)
    print("EX5 Complete")
    print("=" * 60)

    return results


if __name__ == "__main__":
    run_ex5()
