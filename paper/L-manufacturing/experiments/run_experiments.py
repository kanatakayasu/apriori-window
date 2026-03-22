"""
Paper L Experiment Runner: E1-E4.

E1: Dense alarm pattern detection on synthetic manufacturing data
E2: Maintenance event contrast (pattern resolution/introduction)
E3: Parameter sensitivity analysis (window_size, threshold)
E4: Cross-equipment group analysis
"""

import json
import sys
import time
from pathlib import Path

# Add implementation to path
impl_dir = str(Path(__file__).resolve().parent.parent / "implementation" / "python")
if impl_dir not in sys.path:
    sys.path.insert(0, impl_dir)

from synthetic_manufacturing_data import (
    SyntheticManufacturingConfig,
    FaultScenario,
    create_default_config,
    generate_synthetic_alarms,
    generate_transactions,
)
from alarm_adapter import AlarmAdapter, get_equipment_group
from manufacturing_dense_miner import (
    find_dense_alarm_patterns,
    compute_item_transaction_map,
    compute_support_time_series,
)
from maintenance_contrast import (
    run_contrast_analysis,
    summarize_results,
    compute_density_change,
    MaintenanceEvent,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIGURES_DIR = Path(__file__).resolve().parent / "figures"


def ensure_dirs():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


# ===================================================================
# E1: Dense Alarm Pattern Detection
# ===================================================================

def run_e1():
    """E1: Detect dense alarm patterns in synthetic manufacturing data."""
    print("=" * 60)
    print("E1: Dense Alarm Pattern Detection")
    print("=" * 60)

    config = create_default_config()
    txns, adapter, events, gt = generate_transactions(config)

    window_size = 20
    threshold = 8
    max_length = 4

    t0 = time.perf_counter()
    patterns = find_dense_alarm_patterns(txns, window_size, threshold, max_length)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Analyze results
    singleton_count = sum(1 for p in patterns if len(p) == 1)
    pair_count = sum(1 for p in patterns if len(p) == 2)
    triple_count = sum(1 for p in patterns if len(p) == 3)
    quad_count = sum(1 for p in patterns if len(p) >= 4)
    total_intervals = sum(len(iv) for iv in patterns.values())

    # Equipment group distribution
    group_counts = {}
    for pattern in patterns:
        if len(pattern) < 2:
            continue
        groups = adapter.get_equipment_groups(pattern)
        for g in groups:
            group_counts[g] = group_counts.get(g, 0) + 1
        if len(groups) > 1:
            group_counts["CROSS_EQUIP"] = group_counts.get("CROSS_EQUIP", 0) + 1

    results = {
        "experiment": "E1",
        "config": {
            "n_time_bins": config.n_time_bins,
            "n_fault_scenarios": len(config.fault_scenarios),
            "window_size": window_size,
            "threshold": threshold,
            "max_length": max_length,
        },
        "results": {
            "total_patterns": len(patterns),
            "singleton_patterns": singleton_count,
            "pair_patterns": pair_count,
            "triple_patterns": triple_count,
            "quad_patterns": quad_count,
            "total_intervals": total_intervals,
            "equipment_group_distribution": group_counts,
            "elapsed_ms": round(elapsed_ms, 2),
        },
        "sample_patterns": [],
    }

    # Add sample decoded patterns
    for pattern, intervals in sorted(patterns.items(), key=lambda x: len(x[0]), reverse=True)[:10]:
        if len(pattern) < 2:
            continue
        decoded = adapter.decode_pattern(pattern)
        groups = adapter.get_equipment_groups(pattern)
        results["sample_patterns"].append({
            "pattern": list(decoded),
            "equipment_groups": groups,
            "n_intervals": len(intervals),
            "intervals": [(s, e) for s, e in intervals[:5]],
        })

    print(f"  Total patterns: {len(patterns)}")
    print(f"    Singletons: {singleton_count}")
    print(f"    Pairs: {pair_count}")
    print(f"    Triples: {triple_count}")
    print(f"    Quads+: {quad_count}")
    print(f"  Total intervals: {total_intervals}")
    print(f"  Equipment groups: {group_counts}")
    print(f"  Elapsed: {elapsed_ms:.2f} ms")

    return results, patterns, txns, adapter, events, gt


# ===================================================================
# E2: Maintenance Event Contrast
# ===================================================================

def run_e2(patterns, txns, adapter, events, gt):
    """E2: Contrast analysis around maintenance events."""
    print("\n" + "=" * 60)
    print("E2: Maintenance Event Contrast Analysis")
    print("=" * 60)

    item_map = compute_item_transaction_map(txns)
    n_transactions = len(txns)
    window_size = 20
    lookback = 100

    contrast_results = run_contrast_analysis(
        patterns, events, n_transactions, window_size, lookback,
        item_map, adapter, alpha=0.05,
    )

    summary = summarize_results(contrast_results)

    # Per-event breakdown
    event_breakdown = {}
    for event in events:
        event_results = [r for r in contrast_results if r.event_id == event.event_id]
        event_summary = summarize_results(event_results)
        equip_related = sum(1 for r in event_results if r.equipment_related)
        event_breakdown[event.event_id] = {
            "event_type": event.event_type,
            "equipment_group": event.equipment_group,
            "timestamp": event.timestamp,
            "description": event.description,
            "summary": event_summary,
            "equipment_related_count": equip_related,
        }

    results = {
        "experiment": "E2",
        "config": {
            "lookback": lookback,
            "alpha": 0.05,
            "n_events": len(events),
        },
        "results": {
            "total_significant": summary["total"],
            "resolved": summary["resolved"],
            "introduced": summary["introduced"],
            "stable": summary["stable"],
        },
        "event_breakdown": event_breakdown,
        "sample_contrasts": [],
    }

    # Top contrast results by absolute delta
    top_contrasts = sorted(contrast_results, key=lambda r: abs(r.delta), reverse=True)[:10]
    for r in top_contrasts:
        decoded = adapter.decode_pattern(r.pattern)
        results["sample_contrasts"].append({
            "pattern": list(decoded),
            "event_id": r.event_id,
            "pre_mean": round(r.pre_mean, 3),
            "post_mean": round(r.post_mean, 3),
            "delta": round(r.delta, 3),
            "p_value": round(r.p_value, 6),
            "classification": r.classification,
            "equipment_related": r.equipment_related,
        })

    print(f"  Significant contrasts: {summary['total']}")
    print(f"    Resolved: {summary['resolved']}")
    print(f"    Introduced: {summary['introduced']}")
    print(f"    Stable: {summary['stable']}")
    for eid, eb in event_breakdown.items():
        print(f"  {eid} ({eb['event_type']}): {eb['summary']['total']} significant")

    return results


# ===================================================================
# E3: Parameter Sensitivity
# ===================================================================

def run_e3():
    """E3: Parameter sensitivity analysis."""
    print("\n" + "=" * 60)
    print("E3: Parameter Sensitivity Analysis")
    print("=" * 60)

    config = create_default_config()
    txns, adapter, events, gt = generate_transactions(config)

    sensitivity_results = []

    # Vary window_size
    for ws in [10, 15, 20, 30, 50]:
        t0 = time.perf_counter()
        patterns = find_dense_alarm_patterns(txns, ws, 8, 3)
        elapsed = (time.perf_counter() - t0) * 1000
        multi = sum(1 for p in patterns if len(p) >= 2)
        total_iv = sum(len(iv) for iv in patterns.values())
        sensitivity_results.append({
            "window_size": ws, "threshold": 8,
            "total_patterns": len(patterns), "multi_patterns": multi,
            "total_intervals": total_iv, "elapsed_ms": round(elapsed, 2),
        })
        print(f"  W={ws}, T=8: {len(patterns)} patterns ({multi} multi), {elapsed:.1f}ms")

    # Vary threshold
    for th in [4, 6, 8, 10, 12]:
        t0 = time.perf_counter()
        patterns = find_dense_alarm_patterns(txns, 20, th, 3)
        elapsed = (time.perf_counter() - t0) * 1000
        multi = sum(1 for p in patterns if len(p) >= 2)
        total_iv = sum(len(iv) for iv in patterns.values())
        sensitivity_results.append({
            "window_size": 20, "threshold": th,
            "total_patterns": len(patterns), "multi_patterns": multi,
            "total_intervals": total_iv, "elapsed_ms": round(elapsed, 2),
        })
        print(f"  W=20, T={th}: {len(patterns)} patterns ({multi} multi), {elapsed:.1f}ms")

    return {"experiment": "E3", "sensitivity": sensitivity_results}


# ===================================================================
# E4: Cross-Equipment Group Analysis
# ===================================================================

def run_e4(patterns, adapter, gt):
    """E4: Analyze cross-equipment fault propagation."""
    print("\n" + "=" * 60)
    print("E4: Cross-Equipment Group Analysis")
    print("=" * 60)

    cross_equipment = []
    single_equipment = []

    for pattern, intervals in patterns.items():
        if len(pattern) < 2:
            continue
        groups = adapter.get_equipment_groups(pattern)
        decoded = adapter.decode_pattern(pattern)
        entry = {
            "pattern": list(decoded),
            "groups": groups,
            "n_intervals": len(intervals),
            "interval_span": sum(e - s for s, e in intervals),
        }
        if len(groups) > 1:
            cross_equipment.append(entry)
        else:
            single_equipment.append(entry)

    # Match with ground truth faults
    fault_coverage = {}
    for fault_id, fault in gt.items():
        matching = []
        for pattern, intervals in patterns.items():
            if len(pattern) < 2:
                continue
            decoded = adapter.decode_pattern(pattern)
            overlap = set(decoded) & set(fault.alarm_types)
            if len(overlap) >= 2:
                for s, e in intervals:
                    if s < fault.end_bin and e >= fault.start_bin:
                        matching.append({
                            "pattern": list(decoded),
                            "interval": (s, e),
                            "overlap_alarms": list(overlap),
                        })
                        break
        fault_coverage[fault_id] = {
            "description": fault.description,
            "alarm_types": fault.alarm_types,
            "time_range": (fault.start_bin, fault.end_bin),
            "detected_patterns": len(matching),
            "matching": matching[:5],
        }

    results = {
        "experiment": "E4",
        "cross_equipment_patterns": len(cross_equipment),
        "single_equipment_patterns": len(single_equipment),
        "cross_equipment_sample": cross_equipment[:10],
        "fault_coverage": fault_coverage,
    }

    print(f"  Cross-equipment patterns: {len(cross_equipment)}")
    print(f"  Single-equipment patterns: {len(single_equipment)}")
    for fid, fc in fault_coverage.items():
        print(f"  {fid}: {fc['detected_patterns']} detecting patterns ({fc['description'][:40]})")

    return results


# ===================================================================
# Main
# ===================================================================

def main():
    ensure_dirs()

    # E1
    e1_results, patterns, txns, adapter, events, gt = run_e1()

    # E2
    e2_results = run_e2(patterns, txns, adapter, events, gt)

    # E3
    e3_results = run_e3()

    # E4
    e4_results = run_e4(patterns, adapter, gt)

    # Save all results
    all_results = {
        "paper_id": "L-manufacturing",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "experiments": {
            "E1": e1_results,
            "E2": e2_results,
            "E3": e3_results,
            "E4": e4_results,
        },
    }

    out_path = RESULTS_DIR / "all_results.json"
    out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    print(f"\nAll results saved to {out_path}")

    return all_results


if __name__ == "__main__":
    main()
