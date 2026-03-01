//! new_apriori_window — バスケット構造なしの Apriori 窓移動アルゴリズム
//!
//! 設計書: doc/requirements.md
//! 正当性証明: doc/proof.md

pub mod apriori;
pub mod interval;
pub mod io;
pub mod util;

pub use apriori::{
    compute_item_timestamps_map, find_dense_itemsets, generate_candidates, prune_candidates,
};
pub use interval::{
    compute_dense_intervals, compute_dense_intervals_with_candidates, find_covering_interval,
    insert_and_merge_interval, is_interval_covered,
};
pub use io::{read_text_file_as_2d_vec_of_integers, write_output_csv};
pub use util::{intersect_interval_lists, intersect_sorted_lists, lower_bound, upper_bound};
