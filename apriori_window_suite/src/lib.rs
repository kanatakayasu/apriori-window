//! apriori_window_suite — Phase 1 / Phase 2 統合ライブラリ
//!
//! Phase 1: バスケット構造付き Apriori 窓移動アルゴリズム
//! Phase 2: 密集区間 × 外部イベント 時間的関係付け

pub mod apriori;
pub mod basket;
pub mod correlator;
pub mod interval;
pub mod io;
pub mod pipeline;
pub mod util;

pub use apriori::{find_dense_itemsets, generate_candidates, prune_candidates};
pub use basket::{basket_ids_to_transaction_ids, compute_item_basket_map};
pub use correlator::{format_itemset, match_all, Event, Frequents, RelationMatch};
pub use interval::{
    compute_dense_intervals, compute_dense_intervals_with_candidates, find_covering_interval,
    insert_and_merge_interval, is_interval_covered,
};
pub use io::{read_events, read_transactions_with_baskets, write_patterns_csv, write_relations_csv};
pub use pipeline::{
    compute_mi, compute_mi_scores, match_sweep_line, mi_prefilter, permutation_test,
    run_pipeline, PipelineConfig, PipelineResult, SignificantRelation,
};
pub use util::{intersect_interval_lists, intersect_sorted_lists, lower_bound, upper_bound};
