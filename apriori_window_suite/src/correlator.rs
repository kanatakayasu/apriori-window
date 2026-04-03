//! Event Attribution Pipeline — Phase 2 (Rust port)
//!
//! サポート時系列の変化点検出と外部イベントへの帰属。
//! Python 実装: `python/event_attribution.py`

use std::collections::HashMap;

use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use rayon::prelude::*;

use crate::io::Event;
use crate::util::{intersect_sorted_lists, lower_bound, upper_bound};

// ---------------------------------------------------------------------------
// データ型
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct ChangePoint {
    pub time: i64,
    pub direction: String, // "up" or "down"
    pub magnitude: f64,
    pub support_before: f64,
    pub support_after: f64,
}

#[derive(Debug, Clone)]
pub struct SignificantAttribution {
    pub pattern: Vec<i64>,
    /// Dense interval that triggered this attribution (left window index, inclusive).
    pub interval_start: i64,
    /// Dense interval right endpoint (left window index, inclusive).
    pub interval_end: i64,
    pub change_time: i64,
    pub change_direction: String,
    pub change_magnitude: f64,
    pub event_name: String,
    pub event_start: i64,
    pub event_end: i64,
    pub proximity: f64,
    pub attribution_score: f64,
    pub p_value: f64,
    pub adjusted_p_value: f64,
}

#[derive(Debug, Clone)]
pub struct AttributionConfig {
    pub sigma: Option<f64>,
    pub n_permutations: usize,
    pub alpha: f64,
    pub correction_method: String, // "bh" or "bonferroni"
    pub global_correction: bool,
    pub deduplicate_overlap: bool,
    /// 振幅フィルタ: max_support - min_support がこの値以下のパターンを除外 (δ)
    pub min_support_range: i64,
    pub min_magnitude: f64,
    pub attribution_threshold: f64,
    pub seed: Option<u64>,
    pub ablation_mode: Option<String>, // "no_prox", "no_mag", "mag_only", "prox_only"
    pub min_pattern_length: usize,
    /// 変化量の正規化方式: "none", "sqrt", "full"
    pub magnitude_normalization: String,
}

impl Default for AttributionConfig {
    fn default() -> Self {
        Self {
            sigma: None,
            n_permutations: 1000,
            alpha: 0.05,
            correction_method: "bh".to_string(),
            global_correction: true,
            deduplicate_overlap: false,
            min_support_range: 0,
            min_magnitude: 0.0,
            attribution_threshold: 0.1,
            seed: None,
            ablation_mode: None,
            min_pattern_length: 2,
            magnitude_normalization: "sqrt".to_string(),
        }
    }
}

/// 置換検定の中間結果（alpha 判定前）
#[derive(Debug, Clone)]
struct RawTestResult {
    pattern: Vec<i64>,
    interval: (i64, i64),
    change_point: ChangePoint,
    event: Event,
    proximity: f64,
    obs_score: f64,
    p_value: f64,
}

// ---------------------------------------------------------------------------
// Step 1: Local Support & Change Point Detection
// ---------------------------------------------------------------------------

/// 位置 t でのサポートを二分探索で O(log n) 計算する。
///
/// s_P(t) = |{ts in timestamps : t <= ts < t + window_size}|
pub fn local_support(timestamps: &[i64], t: i64, window_size: i64) -> i64 {
    let left = lower_bound(timestamps, t);
    let right = upper_bound(timestamps, t + window_size - 1);
    (right - left) as i64
}

/// Phase 1 の密集区間リストから変化点を直接生成する。
///
/// 各区間 (s, e) について:
///   - 位置 s で "up" 変化点を生成
///   - 位置 e+1 で "down" 変化点を生成（e+1 < max_pos の場合）
///
/// magnitude は交差前後の level_window 幅の平均サポート差（レベルシフト量）。
pub fn dense_intervals_to_change_points(
    intervals: &[(i64, i64)],
    timestamps: &[i64],
    window_size: i64,
    n_transactions: i64,
    level_window: i64,
) -> Vec<ChangePoint> {
    let max_pos = (n_transactions - window_size + 1).max(0);
    if max_pos == 0 || intervals.is_empty() {
        return Vec::new();
    }

    let mut changes = Vec::new();

    for &(s, e) in intervals {
        // "up" change point at position s
        if s >= 0 && s < max_pos {
            let before_start = (s - level_window).max(0);
            let after_end = (s + level_window).min(max_pos);
            let n_before = s - before_start;
            let n_after = after_end - s;

            let mean_before = if n_before > 0 {
                (before_start..s)
                    .map(|t| local_support(timestamps, t, window_size) as f64)
                    .sum::<f64>()
                    / n_before as f64
            } else {
                0.0
            };
            let mean_after = if n_after > 0 {
                (s..after_end)
                    .map(|t| local_support(timestamps, t, window_size) as f64)
                    .sum::<f64>()
                    / n_after as f64
            } else {
                0.0
            };
            let mag = mean_after - mean_before;
            changes.push(ChangePoint {
                time: s,
                direction: "up".to_string(),
                magnitude: mag.max(1.0),
                support_before: mean_before,
                support_after: mean_after,
            });
        }

        // "down" change point at position e+1
        let down_pos = e + 1;
        if down_pos > 0 && down_pos < max_pos {
            let before_start = (down_pos - level_window).max(0);
            let after_end = (down_pos + level_window).min(max_pos);
            let n_before = down_pos - before_start;
            let n_after = after_end - down_pos;

            let mean_before = if n_before > 0 {
                (before_start..down_pos)
                    .map(|t| local_support(timestamps, t, window_size) as f64)
                    .sum::<f64>()
                    / n_before as f64
            } else {
                0.0
            };
            let mean_after = if n_after > 0 {
                (down_pos..after_end)
                    .map(|t| local_support(timestamps, t, window_size) as f64)
                    .sum::<f64>()
                    / n_after as f64
            } else {
                0.0
            };
            let mag = mean_before - mean_after;
            changes.push(ChangePoint {
                time: down_pos,
                direction: "down".to_string(),
                magnitude: mag.max(1.0),
                support_before: mean_before,
                support_after: mean_after,
            });
        }
    }

    changes
}

// ---------------------------------------------------------------------------
// Step 2: Event Attribution Scoring
// ---------------------------------------------------------------------------

/// 変化点とイベントの時間的近接度を計算する。
///
/// dist = min(|change_time - start|, |change_time - end|)
/// return exp(-dist / sigma)
pub fn compute_proximity(change_time: i64, event: &Event, sigma: f64) -> f64 {
    let dist = (change_time - event.start)
        .abs()
        .min((change_time - event.end).abs()) as f64;
    if sigma > 0.0 {
        (-dist / sigma).exp()
    } else if dist == 0.0 {
        1.0
    } else {
        0.0
    }
}

/// magnitude を正規化する。
///
/// - "sqrt": mag / sqrt(max(1, support_before))
/// - "full": mag / max(1, support_before)
/// - "none" (その他): 正規化なし
pub fn normalize_magnitude(magnitude: f64, support_before: f64, normalization: &str) -> f64 {
    match normalization {
        "sqrt" => magnitude / support_before.max(1.0).sqrt(),
        "full" => magnitude / support_before.max(1.0),
        _ => magnitude,
    }
}

/// 帰属スコアを計算し、イベントごとに集約して閾値を超えた (event_id, score) を返す。
pub fn score_attributions(
    change_points: &[ChangePoint],
    events: &[Event],
    sigma: f64,
    threshold: f64,
    ablation_mode: Option<&str>,
    normalization: &str,
) -> Vec<(String, f64)> {
    // event_id -> total score
    let mut scores: HashMap<String, f64> = HashMap::new();

    for cp in change_points {
        for event in events {
            let prox = compute_proximity(cp.time, event, sigma);
            let mag = normalize_magnitude(cp.magnitude.abs(), cp.support_before, normalization);

            let score = match ablation_mode {
                Some("no_prox") | Some("mag_only") => mag,
                Some("no_mag") | Some("prox_only") => prox,
                _ => prox * mag,
            };

            if score >= threshold {
                *scores.entry(event.event_id.clone()).or_insert(0.0) += score;
            }
        }
    }

    scores.into_iter().collect()
}

/// 帰属スコアの詳細情報（置換検定用の内部ヘルパー）
struct ScoredCandidate {
    event: Event,
    proximity: f64,
    score: f64,
}

/// 各 (change_point, event) の詳細スコアを返す内部ヘルパー
fn score_attributions_detailed(
    change_points: &[ChangePoint],
    events: &[Event],
    sigma: f64,
    threshold: f64,
    ablation_mode: Option<&str>,
    normalization: &str,
) -> Vec<ScoredCandidate> {
    let mut candidates = Vec::new();

    for cp in change_points {
        for event in events {
            let prox = compute_proximity(cp.time, event, sigma);
            let mag = normalize_magnitude(cp.magnitude.abs(), cp.support_before, normalization);

            let score = match ablation_mode {
                Some("no_prox") | Some("mag_only") => mag,
                Some("no_mag") | Some("prox_only") => prox,
                _ => prox * mag,
            };

            if score >= threshold {
                candidates.push(ScoredCandidate {
                    event: event.clone(),
                    proximity: prox,
                    score,
                });
            }
        }
    }

    candidates
}

// ---------------------------------------------------------------------------
// Step 3: Permutation Testing
// ---------------------------------------------------------------------------

/// イベント時刻を円形シフトする。
pub fn circular_shift_events(events: &[Event], offset: i64, max_time: i64) -> Vec<Event> {
    events
        .iter()
        .map(|e| {
            let duration = e.end - e.start;
            let new_start = ((e.start + offset) % max_time + max_time) % max_time;
            let mut new_end = new_start + duration;
            if new_end >= max_time {
                new_end = max_time - 1;
            }
            Event {
                event_id: e.event_id.clone(),
                name: e.name.clone(),
                start: new_start,
                end: new_end,
            }
        })
        .collect()
}

/// 1つの密集区間 `interval` に対して置換検定を実行し、未補正 p 値を返す。
///
/// 新設計: (P, I, E) を仮説単位とし、区間ごとに独立した検定を行う。
/// `pair_seed` は (pattern, interval) に固有の決定論的シードで並列実行時の再現性を保証する。
fn permutation_test_raw(
    pattern: &[i64],
    interval: (i64, i64),
    change_points: &[ChangePoint],
    events: &[Event],
    sigma: f64,
    max_time: i64,
    config: &AttributionConfig,
    pair_seed: u64,
) -> Vec<RawTestResult> {
    let ablation = config.ablation_mode.as_deref();
    let threshold = config.attribution_threshold;
    let normalization = config.magnitude_normalization.as_str();

    // 観測スコアの詳細
    let obs_candidates = score_attributions_detailed(
        change_points, events, sigma, threshold, ablation, normalization,
    );
    if obs_candidates.is_empty() {
        return Vec::new();
    }

    // イベント ID ごとのスコア合計とベスト情報
    let mut obs_scores: HashMap<String, f64> = HashMap::new();
    let mut best_prox: HashMap<String, f64> = HashMap::new();
    let mut best_event_map: HashMap<String, Event> = HashMap::new();

    for c in &obs_candidates {
        *obs_scores.entry(c.event.event_id.clone()).or_insert(0.0) += c.score;
        let is_better = best_prox
            .get(&c.event.event_id)
            .map_or(true, |&p| c.proximity > p);
        if is_better {
            best_prox.insert(c.event.event_id.clone(), c.proximity);
            best_event_map.insert(c.event.event_id.clone(), c.event.clone());
        }
    }

    // 置換分布の構築（pair_seed で各 (P, I) ペア固有の RNG を使用）
    let mut perm_counts: HashMap<String, usize> = obs_scores
        .keys()
        .map(|k| (k.clone(), 0))
        .collect();

    let mut rng = StdRng::seed_from_u64(pair_seed);

    for _ in 0..config.n_permutations {
        let offset = rng.gen_range(1..max_time);
        let shifted = circular_shift_events(events, offset, max_time);

        let mut perm_scores: HashMap<String, f64> = HashMap::new();
        for cp in change_points {
            for event in &shifted {
                let prox = compute_proximity(cp.time, event, sigma);
                let mag = normalize_magnitude(cp.magnitude.abs(), cp.support_before, normalization);
                let score = match ablation {
                    Some("no_prox") | Some("mag_only") => mag,
                    Some("no_mag") | Some("prox_only") => prox,
                    _ => prox * mag,
                };
                if score >= threshold {
                    *perm_scores.entry(event.event_id.clone()).or_insert(0.0) += score;
                }
            }
        }

        for (eid, &obs_s) in &obs_scores {
            if perm_scores.get(eid).copied().unwrap_or(0.0) >= obs_s {
                *perm_counts.get_mut(eid).unwrap() += 1;
            }
        }
    }

    // 未補正 p 値（interval は常に正しく設定済み — 事後選択不要）
    let n_perm = config.n_permutations;
    obs_scores
        .iter()
        .map(|(eid, &obs_s)| {
            let count = perm_counts[eid];
            let p_value = (count as f64 + 1.0) / (n_perm as f64 + 1.0);
            let ev = &best_event_map[eid];
            let prox = best_prox[eid];

            // UP 変化点（区間 onset）を代表として選択
            let best_cp = change_points
                .iter()
                .filter(|cp| cp.direction == "up")
                .max_by(|a, b| {
                    compute_proximity(a.time, ev, sigma)
                        .partial_cmp(&compute_proximity(b.time, ev, sigma))
                        .unwrap_or(std::cmp::Ordering::Equal)
                })
                .or_else(|| change_points.first())
                .unwrap()
                .clone();

            RawTestResult {
                pattern: pattern.to_vec(),
                interval,
                change_point: best_cp,
                event: ev.clone(),
                proximity: prox,
                obs_score: obs_s,
                p_value,
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Step 4: Multiple Testing Correction
// ---------------------------------------------------------------------------

/// Benjamini-Hochberg step-down 補正。
///
/// 入力: (index, p_value) のスライス、仮説総数 m
/// 出力: (index, adjusted_p_value) のベクター
pub fn bh_correction(p_values: &mut [(usize, f64)], m: usize) -> Vec<(usize, f64)> {
    // p 値昇順でソート
    p_values.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));

    let n = p_values.len();
    let mut adj = vec![0.0; n];

    for i in (0..n).rev() {
        let rank = i + 1;
        let raw_adj = (p_values[i].1 * m as f64 / rank as f64).min(1.0);
        if i == n - 1 {
            adj[i] = raw_adj;
        } else {
            adj[i] = adj[i + 1].min(raw_adj);
        }
    }

    p_values
        .iter()
        .enumerate()
        .map(|(i, &(idx, _))| (idx, adj[i]))
        .collect()
}

// ---------------------------------------------------------------------------
// Step 5: Deduplication
// ---------------------------------------------------------------------------

/// 同一イベントに帰属されたパターンのうち、アイテムが重複するものを
/// Union-Find でクラスタリングし、各クラスタから最高スコアのパターンのみ残す。
///
/// 長さ l のパターン同士は、共有アイテム数 >= ceil(l/2) のとき辺を張る。
/// 異なる長さのパターン間では辺を張らない。
pub fn deduplicate_by_item_overlap(
    results: Vec<SignificantAttribution>,
) -> Vec<SignificantAttribution> {
    use std::collections::HashSet;

    // (event_name, interval_start, interval_end) でグループ化
    // 同じ区間・同じイベントに帰属されたパターン同士のみ dedup — 異なる区間は独立した帰属として保持
    let mut by_event: HashMap<(String, i64, i64), Vec<SignificantAttribution>> = HashMap::new();
    for r in results {
        let key = (r.event_name.clone(), r.interval_start, r.interval_end);
        by_event
            .entry(key)
            .or_default()
            .push(r);
    }

    let mut deduplicated = Vec::new();

    for (_event_name, event_results) in &by_event {
        // パターン長でグループ化
        let mut by_length: HashMap<usize, Vec<&SignificantAttribution>> = HashMap::new();
        for r in event_results {
            by_length
                .entry(r.pattern.len())
                .or_default()
                .push(r);
        }

        for (&l, length_results) in &by_length {
            let n = length_results.len();
            if n <= 1 {
                for r in length_results {
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

            // Majority sharing threshold: ceil(l / 2)
            let threshold = (l + 1) / 2;

            // ペアワイズ比較
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

            // クラスタごとに最高スコアを選択
            let mut clusters: HashMap<usize, Vec<usize>> = HashMap::new();
            for i in 0..n {
                let root = find(&mut parent, i);
                clusters.entry(root).or_default().push(i);
            }

            for (_root, members) in &clusters {
                let best_idx = *members
                    .iter()
                    .max_by(|&&a, &&b| {
                        length_results[a]
                            .attribution_score
                            .partial_cmp(&length_results[b].attribution_score)
                            .unwrap_or(std::cmp::Ordering::Equal)
                    })
                    .unwrap();
                deduplicated.push(length_results[best_idx].clone());
            }
        }
    }

    // Phase 2: Cross-length subset dedup
    // If pattern A ⊂ B (same event + same interval), merge and keep highest score
    let mut by_event2: HashMap<(String, i64, i64), Vec<SignificantAttribution>> = HashMap::new();
    for r in deduplicated {
        let key = (r.event_name.clone(), r.interval_start, r.interval_end);
        by_event2
            .entry(key)
            .or_default()
            .push(r);
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
                .max_by(|&&a, &&b| {
                    event_results[a]
                        .attribution_score
                        .partial_cmp(&event_results[b].attribution_score)
                        .unwrap_or(std::cmp::Ordering::Equal)
                })
                .unwrap();
            final_results.push(event_results[best_idx].clone());
        }
    }

    final_results
}

// ---------------------------------------------------------------------------
// Pipeline 統合
// ---------------------------------------------------------------------------

/// パターンの出現トランザクション ID リストを取得する。
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
            .map(|item| {
                item_transaction_map
                    .get(item)
                    .expect("item not found in transaction map")
            })
            .collect();
        let refs: Vec<&Vec<i64>> = lists.iter().copied().collect();
        intersect_sorted_lists(&refs)
    }
}

/// Event Attribution Pipeline を実行する。
///
/// 新設計: 密集区間を直接イベントに帰属させる。
/// 仮説単位を (pattern, event) から (pattern, interval, event) に変更。
///
/// 最適化:
/// - タイムスタンプを全パターン分並列プリ計算（複数区間を持つパターンの重複計算を回避）
/// - (pattern, interval) ペアに展開し rayon で並列置換検定
/// - 事後的な区間選択を廃止し、設計上の正確性を向上
pub fn run_attribution_pipeline(
    frequents: &HashMap<Vec<i64>, Vec<(i64, i64)>>,
    item_transaction_map: &HashMap<i64, Vec<i64>>,
    events: &[Event],
    window_size: i64,
    _threshold: i64,
    n_transactions: i64,
    config: &AttributionConfig,
) -> Vec<SignificantAttribution> {
    let sigma = config.sigma.unwrap_or(window_size as f64);
    let max_pos = (n_transactions - window_size + 1).max(0);

    if max_pos == 0 || events.is_empty() {
        return Vec::new();
    }

    // Step 0: パターンのタイムスタンプを並列プリ計算
    // 同一パターンが複数の密集区間を持つ場合に重複計算を避ける
    let filtered_patterns: Vec<&Vec<i64>> = frequents
        .keys()
        .filter(|pat| pat.len() >= config.min_pattern_length)
        .collect();

    let timestamps_map: HashMap<&Vec<i64>, Vec<i64>> = filtered_patterns
        .par_iter()
        .map(|pat| (*pat, get_pattern_timestamps(pat, item_transaction_map)))
        .collect();

    // Step 1: (pattern, interval) ペアに展開
    // 各密集区間を独立した仮説として扱う（今回の設計変更の核心）
    let pairs: Vec<(&Vec<i64>, (i64, i64))> = frequents
        .iter()
        .filter(|(pat, _)| pat.len() >= config.min_pattern_length)
        .flat_map(|(pat, intervals)| intervals.iter().map(move |&iv| (pat, iv)))
        .collect();

    // Step 2: 各 (pattern, interval) ペアに対して並列置換検定
    let all_raw: Vec<RawTestResult> = pairs
        .par_iter()
        .flat_map(|(pattern, interval)| {
            let interval = *interval;
            let timestamps = &timestamps_map[pattern];

            // 区間の変化点を生成（2点: onset@s, offset@e+1）
            let change_points = dense_intervals_to_change_points(
                &[interval],
                timestamps,
                window_size,
                n_transactions,
                20,
            );
            if change_points.is_empty() {
                return Vec::new();
            }

            // 振幅フィルタ: UP CP の magnitude で per-interval 判定
            // dense_intervals_to_change_points が計算した onset magnitude を再利用
            if config.min_support_range > 0 {
                let max_mag = change_points
                    .iter()
                    .filter(|cp| cp.direction == "up")
                    .map(|cp| cp.magnitude)
                    .fold(0.0_f64, f64::max);
                if (max_mag as i64) < config.min_support_range {
                    return Vec::new();
                }
            }

            // min_magnitude フィルタ
            let change_points: Vec<ChangePoint> = if config.min_magnitude > 0.0 {
                change_points
                    .into_iter()
                    .filter(|cp| cp.magnitude >= config.min_magnitude)
                    .collect()
            } else {
                change_points
            };
            if change_points.is_empty() {
                return Vec::new();
            }

            // (P, I) 固有のシードを生成（決定論的・並列実行での再現性を保証）
            let pair_seed = {
                let base = config.seed.unwrap_or(0);
                let ph = pattern.iter().fold(base, |h, &item| {
                    h.wrapping_mul(1_000_003).wrapping_add(item as u64)
                });
                ph.wrapping_mul(1_000_003)
                    .wrapping_add(interval.0 as u64)
                    .wrapping_mul(1_000_003)
                    .wrapping_add(interval.1 as u64)
            };

            permutation_test_raw(
                pattern, interval, &change_points, events,
                sigma, max_pos, config, pair_seed,
            )
        })
        .collect();

    if all_raw.is_empty() {
        return Vec::new();
    }

    // Step 3: (P, I, E) 単位での多重検定補正
    let n_total = all_raw.len();
    let mut results: Vec<SignificantAttribution> = Vec::new();

    if config.correction_method == "bh" {
        let mut indexed: Vec<(usize, f64)> = all_raw
            .iter()
            .enumerate()
            .map(|(i, r)| (i, r.p_value))
            .collect();
        let adjusted = bh_correction(&mut indexed, n_total);
        for (idx, adj_p) in adjusted {
            if adj_p < config.alpha {
                results.push(raw_to_significant(&all_raw[idx], adj_p));
            }
        }
    } else {
        // Bonferroni
        for r in &all_raw {
            let adj_p = (r.p_value * n_total as f64).min(1.0);
            if adj_p < config.alpha {
                results.push(raw_to_significant(r, adj_p));
            }
        }
    }

    // Step 4: 重複排除（同一区間・同一イベントに帰属されたパターン同士のみ）
    if config.deduplicate_overlap && !results.is_empty() {
        results = deduplicate_by_item_overlap(results);
    }

    results
}

fn raw_to_significant(r: &RawTestResult, adj_p: f64) -> SignificantAttribution {
    SignificantAttribution {
        pattern: r.pattern.clone(),
        interval_start: r.interval.0,
        interval_end: r.interval.1,
        change_time: r.change_point.time,
        change_direction: r.change_point.direction.clone(),
        change_magnitude: r.change_point.magnitude,
        event_name: r.event.name.clone(),
        event_start: r.event.start,
        event_end: r.event.end,
        proximity: r.proximity,
        attribution_score: r.obs_score,
        p_value: r.p_value,
        adjusted_p_value: adj_p,
    }
}

// ---------------------------------------------------------------------------
// テスト
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_local_support() {
        // timestamps: [0, 1, 2, 5, 6, 7, 10]
        let ts = vec![0, 1, 2, 5, 6, 7, 10];
        // window_size=3: count of ts in [t, t+3)
        assert_eq!(local_support(&ts, 0, 3), 3); // 0,1,2
        assert_eq!(local_support(&ts, 1, 3), 2); // 1,2
        assert_eq!(local_support(&ts, 5, 3), 3); // 5,6,7
        assert_eq!(local_support(&ts, 8, 3), 1); // 10
        assert_eq!(local_support(&ts, 11, 3), 0); // nothing
    }

    #[test]
    fn test_dense_intervals_to_change_points() {
        // Simple case: one interval (5, 15), timestamps at every position
        let timestamps: Vec<i64> = (0..100).collect();
        let intervals = vec![(5, 15)];
        let window_size = 3;
        let n_transactions = 100;

        let changes = dense_intervals_to_change_points(
            &intervals, &timestamps, window_size, n_transactions, 20,
        );

        // Should have 2 change points: up at 5, down at 16
        assert_eq!(changes.len(), 2);
        assert_eq!(changes[0].time, 5);
        assert_eq!(changes[0].direction, "up");
        assert_eq!(changes[1].time, 16);
        assert_eq!(changes[1].direction, "down");
    }

    #[test]
    fn test_compute_proximity() {
        let event = Event {
            event_id: "E1".to_string(),
            name: "Event1".to_string(),
            start: 10,
            end: 20,
        };

        // Exact match with start
        let prox = compute_proximity(10, &event, 10.0);
        assert!((prox - 1.0).abs() < 1e-10);

        // Distance 5 from start
        let prox = compute_proximity(5, &event, 10.0);
        let expected = (-5.0_f64 / 10.0).exp();
        assert!((prox - expected).abs() < 1e-10);

        // Between start and end (dist = 0 from both or min)
        let prox = compute_proximity(15, &event, 10.0);
        let dist = 5.0_f64.min(5.0); // min(|15-10|, |15-20|)
        let expected = (-dist / 10.0).exp();
        assert!((prox - expected).abs() < 1e-10);
    }

    #[test]
    fn test_score_attributions() {
        let events = vec![
            Event {
                event_id: "E1".to_string(),
                name: "Event1".to_string(),
                start: 10,
                end: 12,
            },
            Event {
                event_id: "E2".to_string(),
                name: "Event2".to_string(),
                start: 100,
                end: 110,
            },
        ];

        let change_points = vec![ChangePoint {
            time: 10,
            direction: "up".to_string(),
            magnitude: 5.0,
            support_before: 1.0,
            support_after: 6.0,
        }];

        let sigma = 10.0;
        let results = score_attributions(&change_points, &events, sigma, 0.1, None, "none");

        // E1 should have high score (proximity ~1.0, magnitude=5.0)
        // E2 should have low score (proximity ~exp(-90/10), likely below threshold)
        assert!(!results.is_empty());
        let e1_score = results.iter().find(|(id, _)| id == "E1");
        assert!(e1_score.is_some());
        assert!(e1_score.unwrap().1 > 4.0); // prox ~1.0, mag=5.0
    }

    #[test]
    fn test_circular_shift_events() {
        let events = vec![Event {
            event_id: "E1".to_string(),
            name: "Event1".to_string(),
            start: 10,
            end: 15,
        }];

        let shifted = circular_shift_events(&events, 50, 100);
        assert_eq!(shifted[0].start, 60);
        assert_eq!(shifted[0].end, 65);

        // Wrap around
        let shifted = circular_shift_events(&events, 95, 100);
        assert_eq!(shifted[0].start, 5); // (10+95) % 100 = 5
        // end clamped: 5 + 5 = 10
        assert_eq!(shifted[0].end, 10);
    }

    #[test]
    fn test_bh_correction() {
        // 5 hypotheses with p-values
        let mut pvals: Vec<(usize, f64)> = vec![
            (0, 0.01),
            (1, 0.04),
            (2, 0.03),
            (3, 0.20),
            (4, 0.50),
        ];
        let adjusted = bh_correction(&mut pvals, 5);

        // After sorting by p: 0.01, 0.03, 0.04, 0.20, 0.50
        // adj[4] = min(1, 0.50 * 5/5) = 0.50
        // adj[3] = min(0.50, min(1, 0.20*5/4)) = min(0.50, 0.25) = 0.25
        // adj[2] = min(0.25, min(1, 0.04*5/3)) = min(0.25, 0.0667) = 0.0667
        // adj[1] = min(0.0667, min(1, 0.03*5/2)) = min(0.0667, 0.075) = 0.0667
        // adj[0] = min(0.0667, min(1, 0.01*5/1)) = min(0.0667, 0.05) = 0.05

        // Find result for original index 0 (p=0.01)
        let adj_0 = adjusted.iter().find(|&&(idx, _)| idx == 0).unwrap().1;
        assert!((adj_0 - 0.05).abs() < 1e-10);

        // All adjusted p-values should be monotonically non-decreasing (after sort)
        for w in adjusted.windows(2) {
            assert!(w[0].1 <= w[1].1 + 1e-10);
        }
    }

    #[test]
    fn test_deduplicate_majority_sharing_len2() {
        // |P|=2: threshold = ceil(2/2) = 1 item shared → merge
        let results = vec![
            SignificantAttribution {
                pattern: vec![1, 2],
                interval_start: 0,
                interval_end: 0,
                change_time: 10,
                change_direction: "up".to_string(),
                change_magnitude: 5.0,
                event_name: "E".to_string(),
                event_start: 10,
                event_end: 15,
                proximity: 1.0,
                attribution_score: 10.0,
                p_value: 0.01,
                adjusted_p_value: 0.01,
            },
            SignificantAttribution {
                pattern: vec![1, 3],
                interval_start: 0,
                interval_end: 0,
                change_time: 10,
                change_direction: "up".to_string(),
                change_magnitude: 5.0,
                event_name: "E".to_string(),
                event_start: 10,
                event_end: 15,
                proximity: 1.0,
                attribution_score: 8.0,
                p_value: 0.02,
                adjusted_p_value: 0.02,
            },
        ];

        let deduped = deduplicate_by_item_overlap(results);
        // 1 shared item (item 1) >= ceil(2/2) = 1 → merged → keep best
        assert_eq!(deduped.len(), 1);
        assert_eq!(deduped[0].pattern, vec![1, 2]); // highest score
    }

    #[test]
    fn test_deduplicate_majority_sharing_len3() {
        // |P|=3: threshold = ceil(3/2) = 2 items shared for merge
        let results = vec![
            SignificantAttribution {
                pattern: vec![1, 2, 3],
                interval_start: 0,
                interval_end: 0,
                change_time: 10,
                change_direction: "up".to_string(),
                change_magnitude: 5.0,
                event_name: "E".to_string(),
                event_start: 10,
                event_end: 15,
                proximity: 1.0,
                attribution_score: 10.0,
                p_value: 0.01,
                adjusted_p_value: 0.01,
            },
            SignificantAttribution {
                pattern: vec![1, 4, 5],
                interval_start: 0,
                interval_end: 0,
                change_time: 10,
                change_direction: "up".to_string(),
                change_magnitude: 5.0,
                event_name: "E".to_string(),
                event_start: 10,
                event_end: 15,
                proximity: 1.0,
                attribution_score: 8.0,
                p_value: 0.02,
                adjusted_p_value: 0.02,
            },
            SignificantAttribution {
                pattern: vec![1, 2, 5],
                interval_start: 0,
                interval_end: 0,
                change_time: 10,
                change_direction: "up".to_string(),
                change_magnitude: 5.0,
                event_name: "E".to_string(),
                event_start: 10,
                event_end: 15,
                proximity: 1.0,
                attribution_score: 6.0,
                p_value: 0.03,
                adjusted_p_value: 0.03,
            },
        ];

        let deduped = deduplicate_by_item_overlap(results);
        // [1,2,3] & [1,4,5]: shared={1} = 1 < 2 → no merge
        // [1,2,3] & [1,2,5]: shared={1,2} = 2 >= 2 → merge → keep [1,2,3] (score=10)
        // [1,4,5] & [1,2,5]: shared={1,5} = 2 >= 2 → merge → keep [1,4,5] (score=8)
        // But [1,2,3]-[1,2,5] merged AND [1,4,5]-[1,2,5] merged
        // → all three in same component via [1,2,5] bridge
        // → keep [1,2,3] (score=10)
        assert_eq!(deduped.len(), 1);
        assert_eq!(deduped[0].pattern, vec![1, 2, 3]);
    }

    #[test]
    fn test_deduplicate_mixed_lengths() {
        // Subset patterns across lengths are merged (cross-length subset dedup)
        let results = vec![
            SignificantAttribution {
                pattern: vec![1, 2],
                interval_start: 0,
                interval_end: 0,
                change_time: 10,
                change_direction: "up".to_string(),
                change_magnitude: 5.0,
                event_name: "E".to_string(),
                event_start: 10,
                event_end: 15,
                proximity: 1.0,
                attribution_score: 10.0,
                p_value: 0.01,
                adjusted_p_value: 0.01,
            },
            SignificantAttribution {
                pattern: vec![1, 2, 3],
                interval_start: 0,
                interval_end: 0,
                change_time: 10,
                change_direction: "up".to_string(),
                change_magnitude: 5.0,
                event_name: "E".to_string(),
                event_start: 10,
                event_end: 15,
                proximity: 1.0,
                attribution_score: 8.0,
                p_value: 0.02,
                adjusted_p_value: 0.02,
            },
        ];

        let deduped = deduplicate_by_item_overlap(results);
        // {1,2} ⊂ {1,2,3} → merged, keep highest score ({1,2} with score 10.0)
        assert_eq!(deduped.len(), 1);
        assert_eq!(deduped[0].pattern, vec![1, 2]);
    }

    #[test]
    fn test_pipeline_basic() {
        // Simple synthetic data:
        // - 50 transactions, items appear densely in [10..30]
        // - Event overlaps with dense region start

        let mut item_transaction_map: HashMap<i64, Vec<i64>> = HashMap::new();
        // Item 1 and 2 appear in transactions 10..30
        let ts: Vec<i64> = (10..30).collect();
        item_transaction_map.insert(1, ts.clone());
        item_transaction_map.insert(2, ts);

        let mut frequents: HashMap<Vec<i64>, Vec<(i64, i64)>> = HashMap::new();
        // Pattern {1, 2} has one dense interval (10, 25)
        frequents.insert(vec![1, 2], vec![(10, 25)]);

        let events = vec![Event {
            event_id: "E1".to_string(),
            name: "TestEvent".to_string(),
            start: 9,
            end: 12,
        }];

        let config = AttributionConfig {
            n_permutations: 100,
            alpha: 1.0, // accept everything for testing
            seed: Some(42),
            ..Default::default()
        };

        let results = run_attribution_pipeline(
            &frequents,
            &item_transaction_map,
            &events,
            5,  // window_size
            3,  // threshold
            50, // n_transactions
            &config,
        );

        // Should find at least one attribution
        assert!(!results.is_empty());
        assert_eq!(results[0].event_name, "TestEvent");
        assert!(results[0].attribution_score > 0.0);
        assert!(results[0].p_value > 0.0 && results[0].p_value <= 1.0);
    }
}
