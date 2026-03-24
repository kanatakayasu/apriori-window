"""
EX5: Real Data Validation — Exploratory analysis on Dunnhumby 30 campaigns.
"""
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

_python_dir = str(Path(_root) / "apriori_window_suite" / "python")
_original_dir = str(Path(_root) / "apriori_window_original" / "python")
for p in [_python_dir, _original_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex5"
DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


def run_ex5() -> Dict[str, Any] | None:
    """Run Dunnhumby real campaign attribution (exploratory)."""
    print("=" * 60)
    print("EX5: Dunnhumby Real Campaigns (exploratory)")
    print("=" * 60)

    from apriori_window import (
        compute_item_timestamps_map,
        find_dense_itemsets,
        read_text_file_as_2d_vec_of_integers,
    )
    from event_attribution import (
        AttributionConfig as AttrConfig,
        read_events,
        run_attribution_pipeline_v2,
    )

    dunnhumby_dir = DATASET_DIR / "dunnhumby"
    txn_path = str(dunnhumby_dir / "transactions.txt")
    events_path = str(dunnhumby_dir / "events.json")

    if not Path(txn_path).exists():
        print(f"  Skipping: {txn_path} not found. Run preprocess_dunnhumby.py first.")
        return None

    # Phase 1
    window_size, min_support, max_length = 300, 5, 2
    print(f"  Phase 1: W={window_size}, min_sup={min_support}, max_len={max_length}")
    t0 = time.perf_counter()
    transactions = read_text_file_as_2d_vec_of_integers(txn_path)
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)
    t1 = time.perf_counter()

    n_patterns = sum(1 for k in frequents if len(k) > 1)
    print(f"  Transactions: {len(transactions):,}")
    print(f"  Patterns (len>1): {n_patterns}")
    print(f"  Phase 1 time: {(t1-t0)*1000:.0f}ms")

    events = read_events(events_path)
    print(f"  Campaigns: {len(events)}")

    # Attribution with dedup
    config = AttrConfig(
        min_support_range=3,
        n_permutations=5000,
        alpha=0.20,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=42,
    )
    results = run_attribution_pipeline_v2(
        frequents, item_transaction_map, events,
        window_size, min_support, len(transactions), config,
    )
    t2 = time.perf_counter()
    print(f"  Significant attributions: {len(results)}")
    print(f"  Attribution time: {(t2-t1)*1000:.0f}ms")

    # Campaign-level summary
    campaign_attrs: Dict[str, list] = {}
    for r in results:
        key = r.event_name
        if key not in campaign_attrs:
            campaign_attrs[key] = []
        campaign_attrs[key].append(r)

    n_with = len(campaign_attrs)
    print(f"  Campaigns with attributions: {n_with}/{len(events)}")

    campaign_summary = []
    for event in events:
        attrs = campaign_attrs.get(event.name, [])
        summary = {
            "campaign": event.name,
            "start": event.start,
            "end": event.end,
            "n_attributions": len(attrs),
            "top_patterns": [],
        }
        for r in sorted(attrs, key=lambda x: -x.attribution_score)[:5]:
            summary["top_patterns"].append({
                "pattern": list(r.pattern),
                "score": round(r.attribution_score, 4),
                "p_adj": round(r.adjusted_p_value, 4),
                "direction": r.change_direction,
            })
        campaign_summary.append(summary)
        if attrs:
            print(f"\n  {event.name} (day {event.start}-{event.end}): {len(attrs)} attributions")
            for r in sorted(attrs, key=lambda x: -x.attribution_score)[:3]:
                print(f"    pattern={list(r.pattern)} score={r.attribution_score:.2f} "
                      f"p_adj={r.adjusted_p_value:.4f} dir={r.change_direction}")

    return {
        "n_transactions": len(transactions),
        "n_patterns": n_patterns,
        "n_campaigns": len(events),
        "n_significant": len(results),
        "n_campaigns_with_attribution": n_with,
        "time_phase1_ms": (t1 - t0) * 1000,
        "time_attribution_ms": (t2 - t1) * 1000,
        "time_total_ms": (t2 - t0) * 1000,
        "campaign_summary": campaign_summary,
    }


if __name__ == "__main__":
    result = run_ex5()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "ex5_results.json")
    if result is not None:
        with open(save_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nEX5 results saved to {save_path}")
    else:
        print("\nEX5: No results to save (dataset not found).")
