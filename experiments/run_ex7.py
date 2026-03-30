"""
EX7: Naive Baseline Comparison — Does the statistical testing pipeline
add value beyond simple score-based ranking?

Compares 4 method variants on EX1 data (β=0.3, CONFOUND, DENSE):
  Naive       — Steps 1-3 only (score > threshold, no test)
  +PermTest   — Add per-pattern permutation test (no global correction)
  +BH         — Add global BH correction
  Full        — Add Union-Find deduplication (= full pipeline)

Each condition × 5 seeds. Evaluation: P/R/F1/FAR/#Predictions.
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import (
    generate_synthetic,
    make_ex1_config,
    make_ex1_confound_config,
    make_ex1_dense_config,
)
from experiments.src.run_experiment import (
    AttributionConfig,
    run_naive_experiment,
    run_single_experiment,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex7"
DATA_DIR = Path(__file__).resolve().parent / "data" / "ex7"

CONDITIONS = {
    "beta_0.3": lambda seed: make_ex1_config(boost=0.3, seed=seed),
    "CONFOUND": lambda seed: make_ex1_confound_config(seed=seed),
    "DENSE":    lambda seed: make_ex1_dense_config(seed=seed),
}

METHODS = {
    "Naive": dict(naive=True),
    "+PermTest": dict(naive=False, global_correction=False, deduplicate_overlap=False),
    "+BH": dict(naive=False, global_correction=True, deduplicate_overlap=False),
    "Full": dict(naive=False, global_correction=True, deduplicate_overlap=True),
}

N_SEEDS = 5


def _run_method(method_name, method_cfg, info, seed):
    """Run a single method variant."""
    if method_cfg.get("naive"):
        config = AttributionConfig(
            min_support_range=5,
            seed=seed,
        )
        return run_naive_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=2,
            config=config,
            unrelated_path=info.get("unrelated_path"),
        )
    else:
        config = AttributionConfig(
            min_support_range=5,
            n_permutations=5000,
            alpha=0.10,
            correction_method="bh",
            global_correction=method_cfg["global_correction"],
            deduplicate_overlap=method_cfg["deduplicate_overlap"],
            seed=seed,
        )
        return run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=2,
            config=config,
            unrelated_path=info.get("unrelated_path"),
        )


def run_ex7():
    """Run EX7: Naive Baseline Comparison."""
    print("=" * 70)
    print("EX7: Naive Baseline Comparison")
    print("  Conditions: beta_0.3, CONFOUND, DENSE")
    print("  Methods: Naive, +PermTest, +BH, Full")
    print(f"  Seeds: {N_SEEDS} per condition")
    print("=" * 70)

    all_results = {}

    for cond_name, config_fn in CONDITIONS.items():
        print(f"\n{'='*50}")
        print(f"Condition: {cond_name}")
        print(f"{'='*50}")

        cond_results = {}

        for method_name, method_cfg in METHODS.items():
            print(f"\n  --- {method_name} ---")
            seed_results = []

            for seed in range(N_SEEDS):
                config = config_fn(seed)
                out_dir = str(DATA_DIR / f"{cond_name}_seed{seed}")
                info = generate_synthetic(config, out_dir)

                result = _run_method(method_name, method_cfg, info, seed)
                print(f"    seed={seed}: P={result.precision:.2f} R={result.recall:.2f} "
                      f"F1={result.f1:.2f} FAR={result.false_attribution_rate:.2f} "
                      f"#pred={result.n_significant} "
                      f"(TP={result.tp} FP={result.fp} FN={result.fn})")
                seed_results.append(asdict(result))

            n = len(seed_results)
            avg = {
                "precision": sum(r["precision"] for r in seed_results) / n,
                "recall": sum(r["recall"] for r in seed_results) / n,
                "f1": sum(r["f1"] for r in seed_results) / n,
                "far": sum(r["false_attribution_rate"] for r in seed_results) / n,
                "n_pred": sum(r["n_significant"] for r in seed_results) / n,
                "tp": sum(r["tp"] for r in seed_results) / n,
                "fp": sum(r["fp"] for r in seed_results) / n,
            }
            print(f"    Avg: P={avg['precision']:.2f} R={avg['recall']:.2f} "
                  f"F1={avg['f1']:.2f} FAR={avg['far']:.2f} "
                  f"#pred={avg['n_pred']:.1f}")

            cond_results[method_name] = {
                "seeds": seed_results,
                **{f"avg_{k}": v for k, v in avg.items()},
            }

        all_results[cond_name] = cond_results

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "ex7_results.json")
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nEX7 results saved to {save_path}")

    # Summary table
    print("\n" + "=" * 80)
    print(f"{'Condition':<12s} {'Method':<12s} {'P':>6s} {'R':>6s} {'F1':>6s} "
          f"{'FAR':>6s} {'#Pred':>7s} {'TP':>5s} {'FP':>5s}")
    print("-" * 80)
    for cond_name, cond_data in all_results.items():
        for method_name, method_data in cond_data.items():
            print(f"{cond_name:<12s} {method_name:<12s} "
                  f"{method_data['avg_precision']:>6.2f} "
                  f"{method_data['avg_recall']:>6.2f} "
                  f"{method_data['avg_f1']:>6.2f} "
                  f"{method_data['avg_far']:>6.2f} "
                  f"{method_data['avg_n_pred']:>7.1f} "
                  f"{method_data['avg_tp']:>5.1f} "
                  f"{method_data['avg_fp']:>5.1f}")
        print("-" * 80)
    print("=" * 80)

    return all_results


if __name__ == "__main__":
    run_ex7()
