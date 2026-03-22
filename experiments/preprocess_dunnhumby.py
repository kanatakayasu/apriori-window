"""
Preprocess Dunnhumby "The Complete Journey" into pipeline input format.

Input:  archive/transaction_data.csv, archive/campaign_desc.csv
Output: dataset/dunnhumby/transactions.txt  (one basket per line, space-separated product IDs)
        dataset/dunnhumby/events.json       (campaigns as events, DAY-indexed)
        dataset/dunnhumby/basket_days.json   (basket_index → DAY mapping for reference)

Baskets are ordered by DAY (then BASKET_ID for determinism).
Product IDs are mapped to compact integers (0-based) to reduce memory.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parent.parent / "dataset" / "dunnhumby" / "raw"
OUT_DIR = Path(__file__).resolve().parent.parent / "dataset" / "dunnhumby"


def preprocess():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- 1. Read transactions, group by basket ---
    print("Reading transaction_data.csv ...")
    basket_items: dict[str, set[int]] = defaultdict(set)
    basket_day: dict[str, int] = {}
    with open(ARCHIVE / "transaction_data.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bid = row["BASKET_ID"]
            basket_items[bid].add(int(row["PRODUCT_ID"]))
            basket_day[bid] = int(row["DAY"])

    # Sort baskets by (DAY, BASKET_ID) for temporal ordering
    sorted_bids = sorted(basket_items.keys(), key=lambda b: (basket_day[b], b))

    # Build compact product ID map (original IDs are up to 9M+)
    all_products = set()
    for items in basket_items.values():
        all_products |= items
    pid_map = {pid: idx for idx, pid in enumerate(sorted(all_products))}
    # Also save reverse map for interpretation
    rev_map = {idx: pid for pid, idx in pid_map.items()}

    # --- 2. Write transactions.txt ---
    print(f"Writing {len(sorted_bids)} baskets ...")
    txn_path = OUT_DIR / "transactions.txt"
    basket_day_list = []
    with open(txn_path, "w") as f:
        for bid in sorted_bids:
            mapped = sorted(pid_map[p] for p in basket_items[bid])
            f.write(" ".join(str(x) for x in mapped) + "\n")
            basket_day_list.append(basket_day[bid])

    # --- 3. Write events.json (campaigns) ---
    # Campaign DAYs → basket indices (find first/last basket on that day)
    day_to_first_idx: dict[int, int] = {}
    day_to_last_idx: dict[int, int] = {}
    for i, day in enumerate(basket_day_list):
        if day not in day_to_first_idx:
            day_to_first_idx[day] = i
        day_to_last_idx[day] = i

    events = []
    with open(ARCHIVE / "campaign_desc.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_day = int(row["START_DAY"])
            end_day = int(row["END_DAY"])
            camp_id = row["CAMPAIGN"]
            desc = row["DESCRIPTION"]
            # Map DAY to basket index; clamp to data range
            start_day_clamped = max(min(basket_day_list), min(start_day, max(basket_day_list)))
            end_day_clamped = max(min(basket_day_list), min(end_day, max(basket_day_list)))
            # Find closest day if exact match doesn't exist
            if start_day_clamped not in day_to_first_idx:
                for d in range(start_day_clamped, max(basket_day_list) + 1):
                    if d in day_to_first_idx:
                        start_day_clamped = d
                        break
            if end_day_clamped not in day_to_last_idx:
                for d in range(end_day_clamped, min(basket_day_list) - 1, -1):
                    if d in day_to_last_idx:
                        end_day_clamped = d
                        break
            start_idx = day_to_first_idx.get(start_day_clamped, 0)
            end_idx = day_to_last_idx.get(end_day_clamped, len(sorted_bids) - 1)
            events.append({
                "event_id": f"C{camp_id}",
                "name": f"{desc}_{camp_id}",
                "start": start_idx,
                "end": end_idx,
                "start_day": start_day,
                "end_day": end_day,
            })

    events_path = OUT_DIR / "events.json"
    with open(events_path, "w") as f:
        json.dump(events, f, indent=2)

    # --- 4. Write metadata ---
    meta = {
        "n_baskets": len(sorted_bids),
        "n_products_original": len(all_products),
        "n_products_mapped": len(pid_map),
        "n_campaigns": len(events),
        "day_range": [min(basket_day_list), max(basket_day_list)],
        "avg_items_per_basket": sum(len(basket_items[b]) for b in sorted_bids) / len(sorted_bids),
    }
    with open(OUT_DIR / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)

    # Save product ID mapping (compact → original)
    with open(OUT_DIR / "product_id_map.json", "w") as f:
        json.dump(rev_map, f)

    # --- 5. Summary ---
    print(f"\nDunnhumby preprocessing complete:")
    print(f"  Baskets:    {meta['n_baskets']:,}")
    print(f"  Products:   {meta['n_products_mapped']:,} (mapped from {meta['n_products_original']:,})")
    print(f"  Campaigns:  {meta['n_campaigns']}")
    print(f"  Day range:  {meta['day_range']}")
    print(f"  Avg items:  {meta['avg_items_per_basket']:.1f}/basket")
    print(f"\nOutput: {OUT_DIR}")


if __name__ == "__main__":
    preprocess()
