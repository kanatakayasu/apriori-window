# Dunnhumby "The Complete Journey" Dataset

## Overview

Household-level transaction data over 2 years (711 days) from a group of 2,500 households who are frequent shoppers at a retailer. Includes purchase history and marketing campaign metadata.

- **Source**: <https://www.kaggle.com/datasets/frtgnn/dunnhumby-the-complete-journey>
- **License**: See the Kaggle page for terms of use.

## Setup

### 1. Download

**Option A — Manual download**

Visit the Kaggle URL above, click "Download", and extract the ZIP contents into this directory.

**Option B — Kaggle CLI**

```sh
pip install kaggle
# Ensure ~/.kaggle/kaggle.json is configured
kaggle datasets download -d frtgnn/dunnhumby-the-complete-journey
unzip dunnhumby-the-complete-journey.zip -d dataset/dunnhumby/
```

### 2. Verify

After extraction, this directory should contain (at minimum):

```
dataset/dunnhumby/
  transaction_data.csv   # Required
  campaign_desc.csv      # Required
  ...                    # Other CSVs (optional, not used)
```

### 3. Preprocess

```sh
python3 dataset/dunnhumby/download_and_preprocess.py
```

This produces three files consumed by the experiment pipeline:

| File | Description |
|------|-------------|
| `transactions.txt` | One line per day (DAY 1-711), space-separated PRODUCT_IDs |
| `events.json` | Campaign events: `[{"event_id", "name", "start", "end"}, ...]` |
| `ground_truth.json` | Empty array (no ground truth available for real data) |

## Data Schema

### transaction_data.csv

| Column | Description |
|--------|-------------|
| household_key | Household identifier |
| BASKET_ID | Basket (receipt) identifier |
| DAY | Day number (1-711) |
| PRODUCT_ID | Product identifier |
| QUANTITY | Number of units purchased |
| SALES_VALUE | Dollar amount of the sale |
| STORE_ID | Store identifier |
| RETAIL_DISC | Retail discount applied |
| TRANS_TIME | Time of transaction (HHMM) |
| WEEK_NO | Week number |
| COUPON_MATCH_DISC | Coupon match discount |

### campaign_desc.csv

| Column | Description |
|--------|-------------|
| DESCRIPTION | Campaign type (e.g., TypeA, TypeB, TypeC) |
| CAMPAIGN | Campaign number |
| START_DAY | Campaign start day |
| END_DAY | Campaign end day |

## Preprocessing Details

- **Temporal unit**: Each DAY value becomes one transaction (all PRODUCT_IDs purchased across all households on that day are merged into a single set).
- **Campaign events**: Each campaign row maps to an event with `event_id = "C{CAMPAIGN}"` and `name = "{DESCRIPTION}_{counter}"`.
- **No ground truth**: Since this is real-world data, `ground_truth.json` is an empty array.
