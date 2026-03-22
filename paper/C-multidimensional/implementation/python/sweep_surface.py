"""
Sweep Surface Algorithm for Multi-Dimensional Dense Region Mining.

Optimized algorithm that processes the grid dimension-by-dimension,
maintaining an active set and merging dense cells incrementally.

Key optimizations over the naive approach:
1. Prefix-sum based support surface computation
2. Sweep-based connected component detection
3. Dimension decomposability check with fallback
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import numpy as np

from multidim_dense import (
    UnionFind,
    extract_dense_regions,
    flat_to_multi_index,
    grid_neighbors,
    multi_index_to_flat,
)


# ---------------------------------------------------------------------------
# Prefix-sum based support surface (optimized)
# ---------------------------------------------------------------------------

def compute_support_surface_fast(
    transactions: List[Set[int]],
    locations: List[Tuple[int, ...]],
    pattern: FrozenSet[int],
    window_sizes: Tuple[int, ...],
    grid_ranges: Tuple[int, ...],
) -> np.ndarray:
    """
    Compute support surface using prefix sums with proper inclusion-exclusion.

    Parameters
    ----------
    transactions, locations : transaction data
    pattern : itemset to evaluate
    window_sizes : (W_0, W_1, ..., W_k) window sizes per dimension
    grid_ranges : (N, X_1, ..., X_k) full extent of each dimension

    Returns
    -------
    surface : ndarray with shape (N - W_0 + 1, X_1 - W_1 + 1, ...)
    """
    ndim = len(grid_ranges)
    # Build indicator: count of pattern occurrences at each grid cell
    indicator = np.zeros(grid_ranges, dtype=np.int64)

    for t in range(len(transactions)):
        if pattern.issubset(transactions[t]):
            loc = locations[t]
            idx = (t,) + tuple(loc)
            if all(0 <= idx[d] < grid_ranges[d] for d in range(ndim)):
                indicator[idx] += 1

    # Prefix sums along each dimension
    prefix = indicator.copy()
    for d in range(ndim):
        prefix = np.cumsum(prefix, axis=d)

    # Output shape
    out_shape = tuple(
        grid_ranges[d] - window_sizes[d] + 1 for d in range(ndim)
    )

    if any(s <= 0 for s in out_shape):
        return np.zeros((0,) * ndim, dtype=np.int32)

    # Inclusion-exclusion to compute window sums
    surface = _inclusion_exclusion(prefix, window_sizes, out_shape)
    return surface.astype(np.int32)


def _inclusion_exclusion(
    prefix: np.ndarray,
    window_sizes: Tuple[int, ...],
    out_shape: Tuple[int, ...],
) -> np.ndarray:
    """
    Compute window sums from prefix sums via inclusion-exclusion.

    For each output cell (i_0, i_1, ..., i_k), the window sum covers
    [i_d, i_d + W_d) in each dimension d.
    """
    ndim = len(out_shape)
    result = np.zeros(out_shape, dtype=np.int64)

    # Iterate over 2^ndim corners of the inclusion-exclusion
    for bits in range(1 << ndim):
        sign = 1
        slices = []
        valid = True
        for d in range(ndim):
            if bits & (1 << d):
                # Subtract 1 corner: index = i_d - 1
                sign *= -1
                if out_shape[d] == 0:
                    valid = False
                    break
                # This slice indexes into prefix at positions [i_d - 1]
                # which means we need i_d >= 1, otherwise skip
                slices.append(slice(0, out_shape[d]))
            else:
                # Add corner: index = i_d + W_d - 1
                slices.append(slice(window_sizes[d] - 1,
                                    window_sizes[d] - 1 + out_shape[d]))

        if not valid:
            continue

        # Build the corresponding prefix array slice
        prefix_slices = []
        for d in range(ndim):
            if bits & (1 << d):
                # i_d - 1: need to handle the -1 offset
                start = -1
                stop = out_shape[d] - 1
                if start < 0:
                    # We need to pad: when i_d = 0, prefix[i_d - 1] = 0
                    prefix_slices.append(None)  # mark for special handling
                else:
                    prefix_slices.append(slice(start, stop))
            else:
                s = window_sizes[d] - 1
                prefix_slices.append(slice(s, s + out_shape[d]))

        # Construct the array
        arr = _extract_prefix_corner(prefix, prefix_slices, out_shape)
        result += sign * arr

    return result


def _extract_prefix_corner(
    prefix: np.ndarray,
    slices: list,
    out_shape: Tuple[int, ...],
) -> np.ndarray:
    """Extract a corner of the prefix sum, handling negative indices with zero padding."""
    ndim = len(out_shape)

    # Replace None with actual slices, tracking which dims need zero-padding
    actual_slices = []
    pad_dims = []
    for d in range(ndim):
        if slices[d] is None:
            pad_dims.append(d)
            actual_slices.append(slice(0, out_shape[d]))
        else:
            actual_slices.append(slices[d])

    if not pad_dims:
        return prefix[tuple(actual_slices)]

    # Need to handle zero padding for dimensions where index can be -1
    result = np.zeros(out_shape, dtype=np.int64)

    # For each padded dimension, the first element (i_d=0 -> index -1) is 0
    # and the rest come from prefix[0:out_shape[d]-1]
    for d in pad_dims:
        actual_slices[d] = slice(0, out_shape[d] - 1)

    # Build output region (skipping first element in padded dims)
    out_slices = [slice(None)] * ndim
    for d in pad_dims:
        out_slices[d] = slice(1, out_shape[d])

    sub = prefix[tuple(actual_slices)]
    result[tuple(out_slices)] = sub
    return result


# ---------------------------------------------------------------------------
# Sweep surface algorithm
# ---------------------------------------------------------------------------

def sweep_surface_detect(
    surface: np.ndarray,
    threshold: int,
) -> List[List[Tuple[int, ...]]]:
    """
    Detect dense regions by sweeping through the first dimension.

    This processes the grid slice-by-slice along dimension 0,
    maintaining connected components incrementally.

    For 2D grids, this is equivalent to a sweep line;
    for 3D+, it's a sweep hyperplane.

    Parameters
    ----------
    surface : ndarray
        The support surface.
    threshold : int
        Density threshold.

    Returns
    -------
    regions : list of list of tuples
        Dense regions as connected components.
    """
    shape = surface.shape
    ndim = len(shape)

    if ndim == 0:
        return []

    total = int(np.prod(shape))
    uf = UnionFind(total)
    above: Set[int] = set()

    # Sweep along dimension 0
    for t in range(shape[0]):
        # Get the current slice shape
        slice_shape = shape[1:]
        if not slice_shape:
            slice_shape = (1,)

        # Process all cells in this slice
        for sub_idx in np.ndindex(*slice_shape) if len(slice_shape) > 0 else [()] :
            full_idx = (t,) + (sub_idx if isinstance(sub_idx, tuple) else (sub_idx,))
            if len(full_idx) > ndim:
                full_idx = full_idx[:ndim]

            if surface[full_idx] >= threshold:
                flat = multi_index_to_flat(full_idx, shape)
                above.add(flat)

                # Connect to neighbors already processed
                for nb in grid_neighbors(full_idx, shape):
                    nb_flat = multi_index_to_flat(nb, shape)
                    if nb_flat in above:
                        uf.union(flat, nb_flat)

    if not above:
        return []

    # Collect components
    comp_map = uf.components(above)
    regions = []
    for root, members in comp_map.items():
        region = [flat_to_multi_index(m, shape) for m in members]
        region.sort()
        regions.append(region)

    regions.sort(key=lambda r: r[0])
    return regions


# ---------------------------------------------------------------------------
# Dimension decomposability check
# ---------------------------------------------------------------------------

def check_decomposability(
    surface: np.ndarray,
    tolerance: float = 0.1,
) -> Tuple[bool, float, Optional[List[np.ndarray]]]:
    """
    Check if a support surface is approximately dimension-decomposable.

    Tests whether S(t, v_1, ..., v_k) ≈ f_0(t) * f_1(v_1) * ... * f_k(v_k)
    by computing a rank-1 tensor approximation and measuring relative error.

    Parameters
    ----------
    surface : ndarray
        The support surface.
    tolerance : float
        Maximum relative error for decomposability.

    Returns
    -------
    is_decomposable : bool
        True if relative error < tolerance.
    relative_error : float
        ||S - rank1_approx||_F / ||S||_F
    factors : list of ndarray or None
        The 1D factors if decomposable, else None.
    """
    if surface.size == 0 or np.all(surface == 0):
        return True, 0.0, None

    ndim = surface.ndim
    shape = surface.shape
    surface_f = surface.astype(np.float64)
    norm_S = np.linalg.norm(surface_f)

    if norm_S < 1e-12:
        return True, 0.0, None

    # Compute rank-1 approximation using SVD for 2D, marginals for higher-D
    if ndim == 2:
        # SVD gives exact rank-1 approximation
        U, s_vals, Vt = np.linalg.svd(surface_f, full_matrices=False)
        factors = [U[:, 0] * np.sqrt(s_vals[0]), Vt[0, :] * np.sqrt(s_vals[0])]
        approx = np.outer(factors[0], factors[1])
    else:
        # Use marginal distributions as rank-1 approximation
        factors = []
        for d in range(ndim):
            axes = tuple(i for i in range(ndim) if i != d)
            marginal = np.sum(surface_f, axis=axes)
            norm = np.linalg.norm(marginal)
            if norm > 1e-12:
                marginal = marginal / norm
            factors.append(marginal)

        # Reconstruct via outer products
        approx = factors[0].copy()
        for d in range(1, ndim):
            approx = np.multiply.outer(approx, factors[d])

    # Scale to match
    scale = np.sum(surface_f * approx) / max(np.sum(approx * approx), 1e-12)
    approx *= scale

    residual = np.linalg.norm(surface_f - approx)
    rel_error = residual / norm_S

    is_decomposable = rel_error < tolerance
    return is_decomposable, float(rel_error), factors if is_decomposable else None


# ---------------------------------------------------------------------------
# Full pipeline: decomposition-aware dense region mining
# ---------------------------------------------------------------------------

def mine_dense_regions_adaptive(
    transactions: List[Set[int]],
    locations: List[Tuple[int, ...]],
    pattern: FrozenSet[int],
    window_sizes: Tuple[int, ...],
    grid_ranges: Tuple[int, ...],
    threshold: int,
    decomp_tolerance: float = 0.1,
) -> Tuple[List[List[Tuple[int, ...]]], Dict]:
    """
    Mine dense regions with adaptive algorithm selection.

    First checks dimension decomposability. If decomposable, solves
    k+1 independent 1D problems. Otherwise, uses the sweep surface
    algorithm on the full grid.

    Returns
    -------
    regions : list of regions
    info : dict with algorithm metadata
    """
    surface = compute_support_surface_fast(
        transactions, locations, pattern, window_sizes, grid_ranges
    )

    is_decomp, rel_error, factors = check_decomposability(surface, decomp_tolerance)

    info = {
        'decomposable': is_decomp,
        'decomp_error': rel_error,
        'surface_shape': surface.shape,
        'surface_max': int(np.max(surface)) if surface.size > 0 else 0,
        'surface_nonzero': int(np.count_nonzero(surface)),
    }

    if is_decomp and factors is not None:
        # Use decomposed 1D detection
        # For decomposed case, find 1D dense intervals per dimension
        # then take Cartesian product
        info['algorithm'] = 'decomposed'
        dense_per_dim: List[List[int]] = []
        for d in range(len(factors)):
            factor_thresh = threshold ** (1.0 / len(factors))
            dense_cells = [i for i in range(len(factors[d]))
                          if abs(factors[d][i]) >= factor_thresh]
            dense_per_dim.append(dense_cells)

        # Cartesian product of dense cells
        if all(len(cells) > 0 for cells in dense_per_dim):
            from itertools import product as iproduct
            candidate_cells = list(iproduct(*dense_per_dim))
            # Filter by actual surface value
            region_pts = []
            for pt in candidate_cells:
                if all(0 <= pt[d] < surface.shape[d] for d in range(len(pt))):
                    if surface[pt] >= threshold:
                        region_pts.append(pt)
            if region_pts:
                # Extract connected components from these points
                regions = _connected_components_from_points(region_pts, surface.shape)
            else:
                regions = []
        else:
            regions = []
    else:
        # Full sweep surface algorithm
        info['algorithm'] = 'sweep_surface'
        regions = sweep_surface_detect(surface, threshold)

    return regions, info


def _connected_components_from_points(
    points: List[Tuple[int, ...]],
    shape: Tuple[int, ...],
) -> List[List[Tuple[int, ...]]]:
    """Extract connected components from a set of grid points."""
    point_set = set(points)
    visited: Set[Tuple[int, ...]] = set()
    components: List[List[Tuple[int, ...]]] = []

    for pt in points:
        if pt in visited:
            continue
        # BFS
        component = []
        queue = [pt]
        visited.add(pt)
        while queue:
            current = queue.pop(0)
            component.append(current)
            for nb in grid_neighbors(current, shape):
                if nb in point_set and nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        component.sort()
        components.append(component)

    components.sort(key=lambda c: c[0])
    return components
