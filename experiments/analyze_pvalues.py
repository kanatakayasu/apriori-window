"""
Analyze p-value distribution in the Event Attribution Pipeline.

Investigates why alpha=0.20 is needed instead of conventional alpha=0.05.
Runs E1a (seed=0) with alpha=1.0 to capture ALL p-values before thresholding,
then analyzes the BH-adjusted p-value distribution.

Output:
  - Console report with detailed statistics
  - paper/manuscript/fig/pvalue_distribution.pdf — histogram for the paper
"""
import json
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
_python_dir = str(Path(_root) / "apriori_window_suite" / "python")
_original_dir = str(Path(_root) / "apriori_window_original" / "python")
for _p in [_root, _python_dir, _original_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apriori_window import (
    compute_item_timestamps_map,
    find_dense_itemsets,
    read_text_file_as_2d_vec_of_integers,
)
from event_attribution import (
    AttributionConfig,
    _detect_and_filter,
    _RawTestResult,
    compute_support_series_all,
    permutation_test_raw,
    read_events,
)
from experiments.src.gen_synthetic import (
    DecoyEvent,
    PlantedSignal,
    SyntheticConfig,
    generate_synthetic,
)


def run_analysis():
    """Run the p-value analysis for E1a seed=0."""
    print("=" * 72)
    print("P-value Distribution Analysis for Event Attribution Pipeline")
    print("=" * 72)

    # --- Generate synthetic data (E1a, seed=0) ---
    seed = 0
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
    data_dir = str(Path(__file__).resolve().parent / "data" / "pvalue_analysis")
    info = generate_synthetic(config, data_dir)

    # --- Phase 1: pattern mining ---
    transactions = read_text_file_as_2d_vec_of_integers(info["txn_path"])
    item_transaction_map = compute_item_timestamps_map(transactions)

    window_size = 50
    min_support = 3
    max_length = 2

    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)

    # Support series
    support_series_map = compute_support_series_all(
        item_transaction_map, frequents, transactions, window_size,
    )
    events = read_events(info["events_path"])

    # Ground truth patterns
    with open(info["gt_path"], "r") as f:
        gt_raw = json.load(f)
    gt_pairs = {(tuple(sorted(g["pattern"])), g["event_id"]) for g in gt_raw}
    gt_patterns = {tuple(sorted(g["pattern"])) for g in gt_raw}

    # Event name -> event_id mapping
    with open(info["events_path"], "r") as f:
        events_raw = json.load(f)
    name_to_id = {e["name"]: e["event_id"] for e in events_raw}

    # --- Collect ALL raw p-values (global pipeline, no thresholding) ---
    attr_config = AttributionConfig(
        min_support_range=5,
        n_permutations=5000,
        alpha=1.0,  # Accept everything
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=False,  # Keep all to see full picture
        seed=seed,
    )

    sigma = float(window_size)
    max_distance = 2 * window_size

    all_raw: list[_RawTestResult] = []
    patterns_tested = 0
    patterns_filtered = 0

    for pattern, series in support_series_map.items():
        if len(pattern) <= 1:
            continue
        if not series:
            continue

        # Support amplitude filter
        if attr_config.min_support_range > 0:
            s_range = max(series) - min(series)
            if s_range < attr_config.min_support_range:
                patterns_filtered += 1
                continue

        max_time = len(series)
        change_points = _detect_and_filter(series, min_support, attr_config)
        if not change_points:
            continue

        patterns_tested += 1
        raw_results = permutation_test_raw(
            pattern=pattern,
            change_points=change_points,
            events=events,
            sigma=sigma,
            max_distance=max_distance,
            max_time=max_time,
            n_permutations=attr_config.n_permutations,
            attribution_threshold=attr_config.attribution_threshold,
            seed=attr_config.seed,
            use_effect_size=attr_config.use_effect_size,
        )
        all_raw.extend(raw_results)

    # --- Apply BH correction manually to get adjusted p-values ---
    M = len(all_raw)
    sorted_raw = sorted(all_raw, key=lambda r: r.p_value)

    adj_p_list = [0.0] * M
    for i in range(M - 1, -1, -1):
        rank = i + 1
        raw_adj = sorted_raw[i].p_value * M / rank
        if i == M - 1:
            adj_p_list[i] = min(1.0, raw_adj)
        else:
            adj_p_list[i] = min(adj_p_list[i + 1], min(1.0, raw_adj))

    # --- Classify each hypothesis ---
    records = []
    for i, r in enumerate(sorted_raw):
        eid = name_to_id.get(r.event.name, r.event.name)
        pat = tuple(sorted(r.pattern))
        is_tp = (pat, eid) in gt_pairs
        is_planted_pattern = pat in gt_patterns
        records.append({
            "rank": i + 1,
            "pattern": pat,
            "event_id": eid,
            "event_name": r.event.name,
            "raw_p": r.p_value,
            "adj_p": adj_p_list[i],
            "bh_factor": M / (i + 1),
            "obs_score": r.obs_score,
            "is_tp": is_tp,
            "is_planted_pattern": is_planted_pattern,
        })

    # --- Print report ---
    print(f"\n--- Pipeline Configuration ---")
    print(f"  N transactions:        5,000")
    print(f"  N events:              {len(events)} (3 planted + 2 decoys)")
    print(f"  Window size:           {window_size}")
    print(f"  min_support_range:     {attr_config.min_support_range}")
    print(f"  n_permutations:        {attr_config.n_permutations}")
    print(f"  Correction:            BH (Benjamini-Hochberg)")

    n_all_patterns = sum(1 for k in frequents if len(k) > 1)
    print(f"\n--- Pattern Filtering ---")
    print(f"  Total 2-itemset patterns:    {n_all_patterns}")
    print(f"  Filtered (low amplitude):    {patterns_filtered}")
    print(f"  Patterns with change points: {patterns_tested}")

    print(f"\n--- Hypothesis Count ---")
    print(f"  M (total hypotheses):  {M}")
    print(f"  (= patterns_with_changepoints x events_matched)")

    tp_records = [r for r in records if r["is_tp"]]
    fp_records = [r for r in records if not r["is_tp"]]

    print(f"\n--- True Positive Hypotheses ({len(tp_records)} / {M}) ---")
    for r in tp_records:
        print(f"  Pattern {r['pattern']} -> {r['event_name']} (event_id={r['event_id']})")
        print(f"    raw_p = {r['raw_p']:.4f},  adj_p = {r['adj_p']:.4f},  "
              f"rank = {r['rank']}/{M},  BH factor = {r['bh_factor']:.1f},  "
              f"score = {r['obs_score']:.2f}")

    print(f"\n--- BH Adjustment Impact ---")
    if tp_records:
        max_raw_tp = max(r["raw_p"] for r in tp_records)
        max_adj_tp = max(r["adj_p"] for r in tp_records)
        min_adj_tp = min(r["adj_p"] for r in tp_records)
        print(f"  Worst-case TP raw p-value:      {max_raw_tp:.4f}")
        print(f"  Worst-case TP adjusted p-value:  {max_adj_tp:.4f}")
        print(f"  Best-case TP adjusted p-value:   {min_adj_tp:.4f}")
        print(f"  Inflation factor (adj/raw):      {max_adj_tp / max_raw_tp:.1f}x" if max_raw_tp > 0 else "")

    print(f"\n--- Threshold Analysis ---")
    for alpha in [0.001, 0.01, 0.05, 0.10, 0.15, 0.20, 0.25]:
        tp_at = sum(1 for r in tp_records if r["adj_p"] < alpha)
        fp_at = sum(1 for r in fp_records if r["adj_p"] < alpha)
        total_sig = tp_at + fp_at
        prec = tp_at / total_sig if total_sig > 0 else 0.0
        rec = tp_at / len(tp_records) if tp_records else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        print(f"  alpha={alpha:.3f}: TP_detected={tp_at}, FP_detected={fp_at}, "
              f"P={prec:.2f}, R={rec:.2f}, F1={f1:.2f}")

    print(f"\n--- Counterfactual: What if M were smaller? ---")
    for m_hyp in [3, 5, 10, 15, 20, M]:
        # Re-compute adjusted p for just the TP raw p-values as if M=m_hyp
        if tp_records:
            worst_raw = max(r["raw_p"] for r in tp_records)
            # In BH: adj_p <= raw_p * M / rank. Worst case rank=M for the worst p-value.
            # Actually for BH: adj_p_i = min_{j>=i}(p_j * M / j)
            # Simplified: if all TPs had rank ~= M, adj_p ~ raw_p * M / M = raw_p
            # But if M is smaller, the inflation is smaller.
            # Simple estimate: adj_p ~ raw_p * m_hyp (bonferroni-like upper bound)
            # More accurately for BH: adj_p <= raw_p * m_hyp / rank_of_this_p
            # Assume rank ~= m_hyp (worst case): adj_p ~ raw_p
            # Assume rank ~= 1 (best case): adj_p ~ raw_p * m_hyp
            # Use actual TP ranks relative to M
            adj_estimate = min(1.0, worst_raw * m_hyp)  # Bonferroni upper bound
            print(f"  M={m_hyp:3d}: worst TP adj_p (Bonf. upper bound) = {adj_estimate:.4f}"
                  f"  {'< 0.05' if adj_estimate < 0.05 else '>= 0.05'}")

    # --- All hypotheses detail ---
    print(f"\n--- All {M} Hypotheses (sorted by raw p) ---")
    print(f"  {'Rank':>4} {'Pattern':>16} {'Event':>10} {'raw_p':>8} {'adj_p':>8} "
          f"{'BH_fac':>7} {'Score':>8} {'TP?':>4}")
    for r in records:
        tp_mark = " *TP" if r["is_tp"] else ""
        print(f"  {r['rank']:4d} {str(r['pattern']):>16} {r['event_name']:>10} "
              f"{r['raw_p']:8.4f} {r['adj_p']:8.4f} {r['bh_factor']:7.1f} "
              f"{r['obs_score']:8.2f}{tp_mark}")

    # --- Generate figure ---
    print("\n--- Generating figure ---")
    _generate_figure(records, tp_records, M)

    # --- Save detailed results ---
    results_path = Path(__file__).resolve().parent / "results" / "pvalue_analysis.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump({
            "M": M,
            "n_patterns_total": n_all_patterns,
            "n_patterns_filtered": patterns_filtered,
            "n_patterns_tested": patterns_tested,
            "records": [{k: (list(v) if isinstance(v, tuple) else v)
                         for k, v in r.items()} for r in records],
        }, f, indent=2)
    print(f"  Saved detailed results to {results_path}")


def _generate_figure(records, tp_records, M):
    """Generate p-value distribution histogram for the paper."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    all_adj = [r["adj_p"] for r in records]
    all_raw = [r["raw_p"] for r in records]
    tp_adj = [r["adj_p"] for r in tp_records]
    tp_raw = [r["raw_p"] for r in tp_records]
    fp_adj = [r["adj_p"] for r in records if not r["is_tp"]]

    # --- Panel (a): Raw p-values ---
    ax = axes[0]
    bins = np.linspace(0, 1.0, 21)
    ax.hist(all_raw, bins=bins, color="#999999", edgecolor="white", alpha=0.7,
            label="All hypotheses")
    # Mark TPs
    for p in tp_raw:
        ax.axvline(p, color="#d62728", linewidth=2, linestyle="--", alpha=0.8)
    ax.axvline(0.05, color="#1f77b4", linewidth=1.5, linestyle="-",
               label=r"$\alpha=0.05$")
    ax.set_xlabel("Raw p-value", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title(f"(a) Raw p-values ($M={M}$)", fontsize=12)
    # Custom legend for TP marker
    from matplotlib.lines import Line2D
    tp_line = Line2D([0], [0], color="#d62728", linewidth=2, linestyle="--",
                     label="True positive")
    handles, labels = ax.get_legend_handles_labels()
    handles.append(tp_line)
    ax.legend(handles=handles, fontsize=9)

    # --- Panel (b): BH-adjusted p-values ---
    ax = axes[1]
    ax.hist(all_adj, bins=bins, color="#999999", edgecolor="white", alpha=0.7,
            label="All hypotheses")
    # Mark TPs
    for p in tp_adj:
        ax.axvline(p, color="#d62728", linewidth=2, linestyle="--", alpha=0.8)
    ax.axvline(0.05, color="#1f77b4", linewidth=1.5, linestyle="-",
               label=r"$\alpha=0.05$")
    ax.axvline(0.20, color="#2ca02c", linewidth=1.5, linestyle="-",
               label=r"$\alpha=0.20$")
    ax.set_xlabel("BH-adjusted p-value", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title(f"(b) After BH correction ($M={M}$)", fontsize=12)
    handles2, labels2 = ax.get_legend_handles_labels()
    handles2.append(tp_line)
    ax.legend(handles=handles2, fontsize=9)

    plt.tight_layout()

    fig_path = Path(__file__).resolve().parent.parent / "paper" / "manuscript" / "fig" / "pvalue_distribution.pdf"
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(fig_path, dpi=300, bbox_inches="tight")
    print(f"  Saved figure to {fig_path}")

    # Also save PNG for quick viewing
    png_path = fig_path.with_suffix(".png")
    plt.savefig(png_path, dpi=150, bbox_inches="tight")
    print(f"  Saved PNG to {png_path}")
    plt.close()


if __name__ == "__main__":
    run_analysis()
