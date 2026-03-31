"""
Spatio-Temporal Event Attribution Experiments.

EX1: Core attribution (spatial-local vs global vs 1D baseline)
EX2: Parameter sensitivity
EX3: Semi-realistic retail scenario
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
from typing import Dict, FrozenSet, List, Set, Tuple

import numpy as np

# Add implementation dir to path
_impl_dir = str(Path(__file__).resolve().parent.parent / "implementation" / "python")
if _impl_dir not in sys.path:
    sys.path.insert(0, _impl_dir)

from gen_st_synthetic import (
    STDecoyEvent,
    STPlantedSignal,
    STSyntheticConfig,
    STUnrelatedDense,
    generate_st_synthetic,
    make_confound_config,
    make_dense_config,
    make_ex1_config,
)
from st_event_attribution import (
    STAttributionConfig,
    STSignificantAttribution,
    SpatialEvent,
    run_1d_baseline_pipeline,
    run_st_attribution_pipeline,
)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(
    predicted: List[STSignificantAttribution],
    gt_path: str,
    unrelated_path: str,
) -> Dict:
    """Evaluate predicted attributions against ground truth."""
    with open(gt_path) as f:
        gt_raw = json.load(f)
    with open(unrelated_path) as f:
        unrelated_raw = json.load(f)

    # Ground truth set: (pattern_tuple, event_id)
    gt_set = set()
    for entry in gt_raw:
        pat = tuple(sorted(entry["pattern"]))
        gt_set.add((pat, entry["event_id"]))

    # Predicted set
    pred_set = set()
    for p in predicted:
        pred_set.add((p.pattern, p.event_id))

    tp = len(gt_set & pred_set)
    fp = len(pred_set - gt_set)
    fn = len(gt_set - pred_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # FAR: fraction of unrelated patterns falsely attributed
    unrelated_patterns = {tuple(sorted(u["pattern"])) for u in unrelated_raw}
    falsely_attributed = {pat for pat, _ in pred_set if pat in unrelated_patterns}
    far = len(falsely_attributed) / len(unrelated_patterns) if unrelated_patterns else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1,
        "far": far, "n_predicted": len(pred_set),
    }


# ---------------------------------------------------------------------------
# Phase 1 substitute: find frequent itemsets from transactions
# ---------------------------------------------------------------------------

def find_frequent_pairs(
    transactions: List[Set[int]],
    locations: List[int],
    window_t: int,
    min_support: int,
    n_locations: int,
    min_cooccurrence: int = 20,
    percentile_threshold: float = 95.0,
) -> Dict[FrozenSet[int], List]:
    """
    Frequent pair finder with adaptive threshold.

    Finds 2-itemsets whose global co-occurrence exceeds both
    min_cooccurrence and the specified percentile of all pair counts.
    This filters out baseline noise while keeping genuinely elevated pairs.
    """
    pair_counts = defaultdict(int)
    for txn in transactions:
        items = sorted(txn)
        if len(items) > 20:  # skip very large transactions
            items = items[:20]
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                pair_counts[(items[i], items[j])] += 1

    if not pair_counts:
        return {}

    # Adaptive threshold: use the higher of min_cooccurrence and percentile
    all_counts = list(pair_counts.values())
    pct_thresh = float(np.percentile(all_counts, percentile_threshold))
    effective_thresh = max(min_cooccurrence, pct_thresh)

    candidates = {
        frozenset(pair): []
        for pair, count in pair_counts.items()
        if count >= effective_thresh
    }

    return candidates


# ---------------------------------------------------------------------------
# Load data helpers
# ---------------------------------------------------------------------------

def load_transactions(path: str) -> List[Set[int]]:
    txns = []
    with open(path) as f:
        for line in f:
            items = set(int(x) for x in line.strip().split() if x)
            txns.append(items)
    return txns


def load_locations(path: str) -> List[int]:
    locs = []
    with open(path) as f:
        for line in f:
            locs.append(int(line.strip()))
    return locs


def load_events(path: str) -> List[SpatialEvent]:
    with open(path) as f:
        raw = json.load(f)
    events = []
    for e in raw:
        events.append(SpatialEvent(
            event_id=e["event_id"], name=e["name"],
            start=e["start"], end=e["end"],
            spatial_scope=set(e.get("spatial_scope", [])),
        ))
    return events


# ---------------------------------------------------------------------------
# EX1: Core Attribution
# ---------------------------------------------------------------------------

def run_ex1():
    """EX1: Compare ST pipeline vs 1D baseline across conditions."""
    print("=" * 60)
    print("EX1: Core Spatio-Temporal Attribution")
    print("=" * 60)

    conditions = {
        "beta_0.1": lambda s: make_ex1_config(beta=0.1, seed=s),
        "beta_0.2": lambda s: make_ex1_config(beta=0.2, seed=s),
        "beta_0.3": lambda s: make_ex1_config(beta=0.3, seed=s),
        "beta_0.5": lambda s: make_ex1_config(beta=0.5, seed=s),
        "CONFOUND": lambda s: make_confound_config(beta=0.3, seed=s),
        "DENSE": lambda s: make_dense_config(beta=0.3, seed=s),
    }

    seeds = [42, 123, 456, 789, 1024]
    window_t = 200
    min_support = 3
    n_permutations = 1000

    results_dir = Path(__file__).parent / "results" / "ex1"
    results_dir.mkdir(parents=True, exist_ok=True)

    all_results = []

    for cond_name, config_fn in conditions.items():
        print(f"\n--- Condition: {cond_name} ---")
        st_metrics = []
        baseline_metrics = []

        for seed in seeds:
            data_config = config_fn(seed)
            data_dir = str(results_dir / f"data_{cond_name}_s{seed}")
            generate_st_synthetic(data_config, data_dir)

            # Load data
            txns = load_transactions(os.path.join(data_dir, "transactions.txt"))
            locs = load_locations(os.path.join(data_dir, "locations.txt"))
            events = load_events(os.path.join(data_dir, "events.json"))
            n_locs = data_config.n_locations

            # Find frequent pairs
            frequents = find_frequent_pairs(txns, locs, window_t, min_support, n_locs)

            # Pipeline config
            pipe_config = STAttributionConfig(
                min_support_range=5,
                # sigma_t defaults to window_t / 4 in pipeline
                sigma_s=3.0,
                n_permutations=n_permutations,
                alpha=0.10,
                correction_method="bh",
                deduplicate_overlap=True,
                seed=seed,
            )

            # ST pipeline
            t0 = time.perf_counter()
            st_results = run_st_attribution_pipeline(
                txns, locs, n_locs, frequents, events,
                window_t, min_support, pipe_config,
            )
            st_time = (time.perf_counter() - t0) * 1000

            st_eval = evaluate(
                st_results,
                os.path.join(data_dir, "ground_truth.json"),
                os.path.join(data_dir, "unrelated_patterns.json"),
            )
            st_eval["time_ms"] = st_time
            st_metrics.append(st_eval)

            # 1D baseline
            t0 = time.perf_counter()
            baseline_results = run_1d_baseline_pipeline(
                txns, locs, n_locs, frequents, events,
                window_t, min_support, pipe_config,
            )
            bl_time = (time.perf_counter() - t0) * 1000

            bl_eval = evaluate(
                baseline_results,
                os.path.join(data_dir, "ground_truth.json"),
                os.path.join(data_dir, "unrelated_patterns.json"),
            )
            bl_eval["time_ms"] = bl_time
            baseline_metrics.append(bl_eval)

            print(f"  seed={seed}: ST F1={st_eval['f1']:.3f} P={st_eval['precision']:.3f} "
                  f"R={st_eval['recall']:.3f} FAR={st_eval['far']:.2f} #pred={st_eval['n_predicted']} | "
                  f"1D F1={bl_eval['f1']:.3f} P={bl_eval['precision']:.3f} "
                  f"R={bl_eval['recall']:.3f} FAR={bl_eval['far']:.2f} #pred={bl_eval['n_predicted']}")

        # Average metrics
        def avg_metrics(metrics):
            keys = ["precision", "recall", "f1", "far", "n_predicted", "time_ms"]
            return {k: np.mean([m[k] for m in metrics]) for k in keys}

        st_avg = avg_metrics(st_metrics)
        bl_avg = avg_metrics(baseline_metrics)

        print(f"\n  AVG ST:  F1={st_avg['f1']:.3f} P={st_avg['precision']:.3f} "
              f"R={st_avg['recall']:.3f} FAR={st_avg['far']:.2f} "
              f"#pred={st_avg['n_predicted']:.1f} time={st_avg['time_ms']:.0f}ms")
        print(f"  AVG 1D:  F1={bl_avg['f1']:.3f} P={bl_avg['precision']:.3f} "
              f"R={bl_avg['recall']:.3f} FAR={bl_avg['far']:.2f} "
              f"#pred={bl_avg['n_predicted']:.1f} time={bl_avg['time_ms']:.0f}ms")

        all_results.append({
            "condition": cond_name,
            "st": {"avg": st_avg, "per_seed": st_metrics},
            "baseline_1d": {"avg": bl_avg, "per_seed": baseline_metrics},
        })

    # Save results
    with open(results_dir / "ex1_results.json", "w") as f:
        json.dump(all_results, f, indent=2, default=float)

    print("\n" + "=" * 60)
    print("EX1 Summary Table")
    print("=" * 60)
    print(f"{'Condition':<12} | {'ST F1':>6} {'ST P':>6} {'ST R':>6} {'ST FAR':>7} | "
          f"{'1D F1':>6} {'1D P':>6} {'1D R':>6} {'1D FAR':>7} | {'ΔF1':>6}")
    print("-" * 85)
    for r in all_results:
        st = r["st"]["avg"]
        bl = r["baseline_1d"]["avg"]
        delta = st["f1"] - bl["f1"]
        print(f"{r['condition']:<12} | {st['f1']:>6.3f} {st['precision']:>6.3f} {st['recall']:>6.3f} "
              f"{st['far']:>7.3f} | {bl['f1']:>6.3f} {bl['precision']:>6.3f} {bl['recall']:>6.3f} "
              f"{bl['far']:>7.3f} | {delta:>+6.3f}")

    return all_results


# ---------------------------------------------------------------------------
# EX2: Parameter Sensitivity
# ---------------------------------------------------------------------------

def run_ex2():
    """EX2: Parameter sensitivity analysis."""
    print("\n" + "=" * 60)
    print("EX2: Parameter Sensitivity")
    print("=" * 60)

    data_config = make_ex1_config(beta=0.3, seed=42)
    data_dir = str(Path(__file__).parent / "results" / "ex2" / "data")
    generate_st_synthetic(data_config, data_dir)

    txns = load_transactions(os.path.join(data_dir, "transactions.txt"))
    locs = load_locations(os.path.join(data_dir, "locations.txt"))
    events = load_events(os.path.join(data_dir, "events.json"))
    n_locs = data_config.n_locations
    window_t = 200
    min_support = 3
    frequents = find_frequent_pairs(txns, locs, window_t, min_support, n_locs)

    results = []

    # Sweep sigma_s
    print("\n--- sigma_s sweep ---")
    for sigma_s in [1.0, 2.0, 3.0, 5.0, 10.0, 20.0]:
        config = STAttributionConfig(
            min_support_range=5, sigma_s=sigma_s,
            n_permutations=500, alpha=0.10, correction_method="bh",
            deduplicate_overlap=True, seed=42,
        )
        preds = run_st_attribution_pipeline(
            txns, locs, n_locs, frequents, events, window_t, min_support, config,
        )
        ev = evaluate(preds, os.path.join(data_dir, "ground_truth.json"),
                      os.path.join(data_dir, "unrelated_patterns.json"))
        print(f"  sigma_s={sigma_s:>5.1f}: F1={ev['f1']:.3f} P={ev['precision']:.3f} "
              f"R={ev['recall']:.3f} FAR={ev['far']:.2f}")
        results.append({"param": "sigma_s", "value": sigma_s, **ev})

    # Sweep sigma_t (overrides default window_t/4)
    print("\n--- sigma_t sweep ---")
    for sigma_t in [10, 25, 50, 100, 200]:
        config = STAttributionConfig(
            min_support_range=5, sigma_s=3.0, sigma_t=float(sigma_t),
            n_permutations=500, alpha=0.10, correction_method="bh",
            deduplicate_overlap=True, seed=42,
        )
        preds = run_st_attribution_pipeline(
            txns, locs, n_locs, frequents, events, window_t, min_support, config,
        )
        ev = evaluate(preds, os.path.join(data_dir, "ground_truth.json"),
                      os.path.join(data_dir, "unrelated_patterns.json"))
        print(f"  sigma_t={sigma_t:>5d}: F1={ev['f1']:.3f} P={ev['precision']:.3f} "
              f"R={ev['recall']:.3f} FAR={ev['far']:.2f}")
        results.append({"param": "sigma_t", "value": sigma_t, **ev})

    # Sweep alpha
    print("\n--- alpha sweep ---")
    for alpha in [0.01, 0.05, 0.10, 0.20]:
        config = STAttributionConfig(
            min_support_range=5, sigma_s=3.0,
            n_permutations=500, alpha=alpha, correction_method="bh",
            deduplicate_overlap=True, seed=42,
        )
        preds = run_st_attribution_pipeline(
            txns, locs, n_locs, frequents, events, window_t, min_support, config,
        )
        ev = evaluate(preds, os.path.join(data_dir, "ground_truth.json"),
                      os.path.join(data_dir, "unrelated_patterns.json"))
        print(f"  alpha={alpha:>5.2f}: F1={ev['f1']:.3f} P={ev['precision']:.3f} "
              f"R={ev['recall']:.3f} FAR={ev['far']:.2f}")
        results.append({"param": "alpha", "value": alpha, **ev})

    # Sweep n_permutations
    print("\n--- n_permutations sweep ---")
    for B in [50, 100, 500, 1000]:
        config = STAttributionConfig(
            min_support_range=5, sigma_s=3.0,
            n_permutations=B, alpha=0.10, correction_method="bh",
            deduplicate_overlap=True, seed=42,
        )
        preds = run_st_attribution_pipeline(
            txns, locs, n_locs, frequents, events, window_t, min_support, config,
        )
        ev = evaluate(preds, os.path.join(data_dir, "ground_truth.json"),
                      os.path.join(data_dir, "unrelated_patterns.json"))
        print(f"  B={B:>5d}: F1={ev['f1']:.3f} P={ev['precision']:.3f} "
              f"R={ev['recall']:.3f} FAR={ev['far']:.2f}")
        results.append({"param": "n_permutations", "value": B, **ev})

    out_dir = Path(__file__).parent / "results" / "ex2"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "ex2_results.json", "w") as f:
        json.dump(results, f, indent=2, default=float)

    return results


# ---------------------------------------------------------------------------
# EX3: Semi-realistic retail scenario
# ---------------------------------------------------------------------------

def run_ex3():
    """EX3: Semi-realistic retail scenario with seasonal/regional campaigns."""
    print("\n" + "=" * 60)
    print("EX3: Semi-Realistic Retail Scenario")
    print("=" * 60)

    config = STSyntheticConfig(
        n_transactions=40000,  # ~2000 timesteps × 20 stores
        n_items=50,
        n_locations=20,
        p_base=0.03,
        planted_signals=[
            STPlantedSignal(
                pattern=[5, 15], event_id="summer", event_name="summer_campaign",
                event_start=12000, event_end=20000,
                spatial_scope=list(range(0, 10)),  # coastal stores
                boost_factor=0.4,
            ),
            STPlantedSignal(
                pattern=[25, 35], event_id="winter", event_name="winter_campaign",
                event_start=28000, event_end=36000,
                spatial_scope=list(range(10, 20)),  # inland stores
                boost_factor=0.4,
            ),
            STPlantedSignal(
                pattern=[8, 18], event_id="promo", event_name="all_store_promo",
                event_start=4000, event_end=8000,
                spatial_scope=list(range(0, 20)),  # all stores
                boost_factor=0.5,
            ),
        ],
        unrelated_dense=[
            STUnrelatedDense(
                pattern=[40, 45], active_start=22000, active_end=26000,
                active_locations=list(range(5, 15)), boost_factor=0.3,
            ),
        ],
        decoy_events=[
            STDecoyEvent("decoy", "fake_campaign", 9000, 11000, list(range(0, 5))),
        ],
        seed=42,
    )

    data_dir = str(Path(__file__).parent / "results" / "ex3" / "data")
    generate_st_synthetic(config, data_dir)

    txns = load_transactions(os.path.join(data_dir, "transactions.txt"))
    locs = load_locations(os.path.join(data_dir, "locations.txt"))
    events = load_events(os.path.join(data_dir, "events.json"))
    n_locs = config.n_locations
    window_t = 400
    min_support = 3

    frequents = find_frequent_pairs(txns, locs, window_t, min_support, n_locs)
    print(f"  Candidate patterns: {len(frequents)}")

    pipe_config = STAttributionConfig(
        min_support_range=5,
        sigma_s=3.0,
        n_permutations=1000,
        alpha=0.10,
        correction_method="bh",
        deduplicate_overlap=True,
        seed=42,
    )

    # ST pipeline
    t0 = time.perf_counter()
    st_results = run_st_attribution_pipeline(
        txns, locs, n_locs, frequents, events,
        window_t, min_support, pipe_config,
    )
    st_time = (time.perf_counter() - t0) * 1000

    st_eval = evaluate(
        st_results,
        os.path.join(data_dir, "ground_truth.json"),
        os.path.join(data_dir, "unrelated_patterns.json"),
    )

    print(f"  ST Pipeline: F1={st_eval['f1']:.3f} P={st_eval['precision']:.3f} "
          f"R={st_eval['recall']:.3f} FAR={st_eval['far']:.2f} "
          f"#pred={st_eval['n_predicted']} time={st_time:.0f}ms")

    # 1D baseline
    t0 = time.perf_counter()
    bl_results = run_1d_baseline_pipeline(
        txns, locs, n_locs, frequents, events,
        window_t, min_support, pipe_config,
    )
    bl_time = (time.perf_counter() - t0) * 1000

    bl_eval = evaluate(
        bl_results,
        os.path.join(data_dir, "ground_truth.json"),
        os.path.join(data_dir, "unrelated_patterns.json"),
    )

    print(f"  1D Baseline: F1={bl_eval['f1']:.3f} P={bl_eval['precision']:.3f} "
          f"R={bl_eval['recall']:.3f} FAR={bl_eval['far']:.2f} "
          f"#pred={bl_eval['n_predicted']} time={bl_time:.0f}ms")

    # Detail output
    print(f"\n  Significant attributions (ST):")
    for r in st_results:
        print(f"    {r.pattern} -> {r.event_name} "
              f"(loc={r.change_location}, t={r.change_time}, "
              f"p_adj={r.adjusted_p_value:.4f}, score={r.attribution_score:.3f})")

    out_dir = Path(__file__).parent / "results" / "ex3"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "ex3_results.json", "w") as f:
        json.dump({
            "st": st_eval, "st_time_ms": st_time,
            "baseline_1d": bl_eval, "bl_time_ms": bl_time,
            "st_attributions": [
                {"pattern": list(r.pattern), "event": r.event_name,
                 "location": r.change_location, "time": r.change_time,
                 "score": r.attribution_score, "adj_p": r.adjusted_p_value}
                for r in st_results
            ],
        }, f, indent=2, default=float)

    return {"st": st_eval, "baseline_1d": bl_eval}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ex1_results = run_ex1()
    ex2_results = run_ex2()
    ex3_results = run_ex3()

    print("\n" + "=" * 60)
    print("ALL EXPERIMENTS COMPLETE")
    print("=" * 60)
