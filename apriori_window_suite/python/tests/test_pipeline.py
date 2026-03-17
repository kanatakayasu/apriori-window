"""
Phase 2 パイプラインテスト: Stage 1–3 + Pipeline Orchestrator

テストケース:
    TC-S1: Stage 1 MI Pre-filter
        1. compute_mi — 完全一致・完全独立・部分重複
        2. mi_prefilter — 閾値フィルタリング
    TC-S2: Stage 2 Sweep Line Matching
        1. Stage 0 との出力一致（全ペア）
        2. 候補ペアフィルタ適用時
    TC-S3: Stage 3 Permutation Test
        1. 強い関係が有意と判定される
        2. 無関係なペアが棄却される
        3. Bonferroni 補正
    TC-P:  Pipeline Orchestrator
        1. 全 Stage 有効
        2. Stage 1 のみ無効
        3. Stage 3 のみ無効
    TC-CSV: write_significant_csv
    TC-CYC: _cyclic_shift_events

実行方法:
    python3 -m pytest apriori_window_suite/python/tests/test_pipeline.py -v
"""
import csv
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_correlator import (
    Event,
    Frequents,
    PipelineConfig,
    PipelineResult,
    RelationMatch,
    SignificantRelation,
    _count_relations,
    _cyclic_shift_events,
    _to_binary_series,
    compute_mi,
    compute_mi_scores,
    match_all,
    match_sweep_line,
    mi_prefilter,
    permutation_test,
    run_pipeline,
    write_significant_csv,
)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _event(eid: str, start: int, end: int, name: str = "") -> Event:
    return Event(event_id=eid, name=name or eid, start=start, end=end)


def _frequents(pairs) -> Frequents:
    return dict(pairs)


def _relation_types(results: List[RelationMatch]) -> List[str]:
    return [r.relation_type for r in results]


# ---------------------------------------------------------------------------
# TC-S1: Stage 1 — MI Pre-filter
# ---------------------------------------------------------------------------

class TestToBinarySeries:
    def test_single_interval(self):
        series = _to_binary_series([(2, 5)], t_min=0, t_max=7)
        assert series == [0, 0, 1, 1, 1, 1, 0, 0]

    def test_multiple_intervals(self):
        series = _to_binary_series([(0, 1), (4, 5)], t_min=0, t_max=5)
        assert series == [1, 1, 0, 0, 1, 1]

    def test_out_of_range_clipped(self):
        series = _to_binary_series([(-2, 1)], t_min=0, t_max=3)
        assert series == [1, 1, 0, 0]


class TestComputeMI:
    def test_identical_series(self):
        """完全一致 → MI > 0"""
        x = [1, 1, 0, 0, 1, 1, 0, 0]
        y = [1, 1, 0, 0, 1, 1, 0, 0]
        mi = compute_mi(x, y)
        assert mi > 0.5  # 高い MI

    def test_independent_series(self):
        """完全独立 → MI ≈ 0"""
        x = [1, 0, 1, 0, 1, 0, 1, 0]
        y = [1, 1, 0, 0, 1, 1, 0, 0]
        mi = compute_mi(x, y)
        assert abs(mi) < 0.01

    def test_complementary_series(self):
        """相補的 → MI > 0（相互情報量は対称）"""
        x = [1, 1, 0, 0]
        y = [0, 0, 1, 1]
        mi = compute_mi(x, y)
        assert mi > 0.5

    def test_all_zeros(self):
        """全ゼロ → MI = 0"""
        x = [0, 0, 0, 0]
        y = [0, 0, 0, 0]
        mi = compute_mi(x, y)
        assert mi == 0.0

    def test_empty(self):
        assert compute_mi([], []) == 0.0


class TestComputeMIScores:
    def test_overlapping_pair_has_high_mi(self):
        # 時間軸 [0, 100] で密集区間 [20, 60] とイベント [30, 50] が大きく重複
        freq = _frequents([((1, 2), [(20, 60)])])
        events = [_event("E1", 30, 50), _event("DISTANT", 90, 100)]
        scores = compute_mi_scores(freq, events)
        assert scores[((1, 2), "E1")] > 0.0
        # 遠いイベントとの MI は低い
        assert scores[((1, 2), "E1")] > scores[((1, 2), "DISTANT")]

    def test_distant_pair_has_low_mi(self):
        freq = _frequents([((1,), [(0, 10)])])
        events = [_event("E1", 990, 1000)]
        scores = compute_mi_scores(freq, events)
        assert scores[((1,), "E1")] < 0.01

    def test_empty_frequents(self):
        scores = compute_mi_scores({}, [_event("E1", 0, 10)])
        assert scores == {}


class TestMIPrefilter:
    def test_high_mi_passes(self):
        freq = _frequents([((1, 2), [(20, 60)])])
        events = [_event("E1", 30, 50), _event("DISTANT", 90, 100)]
        _, passed = mi_prefilter(freq, events, mi_threshold=0.001)
        assert ((1, 2), "E1") in passed

    def test_low_mi_filtered(self):
        freq = _frequents([((1,), [(0, 5)])])
        events = [_event("E1", 500, 1000)]
        _, passed = mi_prefilter(freq, events, mi_threshold=0.1)
        assert ((1,), "E1") not in passed

    def test_threshold_zero_passes_all_nonzero(self):
        freq = _frequents([((1,), [(0, 50)]), ((2,), [(60, 100)])])
        events = [_event("E1", 10, 40)]
        _, passed = mi_prefilter(freq, events, mi_threshold=0.0)
        # MI > 0 のペアのみ通過（MI = 0 は通過しない）
        assert len(passed) >= 1


# ---------------------------------------------------------------------------
# TC-S2: Stage 2 — Sweep Line Matching
# ---------------------------------------------------------------------------

class TestSweepLineMatching:
    def test_matches_brute_force_all_pairs(self):
        """候補ペア制限なし → Stage 0 と同一結果。"""
        freq = _frequents([
            ((1, 2), [(0, 10), (20, 30)]),
            ((3,), [(5, 15)]),
        ])
        events = [
            _event("E1", 12, 20),
            _event("E2", 0, 100),
        ]
        bf = match_all(freq, events, epsilon=2, d_0=1)
        sw = match_sweep_line(freq, events, epsilon=2, d_0=1, candidate_pairs=None)

        bf_set = {(m.itemset, m.dense_start, m.dense_end, m.event.event_id, m.relation_type)
                  for m in bf}
        sw_set = {(m.itemset, m.dense_start, m.dense_end, m.event.event_id, m.relation_type)
                  for m in sw}
        assert bf_set == sw_set, f"Brute-force と Sweep Line の差: {bf_set ^ sw_set}"

    def test_candidate_pairs_filter(self):
        """候補ペアを制限 → 対象外のペアは出力されない。"""
        freq = _frequents([
            ((1, 2), [(0, 10)]),
            ((3,), [(0, 10)]),
        ])
        events = [
            _event("E1", 12, 20),
            _event("E2", 0, 100),
        ]
        # (1,2) × E1 のみ許可
        candidates = [((1, 2), "E1")]
        sw = match_sweep_line(freq, events, epsilon=2, d_0=1, candidate_pairs=candidates)
        for m in sw:
            assert m.itemset == (1, 2)
            assert m.event.event_id == "E1"

    def test_empty_candidates(self):
        """候補ペアが空リスト → 結果も空。"""
        freq = _frequents([((1,), [(0, 10)])])
        events = [_event("E1", 0, 10)]
        sw = match_sweep_line(freq, events, epsilon=0, d_0=1, candidate_pairs=[])
        assert sw == []

    def test_dfe_detected(self):
        """DenseFollowsEvent を Sweep Line が検出すること。"""
        freq = _frequents([((1, 2), [(0, 10)])])
        events = [_event("E1", 12, 20)]
        sw = match_sweep_line(freq, events, epsilon=2, d_0=1)
        assert "DenseFollowsEvent" in _relation_types(sw)

    def test_ecd_detected(self):
        """EventContainsDense を Sweep Line が検出すること。"""
        freq = _frequents([((1,), [(10, 90)])])
        events = [_event("E1", 0, 100)]
        sw = match_sweep_line(freq, events, epsilon=0, d_0=1)
        assert "EventContainsDense" in _relation_types(sw)


# ---------------------------------------------------------------------------
# TC-CYC: _cyclic_shift_events
# ---------------------------------------------------------------------------

class TestCyclicShift:
    def test_shift_within_range(self):
        events = [_event("E1", 10, 20)]
        shifted = _cyclic_shift_events(events, offset=5, t_min=0, t_max=30)
        assert shifted[0].start == 15
        assert shifted[0].end == 25

    def test_shift_wraps_around(self):
        events = [_event("E1", 25, 28)]
        shifted = _cyclic_shift_events(events, offset=10, t_min=0, t_max=30)
        # 25 + 10 = 35, mod 31 = 4
        assert shifted[0].start == 4

    def test_preserves_event_id(self):
        events = [_event("E1", 0, 5), _event("E2", 10, 15)]
        shifted = _cyclic_shift_events(events, offset=3, t_min=0, t_max=20)
        assert shifted[0].event_id == "E1"
        assert shifted[1].event_id == "E2"


# ---------------------------------------------------------------------------
# TC-S3: Stage 3 — Permutation Test
# ---------------------------------------------------------------------------

class TestCountRelations:
    def test_basic_counting(self):
        ev = _event("E1", 0, 10)
        results = [
            RelationMatch((1, 2), 0, 10, ev, "DenseFollowsEvent", None),
            RelationMatch((1, 2), 20, 30, ev, "DenseFollowsEvent", None),
            RelationMatch((1, 2), 0, 10, ev, "EventContainsDense", None),
        ]
        counts = _count_relations(results)
        assert counts[((1, 2), "E1", "DenseFollowsEvent")] == 2
        assert counts[((1, 2), "E1", "EventContainsDense")] == 1


class TestPermutationTest:
    def test_strong_relation_significant(self):
        """密集区間がイベントに完全包含 → 有意と判定されるべき。"""
        # 密集区間がイベント内に多数存在
        freq = _frequents([
            ((1, 2), [(10, 20), (30, 40), (50, 60), (70, 80), (90, 100)]),
        ])
        events = [_event("E1", 0, 110)]  # 全密集区間を包含
        sig = permutation_test(
            freq, events, epsilon=0, d_0=1,
            n_permutations=99, alpha=0.1, seed=42,
        )
        # EventContainsDense が有意であるべき
        sig_types = {s.relation_type for s in sig}
        assert "EventContainsDense" in sig_types, \
            f"Expected EventContainsDense in {sig_types}"

    def test_unrelated_pair_not_significant(self):
        """密集区間とイベントが完全に離れている → 有意にならない。"""
        freq = _frequents([((1,), [(0, 5)])])
        events = [_event("E1", 10000, 10005)]
        sig = permutation_test(
            freq, events, epsilon=0, d_0=1,
            n_permutations=99, alpha=0.05, seed=42,
        )
        assert len(sig) == 0

    def test_bonferroni_correction(self):
        """Bonferroni 補正を使用できること。"""
        freq = _frequents([((1, 2), [(10, 20)])])
        events = [_event("E1", 0, 100)]
        sig = permutation_test(
            freq, events, epsilon=0, d_0=1,
            n_permutations=49, alpha=0.5,
            correction_method="bonferroni", seed=42,
        )
        # エラーなく完了すること
        assert isinstance(sig, list)

    def test_seed_reproducibility(self):
        """同一 seed で同一結果が得られること。"""
        freq = _frequents([((1, 2), [(0, 50)])])
        events = [_event("E1", 10, 40)]
        r1 = permutation_test(freq, events, 0, 1, n_permutations=49, seed=123)
        r2 = permutation_test(freq, events, 0, 1, n_permutations=49, seed=123)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.p_value == b.p_value


# ---------------------------------------------------------------------------
# TC-P: Pipeline Orchestrator
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def _make_data(self):
        freq = _frequents([
            ((1, 2), [(0, 50), (60, 110)]),
            ((3,), [(0, 20)]),
        ])
        events = [
            _event("E1", 10, 40),
            _event("E2", 200, 300),
        ]
        return freq, events

    def test_all_stages_enabled(self):
        freq, events = self._make_data()
        config = PipelineConfig(
            epsilon=2, d_0=1,
            stage1_enabled=True, mi_threshold=0.001,
            stage2_enabled=True,
            stage3_enabled=True, n_permutations=49, alpha=0.5, seed=42,
        )
        result = run_pipeline(freq, events, config)
        assert result.brute_force_results is not None
        assert result.mi_scores is not None
        assert result.mi_passed_pairs is not None
        assert result.sweep_results is not None
        assert result.significant_relations is not None

    def test_stage1_disabled(self):
        freq, events = self._make_data()
        config = PipelineConfig(
            epsilon=2, d_0=1,
            stage1_enabled=False,
            stage2_enabled=True,
            stage3_enabled=False,
        )
        result = run_pipeline(freq, events, config)
        assert result.mi_scores is None
        assert result.sweep_results is not None
        # Stage 1 無効 → sweep line は全ペアを処理
        bf_set = {(m.itemset, m.dense_start, m.event.event_id, m.relation_type)
                  for m in result.brute_force_results}
        sw_set = {(m.itemset, m.dense_start, m.event.event_id, m.relation_type)
                  for m in result.sweep_results}
        assert bf_set == sw_set

    def test_stage3_disabled(self):
        freq, events = self._make_data()
        config = PipelineConfig(
            epsilon=2, d_0=1,
            stage1_enabled=True, mi_threshold=0.001,
            stage2_enabled=True,
            stage3_enabled=False,
        )
        result = run_pipeline(freq, events, config)
        assert result.significant_relations is None
        assert result.sweep_results is not None

    def test_default_config(self):
        freq, events = self._make_data()
        result = run_pipeline(freq, events)
        assert result.brute_force_results is not None

    def test_brute_force_always_runs(self):
        """Stage 0 は常に実行される（検証用ベースライン）。"""
        freq, events = self._make_data()
        config = PipelineConfig(
            stage1_enabled=False, stage2_enabled=False, stage3_enabled=False,
        )
        result = run_pipeline(freq, events, config)
        assert len(result.brute_force_results) > 0


# ---------------------------------------------------------------------------
# TC-CSV: write_significant_csv
# ---------------------------------------------------------------------------

class TestWriteSignificantCsv:
    def test_header_and_row(self):
        relations = [
            SignificantRelation(
                itemset=(1, 2), event_id="E1",
                relation_type="EventContainsDense",
                observed_count=5, p_value=0.001,
                adjusted_p_value=0.005, effect_size=3.2,
                mi_score=0.15,
            ),
        ]
        with tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False, mode="w"
        ) as f:
            path = f.name
        write_significant_csv(path, relations, epsilon=2, d_0=1)

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["relation_type"] == "EventContainsDense"
        assert rows[0]["observed_count"] == "5"
        assert float(rows[0]["p_value"]) == pytest.approx(0.001, abs=0.0001)
        assert rows[0]["epsilon"] == "2"

    def test_empty_relations(self):
        with tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False, mode="w"
        ) as f:
            path = f.name
        write_significant_csv(path, [], epsilon=0, d_0=0)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1  # ヘッダーのみ

    def test_mi_score_none(self):
        relations = [
            SignificantRelation(
                itemset=(1,), event_id="E1",
                relation_type="DFE",
                observed_count=1, p_value=0.01,
                adjusted_p_value=0.01, effect_size=1.0,
                mi_score=None,
            ),
        ]
        with tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False, mode="w"
        ) as f:
            path = f.name
        write_significant_csv(path, relations, epsilon=0, d_0=0)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[0]["mi_score"] == ""
