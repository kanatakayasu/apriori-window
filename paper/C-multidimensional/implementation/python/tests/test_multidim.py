"""
Tests for multidim_dense.py and sweep_surface.py.

Test categories:
  - Normal cases (5+): basic functionality
  - Boundary cases (3+): edge conditions
  - Error/degenerate cases (2+): invalid inputs, empty data
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Add implementation directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from multidim_dense import (
    UnionFind,
    bounding_box,
    compute_support_surface_naive,
    extract_dense_regions,
    find_dense_itemsets_multidim,
    flat_to_multi_index,
    generate_synthetic_2d,
    grid_neighbors,
    multi_index_to_flat,
)
from sweep_surface import (
    check_decomposability,
    compute_support_surface_fast,
    mine_dense_regions_adaptive,
    sweep_surface_detect,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def simple_2d_data():
    """Simple 2D dataset: 20 transactions, 5 spatial positions."""
    transactions = []
    locations = []
    for t in range(20):
        x = t % 5
        txn = set()
        # Items 0,1 appear densely in t=[5,14], x=[1,3]
        if 5 <= t <= 14 and 1 <= x <= 3:
            txn.update([0, 1])
        # Background noise
        if t % 3 == 0:
            txn.add(2)
        transactions.append(txn)
        locations.append((x,))
    return transactions, locations


@pytest.fixture
def single_dense_block():
    """Perfectly axis-aligned dense block for decomposability testing."""
    transactions = []
    locations = []
    for t in range(30):
        x = t % 6
        txn = set()
        if 10 <= t <= 19 and 2 <= x <= 4:
            txn.add(0)
        transactions.append(txn)
        locations.append((x,))
    return transactions, locations


# ===========================================================================
# Normal cases
# ===========================================================================

class TestUnionFind:
    def test_basic_union_find(self):
        uf = UnionFind(5)
        uf.union(0, 1)
        uf.union(2, 3)
        assert uf.find(0) == uf.find(1)
        assert uf.find(2) == uf.find(3)
        assert uf.find(0) != uf.find(2)

    def test_transitive_union(self):
        uf = UnionFind(4)
        uf.union(0, 1)
        uf.union(1, 2)
        assert uf.find(0) == uf.find(2)

    def test_components(self):
        uf = UnionFind(6)
        uf.union(0, 1)
        uf.union(1, 2)
        uf.union(3, 4)
        comps = uf.components({0, 1, 2, 3, 4, 5})
        assert len(comps) == 3  # {0,1,2}, {3,4}, {5}


class TestGridUtilities:
    def test_flat_roundtrip(self):
        shape = (3, 4, 5)
        for idx in np.ndindex(*shape):
            flat = multi_index_to_flat(idx, shape)
            back = flat_to_multi_index(flat, shape)
            assert back == idx

    def test_grid_neighbors_2d(self):
        shape = (5, 5)
        # Interior point
        nbs = grid_neighbors((2, 2), shape)
        assert len(nbs) == 4
        assert (1, 2) in nbs
        assert (3, 2) in nbs
        assert (2, 1) in nbs
        assert (2, 3) in nbs

    def test_grid_neighbors_corner(self):
        shape = (5, 5)
        nbs = grid_neighbors((0, 0), shape)
        assert len(nbs) == 2
        assert (1, 0) in nbs
        assert (0, 1) in nbs


class TestSupportSurface:
    def test_simple_1d(self):
        """Single item, 1D (temporal only), should match known count."""
        transactions = [{0}, {0}, {0}, set(), set()]
        locations = [() for _ in range(5)]
        pattern = frozenset([0])
        # Window size 3, grid shape (3,) since 5-3+1=3
        surface = compute_support_surface_naive(
            transactions, locations, pattern,
            window_sizes=(3,), grid_shape=(3,)
        )
        # Window [0,3): txns 0,1,2 -> count=3
        # Window [1,4): txns 1,2,3 -> count=2
        # Window [2,5): txns 2,3,4 -> count=1
        np.testing.assert_array_equal(surface, [3, 2, 1])

    def test_2d_support(self, simple_2d_data):
        """2D support surface should have non-zero values in dense block."""
        transactions, locations = simple_2d_data
        pattern = frozenset([0, 1])
        surface = compute_support_surface_naive(
            transactions, locations, pattern,
            window_sizes=(5, 2), grid_shape=(16, 4)
        )
        assert surface.shape == (16, 4)
        # The dense block is at t=[5,14], x=[1,3]
        # So the support surface should peak in the middle
        assert surface.max() > 0


class TestDenseRegionExtraction:
    def test_single_region(self):
        """A surface with one connected dense block."""
        surface = np.array([
            [0, 0, 0, 0, 0],
            [0, 3, 3, 3, 0],
            [0, 3, 5, 3, 0],
            [0, 3, 3, 3, 0],
            [0, 0, 0, 0, 0],
        ], dtype=np.int32)
        regions = extract_dense_regions(surface, threshold=3)
        assert len(regions) == 1
        assert len(regions[0]) == 9  # 3x3 block

    def test_two_separate_regions(self):
        """Two disconnected dense blocks."""
        surface = np.array([
            [5, 5, 0, 0, 0],
            [5, 5, 0, 0, 0],
            [0, 0, 0, 0, 0],
            [0, 0, 0, 5, 5],
            [0, 0, 0, 5, 5],
        ], dtype=np.int32)
        regions = extract_dense_regions(surface, threshold=3)
        assert len(regions) == 2


class TestSweepSurface:
    def test_sweep_matches_naive(self):
        """Sweep surface should find same regions as naive extraction."""
        surface = np.array([
            [0, 0, 0, 0],
            [0, 4, 4, 0],
            [0, 4, 4, 0],
            [0, 0, 0, 0],
        ], dtype=np.int32)
        naive_regions = extract_dense_regions(surface, threshold=3)
        sweep_regions = sweep_surface_detect(surface, threshold=3)
        assert len(naive_regions) == len(sweep_regions)
        # Same total points
        naive_pts = sum(len(r) for r in naive_regions)
        sweep_pts = sum(len(r) for r in sweep_regions)
        assert naive_pts == sweep_pts


# ===========================================================================
# Boundary cases
# ===========================================================================

class TestBoundaryCases:
    def test_threshold_equals_max(self):
        """Threshold exactly equals maximum support."""
        surface = np.array([[2, 3], [3, 2]], dtype=np.int32)
        regions = extract_dense_regions(surface, threshold=3)
        # (0,1) and (1,0) are not grid-adjacent (diagonal), so 2 separate regions
        assert len(regions) == 2
        assert len(regions[0]) == 1
        assert len(regions[1]) == 1

    def test_single_cell_region(self):
        """A dense region consisting of a single cell."""
        surface = np.array([[0, 0], [0, 5]], dtype=np.int32)
        regions = extract_dense_regions(surface, threshold=5)
        assert len(regions) == 1
        assert len(regions[0]) == 1
        assert regions[0][0] == (1, 1)

    def test_window_size_1(self):
        """Window size of 1 in all dimensions: each cell is its own window."""
        transactions = [{0}, {0}, set(), {0}]
        locations = [(0,), (1,), (0,), (1,)]
        pattern = frozenset([0])
        surface = compute_support_surface_naive(
            transactions, locations, pattern,
            window_sizes=(1, 1), grid_shape=(4, 2)
        )
        # Each cell counts transactions at that exact (t, x)
        assert surface[0, 0] == 1  # t=0, x=0
        assert surface[1, 1] == 1  # t=1, x=1
        assert surface[2, 0] == 0  # t=2, x=0 (empty transaction)

    def test_all_dense(self):
        """Every cell is above threshold: one single region."""
        surface = np.full((3, 3), 10, dtype=np.int32)
        regions = extract_dense_regions(surface, threshold=5)
        assert len(regions) == 1
        assert len(regions[0]) == 9


# ===========================================================================
# Error/degenerate cases
# ===========================================================================

class TestDegenerateCases:
    def test_empty_transactions(self):
        """No transactions: surface should be all zeros, no regions."""
        transactions: list = []
        locations: list = []
        pattern = frozenset([0])
        surface = compute_support_surface_naive(
            transactions, locations, pattern,
            window_sizes=(3, 2), grid_shape=(1, 1)
        )
        regions = extract_dense_regions(surface, threshold=1)
        assert len(regions) == 0

    def test_no_matching_pattern(self):
        """Pattern not present in any transaction."""
        transactions = [{1, 2}, {2, 3}, {1, 3}]
        locations = [(0,), (1,), (0,)]
        pattern = frozenset([99])
        surface = compute_support_surface_naive(
            transactions, locations, pattern,
            window_sizes=(2, 1), grid_shape=(2, 2)
        )
        assert np.all(surface == 0)

    def test_all_below_threshold(self):
        """Surface has values but all below threshold."""
        surface = np.array([[1, 2], [2, 1]], dtype=np.int32)
        regions = extract_dense_regions(surface, threshold=5)
        assert len(regions) == 0


# ===========================================================================
# Decomposability tests
# ===========================================================================

class TestDecomposability:
    def test_perfectly_decomposable(self):
        """A rank-1 surface should be perfectly decomposable."""
        f0 = np.array([1, 2, 3, 4, 5], dtype=np.float64)
        f1 = np.array([1, 0, 2], dtype=np.float64)
        surface = np.outer(f0, f1).astype(np.int32)
        is_decomp, error, factors = check_decomposability(surface, tolerance=0.05)
        assert is_decomp
        assert error < 0.05

    def test_non_decomposable(self):
        """A surface with strong interaction should not be decomposable."""
        surface = np.array([
            [10, 0, 0],
            [0, 0, 10],
            [0, 10, 0],
        ], dtype=np.int32)
        is_decomp, error, _ = check_decomposability(surface, tolerance=0.1)
        # Anti-diagonal pattern is not rank-1
        assert error > 0.1 or not is_decomp

    def test_zero_surface_decomposable(self):
        """Zero surface is trivially decomposable."""
        surface = np.zeros((5, 5), dtype=np.int32)
        is_decomp, error, _ = check_decomposability(surface)
        assert is_decomp
        assert error == 0.0


# ===========================================================================
# Integration tests
# ===========================================================================

class TestFindDenseItemsets:
    def test_finds_planted_pattern(self, simple_2d_data):
        """Should discover the planted dense pattern {0, 1}."""
        transactions, locations = simple_2d_data
        result = find_dense_itemsets_multidim(
            transactions, locations,
            window_sizes=(5, 2), grid_shape=(16, 4),
            threshold=2, max_length=3,
        )
        # Pattern {0,1} should be found
        assert frozenset([0, 1]) in result
        assert len(result[frozenset([0, 1])]) > 0

    def test_single_items_found(self, simple_2d_data):
        """Single-item patterns should be found."""
        transactions, locations = simple_2d_data
        result = find_dense_itemsets_multidim(
            transactions, locations,
            window_sizes=(5, 2), grid_shape=(16, 4),
            threshold=2, max_length=1,
        )
        # Items 0 and 1 should have dense regions
        assert frozenset([0]) in result
        assert frozenset([1]) in result


class TestSyntheticDataGeneration:
    def test_generate_basic(self):
        """Synthetic data generator should produce correct shapes."""
        txns, locs = generate_synthetic_2d(
            n_transactions=100,
            n_items=5,
            spatial_size=10,
            dense_regions=[{
                'pattern': [0, 1],
                't_start': 20, 't_end': 60,
                'x_start': 2, 'x_end': 7,
                'prob': 0.9,
            }],
        )
        assert len(txns) == 100
        assert len(locs) == 100
        # Check that items 0,1 appear more in the dense region
        dense_count = sum(
            1 for t in range(20, 61)
            if 0 in txns[t] and 1 in txns[t]
        )
        sparse_count = sum(
            1 for t in range(0, 20)
            if 0 in txns[t] and 1 in txns[t]
        )
        assert dense_count > sparse_count


class TestAdaptiveMining:
    def test_adaptive_runs(self, simple_2d_data):
        """Adaptive mining should run and return results."""
        transactions, locations = simple_2d_data
        regions, info = mine_dense_regions_adaptive(
            transactions, locations,
            pattern=frozenset([0, 1]),
            window_sizes=(5, 2),
            grid_ranges=(20, 5),
            threshold=2,
        )
        assert isinstance(regions, list)
        assert 'algorithm' in info
        assert info['algorithm'] in ('decomposed', 'sweep_surface')


class TestBoundingBox:
    def test_bounding_box_2d(self):
        region = [(1, 2), (1, 3), (2, 2), (2, 3)]
        mins, maxs = bounding_box(region)
        assert mins == (1, 2)
        assert maxs == (2, 3)


class TestPrefixSumSurface:
    def test_prefix_matches_naive(self):
        """Prefix-sum surface should match naive computation."""
        transactions = [{0}, {0}, {0, 1}, {1}, {0}]
        locations = [(0,), (1,), (0,), (1,), (0,)]
        pattern = frozenset([0])

        naive = compute_support_surface_naive(
            transactions, locations, pattern,
            window_sizes=(3, 2), grid_shape=(3, 1)
        )
        fast = compute_support_surface_fast(
            transactions, locations, pattern,
            window_sizes=(3, 2), grid_ranges=(5, 2)
        )
        # Both should have shape (3, 1)
        assert naive.shape == (3, 1)
        assert fast.shape == (3, 1)
        np.testing.assert_array_equal(naive, fast)
