#!/usr/bin/env python3
"""
Experiment runner for Paper A: Anti-Dense Intervals and Contrast Dense Patterns.

Experiments:
  E1: Anti-dense interval ground truth recovery (synthetic)
  E2: Contrast pattern classification accuracy (synthetic)
  E3: Parameter sensitivity analysis (theta_low, regime boundary)
  E4: Dunnhumby campaign termination pattern vanishing
  E5: Online Retail seasonal contrast
"""

import json
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# Add implementation to path
_IMPL_DIR = str(Path(__file__).resolve().parents[1] / "implementation" / "python")
if _IMPL_DIR not in sys.path:
    sys.path.insert(0, _IMPL_DIR)

_SUITE_DIR = str(Path(__file__).resolve().parents[2] / ".." / "apriori_window_suite" / "python")
if _SUITE_DIR not in sys.path:
    sys.path.insert(0, _SUITE_DIR)

from anti_dense_interval import compute_anti_dense_intervals, compute_support_series
from contrast_dense import (
    TopologyChangeType,
    classify_topology_change,
    compute_contrast_statistic,
    compute_coverage,
    compute_dense_intervals_in_regime,
    find_contrast_dense_patterns,
    permutation_test,
)
from apriori_window_basket import compute_dense_intervals

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIGURES_DIR = Path(__file__).resolve().parent / "figures"


def ensure_dirs():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


# ================================================================
# Synthetic data generators
# ================================================================

def generate_anti_dense_synthetic(
    N: int = 500,
    dense_ranges: List[Tuple[int, int]] = None,
    anti_dense_ranges: List[Tuple[int, int]] = None,
    base_rate: float = 0.3,
    dense_rate: float = 0.9,
    anti_dense_rate: float = 0.02,
    seed: int = 42,
) -> Tuple[List[int], List[Tuple[int, int]], List[Tuple[int, int]]]:
    """
    Generate synthetic timestamps with embedded dense and anti-dense regions.

    Returns (timestamps, gt_dense_ranges, gt_anti_dense_ranges).
    """
    rng = random.Random(seed)

    if dense_ranges is None:
        dense_ranges = [(50, 150), (300, 400)]
    if anti_dense_ranges is None:
        anti_dense_ranges = [(180, 270)]

    timestamps = []
    for t in range(N):
        in_dense = any(s <= t <= e for s, e in dense_ranges)
        in_anti = any(s <= t <= e for s, e in anti_dense_ranges)

        if in_dense:
            rate = dense_rate
        elif in_anti:
            rate = anti_dense_rate
        else:
            rate = base_rate

        if rng.random() < rate:
            timestamps.append(t)

    return timestamps, dense_ranges, anti_dense_ranges


def generate_contrast_synthetic(
    N: int = 400,
    regime_boundary: int = 200,
    pattern_configs: Dict[str, Dict] = None,
    seed: int = 42,
) -> Tuple[Dict[str, List[int]], int]:
    """
    Generate synthetic data for contrast pattern experiments.

    pattern_configs: dict mapping pattern name to config with keys:
      - 'r1_rate': occurrence rate in regime 1
      - 'r2_rate': occurrence rate in regime 2
    """
    rng = random.Random(seed)

    if pattern_configs is None:
        pattern_configs = {
            "emerge": {"r1_rate": 0.02, "r2_rate": 0.8},
            "vanish": {"r1_rate": 0.8, "r2_rate": 0.02},
            "amplify": {"r1_rate": 0.3, "r2_rate": 0.9},
            "contract": {"r1_rate": 0.9, "r2_rate": 0.3},
            "stable": {"r1_rate": 0.5, "r2_rate": 0.5},
        }

    pattern_timestamps = {}
    for name, config in pattern_configs.items():
        ts = []
        for t in range(N):
            rate = config["r1_rate"] if t <= regime_boundary else config["r2_rate"]
            if rng.random() < rate:
                ts.append(t)
        pattern_timestamps[name] = ts

    return pattern_timestamps, regime_boundary


# ================================================================
# E1: Anti-Dense Interval Ground Truth Recovery
# ================================================================

def run_e1(seeds: List[int] = None) -> Dict:
    """E1: Test anti-dense interval recovery on synthetic data."""
    if seeds is None:
        seeds = list(range(42, 47))  # 5 seeds

    results = []
    W = 10
    theta_low = 2

    for seed in seeds:
        ts, gt_dense, gt_anti_dense = generate_anti_dense_synthetic(
            N=500,
            dense_ranges=[(50, 150), (300, 400)],
            anti_dense_ranges=[(180, 270)],
            seed=seed,
        )

        detected = compute_anti_dense_intervals(ts, W, theta_low)

        # Compute overlap with ground truth anti-dense ranges
        gt_set = set()
        for s, e in gt_anti_dense:
            gt_set.update(range(s, e + 1))

        detected_set = set()
        for s, e in detected:
            detected_set.update(range(s, e + 1))

        # Restrict to valid range [0, max(ts)]
        max_t = max(ts) if ts else 0
        gt_set = {t for t in gt_set if t <= max_t}
        detected_set = {t for t in detected_set if t <= max_t}

        tp = len(gt_set & detected_set)
        fp = len(detected_set - gt_set)
        fn = len(gt_set - detected_set)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        results.append({
            "seed": seed,
            "n_timestamps": len(ts),
            "n_detected": len(detected),
            "precision": precision,
            "recall": recall,
            "f1": f1,
        })

    avg_f1 = np.mean([r["f1"] for r in results])
    avg_precision = np.mean([r["precision"] for r in results])
    avg_recall = np.mean([r["recall"] for r in results])

    return {
        "experiment": "E1",
        "description": "Anti-dense interval ground truth recovery",
        "params": {"W": W, "theta_low": theta_low, "N": 500},
        "per_seed": results,
        "summary": {
            "avg_precision": float(avg_precision),
            "avg_recall": float(avg_recall),
            "avg_f1": float(avg_f1),
        },
    }


# ================================================================
# E2: Contrast Pattern Classification Accuracy
# ================================================================

def run_e2(seeds: List[int] = None) -> Dict:
    """E2: Test contrast pattern classification on synthetic data."""
    if seeds is None:
        seeds = list(range(42, 47))

    W = 10
    theta = 4
    N = 400
    regime_boundary = 200

    expected_types = {
        "emerge": TopologyChangeType.EMERGENCE,
        "vanish": TopologyChangeType.VANISHING,
        "amplify": TopologyChangeType.AMPLIFICATION,
        "contract": TopologyChangeType.CONTRACTION,
        "stable": TopologyChangeType.STABLE,
    }

    results = []
    for seed in seeds:
        pattern_ts, _ = generate_contrast_synthetic(N=N, regime_boundary=regime_boundary, seed=seed)

        classifications = {}
        correct = 0
        total = 0

        for name, ts in pattern_ts.items():
            r1_intervals = compute_dense_intervals_in_regime(ts, W, theta, 0, regime_boundary)
            r2_intervals = compute_dense_intervals_in_regime(ts, W, theta, regime_boundary + 1, N - 1)

            change_type = classify_topology_change(
                r1_intervals, r2_intervals,
                regime_boundary + 1, N - regime_boundary - 1,
                delta=0.1,
            )
            classifications[name] = change_type.value

            if change_type == expected_types[name]:
                correct += 1
            total += 1

        accuracy = correct / total if total > 0 else 0
        results.append({
            "seed": seed,
            "classifications": classifications,
            "accuracy": accuracy,
        })

    avg_accuracy = np.mean([r["accuracy"] for r in results])

    return {
        "experiment": "E2",
        "description": "Contrast pattern classification accuracy",
        "params": {"W": W, "theta": theta, "N": N, "regime_boundary": regime_boundary},
        "per_seed": results,
        "summary": {"avg_accuracy": float(avg_accuracy)},
    }


# ================================================================
# E3: Parameter Sensitivity Analysis
# ================================================================

def run_e3() -> Dict:
    """E3: Parameter sensitivity for theta_low and regime boundary."""
    W = 10
    N = 500
    seed = 42

    ts, gt_dense, gt_anti_dense = generate_anti_dense_synthetic(N=N, seed=seed)

    # Sensitivity to theta_low
    theta_low_results = []
    for theta_low in [1, 2, 3, 4, 5, 6, 8, 10]:
        detected = compute_anti_dense_intervals(ts, W, theta_low)
        total_coverage = sum(e - s + 1 for s, e in detected)
        theta_low_results.append({
            "theta_low": theta_low,
            "n_intervals": len(detected),
            "total_coverage": total_coverage,
        })

    # Sensitivity to regime boundary position
    theta = 4
    regime_results = []
    for boundary in [100, 150, 200, 250, 300, 350]:
        delta_val = compute_contrast_statistic(ts, W, theta, boundary, N)
        regime_results.append({
            "regime_boundary": boundary,
            "contrast_statistic": float(delta_val),
        })

    return {
        "experiment": "E3",
        "description": "Parameter sensitivity analysis",
        "params": {"W": W, "N": N, "seed": seed},
        "theta_low_sensitivity": theta_low_results,
        "regime_boundary_sensitivity": regime_results,
    }


# ================================================================
# E4: Dunnhumby Campaign Termination (simulated)
# ================================================================

def run_e4(seeds: List[int] = None) -> Dict:
    """E4: Simulate campaign termination effect on pattern density."""
    if seeds is None:
        seeds = list(range(42, 47))

    W = 10
    theta = 4
    N = 300
    campaign_end = 150  # campaign active in [0, 150]

    results = []
    for seed in seeds:
        rng = random.Random(seed)

        # Pattern promoted by campaign: high rate during campaign, low after
        promoted_ts = []
        for t in range(N):
            rate = 0.85 if t <= campaign_end else 0.05
            if rng.random() < rate:
                promoted_ts.append(t)

        # Background pattern: unaffected
        background_ts = []
        for t in range(N):
            if rng.random() < 0.4:
                background_ts.append(t)

        patterns = {
            "promoted": promoted_ts,
            "background": background_ts,
        }

        contrast_results = find_contrast_dense_patterns(
            patterns, W, theta,
            regime_boundary=campaign_end,
            total_length=N,
            n_permutations=199,
            seed=seed,
        )

        results.append({
            "seed": seed,
            "promoted_type": contrast_results["promoted"]["type"].value,
            "promoted_delta": contrast_results["promoted"]["delta"],
            "promoted_pvalue": contrast_results["promoted"]["p_value"],
            "promoted_significant": contrast_results["promoted"]["significant"],
            "background_type": contrast_results["background"]["type"].value,
            "background_delta": contrast_results["background"]["delta"],
            "background_pvalue": contrast_results["background"]["p_value"],
            "background_significant": contrast_results["background"]["significant"],
        })

    return {
        "experiment": "E4",
        "description": "Campaign termination pattern vanishing (simulated Dunnhumby)",
        "params": {"W": W, "theta": theta, "N": N, "campaign_end": campaign_end},
        "per_seed": results,
    }


# ================================================================
# E5: Online Retail Seasonal Contrast (simulated)
# ================================================================

def run_e5(seeds: List[int] = None) -> Dict:
    """E5: Seasonal contrast in simulated retail data."""
    if seeds is None:
        seeds = list(range(42, 47))

    W = 10
    theta = 4
    N = 365  # one year of daily transactions

    results = []
    for seed in seeds:
        rng = random.Random(seed)

        # Holiday pattern: peaks in Dec (days 330-365) and summer (150-210)
        holiday_ts = []
        for t in range(N):
            if 330 <= t <= 365 or 150 <= t <= 210:
                rate = 0.85
            else:
                rate = 0.05
            if rng.random() < rate:
                holiday_ts.append(t)

        # Steady pattern: uniform year-round
        steady_ts = []
        for t in range(N):
            if rng.random() < 0.5:
                steady_ts.append(t)

        patterns = {
            "holiday": holiday_ts,
            "steady": steady_ts,
        }

        # Compare H1 (Jan-Jun) vs H2 (Jul-Dec)
        contrast_results = find_contrast_dense_patterns(
            patterns, W, theta,
            regime_boundary=182,  # mid-year
            total_length=N,
            n_permutations=199,
            seed=seed,
        )

        results.append({
            "seed": seed,
            "holiday_type": contrast_results["holiday"]["type"].value,
            "holiday_delta": contrast_results["holiday"]["delta"],
            "holiday_pvalue": contrast_results["holiday"]["p_value"],
            "steady_type": contrast_results["steady"]["type"].value,
            "steady_delta": contrast_results["steady"]["delta"],
            "steady_pvalue": contrast_results["steady"]["p_value"],
        })

    return {
        "experiment": "E5",
        "description": "Seasonal contrast in simulated retail data",
        "params": {"W": W, "theta": theta, "N": N},
        "per_seed": results,
    }


# ================================================================
# Main runner
# ================================================================

def main():
    ensure_dirs()

    all_results = {}

    print("=" * 60)
    print("Running E1: Anti-Dense Interval Ground Truth Recovery")
    print("=" * 60)
    e1 = run_e1()
    all_results["E1"] = e1
    print(f"  Avg F1: {e1['summary']['avg_f1']:.3f}")
    print(f"  Avg Precision: {e1['summary']['avg_precision']:.3f}")
    print(f"  Avg Recall: {e1['summary']['avg_recall']:.3f}")

    print("\n" + "=" * 60)
    print("Running E2: Contrast Pattern Classification Accuracy")
    print("=" * 60)
    e2 = run_e2()
    all_results["E2"] = e2
    print(f"  Avg Accuracy: {e2['summary']['avg_accuracy']:.3f}")

    print("\n" + "=" * 60)
    print("Running E3: Parameter Sensitivity Analysis")
    print("=" * 60)
    e3 = run_e3()
    all_results["E3"] = e3
    print("  theta_low sensitivity:")
    for r in e3["theta_low_sensitivity"]:
        print(f"    theta_low={r['theta_low']}: {r['n_intervals']} intervals, coverage={r['total_coverage']}")

    print("\n" + "=" * 60)
    print("Running E4: Campaign Termination Pattern Vanishing")
    print("=" * 60)
    e4 = run_e4()
    all_results["E4"] = e4
    for r in e4["per_seed"]:
        print(f"  Seed {r['seed']}: promoted={r['promoted_type']} (p={r['promoted_pvalue']:.3f}), "
              f"background={r['background_type']} (p={r['background_pvalue']:.3f})")

    print("\n" + "=" * 60)
    print("Running E5: Seasonal Contrast")
    print("=" * 60)
    e5 = run_e5()
    all_results["E5"] = e5
    for r in e5["per_seed"]:
        print(f"  Seed {r['seed']}: holiday={r['holiday_type']} (p={r['holiday_pvalue']:.3f}), "
              f"steady={r['steady_type']} (p={r['steady_pvalue']:.3f})")

    # Save results
    results_path = RESULTS_DIR / "all_results.json"
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {results_path}")

    # Generate summary table
    generate_summary_table(all_results)


def generate_summary_table(results: Dict):
    """Generate a summary table as text."""
    table_path = RESULTS_DIR / "summary_table.txt"
    lines = []
    lines.append("=" * 70)
    lines.append("EXPERIMENT SUMMARY TABLE")
    lines.append("=" * 70)

    # E1
    e1 = results["E1"]["summary"]
    lines.append(f"\nE1: Anti-Dense Ground Truth Recovery")
    lines.append(f"  Precision: {e1['avg_precision']:.3f}")
    lines.append(f"  Recall:    {e1['avg_recall']:.3f}")
    lines.append(f"  F1:        {e1['avg_f1']:.3f}")

    # E2
    e2 = results["E2"]["summary"]
    lines.append(f"\nE2: Contrast Pattern Classification")
    lines.append(f"  Accuracy:  {e2['avg_accuracy']:.3f}")

    # E3
    lines.append(f"\nE3: Parameter Sensitivity")
    lines.append(f"  theta_low | n_intervals | coverage")
    for r in results["E3"]["theta_low_sensitivity"]:
        lines.append(f"  {r['theta_low']:9d} | {r['n_intervals']:11d} | {r['total_coverage']}")

    # E4
    lines.append(f"\nE4: Campaign Termination")
    for r in results["E4"]["per_seed"]:
        lines.append(f"  Seed {r['seed']}: promoted={r['promoted_type']}, bg={r['background_type']}")

    # E5
    lines.append(f"\nE5: Seasonal Contrast")
    for r in results["E5"]["per_seed"]:
        lines.append(f"  Seed {r['seed']}: holiday={r['holiday_type']}, steady={r['steady_type']}")

    with open(table_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Summary table saved to {table_path}")


if __name__ == "__main__":
    main()
