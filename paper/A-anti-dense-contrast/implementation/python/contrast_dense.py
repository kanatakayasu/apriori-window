"""
Contrast Dense Pattern Detection.

Compares dense interval structures between two temporal regimes
and classifies patterns into topology change types:
  - Emergence: anti-dense -> dense
  - Vanishing: dense -> anti-dense
  - Amplification: dense expands
  - Contraction: dense shrinks
  - Stable: no significant change

Also provides a permutation test for statistical significance
of structural changes.
"""

import random
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from anti_dense_interval import (
    compute_anti_dense_intervals_range,
    compute_support_series,
)

import sys
from pathlib import Path

_SUITE_DIR = str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python")
if _SUITE_DIR not in sys.path:
    sys.path.insert(0, _SUITE_DIR)

from apriori_window_basket import compute_dense_intervals  # noqa: E402


class TopologyChangeType(Enum):
    EMERGENCE = "emergence"
    VANISHING = "vanishing"
    AMPLIFICATION = "amplification"
    CONTRACTION = "contraction"
    STABLE = "stable"


def compute_dense_intervals_in_regime(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
    regime_start: int,
    regime_end: int,
) -> List[Tuple[int, int]]:
    """
    Compute dense intervals restricted to a regime [regime_start, regime_end].

    Returns intervals clipped to the regime boundaries.
    """
    all_intervals = compute_dense_intervals(timestamps, window_size, threshold)
    clipped = []
    for s, e in all_intervals:
        cs = max(s, regime_start)
        ce = min(e, regime_end)
        if cs <= ce:
            clipped.append((cs, ce))
    return clipped


def compute_coverage(
    intervals: Sequence[Tuple[int, int]],
    regime_length: int,
) -> float:
    """
    Compute total dense coverage as a fraction of the regime length.

    Parameters
    ----------
    intervals : list of (start, end) intervals within the regime
    regime_length : total length of the regime

    Returns
    -------
    Coverage ratio in [0, 1].
    """
    if regime_length <= 0:
        return 0.0
    total = sum(e - s + 1 for s, e in intervals)
    return total / regime_length


def classify_topology_change(
    intervals_r1: Sequence[Tuple[int, int]],
    intervals_r2: Sequence[Tuple[int, int]],
    regime1_length: int,
    regime2_length: int,
    delta: float = 0.1,
) -> TopologyChangeType:
    """
    Classify the topology change type of a pattern between two regimes.

    Parameters
    ----------
    intervals_r1 : dense intervals in regime 1
    intervals_r2 : dense intervals in regime 2
    regime1_length : length of regime 1
    regime2_length : length of regime 2
    delta : minimum coverage difference for amplification/contraction

    Returns
    -------
    TopologyChangeType enum value.
    """
    has_r1 = len(intervals_r1) > 0
    has_r2 = len(intervals_r2) > 0

    if not has_r1 and not has_r2:
        return TopologyChangeType.STABLE
    if not has_r1 and has_r2:
        return TopologyChangeType.EMERGENCE
    if has_r1 and not has_r2:
        return TopologyChangeType.VANISHING

    # Both regimes have dense intervals
    cov1 = compute_coverage(intervals_r1, regime1_length)
    cov2 = compute_coverage(intervals_r2, regime2_length)

    if cov2 > cov1 + delta:
        return TopologyChangeType.AMPLIFICATION
    if cov1 > cov2 + delta:
        return TopologyChangeType.CONTRACTION
    return TopologyChangeType.STABLE


def compute_contrast_statistic(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
    regime_boundary: int,
    total_length: int,
) -> float:
    """
    Compute the contrast statistic Delta(P, tau) = cov_2 - cov_1.

    Parameters
    ----------
    timestamps : sorted occurrence timestamps
    window_size : W
    threshold : theta
    regime_boundary : tau (last position of regime 1)
    total_length : N, total number of transactions

    Returns
    -------
    Delta value. Positive means more dense in regime 2.
    """
    r1_len = regime_boundary + 1
    r2_len = total_length - regime_boundary - 1

    if r1_len <= 0 or r2_len <= 0:
        return 0.0

    intervals_r1 = compute_dense_intervals_in_regime(
        timestamps, window_size, threshold, 0, regime_boundary
    )
    intervals_r2 = compute_dense_intervals_in_regime(
        timestamps, window_size, threshold, regime_boundary + 1, total_length - 1
    )

    cov1 = compute_coverage(intervals_r1, r1_len)
    cov2 = compute_coverage(intervals_r2, r2_len)

    return cov2 - cov1


def permutation_test(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
    regime_boundary: int,
    total_length: int,
    n_permutations: int = 999,
    seed: Optional[int] = None,
) -> Tuple[float, float]:
    """
    Permutation test for structural change significance.

    Under H0, the regime boundary has no effect on the dense interval
    structure. We shuffle timestamps and recompute the contrast statistic.

    Parameters
    ----------
    timestamps : sorted occurrence timestamps
    window_size : W
    threshold : theta
    regime_boundary : tau
    total_length : N
    n_permutations : number of permutations (B)
    seed : random seed for reproducibility

    Returns
    -------
    (observed_delta, p_value) tuple.
    """
    if seed is not None:
        random.seed(seed)

    observed = compute_contrast_statistic(
        timestamps, window_size, threshold, regime_boundary, total_length
    )

    count_extreme = 0
    ts_list = list(timestamps)

    for _ in range(n_permutations):
        # Permute timestamps: randomly reassign within [0, total_length-1]
        perm_ts = sorted(random.sample(range(total_length), min(len(ts_list), total_length)))
        perm_delta = compute_contrast_statistic(
            perm_ts, window_size, threshold, regime_boundary, total_length
        )
        if abs(perm_delta) >= abs(observed):
            count_extreme += 1

    p_value = (1 + count_extreme) / (1 + n_permutations)
    return observed, p_value


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> List[bool]:
    """
    Benjamini-Hochberg FDR correction.

    Parameters
    ----------
    p_values : list of p-values
    alpha : significance level

    Returns
    -------
    List of booleans indicating which hypotheses are rejected.
    """
    n = len(p_values)
    if n == 0:
        return []

    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    rejected = [False] * n

    # Find the largest k such that p_(k) <= (k/n) * alpha
    max_k = -1
    for k, (orig_idx, p) in enumerate(indexed, 1):
        if p <= (k / n) * alpha:
            max_k = k

    # Reject all hypotheses with rank <= max_k
    if max_k > 0:
        for k in range(max_k):
            orig_idx = indexed[k][0]
            rejected[orig_idx] = True

    return rejected


def find_contrast_dense_patterns(
    pattern_timestamps: Dict[str, List[int]],
    window_size: int,
    threshold: int,
    regime_boundary: int,
    total_length: int,
    delta: float = 0.1,
    alpha: float = 0.05,
    n_permutations: int = 999,
    seed: Optional[int] = None,
) -> Dict[str, Dict]:
    """
    Find all contrast dense patterns across two regimes.

    Parameters
    ----------
    pattern_timestamps : dict mapping pattern name to sorted timestamps
    window_size : W
    threshold : theta
    regime_boundary : tau
    total_length : N
    delta : coverage difference threshold
    alpha : significance level for permutation test
    n_permutations : number of permutations
    seed : random seed

    Returns
    -------
    Dict mapping pattern name to result dict with keys:
      - 'type': TopologyChangeType
      - 'delta': contrast statistic
      - 'p_value': permutation p-value
      - 'significant': bool after BH correction
      - 'intervals_r1': dense intervals in regime 1
      - 'intervals_r2': dense intervals in regime 2
      - 'cov_r1': coverage in regime 1
      - 'cov_r2': coverage in regime 2
    """
    r1_len = regime_boundary + 1
    r2_len = total_length - regime_boundary - 1

    results = {}
    p_values = []
    pattern_names = []

    for name, ts in pattern_timestamps.items():
        intervals_r1 = compute_dense_intervals_in_regime(
            ts, window_size, threshold, 0, regime_boundary
        )
        intervals_r2 = compute_dense_intervals_in_regime(
            ts, window_size, threshold, regime_boundary + 1, total_length - 1
        )

        cov1 = compute_coverage(intervals_r1, r1_len)
        cov2 = compute_coverage(intervals_r2, r2_len)

        change_type = classify_topology_change(
            intervals_r1, intervals_r2, r1_len, r2_len, delta
        )

        obs_delta, p_val = permutation_test(
            ts, window_size, threshold, regime_boundary, total_length,
            n_permutations=n_permutations, seed=seed,
        )

        results[name] = {
            "type": change_type,
            "delta": obs_delta,
            "p_value": p_val,
            "significant": False,  # will be updated after BH
            "intervals_r1": intervals_r1,
            "intervals_r2": intervals_r2,
            "cov_r1": cov1,
            "cov_r2": cov2,
        }
        p_values.append(p_val)
        pattern_names.append(name)

    # BH correction
    if p_values:
        rejected = benjamini_hochberg(p_values, alpha)
        for i, name in enumerate(pattern_names):
            results[name]["significant"] = rejected[i]

    return results
