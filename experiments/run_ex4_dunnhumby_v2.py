"""
EX4: Dunnhumby Real Campaign Attribution (W3 対応版)

W3(a): キャンペーン内容とトップ帰属パターンを対応付けた定性ケーススタディ
W3(b): W/θ 感度分析（settings_list で複数設定を実行）

TypeA キャンペーン 5 件（C8, C13, C18, C26, C30）のみを使用．
"""
import json
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
_python_dir = str(Path(_root) / "apriori_window_suite" / "python")
for p in [_root, _python_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd

from apriori_window_basket import (
    compute_item_timestamps_map,
    find_dense_itemsets,
    read_text_file_as_2d_vec_of_integers,
)
from event_attribution import AttributionConfig, read_events, run_attribution_pipeline_v2

DATA_DIR    = Path(_root) / "dataset" / "dunnhumby"
RAW_DIR     = DATA_DIR / "raw"
RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex4_dunnhumby"


# ---------------------------------------------------------------------------
# Product / coupon helpers
# ---------------------------------------------------------------------------

def build_id_to_category(product_id_map_path, product_csv_path):
    """internal_id (int) -> (COMMODITY_DESC, SUB_COMMODITY_DESC, PRODUCT_ID)"""
    with open(product_id_map_path) as f:
        id_map = json.load(f)           # {"0": 25671, "1": 26081, ...}
    inv = {v: int(k) for k, v in id_map.items()}  # original_pid -> internal_id

    product = pd.read_csv(product_csv_path)
    result = {}
    for _, row in product.iterrows():
        pid = row["PRODUCT_ID"]
        if pid in inv:
            result[inv[pid]] = {
                "commodity": row["COMMODITY_DESC"],
                "sub_commodity": row["SUB_COMMODITY_DESC"],
                "original_pid": int(pid),
            }
    return result


def build_campaign_coupon_internal(coupon_csv_path, product_id_map_path):
    """campaign_id (int) -> set of internal item IDs covered by coupons"""
    with open(product_id_map_path) as f:
        id_map = json.load(f)
    inv = {v: int(k) for k, v in id_map.items()}
    coupon = pd.read_csv(coupon_csv_path)
    result = {}
    for _, row in coupon.iterrows():
        cid = int(row["CAMPAIGN"])
        pid = int(row["PRODUCT_ID"])
        internal = inv.get(pid)
        if internal is not None:
            result.setdefault(cid, set()).add(internal)
    return result


def is_coupon_consistent(pattern, campaign_id, coupon_map):
    coupons = coupon_map.get(campaign_id, set())
    return any(item in coupons for item in pattern)


# ---------------------------------------------------------------------------
# Single EX4 run
# ---------------------------------------------------------------------------

def run_ex4_single(window_size: int, min_support: int, label: str):
    txn_path    = str(DATA_DIR / "transactions.txt")
    events_path = str(DATA_DIR / "events.json")

    print(f"\n{'='*65}")
    print(f"EX4: W={window_size}, θ={min_support}  [{label}]")
    print(f"{'='*65}")

    # Phase 1
    t0 = time.perf_counter()
    transactions = read_text_file_as_2d_vec_of_integers(txn_path)
    item_ts_map  = compute_item_timestamps_map(transactions)
    frequents    = find_dense_itemsets(transactions, window_size, min_support, 100)
    t1 = time.perf_counter()
    n_patterns = sum(1 for k in frequents if len(k) > 1)
    print(f"  Transactions : {len(transactions):,}")
    print(f"  Patterns (≥2): {n_patterns}")
    print(f"  Phase 1 time : {(t1-t0):.1f}s")

    # Filter TypeA events only
    all_events = read_events(events_path)
    typeA_events = [e for e in all_events if "TypeA" in e.name]
    campaign_id_map = {e.name: int(e.event_id.lstrip("C")) for e in typeA_events}
    # Load day ranges from raw events.json for display
    with open(events_path) as _f:
        raw_events = {ev["event_id"]: ev for ev in json.load(_f)}
    def get_days(ev):
        raw = raw_events.get(ev.event_id, {})
        return raw.get("start_day", "?"), raw.get("end_day", "?")
    print(f"  TypeA campaigns: {[e.name for e in typeA_events]}")

    # Attribution
    config = AttributionConfig(
        min_support_range=3,
        n_permutations=5000,
        alpha=0.10,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=42,
    )
    t2 = time.perf_counter()
    results = run_attribution_pipeline_v2(
        frequents, item_ts_map, typeA_events,
        window_size, min_support, len(transactions), config,
    )
    t3 = time.perf_counter()
    print(f"  Attributions  : {len(results)}")
    print(f"  Attribution t : {(t3-t2):.1f}s")

    # Product mapping
    id_to_cat   = build_id_to_category(
        DATA_DIR / "product_id_map.json", RAW_DIR / "product.csv")
    coupon_map  = build_campaign_coupon_internal(
        RAW_DIR / "coupon.csv", DATA_DIR / "product_id_map.json")

    # Coupon consistency
    n_consistent = 0
    sig_list = []
    for r in results:
        camp_int = campaign_id_map.get(r.event_name)
        cc = is_coupon_consistent(r.pattern, camp_int, coupon_map) if camp_int else False
        if cc:
            n_consistent += 1
        cats = [id_to_cat.get(i, {}).get("commodity", f"ID:{i}") for i in r.pattern]
        sig_list.append({
            "pattern_ids": list(r.pattern),
            "pattern_categories": cats,
            "event_name": r.event_name,
            "score": round(r.attribution_score, 4),
            "p_adj": round(r.adjusted_p_value, 4),
            "direction": r.change_direction,
            "coupon_consistent": cc,
        })

    coupon_rate = n_consistent / len(results) if results else 0.0
    print(f"  Coupon match  : {n_consistent}/{len(results)} ({coupon_rate:.0%})")

    # Campaign-level top patterns
    print("\n  === Campaign Top Patterns ===")
    by_campaign = {}
    for r in sig_list:
        by_campaign.setdefault(r["event_name"], []).append(r)

    campaign_summary = []
    for ev in typeA_events:
        attrs = sorted(by_campaign.get(ev.name, []), key=lambda x: -x["score"])
        top3  = attrs[:3]
        sd, ed = get_days(ev)
        print(f"\n  {ev.name} (C{campaign_id_map[ev.name]}, "
              f"day {sd}-{ed}): {len(attrs)} attributions")
        for r in top3:
            cc_mark = "✓" if r["coupon_consistent"] else "✗"
            print(f"    [{cc_mark}] {r['pattern_categories']}  "
                  f"score={r['score']:.3f} p={r['p_adj']:.4f}")
        sd, ed = get_days(ev)
        campaign_summary.append({
            "campaign": ev.name,
            "campaign_id": campaign_id_map[ev.name],
            "start_day": sd,
            "end_day": ed,
            "n_attributions": len(attrs),
            "top_patterns": top3,
        })

    output = {
        "config": {"window_size": window_size, "min_support": min_support, "label": label},
        "n_transactions": len(transactions),
        "n_patterns": n_patterns,
        "n_attributions": len(results),
        "n_coupon_consistent": n_consistent,
        "coupon_consistency_rate": coupon_rate,
        "time_phase1_s": round(t1-t0, 1),
        "time_attribution_s": round(t3-t2, 1),
        "campaign_summary": campaign_summary,
        "all_attributions": sig_list,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"ex4_{label}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved → {out_path}")
    return output


# ---------------------------------------------------------------------------
# Main: default + sensitivity settings
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # W3(a): default settings (paper §5.5)
    default = run_ex4_single(window_size=300, min_support=5, label="default")

    # W3(b): sensitivity analysis
    sensitivity_settings = [
        (100, 3,  "W100_t3"),
        (100, 5,  "W100_t5"),
        (300, 3,  "W300_t3"),
        (500, 5,  "W500_t5"),
        (500, 10, "W500_t10"),
    ]
    sensitivity_results = [default]
    for w, t, lbl in sensitivity_settings:
        res = run_ex4_single(window_size=w, min_support=t, label=lbl)
        sensitivity_results.append(res)

    # Sensitivity summary table
    print("\n" + "="*70)
    print(f"{'Setting':<14} {'W':>5} {'θ':>4} {'#Pat':>6} {'#Attr':>6} {'CouponMatch':>12}")
    print("-"*70)
    for res in sensitivity_results:
        cfg = res["config"]
        cc  = res["n_coupon_consistent"]
        tot = res["n_attributions"]
        rate = f"{cc}/{tot} ({res['coupon_consistency_rate']:.0%})"
        print(f"{cfg['label']:<14} {cfg['window_size']:>5} {cfg['min_support']:>4} "
              f"{res['n_patterns']:>6} {tot:>6}  {rate}")
    print("="*70)

    # Save combined sensitivity
    with open(RESULTS_DIR / "ex4_sensitivity.json", "w") as f:
        json.dump(sensitivity_results, f, indent=2, default=str)
    print("Sensitivity saved → experiments/results/ex4_dunnhumby/ex4_sensitivity.json")
