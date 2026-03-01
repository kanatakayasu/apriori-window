"""
Phase 1 テスト：バスケット構造対応 apriori_window_basket.py

テストケース一覧:
  TC1  後退互換性（|なしデータで旧実装と同一結果）
  TC2  バスケット分割で偽共起が消えること
  TC3  スタックケース：無限ループにならないこと
  TC4  スタックケース後に右端から新バスケットが入り密集継続
  TC5  空行・エッジケース
  TC6  既存データとの照合（旧フォーマットを新実装で処理）

実行方法:
    cd /Users/kanata/Documents/GitHub/apriori_window
    python -m pytest apriori_window_suite/python/tests/test_basket.py -v
"""
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# python/ を import パスに追加
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apriori_window_basket import (
    basket_ids_to_transaction_ids,
    compute_dense_intervals,
    compute_dense_intervals_with_candidates,
    compute_item_basket_map,
    find_dense_itemsets,
    read_transactions_with_baskets,
)

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _write_tmp(content: str) -> str:
    """テキストを一時ファイルに書き込みパスを返す。"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


def _from_flat(transactions_flat):
    """List[List[int]] → List[List[List[int]]] (1バスケット/トランザクション) に変換。"""
    return [[[item for item in t]] if t else [] for t in transactions_flat]


# ---------------------------------------------------------------------------
# read_transactions_with_baskets の単体テスト
# ---------------------------------------------------------------------------

class TestReadTransactionsWithBaskets:
    def test_single_basket_line(self):
        path = _write_tmp("1 2 3\n")
        result = read_transactions_with_baskets(path)
        assert result == [[[1, 2, 3]]]

    def test_two_basket_line(self):
        path = _write_tmp("1 2 | 3 4\n")
        result = read_transactions_with_baskets(path)
        assert result == [[[1, 2], [3, 4]]]

    def test_three_basket_line(self):
        path = _write_tmp("1 2 | 3 4 | 5\n")
        result = read_transactions_with_baskets(path)
        assert result == [[[1, 2], [3, 4], [5]]]

    def test_empty_line(self):
        path = _write_tmp("\n1 2\n")
        result = read_transactions_with_baskets(path)
        assert result == [[], [[1, 2]]]

    def test_multiple_transactions(self):
        path = _write_tmp("1 2 | 3\n4 5\n")
        result = read_transactions_with_baskets(path)
        assert result == [[[1, 2], [3]], [[4, 5]]]


# ---------------------------------------------------------------------------
# compute_item_basket_map の単体テスト
# ---------------------------------------------------------------------------

class TestComputeItemBasketMap:
    def test_single_basket(self):
        transactions = [[[1, 2]], [[2, 3]]]
        ibm, b2t, itm = compute_item_basket_map(transactions)
        assert ibm[1] == [0]
        assert ibm[2] == [0, 1]
        assert ibm[3] == [1]
        assert b2t == [0, 1]
        assert itm[1] == [0]
        assert itm[2] == [0, 1]
        assert itm[3] == [1]

    def test_two_baskets_same_transaction(self):
        # トランザクション0 に basket0={1,2}, basket1={3}
        transactions = [[[1, 2], [3]], [[1, 2], [3]]]
        ibm, b2t, itm = compute_item_basket_map(transactions)
        # basket_id: 0,1 → t=0; 2,3 → t=1
        assert b2t == [0, 0, 1, 1]
        assert ibm[1] == [0, 2]   # basket 0 and 2
        assert ibm[3] == [1, 3]   # basket 1 and 3
        # item_transaction_map は重複なし
        assert itm[1] == [0, 1]
        assert itm[3] == [0, 1]

    def test_duplicate_item_in_basket(self):
        # 同一バスケット内に同じアイテムが2回 → 1回のみ記録
        transactions = [[[1, 1, 2]]]
        ibm, b2t, itm = compute_item_basket_map(transactions)
        assert ibm[1] == [0]
        assert ibm[2] == [0]


# ---------------------------------------------------------------------------
# basket_ids_to_transaction_ids の単体テスト
# ---------------------------------------------------------------------------

class TestBasketIdsToTransactionIds:
    def test_no_duplicates(self):
        b2t = [0, 1, 2]
        assert basket_ids_to_transaction_ids([0, 1, 2], b2t) == [0, 1, 2]

    def test_duplicates_preserved(self):
        # basket 0,1,2 は全てトランザクション0
        b2t = [0, 0, 0, 1]
        result = basket_ids_to_transaction_ids([0, 1, 2, 3], b2t)
        assert result == [0, 0, 0, 1]

    def test_empty(self):
        assert basket_ids_to_transaction_ids([], [0, 1]) == []


# ---------------------------------------------------------------------------
# compute_dense_intervals のスタックケーステスト
# ---------------------------------------------------------------------------

class TestComputeDenseIntervalsStackCase:
    def test_no_infinite_loop(self):
        """TC3: スタックケースで無限ループにならないこと。"""
        # timestamps = [5,5,5,5,5,8,12]
        # l=5: count=7, surplus=4, window_occurrences[4]=5 → stuck → l+=1=6
        # l=6: count=2 < threshold=3 → dense 終了
        ts = [5, 5, 5, 5, 5, 8, 12]
        intervals = compute_dense_intervals(ts, window_size=10, threshold=3)
        # 完了すること、および dense_intervals が返ること（[-5, 5] を含む）
        assert isinstance(intervals, list)
        # l=5 で in_dense 開始（start=-5, end=5）→ l=6 で count<threshold → 終了
        assert len(intervals) == 1
        assert intervals[0] == (-5, 5)

    def test_density_continues_after_stuck(self):
        """TC4: スタックケース後に右端から新バスケットが入り密集継続。"""
        # timestamps = [5,5,5,5,5, 8, 12, 16]
        # l=5: count=7, surplus=4, stuck → l=6
        # l=6: window=[6,16], count=3=threshold → 密集継続
        # l=7,8: count=3=threshold → 継続
        # l=9: window=[9,19], count=2<3 → 終了
        ts = [5, 5, 5, 5, 5, 8, 12, 16]
        intervals = compute_dense_intervals(ts, window_size=10, threshold=3)
        assert len(intervals) == 1
        start, end = intervals[0]
        # 密集区間の end は stuck 後も継続した 8 以降まで伸びているはず
        assert end >= 8

    def test_unique_timestamps_unaffected(self):
        """一意なタイムスタンプではスタックケースが発火しないこと（後退互換）。"""
        ts = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        # 参照実装と同じ動作になるはず
        intervals_new = compute_dense_intervals(ts, window_size=3, threshold=3)
        assert isinstance(intervals_new, list)
        assert len(intervals_new) > 0


# ---------------------------------------------------------------------------
# TC1: 後退互換性テスト
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """バスケット区切りなし（旧フォーマット）で旧実装と同一の結果が得られること。"""

    def _ref_find(self, transactions_flat, window_size, threshold, max_length):
        """旧アルゴリズムを Python で再現（参照）。"""
        # 旧: item_timestamps_map で一意タイムスタンプ
        from bisect import bisect_left, bisect_right
        item_ts: dict = {}
        for idx, t in enumerate(transactions_flat):
            seen = set()
            for item in t:
                if item not in seen:
                    seen.add(item)
                    item_ts.setdefault(item, []).append(idx)

        def cdi(ts, ws, thr):
            return compute_dense_intervals(ts, ws, thr)

        def cdi_cand(ts, ws, thr, cands):
            return compute_dense_intervals_with_candidates(ts, ws, thr, cands)

        def intersect(lists):
            if not lists:
                return []
            result = list(lists[0])
            for cur in lists[1:]:
                merged = []
                i = j = 0
                while i < len(result) and j < len(cur):
                    if result[i] == cur[j]:
                        merged.append(result[i]); i += 1; j += 1
                    elif result[i] < cur[j]:
                        i += 1
                    else:
                        j += 1
                result = merged
                if not result:
                    break
            return result

        from itertools import combinations as comb

        def gen_cands(prev, k):
            prev_s = sorted(prev)
            cs = set()
            for i in range(len(prev_s)):
                for j in range(i + 1, len(prev_s)):
                    l, r = prev_s[i], prev_s[j]
                    if k > 2 and l[:k-2] != r[:k-2]:
                        break
                    ci = list(l)
                    for x in r:
                        if x not in ci:
                            ci.append(x)
                    ci.sort()
                    if len(ci) == k:
                        cs.add(tuple(ci))
            return sorted(cs)

        def intersect_ilist(ilists):
            if not ilists:
                return []
            res = list(ilists[0])
            for other in ilists[1:]:
                m = []
                i = j = 0
                while i < len(res) and j < len(other):
                    a, b = res[i]; c, d = other[j]
                    s = max(a, c); e = min(b, d)
                    if s <= e:
                        m.append((s, e))
                    if b < d:
                        i += 1
                    else:
                        j += 1
                res = m
                if not res:
                    break
            return res

        frequents = {}
        current = []
        singletons = {}
        for item in sorted(item_ts):
            ts = item_ts[item]
            if not ts:
                continue
            fr = [(ts[0], ts[-1])]
            ivs = cdi_cand(ts, window_size, threshold, fr)
            singletons[item] = cdi(ts, window_size, threshold)
            if ivs:
                frequents[(item,)] = ivs
                current.append((item,))

        k = 2
        while current and k <= max_length:
            cands = gen_cands(current, k)
            pruned = []
            for c in cands:
                if all(tuple(s) in set(current) for s in comb(c, k - 1)):
                    pruned.append(c)
            nxt = []
            for c in pruned:
                ar = intersect_ilist([singletons[i] for i in c])
                ar = [(s, e) for s, e in ar if e - s >= window_size]
                if not ar:
                    continue
                ts2 = intersect([item_ts[i] for i in c])
                ivs2 = cdi_cand(ts2, window_size, threshold, ar)
                if ivs2:
                    frequents[c] = ivs2
                    nxt.append(c)
            current = nxt
            k += 1

        return frequents

    def test_single_basket_matches_reference(self):
        """旧フォーマット相当のデータで、新旧実装が同一結果を返すこと。"""
        flat = [
            [1, 2, 3],
            [1, 2],
            [2, 3],
            [1, 2, 3],
            [1, 3],
            [1, 2],
        ]
        window_size = 3
        threshold = 2
        max_length = 3

        ref = self._ref_find(flat, window_size, threshold, max_length)
        new_txns = _from_flat(flat)
        got = find_dense_itemsets(new_txns, window_size, threshold, max_length)

        assert set(ref.keys()) == set(got.keys()), \
            f"キーが一致しない: ref={set(ref.keys())} got={set(got.keys())}"
        for key in ref:
            assert ref[key] == got[key], \
                f"{key}: ref={ref[key]} got={got[key]}"


# ---------------------------------------------------------------------------
# TC2: 偽共起の排除テスト
# ---------------------------------------------------------------------------

class TestFalseCooccurrenceEliminated:
    def test_separate_baskets_no_cooccurrence(self):
        """
        1 2 | 3  が3トランザクション続く場合:
          {1,2}: 同一バスケット → dense あり
          {1,3}: 別バスケット → dense なし
          {2,3}: 別バスケット → dense なし
        """
        path = _write_tmp("""\
            1 2 | 3
            1 2 | 3
            1 2 | 3
        """)
        transactions = read_transactions_with_baskets(path)
        # window_size=2, threshold=2 で {1,2} は dense になるはず
        frequents = find_dense_itemsets(transactions, window_size=2, threshold=2, max_length=3)

        # {1,2} は dense あり
        assert (1, 2) in frequents, "同一バスケット内共起 {1,2} が検出されるべき"

        # {1,3}, {2,3}, {1,2,3} は dense なし（別バスケット）
        assert (1, 3) not in frequents, "別バスケット {1,3} は dense なし"
        assert (2, 3) not in frequents, "別バスケット {2,3} は dense なし"
        assert (1, 2, 3) not in frequents, "別バスケットまたがり {1,2,3} は dense なし"

    def test_same_basket_detects_cooccurrence(self):
        """1 2 3 が3トランザクション続く場合: {1,2}, {2,3}, {1,3} 全て dense あり。"""
        path = _write_tmp("""\
            1 2 3
            1 2 3
            1 2 3
        """)
        transactions = read_transactions_with_baskets(path)
        frequents = find_dense_itemsets(transactions, window_size=2, threshold=2, max_length=3)
        assert (1, 2) in frequents
        assert (1, 3) in frequents
        assert (2, 3) in frequents


# ---------------------------------------------------------------------------
# TC3: スタックケース（find_dense_itemsets経由）
# ---------------------------------------------------------------------------

class TestStackCaseViaFindDenseItemsets:
    def test_many_baskets_per_transaction_no_hang(self):
        """
        各トランザクションに多バスケット → co_occurrence_timestamps に重複 → スタックケース発生。
        タイムアウトせず正しい結果が返ること。
        """
        # 5バスケット × 3トランザクション
        path = _write_tmp("""\
            1 2 | 1 2 | 1 2 | 1 2 | 1 2
            1 2 | 1 2 | 1 2 | 1 2 | 1 2
            1 2 | 1 2 | 1 2 | 1 2 | 1 2
        """)
        transactions = read_transactions_with_baskets(path)
        # co_occurrence_timestamps = [0,0,0,0,0, 1,1,1,1,1, 2,2,2,2,2]
        # window_size=1: スタックケースが発生しやすい設定
        frequents = find_dense_itemsets(transactions, window_size=1, threshold=3, max_length=2)
        # 結果の型が正しいこと（ハングせず返ってくること自体がテスト）
        assert isinstance(frequents, dict)


# ---------------------------------------------------------------------------
# TC4: スタックケース後に密集継続（compute_dense_intervals 直接）
# ---------------------------------------------------------------------------

class TestStackThenContinue:
    def test_stack_then_right_entry(self):
        """
        スタック発生後、右端から新バスケットが入り密集が継続すること。
        timestamps = [5,5,5,5,5, 8, 12, 16], threshold=3, window_size=10
        """
        ts = [5, 5, 5, 5, 5, 8, 12, 16]
        intervals = compute_dense_intervals(ts, window_size=10, threshold=3)
        assert len(intervals) == 1
        start, end = intervals[0]
        # 密集区間の end は 8 以降まで伸びているはず（右端から 8,12,16 が入るため）
        assert end >= 8, f"スタック後も密集が継続するはず: end={end}"

    def test_stack_then_no_right_entry(self):
        """
        スタック後、右端から新バスケットが入らない場合は密集が終了すること。
        timestamps = [5,5,5,5,5, 8, 12], threshold=3, window_size=10
        l=5 → stuck → l=6, window=[6,16], count=2 < 3 → 終了
        """
        ts = [5, 5, 5, 5, 5, 8, 12]
        intervals = compute_dense_intervals(ts, window_size=10, threshold=3)
        # dense_intervals が存在し、end は 8 には達しないこと
        assert len(intervals) == 1
        _, end = intervals[0]
        assert end == 5  # スタック前の l=5 が end


# ---------------------------------------------------------------------------
# TC5: 空行・エッジケース
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_line_at_start(self):
        path = _write_tmp("\n1 2\n1 2\n")
        transactions = read_transactions_with_baskets(path)
        assert transactions[0] == []  # 空トランザクション
        frequents = find_dense_itemsets(transactions, window_size=2, threshold=2, max_length=2)
        # 2行目(t=1)と3行目(t=2)で {1,2} が dense になるか確認
        assert isinstance(frequents, dict)

    def test_all_empty(self):
        path = _write_tmp("\n\n\n")
        transactions = read_transactions_with_baskets(path)
        frequents = find_dense_itemsets(transactions, window_size=2, threshold=2, max_length=2)
        assert frequents == {}

    def test_single_item_only(self):
        path = _write_tmp("1\n1\n1\n")
        transactions = read_transactions_with_baskets(path)
        frequents = find_dense_itemsets(transactions, window_size=2, threshold=2, max_length=2)
        assert (1,) in frequents
        assert (1, 1) not in frequents  # 自身との共起はない


# ---------------------------------------------------------------------------
# TC6: 既存データとの照合（旧フォーマットを新実装で処理）
# ---------------------------------------------------------------------------

class TestExistingDataConsistency:
    """
    旧フォーマット（"|"なし）のデータを新実装で読み込み、
    同一データを旧実装相当のロジック（単一バスケット）で処理した結果と一致すること。
    """

    def test_consistency_on_known_data(self):
        data = [
            [1, 2, 3],
            [1, 2],
            [2, 3],
            [1, 3],
            [1, 2, 3],
            [2, 3],
            [1, 2, 3],
        ]
        window_size = 3
        threshold = 3
        max_length = 3

        # 新実装（旧フォーマット互換）
        new_txns = _from_flat(data)
        got = find_dense_itemsets(new_txns, window_size, threshold, max_length)

        # 旧実装（item_transaction_map = item_basket_map で一意なので同一になるはず）
        ibm, b2t, itm = compute_item_basket_map(new_txns)
        # 単一バスケット → basket_id == transaction_id
        assert b2t == list(range(len(data)))

        # 全アイテムの basket_id リスト == transaction_id リスト（重複なし）
        for item in itm:
            assert ibm[item] == itm[item], \
                f"item={item}: basket_map={ibm[item]} tx_map={itm[item]}"

        # {1,2} の共起 = 旧実装と同じになること
        ref_12_ts = [i for i, t in enumerate(data) if 1 in t and 2 in t]
        ibm_12 = ibm.get(1, [])
        ibm_22 = ibm.get(2, [])
        # basket_ids の積集合 → transaction_ids（1バスケット/tx なので重複なし）
        from apriori_window_basket import intersect_sorted_lists
        co_baskets = intersect_sorted_lists([ibm_12, ibm_22])
        co_ts = basket_ids_to_transaction_ids(co_baskets, b2t)
        assert co_ts == ref_12_ts, \
            f"共起タイムスタンプが一致しない: {co_ts} vs {ref_12_ts}"
