"""
Anti-Dense Interval Detection.

Computes anti-dense intervals: maximal contiguous ranges [s, e] where
the sliding-window support count is strictly below a low threshold.

This is the symmetric dual of dense interval detection from
apriori_window_basket.py — the threshold crossing direction is reversed.
"""

import sys
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# Import the existing dense interval detector for comparison/composition
_SUITE_DIR = str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python")
if _SUITE_DIR not in sys.path:
    sys.path.insert(0, _SUITE_DIR)

from apriori_window_basket import compute_dense_intervals  # noqa: E402


def compute_anti_dense_intervals(
    timestamps: Sequence[int],
    window_size: int,
    threshold_low: int,
) -> List[Tuple[int, int]]:
    """
    Compute anti-dense intervals for a pattern.

    An anti-dense interval [s, e] is a maximal contiguous range of
    window-start positions where the support count is strictly below
    threshold_low.

    Parameters
    ----------
    timestamps : sorted list of occurrence timestamps (transaction IDs)
    window_size : W, the sliding window width
    threshold_low : theta_low; support < theta_low triggers anti-dense

    Returns
    -------
    List of (start, end) tuples representing anti-dense intervals.
    The intervals are in the space of window-start positions [0, max_t].
    """
    if window_size < 1 or threshold_low < 1:
        raise ValueError("window_size and threshold_low must be >= 1.")

    if not timestamps:
        # No occurrences at all — the entire range is anti-dense
        return []  # But we have no range information, so return empty

    ts = list(timestamps)
    # The range of possible window starts is [0, ts[-1]]
    # But we only need to check positions where count can change,
    # which are around the timestamps themselves.
    # We scan through all critical positions.

    max_pos = ts[-1]  # last possible meaningful window start

    intervals: List[Tuple[int, int]] = []
    in_anti_dense = False
    start: Optional[int] = None

    # We need to evaluate support at every position from 0 to max_pos.
    # For efficiency, we identify critical points where the count changes:
    # these are at each timestamp t and at each t - window_size.
    critical_points = set()
    for t in ts:
        critical_points.add(t)
        if t - window_size >= 0:
            critical_points.add(t - window_size)
        critical_points.add(t + 1)  # just after a timestamp
        if t - window_size + 1 >= 0:
            critical_points.add(t - window_size + 1)
    # Add boundaries
    critical_points.add(0)
    critical_points.add(max_pos)

    # Filter to valid range and sort
    sorted_cps = sorted(cp for cp in critical_points if 0 <= cp <= max_pos)

    prev_pos = -2  # sentinel

    for i, pos in enumerate(sorted_cps):
        # Count occurrences in [pos, pos + window_size)
        start_idx = bisect_left(ts, pos)
        end_idx = bisect_right(ts, pos + window_size - 1)
        count = end_idx - start_idx

        if count < threshold_low:
            if not in_anti_dense:
                in_anti_dense = True
                start = pos
            # Extend: the anti-dense region continues until next critical point
        else:
            if in_anti_dense and start is not None:
                # End the anti-dense interval at the position before this one
                end_pos = pos - 1
                if end_pos >= start:
                    intervals.append((start, end_pos))
                in_anti_dense = False
                start = None

    # Close any open anti-dense interval
    if in_anti_dense and start is not None:
        intervals.append((start, max_pos))

    return intervals


def compute_anti_dense_intervals_range(
    timestamps: Sequence[int],
    window_size: int,
    threshold_low: int,
    range_start: int,
    range_end: int,
) -> List[Tuple[int, int]]:
    """
    Compute anti-dense intervals within a specified range [range_start, range_end].

    This is useful for regime-restricted anti-dense interval computation.

    Parameters
    ----------
    timestamps : sorted list of occurrence timestamps
    window_size : W
    threshold_low : theta_low
    range_start : start of the range to analyze
    range_end : end of the range to analyze

    Returns
    -------
    List of (start, end) tuples of anti-dense intervals within the range.
    """
    if window_size < 1 or threshold_low < 1:
        raise ValueError("window_size and threshold_low must be >= 1.")

    if range_start > range_end:
        return []

    ts = list(timestamps)

    intervals: List[Tuple[int, int]] = []
    in_anti_dense = False
    start: Optional[int] = None

    # Critical points within the range
    critical_points = set()
    for t in ts:
        critical_points.add(t)
        if t - window_size >= 0:
            critical_points.add(t - window_size)
        critical_points.add(t + 1)
        if t - window_size + 1 >= 0:
            critical_points.add(t - window_size + 1)
    critical_points.add(range_start)
    critical_points.add(range_end)

    sorted_cps = sorted(cp for cp in critical_points if range_start <= cp <= range_end)

    for pos in sorted_cps:
        start_idx = bisect_left(ts, pos)
        end_idx = bisect_right(ts, pos + window_size - 1)
        count = end_idx - start_idx

        if count < threshold_low:
            if not in_anti_dense:
                in_anti_dense = True
                start = pos
        else:
            if in_anti_dense and start is not None:
                end_pos = pos - 1
                if end_pos >= start:
                    intervals.append((start, end_pos))
                in_anti_dense = False
                start = None

    if in_anti_dense and start is not None:
        intervals.append((start, range_end))

    return intervals


def compute_support_series(
    timestamps: Sequence[int],
    window_size: int,
    range_start: int,
    range_end: int,
) -> List[int]:
    """
    Compute the support time series s_P(t) for t in [range_start, range_end].

    s_P(t) = |{j in timestamps : t <= j < t + W}|

    Parameters
    ----------
    timestamps : sorted occurrence timestamps
    window_size : W
    range_start : start position
    range_end : end position

    Returns
    -------
    List of support counts, one per position in [range_start, range_end].
    """
    ts = list(timestamps)
    series = []
    for t in range(range_start, range_end + 1):
        start_idx = bisect_left(ts, t)
        end_idx = bisect_right(ts, t + window_size - 1)
        series.append(end_idx - start_idx)
    return series
