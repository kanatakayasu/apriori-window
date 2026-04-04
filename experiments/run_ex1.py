"""
EX1: Core Attribution Accuracy — Can the pipeline correctly attribute event-driven
changes and reject unrelated dense patterns?

7 conditions testing signal strength and structural diversity:
  Beta sweep (signal strength):
    β=0.2, 0.3, 0.5
  Structural conditions (β=0.3 fixed):
    OVERLAP  — temporally overlapping events
    CONFOUND — Type B patterns deliberately near events
    DENSE    — 6 planted + 4 Type B + 4 decoy (2x scale)
    SHORT    — event duration 80 (vs 300 baseline)

Each condition × 5 seeds. Evaluation: P/R/F1 + FAR.
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
    make_ex1_overlap_config,
    make_ex1_confound_config,
    make_ex1_dense_config,
    make_ex1_short_config,
)
from experiments.src.run_experiment import (
    AttributionConfig,
    run_single_experiment,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex1"
DATA_DIR = Path(__file__).resolve().parent / "data" / "ex1"

# --- 7 conditions ---
CONDITIONS = {
    # Beta sweep (signal strength)
    "beta_0.2": lambda seed: make_ex1_config(boost=0.2, seed=seed),
    "beta_0.3": lambda seed: make_ex1_config(boost=0.3, seed=seed),
    "beta_0.5": lambda seed: make_ex1_config(boost=0.5, seed=seed),
    # Structural conditions (β=0.3 fixed)
    "OVERLAP":  lambda seed: make_ex1_overlap_config(seed=seed),
    "CONFOUND": lambda seed: make_ex1_confound_config(seed=seed),
    "DENSE":    lambda seed: make_ex1_dense_config(seed=seed),
    "SHORT":    lambda seed: make_ex1_short_config(seed=seed),
}

N_SEEDS = 5


def run_ex1():
    """Run all EX1 conditions."""
    print("=" * 70)
    print("EX1: Core Attribution Accuracy")
    print("  Beta sweep: β ∈ {0.2, 0.3, 0.5}")
    print("  Structural: OVERLAP, CONFOUND, DENSE, SHORT")
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

            print(f"  seed={seed}: P={result.precision:.2f} R={result.recall:.2f} "
                  f"F1={result.f1:.2f} FAR={result.false_attribution_rate:.2f} "
                  f"(TP={result.tp} FP={result.fp} FN={result.fn})")
            seed_results.append(asdict(result))

        avg_p = sum(r["precision"] for r in seed_results) / len(seed_results)
        avg_r = sum(r["recall"] for r in seed_results) / len(seed_results)
        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        avg_far = sum(r["false_attribution_rate"] for r in seed_results) / len(seed_results)
        print(f"  Average: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f} FAR={avg_far:.2f}")

        all_results[cond_name] = {
            "seeds": seed_results,
            "avg_precision": avg_p,
            "avg_recall": avg_r,
            "avg_f1": avg_f1,
            "avg_false_attribution_rate": avg_far,
        }

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "ex1_results.json")
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nEX1 results saved to {save_path}")

    # Summary table
    print("\n" + "=" * 70)
    print(f"{'Condition':<12s} {'Precision':>10s} {'Recall':>8s} {'F1':>6s} {'FAR':>6s}")
    print("-" * 70)
    for name, data in all_results.items():
        print(f"{name:<12s} {data['avg_precision']:>10.2f} "
              f"{data['avg_recall']:>8.2f} {data['avg_f1']:>6.2f} "
              f"{data['avg_false_attribution_rate']:>6.2f}")
    print("=" * 70)

    return all_results


if __name__ == "__main__":
    run_ex1()
