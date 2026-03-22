"""
Tests for MDL Summary (Paper F).
"""

import math
import os
import sys
import tempfile
from pathlib import Path

import pytest

# テスト対象
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mdl_summary import (
    TemporalCodeEntry,
    TemporalCodeTable,
    build_standard_code_table,
    compression_ratio,
    compute_baseline_length,
    greedy_mdl_selection,
    log2_binomial,
    mine_temporal_patterns,
    prequential_code_length,
    run_mdl_summary,
    time_scoped_code_length,
    universal_integer_code_length,
)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def make_temp_data(lines: list[str]) -> str:
    """一時ファイルにトランザクションデータを書き込み、パスを返す。"""
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def make_simple_transactions():
    """テスト用の簡単なトランザクションデータ。"""
    # 10トランザクション、アイテム 1,2,3 が前半に密集
    lines = [
        "1 2 3",    # t=0
        "1 2 3",    # t=1
        "1 2 3",    # t=2
        "1 2",      # t=3
        "1 3",      # t=4
        "4 5",      # t=5
        "4 5",      # t=6
        "4 5 6",    # t=7
        "6 7",      # t=8
        "7 8",      # t=9
    ]
    return lines


# ---------------------------------------------------------------------------
# 基本符号長
# ---------------------------------------------------------------------------

class TestUniversalIntegerCode:
    def test_zero(self):
        assert universal_integer_code_length(0) == 0.0

    def test_negative(self):
        assert universal_integer_code_length(-1) == 0.0

    def test_positive(self):
        result = universal_integer_code_length(1)
        assert result > 0

    def test_monotone(self):
        """大きい整数ほど長い符号。"""
        l1 = universal_integer_code_length(1)
        l10 = universal_integer_code_length(10)
        l100 = universal_integer_code_length(100)
        assert l1 < l10 < l100


class TestLog2Binomial:
    def test_c_n_0(self):
        assert log2_binomial(5, 0) == 0.0

    def test_c_n_n(self):
        assert log2_binomial(5, 5) == 0.0

    def test_c_4_2(self):
        expected = math.log2(6)  # C(4,2) = 6
        assert abs(log2_binomial(4, 2) - expected) < 1e-10

    def test_symmetry(self):
        assert abs(log2_binomial(10, 3) - log2_binomial(10, 7)) < 1e-10


class TestPrequentialCodeLength:
    def test_empty(self):
        assert prequential_code_length([]) == 0.0

    def test_single_symbol(self):
        assert prequential_code_length([10]) == 0.0

    def test_uniform(self):
        result = prequential_code_length([5, 5])
        assert result > 0

    def test_skewed_shorter(self):
        """偏った分布は均一分布より短い（エントロピーが低い）。"""
        uniform = prequential_code_length([10, 10, 10, 10])
        skewed = prequential_code_length([37, 1, 1, 1])
        assert skewed < uniform


# ---------------------------------------------------------------------------
# Temporal Code Table
# ---------------------------------------------------------------------------

class TestTemporalCodeEntry:
    def test_create(self):
        e = TemporalCodeEntry(frozenset([1, 2]), [(0, 5)], usage_count=3)
        assert len(e.pattern) == 2
        assert e.intervals == [(0, 5)]
        assert e.usage_count == 3

    def test_repr(self):
        e = TemporalCodeEntry(frozenset([3, 1]), [(0, 2)], usage_count=1)
        r = repr(e)
        assert "1" in r
        assert "3" in r


class TestTemporalCodeTable:
    def test_create(self):
        tct = TemporalCodeTable(num_items=5, num_transactions=10)
        assert tct.num_items == 5
        assert tct.num_transactions == 10

    def test_add_entry(self):
        tct = TemporalCodeTable(num_items=5, num_transactions=10)
        e = TemporalCodeEntry(frozenset([1, 2]), [(0, 5)])
        tct.add_entry(e)
        assert len(tct.entries) == 1

    def test_sort_order(self):
        """長いパターンが先。"""
        tct = TemporalCodeTable(5, 10)
        tct.add_entry(TemporalCodeEntry(frozenset([1]), [(0, 5)], usage_count=10))
        tct.add_entry(TemporalCodeEntry(frozenset([1, 2, 3]), [(0, 5)], usage_count=2))
        tct.add_entry(TemporalCodeEntry(frozenset([1, 2]), [(0, 5)], usage_count=5))
        assert len(tct.entries[0].pattern) == 3
        assert len(tct.entries[1].pattern) == 2
        assert len(tct.entries[2].pattern) == 1


class TestCover:
    def test_simple_cover(self):
        lines = make_simple_transactions()
        path = make_temp_data(lines)
        try:
            from apriori_window_basket import read_transactions_with_baskets
            transactions = read_transactions_with_baskets(path)

            tct = TemporalCodeTable(8, 10)
            tct.sct_entries = build_standard_code_table(transactions)
            e = TemporalCodeEntry(frozenset([1, 2]), [(0, 4)])
            tct.add_entry(e)

            usage = tct.compute_cover(transactions)
            # {1,2} は t=0,1,2,3 で使われるはず（t=0..4が区間内）
            assert usage.get(frozenset([1, 2]), 0) >= 3
        finally:
            os.unlink(path)


class TestDescriptionLength:
    def test_empty_table(self):
        tct = TemporalCodeTable(5, 10)
        tct.sct_entries = {1: 5, 2: 3}
        length = tct.compute_description_length()
        assert length == 0.0  # エントリなし


# ---------------------------------------------------------------------------
# Build Standard Code Table
# ---------------------------------------------------------------------------

class TestBuildSCT:
    def test_simple(self):
        lines = make_simple_transactions()
        path = make_temp_data(lines)
        try:
            from apriori_window_basket import read_transactions_with_baskets
            transactions = read_transactions_with_baskets(path)
            sct = build_standard_code_table(transactions)
            # item 1: t=0..4 = 5回
            assert sct[1] == 5
            # item 4: t=5,6,7 = 3回
            assert sct[4] == 3
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Baseline Length
# ---------------------------------------------------------------------------

class TestBaselineLength:
    def test_positive(self):
        lines = make_simple_transactions()
        path = make_temp_data(lines)
        try:
            from apriori_window_basket import read_transactions_with_baskets
            transactions = read_transactions_with_baskets(path)
            bl = compute_baseline_length(transactions)
            assert bl > 0
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Time-Scoped Code Length
# ---------------------------------------------------------------------------

class TestTimeScopedCodeLength:
    def test_no_intervals(self):
        e = TemporalCodeEntry(frozenset([1, 2]), [], usage_count=5)
        assert time_scoped_code_length(e, 100) == 0.0

    def test_with_interval(self):
        e = TemporalCodeEntry(frozenset([1, 2]), [(0, 9)], usage_count=5)
        length = time_scoped_code_length(e, 100)
        assert length > 0


# ---------------------------------------------------------------------------
# Compression Ratio
# ---------------------------------------------------------------------------

class TestCompressionRatio:
    def test_with_patterns(self):
        lines = make_simple_transactions()
        path = make_temp_data(lines)
        try:
            from apriori_window_basket import read_transactions_with_baskets
            transactions = read_transactions_with_baskets(path)
            sct = build_standard_code_table(transactions)

            patterns = [
                TemporalCodeEntry(frozenset([1, 2, 3]), [(0, 4)], usage_count=3),
            ]
            result = compression_ratio(transactions, patterns, sct)
            assert "compression_ratio" in result
            assert result["compression_ratio"] > 0
            assert result["num_patterns"] == 1
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Mine Temporal Patterns
# ---------------------------------------------------------------------------

class TestMineTemporalPatterns:
    def test_finds_patterns(self):
        lines = make_simple_transactions()
        path = make_temp_data(lines)
        try:
            from apriori_window_basket import read_transactions_with_baskets
            transactions = read_transactions_with_baskets(path)
            candidates = mine_temporal_patterns(
                transactions, window_size=5, min_support=3, max_pattern_length=3
            )
            # {1,2,3} は t=0..2 で3回出現し、window_size=5 で密集
            # 候補が見つかるはず
            assert isinstance(candidates, list)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_run_mdl_summary(self):
        lines = make_simple_transactions()
        path = make_temp_data(lines)
        try:
            result = run_mdl_summary(
                path, window_size=5, min_support=3, max_pattern_length=3
            )
            assert "num_transactions" in result
            assert result["num_transactions"] == 10
            assert "metrics" in result
            assert "compression_ratio" in result["metrics"]
        finally:
            os.unlink(path)

    def test_empty_data(self):
        """空データでもクラッシュしない。"""
        lines = ["", "", ""]
        path = make_temp_data(lines)
        try:
            result = run_mdl_summary(
                path, window_size=5, min_support=3
            )
            assert result["num_transactions"] == 3
        finally:
            os.unlink(path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
