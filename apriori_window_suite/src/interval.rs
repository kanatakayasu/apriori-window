use crate::util::{lower_bound, upper_bound};

// ---------------------------------------------------------------------------
// 区間管理ヘルパー
// ---------------------------------------------------------------------------

pub fn find_covering_interval(intervals: &[(i64, i64)], point: i64) -> Option<(i64, i64)> {
    for (s, e) in intervals.iter().cloned() {
        if point >= s && point <= e {
            return Some((s, e));
        }
    }
    None
}

pub fn is_interval_covered(intervals: &[(i64, i64)], start: i64, end: i64) -> bool {
    intervals.iter().any(|(s, e)| start >= *s && end <= *e)
}

pub fn insert_and_merge_interval(intervals: &mut Vec<(i64, i64)>, new_interval: (i64, i64)) {
    intervals.push(new_interval);
    intervals.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| a.1.cmp(&b.1)));
    let mut merged: Vec<(i64, i64)> = Vec::new();
    for (s, e) in intervals.iter().cloned() {
        if let Some((_, last_e)) = merged.last_mut() {
            if s <= *last_e + 1 {
                *last_e = (*last_e).max(e);
            } else {
                merged.push((s, e));
            }
        } else {
            merged.push((s, e));
        }
    }
    *intervals = merged;
}

// ---------------------------------------------------------------------------
// 密集区間計算（スタックケース修正を追加）
// ---------------------------------------------------------------------------

/// 密集区間を計算する。
///
/// count > threshold のストライド調整にスタックケース処理を追加。
/// window_occurrences[surplus] == l のとき l += 1 にフォールバック。
pub fn compute_dense_intervals(
    timestamps: &[i64],
    window_size: i64,
    threshold: usize,
) -> Vec<(i64, i64)> {
    if window_size < 1 || threshold < 1 {
        panic!("window_size and threshold must be >= 1");
    }
    if timestamps.is_empty() {
        return Vec::new();
    }

    let ts = timestamps;
    let mut intervals: Vec<(i64, i64)> = Vec::new();
    let mut l = ts[0];
    let mut in_dense = false;
    let mut start: Option<i64> = None;
    let mut rightmost: Option<i64> = None;
    let ts_last = *ts.last().unwrap();

    while l <= ts_last {
        let start_idx = lower_bound(ts, l);
        let end_idx = upper_bound(ts, l + window_size);
        let count = end_idx - start_idx;
        let last_in_window = if count > 0 { Some(ts[end_idx - 1]) } else { None };

        if count < threshold {
            if in_dense {
                if let (Some(s), Some(r)) = (start, rightmost) {
                    intervals.push((s, r));
                }
            }
            in_dense = false;
            start = None;
            rightmost = None;
            let next_idx = upper_bound(ts, l);
            if next_idx >= ts.len() {
                break;
            }
            l = ts[next_idx];
            continue;
        }

        if count == threshold {
            if !in_dense {
                in_dense = true;
                start = Some(l);
                rightmost = last_in_window;
            } else if let (Some(rm), Some(liw)) = (rightmost, last_in_window) {
                rightmost = Some(rm.max(liw));
            }
            l += 1;
            continue;
        }

        // count > threshold
        if !in_dense {
            in_dense = true;
            start = Some(l);
            rightmost = last_in_window;
        } else if let (Some(rm), Some(liw)) = (rightmost, last_in_window) {
            rightmost = Some(rm.max(liw));
        }

        // ストライド調整（スタックケース修正）
        let surplus = count - threshold;
        let window_occurrences = &ts[start_idx..end_idx];
        let next_l = window_occurrences[surplus];
        if next_l > l {
            l = next_l;
        } else {
            l += 1; // スタック：window_occurrences[surplus] == l → 1トランザクション前進
        }
    }

    if in_dense {
        if let (Some(s), Some(r)) = (start, rightmost) {
            intervals.push((s, r));
        }
    }

    intervals
        .into_iter()
        .filter(|(s, e)| *e - *s >= window_size)
        .collect()
}

/// 候補区間ごとに密集区間を評価する。
pub fn compute_dense_intervals_with_candidates(
    timestamps: &[i64],
    window_size: i64,
    threshold: usize,
    candidate_ranges: &[(i64, i64)],
) -> Vec<(i64, i64)> {
    if candidate_ranges.is_empty() {
        return Vec::new();
    }
    if window_size < 1 || threshold < 1 {
        panic!("window_size and threshold must be >= 1");
    }
    if timestamps.is_empty() {
        return Vec::new();
    }

    let ts = timestamps;
    let mut intervals: Vec<(i64, i64)> = Vec::new();
    let ts_last = *ts.last().unwrap();
    let mut recorded: Vec<(i64, i64)> = Vec::new();

    let mut sorted_candidates = candidate_ranges.to_vec();
    sorted_candidates.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| a.1.cmp(&b.1)));

    for (c_start, c_end) in sorted_candidates.iter().cloned() {
        let mut l = c_start;
        let mut in_dense = false;
        let mut start: Option<i64> = None;
        let mut rightmost: Option<i64> = None;

        while l <= c_end && l <= ts_last {
            if let Some((_, rec_end)) = find_covering_interval(&recorded, l) {
                let next_l = rec_end + 1;
                if next_l > c_end {
                    break;
                }
                l = next_l;
                continue;
            }

            let start_idx = lower_bound(ts, l);
            let end_idx = upper_bound(ts, l + window_size);
            let count = end_idx - start_idx;
            let last_in_window = if count > 0 { Some(ts[end_idx - 1]) } else { None };

            if count < threshold {
                if in_dense {
                    if let (Some(s), Some(r)) = (start, rightmost) {
                        if !is_interval_covered(&recorded, s, r) {
                            intervals.push((s, r));
                            insert_and_merge_interval(&mut recorded, (s, r));
                        }
                    }
                }
                in_dense = false;
                start = None;
                rightmost = None;
                let next_idx = upper_bound(ts, l);
                if next_idx >= ts.len() {
                    break;
                }
                let next_l = ts[next_idx];
                if next_l > c_end {
                    break;
                }
                l = next_l;
                continue;
            }

            if count == threshold {
                if !in_dense {
                    in_dense = true;
                    start = Some(l);
                    rightmost = last_in_window;
                } else if let (Some(rm), Some(liw)) = (rightmost, last_in_window) {
                    rightmost = Some(rm.max(liw));
                }
                l += 1;
                continue;
            }

            // count > threshold
            if !in_dense {
                in_dense = true;
                start = Some(l);
                rightmost = last_in_window;
            } else if let (Some(rm), Some(liw)) = (rightmost, last_in_window) {
                rightmost = Some(rm.max(liw));
            }

            // ストライド調整（スタックケース修正）
            let surplus = count - threshold;
            let window_occurrences = &ts[start_idx..end_idx];
            let next_l = window_occurrences[surplus];
            if next_l > l {
                if next_l > c_end {
                    break;
                }
                l = next_l;
            } else {
                l += 1;
            }
        }

        if in_dense {
            if let (Some(s), Some(r)) = (start, rightmost) {
                if !is_interval_covered(&recorded, s, r) {
                    intervals.push((s, r));
                    insert_and_merge_interval(&mut recorded, (s, r));
                }
            }
        }
    }

    intervals
        .into_iter()
        .filter(|(s, e)| *e - *s >= window_size)
        .collect()
}

// ---------------------------------------------------------------------------
// テスト (TC3: スタックケース)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stuck_case_no_infinite_loop() {
        // ts=[5,5,5,5,5,8,12], threshold=3, window_size=10
        // l=5: count=7, surplus=4, window_occurrences[4]=5 → stuck → l=6
        let ts = vec![5i64, 5, 5, 5, 5, 8, 12];
        let intervals = compute_dense_intervals(&ts, 10, 3);
        let _ = intervals; // 完了すること自体がテスト（ハングしなければ OK）
    }

    #[test]
    fn test_stuck_case_with_candidates_no_hang() {
        let ts = vec![5i64, 5, 5, 5, 5, 8, 12];
        let cands = vec![(5i64, 15i64)];
        let intervals = compute_dense_intervals_with_candidates(&ts, 10, 3, &cands);
        let _ = intervals; // 完了すること自体がテスト
    }

    #[test]
    fn test_stuck_then_density_continues() {
        // ts=[5,5,5,5,5, 8, 12, 16], threshold=3, window_size=10
        // l=5: count=7, surplus=4, stuck → l=6
        // l=6: window=[6,16], count=3=threshold → 継続
        // l=9: count=2 < 3 → 終了 → interval (5, 16), 16-5=11 >= 10 → keep
        let ts = vec![5i64, 5, 5, 5, 5, 8, 12, 16];
        let intervals = compute_dense_intervals(&ts, 10, 3);
        assert_eq!(intervals.len(), 1);
        let (start, end) = intervals[0];
        assert_eq!(start, 5);
        assert_eq!(end, 16);
    }

    #[test]
    fn test_unique_timestamps_unaffected() {
        // 一意なタイムスタンプではスタックケースが発火しない（後退互換）
        let ts: Vec<i64> = (0..10).collect();
        let intervals = compute_dense_intervals(&ts, 3, 3);
        assert!(!intervals.is_empty());
    }
}
