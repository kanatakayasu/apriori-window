"""
Tests for Paper L (Manufacturing) implementation.

40 test cases covering:
- AlarmAdapter: encoding/decoding, transaction generation
- Dense interval computation: edge cases, stack-case
- Manufacturing dense miner: pattern detection
- Maintenance contrast: Welch t-test, BH correction, classification
- Synthetic data: generation, ground truth
"""

import sys
from pathlib import Path

# Add implementation to path
impl_dir = str(Path(__file__).resolve().parent.parent)
if impl_dir not in sys.path:
    sys.path.insert(0, impl_dir)

import pytest
from alarm_adapter import (
    AlarmAdapter,
    ALARM_CATALOG,
    get_all_alarm_types,
    get_equipment_group,
)
from manufacturing_dense_miner import (
    compute_dense_intervals,
    compute_dense_intervals_with_candidates,
    compute_item_transaction_map,
    compute_support_time_series,
    find_dense_alarm_patterns,
    intersect_sorted_lists,
    intersect_interval_lists,
    generate_candidates,
    prune_candidates,
)
from maintenance_contrast import (
    MaintenanceEvent,
    ContrastResult,
    compute_density_change,
    welch_t_test,
    benjamini_hochberg,
    run_contrast_analysis,
    summarize_results,
)
from synthetic_manufacturing_data import (
    SyntheticManufacturingConfig,
    FaultScenario,
    create_default_config,
    generate_synthetic_alarms,
    generate_transactions,
)


# ===================================================================
# AlarmAdapter tests
# ===================================================================

class TestAlarmAdapter:
    def test_encode_decode_roundtrip(self):
        adapter = AlarmAdapter()
        alarm_id = adapter.encode_alarm("ETCH_TEMP_HIGH")
        assert adapter.decode_alarm(alarm_id) == "ETCH_TEMP_HIGH"

    def test_encode_same_alarm_twice(self):
        adapter = AlarmAdapter()
        id1 = adapter.encode_alarm("CVD_PRESSURE")
        id2 = adapter.encode_alarm("CVD_PRESSURE")
        assert id1 == id2

    def test_encode_different_alarms(self):
        adapter = AlarmAdapter()
        id1 = adapter.encode_alarm("ETCH_TEMP_HIGH")
        id2 = adapter.encode_alarm("CVD_TEMP_HIGH")
        assert id1 != id2

    def test_decode_unknown_raises(self):
        adapter = AlarmAdapter()
        with pytest.raises(KeyError):
            adapter.decode_alarm(999)

    def test_decode_pattern(self):
        adapter = AlarmAdapter()
        id1 = adapter.encode_alarm("ETCH_TEMP_HIGH")
        id2 = adapter.encode_alarm("ETCH_PRESSURE")
        decoded = adapter.decode_pattern((id1, id2))
        assert decoded == ("ETCH_TEMP_HIGH", "ETCH_PRESSURE")

    def test_alarm_log_to_transactions_empty(self):
        adapter = AlarmAdapter()
        txns, n = adapter.alarm_log_to_transactions([])
        assert txns == []
        assert n == 0

    def test_alarm_log_to_transactions_basic(self):
        adapter = AlarmAdapter(time_bin_seconds=10)
        log = [
            ("ETCH_TEMP_HIGH", 0),
            ("ETCH_PRESSURE", 5),
            ("CVD_TEMP_HIGH", 15),
        ]
        txns, n = adapter.alarm_log_to_transactions(log)
        assert n == 2
        assert len(txns) == 2
        # First bin has both ETCH alarms
        assert len(txns[0][0]) == 2
        # Second bin has CVD alarm
        assert len(txns[1][0]) == 1

    def test_alarm_log_dedup_within_bin(self):
        adapter = AlarmAdapter(time_bin_seconds=100)
        log = [
            ("ETCH_TEMP_HIGH", 0),
            ("ETCH_TEMP_HIGH", 50),
        ]
        txns, n = adapter.alarm_log_to_transactions(log)
        assert len(txns[0][0]) == 1  # Deduplicated

    def test_get_equipment_groups(self):
        adapter = AlarmAdapter()
        id1 = adapter.encode_alarm("ETCH_TEMP_HIGH")
        id2 = adapter.encode_alarm("CVD_PRESSURE")
        groups = adapter.get_equipment_groups((id1, id2))
        assert "ETCH" in groups
        assert "CVD" in groups

    def test_time_bin_validation(self):
        with pytest.raises(ValueError):
            AlarmAdapter(time_bin_seconds=0)


# ===================================================================
# Alarm catalog tests
# ===================================================================

class TestAlarmCatalog:
    def test_all_alarm_types_not_empty(self):
        assert len(get_all_alarm_types()) > 0

    def test_equipment_group_lookup(self):
        assert get_equipment_group("ETCH_TEMP_HIGH") == "ETCH"
        assert get_equipment_group("CVD_PRESSURE") == "CVD"
        assert get_equipment_group("NONEXISTENT") is None

    def test_catalog_has_expected_groups(self):
        expected = {"ETCH", "CVD", "LITHO", "CMP", "IMPLANT", "INSPECT", "GENERAL"}
        assert set(ALARM_CATALOG.keys()) == expected


# ===================================================================
# Dense interval tests
# ===================================================================

class TestDenseIntervals:
    def test_empty_timestamps(self):
        assert compute_dense_intervals([], 5, 3) == []

    def test_single_dense_interval(self):
        ts = [0, 1, 2, 3, 4]
        result = compute_dense_intervals(ts, 3, 3)
        assert len(result) >= 1

    def test_no_dense_region(self):
        ts = [0, 100, 200]
        result = compute_dense_intervals(ts, 5, 3)
        assert result == []

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            compute_dense_intervals([1, 2, 3], 0, 1)
        with pytest.raises(ValueError):
            compute_dense_intervals([1, 2, 3], 1, 0)

    def test_stack_case(self):
        """Stack case: window_occurrences[surplus] == l."""
        ts = [0, 0, 0, 1, 1, 1]
        result = compute_dense_intervals(ts, 2, 3)
        assert len(result) >= 1

    def test_with_candidates(self):
        ts = [0, 1, 2, 3, 10, 11, 12, 13]
        result = compute_dense_intervals_with_candidates(
            ts, 3, 3, [(0, 5)]
        )
        assert len(result) >= 1

    def test_with_candidates_empty(self):
        assert compute_dense_intervals_with_candidates([], 3, 3, [(0, 5)]) == []
        assert compute_dense_intervals_with_candidates([1], 3, 3, []) == []


# ===================================================================
# Utility function tests
# ===================================================================

class TestUtilities:
    def test_intersect_sorted_lists(self):
        result = intersect_sorted_lists([[1, 2, 3, 4], [2, 3, 4, 5]])
        assert result == [2, 3, 4]

    def test_intersect_sorted_lists_empty(self):
        assert intersect_sorted_lists([]) == []
        assert intersect_sorted_lists([[1, 2], [3, 4]]) == []

    def test_intersect_interval_lists(self):
        result = intersect_interval_lists([[(0, 10), (20, 30)], [(5, 25)]])
        assert (5, 10) in result
        assert (20, 25) in result

    def test_intersect_interval_lists_empty(self):
        assert intersect_interval_lists([]) == []

    def test_generate_candidates(self):
        prev = [(1,), (2,), (3,)]
        result = generate_candidates(prev, 2)
        assert (1, 2) in result
        assert (1, 3) in result
        assert (2, 3) in result

    def test_prune_candidates(self):
        candidates = [(1, 2, 3)]
        prev_set = {(1, 2), (1, 3), (2, 3)}
        result = prune_candidates(candidates, prev_set)
        assert (1, 2, 3) in result

    def test_prune_removes_invalid(self):
        candidates = [(1, 2, 3)]
        prev_set = {(1, 2), (1, 3)}  # missing (2,3)
        result = prune_candidates(candidates, prev_set)
        assert result == []


# ===================================================================
# Manufacturing dense miner tests
# ===================================================================

class TestManufacturingDenseMiner:
    def test_item_transaction_map(self):
        txns = [[[1, 2]], [[2, 3]], [[1, 3]]]
        item_map = compute_item_transaction_map(txns)
        assert item_map[1] == [0, 2]
        assert item_map[2] == [0, 1]
        assert item_map[3] == [1, 2]

    def test_support_time_series(self):
        ts = [0, 1, 2, 5, 6]
        result = compute_support_time_series(ts, 8, 2)
        assert result[0] == 3  # [0,2] contains 0,1,2
        assert result[5] == 2  # [5,7] contains 5,6

    def test_find_dense_patterns_basic(self):
        # Dense region with items 1,2 co-occurring
        txns = []
        for t in range(50):
            if 10 <= t <= 30:
                txns.append([[1, 2, 3]])
            else:
                txns.append([[]])
        result = find_dense_alarm_patterns(txns, 5, 4, 3)
        # Should find patterns involving items 1, 2, 3
        assert len(result) > 0

    def test_find_dense_patterns_empty(self):
        txns = [[[]] for _ in range(10)]
        result = find_dense_alarm_patterns(txns, 3, 5, 3)
        assert len(result) == 0


# ===================================================================
# Maintenance contrast tests
# ===================================================================

class TestMaintenanceContrast:
    def test_density_change_resolved(self):
        # High pre, low post -> resolved
        series = [5] * 50 + [0] * 50
        pre, post, delta = compute_density_change(series, 50, 30)
        assert pre > post
        assert delta < 0

    def test_density_change_introduced(self):
        # Low pre, high post -> introduced
        series = [0] * 50 + [5] * 50
        pre, post, delta = compute_density_change(series, 50, 30)
        assert post > pre
        assert delta > 0

    def test_density_change_stable(self):
        series = [3] * 100
        pre, post, delta = compute_density_change(series, 50, 30)
        assert abs(delta) < 0.01

    def test_density_change_empty(self):
        pre, post, delta = compute_density_change([], 50, 30)
        assert pre == 0.0 and post == 0.0

    def test_welch_t_test_significant(self):
        pre = [10.0] * 30
        post = [0.0] * 30
        p = welch_t_test(pre, post)
        assert p < 0.01

    def test_welch_t_test_not_significant(self):
        pre = [5.0, 5.1, 4.9, 5.0, 5.1]
        post = [5.0, 4.9, 5.1, 5.0, 4.9]
        p = welch_t_test(pre, post)
        assert p > 0.05

    def test_welch_t_test_degenerate(self):
        assert welch_t_test([1.0], [2.0]) == 1.0
        assert welch_t_test([], []) == 1.0

    def test_benjamini_hochberg_all_significant(self):
        p_values = [0.001, 0.002, 0.003]
        result = benjamini_hochberg(p_values, 0.05)
        assert all(result)

    def test_benjamini_hochberg_none_significant(self):
        p_values = [0.9, 0.8, 0.7]
        result = benjamini_hochberg(p_values, 0.05)
        assert not any(result)

    def test_benjamini_hochberg_empty(self):
        assert benjamini_hochberg([], 0.05) == []

    def test_summarize_results(self):
        results = [
            ContrastResult((1, 2), "M1", 100, 5.0, 1.0, -4.0, 0.001, "resolved", True),
            ContrastResult((3, 4), "M2", 200, 1.0, 5.0, 4.0, 0.001, "introduced", False),
            ContrastResult((5, 6), "M3", 300, 3.0, 3.0, 0.0, 0.5, "stable", False),
        ]
        summary = summarize_results(results)
        assert summary["resolved"] == 1
        assert summary["introduced"] == 1
        assert summary["stable"] == 1
        assert summary["total"] == 3


# ===================================================================
# Synthetic data tests
# ===================================================================

class TestSyntheticData:
    def test_default_config(self):
        config = create_default_config()
        assert config.n_time_bins == 2000
        assert len(config.fault_scenarios) == 5
        assert len(config.maintenance_events) == 5

    def test_generate_alarms(self):
        config = create_default_config()
        alarm_log, gt = generate_synthetic_alarms(config)
        assert len(alarm_log) > 0
        assert len(gt) == 5
        # Check sorted by time
        times = [t for _, t in alarm_log]
        assert times == sorted(times)

    def test_generate_transactions(self):
        config = SyntheticManufacturingConfig(
            n_time_bins=100,
            seed=42,
            base_alarm_prob=0.05,
            fault_scenarios=[
                FaultScenario("F1", ["ETCH_TEMP_HIGH", "ETCH_PRESSURE"],
                              20, 50, 0.6),
            ],
            maintenance_events=[
                MaintenanceEvent("M1", 50, "scheduled_maintenance", "ETCH"),
            ],
        )
        txns, adapter, events, gt = generate_transactions(config)
        assert len(txns) == 100
        assert len(events) == 1
        assert "F1" in gt

    def test_fault_injection_increases_alarms(self):
        """Verify fault injection creates more alarms in fault region."""
        config = SyntheticManufacturingConfig(
            n_time_bins=200,
            seed=42,
            base_alarm_prob=0.01,
            fault_scenarios=[
                FaultScenario("F1", ["ETCH_TEMP_HIGH"], 50, 150, 0.8),
            ],
        )
        alarm_log, _ = generate_synthetic_alarms(config)
        fault_alarms = [
            (a, t) for a, t in alarm_log
            if a == "ETCH_TEMP_HIGH" and 50 <= t < 150
        ]
        normal_alarms = [
            (a, t) for a, t in alarm_log
            if a == "ETCH_TEMP_HIGH" and t < 50
        ]
        # Fault region should have many more alarms per bin
        fault_rate = len(fault_alarms) / 100
        normal_rate = len(normal_alarms) / 50 if normal_alarms else 0
        assert fault_rate > normal_rate
