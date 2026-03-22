"""
Scale-Space Dense Ridge detection.

Builds a dense indicator matrix phi(level, position) and finds
connected components that span multiple scale levels (ridges).
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import deque
from typing import Dict, List, Optional, Sequence, Set, Tuple


def build_dense_indicator(
    timestamps: Sequence[int],
    w0: int,
    theta0: int,
    n: int,
) -> Tuple[List[List[bool]], List[Tuple[int, int]]]:
    """
    Build the dense indicator matrix phi(level, position).

    phi(ell, t) = True iff s_P^{W_ell}(t) >= theta_ell

    Returns:
        (matrix, level_params) where level_params[i] = (W_i, theta_i)
    """
    ts = list(timestamps)
    max_level = max(0, int(math.log2(max(1, n // w0))))
    level_params: List[Tuple[int, int]] = []
    matrix: List[List[bool]] = []

    for ell in range(max_level + 1):
        w = (2 ** ell) * w0
        if w > n:
            break
        theta = max(1, math.ceil(theta0 * (2 ** ell)))
        level_params.append((w, theta))

        # Compute dense indicator for this level
        num_positions = max(0, n - w + 1)
        row = [False] * num_positions
        for t in range(num_positions):
            start_idx = bisect_left(ts, t)
            end_idx = bisect_right(ts, t + w)
            if (end_idx - start_idx) >= theta:
                row[t] = True
        matrix.append(row)

    return matrix, level_params


def find_ridges(
    matrix: List[List[bool]],
    min_levels: int = 2,
) -> List[List[Tuple[int, int]]]:
    """
    Find Scale-Space Dense Ridges via BFS on the dense indicator matrix.

    A ridge is a connected component of True cells in the (level, position)
    plane that spans at least min_levels scale levels.

    Connectivity: 4-connected (up/down in level, left/right in position).

    Returns list of ridges, where each ridge is a list of (level, position).
    """
    if not matrix:
        return []

    num_levels = len(matrix)
    visited: Set[Tuple[int, int]] = set()
    ridges: List[List[Tuple[int, int]]] = []

    for ell in range(num_levels):
        for t in range(len(matrix[ell])):
            if not matrix[ell][t] or (ell, t) in visited:
                continue

            # BFS to find connected component
            component: List[Tuple[int, int]] = []
            queue: deque[Tuple[int, int]] = deque()
            queue.append((ell, t))
            visited.add((ell, t))

            while queue:
                cl, ct = queue.popleft()
                component.append((cl, ct))

                # 4-connected neighbors
                neighbors = [
                    (cl - 1, ct), (cl + 1, ct),
                    (cl, ct - 1), (cl, ct + 1),
                ]
                for nl, nt in neighbors:
                    if (nl, nt) in visited:
                        continue
                    if nl < 0 or nl >= num_levels:
                        continue
                    if nt < 0 or nt >= len(matrix[nl]):
                        continue
                    if matrix[nl][nt]:
                        visited.add((nl, nt))
                        queue.append((nl, nt))

            # Check if component spans enough levels
            levels_in_component = set(c[0] for c in component)
            level_span = max(levels_in_component) - min(levels_in_component) + 1
            if level_span >= min_levels:
                ridges.append(component)

    return ridges


def compute_ridge_strength(
    ridge: List[Tuple[int, int]],
    timestamps: Sequence[int],
    level_params: List[Tuple[int, int]],
) -> float:
    """
    Compute ridge strength = sum of support values at all (level, position) in the ridge.
    """
    ts = list(timestamps)
    strength = 0.0
    for ell, t in ridge:
        w, _theta = level_params[ell]
        start_idx = bisect_left(ts, t)
        end_idx = bisect_right(ts, t + w)
        strength += (end_idx - start_idx)
    return strength


def detect_scale_space_ridges(
    timestamps: Sequence[int],
    w0: int,
    theta0: int,
    n: int,
    min_levels: int = 2,
) -> List[Dict]:
    """
    Full scale-space ridge detection pipeline.

    Returns list of ridge dictionaries:
      {
        'cells': [(level, position), ...],
        'strength': float,
        'level_span': int,
        'position_range': (min_t, max_t),
      }
    """
    if not timestamps:
        return []

    matrix, level_params = build_dense_indicator(timestamps, w0, theta0, n)
    raw_ridges = find_ridges(matrix, min_levels=min_levels)

    results = []
    for ridge in raw_ridges:
        levels = [c[0] for c in ridge]
        positions = [c[1] for c in ridge]
        strength = compute_ridge_strength(ridge, timestamps, level_params)
        results.append({
            'cells': ridge,
            'strength': strength,
            'level_span': max(levels) - min(levels) + 1,
            'position_range': (min(positions), max(positions)),
        })

    # Sort by strength descending
    results.sort(key=lambda r: r['strength'], reverse=True)
    return results
