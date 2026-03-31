"""
E1: Ground Truth Recovery — Can the pipeline correctly identify known attributions?

Sub-experiments:
  E1a: Clean signal (high boost)
  E1b: Moderate signal (lower boost)
  E1c: Multiple simultaneous events
  E1d: Varying planted/decoy counts
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

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "e1"
DATA_DIR = Path(__file__).resolve().parent / "data" / "e1"


def run_e1a():
    """E1a: Clean signal — high boost, well-separated events."""
    print("=== E1a: Clean Signal ===")
    results = []
    for seed in range(5):
        config = SyntheticConfig(
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
        out_dir = str(DATA_DIR / f"e1a_seed{seed}")
        info = generate_synthetic(config, out_dir)

        attr_config = AttributionConfig(
            min_support_range=5,
            n_permutations=5000,
            alpha=0.20,
            correction_method="bh",
            global_correction=True,
            deduplicate_overlap=True,
            seed=seed,
        )
        result = run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=100,
            config=attr_config,
        )
        print(f"  seed={seed}: P={result.precision:.2f} R={result.recall:.2f} "
              f"F1={result.f1:.2f} (TP={result.tp} FP={result.fp} FN={result.fn})")
        results.append(asdict(result))

    save_path = str(RESULTS_DIR / "e1a_results.json")
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Saved to {save_path}")
    return results


def run_e1b():
    """E1b: Moderate signal — lower boost factor."""
    print("=== E1b: Moderate Signal ===")
    results = []
    for boost in [0.1, 0.2, 0.3, 0.5, 0.8]:
        seed_results = []
        for seed in range(5):
            config = SyntheticConfig(
                n_transactions=5000,
                n_items=200,
                p_base=0.03,
                planted_signals=[
                    PlantedSignal([1001, 1002], "E1", "Sale", 800, 1200, boost_factor=boost),
                    PlantedSignal([1003, 1004], "E2", "Holiday", 2000, 2400, boost_factor=boost),
                    PlantedSignal([1005, 1006], "E3", "Campaign", 3200, 3600, boost_factor=boost),  # noqa
                ],
                decoy_events=[
                    DecoyEvent("D1", "Decoy_1", 1500, 1700),
                    DecoyEvent("D2", "Decoy_2", 4000, 4200),
                ],
                seed=seed + 100,
            )
            out_dir = str(DATA_DIR / f"e1b_boost{boost}_seed{seed}")
            info = generate_synthetic(config, out_dir)

            attr_config = AttributionConfig(
                min_support_range=5,
                n_permutations=5000,
                alpha=0.20,
                correction_method="bh",
                global_correction=True,
                deduplicate_overlap=True,
                seed=seed,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=3, max_length=100,
                config=attr_config,
            )
            seed_results.append(asdict(result))

        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        avg_p = sum(r["precision"] for r in seed_results) / len(seed_results)
        avg_r = sum(r["recall"] for r in seed_results) / len(seed_results)
        print(f"  boost={boost}: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f}")
        results.append({"boost": boost, "seeds": seed_results})

    save_path = str(RESULTS_DIR / "e1b_results.json")
    with open(save_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Saved to {save_path}")
    return results


def run_e1c():
    """E1c: Overlapping events — events with overlapping time windows."""
    print("=== E1c: Overlapping Events ===")
    results = []
    for seed in range(5):
        config = SyntheticConfig(
            n_transactions=5000,
            n_items=200,
            p_base=0.03,
            planted_signals=[
                PlantedSignal([1001, 1002], "E1", "Sale", 1000, 1500, boost_factor=0.5),
                PlantedSignal([1003, 1004], "E2", "Holiday", 1200, 1700, boost_factor=0.5),
                PlantedSignal([1005, 1006], "E3", "Campaign", 3000, 3500, boost_factor=0.5),
            ],
            decoy_events=[
                DecoyEvent("D1", "Decoy_1", 1100, 1600),  # overlaps with E1 and E2
            ],
            seed=seed + 200,
        )
        out_dir = str(DATA_DIR / f"e1c_seed{seed}")
        info = generate_synthetic(config, out_dir)

        attr_config = AttributionConfig(
            min_support_range=5,
            n_permutations=5000,
            alpha=0.20,
            correction_method="bh",
            global_correction=True,
            deduplicate_overlap=True,
            seed=seed,
        )
        result = run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=100,
            config=attr_config,
        )
        print(f"  seed={seed}: P={result.precision:.2f} R={result.recall:.2f} "
              f"F1={result.f1:.2f} (TP={result.tp} FP={result.fp} FN={result.fn})")
        results.append(asdict(result))

    save_path = str(RESULTS_DIR / "e1c_results.json")
    with open(save_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Saved to {save_path}")
    return results


def run_e1d():
    """E1d: Varying number of planted signals and decoys."""
    print("=== E1d: Varying Counts ===")
    results = []
    for n_planted in [1, 3, 5]:
        for n_decoy in [0, 5, 10]:
            seed_results = []
            for seed in range(3):
                planted = []
                spacing = 5000 // (n_planted + 1)
                for i in range(n_planted):
                    start = spacing * (i + 1) - 200
                    end = start + 400
                    base = 1001 + i * 10
                    planted.append(PlantedSignal(
                        [base, base + 1], f"E{i+1}", f"Event_{i+1}",
                        max(0, start), min(4999, end), 0.5
                    ))

                decoys = []
                rng_d = __import__("random").Random(seed + 300)
                for i in range(n_decoy):
                    s = rng_d.randint(0, 4500)
                    decoys.append(DecoyEvent(f"D{i+1}", f"Decoy_{i+1}", s, s + 200))

                config = SyntheticConfig(
                    n_transactions=5000, n_items=200, p_base=0.03,
                    planted_signals=planted, decoy_events=decoys, seed=seed + 300,
                )
                out_dir = str(DATA_DIR / f"e1d_p{n_planted}_d{n_decoy}_seed{seed}")
                info = generate_synthetic(config, out_dir)

                attr_config = AttributionConfig(
                    min_support_range=5,
                    n_permutations=5000, alpha=0.20,
                    correction_method="bh", global_correction=True, deduplicate_overlap=True, seed=seed,
                )
                result = run_single_experiment(
                    info["txn_path"], info["events_path"], info["gt_path"],
                    window_size=50, min_support=3, max_length=100, config=attr_config,
                )
                seed_results.append(asdict(result))

            avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
            print(f"  planted={n_planted} decoy={n_decoy}: F1={avg_f1:.2f}")
            results.append({
                "n_planted": n_planted, "n_decoy": n_decoy, "seeds": seed_results
            })

    save_path = str(RESULTS_DIR / "e1d_results.json")
    with open(save_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Saved to {save_path}")
    return results


if __name__ == "__main__":
    run_e1a()
    print()
    run_e1b()
    print()
    run_e1c()
    print()
    run_e1d()
    print("\nE1 experiments complete.")
