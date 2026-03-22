"""
Paper N — Genomics: Experiment runner.

E1: Sensitivity analysis (window_size, min_support)
E2: Threshold strategy comparison
E3: Scalability (varying n_cells)
E4: Module detection quality with ground truth
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List

_IMPL_DIR = Path(__file__).resolve().parents[1] / "implementation" / "python"
sys.path.insert(0, str(_IMPL_DIR))

from dgci_miner import DGCIMiner
from synthetic_scrna_data import SyntheticScRNAConfig, generate_synthetic_scrna


def run_e1_sensitivity() -> Dict:
    """E1: Sensitivity analysis varying W and sigma."""
    config = SyntheticScRNAConfig(n_cells=500, seed=42)
    data = generate_synthetic_scrna(config)

    results = []
    for W in [20, 30, 50, 80, 100]:
        for sigma in [5, 8, 10, 15]:
            miner = DGCIMiner(
                window_size=W,
                min_support=sigma,
                max_length=5,
                threshold_strategy="quantile",
                threshold_param=0.5,
                min_cells_expressed=10,
            )

            t0 = time.perf_counter()
            detected = miner.mine(
                data.expression_matrix, data.gene_names, data.pseudotime
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000

            metrics = miner.evaluate(
                detected, data.ground_truth_modules, data.pseudotime
            )

            n_multi = len({k: v for k, v in detected.items() if len(k) > 1})
            n_single = len({k: v for k, v in detected.items() if len(k) == 1})

            results.append({
                "window_size": W,
                "min_support": sigma,
                "n_single_gene": n_single,
                "n_multi_gene": n_multi,
                "module_recall": metrics["module_recall"],
                "mean_iou": metrics["mean_iou"],
                "precision": metrics["precision_at_module"],
                "elapsed_ms": round(elapsed_ms, 2),
            })

    return {"experiment": "E1_sensitivity", "results": results}


def run_e2_threshold_strategies() -> Dict:
    """E2: Compare threshold strategies."""
    config = SyntheticScRNAConfig(n_cells=500, seed=42)
    data = generate_synthetic_scrna(config)

    strategies = [
        ("median", 0.0),
        ("quantile", 0.3),
        ("quantile", 0.5),
        ("quantile", 0.7),
        ("zscore", 0.5),
        ("zscore", 1.0),
    ]

    results = []
    for strategy, param in strategies:
        miner = DGCIMiner(
            window_size=50,
            min_support=8,
            max_length=5,
            threshold_strategy=strategy,
            threshold_param=param,
            min_cells_expressed=10,
        )

        detected = miner.mine(
            data.expression_matrix, data.gene_names, data.pseudotime
        )
        metrics = miner.evaluate(
            detected, data.ground_truth_modules, data.pseudotime
        )

        n_multi = len({k: v for k, v in detected.items() if len(k) > 1})

        results.append({
            "strategy": strategy,
            "param": param,
            "n_multi_gene": n_multi,
            "module_recall": metrics["module_recall"],
            "mean_iou": metrics["mean_iou"],
            "precision": metrics["precision_at_module"],
        })

    return {"experiment": "E2_threshold_strategies", "results": results}


def run_e3_scalability() -> Dict:
    """E3: Scalability with varying number of cells."""
    results = []
    for n_cells in [100, 200, 500, 1000, 2000]:
        config = SyntheticScRNAConfig(n_cells=n_cells, seed=42)
        data = generate_synthetic_scrna(config)

        W = max(10, n_cells // 10)
        sigma = max(3, n_cells // 50)

        miner = DGCIMiner(
            window_size=W,
            min_support=sigma,
            max_length=4,
            threshold_strategy="quantile",
            threshold_param=0.5,
            min_cells_expressed=max(3, n_cells // 50),
        )

        t0 = time.perf_counter()
        detected = miner.mine(
            data.expression_matrix, data.gene_names, data.pseudotime
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        metrics = miner.evaluate(
            detected, data.ground_truth_modules, data.pseudotime
        )

        n_multi = len({k: v for k, v in detected.items() if len(k) > 1})

        results.append({
            "n_cells": n_cells,
            "n_genes": len(data.gene_names),
            "window_size": W,
            "min_support": sigma,
            "n_multi_gene": n_multi,
            "module_recall": metrics["module_recall"],
            "elapsed_ms": round(elapsed_ms, 2),
        })

    return {"experiment": "E3_scalability", "results": results}


def run_e4_module_detection() -> Dict:
    """E4: Detailed module detection quality analysis."""
    config = SyntheticScRNAConfig(n_cells=500, seed=42)
    data = generate_synthetic_scrna(config)

    miner = DGCIMiner(
        window_size=50,
        min_support=8,
        max_length=5,
        threshold_strategy="quantile",
        threshold_param=0.4,
        min_cells_expressed=10,
    )

    detected = miner.mine(
        data.expression_matrix, data.gene_names, data.pseudotime
    )

    # Per-module analysis
    multi_gene_dgcis = {k: v for k, v in detected.items() if len(k) > 1}

    module_results = []
    for gt_mod in data.ground_truth_modules:
        gt_genes = set(gt_mod["genes"])
        gt_start = gt_mod["cell_index_start"]
        gt_end = gt_mod["cell_index_end"]

        matching_dgcis = []
        for gene_set, intervals in multi_gene_dgcis.items():
            overlap = gt_genes & set(gene_set)
            if len(overlap) >= 2:
                matching_dgcis.append({
                    "genes": list(gene_set),
                    "gene_overlap": list(overlap),
                    "intervals": [(s, e) for s, e in intervals],
                })

        module_results.append({
            "module_name": gt_mod["name"],
            "gt_genes": gt_mod["genes"],
            "gt_interval": [gt_start, gt_end],
            "n_matching_dgcis": len(matching_dgcis),
            "matching_dgcis": matching_dgcis[:5],  # top 5
        })

    # Top detected DGCIs
    top_dgcis = []
    for gene_set, intervals in sorted(
        multi_gene_dgcis.items(), key=lambda x: len(x[0]), reverse=True
    )[:10]:
        total_span = sum(e - s + 1 for s, e in intervals)
        top_dgcis.append({
            "genes": list(gene_set),
            "n_intervals": len(intervals),
            "total_span": total_span,
            "intervals": [(s, e) for s, e in intervals],
        })

    metrics = miner.evaluate(
        detected, data.ground_truth_modules, data.pseudotime
    )

    return {
        "experiment": "E4_module_detection",
        "metrics": metrics,
        "module_results": module_results,
        "top_dgcis": top_dgcis,
        "n_total_patterns": len(detected),
        "n_multi_gene": len(multi_gene_dgcis),
    }


def main():
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    experiments = [
        ("e1_results.json", run_e1_sensitivity),
        ("e2_results.json", run_e2_threshold_strategies),
        ("e3_results.json", run_e3_scalability),
        ("e4_results.json", run_e4_module_detection),
    ]

    for fname, func in experiments:
        print(f"Running {fname}...")
        t0 = time.perf_counter()
        result = func()
        elapsed = time.perf_counter() - t0
        result["total_elapsed_s"] = round(elapsed, 3)

        with open(out_dir / fname, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  Done in {elapsed:.2f}s -> {out_dir / fname}")

    print("All experiments complete.")


if __name__ == "__main__":
    main()
