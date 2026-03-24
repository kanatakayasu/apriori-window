"""
EX5: Real Data Validation — Exploratory analysis on Dunnhumby 30 campaigns.

Includes partial ground truth validation via coupon.csv:
coupon-targeted products are used to check if attributed patterns
contain items that were actually promoted by the attributed campaign.
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

_src_dir = str(Path(__file__).resolve().parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex5"
DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


# ── Coupon Consistency Evaluation ────────────────────────────────
def evaluate_coupon_consistency(
    results: list,
    dunnhumby_dir: Path,
) -> Dict[str, Any]:
    """Evaluate attributions against coupon ground truth.

    For each significant attribution (pattern -> campaign), check if ANY
    item in the pattern was coupon-targeted by that campaign.

    Returns dict with coupon_hit_rate, coupon_precision, and per-campaign breakdown.
    """
    from build_dunnhumby_gt import (
        build_coupon_ground_truth,
        get_event_name_to_id_map,
    )

    gt = build_coupon_ground_truth(dunnhumby_dir)
    name_to_eid = get_event_name_to_id_map(dunnhumby_dir)

    n_total = 0
    n_hit = 0  # attribution where >= 1 pattern item is coupon-targeted
    n_with_gt = 0  # attributions whose campaign has coupon-targeted items
    n_hit_among_gt = 0  # hits among those with ground truth

    per_campaign: Dict[str, Dict[str, Any]] = {}

    for r in results:
        eid = name_to_eid.get(r.event_name)
        if eid is None:
            continue
        coupon_items = gt.get(eid, set())
        pattern_items = set(r.pattern)
        overlap = pattern_items & coupon_items
        is_hit = len(overlap) > 0

        n_total += 1
        if is_hit:
            n_hit += 1
        if coupon_items:
            n_with_gt += 1
            if is_hit:
                n_hit_among_gt += 1

        # Per-campaign tracking
        if r.event_name not in per_campaign:
            per_campaign[r.event_name] = {
                "event_id": eid,
                "n_coupon_items": len(coupon_items),
                "n_attributions": 0,
                "n_hits": 0,
                "hit_patterns": [],
            }
        entry = per_campaign[r.event_name]
        entry["n_attributions"] += 1
        if is_hit:
            entry["n_hits"] += 1
            entry["hit_patterns"].append({
                "pattern": list(r.pattern),
                "overlap_items": sorted(overlap),
                "score": round(r.attribution_score, 4),
            })

    coupon_hit_rate = n_hit / n_total if n_total > 0 else 0.0
    coupon_precision = n_hit_among_gt / n_with_gt if n_with_gt > 0 else 0.0

    return {
        "n_attributions_evaluated": n_total,
        "n_coupon_hits": n_hit,
        "coupon_hit_rate": round(coupon_hit_rate, 4),
        "n_with_coupon_gt": n_with_gt,
        "n_hits_among_gt": n_hit_among_gt,
        "coupon_precision": round(coupon_precision, 4),
        "per_campaign": per_campaign,
    }


def print_coupon_summary(coupon_eval: Dict[str, Any]) -> None:
    """Print coupon consistency evaluation results."""
    print("\n" + "=" * 60)
    print("Coupon Consistency Evaluation (Partial Ground Truth)")
    print("=" * 60)
    print(f"  Total attributions evaluated: {coupon_eval['n_attributions_evaluated']}")
    print(f"  Coupon hits (>= 1 item match): {coupon_eval['n_coupon_hits']}")
    print(f"  Coupon hit rate: {coupon_eval['coupon_hit_rate']:.4f}")
    print(f"  Attributions with coupon GT: {coupon_eval['n_with_coupon_gt']}")
    print(f"  Hits among GT-available: {coupon_eval['n_hits_among_gt']}")
    print(f"  Coupon precision: {coupon_eval['coupon_precision']:.4f}")

    per_campaign = coupon_eval["per_campaign"]
    if per_campaign:
        print(f"\n  Per-campaign breakdown ({len(per_campaign)} campaigns with attributions):")
        for cname in sorted(per_campaign, key=lambda x: int(per_campaign[x]["event_id"][1:])):
            entry = per_campaign[cname]
            rate = entry["n_hits"] / entry["n_attributions"] if entry["n_attributions"] > 0 else 0
            print(f"    {cname} ({entry['event_id']}): "
                  f"{entry['n_hits']}/{entry['n_attributions']} hits "
                  f"(rate={rate:.2f}, coupon_items={entry['n_coupon_items']})")


# ── Main Experiment ──────────────────────────────────────────────
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
        alpha=0.10,
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

    # ── Coupon Consistency Evaluation ────────────────────────────
    coupon_eval = None
    coupon_csv = dunnhumby_dir / "raw" / "coupon.csv"
    if coupon_csv.exists() and results:
        coupon_eval = evaluate_coupon_consistency(results, dunnhumby_dir)
        print_coupon_summary(coupon_eval)
    elif not coupon_csv.exists():
        print("\n  Coupon GT: skipped (coupon.csv not found)")
    else:
        print("\n  Coupon GT: skipped (no significant attributions)")

    out: Dict[str, Any] = {
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
    if coupon_eval is not None:
        # Serialize sets in per_campaign for JSON compatibility
        out["coupon_consistency"] = coupon_eval
    return out


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
