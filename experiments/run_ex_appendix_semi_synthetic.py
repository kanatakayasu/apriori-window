"""
Appendix Experiment: Semi-synthetic validation (vocabulary-internal injection on real datasets).

Injects mid-frequency item pair boosts into T10I4D100K, retail, onlineretail
and evaluates P/R/F1. Supplements the main EX5 (Dunnhumby) analysis.
"""
import itertools
import json
import sys
from collections import Counter
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

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "appendix"
DATA_DIR = Path(__file__).resolve().parent / "data" / "appendix_semi_synthetic"
DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


def _select_mid_frequency_pairs(dataset_path: str, n_pairs: int = 3) -> list:
    """Select mid-frequency item pairs for vocabulary-internal injection."""
    item_counts: Counter = Counter()
    with open(dataset_path) as f:
        lines = f.readlines()

    for line in lines:
        for tok in line.strip().split():
            try:
                item_counts[int(tok)] += 1
            except ValueError:
                continue

    ranked = [item for item, _ in item_counts.most_common(200)]
    if len(ranked) < 60:
        candidates = ranked[5:] if len(ranked) > 10 else ranked
    else:
        candidates = ranked[50:150]

    cooccur: Counter = Counter()
    candidate_set = set(candidates)
    for line in lines:
        items = set()
        for x in line.strip().split():
            try:
                v = int(x)
                if v in candidate_set:
                    items.add(v)
            except ValueError:
                continue
        for a, b in itertools.combinations(sorted(items), 2):
            cooccur[(a, b)] += 1

    used = set()
    patterns = []
    candidates_sorted = sorted(candidates, key=lambda x: -item_counts[x])
    for a in candidates_sorted:
        if a in used:
            continue
        best_b = None
        best_cooc = float('inf')
        for b in candidates_sorted:
            if b == a or b in used:
                continue
            cooc = cooccur.get((min(a, b), max(a, b)), 0)
            if cooc < best_cooc:
                best_cooc = cooc
                best_b = b
        if best_b is not None:
            used.add(a)
            used.add(best_b)
            patterns.append([a, best_b])
            if len(patterns) >= n_pairs:
                break
    return patterns


def _make_attr_config() -> AttributionConfig:
    return AttributionConfig(
        min_support_range=5,
        n_permutations=5000,
        alpha=0.20,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=42,
    )


def run_dataset(name: str, dataset_path: str, patterns: list,
                boost: float, window_size: int, min_support: int,
                event_duration: int = 500):
    """Run semi-synthetic injection on a single dataset."""
    print(f"  --- {name} (boost={boost}) ---")
    out_dir = str(DATA_DIR / f"{name}_boost{boost}")
    info = inject_events_into_real_data(
        dataset_path, out_dir,
        patterns_to_boost=patterns,
        event_duration=event_duration,
        boost_factor=boost,
        n_decoy=3,
        seed=42,
    )

    result = run_single_experiment(
        info["txn_path"], info["events_path"], info["gt_path"],
        window_size=window_size, min_support=min_support, max_length=100,
        config=_make_attr_config(),
    )
    print(f"    P={result.precision:.2f} R={result.recall:.2f} F1={result.f1:.2f} "
          f"(TP={result.tp} FP={result.fp} FN={result.fn}) "
          f"time={result.time_total_ms:.0f}ms")
    return asdict(result)


def run_all():
    print("=" * 60)
    print("Appendix: Semi-synthetic validation (vocabulary-internal injection)")
    print("=" * 60)

    all_results = {}

    for name, path_rel, ws, ms, ed in [
        ("T10I4D100K", "T10I4D100K.txt", 100, 5, 500),
        ("retail", "original/retail.txt", 100, 5, 500),
        ("onlineretail", "original/onlineretail.txt", 200, 10, 2000),
    ]:
        dataset_path = str(DATASET_DIR / path_rel)
        if not Path(dataset_path).exists():
            print(f"Skipping {name}: not found")
            continue

        print(f"\n{name}:")
        patterns = _select_mid_frequency_pairs(dataset_path, n_pairs=3)
        print(f"  Selected patterns: {patterns}")

        results = []
        for boost in [3.0, 5.0, 10.0]:
            r = run_dataset(name, dataset_path, patterns, boost, ws, ms, ed)
            results.append({"boost": boost, **r})
        all_results[name] = results

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "semi_synthetic_results.json")
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {save_path}")


if __name__ == "__main__":
    run_all()
