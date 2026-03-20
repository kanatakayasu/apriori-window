"""
E3: Scalability — How does wall-clock time scale with dataset size and events?
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

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "e3"
DATA_DIR = Path(__file__).resolve().parent / "data" / "e3"


def sweep_n_transactions():
    """Sweep dataset size N."""
    print("--- Sweep: n_transactions ---")
    results = []
    for n in [1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000, 1000000]:
        event_dur = n // 5
        config = SyntheticConfig(
            n_transactions=n,
            n_items=200,
            p_base=0.03,
            planted_signals=[
                PlantedSignal([1001, 1002], "E1", "Sale",
                              n // 4 - event_dur // 2, n // 4 + event_dur // 2, 0.5),
                PlantedSignal([1003, 1004], "E2", "Holiday",
                              n // 2 - event_dur // 2, n // 2 + event_dur // 2, 0.5),
                PlantedSignal([1005, 1006], "E3", "Campaign",
                              3 * n // 4 - event_dur // 2, 3 * n // 4 + event_dur // 2, 0.5),
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
            correction_method="bh", global_correction=True, deduplicate_overlap=True, seed=42,
        )
        result = run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=2, config=attr_config,
        )
        print(f"  N={n}: total={result.time_total_ms:.0f}ms "
              f"(phase1={result.time_phase1_ms:.0f} "
              f"attr={result.time_attribution_ms:.0f}) "
              f"patterns={result.n_patterns} F1={result.f1:.2f}")
        results.append({
            "n_transactions": n,
            **asdict(result),
        })
    return results


def sweep_n_events():
    """Sweep number of events."""
    print("--- Sweep: n_events ---")
    results = []
    n = 5000
    for n_events in [1, 3, 5, 10, 20]:
        planted = []
        spacing = n // (n_events + 1)
        for i in range(n_events):
            start = spacing * (i + 1) - 100
            end = start + 200
            base = 1001 + i * 10
            planted.append(PlantedSignal(
                [base, base + 1], f"E{i+1}", f"Event_{i+1}",
                max(0, start), min(n - 1, end), 8.0
            ))

        config = SyntheticConfig(
            n_transactions=n, n_items=300, p_base=0.03,
            planted_signals=planted, decoy_events=[], seed=42,
        )
        out_dir = str(DATA_DIR / f"events{n_events}")
        info = generate_synthetic(config, out_dir)

        attr_config = AttributionConfig(
            min_support_range=5,
            n_permutations=200, alpha=0.20,
            correction_method="bh", global_correction=True, deduplicate_overlap=True, seed=42,
        )
        result = run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=2, config=attr_config,
        )
        print(f"  n_events={n_events}: total={result.time_total_ms:.0f}ms "
              f"attr={result.time_attribution_ms:.0f}ms "
              f"F1={result.f1:.2f}")
        results.append({"n_events": n_events, **asdict(result)})
    return results


def sweep_n_permutations():
    """Sweep permutation count for timing."""
    print("--- Sweep: n_permutations (timing) ---")
    results = []
    config = SyntheticConfig(
        n_transactions=5000, n_items=200, p_base=0.03,
        planted_signals=[
            PlantedSignal([1001, 1002], "E1", "Sale", 800, 1200, 0.5),
            PlantedSignal([1003, 1004], "E2", "Holiday", 2000, 2400, 0.5),
        ],
        decoy_events=[DecoyEvent("D1", "Decoy_1", 3500, 3700)],
        seed=42,
    )
    out_dir = str(DATA_DIR / "perm_timing")
    info = generate_synthetic(config, out_dir)

    for n_perm in [50, 100, 200, 500, 1000, 2000]:
        attr_config = AttributionConfig(
            min_support_range=5,
            n_permutations=n_perm, alpha=0.20,
            correction_method="bh", global_correction=True, deduplicate_overlap=True, seed=42,
        )
        result = run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=2, config=attr_config,
        )
        print(f"  n_perm={n_perm}: attr={result.time_attribution_ms:.0f}ms "
              f"total={result.time_total_ms:.0f}ms")
        results.append({"n_permutations": n_perm, **asdict(result)})
    return results


if __name__ == "__main__":
    all_results = {}
    all_results["n_transactions"] = sweep_n_transactions()
    print()
    all_results["n_events"] = sweep_n_events()
    print()
    all_results["n_permutations"] = sweep_n_permutations()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(str(RESULTS_DIR / "e3_all_results.json"), "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nE3 results saved.")
