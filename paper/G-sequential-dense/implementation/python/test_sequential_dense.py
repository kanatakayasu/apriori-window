"""
Tests for Sequential Dense Pattern Mining
"""

import pytest
from sequential_dense import (
    build_item_occurrence_map,
    compute_dense_intervals,
    compute_sequential_occurrences,
    compute_in_window_sequential_support,
    find_sequential_dense_patterns,
    generate_length2_candidates,
    generate_sequential_candidates,
    prune_sequential_candidates,
    read_transactions,
)


# ---------------------------------------------------------------------------
# build_item_occurrence_map
# ---------------------------------------------------------------------------

class TestBuildItemOccurrenceMap:
    def test_basic(self):
        txns = [[1, 2], [2, 3], [1, 3]]
        m = build_item_occurrence_map(txns)
        assert m[1] == [0, 2]
        assert m[2] == [0, 1]
        assert m[3] == [1, 2]

    def test_empty(self):
        m = build_item_occurrence_map([])
        assert m == {}

    def test_no_duplicates(self):
        txns = [[1, 1, 2, 2]]
        m = build_item_occurrence_map(txns)
        assert m[1] == [0]
        assert m[2] == [0]

    def test_empty_transactions(self):
        txns = [[], [1], []]
        m = build_item_occurrence_map(txns)
        assert m[1] == [1]


# ---------------------------------------------------------------------------
# compute_dense_intervals
# ---------------------------------------------------------------------------

class TestComputeDenseIntervals:
    def test_basic_dense(self):
        # 3 occurrences within window of 5, threshold 3
        ts = [0, 1, 2, 10, 11, 12]
        intervals = compute_dense_intervals(ts, 5, 3)
        assert len(intervals) >= 1

    def test_no_dense(self):
        ts = [0, 10, 20]
        intervals = compute_dense_intervals(ts, 2, 3)
        assert intervals == []

    def test_empty(self):
        assert compute_dense_intervals([], 5, 3) == []

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            compute_dense_intervals([1], 0, 1)
        with pytest.raises(ValueError):
            compute_dense_intervals([1], 1, 0)

    def test_single_element_meets_threshold(self):
        ts = [5]
        intervals = compute_dense_intervals(ts, 10, 1)
        assert len(intervals) == 1

    def test_continuous_dense(self):
        ts = list(range(10))
        intervals = compute_dense_intervals(ts, 3, 2)
        assert len(intervals) >= 1


# ---------------------------------------------------------------------------
# compute_sequential_occurrences
# ---------------------------------------------------------------------------

class TestComputeSequentialOccurrences:
    def test_simple_sequence(self):
        item_map = {1: [0, 3, 6], 2: [1, 4, 7]}
        occs = compute_sequential_occurrences(item_map, (1, 2), max_gap=0)
        # 1@0 -> 2@1, 1@3 -> 2@4, 1@6 -> 2@7
        assert occs == [1, 4, 7]

    def test_no_occurrence(self):
        item_map = {1: [5], 2: [3]}
        occs = compute_sequential_occurrences(item_map, (1, 2), max_gap=0)
        # 1@5 but no 2 after 5
        assert occs == []

    def test_single_item(self):
        item_map = {1: [0, 3, 7]}
        occs = compute_sequential_occurrences(item_map, (1,), max_gap=0)
        assert occs == [0, 3, 7]

    def test_empty_sequence(self):
        item_map = {1: [0]}
        assert compute_sequential_occurrences(item_map, (), max_gap=0) == []

    def test_missing_item(self):
        item_map = {1: [0]}
        assert compute_sequential_occurrences(item_map, (1, 2), max_gap=0) == []

    def test_with_max_gap(self):
        item_map = {1: [0, 10], 2: [2, 11]}
        # max_gap=2: 1@0 -> 2@2 (gap=2, OK), 1@10 -> 2@11 (gap=1, OK)
        occs = compute_sequential_occurrences(item_map, (1, 2), max_gap=2)
        assert occs == [2, 11]

    def test_max_gap_filters(self):
        item_map = {1: [0], 2: [5]}
        # max_gap=2: 1@0 -> 2@5 (gap=5, exceeds max_gap=2)
        occs = compute_sequential_occurrences(item_map, (1, 2), max_gap=2)
        assert occs == []

    def test_length3_sequence(self):
        item_map = {1: [0, 5], 2: [1, 6], 3: [2, 7]}
        occs = compute_sequential_occurrences(item_map, (1, 2, 3), max_gap=0)
        assert occs == [2, 7]

    def test_same_item_repeated(self):
        item_map = {1: [0, 1, 2, 5, 6]}
        occs = compute_sequential_occurrences(item_map, (1, 1), max_gap=0)
        # 1@0->1@1, 1@1->1@2, 1@2->1@5, 1@5->1@6
        assert occs == [1, 2, 5, 6]

    def test_no_gap_constraint(self):
        item_map = {1: [0], 2: [100]}
        occs = compute_sequential_occurrences(item_map, (1, 2), max_gap=0)
        assert occs == [100]


# ---------------------------------------------------------------------------
# compute_in_window_sequential_support
# ---------------------------------------------------------------------------

class TestInWindowSequentialSupport:
    def test_basic(self):
        item_map = {1: [0, 3, 6], 2: [1, 4, 7]}
        sup = compute_in_window_sequential_support(item_map, (1, 2), 0, 5, max_gap=0)
        # within [0,5]: occ endpoints at 1, 4
        assert sup == 2

    def test_empty_window(self):
        item_map = {1: [0], 2: [1]}
        sup = compute_in_window_sequential_support(item_map, (1, 2), 10, 5, max_gap=0)
        assert sup == 0


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

class TestCandidateGeneration:
    def test_length2(self):
        cands = generate_length2_candidates([1, 2])
        assert (1, 2) in cands
        assert (2, 1) in cands
        assert (1, 1) in cands
        assert (2, 2) in cands
        assert len(cands) == 4

    def test_sequential_candidates(self):
        prev = [(1, 2), (2, 3), (1, 3)]
        cands = generate_sequential_candidates(prev, 3)
        # (1,2) suffix=(2,), extends to (1,2,3) via (2,3)
        assert (1, 2, 3) in cands

    def test_prune(self):
        candidates = [(1, 2, 3)]
        prev_set = {(1, 2), (2, 3), (1, 3)}
        pruned = prune_sequential_candidates(candidates, prev_set)
        assert (1, 2, 3) in pruned

    def test_prune_removes(self):
        candidates = [(1, 2, 3)]
        prev_set = {(1, 2)}  # (2,3) and (1,3) missing
        pruned = prune_sequential_candidates(candidates, prev_set)
        assert pruned == []


# ---------------------------------------------------------------------------
# find_sequential_dense_patterns (integration)
# ---------------------------------------------------------------------------

class TestFindSequentialDensePatterns:
    def test_basic_discovery(self):
        # Dense region: t=0..9, items 1 and 2 alternate
        txns: list = []
        for i in range(20):
            if i < 10:
                txns.append([1] if i % 2 == 0 else [2])
            else:
                txns.append([])

        result = find_sequential_dense_patterns(
            txns, window_size=5, threshold=2, max_length=2, max_gap=0
        )
        # Single items should have dense intervals
        assert (1,) in result
        assert (2,) in result

    def test_sequential_pattern_found(self):
        # Create data: 1 always followed by 2 in next transaction
        txns = []
        for i in range(20):
            if i % 2 == 0:
                txns.append([1])
            else:
                txns.append([2])

        result = find_sequential_dense_patterns(
            txns, window_size=10, threshold=3, max_length=2, max_gap=0
        )
        # (1, 2) should be found as sequential dense pattern
        assert (1, 2) in result

    def test_no_pattern_sparse_data(self):
        txns = [[1], [], [], [], [], [], [], [], [], [2]]
        result = find_sequential_dense_patterns(
            txns, window_size=2, threshold=3, max_length=2, max_gap=0
        )
        # No dense patterns expected for length >= 2
        seq_patterns = {k: v for k, v in result.items() if len(k) >= 2}
        assert len(seq_patterns) == 0

    def test_max_length_respected(self):
        txns = [[1], [2], [3], [1], [2], [3], [1], [2], [3]]
        result = find_sequential_dense_patterns(
            txns, window_size=5, threshold=2, max_length=2, max_gap=0
        )
        for seq in result:
            assert len(seq) <= 2

    def test_max_gap_constraint(self):
        # 1 at 0, 2 at 5 -- gap=5 exceeds max_gap=2
        txns = [[1], [], [], [], [], [2]]
        result = find_sequential_dense_patterns(
            txns, window_size=10, threshold=1, max_length=2, max_gap=2
        )
        assert (1, 2) not in result

    def test_empty_transactions(self):
        result = find_sequential_dense_patterns(
            [], window_size=5, threshold=2, max_length=3, max_gap=0
        )
        assert result == {}

    def test_length3_pattern(self):
        # Repeating 1->2->3 sequence densely
        txns = []
        for _ in range(5):
            txns.extend([[1], [2], [3]])
        result = find_sequential_dense_patterns(
            txns, window_size=10, threshold=2, max_length=3, max_gap=0
        )
        # Check that length-3 pattern is found
        len3 = [k for k in result if len(k) == 3]
        assert len(len3) > 0


# ---------------------------------------------------------------------------
# Anti-monotonicity property test
# ---------------------------------------------------------------------------

class TestAntiMonotonicity:
    def test_subsequence_support_geq_supersequence(self):
        """系列反単調性: 部分系列のサポートは上位系列以上"""
        txns = []
        for _ in range(10):
            txns.extend([[1], [2], [3]])

        item_map = build_item_occurrence_map(txns)

        occ_12 = compute_sequential_occurrences(item_map, (1, 2), max_gap=0)
        occ_123 = compute_sequential_occurrences(item_map, (1, 2, 3), max_gap=0)

        assert len(occ_12) >= len(occ_123)
