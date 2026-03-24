"""
EX4: Scalability — How does wall-clock time scale with dataset size and event count?

Sweeps:
  - N (dataset size): {1K, 5K, 10K, 50K, 100K, 500K, 1M}
  - |E| (event count): {1, 3, 5, 10, 20}

Presentation: log-log plot + summary table.
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
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex4"
DATA_DIR = Path(__file__).resolve().parent / "data" / "ex4"


def sweep_n_transactions():
    """Sweep dataset size N."""
    print("--- Sweep: N (dataset size) ---")
    results = []
    for n in [1000, 5000, 10000, 50000, 100000, 500000, 1000000]:
        event_dur = max(200, n // 5)
        # Use vocabulary-internal items with baseline presence
        config = SyntheticConfig(
            n_transactions=n,
            n_items=200,
            p_base=0.03,
            planted_signals=[
                PlantedSignal([5, 15], "E1", "Sale",
                              n // 4 - event_dur // 2, n // 4 + event_dur // 2,
                              boost_factor=0.4, baseline_prob=0.03),
                PlantedSignal([25, 35], "E2", "Holiday",
                              n // 2 - event_dur // 2, n // 2 + event_dur // 2,
                              boost_factor=0.4, baseline_prob=0.03),
                PlantedSignal([45, 55], "E3", "Campaign",
                              3 * n // 4 - event_dur // 2, 3 * n // 4 + event_dur // 2,
                              boost_factor=0.4, baseline_prob=0.03),
            ],
            decoy_events=[
                DecoyEvent("D1", "Decoy_1", n // 3, n // 3 + event_dur),
            ],
            seed=42,
        )
        out_dir = str(DATA_DIR / f"n{n}")
        info = generate_synthetic(config, out_dir)

        attr_config = AttributionConfig(
            min_support_range=5,
            n_permutations=200, alpha=0.20,
            correction_method="bh", global_correction=True,
            deduplicate_overlap=True, seed=42,
        )
        result = run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=2, config=attr_config,
        )
        print(f"  N={n:>8,d}: total={result.time_total_ms:>8.0f}ms "
              f"(phase1={result.time_phase1_ms:.0f} "
              f"attr={result.time_attribution_ms:.0f}) "
              f"patterns={result.n_patterns} F1={result.f1:.2f}")
        results.append({"n_transactions": n, **asdict(result)})
    return results


def sweep_n_events():
    """Sweep number of events |E|."""
    print("--- Sweep: |E| (event count) ---")
    results = []
    n = 5000
    for n_events in [1, 3, 5, 10, 20]:
        planted = []
        spacing = n // (n_events + 1)
        for i in range(n_events):
            start = spacing * (i + 1) - 100
            end = start + 200
            # Use vocabulary-internal items
            item_a = 5 + i * 10
            item_b = item_a + 5
            # Ensure items stay within base vocabulary
            if item_b > 200:
                item_a = (i % 20) * 10 + 5
                item_b = item_a + 5
            planted.append(PlantedSignal(
                [item_a, item_b], f"E{i+1}", f"Event_{i+1}",
                max(0, start), min(n - 1, end),
                boost_factor=0.4, baseline_prob=0.03,
            ))

        config = SyntheticConfig(
            n_transactions=n, n_items=200, p_base=0.03,
            planted_signals=planted, decoy_events=[], seed=42,
        )
        out_dir = str(DATA_DIR / f"events{n_events}")
        info = generate_synthetic(config, out_dir)

        attr_config = AttributionConfig(
            min_support_range=5,
            n_permutations=200, alpha=0.20,
            correction_method="bh", global_correction=True,
            deduplicate_overlap=True, seed=42,
        )
        result = run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=2, config=attr_config,
        )
        print(f"  |E|={n_events:>2d}: total={result.time_total_ms:>6.0f}ms "
              f"attr={result.time_attribution_ms:.0f}ms F1={result.f1:.2f}")
        results.append({"n_events": n_events, **asdict(result)})
    return results


if __name__ == "__main__":
    all_results = {}
    all_results["n_transactions"] = sweep_n_transactions()
    print()
    all_results["n_events"] = sweep_n_events()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(str(RESULTS_DIR / "ex4_all_results.json"), "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nEX4 results saved.")
