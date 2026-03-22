"""
Maintenance event contrast analysis for manufacturing.

Detects alarm pattern changes around maintenance events
(scheduled maintenance, part replacement, calibration, process changes)
by comparing support levels in pre-event vs post-event windows.
Uses Welch's t-test with Benjamini-Hochberg FDR correction.
"""

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from manufacturing_dense_miner import compute_support_time_series


@dataclass
class MaintenanceEvent:
    """A maintenance or process change event."""
    event_id: str
    timestamp: int
    event_type: str  # 'scheduled_maintenance', 'part_replacement',
                     # 'calibration', 'process_change', 'recipe_update'
    equipment_group: str  # which equipment group was affected
    description: str = ""


@dataclass
class ContrastResult:
    """Result of contrast analysis for one pattern-event pair."""
    pattern: Tuple[int, ...]
    event_id: str
    event_timestamp: int
    pre_mean: float
    post_mean: float
    delta: float
    p_value: float
    classification: str  # 'resolved', 'introduced', 'stable'
    equipment_related: bool  # pattern overlaps with event equipment group


def compute_density_change(
    support_series: Sequence[int],
    event_time: int,
    lookback: int,
) -> Tuple[float, float, float]:
    """
    Compute pre/post mean support and density change score.

    Args:
        support_series: Support time series s_P(t)
        event_time: Maintenance event time index
        lookback: Number of time steps before/after event to consider

    Returns:
        (pre_mean, post_mean, delta)
    """
    n = len(support_series)
    if n == 0:
        return 0.0, 0.0, 0.0

    pre_start = max(0, event_time - lookback)
    pre_end = event_time
    pre_values = support_series[pre_start:pre_end]

    post_start = event_time
    post_end = min(n, event_time + lookback)
    post_values = support_series[post_start:post_end]

    pre_mean = sum(pre_values) / len(pre_values) if pre_values else 0.0
    post_mean = sum(post_values) / len(post_values) if post_values else 0.0
    delta = post_mean - pre_mean

    return pre_mean, post_mean, delta


def welch_t_test(
    pre_values: Sequence[float],
    post_values: Sequence[float],
) -> float:
    """
    Compute p-value using Welch's t-test.

    Returns p-value (two-tailed). Returns 1.0 if test is degenerate.
    """
    n1 = len(pre_values)
    n2 = len(post_values)
    if n1 < 2 or n2 < 2:
        return 1.0

    mean1 = sum(pre_values) / n1
    mean2 = sum(post_values) / n2
    var1 = sum((x - mean1) ** 2 for x in pre_values) / (n1 - 1)
    var2 = sum((x - mean2) ** 2 for x in post_values) / (n2 - 1)

    se_sq = var1 / n1 + var2 / n2
    if se_sq <= 0:
        # Both groups have zero variance; if means differ, highly significant
        if abs(mean1 - mean2) > 1e-12:
            return 0.0
        return 1.0
    se = math.sqrt(se_sq)

    t_stat = (mean1 - mean2) / se

    # Welch-Satterthwaite degrees of freedom
    num = (var1 / n1 + var2 / n2) ** 2
    d1 = (var1 / n1) ** 2 / (n1 - 1) if var1 > 0 else 0
    d2 = (var2 / n2) ** 2 / (n2 - 1) if var2 > 0 else 0
    denom = d1 + d2
    if denom == 0:
        return 1.0
    df = num / denom

    # Approximate p-value using normal distribution for large df
    p_value = 2 * _normal_cdf(-abs(t_stat))
    return p_value


def _normal_cdf(x: float) -> float:
    """Approximation of standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def benjamini_hochberg(p_values: List[float], alpha: float = 0.05) -> List[bool]:
    """
    Benjamini-Hochberg FDR correction.

    Returns list of booleans indicating significance.
    """
    n = len(p_values)
    if n == 0:
        return []

    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    significant = [False] * n

    max_k = -1
    for rank, (orig_idx, p) in enumerate(indexed, 1):
        threshold = rank * alpha / n
        if p <= threshold:
            max_k = rank

    if max_k > 0:
        for rank, (orig_idx, p) in enumerate(indexed, 1):
            if rank <= max_k:
                significant[orig_idx] = True

    return significant


def run_contrast_analysis(
    patterns: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    events: List[MaintenanceEvent],
    n_transactions: int,
    window_size: int,
    lookback: int,
    item_map: Dict[int, List[int]],
    adapter=None,
    alpha: float = 0.05,
) -> List[ContrastResult]:
    """
    Run contrast analysis for all pattern-event pairs.

    Args:
        patterns: Dense patterns from mining
        events: Maintenance events
        n_transactions: Total number of transactions
        window_size: Window size used for mining
        lookback: Pre/post window for contrast
        item_map: Item -> transaction map
        adapter: AlarmAdapter for decoding (optional)
        alpha: Significance level for BH correction

    Returns:
        List of ContrastResult (significant results only)
    """
    all_results: List[ContrastResult] = []
    all_p_values: List[float] = []

    for pattern, intervals in patterns.items():
        if len(pattern) < 2:
            continue

        # Compute co-occurrence timestamps
        co_timestamps = item_map.get(pattern[0], [])
        for item in pattern[1:]:
            other = item_map.get(item, [])
            merged = []
            i = j = 0
            while i < len(co_timestamps) and j < len(other):
                if co_timestamps[i] == other[j]:
                    merged.append(co_timestamps[i])
                    i += 1
                    j += 1
                elif co_timestamps[i] < other[j]:
                    i += 1
                else:
                    j += 1
            co_timestamps = merged

        support_series = compute_support_time_series(
            co_timestamps, n_transactions, window_size
        )

        for event in events:
            pre_mean, post_mean, delta = compute_density_change(
                support_series, event.timestamp, lookback
            )

            pre_start = max(0, event.timestamp - lookback)
            pre_values = [float(x) for x in support_series[pre_start:event.timestamp]]
            post_end = min(n_transactions, event.timestamp + lookback)
            post_values = [float(x) for x in support_series[event.timestamp:post_end]]

            p_value = welch_t_test(pre_values, post_values)

            # Classify change
            if delta < -0.5:
                classification = "resolved"
            elif delta > 0.5:
                classification = "introduced"
            else:
                classification = "stable"

            # Check equipment group overlap
            equipment_related = False
            if adapter is not None:
                pattern_groups = adapter.get_equipment_groups(pattern)
                equipment_related = event.equipment_group in pattern_groups

            result = ContrastResult(
                pattern=pattern,
                event_id=event.event_id,
                event_timestamp=event.timestamp,
                pre_mean=pre_mean,
                post_mean=post_mean,
                delta=delta,
                p_value=p_value,
                classification=classification,
                equipment_related=equipment_related,
            )
            all_results.append(result)
            all_p_values.append(p_value)

    # Apply BH correction
    if all_p_values:
        significant = benjamini_hochberg(all_p_values, alpha)
        significant_results = [r for r, s in zip(all_results, significant) if s]
    else:
        significant_results = []

    return significant_results


def summarize_results(
    results: List[ContrastResult],
) -> Dict[str, int]:
    """Summarize contrast results by classification."""
    summary = {"resolved": 0, "introduced": 0, "stable": 0, "total": 0}
    for r in results:
        summary[r.classification] += 1
        summary["total"] += 1
    return summary
