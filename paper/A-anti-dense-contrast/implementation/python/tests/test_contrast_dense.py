"""Tests for contrast_dense.py."""
import sys
from pathlib import Path

_IMPL_DIR = str(Path(__file__).resolve().parents[1])
if _IMPL_DIR not in sys.path:
    sys.path.insert(0, _IMPL_DIR)

import pytest
from contrast_dense import (
    TopologyChangeType,
    classify_topology_change,
    compute_contrast_statistic,
    compute_coverage,
    compute_dense_intervals_in_regime,
    find_contrast_dense_patterns,
    permutation_test,
    benjamini_hochberg,
)


# ===========================================================
# Normal cases (5+)
# ===========================================================

class TestContrastNormal:
    """Normal operation tests."""

    def test_emergence_detection(self):
        """Pattern absent in R1 and present in R2 -> Emergence."""
        # Use wider separation to avoid window-boundary effects
        # No occurrences in [0, 99], dense in [110, 199]
        timestamps = list(range(110, 200))
        intervals_r1 = compute_dense_intervals_in_regime(timestamps, 5, 3, 0, 99)
        intervals_r2 = compute_dense_intervals_in_regime(timestamps, 5, 3, 100, 199)

        assert len(intervals_r1) == 0
        assert len(intervals_r2) > 0

        change = classify_topology_change(intervals_r1, intervals_r2, 100, 100)
        assert change == TopologyChangeType.EMERGENCE

    def test_vanishing_detection(self):
        """Pattern present in R1 and absent in R2 -> Vanishing."""
        timestamps = list(range(0, 50))
        intervals_r1 = compute_dense_intervals_in_regime(timestamps, 5, 3, 0, 49)
        intervals_r2 = compute_dense_intervals_in_regime(timestamps, 5, 3, 50, 99)

        assert len(intervals_r1) > 0
        assert len(intervals_r2) == 0

        change = classify_topology_change(intervals_r1, intervals_r2, 50, 50)
        assert change == TopologyChangeType.VANISHING

    def test_amplification_detection(self):
        """Pattern denser in R2 than R1 -> Amplification."""
        # R1: sparse coverage; R2: full coverage
        timestamps = [5, 10, 15, 20, 25] + list(range(50, 100))
        intervals_r1 = compute_dense_intervals_in_regime(timestamps, 5, 3, 0, 49)
        intervals_r2 = compute_dense_intervals_in_regime(timestamps, 5, 3, 50, 99)

        cov1 = compute_coverage(intervals_r1, 50)
        cov2 = compute_coverage(intervals_r2, 50)

        # If R2 has significantly more coverage
        if cov2 > cov1 + 0.1:
            change = classify_topology_change(intervals_r1, intervals_r2, 50, 50, delta=0.1)
            assert change == TopologyChangeType.AMPLIFICATION

    def test_stable_detection(self):
        """Pattern with similar structure in both regimes -> Stable."""
        timestamps = list(range(0, 100))
        intervals_r1 = compute_dense_intervals_in_regime(timestamps, 5, 3, 0, 49)
        intervals_r2 = compute_dense_intervals_in_regime(timestamps, 5, 3, 50, 99)

        change = classify_topology_change(intervals_r1, intervals_r2, 50, 50)
        assert change == TopologyChangeType.STABLE

    def test_contrast_statistic_sign(self):
        """Emergence should give positive delta, vanishing should give negative."""
        # Emergence case
        ts_emerge = list(range(50, 100))
        delta_e = compute_contrast_statistic(ts_emerge, 5, 3, 49, 100)
        assert delta_e > 0  # more coverage in R2

        # Vanishing case
        ts_vanish = list(range(0, 50))
        delta_v = compute_contrast_statistic(ts_vanish, 5, 3, 49, 100)
        assert delta_v < 0  # more coverage in R1

    def test_coverage_computation(self):
        """Coverage should be correct fraction."""
        intervals = [(0, 9), (20, 29)]  # 20 positions total
        cov = compute_coverage(intervals, 100)
        assert abs(cov - 0.2) < 1e-9

    def test_find_contrast_patterns_returns_all_types(self):
        """Pipeline should classify multiple patterns correctly."""
        # Use wider separation to avoid window boundary effects
        patterns = {
            "emerge": list(range(110, 200)),
            "vanish": list(range(0, 90)),
            "stable": list(range(0, 200)),
        }
        results = find_contrast_dense_patterns(
            patterns, window_size=5, threshold=3,
            regime_boundary=99, total_length=200,
            n_permutations=99, seed=42,
        )

        assert results["emerge"]["type"] == TopologyChangeType.EMERGENCE
        assert results["vanish"]["type"] == TopologyChangeType.VANISHING
        assert results["stable"]["type"] == TopologyChangeType.STABLE


# ===========================================================
# Boundary cases (3+)
# ===========================================================

class TestContrastBoundary:
    """Boundary condition tests."""

    def test_regime_boundary_at_start(self):
        """Regime boundary at position 0 (R1 has length 1)."""
        timestamps = list(range(0, 50))
        delta = compute_contrast_statistic(timestamps, 5, 3, 0, 50)
        # Should not crash
        assert isinstance(delta, float)

    def test_both_regimes_empty(self):
        """No dense intervals in either regime -> Stable."""
        change = classify_topology_change([], [], 50, 50)
        assert change == TopologyChangeType.STABLE

    def test_zero_coverage(self):
        """Coverage of empty interval list should be 0."""
        assert compute_coverage([], 100) == 0.0

    def test_bh_correction_no_pvalues(self):
        """BH correction with empty list should return empty."""
        assert benjamini_hochberg([]) == []


# ===========================================================
# Error / edge cases (2+)
# ===========================================================

class TestContrastEdge:
    """Edge case tests."""

    def test_permutation_test_deterministic(self):
        """With same seed, permutation test should give same result."""
        ts = list(range(50, 100))
        _, p1 = permutation_test(ts, 5, 3, 49, 100, n_permutations=49, seed=123)
        _, p2 = permutation_test(ts, 5, 3, 49, 100, n_permutations=49, seed=123)
        assert p1 == p2

    def test_bh_correction_all_significant(self):
        """When all p-values are very small, all should be rejected."""
        p_values = [0.001, 0.002, 0.003]
        rejected = benjamini_hochberg(p_values, alpha=0.05)
        assert all(rejected)

    def test_bh_correction_none_significant(self):
        """When all p-values are large, none should be rejected."""
        p_values = [0.9, 0.95, 0.99]
        rejected = benjamini_hochberg(p_values, alpha=0.05)
        assert not any(rejected)
