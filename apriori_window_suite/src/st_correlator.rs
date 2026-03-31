//! Spatio-Temporal Event Attribution Pipeline.
//!
//! Extends the 1D event attribution pipeline to multi-dimensional support surfaces.
//! Each transaction has a spatial location; events have spatial scopes.
//! The pipeline detects per-location change points, scores attributions using
//! temporal proximity × spatial proximity × magnitude, and tests significance
//! via circular time-shift permutation (preserving spatial structure).

use std::collections::{HashMap, HashSet};

use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

/// External event with spatial scope.
#[derive(Debug, Clone, Deserialize)]
pub struct SpatialEvent {
    pub event_id: String,
    pub name: String,
    pub start: i64,
    pub end: i64,
    pub spatial_scope: Vec<usize>,
}

/// Direction of a change point.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Direction {
    Up,
    Down,
}

/// Change point at a specific time and spatial location.
#[derive(Debug, Clone)]
pub struct STChangePoint {
    pub time: i64,
    pub location: usize,
    pub direction: Direction,
    pub magnitude: f64,
    pub support_before: f64,
    pub support_after: f64,
}

/// Configuration for the ST attribution pipeline.
#[derive(Debug, Clone)]
pub struct STConfig {
    /// Minimum magnitude to report a change point.
    pub min_magnitude: f64,
    /// Minimum range (max - min) of support values per location.
    pub min_support_range: i32,
    /// Window size for magnitude computation (before/after).
    pub level_window: usize,
    /// Keep top-K change points per location.
    pub max_cps_per_location: usize,
    /// Temporal decay parameter (default: window_t / 4).
    pub sigma_t: Option<f64>,
    /// Spatial decay parameter.
    pub sigma_s: f64,
    /// Pre-filter threshold for attribution scores.
    pub attribution_threshold: f64,
    /// Number of permutation replicates.
    pub n_permutations: usize,
    /// Significance level.
    pub alpha: f64,
    /// Multiple testing correction: "bh" or "bonferroni".
    pub correction_method: String,
    /// Deduplicate overlapping patterns via Union-Find.
    pub deduplicate_overlap: bool,
    /// Random seed.
    pub seed: Option<u64>,
}

impl Default for STConfig {
    fn default() -> Self {
        Self {
            min_magnitude: 0.0,
            min_support_range: 0,
            level_window: 20,
            max_cps_per_location: 3,
            sigma_t: None,
            sigma_s: 3.0,
            attribution_threshold: 0.01,
            n_permutations: 1000,
            alpha: 0.10,
            correction_method: "bh".to_string(),
            deduplicate_overlap: true,
            seed: None,
        }
    }
}

/// Significant attribution result.
#[derive(Debug, Clone, Serialize)]
pub struct STAttribution {
    pub pattern: Vec<i64>,
    pub change_time: i64,
    pub change_location: usize,
    pub change_direction: Direction,
    pub change_magnitude: f64,
    pub event_name: String,
    pub event_id: String,
    pub event_start: i64,
    pub event_end: i64,
    pub prox_t: f64,
    pub prox_s: f64,
    pub attribution_score: f64,
    pub p_value: f64,
    pub adjusted_p_value: f64,
}

// ---------------------------------------------------------------------------
// Step 1: Support surface computation
// ---------------------------------------------------------------------------

/// Compute support surface: S_P(t, v) = count of transactions matching P
/// in window [t, t+window_t) at location v.
///
/// Returns a flat array of shape (T, n_locations) in row-major order,
/// where T = n_transactions - window_t + 1.
///
/// Uses two-pointer sliding window per location for O(N) total.
pub fn compute_support_surface(
    transactions: &[HashSet<i64>],
    locations: &[usize],
    pattern: &[i64],
    window_t: usize,
    n_locations: usize,
) -> (Vec<i32>, usize, usize) {
    let n = transactions.len();
    if n < window_t || window_t == 0 {
        return (vec![], 0, n_locations);
    }
    let t_len = n - window_t + 1;

    // Precompute per-location match lists
    let mut loc_matches: Vec<Vec<usize>> = vec![Vec::new(); n_locations];
    for (t, txn) in transactions.iter().enumerate() {
        if pattern.iter().all(|item| txn.contains(item)) {
            let loc = locations[t];
            if loc < n_locations {
                loc_matches[loc].push(t);
            }
        }
    }

    // Compute windowed counts via two-pointer per location
    let mut surface = vec![0i32; t_len * n_locations];

    // Parallelize over locations
    let chunks: Vec<(usize, Vec<i32>)> = (0..n_locations)
        .into_par_iter()
        .filter_map(|v| {
            let matches = &loc_matches[v];
            if matches.is_empty() {
                return None;
            }
            let mut col = vec![0i32; t_len];
            let mut left = 0usize;
            for t in 0..t_len {
                let win_start = t;
                let win_end = t + window_t;
                // Advance left pointer
                while left < matches.len() && matches[left] < win_start {
                    left += 1;
                }
                // Count matches in [win_start, win_end)
                let mut right = left;
                while right < matches.len() && matches[right] < win_end {
                    right += 1;
                }
                col[t] = (right - left) as i32;
            }
            Some((v, col))
        })
        .collect();

    for (v, col) in chunks {
        for t in 0..t_len {
            surface[t * n_locations + v] = col[t];
        }
    }

    (surface, t_len, n_locations)
}

// ---------------------------------------------------------------------------
// Step 2: Per-location change point detection
// ---------------------------------------------------------------------------

/// Detect threshold-crossing change points at each spatial location.
/// Returns top-K per location by magnitude.
pub fn detect_changepoints(
    surface: &[i32],
    t_len: usize,
    n_locations: usize,
    threshold: i32,
    config: &STConfig,
) -> Vec<STChangePoint> {
    let h = config.level_window;

    // Process each location in parallel
    let all_cps: Vec<Vec<STChangePoint>> = (0..n_locations)
        .into_par_iter()
        .map(|v| {
            // Extract column for this location
            let mut series = Vec::with_capacity(t_len);
            for t in 0..t_len {
                series.push(surface[t * n_locations + v]);
            }

            // Support range filter
            if config.min_support_range > 0 {
                let max_s = series.iter().copied().max().unwrap_or(0);
                let min_s = series.iter().copied().min().unwrap_or(0);
                if (max_s - min_s) < config.min_support_range {
                    return Vec::new();
                }
            }

            let mut loc_cps = Vec::new();

            for t in 0..t_len {
                let is_up = series[t] >= threshold
                    && (t == 0 || series[t - 1] < threshold);
                let is_down = series[t] < threshold
                    && t > 0
                    && series[t - 1] >= threshold;

                if !is_up && !is_down {
                    continue;
                }

                let direction = if is_up { Direction::Up } else { Direction::Down };

                // Compute magnitude: mean of [t-h, t) vs [t, t+h)
                let before_start = if t >= h { t - h } else { 0 };
                let after_end = if t + h <= t_len { t + h } else { t_len };

                let before_sum: i64 = if t > before_start {
                    series[before_start..t].iter().map(|&x| x as i64).sum()
                } else {
                    0
                };
                let before_count = (t - before_start) as f64;
                let before_mean = if before_count > 0.0 {
                    before_sum as f64 / before_count
                } else {
                    0.0
                };

                let after_sum: i64 = if after_end > t {
                    series[t..after_end].iter().map(|&x| x as i64).sum()
                } else {
                    0
                };
                let after_count = (after_end - t) as f64;
                let after_mean = if after_count > 0.0 {
                    after_sum as f64 / after_count
                } else {
                    0.0
                };

                let mag = (after_mean - before_mean).abs();
                if mag < config.min_magnitude {
                    continue;
                }

                loc_cps.push(STChangePoint {
                    time: t as i64,
                    location: v,
                    direction,
                    magnitude: mag,
                    support_before: before_mean,
                    support_after: after_mean,
                });
            }

            // Keep top-K by magnitude
            if loc_cps.len() > config.max_cps_per_location {
                loc_cps.sort_by(|a, b| b.magnitude.partial_cmp(&a.magnitude).unwrap());
                loc_cps.truncate(config.max_cps_per_location);
            }

            loc_cps
        })
        .collect();

    all_cps.into_iter().flatten().collect()
}

// ---------------------------------------------------------------------------
// Step 3: Attribution scoring
// ---------------------------------------------------------------------------

/// Temporal proximity: exp(-dist / sigma_t).
#[inline]
fn prox_t(cp_time: i64, event: &SpatialEvent, sigma_t: f64) -> f64 {
    let dist_start = (cp_time - event.start).unsigned_abs() as f64;
    let dist_end = (cp_time - event.end).unsigned_abs() as f64;
    let dist = dist_start.min(dist_end);
    if sigma_t > 0.0 {
        (-dist / sigma_t).exp()
    } else if dist == 0.0 {
        1.0
    } else {
        0.0
    }
}

/// Spatial proximity: 1.0 if inside scope, exp(-dist / sigma_s) outside.
#[inline]
fn prox_s(cp_location: usize, event: &SpatialEvent, sigma_s: f64) -> f64 {
    if event.spatial_scope.contains(&cp_location) {
        return 1.0;
    }
    if event.spatial_scope.is_empty() {
        return 1.0;
    }
    let dist = event
        .spatial_scope
        .iter()
        .map(|&v| (cp_location as i64 - v as i64).unsigned_abs() as f64)
        .fold(f64::MAX, f64::min);
    (-dist / sigma_s).exp()
}

/// Score attribution for a single (changepoint, event) pair.
#[inline]
fn score_single(cp: &STChangePoint, event: &SpatialEvent, sigma_t: f64, sigma_s: f64) -> f64 {
    prox_t(cp.time, event, sigma_t) * prox_s(cp.location, event, sigma_s) * cp.magnitude
}

/// Compute per-event observed scores by summing over all changepoints.
fn compute_event_scores(
    changepoints: &[STChangePoint],
    events: &[SpatialEvent],
    sigma_t: f64,
    sigma_s: f64,
    threshold: f64,
) -> HashMap<String, f64> {
    let mut scores: HashMap<String, f64> = HashMap::new();
    for event in events {
        let mut total = 0.0;
        for cp in changepoints {
            let s = score_single(cp, event, sigma_t, sigma_s);
            if s >= threshold {
                total += s;
            }
        }
        scores.insert(event.event_id.clone(), total);
    }
    scores
}

// ---------------------------------------------------------------------------
// Step 4: Permutation test (circular time-shift, spatial structure preserved)
// ---------------------------------------------------------------------------

/// Circular-shift events in time, preserving spatial scope.
fn circular_shift_events(events: &[SpatialEvent], offset: i64, max_time: i64) -> Vec<SpatialEvent> {
    events
        .iter()
        .map(|e| {
            let duration = e.end - e.start;
            let new_start = ((e.start + offset) % max_time + max_time) % max_time;
            let mut new_end = new_start + duration;
            if new_end >= max_time {
                new_end = max_time - 1;
            }
            SpatialEvent {
                event_id: e.event_id.clone(),
                name: e.name.clone(),
                start: new_start,
                end: new_end,
                spatial_scope: e.spatial_scope.clone(),
            }
        })
        .collect()
}

/// Run permutation test for all events against given changepoints.
/// Returns: event_id → (observed_score, p_value).
///
/// Parallelizes permutation replicates across threads.
fn permutation_test(
    changepoints: &[STChangePoint],
    events: &[SpatialEvent],
    max_time: i64,
    sigma_t: f64,
    sigma_s: f64,
    config: &STConfig,
) -> HashMap<String, (f64, f64)> {
    let threshold = config.attribution_threshold;
    let n_perm = config.n_permutations;

    // Observed scores
    let obs_scores = compute_event_scores(changepoints, events, sigma_t, sigma_s, threshold);

    // Parallel permutation: each thread generates its own RNG from a deterministic seed
    let base_seed = config.seed.unwrap_or(42);
    let n_chunks = rayon::current_num_threads().max(1);
    let perms_per_chunk = (n_perm + n_chunks - 1) / n_chunks;

    // Each chunk returns: HashMap<event_id, count_ge>
    let chunk_results: Vec<HashMap<String, usize>> = (0..n_chunks)
        .into_par_iter()
        .map(|chunk_idx| {
            let mut rng = StdRng::seed_from_u64(base_seed + chunk_idx as u64);
            let start = chunk_idx * perms_per_chunk;
            let end = (start + perms_per_chunk).min(n_perm);
            let mut counts: HashMap<String, usize> = HashMap::new();
            for event in events {
                counts.insert(event.event_id.clone(), 0);
            }

            for _ in start..end {
                let offset = rng.gen_range(1..max_time);
                let shifted = circular_shift_events(events, offset, max_time);
                let perm_scores =
                    compute_event_scores(changepoints, &shifted, sigma_t, sigma_s, threshold);
                for event in events {
                    let perm_s = perm_scores.get(&event.event_id).copied().unwrap_or(0.0);
                    let obs_s = obs_scores.get(&event.event_id).copied().unwrap_or(0.0);
                    if perm_s >= obs_s {
                        *counts.get_mut(&event.event_id).unwrap() += 1;
                    }
                }
            }
            counts
        })
        .collect();

    // Merge chunk results
    let mut total_counts: HashMap<String, usize> = HashMap::new();
    let mut actual_perms = 0usize;
    for (i, chunk) in chunk_results.iter().enumerate() {
        let start = i * perms_per_chunk;
        let end = (start + perms_per_chunk).min(n_perm);
        actual_perms += end - start;
        for (eid, &count) in chunk {
            *total_counts.entry(eid.clone()).or_insert(0) += count;
        }
    }

    // Compute p-values
    let mut results = HashMap::new();
    for event in events {
        let obs = obs_scores.get(&event.event_id).copied().unwrap_or(0.0);
        let count = total_counts.get(&event.event_id).copied().unwrap_or(0);
        let p = (count as f64 + 1.0) / (actual_perms as f64 + 1.0);
        results.insert(event.event_id.clone(), (obs, p));
    }
    results
}

// ---------------------------------------------------------------------------
// Step 5: Multiple testing correction (BH or Bonferroni)
// ---------------------------------------------------------------------------

#[derive(Debug)]
struct RawResult {
    pattern: Vec<i64>,
    event_id: String,
    obs_score: f64,
    p_value: f64,
    // Best changepoint info for this (pattern, event) pair
    best_cp_time: i64,
    best_cp_location: usize,
    best_cp_direction: Direction,
    best_cp_magnitude: f64,
    best_prox_t: f64,
    best_prox_s: f64,
}

fn bh_correction(raw: &mut [RawResult], alpha: f64) -> Vec<(usize, f64)> {
    // Sort by p-value
    let mut indices: Vec<usize> = (0..raw.len()).collect();
    indices.sort_by(|&a, &b| raw[a].p_value.partial_cmp(&raw[b].p_value).unwrap());

    let m = raw.len();
    let mut adj_p = vec![0.0f64; m];

    // Step-up BH procedure
    if m > 0 {
        adj_p[indices[m - 1]] = raw[indices[m - 1]].p_value.min(1.0);
        for i in (0..m - 1).rev() {
            let rank = i + 1;
            let corrected = (raw[indices[i]].p_value * m as f64 / rank as f64).min(1.0);
            adj_p[indices[i]] = corrected.min(adj_p[indices[i + 1]]);
        }
    }

    // Filter significant
    let mut significant = Vec::new();
    for (i, &ap) in adj_p.iter().enumerate() {
        if ap < alpha {
            significant.push((i, ap));
        }
    }
    significant
}

fn bonferroni_correction(raw: &[RawResult], alpha: f64) -> Vec<(usize, f64)> {
    let m = raw.len();
    raw.iter()
        .enumerate()
        .filter_map(|(i, r)| {
            let adj = (r.p_value * m as f64).min(1.0);
            if adj < alpha {
                Some((i, adj))
            } else {
                None
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Step 6: Deduplication (Union-Find)
// ---------------------------------------------------------------------------

struct UnionFind {
    parent: Vec<usize>,
    rank: Vec<usize>,
}

impl UnionFind {
    fn new(n: usize) -> Self {
        Self {
            parent: (0..n).collect(),
            rank: vec![0; n],
        }
    }

    fn find(&mut self, mut x: usize) -> usize {
        while self.parent[x] != x {
            self.parent[x] = self.parent[self.parent[x]]; // path halving
            x = self.parent[x];
        }
        x
    }

    fn union(&mut self, a: usize, b: usize) {
        let ra = self.find(a);
        let rb = self.find(b);
        if ra == rb {
            return;
        }
        if self.rank[ra] < self.rank[rb] {
            self.parent[ra] = rb;
        } else if self.rank[ra] > self.rank[rb] {
            self.parent[rb] = ra;
        } else {
            self.parent[rb] = ra;
            self.rank[ra] += 1;
        }
    }
}

fn deduplicate_by_overlap(results: &mut Vec<STAttribution>) {
    if results.is_empty() {
        return;
    }

    // Group by event
    let mut by_event: HashMap<String, Vec<usize>> = HashMap::new();
    for (i, r) in results.iter().enumerate() {
        by_event
            .entry(r.event_id.clone())
            .or_default()
            .push(i);
    }

    let mut keep = vec![true; results.len()];

    for indices in by_event.values() {
        if indices.len() <= 1 {
            continue;
        }
        let mut uf = UnionFind::new(indices.len());

        // For each item, union all indices containing that item
        let mut item_to_local: HashMap<i64, Vec<usize>> = HashMap::new();
        for (local, &global) in indices.iter().enumerate() {
            for &item in &results[global].pattern {
                item_to_local.entry(item).or_default().push(local);
            }
        }
        for local_indices in item_to_local.values() {
            for i in 1..local_indices.len() {
                uf.union(local_indices[0], local_indices[i]);
            }
        }

        // Per component: keep highest score
        let mut component_best: HashMap<usize, usize> = HashMap::new();
        for (local, &global) in indices.iter().enumerate() {
            let root = uf.find(local);
            let entry = component_best.entry(root).or_insert(local);
            if results[indices[*entry]].attribution_score < results[global].attribution_score {
                *entry = local;
            }
        }

        let best_locals: HashSet<usize> = component_best.values().copied().collect();
        for (local, &global) in indices.iter().enumerate() {
            if !best_locals.contains(&local) {
                keep[global] = false;
            }
        }
    }

    let mut i = 0;
    results.retain(|_| {
        let k = keep[i];
        i += 1;
        k
    });
}

// ---------------------------------------------------------------------------
// Full pipeline
// ---------------------------------------------------------------------------

/// Run the full ST attribution pipeline.
///
/// Input:
/// - transactions: flat transaction data (each is a set of item IDs)
/// - locations: spatial location for each transaction
/// - n_locations: number of distinct spatial locations
/// - frequent_patterns: candidate patterns (sorted item vectors)
/// - events: spatial events with scopes
/// - window_t: temporal window size
/// - threshold: support threshold for change detection
/// - config: pipeline configuration
///
/// Parallelizes across patterns.
pub fn run_st_pipeline(
    transactions: &[HashSet<i64>],
    locations: &[usize],
    n_locations: usize,
    frequent_patterns: &[Vec<i64>],
    events: &[SpatialEvent],
    window_t: usize,
    threshold: i32,
    config: &STConfig,
) -> Vec<STAttribution> {
    let n = transactions.len();
    if n < window_t {
        return Vec::new();
    }
    let t_len = n - window_t + 1;
    let max_time = t_len as i64;
    let sigma_t = config.sigma_t.unwrap_or(window_t as f64 / 4.0);

    // Step 1-4: Process each pattern in parallel
    let all_raw: Vec<RawResult> = frequent_patterns
        .par_iter()
        .flat_map(|pattern| {
            // Step 1: Compute support surface
            let (surface, t_len, n_locs) =
                compute_support_surface(transactions, locations, pattern, window_t, n_locations);
            if surface.is_empty() {
                return Vec::new();
            }

            // Step 2: Detect change points
            let cps = detect_changepoints(&surface, t_len, n_locs, threshold, config);
            if cps.is_empty() {
                return Vec::new();
            }

            // Step 3 & 4: Permutation test
            let test_results =
                permutation_test(&cps, events, max_time, sigma_t, config.sigma_s, config);

            // Build raw results
            let mut raw = Vec::new();
            for (eid, &(obs_score, p_value)) in &test_results {
                if obs_score <= 0.001 {
                    continue; // Pre-filter zero-score hypotheses
                }

                // Find best changepoint for this event
                let event = events.iter().find(|e| &e.event_id == eid).unwrap();
                let mut best_score = 0.0f64;
                let mut best_cp: Option<&STChangePoint> = None;
                for cp in &cps {
                    let s = score_single(cp, event, sigma_t, config.sigma_s);
                    if s > best_score {
                        best_score = s;
                        best_cp = Some(cp);
                    }
                }

                if let Some(cp) = best_cp {
                    raw.push(RawResult {
                        pattern: pattern.clone(),
                        event_id: eid.clone(),
                        obs_score,
                        p_value,
                        best_cp_time: cp.time,
                        best_cp_location: cp.location,
                        best_cp_direction: cp.direction,
                        best_cp_magnitude: cp.magnitude,
                        best_prox_t: prox_t(cp.time, event, sigma_t),
                        best_prox_s: prox_s(cp.location, event, config.sigma_s),
                    });
                }
            }
            raw
        })
        .collect();

    if all_raw.is_empty() {
        return Vec::new();
    }

    // Step 5: Global multiple testing correction
    let mut all_raw = all_raw;
    let significant = if config.correction_method == "bh" {
        bh_correction(&mut all_raw, config.alpha)
    } else {
        bonferroni_correction(&all_raw, config.alpha)
    };

    // Build event map for name lookup
    let event_map: HashMap<&str, &SpatialEvent> =
        events.iter().map(|e| (e.event_id.as_str(), e)).collect();

    let mut results: Vec<STAttribution> = significant
        .iter()
        .map(|&(idx, adj_p)| {
            let r = &all_raw[idx];
            let event = event_map[r.event_id.as_str()];
            STAttribution {
                pattern: r.pattern.clone(),
                change_time: r.best_cp_time,
                change_location: r.best_cp_location,
                change_direction: r.best_cp_direction,
                change_magnitude: r.best_cp_magnitude,
                event_name: event.name.clone(),
                event_id: r.event_id.clone(),
                event_start: event.start,
                event_end: event.end,
                prox_t: r.best_prox_t,
                prox_s: r.best_prox_s,
                attribution_score: r.obs_score,
                p_value: r.p_value,
                adjusted_p_value: adj_p,
            }
        })
        .collect();

    // Step 6: Deduplication
    if config.deduplicate_overlap {
        deduplicate_by_overlap(&mut results);
    }

    // Sort by adjusted p-value
    results.sort_by(|a, b| a.adjusted_p_value.partial_cmp(&b.adjusted_p_value).unwrap());
    results
}

/// Run the 1D baseline pipeline (ignores spatial dimension).
/// Aggregates support across all locations.
pub fn run_1d_baseline_pipeline(
    transactions: &[HashSet<i64>],
    _locations: &[usize],
    _n_locations: usize,
    frequent_patterns: &[Vec<i64>],
    events: &[SpatialEvent],
    window_t: usize,
    threshold: i32,
    config: &STConfig,
) -> Vec<STAttribution> {
    let n = transactions.len();
    if n < window_t {
        return Vec::new();
    }
    let t_len = n - window_t + 1;
    let max_time = t_len as i64;
    let sigma_t = config.sigma_t.unwrap_or(window_t as f64 / 4.0);

    // Process each pattern in parallel
    let all_raw: Vec<RawResult> = frequent_patterns
        .par_iter()
        .flat_map(|pattern| {
            // Compute 1D support series (aggregate across all locations)
            let mut matches: Vec<usize> = Vec::new();
            for (t, txn) in transactions.iter().enumerate() {
                if pattern.iter().all(|item| txn.contains(item)) {
                    matches.push(t);
                }
            }

            if matches.is_empty() {
                return Vec::new();
            }

            // Sliding window support
            let mut series = vec![0i32; t_len];
            let mut left = 0usize;
            for t in 0..t_len {
                while left < matches.len() && matches[left] < t {
                    left += 1;
                }
                let mut right = left;
                while right < matches.len() && matches[right] < t + window_t {
                    right += 1;
                }
                series[t] = (right - left) as i32;
            }

            // Check support range
            let max_s = series.iter().copied().max().unwrap_or(0);
            let min_s = series.iter().copied().min().unwrap_or(0);
            if config.min_support_range > 0 && (max_s - min_s) < config.min_support_range {
                return Vec::new();
            }

            // Detect change points (1D, single location)
            let h = config.level_window;
            let mut cps = Vec::new();
            for t in 0..t_len {
                let is_up = series[t] >= threshold && (t == 0 || series[t - 1] < threshold);
                let is_down = series[t] < threshold && t > 0 && series[t - 1] >= threshold;
                if !is_up && !is_down {
                    continue;
                }
                let direction = if is_up { Direction::Up } else { Direction::Down };

                let before_start = t.saturating_sub(h);
                let after_end = (t + h).min(t_len);
                let before_mean = if t > before_start {
                    series[before_start..t].iter().map(|&x| x as f64).sum::<f64>()
                        / (t - before_start) as f64
                } else {
                    0.0
                };
                let after_mean = if after_end > t {
                    series[t..after_end].iter().map(|&x| x as f64).sum::<f64>()
                        / (after_end - t) as f64
                } else {
                    0.0
                };
                let mag = (after_mean - before_mean).abs();
                if mag < config.min_magnitude {
                    continue;
                }
                cps.push(STChangePoint {
                    time: t as i64,
                    location: 0,
                    direction,
                    magnitude: mag,
                    support_before: before_mean,
                    support_after: after_mean,
                });
            }

            // Keep top-1 by magnitude
            if cps.len() > 1 {
                cps.sort_by(|a, b| b.magnitude.partial_cmp(&a.magnitude).unwrap());
                cps.truncate(1);
            }

            if cps.is_empty() {
                return Vec::new();
            }

            // Permutation test using max score
            let base_seed = config.seed.unwrap_or(42);
            let mut rng = StdRng::seed_from_u64(
                base_seed.wrapping_add(pattern.iter().map(|&x| x as u64).sum::<u64>()),
            );

            let mut test_results = Vec::new();
            for event in events {
                let obs_score = cps
                    .iter()
                    .map(|cp| score_single(cp, event, sigma_t, config.sigma_s))
                    .fold(0.0f64, f64::max);

                if obs_score <= 0.001 {
                    continue;
                }

                let mut count_ge = 0usize;
                for _ in 0..config.n_permutations {
                    let offset = rng.gen_range(1..max_time);
                    let shifted = circular_shift_events(events, offset, max_time);
                    let shifted_event = shifted.iter().find(|e| e.event_id == event.event_id).unwrap();
                    let perm_score = cps
                        .iter()
                        .map(|cp| score_single(cp, shifted_event, sigma_t, config.sigma_s))
                        .fold(0.0f64, f64::max);
                    if perm_score >= obs_score {
                        count_ge += 1;
                    }
                }

                let p = (count_ge as f64 + 1.0) / (config.n_permutations as f64 + 1.0);
                let best_cp = cps
                    .iter()
                    .max_by(|a, b| {
                        score_single(a, event, sigma_t, config.sigma_s)
                            .partial_cmp(&score_single(b, event, sigma_t, config.sigma_s))
                            .unwrap()
                    })
                    .unwrap();

                test_results.push(RawResult {
                    pattern: pattern.clone(),
                    event_id: event.event_id.clone(),
                    obs_score,
                    p_value: p,
                    best_cp_time: best_cp.time,
                    best_cp_location: best_cp.location,
                    best_cp_direction: best_cp.direction,
                    best_cp_magnitude: best_cp.magnitude,
                    best_prox_t: prox_t(best_cp.time, event, sigma_t),
                    best_prox_s: prox_s(best_cp.location, event, config.sigma_s),
                });
            }
            test_results
        })
        .collect();

    if all_raw.is_empty() {
        return Vec::new();
    }

    let mut all_raw = all_raw;
    let significant = if config.correction_method == "bh" {
        bh_correction(&mut all_raw, config.alpha)
    } else {
        bonferroni_correction(&all_raw, config.alpha)
    };

    let event_map: HashMap<&str, &SpatialEvent> =
        events.iter().map(|e| (e.event_id.as_str(), e)).collect();

    let mut results: Vec<STAttribution> = significant
        .iter()
        .map(|&(idx, adj_p)| {
            let r = &all_raw[idx];
            let event = event_map[r.event_id.as_str()];
            STAttribution {
                pattern: r.pattern.clone(),
                change_time: r.best_cp_time,
                change_location: r.best_cp_location,
                change_direction: r.best_cp_direction,
                change_magnitude: r.best_cp_magnitude,
                event_name: event.name.clone(),
                event_id: r.event_id.clone(),
                event_start: event.start,
                event_end: event.end,
                prox_t: r.best_prox_t,
                prox_s: r.best_prox_s,
                attribution_score: r.obs_score,
                p_value: r.p_value,
                adjusted_p_value: adj_p,
            }
        })
        .collect();

    if config.deduplicate_overlap {
        deduplicate_by_overlap(&mut results);
    }

    results.sort_by(|a, b| a.adjusted_p_value.partial_cmp(&b.adjusted_p_value).unwrap());
    results
}

// ---------------------------------------------------------------------------
// I/O helpers
// ---------------------------------------------------------------------------

/// Read transactions as sets of items (flat format, one line per transaction).
pub fn read_transactions_flat(path: &str) -> Vec<HashSet<i64>> {
    let file = std::fs::File::open(path).expect("failed to open transactions file");
    let reader = std::io::BufReader::new(file);
    reader
        .lines()
        .map(|line| {
            let line = line.expect("failed to read line");
            line.split_whitespace()
                .filter_map(|x| x.parse::<i64>().ok())
                .collect()
        })
        .collect()
}

/// Read location assignments (one integer per line).
pub fn read_locations(path: &str) -> Vec<usize> {
    let file = std::fs::File::open(path).expect("failed to open locations file");
    let reader = std::io::BufReader::new(file);
    reader
        .lines()
        .map(|line| {
            let line = line.expect("failed to read line");
            line.trim().parse::<usize>().expect("invalid location")
        })
        .collect()
}

/// Read spatial events from JSON.
pub fn read_spatial_events(path: &str) -> Vec<SpatialEvent> {
    let text = std::fs::read_to_string(path).expect("failed to read spatial events");
    serde_json::from_str(&text).expect("failed to parse spatial events JSON")
}

use std::io::BufRead;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn make_transactions(n: usize, pattern: &[i64], boost_range: (usize, usize), boost_locs: &[usize], locations: &[usize]) -> Vec<HashSet<i64>> {
        let mut txns = Vec::with_capacity(n);
        let mut rng = StdRng::seed_from_u64(42);
        for t in 0..n {
            let mut items: HashSet<i64> = HashSet::new();
            // Random background items
            for _ in 0..5 {
                items.insert(rng.gen_range(100..200));
            }
            // Boost pattern in specific range and locations
            if t >= boost_range.0 && t < boost_range.1 && boost_locs.contains(&locations[t]) {
                if rng.gen::<f64>() < 0.5 {
                    for &item in pattern {
                        items.insert(item);
                    }
                }
            }
            txns.push(items);
        }
        txns
    }

    #[test]
    fn test_support_surface_basic() {
        let txns: Vec<HashSet<i64>> = vec![
            [1, 2].iter().copied().collect(),
            [1, 3].iter().copied().collect(),
            [1, 2].iter().copied().collect(),
            [3, 4].iter().copied().collect(),
            [1, 2].iter().copied().collect(),
        ];
        let locs = vec![0, 0, 1, 1, 0];
        let pattern = vec![1, 2];
        let (surface, t_len, n_locs) = compute_support_surface(&txns, &locs, &pattern, 3, 2);
        assert_eq!(t_len, 3);
        assert_eq!(n_locs, 2);
        // Window [0,3): loc0 has txn0,txn1→{1,2} at t=0 → match; loc1 has txn2 → match
        assert!(surface[0 * 2 + 0] >= 1); // loc 0 window [0,3)
    }

    #[test]
    fn test_detect_changepoints_up() {
        // Simulate a surface where loc 0 goes from 0 to 5
        let n_locs = 2;
        let t_len = 20;
        let mut surface = vec![0i32; t_len * n_locs];
        for t in 10..20 {
            surface[t * n_locs + 0] = 5;
        }
        let config = STConfig {
            min_support_range: 0,
            max_cps_per_location: 3,
            level_window: 5,
            ..Default::default()
        };
        let cps = detect_changepoints(&surface, t_len, n_locs, 3, &config);
        assert!(!cps.is_empty());
        assert!(cps.iter().any(|cp| cp.direction == Direction::Up && cp.location == 0));
    }

    #[test]
    fn test_prox_t_at_event() {
        let event = SpatialEvent {
            event_id: "E1".into(),
            name: "test".into(),
            start: 100,
            end: 200,
            spatial_scope: vec![0, 1],
        };
        let p = prox_t(100, &event, 50.0);
        assert!((p - 1.0).abs() < 1e-10); // At event start → dist=0 → prox=1.0
    }

    #[test]
    fn test_prox_s_in_scope() {
        let event = SpatialEvent {
            event_id: "E1".into(),
            name: "test".into(),
            start: 0,
            end: 100,
            spatial_scope: vec![0, 1, 2],
        };
        assert_eq!(prox_s(1, &event, 3.0), 1.0);
    }

    #[test]
    fn test_prox_s_out_of_scope() {
        let event = SpatialEvent {
            event_id: "E1".into(),
            name: "test".into(),
            start: 0,
            end: 100,
            spatial_scope: vec![0, 1, 2],
        };
        let p = prox_s(5, &event, 3.0);
        assert!(p < 1.0);
        assert!(p > 0.0);
    }

    #[test]
    fn test_circular_shift() {
        let events = vec![SpatialEvent {
            event_id: "E1".into(),
            name: "test".into(),
            start: 10,
            end: 20,
            spatial_scope: vec![0],
        }];
        let shifted = circular_shift_events(&events, 90, 100);
        assert_eq!(shifted[0].start, 0); // (10 + 90) % 100 = 0
    }

    #[test]
    fn test_bh_correction_basic() {
        let mut raw = vec![
            RawResult {
                pattern: vec![1, 2],
                event_id: "E1".into(),
                obs_score: 5.0,
                p_value: 0.01,
                best_cp_time: 10,
                best_cp_location: 0,
                best_cp_direction: Direction::Up,
                best_cp_magnitude: 5.0,
                best_prox_t: 1.0,
                best_prox_s: 1.0,
            },
            RawResult {
                pattern: vec![3, 4],
                event_id: "E2".into(),
                obs_score: 2.0,
                p_value: 0.50,
                best_cp_time: 20,
                best_cp_location: 1,
                best_cp_direction: Direction::Up,
                best_cp_magnitude: 2.0,
                best_prox_t: 0.5,
                best_prox_s: 1.0,
            },
        ];
        let sig = bh_correction(&mut raw, 0.10);
        assert_eq!(sig.len(), 1); // Only p=0.01 should pass
        assert_eq!(sig[0].0, 0);
    }

    #[test]
    fn test_full_pipeline_smoke() {
        let n = 2000;
        let n_locs = 10;
        let pattern = vec![50, 51];
        let mut rng = StdRng::seed_from_u64(42);
        let locations: Vec<usize> = (0..n).map(|_| rng.gen_range(0..n_locs)).collect();

        let txns = make_transactions(n, &pattern, (500, 1000), &[0, 1, 2, 3, 4], &locations);

        let events = vec![SpatialEvent {
            event_id: "EVT".into(),
            name: "test_event".into(),
            start: 500,
            end: 1000,
            spatial_scope: vec![0, 1, 2, 3, 4],
        }];

        let config = STConfig {
            min_support_range: 2,
            n_permutations: 200,
            alpha: 0.10,
            seed: Some(42),
            ..Default::default()
        };

        let results = run_st_pipeline(
            &txns,
            &locations,
            n_locs,
            &[pattern],
            &events,
            200,
            3,
            &config,
        );

        // Smoke test: pipeline runs without error
        // Results may or may not be significant depending on random data
        println!("ST pipeline returned {} results", results.len());
    }
}
