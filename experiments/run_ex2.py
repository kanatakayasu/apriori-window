"""
EX2: Score Component Ablation — How do prox and mag contribute under realistic conditions?

Two designed scenarios where each component is essential:
  - Scenario A (prox required): Same pattern, two dense intervals — one near event (causal),
    one far from event (coincidental). Without prox, both get equal scores.
  - Scenario B (mag required): Two events affect the same pattern — one with large change,
    one with small change. Without mag, both get equal weight.

Ablation modes: Full (prox*mag), mag_only, prox_only
All 3 modes are tested on each scenario (2 × 3 = 6 conditions × 5 seeds).
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
    UnrelatedDensePattern,
    generate_synthetic,
)
from experiments.src.run_experiment import (
    AttributionConfig,
    run_single_experiment,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex2"
DATA_DIR = Path(__file__).resolve().parent / "data" / "ex2"

ABLATION_MODES = OrderedDict([
    ("Full (prox*mag)", None),
    ("No proximity (mag only)", "no_prox"),
    ("No magnitude (prox only)", "no_mag"),
])


def _make_scenario_a(seed=42):
    """Scenario A: prox is required.

    Pattern [5, 15] has two dense intervals:
      - Interval 1: near Event E1 (causal) — t=800-1200, event at 750-1250
      - Interval 2: far from any event (coincidental) — t=3000-3400

    The coincidental interval is generated as an UnrelatedDensePattern.
    Only the causal attribution (pattern→E1) is ground truth.
    """
    return SyntheticConfig(
        n_transactions=5000,
        n_items=200,
        p_base=0.03,
        planted_signals=[
            # Causal: pattern boosted during event window
            PlantedSignal([5, 15], "E1", "Sale", 750, 1250, boost_factor=0.4,
                          baseline_prob=0.03),
        ],
        unrelated_dense_patterns=[
            # Coincidental: same pattern boosted far from any event
            UnrelatedDensePattern([5, 15], 3000, 3400, boost_factor=0.4),
        ],
        decoy_events=[],
        seed=seed,
    )


def _make_scenario_b(seed=42):
    """Scenario B: mag is required.

    Pattern [5, 15] is affected by two events:
      - E1 (t=800-1200): large boost (0.5) → large magnitude change
      - E2 (t=2500-2900): small boost (0.1) → small magnitude change

    Both are technically causal, but mag helps rank E1 higher.
    Ground truth includes both, but we evaluate if mag_only can still
    distinguish the relative importance.
    """
    return SyntheticConfig(
        n_transactions=5000,
        n_items=200,
        p_base=0.03,
        planted_signals=[
            PlantedSignal([5, 15], "E1", "BigSale", 800, 1200, boost_factor=0.5,
                          baseline_prob=0.03),
            PlantedSignal([5, 15], "E2", "SmallPromo", 2500, 2900, boost_factor=0.1,
                          baseline_prob=0.03),
        ],
        unrelated_dense_patterns=[],
        decoy_events=[],
        seed=seed,
    )


SCENARIOS = {
    "A_prox_required": _make_scenario_a,
    "B_mag_required": _make_scenario_b,
}


def run_ex2():
    """Run EX2: Score component ablation with designed scenarios."""
    print("=" * 60)
    print("EX2: Score Component Ablation")
    print("=" * 60)

    all_results = {}

    for scenario_name, config_fn in SCENARIOS.items():
        print(f"\n{'='*60}")
        print(f"Scenario {scenario_name}")
        print(f"{'='*60}")

        scenario_results = {}

        for variant_name, ablation_mode in ABLATION_MODES.items():
            print(f"\n  --- {variant_name} (mode={ablation_mode}) ---")
            seed_results = []

            for seed in range(5):
                config = config_fn(seed)
                mode_label = ablation_mode or "full"
                out_dir = str(DATA_DIR / scenario_name / f"{mode_label}_seed{seed}")
                info = generate_synthetic(config, out_dir)

                attr_config = AttributionConfig(
                    min_support_range=5,
                    n_permutations=5000,
                    alpha=0.10,
                    correction_method="bh",
                    global_correction=True,
                    deduplicate_overlap=True,
                    seed=seed,
                    ablation_mode=ablation_mode,
                )
                result = run_single_experiment(
                    info["txn_path"], info["events_path"], info["gt_path"],
                    window_size=50, min_support=3, max_length=100,
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
            print(f"    Average: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f} FAR={avg_far:.2f}")

            scenario_results[variant_name] = {
                "ablation_mode": ablation_mode,
                "seeds": seed_results,
                "avg_precision": avg_p,
                "avg_recall": avg_r,
                "avg_f1": avg_f1,
                "avg_false_attribution_rate": avg_far,
            }

        all_results[scenario_name] = scenario_results

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "ex2_results.json")
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nEX2 results saved to {save_path}")

    # Print summary tables per scenario
    for scenario_name, scenario_results in all_results.items():
        print(f"\n{'='*70}")
        print(f"Scenario {scenario_name}")
        print(f"{'Variant':<30s} {'Precision':>10s} {'Recall':>8s} {'F1':>6s} {'FAR':>6s}")
        print("-" * 70)
        for name, data in scenario_results.items():
            print(f"{name:<30s} {data['avg_precision']:>10.2f} "
                  f"{data['avg_recall']:>8.2f} {data['avg_f1']:>6.2f} "
                  f"{data['avg_false_attribution_rate']:>6.2f}")
        print("=" * 70)

    return all_results


if __name__ == "__main__":
    run_ex2()
