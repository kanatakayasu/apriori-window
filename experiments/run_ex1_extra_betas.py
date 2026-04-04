"""
EX1 extra beta conditions: β=0.1 and β=0.4 (20 seeds each).
Results are merged into the existing ex1_20seeds/ex1_results.json.
"""
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import generate_synthetic, make_ex1_config
from experiments.src.run_experiment import AttributionConfig, run_single_experiment

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex1_20seeds"
DATA_DIR = Path(__file__).resolve().parent / "data" / "ex1_20seeds"

NEW_CONDITIONS = {
    "beta_0.1": lambda seed: make_ex1_config(boost=0.1, seed=seed),
    "beta_0.4": lambda seed: make_ex1_config(boost=0.4, seed=seed),
}

N_SEEDS = 20


def _compute_stats(values):
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0, 0.0, mean, mean
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance)
    se = std / math.sqrt(n)
    t_crit = 2.093  # t_{0.025,19}
    ci_lower = max(0.0, mean - t_crit * se)
    ci_upper = min(1.0, mean + t_crit * se)
    return mean, std, se, ci_lower, ci_upper


def run_extra_betas():
    print("=" * 70)
    print("EX1 extra betas: β=0.1, β=0.4 (20 seeds each)")
    print("=" * 70)

    # Load existing results
    results_path = RESULTS_DIR / "ex1_results.json"
    if results_path.exists():
        with open(results_path) as f:
            all_results = json.load(f)
        print(f"Loaded existing results from {results_path}")
    else:
        all_results = {}

    for cond_name, config_fn in NEW_CONDITIONS.items():
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

        avg_f1, std_f1, se_f1, ci95_lo, ci95_hi = _compute_stats(f1_vals)
        avg_p   = sum(p_vals)  / N_SEEDS
        avg_r   = sum(r_vals)  / N_SEEDS
        avg_far = sum(far_vals) / N_SEEDS

        print(f"  Mean: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f} "
              f"[95%CI: {ci95_lo:.2f}–{ci95_hi:.2f}] FAR={avg_far:.2f}")

        all_results[cond_name] = {
            "seeds": seed_results,
            "avg_precision": avg_p,
            "avg_recall": avg_r,
            "avg_f1": avg_f1,
            "std_f1": std_f1,
            "se_f1": se_f1,
            "ci95_lower": ci95_lo,
            "ci95_upper": ci95_hi,
            "avg_false_attribution_rate": avg_far,
        }

    # Save merged results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nMerged results saved to {results_path}")

    # Summary
    print("\n" + "=" * 80)
    print(f"{'Condition':<12s} {'Prec':>6s} {'Rec':>6s} {'F1':>6s} {'95%CI':>16s} {'FAR':>6s}")
    print("-" * 80)
    for name in ["beta_0.1", "beta_0.4"]:
        d = all_results[name]
        ci = f"[{d['ci95_lower']:.2f}, {d['ci95_upper']:.2f}]"
        print(f"{name:<12s} {d['avg_precision']:>6.2f} {d['avg_recall']:>6.2f} "
              f"{d['avg_f1']:>6.2f} {ci:>16s} {d['avg_false_attribution_rate']:>6.2f}")
    print("=" * 80)


if __name__ == "__main__":
    run_extra_betas()
