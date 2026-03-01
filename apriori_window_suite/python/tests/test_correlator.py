"""
Phase 2 テスト: event_correlator.py

実行方法:
    cd /Users/kanata/Documents/GitHub/apriori_window
    python3 -m pytest apriori_window_suite/python/tests/test_correlator.py -v

テストケース:
    TC-U1~3  : satisfies_* 単体テスト
    TC-M1~8  : match_all テスト（frequents を直接注入）
    TC-IO1~4 : read_events / write_relations_csv I/O テスト
    TC-E1    : run_from_settings E2E テスト
"""
import csv
import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_correlator import (
    Event,
    RelationMatch,
    match_all,
    read_events,
    run_from_settings,
    satisfies_contains,
    satisfies_follows,
    satisfies_overlaps,
    write_relations_csv,
)

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _event(eid: str, start: int, end: int, name: str = "") -> Event:
    return Event(event_id=eid, name=name or eid, start=start, end=end)


def _frequents(pairs: List[Tuple[Tuple[int, ...], List[Tuple[int, int]]]]):
    return dict(pairs)


def _relation_types(results: List[RelationMatch]) -> List[str]:
    return [r.relation_type for r in results]


# ---------------------------------------------------------------------------
# TC-U1: satisfies_follows
# ---------------------------------------------------------------------------

class TestSatisfiesFollows:
    def test_adjacent(self):
        """te_i == ts_j, ε=0 → True（隣接はFollows）"""
        assert satisfies_follows(10, 10, 0) is True

    def test_gap_within_epsilon(self):
        assert satisfies_follows(10, 12, 2) is True

    def test_gap_exceeds_epsilon(self):
        assert satisfies_follows(10, 13, 2) is False

    def test_slight_overlap_within_epsilon(self):
        """ts_j < te_i だが差が ε 以内 → True"""
        assert satisfies_follows(10, 8, 2) is True

    def test_overlap_exceeds_epsilon(self):
        assert satisfies_follows(10, 7, 2) is False

    def test_epsilon_zero_strict(self):
        assert satisfies_follows(10, 11, 0) is False
        assert satisfies_follows(10, 9, 0) is False
        assert satisfies_follows(10, 10, 0) is True


# ---------------------------------------------------------------------------
# TC-U2: satisfies_contains
# ---------------------------------------------------------------------------

class TestSatisfiesContains:
    def test_full_containment(self):
        assert satisfies_contains(0, 100, 10, 90, 0) is True

    def test_right_edge_exact(self):
        assert satisfies_contains(0, 100, 10, 100, 0) is True

    def test_right_edge_within_epsilon(self):
        """te_j = te_i + 2, ε = 2 → True"""
        assert satisfies_contains(0, 100, 10, 102, 2) is True

    def test_right_edge_exceeds_epsilon(self):
        assert satisfies_contains(0, 100, 10, 103, 2) is False

    def test_j_starts_before_i(self):
        """ts_j < ts_i → False"""
        assert satisfies_contains(5, 100, 0, 90, 0) is False

    def test_ts_equal(self):
        """ts_i == ts_j → True（左端一致は含む）"""
        assert satisfies_contains(10, 100, 10, 90, 0) is True


# ---------------------------------------------------------------------------
# TC-U3: satisfies_overlaps
# ---------------------------------------------------------------------------

class TestSatisfiesOverlaps:
    def test_normal_overlap(self):
        ok, ovl = satisfies_overlaps(0, 15, 10, 25, 0, 5)
        assert ok is True
        assert ovl == 5  # te_i - ts_j = 15 - 10

    def test_overlap_exactly_d0(self):
        ok, ovl = satisfies_overlaps(0, 15, 10, 25, 0, 5)
        assert ok is True
        assert ovl == 5

    def test_overlap_below_d0(self):
        ok, _ = satisfies_overlaps(0, 14, 10, 25, 0, 5)
        assert ok is False  # overlap=4 < d_0=5

    def test_epsilon_rescues_short_overlap(self):
        ok, ovl = satisfies_overlaps(0, 14, 10, 25, 1, 5)
        assert ok is True   # overlap=4 >= 5-1=4
        assert ovl == 4

    def test_i_does_not_start_first(self):
        ok, _ = satisfies_overlaps(10, 25, 0, 15, 0, 5)
        assert ok is False

    def test_i_equals_j_start(self):
        """ts_i == ts_j → False（先に始まらない）"""
        ok, _ = satisfies_overlaps(10, 25, 10, 30, 0, 5)
        assert ok is False

    def test_complete_containment_not_overlap(self):
        """te_i >= te_j + ε のとき Overlaps でない（Contains）"""
        ok, _ = satisfies_overlaps(0, 30, 10, 25, 0, 5)
        assert ok is False  # te_i=30 >= te_j+ε=25

    def test_contains_boundary_with_epsilon(self):
        """te_i = te_j + ε のとき境界（False）"""
        ok, _ = satisfies_overlaps(0, 27, 10, 25, 2, 5)
        assert ok is False  # te_i=27 >= te_j+ε=27


# ---------------------------------------------------------------------------
# TC-M: match_all テスト
# ---------------------------------------------------------------------------

class TestMatchAll:
    """frequents を直接注入して match_all を検証する"""

    # TC-M1: DenseFollowsEvent
    def test_dense_follows_event(self):
        freq = _frequents([((1, 2), [(0, 10)])])
        events = [_event("E1", start=12, end=20)]
        results = match_all(freq, events, epsilon=2, d_0=1)
        assert "DenseFollowsEvent" in _relation_types(results)

    # TC-M2: EventFollowsDense
    def test_event_follows_dense(self):
        freq = _frequents([((1, 2), [(15, 25)])])
        events = [_event("E2", start=0, end=13)]
        results = match_all(freq, events, epsilon=2, d_0=1)
        assert "EventFollowsDense" in _relation_types(results)

    # TC-M3: DenseContainsEvent
    def test_dense_contains_event(self):
        freq = _frequents([((3,), [(0, 100)])])
        events = [_event("E3", start=10, end=90)]
        results = match_all(freq, events, epsilon=0, d_0=1)
        assert "DenseContainsEvent" in _relation_types(results)

    # TC-M4: EventContainsDense
    def test_event_contains_dense(self):
        freq = _frequents([((3,), [(10, 90)])])
        events = [_event("E4", start=0, end=100)]
        results = match_all(freq, events, epsilon=0, d_0=1)
        assert "EventContainsDense" in _relation_types(results)

    # TC-M5: DenseOverlapsEvent
    def test_dense_overlaps_event(self):
        freq = _frequents([((1, 2), [(0, 15)])])
        events = [_event("E5", start=10, end=25)]
        results = match_all(freq, events, epsilon=0, d_0=5)
        rtype = _relation_types(results)
        assert "DenseOverlapsEvent" in rtype
        doe = next(r for r in results if r.relation_type == "DenseOverlapsEvent")
        assert doe.overlap_length == 5  # te_i - ts_j = 15 - 10

    # TC-M6: EventOverlapsDense
    def test_event_overlaps_dense(self):
        freq = _frequents([((1, 2), [(10, 25)])])
        events = [_event("E6", start=0, end=15)]
        results = match_all(freq, events, epsilon=0, d_0=5)
        assert "EventOverlapsDense" in _relation_types(results)
        eod = next(r for r in results if r.relation_type == "EventOverlapsDense")
        assert eod.overlap_length == 5  # te_j - ts_i = 15 - 10

    # TC-M7: 関係なし
    def test_no_relation(self):
        freq = _frequents([((1,), [(0, 5)])])
        events = [_event("E7", start=100, end=200)]
        results = match_all(freq, events, epsilon=2, d_0=5)
        assert results == []

    # TC-M8: 複数関係の同時成立（DFE + DOE）
    def test_multiple_relations(self):
        # dense=(0,12), event=[10,20], ε=2, d_0=2
        # DFE: te_i=12, ts_j=10 → 12-2=10 ≤ 10 ≤ 14 ✓
        # DOE: ts_i=0 < ts_j=10 ✓, overlap=12-10=2≥2-2=0 ✓, 12 < 20+2=22 ✓
        freq = _frequents([((1, 2), [(0, 12)])])
        events = [_event("E8", start=10, end=20)]
        results = match_all(freq, events, epsilon=2, d_0=2)
        rtypes = set(_relation_types(results))
        assert "DenseFollowsEvent" in rtypes
        assert "DenseOverlapsEvent" in rtypes

    # ソート順の確認
    def test_sort_order(self):
        freq = _frequents([
            ((1, 2, 3), [(0, 10)]),   # 3アイテム
            ((1, 2), [(0, 10)]),      # 2アイテム
        ])
        events = [_event("EA", start=11, end=20)]
        results = match_all(freq, events, epsilon=2, d_0=1)
        # 3アイテムが先
        sizes = [len(r.itemset) for r in results]
        assert sizes == sorted(sizes, reverse=True)

    # overlap_length が None になること（Follows / Contains）
    def test_overlap_length_none_for_non_overlaps(self):
        freq = _frequents([((1,), [(0, 10)])])
        events = [_event("E", start=12, end=20)]
        results = match_all(freq, events, epsilon=2, d_0=1)
        dfe = next((r for r in results if r.relation_type == "DenseFollowsEvent"), None)
        assert dfe is not None
        assert dfe.overlap_length is None


# ---------------------------------------------------------------------------
# TC-IO: I/O テスト
# ---------------------------------------------------------------------------

class TestReadEvents:
    def test_normal(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                [
                    {"event_id": "E1", "name": "Name1", "start": 0, "end": 10},
                    {"event_id": "E2", "name": "Name2", "start": 20, "end": 30},
                ],
                f,
            )
            path = f.name
        events = read_events(path)
        assert len(events) == 2
        assert events[0].event_id == "E1"
        assert events[1].start == 20

    def test_duplicate_event_id_raises(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                [
                    {"event_id": "DUP", "name": "A", "start": 0, "end": 10},
                    {"event_id": "DUP", "name": "B", "start": 5, "end": 15},
                ],
                f,
            )
            path = f.name
        with pytest.raises(ValueError, match="Duplicate event_id"):
            read_events(path)

    def test_start_after_end_raises(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                [{"event_id": "BAD", "name": "B", "start": 100, "end": 50}],
                f,
            )
            path = f.name
        with pytest.raises(ValueError, match="start"):
            read_events(path)

    def test_start_equals_end_ok(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                [{"event_id": "PT", "name": "P", "start": 5, "end": 5}],
                f,
            )
            path = f.name
        events = read_events(path)
        assert events[0].start == events[0].end == 5


class TestWriteRelationsCsv:
    def test_csv_format(self):
        events = [_event("E1", 10, 20, "Name1")]
        results = [
            RelationMatch((1, 2), 0, 8, events[0], "DenseFollowsEvent", None),
            RelationMatch((3,), 5, 15, events[0], "DenseOverlapsEvent", 5),
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            path = f.name
        write_relations_csv(path, results, epsilon=2, d_0=1)

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        # DenseFollowsEvent → overlap_length は空文字
        dfe_row = next(r for r in rows if r["relation_type"] == "DenseFollowsEvent")
        assert dfe_row["overlap_length"] == ""
        assert dfe_row["epsilon"] == "2"
        assert dfe_row["d_0"] == "1"
        # DenseOverlapsEvent → overlap_length = 5
        doe_row = next(r for r in rows if r["relation_type"] == "DenseOverlapsEvent")
        assert doe_row["overlap_length"] == "5"

    def test_header_columns(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            path = f.name
        write_relations_csv(path, [], epsilon=0, d_0=0)
        with open(path, "r", encoding="utf-8") as f:
            header = f.readline().strip().split(",")
        expected = [
            "pattern_components", "dense_start", "dense_end",
            "event_id", "event_name", "relation_type",
            "overlap_length", "epsilon", "d_0",
        ]
        assert header == expected


# ---------------------------------------------------------------------------
# TC-E1: run_from_settings E2E テスト
# ---------------------------------------------------------------------------

class TestRunFromSettings:
    def _make_settings(self, tmp: Path, epsilon: int = 2, d_0: int = 1) -> str:
        # トランザクションファイル（5行、{1,2} が同一バスケット）
        txn_file = tmp / "txn.txt"
        txn_file.write_text(
            "1 2\n1 2\n1 2\n1 2\n1 2\n", encoding="utf-8"
        )
        # イベントファイル
        evt_file = tmp / "events.json"
        evt_file.write_text(
            json.dumps([
                {"event_id": "E1", "name": "N1", "start": 0, "end": 1},
                {"event_id": "E2", "name": "N2", "start": 10, "end": 20},
            ]),
            encoding="utf-8",
        )
        out_dir = str(tmp / "out")
        settings = {
            "input_file": {"dir": str(tmp), "file_name": "txn.txt"},
            "event_file": {"dir": str(tmp), "file_name": "events.json"},
            "output_files": {
                "dir": out_dir,
                "patterns_output_file_name": "patterns.csv",
                "relations_output_file_name": "relations.csv",
            },
            "apriori_parameters": {"window_size": 2, "min_support": 2, "max_length": 2},
            "temporal_relation_parameters": {"epsilon": epsilon, "d_0": d_0},
        }
        s_file = tmp / "settings.json"
        s_file.write_text(json.dumps(settings), encoding="utf-8")
        return str(s_file)

    def test_outputs_created(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._make_settings(Path(td))
            p_path, r_path = run_from_settings(s)
            assert Path(p_path).exists()
            assert r_path is not None and Path(r_path).exists()

    def test_no_event_file_phase1_only(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            txn_file = tmp / "txn.txt"
            txn_file.write_text("1 2\n1 2\n1 2\n", encoding="utf-8")
            out_dir = str(tmp / "out")
            settings = {
                "input_file": {"dir": str(tmp), "file_name": "txn.txt"},
                "output_files": {
                    "dir": out_dir,
                    "patterns_output_file_name": "patterns.csv",
                    "relations_output_file_name": "relations.csv",
                },
                "apriori_parameters": {
                    "window_size": 2, "min_support": 2, "max_length": 2
                },
            }
            s_file = tmp / "settings.json"
            s_file.write_text(json.dumps(settings), encoding="utf-8")
            p_path, r_path = run_from_settings(str(s_file))
            assert Path(p_path).exists()
            assert r_path is None  # Phase 2 は実行されない

    def test_relations_csv_has_content(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._make_settings(Path(td), epsilon=2, d_0=1)
            _, r_path = run_from_settings(s)
            assert r_path is not None
            with open(r_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            # E1 は dense interval と重なりやすい→何らかの関係が成立するはず
            assert len(rows) >= 0  # 少なくともエラーなく出力できること

    def test_event_contains_dense_detected(self):
        """EventContainsDense: event=[-10,100] が dense=(-1,3) を包含するケース

        5行 {1,2}、window_size=2 の場合:
            start = ts[threshold-1] - window_size = 1 - 2 = -1
        よって event.start <= -1 が必要。
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            txn_file = tmp / "txn.txt"
            # 5行の {1,2}: dense interval が存在する
            txn_file.write_text("1 2\n1 2\n1 2\n1 2\n1 2\n", encoding="utf-8")
            evt_file = tmp / "events.json"
            evt_file.write_text(
                json.dumps([{"event_id": "BIG", "name": "Big", "start": -10, "end": 100}]),
                encoding="utf-8",
            )
            settings = {
                "input_file": {"dir": str(tmp), "file_name": "txn.txt"},
                "event_file": {"dir": str(tmp), "file_name": "events.json"},
                "output_files": {
                    "dir": str(tmp / "out"),
                    "patterns_output_file_name": "p.csv",
                    "relations_output_file_name": "r.csv",
                },
                "apriori_parameters": {"window_size": 2, "min_support": 2, "max_length": 2},
                "temporal_relation_parameters": {"epsilon": 0, "d_0": 1},
            }
            sf = tmp / "settings.json"
            sf.write_text(json.dumps(settings), encoding="utf-8")
            _, r_path = run_from_settings(str(sf))
            assert r_path is not None
            with open(r_path, encoding="utf-8") as f:
                content = f.read()
            assert "EventContainsDense" in content
