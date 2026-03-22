"""
Experiments E1-E5 for Paper D: Causal Attribution via Synthetic Control

E1: Recovery of known causal effects on synthetic data
E2: Donor pool size sensitivity
E3: False positive rate (null events)
E4: Semi-realistic Dunnhumby-style synthetic data
E5: Comparison with permutation test (Phase 2)
"""

import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# Setup imports
_repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_repo_root / "paper" / "D-causal-attribution" / "implementation" / "python"))

from synthetic_control_attribution import (
    build_donor_pool,
    compute_support_series,
    estimate_weights,
    run_causal_attribution,
    synthetic_control,
    placebo_test,
)

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = Path(__file__).parent / "figures"
RESULTS_DIR.mkdir(exist_ok=True)
FIGURES_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Synthetic Data Generators
# ---------------------------------------------------------------------------

def generate_causal_data(
    n_transactions: int = 500,
    n_items: int = 30,
    treated_items: Tuple[int, ...] = (1, 2, 3),
    n_control_patterns: int = 8,
    intervention_time_frac: float = 0.5,
    true_effect: float = 0.3,
    base_support: float = 0.15,
    noise_std: float = 0.02,
    seed: int = 42,
) -> Tuple[List[List[int]], List[Tuple[int, ...]], int, float]:
    """
    Generate synthetic transactions with a known causal effect.

    The treated pattern has its support boosted by `true_effect` after
    the intervention time. Control patterns are unaffected.

    Returns:
        (transactions, all_patterns, intervention_tx_idx, true_effect)
    """
    rng = np.random.RandomState(seed)
    intervention_tx = int(n_transactions * intervention_time_frac)

    # Generate control patterns (item-disjoint with treated)
    used_items = set(treated_items)
    control_patterns = []
    item_counter = max(used_items) + 1
    for _ in range(n_control_patterns):
        size = rng.choice([2, 3])
        pattern = tuple(range(item_counter, item_counter + size))
        item_counter += size
        used_items.update(pattern)
        control_patterns.append(pattern)

    all_items = list(range(1, item_counter))
    all_patterns = [treated_items] + control_patterns

    transactions = []
    for t in range(n_transactions):
        tx = []
        # Background items
        for item in all_items:
            if rng.random() < 0.05:
                tx.append(item)

        # Treated pattern: base support + effect after intervention
        p_treated = base_support + noise_std * rng.randn()
        if t >= intervention_tx:
            p_treated += true_effect
        p_treated = max(0, min(1, p_treated))
        if rng.random() < p_treated:
            for item in treated_items:
                if item not in tx:
                    tx.append(item)

        # Control patterns: stable support
        for cp in control_patterns:
            p_ctrl = base_support + noise_std * rng.randn()
            p_ctrl = max(0, min(1, p_ctrl))
            if rng.random() < p_ctrl:
                for item in cp:
                    if item not in tx:
                        tx.append(item)

        transactions.append(sorted(tx))

    return transactions, all_patterns, intervention_tx, true_effect


def generate_null_data(
    n_transactions: int = 500,
    n_items: int = 30,
    n_patterns: int = 6,
    base_support: float = 0.15,
    noise_std: float = 0.02,
    seed: int = 42,
) -> Tuple[List[List[int]], List[Tuple[int, ...]]]:
    """Generate data with NO causal effect (for false positive testing)."""
    rng = np.random.RandomState(seed)
    patterns = []
    item_counter = 1
    for _ in range(n_patterns):
        size = rng.choice([2, 3])
        pattern = tuple(range(item_counter, item_counter + size))
        item_counter += size
        patterns.append(pattern)

    all_items = list(range(1, item_counter))
    transactions = []
    for t in range(n_transactions):
        tx = []
        for item in all_items:
            if rng.random() < 0.05:
                tx.append(item)
        for cp in patterns:
            p = base_support + noise_std * rng.randn()
            p = max(0, min(1, p))
            if rng.random() < p:
                for item in cp:
                    if item not in tx:
                        tx.append(item)
        transactions.append(sorted(tx))

    return transactions, patterns


# ---------------------------------------------------------------------------
# E1: Recovery of Known Causal Effects
# ---------------------------------------------------------------------------

def run_e1(seeds: List[int] = list(range(20))) -> Dict:
    """Test recovery accuracy across multiple seeds and effect sizes."""
    print("=== E1: Causal Effect Recovery ===")
    results = {"effect_sizes": [], "recovered": [], "p_values": [], "errors": []}

    effect_sizes = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
    window_size = 30

    for effect in effect_sizes:
        recovered_list = []
        p_list = []
        for seed in seeds:
            tx, patterns, t0_tx, _ = generate_causal_data(
                n_transactions=500, true_effect=effect, seed=seed,
                n_control_patterns=6,
            )
            # Convert intervention time from tx-space to series-space
            t0_series = max(0, t0_tx - window_size + 1)

            result = run_causal_attribution(
                transactions=tx,
                treated_pattern=patterns[0],
                candidate_patterns=patterns[1:],
                intervention_time=t0_series,
                window_size=window_size,
                n_bootstrap=50,
                seed=seed,
            )

            if "error" not in result:
                # Average post-intervention causal effect
                ce = np.array(result["causal_effect"])
                avg_post_effect = float(np.mean(ce[t0_series:]))
                recovered_list.append(avg_post_effect)
                p_list.append(result["p_value"])
            else:
                recovered_list.append(float("nan"))
                p_list.append(1.0)

        mean_recovered = float(np.nanmean(recovered_list))
        mean_p = float(np.nanmean(p_list))
        error = abs(mean_recovered - effect)

        results["effect_sizes"].append(effect)
        results["recovered"].append(mean_recovered)
        results["p_values"].append(mean_p)
        results["errors"].append(error)

        print(f"  Effect={effect:.2f}: recovered={mean_recovered:.4f}, "
              f"error={error:.4f}, mean_p={mean_p:.4f}")

    return results


# ---------------------------------------------------------------------------
# E2: Donor Pool Size Sensitivity
# ---------------------------------------------------------------------------

def run_e2(seeds: List[int] = list(range(15))) -> Dict:
    """Test how donor pool size affects estimation quality."""
    print("\n=== E2: Donor Pool Size ===")
    results = {"n_donors": [], "mean_error": [], "mean_p": [], "pre_rmspe": []}

    donor_counts = [2, 3, 5, 8, 12, 20]
    window_size = 30
    true_effect = 0.2

    for n_donors in donor_counts:
        errors = []
        p_vals = []
        pre_rmspes = []
        for seed in seeds:
            tx, patterns, t0_tx, _ = generate_causal_data(
                n_transactions=500, true_effect=true_effect,
                n_control_patterns=n_donors, seed=seed,
            )
            t0_series = max(0, t0_tx - window_size + 1)

            result = run_causal_attribution(
                transactions=tx,
                treated_pattern=patterns[0],
                candidate_patterns=patterns[1:],
                intervention_time=t0_series,
                window_size=window_size,
                n_bootstrap=30,
                seed=seed,
            )

            if "error" not in result:
                ce = np.array(result["causal_effect"])
                avg_effect = float(np.mean(ce[t0_series:]))
                errors.append(abs(avg_effect - true_effect))
                p_vals.append(result["p_value"])
                pre_rmspes.append(result["pre_rmspe"])

        results["n_donors"].append(n_donors)
        results["mean_error"].append(float(np.mean(errors)) if errors else float("nan"))
        results["mean_p"].append(float(np.mean(p_vals)) if p_vals else 1.0)
        results["pre_rmspe"].append(float(np.mean(pre_rmspes)) if pre_rmspes else float("nan"))

        print(f"  Donors={n_donors}: mean_error={results['mean_error'][-1]:.4f}, "
              f"mean_p={results['mean_p'][-1]:.4f}")

    return results


# ---------------------------------------------------------------------------
# E3: False Positive Rate
# ---------------------------------------------------------------------------

def run_e3(n_trials: int = 100) -> Dict:
    """Test rejection rate under null (no true effect)."""
    print("\n=== E3: False Positive Rate ===")
    window_size = 30
    alpha_levels = [0.01, 0.05, 0.10]
    rejections = {a: 0 for a in alpha_levels}
    p_values = []

    for seed in range(n_trials):
        tx, patterns = generate_null_data(
            n_transactions=400, n_patterns=6, seed=seed
        )
        # Arbitrary "intervention" at midpoint
        t0_series = (len(tx) - window_size + 1) // 2

        result = run_causal_attribution(
            transactions=tx,
            treated_pattern=patterns[0],
            candidate_patterns=patterns[1:],
            intervention_time=t0_series,
            window_size=window_size,
            n_bootstrap=30,
            seed=seed,
        )

        if "error" not in result:
            p = result["p_value"]
            p_values.append(p)
            for a in alpha_levels:
                if p < a:
                    rejections[a] += 1

    n_valid = len(p_values)
    results = {
        "n_trials": n_trials,
        "n_valid": n_valid,
        "alpha_levels": alpha_levels,
        "rejection_rates": [rejections[a] / n_valid if n_valid > 0 else 0.0 for a in alpha_levels],
        "mean_p_value": float(np.mean(p_values)) if p_values else float("nan"),
    }

    for a, rate in zip(alpha_levels, results["rejection_rates"]):
        print(f"  alpha={a}: rejection_rate={rate:.4f} (expected ~{a})")

    return results


# ---------------------------------------------------------------------------
# E4: Semi-Realistic (Dunnhumby-style) Synthetic
# ---------------------------------------------------------------------------

def run_e4(seeds: List[int] = list(range(10))) -> Dict:
    """Dunnhumby-style campaign scenario with seasonal baseline."""
    print("\n=== E4: Dunnhumby-style Synthetic ===")
    window_size = 30
    results = {"seeds": [], "recovered_effect": [], "p_value": [], "ci_width": []}

    for seed in seeds:
        rng = np.random.RandomState(seed)
        n_tx = 600
        # Seasonal baseline
        t_arr = np.arange(n_tx, dtype=float)
        seasonal = 0.03 * np.sin(2 * np.pi * t_arr / 52)  # weekly seasonality

        # Campaign at t=300
        campaign_start = 300
        campaign_boost = 0.15

        # Treated: {1,2,3} - affected by campaign
        # Controls: {10,11}, {12,13,14}, {15,16}, {17,18,19}, {20,21}
        treated = (1, 2, 3)
        controls = [(10, 11), (12, 13, 14), (15, 16), (17, 18, 19), (20, 21)]

        all_items = set()
        for p in [treated] + controls:
            all_items.update(p)
        all_items = sorted(all_items)

        transactions = []
        for t in range(n_tx):
            tx = []
            # Background
            for item in all_items:
                if rng.random() < 0.05:
                    tx.append(item)

            # Treated pattern
            p_t = 0.12 + seasonal[t] + 0.02 * rng.randn()
            if t >= campaign_start:
                p_t += campaign_boost
            if rng.random() < max(0, min(1, p_t)):
                for item in treated:
                    if item not in tx:
                        tx.append(item)

            # Control patterns (share seasonality but not campaign)
            for cp in controls:
                p_c = 0.12 + seasonal[t] + 0.02 * rng.randn()
                if rng.random() < max(0, min(1, p_c)):
                    for item in cp:
                        if item not in tx:
                            tx.append(item)

            transactions.append(sorted(tx))

        t0_series = max(0, campaign_start - window_size + 1)

        result = run_causal_attribution(
            transactions=transactions,
            treated_pattern=treated,
            candidate_patterns=controls,
            intervention_time=t0_series,
            window_size=window_size,
            n_bootstrap=50,
            seed=seed,
        )

        if "error" not in result:
            ce = np.array(result["causal_effect"])
            avg_effect = float(np.mean(ce[t0_series:]))
            ci_w = float(np.mean(
                np.array(result["ci_upper"])[t0_series:] -
                np.array(result["ci_lower"])[t0_series:]
            ))
            results["seeds"].append(seed)
            results["recovered_effect"].append(avg_effect)
            results["p_value"].append(result["p_value"])
            results["ci_width"].append(ci_w)

            print(f"  Seed={seed}: effect={avg_effect:.4f}, p={result['p_value']:.4f}, "
                  f"CI_width={ci_w:.4f}")

    results["mean_effect"] = float(np.mean(results["recovered_effect"]))
    results["mean_p"] = float(np.mean(results["p_value"]))
    results["true_effect"] = campaign_boost
    return results


# ---------------------------------------------------------------------------
# E5: Comparison with Permutation Test
# ---------------------------------------------------------------------------

def run_e5(seeds: List[int] = list(range(15))) -> Dict:
    """Compare SCM-based p-values with simple permutation test p-values."""
    print("\n=== E5: SCM vs Permutation Test ===")
    window_size = 30
    true_effect = 0.2
    results = {"scm_p": [], "perm_p": [], "scm_detected": [], "perm_detected": []}

    for seed in seeds:
        tx, patterns, t0_tx, _ = generate_causal_data(
            n_transactions=500, true_effect=true_effect,
            n_control_patterns=6, seed=seed,
        )
        t0_series = max(0, t0_tx - window_size + 1)

        # SCM approach
        scm_result = run_causal_attribution(
            transactions=tx,
            treated_pattern=patterns[0],
            candidate_patterns=patterns[1:],
            intervention_time=t0_series,
            window_size=window_size,
            n_bootstrap=30,
            seed=seed,
        )

        if "error" in scm_result:
            continue

        scm_p = scm_result["p_value"]

        # Simple permutation test: shuffle time labels and compare
        treated_series = np.array(scm_result["treated_series"])
        n_perm = 199
        rng = np.random.RandomState(seed)
        obs_diff = float(np.mean(treated_series[t0_series:]) - np.mean(treated_series[:t0_series]))
        count_extreme = 0
        for _ in range(n_perm):
            perm_series = treated_series.copy()
            rng.shuffle(perm_series)
            perm_diff = float(np.mean(perm_series[t0_series:]) - np.mean(perm_series[:t0_series]))
            if abs(perm_diff) >= abs(obs_diff):
                count_extreme += 1
        perm_p = (count_extreme + 1) / (n_perm + 1)

        results["scm_p"].append(scm_p)
        results["perm_p"].append(perm_p)
        results["scm_detected"].append(scm_p < 0.05)
        results["perm_detected"].append(perm_p < 0.05)

        print(f"  Seed={seed}: SCM_p={scm_p:.4f}, Perm_p={perm_p:.4f}")

    results["scm_power"] = float(np.mean(results["scm_detected"])) if results["scm_detected"] else 0.0
    results["perm_power"] = float(np.mean(results["perm_detected"])) if results["perm_detected"] else 0.0
    print(f"  Power: SCM={results['scm_power']:.3f}, Perm={results['perm_power']:.3f}")

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start_time = time.time()

    e1 = run_e1()
    e2 = run_e2()
    e3 = run_e3()
    e4 = run_e4()
    e5 = run_e5()

    # Save results
    all_results = {"e1": e1, "e2": e2, "e3": e3, "e4": e4, "e5": e5}
    with open(RESULTS_DIR / "all_results.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    elapsed = time.time() - start_time
    print(f"\nAll experiments completed in {elapsed:.1f}s")
    print(f"Results saved to {RESULTS_DIR / 'all_results.json'}")

    return all_results


if __name__ == "__main__":
    main()
