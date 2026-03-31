"""
Hypothesis count analysis for the Event Attribution Pipeline paper.

Analyzes how the support amplitude filter (min_support_range) reduces
the number of hypotheses (M) and its effect on FDR control.

Usage:
    .venv/bin/python3 experiments/run_hypothesis_analysis.py
"""
import json
import sys
import time
from pathlib import Path

# Project root setup
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, str(Path(PROJECT_ROOT) / "apriori_window_suite" / "python"))
sys.path.insert(0, str(Path(PROJECT_ROOT) / "apriori_window_original" / "python"))

from experiments.src.gen_synthetic import (
    SyntheticConfig,
    PlantedSignal,
    DecoyEvent,
    generate_synthetic,
)
from experiments.src.run_experiment import run_single_experiment, ExperimentResult
from event_attribution import (
    AttributionConfig,
    read_events,
    run_attribution_pipeline_v2,
    _run_pipeline_global_v2,
    _get_pattern_timestamps,
    _detect_and_filter_from_intervals,
    permutation_test_raw,
)
from apriori_window import (
    read_text_file_as_2d_vec_of_integers,
    compute_item_timestamps_map,
    find_dense_itemsets,
)

import random


def make_e1a_config(
    n_transactions: int = 5000,
    n_planted: int = 3,
    n_decoy: int = 2,
    boost: float = 0.5,
    event_duration: int = 200,
    seed: int = 0,
) -> SyntheticConfig:
    """Create E1a synthetic config (replicated from make_default_config, fixing boost_factor bug)."""
    rng = random.Random(seed)
    spacing = n_transactions // (n_planted + 1)

    planted = []
    for i in range(n_planted):
        start = spacing * (i + 1) - event_duration // 2
        end = start + event_duration
        start = max(0, start)
        end = min(n_transactions - 1, end)
        base_item = 10 + i * 10
        pattern = [base_item, base_item + 1]
        planted.append(PlantedSignal(
            pattern=pattern,
            event_id=f"E{i+1}",
            event_name=f"Event_{i+1}",
            event_start=start,
            event_end=end,
            boost_factor=boost,
        ))

    decoys = []
    for i in range(n_decoy):
        start = rng.randint(0, n_transactions - event_duration - 1)
        end = start + event_duration
        decoys.append(DecoyEvent(
            event_id=f"D{i+1}",
            event_name=f"Decoy_{i+1}",
            start=start,
            end=end,
        ))

    return SyntheticConfig(
        n_transactions=n_transactions,
        planted_signals=planted,
        decoy_events=decoys,
        seed=seed,
    )


def count_patterns_and_hypotheses(
    frequents, item_transaction_map, events, window_size, threshold,
    n_transactions, config,
):
    """Count patterns passing filter and hypotheses (patterns x events with change points)."""
    sigma = config.sigma if config.sigma is not None else float(window_size)
    max_pos = max(0, n_transactions - window_size + 1)

    n_patterns_total = sum(1 for k in frequents if len(k) > 1)
    n_patterns_with_intervals = 0
    n_patterns_passing_filter = 0
    n_patterns_with_change_points = 0
    n_hypotheses = 0

    for pattern, intervals in frequents.items():
        if len(pattern) <= 1:
            continue
        if not intervals:
            continue
        n_patterns_with_intervals += 1

        # Check min_support_range filter (replicate pipeline logic)
        if config.min_support_range > 0:
            from event_attribution import _local_support
            timestamps = _get_pattern_timestamps(pattern, item_transaction_map)
            if config.min_support_range > threshold:
                max_sup = 0
                for s, e in intervals:
                    mid = (s + e) // 2
                    sup = _local_support(timestamps, mid, window_size)
                    if sup > max_sup:
                        max_sup = sup
                min_sup = max_sup
                candidate_positions = [0, max(0, max_pos - 1)]
                sorted_intervals = sorted(intervals)
                for i in range(len(sorted_intervals) - 1):
                    gap_mid = (sorted_intervals[i][1] + sorted_intervals[i + 1][0]) // 2
                    candidate_positions.append(gap_mid)
                for pos in candidate_positions:
                    if 0 <= pos < max_pos:
                        sup = _local_support(timestamps, pos, window_size)
                        if sup < min_sup:
                            min_sup = sup
                s_range = max_sup - min_sup
                if s_range < config.min_support_range:
                    continue
            # For min_support_range <= threshold, all patterns with intervals pass

        n_patterns_passing_filter += 1

        timestamps = _get_pattern_timestamps(pattern, item_transaction_map)
        change_points = _detect_and_filter_from_intervals(
            intervals, timestamps, window_size, n_transactions, config,
        )
        if change_points:
            n_patterns_with_change_points += 1
            # Count hypotheses: each (pattern, event) pair that produces a candidate
            for event in events:
                from event_attribution import score_attributions
                candidates = score_attributions(
                    pattern, change_points, [event], sigma,
                    config.attribution_threshold,
                )
                if candidates:
                    n_hypotheses += 1

    return {
        "n_patterns_total": n_patterns_total,
        "n_patterns_with_intervals": n_patterns_with_intervals,
        "n_patterns_passing_filter": n_patterns_passing_filter,
        "n_patterns_with_change_points": n_patterns_with_change_points,
        "n_hypotheses": n_hypotheses,
    }


def main():
    out_dir = Path(PROJECT_ROOT) / "experiments" / "data" / "hypothesis_analysis"
    results_path = Path(PROJECT_ROOT) / "experiments" / "results" / "hypothesis_analysis.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # 1. Generate synthetic data (E1a condition)
    # =========================================================================
    print("=" * 70)
    print("Step 1: Generating synthetic data (E1a condition)")
    print("=" * 70)

    config = make_e1a_config(
        n_transactions=5000, n_planted=3, n_decoy=2,
        boost=0.5, event_duration=200, seed=0,
    )
    info = generate_synthetic(config, str(out_dir))
    print(f"  Transactions: {info['txn_path']}")
    print(f"  Events:       {info['events_path']}")
    print(f"  Ground truth: {info['gt_path']}")
    print(f"  N planted: {info['n_planted']}, N decoy: {info['n_decoy']}")

    # =========================================================================
    # 2. Run Phase 1
    # =========================================================================
    print("\n" + "=" * 70)
    print("Step 2: Running Phase 1 (frequent dense itemsets)")
    print("=" * 70)

    transactions = read_text_file_as_2d_vec_of_integers(info['txn_path'])
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(transactions, 50, 3, 2)

    n_all = len(frequents)
    n_multi = sum(1 for k in frequents if len(k) > 1)
    print(f"  Total patterns: {n_all}")
    print(f"  Multi-item patterns (len>1): {n_multi}")

    events = read_events(info['events_path'])
    n_events = len(events)
    print(f"  Events: {n_events}")

    # =========================================================================
    # 3. Sweep min_support_range and run full pipeline
    # =========================================================================
    print("\n" + "=" * 70)
    print("Step 3: Sweeping min_support_range (delta)")
    print("=" * 70)

    deltas = [0, 1, 2, 3, 5, 10, 20]
    sweep_results = []

    header = (
        f"{'delta':>5} | {'Pat(filt)':>9} | {'Pat(CP)':>7} | {'M_hyp':>5} | "
        f"{'sig(raw)':>8} | {'sig(ded)':>8} | {'P':>5} | {'R':>5} | {'F1':>5} | "
        f"{'TP':>3} | {'FP':>3} | {'FN':>3} | {'time_ms':>8}"
    )
    print(header)
    print("-" * len(header))

    for delta in deltas:
        t0 = time.perf_counter()

        # Count patterns/hypotheses
        attr_config = AttributionConfig(
            min_support_range=delta,
            n_permutations=5000,
            alpha=0.20,
            correction_method="bh",
            global_correction=True,
            deduplicate_overlap=True,
            seed=0,
        )
        counts = count_patterns_and_hypotheses(
            frequents, item_transaction_map, events, 50, 3,
            len(transactions), attr_config,
        )

        # Run WITH dedup
        result_dedup = run_single_experiment(
            info['txn_path'], info['events_path'], info['gt_path'],
            window_size=50, min_support=3, max_length=100,
            config=attr_config,
        )

        # Run WITHOUT dedup to get raw significant count
        attr_config_no_dedup = AttributionConfig(
            min_support_range=delta,
            n_permutations=5000,
            alpha=0.20,
            correction_method="bh",
            global_correction=True,
            deduplicate_overlap=False,
            seed=0,
        )
        result_no_dedup = run_single_experiment(
            info['txn_path'], info['events_path'], info['gt_path'],
            window_size=50, min_support=3, max_length=100,
            config=attr_config_no_dedup,
        )

        elapsed = (time.perf_counter() - t0) * 1000

        row = {
            "delta": delta,
            "n_patterns_total": counts["n_patterns_total"],
            "n_patterns_passing_filter": counts["n_patterns_passing_filter"],
            "n_patterns_with_change_points": counts["n_patterns_with_change_points"],
            "n_hypotheses": counts["n_hypotheses"],
            "n_significant_raw": result_no_dedup.n_significant,
            "n_significant_dedup": result_dedup.n_significant,
            "precision": result_dedup.precision,
            "recall": result_dedup.recall,
            "f1": result_dedup.f1,
            "tp": result_dedup.tp,
            "fp": result_dedup.fp,
            "fn": result_dedup.fn,
            "time_ms": round(elapsed, 1),
            "significant_attributions_dedup": result_dedup.significant_attributions,
            "significant_attributions_raw": result_no_dedup.significant_attributions,
        }
        sweep_results.append(row)

        print(
            f"{delta:>5} | {counts['n_patterns_passing_filter']:>9} | "
            f"{counts['n_patterns_with_change_points']:>7} | {counts['n_hypotheses']:>5} | "
            f"{result_no_dedup.n_significant:>8} | {result_dedup.n_significant:>8} | "
            f"{result_dedup.precision:>5.2f} | {result_dedup.recall:>5.2f} | "
            f"{result_dedup.f1:>5.2f} | "
            f"{result_dedup.tp:>3} | {result_dedup.fp:>3} | {result_dedup.fn:>3} | "
            f"{elapsed:>8.1f}"
        )

    # =========================================================================
    # 4. P-value distribution analysis (alpha=1.0, no dedup, delta=0)
    # =========================================================================
    print("\n" + "=" * 70)
    print("Step 4: P-value distribution analysis (all hypotheses)")
    print("=" * 70)

    config_all = AttributionConfig(
        min_support_range=0,
        n_permutations=5000,
        alpha=1.0,  # accept all
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=False,
        seed=0,
    )
    all_results = run_attribution_pipeline_v2(
        frequents, item_transaction_map, events,
        50, 3, len(transactions), config_all,
    )

    print(f"\n  Total significant attributions (alpha=1.0): {len(all_results)}")

    # Also get ALL raw p-values by running the internal pipeline
    # We need raw p-values before BH adjustment. Run with alpha=1.0 to get all.
    # The results already have adjusted_p_value from BH.
    p_values_raw = [r.p_value for r in all_results]
    p_values_adj = [r.adjusted_p_value for r in all_results]

    print(f"  Total hypotheses tested: {len(all_results)}")

    print("\n  --- Raw p-value distribution ---")
    thresholds = [0.001, 0.01, 0.05, 0.10, 0.20, 0.50, 1.0]
    pvalue_dist_raw = {}
    for threshold in thresholds:
        count = sum(1 for p in p_values_raw if p < threshold)
        pvalue_dist_raw[str(threshold)] = count
        print(f"    raw_p < {threshold:>5.3f}: {count:>4}/{len(p_values_raw)}")

    print("\n  --- BH-adjusted p-value distribution ---")
    pvalue_dist_adj = {}
    for threshold in thresholds:
        count = sum(1 for p in p_values_adj if p < threshold)
        pvalue_dist_adj[str(threshold)] = count
        print(f"    adj_p < {threshold:>5.3f}: {count:>4}/{len(p_values_adj)}")

    # Show the actual p-values for the top results
    print("\n  --- Top 20 results by adjusted p-value ---")
    sorted_results = sorted(all_results, key=lambda r: r.adjusted_p_value)
    print(f"  {'Pattern':<20} {'Event':<12} {'Dir':<5} {'Score':>7} {'p_raw':>8} {'p_adj':>8}")
    print(f"  {'-'*20} {'-'*12} {'-'*5} {'-'*7} {'-'*8} {'-'*8}")
    for r in sorted_results[:20]:
        pat_str = str(list(r.pattern))
        print(
            f"  {pat_str:<20} {r.event_name:<12} {r.change_direction:<5} "
            f"{r.attribution_score:>7.2f} {r.p_value:>8.4f} {r.adjusted_p_value:>8.4f}"
        )

    # =========================================================================
    # 5. Summary and save
    # =========================================================================
    print("\n" + "=" * 70)
    print("Step 5: Summary")
    print("=" * 70)

    # Key findings
    baseline = sweep_results[0]  # delta=0
    print(f"\n  Baseline (delta=0):")
    print(f"    Patterns: {baseline['n_patterns_passing_filter']}")
    print(f"    Hypotheses: {baseline['n_hypotheses']}")
    print(f"    Significant (raw): {baseline['n_significant_raw']}")
    print(f"    Significant (dedup): {baseline['n_significant_dedup']}")
    print(f"    P={baseline['precision']:.2f} R={baseline['recall']:.2f} F1={baseline['f1']:.2f}")

    # Find best F1
    best = max(sweep_results, key=lambda r: r["f1"])
    print(f"\n  Best F1 (delta={best['delta']}):")
    print(f"    Patterns: {best['n_patterns_passing_filter']}")
    print(f"    Hypotheses: {best['n_hypotheses']}")
    print(f"    Significant (raw): {best['n_significant_raw']}")
    print(f"    Significant (dedup): {best['n_significant_dedup']}")
    print(f"    P={best['precision']:.2f} R={best['recall']:.2f} F1={best['f1']:.2f}")

    # Hypothesis reduction
    if baseline['n_hypotheses'] > 0:
        for row in sweep_results:
            reduction = 1.0 - row['n_hypotheses'] / baseline['n_hypotheses']
            row['hypothesis_reduction_pct'] = round(reduction * 100, 1)
            print(f"    delta={row['delta']:>2}: M={row['n_hypotheses']:>4} "
                  f"({reduction*100:>5.1f}% reduction)")

    # Save all results
    output = {
        "experiment": "hypothesis_count_analysis",
        "synthetic_config": {
            "n_transactions": 5000,
            "n_planted": 3,
            "n_decoy": 2,
            "boost": 0.5,
            "event_duration": 200,
            "seed": 0,
        },
        "phase1_params": {
            "window_size": 50,
            "min_support": 3,
            "max_length": 2,
        },
        "pipeline_params": {
            "n_permutations": 5000,
            "alpha": 0.20,
            "correction_method": "bh",
            "global_correction": True,
            "deduplicate_overlap": True,
        },
        "n_patterns_total": n_multi,
        "n_events": n_events,
        "sweep_results": [
            {k: v for k, v in row.items()
             if k not in ("significant_attributions_dedup", "significant_attributions_raw")}
            for row in sweep_results
        ],
        "pvalue_distribution": {
            "n_total_hypotheses": len(all_results),
            "raw_p_values": {
                str(t): pvalue_dist_raw[str(t)] for t in thresholds
            },
            "adjusted_p_values": {
                str(t): pvalue_dist_adj[str(t)] for t in thresholds
            },
        },
        "top_results": [
            {
                "pattern": list(r.pattern),
                "event_name": r.event_name,
                "change_direction": r.change_direction,
                "attribution_score": round(r.attribution_score, 4),
                "p_value": round(r.p_value, 6),
                "adjusted_p_value": round(r.adjusted_p_value, 6),
            }
            for r in sorted_results[:20]
        ],
    }

    with open(results_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n  Results saved to: {results_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
