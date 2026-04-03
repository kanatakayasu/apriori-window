"""
Four baseline methods for Event Attribution.

1. ITS  (Interrupted Time Series)
2. Event Study
3. EP/Contrast (Emerging Pattern)
4. ECA (Event Coincidence Analysis)

All share:
  - Phase 1 (Apriori-window pattern enumeration)
  - Amplitude filter (min_support_range)
  - BH correction (global)
  - Union-Find deduplication
"""
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

_project_root = str(Path(__file__).resolve().parent.parent.parent)
_python_dir = str(Path(_project_root) / "apriori_window_suite" / "python")
for p in [_project_root, _python_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from apriori_window_basket import (
    compute_item_timestamps_map,
    find_dense_itemsets,
    intersect_sorted_lists,
    read_text_file_as_2d_vec_of_integers,
)
from event_attribution import (
    compute_support_series,
    read_events,
)


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _normal_cdf(z: float) -> float:
    """Approximate standard normal CDF using error function approximation."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _get_timestamps(pattern: Tuple[int, ...],
                    item_transaction_map: Dict[int, List[int]]) -> List[int]:
    items = list(pattern)
    if len(items) == 1:
        return item_transaction_map.get(items[0], [])
    lists = [item_transaction_map.get(item, []) for item in items]
    return intersect_sorted_lists(lists)


def _bh_correction(p_values: List[float], alpha: float) -> List[float]:
    """Benjamini-Hochberg adjusted p-values."""
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [1.0] * m
    for rank_i, idx in enumerate(indexed):
        adjusted[idx] = min(1.0, p_values[idx] * m / (rank_i + 1))
    # Enforce monotonicity (step-up)
    for i in range(m - 2, -1, -1):
        idx = indexed[i]
        idx_next = indexed[i + 1]
        adjusted[idx] = min(adjusted[idx], adjusted[idx_next])
    return adjusted


def _deduplicate(results, pattern_attr="pattern", event_attr="event_name",
                 score_fn=None):
    """Union-Find deduplication by shared items, per event.

    *results* is a list of dataclass instances that have *pattern_attr* and
    *event_attr* fields.  *score_fn* maps a result to a score (higher is
    better); the best-scoring result per component is kept.
    """
    if score_fn is None:
        # Default: prefer smaller (more significant) adjusted p-value
        score_fn = lambda r: -r.adjusted_p_value

    by_event: Dict[str, list] = defaultdict(list)
    for r in results:
        by_event[getattr(r, event_attr)].append(r)

    kept = []
    for event_name, event_results in by_event.items():
        if len(event_results) <= 1:
            kept.extend(event_results)
            continue

        n = len(event_results)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for i in range(n):
            for j in range(i + 1, n):
                si = set(getattr(event_results[i], pattern_attr))
                sj = set(getattr(event_results[j], pattern_attr))
                overlap = len(si & sj)
                threshold = max(1, min(len(si), len(sj)) // 2)
                if overlap >= threshold:
                    union(i, j)

        components: Dict[int, list] = defaultdict(list)
        for i in range(n):
            components[find(i)].append(i)

        for comp_indices in components.values():
            best_idx = max(comp_indices, key=lambda i: score_fn(event_results[i]))
            kept.append(event_results[best_idx])

    return kept


def _phase1_common(txn_path, events_path, window_size, min_support,
                   max_length, min_support_range):
    """Shared Phase 1: load data, enumerate patterns, amplitude filter."""
    transactions = read_text_file_as_2d_vec_of_integers(txn_path)
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)
    events = read_events(events_path)
    n_transactions = len(transactions)

    # Pre-filter patterns (len >= 2, amplitude check)
    filtered = {}
    timestamps_cache: Dict[Tuple[int, ...], List[int]] = {}
    support_cache: Dict[Tuple[int, ...], List[int]] = {}

    for pattern, intervals in frequents.items():
        if len(pattern) < 2 or not intervals:
            continue
        ts = _get_timestamps(pattern, item_transaction_map)
        support = compute_support_series(ts, window_size, n_transactions)
        s_max = max(support) if support else 0
        s_min = min(support) if support else 0
        if s_max - s_min < min_support_range:
            continue
        filtered[pattern] = intervals
        timestamps_cache[pattern] = ts
        support_cache[pattern] = support

    return (transactions, item_transaction_map, filtered, events,
            n_transactions, timestamps_cache, support_cache)


# ---------------------------------------------------------------------------
# 1. ITS (Interrupted Time Series)
# ---------------------------------------------------------------------------

@dataclass
class ITSResult:
    """Result of ITS baseline for a single (pattern, event) pair."""
    pattern: Tuple[int, ...]
    event_name: str
    event_start: int
    event_end: int
    p_value: float
    adjusted_p_value: float
    beta_level: float       # beta_2: level shift coefficient
    beta_slope: float       # beta_3: slope change coefficient
    t_statistic: float


def run_its_baseline(
    txn_path: str,
    events_path: str,
    window_size: int = 50,
    min_support: int = 5,
    max_length: int = 100,
    alpha: float = 0.10,
    min_support_range: int = 10,
    deduplicate: bool = True,
) -> List[ITSResult]:
    """Run Interrupted Time Series baseline.

    For each (pattern, event):
      - Fit OLS: s_P(t) = alpha + beta1*t + beta2*D(t) + beta3*(t-t_s)*D(t)
      - Test beta2 > 0 (one-sided)
      - BH correction, Union-Find deduplication
    """
    (transactions, item_transaction_map, filtered, events,
     n_transactions, timestamps_cache, support_cache) = _phase1_common(
        txn_path, events_path, window_size, min_support, max_length,
        min_support_range)

    hypotheses: List[Tuple[Tuple[int, ...], object, float, float, float, float]] = []

    for pattern, intervals in filtered.items():
        support = support_cache[pattern]
        n_windows = len(support)

        for event in events:
            es = event.start
            ee = event.end

            # Build design matrix
            t_arr = np.arange(n_windows, dtype=np.float64)
            y = np.array(support, dtype=np.float64)

            # D(t) = 1 if window [t, t+W-1] overlaps [es, ee]
            D = np.zeros(n_windows, dtype=np.float64)
            for t in range(n_windows):
                if t + window_size - 1 >= es and t <= ee:
                    D[t] = 1.0

            n_during = int(D.sum())
            n_outside = n_windows - n_during
            if n_during < 10 or n_outside < 10:
                continue

            # Post-intervention slope: (t - t_s) * D(t)
            t_s = es  # intervention start
            post_slope = (t_arr - t_s) * D

            # X = [1, t, D, (t-t_s)*D]
            X = np.column_stack([np.ones(n_windows), t_arr, D, post_slope])

            # OLS via least squares
            result = np.linalg.lstsq(X, y, rcond=None)
            beta = result[0]
            y_hat = X @ beta
            residuals = y - y_hat
            dof = n_windows - 4  # n - k
            if dof <= 0:
                continue

            sigma2 = np.sum(residuals ** 2) / dof

            # (X'X)^-1
            try:
                XtX_inv = np.linalg.inv(X.T @ X)
            except np.linalg.LinAlgError:
                continue

            se_beta = np.sqrt(np.maximum(0.0, sigma2 * np.diag(XtX_inv)))
            if se_beta[2] <= 0:
                continue

            # Test beta_2 > 0 (one-sided)
            t_stat = beta[2] / se_beta[2]
            p_value = 1.0 - _normal_cdf(t_stat)
            p_value = max(0.0, min(1.0, p_value))

            hypotheses.append((pattern, event, p_value,
                               float(beta[2]), float(beta[3]), float(t_stat)))

    if not hypotheses:
        return []

    # BH correction
    p_values = [h[2] for h in hypotheses]
    adjusted = _bh_correction(p_values, alpha)

    significant: List[ITSResult] = []
    for i, (pattern, event, p_raw, b2, b3, t_stat) in enumerate(hypotheses):
        if adjusted[i] < alpha:
            significant.append(ITSResult(
                pattern=pattern,
                event_name=event.name,
                event_start=event.start,
                event_end=event.end,
                p_value=p_raw,
                adjusted_p_value=adjusted[i],
                beta_level=b2,
                beta_slope=b3,
                t_statistic=t_stat,
            ))

    if not deduplicate or not significant:
        return significant

    return _deduplicate(significant,
                        score_fn=lambda r: r.beta_level)


# ---------------------------------------------------------------------------
# 2. Event Study
# ---------------------------------------------------------------------------

@dataclass
class EventStudyResult:
    """Result of Event Study baseline for a single (pattern, event) pair."""
    pattern: Tuple[int, ...]
    event_name: str
    event_start: int
    event_end: int
    p_value: float
    adjusted_p_value: float
    cas: float              # Cumulative Abnormal Support
    z_statistic: float
    mean_estimation: float


def run_event_study_baseline(
    txn_path: str,
    events_path: str,
    window_size: int = 50,
    min_support: int = 5,
    max_length: int = 100,
    alpha: float = 0.10,
    min_support_range: int = 10,
    deduplicate: bool = True,
) -> List[EventStudyResult]:
    """Run Event Study baseline.

    For each (pattern, event):
      - Estimation window: before event; Event window: overlapping event
      - CAS = sum(support_during - mu_est)
      - z = CAS / (sigma_est * sqrt(n_event_windows))
      - BH correction, Union-Find deduplication
    """
    (transactions, item_transaction_map, filtered, events,
     n_transactions, timestamps_cache, support_cache) = _phase1_common(
        txn_path, events_path, window_size, min_support, max_length,
        min_support_range)

    hypotheses: List[Tuple[Tuple[int, ...], object, float, float, float, float]] = []

    for pattern, intervals in filtered.items():
        support = support_cache[pattern]
        n_windows = len(support)

        for event in events:
            es = event.start
            ee = event.end

            # Estimation window: windows entirely before event
            estimation = []
            event_window = []
            for t in range(n_windows):
                if t + window_size - 1 < es:
                    estimation.append(float(support[t]))
                elif t + window_size - 1 >= es and t <= ee:
                    event_window.append(float(support[t]))

            if len(estimation) < 10 or len(event_window) < 5:
                continue

            mu_est = sum(estimation) / len(estimation)
            var_est = sum((x - mu_est) ** 2 for x in estimation) / len(estimation)
            sigma_est = math.sqrt(var_est) if var_est > 0 else 0.0

            if sigma_est <= 0:
                continue

            # Cumulative Abnormal Support
            cas = sum(s - mu_est for s in event_window)
            n_ev = len(event_window)
            z = cas / (sigma_est * math.sqrt(n_ev))

            p_value = 1.0 - _normal_cdf(z)
            p_value = max(0.0, min(1.0, p_value))

            hypotheses.append((pattern, event, p_value,
                               float(cas), float(z), float(mu_est)))

    if not hypotheses:
        return []

    # BH correction
    p_values = [h[2] for h in hypotheses]
    adjusted = _bh_correction(p_values, alpha)

    significant: List[EventStudyResult] = []
    for i, (pattern, event, p_raw, cas, z_stat, mu_est) in enumerate(hypotheses):
        if adjusted[i] < alpha:
            significant.append(EventStudyResult(
                pattern=pattern,
                event_name=event.name,
                event_start=event.start,
                event_end=event.end,
                p_value=p_raw,
                adjusted_p_value=adjusted[i],
                cas=cas,
                z_statistic=z_stat,
                mean_estimation=mu_est,
            ))

    if not deduplicate or not significant:
        return significant

    return _deduplicate(significant,
                        score_fn=lambda r: r.cas)


# ---------------------------------------------------------------------------
# 3. EP/Contrast (Emerging Pattern)
# ---------------------------------------------------------------------------

@dataclass
class EPContrastResult:
    """Result of EP/Contrast baseline for a single (pattern, event) pair."""
    pattern: Tuple[int, ...]
    event_name: str
    event_start: int
    event_end: int
    p_value: float
    adjusted_p_value: float
    support_during: float   # p1 = a/n1
    support_outside: float  # p2 = c/n2
    z_statistic: float


def run_ep_contrast_baseline(
    txn_path: str,
    events_path: str,
    window_size: int = 50,
    min_support: int = 5,
    max_length: int = 100,
    alpha: float = 0.10,
    min_support_range: int = 10,
    deduplicate: bool = True,
) -> List[EPContrastResult]:
    """Run Emerging Pattern / Contrast baseline.

    For each (pattern, event):
      - Count occurrences during vs outside event
      - Two-proportion z-test (one-sided: during > outside)
      - BH correction, Union-Find deduplication
    """
    (transactions, item_transaction_map, filtered, events,
     n_transactions, timestamps_cache, support_cache) = _phase1_common(
        txn_path, events_path, window_size, min_support, max_length,
        min_support_range)

    hypotheses: List[Tuple[Tuple[int, ...], object, float, float, float, float]] = []

    for pattern, intervals in filtered.items():
        timestamps = timestamps_cache[pattern]
        ts_set = set(timestamps)

        for event in events:
            es = event.start
            ee = event.end
            n1 = ee - es + 1  # transactions during event
            n2 = n_transactions - n1  # transactions outside

            if n1 < 5 or n2 < 5:
                continue

            # Count occurrences during event
            a = sum(1 for ts in timestamps if es <= ts <= ee)
            c = len(timestamps) - a

            p1 = a / n1
            p2 = c / n2

            # Pooled proportion
            total = a + c
            p_pool = total / (n1 + n2) if (n1 + n2) > 0 else 0.0

            if p_pool <= 0 or p_pool >= 1.0:
                continue

            denom = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2))
            if denom <= 0:
                continue

            z = (p1 - p2) / denom
            p_value = 1.0 - _normal_cdf(z)
            p_value = max(0.0, min(1.0, p_value))

            hypotheses.append((pattern, event, p_value,
                               float(p1), float(p2), float(z)))

    if not hypotheses:
        return []

    # BH correction
    p_values = [h[2] for h in hypotheses]
    adjusted = _bh_correction(p_values, alpha)

    significant: List[EPContrastResult] = []
    for i, (pattern, event, p_raw, p1, p2, z_stat) in enumerate(hypotheses):
        if adjusted[i] < alpha:
            significant.append(EPContrastResult(
                pattern=pattern,
                event_name=event.name,
                event_start=event.start,
                event_end=event.end,
                p_value=p_raw,
                adjusted_p_value=adjusted[i],
                support_during=p1,
                support_outside=p2,
                z_statistic=z_stat,
            ))

    if not deduplicate or not significant:
        return significant

    return _deduplicate(significant,
                        score_fn=lambda r: r.support_during - r.support_outside)


# ---------------------------------------------------------------------------
# 4. ECA (Event Coincidence Analysis)
# ---------------------------------------------------------------------------

@dataclass
class ECAResult:
    """Result of ECA baseline for a single (pattern, event) pair."""
    pattern: Tuple[int, ...]
    event_name: str
    event_start: int
    event_end: int
    p_value: float
    adjusted_p_value: float
    n_change_points: int    # total change points for this pattern
    k_coincident: int       # change points within coincidence window
    z_statistic: float


def _extract_change_points(
    intervals: List[Tuple[int, int]],
    n_transactions: int,
) -> List[int]:
    """Extract change points from dense intervals.

    For each dense interval [s, e]:
      - up change point at s
      - down change point at e+1 (if e+1 < n_transactions)
    """
    cps: List[int] = []
    for s, e in intervals:
        cps.append(s)
        if e + 1 < n_transactions:
            cps.append(e + 1)
    # Remove duplicates and sort
    return sorted(set(cps))


def run_eca_baseline(
    txn_path: str,
    events_path: str,
    window_size: int = 50,
    min_support: int = 5,
    max_length: int = 100,
    alpha: float = 0.10,
    min_support_range: int = 10,
    deduplicate: bool = True,
) -> List[ECAResult]:
    """Run Event Coincidence Analysis baseline.

    For each (pattern, event):
      - Extract change points from Phase 1 dense intervals
      - Count change points within coincidence window around event
      - Binomial test (normal approximation, one-sided)
      - BH correction, Union-Find deduplication
    """
    (transactions, item_transaction_map, filtered, events,
     n_transactions, timestamps_cache, support_cache) = _phase1_common(
        txn_path, events_path, window_size, min_support, max_length,
        min_support_range)

    delta = window_size  # coincidence window tolerance

    hypotheses: List[Tuple[Tuple[int, ...], object, float, int, int, float]] = []

    for pattern, intervals in filtered.items():
        change_points = _extract_change_points(intervals, n_transactions)
        n = len(change_points)
        if n < 3:
            continue

        for event in events:
            es = event.start
            ee = event.end
            event_duration = ee - es + 1

            # Count change points within coincidence window
            lo = es - delta
            hi = ee + delta
            k = sum(1 for cp in change_points if lo <= cp <= hi)

            # Under H0: change points uniformly distributed
            lam = min(1.0, (event_duration + 2 * delta) / n_transactions)

            if lam <= 0 or lam >= 1.0:
                continue

            mu = n * lam
            var = n * lam * (1.0 - lam)
            if var <= 0:
                continue

            z = (k - mu) / math.sqrt(var)
            p_value = 1.0 - _normal_cdf(z)
            p_value = max(0.0, min(1.0, p_value))

            hypotheses.append((pattern, event, p_value, n, k, float(z)))

    if not hypotheses:
        return []

    # BH correction
    p_values = [h[2] for h in hypotheses]
    adjusted = _bh_correction(p_values, alpha)

    significant: List[ECAResult] = []
    for i, (pattern, event, p_raw, n_cp, k, z_stat) in enumerate(hypotheses):
        if adjusted[i] < alpha:
            significant.append(ECAResult(
                pattern=pattern,
                event_name=event.name,
                event_start=event.start,
                event_end=event.end,
                p_value=p_raw,
                adjusted_p_value=adjusted[i],
                n_change_points=n_cp,
                k_coincident=k,
                z_statistic=z_stat,
            ))

    if not deduplicate or not significant:
        return significant

    return _deduplicate(significant,
                        score_fn=lambda r: r.k_coincident)
