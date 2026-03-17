//! 4段パイプライン: MI Pre-filter → Sweep Line → Permutation Test
//!
//! Stage 0: Brute-Force Baseline（correlator::match_all）
//! Stage 1: 相互情報量による事前フィルタリング
//! Stage 2: 走査線アルゴリズムによる高速マッチング
//! Stage 3: 置換検定による有意性検定

use std::collections::HashMap;

use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};

use crate::correlator::{match_all, Event, Frequents, RelationMatch};

// ---------------------------------------------------------------------------
// Stage 1: Mutual Information Pre-filter
// ---------------------------------------------------------------------------

/// 区間リストを [t_min, t_max] 上の二値ベクタに変換する。
fn to_binary_series(intervals: &[(i64, i64)], t_min: i64, t_max: i64) -> Vec<u8> {
    let length = (t_max - t_min + 1) as usize;
    let mut series = vec![0u8; length];
    for &(s, e) in intervals {
        let lo = (s.max(t_min) - t_min) as usize;
        let hi = (e.min(t_max) - t_min) as usize;
        for t in lo..=hi {
            series[t] = 1;
        }
    }
    series
}

/// 二値時系列 x, y の相互情報量 I(X;Y) を計算する。
pub fn compute_mi(x: &[u8], y: &[u8]) -> f64 {
    let n = x.len();
    if n == 0 {
        return 0.0;
    }
    let mut counts = [[0u64; 2]; 2];
    for i in 0..n {
        counts[x[i] as usize][y[i] as usize] += 1;
    }
    let nf = n as f64;
    let mut mi = 0.0;
    for a in 0..2 {
        for b in 0..2 {
            let p_xy = counts[a][b] as f64 / nf;
            if p_xy == 0.0 {
                continue;
            }
            let p_x = (counts[a][0] + counts[a][1]) as f64 / nf;
            let p_y = (counts[0][b] + counts[1][b]) as f64 / nf;
            if p_x == 0.0 || p_y == 0.0 {
                continue;
            }
            mi += p_xy * (p_xy / (p_x * p_y)).ln();
        }
    }
    mi
}

/// 全 (パターン, イベント) ペアの MI スコアを計算する。
pub fn compute_mi_scores(
    frequents: &Frequents,
    events: &[Event],
) -> HashMap<(Vec<i64>, String), f64> {
    if frequents.is_empty() || events.is_empty() {
        return HashMap::new();
    }

    // 時間軸の範囲を決定
    let mut t_min = i64::MAX;
    let mut t_max = i64::MIN;
    for intervals in frequents.values() {
        for &(s, e) in intervals {
            t_min = t_min.min(s);
            t_max = t_max.max(e);
        }
    }
    for ev in events {
        t_min = t_min.min(ev.start);
        t_max = t_max.max(ev.end);
    }

    // パターンごとの二値時系列を事前計算
    let pattern_series: HashMap<&Vec<i64>, Vec<u8>> = frequents
        .iter()
        .map(|(itemset, intervals)| (itemset, to_binary_series(intervals, t_min, t_max)))
        .collect();

    // イベントごとの二値時系列を事前計算
    let event_series: HashMap<&str, Vec<u8>> = events
        .iter()
        .map(|ev| {
            (
                ev.event_id.as_str(),
                to_binary_series(&[(ev.start, ev.end)], t_min, t_max),
            )
        })
        .collect();

    let mut scores = HashMap::new();
    for (itemset, x) in &pattern_series {
        for ev in events {
            let y = &event_series[ev.event_id.as_str()];
            let mi = compute_mi(x, y);
            scores.insert(((*itemset).clone(), ev.event_id.clone()), mi);
        }
    }
    scores
}

/// Stage 1: MI スコアを計算し、閾値以上のペアのみ返す。
pub fn mi_prefilter(
    frequents: &Frequents,
    events: &[Event],
    mi_threshold: f64,
) -> (HashMap<(Vec<i64>, String), f64>, Vec<(Vec<i64>, String)>) {
    let scores = compute_mi_scores(frequents, events);
    let passed: Vec<(Vec<i64>, String)> = scores
        .iter()
        .filter(|(_, &mi)| mi > mi_threshold)
        .map(|(k, _)| k.clone())
        .collect();
    (scores, passed)
}

// ---------------------------------------------------------------------------
// Stage 2: Sweep Line Matching
// ---------------------------------------------------------------------------

/// 走査線アルゴリズムで Allen 関係を判定する。
///
/// candidate_pairs が Some の場合、そのペアのみ判定する。
/// None の場合は全ペアを判定する（Stage 0 相当）。
pub fn match_sweep_line(
    frequents: &Frequents,
    events: &[Event],
    epsilon: i64,
    d_0: i64,
    candidate_pairs: Option<&[(Vec<i64>, String)]>,
) -> Vec<RelationMatch> {
    // candidate_pairs からパターンごとのイベントIDセットを構築
    let pair_set: Option<HashMap<&Vec<i64>, Vec<&str>>> = candidate_pairs.map(|pairs| {
        let mut m: HashMap<&Vec<i64>, Vec<&str>> = HashMap::new();
        for (itemset, eid) in pairs {
            // itemset を frequents のキーにマッチさせる
            if let Some(key) = frequents.keys().find(|k| *k == itemset) {
                m.entry(key).or_default().push(eid.as_str());
            }
        }
        m
    });

    let event_map: HashMap<&str, &Event> =
        events.iter().map(|ev| (ev.event_id.as_str(), ev)).collect();

    let mut results = Vec::new();

    for (itemset, intervals) in frequents {
        let target_events: Vec<&Event> = match &pair_set {
            Some(ps) => match ps.get(itemset) {
                Some(eids) => eids
                    .iter()
                    .filter_map(|eid| event_map.get(eid).copied())
                    .collect(),
                None => continue,
            },
            None => events.iter().collect(),
        };

        if target_events.is_empty() || intervals.is_empty() {
            continue;
        }

        // 密集区間をソート
        let mut sorted_intervals: Vec<(i64, i64)> = intervals.clone();
        sorted_intervals.sort_by_key(|&(s, _)| s);

        // イベントをソート
        let mut sorted_events: Vec<&&Event> = target_events.iter().collect();
        sorted_events.sort_by_key(|ev| ev.start);

        for &(ts_i, te_i) in &sorted_intervals {
            // 走査: 近傍イベントを探索
            let mut scan_idx = 0;
            for (idx, ev) in sorted_events.iter().enumerate() {
                if ev.end >= ts_i - epsilon {
                    scan_idx = idx;
                    break;
                }
            }

            for j in scan_idx..sorted_events.len() {
                let ev = sorted_events[j];
                let ts_j = ev.start;
                let te_j = ev.end;

                // 離れすぎたら終了
                if ts_j > te_i + epsilon + (te_i - ts_i) {
                    break;
                }

                // 6 関係を判定
                if satisfies_follows(te_i, ts_j, epsilon) {
                    results.push(make_match(itemset, ts_i, te_i, ev, "DenseFollowsEvent", None));
                }
                if satisfies_follows(te_j, ts_i, epsilon) {
                    results.push(make_match(itemset, ts_i, te_i, ev, "EventFollowsDense", None));
                }
                if satisfies_contains(ts_i, te_i, ts_j, te_j, epsilon) {
                    results.push(make_match(
                        itemset,
                        ts_i,
                        te_i,
                        ev,
                        "DenseContainsEvent",
                        None,
                    ));
                }
                if satisfies_contains(ts_j, te_j, ts_i, te_i, epsilon) {
                    results.push(make_match(
                        itemset,
                        ts_i,
                        te_i,
                        ev,
                        "EventContainsDense",
                        None,
                    ));
                }
                if let Some(ovl) = satisfies_overlaps_fn(ts_i, te_i, ts_j, te_j, epsilon, d_0) {
                    results.push(make_match(
                        itemset,
                        ts_i,
                        te_i,
                        ev,
                        "DenseOverlapsEvent",
                        Some(ovl),
                    ));
                }
                if let Some(ovl) = satisfies_overlaps_fn(ts_j, te_j, ts_i, te_i, epsilon, d_0) {
                    results.push(make_match(
                        itemset,
                        ts_i,
                        te_i,
                        ev,
                        "EventOverlapsDense",
                        Some(ovl),
                    ));
                }
            }
        }
    }

    results.sort_by(|a, b| {
        b.itemset
            .len()
            .cmp(&a.itemset.len())
            .then_with(|| a.dense_start.cmp(&b.dense_start))
            .then_with(|| a.event_id.cmp(&b.event_id))
            .then_with(|| a.relation_type.cmp(&b.relation_type))
    });
    results
}

#[inline]
fn satisfies_follows(te_i: i64, ts_j: i64, epsilon: i64) -> bool {
    te_i - epsilon <= ts_j && ts_j <= te_i + epsilon
}

#[inline]
fn satisfies_contains(ts_i: i64, te_i: i64, ts_j: i64, te_j: i64, epsilon: i64) -> bool {
    ts_i <= ts_j && te_i + epsilon >= te_j
}

#[inline]
fn satisfies_overlaps_fn(
    ts_i: i64,
    te_i: i64,
    ts_j: i64,
    te_j: i64,
    epsilon: i64,
    d_0: i64,
) -> Option<i64> {
    if ts_i >= ts_j {
        return None;
    }
    let overlap = te_i - ts_j;
    if overlap < d_0 - epsilon {
        return None;
    }
    if te_i >= te_j + epsilon {
        return None;
    }
    Some(overlap)
}

fn make_match(
    itemset: &[i64],
    ts_i: i64,
    te_i: i64,
    event: &Event,
    relation_type: &str,
    overlap_length: Option<i64>,
) -> RelationMatch {
    RelationMatch {
        itemset: itemset.to_vec(),
        dense_start: ts_i,
        dense_end: te_i,
        event_id: event.event_id.clone(),
        event_name: event.name.clone(),
        relation_type: relation_type.to_string(),
        overlap_length,
    }
}

// ---------------------------------------------------------------------------
// Stage 3: Permutation-based Significance Testing
// ---------------------------------------------------------------------------

/// Stage 3 出力: 有意な時間的関係。
#[derive(Debug, Clone)]
pub struct SignificantRelation {
    pub itemset: Vec<i64>,
    pub event_id: String,
    pub relation_type: String,
    pub observed_count: usize,
    pub p_value: f64,
    pub adjusted_p_value: f64,
    pub effect_size: f64,
    pub mi_score: Option<f64>,
}

/// イベント群を循環シフトする。
fn cyclic_shift_events(events: &[Event], offset: i64, t_min: i64, t_max: i64) -> Vec<Event> {
    let span = t_max - t_min + 1;
    events
        .iter()
        .map(|ev| {
            let new_start = t_min + (ev.start - t_min + offset).rem_euclid(span);
            let mut new_end = t_min + (ev.end - t_min + offset).rem_euclid(span);
            if new_end < new_start {
                new_end = new_start + (ev.end - ev.start);
                if new_end > t_max {
                    new_end = t_max;
                }
            }
            Event {
                event_id: ev.event_id.clone(),
                name: ev.name.clone(),
                start: new_start,
                end: new_end,
            }
        })
        .collect()
}

type RelationKey = (Vec<i64>, String, String);

/// マッチ結果を (itemset, event_id, relation_type) ごとに集計する。
fn count_relations(results: &[RelationMatch]) -> HashMap<RelationKey, usize> {
    let mut counts: HashMap<RelationKey, usize> = HashMap::new();
    for m in results {
        let key = (
            m.itemset.clone(),
            m.event_id.clone(),
            m.relation_type.clone(),
        );
        *counts.entry(key).or_insert(0) += 1;
    }
    counts
}

/// パイプライン設定。
#[derive(Debug, Clone)]
pub struct PipelineConfig {
    pub epsilon: i64,
    pub d_0: i64,
    pub stage1_enabled: bool,
    pub mi_threshold: f64,
    pub stage2_enabled: bool,
    pub stage3_enabled: bool,
    pub n_permutations: usize,
    pub alpha: f64,
    pub correction_method: String,
    pub seed: Option<u64>,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self {
            epsilon: 0,
            d_0: 0,
            stage1_enabled: true,
            mi_threshold: 0.01,
            stage2_enabled: true,
            stage3_enabled: true,
            n_permutations: 1000,
            alpha: 0.05,
            correction_method: "westfall_young".to_string(),
            seed: None,
        }
    }
}

/// パイプラインの全段階の結果。
#[derive(Debug)]
pub struct PipelineResult {
    pub brute_force_results: Vec<RelationMatch>,
    pub mi_scores: Option<HashMap<(Vec<i64>, String), f64>>,
    pub mi_passed_pairs: Option<Vec<(Vec<i64>, String)>>,
    pub sweep_results: Option<Vec<RelationMatch>>,
    pub significant_relations: Option<Vec<SignificantRelation>>,
}

/// 置換検定を実行する。
pub fn permutation_test(
    frequents: &Frequents,
    events: &[Event],
    epsilon: i64,
    d_0: i64,
    n_permutations: usize,
    alpha: f64,
    correction_method: &str,
    seed: Option<u64>,
    mi_scores: Option<&HashMap<(Vec<i64>, String), f64>>,
) -> Vec<SignificantRelation> {
    let mut rng: StdRng = match seed {
        Some(s) => StdRng::seed_from_u64(s),
        None => StdRng::from_entropy(),
    };

    // 時間軸の範囲
    let mut t_min = i64::MAX;
    let mut t_max = i64::MIN;
    for intervals in frequents.values() {
        for &(s, e) in intervals {
            t_min = t_min.min(s);
            t_max = t_max.max(e);
        }
    }
    for ev in events {
        t_min = t_min.min(ev.start);
        t_max = t_max.max(ev.end);
    }
    if t_min > t_max {
        return Vec::new();
    }
    let span = t_max - t_min + 1;

    // 観測統計量
    let observed_results = match_all(frequents, events, epsilon, d_0);
    let observed_counts = count_relations(&observed_results);
    if observed_counts.is_empty() {
        return Vec::new();
    }

    // 置換テスト
    let mut perm_exceed: HashMap<RelationKey, usize> = observed_counts
        .keys()
        .map(|k| (k.clone(), 0))
        .collect();
    let mut max_stats_per_perm: Vec<f64> = Vec::with_capacity(n_permutations);

    for _ in 0..n_permutations {
        let offset = rng.gen_range(1..span);
        let shifted = cyclic_shift_events(events, offset, t_min, t_max);
        let perm_results = match_all(frequents, &shifted, epsilon, d_0);
        let perm_counts = count_relations(&perm_results);

        let mut max_stat: f64 = 0.0;
        for (key, &c_obs) in &observed_counts {
            let c_perm = perm_counts.get(key).copied().unwrap_or(0);
            if c_perm >= c_obs {
                *perm_exceed.get_mut(key).unwrap() += 1;
            }
            if (c_perm as f64) > max_stat {
                max_stat = c_perm as f64;
            }
        }
        max_stats_per_perm.push(max_stat);
    }

    // p 値計算
    let mut raw_p: HashMap<RelationKey, f64> = HashMap::new();
    for (key, _) in &observed_counts {
        let exceed = perm_exceed[key];
        raw_p.insert(key.clone(), (exceed as f64 + 1.0) / (n_permutations as f64 + 1.0));
    }

    // 多重検定補正
    let mut adjusted_p: HashMap<RelationKey, f64> = HashMap::new();
    if correction_method == "bonferroni" {
        let n_tests = observed_counts.len() as f64;
        for (key, &p) in &raw_p {
            adjusted_p.insert(key.clone(), (p * n_tests).min(1.0));
        }
    } else {
        // Westfall-Young stepdown
        for (key, _) in &raw_p {
            let c_obs = observed_counts[key];
            let exceed_count = max_stats_per_perm
                .iter()
                .filter(|&&ms| ms >= c_obs as f64)
                .count();
            adjusted_p.insert(
                key.clone(),
                (exceed_count as f64 + 1.0) / (n_permutations as f64 + 1.0),
            );
        }
    }

    // 有意な関係のみ抽出
    let mut significant: Vec<SignificantRelation> = Vec::new();
    for (key, &adj_p) in &adjusted_p {
        if adj_p >= alpha {
            continue;
        }
        let (ref itemset, ref event_id, ref relation_type) = *key;
        let c_obs = observed_counts[key];
        let p_raw = raw_p[key];
        let exceed = perm_exceed[key];

        let mean_perm = (n_permutations - exceed) as f64 * c_obs as f64
            / n_permutations.max(1) as f64;
        let effect = if mean_perm > 0.0 {
            c_obs as f64 / mean_perm
        } else if c_obs > 0 {
            c_obs as f64
        } else {
            0.0
        };

        let mi = mi_scores
            .and_then(|scores| scores.get(&(itemset.clone(), event_id.clone())).copied());

        significant.push(SignificantRelation {
            itemset: itemset.clone(),
            event_id: event_id.clone(),
            relation_type: relation_type.clone(),
            observed_count: c_obs,
            p_value: p_raw,
            adjusted_p_value: adj_p,
            effect_size: effect,
            mi_score: mi,
        });
    }

    significant.sort_by(|a, b| {
        a.adjusted_p_value
            .partial_cmp(&b.adjusted_p_value)
            .unwrap()
            .then_with(|| b.itemset.len().cmp(&a.itemset.len()))
    });
    significant
}

/// 4 段パイプラインを実行する。
pub fn run_pipeline(
    frequents: &Frequents,
    events: &[Event],
    config: &PipelineConfig,
) -> PipelineResult {
    // Stage 0: Brute-Force
    let brute_force = match_all(frequents, events, config.epsilon, config.d_0);

    let mut result = PipelineResult {
        brute_force_results: brute_force.clone(),
        mi_scores: None,
        mi_passed_pairs: None,
        sweep_results: None,
        significant_relations: None,
    };

    // Stage 1: MI Pre-filter
    let mut candidate_pairs: Option<Vec<(Vec<i64>, String)>> = None;
    if config.stage1_enabled {
        let (scores, passed) = mi_prefilter(frequents, events, config.mi_threshold);
        result.mi_scores = Some(scores);
        result.mi_passed_pairs = Some(passed.clone());
        candidate_pairs = Some(passed);
    }

    // Stage 2: Sweep Line Matching
    if config.stage2_enabled {
        let sweep = match_sweep_line(
            frequents,
            events,
            config.epsilon,
            config.d_0,
            candidate_pairs.as_deref(),
        );
        result.sweep_results = Some(sweep);
    } else if let Some(ref pairs) = candidate_pairs {
        let pair_set: std::collections::HashSet<(Vec<i64>, String)> =
            pairs.iter().cloned().collect();
        let filtered: Vec<RelationMatch> = brute_force
            .into_iter()
            .filter(|m| pair_set.contains(&(m.itemset.clone(), m.event_id.clone())))
            .collect();
        result.sweep_results = Some(filtered);
    } else {
        result.sweep_results = Some(result.brute_force_results.clone());
    }

    // Stage 3: Permutation Test
    if config.stage3_enabled {
        let mi_ref = result.mi_scores.as_ref();
        let sig = permutation_test(
            frequents,
            events,
            config.epsilon,
            config.d_0,
            config.n_permutations,
            config.alpha,
            &config.correction_method,
            config.seed,
            mi_ref,
        );
        result.significant_relations = Some(sig);
    }

    result
}

// ---------------------------------------------------------------------------
// テスト
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::{HashMap, HashSet};

    fn make_frequents(itemset: Vec<i64>, intervals: Vec<(i64, i64)>) -> Frequents {
        let mut m = HashMap::new();
        m.insert(itemset, intervals);
        m
    }

    fn make_event(id: &str, start: i64, end: i64) -> Event {
        Event {
            event_id: id.to_string(),
            name: id.to_string(),
            start,
            end,
        }
    }

    // -----------------------------------------------------------------------
    // Stage 1: MI
    // -----------------------------------------------------------------------

    #[test]
    fn test_to_binary_series() {
        let s = to_binary_series(&[(2, 5)], 0, 7);
        assert_eq!(s, vec![0, 0, 1, 1, 1, 1, 0, 0]);
    }

    #[test]
    fn test_compute_mi_identical() {
        let x = vec![1u8, 1, 0, 0, 1, 1, 0, 0];
        let y = vec![1, 1, 0, 0, 1, 1, 0, 0];
        assert!(compute_mi(&x, &y) > 0.5);
    }

    #[test]
    fn test_compute_mi_independent() {
        let x = vec![1u8, 0, 1, 0, 1, 0, 1, 0];
        let y = vec![1, 1, 0, 0, 1, 1, 0, 0];
        assert!(compute_mi(&x, &y).abs() < 0.01);
    }

    #[test]
    fn test_compute_mi_empty() {
        assert_eq!(compute_mi(&[], &[]), 0.0);
    }

    #[test]
    fn test_mi_scores_overlapping() {
        let freq = make_frequents(vec![1, 2], vec![(20, 60)]);
        let events = vec![
            make_event("E1", 30, 50),
            make_event("DISTANT", 90, 100),
        ];
        let scores = compute_mi_scores(&freq, &events);
        let mi_e1 = scores[&(vec![1, 2], "E1".to_string())];
        let mi_dist = scores[&(vec![1, 2], "DISTANT".to_string())];
        assert!(mi_e1 > 0.0);
        assert!(mi_e1 > mi_dist);
    }

    #[test]
    fn test_mi_prefilter_passes() {
        let freq = make_frequents(vec![1, 2], vec![(20, 60)]);
        let events = vec![
            make_event("E1", 30, 50),
            make_event("DISTANT", 90, 100),
        ];
        let (_, passed) = mi_prefilter(&freq, &events, 0.001);
        assert!(passed.contains(&(vec![1, 2], "E1".to_string())));
    }

    #[test]
    fn test_mi_prefilter_filters_low() {
        let freq = make_frequents(vec![1], vec![(0, 5)]);
        let events = vec![make_event("E1", 500, 1000)];
        let (_, passed) = mi_prefilter(&freq, &events, 0.1);
        assert!(!passed.contains(&(vec![1], "E1".to_string())));
    }

    // -----------------------------------------------------------------------
    // Stage 2: Sweep Line
    // -----------------------------------------------------------------------

    #[test]
    fn test_sweep_matches_brute_force() {
        let mut freq = HashMap::new();
        freq.insert(vec![1i64, 2], vec![(0i64, 10), (20, 30)]);
        freq.insert(vec![3i64], vec![(5i64, 15)]);
        let events = vec![make_event("E1", 12, 20), make_event("E2", 0, 100)];
        let bf = match_all(&freq, &events, 2, 1);
        let sw = match_sweep_line(&freq, &events, 2, 1, None);

        let bf_set: HashSet<(Vec<i64>, i64, i64, String, String)> = bf
            .iter()
            .map(|m| {
                (
                    m.itemset.clone(),
                    m.dense_start,
                    m.dense_end,
                    m.event_id.clone(),
                    m.relation_type.clone(),
                )
            })
            .collect();
        let sw_set: HashSet<(Vec<i64>, i64, i64, String, String)> = sw
            .iter()
            .map(|m| {
                (
                    m.itemset.clone(),
                    m.dense_start,
                    m.dense_end,
                    m.event_id.clone(),
                    m.relation_type.clone(),
                )
            })
            .collect();
        assert_eq!(bf_set, sw_set, "Brute-force and Sweep Line should match");
    }

    #[test]
    fn test_sweep_candidate_filter() {
        let mut freq = HashMap::new();
        freq.insert(vec![1i64, 2], vec![(0i64, 10)]);
        freq.insert(vec![3i64], vec![(0i64, 10)]);
        let events = vec![make_event("E1", 12, 20), make_event("E2", 0, 100)];
        let candidates = vec![(vec![1i64, 2], "E1".to_string())];
        let sw = match_sweep_line(&freq, &events, 2, 1, Some(&candidates));
        for m in &sw {
            assert_eq!(m.itemset, vec![1, 2]);
            assert_eq!(m.event_id, "E1");
        }
    }

    #[test]
    fn test_sweep_empty_candidates() {
        let freq = make_frequents(vec![1], vec![(0, 10)]);
        let events = vec![make_event("E1", 0, 10)];
        let sw = match_sweep_line(&freq, &events, 0, 1, Some(&[]));
        assert!(sw.is_empty());
    }

    #[test]
    fn test_sweep_dfe_detected() {
        let freq = make_frequents(vec![1, 2], vec![(0, 10)]);
        let events = vec![make_event("E1", 12, 20)];
        let sw = match_sweep_line(&freq, &events, 2, 1, None);
        let types: Vec<&str> = sw.iter().map(|m| m.relation_type.as_str()).collect();
        assert!(types.contains(&"DenseFollowsEvent"));
    }

    // -----------------------------------------------------------------------
    // Stage 3: Permutation Test
    // -----------------------------------------------------------------------

    #[test]
    fn test_cyclic_shift() {
        let events = vec![make_event("E1", 10, 20)];
        let shifted = cyclic_shift_events(&events, 5, 0, 30);
        assert_eq!(shifted[0].start, 15);
        assert_eq!(shifted[0].end, 25);
    }

    #[test]
    fn test_cyclic_shift_wraps() {
        let events = vec![make_event("E1", 25, 28)];
        let shifted = cyclic_shift_events(&events, 10, 0, 30);
        assert_eq!(shifted[0].start, 4); // (25 + 10) % 31 = 4
    }

    #[test]
    fn test_count_relations_basic() {
        let results = vec![
            make_match(&[1, 2], 0, 10, &make_event("E1", 0, 10), "DenseFollowsEvent", None),
            make_match(&[1, 2], 20, 30, &make_event("E1", 0, 10), "DenseFollowsEvent", None),
        ];
        let counts = count_relations(&results);
        assert_eq!(
            counts[&(vec![1, 2], "E1".to_string(), "DenseFollowsEvent".to_string())],
            2
        );
    }

    #[test]
    fn test_permutation_strong_relation_significant() {
        // 密集区間が多数あり、全てイベント内 → ECD が高頻度で有意になるべき
        let freq = make_frequents(
            vec![1, 2],
            vec![(10, 20), (30, 40), (50, 60), (70, 80), (90, 100)],
        );
        let events = vec![make_event("E1", 0, 110)];
        let sig = permutation_test(
            &freq, &events, 0, 1, 199, 0.2, "westfall_young", Some(42), None,
        );
        let types: HashSet<&str> = sig.iter().map(|s| s.relation_type.as_str()).collect();
        assert!(
            types.contains("EventContainsDense") || types.contains("DenseContainsEvent"),
            "A containment relation should be significant, got: {:?}",
            sig.iter().map(|s| (&s.relation_type, s.adjusted_p_value)).collect::<Vec<_>>()
        );
    }

    #[test]
    fn test_permutation_unrelated_not_significant() {
        let freq = make_frequents(vec![1], vec![(0, 5)]);
        let events = vec![make_event("E1", 10000, 10005)];
        let sig = permutation_test(&freq, &events, 0, 1, 99, 0.05, "westfall_young", Some(42), None);
        assert!(sig.is_empty());
    }

    #[test]
    fn test_permutation_seed_reproducibility() {
        let freq = make_frequents(vec![1, 2], vec![(0, 50)]);
        let events = vec![make_event("E1", 10, 40)];
        let r1 = permutation_test(&freq, &events, 0, 1, 49, 0.5, "westfall_young", Some(123), None);
        let r2 = permutation_test(&freq, &events, 0, 1, 49, 0.5, "westfall_young", Some(123), None);
        assert_eq!(r1.len(), r2.len());
        for (a, b) in r1.iter().zip(r2.iter()) {
            assert_eq!(a.p_value, b.p_value);
        }
    }

    #[test]
    fn test_permutation_bonferroni() {
        let freq = make_frequents(vec![1, 2], vec![(10, 20)]);
        let events = vec![make_event("E1", 0, 100)];
        let sig = permutation_test(&freq, &events, 0, 1, 49, 0.5, "bonferroni", Some(42), None);
        // エラーなく完了
        assert!(sig.iter().all(|s| s.adjusted_p_value <= 1.0));
    }

    // -----------------------------------------------------------------------
    // Pipeline Orchestrator
    // -----------------------------------------------------------------------

    #[test]
    fn test_pipeline_all_stages() {
        let mut freq = HashMap::new();
        freq.insert(vec![1i64, 2], vec![(0i64, 50), (60, 110)]);
        freq.insert(vec![3i64], vec![(0i64, 20)]);
        let events = vec![make_event("E1", 10, 40), make_event("E2", 200, 300)];
        let config = PipelineConfig {
            epsilon: 2,
            d_0: 1,
            stage1_enabled: true,
            mi_threshold: 0.001,
            stage2_enabled: true,
            stage3_enabled: true,
            n_permutations: 49,
            alpha: 0.5,
            seed: Some(42),
            ..Default::default()
        };
        let result = run_pipeline(&freq, &events, &config);
        assert!(!result.brute_force_results.is_empty());
        assert!(result.mi_scores.is_some());
        assert!(result.sweep_results.is_some());
        assert!(result.significant_relations.is_some());
    }

    #[test]
    fn test_pipeline_stage1_disabled() {
        let freq = make_frequents(vec![1, 2], vec![(0, 50)]);
        let events = vec![make_event("E1", 10, 40)];
        let config = PipelineConfig {
            epsilon: 2,
            d_0: 1,
            stage1_enabled: false,
            stage2_enabled: true,
            stage3_enabled: false,
            ..Default::default()
        };
        let result = run_pipeline(&freq, &events, &config);
        assert!(result.mi_scores.is_none());
        assert!(result.sweep_results.is_some());
        // Stage 1 無効 → sweep line は全ペアを処理
        let bf_set: HashSet<(Vec<i64>, i64, String, String)> = result
            .brute_force_results
            .iter()
            .map(|m| (m.itemset.clone(), m.dense_start, m.event_id.clone(), m.relation_type.clone()))
            .collect();
        let sw_set: HashSet<(Vec<i64>, i64, String, String)> = result
            .sweep_results
            .unwrap()
            .iter()
            .map(|m| (m.itemset.clone(), m.dense_start, m.event_id.clone(), m.relation_type.clone()))
            .collect();
        assert_eq!(bf_set, sw_set);
    }

    #[test]
    fn test_pipeline_brute_force_always_runs() {
        let freq = make_frequents(vec![1, 2], vec![(0, 50)]);
        let events = vec![make_event("E1", 10, 40)];
        let config = PipelineConfig {
            stage1_enabled: false,
            stage2_enabled: false,
            stage3_enabled: false,
            ..Default::default()
        };
        let result = run_pipeline(&freq, &events, &config);
        assert!(!result.brute_force_results.is_empty());
    }
}
