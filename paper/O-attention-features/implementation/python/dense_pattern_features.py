"""
Dense Pattern Feature Vector extraction module.

Converts raw dense intervals from apriori_window into structured feature
vectors suitable for cross-attention event attribution.

Paper O: "Learning Event Attribution with Cross-Attention and Dense Pattern Featurization"
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Add parent path for apriori_window_basket import
# ---------------------------------------------------------------------------
_SUITE_PYTHON = str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python")
if _SUITE_PYTHON not in sys.path:
    sys.path.insert(0, _SUITE_PYTHON)

from apriori_window_basket import (  # noqa: E402
    compute_dense_intervals,
    read_transactions_with_baskets,
    compute_item_basket_map,
    basket_ids_to_transaction_ids,
    intersect_sorted_lists,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DensePatternFeature:
    """Feature vector for a single dense pattern (itemset + its intervals)."""

    itemset: Tuple[int, ...]
    # Raw interval list [(start, end), ...]
    intervals: List[Tuple[int, int]] = field(default_factory=list)

    # --- Computed features ---
    num_intervals: int = 0
    total_coverage: int = 0        # sum of (end - start + 1) for all intervals
    max_duration: int = 0          # longest single interval
    mean_duration: float = 0.0
    std_duration: float = 0.0
    first_onset: int = 0           # earliest interval start
    last_offset: int = 0           # latest interval end
    span: int = 0                  # last_offset - first_onset
    interval_density: float = 0.0  # total_coverage / span
    gap_mean: float = 0.0          # mean gap between consecutive intervals
    itemset_size: int = 0

    def compute(self) -> "DensePatternFeature":
        """Fill computed features from raw intervals."""
        self.itemset_size = len(self.itemset)
        self.num_intervals = len(self.intervals)

        if self.num_intervals == 0:
            return self

        durations = [e - s + 1 for s, e in self.intervals]
        self.total_coverage = sum(durations)
        self.max_duration = max(durations)
        self.mean_duration = float(np.mean(durations))
        self.std_duration = float(np.std(durations)) if len(durations) > 1 else 0.0
        self.first_onset = self.intervals[0][0]
        self.last_offset = self.intervals[-1][1]
        self.span = self.last_offset - self.first_onset + 1
        self.interval_density = self.total_coverage / self.span if self.span > 0 else 0.0

        if self.num_intervals > 1:
            gaps = [
                self.intervals[i + 1][0] - self.intervals[i][1]
                for i in range(self.num_intervals - 1)
            ]
            self.gap_mean = float(np.mean(gaps))
        else:
            self.gap_mean = 0.0

        return self

    def to_vector(self) -> np.ndarray:
        """Return a fixed-size feature vector (d=10)."""
        return np.array([
            self.num_intervals,
            self.total_coverage,
            self.max_duration,
            self.mean_duration,
            self.std_duration,
            self.first_onset,
            self.last_offset,
            self.interval_density,
            self.gap_mean,
            self.itemset_size,
        ], dtype=np.float64)

    @staticmethod
    def vector_dim() -> int:
        return 10

    @staticmethod
    def feature_names() -> List[str]:
        return [
            "num_intervals", "total_coverage", "max_duration",
            "mean_duration", "std_duration", "first_onset",
            "last_offset", "interval_density", "gap_mean",
            "itemset_size",
        ]


# ---------------------------------------------------------------------------
# Event representation
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """An external event with timestamp and optional metadata."""
    timestamp: int
    event_type: str = "unknown"
    magnitude: float = 1.0

    def to_vector(self, total_time: int) -> np.ndarray:
        """Return event feature vector (d_event = 3)."""
        return np.array([
            self.timestamp / max(total_time, 1),  # normalized timestamp
            self.magnitude,
            hash(self.event_type) % 1000 / 1000.0,  # simple type encoding
        ], dtype=np.float64)

    @staticmethod
    def vector_dim() -> int:
        return 3


# ---------------------------------------------------------------------------
# Time-binned pattern features (for temporal alignment)
# ---------------------------------------------------------------------------

def compute_time_binned_features(
    patterns: List[DensePatternFeature],
    total_time: int,
    num_bins: int = 50,
) -> np.ndarray:
    """
    Compute time-binned pattern activity matrix.

    Returns:
        matrix of shape (num_bins, num_patterns) where each entry
        indicates the fraction of the bin covered by the pattern's
        dense intervals.
    """
    bin_size = max(total_time // num_bins, 1)
    activity = np.zeros((num_bins, len(patterns)), dtype=np.float64)

    for j, pat in enumerate(patterns):
        for s, e in pat.intervals:
            bin_start = s // bin_size
            bin_end = min(e // bin_size, num_bins - 1)
            for b in range(bin_start, bin_end + 1):
                b_lo = b * bin_size
                b_hi = (b + 1) * bin_size - 1
                overlap = min(e, b_hi) - max(s, b_lo) + 1
                activity[b, j] += overlap / bin_size

    return activity


# ---------------------------------------------------------------------------
# Pipeline: transactions -> dense pattern features
# ---------------------------------------------------------------------------

def extract_dense_patterns(
    transactions_path: str,
    window_size: int = 10,
    threshold: int = 3,
    max_itemset_size: int = 3,
    min_support: int = 3,
) -> List[DensePatternFeature]:
    """
    Extract dense pattern features from a transaction file.

    Args:
        transactions_path: Path to transaction file.
        window_size: Sliding window size W.
        threshold: Minimum occurrence count for density.
        max_itemset_size: Max itemset length to consider.
        min_support: Min support count for candidate generation.

    Returns:
        List of DensePatternFeature with computed features.
    """
    transactions = read_transactions_with_baskets(transactions_path)
    _, basket_to_tx, item_tx_map = compute_item_basket_map(transactions)
    total_time = len(transactions)

    # Singleton dense intervals
    item_intervals: Dict[int, List[Tuple[int, int]]] = {}
    frequent_items: List[int] = []

    for item, tx_ids in item_tx_map.items():
        if len(tx_ids) >= min_support:
            intervals = compute_dense_intervals(tx_ids, window_size, threshold)
            if intervals:
                item_intervals[item] = intervals
                frequent_items.append(item)

    frequent_items.sort()

    patterns: List[DensePatternFeature] = []

    # Add singleton patterns
    for item in frequent_items:
        if item in item_intervals:
            feat = DensePatternFeature(
                itemset=(item,),
                intervals=item_intervals[item],
            ).compute()
            patterns.append(feat)

    # Generate pairs and triples via intersection
    from itertools import combinations

    for size in range(2, max_itemset_size + 1):
        for combo in combinations(frequent_items, size):
            # Intersect transaction lists
            tx_lists = [item_tx_map[it] for it in combo]
            common_txs = intersect_sorted_lists(tx_lists)
            if len(common_txs) < min_support:
                continue

            intervals = compute_dense_intervals(common_txs, window_size, threshold)
            if intervals:
                feat = DensePatternFeature(
                    itemset=combo,
                    intervals=intervals,
                ).compute()
                patterns.append(feat)

    return patterns


# ---------------------------------------------------------------------------
# Synthetic data generation for experiments
# ---------------------------------------------------------------------------

def generate_synthetic_data(
    num_transactions: int = 500,
    num_items: int = 20,
    num_events: int = 5,
    event_effect_window: int = 30,
    base_density: float = 0.1,
    boost_density: float = 0.4,
    seed: int = 42,
) -> Tuple[str, List[Event], Dict[str, List[Tuple[int, ...]]]]:
    """
    Generate synthetic transaction data with known event-pattern associations.

    Returns:
        (path_to_file, events, ground_truth)
        ground_truth maps event_type -> list of affected itemsets
    """
    rng = np.random.RandomState(seed)
    items = list(range(1, num_items + 1))

    # Generate events
    events: List[Event] = []
    event_intervals: Dict[str, Tuple[int, int]] = {}
    for i in range(num_events):
        t = rng.randint(50, num_transactions - event_effect_window - 50)
        evt = Event(timestamp=t, event_type=f"E{i}", magnitude=rng.uniform(0.5, 2.0))
        events.append(evt)
        event_intervals[f"E{i}"] = (t, t + event_effect_window)

    # Assign itemsets to events (ground truth)
    ground_truth: Dict[str, List[Tuple[int, ...]]] = {}
    assigned_items = list(rng.choice(items, size=min(num_events * 3, num_items), replace=False))

    for i, evt in enumerate(events):
        affected = []
        # Each event affects 1-2 itemsets
        n_affected = rng.randint(1, 3)
        for j in range(n_affected):
            idx = (i * 3 + j) % len(assigned_items)
            if rng.random() < 0.5 and idx + 1 < len(assigned_items):
                itemset = tuple(sorted([assigned_items[idx], assigned_items[idx + 1]]))
            else:
                itemset = (assigned_items[idx],)
            affected.append(itemset)
        ground_truth[evt.event_type] = affected

    # Generate transactions
    lines: List[str] = []
    for t in range(num_transactions):
        tx_items: List[int] = []
        for item in items:
            p = base_density
            # Check if any event boosts this item
            for evt_type, (es, ee) in event_intervals.items():
                if es <= t <= ee:
                    for affected_is in ground_truth[evt_type]:
                        if item in affected_is:
                            p = boost_density
                            break
            if rng.random() < p:
                tx_items.append(item)
        lines.append(" ".join(str(x) for x in sorted(tx_items)) if tx_items else "")

    # Write to temp file
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="synth_paper_o_")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")

    return path, events, ground_truth
