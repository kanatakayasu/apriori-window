"""
EX3: Dunnhumby Real Campaign Data with √norm default.
"""
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

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

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "sqrt_default"
DATA_DIR = Path(__file__).resolve().parent.parent / "dataset" / "dunnhumby"


def run_ex3(window_size=300, min_support=5, max_length=100):
    txn_path = str(DATA_DIR / "transactions.txt")
    events_path = str(DATA_DIR / "events.json")

    if not Path(txn_path).exists():
        print(f"ERROR: {txn_path} not found.")
        return

    print("=" * 60)
    print("EX3: Dunnhumby (√norm default)")
    print("=" * 60)

    t0 = time.perf_counter()
    transactions = read_text_file_as_2d_vec_of_integers(txn_path)
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)
    t1 = time.perf_counter()

    n_patterns = sum(1 for k in frequents if len(k) > 1)
    print(f"  Transactions: {len(transactions):,}")
    print(f"  Patterns (len>1): {n_patterns}")
    print(f"  Phase 1: {(t1-t0)*1000:.0f}ms")

    events = read_events(events_path)
    print(f"  Campaigns: {len(events)}")

    # With dedup + √norm
    config = AttributionConfig(
        min_support_range=3,
        n_permutations=5000,
        alpha=0.20,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=42,
        magnitude_normalization="sqrt",
    )
    t2 = time.perf_counter()
    results = run_attribution_pipeline_v2(
        frequents, item_transaction_map, events,
        window_size, min_support, len(transactions), config,
    )
    t3 = time.perf_counter()

    print(f"\n  Significant attributions: {len(results)}")

    # Campaign summary
    campaign_attrs = {}
    for r in results:
        key = r.event_name
        if key not in campaign_attrs:
            campaign_attrs[key] = []
        campaign_attrs[key].append(r)

    n_with = len(campaign_attrs)
    print(f"  Campaigns with attributions: {n_with}/{len(events)}")
    if len(results) > 0:
        avg_per_campaign = len(results) / len(events)
        print(f"  Avg attributions per campaign: {avg_per_campaign:.1f}")

    # Coupon consistency check
    coupon_path = DATA_DIR / "coupon.csv"
    if coupon_path.exists():
        import csv
        coupon_items = {}
        with open(str(coupon_path)) as f:
            reader = csv.DictReader(f)
            for row in reader:
                cid = row.get("CAMPAIGN", row.get("campaign", ""))
                product = row.get("PRODUCT_ID", row.get("product_id", ""))
                if cid and product:
                    coupon_items.setdefault(cid, set()).add(int(product))

        # Map event_id to campaign key
        total_attr = 0
        total_consistent = 0
        type_stats = {}

        for r in results:
            eid = r.event_id if hasattr(r, 'event_id') else ""
            campaign_key = eid.replace("campaign_", "")
            items_in_pattern = set(r.pattern)
            coupons = coupon_items.get(campaign_key, set())
            consistent = bool(items_in_pattern & coupons)
            total_attr += 1
            if consistent:
                total_consistent += 1

        if total_attr > 0:
            print(f"\n  Coupon consistency: {total_consistent}/{total_attr} "
                  f"({total_consistent/total_attr:.2f})")

    # Save
    sig_dicts = []
    for r in results:
        sig_dicts.append({
            "pattern": list(r.pattern),
            "event_name": r.event_name,
            "event_id": r.event_id if hasattr(r, 'event_id') else "",
            "attribution_score": r.attribution_score,
            "adjusted_p_value": r.adjusted_p_value,
        })

    output = {
        "n_transactions": len(transactions),
        "n_patterns": n_patterns,
        "n_campaigns": len(events),
        "n_significant": len(results),
        "n_campaigns_with_attribution": n_with,
        "avg_per_campaign": len(results) / max(1, len(events)),
        "time_phase1_ms": (t1 - t0) * 1000,
        "time_attribution_ms": (t3 - t2) * 1000,
        "time_total_ms": (t3 - t0) * 1000,
        "attributions": sig_dicts,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(str(RESULTS_DIR / "ex3_dunnhumby_sqrt.json"), "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved to {RESULTS_DIR / 'ex3_dunnhumby_sqrt.json'}")


if __name__ == "__main__":
    run_ex3()
