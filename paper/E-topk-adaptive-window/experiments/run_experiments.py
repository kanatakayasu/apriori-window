"""
Paper E Experiments: E1-E4

E1: Quality comparison vs. grid-search over (theta, W)
E2: Branch-and-bound pruning efficiency
E3: Scalability with dataset size
E4: Parameter sensitivity elimination on real-like data
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add implementation path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "implementation" / "python"))

from adaptive_window import compute_dense_coverage_score, compute_dense_intervals, compute_multiscale_dcs
from scale_space import detect_scale_space_ridges
from topk_dense import build_item_timestamps, mine_topk_dense, mine_topk_with_ridges


def generate_synthetic(
    n: int = 500,
    num_items: int = 20,
    num_dense_items: int = 5,
    dense_region: Tuple[int, int] = (100, 250),
    dense_prob: float = 0.7,
    sparse_prob: float = 0.1,
    seed: int = 42,
) -> List[List[int]]:
    """Generate synthetic transactions with known dense region."""
    rng = random.Random(seed)
    txns: List[List[int]] = []
    for t in range(n):
        items = []
        for item in range(1, num_items + 1):
            if item <= num_dense_items and dense_region[0] <= t <= dense_region[1]:
                if rng.random() < dense_prob:
                    items.append(item)
            else:
                if rng.random() < sparse_prob:
                    items.append(item)
        txns.append(items)
    return txns


def experiment_e1_quality_comparison(
    out_dir: Path,
) -> Dict[str, Any]:
    """
    E1: Quality comparison — Top-k vs. grid-search over (theta, W).

    Compare top-k mining results against exhaustive grid search
    over multiple (theta, W) combinations. Measure Jaccard similarity
    of discovered patterns.
    """
    print("=== E1: Quality Comparison ===")
    txns = generate_synthetic(n=300, num_items=15, num_dense_items=5, seed=42)
    k = 5
    w0 = 10
    theta0 = 5

    # Top-k approach
    t0 = time.perf_counter()
    topk_results = mine_topk_dense(txns, k=k, w0=w0, theta0=theta0, max_length=3)
    topk_time = time.perf_counter() - t0
    topk_patterns = set(r[0] for r in topk_results)

    # Grid search approach: try many (W, theta) combos, collect all patterns
    grid_configs = [
        (8, 4), (10, 5), (12, 6), (15, 7), (20, 10),
        (8, 3), (10, 4), (12, 5), (15, 6), (20, 8),
    ]
    t0 = time.perf_counter()
    grid_all_patterns: Dict[Tuple[int, ...], float] = {}
    item_ts = build_item_timestamps(txns)
    n = len(txns)

    for w, theta in grid_configs:
        for item in item_ts:
            ts = item_ts[item]
            intervals = compute_dense_intervals(ts, w, theta)
            if intervals:
                score, _ = compute_dense_coverage_score(ts, w, theta)
                pat = (item,)
                grid_all_patterns[pat] = max(grid_all_patterns.get(pat, 0), score)

    # Get top-k from grid
    grid_sorted = sorted(grid_all_patterns.items(), key=lambda x: x[1], reverse=True)[:k]
    grid_patterns = set(p for p, _ in grid_sorted)
    grid_time = time.perf_counter() - t0

    # Jaccard similarity
    intersection = topk_patterns & grid_patterns
    union = topk_patterns | grid_patterns
    jaccard = len(intersection) / len(union) if union else 1.0

    result = {
        "experiment": "E1",
        "k": k,
        "topk_patterns": [list(p) for p in sorted(topk_patterns)],
        "topk_scores": {str(r[0]): r[1] for r in topk_results},
        "grid_patterns": [list(p) for p in sorted(grid_patterns)],
        "jaccard_similarity": jaccard,
        "topk_time_ms": topk_time * 1000,
        "grid_time_ms": grid_time * 1000,
        "speedup": grid_time / topk_time if topk_time > 0 else float("inf"),
    }

    print(f"  Jaccard similarity: {jaccard:.3f}")
    print(f"  Top-k time: {topk_time*1000:.1f} ms, Grid time: {grid_time*1000:.1f} ms")
    print(f"  Speedup: {result['speedup']:.1f}x")

    with open(out_dir / "e1_quality.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    return result


def experiment_e2_pruning_efficiency(
    out_dir: Path,
) -> Dict[str, Any]:
    """
    E2: Branch-and-bound pruning efficiency.

    Measure how many candidates are evaluated vs. total possible
    at different k values and dataset sizes.
    """
    print("=== E2: Pruning Efficiency ===")
    results_list = []

    for n_items in [10, 15, 20]:
        txns = generate_synthetic(n=200, num_items=n_items, num_dense_items=5, seed=42)
        item_ts = build_item_timestamps(txns)
        total_singletons = len(item_ts)
        # Total possible pairs
        total_pairs = total_singletons * (total_singletons - 1) // 2
        total_candidates = total_singletons + total_pairs

        for k_val in [1, 3, 5, 10]:
            t0 = time.perf_counter()
            results = mine_topk_dense(txns, k=k_val, w0=10, theta0=5, max_length=2)
            elapsed = time.perf_counter() - t0

            # Count evaluated (from results + those not in top-k but evaluated)
            n_returned = len(results)

            row = {
                "n_items": n_items,
                "k": k_val,
                "total_singletons": total_singletons,
                "total_possible_candidates": total_candidates,
                "returned": n_returned,
                "time_ms": elapsed * 1000,
            }
            results_list.append(row)
            print(f"  items={n_items}, k={k_val}: {n_returned} returned, "
                  f"{elapsed*1000:.1f} ms, candidates={total_candidates}")

    result = {"experiment": "E2", "data": results_list}
    with open(out_dir / "e2_pruning.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


def experiment_e3_scalability(
    out_dir: Path,
) -> Dict[str, Any]:
    """
    E3: Scalability with dataset size.

    Measure runtime as N increases from 100 to 5000.
    """
    print("=== E3: Scalability ===")
    results_list = []

    for n_val in [100, 200, 500, 1000, 2000, 5000]:
        txns = generate_synthetic(
            n=n_val, num_items=15, num_dense_items=5,
            dense_region=(n_val // 4, 3 * n_val // 4),
            seed=42,
        )

        t0 = time.perf_counter()
        results = mine_topk_dense(txns, k=5, w0=max(5, n_val // 20), theta0=3, max_length=2)
        elapsed = time.perf_counter() - t0

        row = {
            "n": n_val,
            "k": 5,
            "n_results": len(results),
            "time_ms": elapsed * 1000,
        }
        results_list.append(row)
        print(f"  N={n_val}: {elapsed*1000:.1f} ms, {len(results)} results")

    result = {"experiment": "E3", "data": results_list}
    with open(out_dir / "e3_scalability.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


def experiment_e4_parameter_sensitivity(
    out_dir: Path,
) -> Dict[str, Any]:
    """
    E4: Parameter sensitivity elimination.

    Show that top-k + adaptive window produces stable results
    regardless of W0 choice, while fixed (W, theta) is sensitive.
    """
    print("=== E4: Parameter Sensitivity ===")
    txns = generate_synthetic(
        n=500, num_items=15, num_dense_items=5,
        dense_region=(100, 350), seed=42,
    )

    # Top-k approach with different w0 values
    topk_results_by_w0: Dict[int, List[Tuple[int, ...]]] = {}
    for w0 in [5, 8, 10, 15, 20, 25]:
        results = mine_topk_dense(txns, k=5, w0=w0, theta0=3, max_length=2)
        patterns = [r[0] for r in results]
        topk_results_by_w0[w0] = patterns

    # Fixed (W, theta) approach
    fixed_results: Dict[str, List[Tuple[int, ...]]] = {}
    item_ts = build_item_timestamps(txns)
    for w, theta in [(5, 3), (10, 5), (15, 7), (20, 10), (25, 12)]:
        patterns_found = []
        for item in sorted(item_ts.keys()):
            intervals = compute_dense_intervals(item_ts[item], w, theta)
            if intervals:
                patterns_found.append((item,))
        fixed_results[f"W={w},theta={theta}"] = patterns_found[:5]

    # Compute stability: pairwise Jaccard among top-k results
    w0_values = sorted(topk_results_by_w0.keys())
    topk_jaccards = []
    for i in range(len(w0_values)):
        for j in range(i + 1, len(w0_values)):
            s1 = set(topk_results_by_w0[w0_values[i]])
            s2 = set(topk_results_by_w0[w0_values[j]])
            jac = len(s1 & s2) / len(s1 | s2) if (s1 | s2) else 1.0
            topk_jaccards.append(jac)

    fixed_keys = sorted(fixed_results.keys())
    fixed_jaccards = []
    for i in range(len(fixed_keys)):
        for j in range(i + 1, len(fixed_keys)):
            s1 = set(fixed_results[fixed_keys[i]])
            s2 = set(fixed_results[fixed_keys[j]])
            jac = len(s1 & s2) / len(s1 | s2) if (s1 | s2) else 1.0
            fixed_jaccards.append(jac)

    avg_topk_stability = sum(topk_jaccards) / len(topk_jaccards) if topk_jaccards else 0
    avg_fixed_stability = sum(fixed_jaccards) / len(fixed_jaccards) if fixed_jaccards else 0

    result = {
        "experiment": "E4",
        "topk_w0_values": w0_values,
        "topk_patterns_by_w0": {str(w): [list(p) for p in pats] for w, pats in topk_results_by_w0.items()},
        "fixed_patterns": {k: [list(p) for p in v] for k, v in fixed_results.items()},
        "topk_avg_jaccard": avg_topk_stability,
        "fixed_avg_jaccard": avg_fixed_stability,
        "topk_stability_improvement": (avg_topk_stability - avg_fixed_stability) / max(avg_fixed_stability, 0.01),
    }

    print(f"  Top-k avg Jaccard (stability): {avg_topk_stability:.3f}")
    print(f"  Fixed avg Jaccard (stability): {avg_fixed_stability:.3f}")
    print(f"  Stability improvement: {result['topk_stability_improvement']:.1%}")

    with open(out_dir / "e4_sensitivity.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    return result


def generate_figures(out_dir: Path, results: Dict[str, Dict]) -> None:
    """Generate ASCII tables as figure placeholders."""
    fig_dir = out_dir.parent / "figures"
    fig_dir.mkdir(exist_ok=True)

    # E3 scalability table
    e3 = results.get("E3", {}).get("data", [])
    lines = ["# E3: Scalability Results", "N\tTime(ms)\tPatterns"]
    for row in e3:
        lines.append(f"{row['n']}\t{row['time_ms']:.1f}\t{row['n_results']}")

    with open(fig_dir / "e3_scalability_table.txt", "w") as f:
        f.write("\n".join(lines))

    # E4 sensitivity summary
    e4 = results.get("E4", {})
    lines = [
        "# E4: Parameter Sensitivity",
        f"Top-k avg Jaccard stability: {e4.get('topk_avg_jaccard', 0):.3f}",
        f"Fixed avg Jaccard stability: {e4.get('fixed_avg_jaccard', 0):.3f}",
    ]
    with open(fig_dir / "e4_sensitivity_summary.txt", "w") as f:
        f.write("\n".join(lines))


def main():
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = {}

    all_results["E1"] = experiment_e1_quality_comparison(out_dir)
    all_results["E2"] = experiment_e2_pruning_efficiency(out_dir)
    all_results["E3"] = experiment_e3_scalability(out_dir)
    all_results["E4"] = experiment_e4_parameter_sensitivity(out_dir)

    # Save combined results
    with open(out_dir / "all_results.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    generate_figures(out_dir, all_results)

    print("\n=== All experiments complete ===")
    print(f"Results saved to {out_dir}")


if __name__ == "__main__":
    main()
