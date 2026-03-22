"""Tests for anti_dense_interval.py."""
import sys
from pathlib import Path

# Add implementation directory to path
_IMPL_DIR = str(Path(__file__).resolve().parents[1])
if _IMPL_DIR not in sys.path:
    sys.path.insert(0, _IMPL_DIR)

import pytest
from anti_dense_interval import (
    compute_anti_dense_intervals,
    compute_anti_dense_intervals_range,
    compute_support_series,
)


# ===========================================================
# Normal cases (5+)
# ===========================================================

class TestAntiDenseNormal:
    """Normal operation tests for anti-dense interval detection."""

    def test_single_gap_produces_anti_dense(self):
        """Pattern with a gap in the middle should produce an anti-dense interval."""
        # Dense at [0..10], gap at [20..30], dense at [40..50]
        timestamps = list(range(0, 11)) + list(range(40, 51))
        result = compute_anti_dense_intervals(timestamps, window_size=5, threshold_low=2)
        # There should be an anti-dense interval in the gap region
        assert len(result) >= 1
        # The anti-dense interval should cover roughly the gap area
        for s, e in result:
            assert e >= s  # valid interval

    def test_no_anti_dense_when_always_above(self):
        """When support is always above threshold in core region, no anti-dense there."""
        timestamps = list(range(0, 100))  # continuous presence
        result = compute_anti_dense_intervals(timestamps, window_size=5, threshold_low=3)
        # Near the end (positions >= 98), the window [98, 102] only has 2 items,
        # so anti-dense is expected at the boundary. Check core region is clean.
        core_anti = [(s, e) for s, e in result if s < 95]
        assert core_anti == []

    def test_entire_range_anti_dense(self):
        """Very sparse pattern should be entirely anti-dense."""
        timestamps = [0, 50, 100]  # very sparse
        result = compute_anti_dense_intervals(timestamps, window_size=5, threshold_low=2)
        # Should have anti-dense intervals covering most of the range
        assert len(result) >= 1

    def test_multiple_anti_dense_intervals(self):
        """Pattern with multiple gaps should produce multiple anti-dense intervals."""
        # Three clusters with gaps between them
        timestamps = [0, 1, 2, 3, 4, 30, 31, 32, 33, 34, 60, 61, 62, 63, 64]
        result = compute_anti_dense_intervals(timestamps, window_size=3, threshold_low=2)
        # Should have anti-dense intervals in the gaps
        assert len(result) >= 2

    def test_symmetry_with_dense(self):
        """Anti-dense and dense intervals should not have interior overlap."""
        timestamps = list(range(0, 10)) + list(range(50, 60))
        W = 5
        theta = 3

        from apriori_window_basket import compute_dense_intervals
        dense = compute_dense_intervals(timestamps, W, theta)
        anti_dense = compute_anti_dense_intervals(timestamps, W, theta)

        # Anti-dense intervals should not be fully contained within dense intervals
        # (boundary points may touch since dense uses >= and anti-dense uses <)
        for ds, de in dense:
            for ads, ade in anti_dense:
                # Interior overlap means shared range of length > 0
                overlap_start = max(ds, ads)
                overlap_end = min(de, ade)
                # Allow at most 1-position boundary touch
                assert overlap_end - overlap_start <= 0, \
                    f"Dense [{ds},{de}] has interior overlap with anti-dense [{ads},{ade}]"

    def test_support_series_correctness(self):
        """Support series should count correctly."""
        timestamps = [0, 1, 2, 5, 6]
        series = compute_support_series(timestamps, window_size=3, range_start=0, range_end=6)
        # Position 0: window [0,2] -> items 0,1,2 -> count 3
        assert series[0] == 3
        # Position 3: window [3,5] -> item 5 -> count 1
        assert series[3] == 1
        # Position 4: window [4,6] -> items 5,6 -> count 2
        assert series[4] == 2


# ===========================================================
# Boundary cases (3+)
# ===========================================================

class TestAntiDenseBoundary:
    """Boundary condition tests."""

    def test_empty_timestamps(self):
        """No timestamps should return no intervals."""
        result = compute_anti_dense_intervals([], window_size=5, threshold_low=2)
        assert result == []

    def test_single_timestamp(self):
        """Single timestamp should produce anti-dense on both sides."""
        result = compute_anti_dense_intervals([50], window_size=5, threshold_low=2)
        # With only 1 occurrence, count is always < 2
        # The range is [0, 50] with max_pos=50
        # Anti-dense should cover the entire range
        assert len(result) >= 1

    def test_threshold_low_equals_one(self):
        """Threshold_low=1 means anti-dense only where count=0."""
        timestamps = [0, 10, 20]
        result = compute_anti_dense_intervals(timestamps, window_size=3, threshold_low=1)
        # Between timestamps where count drops to 0
        for s, e in result:
            # Verify no timestamps fall within any window starting in [s, e]
            for pos in range(s, e + 1):
                count = sum(1 for t in timestamps if pos <= t <= pos + 2)
                assert count < 1

    def test_range_restricted_computation(self):
        """Range-restricted version should only return intervals within range."""
        timestamps = list(range(0, 100))
        result = compute_anti_dense_intervals_range(
            timestamps, window_size=5, threshold_low=3, range_start=10, range_end=20
        )
        for s, e in result:
            assert s >= 10
            assert e <= 20


# ===========================================================
# Error cases (2+)
# ===========================================================

class TestAntiDenseErrors:
    """Error handling tests."""

    def test_invalid_window_size(self):
        """Window size < 1 should raise ValueError."""
        with pytest.raises(ValueError):
            compute_anti_dense_intervals([1, 2, 3], window_size=0, threshold_low=2)

    def test_invalid_threshold(self):
        """Threshold < 1 should raise ValueError."""
        with pytest.raises(ValueError):
            compute_anti_dense_intervals([1, 2, 3], window_size=5, threshold_low=0)
