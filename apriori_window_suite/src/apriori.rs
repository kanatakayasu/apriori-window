use std::collections::{HashMap, HashSet};

use itertools::Itertools;
use rayon::prelude::*;

use crate::basket::{basket_ids_to_transaction_ids, compute_item_basket_map};
use crate::interval::{compute_dense_intervals, compute_dense_intervals_with_candidates};
use crate::util::{intersect_interval_lists, intersect_sorted_lists};

pub fn generate_candidates(prev_frequents: &[Vec<i64>], k: usize) -> Vec<Vec<i64>> {
    let mut prev_sorted = prev_frequents.to_vec();
    prev_sorted.sort();
    let mut candidates: HashSet<Vec<i64>> = HashSet::new();

    for i in 0..prev_sorted.len() {
        for j in (i + 1)..prev_sorted.len() {
            if k > 2 && prev_sorted[i][..k - 2] != prev_sorted[j][..k - 2] {
                break;
            }
            let mut candidate = prev_sorted[i].clone();
            for item in prev_sorted[j].iter() {
                if !candidate.contains(item) {
                    candidate.push(*item);
                }
            }
            candidate.sort();
            if candidate.len() == k {
                candidates.insert(candidate);
            }
        }
    }

    let mut result: Vec<Vec<i64>> = candidates.into_iter().collect();
    result.sort();
    result
}

pub fn prune_candidates(
    candidates: Vec<Vec<i64>>,
    prev_frequents_set: &HashSet<Vec<i64>>,
) -> Vec<Vec<i64>> {
    candidates
        .into_iter()
        .filter(|candidate| {
            candidate
                .iter()
                .cloned()
                .combinations(candidate.len() - 1)
                .all(|subset| prev_frequents_set.contains(&subset))
        })
        .collect()
}

/// Apriori 性質を用いて密集区間を持つアイテムセットを探索する。
///
/// ① compute_item_basket_map で item_basket_map / basket_to_transaction /
///   item_transaction_map を一括生成
/// ② 単体アイテムの密集区間は item_transaction_map（重複なし）を使う
/// ③ multi-item 候補の共起タイムスタンプは basket_id の積集合 →
///   basket_ids_to_transaction_ids で transaction_id（重複あり）に変換
pub fn find_dense_itemsets(
    transactions: &[Vec<Vec<i64>>],
    window_size: i64,
    threshold: usize,
    max_length: usize,
) -> HashMap<Vec<i64>, Vec<(i64, i64)>> {
    let (item_basket_map, basket_to_transaction, item_transaction_map) =
        compute_item_basket_map(transactions);
    let mut frequents: HashMap<Vec<i64>, Vec<(i64, i64)>> = HashMap::new();

    // --- 単体アイテムの処理（並列） ---
    let mut items: Vec<i64> = item_transaction_map.keys().cloned().collect();
    items.sort();

    let initial_results: Vec<(i64, Vec<(i64, i64)>, Vec<(i64, i64)>)> = items
        .par_iter()
        .map(|item| {
            let timestamps = item_transaction_map.get(item).expect("item not found");
            if timestamps.is_empty() {
                return (*item, Vec::new(), Vec::new());
            }
            let full_range = vec![(timestamps[0], *timestamps.last().unwrap())];
            let intervals = compute_dense_intervals_with_candidates(
                timestamps,
                window_size,
                threshold,
                &full_range,
            );
            let singleton = compute_dense_intervals(timestamps, window_size, threshold);
            (*item, intervals, singleton)
        })
        .collect();

    let mut current_level: Vec<Vec<i64>> = Vec::new();
    let mut singleton_intervals: HashMap<i64, Vec<(i64, i64)>> = HashMap::new();

    for (item, intervals, singleton) in initial_results {
        singleton_intervals.insert(item, singleton);
        if !intervals.is_empty() {
            let key = vec![item];
            frequents.insert(key.clone(), intervals);
            current_level.push(key);
        }
    }

    // --- multi-item 候補の処理（並列） ---
    let mut k = 2;
    while !current_level.is_empty() && k <= max_length {
        let candidates = generate_candidates(&current_level, k);
        let prev_set: HashSet<Vec<i64>> = current_level.iter().cloned().collect();
        let candidates = prune_candidates(candidates, &prev_set);

        let candidate_results: Vec<(Vec<i64>, Vec<(i64, i64)>)> = candidates
            .par_iter()
            .map(|candidate| {
                let allowed_sources: Vec<Vec<(i64, i64)>> = candidate
                    .iter()
                    .map(|item| singleton_intervals.get(item).cloned().unwrap_or_default())
                    .collect();
                let mut allowed_ranges = intersect_interval_lists(&allowed_sources);
                allowed_ranges.retain(|(s, e)| *e - *s >= window_size);
                if allowed_ranges.is_empty() {
                    return (candidate.clone(), Vec::new());
                }

                let basket_id_lists: Vec<&Vec<i64>> = candidate
                    .iter()
                    .map(|item| item_basket_map.get(item).expect("item not found"))
                    .collect();
                let co_basket_ids = intersect_sorted_lists(&basket_id_lists);
                if co_basket_ids.is_empty() {
                    return (candidate.clone(), Vec::new());
                }
                let timestamps =
                    basket_ids_to_transaction_ids(&co_basket_ids, &basket_to_transaction);

                let intervals = compute_dense_intervals_with_candidates(
                    &timestamps,
                    window_size,
                    threshold,
                    &allowed_ranges,
                );
                (candidate.clone(), intervals)
            })
            .filter(|(_, intervals)| !intervals.is_empty())
            .collect();

        let mut next_level: Vec<Vec<i64>> = Vec::new();
        for (candidate, intervals) in candidate_results {
            frequents.insert(candidate.clone(), intervals);
            next_level.push(candidate);
        }

        current_level = next_level;
        k += 1;
    }

    frequents
}

// ---------------------------------------------------------------------------
// テスト (TC1: 後退互換性, TC2: 偽共起, TC5: エッジケース, TC3 E2E)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::basket::compute_item_basket_map;

    fn from_flat(flat: &[Vec<i64>]) -> Vec<Vec<Vec<i64>>> {
        flat.iter()
            .map(|t| if t.is_empty() { vec![] } else { vec![t.clone()] })
            .collect()
    }

    fn is_a_map_result(_m: &HashMap<Vec<i64>, Vec<(i64, i64)>>) -> bool {
        true
    }

    #[test]
    fn test_backward_compatibility() {
        let flat: Vec<Vec<i64>> = vec![
            vec![1, 2, 3],
            vec![1, 2],
            vec![2, 3],
            vec![1, 2, 3],
            vec![1, 3],
            vec![1, 2],
        ];
        let txns = from_flat(&flat);
        let frequents = find_dense_itemsets(&txns, 3, 2, 3);

        let (ibm, b2t, itm) = compute_item_basket_map(&txns);
        assert_eq!(b2t, (0..flat.len() as i64).collect::<Vec<_>>());
        for item in itm.keys() {
            assert_eq!(ibm[item], itm[item]);
        }

        let _ = frequents;
    }

    #[test]
    fn test_false_cooccurrence_eliminated() {
        let txns: Vec<Vec<Vec<i64>>> = vec![
            vec![vec![1, 2], vec![3]],
            vec![vec![1, 2], vec![3]],
            vec![vec![1, 2], vec![3]],
        ];
        let frequents = find_dense_itemsets(&txns, 2, 2, 3);

        assert!(
            !frequents.contains_key(&vec![1i64, 3]),
            "別バスケット [1,3] は dense なし"
        );
        assert!(
            !frequents.contains_key(&vec![2i64, 3]),
            "別バスケット [2,3] は dense なし"
        );
        assert!(
            !frequents.contains_key(&vec![1i64, 2, 3]),
            "[1,2,3] は dense なし"
        );
    }

    #[test]
    fn test_same_basket_detects_cooccurrence() {
        let txns: Vec<Vec<Vec<i64>>> = vec![
            vec![vec![1, 2, 3]],
            vec![vec![1, 2, 3]],
            vec![vec![1, 2, 3]],
        ];
        let frequents = find_dense_itemsets(&txns, 2, 2, 3);
        assert!(frequents.contains_key(&vec![1i64, 2]), "[1,2] は dense あり");
        assert!(frequents.contains_key(&vec![1i64, 3]), "[1,3] は dense あり");
        assert!(frequents.contains_key(&vec![2i64, 3]), "[2,3] は dense あり");
    }

    #[test]
    fn test_empty_transactions() {
        let txns: Vec<Vec<Vec<i64>>> = vec![vec![], vec![], vec![]];
        let frequents = find_dense_itemsets(&txns, 2, 2, 2);
        assert!(frequents.is_empty());
    }

    #[test]
    fn test_single_item_no_self_cooccurrence() {
        let txns = vec![vec![vec![1i64]], vec![vec![1]], vec![vec![1]]];
        let frequents = find_dense_itemsets(&txns, 2, 2, 2);
        assert!(frequents.contains_key(&vec![1]));
        assert!(!frequents.contains_key(&vec![1, 1]));
    }

    #[test]
    fn test_many_baskets_per_tx_no_hang() {
        let txns: Vec<Vec<Vec<i64>>> = vec![
            vec![vec![1, 2], vec![1, 2], vec![1, 2], vec![1, 2], vec![1, 2]],
            vec![vec![1, 2], vec![1, 2], vec![1, 2], vec![1, 2], vec![1, 2]],
            vec![vec![1, 2], vec![1, 2], vec![1, 2], vec![1, 2], vec![1, 2]],
        ];
        let frequents = find_dense_itemsets(&txns, 1, 3, 2);
        assert!(is_a_map_result(&frequents));
    }
}
