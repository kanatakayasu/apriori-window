"""
Spatio-Temporal Event Attribution Pipeline.

Extends the 1D event attribution pipeline to multi-dimensional support surfaces.
Each transaction has a spatial location; events have spatial scopes.
The pipeline detects per-location change points, scores attributions using
temporal proximity × spatial proximity × magnitude, and tests significance
via circular time-shift permutation (preserving spatial structure).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import numpy as np

from multidim_dense import (
    UnionFind as UF_Dense,
    compute_support_surface_naive,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SpatialEvent:
    """External event with temporal range and spatial scope."""
    event_id: str
    name: str
    start: int          # temporal start
    end: int            # temporal end
    spatial_scope: Set[int]  # set of spatial location IDs affected


@dataclass
class STChangePoint:
    """Change point at a specific time and spatial location."""
    time: int
    location: int
    direction: str       # "up" or "down"
    magnitude: float
    support_before: float
    support_after: float


@dataclass
class STAttributionCandidate:
    """Candidate attribution before significance testing."""
    pattern: Tuple[int, ...]
    change_point: STChangePoint
    event: SpatialEvent
    prox_t: float
    prox_s: float
    magnitude: float
    score: float


@dataclass
class STSignificantAttribution:
    """Significant attribution result after testing."""
    pattern: Tuple[int, ...]
    change_time: int
    change_location: int
    change_direction: str
    change_magnitude: float
    event_name: str
    event_id: str
    event_start: int
    event_end: int
    prox_t: float
    prox_s: float
    attribution_score: float
    p_value: float
    adjusted_p_value: float


@dataclass
class STAttributionConfig:
    """Configuration for the spatio-temporal attribution pipeline."""
    # Change detection
    min_magnitude: float = 0.0
    min_support_range: int = 0
    level_window: int = 20
    max_cps_per_location: int = 3    # top-K changepoints per location

    # Attribution scoring
    sigma_t: Optional[float] = None   # temporal decay (default: window_t / 4)
    sigma_s: float = 3.0              # spatial decay
    attribution_threshold: float = 0.01

    # Significance testing
    n_permutations: int = 1000
    alpha: float = 0.10
    correction_method: str = "bh"    # "bh" or "bonferroni"
    seed: Optional[int] = None

    # Post-processing
    deduplicate_overlap: bool = True


# ---------------------------------------------------------------------------
# Step 1: Support surface computation
# ---------------------------------------------------------------------------

def compute_support_surface(
    transactions: List[Set[int]],
    locations: List[int],
    pattern: FrozenSet[int],
    window_t: int,
    window_s: int,
    n_locations: int,
) -> np.ndarray:
    """
    Compute 2D support surface S_P(t, v).

    Returns ndarray of shape (T - window_t + 1, n_locations - window_s + 1).
    """
    N = len(transactions)
    # Convert locations to list of 1-tuples for multidim_dense API
    locs_tuples = [(loc,) for loc in locations]
    grid_shape = (N, n_locations)
    window_sizes = (window_t, window_s)

    surface = compute_support_surface_naive(
        transactions, locs_tuples, pattern, window_sizes, grid_shape
    )
    return surface


def compute_support_surface_direct(
    transactions: List[Set[int]],
    locations: List[int],
    pattern: FrozenSet[int],
    window_t: int,
    n_locations: int,
) -> np.ndarray:
    """
    Compute support surface with window_s=1 (per-location temporal series).

    Returns ndarray of shape (N - window_t + 1, n_locations).
    Each column is the temporal support series at that location.
    """
    N = len(transactions)
    T = N - window_t + 1
    if T <= 0:
        return np.zeros((0, n_locations), dtype=np.int32)

    # Precompute which transactions match the pattern at each location
    surface = np.zeros((T, n_locations), dtype=np.int32)

    # Build per-location match lists
    loc_matches: Dict[int, List[int]] = {v: [] for v in range(n_locations)}
    for t in range(N):
        if pattern.issubset(transactions[t]):
            loc = locations[t]
            if 0 <= loc < n_locations:
                loc_matches[loc].append(t)

    # For each location, compute windowed count via sliding window
    for v in range(n_locations):
        matches = loc_matches[v]
        if not matches:
            continue
        match_set = sorted(matches)
        # Two-pointer sliding window
        left_ptr = 0
        for t in range(T):
            # Window: [t, t + window_t)
            while left_ptr < len(match_set) and match_set[left_ptr] < t:
                left_ptr += 1
            right_ptr = left_ptr
            while right_ptr < len(match_set) and match_set[right_ptr] < t + window_t:
                right_ptr += 1
            surface[t, v] = right_ptr - left_ptr

    return surface


# ---------------------------------------------------------------------------
# Step 2: Per-location change point detection
# ---------------------------------------------------------------------------

def detect_changepoints_per_location(
    surface: np.ndarray,
    threshold: int,
    config: STAttributionConfig,
) -> List[STChangePoint]:
    """
    Detect threshold-crossing change points at each spatial location.

    For each column v of the surface (a 1D temporal series),
    find times where support crosses the threshold.
    Returns only the top changepoint per location (highest magnitude)
    to avoid diluting signal with noisy oscillations.
    """
    T, n_locs = surface.shape
    h = config.level_window
    changepoints = []

    for v in range(n_locs):
        series = surface[:, v]
        max_s = int(np.max(series))
        min_s = int(np.min(series))

        # Support range filter
        if config.min_support_range > 0 and (max_s - min_s) < config.min_support_range:
            continue

        # Collect all threshold crossings at this location
        loc_cps = []
        for t in range(T):
            is_up = (series[t] >= threshold and
                     (t == 0 or series[t - 1] < threshold))
            is_down = (series[t] < threshold and
                       t > 0 and series[t - 1] >= threshold)

            if not is_up and not is_down:
                continue

            direction = "up" if is_up else "down"

            # Compute magnitude: mean of [t-h, t) vs [t, t+h)
            before_start = max(0, t - h)
            after_end = min(T, t + h)
            before = series[before_start:t] if t > 0 else np.array([0.0])
            after = series[t:after_end] if after_end > t else np.array([0.0])

            mean_before = float(np.mean(before)) if len(before) > 0 else 0.0
            mean_after = float(np.mean(after)) if len(after) > 0 else 0.0
            mag = abs(mean_after - mean_before)

            if mag < config.min_magnitude:
                continue

            loc_cps.append(STChangePoint(
                time=t, location=v, direction=direction,
                magnitude=mag,
                support_before=mean_before, support_after=mean_after,
            ))

        # Keep top-K changepoints per location (highest magnitude)
        if loc_cps:
            k = config.max_cps_per_location
            loc_cps.sort(key=lambda cp: cp.magnitude, reverse=True)
            changepoints.extend(loc_cps[:k])

    return changepoints


# ---------------------------------------------------------------------------
# Step 3: Spatio-temporal attribution scoring
# ---------------------------------------------------------------------------

def compute_prox_t(cp_time: int, event: SpatialEvent, sigma_t: float) -> float:
    """Temporal proximity: exp(-dist / sigma_t)."""
    dist = min(abs(cp_time - event.start), abs(cp_time - event.end))
    return math.exp(-dist / sigma_t) if sigma_t > 0 else (1.0 if dist == 0 else 0.0)


def compute_prox_s(cp_location: int, event: SpatialEvent, sigma_s: float) -> float:
    """Spatial proximity: 1.0 if inside scope, exp(-dist / sigma_s) otherwise."""
    if cp_location in event.spatial_scope:
        return 1.0
    if not event.spatial_scope:
        return 1.0
    dist = min(abs(cp_location - v) for v in event.spatial_scope)
    return math.exp(-dist / sigma_s)


def score_attributions(
    pattern: Tuple[int, ...],
    changepoints: List[STChangePoint],
    events: List[SpatialEvent],
    sigma_t: float,
    sigma_s: float,
    threshold: float,
) -> List[STAttributionCandidate]:
    """Score all (change_point, event) pairs."""
    candidates = []
    for cp in changepoints:
        for event in events:
            pt = compute_prox_t(cp.time, event, sigma_t)
            ps = compute_prox_s(cp.location, event, sigma_s)
            score = pt * ps * cp.magnitude
            if score >= threshold:
                candidates.append(STAttributionCandidate(
                    pattern=pattern, change_point=cp, event=event,
                    prox_t=pt, prox_s=ps, magnitude=cp.magnitude,
                    score=score,
                ))
    return candidates


# ---------------------------------------------------------------------------
# Step 4: Spatio-temporal permutation test
# ---------------------------------------------------------------------------

def circular_shift_events(
    events: List[SpatialEvent],
    offset: int,
    max_time: int,
) -> List[SpatialEvent]:
    """Shift event times circularly, preserving spatial scope."""
    shifted = []
    for e in events:
        duration = e.end - e.start
        new_start = (e.start + offset) % max_time
        new_end = new_start + duration
        shifted.append(SpatialEvent(
            event_id=e.event_id, name=e.name,
            start=new_start, end=new_end,
            spatial_scope=e.spatial_scope,  # PRESERVED
        ))
    return shifted


def permutation_test(
    pattern: Tuple[int, ...],
    changepoints: List[STChangePoint],
    events: List[SpatialEvent],
    max_time: int,
    config: STAttributionConfig,
    sigma_t: float,
    sigma_s: float,
) -> Dict[str, Tuple[float, float]]:
    """
    Run circular-shift permutation test.

    Returns dict: event_id -> (observed_score, p_value)
    """
    if not changepoints or not events:
        return {}

    # Compute observed scores per event (sum across changepoints)
    candidates = score_attributions(
        pattern, changepoints, events, sigma_t, sigma_s, 0.0
    )
    obs_scores: Dict[str, float] = {}
    for c in candidates:
        obs_scores[c.event.event_id] = obs_scores.get(c.event.event_id, 0.0) + c.score

    if not obs_scores:
        return {}

    # Permutations
    rng = random.Random(config.seed)
    count_ge: Dict[str, int] = {eid: 0 for eid in obs_scores}

    for _ in range(config.n_permutations):
        offset = rng.randint(1, max_time - 1)
        shifted_events = circular_shift_events(events, offset, max_time)
        perm_candidates = score_attributions(
            pattern, changepoints, shifted_events, sigma_t, sigma_s, 0.0
        )
        perm_scores: Dict[str, float] = {}
        for c in perm_candidates:
            perm_scores[c.event.event_id] = perm_scores.get(c.event.event_id, 0.0) + c.score

        for eid, obs in obs_scores.items():
            if perm_scores.get(eid, 0.0) >= obs:
                count_ge[eid] += 1

    results = {}
    for eid, obs in obs_scores.items():
        p_value = (count_ge[eid] + 1) / (config.n_permutations + 1)
        results[eid] = (obs, p_value)

    return results


# ---------------------------------------------------------------------------
# Step 5: Global BH correction
# ---------------------------------------------------------------------------

def bh_correction(
    raw_results: List[Tuple[Tuple[int, ...], str, float, float]],
    alpha: float,
    method: str = "bh",
) -> List[Tuple[Tuple[int, ...], str, float, float, float]]:
    """
    Apply BH or Bonferroni correction.

    Input: list of (pattern, event_id, obs_score, p_value)
    Output: list of (pattern, event_id, obs_score, p_value, adj_p_value) for significant ones
    """
    if not raw_results:
        return []

    n = len(raw_results)

    if method == "bonferroni":
        results = []
        for pat, eid, score, p in raw_results:
            adj_p = min(1.0, p * n)
            if adj_p < alpha:
                results.append((pat, eid, score, p, adj_p))
        return results

    # BH step-down
    indexed = sorted(enumerate(raw_results), key=lambda x: x[1][3])  # sort by p
    adj_p = [0.0] * n

    for rank, (orig_idx, (pat, eid, score, p)) in enumerate(indexed):
        raw_adj = p * n / (rank + 1)
        adj_p[orig_idx] = min(1.0, raw_adj)

    # Step-down monotonicity (process in reverse sorted order)
    sorted_indices = [orig_idx for orig_idx, _ in indexed]
    for i in range(n - 2, -1, -1):
        idx = sorted_indices[i]
        idx_next = sorted_indices[i + 1]
        adj_p[idx] = min(adj_p[idx], adj_p[idx_next])

    results = []
    for i, (pat, eid, score, p) in enumerate(raw_results):
        if adj_p[i] < alpha:
            results.append((pat, eid, score, p, adj_p[i]))

    return results


# ---------------------------------------------------------------------------
# Step 6: Union-Find deduplication
# ---------------------------------------------------------------------------

def deduplicate_by_item_overlap(
    results: List[STSignificantAttribution],
) -> List[STSignificantAttribution]:
    """Remove overlapping patterns per event, keeping highest score."""
    by_event: Dict[str, List[STSignificantAttribution]] = {}
    for r in results:
        by_event.setdefault(r.event_name, []).append(r)

    final = []
    for event_name, group in by_event.items():
        if len(group) <= 1:
            final.extend(group)
            continue

        n = len(group)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Build item -> index map
        item_to_indices: Dict[int, List[int]] = {}
        for i, r in enumerate(group):
            for item in r.pattern:
                item_to_indices.setdefault(item, []).append(i)

        # Union patterns sharing items
        for item, indices in item_to_indices.items():
            for j in range(1, len(indices)):
                union(indices[0], indices[j])

        # Keep best per cluster
        clusters: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            clusters.setdefault(root, []).append(i)

        for cluster_indices in clusters.values():
            best_idx = max(cluster_indices, key=lambda i: group[i].attribution_score)
            final.append(group[best_idx])

    return final


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_st_attribution_pipeline(
    transactions: List[Set[int]],
    locations: List[int],
    n_locations: int,
    frequents: Dict[FrozenSet[int], List],
    events: List[SpatialEvent],
    window_t: int,
    threshold: int,
    config: Optional[STAttributionConfig] = None,
) -> List[STSignificantAttribution]:
    """
    Run the full spatio-temporal event attribution pipeline.

    Parameters
    ----------
    transactions : list of sets - transaction data
    locations : list of int - spatial location for each transaction
    n_locations : int - total number of spatial locations
    frequents : dict - {pattern: dense_intervals} from Phase 1 (or empty lists)
    events : list of SpatialEvent
    window_t : int - temporal window size
    threshold : int - min support threshold
    config : STAttributionConfig

    Returns
    -------
    List of STSignificantAttribution
    """
    if config is None:
        config = STAttributionConfig()

    sigma_t = config.sigma_t if config.sigma_t is not None else float(window_t) / 4.0
    sigma_s = config.sigma_s
    N = len(transactions)
    max_time = N - window_t + 1

    if config.seed is not None:
        random.seed(config.seed)

    # Collect all raw test results across patterns
    all_raw: List[Tuple[Tuple[int, ...], str, float, float, List[STChangePoint], List[SpatialEvent]]] = []

    for pattern_fs in frequents:
        pattern = tuple(sorted(pattern_fs))
        if len(pattern) < 2:
            continue

        # Step 1: Compute per-location support surface
        surface = compute_support_surface_direct(
            transactions, locations, pattern_fs, window_t, n_locations
        )
        if surface.size == 0:
            continue

        # Step 2: Detect change points per location
        changepoints = detect_changepoints_per_location(surface, threshold, config)
        if not changepoints:
            continue

        # Step 3-4: Score + permutation test
        test_results = permutation_test(
            pattern, changepoints, events, max_time, config, sigma_t, sigma_s
        )

        for eid, (obs_score, p_value) in test_results.items():
            # Pre-filter: only test hypotheses with nonzero observed score
            if obs_score > 0.001:
                all_raw.append((pattern, eid, obs_score, p_value, changepoints, events))

    # Step 5: Global BH correction
    raw_for_correction = [(pat, eid, score, pval) for pat, eid, score, pval, _, _ in all_raw]
    significant = bh_correction(raw_for_correction, config.alpha, config.correction_method)

    # Build significant attributions with detail
    sig_set = {(pat, eid) for pat, eid, _, _, _ in significant}
    sig_scores = {(pat, eid): (score, pval, adj_p) for pat, eid, score, pval, adj_p in significant}

    # Build event lookup
    event_map = {e.event_id: e for e in events}

    results = []
    for pat, eid, score, pval, changepoints, _ in all_raw:
        if (pat, eid) not in sig_set:
            continue
        obs_score, p_value, adj_p = sig_scores[(pat, eid)]
        event = event_map[eid]

        # Find best change point for this (pattern, event) pair
        best_cp = None
        best_cp_score = -1
        for cp in changepoints:
            pt = compute_prox_t(cp.time, event, sigma_t)
            ps = compute_prox_s(cp.location, event, sigma_s)
            s = pt * ps * cp.magnitude
            if s > best_cp_score:
                best_cp_score = s
                best_cp = cp

        if best_cp is None:
            continue

        results.append(STSignificantAttribution(
            pattern=pat,
            change_time=best_cp.time,
            change_location=best_cp.location,
            change_direction=best_cp.direction,
            change_magnitude=best_cp.magnitude,
            event_name=event.name,
            event_id=event.event_id,
            event_start=event.start,
            event_end=event.end,
            prox_t=compute_prox_t(best_cp.time, event, sigma_t),
            prox_s=compute_prox_s(best_cp.location, event, sigma_s),
            attribution_score=obs_score,
            p_value=p_value,
            adjusted_p_value=adj_p,
        ))

    # Step 6: Deduplication
    if config.deduplicate_overlap:
        results = deduplicate_by_item_overlap(results)

    return results


# ---------------------------------------------------------------------------
# 1D baseline: aggregate across all locations
# ---------------------------------------------------------------------------

def run_1d_baseline_pipeline(
    transactions: List[Set[int]],
    locations: List[int],
    n_locations: int,
    frequents: Dict[FrozenSet[int], List],
    events: List[SpatialEvent],
    window_t: int,
    threshold: int,
    config: Optional[STAttributionConfig] = None,
) -> List[STSignificantAttribution]:
    """
    1D baseline: ignore spatial dimension, aggregate support across all locations.

    This is equivalent to the main branch pipeline applied to the full dataset
    without spatial information.
    """
    if config is None:
        config = STAttributionConfig()

    sigma_t = config.sigma_t if config.sigma_t is not None else float(window_t) / 4.0
    N = len(transactions)
    T = N - window_t + 1
    max_time = T

    if config.seed is not None:
        random.seed(config.seed)

    all_raw = []

    for pattern_fs in frequents:
        pattern = tuple(sorted(pattern_fs))
        if len(pattern) < 2:
            continue

        # Compute global (non-spatial) support time series
        series = np.zeros(T, dtype=np.int32)
        match_times = sorted(t for t in range(N) if pattern_fs.issubset(transactions[t]))
        left = 0
        for t in range(T):
            while left < len(match_times) and match_times[left] < t:
                left += 1
            right = left
            while right < len(match_times) and match_times[right] < t + window_t:
                right += 1
            series[t] = right - left

        # Detect change points
        h = config.level_window
        changepoints = []
        max_s, min_s = int(np.max(series)), int(np.min(series))
        if config.min_support_range > 0 and (max_s - min_s) < config.min_support_range:
            continue

        for t in range(T):
            is_up = series[t] >= threshold and (t == 0 or series[t - 1] < threshold)
            is_down = series[t] < threshold and t > 0 and series[t - 1] >= threshold

            if not is_up and not is_down:
                continue

            direction = "up" if is_up else "down"
            before = series[max(0, t - h):t]
            after = series[t:min(T, t + h)]
            mean_before = float(np.mean(before)) if len(before) > 0 else 0.0
            mean_after = float(np.mean(after)) if len(after) > 0 else 0.0
            mag = abs(mean_after - mean_before)

            if mag < config.min_magnitude:
                continue

            changepoints.append(STChangePoint(
                time=t, location=-1, direction=direction,
                magnitude=mag, support_before=mean_before, support_after=mean_after,
            ))

        if not changepoints:
            continue

        # Keep only the top changepoint (highest magnitude) for 1D
        changepoints = [max(changepoints, key=lambda cp: cp.magnitude)]

        # Score with prox_t only (no spatial proximity), sum per event
        obs_scores: Dict[str, float] = {}
        for cp in changepoints:
            for event in events:
                pt = compute_prox_t(cp.time, event, sigma_t)
                score = pt * cp.magnitude  # No prox_s
                obs_scores[event.event_id] = obs_scores.get(event.event_id, 0.0) + score

        # Permutation test
        rng = random.Random(config.seed)
        count_ge = {eid: 0 for eid in obs_scores}
        for _ in range(config.n_permutations):
            offset = rng.randint(1, max_time - 1)
            shifted = circular_shift_events(events, offset, max_time)
            perm_scores: Dict[str, float] = {}
            for cp in changepoints:
                for ev in shifted:
                    pt = compute_prox_t(cp.time, ev, sigma_t)
                    s = pt * cp.magnitude
                    perm_scores[ev.event_id] = perm_scores.get(ev.event_id, 0.0) + s
            for eid, obs in obs_scores.items():
                if perm_scores.get(eid, 0.0) >= obs:
                    count_ge[eid] += 1

        for eid, obs in obs_scores.items():
            if obs <= 0.001:
                continue  # Pre-filter zero-score hypotheses
            p_val = (count_ge[eid] + 1) / (config.n_permutations + 1)
            all_raw.append((pattern, eid, obs, p_val))

    # BH correction
    significant = bh_correction(all_raw, config.alpha, config.correction_method)

    event_map = {e.event_id: e for e in events}
    results = []
    for pat, eid, score, pval, adj_p in significant:
        event = event_map[eid]
        results.append(STSignificantAttribution(
            pattern=pat, change_time=-1, change_location=-1,
            change_direction="", change_magnitude=0.0,
            event_name=event.name, event_id=eid,
            event_start=event.start, event_end=event.end,
            prox_t=0.0, prox_s=0.0, attribution_score=score,
            p_value=pval, adjusted_p_value=adj_p,
        ))

    if config.deduplicate_overlap:
        results = deduplicate_by_item_overlap(results)

    return results
