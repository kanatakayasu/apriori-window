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
        if let Some((last_s, last_e)) = merged.last_mut() {
            if s <= *last_e + 1 {
                *last_e = (*last_e).max(e);
                *last_s = (*last_s).min(s);
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
// 密集区間計算
// ---------------------------------------------------------------------------

pub fn compute_dense_intervals(
    timestamps: &[i64],
    window_size: i64,
    threshold: usize,
    _data_length: i64,
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
    let ts_last = *ts.last().expect("timestamps should not be empty");

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

        let surplus = count - threshold;
        let window_occurrences = &ts[start_idx..end_idx];
        l = window_occurrences[surplus];
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

pub fn compute_dense_intervals_with_candidates(
    timestamps: &[i64],
    window_size: i64,
    threshold: usize,
    candidate_ranges: &[(i64, i64)],
    _data_length: i64,
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
    let ts_last = *ts.last().expect("timestamps should not be empty");
    let mut recorded: Vec<(i64, i64)> = Vec::new();

    let mut sorted_candidates = candidate_ranges.to_vec();
    sorted_candidates.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| a.1.cmp(&b.1)));

    for (c_start, c_end) in sorted_candidates.iter().cloned() {
        let mut l = c_start;
        let mut in_dense = false;
        let mut start: Option<i64> = None;
        let mut rightmost: Option<i64> = None;

        if l < c_start {
            l = c_start;
        }

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

            let surplus = count - threshold;
            let window_occurrences = &ts[start_idx..end_idx];
            let candidate_next_l = window_occurrences[surplus];
            if candidate_next_l > c_end {
                break;
            }
            l = candidate_next_l;
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
