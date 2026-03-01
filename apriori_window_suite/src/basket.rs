use std::collections::{HashMap, HashSet};

/// アイテムのバスケット情報マップを一括生成する。
///
/// 返り値:
///   item_basket_map:      item → basket_id リスト（ソート済み・一意）
///   basket_to_transaction: basket_id → transaction_id
///   item_transaction_map:  item → transaction_id リスト（ソート済み・重複なし）
pub fn compute_item_basket_map(
    transactions: &[Vec<Vec<i64>>],
) -> (HashMap<i64, Vec<i64>>, Vec<i64>, HashMap<i64, Vec<i64>>) {
    let mut item_basket_map: HashMap<i64, Vec<i64>> = HashMap::new();
    let mut basket_to_transaction: Vec<i64> = Vec::new();
    let mut item_transaction_map: HashMap<i64, Vec<i64>> = HashMap::new();

    let mut basket_id: i64 = 0;
    for (t_id, baskets) in transactions.iter().enumerate() {
        let mut seen_in_transaction: HashSet<i64> = HashSet::new();
        for basket in baskets.iter() {
            basket_to_transaction.push(t_id as i64);
            let mut seen_in_basket: HashSet<i64> = HashSet::new();
            for &item in basket.iter() {
                if seen_in_basket.insert(item) {
                    item_basket_map.entry(item).or_default().push(basket_id);
                }
                if seen_in_transaction.insert(item) {
                    item_transaction_map
                        .entry(item)
                        .or_default()
                        .push(t_id as i64);
                }
            }
            basket_id += 1;
        }
    }
    (item_basket_map, basket_to_transaction, item_transaction_map)
}

/// basket_id リストを transaction_id リストに変換する（重複を保持）。
///
/// 重複の保持はバスケット粒度の密集計数を実現するための意図的な設計。
pub fn basket_ids_to_transaction_ids(
    basket_ids: &[i64],
    basket_to_transaction: &[i64],
) -> Vec<i64> {
    basket_ids
        .iter()
        .map(|&bid| basket_to_transaction[bid as usize])
        .collect()
}

// ---------------------------------------------------------------------------
// テスト (compute_item_basket_map, basket_ids_to_transaction_ids)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basket_map_single_basket_per_tx() {
        let txns = vec![vec![vec![1i64, 2]], vec![vec![2i64, 3]]];
        let (ibm, b2t, itm) = compute_item_basket_map(&txns);
        assert_eq!(ibm[&1], vec![0]);
        assert_eq!(ibm[&2], vec![0, 1]);
        assert_eq!(ibm[&3], vec![1]);
        assert_eq!(b2t, vec![0, 1]);
        assert_eq!(itm[&1], vec![0]);
        assert_eq!(itm[&2], vec![0, 1]);
        assert_eq!(itm[&3], vec![1]);
    }

    #[test]
    fn test_basket_map_two_baskets_same_tx() {
        // tx0: basket0={1,2}, basket1={3}; tx1: basket2={1,2}, basket3={3}
        let txns = vec![
            vec![vec![1i64, 2], vec![3]],
            vec![vec![1i64, 2], vec![3]],
        ];
        let (ibm, b2t, itm) = compute_item_basket_map(&txns);
        assert_eq!(b2t, vec![0, 0, 1, 1]);
        assert_eq!(ibm[&1], vec![0, 2]); // basket 0 and 2
        assert_eq!(ibm[&3], vec![1, 3]); // basket 1 and 3
        // item_transaction_map は重複なし
        assert_eq!(itm[&1], vec![0, 1]);
        assert_eq!(itm[&3], vec![0, 1]);
    }

    #[test]
    fn test_basket_map_duplicate_item_in_basket() {
        let txns = vec![vec![vec![1i64, 1, 2]]];
        let (ibm, _, _) = compute_item_basket_map(&txns);
        assert_eq!(ibm[&1], vec![0]); // 1回のみ
    }

    #[test]
    fn test_basket_to_tx_no_duplicates() {
        let b2t = vec![0i64, 1, 2];
        assert_eq!(basket_ids_to_transaction_ids(&[0, 1, 2], &b2t), vec![0, 1, 2]);
    }

    #[test]
    fn test_basket_to_tx_with_duplicates() {
        let b2t = vec![0i64, 0, 0, 1];
        assert_eq!(
            basket_ids_to_transaction_ids(&[0, 1, 2, 3], &b2t),
            vec![0, 0, 0, 1]
        );
    }

    #[test]
    fn test_basket_to_tx_empty() {
        let b2t = vec![0i64, 1];
        assert_eq!(basket_ids_to_transaction_ids(&[], &b2t), vec![] as Vec<i64>);
    }
}
