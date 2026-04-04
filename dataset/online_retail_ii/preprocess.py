#!/usr/bin/env python3
"""
Preprocess Online Retail II dataset for event attribution analysis.

Steps:
1. Read Excel file
2. Filter: UK only, remove cancellations, remove non-product items
3. Create daily baskets grouped by (date, InvoiceNo)
4. Map StockCode to integer IDs
5. Write transactions.txt, events.json, product_id_map.json, metadata.json
"""

import json
import os
from datetime import datetime

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XLSX_PATH = os.path.join(BASE_DIR, "online_retail_II.xlsx")

# Non-product stock codes to exclude
NON_PRODUCT_CODES = {
    "POST", "DOT", "M", "BANK CHARGES", "PADS", "CRUK",
    "D", "C2", "S", "AMAZONFEE", "B", "m",
}


def load_data():
    """Load both sheets of the Excel file."""
    print("Loading Excel file (this may take a minute)...")
    df1 = pd.read_excel(XLSX_PATH, sheet_name="Year 2009-2010")
    df2 = pd.read_excel(XLSX_PATH, sheet_name="Year 2010-2011")
    df = pd.concat([df1, df2], ignore_index=True)
    print(f"  Raw rows: {len(df):,}")
    return df


def clean_data(df):
    """Filter and clean the dataset."""
    original = len(df)

    # Standardize column names
    df.columns = [c.strip() for c in df.columns]

    # UK only
    df = df[df["Country"] == "United Kingdom"].copy()
    print(f"  After UK filter: {len(df):,} (removed {original - len(df):,})")

    # Convert Invoice to string for prefix check
    df["Invoice"] = df["Invoice"].astype(str)

    # Remove cancelled orders (Invoice starts with 'C')
    mask_cancel = df["Invoice"].str.startswith("C")
    n_cancel = mask_cancel.sum()
    df = df[~mask_cancel].copy()
    print(f"  After removing cancellations: {len(df):,} (removed {n_cancel:,})")

    # Remove non-product items
    df["StockCode"] = df["StockCode"].astype(str).str.strip()
    mask_non_product = df["StockCode"].isin(NON_PRODUCT_CODES)
    # Also remove purely numeric codes that are too short (adjustments)
    # and codes starting with certain patterns
    n_non = mask_non_product.sum()
    df = df[~mask_non_product].copy()
    print(f"  After removing non-products: {len(df):,} (removed {n_non:,})")

    # Remove rows with missing StockCode or InvoiceDate
    df = df.dropna(subset=["StockCode", "InvoiceDate"])

    # Remove rows with Quantity <= 0 or Price <= 0
    df = df[(df["Quantity"] > 0) & (df["Price"] > 0)].copy()
    print(f"  After removing invalid qty/price: {len(df):,}")

    # Extract date
    df["Date"] = pd.to_datetime(df["InvoiceDate"]).dt.date

    return df


def build_baskets(df):
    """
    Group by (Date, Invoice) to form baskets.
    Each basket = set of unique StockCodes in that invoice.
    Sort chronologically by date, then by Invoice within the same date.
    """
    # Get unique items per invoice
    baskets = (
        df.groupby(["Date", "Invoice"])["StockCode"]
        .apply(lambda x: sorted(set(x)))
        .reset_index()
    )
    baskets = baskets.sort_values(["Date", "Invoice"]).reset_index(drop=True)
    print(f"  Total baskets: {len(baskets):,}")
    print(f"  Date range: {baskets['Date'].min()} to {baskets['Date'].max()}")
    return baskets


def build_id_map(baskets):
    """Map StockCode strings to integer IDs."""
    all_codes = set()
    for items in baskets["StockCode"]:
        all_codes.update(items)
    all_codes = sorted(all_codes)
    code_to_id = {code: i for i, code in enumerate(all_codes)}
    print(f"  Unique products: {len(code_to_id):,}")
    return code_to_id


def write_transactions(baskets, code_to_id, path):
    """Write transactions.txt: one basket per line, items space-separated."""
    with open(path, "w") as f:
        for items in baskets["StockCode"]:
            ids = sorted(code_to_id[c] for c in items)
            f.write(" ".join(str(i) for i in ids) + "\n")
    print(f"  Written {len(baskets):,} transactions to {os.path.basename(path)}")


def build_events(baskets):
    """
    Build events.json mapping event date ranges to transaction indices.
    """
    # Build date-to-index mapping
    dates = baskets["Date"].tolist()
    date_to_first_idx = {}
    date_to_last_idx = {}
    for i, d in enumerate(dates):
        if d not in date_to_first_idx:
            date_to_first_idx[d] = i
        date_to_last_idx[d] = i

    from datetime import date, timedelta

    def find_range(start_date, end_date):
        """Find first and last transaction indices within a date range."""
        sd = start_date if isinstance(start_date, date) else date.fromisoformat(start_date)
        ed = end_date if isinstance(end_date, date) else date.fromisoformat(end_date)

        first_idx = None
        last_idx = None
        d = sd
        while d <= ed:
            if d in date_to_first_idx:
                if first_idx is None:
                    first_idx = date_to_first_idx[d]
                last_idx = date_to_last_idx[d]
            d += timedelta(days=1)
        return first_idx, last_idx

    event_defs = [
        ("E01", "Christmas_2009", "2009-12-01", "2009-12-25"),
        ("E02", "Christmas_2010", "2010-12-01", "2010-12-25"),
        ("E03", "Christmas_2011", "2011-12-01", "2011-12-25"),
        ("E04", "Valentines_2010", "2010-02-01", "2010-02-14"),
        ("E05", "Valentines_2011", "2011-02-01", "2011-02-14"),
        ("E06", "MothersDay_UK_2010", "2010-03-01", "2010-03-14"),
        ("E07", "MothersDay_UK_2011", "2011-03-01", "2011-03-27"),
        ("E08", "Easter_2010", "2010-03-22", "2010-04-05"),
        ("E09", "Easter_2011", "2011-04-11", "2011-04-25"),
        ("E10", "BackToSchool_2010", "2010-08-15", "2010-09-15"),
        ("E11", "BlackFriday_2010", "2010-11-22", "2010-11-29"),
        ("E12", "BlackFriday_2011", "2011-11-21", "2011-11-28"),
        ("E13", "SummerSale_2010", "2010-06-15", "2010-07-15"),
        ("E14", "SummerSale_2011", "2011-06-15", "2011-07-15"),
    ]

    events = []
    for eid, name, start, end in event_defs:
        first_idx, last_idx = find_range(start, end)
        if first_idx is not None:
            events.append({
                "event_id": eid,
                "name": name,
                "date_start": start,
                "date_end": end,
                "start": first_idx,
                "end": last_idx,
            })
            print(f"    {eid} {name}: txn [{first_idx}, {last_idx}] "
                  f"({last_idx - first_idx + 1} transactions)")
        else:
            print(f"    {eid} {name}: NO DATA in range {start} to {end}")

    return events


def build_metadata(df, baskets, code_to_id, events):
    """Build metadata.json with dataset statistics."""
    dates = baskets["Date"].tolist()
    unique_dates = sorted(set(dates))
    basket_sizes = [len(items) for items in baskets["StockCode"]]

    return {
        "dataset": "Online Retail II (UCI)",
        "source_url": "https://archive.ics.uci.edu/dataset/502/online+retail+ii",
        "filter": "UK only, no cancellations, no non-product items, qty>0, price>0",
        "date_range": {
            "start": str(unique_dates[0]),
            "end": str(unique_dates[-1]),
        },
        "num_transactions": len(baskets),
        "num_unique_products": len(code_to_id),
        "num_unique_dates": len(unique_dates),
        "avg_basket_size": round(sum(basket_sizes) / len(basket_sizes), 2),
        "max_basket_size": max(basket_sizes),
        "min_basket_size": min(basket_sizes),
        "num_events": len(events),
        "created_at": datetime.now().isoformat(),
    }


def main():
    df = load_data()
    df = clean_data(df)

    print("\nBuilding baskets...")
    baskets = build_baskets(df)

    print("\nBuilding product ID map...")
    code_to_id = build_id_map(baskets)

    print("\nWriting transactions.txt...")
    txn_path = os.path.join(BASE_DIR, "transactions.txt")
    write_transactions(baskets, code_to_id, txn_path)

    print("\nBuilding events...")
    events = build_events(baskets)

    print("\nWriting output files...")
    # events.json
    events_path = os.path.join(BASE_DIR, "events.json")
    with open(events_path, "w") as f:
        json.dump(events, f, indent=2)
    print(f"  Written events.json ({len(events)} events)")

    # product_id_map.json
    map_path = os.path.join(BASE_DIR, "product_id_map.json")
    with open(map_path, "w") as f:
        json.dump(code_to_id, f, indent=2)
    print(f"  Written product_id_map.json ({len(code_to_id)} products)")

    # metadata.json
    meta = build_metadata(df, baskets, code_to_id, events)
    meta_path = os.path.join(BASE_DIR, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Written metadata.json")

    print("\nDone! Summary:")
    print(f"  Transactions: {meta['num_transactions']:,}")
    print(f"  Products: {meta['num_unique_products']:,}")
    print(f"  Date range: {meta['date_range']['start']} to {meta['date_range']['end']}")
    print(f"  Avg basket size: {meta['avg_basket_size']}")
    print(f"  Events: {meta['num_events']}")


if __name__ == "__main__":
    main()
