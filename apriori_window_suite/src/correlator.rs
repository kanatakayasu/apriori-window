//! Phase 2: 密集区間 × 外部イベント 時間的関係付け
//!
//! Phase 1 の find_dense_itemsets が返す frequents と
//! JSON 形式のイベントリストを突き合わせ、以下 6 種の時間的関係を列挙する:
//!   DenseFollowsEvent  (DFE) : 密集終了直後にイベント開始
//!   EventFollowsDense  (EFD) : イベント終了直後に密集開始
//!   DenseContainsEvent (DCE) : 密集がイベントを包含
//!   EventContainsDense (ECD) : イベントが密集を包含
//!   DenseOverlapsEvent (DOE) : 密集が先に始まり部分重複
//!   EventOverlapsDense (EOD) : イベントが先に始まり部分重複

use std::collections::HashMap;

use itertools::Itertools;
use rayon::prelude::*;

// ---------------------------------------------------------------------------
// 型定義
// ---------------------------------------------------------------------------

pub type Frequents = HashMap<Vec<i64>, Vec<(i64, i64)>>;

#[derive(Debug, Clone)]
pub struct Event {
    pub event_id: String,
    pub name: String,
    pub start: i64,
    pub end: i64,
}

#[derive(Debug, Clone)]
pub struct RelationMatch {
    pub itemset: Vec<i64>,
    pub dense_start: i64,
    pub dense_end: i64,
    pub event_id: String,
    pub event_name: String,
    pub relation_type: String,
    pub overlap_length: Option<i64>,
}

// ---------------------------------------------------------------------------
// 時間的関係の判定ロジック
// ---------------------------------------------------------------------------

/// Follows(I → J): I が終わった直後に J が始まる。
/// 条件: te_i - epsilon <= ts_j <= te_i + epsilon
#[inline]
fn satisfies_follows(te_i: i64, ts_j: i64, epsilon: i64) -> bool {
    te_i - epsilon <= ts_j && ts_j <= te_i + epsilon
}

/// Contains(I ⊇ J): I が J を包含する。
/// 条件: ts_i <= ts_j  かつ  te_i + epsilon >= te_j
#[inline]
fn satisfies_contains(ts_i: i64, te_i: i64, ts_j: i64, te_j: i64, epsilon: i64) -> bool {
    ts_i <= ts_j && te_i + epsilon >= te_j
}

/// Overlaps(I ⊙ J): I が先に始まり J と部分的に重なる。
/// 条件:
///   ts_i < ts_j                   # I が先
///   te_i - ts_j >= d_0 - epsilon  # 重複長 >= d_0（許容誤差あり）
///   te_i < te_j + epsilon         # 完全包含でない
///
/// 返り値: Some(重複長 te_i - ts_j) または None
#[inline]
fn satisfies_overlaps(
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

// ---------------------------------------------------------------------------
// マッチング（rayon 並列版）
// ---------------------------------------------------------------------------

/// 全密集区間 × 全イベントの総当たりマッチング（rayon 並列化）。
pub fn match_all(
    frequents: &Frequents,
    events: &[Event],
    epsilon: i64,
    d_0: i64,
) -> Vec<RelationMatch> {
    let pairs: Vec<(&Vec<i64>, i64, i64)> = frequents
        .iter()
        .flat_map(|(itemset, intervals)| {
            intervals
                .iter()
                .map(move |&(ts, te)| (itemset, ts, te))
        })
        .collect();

    let results: Vec<Vec<RelationMatch>> = pairs
        .par_iter()
        .map(|(itemset, ts_i, te_i)| {
            let mut local: Vec<RelationMatch> = Vec::new();
            for event in events {
                let ts_j = event.start;
                let te_j = event.end;

                if satisfies_follows(*te_i, ts_j, epsilon) {
                    local.push(RelationMatch {
                        itemset: (*itemset).clone(),
                        dense_start: *ts_i,
                        dense_end: *te_i,
                        event_id: event.event_id.clone(),
                        event_name: event.name.clone(),
                        relation_type: "DenseFollowsEvent".to_string(),
                        overlap_length: None,
                    });
                }
                if satisfies_follows(te_j, *ts_i, epsilon) {
                    local.push(RelationMatch {
                        itemset: (*itemset).clone(),
                        dense_start: *ts_i,
                        dense_end: *te_i,
                        event_id: event.event_id.clone(),
                        event_name: event.name.clone(),
                        relation_type: "EventFollowsDense".to_string(),
                        overlap_length: None,
                    });
                }

                if satisfies_contains(*ts_i, *te_i, ts_j, te_j, epsilon) {
                    local.push(RelationMatch {
                        itemset: (*itemset).clone(),
                        dense_start: *ts_i,
                        dense_end: *te_i,
                        event_id: event.event_id.clone(),
                        event_name: event.name.clone(),
                        relation_type: "DenseContainsEvent".to_string(),
                        overlap_length: None,
                    });
                }
                if satisfies_contains(ts_j, te_j, *ts_i, *te_i, epsilon) {
                    local.push(RelationMatch {
                        itemset: (*itemset).clone(),
                        dense_start: *ts_i,
                        dense_end: *te_i,
                        event_id: event.event_id.clone(),
                        event_name: event.name.clone(),
                        relation_type: "EventContainsDense".to_string(),
                        overlap_length: None,
                    });
                }

                if let Some(ovl) = satisfies_overlaps(*ts_i, *te_i, ts_j, te_j, epsilon, d_0) {
                    local.push(RelationMatch {
                        itemset: (*itemset).clone(),
                        dense_start: *ts_i,
                        dense_end: *te_i,
                        event_id: event.event_id.clone(),
                        event_name: event.name.clone(),
                        relation_type: "DenseOverlapsEvent".to_string(),
                        overlap_length: Some(ovl),
                    });
                }
                if let Some(ovl) = satisfies_overlaps(ts_j, te_j, *ts_i, *te_i, epsilon, d_0) {
                    local.push(RelationMatch {
                        itemset: (*itemset).clone(),
                        dense_start: *ts_i,
                        dense_end: *te_i,
                        event_id: event.event_id.clone(),
                        event_name: event.name.clone(),
                        relation_type: "EventOverlapsDense".to_string(),
                        overlap_length: Some(ovl),
                    });
                }
            }
            local
        })
        .collect();

    let mut all: Vec<RelationMatch> = results.into_iter().flatten().collect();
    all.sort_by(|a, b| {
        b.itemset
            .len()
            .cmp(&a.itemset.len())
            .then_with(|| a.dense_start.cmp(&b.dense_start))
            .then_with(|| a.event_id.cmp(&b.event_id))
            .then_with(|| a.relation_type.cmp(&b.relation_type))
    });
    all
}

// ---------------------------------------------------------------------------
// フォーマット
// ---------------------------------------------------------------------------

pub fn format_itemset(itemset: &[i64]) -> String {
    let body = itemset.iter().map(|i| i.to_string()).join(", ");
    format!("[{{{}}}]", body)
}

// ---------------------------------------------------------------------------
// テスト (TC-U1, TC-U2, TC-U3, TC-M)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    // -----------------------------------------------------------------------
    // TC-U1: satisfies_follows
    // -----------------------------------------------------------------------

    #[test]
    fn test_follows_adjacent() {
        assert!(satisfies_follows(5, 6, 1));
    }

    #[test]
    fn test_follows_gap_within_epsilon() {
        assert!(satisfies_follows(5, 7, 2));
    }

    #[test]
    fn test_follows_gap_exceeds_epsilon() {
        assert!(!satisfies_follows(5, 8, 2));
    }

    #[test]
    fn test_follows_slight_overlap_within_epsilon() {
        assert!(satisfies_follows(5, 4, 2));
    }

    #[test]
    fn test_follows_overlap_exceeds_epsilon() {
        assert!(!satisfies_follows(5, 2, 2));
    }

    #[test]
    fn test_follows_epsilon_zero_strict() {
        assert!(satisfies_follows(5, 5, 0));
        assert!(!satisfies_follows(5, 6, 0));
    }

    // -----------------------------------------------------------------------
    // TC-U2: satisfies_contains
    // -----------------------------------------------------------------------

    #[test]
    fn test_contains_full() {
        assert!(satisfies_contains(0, 10, 2, 8, 0));
    }

    #[test]
    fn test_contains_right_edge_exact() {
        assert!(satisfies_contains(0, 8, 2, 8, 0));
    }

    #[test]
    fn test_contains_right_edge_within_epsilon() {
        assert!(satisfies_contains(0, 7, 2, 8, 1));
    }

    #[test]
    fn test_contains_right_edge_exceeds_epsilon() {
        assert!(!satisfies_contains(0, 6, 2, 8, 1));
    }

    #[test]
    fn test_contains_j_starts_before_i() {
        assert!(!satisfies_contains(2, 10, 0, 8, 0));
    }

    #[test]
    fn test_contains_ts_equal() {
        assert!(satisfies_contains(2, 10, 2, 8, 0));
    }

    // -----------------------------------------------------------------------
    // TC-U3: satisfies_overlaps
    // -----------------------------------------------------------------------

    #[test]
    fn test_overlaps_normal() {
        assert_eq!(satisfies_overlaps(0, 5, 3, 10, 0, 1), Some(2));
    }

    #[test]
    fn test_overlaps_exactly_d0() {
        assert_eq!(satisfies_overlaps(0, 4, 3, 10, 0, 1), Some(1));
    }

    #[test]
    fn test_overlaps_below_d0() {
        assert_eq!(satisfies_overlaps(0, 3, 3, 10, 0, 2), None);
    }

    #[test]
    fn test_overlaps_epsilon_rescues_short_overlap() {
        assert_eq!(satisfies_overlaps(0, 3, 3, 10, 1, 2), None);
        assert_eq!(satisfies_overlaps(0, 4, 3, 10, 1, 2), Some(1));
    }

    #[test]
    fn test_overlaps_i_does_not_start_first() {
        assert_eq!(satisfies_overlaps(3, 8, 3, 10, 0, 1), None);
    }

    #[test]
    fn test_overlaps_complete_containment_not_overlap() {
        assert_eq!(satisfies_overlaps(0, 15, 3, 10, 0, 1), None);
    }

    #[test]
    fn test_overlaps_contains_boundary_with_epsilon() {
        assert!(satisfies_overlaps(0, 10, 3, 10, 1, 1).is_some());
    }

    // -----------------------------------------------------------------------
    // TC-M: match_all
    // -----------------------------------------------------------------------

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

    #[test]
    fn test_match_dense_follows_event() {
        let freq = make_frequents(vec![1, 2], vec![(0, 5)]);
        let events = vec![make_event("E1", 6, 10)];
        let results = match_all(&freq, &events, 2, 1);
        let types: Vec<&str> = results.iter().map(|r| r.relation_type.as_str()).collect();
        assert!(types.contains(&"DenseFollowsEvent"), "DFE expected, got: {types:?}");
    }

    #[test]
    fn test_match_event_follows_dense() {
        let freq = make_frequents(vec![1, 2], vec![(5, 10)]);
        let events = vec![make_event("E1", 0, 4)];
        let results = match_all(&freq, &events, 2, 1);
        let types: Vec<&str> = results.iter().map(|r| r.relation_type.as_str()).collect();
        assert!(types.contains(&"EventFollowsDense"), "EFD expected, got: {types:?}");
    }

    #[test]
    fn test_match_dense_contains_event() {
        let freq = make_frequents(vec![1, 2], vec![(0, 20)]);
        let events = vec![make_event("E1", 5, 10)];
        let results = match_all(&freq, &events, 0, 1);
        let types: Vec<&str> = results.iter().map(|r| r.relation_type.as_str()).collect();
        assert!(types.contains(&"DenseContainsEvent"), "DCE expected, got: {types:?}");
    }

    #[test]
    fn test_match_event_contains_dense() {
        let freq = make_frequents(vec![1, 2], vec![(5, 10)]);
        let events = vec![make_event("E1", 0, 20)];
        let results = match_all(&freq, &events, 0, 1);
        let types: Vec<&str> = results.iter().map(|r| r.relation_type.as_str()).collect();
        assert!(types.contains(&"EventContainsDense"), "ECD expected, got: {types:?}");
    }

    #[test]
    fn test_match_dense_overlaps_event() {
        let freq = make_frequents(vec![1, 2], vec![(0, 5)]);
        let events = vec![make_event("E1", 3, 10)];
        let results = match_all(&freq, &events, 0, 1);
        let types: Vec<&str> = results.iter().map(|r| r.relation_type.as_str()).collect();
        assert!(types.contains(&"DenseOverlapsEvent"), "DOE expected, got: {types:?}");
    }

    #[test]
    fn test_match_event_overlaps_dense() {
        let freq = make_frequents(vec![1, 2], vec![(5, 10)]);
        let events = vec![make_event("E1", 3, 7)];
        let results = match_all(&freq, &events, 0, 1);
        let types: Vec<&str> = results.iter().map(|r| r.relation_type.as_str()).collect();
        assert!(types.contains(&"EventOverlapsDense"), "EOD expected, got: {types:?}");
    }

    #[test]
    fn test_match_no_relation() {
        let freq = make_frequents(vec![1, 2], vec![(0, 3)]);
        let events = vec![make_event("E1", 100, 200)];
        let results = match_all(&freq, &events, 0, 1);
        assert!(results.is_empty(), "no relation expected, got: {results:?}");
    }

    #[test]
    fn test_match_overlap_length_none_for_non_overlaps() {
        let freq = make_frequents(vec![1, 2], vec![(0, 5)]);
        let events = vec![make_event("E1", 6, 10)];
        let results = match_all(&freq, &events, 2, 1);
        for r in &results {
            if r.relation_type != "DenseOverlapsEvent" && r.relation_type != "EventOverlapsDense" {
                assert!(
                    r.overlap_length.is_none(),
                    "overlap_length should be None for {}",
                    r.relation_type
                );
            }
        }
    }

    #[test]
    fn test_match_sort_order() {
        let mut freq = HashMap::new();
        freq.insert(vec![1i64, 2, 3], vec![(0i64, 10i64)]);
        freq.insert(vec![1i64, 2], vec![(0i64, 10i64)]);
        let events = vec![make_event("A", 0, 20)];
        let results = match_all(&freq, &events, 0, 1);
        if results.len() >= 2 {
            assert!(results[0].itemset.len() >= results[1].itemset.len());
        }
    }
}
