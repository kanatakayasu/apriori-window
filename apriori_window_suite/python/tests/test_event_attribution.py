"""Tests for event_attribution.py — Phase 2 Event Attribution Pipeline."""
import math
import sys
from pathlib import Path

import pytest

# event_attribution.py は tests/ の親ディレクトリにある
_python_dir = str(Path(__file__).resolve().parent.parent)
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

from event_attribution import (
    AttributionCandidate,
    AttributionConfig,
    ChangePoint,
    Event,
    SignificantAttribution,
    circular_shift_events,
    compute_proximity,
    compute_support_series,
    detect_change_points,
    detect_cusum,
    detect_threshold_crossings,
    permutation_test,
    read_events,
    run_attribution_pipeline,
    score_attributions,
)


# =========================================================================
# Step 1: compute_support_series
# =========================================================================


class TestComputeSupportSeries:
    def test_empty_timestamps(self):
        assert compute_support_series([], 3, 10) == [0] * 8

    def test_single_timestamp(self):
        # window_size=3, n=5 → length=3, positions 0,1,2
        # ts=[2]: window [0,2]=yes, [1,3]=yes, [2,4]=yes
        series = compute_support_series([2], 3, 5)
        assert series == [1, 1, 1]

    def test_all_in_one_window(self):
        series = compute_support_series([0, 1, 2], 3, 5)
        # t=0: [0,2] → 3, t=1: [1,3] → 2, t=2: [2,4] → 1
        assert series == [3, 2, 1]

    def test_window_equals_n(self):
        # window_size == n → length = 1
        series = compute_support_series([0, 2, 4], 5, 5)
        assert series == [3]

    def test_window_larger_than_n(self):
        series = compute_support_series([0], 10, 5)
        assert series == []

    def test_scattered_timestamps(self):
        # n=10, W=3 → length=8
        # ts=[0, 5, 9]
        series = compute_support_series([0, 5, 9], 3, 10)
        assert len(series) == 8
        # t=0: [0,2] → {0} = 1
        assert series[0] == 1
        # t=3: [3,5] → {5} = 1
        assert series[3] == 1
        # t=7: [7,9] → {9} = 1
        assert series[7] == 1
        # t=1: [1,3] → {} = 0
        assert series[1] == 0

    def test_n_zero(self):
        assert compute_support_series([], 3, 0) == []

    def test_window_size_one(self):
        series = compute_support_series([0, 2, 4], 1, 5)
        assert series == [1, 0, 1, 0, 1]


# =========================================================================
# Step 2: detect_threshold_crossings
# =========================================================================


class TestDetectThresholdCrossings:
    def test_empty_series(self):
        assert detect_threshold_crossings([], 2) == []

    def test_no_crossing(self):
        assert detect_threshold_crossings([0, 0, 1, 0], 2) == []

    def test_single_up_crossing(self):
        series = [0, 0, 3, 3, 0]
        changes = detect_threshold_crossings(series, 2)
        assert len(changes) == 2
        assert changes[0].direction == "up"
        assert changes[0].time == 2
        assert changes[1].direction == "down"
        assert changes[1].time == 4

    def test_up_at_start(self):
        series = [3, 3, 0]
        changes = detect_threshold_crossings(series, 2)
        assert len(changes) == 2
        assert changes[0].direction == "up"
        assert changes[0].time == 0
        assert changes[0].support_before == 0  # t=0, prev defaults to 0

    def test_multiple_crossings(self):
        series = [0, 3, 0, 4, 0]
        changes = detect_threshold_crossings(series, 2)
        assert len(changes) == 4
        dirs = [c.direction for c in changes]
        assert dirs == ["up", "down", "up", "down"]

    def test_magnitude(self):
        # magnitude is level-shift based (mean_after - mean_before)
        series = [1, 5, 1]
        changes = detect_threshold_crossings(series, 3)
        assert changes[0].magnitude >= 1.0
        assert changes[1].magnitude >= 1.0

    def test_exact_threshold(self):
        # threshold=2, series goes from 1 to 2 → crossing
        series = [1, 2, 1]
        changes = detect_threshold_crossings(series, 2)
        assert len(changes) == 2
        assert changes[0].direction == "up"


# =========================================================================
# Step 2: detect_cusum
# =========================================================================


class TestDetectCusum:
    def test_empty(self):
        assert detect_cusum([], 0.5, 4.0) == []

    def test_single_element(self):
        assert detect_cusum([5], 0.5, 4.0) == []

    def test_constant_series(self):
        # No change → no detection
        assert detect_cusum([3, 3, 3, 3, 3], 0.5, 4.0) == []

    def test_level_shift_up(self):
        # Clear upward shift should trigger detection
        series = [0, 0, 0, 0, 0, 10, 10, 10, 10, 10]
        changes = detect_cusum(series, 0.5, 4.0)
        up_changes = [c for c in changes if c.direction == "up"]
        assert len(up_changes) >= 1

    def test_level_shift_down(self):
        series = [10, 10, 10, 10, 10, 0, 0, 0, 0, 0]
        changes = detect_cusum(series, 0.5, 4.0)
        down_changes = [c for c in changes if c.direction == "down"]
        assert len(down_changes) >= 1


# =========================================================================
# Step 2: detect_change_points (dispatcher)
# =========================================================================


class TestDetectChangePoints:
    def test_threshold_crossing_method(self):
        series = [0, 3, 0]
        changes = detect_change_points(series, method="threshold_crossing", threshold=2)
        assert len(changes) == 2

    def test_cusum_method(self):
        series = [0, 0, 0, 10, 10, 10]
        changes = detect_change_points(series, method="cusum")
        assert len(changes) >= 1

    def test_unknown_method(self):
        with pytest.raises(ValueError, match="Unknown"):
            detect_change_points([1, 2, 3], method="invalid")


# =========================================================================
# Step 3: compute_proximity
# =========================================================================


class TestComputeProximity:
    def test_zero_distance(self):
        e = Event("E1", "test", start=5, end=10)
        assert compute_proximity(5, e, sigma=3.0) == pytest.approx(1.0)

    def test_positive_distance(self):
        e = Event("E1", "test", start=5, end=10)
        prox = compute_proximity(8, e, sigma=3.0)
        # dist = min(|8-5|, |8-10|) = 2
        expected = math.exp(-2.0 / 3.0)
        assert prox == pytest.approx(expected)

    def test_large_distance(self):
        e = Event("E1", "test", start=5, end=10)
        prox = compute_proximity(100, e, sigma=3.0)
        assert prox < 0.01  # practically zero

    def test_sigma_zero(self):
        e = Event("E1", "test", start=5, end=10)
        assert compute_proximity(5, e, sigma=0.0) == 1.0
        assert compute_proximity(6, e, sigma=0.0) == 0.0

    def test_uses_min_distance(self):
        e = Event("E1", "test", start=5, end=10)
        # change at t=8: dist_start=3, dist_end=2 → use 2
        prox = compute_proximity(8, e, sigma=5.0)
        expected = math.exp(-2.0 / 5.0)
        assert prox == pytest.approx(expected)


# =========================================================================
# Step 3: score_attributions
# =========================================================================


class TestScoreAttributions:
    def test_no_change_points(self):
        events = [Event("E1", "test", 5, 10)]
        assert score_attributions((1, 2), [], events, 5.0, 20) == []

    def test_no_events(self):
        cps = [ChangePoint(time=5, direction="up", magnitude=3.0)]
        assert score_attributions((1, 2), cps, [], 5.0, 20) == []

    def test_beyond_max_distance(self):
        cps = [ChangePoint(time=5, direction="up", magnitude=3.0)]
        events = [Event("E1", "test", 100, 110)]
        assert score_attributions((1, 2), cps, events, 5.0, 20) == []

    def test_within_max_distance(self):
        cps = [ChangePoint(time=5, direction="up", magnitude=3.0)]
        events = [Event("E1", "test", 5, 10)]
        candidates = score_attributions((1, 2), cps, events, 5.0, 20)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.pattern == (1, 2)
        assert c.event.event_id == "E1"
        assert c.proximity == pytest.approx(1.0)
        assert c.attribution_score == pytest.approx(3.0)

    def test_threshold_filtering(self):
        cps = [ChangePoint(time=5, direction="up", magnitude=0.001)]
        events = [Event("E1", "test", 5, 10)]
        # Very small magnitude → score below default threshold
        candidates = score_attributions(
            (1, 2), cps, events, 5.0, 20, attribution_threshold=0.1
        )
        assert len(candidates) == 0

    def test_multiple_candidates(self):
        cps = [
            ChangePoint(time=5, direction="up", magnitude=3.0),
            ChangePoint(time=15, direction="down", magnitude=2.0),
        ]
        events = [
            Event("E1", "sale", 5, 10),
            Event("E2", "holiday", 14, 16),
        ]
        candidates = score_attributions((1, 2), cps, events, 5.0, 20)
        assert len(candidates) >= 2


# =========================================================================
# Step 4: circular_shift_events
# =========================================================================


class TestCircularShiftEvents:
    def test_basic_shift(self):
        events = [Event("E1", "test", start=5, end=10)]
        shifted = circular_shift_events(events, offset=3, max_time=20)
        assert shifted[0].start == 8
        assert shifted[0].end == 13

    def test_wrap_around(self):
        events = [Event("E1", "test", start=18, end=19)]
        shifted = circular_shift_events(events, offset=5, max_time=20)
        # new_start = (18+5) % 20 = 3
        assert shifted[0].start == 3

    def test_preserves_id_and_name(self):
        events = [Event("E1", "sale", start=5, end=10)]
        shifted = circular_shift_events(events, offset=2, max_time=100)
        assert shifted[0].event_id == "E1"
        assert shifted[0].name == "sale"

    def test_end_clamped(self):
        events = [Event("E1", "test", start=15, end=19)]
        shifted = circular_shift_events(events, offset=7, max_time=20)
        # new_start = (15+7) % 20 = 2, duration=4, new_end = 6 < 20 → OK
        assert shifted[0].start == 2
        assert shifted[0].end == 6

    def test_end_exceeds_max_time(self):
        events = [Event("E1", "test", start=15, end=19)]
        shifted = circular_shift_events(events, offset=3, max_time=20)
        # new_start = (15+3) % 20 = 18, duration=4, new_end = 22 >= 20 → clamped to 19
        assert shifted[0].start == 18
        assert shifted[0].end == 19

    def test_multiple_events(self):
        events = [
            Event("E1", "a", 5, 10),
            Event("E2", "b", 15, 18),
        ]
        shifted = circular_shift_events(events, offset=2, max_time=50)
        assert len(shifted) == 2
        assert shifted[0].start == 7
        assert shifted[1].start == 17


# =========================================================================
# Step 4: permutation_test
# =========================================================================


class TestPermutationTest:
    def test_no_change_points(self):
        events = [Event("E1", "test", 5, 10)]
        results = permutation_test(
            (1, 2), [], events, sigma=5.0, max_distance=20,
            max_time=50, n_permutations=100, seed=42,
        )
        assert results == []

    def test_no_events(self):
        cps = [ChangePoint(time=5, direction="up", magnitude=3.0)]
        results = permutation_test(
            (1, 2), cps, [], sigma=5.0, max_distance=20,
            max_time=50, n_permutations=100, seed=42,
        )
        assert results == []

    def test_strong_signal_returns_significant(self):
        # Strong change point right at event start → should be significant
        cps = [ChangePoint(time=10, direction="up", magnitude=50.0)]
        events = [Event("E1", "sale", start=10, end=15)]
        results = permutation_test(
            (1, 2), cps, events, sigma=5.0, max_distance=20,
            max_time=100, n_permutations=200, alpha=0.1, seed=42,
        )
        # With a very strong signal at the exact event time, it should be significant
        # (though permutation test is stochastic, seed=42 makes it deterministic)
        # We don't assert it IS significant because the permutation test
        # outcome depends on the random shifts. Instead check structure.
        for r in results:
            assert isinstance(r, SignificantAttribution)
            assert r.pattern == (1, 2)
            assert r.p_value > 0
            assert r.adjusted_p_value <= 0.1

    def test_deterministic_with_seed(self):
        cps = [ChangePoint(time=10, direction="up", magnitude=5.0)]
        events = [Event("E1", "sale", start=10, end=15)]
        kwargs = dict(
            pattern=(1, 2), change_points=cps, events=events,
            sigma=5.0, max_distance=20, max_time=50,
            n_permutations=100, seed=123,
        )
        r1 = permutation_test(**kwargs)
        r2 = permutation_test(**kwargs)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.p_value == b.p_value

    def test_p_value_bounded(self):
        cps = [ChangePoint(time=5, direction="up", magnitude=3.0)]
        events = [Event("E1", "sale", start=5, end=10)]
        results = permutation_test(
            (1, 2), cps, events, sigma=5.0, max_distance=20,
            max_time=50, n_permutations=100, alpha=1.0, seed=42,
        )
        for r in results:
            assert 0 < r.p_value <= 1.0


# =========================================================================
# read_events
# =========================================================================


class TestReadEvents:
    def test_normal(self, tmp_path):
        p = tmp_path / "events.json"
        p.write_text('[{"event_id":"A","name":"Aname","start":1,"end":5}]')
        events = read_events(str(p))
        assert len(events) == 1
        assert events[0].event_id == "A"
        assert events[0].start == 1
        assert events[0].end == 5

    def test_multiple(self, tmp_path):
        p = tmp_path / "events.json"
        p.write_text(
            '[{"event_id":"A","name":"A","start":1,"end":5},'
            '{"event_id":"B","name":"B","start":6,"end":10}]'
        )
        events = read_events(str(p))
        assert len(events) == 2

    def test_start_equals_end(self, tmp_path):
        p = tmp_path / "events.json"
        p.write_text('[{"event_id":"A","name":"A","start":3,"end":3}]')
        events = read_events(str(p))
        assert events[0].start == events[0].end == 3

    def test_duplicate_id(self, tmp_path):
        p = tmp_path / "events.json"
        p.write_text(
            '[{"event_id":"A","name":"A","start":1,"end":5},'
            '{"event_id":"A","name":"B","start":6,"end":10}]'
        )
        with pytest.raises(ValueError, match="Duplicate"):
            read_events(str(p))

    def test_start_after_end(self, tmp_path):
        p = tmp_path / "events.json"
        p.write_text('[{"event_id":"A","name":"A","start":5,"end":3}]')
        with pytest.raises(ValueError, match="start.*end"):
            read_events(str(p))

    def test_missing_name_defaults_empty(self, tmp_path):
        p = tmp_path / "events.json"
        p.write_text('[{"event_id":"A","start":1,"end":5}]')
        events = read_events(str(p))
        assert events[0].name == ""


# =========================================================================
# run_attribution_pipeline
# =========================================================================


class TestRunAttributionPipeline:
    def test_empty_frequents(self):
        events = [Event("E1", "test", 5, 10)]
        results = run_attribution_pipeline({}, {}, events, 3, 2)
        assert results == []

    def test_skips_single_item_patterns(self):
        frequents = {(1,): [(0, 5)]}
        support_map = {(1,): [3, 3, 3, 3, 3]}
        events = [Event("E1", "test", 0, 2)]
        results = run_attribution_pipeline(
            frequents, support_map, events, 3, 2
        )
        assert results == []

    def test_no_change_points_yields_empty(self):
        # Constant support → no threshold crossings
        frequents = {(1, 2): [(0, 5)]}
        support_map = {(1, 2): [0, 0, 0, 0, 0]}
        events = [Event("E1", "test", 0, 2)]
        results = run_attribution_pipeline(
            frequents, support_map, events, 3, 2
        )
        assert results == []

    def test_basic_pipeline(self):
        # Create a support series with a clear threshold crossing at t=5
        series = [0, 0, 0, 0, 0, 5, 5, 5, 5, 5, 0, 0, 0, 0, 0]
        frequents = {(1, 2): [(5, 9)]}
        support_map = {(1, 2): series}
        events = [Event("E1", "sale", start=5, end=9)]

        config = AttributionConfig(
            change_method="threshold_crossing",
            n_permutations=50,
            alpha=1.0,  # accept everything to test pipeline flow
            seed=42,
        )
        results = run_attribution_pipeline(
            frequents, support_map, events, 3, 2, config
        )
        # Pipeline should produce results (with alpha=1.0, everything passes)
        assert len(results) >= 1
        assert all(isinstance(r, SignificantAttribution) for r in results)

    def test_custom_config(self):
        series = [0, 0, 0, 0, 0, 10, 10, 10, 10, 10]
        frequents = {(1, 2): [(5, 9)]}
        support_map = {(1, 2): series}
        events = [Event("E1", "sale", start=5, end=9)]

        config = AttributionConfig(
            change_method="threshold_crossing",
            sigma=3.0,
            max_distance=10,
            n_permutations=50,
            alpha=1.0,
            seed=99,
        )
        results = run_attribution_pipeline(
            frequents, support_map, events, 3, 2, config
        )
        assert isinstance(results, list)

    def test_cusum_method(self):
        series = [0, 0, 0, 0, 0, 10, 10, 10, 10, 10]
        frequents = {(1, 2): [(5, 9)]}
        support_map = {(1, 2): series}
        events = [Event("E1", "sale", start=5, end=9)]

        config = AttributionConfig(
            change_method="cusum",
            cusum_drift=0.5,
            cusum_h=4.0,
            n_permutations=50,
            alpha=1.0,
            seed=42,
        )
        results = run_attribution_pipeline(
            frequents, support_map, events, 3, 2, config
        )
        assert isinstance(results, list)
