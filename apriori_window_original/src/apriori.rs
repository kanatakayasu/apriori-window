use std::collections::{HashMap, HashSet};

use itertools::Itertools;
use rayon::prelude::*;

use crate::interval::{compute_dense_intervals, compute_dense_intervals_with_candidates};
use crate::util::{intersect_interval_lists, intersect_sorted_lists};

pub fn compute_item_timestamps_map(transactions: &[Vec<i64>]) -> HashMap<i64, Vec<i64>> {
    let mut item_map: HashMap<i64, Vec<i64>> = HashMap::new();
    for (idx, transaction) in transactions.iter().enumerate() {
        let mut seen: HashSet<i64> = HashSet::new();
        for item in transaction.iter() {
            if seen.insert(*item) {
                item_map.entry(*item).or_default().push(idx as i64);
            }
        }
    }
    item_map
}

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

    candidates.into_iter().collect()
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

pub fn find_dense_itemsets(
    transactions: &[Vec<i64>],
    window_size: i64,
    threshold: usize,
    max_length: usize,
) -> HashMap<Vec<i64>, Vec<(i64, i64)>> {
    let item_timestamps = compute_item_timestamps_map(transactions);
    let mut frequents: HashMap<Vec<i64>, Vec<(i64, i64)>> = HashMap::new();
    let data_length = transactions.len() as i64;

    let mut current_level: Vec<Vec<i64>> = Vec::new();
    let mut singleton_intervals: HashMap<i64, Vec<(i64, i64)>> = HashMap::new();

    let mut items: Vec<i64> = item_timestamps.keys().cloned().collect();
    items.sort();

    let initial_results: Vec<(i64, Vec<(i64, i64)>, Vec<(i64, i64)>)> = items
        .par_iter()
        .map(|item| {
            let timestamps = item_timestamps.get(item).expect("item not found");
            if timestamps.is_empty() {
                return (*item, Vec::new(), Vec::new());
            }
            let full_range = vec![(timestamps[0], *timestamps.last().unwrap())];
            let intervals = compute_dense_intervals_with_candidates(
                timestamps,
                window_size,
                threshold,
                &full_range,
                data_length,
            );
            let singleton = compute_dense_intervals(timestamps, window_size, threshold, data_length);
            (*item, intervals, singleton)
        })
        .collect();

    for (item, intervals, singleton) in initial_results {
        if !singleton.is_empty() || item_timestamps.contains_key(&item) {
            singleton_intervals.insert(item, singleton);
        }
        if !intervals.is_empty() {
            let key = vec![item];
            frequents.insert(key.clone(), intervals);
            current_level.push(key);
        }
    }

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
                    .map(|item| {
                        singleton_intervals
                            .get(item)
                            .cloned()
                            .unwrap_or_default()
                    })
                    .collect();
                let mut allowed_ranges = intersect_interval_lists(&allowed_sources);
                allowed_ranges.retain(|(s, e)| *e - *s >= window_size);
                if allowed_ranges.is_empty() {
                    return (candidate.clone(), Vec::new());
                }

                let lists: Vec<&Vec<i64>> = candidate
                    .iter()
                    .map(|item| item_timestamps.get(item).expect("item not found"))
                    .collect();
                let timestamps = intersect_sorted_lists(&lists);
                if timestamps.is_empty() {
                    return (candidate.clone(), Vec::new());
                }
                let intervals = compute_dense_intervals_with_candidates(
                    &timestamps,
                    window_size,
                    threshold,
                    &allowed_ranges,
                    data_length,
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
