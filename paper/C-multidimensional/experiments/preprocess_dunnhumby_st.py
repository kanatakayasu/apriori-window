"""
Preprocess Dunnhumby data for Spatio-Temporal Event Attribution.

Creates store-level transaction data with real spatial events from
in-store product displays/mailers (causal_data.csv).

Output:
- transactions.txt: one line per basket, space-separated product IDs
- locations.txt: store index (0-based) for each basket
- events.json: store-specific display events
- store_map.json: store_index -> original STORE_ID
- product_id_map.json: compact_id -> original PRODUCT_ID
- metadata.json: dataset statistics
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent.parent.parent / "dataset" / "dunnhumby" / "raw"
OUT_DIR = Path(__file__).resolve().parent / "data" / "dunnhumby_st"


def preprocess():
    print("=" * 60)
    print("Preprocessing Dunnhumby for ST Attribution")
    print("=" * 60)

    # Step 1: Select top-N stores by transaction volume
    N_STORES = 20
    print(f"\nStep 1: Selecting top {N_STORES} stores...")

    store_counts = Counter()
    with open(RAW_DIR / "transaction_data.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            store_counts[row["STORE_ID"]] += 1

    top_stores = [s for s, _ in store_counts.most_common(N_STORES)]
    store_to_idx = {s: i for i, s in enumerate(top_stores)}
    print(f"  Selected stores: {top_stores}")
    total_txns = sum(store_counts[s] for s in top_stores)
    print(f"  Total transactions in selected stores: {total_txns:,}")

    # Step 2: Build baskets per store with day information
    print("\nStep 2: Building baskets...")

    # Group by (BASKET_ID) -> collect items, store, day
    basket_items = defaultdict(set)
    basket_meta = {}  # basket_id -> (store_id, day)

    with open(RAW_DIR / "transaction_data.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            store = row["STORE_ID"]
            if store not in store_to_idx:
                continue
            bid = row["BASKET_ID"]
            basket_items[bid].add(row["PRODUCT_ID"])
            if bid not in basket_meta:
                basket_meta[bid] = (store, int(row["DAY"]))

    # Sort baskets by day for temporal ordering
    sorted_baskets = sorted(basket_meta.keys(), key=lambda b: basket_meta[b][1])
    print(f"  Total baskets: {len(sorted_baskets):,}")

    # Step 3: Compact product IDs
    print("\nStep 3: Compacting product IDs...")
    all_products = set()
    for items in basket_items.values():
        all_products.update(items)

    product_to_compact = {}
    compact_to_product = {}
    for i, pid in enumerate(sorted(all_products)):
        product_to_compact[pid] = i
        compact_to_product[i] = pid

    print(f"  Unique products: {len(all_products):,}")

    # Step 4: Write output
    print("\nStep 4: Writing output...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # transactions.txt + locations.txt
    basket_to_idx = {}
    day_list = []
    with open(OUT_DIR / "transactions.txt", "w") as f_txn, \
         open(OUT_DIR / "locations.txt", "w") as f_loc:
        for i, bid in enumerate(sorted_baskets):
            items = basket_items[bid]
            store, day = basket_meta[bid]
            compact_items = sorted(product_to_compact[p] for p in items)
            f_txn.write(" ".join(str(x) for x in compact_items) + "\n")
            f_loc.write(f"{store_to_idx[store]}\n")
            basket_to_idx[bid] = i
            day_list.append(day)

    print(f"  Written {len(sorted_baskets):,} baskets")

    # Step 5: Build spatial events from causal_data
    print("\nStep 5: Building spatial events from display data...")

    # Find product displays by store and week
    # A "display event" = product displayed in specific stores during specific weeks
    display_by_product_week = defaultdict(lambda: defaultdict(set))  # product -> week -> set(stores)

    with open(RAW_DIR / "causal_data.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            store = row["STORE_ID"]
            if store not in store_to_idx:
                continue
            if row.get("display") and row["display"] not in ("0", "", "A"):
                pid = row["PRODUCT_ID"]
                week = int(row["WEEK_NO"])
                display_by_product_week[pid][week].add(store)

    # Find display events that are spatially localized (not all stores)
    # and temporally bounded (specific weeks)
    events = []
    event_id = 0

    # Group consecutive weeks for same product with same store set
    for pid, week_stores in display_by_product_week.items():
        if pid not in product_to_compact:
            continue

        # Sort weeks and group consecutive
        sorted_weeks = sorted(week_stores.keys())
        if not sorted_weeks:
            continue

        # Simple grouping: merge consecutive weeks with overlapping stores
        groups = []
        current_start = sorted_weeks[0]
        current_end = sorted_weeks[0]
        current_stores = set(week_stores[sorted_weeks[0]])

        for w in sorted_weeks[1:]:
            if w <= current_end + 2 and week_stores[w] & current_stores:
                current_end = w
                current_stores &= week_stores[w]
            else:
                if current_end - current_start >= 1 and len(current_stores) >= 2:
                    groups.append((current_start, current_end, current_stores))
                current_start = w
                current_end = w
                current_stores = set(week_stores[w])

        if current_end - current_start >= 1 and len(current_stores) >= 2:
            groups.append((current_start, current_end, current_stores))

        for start_week, end_week, stores in groups:
            # Convert week to basket index range
            # Week N corresponds to days (N-1)*7+1 to N*7
            start_day = (start_week - 1) * 7 + 1
            end_day = end_week * 7

            # Find basket index range for this day range
            start_idx = None
            end_idx = None
            for idx, day in enumerate(day_list):
                if day >= start_day and start_idx is None:
                    start_idx = idx
                if day <= end_day:
                    end_idx = idx

            if start_idx is None or end_idx is None or end_idx <= start_idx:
                continue

            store_indices = sorted(store_to_idx[s] for s in stores if s in store_to_idx)
            if len(store_indices) < 2 or len(store_indices) >= N_STORES:
                continue  # Skip global or single-store events

            n_stores_in_scope = len(store_indices)
            compact_pid = product_to_compact[pid]

            events.append({
                "event_id": f"DISP_{event_id}",
                "name": f"display_product_{compact_pid}_w{start_week}-{end_week}",
                "start": start_idx,
                "end": end_idx,
                "spatial_scope": store_indices,
                "product_id": compact_pid,
                "original_product_id": pid,
                "n_stores": n_stores_in_scope,
                "week_range": [start_week, end_week],
            })
            event_id += 1

    # Select a diverse subset of events
    # Prefer events with moderate spatial scope and reasonable duration
    events.sort(key=lambda e: (e["n_stores"], e["end"] - e["start"]), reverse=True)

    # Take events with different spatial scopes
    selected_events = []
    seen_products = set()
    for e in events:
        if e["product_id"] not in seen_products and len(selected_events) < 30:
            selected_events.append(e)
            seen_products.add(e["product_id"])

    print(f"  Total display events found: {len(events)}")
    print(f"  Selected events: {len(selected_events)}")
    for e in selected_events[:10]:
        print(f"    {e['event_id']}: product {e['product_id']}, "
              f"stores={e['n_stores']}, weeks={e['week_range']}, "
              f"baskets=[{e['start']},{e['end']}]")

    # Write events
    with open(OUT_DIR / "events.json", "w") as f:
        json.dump(selected_events, f, indent=2)

    # Write mappings
    with open(OUT_DIR / "store_map.json", "w") as f:
        json.dump({str(i): s for i, s in enumerate(top_stores)}, f, indent=2)

    with open(OUT_DIR / "product_id_map.json", "w") as f:
        json.dump({str(k): v for k, v in compact_to_product.items()}, f, indent=2)

    # Write metadata
    meta = {
        "n_baskets": len(sorted_baskets),
        "n_products": len(all_products),
        "n_stores": N_STORES,
        "n_events": len(selected_events),
        "day_range": [min(day_list), max(day_list)],
        "store_ids": top_stores,
        "avg_items_per_basket": sum(len(basket_items[b]) for b in sorted_baskets) / len(sorted_baskets),
    }
    with open(OUT_DIR / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nOutput written to {OUT_DIR}")
    print(f"  n_baskets: {meta['n_baskets']:,}")
    print(f"  n_products: {meta['n_products']:,}")
    print(f"  n_stores: {meta['n_stores']}")
    print(f"  n_events: {meta['n_events']}")
    print(f"  avg_items/basket: {meta['avg_items_per_basket']:.1f}")


if __name__ == "__main__":
    preprocess()
