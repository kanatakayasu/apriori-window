"""
EX3: Parameter Sensitivity — How robust is the pipeline to parameter choices?

Uses EX1's vocabulary-internal data (β=0.3 fixed) and sweeps 4 parameters:
  - W (window size): {10, 20, 50, 100, 200}
  - α (significance level): {0.01, 0.05, 0.10, 0.20, 0.30}
  - B (permutation count): {50, 100, 500, 1000, 5000}
  - Change detection method: threshold_crossing vs CUSUM

Presentation: 4-panel figure.
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
)
from experiments.src.run_experiment import (
    AttributionConfig,
    run_single_experiment,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex3"
DATA_DIR = Path(__file__).resolve().parent / "data" / "ex3"

# Fixed baseline: EX1 config with β=0.3
FIXED_BOOST = 0.3


def _generate_data(seed):
    """Generate EX1-style vocabulary-internal data."""
    config = make_ex1_config(
        n_transactions=5000,
        boost=FIXED_BOOST,
        n_unrelated=2,
        n_decoy=2,
        seed=seed,
    )
    out_dir = str(DATA_DIR / f"base_seed{seed}")
    return generate_synthetic(config, out_dir)


def _base_attr_config(seed):
    """Default attribution config (baseline)."""
    return AttributionConfig(
        min_support_range=5,
        n_permutations=5000,
        alpha=0.20,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=seed,
    )


def sweep_window_size():
    """Sweep window size W."""
    print("--- Sweep: window_size ---")
    results = []
    for ws in [10, 20, 50, 100, 200]:
        seed_results = []
        for seed in range(3):
            info = _generate_data(seed)
            attr_config = _base_attr_config(seed)
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=ws, min_support=3, max_length=100,
                config=attr_config,
                unrelated_path=info.get("unrelated_path"),
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        avg_far = sum(r["false_attribution_rate"] for r in seed_results) / len(seed_results)
        print(f"  W={ws}: F1={avg_f1:.2f} FAR={avg_far:.2f}")
        results.append({"window_size": ws, "seeds": seed_results})
    return results


def sweep_alpha():
    """Sweep significance level α."""
    print("--- Sweep: alpha ---")
    results = []
    for alpha in [0.01, 0.05, 0.10, 0.20, 0.30]:
        seed_results = []
        for seed in range(3):
            info = _generate_data(seed)
            attr_config = _base_attr_config(seed)
            attr_config.alpha = alpha
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=3, max_length=100,
                config=attr_config,
                unrelated_path=info.get("unrelated_path"),
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        avg_far = sum(r["false_attribution_rate"] for r in seed_results) / len(seed_results)
        print(f"  α={alpha}: F1={avg_f1:.2f} FAR={avg_far:.2f}")
        results.append({"alpha": alpha, "seeds": seed_results})
    return results


def sweep_n_permutations():
    """Sweep permutation count B."""
    print("--- Sweep: n_permutations ---")
    results = []
    for n_perm in [50, 100, 500, 1000, 5000]:
        seed_results = []
        for seed in range(3):
            info = _generate_data(seed)
            attr_config = _base_attr_config(seed)
            attr_config.n_permutations = n_perm
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=3, max_length=100,
                config=attr_config,
                unrelated_path=info.get("unrelated_path"),
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        avg_time = sum(r["time_total_ms"] for r in seed_results) / len(seed_results)
        print(f"  B={n_perm}: F1={avg_f1:.2f} time={avg_time:.0f}ms")
        results.append({"n_permutations": n_perm, "seeds": seed_results})
    return results


def sweep_change_method():
    """Compare threshold_crossing vs CUSUM."""
    print("--- Sweep: change_method ---")
    results = []
    for method in ["threshold_crossing", "cusum"]:
        seed_results = []
        for seed in range(3):
            info = _generate_data(seed)
            attr_config = _base_attr_config(seed)
            attr_config.change_method = method
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=3, max_length=100,
                config=attr_config,
                unrelated_path=info.get("unrelated_path"),
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        print(f"  method={method}: F1={avg_f1:.2f}")
        results.append({"change_method": method, "seeds": seed_results})
    return results


if __name__ == "__main__":
    all_results = {}
    all_results["window_size"] = sweep_window_size()
    print()
    all_results["alpha"] = sweep_alpha()
    print()
    all_results["n_permutations"] = sweep_n_permutations()
    print()
    all_results["change_method"] = sweep_change_method()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "ex3_all_results.json")
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nEX3 results saved to {save_path}")
