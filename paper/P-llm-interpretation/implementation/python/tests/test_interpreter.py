"""Tests for LLM Pattern Interpreter."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add implementation to path
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2]),
)

from llm_pattern_interpreter import (
    PatternInfo,
    PatternInterpreter,
    ItemMetadata,
    InterpretationResult,
    build_pattern_prompt,
    build_comparative_prompt,
    build_batch_prompt,
    extract_pattern_info,
    evaluate_interpretations,
    run_interpretation_pipeline,
    _generate_mock_response,
    _generate_mock_comparative_response,
    SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_pattern():
    return PatternInfo(
        itemset=(1, 2, 3),
        intervals=[(0, 10), (20, 30)],
        support_ratio=0.2,
        interval_count=2,
        total_span=22,
        max_gap=10,
    )


@pytest.fixture
def sample_metadata():
    return {
        1: ItemMetadata(item_id=1, name="パン", category="食品"),
        2: ItemMetadata(item_id=2, name="牛乳", category="飲料"),
        3: ItemMetadata(item_id=3, name="バター", category="食品"),
    }


@pytest.fixture
def sample_transaction_file(tmp_path):
    data = "1 2 3\n1 2\n2 3\n1 3\n1 2 3\n2 3\n1 2\n1 2 3\n3\n1 2\n"
    f = tmp_path / "test_data.txt"
    f.write_text(data)
    return str(f)


@pytest.fixture
def sample_metadata_file(tmp_path):
    meta = [
        {"item_id": 1, "name": "パン", "category": "食品"},
        {"item_id": 2, "name": "牛乳", "category": "飲料"},
        {"item_id": 3, "name": "バター", "category": "食品"},
    ]
    f = tmp_path / "metadata.json"
    f.write_text(json.dumps(meta, ensure_ascii=False))
    return str(f)


# ---------------------------------------------------------------------------
# PatternInfo tests
# ---------------------------------------------------------------------------

class TestPatternInfo:
    def test_to_dict(self, sample_pattern):
        d = sample_pattern.to_dict()
        assert d["itemset"] == [1, 2, 3]
        assert d["intervals"] == [[0, 10], [20, 30]]
        assert d["support_ratio"] == 0.2

    def test_empty_intervals(self):
        p = PatternInfo(
            itemset=(1, 2),
            intervals=[],
            support_ratio=0.0,
            interval_count=0,
            total_span=0,
            max_gap=0,
        )
        assert p.interval_count == 0
        assert p.total_span == 0


# ---------------------------------------------------------------------------
# extract_pattern_info tests
# ---------------------------------------------------------------------------

class TestExtractPatternInfo:
    def test_basic(self):
        info = extract_pattern_info(
            (1, 2), [(0, 10), (20, 30)], 100
        )
        assert info.itemset == (1, 2)
        assert info.interval_count == 2
        assert info.total_span == 22
        assert info.max_gap == 10
        assert abs(info.support_ratio - 0.22) < 0.01

    def test_single_interval(self):
        info = extract_pattern_info((1, 2), [(5, 15)], 100)
        assert info.interval_count == 1
        assert info.total_span == 11
        assert info.max_gap == 0

    def test_empty_intervals(self):
        info = extract_pattern_info((1, 2), [], 100)
        assert info.interval_count == 0
        assert info.support_ratio == 0.0

    def test_zero_transactions(self):
        info = extract_pattern_info((1, 2), [(0, 5)], 0)
        assert info.support_ratio == 6.0  # 6 / max(0,1)


# ---------------------------------------------------------------------------
# Prompt generation tests
# ---------------------------------------------------------------------------

class TestPromptGeneration:
    def test_basic_prompt(self, sample_pattern):
        prompt = build_pattern_prompt(
            sample_pattern, window_size=5, threshold=3, max_transaction=100
        )
        assert "Item 1" in prompt
        assert "Item 2" in prompt
        assert "Item 3" in prompt
        assert "[0, 10]" in prompt
        assert "20.0%" in prompt

    def test_prompt_with_metadata(self, sample_pattern, sample_metadata):
        prompt = build_pattern_prompt(
            sample_pattern, 5, 3, 100, metadata=sample_metadata
        )
        assert "パン" in prompt
        assert "牛乳" in prompt
        assert "バター" in prompt
        assert "食品" in prompt

    def test_comparative_prompt(self, sample_pattern):
        p2 = PatternInfo(
            itemset=(4, 5),
            intervals=[(50, 60)],
            support_ratio=0.1,
            interval_count=1,
            total_span=11,
            max_gap=0,
        )
        prompt = build_comparative_prompt(
            [sample_pattern, p2], 5, 3, 100
        )
        assert "パターン 1" in prompt
        assert "パターン 2" in prompt
        assert "比較分析" in prompt

    def test_batch_prompt(self, sample_pattern):
        prompt = build_batch_prompt([sample_pattern])
        assert "1 件" in prompt
        assert "一括" in prompt


# ---------------------------------------------------------------------------
# Mock LLM response tests
# ---------------------------------------------------------------------------

class TestMockResponse:
    def test_single_interval_response(self):
        p = PatternInfo(
            itemset=(1, 2), intervals=[(0, 10)],
            support_ratio=0.4, interval_count=1,
            total_span=11, max_gap=0,
        )
        resp = _generate_mock_response(p)
        assert "単一連続" in resp["summary"]
        assert resp["confidence"] == 0.85

    def test_multi_interval_response(self, sample_pattern):
        resp = _generate_mock_response(sample_pattern)
        assert "断続的" in resp["summary"]
        assert resp["confidence"] == 0.70

    def test_many_intervals_response(self):
        p = PatternInfo(
            itemset=(1, 2),
            intervals=[(i * 10, i * 10 + 3) for i in range(5)],
            support_ratio=0.05,
            interval_count=5,
            total_span=20,
            max_gap=7,
        )
        resp = _generate_mock_response(p)
        assert "高頻度断続" in resp["summary"]
        assert resp["confidence"] == 0.55

    def test_with_metadata(self, sample_metadata):
        p = PatternInfo(
            itemset=(1, 2), intervals=[(0, 10)],
            support_ratio=0.4, interval_count=1,
            total_span=11, max_gap=0,
        )
        resp = _generate_mock_response(p, metadata=sample_metadata)
        assert "パン" in resp["summary"]
        assert "牛乳" in resp["summary"]

    def test_comparative_response(self, sample_pattern):
        p2 = PatternInfo(
            itemset=(1, 4), intervals=[(50, 60)],
            support_ratio=0.1, interval_count=1,
            total_span=11, max_gap=0,
        )
        result = _generate_mock_comparative_response([sample_pattern, p2])
        assert "比較分析結果" in result
        assert "2パターン" in result

    def test_comparative_common_items(self, sample_pattern):
        p2 = PatternInfo(
            itemset=(1, 2, 4), intervals=[(50, 60)],
            support_ratio=0.1, interval_count=1,
            total_span=11, max_gap=0,
        )
        result = _generate_mock_comparative_response([sample_pattern, p2])
        assert "共通アイテム" in result


# ---------------------------------------------------------------------------
# PatternInterpreter tests
# ---------------------------------------------------------------------------

class TestPatternInterpreter:
    def test_interpret_single(self, sample_pattern):
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100
        )
        result = interp.interpret_pattern(sample_pattern)
        assert isinstance(result, InterpretationResult)
        assert len(result.summary) > 0
        assert len(result.temporal_description) > 0
        assert len(result.business_hypothesis) > 0
        assert 0 <= result.confidence <= 1
        assert len(result.prompt_used) > 0

    def test_interpret_with_metadata(self, sample_pattern, sample_metadata):
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100,
            metadata=sample_metadata,
        )
        result = interp.interpret_pattern(sample_pattern)
        assert "パン" in result.summary

    def test_interpret_all(self):
        frequents = {
            (1,): [(0, 10)],
            (1, 2): [(0, 10), (20, 30)],
            (2, 3): [(5, 15)],
        }
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100
        )
        results = interp.interpret_all(frequents, top_k=5)
        # Singletons should be excluded
        assert len(results) == 2

    def test_interpret_all_top_k(self):
        frequents = {
            (i, i + 1): [(0, 10)] for i in range(20)
        }
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100
        )
        results = interp.interpret_all(frequents, top_k=3)
        assert len(results) == 3

    def test_compare_patterns(self, sample_pattern):
        p2 = PatternInfo(
            itemset=(4, 5), intervals=[(50, 60)],
            support_ratio=0.1, interval_count=1,
            total_span=11, max_gap=0,
        )
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100
        )
        result = interp.compare_patterns([sample_pattern, p2])
        assert "比較分析結果" in result

    def test_batch_summarize(self):
        frequents = {
            (1,): [(0, 10)],
            (1, 2): [(0, 10)],
            (2, 3): [(5, 15)],
        }
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100
        )
        result = interp.batch_summarize(frequents)
        assert "全2パターン" in result

    def test_unsupported_backend(self, sample_pattern):
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100,
            llm_backend="openai",
        )
        with pytest.raises(NotImplementedError):
            interp.interpret_pattern(sample_pattern)


# ---------------------------------------------------------------------------
# Evaluation metrics tests
# ---------------------------------------------------------------------------

class TestEvaluationMetrics:
    def test_basic_metrics(self, sample_pattern):
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100
        )
        results = [interp.interpret_pattern(sample_pattern)]
        metrics = evaluate_interpretations(results)
        assert metrics.pattern_count == 1
        assert metrics.avg_confidence > 0
        assert metrics.has_temporal_info == 1.0
        assert metrics.has_hypothesis == 1.0

    def test_empty_metrics(self):
        metrics = evaluate_interpretations([])
        assert metrics.pattern_count == 0
        assert metrics.avg_confidence == 0

    def test_multiple_patterns_metrics(self):
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100
        )
        patterns = [
            PatternInfo((1, 2), [(0, 10)], 0.4, 1, 11, 0),
            PatternInfo((3, 4), [(0, 3), (10, 13)], 0.08, 2, 8, 7),
        ]
        results = [interp.interpret_pattern(p) for p in patterns]
        metrics = evaluate_interpretations(results)
        assert metrics.pattern_count == 2
        assert metrics.avg_summary_length > 0
        # Higher cover -> higher confidence -> positive correlation
        assert metrics.coverage_correlation > 0


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_pipeline(self, sample_transaction_file):
        result = run_interpretation_pipeline(
            input_path=sample_transaction_file,
            window_size=5,
            threshold=2,
            max_length=3,
            top_k=5,
        )
        assert "parameters" in result
        assert "interpretations" in result
        assert "metrics" in result
        assert "batch_summary" in result

    def test_pipeline_with_metadata(
        self, sample_transaction_file, sample_metadata_file
    ):
        result = run_interpretation_pipeline(
            input_path=sample_transaction_file,
            window_size=5,
            threshold=2,
            max_length=3,
            metadata_path=sample_metadata_file,
        )
        assert "interpretations" in result
        # Check metadata was used
        if result["interpretations"]:
            raw = result["interpretations"][0].get("raw_response", "")
            assert "パン" in raw or "牛乳" in raw or "バター" in raw

    def test_pipeline_output_file(self, sample_transaction_file, tmp_path):
        out = str(tmp_path / "output.json")
        result = run_interpretation_pipeline(
            input_path=sample_transaction_file,
            window_size=5,
            threshold=2,
            max_length=3,
            output_path=out,
        )
        assert Path(out).exists()
        with open(out, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["parameters"]["window_size"] == 5

    def test_result_serialization(self, sample_pattern):
        interp = PatternInterpreter(
            window_size=5, threshold=3, max_transaction=100
        )
        result = interp.interpret_pattern(sample_pattern)
        d = result.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d, ensure_ascii=False)
        assert len(json_str) > 0


# ---------------------------------------------------------------------------
# ItemMetadata tests
# ---------------------------------------------------------------------------

class TestItemMetadata:
    def test_from_dict(self):
        d = {"item_id": 1, "name": "テスト", "category": "カテA"}
        m = ItemMetadata.from_dict(d)
        assert m.item_id == 1
        assert m.name == "テスト"
        assert m.category == "カテA"

    def test_from_dict_no_category(self):
        d = {"item_id": 2, "name": "テスト2"}
        m = ItemMetadata.from_dict(d)
        assert m.category == ""
