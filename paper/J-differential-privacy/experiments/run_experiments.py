"""
Experiment runner for Paper J: Differentially Private Dense Interval Mining.

Experiments:
  E1: Privacy-Accuracy Trade-off (epsilon vs Jaccard/F1)
  E2: Mechanism Comparison (Laplace vs Gaussian vs SVT)
  E3: Scalability (n_transactions vs runtime)
  E4: Stability Analysis (stability margin vs false positive rate)
  E5: Budget Composition (sequential vs advanced composition)
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "implementation" / "python"))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "apriori_window_suite" / "python")
)

from dp_dense_intervals import (
    PrivacyAccountant,
    compute_dp_dense_intervals,
    compute_precision_recall,
    compute_stability_margin,
    generate_synthetic_dp_data,
    interval_jaccard,
    mine_dp_dense_itemsets,
    sparse_vector_dense_intervals,
)
from apriori_window_basket import (
    compute_dense_intervals,
    find_dense_itemsets,
)


def run_e1_privacy_accuracy_tradeoff(seeds: List[int] = None) -> Dict[str, Any]:
    """E1: epsilon を変化させて精度を測定。"""
    if seeds is None:
        seeds = list(range(42, 52))  # 10 seeds
    epsilons = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    window_size = 20
    threshold = 5
    max_length = 3

    results: Dict[str, Any] = {"epsilons": epsilons, "seeds": seeds, "per_epsilon": {}}

    for eps in epsilons:
        jaccard_scores = []
        f1_scores = []
        n_detected = []

        for seed in seeds:
            data = generate_synthetic_dp_data(
                n_transactions=300,
                dense_itemset=(1, 2, 3),
                dense_start=80,
                dense_end=200,
                dense_prob=0.85,
                background_prob=0.05,
                seed=seed,
            )
            true_result = find_dense_itemsets(data, window_size, threshold, max_length)
            dp_result, acc = mine_dp_dense_itemsets(
                data, window_size, threshold, max_length,
                epsilon=eps, seed=seed,
            )

            # 全アイテムセットの平均 Jaccard/F1
            all_jaccards = []
            all_f1s = []
            for itemset in true_result:
                if len(itemset) <= 1:
                    continue
                true_iv = true_result.get(itemset, [])
                dp_iv = dp_result.get(itemset, [])
                j = interval_jaccard(dp_iv, true_iv, 300)
                _, _, f1 = compute_precision_recall(true_iv, dp_iv, 300)
                all_jaccards.append(j)
                all_f1s.append(f1)

            jaccard_scores.append(np.mean(all_jaccards) if all_jaccards else 0.0)
            f1_scores.append(np.mean(all_f1s) if all_f1s else 0.0)
            n_detected.append(len([k for k in dp_result if len(k) > 1]))

        results["per_epsilon"][str(eps)] = {
            "mean_jaccard": float(np.mean(jaccard_scores)),
            "std_jaccard": float(np.std(jaccard_scores)),
            "mean_f1": float(np.mean(f1_scores)),
            "std_f1": float(np.std(f1_scores)),
            "mean_n_detected": float(np.mean(n_detected)),
        }

    return results


def run_e2_mechanism_comparison(seeds: List[int] = None) -> Dict[str, Any]:
    """E2: Laplace vs Gaussian vs SVT の比較。"""
    if seeds is None:
        seeds = list(range(42, 52))
    epsilon = 2.0
    window_size = 20
    threshold = 5

    results: Dict[str, Any] = {"epsilon": epsilon, "mechanisms": {}}

    for mechanism in ["laplace", "gaussian"]:
        jaccards = []
        runtimes = []

        for seed in seeds:
            data = generate_synthetic_dp_data(
                n_transactions=300,
                dense_itemset=(1, 2),
                dense_start=80,
                dense_end=180,
                dense_prob=0.85,
                background_prob=0.05,
                seed=seed,
            )
            # 真の単体アイテム密集区間
            ts_item1 = [t for t, txn in enumerate(data) if txn and txn[0] and 1 in txn[0]]
            true_iv = compute_dense_intervals(ts_item1, window_size, threshold)

            t0 = time.perf_counter()
            dp_iv, _ = compute_dp_dense_intervals(
                ts_item1, window_size, threshold, epsilon,
                mechanism=mechanism,
                delta=1e-5 if mechanism == "gaussian" else 1e-6,
                seed=seed,
            )
            runtimes.append(time.perf_counter() - t0)
            jaccards.append(interval_jaccard(dp_iv, true_iv, 300))

        results["mechanisms"][mechanism] = {
            "mean_jaccard": float(np.mean(jaccards)),
            "std_jaccard": float(np.std(jaccards)),
            "mean_runtime_sec": float(np.mean(runtimes)),
        }

    # SVT
    svt_jaccards = []
    svt_runtimes = []
    for seed in seeds:
        data = generate_synthetic_dp_data(
            n_transactions=300,
            dense_itemset=(1, 2),
            dense_start=80,
            dense_end=180,
            dense_prob=0.85,
            background_prob=0.05,
            seed=seed,
        )
        ts_item1 = [t for t, txn in enumerate(data) if txn and txn[0] and 1 in txn[0]]
        true_iv = compute_dense_intervals(ts_item1, window_size, threshold)

        t0 = time.perf_counter()
        svt_iv, _ = sparse_vector_dense_intervals(
            ts_item1, window_size, threshold, epsilon, max_above=50, seed=seed,
        )
        svt_runtimes.append(time.perf_counter() - t0)
        svt_jaccards.append(interval_jaccard(svt_iv, true_iv, 300))

    results["mechanisms"]["svt"] = {
        "mean_jaccard": float(np.mean(svt_jaccards)),
        "std_jaccard": float(np.std(svt_jaccards)),
        "mean_runtime_sec": float(np.mean(svt_runtimes)),
    }

    return results


def run_e3_scalability(seeds: List[int] = None) -> Dict[str, Any]:
    """E3: トランザクション数 vs 実行時間。"""
    if seeds is None:
        seeds = [42, 43, 44]
    sizes = [100, 200, 500, 1000, 2000]
    epsilon = 1.0
    window_size = 20
    threshold = 5

    results: Dict[str, Any] = {"sizes": sizes, "per_size": {}}

    for n in sizes:
        runtimes = []
        for seed in seeds:
            data = generate_synthetic_dp_data(
                n_transactions=n,
                dense_itemset=(1, 2),
                dense_start=n // 4,
                dense_end=3 * n // 4,
                dense_prob=0.8,
                background_prob=0.05,
                seed=seed,
            )
            t0 = time.perf_counter()
            mine_dp_dense_itemsets(
                data, window_size, threshold, 3, epsilon=epsilon, seed=seed,
            )
            runtimes.append(time.perf_counter() - t0)

        results["per_size"][str(n)] = {
            "mean_runtime_sec": float(np.mean(runtimes)),
            "std_runtime_sec": float(np.std(runtimes)),
        }

    return results


def run_e4_stability_analysis(seeds: List[int] = None) -> Dict[str, Any]:
    """E4: 閾値安定性マージンと偽陽性率の関係。"""
    if seeds is None:
        seeds = list(range(42, 52))
    epsilons = [0.5, 1.0, 2.0, 5.0]
    confidences = [0.8, 0.9, 0.95, 0.99]
    window_size = 20
    threshold = 5

    results: Dict[str, Any] = {"per_config": {}}

    for eps in epsilons:
        for conf in confidences:
            margin = compute_stability_margin(1, eps, conf)
            key = f"eps={eps}_conf={conf}"
            results["per_config"][key] = {
                "epsilon": eps,
                "confidence": conf,
                "stability_margin": float(margin),
            }

    return results


def run_e5_budget_composition(seeds: List[int] = None) -> Dict[str, Any]:
    """E5: 逐次合成 vs 高度合成。"""
    if seeds is None:
        seeds = [42]
    n_queries_list = [10, 50, 100, 500]
    eps_per_query = 0.01
    delta_prime = 1e-5

    results: Dict[str, Any] = {"per_k": {}}

    for k in n_queries_list:
        sequential_eps = k * eps_per_query

        acc = PrivacyAccountant(sequential_eps + 1)  # 十分大きい予算
        for _ in range(k):
            acc.consume(eps_per_query)
        advanced_eps = acc.advanced_composition_epsilon(k, delta_prime)

        results["per_k"][str(k)] = {
            "sequential_epsilon": sequential_eps,
            "advanced_epsilon": float(advanced_eps),
            "savings_ratio": float(1 - advanced_eps / sequential_eps) if sequential_eps > 0 else 0.0,
        }

    return results


def main():
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: Dict[str, Any] = {}

    print("Running E1: Privacy-Accuracy Trade-off...")
    t0 = time.perf_counter()
    all_results["e1_privacy_accuracy"] = run_e1_privacy_accuracy_tradeoff()
    print(f"  Done in {time.perf_counter() - t0:.2f}s")

    print("Running E2: Mechanism Comparison...")
    t0 = time.perf_counter()
    all_results["e2_mechanism_comparison"] = run_e2_mechanism_comparison()
    print(f"  Done in {time.perf_counter() - t0:.2f}s")

    print("Running E3: Scalability...")
    t0 = time.perf_counter()
    all_results["e3_scalability"] = run_e3_scalability()
    print(f"  Done in {time.perf_counter() - t0:.2f}s")

    print("Running E4: Stability Analysis...")
    t0 = time.perf_counter()
    all_results["e4_stability"] = run_e4_stability_analysis()
    print(f"  Done in {time.perf_counter() - t0:.2f}s")

    print("Running E5: Budget Composition...")
    t0 = time.perf_counter()
    all_results["e5_composition"] = run_e5_budget_composition()
    print(f"  Done in {time.perf_counter() - t0:.2f}s")

    out_path = out_dir / "all_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
