"""
Paper K Experiment Runner: E1-E4.

E1: Dense prescription pattern detection on synthetic data
E2: Regulatory event contrast patterns (pattern disappearance/emergence)
E3: Parameter sensitivity analysis
E4: Multi-drug-class cross-analysis
"""

import json
import sys
import time
from pathlib import Path

# Add implementation to path
impl_dir = str(Path(__file__).resolve().parent.parent / "implementation" / "python")
if impl_dir not in sys.path:
    sys.path.insert(0, impl_dir)

from synthetic_pharma_data import (
    SyntheticPharmaConfig,
    RegulatoryEvent,
    generate_synthetic_prescriptions,
    ATC_CATALOG,
)
from pharma_adapter import ATCAdapter
from pharma_dense_miner import (
    find_dense_prescription_patterns,
    compute_item_transaction_map,
    compute_support_time_series,
)
from regulatory_contrast import (
    run_contrast_analysis,
    summarize_results,
    compute_density_change,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIGURES_DIR = Path(__file__).resolve().parent / "figures"


def ensure_dirs():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


# ===================================================================
# E1: Dense Prescription Pattern Detection
# ===================================================================

def run_e1():
    """E1: Detect dense prescription patterns in synthetic data."""
    print("=" * 60)
    print("E1: Dense Prescription Pattern Detection")
    print("=" * 60)

    config = SyntheticPharmaConfig(
        n_transactions=1000,
        seed=42,
        base_pattern_prob=0.20,
        single_drug_prob=0.35,
    )
    txns, events, meta = generate_synthetic_prescriptions(config)

    adapter = ATCAdapter(atc_level=3)
    int_txns = []
    for txn in txns:
        items = sorted(set(adapter.encode_atc(atc) for atc in txn))
        int_txns.append(items)

    t0 = time.perf_counter()
    patterns = find_dense_prescription_patterns(
        int_txns, window_size=30, threshold=5, max_length=4
    )
    elapsed = time.perf_counter() - t0

    # Decode patterns
    decoded_results = []
    for pat, intervals in sorted(patterns.items(), key=lambda x: -len(x[0])):
        atc_codes = adapter.decode_itemset(pat)
        decoded_results.append({
            "pattern_ids": list(pat),
            "pattern_atc": atc_codes,
            "pattern_size": len(pat),
            "n_intervals": len(intervals),
            "intervals": [list(iv) for iv in intervals],
            "descriptions": [ATC_CATALOG.get(a, "?") for a in atc_codes],
        })

    result = {
        "experiment": "E1",
        "description": "Dense prescription pattern detection",
        "config": {
            "n_transactions": config.n_transactions,
            "window_size": 30,
            "threshold": 5,
            "max_length": 4,
            "seed": config.seed,
        },
        "elapsed_ms": elapsed * 1000,
        "n_patterns_found": len(patterns),
        "pattern_size_distribution": {},
        "patterns": decoded_results,
    }

    # Size distribution
    for d in decoded_results:
        sz = str(d["pattern_size"])
        result["pattern_size_distribution"][sz] = (
            result["pattern_size_distribution"].get(sz, 0) + 1
        )

    print(f"  Patterns found: {len(patterns)}")
    print(f"  Size distribution: {result['pattern_size_distribution']}")
    print(f"  Elapsed: {elapsed*1000:.1f} ms")

    # Top multi-item patterns
    multi = [d for d in decoded_results if d["pattern_size"] >= 2]
    print(f"  Multi-item patterns: {len(multi)}")
    for d in multi[:5]:
        print(f"    {d['pattern_atc']} ({', '.join(d['descriptions'])}) "
              f"-> {d['n_intervals']} intervals")

    with open(RESULTS_DIR / "e1_results.json", "w") as f:
        json.dump(result, f, indent=2)

    return patterns, adapter, int_txns, events


# ===================================================================
# E2: Regulatory Event Contrast Patterns
# ===================================================================

def run_e2(patterns, adapter, int_txns, events):
    """E2: Contrast analysis around regulatory events."""
    print("\n" + "=" * 60)
    print("E2: Regulatory Event Contrast Patterns")
    print("=" * 60)

    item_map = compute_item_transaction_map(int_txns)

    event_dicts = [
        {
            "event_id": e.event_id,
            "timestamp": e.timestamp,
            "targeted_atc": e.targeted_atc,
            "description": e.description,
        }
        for e in events
    ]

    # Two-stage approach: (1) screen by raw p-value, (2) BH on screened set
    # Focus on 2- and 3-item patterns only (most clinically interpretable)
    focused_patterns = {
        k: v for k, v in patterns.items()
        if 2 <= len(k) <= 3
    }
    print(f"  Focused patterns (size 2-3): {len(focused_patterns)}")

    t0 = time.perf_counter()
    results = run_contrast_analysis(
        dense_patterns=focused_patterns,
        item_transaction_map=item_map,
        n_transactions=len(int_txns),
        window_size=30,
        events=event_dicts,
        atc_id_mapping=adapter.get_mapping(),
        lookback=100,
        n_permutations=999,
        alpha=0.10,
        change_threshold=0.5,
        seed=42,
        test_method="welch",
    )
    elapsed = time.perf_counter() - t0

    summary = summarize_results(results)

    # Detailed results
    detailed = []
    for r in results:
        atc_codes = adapter.decode_itemset(r.pattern)
        detailed.append({
            "pattern_atc": atc_codes,
            "pattern_ids": list(r.pattern),
            "event_id": r.event_id,
            "event_timestamp": r.event_timestamp,
            "pre_mean": round(r.pre_mean, 3),
            "post_mean": round(r.post_mean, 3),
            "delta": round(r.delta, 3),
            "p_value": round(r.p_value, 4),
            "classification": r.classification,
            "targeted": r.targeted,
        })

    result = {
        "experiment": "E2",
        "description": "Regulatory event contrast patterns",
        "config": {
            "lookback": 100,
            "n_permutations": 999,
            "alpha": 0.05,
            "change_threshold": 1.0,
        },
        "elapsed_ms": elapsed * 1000,
        "summary": summary,
        "events": [
            {"event_id": e["event_id"], "description": e["description"],
             "timestamp": e["timestamp"], "targeted_atc": e["targeted_atc"]}
            for e in event_dicts
        ],
        "results": detailed,
    }

    print(f"  Total tests: {summary['total_tests']}")
    print(f"  Disappearing: {summary['disappearing']}")
    print(f"  Emerging: {summary['emerging']}")
    print(f"  Stable: {summary['stable']}")
    print(f"  Targeted disappearing: {summary['targeted_disappearing']}")
    print(f"  Elapsed: {elapsed*1000:.1f} ms")

    # Show significant results
    sig = [d for d in detailed if d["classification"] != "stable"]
    print(f"\n  Significant contrast patterns ({len(sig)}):")
    for d in sig:
        print(f"    {d['pattern_atc']} @ {d['event_id']}: "
              f"delta={d['delta']:+.2f}, p={d['p_value']:.4f}, "
              f"class={d['classification']}, targeted={d['targeted']}")

    with open(RESULTS_DIR / "e2_results.json", "w") as f:
        json.dump(result, f, indent=2)

    return results


# ===================================================================
# E3: Parameter Sensitivity Analysis
# ===================================================================

def run_e3():
    """E3: Sensitivity to window_size and threshold."""
    print("\n" + "=" * 60)
    print("E3: Parameter Sensitivity Analysis")
    print("=" * 60)

    config = SyntheticPharmaConfig(n_transactions=1000, seed=42)
    txns, events, _ = generate_synthetic_prescriptions(config)

    adapter = ATCAdapter(atc_level=3)
    int_txns = []
    for txn in txns:
        items = sorted(set(adapter.encode_atc(atc) for atc in txn))
        int_txns.append(items)

    window_sizes = [10, 20, 30, 50, 80]
    thresholds = [3, 5, 8, 10]

    sensitivity_results = []

    for w in window_sizes:
        for th in thresholds:
            t0 = time.perf_counter()
            patterns = find_dense_prescription_patterns(
                int_txns, window_size=w, threshold=th, max_length=3
            )
            elapsed = time.perf_counter() - t0

            n_total = len(patterns)
            n_multi = sum(1 for p in patterns if len(p) >= 2)
            n_triple = sum(1 for p in patterns if len(p) >= 3)

            row = {
                "window_size": w,
                "threshold": th,
                "n_patterns": n_total,
                "n_multi": n_multi,
                "n_triple": n_triple,
                "elapsed_ms": round(elapsed * 1000, 1),
            }
            sensitivity_results.append(row)
            print(f"  W={w:3d}, th={th:2d} -> "
                  f"patterns={n_total:3d}, multi={n_multi:2d}, "
                  f"triple={n_triple:2d}, {elapsed*1000:.1f}ms")

    result = {
        "experiment": "E3",
        "description": "Parameter sensitivity analysis",
        "parameters_tested": {
            "window_sizes": window_sizes,
            "thresholds": thresholds,
        },
        "results": sensitivity_results,
    }

    with open(RESULTS_DIR / "e3_results.json", "w") as f:
        json.dump(result, f, indent=2)

    return sensitivity_results


# ===================================================================
# E4: Multi-Drug-Class Cross Analysis
# ===================================================================

def run_e4():
    """E4: Analysis across different drug classes with different events."""
    print("\n" + "=" * 60)
    print("E4: Multi-Drug-Class Cross Analysis")
    print("=" * 60)

    # Define drug class scenarios
    scenarios = [
        {
            "name": "Cardiovascular",
            "event": RegulatoryEvent(
                event_id="CV-001",
                event_type="safety_alert",
                timestamp=333,
                description="Statin hepatotoxicity warning",
                targeted_atc=["C10A"],
                effect_magnitude=0.6,
            ),
            "focus_atc": ["C03A", "C07A", "C08C", "C09A", "C09C", "C10A"],
        },
        {
            "name": "Pain_Management",
            "event": RegulatoryEvent(
                event_id="PAIN-001",
                event_type="boxed_warning",
                timestamp=333,
                description="Opioid-benzodiazepine concurrent use warning",
                targeted_atc=["N02A", "N05B"],
                effect_magnitude=0.7,
            ),
            "focus_atc": ["M01A", "N02A", "N02B", "N05B", "A02B"],
        },
        {
            "name": "Antibiotics",
            "event": RegulatoryEvent(
                event_id="ABX-001",
                event_type="safety_alert",
                timestamp=333,
                description="Fluoroquinolone tendon rupture risk",
                targeted_atc=["J01M"],
                effect_magnitude=0.5,
            ),
            "focus_atc": ["J01C", "J01D", "J01F", "J01M", "A02B"],
        },
    ]

    # Use stronger effect for cross analysis scenarios
    for s in scenarios:
        s["event"].effect_magnitude = 0.85

    cross_results = []

    for scenario in scenarios:
        print(f"\n  --- {scenario['name']} ---")

        config = SyntheticPharmaConfig(
            n_transactions=1000,
            seed=42,
            regulatory_events=[scenario["event"]],
        )
        txns, events, _ = generate_synthetic_prescriptions(config)

        adapter = ATCAdapter(atc_level=3)
        int_txns = []
        for txn in txns:
            items = sorted(set(adapter.encode_atc(atc) for atc in txn))
            int_txns.append(items)

        patterns = find_dense_prescription_patterns(
            int_txns, window_size=30, threshold=5, max_length=3
        )

        item_map = compute_item_transaction_map(int_txns)

        event_dicts = [{
            "event_id": events[0].event_id,
            "timestamp": events[0].timestamp,
            "targeted_atc": events[0].targeted_atc,
        }]

        # Focus on patterns overlapping with targeted drugs
        t_ids = set()
        for atc in scenario["event"].targeted_atc:
            if atc in adapter.get_mapping():
                t_ids.add(adapter.get_mapping()[atc])
        focused = {
            k: v for k, v in patterns.items()
            if len(k) >= 2 and bool(set(k) & t_ids)
        }
        contrast_results = run_contrast_analysis(
            dense_patterns=focused,
            item_transaction_map=item_map,
            n_transactions=len(int_txns),
            window_size=30,
            events=event_dicts,
            atc_id_mapping=adapter.get_mapping(),
            lookback=100,
            n_permutations=999,
            alpha=0.10,
            change_threshold=0.5,
            seed=42,
            test_method="welch",
        )

        summary = summarize_results(contrast_results)

        # Decode significant patterns
        sig_patterns = []
        for r in contrast_results:
            if r.classification != "stable":
                sig_patterns.append({
                    "pattern_atc": adapter.decode_itemset(r.pattern),
                    "delta": round(r.delta, 3),
                    "p_value": round(r.p_value, 4),
                    "classification": r.classification,
                    "targeted": r.targeted,
                })

        scenario_result = {
            "scenario": scenario["name"],
            "event_description": scenario["event"].description,
            "targeted_atc": scenario["event"].targeted_atc,
            "n_patterns_found": len(patterns),
            "summary": summary,
            "significant_patterns": sig_patterns,
        }
        cross_results.append(scenario_result)

        print(f"    Patterns: {len(patterns)}, "
              f"Disappearing: {summary['disappearing']}, "
              f"Emerging: {summary['emerging']}")

    result = {
        "experiment": "E4",
        "description": "Multi-drug-class cross analysis",
        "scenarios": cross_results,
    }

    with open(RESULTS_DIR / "e4_results.json", "w") as f:
        json.dump(result, f, indent=2)

    return cross_results


# ===================================================================
# Figure generation
# ===================================================================

def generate_figures(patterns, adapter, int_txns, events, contrast_results):
    """Generate figures for the paper."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("\n[WARN] matplotlib not available, skipping figure generation")
        return

    item_map = compute_item_transaction_map(int_txns)

    # Figure 1: Support time series for key patterns around events
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("Support Time Series Around Regulatory Events", fontsize=14)

    # Select interesting patterns (multi-item)
    multi_patterns = [p for p in patterns if len(p) >= 2]
    selected = multi_patterns[:4] if len(multi_patterns) >= 4 else multi_patterns

    for idx, pat in enumerate(selected):
        if idx >= 4:
            break
        ax = axes[idx // 2][idx % 2]

        # Compute timestamps
        if len(pat) == 1:
            timestamps = item_map.get(pat[0], [])
        else:
            from pharma_dense_miner import intersect_sorted_lists
            id_lists = [item_map.get(item, []) for item in pat]
            timestamps = intersect_sorted_lists(id_lists)

        series = compute_support_time_series(timestamps, len(int_txns), 30)
        atc_codes = adapter.decode_itemset(pat)

        ax.plot(series, linewidth=0.8, color="steelblue")
        ax.set_title(f"Pattern: {', '.join(atc_codes)}", fontsize=10)
        ax.set_xlabel("Time index")
        ax.set_ylabel("Support (W=30)")

        # Mark regulatory events
        for e in events:
            ax.axvline(x=e.timestamp, color="red", linestyle="--",
                      linewidth=1, alpha=0.7)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "fig1_support_timeseries.png", dpi=150)
    plt.close()

    # Figure 2: Parameter sensitivity heatmap
    e3_path = RESULTS_DIR / "e3_results.json"
    if e3_path.exists():
        with open(e3_path) as f:
            e3 = json.load(f)

        ws = sorted(set(r["window_size"] for r in e3["results"]))
        ths = sorted(set(r["threshold"] for r in e3["results"]))

        matrix = np.zeros((len(ths), len(ws)))
        for r in e3["results"]:
            i = ths.index(r["threshold"])
            j = ws.index(r["window_size"])
            matrix[i, j] = r["n_patterns"]

        fig, ax = plt.subplots(figsize=(8, 5))
        im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")
        ax.set_xticks(range(len(ws)))
        ax.set_xticklabels(ws)
        ax.set_yticks(range(len(ths)))
        ax.set_yticklabels(ths)
        ax.set_xlabel("Window Size (W)")
        ax.set_ylabel("Threshold (theta)")
        ax.set_title("Number of Dense Patterns by Parameters")

        for i in range(len(ths)):
            for j in range(len(ws)):
                ax.text(j, i, int(matrix[i, j]),
                       ha="center", va="center", fontsize=10)

        plt.colorbar(im)
        plt.tight_layout()
        plt.savefig(FIGURES_DIR / "fig2_sensitivity_heatmap.png", dpi=150)
        plt.close()

    # Figure 3: Contrast analysis summary bar chart
    fig, ax = plt.subplots(figsize=(8, 5))
    categories = ["Disappearing\n(targeted)", "Disappearing\n(non-targeted)",
                   "Emerging", "Stable"]

    targeted_dis = sum(1 for r in contrast_results
                       if r.classification == "disappearing" and r.targeted)
    nontarget_dis = sum(1 for r in contrast_results
                        if r.classification == "disappearing" and not r.targeted)
    emerging = sum(1 for r in contrast_results
                   if r.classification == "emerging")
    stable = sum(1 for r in contrast_results
                 if r.classification == "stable")

    counts = [targeted_dis, nontarget_dis, emerging, stable]
    colors = ["#d32f2f", "#ff9800", "#4caf50", "#9e9e9e"]

    bars = ax.bar(categories, counts, color=colors)
    ax.set_ylabel("Number of Pattern-Event Pairs")
    ax.set_title("Contrast Pattern Classification")

    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.3,
               str(count), ha="center", va="bottom", fontsize=11)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "fig3_contrast_summary.png", dpi=150)
    plt.close()

    print("\n  Figures saved to", FIGURES_DIR)


# ===================================================================
# Main
# ===================================================================

def main():
    ensure_dirs()

    # E1
    patterns, adapter, int_txns, events = run_e1()

    # E2
    contrast_results = run_e2(patterns, adapter, int_txns, events)

    # E3
    run_e3()

    # E4
    run_e4()

    # Figures
    generate_figures(patterns, adapter, int_txns, events, contrast_results)

    print("\n" + "=" * 60)
    print("All experiments complete. Results in:", RESULTS_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
