//! Baseline methods for event attribution comparison.
//!
//! Five statistical baselines sharing Phase 1 (Apriori-window), amplitude filter,
//! BH correction, and Union-Find deduplication:
//!   1. Wilcoxon (Mann-Whitney U)
//!   2. CausalImpact (OLS + cumulative impact)
//!   3. ITS (Interrupted Time Series)
//!   4. EventStudy (Abnormal support accumulation)
//!   5. ECA (Event Coincidence Analysis)

use std::collections::{HashMap, HashSet};

use rayon::prelude::*;
use serde::Serialize;

use crate::correlator::bh_correction;
use crate::io::Event;
use crate::util::{intersect_sorted_lists, lower_bound, upper_bound};

// ---------------------------------------------------------------------------
// Shared Types
// ---------------------------------------------------------------------------

/// Result from a baseline method (post-BH correction).
#[derive(Debug, Clone, Serialize)]
pub struct BaselineResult {
    pub pattern: Vec<i64>,
    pub event_name: String,
    pub event_start: i64,
    pub event_end: i64,
    pub p_value: f64,
    pub adjusted_p_value: f64,
}

/// Input data for baseline methods (pre-processed Phase 1 output).
pub struct PatternData {
    pub frequents: HashMap<Vec<i64>, Vec<(i64, i64)>>,
    pub item_transaction_map: HashMap<i64, Vec<i64>>,
    pub n_transactions: i64,
}

/// Parameters for baseline methods.
pub struct BaselineParams {
    pub window_size: i64,
    pub alpha: f64,
    pub min_support_range: i64,
    pub deduplicate: bool,
}

// ---------------------------------------------------------------------------
// Support Time Series
// ---------------------------------------------------------------------------

/// Compute full support time series using two-pointer O(N) sweep.
///
/// Returns `s_P(t)` for `t` in `0..n_windows` where
/// `n_windows = n_transactions - window_size + 1`.
///
/// Each entry counts how many timestamps fall in `[t, t + window_size)`.
pub fn compute_support_series(
    timestamps: &[i64],
    window_size: i64,
    n_transactions: i64,
) -> Vec<i64> {
    let n_windows = (n_transactions - window_size + 1).max(0) as usize;
    if n_windows == 0 || timestamps.is_empty() {
        return vec![0; n_windows];
    }

    let mut series = Vec::with_capacity(n_windows);
    let mut left = 0usize; // index into timestamps: first >= t
    let mut right = 0usize; // index into timestamps: first >= t + window_size

    for t in 0..n_windows as i64 {
        // Advance left pointer: skip timestamps < t
        while left < timestamps.len() && timestamps[left] < t {
            left += 1;
        }
        // Advance right pointer: skip timestamps < t + window_size
        let upper = t + window_size;
        while right < timestamps.len() && timestamps[right] < upper {
            right += 1;
        }
        series.push((right - left) as i64);
    }

    series
}

// ---------------------------------------------------------------------------
// Normal CDF (Abramowitz & Stegun)
// ---------------------------------------------------------------------------

/// Standard normal CDF Phi(z) using Abramowitz & Stegun erf approximation
/// (7.1.26, max error < 1.5e-7).
fn normal_cdf(z: f64) -> f64 {
    // erf(x) approximation for x >= 0
    fn erf_approx(x: f64) -> f64 {
        let a1 = 0.254829592_f64;
        let a2 = -0.284496736_f64;
        let a3 = 1.421413741_f64;
        let a4 = -1.453152027_f64;
        let a5 = 1.061405429_f64;
        let p = 0.3275911_f64;

        let ax = x.abs();
        let t = 1.0 / (1.0 + p * ax);
        let poly = t * (a1 + t * (a2 + t * (a3 + t * (a4 + t * a5))));
        let val = 1.0 - poly * (-ax * ax).exp();
        if x >= 0.0 {
            val
        } else {
            -val
        }
    }

    0.5 * (1.0 + erf_approx(z / std::f64::consts::SQRT_2))
}

// ---------------------------------------------------------------------------
// Shared Helpers
// ---------------------------------------------------------------------------

/// Get pattern timestamps by intersecting item transaction lists.
fn get_pattern_timestamps(
    pattern: &[i64],
    item_transaction_map: &HashMap<i64, Vec<i64>>,
) -> Vec<i64> {
    if pattern.len() == 1 {
        item_transaction_map
            .get(&pattern[0])
            .cloned()
            .unwrap_or_default()
    } else {
        let lists: Vec<&Vec<i64>> = pattern
            .iter()
            .filter_map(|item| item_transaction_map.get(item))
            .collect();
        if lists.len() != pattern.len() {
            return Vec::new();
        }
        intersect_sorted_lists(&lists)
    }
}

/// Filter patterns by amplitude (min_support_range).
///
/// Returns true if pattern passes the amplitude filter.
fn passes_amplitude_filter(
    timestamps: &[i64],
    intervals: &[(i64, i64)],
    window_size: i64,
    n_transactions: i64,
    min_support_range: i64,
) -> bool {
    if min_support_range <= 0 {
        return true;
    }
    let max_pos = (n_transactions - window_size + 1).max(0);
    if max_pos == 0 {
        return false;
    }

    // max support at interval midpoints
    let max_sup = intervals
        .iter()
        .map(|&(s, e)| {
            let mid = (s + e) / 2;
            let left = lower_bound(timestamps, mid);
            let right = upper_bound(timestamps, mid + window_size - 1);
            (right - left) as i64
        })
        .max()
        .unwrap_or(0);

    // min support at candidate positions (endpoints, gaps between intervals)
    let mut candidate_positions = vec![0, (max_pos - 1).max(0)];
    let mut sorted_ivs: Vec<(i64, i64)> = intervals.to_vec();
    sorted_ivs.sort();
    for w in sorted_ivs.windows(2) {
        candidate_positions.push((w[0].1 + w[1].0) / 2);
    }
    let min_sup = candidate_positions
        .iter()
        .filter(|&&pos| pos >= 0 && pos < max_pos)
        .map(|&pos| {
            let left = lower_bound(timestamps, pos);
            let right = upper_bound(timestamps, pos + window_size - 1);
            (right - left) as i64
        })
        .min()
        .unwrap_or(max_sup);

    max_sup - min_sup >= min_support_range
}

/// Deduplicate baseline results by item overlap (Union-Find).
///
/// Same algorithm as `correlator::deduplicate_by_item_overlap` but for
/// `BaselineResult`. Per-event grouping, same-length Union-Find with
/// ceil(l/2) threshold, cross-length subset dedup. Keeps lowest p-value.
fn deduplicate_baseline_results(results: Vec<BaselineResult>) -> Vec<BaselineResult> {
    // Phase 1: Same-length dedup with majority sharing
    let mut by_event: HashMap<String, Vec<BaselineResult>> = HashMap::new();
    for r in results {
        by_event.entry(r.event_name.clone()).or_default().push(r);
    }

    let mut deduplicated = Vec::new();

    for (_event_name, event_results) in &by_event {
        let mut by_length: HashMap<usize, Vec<&BaselineResult>> = HashMap::new();
        for r in event_results {
            by_length.entry(r.pattern.len()).or_default().push(r);
        }

        for (&l, length_results) in &by_length {
            let n = length_results.len();
            if n <= 1 {
                for r in length_results.iter() {
                    deduplicated.push((*r).clone());
                }
                continue;
            }

            // Union-Find
            let mut parent: Vec<usize> = (0..n).collect();

            fn find(parent: &mut [usize], x: usize) -> usize {
                let mut x = x;
                while parent[x] != x {
                    parent[x] = parent[parent[x]];
                    x = parent[x];
                }
                x
            }

            fn union(parent: &mut [usize], a: usize, b: usize) {
                let ra = find(parent, a);
                let rb = find(parent, b);
                if ra != rb {
                    parent[ra] = rb;
                }
            }

            let threshold = (l + 1) / 2; // ceil(l/2)

            let sets: Vec<HashSet<i64>> = length_results
                .iter()
                .map(|r| r.pattern.iter().copied().collect())
                .collect();

            for i in 0..n {
                for j in (i + 1)..n {
                    let shared = sets[i].intersection(&sets[j]).count();
                    if shared >= threshold {
                        union(&mut parent, i, j);
                    }
                }
            }

            // Keep best (lowest p-value) per cluster
            let mut clusters: HashMap<usize, Vec<usize>> = HashMap::new();
            for i in 0..n {
                let root = find(&mut parent, i);
                clusters.entry(root).or_default().push(i);
            }

            for (_root, members) in &clusters {
                let best_idx = *members
                    .iter()
                    .min_by(|&&a, &&b| {
                        length_results[a]
                            .adjusted_p_value
                            .partial_cmp(&length_results[b].adjusted_p_value)
                            .unwrap_or(std::cmp::Ordering::Equal)
                    })
                    .unwrap();
                deduplicated.push(length_results[best_idx].clone());
            }
        }
    }

    // Phase 2: Cross-length subset dedup
    let mut by_event2: HashMap<String, Vec<BaselineResult>> = HashMap::new();
    for r in deduplicated {
        by_event2.entry(r.event_name.clone()).or_default().push(r);
    }

    let mut final_results = Vec::new();

    for (_event_name, event_results) in &by_event2 {
        let n = event_results.len();
        if n <= 1 {
            final_results.extend(event_results.iter().cloned());
            continue;
        }

        let mut parent: Vec<usize> = (0..n).collect();

        fn find2(parent: &mut [usize], x: usize) -> usize {
            let mut x = x;
            while parent[x] != x {
                parent[x] = parent[parent[x]];
                x = parent[x];
            }
            x
        }

        fn union2(parent: &mut [usize], a: usize, b: usize) {
            let ra = find2(parent, a);
            let rb = find2(parent, b);
            if ra != rb {
                parent[ra] = rb;
            }
        }

        let sets: Vec<HashSet<i64>> = event_results
            .iter()
            .map(|r| r.pattern.iter().copied().collect())
            .collect();

        for i in 0..n {
            for j in (i + 1)..n {
                if sets[i].is_subset(&sets[j]) || sets[j].is_subset(&sets[i]) {
                    union2(&mut parent, i, j);
                }
            }
        }

        let mut clusters: HashMap<usize, Vec<usize>> = HashMap::new();
        for i in 0..n {
            let root = find2(&mut parent, i);
            clusters.entry(root).or_default().push(i);
        }

        for (_root, members) in &clusters {
            let best_idx = *members
                .iter()
                .min_by(|&&a, &&b| {
                    event_results[a]
                        .adjusted_p_value
                        .partial_cmp(&event_results[b].adjusted_p_value)
                        .unwrap_or(std::cmp::Ordering::Equal)
                })
                .unwrap();
            final_results.push(event_results[best_idx].clone());
        }
    }

    final_results
}

/// Apply BH correction and alpha filtering to raw hypotheses, then optionally deduplicate.
fn apply_correction_and_filter(
    raw: Vec<RawHypothesis>,
    params: &BaselineParams,
) -> Vec<BaselineResult> {
    if raw.is_empty() {
        return Vec::new();
    }

    let m = raw.len();
    let mut indexed: Vec<(usize, f64)> = raw.iter().enumerate().map(|(i, r)| (i, r.p_value)).collect();
    let adjusted = bh_correction(&mut indexed, m);

    let mut results: Vec<BaselineResult> = Vec::new();
    for (idx, adj_p) in adjusted {
        if adj_p < params.alpha {
            let r = &raw[idx];
            results.push(BaselineResult {
                pattern: r.pattern.clone(),
                event_name: r.event_name.clone(),
                event_start: r.event_start,
                event_end: r.event_end,
                p_value: r.p_value,
                adjusted_p_value: adj_p,
            });
        }
    }

    if params.deduplicate && !results.is_empty() {
        results = deduplicate_baseline_results(results);
    }

    results
}

/// Raw hypothesis before BH correction.
struct RawHypothesis {
    pattern: Vec<i64>,
    event_name: String,
    event_start: i64,
    event_end: i64,
    p_value: f64,
}

// ---------------------------------------------------------------------------
// Method 1: Wilcoxon (Mann-Whitney U Test)
// ---------------------------------------------------------------------------

/// Run Mann-Whitney U (Wilcoxon rank-sum) test for each (pattern, event) pair.
///
/// Tests whether support during an event is significantly higher than outside.
/// One-sided test with continuity correction and tie correction.
pub fn run_wilcoxon(
    patterns: &PatternData,
    events: &[Event],
    params: &BaselineParams,
) -> Vec<BaselineResult> {
    let pattern_list: Vec<(&Vec<i64>, &Vec<(i64, i64)>)> = patterns.frequents.iter().collect();

    let raw: Vec<RawHypothesis> = pattern_list
        .par_iter()
        .flat_map(|(pattern, intervals)| {
            if pattern.len() < 2 || intervals.is_empty() {
                return Vec::new();
            }

            let timestamps = get_pattern_timestamps(pattern, &patterns.item_transaction_map);
            if !passes_amplitude_filter(
                &timestamps,
                intervals,
                params.window_size,
                patterns.n_transactions,
                params.min_support_range,
            ) {
                return Vec::new();
            }

            let series = compute_support_series(&timestamps, params.window_size, patterns.n_transactions);
            let mut hypotheses = Vec::new();

            for event in events {
                // Split into during (window overlaps event) and outside
                let mut during = Vec::new();
                let mut outside = Vec::new();

                for (t, &val) in series.iter().enumerate() {
                    let t = t as i64;
                    let w_end = t + params.window_size - 1;
                    if t <= event.end && w_end >= event.start {
                        during.push(val as f64);
                    } else {
                        outside.push(val as f64);
                    }
                }

                if during.len() < 5 || outside.len() < 5 {
                    continue;
                }

                if let Some(p) = mann_whitney_u_one_sided(&during, &outside) {
                    hypotheses.push(RawHypothesis {
                        pattern: pattern.to_vec(),
                        event_name: event.name.clone(),
                        event_start: event.start,
                        event_end: event.end,
                        p_value: p,
                    });
                }
            }

            hypotheses
        })
        .collect();

    apply_correction_and_filter(raw, params)
}

/// One-sided Mann-Whitney U test: H1: sample1 > sample2.
///
/// Returns p-value or None if variance is zero.
fn mann_whitney_u_one_sided(sample1: &[f64], sample2: &[f64]) -> Option<f64> {
    let n1 = sample1.len();
    let n2 = sample2.len();
    let n = n1 + n2;

    // Combine and rank
    let mut combined: Vec<(f64, usize)> = Vec::with_capacity(n);
    for &v in sample1 {
        combined.push((v, 0)); // group 0 = sample1
    }
    for &v in sample2 {
        combined.push((v, 1)); // group 1 = sample2
    }

    // Sort by value
    combined.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));

    // Assign ranks with tie averaging
    let mut ranks = vec![0.0_f64; n];
    let mut i = 0;
    while i < n {
        let mut j = i;
        while j < n && (combined[j].0 - combined[i].0).abs() < 1e-12 {
            j += 1;
        }
        // Tied group from i to j-1
        let avg_rank = (i + j + 1) as f64 / 2.0; // 1-based average
        for k in i..j {
            ranks[k] = avg_rank;
        }
        i = j;
    }

    // Sum ranks for sample1
    let r1: f64 = (0..n)
        .filter(|&k| combined[k].1 == 0)
        .map(|k| ranks[k])
        .sum();

    let u1 = r1 - (n1 as f64) * (n1 as f64 + 1.0) / 2.0;
    let mu = (n1 as f64) * (n2 as f64) / 2.0;

    // Tie correction factor T = sum(t^3 - t)
    let mut tie_correction = 0.0_f64;
    let mut i = 0;
    while i < n {
        let mut j = i;
        while j < n && (combined[j].0 - combined[i].0).abs() < 1e-12 {
            j += 1;
        }
        let t = (j - i) as f64;
        if t > 1.0 {
            tie_correction += t * t * t - t;
        }
        i = j;
    }

    let n_f = n as f64;
    let sigma_sq = (n1 as f64) * (n2 as f64) / 12.0
        * (n_f + 1.0 - tie_correction / (n_f * (n_f - 1.0)));

    if sigma_sq <= 0.0 {
        return None;
    }

    let sigma = sigma_sq.sqrt();
    let z = (u1 - mu - 0.5) / sigma; // continuity correction
    let p = 1.0 - normal_cdf(z);

    Some(p.clamp(0.0, 1.0))
}

// ---------------------------------------------------------------------------
// Method 2: CausalImpact
// ---------------------------------------------------------------------------

/// Run CausalImpact analysis for each (pattern, event) pair.
///
/// Fits OLS trend on pre-event period, forecasts during-event, and tests
/// cumulative deviation significance.
pub fn run_causalimpact(
    patterns: &PatternData,
    events: &[Event],
    params: &BaselineParams,
) -> Vec<BaselineResult> {
    let pattern_list: Vec<(&Vec<i64>, &Vec<(i64, i64)>)> = patterns.frequents.iter().collect();

    let raw: Vec<RawHypothesis> = pattern_list
        .par_iter()
        .flat_map(|(pattern, intervals)| {
            if pattern.len() < 2 || intervals.is_empty() {
                return Vec::new();
            }

            let timestamps = get_pattern_timestamps(pattern, &patterns.item_transaction_map);
            if !passes_amplitude_filter(
                &timestamps,
                intervals,
                params.window_size,
                patterns.n_transactions,
                params.min_support_range,
            ) {
                return Vec::new();
            }

            let series = compute_support_series(&timestamps, params.window_size, patterns.n_transactions);
            let mut hypotheses = Vec::new();

            for event in events {
                // Pre-event: windows entirely before event
                let mut pre_t = Vec::new();
                let mut pre_y = Vec::new();
                // During: windows overlapping event
                let mut during_y = Vec::new();
                let mut during_indices = Vec::new();

                for (t, &val) in series.iter().enumerate() {
                    let t_i64 = t as i64;
                    let w_end = t_i64 + params.window_size - 1;
                    if w_end < event.start {
                        pre_t.push(t as f64);
                        pre_y.push(val as f64);
                    } else if t_i64 <= event.end && w_end >= event.start {
                        during_y.push(val as f64);
                        during_indices.push(t as f64);
                    }
                }

                let n_pre = pre_y.len();
                let n_during = during_y.len();

                if n_during < 5 || n_pre < 10 {
                    continue;
                }

                // OLS: y = a + b*t
                let t_mean: f64 = pre_t.iter().sum::<f64>() / n_pre as f64;
                let y_mean: f64 = pre_y.iter().sum::<f64>() / n_pre as f64;

                let mut ss_tt = 0.0_f64;
                let mut ss_ty = 0.0_f64;
                for i in 0..n_pre {
                    let dt = pre_t[i] - t_mean;
                    ss_tt += dt * dt;
                    ss_ty += dt * (pre_y[i] - y_mean);
                }

                let b = if ss_tt.abs() > 1e-12 { ss_ty / ss_tt } else { 0.0 };
                let a = y_mean - b * t_mean;

                // Residual standard error
                let mut ss_res = 0.0_f64;
                for i in 0..n_pre {
                    let pred = a + b * pre_t[i];
                    let res = pre_y[i] - pred;
                    ss_res += res * res;
                }
                let sigma_res = (ss_res / (n_pre as f64 - 2.0).max(1.0)).sqrt();

                // Cumulative impact
                let mut ci = 0.0_f64;
                for i in 0..n_during {
                    let predicted = a + b * during_indices[i];
                    ci += during_y[i] - predicted;
                }

                // Standard error of cumulative impact
                let se = sigma_res * ((n_during as f64) * (1.0 + n_during as f64 / n_pre as f64)).sqrt();

                if se.abs() < 1e-12 {
                    continue;
                }

                let z = ci / se;
                let p = 1.0 - normal_cdf(z);

                hypotheses.push(RawHypothesis {
                    pattern: pattern.to_vec(),
                    event_name: event.name.clone(),
                    event_start: event.start,
                    event_end: event.end,
                    p_value: p.clamp(0.0, 1.0),
                });
            }

            hypotheses
        })
        .collect();

    apply_correction_and_filter(raw, params)
}

// ---------------------------------------------------------------------------
// Method 3: ITS (Interrupted Time Series)
// ---------------------------------------------------------------------------

/// Run Interrupted Time Series regression for each (pattern, event) pair.
///
/// Design matrix: X = [1, t, D(t), (t - t_s) * D(t)]
/// Tests significance of the level-shift coefficient beta2.
pub fn run_its(
    patterns: &PatternData,
    events: &[Event],
    params: &BaselineParams,
) -> Vec<BaselineResult> {
    let pattern_list: Vec<(&Vec<i64>, &Vec<(i64, i64)>)> = patterns.frequents.iter().collect();

    let raw: Vec<RawHypothesis> = pattern_list
        .par_iter()
        .flat_map(|(pattern, intervals)| {
            if pattern.len() < 2 || intervals.is_empty() {
                return Vec::new();
            }

            let timestamps = get_pattern_timestamps(pattern, &patterns.item_transaction_map);
            if !passes_amplitude_filter(
                &timestamps,
                intervals,
                params.window_size,
                patterns.n_transactions,
                params.min_support_range,
            ) {
                return Vec::new();
            }

            let series = compute_support_series(&timestamps, params.window_size, patterns.n_transactions);
            let mut hypotheses = Vec::new();

            for event in events {
                let n = series.len();

                // Count during/outside
                let mut n_during = 0usize;
                let mut n_outside = 0usize;
                for t in 0..n {
                    let t_i64 = t as i64;
                    let w_end = t_i64 + params.window_size - 1;
                    if t_i64 <= event.end && w_end >= event.start {
                        n_during += 1;
                    } else {
                        n_outside += 1;
                    }
                }

                if n_during < 10 || n_outside < 10 {
                    continue;
                }

                // Build design matrix and y vector
                let t_s = event.start as f64;
                let mut x_flat = Vec::with_capacity(n * 4);
                let mut y_vec = Vec::with_capacity(n);

                for t in 0..n {
                    let t_f = t as f64;
                    let t_i64 = t as i64;
                    let w_end = t_i64 + params.window_size - 1;
                    let d = if t_i64 <= event.end && w_end >= event.start {
                        1.0
                    } else {
                        0.0
                    };
                    x_flat.push(1.0);
                    x_flat.push(t_f);
                    x_flat.push(d);
                    x_flat.push((t_f - t_s) * d);
                    y_vec.push(series[t] as f64);
                }

                if let Some((beta, se)) = solve_ols_4x4(&x_flat, &y_vec, n) {
                    let se_beta2 = se[2];
                    if se_beta2.abs() < 1e-12 {
                        continue;
                    }
                    let t_stat = beta[2] / se_beta2;
                    let p = 1.0 - normal_cdf(t_stat);

                    hypotheses.push(RawHypothesis {
                        pattern: pattern.to_vec(),
                        event_name: event.name.clone(),
                        event_start: event.start,
                        event_end: event.end,
                        p_value: p.clamp(0.0, 1.0),
                    });
                }
            }

            hypotheses
        })
        .collect();

    apply_correction_and_filter(raw, params)
}

/// Solve OLS with 4 predictors: beta = (X'X)^{-1} X'y.
///
/// `x` is row-major flattened n x 4 matrix.
/// Returns (beta[4], se[4]) or None if X'X is singular.
fn solve_ols_4x4(x: &[f64], y: &[f64], n: usize) -> Option<([f64; 4], [f64; 4])> {
    // Compute X'X (4x4 symmetric)
    let mut xtx = [0.0_f64; 16]; // row-major 4x4
    for i in 0..4 {
        for j in 0..4 {
            let mut sum = 0.0;
            for k in 0..n {
                sum += x[k * 4 + i] * x[k * 4 + j];
            }
            xtx[i * 4 + j] = sum;
        }
    }

    // Compute X'y (4x1)
    let mut xty = [0.0_f64; 4];
    for i in 0..4 {
        let mut sum = 0.0;
        for k in 0..n {
            sum += x[k * 4 + i] * y[k];
        }
        xty[i] = sum;
    }

    // Invert X'X using Gaussian elimination with partial pivoting
    let inv = invert_4x4(&xtx)?;

    // beta = inv * X'y
    let mut beta = [0.0_f64; 4];
    for i in 0..4 {
        for j in 0..4 {
            beta[i] += inv[i * 4 + j] * xty[j];
        }
    }

    // Residuals and sigma^2
    let mut ss_res = 0.0_f64;
    for k in 0..n {
        let mut pred = 0.0;
        for j in 0..4 {
            pred += x[k * 4 + j] * beta[j];
        }
        let res = y[k] - pred;
        ss_res += res * res;
    }

    let df = if n > 4 { n - 4 } else { 1 };
    let sigma_sq = ss_res / df as f64;

    // SE(beta) = sqrt(sigma^2 * diag((X'X)^{-1}))
    let mut se = [0.0_f64; 4];
    for i in 0..4 {
        let diag = inv[i * 4 + i];
        se[i] = (sigma_sq * diag.abs()).sqrt();
    }

    Some((beta, se))
}

/// Invert a 4x4 matrix using Gaussian elimination with partial pivoting.
///
/// Returns None if the matrix is singular.
fn invert_4x4(m: &[f64; 16]) -> Option<[f64; 16]> {
    // Augmented matrix [M | I]
    let mut aug = [[0.0_f64; 8]; 4];
    for i in 0..4 {
        for j in 0..4 {
            aug[i][j] = m[i * 4 + j];
            aug[i][j + 4] = if i == j { 1.0 } else { 0.0 };
        }
    }

    // Forward elimination with partial pivoting
    for col in 0..4 {
        // Find pivot
        let mut max_val = aug[col][col].abs();
        let mut max_row = col;
        for row in (col + 1)..4 {
            let val = aug[row][col].abs();
            if val > max_val {
                max_val = val;
                max_row = row;
            }
        }

        if max_val < 1e-12 {
            return None; // Singular
        }

        // Swap rows
        if max_row != col {
            aug.swap(col, max_row);
        }

        // Eliminate below
        let pivot = aug[col][col];
        for row in (col + 1)..4 {
            let factor = aug[row][col] / pivot;
            for j in col..8 {
                aug[row][j] -= factor * aug[col][j];
            }
        }
    }

    // Back substitution
    for col in (0..4).rev() {
        let pivot = aug[col][col];
        if pivot.abs() < 1e-12 {
            return None;
        }
        for j in 0..8 {
            aug[col][j] /= pivot;
        }
        for row in 0..col {
            let factor = aug[row][col];
            for j in 0..8 {
                aug[row][j] -= factor * aug[col][j];
            }
        }
    }

    // Extract inverse
    let mut inv = [0.0_f64; 16];
    for i in 0..4 {
        for j in 0..4 {
            inv[i * 4 + j] = aug[i][j + 4];
        }
    }

    Some(inv)
}

// ---------------------------------------------------------------------------
// Method 4: EventStudy
// ---------------------------------------------------------------------------

/// Run Event Study analysis for each (pattern, event) pair.
///
/// Computes Cumulative Abnormal Support (CAS) relative to a pre-event
/// estimation window and tests for significance.
pub fn run_event_study(
    patterns: &PatternData,
    events: &[Event],
    params: &BaselineParams,
) -> Vec<BaselineResult> {
    let pattern_list: Vec<(&Vec<i64>, &Vec<(i64, i64)>)> = patterns.frequents.iter().collect();

    let raw: Vec<RawHypothesis> = pattern_list
        .par_iter()
        .flat_map(|(pattern, intervals)| {
            if pattern.len() < 2 || intervals.is_empty() {
                return Vec::new();
            }

            let timestamps = get_pattern_timestamps(pattern, &patterns.item_transaction_map);
            if !passes_amplitude_filter(
                &timestamps,
                intervals,
                params.window_size,
                patterns.n_transactions,
                params.min_support_range,
            ) {
                return Vec::new();
            }

            let series = compute_support_series(&timestamps, params.window_size, patterns.n_transactions);
            let mut hypotheses = Vec::new();

            for event in events {
                // Estimation window: windows entirely before event
                let mut estimation = Vec::new();
                // Event windows: overlap with event
                let mut event_windows = Vec::new();

                for (t, &val) in series.iter().enumerate() {
                    let t_i64 = t as i64;
                    let w_end = t_i64 + params.window_size - 1;
                    if w_end < event.start {
                        estimation.push(val as f64);
                    } else if t_i64 <= event.end && w_end >= event.start {
                        event_windows.push(val as f64);
                    }
                }

                let n_estimation = estimation.len();
                let n_event_windows = event_windows.len();

                if n_estimation < 10 || n_event_windows < 5 {
                    continue;
                }

                let mu_est: f64 = estimation.iter().sum::<f64>() / n_estimation as f64;
                let sigma_est = {
                    let var: f64 = estimation.iter().map(|&v| (v - mu_est).powi(2)).sum::<f64>()
                        / n_estimation as f64; // ddof=0
                    var.sqrt()
                };

                if sigma_est.abs() < 1e-12 {
                    continue;
                }

                let cas: f64 = event_windows.iter().map(|&v| v - mu_est).sum();
                let z = cas / (sigma_est * (n_event_windows as f64).sqrt());
                let p = 1.0 - normal_cdf(z);

                hypotheses.push(RawHypothesis {
                    pattern: pattern.to_vec(),
                    event_name: event.name.clone(),
                    event_start: event.start,
                    event_end: event.end,
                    p_value: p.clamp(0.0, 1.0),
                });
            }

            hypotheses
        })
        .collect();

    apply_correction_and_filter(raw, params)
}

// ---------------------------------------------------------------------------
// Method 5: ECA (Event Coincidence Analysis)
// ---------------------------------------------------------------------------

/// Run Event Coincidence Analysis for each (pattern, event) pair.
///
/// Tests whether change points from dense intervals coincide with events
/// more than expected under a uniform null.
pub fn run_eca(
    patterns: &PatternData,
    events: &[Event],
    params: &BaselineParams,
) -> Vec<BaselineResult> {
    let pattern_list: Vec<(&Vec<i64>, &Vec<(i64, i64)>)> = patterns.frequents.iter().collect();

    let raw: Vec<RawHypothesis> = pattern_list
        .par_iter()
        .flat_map(|(pattern, intervals)| {
            if pattern.len() < 2 || intervals.is_empty() {
                return Vec::new();
            }

            let timestamps = get_pattern_timestamps(pattern, &patterns.item_transaction_map);
            if !passes_amplitude_filter(
                &timestamps,
                intervals,
                params.window_size,
                patterns.n_transactions,
                params.min_support_range,
            ) {
                return Vec::new();
            }

            // Extract change points from dense intervals
            let mut change_points = Vec::new();
            let max_pos = (patterns.n_transactions - params.window_size + 1).max(0);
            for &(s, e) in intervals.iter() {
                if s >= 0 && s < max_pos {
                    change_points.push(s); // up at s
                }
                let down = e + 1;
                if down > 0 && down < max_pos {
                    change_points.push(down); // down at e+1
                }
            }

            if change_points.len() < 3 {
                return Vec::new();
            }

            let n_cp = change_points.len() as f64;
            let n_trans = patterns.n_transactions as f64;
            let delta = params.window_size as f64;

            let mut hypotheses = Vec::new();

            for event in events {
                let event_duration = (event.end - event.start + 1) as f64;
                let lo = event.start as f64 - delta;
                let hi = event.end as f64 + delta;

                // Count change points within coincidence window
                let k = change_points
                    .iter()
                    .filter(|&&cp| (cp as f64) >= lo && (cp as f64) <= hi)
                    .count() as f64;

                // Null: uniform distribution
                let lambda = ((event_duration + 2.0 * delta) / n_trans).min(1.0);
                let mu = n_cp * lambda;
                let var = n_cp * lambda * (1.0 - lambda);

                if var <= 0.0 {
                    continue;
                }

                let z = (k - mu) / var.sqrt();
                let p = 1.0 - normal_cdf(z);

                hypotheses.push(RawHypothesis {
                    pattern: pattern.to_vec(),
                    event_name: event.name.clone(),
                    event_start: event.start,
                    event_end: event.end,
                    p_value: p.clamp(0.0, 1.0),
                });
            }

            hypotheses
        })
        .collect();

    apply_correction_and_filter(raw, params)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compute_support_series() {
        // Timestamps at 0,1,2,5,6,7,10 with window_size=3, n_transactions=12
        // n_windows = 12 - 3 + 1 = 10 (t = 0..9)
        let timestamps = vec![0, 1, 2, 5, 6, 7, 10];
        let series = compute_support_series(&timestamps, 3, 12);
        assert_eq!(series.len(), 10);

        // Verify against binary search approach
        for (t, &val) in series.iter().enumerate() {
            let t = t as i64;
            let left = lower_bound(&timestamps, t);
            let right = upper_bound(&timestamps, t + 3 - 1);
            let expected = (right - left) as i64;
            assert_eq!(val, expected, "mismatch at t={t}");
        }
    }

    #[test]
    fn test_compute_support_series_empty() {
        let timestamps: Vec<i64> = vec![];
        let series = compute_support_series(&timestamps, 3, 10);
        assert_eq!(series.len(), 8);
        assert!(series.iter().all(|&v| v == 0));
    }

    #[test]
    fn test_normal_cdf() {
        // Known values for standard normal CDF
        let eps = 1.5e-7;
        assert!((normal_cdf(0.0) - 0.5).abs() < eps);
        assert!((normal_cdf(1.0) - 0.8413447).abs() < 1e-5);
        assert!((normal_cdf(-1.0) - 0.1586553).abs() < 1e-5);
        assert!((normal_cdf(2.0) - 0.9772499).abs() < 1e-5);
        assert!((normal_cdf(-2.0) - 0.0227501).abs() < 1e-5);
        assert!((normal_cdf(3.0) - 0.9986501).abs() < 1e-4);
        // Extreme values
        assert!(normal_cdf(10.0) > 0.999999);
        assert!(normal_cdf(-10.0) < 0.000001);
    }

    #[test]
    fn test_mann_whitney_u() {
        // Simple example: group1 = [5,6,7,8,9], group2 = [1,2,3,4,5]
        // group1 should be significantly larger
        let sample1 = vec![5.0, 6.0, 7.0, 8.0, 9.0];
        let sample2 = vec![1.0, 2.0, 3.0, 4.0, 5.0];

        let p = mann_whitney_u_one_sided(&sample1, &sample2).unwrap();
        // p should be small (significant difference)
        assert!(p < 0.05, "Expected p < 0.05, got {p}");

        // No difference: identical groups
        let same1 = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let same2 = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let p_same = mann_whitney_u_one_sided(&same1, &same2).unwrap();
        assert!(p_same > 0.3, "Expected p > 0.3, got {p_same}");
    }

    #[test]
    fn test_mann_whitney_u_reversed() {
        // group1 < group2 → one-sided p should be large
        let sample1 = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let sample2 = vec![6.0, 7.0, 8.0, 9.0, 10.0];
        let p = mann_whitney_u_one_sided(&sample1, &sample2).unwrap();
        assert!(p > 0.9, "Expected p > 0.9, got {p}");
    }

    #[test]
    fn test_bh_correction_integration() {
        // Verify that BH correction from correlator works with baseline types
        let mut pvals: Vec<(usize, f64)> = vec![
            (0, 0.01),
            (1, 0.04),
            (2, 0.03),
            (3, 0.20),
            (4, 0.50),
        ];
        let adjusted = bh_correction(&mut pvals, 5);
        assert_eq!(adjusted.len(), 5);

        // Adjusted p-values should be monotonically non-decreasing (after sort)
        for w in adjusted.windows(2) {
            assert!(w[0].1 <= w[1].1 + 1e-10);
        }
    }

    #[test]
    fn test_invert_4x4_identity() {
        let identity = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ];
        let inv = invert_4x4(&identity).unwrap();
        for i in 0..4 {
            for j in 0..4 {
                let expected = if i == j { 1.0 } else { 0.0 };
                assert!(
                    (inv[i * 4 + j] - expected).abs() < 1e-10,
                    "inv[{i}][{j}] = {}, expected {expected}",
                    inv[i * 4 + j]
                );
            }
        }
    }

    #[test]
    fn test_invert_4x4_singular() {
        // All zeros → singular
        let zero = [0.0_f64; 16];
        assert!(invert_4x4(&zero).is_none());
    }

    #[test]
    fn test_solve_ols_4x4_simple() {
        // y = 2 + 3*t + 5*D(t), intervention at t >= 10
        // X = [1, t, D(t), (t-10)*D(t)]
        let n = 20;
        let t_s = 10.0;
        let mut x = Vec::new();
        let mut y = Vec::new();
        for t in 0..n {
            let t_f = t as f64;
            let d = if t >= 10 { 1.0 } else { 0.0 };
            x.push(1.0);
            x.push(t_f);
            x.push(d);
            x.push((t_f - t_s) * d);
            y.push(2.0 + 3.0 * t_f + 5.0 * d);
        }

        let result = solve_ols_4x4(&x, &y, n);
        assert!(result.is_some());
        let (beta, _se) = result.unwrap();
        assert!((beta[0] - 2.0).abs() < 1e-6, "intercept: {}", beta[0]);
        assert!((beta[1] - 3.0).abs() < 1e-6, "slope: {}", beta[1]);
        assert!((beta[2] - 5.0).abs() < 1e-6, "level shift: {}", beta[2]);
    }

    #[test]
    fn test_deduplicate_baseline_results() {
        let results = vec![
            BaselineResult {
                pattern: vec![1, 2],
                event_name: "E".to_string(),
                event_start: 10,
                event_end: 15,
                p_value: 0.01,
                adjusted_p_value: 0.02,
            },
            BaselineResult {
                pattern: vec![1, 3],
                event_name: "E".to_string(),
                event_start: 10,
                event_end: 15,
                p_value: 0.005,
                adjusted_p_value: 0.01,
            },
        ];

        let deduped = deduplicate_baseline_results(results);
        // {1,2} & {1,3}: shared={1}, threshold=ceil(2/2)=1 → merge
        // Keep lowest p-value: {1,3} with adj_p=0.01
        assert_eq!(deduped.len(), 1);
        assert_eq!(deduped[0].pattern, vec![1, 3]);
    }

    #[test]
    fn test_run_wilcoxon_basic() {
        // Synthetic: item pair with strong support during event
        let mut item_transaction_map: HashMap<i64, Vec<i64>> = HashMap::new();
        // Items 1,2 appear densely in [20..40] and sparsely elsewhere
        let mut ts: Vec<i64> = (0..50).filter(|t| *t >= 20 && *t < 40).collect();
        // Add a few outside
        ts.extend_from_slice(&[0, 5, 10, 45, 48]);
        ts.sort();
        item_transaction_map.insert(1, ts.clone());
        item_transaction_map.insert(2, ts);

        let mut frequents: HashMap<Vec<i64>, Vec<(i64, i64)>> = HashMap::new();
        frequents.insert(vec![1, 2], vec![(18, 35)]);

        let patterns = PatternData {
            frequents,
            item_transaction_map,
            n_transactions: 50,
        };

        let events = vec![Event {
            event_id: "E1".to_string(),
            name: "TestEvent".to_string(),
            start: 20,
            end: 35,
        }];

        let params = BaselineParams {
            window_size: 5,
            alpha: 1.0, // accept all for testing
            min_support_range: 0,
            deduplicate: false,
        };

        let results = run_wilcoxon(&patterns, &events, &params);
        // Should produce at least one hypothesis
        assert!(!results.is_empty());
        assert_eq!(results[0].event_name, "TestEvent");
    }
}
