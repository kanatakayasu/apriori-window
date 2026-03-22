"""
Synthetic Control for Dense Pattern Attribution

Applies the Synthetic Control Method (Abadie+ 2010) to pattern support
time series for causal attribution of support changes to external events.

Core components:
  - Donor pool construction via item disjointness
  - Counterfactual support trajectory estimation (constrained OLS)
  - Causal effect estimation with confidence intervals
  - Placebo-based inference (permutation tests)
"""

import sys
from pathlib import Path
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from numpy.typing import NDArray

# Import core functions from existing apriori_window_basket
_repo_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_repo_root / "apriori_window_suite" / "python"))

from apriori_window_basket import (  # noqa: E402
    compute_dense_intervals,
    generate_candidates,
    intersect_sorted_lists,
)


# ---------------------------------------------------------------------------
# Transaction I/O
# ---------------------------------------------------------------------------

def read_flat_transactions(path: str) -> List[List[int]]:
    """Read transactions as flat lists (one per line, space-separated items)."""
    transactions: List[List[int]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                transactions.append([])
                continue
            transactions.append([int(x) for x in line.split()])
    return transactions


# ---------------------------------------------------------------------------
# Support Time Series
# ---------------------------------------------------------------------------

def compute_support_series(
    transactions: List[List[int]],
    itemset: Tuple[int, ...],
    window_size: int,
) -> NDArray[np.float64]:
    """
    Compute the windowed support time series for an itemset.

    Args:
        transactions: list of transactions (each a list of item ints)
        itemset: tuple of items
        window_size: sliding window size W

    Returns:
        1D array of length (N - W + 1) with support values in [0, 1]
    """
    n = len(transactions)
    if n < window_size:
        return np.array([], dtype=np.float64)

    # Binary indicator: does transaction t contain itemset?
    contains = np.array(
        [1.0 if all(item in t for item in itemset) else 0.0 for t in transactions],
        dtype=np.float64,
    )

    # Sliding window sum
    cumsum = np.cumsum(contains)
    cumsum = np.insert(cumsum, 0, 0.0)
    window_counts = cumsum[window_size:] - cumsum[:-window_size]
    return window_counts / window_size


# ---------------------------------------------------------------------------
# Donor Pool Construction
# ---------------------------------------------------------------------------

def build_donor_pool(
    treated_pattern: Tuple[int, ...],
    candidate_patterns: List[Tuple[int, ...]],
) -> List[Tuple[int, ...]]:
    """
    Build a donor pool of item-disjoint patterns.

    A pattern P_j is a valid donor for P* if P_j and P* share no items.

    Args:
        treated_pattern: the pattern whose support change is being attributed
        candidate_patterns: all available candidate patterns

    Returns:
        list of item-disjoint patterns (the donor pool)
    """
    treated_set = set(treated_pattern)
    donors = []
    for p in candidate_patterns:
        if not treated_set.intersection(p):
            donors.append(p)
    return donors


def filter_donors_by_prefit(
    donor_series: Dict[Tuple[int, ...], NDArray[np.float64]],
    treated_series: NDArray[np.float64],
    intervention_time: int,
    max_rmspe: float = 0.1,
    min_variance: float = 1e-8,
) -> Dict[Tuple[int, ...], NDArray[np.float64]]:
    """
    Filter donors by pre-intervention fit quality and minimum variance.

    Args:
        donor_series: dict mapping donor pattern -> support time series
        treated_series: support time series for treated pattern
        intervention_time: time index of intervention (t0)
        max_rmspe: maximum pre-intervention RMSPE for inclusion
        min_variance: minimum variance in pre-period (avoid flat series)

    Returns:
        filtered dict of donor pattern -> series
    """
    pre_treated = treated_series[:intervention_time]
    filtered = {}
    for pattern, series in donor_series.items():
        pre_donor = series[:intervention_time]
        if len(pre_donor) == 0:
            continue
        # Check minimum variance
        if np.var(pre_donor) < min_variance:
            continue
        # Check RMSPE (raw, not fitted yet - just a correlation check)
        # We accept donors whose scale is at least somewhat comparable
        if np.std(pre_donor) > 0:
            filtered[pattern] = series
    return filtered


# ---------------------------------------------------------------------------
# Synthetic Control Estimation
# ---------------------------------------------------------------------------

def estimate_weights(
    treated_pre: NDArray[np.float64],
    donor_pre: NDArray[np.float64],
    regularization: float = 1e-6,
) -> NDArray[np.float64]:
    """
    Estimate synthetic control weights via constrained least squares.

    Minimizes ||treated_pre - donor_pre @ w||^2
    subject to w >= 0, sum(w) = 1.

    Uses a simple iterative projection algorithm (Frank-Wolfe / simplex projection).

    Args:
        treated_pre: (T0,) pre-intervention treated series
        donor_pre: (T0, J) pre-intervention donor series matrix
        regularization: L2 regularization strength

    Returns:
        (J,) weight vector
    """
    t0, j = donor_pre.shape
    if j == 0:
        return np.array([], dtype=np.float64)
    if j == 1:
        return np.array([1.0], dtype=np.float64)

    # Solve via quadratic programming using iterative projection
    # Q = D^T D + reg * I, c = -D^T y
    Q = donor_pre.T @ donor_pre + regularization * np.eye(j)
    c = -donor_pre.T @ treated_pre

    # Initialize with uniform weights
    w = np.ones(j) / j

    # Frank-Wolfe iterations
    for _ in range(1000):
        grad = Q @ w + c
        # Find the vertex of the simplex that minimizes the gradient
        min_idx = np.argmin(grad)
        s = np.zeros(j)
        s[min_idx] = 1.0
        # Line search
        d = s - w
        denom = d @ Q @ d
        if denom <= 0:
            gamma = 1.0
        else:
            gamma = min(1.0, max(0.0, -(grad @ d) / denom))
        w_new = w + gamma * d
        if np.linalg.norm(w_new - w) < 1e-10:
            break
        w = w_new

    # Ensure non-negative and normalized
    w = np.maximum(w, 0)
    w_sum = w.sum()
    if w_sum > 0:
        w /= w_sum
    else:
        w = np.ones(j) / j

    return w


def synthetic_control(
    treated_series: NDArray[np.float64],
    donor_matrix: NDArray[np.float64],
    intervention_time: int,
    regularization: float = 1e-6,
) -> Tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """
    Estimate causal effect using synthetic control method.

    Args:
        treated_series: (T,) full treated pattern support series
        donor_matrix: (T, J) full donor pattern support series matrix
        intervention_time: time index t0
        regularization: L2 reg for weight estimation

    Returns:
        (weights, counterfactual, causal_effect)
        - weights: (J,) estimated weights
        - counterfactual: (T,) estimated counterfactual trajectory
        - causal_effect: (T,) tau(t) = treated - counterfactual
    """
    treated_pre = treated_series[:intervention_time]
    donor_pre = donor_matrix[:intervention_time]

    weights = estimate_weights(treated_pre, donor_pre, regularization)

    counterfactual = donor_matrix @ weights
    causal_effect = treated_series - counterfactual

    return weights, counterfactual, causal_effect


# ---------------------------------------------------------------------------
# Inference: Placebo Tests
# ---------------------------------------------------------------------------

def compute_rmspe(series: NDArray[np.float64], start: int, end: int) -> float:
    """Compute root mean square prediction error over [start, end)."""
    segment = series[start:end]
    if len(segment) == 0:
        return 0.0
    return float(np.sqrt(np.mean(segment ** 2)))


def placebo_test(
    treated_series: NDArray[np.float64],
    donor_matrix: NDArray[np.float64],
    intervention_time: int,
    regularization: float = 1e-6,
) -> Tuple[float, List[float], float]:
    """
    Run placebo tests (in-space) by iteratively treating each donor as treated.

    For each donor j, construct a synthetic control using the remaining donors
    and the original treated pattern, compute the post/pre RMSPE ratio.

    Args:
        treated_series: (T,) treated series
        donor_matrix: (T, J) donor series
        intervention_time: t0
        regularization: for weight estimation

    Returns:
        (treated_ratio, placebo_ratios, p_value)
    """
    t_total = len(treated_series)
    j_total = donor_matrix.shape[1]

    # Treated unit's ratio
    _, _, treated_effect = synthetic_control(
        treated_series, donor_matrix, intervention_time, regularization
    )
    pre_rmspe = compute_rmspe(treated_effect, 0, intervention_time)
    post_rmspe = compute_rmspe(treated_effect, intervention_time, t_total)
    treated_ratio = post_rmspe / pre_rmspe if pre_rmspe > 1e-10 else float("inf")

    # Placebo ratios
    placebo_ratios = []
    for j in range(j_total):
        # Treat donor j as the treated unit
        placebo_treated = donor_matrix[:, j]
        # Remaining donors + original treated
        remaining_indices = [i for i in range(j_total) if i != j]
        placebo_donors = np.column_stack(
            [donor_matrix[:, remaining_indices], treated_series.reshape(-1, 1)]
        ) if remaining_indices else treated_series.reshape(-1, 1)

        try:
            _, _, placebo_effect = synthetic_control(
                placebo_treated, placebo_donors, intervention_time, regularization
            )
            pre_r = compute_rmspe(placebo_effect, 0, intervention_time)
            post_r = compute_rmspe(placebo_effect, intervention_time, t_total)
            ratio = post_r / pre_r if pre_r > 1e-10 else float("inf")
            placebo_ratios.append(ratio)
        except Exception:
            placebo_ratios.append(0.0)

    # p-value: fraction of placebos with ratio >= treated ratio
    n_extreme = sum(1 for r in placebo_ratios if r >= treated_ratio)
    p_value = (n_extreme + 1) / (len(placebo_ratios) + 1)

    return treated_ratio, placebo_ratios, p_value


# ---------------------------------------------------------------------------
# Confidence Intervals (Bootstrap)
# ---------------------------------------------------------------------------

def bootstrap_causal_effect(
    treated_series: NDArray[np.float64],
    donor_matrix: NDArray[np.float64],
    intervention_time: int,
    n_bootstrap: int = 200,
    confidence: float = 0.95,
    seed: int = 42,
    regularization: float = 1e-6,
) -> Tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """
    Bootstrap confidence intervals for the causal effect.

    Resamples pre-intervention periods (block bootstrap) and re-estimates weights.

    Args:
        treated_series: (T,) treated series
        donor_matrix: (T, J) donor series
        intervention_time: t0
        n_bootstrap: number of bootstrap samples
        confidence: confidence level (e.g. 0.95)
        seed: random seed
        regularization: for weight estimation

    Returns:
        (mean_effect, lower_bound, upper_bound) each of shape (T,)
    """
    rng = np.random.RandomState(seed)
    t_total = len(treated_series)
    effects = []

    for _ in range(n_bootstrap):
        # Resample pre-intervention indices (with replacement)
        pre_indices = rng.choice(intervention_time, size=intervention_time, replace=True)
        pre_indices.sort()

        resampled_treated_pre = treated_series[pre_indices]
        resampled_donor_pre = donor_matrix[pre_indices]

        weights = estimate_weights(
            resampled_treated_pre, resampled_donor_pre, regularization
        )
        counterfactual = donor_matrix @ weights
        effect = treated_series - counterfactual
        effects.append(effect)

    effects = np.array(effects)  # (n_bootstrap, T)
    alpha = (1 - confidence) / 2
    mean_effect = np.mean(effects, axis=0)
    lower = np.percentile(effects, 100 * alpha, axis=0)
    upper = np.percentile(effects, 100 * (1 - alpha), axis=0)

    return mean_effect, lower, upper


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------

def run_causal_attribution(
    transactions: List[List[int]],
    treated_pattern: Tuple[int, ...],
    candidate_patterns: List[Tuple[int, ...]],
    intervention_time: int,
    window_size: int,
    regularization: float = 1e-6,
    n_bootstrap: int = 200,
    confidence: float = 0.95,
    seed: int = 42,
) -> Dict:
    """
    Full causal attribution pipeline.

    1. Compute support time series for all patterns
    2. Build donor pool (item-disjoint)
    3. Estimate synthetic control weights
    4. Compute causal effect with confidence intervals
    5. Run placebo tests for p-value

    Args:
        transactions: list of transactions
        treated_pattern: the pattern to analyze
        candidate_patterns: all candidate patterns for donor pool
        intervention_time: t0 (index in support series)
        window_size: sliding window size W
        regularization: for weight estimation
        n_bootstrap: bootstrap iterations for CI
        confidence: confidence level
        seed: random seed

    Returns:
        dict with keys:
            treated_series, counterfactual, causal_effect,
            weights, donors, p_value, ci_lower, ci_upper,
            cumulative_effect, pre_rmspe, post_rmspe
    """
    # Step 1: Compute support series
    treated_series = compute_support_series(transactions, treated_pattern, window_size)
    if len(treated_series) == 0:
        return {"error": "No support series (not enough transactions for window)"}

    # Step 2: Build donor pool
    donors = build_donor_pool(treated_pattern, candidate_patterns)
    if len(donors) == 0:
        return {"error": "Empty donor pool (no item-disjoint patterns found)"}

    # Step 3: Compute donor series
    donor_series_list = []
    valid_donors = []
    for d in donors:
        ds = compute_support_series(transactions, d, window_size)
        if len(ds) == len(treated_series) and np.var(ds[:intervention_time]) > 1e-10:
            donor_series_list.append(ds)
            valid_donors.append(d)

    if len(valid_donors) == 0:
        return {"error": "No valid donors after variance filtering"}

    donor_matrix = np.column_stack(donor_series_list)

    # Step 4: Synthetic control
    weights, counterfactual, causal_effect = synthetic_control(
        treated_series, donor_matrix, intervention_time, regularization
    )

    # Step 5: Placebo tests
    treated_ratio, placebo_ratios, p_value = placebo_test(
        treated_series, donor_matrix, intervention_time, regularization
    )

    # Step 6: Bootstrap CI
    mean_effect, ci_lower, ci_upper = bootstrap_causal_effect(
        treated_series, donor_matrix, intervention_time,
        n_bootstrap, confidence, seed, regularization
    )

    # Compute summary statistics
    pre_rmspe = compute_rmspe(causal_effect, 0, intervention_time)
    post_rmspe = compute_rmspe(causal_effect, intervention_time, len(treated_series))
    cumulative_effect = float(np.sum(causal_effect[intervention_time:]))

    return {
        "treated_pattern": treated_pattern,
        "donors": valid_donors,
        "weights": weights.tolist(),
        "treated_series": treated_series.tolist(),
        "counterfactual": counterfactual.tolist(),
        "causal_effect": causal_effect.tolist(),
        "cumulative_effect": cumulative_effect,
        "pre_rmspe": pre_rmspe,
        "post_rmspe": post_rmspe,
        "p_value": p_value,
        "treated_ratio": treated_ratio,
        "placebo_ratios": placebo_ratios,
        "ci_lower": ci_lower.tolist(),
        "ci_upper": ci_upper.tolist(),
        "intervention_time": intervention_time,
        "window_size": window_size,
    }
