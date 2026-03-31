//! apriori_window_suite — Phase 1 ライブラリ
//!
//! Phase 1: Apriori + スライディングウィンドウによる密集アイテムセット区間検出
//! Phase 2 (Event Attribution): Python プロトタイプで実装中

pub mod apriori;
pub mod basket;
pub mod interval;
pub mod io;
pub mod st_correlator;
pub mod util;

pub use apriori::{find_dense_itemsets, generate_candidates, prune_candidates};
pub use basket::{basket_ids_to_transaction_ids, compute_item_basket_map};
pub use interval::{
    compute_dense_intervals, compute_dense_intervals_with_candidates, find_covering_interval,
    insert_and_merge_interval, is_interval_covered,
};
pub use io::{read_events, read_transactions_with_baskets, write_patterns_csv, Event};
pub use util::{intersect_interval_lists, intersect_sorted_lists, lower_bound, upper_bound};
