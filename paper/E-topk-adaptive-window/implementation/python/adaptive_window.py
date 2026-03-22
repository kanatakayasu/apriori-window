"""
Multi-scale dense interval computation with dyadic scale hierarchy.

Computes dense intervals at multiple window sizes W_0, 2*W_0, 4*W_0, ...
and aggregates results across the scale hierarchy.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from typing import Dict, List, Optional, Sequence, Tuple


def compute_dense_intervals(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
) -> List[Tuple[int, int]]:
    """
    Compute dense intervals using sliding window.

    A dense interval [a, b] means for all t in [a, b],
    the count of timestamps in [t, t+window_size] >= threshold.

    Returns list of (start, end) tuples.
    """
    if window_size < 1 or threshold < 1:
        raise ValueError("window_size and threshold must be >= 1.")
    if not timestamps:
        return []

    ts = list(timestamps)
    intervals: List[Tuple[int, int]] = []
    l: Optional[int] = ts[0]
    in_dense = False
    start: Optional[int] = None
    end: Optional[int] = None

    while l is not None and l <= ts[-1]:
        start_idx = bisect_left(ts, l)
        end_idx = bisect_right(ts, l + window_size)
        count = end_idx - start_idx
        window_occurrences = ts[start_idx:end_idx]

        if count < threshold:
            if in_dense and start is not None and end is not None:
                intervals.append((start, end))
            in_dense = False
            start = None
            end = None
            next_idx = bisect_right(ts, l)
            l = ts[next_idx] if next_idx < len(ts) else None
            continue

        if count == threshold:
            if not in_dense:
                in_dense = True
                surplus = count - threshold
                right_from = window_occurrences[count - 1 - surplus]
                start = right_from - window_size
                end = l
            else:
                if end is not None:
                    end = max(end, l)
            l += 1
            continue

        # count > threshold
        if not in_dense:
            in_dense = True
            surplus = count - threshold
            right_from = window_occurrences[count - 1 - surplus]
            start = right_from - window_size
            end = l
        else:
            if end is not None:
                end = max(end, l)

        surplus = count - threshold
        next_l = window_occurrences[surplus]
        if next_l > l:
            l = next_l
        else:
            l += 1

    if in_dense and start is not None and end is not None:
        intervals.append((start, end))

    return intervals


def compute_support_at_positions(
    timestamps: Sequence[int],
    window_size: int,
    positions: Sequence[int],
) -> List[int]:
    """Compute support (count in window) at given positions."""
    ts = list(timestamps)
    result = []
    for t in positions:
        start_idx = bisect_left(ts, t)
        end_idx = bisect_right(ts, t + window_size)
        result.append(end_idx - start_idx)
    return result


def compute_dense_coverage_score(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
) -> Tuple[float, List[Tuple[int, int]]]:
    """
    Compute Dense Coverage Score (DCS) for given timestamps.

    DCS = sum over all dense intervals [a,b] of sum_{t=a}^{b} s(t)

    Returns (score, intervals).
    """
    intervals = compute_dense_intervals(timestamps, window_size, threshold)
    if not intervals:
        return 0.0, []

    ts = list(timestamps)
    total_score = 0.0
    for a, b in intervals:
        for t in range(a, b + 1):
            start_idx = bisect_left(ts, t)
            end_idx = bisect_right(ts, t + window_size)
            total_score += (end_idx - start_idx)

    return total_score, intervals


def dyadic_scale_hierarchy(
    w0: int,
    n: int,
) -> List[Tuple[int, int, int]]:
    """
    Generate dyadic scale hierarchy.

    Returns list of (level, window_size, threshold) tuples.
    The threshold maintains constant density ratio theta_0 / W_0.
    """
    if w0 < 1 or n < 1:
        raise ValueError("w0 and n must be >= 1.")

    max_level = int(math.log2(max(1, n // w0)))
    levels = []
    for ell in range(max_level + 1):
        w = (2 ** ell) * w0
        if w > n:
            break
        levels.append((ell, w, ell))  # threshold multiplier stored separately
    return levels


def compute_multiscale_dcs(
    timestamps: Sequence[int],
    w0: int,
    theta0: int,
    n: int,
    weights: Optional[Sequence[float]] = None,
) -> Tuple[float, Dict[int, List[Tuple[int, int]]]]:
    """
    Compute Multi-Scale Dense Coverage Score (MSDCS).

    MSDCS = sum_ell omega_ell * DCS(P, W_ell, theta_ell)

    Args:
        timestamps: sorted occurrence positions
        w0: base window size
        theta0: base threshold
        n: total number of transactions
        weights: per-level weights (default: uniform)

    Returns:
        (total_msdcs, {level: intervals})
    """
    max_level = max(0, int(math.log2(max(1, n // w0))))
    num_levels = 0
    level_params: List[Tuple[int, int, int]] = []  # (level, W, theta)

    for ell in range(max_level + 1):
        w = (2 ** ell) * w0
        if w > n:
            break
        theta = max(1, math.ceil(theta0 * (2 ** ell)))
        level_params.append((ell, w, theta))
        num_levels += 1

    if num_levels == 0:
        return 0.0, {}

    if weights is None:
        w_arr = [1.0 / num_levels] * num_levels
    else:
        w_arr = list(weights[:num_levels])
        while len(w_arr) < num_levels:
            w_arr.append(0.0)

    total_msdcs = 0.0
    all_intervals: Dict[int, List[Tuple[int, int]]] = {}

    for i, (ell, w, theta) in enumerate(level_params):
        dcs, intervals = compute_dense_coverage_score(timestamps, w, theta)
        total_msdcs += w_arr[i] * dcs
        all_intervals[ell] = intervals

    return total_msdcs, all_intervals
