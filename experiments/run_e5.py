"""
E5: Extended Real Data Evaluation — Does the pipeline generalise across diverse real datasets?

Tests Event Attribution Pipeline on multiple real-world datasets (onlineretail,
kosarak, chicago) with injected events at varying boost strengths, strengthening
the real-data story beyond the E4 retail/T10I4D100K pair.
"""
import json
import sys
import tempfile
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

# ---------------------------------------------------------------------------
# New-item injection (simulates "new product campaign")
# ---------------------------------------------------------------------------

def inject_new_items_into_real_data(
    input_path: str,
    out_dir: str,
    n_patterns: int = 4,
    event_duration: int = 2000,
    boost_factor: float = 0.5,
    n_decoy: int = 5,
    seed: int = 42,
) -> dict:
    """Inject new items (IDs beyond max existing) into a real dataset.

    Simulates a 'new product launch' campaign: item pairs that only appear
    during the event window, avoiding confounding with existing item dynamics.
    """
    import random as _random
    from pathlib import Path as _Path

    rng = _random.Random(seed)
    out_path = _Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    with open(input_path) as f:
        lines = f.readlines()

    n_transactions = len(lines)

    # Find max item ID
    max_item = 0
    for line in lines:
        for tok in line.strip().split():
            try:
                v = int(tok)
                if v > max_item:
                    max_item = v
            except ValueError:
                pass
    base_new = max_item + 100  # Start new items well above existing

    spacing = n_transactions // (n_patterns + 1)
    planted = []
    for i in range(n_patterns):
        start = spacing * (i + 1) - event_duration // 2
        end = start + event_duration
        start = max(0, start)
        end = min(n_transactions - 1, end)
        item_a = base_new + i * 10
        item_b = base_new + i * 10 + 1
        planted.append({
            "pattern": [item_a, item_b],
            "event_id": f"E{i+1}",
            "event_name": f"Campaign_{i+1}",
            "start": start,
            "end": end,
            "boost_factor": boost_factor,
        })

    # Modify transactions
    new_lines = []
    for t, line in enumerate(lines):
        line = line.strip()
        if not line:
            new_lines.append("")
            continue
        items = [int(x) for x in line.split()]
        for sig in planted:
            if sig["start"] <= t <= sig["end"]:
                if rng.random() < min(1.0, sig["boost_factor"]):
                    items.extend(sig["pattern"])
        new_lines.append(" ".join(str(x) for x in sorted(set(items))))

    txn_path = out_path / "transactions.txt"
    with open(txn_path, "w") as f:
        for line in new_lines:
            f.write(line + "\n")

    # Events
    events = []
    for sig in planted:
        events.append({
            "event_id": sig["event_id"],
            "name": sig["event_name"],
            "start": sig["start"],
            "end": sig["end"],
        })
    for i in range(n_decoy):
        s = rng.randint(0, n_transactions - event_duration - 1)
        events.append({
            "event_id": f"D{i+1}",
            "name": f"Decoy_{i+1}",
            "start": s,
            "end": s + event_duration,
        })

    events_path = out_path / "events.json"
    with open(events_path, "w") as f:
        import json as _json
        _json.dump(events, f, indent=2)

    ground_truth = [{"pattern": sorted(sig["pattern"]), "event_id": sig["event_id"]}
                    for sig in planted]
    gt_path = out_path / "ground_truth.json"
    with open(gt_path, "w") as f:
        import json as _json
        _json.dump(ground_truth, f, indent=2)

    return {
        "txn_path": str(txn_path),
        "events_path": str(events_path),
        "gt_path": str(gt_path),
        "n_transactions": n_transactions,
        "n_planted": n_patterns,
        "n_decoy": n_decoy,
        "patterns": [sig["pattern"] for sig in planted],
    }

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "e5"
DATA_DIR = Path(__file__).resolve().parent / "data" / "e5"
DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


def _scan_top_items(dataset_path: str, n: int = 20) -> list:
    """Scan a dataset and return the *n* most frequent item IDs."""
    item_counts: Counter = Counter()
    with open(dataset_path) as f:
        for line in f:
            items = line.strip().split()
            for item in items:
                try:
                    item_counts[int(item)] += 1
                except ValueError:
                    continue
    return [item for item, _ in item_counts.most_common(n)]


def _select_non_cooccurring_items(dataset_path: str, n_pairs: int = 4) -> list:
    """Select mid-frequency items that rarely co-occur — simulates realistic promotions.

    Strategy: pick items from rank 50-150 by frequency, then greedily select
    pairs that have low co-occurrence in the original data.
    """
    import itertools

    item_counts: Counter = Counter()
    with open(dataset_path) as f:
        lines = f.readlines()

    for line in lines:
        items = line.strip().split()
        for item in items:
            try:
                item_counts[int(item)] += 1
            except ValueError:
                continue

    # Pick items from rank 50-150 (medium frequency, not too rare, not too common)
    ranked = [item for item, _ in item_counts.most_common(200)]
    if len(ranked) < 100:
        # Small dataset: use rank 10-50
        candidates = ranked[10:50] if len(ranked) > 50 else ranked[5:]
    else:
        candidates = ranked[50:150]

    # Count co-occurrences among candidates
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

    # Greedily select pairs with lowest co-occurrence
    used = set()
    patterns = []
    # Sort candidates by count (prefer items that appear enough to be detectable)
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


def _truncate_dataset(src_path: str, max_lines: int, out_path: str) -> str:
    """Write the first *max_lines* lines of *src_path* to *out_path*."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(src_path) as fin, open(out_path, "w") as fout:
        for i, line in enumerate(fin):
            if i >= max_lines:
                break
            fout.write(line)
    return out_path


def _make_attr_config() -> AttributionConfig:
    """Shared AttributionConfig for all E5 sub-experiments."""
    return AttributionConfig(
        min_support_range=5,
        n_permutations=5000,
        alpha=0.20,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=42,
    )


def run_dataset(
    name: str,
    dataset_path: str,
    patterns: list,
    boost: float,
    window_size: int,
    min_support: int,
    event_duration: int = 500,
    n_decoy: int = 5,
):
    """Run E5 on a single real dataset with a given boost factor."""
    print(f"--- {name} (boost={boost}) ---")
    out_dir = str(DATA_DIR / f"{name}_boost{boost}")
    info = inject_events_into_real_data(
        dataset_path,
        out_dir,
        patterns_to_boost=patterns,
        event_duration=event_duration,
        boost_factor=boost,
        n_decoy=n_decoy,
        seed=42,
    )

    attr_config = _make_attr_config()
    result = run_single_experiment(
        info["txn_path"],
        info["events_path"],
        info["gt_path"],
        window_size=window_size,
        min_support=min_support,
        max_length=2,
        config=attr_config,
    )
    print(f"  P={result.precision:.2f} R={result.recall:.2f} F1={result.f1:.2f}")
    print(f"  TP={result.tp} FP={result.fp} FN={result.fn}")
    print(f"  patterns={result.n_patterns} time={result.time_total_ms:.0f}ms")
    return asdict(result)


# ---------------------------------------------------------------------------
# Per-dataset runners
# ---------------------------------------------------------------------------

def run_dataset_new_items(
    name: str,
    dataset_path: str,
    boost: float,
    window_size: int,
    min_support: int,
    n_patterns: int = 4,
    event_duration: int = 2000,
    n_decoy: int = 5,
):
    """Run E5 with new-item injection (campaign simulation)."""
    print(f"--- {name} (boost={boost}, new items) ---")
    out_dir = str(DATA_DIR / f"{name}_new_boost{boost}")
    info = inject_new_items_into_real_data(
        dataset_path, out_dir,
        n_patterns=n_patterns,
        event_duration=event_duration,
        boost_factor=boost,
        n_decoy=n_decoy,
        seed=42,
    )
    print(f"  Injected patterns: {info['patterns']}")

    attr_config = _make_attr_config()
    result = run_single_experiment(
        info["txn_path"], info["events_path"], info["gt_path"],
        window_size=window_size, min_support=min_support, max_length=2,
        config=attr_config,
    )
    print(f"  P={result.precision:.2f} R={result.recall:.2f} F1={result.f1:.2f}")
    print(f"  TP={result.tp} FP={result.fp} FN={result.fn}")
    print(f"  patterns={result.n_patterns} time={result.time_total_ms:.0f}ms")
    return asdict(result)


def _run_onlineretail(all_results: dict, boosts: list | None = None):
    """onlineretail — ~541K transactions, large e-commerce dataset."""
    dataset_path = str(DATASET_DIR / "original" / "onlineretail.txt")
    if not Path(dataset_path).exists():
        print(f"WARNING: Skipping onlineretail — {dataset_path} not found")
        return

    if boosts is None:
        boosts = [0.3, 0.5, 0.8, 1.0]

    results = []
    for boost in boosts:
        r = run_dataset_new_items(
            "onlineretail", dataset_path, boost,
            window_size=200, min_support=10,
            n_patterns=4, event_duration=2000, n_decoy=5,
        )
        results.append({"boost": boost, **r})
    all_results["onlineretail"] = results


def _run_kosarak(all_results: dict):
    """kosarak — web clickstream dataset."""
    dataset_path = str(DATASET_DIR / "original" / "kosarak.txt")
    if not Path(dataset_path).exists():
        print(f"WARNING: Skipping kosarak — {dataset_path} not found")
        return

    results = []
    for boost in [0.3, 0.5, 1.0]:
        r = run_dataset_new_items(
            "kosarak", dataset_path, boost,
            window_size=500, min_support=20,
            n_patterns=3, event_duration=5000, n_decoy=5,
        )
        results.append({"boost": boost, **r})
    all_results["kosarak"] = results


def _run_chicago(all_results: dict):
    """chicago — ~2.6M transactions (truncated to 500K for practicality)."""
    dataset_path = str(DATASET_DIR / "original" / "chicago.txt")
    if not Path(dataset_path).exists():
        print(f"WARNING: Skipping chicago — {dataset_path} not found")
        return

    print("\nTruncating chicago to 500K lines...")
    truncated_path = str(DATA_DIR / "chicago_500k.txt")
    _truncate_dataset(dataset_path, max_lines=500_000, out_path=truncated_path)

    results = []
    for boost in [0.3, 0.5, 1.0]:
        r = run_dataset_new_items(
            "chicago", truncated_path, boost,
            window_size=500, min_support=20,
            n_patterns=3, event_duration=5000, n_decoy=5,
        )
        results.append({"boost": boost, **r})
    all_results["chicago"] = results


# ---------------------------------------------------------------------------
# Top-level entry points
# ---------------------------------------------------------------------------

def run_e5():
    """Full E5 run: onlineretail + kosarak + chicago."""
    print("=" * 60)
    print("E5: Extended Real Data Evaluation")
    print("=" * 60)

    all_results: dict = {}

    _run_onlineretail(all_results)
    _run_kosarak(all_results)
    _run_chicago(all_results)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "e5_all_results.json"
    with open(str(out_path), "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nE5 results saved to {out_path}")


def run_e5_quick():
    """Quick variant: onlineretail only, boost=5.0."""
    print("=" * 60)
    print("E5 Quick: onlineretail only (boost=5.0)")
    print("=" * 60)

    all_results: dict = {}
    _run_onlineretail(all_results, boosts=[0.5])

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "e5_all_results.json"
    with open(str(out_path), "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nE5 quick results saved to {out_path}")


if __name__ == "__main__":
    if "--quick" in sys.argv:
        run_e5_quick()
    else:
        run_e5()
