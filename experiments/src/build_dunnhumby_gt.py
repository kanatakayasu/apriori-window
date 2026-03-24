"""
Build partial ground truth for Dunnhumby experiment using coupon.csv.

coupon.csv tells us which PRODUCT_IDs were targeted by each CAMPAIGN.
By mapping back through product_id_map.json, we can check if our pipeline's
attributions are "coupon-consistent" — i.e., the attributed pattern contains
items that were actually coupon-targeted by the attributed campaign.
"""
import csv
import json
from pathlib import Path
from typing import Dict, Set


def build_coupon_ground_truth(
    dunnhumby_dir: Path,
) -> Dict[str, Set[int]]:
    """Build ground truth: event_id -> set of compact item IDs targeted by that campaign's coupons.

    Args:
        dunnhumby_dir: Path to dataset/dunnhumby/ directory.

    Returns:
        Dict mapping event_id (e.g. "C24") to set of compact_ids
        that were coupon-targeted by that campaign.
    """
    # 1. Load product_id_map: compact_id (str) -> original PRODUCT_ID (int)
    map_path = dunnhumby_dir / "product_id_map.json"
    with open(map_path) as f:
        product_id_map = json.load(f)

    # Build reverse mapping: original PRODUCT_ID (int) -> compact_id (int)
    original_to_compact: Dict[int, int] = {}
    for compact_str, original_id in product_id_map.items():
        original_to_compact[int(original_id)] = int(compact_str)

    # 2. Read coupon.csv: campaign_number -> set of original PRODUCT_IDs
    coupon_path = dunnhumby_dir / "raw" / "coupon.csv"
    campaign_products: Dict[int, Set[int]] = {}
    with open(coupon_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            campaign_num = int(row["CAMPAIGN"])
            product_id = int(row["PRODUCT_ID"])
            if campaign_num not in campaign_products:
                campaign_products[campaign_num] = set()
            campaign_products[campaign_num].add(product_id)

    # 3. Read events.json to get event_id -> campaign_number mapping
    events_path = dunnhumby_dir / "events.json"
    with open(events_path) as f:
        events = json.load(f)

    # event_id like "C24" -> campaign number 24
    event_to_campaign: Dict[str, int] = {}
    for ev in events:
        eid = ev["event_id"]  # e.g. "C24"
        campaign_num = int(eid[1:])  # strip 'C' prefix
        event_to_campaign[eid] = campaign_num

    # 4. Build ground truth: event_id -> set of compact_ids
    ground_truth: Dict[str, Set[int]] = {}
    for eid, campaign_num in event_to_campaign.items():
        original_ids = campaign_products.get(campaign_num, set())
        compact_ids = set()
        for orig_id in original_ids:
            if orig_id in original_to_compact:
                compact_ids.add(original_to_compact[orig_id])
        ground_truth[eid] = compact_ids

    return ground_truth


def get_event_name_to_id_map(dunnhumby_dir: Path) -> Dict[str, str]:
    """Build mapping from event name (e.g. 'TypeB_24') to event_id (e.g. 'C24').

    Args:
        dunnhumby_dir: Path to dataset/dunnhumby/ directory.

    Returns:
        Dict mapping event name to event_id.
    """
    events_path = dunnhumby_dir / "events.json"
    with open(events_path) as f:
        events = json.load(f)
    return {ev["name"]: ev["event_id"] for ev in events}


def summarize_ground_truth(ground_truth: Dict[str, Set[int]]) -> None:
    """Print summary of coupon ground truth."""
    total_items = sum(len(v) for v in ground_truth.values())
    non_empty = sum(1 for v in ground_truth.values() if v)
    print(f"  Coupon GT: {non_empty}/{len(ground_truth)} campaigns have "
          f"coupon-targeted items ({total_items} total item mappings)")


if __name__ == "__main__":
    dunnhumby_dir = Path(__file__).resolve().parent.parent.parent / "dataset" / "dunnhumby"
    gt = build_coupon_ground_truth(dunnhumby_dir)
    summarize_ground_truth(gt)
    for eid in sorted(gt, key=lambda x: int(x[1:])):
        items = gt[eid]
        print(f"  {eid}: {len(items)} coupon-targeted items")
