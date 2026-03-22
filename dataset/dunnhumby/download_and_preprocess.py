#!/usr/bin/env python3
"""Download and preprocess the Dunnhumby "The Complete Journey" dataset.

Dataset URL:
    https://www.kaggle.com/datasets/frtgnn/dunnhumby-the-complete-journey

Download options:
    1. Manual: Visit the URL above, click "Download", and extract the ZIP.
    2. Kaggle CLI:
        pip install kaggle
        kaggle datasets download -d frtgnn/dunnhumby-the-complete-journey
        unzip dunnhumby-the-complete-journey.zip -d .

Expected files in this directory after download:
    - transaction_data.csv
    - campaign_desc.csv
    (Other CSV files may also be present but are not used here.)

Output files:
    - transactions.txt   : One line per day, space-separated PRODUCT_IDs
    - events.json        : Campaign events in the experiment pipeline format
    - ground_truth.json  : Empty array (no ground truth for real data)

Usage:
    python3 dataset/dunnhumby/download_and_preprocess.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def _print_download_instructions() -> None:
    print("=" * 70)
    print("Dunnhumby 'The Complete Journey' dataset preprocessor")
    print("=" * 70)
    print()
    print("Dataset URL:")
    print("  https://www.kaggle.com/datasets/frtgnn/dunnhumby-the-complete-journey")
    print()
    print("Download options:")
    print("  1. Manual: Visit the URL, click 'Download', extract the ZIP here.")
    print("  2. Kaggle CLI:")
    print("     pip install kaggle")
    print("     kaggle datasets download -d frtgnn/dunnhumby-the-complete-journey")
    print("     unzip dunnhumby-the-complete-journey.zip -d <this directory>")
    print()


def preprocess(data_dir: str | Path | None = None) -> None:
    """Preprocess Dunnhumby CSV files into experiment pipeline format.

    Parameters
    ----------
    data_dir : str or Path, optional
        Directory containing ``transaction_data.csv`` and ``campaign_desc.csv``.
        Defaults to the directory where this script resides.
    """
    if data_dir is None:
        data_dir = Path(__file__).resolve().parent
    else:
        data_dir = Path(data_dir).resolve()

    transaction_path = data_dir / "transaction_data.csv"
    campaign_path = data_dir / "campaign_desc.csv"

    # ------------------------------------------------------------------
    # Validate required files
    # ------------------------------------------------------------------
    missing = []
    if not transaction_path.is_file():
        missing.append(str(transaction_path))
    if not campaign_path.is_file():
        missing.append(str(campaign_path))

    if missing:
        _print_download_instructions()
        print("ERROR: Required file(s) not found:")
        for m in missing:
            print(f"  - {m}")
        print()
        print("Please download the dataset first (see instructions above).")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 1. Process transaction_data.csv -> transactions.txt
    # ------------------------------------------------------------------
    print("Reading transaction_data.csv ...")
    day_products: dict[int, set[str]] = defaultdict(set)

    with open(transaction_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            day = int(row["DAY"])
            product_id = row["PRODUCT_ID"].strip()
            day_products[day].add(product_id)

    # Sort by DAY (1..711) and write one line per day
    sorted_days = sorted(day_products.keys())
    n_transactions = len(sorted_days)

    all_items: set[str] = set()
    total_items = 0
    out_transactions = data_dir / "transactions.txt"

    with open(out_transactions, "w", encoding="utf-8") as f:
        for day in sorted_days:
            products = sorted(day_products[day])
            all_items.update(products)
            total_items += len(products)
            f.write(" ".join(products) + "\n")

    n_items = len(all_items)
    avg_items_per_day = total_items / n_transactions if n_transactions > 0 else 0.0

    print(f"  -> {out_transactions}")
    print(f"     {n_transactions} days, {n_items} unique items, "
          f"{avg_items_per_day:.1f} avg items/day")

    # ------------------------------------------------------------------
    # 2. Process campaign_desc.csv -> events.json
    # ------------------------------------------------------------------
    print("Reading campaign_desc.csv ...")
    events: list[dict] = []
    type_counters: dict[str, int] = defaultdict(int)

    with open(campaign_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            description = row["DESCRIPTION"].strip()
            campaign_id = row["CAMPAIGN"].strip()
            start_day = int(row["START_DAY"])
            end_day = int(row["END_DAY"])

            type_counters[description] += 1
            name = f"{description}_{type_counters[description]}"

            events.append({
                "event_id": f"C{campaign_id}",
                "name": name,
                "start": start_day,
                "end": end_day,
            })

    # Sort by start day
    events.sort(key=lambda e: e["start"])
    n_events = len(events)

    out_events = data_dir / "events.json"
    with open(out_events, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)

    print(f"  -> {out_events}")
    print(f"     {n_events} campaign events")

    # ------------------------------------------------------------------
    # 3. Create empty ground_truth.json
    # ------------------------------------------------------------------
    out_gt = data_dir / "ground_truth.json"
    with open(out_gt, "w", encoding="utf-8") as f:
        json.dump([], f)

    print(f"  -> {out_gt}")
    print("     (empty — no ground truth for real data)")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    print("Preprocessing complete. Summary:")
    print(f"  Transactions (days) : {n_transactions}")
    print(f"  Unique items        : {n_items}")
    print(f"  Campaign events     : {n_events}")
    print(f"  Avg items per day   : {avg_items_per_day:.1f}")
    print("=" * 70)


if __name__ == "__main__":
    preprocess()
