"""
Tests for High-Utility Dense Interval Mining.

Covers:
  - Utility computation (item, itemset, TWU)
  - Window utility / TWU queries
  - Prefix sum correctness
  - Synthetic data generation
  - End-to-end mining with known patterns
  - TWU pruning effectiveness
  - Edge cases
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
from high_utility_dense_intervals import (
    UtilityTransaction,
    build_item_transaction_map,
    build_transaction_index,
    compute_item_utility,
    compute_itemset_utility,
    compute_prefix_twu,
    compute_prefix_utility,
    compute_twu,
    compute_window_twu,
    compute_window_utility,
    find_utility_dense_intervals,
    generate_synthetic_utility_data,
    mine_high_utility_dense_itemsets,
    read_utility_transactions,
    write_external_utilities,
    write_utility_transactions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_transactions():
    """5 transactions with known utilities."""
    ext = {1: 2.0, 2: 3.0, 3: 1.0, 4: 5.0}
    txs = [
        UtilityTransaction(0, [1, 2, 3], [1, 2, 3], 11.0),  # 2+6+3=11
        UtilityTransaction(1, [1, 3], [2, 1], 5.0),          # 4+1=5
        UtilityTransaction(2, [2, 4], [1, 2], 13.0),         # 3+10=13
        UtilityTransaction(3, [1, 2, 3, 4], [1, 1, 1, 1], 11.0),  # 2+3+1+5=11
        UtilityTransaction(4, [1, 2], [3, 1], 9.0),          # 6+3=9
    ]
    return txs, ext


@pytest.fixture
def dense_transactions():
    """20 transactions with a dense pattern in [5, 15]."""
    ext = {0: 1.0, 1: 2.0, 2: 3.0, 3: 4.0, 4: 5.0}
    txs = []
    for tid in range(20):
        if 5 <= tid <= 15:
            # Pattern {1, 2} with high utility
            items = [1, 2, 3]
            quantities = [3, 2, 1]
            tu = 3*2.0 + 2*3.0 + 1*4.0  # 6+6+4=16
        else:
            items = [0, 4]
            quantities = [1, 1]
            tu = 1*1.0 + 1*5.0  # 6
        txs.append(UtilityTransaction(tid, items, quantities, tu))
    return txs, ext


# ---------------------------------------------------------------------------
# Unit Tests: Utility computation
# ---------------------------------------------------------------------------

class TestUtilityComputation:
    def test_item_utility(self, simple_transactions):
        txs, ext = simple_transactions
        assert compute_item_utility(txs[0], 1, ext) == 2.0   # 1 * 2.0
        assert compute_item_utility(txs[0], 2, ext) == 6.0   # 2 * 3.0
        assert compute_item_utility(txs[0], 3, ext) == 3.0   # 3 * 1.0
        assert compute_item_utility(txs[0], 4, ext) == 0.0   # not present

    def test_itemset_utility(self, simple_transactions):
        txs, ext = simple_transactions
        # {1, 2} in tx0: 1*2 + 2*3 = 8
        assert compute_itemset_utility(txs[0], (1, 2), ext) == 8.0
        # {1, 2} in tx1: item 2 not present -> 0
        assert compute_itemset_utility(txs[1], (1, 2), ext) == 0.0
        # {1, 2, 3} in tx0: 2 + 6 + 3 = 11
        assert compute_itemset_utility(txs[0], (1, 2, 3), ext) == 11.0

    def test_twu(self, simple_transactions):
        txs, ext = simple_transactions
        # Item 1 appears in tx0(11), tx1(5), tx3(11), tx4(9) -> TWU = 36
        assert compute_twu(txs, 1) == 36.0
        # Item 4 appears in tx2(13), tx3(11) -> TWU = 24
        assert compute_twu(txs, 4) == 24.0


class TestWindowComputation:
    def test_window_utility(self, simple_transactions):
        txs, ext = simple_transactions
        # {1, 2} in window [0, 1]: tx0 has both (8.0), tx1 missing item 2 (0)
        assert compute_window_utility(txs, (1, 2), ext, 0, 1) == 8.0
        # {1, 2} in window [3, 4]: tx3(2+3=5), tx4(6+3=9) -> 14
        assert compute_window_utility(txs, (1, 2), ext, 3, 4) == 14.0

    def test_window_twu(self, simple_transactions):
        txs, ext = simple_transactions
        # {1, 2} in window [0, 1]: only tx0 has both -> TU=11
        assert compute_window_twu(txs, (1, 2), 0, 1) == 11.0
        # {1, 2} in window [0, 4]: tx0(11), tx3(11), tx4(9) -> 31
        assert compute_window_twu(txs, (1, 2), 0, 4) == 31.0


# ---------------------------------------------------------------------------
# Unit Tests: Prefix sums
# ---------------------------------------------------------------------------

class TestPrefixSums:
    def test_prefix_twu_single_item(self, simple_transactions):
        txs, ext = simple_transactions
        item_map = build_item_transaction_map(txs)
        tx_idx = build_transaction_index(txs)

        prefix = compute_prefix_twu(txs, (1,), item_map, tx_idx, 5)
        # Item 1 in tx0(11), tx1(5), tx3(11), tx4(9)
        assert len(prefix) == 6
        assert prefix[0] == 0.0
        assert prefix[1] == 11.0   # tx0
        assert prefix[2] == 16.0   # tx0+tx1
        assert prefix[3] == 16.0   # tx2 doesn't have item 1
        assert prefix[4] == 27.0   # +tx3
        assert prefix[5] == 36.0   # +tx4

    def test_prefix_utility(self, simple_transactions):
        txs, ext = simple_transactions
        item_map = build_item_transaction_map(txs)
        tx_idx = build_transaction_index(txs)

        prefix = compute_prefix_utility(txs, (1, 2), ext, item_map, tx_idx, 5)
        # {1,2} in tx0: 8.0, tx3: 5.0, tx4: 9.0
        assert prefix[0] == 0.0
        assert prefix[1] == 8.0
        assert prefix[2] == 8.0   # tx1 doesn't have {1,2}
        assert prefix[3] == 8.0   # tx2 doesn't have {1,2}
        assert prefix[4] == 13.0  # +5.0
        assert prefix[5] == 22.0  # +9.0

    def test_window_query_via_prefix(self, simple_transactions):
        txs, ext = simple_transactions
        item_map = build_item_transaction_map(txs)
        tx_idx = build_transaction_index(txs)

        prefix = compute_prefix_utility(txs, (1, 2), ext, item_map, tx_idx, 5)
        # Window [3, 4]: prefix[5] - prefix[3] = 22 - 8 = 14
        assert prefix[5] - prefix[3] == 14.0
        # Matches direct computation
        assert compute_window_utility(txs, (1, 2), ext, 3, 4) == 14.0


# ---------------------------------------------------------------------------
# Unit Tests: Utility-Dense Interval Detection
# ---------------------------------------------------------------------------

class TestUtilityDenseIntervals:
    def test_finds_injected_pattern(self, dense_transactions):
        txs, ext = dense_transactions
        item_map = build_item_transaction_map(txs)
        tx_idx = build_transaction_index(txs)
        n = len(txs)

        timestamps = item_map[1]  # item 1 appears in [5..15]
        prefix_util = compute_prefix_utility(
            txs, (1,), ext, item_map, tx_idx, n
        )
        prefix_twu = compute_prefix_twu(
            txs, (1,), item_map, tx_idx, n
        )

        intervals, utils = find_utility_dense_intervals(
            (1,), timestamps, prefix_util, prefix_twu,
            window_size=5, freq_threshold=3, util_threshold=10.0,
            n_transactions=n,
        )
        assert len(intervals) > 0
        # Intervals represent window-left-edge ranges.
        # A window starting at s covers [s, s+W], so s can be as low as
        # first_occurrence - window_size = 5 - 5 = 0.
        # The end e should not exceed the last occurrence (15).
        for s, e in intervals:
            assert s >= 0
            assert e <= 15

    def test_empty_when_threshold_too_high(self, dense_transactions):
        txs, ext = dense_transactions
        item_map = build_item_transaction_map(txs)
        tx_idx = build_transaction_index(txs)
        n = len(txs)

        timestamps = item_map[1]
        prefix_util = compute_prefix_utility(
            txs, (1,), ext, item_map, tx_idx, n
        )
        prefix_twu = compute_prefix_twu(
            txs, (1,), item_map, tx_idx, n
        )

        intervals, _ = find_utility_dense_intervals(
            (1,), timestamps, prefix_util, prefix_twu,
            window_size=5, freq_threshold=3, util_threshold=99999.0,
            n_transactions=n,
        )
        assert len(intervals) == 0


# ---------------------------------------------------------------------------
# Integration Tests: End-to-end mining
# ---------------------------------------------------------------------------

class TestEndToEndMining:
    def test_synthetic_pattern_recovery(self):
        """Inject a known pattern and verify it is recovered."""
        inject = {
            "itemset": [1, 3],
            "interval": (100, 300),
            "frequency": 0.9,
            "high_quantity": 3,
        }
        txs, ext = generate_synthetic_utility_data(
            n_transactions=500, n_items=10, max_items_per_tx=5,
            seed=123, inject_pattern=inject,
        )
        results, stats = mine_high_utility_dense_itemsets(
            txs, ext,
            window_size=30, freq_threshold=5, util_threshold=50.0,
            max_length=3, use_twu_pruning=True,
        )
        # Should find at least the injected 2-itemset
        found_itemsets = {r.itemset for r in results if len(r.itemset) >= 2}
        assert (1, 3) in found_itemsets, f"Expected (1,3) in {found_itemsets}"

        # The interval should overlap with [100, 300]
        for r in results:
            if r.itemset == (1, 3):
                has_overlap = any(
                    s <= 300 and e >= 100 for s, e in r.intervals
                )
                assert has_overlap, f"Intervals {r.intervals} should overlap [100, 300]"

    def test_twu_pruning_reduces_candidates(self):
        """TWU pruning should reduce the number of evaluated candidates."""
        txs, ext = generate_synthetic_utility_data(
            n_transactions=200, n_items=10, seed=99,
        )
        _, stats_with = mine_high_utility_dense_itemsets(
            txs, ext,
            window_size=20, freq_threshold=3, util_threshold=30.0,
            max_length=3, use_twu_pruning=True,
        )
        _, stats_without = mine_high_utility_dense_itemsets(
            txs, ext,
            window_size=20, freq_threshold=3, util_threshold=30.0,
            max_length=3, use_twu_pruning=False,
        )
        assert stats_with["candidates_pruned_twu"] >= 0
        # With pruning, evaluated should be <= without pruning
        assert stats_with["candidates_evaluated"] <= stats_without["candidates_evaluated"]

    def test_empty_input(self):
        """No transactions should return empty results."""
        results, stats = mine_high_utility_dense_itemsets(
            [], {}, window_size=5, freq_threshold=2,
            util_threshold=10.0, max_length=3,
        )
        assert len(results) == 0

    def test_max_length_respected(self):
        """Results should not contain itemsets longer than max_length."""
        txs, ext = generate_synthetic_utility_data(
            n_transactions=300, n_items=8, seed=77,
        )
        results, _ = mine_high_utility_dense_itemsets(
            txs, ext,
            window_size=20, freq_threshold=3, util_threshold=10.0,
            max_length=2,
        )
        for r in results:
            assert len(r.itemset) <= 2


# ---------------------------------------------------------------------------
# I/O Tests
# ---------------------------------------------------------------------------

class TestIO:
    def test_write_read_roundtrip(self, tmp_path):
        """Write and re-read utility transactions."""
        ext = {0: 1.5, 1: 2.5, 2: 3.5}
        txs = [
            UtilityTransaction(0, [0, 1], [2, 3], 2*1.5 + 3*2.5),
            UtilityTransaction(1, [1, 2], [1, 1], 1*2.5 + 1*3.5),
        ]

        tx_path = str(tmp_path / "transactions.txt")
        write_utility_transactions(tx_path, txs)

        loaded, _ = read_utility_transactions(tx_path)
        assert len(loaded) == 2
        assert loaded[0].items == [0, 1]
        assert loaded[0].quantities == [2, 3]

    def test_write_read_external_utilities(self, tmp_path):
        ext = {0: 1.5, 1: 2.5, 2: 3.5}
        path = str(tmp_path / "utilities.txt")
        write_external_utilities(path, ext)

        from high_utility_dense_intervals import read_external_utilities
        loaded = read_external_utilities(path)
        assert len(loaded) == 3
        assert abs(loaded[0] - 1.5) < 0.01


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_transaction(self):
        ext = {1: 5.0}
        txs = [UtilityTransaction(0, [1], [10], 50.0)]
        results, _ = mine_high_utility_dense_itemsets(
            txs, ext, window_size=1, freq_threshold=1,
            util_threshold=40.0, max_length=2,
        )
        assert len(results) == 1
        assert results[0].itemset == (1,)

    def test_no_high_utility(self):
        """All items have very low utility; threshold is high."""
        ext = {i: 0.01 for i in range(5)}
        txs = [
            UtilityTransaction(t, [0, 1, 2], [1, 1, 1], 0.03)
            for t in range(50)
        ]
        results, _ = mine_high_utility_dense_itemsets(
            txs, ext, window_size=10, freq_threshold=3,
            util_threshold=100.0, max_length=3,
        )
        assert len(results) == 0

    def test_all_same_items(self):
        """Every transaction has the same items."""
        ext = {1: 10.0, 2: 10.0}
        txs = [
            UtilityTransaction(t, [1, 2], [1, 1], 20.0)
            for t in range(30)
        ]
        results, _ = mine_high_utility_dense_itemsets(
            txs, ext, window_size=5, freq_threshold=3,
            util_threshold=50.0, max_length=3,
        )
        # {1,2} should be found as utility-dense
        found = {r.itemset for r in results}
        assert (1, 2) in found
