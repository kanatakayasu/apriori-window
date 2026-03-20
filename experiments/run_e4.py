"""
E4: Real Data with Injected Events — Does the pipeline work on real-world data?

Uses T10I4D100K and retail datasets with synthetic events injected.
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import inject_events_into_real_data
from experiments.src.run_experiment import (
    AttributionConfig,
    run_single_experiment,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "e4"
DATA_DIR = Path(__file__).resolve().parent / "data" / "e4"
DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


def run_dataset(name: str, dataset_path: str, patterns: list, boost: float,
                window_size: int, min_support: int):
    """Run E4 on a single real dataset."""
    print(f"--- {name} (boost={boost}) ---")
    out_dir = str(DATA_DIR / f"{name}_boost{boost}")
    info = inject_events_into_real_data(
        dataset_path, out_dir,
        patterns_to_boost=patterns,
        event_duration=500,
        boost_factor=boost,
        n_decoy=3,
        seed=42,
    )

    attr_config = AttributionConfig(
        min_support_range=5,
        n_permutations=5000,
        alpha=0.20,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=42,
    )
    result = run_single_experiment(
        info["txn_path"], info["events_path"], info["gt_path"],
        window_size=window_size, min_support=min_support, max_length=2,
        config=attr_config,
    )
    print(f"  P={result.precision:.2f} R={result.recall:.2f} F1={result.f1:.2f}")
    print(f"  TP={result.tp} FP={result.fp} FN={result.fn}")
    print(f"  patterns={result.n_patterns} time={result.time_total_ms:.0f}ms")
    return asdict(result)


def run_e4():
    all_results = {}

    # T10I4D100K — sparse synthetic, 100K transactions
    # Use common small item IDs that are likely frequent
    t10_path = str(DATASET_DIR / "T10I4D100K.txt")
    if Path(t10_path).exists():
        # First scan to find some frequent items
        print("Scanning T10I4D100K for frequent items...")
        from collections import Counter
        item_counts = Counter()
        with open(t10_path) as f:
            for line in f:
                items = line.strip().split()
                for item in items:
                    item_counts[int(item)] += 1
        top_items = [item for item, _ in item_counts.most_common(20)]
        patterns = [[top_items[0], top_items[1]],
                     [top_items[2], top_items[3]],
                     [top_items[4], top_items[5]]]
        print(f"  Using patterns: {patterns}")

        t10_results = []
        for boost in [3.0, 5.0, 10.0]:
            r = run_dataset("T10I4D100K", t10_path, patterns, boost,
                            window_size=100, min_support=5)
            t10_results.append({"boost": boost, **r})
        all_results["T10I4D100K"] = t10_results
    else:
        print(f"Skipping T10I4D100K: {t10_path} not found")

    # retail.txt — real Belgian retail, 88K transactions
    retail_path = str(DATASET_DIR / "original" / "retail.txt")
    if Path(retail_path).exists():
        print("\nScanning retail for frequent items...")
        from collections import Counter
        item_counts = Counter()
        with open(retail_path) as f:
            for line in f:
                items = line.strip().split()
                for item in items:
                    item_counts[int(item)] += 1
        top_items = [item for item, _ in item_counts.most_common(20)]
        patterns = [[top_items[0], top_items[1]],
                     [top_items[2], top_items[3]]]
        print(f"  Using patterns: {patterns}")

        retail_results = []
        for boost in [3.0, 5.0, 10.0]:
            r = run_dataset("retail", retail_path, patterns, boost,
                            window_size=100, min_support=5)
            retail_results.append({"boost": boost, **r})
        all_results["retail"] = retail_results
    else:
        print(f"Skipping retail: {retail_path} not found")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(str(RESULTS_DIR / "e4_all_results.json"), "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nE4 results saved.")


if __name__ == "__main__":
    run_e4()
