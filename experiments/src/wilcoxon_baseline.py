"""
Wilcoxon rank-sum test baseline for Event Attribution.

Pure Python implementation (no numpy/scipy dependency).

For each (pattern, event) pair:
  1. Compute support time series
  2. Split into "during event" and "outside event" windows
  3. Apply Mann-Whitney U test (one-sided: during > outside)
  4. Apply global BH correction
  5. Apply Union-Find deduplication (same as proposed method)
"""
import math
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
class WilcoxonResult:
    """Result of Wilcoxon baseline for a single (pattern, event) pair."""
    pattern: Tuple[int, ...]
    event_name: str
    event_start: int
    event_end: int
    p_value: float
    adjusted_p_value: float
    mean_during: float
    mean_outside: float


def _normal_cdf(z: float) -> float:
    """Approximate standard normal CDF using error function approximation."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _mann_whitney_u_test(x: List[float], y: List[float]) -> float:
    """Mann-Whitney U test, one-sided (x > y).

    Returns p-value for the alternative hypothesis that x is
    stochastically greater than y.

    Uses normal approximation with continuity correction for n > 20.
    """
    n1 = len(x)
    n2 = len(y)
    if n1 == 0 or n2 == 0:
        return 1.0

    # Combine and rank
    combined = [(v, 0, i) for i, v in enumerate(x)] + [(v, 1, i) for i, v in enumerate(y)]
    combined.sort(key=lambda t: t[0])

    # Assign ranks (handle ties by averaging)
    ranks = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0  # 1-based average rank
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j

    # Sum of ranks for group x (group 0)
    r1 = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)

    # U statistic for x
    u1 = r1 - n1 * (n1 + 1) / 2.0

    # Expected value and variance under H0
    mu = n1 * n2 / 2.0

    # Tie correction for variance
    n = n1 + n2
    # Count tie groups
    tie_sum = 0.0
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        t = j - i
        if t > 1:
            tie_sum += t * t * t - t
        i = j

    sigma2 = (n1 * n2 / 12.0) * (n + 1 - tie_sum / (n * (n - 1)))
    if sigma2 <= 0:
        return 1.0

    sigma = math.sqrt(sigma2)

    # Normal approximation with continuity correction
    # For one-sided test (x > y), large U1 means x tends to have higher ranks
    z = (u1 - mu - 0.5) / sigma  # continuity correction

    # P(U >= u1) = P(Z >= z) = 1 - Phi(z)
    p_value = 1.0 - _normal_cdf(z)
    return max(0.0, min(1.0, p_value))


def _get_timestamps(pattern: Tuple[int, ...],
                    item_transaction_map: Dict[int, List[int]]) -> List[int]:
    items = list(pattern)
    if len(items) == 1:
        return item_transaction_map.get(items[0], [])
    lists = [item_transaction_map.get(item, []) for item in items]
    return intersect_sorted_lists(lists)


def run_wilcoxon_baseline(
    txn_path: str,
    events_path: str,
    window_size: int = 50,
    min_support: int = 3,
    max_length: int = 100,
    alpha: float = 0.10,
    min_support_range: int = 10,
    deduplicate: bool = True,
) -> List[WilcoxonResult]:
    """Run Wilcoxon rank-sum test baseline.

    For each pattern P (|P| >= 2) and event e:
      - Compute support time series s_P(t)
      - Split into during=[event_start, event_end] and outside
      - Mann-Whitney U test (one-sided: during > outside)
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
    hypotheses: List[Tuple[Tuple[int, ...], object, float, float, float]] = []

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
            es = event.start
            ee = event.end
            n_windows = len(support)

            during = []
            outside = []
            for t in range(n_windows):
                if t + window_size - 1 >= es and t <= ee:
                    during.append(float(support[t]))
                else:
                    outside.append(float(support[t]))

            if len(during) < 5 or len(outside) < 5:
                continue

            p_value = _mann_whitney_u_test(during, outside)
            mean_d = sum(during) / len(during)
            mean_o = sum(outside) / len(outside)
            hypotheses.append((pattern, event, p_value, mean_d, mean_o))

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
    significant: List[WilcoxonResult] = []
    for i, (pattern, event, p_raw, mean_d, mean_o) in enumerate(hypotheses):
        if adjusted[i] < alpha:
            significant.append(WilcoxonResult(
                pattern=pattern,
                event_name=event.name,
                event_start=event.start,
                event_end=event.end,
                p_value=p_raw,
                adjusted_p_value=adjusted[i],
                mean_during=mean_d,
                mean_outside=mean_o,
            ))

    if not deduplicate or not significant:
        return significant

    return _deduplicate_wilcoxon(significant)


def _deduplicate_wilcoxon(results: List[WilcoxonResult]) -> List[WilcoxonResult]:
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
                           key=lambda i: event_results[i].mean_during - event_results[i].mean_outside)
            kept.append(event_results[best_idx])

    return kept
