"""
Tests for top-k dense pattern mining, adaptive window, and scale-space ridge detection.

Test categories:
  - Normal cases (5+): basic functionality
  - Boundary cases (3+): edge conditions
  - Error cases (2+): invalid inputs
"""

import sys
from pathlib import Path

# Add implementation directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import math
import pytest
from adaptive_window import (
    compute_dense_coverage_score,
    compute_dense_intervals,
    compute_multiscale_dcs,
    dyadic_scale_hierarchy,
)
from scale_space import (
    build_dense_indicator,
    detect_scale_space_ridges,
    find_ridges,
)
from topk_dense import (
    TopKResult,
    build_item_timestamps,
    compute_itemset_timestamps,
    intersect_sorted,
    mine_topk_dense,
    mine_topk_with_ridges,
)


# =====================================================================
# Helpers
# =====================================================================

def make_transactions(item_positions: dict, n: int) -> list:
    """Create transaction list from item -> positions mapping."""
    txns = [[] for _ in range(n)]
    for item, positions in item_positions.items():
        for pos in positions:
            if pos < n:
                txns[pos].append(item)
    return txns


# =====================================================================
# Normal Cases — adaptive_window
# =====================================================================

class TestDenseIntervalsNormal:
    def test_basic_dense_interval(self):
        """Dense interval detected when timestamps are concentrated."""
        ts = [0, 1, 2, 3, 4, 10, 11, 12, 13, 14]
        intervals = compute_dense_intervals(ts, window_size=5, threshold=4)
        assert len(intervals) >= 1
        # First cluster [0..4] should produce a dense interval
        assert any(s <= 0 and e >= 0 for s, e in intervals)

    def test_no_dense_interval_sparse(self):
        """No dense interval when timestamps are too sparse."""
        ts = [0, 10, 20, 30, 40]
        intervals = compute_dense_intervals(ts, window_size=3, threshold=3)
        assert intervals == []

    def test_dense_coverage_score_basic(self):
        """DCS accumulates support within dense intervals."""
        ts = [0, 1, 2, 3, 4]
        score, intervals = compute_dense_coverage_score(ts, window_size=5, threshold=3)
        assert score > 0
        assert len(intervals) >= 1

    def test_multiscale_dcs_increases_with_density(self):
        """Denser patterns get higher MSDCS."""
        dense_ts = list(range(20))  # very dense
        sparse_ts = list(range(0, 40, 4))  # sparse
        s_dense, _ = compute_multiscale_dcs(dense_ts, w0=5, theta0=3, n=40)
        s_sparse, _ = compute_multiscale_dcs(sparse_ts, w0=5, theta0=3, n=40)
        assert s_dense > s_sparse

    def test_dyadic_hierarchy_levels(self):
        """Dyadic hierarchy produces correct number of levels."""
        levels = dyadic_scale_hierarchy(w0=4, n=64)
        # log2(64/4) = 4, so levels 0..4
        assert len(levels) == 5
        assert levels[0][1] == 4   # W_0
        assert levels[1][1] == 8   # 2*W_0
        assert levels[2][1] == 16  # 4*W_0


# =====================================================================
# Normal Cases — scale_space
# =====================================================================

class TestScaleSpaceNormal:
    def test_build_dense_indicator(self):
        """Dense indicator matrix is correctly constructed."""
        ts = list(range(10))
        matrix, params = build_dense_indicator(ts, w0=3, theta0=2, n=10)
        assert len(matrix) >= 1
        # At level 0 (W=3, theta=2), many positions should be dense
        assert any(matrix[0])

    def test_find_ridges_single_level_rejected(self):
        """Single-level components are not ridges (min_levels=2)."""
        matrix = [[True, True, True], [False, False, False]]
        ridges = find_ridges(matrix, min_levels=2)
        assert len(ridges) == 0

    def test_find_ridges_multi_level(self):
        """Multi-level connected component detected as ridge."""
        matrix = [
            [False, True, True, False],
            [False, True, True, False],
        ]
        ridges = find_ridges(matrix, min_levels=2)
        assert len(ridges) == 1
        levels = set(c[0] for c in ridges[0])
        assert 0 in levels and 1 in levels

    def test_detect_ridges_end_to_end(self):
        """Full ridge detection pipeline produces results for dense data."""
        ts = list(range(20))
        ridges = detect_scale_space_ridges(ts, w0=3, theta0=2, n=20, min_levels=2)
        # Dense data should produce at least one ridge
        assert len(ridges) >= 1
        assert ridges[0]['level_span'] >= 2


# =====================================================================
# Normal Cases — topk_dense
# =====================================================================

class TestTopKDenseNormal:
    def test_topk_returns_k_patterns(self):
        """Top-k mining returns exactly k patterns when enough exist."""
        txns = make_transactions({
            1: list(range(0, 20)),
            2: list(range(0, 18)),
            3: list(range(0, 15)),
            4: list(range(5, 12)),
            5: list(range(10, 20)),
        }, n=20)
        results = mine_topk_dense(txns, k=3, w0=5, theta0=3, max_length=2)
        assert len(results) == 3

    def test_topk_scores_descending(self):
        """Results are sorted by MSDCS descending."""
        txns = make_transactions({
            1: list(range(20)),
            2: list(range(15)),
            3: list(range(10)),
        }, n=20)
        results = mine_topk_dense(txns, k=3, w0=5, theta0=3, max_length=1)
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_topk_bb_pruning_works(self):
        """B&B prunes patterns with low upper bounds."""
        # Item 1 dense, item 2 very sparse -> pair (1,2) should be pruned
        txns = make_transactions({
            1: list(range(30)),
            2: [0, 15, 29],
        }, n=30)
        results = mine_topk_dense(txns, k=1, w0=5, theta0=3, max_length=2)
        assert len(results) >= 1
        # Top pattern should be singleton (1,) not (1,2)
        assert len(results[0][0]) == 1

    def test_topk_with_ridges(self):
        """Ridge-enriched mining produces ridge data."""
        txns = make_transactions({
            1: list(range(20)),
            2: list(range(18)),
        }, n=20)
        results = mine_topk_with_ridges(txns, k=2, w0=3, theta0=2, max_length=2)
        assert len(results) >= 1
        assert 'ridges' in results[0]
        assert 'msdcs' in results[0]

    def test_intersect_sorted(self):
        """Sorted list intersection works correctly."""
        assert intersect_sorted([1, 3, 5, 7], [2, 3, 5, 8]) == [3, 5]
        assert intersect_sorted([], [1, 2]) == []
        assert intersect_sorted([1, 2, 3], [1, 2, 3]) == [1, 2, 3]


# =====================================================================
# Boundary Cases
# =====================================================================

class TestBoundaryCases:
    def test_single_transaction(self):
        """Single transaction still produces valid results."""
        txns = [[1, 2, 3]]
        results = mine_topk_dense(txns, k=1, w0=1, theta0=1, max_length=2)
        # With W=1 and theta=1, single occurrence is dense
        assert len(results) >= 1

    def test_k_larger_than_available(self):
        """When k > available patterns, returns all available."""
        txns = make_transactions({1: [0, 1, 2]}, n=3)
        results = mine_topk_dense(txns, k=100, w0=3, theta0=2, max_length=1)
        assert len(results) <= 100
        assert len(results) >= 1

    def test_empty_transactions(self):
        """Empty transaction list returns empty results."""
        results = mine_topk_dense([], k=5, w0=5, theta0=3, max_length=3)
        assert results == []

    def test_all_same_item(self):
        """All transactions contain same single item."""
        txns = [[1]] * 50
        results = mine_topk_dense(txns, k=1, w0=5, theta0=3, max_length=1)
        assert len(results) == 1
        assert results[0][0] == (1,)
        assert results[0][1] > 0

    def test_window_equals_n(self):
        """Window size equals total transactions."""
        ts = [0, 1, 2, 3, 4]
        intervals = compute_dense_intervals(ts, window_size=5, threshold=3)
        assert len(intervals) >= 1


# =====================================================================
# Error Cases
# =====================================================================

class TestErrorCases:
    def test_invalid_k(self):
        """k=0 raises ValueError."""
        with pytest.raises(ValueError):
            mine_topk_dense([[1]], k=0, w0=5, theta0=3)

    def test_invalid_window(self):
        """window_size=0 raises ValueError."""
        with pytest.raises(ValueError):
            compute_dense_intervals([0, 1, 2], window_size=0, threshold=1)

    def test_invalid_threshold(self):
        """threshold=0 raises ValueError."""
        with pytest.raises(ValueError):
            compute_dense_intervals([0, 1, 2], window_size=5, threshold=0)

    def test_invalid_w0(self):
        """w0=0 raises ValueError for mine_topk_dense."""
        with pytest.raises(ValueError):
            mine_topk_dense([[1, 2]], k=1, w0=0, theta0=1)


# =====================================================================
# TopKResult unit tests
# =====================================================================

class TestTopKResult:
    def test_basic_insert(self):
        """Inserting k items fills the heap."""
        tkr = TopKResult(3)
        tkr.try_insert(10.0, (1,))
        tkr.try_insert(20.0, (2,))
        tkr.try_insert(30.0, (3,))
        assert len(tkr.heap) == 3
        assert tkr.threshold == 10.0

    def test_threshold_update(self):
        """Threshold updates when better pattern replaces worst."""
        tkr = TopKResult(2)
        tkr.try_insert(5.0, (1,))
        tkr.try_insert(10.0, (2,))
        assert tkr.threshold == 5.0
        tkr.try_insert(15.0, (3,))
        assert tkr.threshold == 10.0

    def test_zero_score_rejected(self):
        """Score of 0 is not inserted."""
        tkr = TopKResult(5)
        assert not tkr.try_insert(0.0, (1,))
        assert len(tkr.heap) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
