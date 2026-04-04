"""
Appendix Experiment: Robustness under item-item correlation (Zipf + correlated pairs).

Tests whether the attribution pipeline maintains attribution accuracy when
items have strong pairwise correlations (simulating realistic grocery data).
Also empirically assesses whether the magnitude ordering assumed in the
deduplication claim (Claim 1) holds under correlated co-occurrence.

Conditions:
  - zipf_only:   Zipf-distributed item frequencies, independent items
  - zipf_corr:   Zipf + 5 correlated item pairs (corr prob 0.5–0.7)

20 seeds each. Results saved for appendix reporting.
"""
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import (
    generate_synthetic,
    make_ex6_zipf_config,
    make_ex6_correlated_config,
)
from experiments.src.run_experiment import AttributionConfig, run_single_experiment

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex_robustness"
DATA_DIR    = Path(__file__).resolve().parent / "data"    / "ex_robustness"
N_SEEDS = 20


def _compute_stats(values):
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0, 0.0, mean, mean
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance)
    se = std / math.sqrt(n)
    t_crit = 2.093  # t_{0.025, df=19}
    ci_lo = max(0.0, mean - t_crit * se)
    ci_hi = min(1.0, mean + t_crit * se)
    return mean, std, se, ci_lo, ci_hi


CONDITIONS = {
    "zipf_only": lambda seed: make_ex6_zipf_config(zipf_alpha=1.0, seed=seed),
    "zipf_corr": lambda seed: make_ex6_correlated_config(zipf_alpha=1.0, seed=seed),
}


def run_robustness_experiment():
    print("=" * 70)
    print("Appendix: Robustness under Item-Item Correlation")
    print(f"  Seeds: {N_SEEDS} per condition")
    print("=" * 70)

    all_results = {}

    for cond_name, config_fn in CONDITIONS.items():
        print(f"\n--- {cond_name} ---")
        seed_results = []

        for seed in range(N_SEEDS):
            config = config_fn(seed)
            out_dir = str(DATA_DIR / f"{cond_name}_seed{seed}")
            info = generate_synthetic(config, out_dir, window_size=1000, min_support=100)

            attr_config = AttributionConfig(
                n_permutations=5000,
                alpha=0.10,
                correction_method="bh",
                global_correction=True,
                deduplicate_overlap=True,
                seed=seed,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=1000, min_support=100, max_length=2,
                config=attr_config,
                unrelated_path=info.get("unrelated_path"),
            )
            print(f"  seed={seed:2d}: P={result.precision:.2f} R={result.recall:.2f} "
                  f"F1={result.f1:.2f} (TP={result.tp} FP={result.fp} FN={result.fn})")
            seed_results.append(asdict(result))

        f1_vals  = [r["f1"] for r in seed_results]
        p_vals   = [r["precision"] for r in seed_results]
        r_vals   = [r["recall"] for r in seed_results]
        far_vals = [r["false_attribution_rate"] for r in seed_results]

        avg_f1, std_f1, se_f1, ci_lo, ci_hi = _compute_stats(f1_vals)
        avg_p   = sum(p_vals)   / N_SEEDS
        avg_r   = sum(r_vals)   / N_SEEDS
        avg_far = sum(far_vals) / N_SEEDS
        print(f"  Mean: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f} "
              f"[95%CI: {ci_lo:.2f}–{ci_hi:.2f}] FAR={avg_far:.2f}")

        all_results[cond_name] = {
            "seeds": seed_results,
            "avg_precision": avg_p,
            "avg_recall": avg_r,
            "avg_f1": avg_f1,
            "std_f1": std_f1,
            "se_f1": se_f1,
            "ci95_lower": ci_lo,
            "ci95_upper": ci_hi,
            "avg_false_attribution_rate": avg_far,
        }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = RESULTS_DIR / "robustness_results.json"
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {save_path}")

    print("\n" + "=" * 75)
    print(f"{'Condition':<14s} {'Prec':>6s} {'Rec':>6s} {'F1':>6s} {'95%CI':>16s} {'FAR':>6s}")
    print("-" * 75)
    for name, data in all_results.items():
        ci = f"[{data['ci95_lower']:.2f}, {data['ci95_upper']:.2f}]"
        print(f"{name:<14s} {data['avg_precision']:>6.2f} {data['avg_recall']:>6.2f} "
              f"{data['avg_f1']:>6.2f} {ci:>16s} {data['avg_false_attribution_rate']:>6.2f}")
    print("=" * 75)
    return all_results


if __name__ == "__main__":
    run_robustness_experiment()
