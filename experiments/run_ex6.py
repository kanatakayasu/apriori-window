"""
EX6: Zipf-Distribution Robustness — Does the pipeline degrade under realistic
(non-uniform) item frequency distributions?

Addresses reviewer concern that uniform p_base=0.03 is unrealistic; real
basket data follows Zipf / power-law item frequencies.

3 conditions:
  zipf_1.0     — Zipf α=1.0 (standard Zipf's law)
  zipf_1.5     — Zipf α=1.5 (heavy-tailed; few dominant items)
  correlated   — Zipf α=1.0 + correlated item pairs (bread+butter)

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
    make_ex6_zipf_config,
    make_ex6_correlated_config,
)
from experiments.src.run_experiment import (
    AttributionConfig,
    run_single_experiment,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex6"
DATA_DIR = Path(__file__).resolve().parent / "data" / "ex6"

# --- 3 conditions ---
CONDITIONS = {
    "zipf_1.0":   lambda seed: make_ex6_zipf_config(zipf_alpha=1.0, seed=seed),
    "zipf_1.5":   lambda seed: make_ex6_zipf_config(zipf_alpha=1.5, seed=seed),
    "correlated": lambda seed: make_ex6_correlated_config(zipf_alpha=1.0, seed=seed),
}

N_SEEDS = 5


def run_ex6():
    """Run all EX6 conditions."""
    print("=" * 70)
    print("EX6: Zipf-Distribution Robustness")
    print("  Conditions: zipf_1.0, zipf_1.5, correlated")
    print(f"  Seeds: {N_SEEDS} per condition")
    print("=" * 70)

    all_results = {}

    for cond_name, config_fn in CONDITIONS.items():
        print(f"\n--- {cond_name} ---")
        seed_results = []

        for seed in range(N_SEEDS):
            config = config_fn(seed)
            out_dir = str(DATA_DIR / f"{cond_name}_seed{seed}")
            info = generate_synthetic(config, out_dir)

            attr_config = AttributionConfig(
                min_support_range=5,
                n_permutations=5000,
                alpha=0.10,
                correction_method="bh",
                global_correction=True,
                deduplicate_overlap=True,
                seed=seed,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=5, max_length=100,
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
    save_path = str(RESULTS_DIR / "ex6_results.json")
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nEX6 results saved to {save_path}")

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
    run_ex6()
