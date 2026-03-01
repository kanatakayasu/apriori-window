/// 昇順リストの積集合を二ポインタで求める。
pub fn intersect_sorted_lists(lists: &[&Vec<i64>]) -> Vec<i64> {
    if lists.is_empty() {
        return Vec::new();
    }
    let mut result = lists[0].clone();
    for current in lists.iter().skip(1) {
        let mut merged = Vec::new();
        let mut i = 0;
        let mut j = 0;
        while i < result.len() && j < current.len() {
            if result[i] == current[j] {
                merged.push(result[i]);
                i += 1;
                j += 1;
            } else if result[i] < current[j] {
                i += 1;
            } else {
                j += 1;
            }
        }
        result = merged;
        if result.is_empty() {
            break;
        }
    }
    result
}

/// 複数の区間リストの積集合を求める。
pub fn intersect_interval_lists(intervals_list: &[Vec<(i64, i64)>]) -> Vec<(i64, i64)> {
    if intervals_list.is_empty() {
        return Vec::new();
    }
    let mut result = intervals_list[0].clone();
    for other in intervals_list.iter().skip(1) {
        let mut merged: Vec<(i64, i64)> = Vec::new();
        let mut i = 0;
        let mut j = 0;
        while i < result.len() && j < other.len() {
            let (a_start, a_end) = result[i];
            let (b_start, b_end) = other[j];
            let s = a_start.max(b_start);
            let e = a_end.min(b_end);
            if s <= e {
                merged.push((s, e));
            }
            if a_end < b_end {
                i += 1;
            } else {
                j += 1;
            }
        }
        result = merged;
        if result.is_empty() {
            break;
        }
    }
    result
}

/// slice 内で value 以上の最小インデックスを返す（lower_bound）。
pub fn lower_bound(slice: &[i64], value: i64) -> usize {
    let mut left = 0;
    let mut right = slice.len();
    while left < right {
        let mid = (left + right) / 2;
        if slice[mid] < value {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    left
}

/// slice 内で value を超える最小インデックスを返す（upper_bound）。
pub fn upper_bound(slice: &[i64], value: i64) -> usize {
    let mut left = 0;
    let mut right = slice.len();
    while left < right {
        let mid = (left + right) / 2;
        if slice[mid] <= value {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    left
}
