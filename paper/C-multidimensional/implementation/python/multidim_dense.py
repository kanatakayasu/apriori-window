"""
Multi-Dimensional Dense Region Mining.

Computes support surfaces on discretized grids and extracts
dense regions (connected components of superlevel sets) using
union-find.

This module provides the naive/prefix-sum approach.
See sweep_surface.py for the optimized sweep-based algorithm.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from itertools import combinations, product
from pathlib import Path
from typing import (
    Dict,
    FrozenSet,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

import numpy as np


# ---------------------------------------------------------------------------
# Union-Find for connected component labeling
# ---------------------------------------------------------------------------

class UnionFind:
    """Weighted union-find with path compression."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n
        self.size = [1] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path halving
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True

    def components(self, active: Set[int]) -> Dict[int, List[int]]:
        """Return mapping from root -> list of active members."""
        groups: Dict[int, List[int]] = defaultdict(list)
        for x in active:
            groups[self.find(x)].append(x)
        return dict(groups)


# ---------------------------------------------------------------------------
# Grid coordinate utilities
# ---------------------------------------------------------------------------

def multi_index_to_flat(idx: Tuple[int, ...], shape: Tuple[int, ...]) -> int:
    """Convert a multi-dimensional index to a flat index."""
    flat = 0
    stride = 1
    for i in range(len(shape) - 1, -1, -1):
        flat += idx[i] * stride
        stride *= shape[i]
    return flat


def flat_to_multi_index(flat: int, shape: Tuple[int, ...]) -> Tuple[int, ...]:
    """Convert a flat index back to a multi-dimensional index."""
    idx = []
    for i in range(len(shape) - 1, -1, -1):
        idx.append(flat % shape[i])
        flat //= shape[i]
    return tuple(reversed(idx))


def grid_neighbors(idx: Tuple[int, ...], shape: Tuple[int, ...]) -> List[Tuple[int, ...]]:
    """Return grid-adjacent neighbors (differ by 1 in exactly one coordinate)."""
    neighbors = []
    for d in range(len(shape)):
        for delta in (-1, +1):
            new_val = idx[d] + delta
            if 0 <= new_val < shape[d]:
                neighbor = list(idx)
                neighbor[d] = new_val
                neighbors.append(tuple(neighbor))
    return neighbors


# ---------------------------------------------------------------------------
# Support surface computation
# ---------------------------------------------------------------------------

def compute_support_surface_naive(
    transactions: List[Set[int]],
    locations: List[Tuple[int, ...]],
    pattern: FrozenSet[int],
    window_sizes: Tuple[int, ...],
    grid_shape: Tuple[int, ...],
) -> np.ndarray:
    """
    Compute support surface via naive counting.

    Parameters
    ----------
    transactions : list of sets
        Each set contains item IDs present in that transaction.
    locations : list of tuples
        locations[t] = (x_1, ..., x_k) for transaction t.
        The first dimension (time) is the transaction index itself.
    pattern : frozenset
        The itemset pattern P.
    window_sizes : tuple of int
        (W_0, W_1, ..., W_k) where W_0 is the temporal window size.
    grid_shape : tuple of int
        The shape of the output grid: (T_0, T_1, ..., T_k).

    Returns
    -------
    surface : np.ndarray of shape grid_shape
        S_P(t, v_1, ..., v_k) = count of transactions matching P
        within the window centered at (t, v_1, ..., v_k).
    """
    ndim = len(grid_shape)
    surface = np.zeros(grid_shape, dtype=np.int32)
    N = len(transactions)

    # Precompute which transactions contain the pattern
    matching = []
    for t in range(N):
        if pattern.issubset(transactions[t]):
            matching.append(t)

    # For each matching transaction, add 1 to all windows containing it
    for t in matching:
        loc = locations[t]
        # Determine which grid cells' windows contain this transaction
        ranges = []
        # Time dimension
        t_min = max(0, t - window_sizes[0] + 1)
        t_max = min(grid_shape[0] - 1, t)
        ranges.append(range(t_min, t_max + 1))
        # Spatial dimensions
        for d in range(1, ndim):
            v_min = max(0, loc[d - 1] - window_sizes[d] + 1)
            v_max = min(grid_shape[d] - 1, loc[d - 1])
            ranges.append(range(v_min, v_max + 1))

        for idx in product(*ranges):
            surface[idx] += 1

    return surface


def compute_support_surface_prefix(
    transactions: List[Set[int]],
    locations: List[Tuple[int, ...]],
    pattern: FrozenSet[int],
    window_sizes: Tuple[int, ...],
    grid_ranges: Tuple[int, ...],
) -> np.ndarray:
    """
    Compute support surface via prefix sums (inclusion-exclusion).

    This is more efficient when the grid is large relative to the
    number of transactions.

    Parameters
    ----------
    grid_ranges : tuple of int
        Size of each dimension's full range (before windowing).
    """
    ndim = len(grid_ranges)
    # Build indicator tensor
    indicator = np.zeros(grid_ranges, dtype=np.int32)
    N = len(transactions)

    for t in range(N):
        if pattern.issubset(transactions[t]):
            loc = locations[t]
            idx = (t,) + tuple(loc)
            if all(0 <= idx[d] < grid_ranges[d] for d in range(ndim)):
                indicator[idx] += 1

    # Compute prefix sums along each dimension
    prefix = indicator.astype(np.int64)
    for d in range(ndim):
        prefix = np.cumsum(prefix, axis=d)

    # Extract support surface via inclusion-exclusion
    out_shape = tuple(
        grid_ranges[d] - window_sizes[d] + 1 for d in range(ndim)
    )
    surface = np.zeros(out_shape, dtype=np.int32)

    for idx in np.ndindex(*out_shape):
        # Window: [idx[d], idx[d] + window_sizes[d]) for each d
        val = 0
        for signs in product(*[range(2)] * ndim):
            corner = tuple(
                idx[d] + window_sizes[d] - 1 if signs[d] == 0
                else idx[d] - 1
                for d in range(ndim)
            )
            # Skip if any coordinate is negative
            if any(c < 0 for c in corner):
                if sum(signs) % 2 == 0:
                    continue
                else:
                    continue
            sign = (-1) ** sum(signs)
            if any(c < 0 for c in corner):
                continue
            val += sign * int(prefix[corner])
        surface[idx] = val

    return surface


# ---------------------------------------------------------------------------
# Dense region extraction
# ---------------------------------------------------------------------------

def extract_dense_regions(
    surface: np.ndarray,
    threshold: int,
) -> List[List[Tuple[int, ...]]]:
    """
    Extract dense regions as connected components of the superlevel set.

    Parameters
    ----------
    surface : np.ndarray
        The support surface (any number of dimensions).
    threshold : int
        The density threshold theta.

    Returns
    -------
    regions : list of list of tuples
        Each element is a list of grid coordinates forming a dense region
        (connected component of {x : surface[x] >= threshold}).
    """
    shape = surface.shape
    total = int(np.prod(shape))
    uf = UnionFind(total)

    # Find all cells above threshold
    above = set()
    for idx in np.ndindex(*shape):
        if surface[idx] >= threshold:
            flat = multi_index_to_flat(idx, shape)
            above.add(flat)

    if not above:
        return []

    # Union adjacent cells that are both above threshold
    for idx in np.ndindex(*shape):
        flat = multi_index_to_flat(idx, shape)
        if flat not in above:
            continue
        for nb in grid_neighbors(idx, shape):
            nb_flat = multi_index_to_flat(nb, shape)
            if nb_flat in above:
                uf.union(flat, nb_flat)

    # Collect components
    comp_map = uf.components(above)
    regions = []
    for root, members in comp_map.items():
        region = [flat_to_multi_index(m, shape) for m in members]
        region.sort()
        regions.append(region)

    regions.sort(key=lambda r: r[0])
    return regions


def bounding_box(
    region: List[Tuple[int, ...]],
) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    """Return the bounding box (min_corner, max_corner) of a region."""
    ndim = len(region[0])
    mins = tuple(min(pt[d] for pt in region) for d in range(ndim))
    maxs = tuple(max(pt[d] for pt in region) for d in range(ndim))
    return mins, maxs


# ---------------------------------------------------------------------------
# Multi-dimensional dense itemset mining (Apriori with containment pruning)
# ---------------------------------------------------------------------------

def find_dense_itemsets_multidim(
    transactions: List[Set[int]],
    locations: List[Tuple[int, ...]],
    window_sizes: Tuple[int, ...],
    grid_shape: Tuple[int, ...],
    threshold: int,
    max_length: int,
) -> Dict[FrozenSet[int], List[List[Tuple[int, ...]]]]:
    """
    Find all itemsets with non-empty dense regions using Apriori pruning.

    Uses the Dense Region Containment Theorem for candidate restriction:
    the superlevel set of P is contained in the intersection of superlevel
    sets of all (|P|-1)-subsets.

    Parameters
    ----------
    transactions : list of sets
        Transaction data.
    locations : list of tuples
        Spatial coordinates for each transaction.
    window_sizes : tuple
        Window sizes (W_0, W_1, ..., W_k).
    grid_shape : tuple
        Grid dimensions (T_0, T_1, ..., T_k).
    threshold : int
        Density threshold.
    max_length : int
        Maximum itemset size.

    Returns
    -------
    result : dict mapping frozenset -> list of regions
    """
    result: Dict[FrozenSet[int], List[List[Tuple[int, ...]]]] = {}

    # Collect all items
    all_items: Set[int] = set()
    for txn in transactions:
        all_items |= txn

    # Level 1: single items
    current_level: List[FrozenSet[int]] = []
    superlevel_sets: Dict[FrozenSet[int], Set[Tuple[int, ...]]] = {}

    for item in sorted(all_items):
        pattern = frozenset([item])
        surface = compute_support_surface_naive(
            transactions, locations, pattern, window_sizes, grid_shape
        )
        regions = extract_dense_regions(surface, threshold)
        if regions:
            result[pattern] = regions
            current_level.append(pattern)
            # Store superlevel set for pruning
            sl = set()
            for region in regions:
                sl.update(region)
            superlevel_sets[pattern] = sl

    # Level k >= 2
    k = 2
    while current_level and k <= max_length:
        # Generate candidates
        candidates = _generate_candidates_frozenset(current_level, k)

        next_level: List[FrozenSet[int]] = []
        current_set = set(current_level)

        for candidate in candidates:
            # Apriori pruning: all (k-1)-subsets must be in current_level
            subsets = [candidate - {item} for item in candidate]
            if not all(s in current_set for s in subsets):
                continue

            # Containment-based candidate region restriction
            candidate_region = None
            for s in subsets:
                if s in superlevel_sets:
                    if candidate_region is None:
                        candidate_region = set(superlevel_sets[s])
                    else:
                        candidate_region &= superlevel_sets[s]

            if candidate_region is not None and len(candidate_region) == 0:
                continue

            # Compute support surface (only in candidate region if available)
            surface = compute_support_surface_naive(
                transactions, locations, candidate, window_sizes, grid_shape
            )

            # Mask out non-candidate cells for efficiency
            if candidate_region is not None:
                masked = np.zeros_like(surface)
                for pt in candidate_region:
                    if all(0 <= pt[d] < surface.shape[d] for d in range(len(pt))):
                        masked[pt] = surface[pt]
                surface = masked

            regions = extract_dense_regions(surface, threshold)
            if regions:
                result[candidate] = regions
                next_level.append(candidate)
                sl = set()
                for region in regions:
                    sl.update(region)
                superlevel_sets[candidate] = sl

        current_level = next_level
        k += 1

    return result


def _generate_candidates_frozenset(
    prev: List[FrozenSet[int]], k: int
) -> List[FrozenSet[int]]:
    """Generate k-itemset candidates from (k-1)-itemsets."""
    candidates: Set[FrozenSet[int]] = set()
    prev_sorted = sorted(prev, key=lambda s: sorted(s))
    for i in range(len(prev_sorted)):
        for j in range(i + 1, len(prev_sorted)):
            union = prev_sorted[i] | prev_sorted[j]
            if len(union) == k:
                candidates.add(union)
    return sorted(candidates, key=lambda s: sorted(s))


# ---------------------------------------------------------------------------
# Convenience: create synthetic data for testing
# ---------------------------------------------------------------------------

def generate_synthetic_2d(
    n_transactions: int,
    n_items: int,
    spatial_size: int,
    dense_regions: List[Dict],
    item_prob: float = 0.1,
    seed: int = 42,
) -> Tuple[List[Set[int]], List[Tuple[int, ...]]]:
    """
    Generate 2D synthetic data with planted dense regions.

    Parameters
    ----------
    n_transactions : int
        Total number of transactions.
    n_items : int
        Number of distinct items.
    spatial_size : int
        Size of the spatial dimension.
    dense_regions : list of dict
        Each dict has keys:
          - 'pattern': list of int (items in the dense pattern)
          - 't_start', 't_end': temporal range
          - 'x_start', 'x_end': spatial range
          - 'prob': probability of pattern occurrence in the region
    item_prob : float
        Background probability of each item.
    seed : int
        Random seed.

    Returns
    -------
    transactions, locations
    """
    rng = np.random.default_rng(seed)

    transactions: List[Set[int]] = []
    locations: List[Tuple[int, ...]] = []

    for t in range(n_transactions):
        x = t % spatial_size  # simple round-robin spatial assignment
        loc = (x,)
        locations.append(loc)

        # Background items
        txn: Set[int] = set()
        for item in range(n_items):
            if rng.random() < item_prob:
                txn.add(item)

        # Plant dense region items
        for dr in dense_regions:
            if dr['t_start'] <= t <= dr['t_end']:
                if dr['x_start'] <= x <= dr['x_end']:
                    if rng.random() < dr['prob']:
                        for item in dr['pattern']:
                            txn.add(item)

        transactions.append(txn)

    return transactions, locations
