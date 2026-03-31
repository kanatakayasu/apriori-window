"""
E2: Parameter Sensitivity — How does performance vary with key parameters?

Sweeps one parameter at a time using a clean synthetic dataset.
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import (
    DecoyEvent,
    PlantedSignal,
    SyntheticConfig,
    generate_synthetic,
)
from experiments.src.run_experiment import (
    AttributionConfig,
    run_single_experiment,
    save_result,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "e2"
DATA_DIR = Path(__file__).resolve().parent / "data" / "e2"


def _base_config(seed=42):
    return SyntheticConfig(
        n_transactions=5000,
        n_items=200,
        p_base=0.03,
        planted_signals=[
            PlantedSignal([1001, 1002], "E1", "Sale", 800, 1200, boost_factor=0.5),
            PlantedSignal([1003, 1004], "E2", "Holiday", 2000, 2400, boost_factor=0.5),
            PlantedSignal([1005, 1006], "E3", "Campaign", 3200, 3600, boost_factor=0.5),
        ],
        decoy_events=[
            DecoyEvent("D1", "Decoy_1", 1500, 1700),
            DecoyEvent("D2", "Decoy_2", 4000, 4200),
        ],
        seed=seed,
    )


def sweep_window_size():
    """Sweep window_size."""
    print("--- Sweep: window_size ---")
    results = []
    for ws in [10, 20, 50, 100, 200]:
        seed_results = []
        for seed in range(3):
            config = _base_config(seed)
            out_dir = str(DATA_DIR / f"ws{ws}_seed{seed}")
            info = generate_synthetic(config, out_dir)

            attr_config = AttributionConfig(
                min_support_range=5,
                n_permutations=5000, alpha=0.20,
                correction_method="bh", global_correction=True, deduplicate_overlap=True, seed=seed,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=ws, min_support=3, max_length=100, config=attr_config,
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        avg_p = sum(r["precision"] for r in seed_results) / len(seed_results)
        avg_r = sum(r["recall"] for r in seed_results) / len(seed_results)
        print(f"  window_size={ws}: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f}")
        results.append({"window_size": ws, "seeds": seed_results})
    return results


def sweep_sigma():
    """Sweep sigma (proximity decay)."""
    print("--- Sweep: sigma ---")
    results = []
    for sigma in [5.0, 10.0, 25.0, 50.0, 100.0, 200.0]:
        seed_results = []
        for seed in range(3):
            config = _base_config(seed)
            out_dir = str(DATA_DIR / f"sigma{sigma}_seed{seed}")
            info = generate_synthetic(config, out_dir)

            attr_config = AttributionConfig(
                sigma=sigma, min_support_range=5,
                n_permutations=5000, alpha=0.20,
                correction_method="bh", global_correction=True, deduplicate_overlap=True, seed=seed,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=3, max_length=100, config=attr_config,
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        print(f"  sigma={sigma}: F1={avg_f1:.2f}")
        results.append({"sigma": sigma, "seeds": seed_results})
    return results


def sweep_n_permutations():
    """Sweep n_permutations."""
    print("--- Sweep: n_permutations ---")
    results = []
    for n_perm in [50, 100, 200, 500, 1000]:
        seed_results = []
        for seed in range(3):
            config = _base_config(seed)
            out_dir = str(DATA_DIR / f"nperm{n_perm}_seed{seed}")
            info = generate_synthetic(config, out_dir)

            attr_config = AttributionConfig(
                n_permutations=n_perm, min_support_range=5,
                alpha=0.20, correction_method="bh", global_correction=True, deduplicate_overlap=True, seed=seed,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=3, max_length=100, config=attr_config,
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        avg_time = sum(r["time_total_ms"] for r in seed_results) / len(seed_results)
        print(f"  n_permutations={n_perm}: F1={avg_f1:.2f} time={avg_time:.0f}ms")
        results.append({"n_permutations": n_perm, "seeds": seed_results})
    return results


def sweep_alpha():
    """Sweep significance level alpha."""
    print("--- Sweep: alpha ---")
    results = []
    for alpha in [0.001, 0.01, 0.05, 0.10, 0.20]:
        seed_results = []
        for seed in range(3):
            config = _base_config(seed)
            out_dir = str(DATA_DIR / f"alpha{alpha}_seed{seed}")
            info = generate_synthetic(config, out_dir)

            attr_config = AttributionConfig(
                n_permutations=5000, alpha=alpha, min_support_range=5,
                correction_method="bh",
                global_correction=True, deduplicate_overlap=True, seed=seed,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=3, max_length=100, config=attr_config,
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        avg_p = sum(r["precision"] for r in seed_results) / len(seed_results)
        avg_r = sum(r["recall"] for r in seed_results) / len(seed_results)
        print(f"  alpha={alpha}: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f}")
        results.append({"alpha": alpha, "seeds": seed_results})
    return results


def sweep_change_method():
    """Compare threshold_crossing vs CUSUM."""
    print("--- Sweep: change_method ---")
    results = []
    for method in ["threshold_crossing", "cusum"]:
        seed_results = []
        for seed in range(3):
            config = _base_config(seed)
            out_dir = str(DATA_DIR / f"method_{method}_seed{seed}")
            info = generate_synthetic(config, out_dir)

            attr_config = AttributionConfig(
                change_method=method, min_support_range=5,
                n_permutations=5000, alpha=0.20,
                correction_method="bh", global_correction=True, deduplicate_overlap=True, seed=seed,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=3, max_length=100, config=attr_config,
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        avg_p = sum(r["precision"] for r in seed_results) / len(seed_results)
        avg_r = sum(r["recall"] for r in seed_results) / len(seed_results)
        print(f"  method={method}: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f}")
        results.append({"change_method": method, "seeds": seed_results})
    return results


if __name__ == "__main__":
    all_results = {}
    all_results["window_size"] = sweep_window_size()
    print()
    all_results["sigma"] = sweep_sigma()
    print()
    all_results["n_permutations"] = sweep_n_permutations()
    print()
    all_results["alpha"] = sweep_alpha()
    print()
    all_results["change_method"] = sweep_change_method()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "e2_all_results.json")
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nE2 results saved to {save_path}")
