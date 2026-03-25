"""
Score Component Ablation Experiment.

Evaluates the contribution of each component of the attribution score
A = prox * dir * mag by testing different combinations.

Ablation variants:
  - Full:      prox * dir * mag (baseline)
  - No dir:    prox * mag
  - No prox:   dir * mag
  - No mag:    prox * dir
  - Mag only:  mag
  - Prox only: prox
"""
import json
import sys
from collections import OrderedDict
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
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ablation_score"
DATA_DIR = Path(__file__).resolve().parent / "data" / "ablation_score"

# Ablation variants: label -> ablation_mode value
VARIANTS = OrderedDict([
    ("Full (prox*mag)", None),
    ("No proximity (mag only)", "no_prox"),
    ("No magnitude (prox only)", "no_mag"),
])


def run_ablation():
    """Run score component ablation on E1a conditions."""
    print("=== Score Component Ablation ===")
    print(f"Conditions: 5 seeds, beta=0.5, 3 planted, 2 decoys, N=5000")
    print()

    all_results = {}

    for variant_name, ablation_mode in VARIANTS.items():
        print(f"--- {variant_name} (mode={ablation_mode}) ---")
        seed_results = []

        for seed in range(5):
            # Generate synthetic data (same as E1a)
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
            mode_label = ablation_mode or "full"
            out_dir = str(DATA_DIR / f"{mode_label}_seed{seed}")
            info = generate_synthetic(config, out_dir)

            attr_config = AttributionConfig(
                min_support_range=5,
                n_permutations=5000,
                alpha=0.20,
                correction_method="bh",
                global_correction=True,
                deduplicate_overlap=True,
                seed=seed,
                ablation_mode=ablation_mode,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=3, max_length=2,
                config=attr_config,
            )
            print(f"  seed={seed}: P={result.precision:.2f} R={result.recall:.2f} "
                  f"F1={result.f1:.2f} (TP={result.tp} FP={result.fp} FN={result.fn})")
            seed_results.append(asdict(result))

        # Compute averages
        avg_p = sum(r["precision"] for r in seed_results) / len(seed_results)
        avg_r = sum(r["recall"] for r in seed_results) / len(seed_results)
        avg_f1 = sum(r["f1"] for r in seed_results) / len(seed_results)
        print(f"  Average: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f}")
        print()

        all_results[variant_name] = {
            "ablation_mode": ablation_mode,
            "seeds": seed_results,
            "avg_precision": avg_p,
            "avg_recall": avg_r,
            "avg_f1": avg_f1,
        }

    # Save results
    save_path = str(RESULTS_DIR / "ablation_score_results.json")
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Saved to {save_path}")

    # Print summary table
    print()
    print("=" * 65)
    print(f"{'Variant':<30s} {'Precision':>10s} {'Recall':>8s} {'F1':>6s}")
    print("-" * 65)
    for name, data in all_results.items():
        print(f"{name:<30s} {data['avg_precision']:>10.2f} {data['avg_recall']:>8.2f} {data['avg_f1']:>6.2f}")
    print("=" * 65)

    return all_results


if __name__ == "__main__":
    run_ablation()
