"""
Tests for Rare Dense Pattern Miner.

Categories:
  - Normal cases (5+): basic functionality
  - Boundary cases (3+): edge parameters
  - Error / degenerate cases (2+): empty inputs, impossible thresholds
"""

import sys
from pathlib import Path

import pytest

# Ensure the implementation module is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rare_dense_miner import (
    compute_global_support,
    compute_global_support_count,
    compute_item_transaction_map,
    mine_rare_dense_patterns,
    mine_rare_dense_patterns_detailed,
    phase1_find_locally_dense,
    phase2_filter_rare,
)


# ---------------------------------------------------------------------------
# Helper: generate synthetic transactions
# ---------------------------------------------------------------------------

def make_transactions_with_rare_dense_pattern(
    n: int = 100,
    rare_items: tuple = (90, 91),
    burst_start: int = 40,
    burst_end: int = 50,
    common_items: tuple = (1, 2, 3),
) -> list:
    """
    Create n transactions where:
    - common_items appear in every transaction (globally frequent)
    - rare_items appear ONLY in [burst_start, burst_end) (globally rare, locally dense)
    """
    txns = []
    for t in range(n):
        txn = list(common_items)
        if burst_start <= t < burst_end:
            txn.extend(rare_items)
        txns.append(txn)
    return txns


# ===========================================================================
# Normal cases
# ===========================================================================

class TestNormalCases:
    """Normal operation: verify that rare dense patterns are correctly identified."""

    def test_basic_rare_dense_detection(self):
        """Items 90,91 appear only in t=40..49 (10/100 = 10% support).
        With max_sup=0.15, theta=3, W=5, they should be rare dense."""
        txns = make_transactions_with_rare_dense_pattern(
            n=100, rare_items=(90, 91), burst_start=40, burst_end=50
        )
        result = mine_rare_dense_patterns(
            txns, window_size=5, theta=3, max_sup=0.15, max_length=4
        )
        # The pair (90, 91) should be found as a rare dense pattern
        assert (90, 91) in result
        assert len(result[(90, 91)]) > 0

    def test_common_items_filtered_out(self):
        """Items 1,2,3 appear in every transaction -> gsupp=1.0 -> filtered by rarity."""
        txns = make_transactions_with_rare_dense_pattern(n=100)
        result = mine_rare_dense_patterns(
            txns, window_size=5, theta=3, max_sup=0.15, max_length=4
        )
        # Common items should NOT be in the result (gsupp = 1.0)
        assert (1, 2) not in result
        assert (1, 3) not in result
        assert (2, 3) not in result
        assert (1, 2, 3) not in result

    def test_multiple_rare_dense_patterns(self):
        """Two separate rare dense patterns in different time periods."""
        txns = []
        for t in range(200):
            txn = [1]  # common item
            if 20 <= t < 30:
                txn.extend([50, 51])  # burst 1
            if 150 <= t < 160:
                txn.extend([60, 61])  # burst 2
            txns.append(txn)

        result = mine_rare_dense_patterns(
            txns, window_size=5, theta=3, max_sup=0.10, max_length=3
        )
        assert (50, 51) in result
        assert (60, 61) in result

    def test_detailed_output_stats(self):
        """Verify the detailed output contains correct statistics."""
        txns = make_transactions_with_rare_dense_pattern(n=100)
        detail = mine_rare_dense_patterns_detailed(
            txns, window_size=5, theta=3, max_sup=0.15, max_length=4
        )
        assert "rare_dense" in detail
        assert "locally_dense" in detail
        assert "stats" in detail
        assert detail["stats"]["n_transactions"] == 100
        assert detail["stats"]["n_rare_dense"] <= detail["stats"]["n_locally_dense"]
        assert detail["stats"]["n_filtered_out"] >= 0

    def test_singleton_rare_dense(self):
        """A single item can be a rare dense pattern."""
        txns = []
        for t in range(100):
            txn = [1]  # always present
            if 30 <= t < 38:
                txn.append(99)  # 8% support, but dense in window
            txns.append(txn)

        result = mine_rare_dense_patterns(
            txns, window_size=5, theta=3, max_sup=0.10, max_length=2
        )
        assert (99,) in result

    def test_dense_intervals_correct(self):
        """Verify the returned dense intervals are in the correct range."""
        txns = make_transactions_with_rare_dense_pattern(
            n=100, rare_items=(90, 91), burst_start=40, burst_end=50
        )
        result = mine_rare_dense_patterns(
            txns, window_size=5, theta=3, max_sup=0.15, max_length=3
        )
        intervals = result[(90, 91)]
        for s, e in intervals:
            assert s >= 35  # earliest possible window start
            assert e <= 50  # latest possible window end


# ===========================================================================
# Boundary cases
# ===========================================================================

class TestBoundaryCases:
    """Test boundary conditions for parameters."""

    def test_exact_threshold_support(self):
        """Pattern with gsupp exactly at max_sup should be excluded (strict <)."""
        # 10 occurrences in 100 transactions = 0.10
        txns = make_transactions_with_rare_dense_pattern(
            n=100, rare_items=(90,), burst_start=0, burst_end=10
        )
        result = mine_rare_dense_patterns(
            txns, window_size=5, theta=3, max_sup=0.10, max_length=2
        )
        # gsupp = 10/100 = 0.10, max_sup = 0.10, condition is strict <
        assert (90,) not in result

    def test_just_below_threshold(self):
        """Pattern with gsupp just below max_sup should be included."""
        txns = make_transactions_with_rare_dense_pattern(
            n=100, rare_items=(90,), burst_start=0, burst_end=9
        )
        result = mine_rare_dense_patterns(
            txns, window_size=5, theta=3, max_sup=0.10, max_length=2
        )
        # gsupp = 9/100 = 0.09 < 0.10
        assert (90,) in result

    def test_window_equals_burst_length(self):
        """When window size equals the burst length, singletons and pair should be found."""
        txns = []
        for t in range(50):
            txn = []
            if 20 <= t < 30:
                txn = [10, 11]
            else:
                txn = [1]
            txns.append(txn)

        result = mine_rare_dense_patterns(
            txns, window_size=5, theta=3, max_sup=0.25, max_length=3
        )
        # 10 occurrences in 50 transactions = 20% support < 25% max_sup
        # Dense in a window of 5 with theta=3
        assert (10, 11) in result


# ===========================================================================
# Error / degenerate cases
# ===========================================================================

class TestDegenerateCases:
    """Test degenerate inputs and edge cases."""

    def test_empty_transactions(self):
        """Empty transaction list should return empty result."""
        result = mine_rare_dense_patterns(
            [], window_size=5, theta=3, max_sup=0.15, max_length=3
        )
        assert result == {}

    def test_no_rare_patterns(self):
        """When all patterns are frequent, result should be empty."""
        txns = [[1, 2, 3]] * 100  # all identical
        result = mine_rare_dense_patterns(
            txns, window_size=5, theta=3, max_sup=0.05, max_length=3
        )
        # All items have gsupp = 1.0, nothing is rare
        assert len(result) == 0
