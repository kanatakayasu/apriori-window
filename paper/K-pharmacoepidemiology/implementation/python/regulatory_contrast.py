"""
Regulatory event contrast analysis.

Detects prescription pattern changes around regulatory events
(FDA safety alerts, drug withdrawals, label changes) by comparing
support levels in pre-event vs post-event windows.
"""

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from pharma_dense_miner import compute_support_time_series


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
    classification: str  # 'disappearing', 'emerging', 'stable'
    targeted: bool  # whether pattern overlaps with event-targeted drugs


def compute_density_change(
    support_series: Sequence[int],
    event_time: int,
    lookback: int,
) -> Tuple[float, float, float]:
    """
    Compute pre/post mean support and density change score.

    Args:
        support_series: Support time series s_P(t)
        event_time: Regulatory event time index
        lookback: Number of time steps before/after event to consider

    Returns:
        (pre_mean, post_mean, delta)
    """
    n = len(support_series)
    if n == 0:
        return 0.0, 0.0, 0.0

    # Pre-event window
    pre_start = max(0, event_time - lookback)
    pre_end = event_time
    pre_values = support_series[pre_start:pre_end]

    # Post-event window
    post_start = event_time
    post_end = min(n, event_time + lookback)
    post_values = support_series[post_start:post_end]

    pre_mean = sum(pre_values) / max(1, len(pre_values))
    post_mean = sum(post_values) / max(1, len(post_values))
    delta = post_mean - pre_mean

    return pre_mean, post_mean, delta


def permutation_test(
    support_series: Sequence[int],
    event_time: int,
    lookback: int,
    n_permutations: int = 999,
    seed: Optional[int] = None,
) -> float:
    """
    Permutation test for density change significance.

    Tests H0: the observed density change at event_time is no greater
    than expected by chance.

    Args:
        support_series: Support time series
        event_time: Observed event time
        lookback: Window size for pre/post comparison
        n_permutations: Number of random permutations
        seed: Random seed for reproducibility

    Returns:
        p-value
    """
    rng = random.Random(seed)
    n = len(support_series)

    if n < 2 * lookback:
        return 1.0

    _, _, observed_delta = compute_density_change(
        support_series, event_time, lookback
    )
    observed_stat = abs(observed_delta)

    # Valid positions for random event placement
    valid_range = range(lookback, n - lookback)
    if not valid_range:
        return 1.0

    count_extreme = 0
    for _ in range(n_permutations):
        random_time = rng.choice(valid_range)
        _, _, perm_delta = compute_density_change(
            support_series, random_time, lookback
        )
        if abs(perm_delta) >= observed_stat:
            count_extreme += 1

    p_value = (1 + count_extreme) / (1 + n_permutations)
    return p_value


def benjamini_hochberg(
    p_values: List[float],
    alpha: float = 0.05,
) -> List[bool]:
    """
    Benjamini-Hochberg FDR correction.

    Args:
        p_values: List of raw p-values
        alpha: FDR control level

    Returns:
        List of booleans indicating rejection
    """
    m = len(p_values)
    if m == 0:
        return []

    # Sort by p-value
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    # Find BH threshold
    rejected = [False] * m
    max_k = -1
    for rank, (orig_idx, pval) in enumerate(indexed, start=1):
        if pval <= (rank / m) * alpha:
            max_k = rank

    if max_k > 0:
        for rank, (orig_idx, pval) in enumerate(indexed, start=1):
            if rank <= max_k:
                rejected[orig_idx] = True

    return rejected


def classify_pattern(
    delta: float,
    p_value: float,
    alpha: float,
    change_threshold: float,
    pattern: Tuple[int, ...],
    targeted_atc_ids: List[int],
) -> str:
    """
    Classify a pattern relative to a regulatory event.

    Returns: 'disappearing', 'emerging', or 'stable'
    """
    if p_value > alpha:
        return "stable"

    has_overlap = bool(set(pattern) & set(targeted_atc_ids))

    if delta < -change_threshold:
        return "disappearing"
    elif delta > change_threshold:
        return "emerging"
    else:
        return "stable"


def run_contrast_analysis(
    dense_patterns: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    item_transaction_map: Dict[int, List[int]],
    n_transactions: int,
    window_size: int,
    events: List[dict],
    atc_id_mapping: Dict[str, int],
    lookback: int = 100,
    n_permutations: int = 999,
    alpha: float = 0.05,
    change_threshold: float = 1.0,
    seed: int = 42,
) -> List[ContrastResult]:
    """
    Run full contrast analysis for all pattern-event pairs.

    Args:
        dense_patterns: Pattern -> dense intervals mapping
        item_transaction_map: Item -> transaction ID list
        n_transactions: Total number of transactions
        window_size: Sliding window size
        events: List of regulatory event dicts with keys:
            event_id, timestamp, targeted_atc
        atc_id_mapping: ATC code -> integer ID mapping
        lookback: Pre/post event window size
        n_permutations: Permutation test iterations
        alpha: FDR control level
        change_threshold: Minimum delta for classification
        seed: Random seed

    Returns:
        List of ContrastResult objects
    """
    results: List[ContrastResult] = []
    all_p_values: List[float] = []
    result_indices: List[Tuple[int, int]] = []  # (pattern_idx, event_idx)

    patterns = list(dense_patterns.keys())

    for pi, pattern in enumerate(patterns):
        # Compute co-occurrence timestamps
        if len(pattern) == 1:
            timestamps = item_transaction_map.get(pattern[0], [])
        else:
            id_lists = [item_transaction_map.get(item, []) for item in pattern]
            # Intersect sorted lists
            timestamps = id_lists[0] if id_lists else []
            for other in id_lists[1:]:
                merged = []
                i, j = 0, 0
                while i < len(timestamps) and j < len(other):
                    if timestamps[i] == other[j]:
                        merged.append(timestamps[i])
                        i += 1
                        j += 1
                    elif timestamps[i] < other[j]:
                        i += 1
                    else:
                        j += 1
                timestamps = merged

        support_series = compute_support_time_series(
            timestamps, n_transactions, window_size
        )

        for ei, event in enumerate(events):
            event_time = event["timestamp"]

            pre_mean, post_mean, delta = compute_density_change(
                support_series, event_time, lookback
            )

            p_value = permutation_test(
                support_series, event_time, lookback,
                n_permutations=n_permutations, seed=seed + pi * 1000 + ei
            )

            # Map targeted ATC codes to integer IDs
            targeted_ids = [
                atc_id_mapping[atc]
                for atc in event.get("targeted_atc", [])
                if atc in atc_id_mapping
            ]

            has_overlap = bool(set(pattern) & set(targeted_ids))

            classification = classify_pattern(
                delta, p_value, alpha, change_threshold,
                pattern, targeted_ids
            )

            results.append(ContrastResult(
                pattern=pattern,
                event_id=event["event_id"],
                event_timestamp=event_time,
                pre_mean=pre_mean,
                post_mean=post_mean,
                delta=delta,
                p_value=p_value,
                classification=classification,
                targeted=has_overlap,
            ))
            all_p_values.append(p_value)
            result_indices.append((pi, ei))

    # Apply BH correction
    if all_p_values:
        rejections = benjamini_hochberg(all_p_values, alpha)
        for idx, rejected in enumerate(rejections):
            if not rejected:
                results[idx].classification = "stable"

    return results


def summarize_results(results: List[ContrastResult]) -> Dict:
    """Summarize contrast analysis results."""
    summary = {
        "total_tests": len(results),
        "disappearing": sum(1 for r in results if r.classification == "disappearing"),
        "emerging": sum(1 for r in results if r.classification == "emerging"),
        "stable": sum(1 for r in results if r.classification == "stable"),
        "targeted_disappearing": sum(
            1 for r in results
            if r.classification == "disappearing" and r.targeted
        ),
        "non_targeted_emerging": sum(
            1 for r in results
            if r.classification == "emerging" and not r.targeted
        ),
        "significant_at_005": sum(1 for r in results if r.p_value < 0.05),
    }
    return summary
