"""
CausalImpact-inspired baseline for Event Attribution.

Pure Python + numpy implementation (no scipy/statsmodels dependency).

For each (pattern, event) pair:
  1. Compute support time series
  2. Fit a local level model (mean + optional linear trend) on pre-event data
  3. Forecast the counterfactual during the event period
  4. Compute cumulative impact (actual - predicted) and its significance
  5. Apply global BH correction
  6. Apply Union-Find deduplication (same as proposed method)

This follows the methodology of Brodersen et al. (2015) "Inferring causal
impact using Bayesian structural time-series models", simplified to a
frequentist local-level model since we lack covariates.
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


@dataclass
class CausalImpactResult:
    """Result of CausalImpact baseline for a single (pattern, event) pair."""
    pattern: Tuple[int, ...]
    event_name: str
    event_start: int
    event_end: int
    p_value: float
    adjusted_p_value: float
    cumulative_impact: float
    mean_actual: float
    mean_predicted: float


def _normal_cdf(z: float) -> float:
    """Approximate standard normal CDF using error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _fit_local_level(pre_data: np.ndarray) -> Tuple[float, float, float]:
    """Fit a local level model (mean + linear trend) to pre-event data.

    Returns (intercept, slope, residual_std).
    """
    n = len(pre_data)
    if n < 3:
        mu = float(np.mean(pre_data))
        return mu, 0.0, max(float(np.std(pre_data, ddof=0)), 1e-6)

    # Fit linear regression: y = a + b*t
    t = np.arange(n, dtype=np.float64)
    t_mean = np.mean(t)
    y_mean = np.mean(pre_data)

    ss_tt = np.sum((t - t_mean) ** 2)
    if ss_tt < 1e-12:
        return float(y_mean), 0.0, max(float(np.std(pre_data, ddof=0)), 1e-6)

    slope = float(np.sum((t - t_mean) * (pre_data - y_mean)) / ss_tt)
    intercept = float(y_mean - slope * t_mean)

    # Residual standard deviation
    fitted = intercept + slope * t
    residuals = pre_data - fitted
    res_std = float(np.sqrt(np.sum(residuals ** 2) / max(1, n - 2)))
    return intercept, slope, max(res_std, 1e-6)


def _causalimpact_test(
    support: List[int],
    event_start: int,
    event_end: int,
    window_size: int,
) -> Optional[Tuple[float, float, float, float]]:
    """CausalImpact-inspired test for a single (pattern, event) pair.

    Returns (p_value, cumulative_impact, mean_actual, mean_predicted) or None.
    """
    n_windows = len(support)
    if n_windows == 0:
        return None

    # Define during-event and pre-event windows
    during_indices = []
    pre_indices = []

    for t in range(n_windows):
        # Window [t, t+W-1] overlaps with event [event_start, event_end]
        if t + window_size - 1 >= event_start and t <= event_end:
            during_indices.append(t)
        elif t + window_size - 1 < event_start:
            pre_indices.append(t)
        # Post-event windows are not used for model fitting

    if len(during_indices) < 5 or len(pre_indices) < 10:
        return None

    pre_data = np.array([float(support[t]) for t in pre_indices])
    during_data = np.array([float(support[t]) for t in during_indices])

    # Fit local level model on pre-event data
    intercept, slope, res_std = _fit_local_level(pre_data)

    # Forecast counterfactual during event period
    # Continue the trend from pre-event period
    n_pre = len(pre_indices)
    predicted = np.array([
        intercept + slope * (n_pre + i)
        for i in range(len(during_indices))
    ])

    # Cumulative impact
    impact = during_data - predicted
    cumulative_impact = float(np.sum(impact))
    n_during = len(during_indices)

    # Standard error of cumulative impact
    # Under H0, each residual has variance res_std^2
    # Cumulative impact SE = res_std * sqrt(n_during) * correction_factor
    # Correction factor accounts for forecast uncertainty growing with horizon
    # Simplified: SE = res_std * sqrt(n_during + n_during^2 / n_pre)
    forecast_var_factor = 1.0 + n_during / max(1, n_pre)
    se_cumulative = res_std * math.sqrt(n_during * forecast_var_factor)

    if se_cumulative < 1e-10:
        return None

    # One-sided test: is cumulative impact significantly positive?
    z = cumulative_impact / se_cumulative
    p_value = 1.0 - _normal_cdf(z)
    p_value = max(0.0, min(1.0, p_value))

    mean_actual = float(np.mean(during_data))
    mean_predicted = float(np.mean(predicted))

    return p_value, cumulative_impact, mean_actual, mean_predicted


def _get_timestamps(pattern: Tuple[int, ...],
                    item_transaction_map: Dict[int, List[int]]) -> List[int]:
    items = list(pattern)
    if len(items) == 1:
        return item_transaction_map.get(items[0], [])
    lists = [item_transaction_map.get(item, []) for item in items]
    return intersect_sorted_lists(lists)


def run_causalimpact_baseline(
    txn_path: str,
    events_path: str,
    window_size: int = 50,
    min_support: int = 5,
    max_length: int = 100,
    alpha: float = 0.10,
    min_support_range: int = 10,
    deduplicate: bool = True,
) -> List[CausalImpactResult]:
    """Run CausalImpact-inspired baseline.

    For each pattern P (|P| >= 2) and event e:
      - Compute support time series s_P(t)
      - Fit local level model on pre-event data
      - Forecast counterfactual during event period
      - Test if cumulative impact is significantly positive
      - BH correction over all hypotheses
      - Union-Find deduplication (optional)

    Returns list of significant (pattern, event) attributions.
    """
    # Phase 1
    transactions = read_text_file_as_2d_vec_of_integers(txn_path)
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)
    events = read_events(events_path)
    n_transactions = len(transactions)

    # Collect all (pattern, event) hypotheses with p-values
    hypotheses: List[Tuple[Tuple[int, ...], object, float, float, float, float]] = []

    for pattern, intervals in frequents.items():
        if len(pattern) < 2:
            continue
        if not intervals:
            continue

        timestamps = _get_timestamps(pattern, item_transaction_map)
        support = compute_support_series(timestamps, window_size, n_transactions)

        # Amplitude filter (same as proposed method)
        s_max = max(support) if support else 0
        s_min = min(support) if support else 0
        if s_max - s_min < min_support_range:
            continue

        for event in events:
            result = _causalimpact_test(
                support, event.start, event.end, window_size
            )
            if result is None:
                continue

            p_value, cum_impact, mean_actual, mean_predicted = result
            hypotheses.append((
                pattern, event, p_value, cum_impact, mean_actual, mean_predicted
            ))

    if not hypotheses:
        return []

    # BH correction
    m = len(hypotheses)
    p_values = [h[2] for h in hypotheses]
    indexed = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [1.0] * m

    for rank_i, idx in enumerate(indexed):
        adjusted[idx] = min(1.0, p_values[idx] * m / (rank_i + 1))

    # Enforce monotonicity (step-up)
    for i in range(m - 2, -1, -1):
        idx = indexed[i]
        idx_next = indexed[i + 1]
        adjusted[idx] = min(adjusted[idx], adjusted[idx_next])

    # Filter significant
    significant: List[CausalImpactResult] = []
    for i, (pattern, event, p_raw, cum_impact, mean_a, mean_p) in enumerate(hypotheses):
        if adjusted[i] < alpha:
            significant.append(CausalImpactResult(
                pattern=pattern,
                event_name=event.name,
                event_start=event.start,
                event_end=event.end,
                p_value=p_raw,
                adjusted_p_value=adjusted[i],
                cumulative_impact=cum_impact,
                mean_actual=mean_a,
                mean_predicted=mean_p,
            ))

    if not deduplicate or not significant:
        return significant

    return _deduplicate_ci(significant)


def _deduplicate_ci(results: List[CausalImpactResult]) -> List[CausalImpactResult]:
    """Union-Find deduplication by shared items, per event."""
    by_event = defaultdict(list)
    for r in results:
        by_event[r.event_name].append(r)

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
                si = set(event_results[i].pattern)
                sj = set(event_results[j].pattern)
                overlap = len(si & sj)
                threshold = max(1, min(len(si), len(sj)) // 2)
                if overlap >= threshold:
                    union(i, j)

        components = defaultdict(list)
        for i in range(n):
            components[find(i)].append(i)

        for comp_indices in components.values():
            best_idx = max(comp_indices,
                           key=lambda i: event_results[i].cumulative_impact)
            kept.append(event_results[best_idx])

    return kept
