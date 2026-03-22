#!/usr/bin/env python3
"""
Baseline comparison experiment — final version.

Runs 6 configurations on synthetic (E1a) and real (T10I4D100K) data.
CUSUM on T10I4D100K uses 200 permutations due to computational cost.
"""
import json
import sys
import time
import random as _random
from collections import Counter
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
sys.path.insert(0, str(Path(_root) / "apriori_window_original" / "python"))
sys.path.insert(0, str(Path(_root) / "apriori_window_suite" / "python"))

from apriori_window import (
    compute_item_timestamps_map,
    find_dense_itemsets,
    read_text_file_as_2d_vec_of_integers,
)
from event_attribution import (
    AttributionConfig,
    compute_support_series_all,
    read_events,
    run_attribution_pipeline,
    run_attribution_pipeline_v2,
)
from experiments.src.evaluate import evaluate_with_event_name_mapping
from experiments.src.gen_synthetic import (
    DecoyEvent, PlantedSignal, SyntheticConfig,
    inject_events_into_real_data, generate_synthetic,
)


def run_one_config(name, config, frequents, item_transaction_map, transactions,
                   events, window_size, min_support, support_series_map_fn,
                   gt_path, events_path):
    """Run a single config and return result dict."""
    print(f"  Running [{name}]...", end=" ", flush=True)
    t0 = time.perf_counter()

    if config.change_method == "cusum":
        ssm = support_series_map_fn()
        sig_results = run_attribution_pipeline(
            frequents, ssm, events, window_size, min_support, config)
    else:
        sig_results = run_attribution_pipeline_v2(
            frequents, item_transaction_map, events,
            window_size, min_support, len(transactions), config)

    elapsed = (time.perf_counter() - t0) * 1000
    ev = evaluate_with_event_name_mapping(sig_results, gt_path, events_path)

    entry = {
        "method": name,
        "precision": round(ev.precision, 4),
        "recall": round(ev.recall, 4),
        "f1": round(ev.f1, 4),
        "tp": ev.tp, "fp": ev.fp, "fn": ev.fn,
        "n_significant": len(sig_results),
        "time_ms": round(elapsed, 1),
        "n_permutations": config.n_permutations,
    }
    print(f"P={ev.precision:.3f} R={ev.recall:.3f} F1={ev.f1:.3f} "
          f"TP={ev.tp} FP={ev.fp} FN={ev.fn} ({elapsed:.0f}ms)")
    return entry


def make_config_list(n_perm, cusum_n_perm=None):
    """Build the 6 configs. CUSUM can have separate n_permutations."""
    if cusum_n_perm is None:
        cusum_n_perm = n_perm
    base = dict(alpha=0.20, global_correction=True, seed=0)
    return [
        ("Full pipeline", AttributionConfig(
            min_support_range=5, correction_method="bh",
            deduplicate_overlap=True, n_permutations=n_perm, **base)),
        ("No dedup", AttributionConfig(
            min_support_range=5, correction_method="bh",
            deduplicate_overlap=False, n_permutations=n_perm, **base)),
        ("Bonferroni", AttributionConfig(
            min_support_range=5, correction_method="bonferroni",
            deduplicate_overlap=True, n_permutations=n_perm, **base)),
        ("No amp filter", AttributionConfig(
            min_support_range=0, correction_method="bh",
            deduplicate_overlap=True, n_permutations=n_perm, **base)),
        ("CUSUM", AttributionConfig(
            min_support_range=5, correction_method="bh",
            deduplicate_overlap=True, change_method="cusum",
            n_permutations=cusum_n_perm, **base)),
        ("Naive", AttributionConfig(
            min_support_range=0, correction_method="bonferroni",
            deduplicate_overlap=False, n_permutations=n_perm, **base)),
    ]


def run_dataset(txn_path, events_path, gt_path, window_size, min_support,
                max_length, label, n_perm=5000, cusum_n_perm=None):
    print(f"\n{'='*60}")
    print(f"  Dataset: {label}")
    print(f"{'='*60}")

    t0 = time.perf_counter()
    transactions = read_text_file_as_2d_vec_of_integers(txn_path)
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)
    t1 = time.perf_counter()

    n_patterns = sum(1 for k in frequents if len(k) > 1)
    print(f"  Phase 1: {len(transactions)} txns, {n_patterns} patterns (len>1), {(t1-t0)*1000:.0f} ms")

    events = read_events(events_path)
    _cache = {}

    def get_ssm():
        if "ssm" not in _cache:
            print("    Computing support series for CUSUM...", flush=True)
            ts = time.perf_counter()
            _cache["ssm"] = compute_support_series_all(
                item_transaction_map, frequents, transactions, window_size)
            print(f"    Done in {(time.perf_counter()-ts)*1000:.0f} ms")
        return _cache["ssm"]

    configs = make_config_list(n_perm, cusum_n_perm)
    results = []
    for name, config in configs:
        entry = run_one_config(
            name, config, frequents, item_transaction_map, transactions,
            events, window_size, min_support, get_ssm, gt_path, events_path)
        results.append(entry)

    return results


def print_table(label, results):
    print(f"\n{'='*85}")
    print(f"  {label}")
    print(f"{'='*85}")
    h = f"{'Method':20s} {'Prec':>6s} {'Rec':>6s} {'F1':>6s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'#Sig':>5s} {'nPerm':>6s} {'Time':>8s}"
    print(h)
    print("-" * len(h))
    for r in results:
        print(f"{r['method']:20s} {r['precision']:6.3f} {r['recall']:6.3f} {r['f1']:6.3f} "
              f"{r['tp']:4d} {r['fp']:4d} {r['fn']:4d} {r['n_significant']:5d} "
              f"{r['n_permutations']:6d} {r['time_ms']:7.0f}ms")


def main():
    root = Path(__file__).resolve().parent.parent
    all_results = {}

    # ── E1a: Synthetic ──
    print("\n>>> Generating synthetic data (E1a)...")
    syn_dir = str(root / "experiments" / "data" / "comparison_baseline")
    rng = _random.Random(0)
    n_txn, n_planted, n_decoy, boost, dur = 5000, 3, 2, 0.5, 200
    spacing = n_txn // (n_planted + 1)
    planted = []
    for i in range(n_planted):
        s = spacing * (i + 1) - dur // 2
        e = s + dur
        s, e = max(0, s), min(n_txn - 1, e)
        b = 10 + i * 10
        planted.append(PlantedSignal(
            pattern=[b, b+1], event_id=f"E{i+1}", event_name=f"Event_{i+1}",
            event_start=s, event_end=e, boost_factor=boost))
    decoys = []
    for i in range(n_decoy):
        ds = rng.randint(0, n_txn - dur - 1)
        decoys.append(DecoyEvent(
            event_id=f"D{i+1}", event_name=f"Decoy_{i+1}", start=ds, end=ds+dur))
    info = generate_synthetic(
        SyntheticConfig(n_transactions=n_txn, planted_signals=planted,
                        decoy_events=decoys, seed=0), syn_dir)
    print(f"    {info['n_transactions']} txns, {info['n_planted']} planted, {info['n_decoy']} decoy")

    all_results["synthetic_e1a"] = run_dataset(
        info["txn_path"], info["events_path"], info["gt_path"],
        50, 3, 2, "E1a Synthetic (boost=0.5, N=5000)", n_perm=5000)

    # ── T10I4D100K ──
    print("\n>>> Preparing T10I4D100K data (E4)...")
    t10_in = str(root / "dataset" / "T10I4D100K.txt")
    t10_dir = str(root / "experiments" / "data" / "comparison_t10")
    ic = Counter()
    with open(t10_in) as f:
        for line in f:
            for tok in line.strip().split():
                if tok:
                    ic[int(tok)] += 1
    top = [i for i, _ in ic.most_common(20)]
    pats = [[top[0], top[1]], [top[2], top[3]], [top[4], top[5]]]
    print(f"    Patterns: {pats}")
    info2 = inject_events_into_real_data(
        t10_in, t10_dir, pats, event_duration=500, boost_factor=5.0, n_decoy=3, seed=42)
    print(f"    {info2['n_transactions']} txns, {info2['n_planted']} planted, {info2['n_decoy']} decoy")

    # 1000 perm for most, 200 for CUSUM (too many change points)
    all_results["T10I4D100K"] = run_dataset(
        info2["txn_path"], info2["events_path"], info2["gt_path"],
        100, 5, 2, "T10I4D100K (boost=5.0)", n_perm=1000, cusum_n_perm=200)

    # ── Save ──
    out = root / "experiments" / "results" / "comparison_baselines.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {out}")

    print_table("E1a Synthetic (boost=0.5, N=5000, seed=0)", all_results["synthetic_e1a"])
    print_table("T10I4D100K (boost=5.0, event_dur=500)", all_results["T10I4D100K"])
    print()


if __name__ == "__main__":
    main()
