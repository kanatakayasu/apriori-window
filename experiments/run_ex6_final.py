"""
EX6 Final: Baseline vs Improved (sqrt normalization + relative change filter).

Runs baseline and improved configs side-by-side to produce the final paper numbers.
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
DATA_DIR = Path(__file__).resolve().parent / "data" / "ex6_final"

CONDITIONS = {
    "zipf_1.0":   lambda seed: make_ex6_zipf_config(zipf_alpha=1.0, seed=seed),
    "zipf_1.5":   lambda seed: make_ex6_zipf_config(zipf_alpha=1.5, seed=seed),
    "correlated": lambda seed: make_ex6_correlated_config(zipf_alpha=1.0, seed=seed),
}

ATTR_CONFIGS = {
    "baseline": lambda seed: AttributionConfig(
        min_support_range=5, n_permutations=5000, alpha=0.10,
        correction_method="bh", global_correction=True,
        deduplicate_overlap=True, seed=seed,
        magnitude_normalization="none",
    ),
    "improved": lambda seed: AttributionConfig(
        min_support_range=5, n_permutations=5000, alpha=0.10,
        correction_method="bh", global_correction=True,
        deduplicate_overlap=True, seed=seed,
        magnitude_normalization="sqrt",
        min_relative_change=0.5,
    ),
}

N_SEEDS = 5


def run():
    print("=" * 80)
    print("EX6 Final: Baseline vs Improved (sqrt + min_relative_change=0.5)")
    print("=" * 80)

    all_results = {}

    for cond_name, config_fn in CONDITIONS.items():
        print(f"\n{'='*60}")
        print(f"Condition: {cond_name}")
        print(f"{'='*60}")

        cond_results = {}
        data_cache = {}
        for seed in range(N_SEEDS):
            config = config_fn(seed)
            out_dir = str(DATA_DIR / f"{cond_name}_seed{seed}")
            info = generate_synthetic(config, out_dir)
            data_cache[seed] = info

        for attr_name, attr_fn in ATTR_CONFIGS.items():
            print(f"\n  --- {attr_name} ---")
            seed_results = []
            for seed in range(N_SEEDS):
                info = data_cache[seed]
                attr_config = attr_fn(seed)
                result = run_single_experiment(
                    info["txn_path"], info["events_path"], info["gt_path"],
                    window_size=50, min_support=5, max_length=100,
                    config=attr_config,
                    unrelated_path=info.get("unrelated_path"),
                )
                print(f"    seed={seed}: P={result.precision:.2f} R={result.recall:.2f} "
                      f"F1={result.f1:.2f} FAR={result.false_attribution_rate:.2f}")
                seed_results.append(asdict(result))

            avg_p = sum(r["precision"] for r in seed_results) / len(seed_results)
            avg_r = sum(r["recall"] for r in seed_results) / len(seed_results)
            avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
            avg_far = sum(r["false_attribution_rate"] for r in seed_results) / len(seed_results)
            print(f"  Average: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f} FAR={avg_far:.2f}")

            cond_results[attr_name] = {
                "seeds": seed_results,
                "avg_precision": avg_p,
                "avg_recall": avg_r,
                "avg_f1": avg_f1,
                "avg_false_attribution_rate": avg_far,
            }

        all_results[cond_name] = cond_results

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "ex6_final_results.json")
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {save_path}")

    # Summary
    print("\n" + "=" * 80)
    print(f"{'Condition':<14s} {'Config':<12s} {'P':>6s} {'R':>6s} {'F1':>6s} {'FAR':>6s}")
    print("-" * 80)
    for cond_name, cond_data in all_results.items():
        for attr_name, data in cond_data.items():
            print(f"{cond_name:<14s} {attr_name:<12s} "
                  f"{data['avg_precision']:>6.2f} {data['avg_recall']:>6.2f} "
                  f"{data['avg_f1']:>6.2f} {data['avg_false_attribution_rate']:>6.2f}")
        print("-" * 80)
    print("=" * 80)


if __name__ == "__main__":
    run()
