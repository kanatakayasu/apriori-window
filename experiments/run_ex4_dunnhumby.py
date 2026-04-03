"""
E5: Dunnhumby Real Campaign Data — Exploratory attribution on real-world campaigns.

Unlike E1-E4, this experiment uses REAL campaign events (no injection).
Since ground truth is unknown, evaluation is qualitative:
  - How many campaigns receive significant attributions?
  - Are attributed patterns plausible (campaign-related products)?
  - Does deduplication reduce redundancy?
"""
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

_python_dir = str(Path(_root) / "apriori_window_suite" / "python")
_original_dir = str(Path(_root) / "apriori_window_original" / "python")
for p in [_python_dir, _original_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from apriori_window import (
    compute_item_timestamps_map,
    find_dense_itemsets,
    read_text_file_as_2d_vec_of_integers,
)
from event_attribution import (
    AttributionConfig,
    read_events,
    run_attribution_pipeline_v2,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "e5"
DATA_DIR = Path(__file__).resolve().parent.parent / "dataset" / "dunnhumby"


@dataclass
class E5Result:
    config: Dict[str, Any]
    n_transactions: int
    n_patterns: int
    n_campaigns: int
    n_significant: int
    n_significant_no_dedup: int
    n_campaigns_with_attribution: int
    time_phase1_ms: float
    time_attribution_ms: float
    time_total_ms: float
    significant_attributions: List[Dict]
    campaign_summary: List[Dict]


def run_e5(window_size: int = 300, min_support: int = 5, max_length: int = 100):
    """Run Dunnhumby real campaign attribution."""
    txn_path = str(DATA_DIR / "transactions.txt")
    events_path = str(DATA_DIR / "events.json")

    if not Path(txn_path).exists():
        print(f"ERROR: {txn_path} not found. Run preprocess_dunnhumby.py first.")
        return

    print("=" * 60)
    print("E5: Dunnhumby Real Campaign Attribution")
    print("=" * 60)

    # Phase 1
    print(f"\nPhase 1: window_size={window_size}, min_support={min_support}, max_length={max_length}")
    t0 = time.perf_counter()
    transactions = read_text_file_as_2d_vec_of_integers(txn_path)
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)
    t1 = time.perf_counter()

    n_patterns = sum(1 for k in frequents if len(k) > 1)
    print(f"  Transactions: {len(transactions):,}")
    print(f"  Patterns (len>1): {n_patterns}")
    print(f"  Phase 1 time: {(t1-t0)*1000:.0f}ms")

    # Events
    events = read_events(events_path)
    print(f"  Campaigns: {len(events)}")

    # Attribution — first without dedup for comparison
    config_no_dedup = AttributionConfig(
        min_support_range=3,
        n_permutations=5000,
        alpha=0.20,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=False,
        seed=42,
    )
    t2 = time.perf_counter()
    results_no_dedup = run_attribution_pipeline_v2(
        frequents, item_transaction_map, events,
        window_size, min_support, len(transactions), config_no_dedup,
    )
    t3 = time.perf_counter()
    print(f"\n  Without dedup: {len(results_no_dedup)} significant attributions")

    # Attribution — with dedup
    config_dedup = AttributionConfig(
        min_support_range=3,
        n_permutations=5000,
        alpha=0.20,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=42,
    )
    results_dedup = run_attribution_pipeline_v2(
        frequents, item_transaction_map, events,
        window_size, min_support, len(transactions), config_dedup,
    )
    t4 = time.perf_counter()
    print(f"  With dedup:    {len(results_dedup)} significant attributions")

    if len(results_no_dedup) > 0:
        reduction = (1 - len(results_dedup) / len(results_no_dedup)) * 100
        print(f"  Reduction:     {reduction:.0f}%")

    # Campaign-level summary
    campaign_attrs = {}
    for r in results_dedup:
        key = r.event_name
        if key not in campaign_attrs:
            campaign_attrs[key] = []
        campaign_attrs[key].append(r)

    n_with = len(campaign_attrs)
    print(f"\n  Campaigns with attributions: {n_with}/{len(events)}")

    campaign_summary = []
    for event in events:
        attrs = campaign_attrs.get(event.name, [])
        summary = {
            "campaign": event.name,
            "event_id": event.event_id if hasattr(event, 'event_id') else "",
            "start": event.start,
            "end": event.end,
            "n_attributions": len(attrs),
            "top_patterns": [],
        }
        # Top 5 by score
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

    # Serialize
    sig_dicts = []
    for r in results_dedup:
        sig_dicts.append({
            "pattern": list(r.pattern),
            "change_time": r.change_time,
            "change_direction": r.change_direction,
            "change_magnitude": r.change_magnitude,
            "event_name": r.event_name,
            "event_start": r.event_start,
            "event_end": r.event_end,
            "proximity": r.proximity,
            "attribution_score": r.attribution_score,
            "p_value": r.p_value,
            "adjusted_p_value": r.adjusted_p_value,
        })

    result = E5Result(
        config={
            "window_size": window_size,
            "min_support": min_support,
            "max_length": max_length,
            "n_permutations": 5000,
            "alpha": 0.20,
            "correction_method": "bh",
            "min_support_range": 3,
        },
        n_transactions=len(transactions),
        n_patterns=n_patterns,
        n_campaigns=len(events),
        n_significant=len(results_dedup),
        n_significant_no_dedup=len(results_no_dedup),
        n_campaigns_with_attribution=n_with,
        time_phase1_ms=(t1 - t0) * 1000,
        time_attribution_ms=(t4 - t1) * 1000,
        time_total_ms=(t4 - t0) * 1000,
        significant_attributions=sig_dicts,
        campaign_summary=campaign_summary,
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "e5_dunnhumby_results.json"
    with open(str(out_path), "w") as f:
        json.dump(asdict(result), f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")
    return result


if __name__ == "__main__":
    run_e5()
