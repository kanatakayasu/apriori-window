"""
Experiments for Paper I: High-Utility Dense Intervals.

E1: Synthetic pattern recovery (precision/recall)
E2: TWU pruning efficiency
E3: Scalability (varying N and |I|)
E4: Real-data-style high-utility dense pattern discovery
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "implementation" / "python"))
from high_utility_dense_intervals import (
    generate_synthetic_utility_data,
    mine_high_utility_dense_itemsets,
)


def run_e1_pattern_recovery() -> dict:
    """E1: Inject known patterns, measure recovery."""
    print("=" * 60)
    print("E1: Pattern Recovery")
    print("=" * 60)

    results_all = []
    seeds = [42, 123, 456, 789, 1024]

    for seed in seeds:
        inject = {
            "itemset": [2, 5],
            "interval": (200, 400),
            "frequency": 0.85,
            "high_quantity": 3,
        }
        txs, ext = generate_synthetic_utility_data(
            n_transactions=1000, n_items=15, max_items_per_tx=6,
            seed=seed, inject_pattern=inject,
        )

        mining_results, stats = mine_high_utility_dense_itemsets(
            txs, ext,
            window_size=40, freq_threshold=8, util_threshold=80.0,
            max_length=3, use_twu_pruning=True,
        )

        # Check if injected pattern is recovered
        recovered = False
        overlap_ratio = 0.0
        for r in mining_results:
            if set(r.itemset) == {2, 5}:
                recovered = True
                # Compute overlap with [200, 400]
                for s, e in r.intervals:
                    ov_start = max(s, 200)
                    ov_end = min(e, 400)
                    if ov_end >= ov_start:
                        overlap_ratio = max(
                            overlap_ratio,
                            (ov_end - ov_start + 1) / (400 - 200 + 1)
                        )
                break

        results_all.append({
            "seed": seed,
            "recovered": recovered,
            "overlap_ratio": round(overlap_ratio, 3),
            "n_results": stats["results_found"],
            "time_ms": round(stats["total_time_ms"], 1),
        })
        print(f"  seed={seed}: recovered={recovered}, overlap={overlap_ratio:.3f}, "
              f"results={stats['results_found']}, time={stats['total_time_ms']:.1f}ms")

    recovery_rate = sum(1 for r in results_all if r["recovered"]) / len(results_all)
    avg_overlap = sum(r["overlap_ratio"] for r in results_all) / len(results_all)
    print(f"\n  Recovery rate: {recovery_rate:.0%}")
    print(f"  Avg overlap:  {avg_overlap:.3f}")

    return {
        "experiment": "E1",
        "recovery_rate": recovery_rate,
        "avg_overlap": round(avg_overlap, 3),
        "details": results_all,
    }


def run_e2_twu_pruning() -> dict:
    """E2: Compare mining with/without TWU pruning."""
    print("\n" + "=" * 60)
    print("E2: TWU Pruning Efficiency")
    print("=" * 60)

    configs = [
        {"n": 500, "items": 10, "util_thresh": 50.0},
        {"n": 1000, "items": 15, "util_thresh": 80.0},
        {"n": 2000, "items": 20, "util_thresh": 100.0},
    ]

    results_all = []
    for cfg in configs:
        txs, ext = generate_synthetic_utility_data(
            n_transactions=cfg["n"], n_items=cfg["items"],
            max_items_per_tx=6, seed=42,
        )

        # With TWU pruning
        _, stats_with = mine_high_utility_dense_itemsets(
            txs, ext,
            window_size=30, freq_threshold=5,
            util_threshold=cfg["util_thresh"],
            max_length=4, use_twu_pruning=True,
        )

        # Without TWU pruning
        _, stats_without = mine_high_utility_dense_itemsets(
            txs, ext,
            window_size=30, freq_threshold=5,
            util_threshold=cfg["util_thresh"],
            max_length=4, use_twu_pruning=False,
        )

        pruning_ratio = (
            1.0 - stats_with["candidates_evaluated"] / max(stats_without["candidates_evaluated"], 1)
        )
        speedup = stats_without["total_time_ms"] / max(stats_with["total_time_ms"], 0.001)

        row = {
            "n": cfg["n"],
            "items": cfg["items"],
            "util_thresh": cfg["util_thresh"],
            "eval_with_twu": stats_with["candidates_evaluated"],
            "eval_without_twu": stats_without["candidates_evaluated"],
            "pruned_by_twu": stats_with["candidates_pruned_twu"],
            "pruning_ratio": round(pruning_ratio, 3),
            "time_with_ms": round(stats_with["total_time_ms"], 1),
            "time_without_ms": round(stats_without["total_time_ms"], 1),
            "speedup": round(speedup, 2),
        }
        results_all.append(row)
        print(f"  N={cfg['n']}, |I|={cfg['items']}: "
              f"pruning={pruning_ratio:.1%}, speedup={speedup:.2f}x, "
              f"TWU-pruned={stats_with['candidates_pruned_twu']}")

    return {
        "experiment": "E2",
        "details": results_all,
    }


def run_e3_scalability() -> dict:
    """E3: Scalability with varying N."""
    print("\n" + "=" * 60)
    print("E3: Scalability")
    print("=" * 60)

    n_values = [500, 1000, 2000, 5000, 10000]
    results_all = []

    for n in n_values:
        txs, ext = generate_synthetic_utility_data(
            n_transactions=n, n_items=15, max_items_per_tx=6, seed=42,
        )

        start = time.perf_counter()
        _, stats = mine_high_utility_dense_itemsets(
            txs, ext,
            window_size=30, freq_threshold=5, util_threshold=50.0,
            max_length=3, use_twu_pruning=True,
        )
        elapsed = (time.perf_counter() - start) * 1000

        row = {
            "n_transactions": n,
            "time_ms": round(elapsed, 1),
            "results": stats["results_found"],
            "candidates_evaluated": stats["candidates_evaluated"],
        }
        results_all.append(row)
        print(f"  N={n:>6d}: time={elapsed:>8.1f}ms, "
              f"results={stats['results_found']}, "
              f"evaluated={stats['candidates_evaluated']}")

    return {
        "experiment": "E3",
        "details": results_all,
    }


def run_e4_real_data_style() -> dict:
    """E4: Real-data-style experiment with multiple injected patterns."""
    print("\n" + "=" * 60)
    print("E4: Real-Data-Style Multi-Pattern Discovery")
    print("=" * 60)

    # Generate base data
    import random
    rng = random.Random(42)
    n_items = 20
    ext = {i: rng.uniform(1.0, 15.0) for i in range(n_items)}
    n_tx = 2000

    # Create transactions
    txs_raw = []
    for tid in range(n_tx):
        n_in = rng.randint(2, 8)
        items = sorted(rng.sample(range(n_items), min(n_in, n_items)))
        quantities = [rng.randint(1, 3) for _ in items]
        tu = sum(q * ext[i] for i, q in zip(items, quantities))

        # Inject pattern 1: {3, 7} in [300, 600] with high quantity
        if 300 <= tid <= 600 and rng.random() < 0.85:
            for pi in [3, 7]:
                if pi not in items:
                    items.append(pi)
                    quantities.append(rng.randint(3, 8))
                else:
                    idx = items.index(pi)
                    quantities[idx] = rng.randint(3, 8)
            paired = sorted(zip(items, quantities))
            items = [p[0] for p in paired]
            quantities = [p[1] for p in paired]
            tu = sum(q * ext[i] for i, q in zip(items, quantities))

        # Inject pattern 2: {1, 5, 12} in [1200, 1500] with high quantity
        if 1200 <= tid <= 1500 and rng.random() < 0.80:
            for pi in [1, 5, 12]:
                if pi not in items:
                    items.append(pi)
                    quantities.append(rng.randint(4, 10))
                else:
                    idx = items.index(pi)
                    quantities[idx] = rng.randint(4, 10)
            paired = sorted(zip(items, quantities))
            items = [p[0] for p in paired]
            quantities = [p[1] for p in paired]
            tu = sum(q * ext[i] for i, q in zip(items, quantities))

        from high_utility_dense_intervals import UtilityTransaction
        txs_raw.append(UtilityTransaction(tid, items, quantities, tu))

    # Mine
    mining_results, stats = mine_high_utility_dense_itemsets(
        txs_raw, ext,
        window_size=50, freq_threshold=10, util_threshold=200.0,
        max_length=4, use_twu_pruning=True,
    )

    print(f"  Total results: {stats['results_found']}")
    print(f"  Candidates evaluated: {stats['candidates_evaluated']}")
    print(f"  TWU pruned: {stats['candidates_pruned_twu']}")
    print(f"  Time: {stats['total_time_ms']:.1f}ms")

    # Check pattern recovery
    found_patterns = []
    for r in mining_results:
        if len(r.itemset) >= 2:
            found_patterns.append({
                "itemset": list(r.itemset),
                "n_intervals": len(r.intervals),
                "intervals": [(s, e) for s, e in r.intervals],
                "max_utility": max(r.interval_utilities) if r.interval_utilities else 0,
            })
            print(f"  Found: {r.itemset} -> {len(r.intervals)} intervals, "
                  f"max_util={max(r.interval_utilities) if r.interval_utilities else 0:.1f}")

    p1_found = any(set(p["itemset"]) == {3, 7} for p in found_patterns)
    p2_found = any(set(p["itemset"]) == {1, 5, 12} for p in found_patterns)
    print(f"\n  Pattern 1 {{3,7}}: {'FOUND' if p1_found else 'NOT FOUND'}")
    print(f"  Pattern 2 {{1,5,12}}: {'FOUND' if p2_found else 'NOT FOUND'}")

    return {
        "experiment": "E4",
        "stats": stats,
        "pattern1_found": p1_found,
        "pattern2_found": p2_found,
        "found_multi_item_patterns": found_patterns,
    }


def main():
    all_results = {}

    all_results["E1"] = run_e1_pattern_recovery()
    all_results["E2"] = run_e2_twu_pruning()
    all_results["E3"] = run_e3_scalability()
    all_results["E4"] = run_e4_real_data_style()

    # Save results
    out_path = Path(__file__).resolve().parent / "results" / "all_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
