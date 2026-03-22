"""
Tests for pharmacoepidemiology modules.

Covers:
- Synthetic data generation (normal + boundary + error)
- ATC adapter (encoding, truncation, round-trip)
- Dense prescription mining (pattern detection, empty inputs)
- Regulatory contrast analysis (contrast detection, permutation test, BH)
"""

import sys
from pathlib import Path

# Ensure implementation directory is on path
impl_dir = str(Path(__file__).resolve().parent.parent)
if impl_dir not in sys.path:
    sys.path.insert(0, impl_dir)

import pytest
from synthetic_pharma_data import (
    SyntheticPharmaConfig,
    RegulatoryEvent,
    generate_synthetic_prescriptions,
    ATC_CATALOG,
    COMMON_PATTERNS,
)
from pharma_adapter import ATCAdapter, is_valid_atc, write_basket_file
from pharma_dense_miner import (
    compute_dense_intervals,
    compute_item_transaction_map,
    find_dense_prescription_patterns,
    compute_support_time_series,
    intersect_sorted_lists,
)
from regulatory_contrast import (
    compute_density_change,
    permutation_test,
    benjamini_hochberg,
    classify_pattern,
    run_contrast_analysis,
    summarize_results,
    ContrastResult,
)


# ===================================================================
# Synthetic data generation tests
# ===================================================================

class TestSyntheticData:
    """Tests for synthetic_pharma_data module."""

    def test_default_generation(self):
        """Normal: default config produces expected output shape."""
        config = SyntheticPharmaConfig(n_transactions=100, seed=42)
        txns, events, meta = generate_synthetic_prescriptions(config)
        assert len(txns) == 100
        assert len(events) == 2  # default events
        assert meta["n_transactions"] == 100

    def test_all_transactions_non_empty(self):
        """Normal: no empty transactions."""
        config = SyntheticPharmaConfig(n_transactions=200, seed=123)
        txns, _, _ = generate_synthetic_prescriptions(config)
        for t_idx, txn in enumerate(txns):
            assert len(txn) > 0, f"Transaction {t_idx} is empty"

    def test_atc_codes_valid(self):
        """Normal: all generated items are valid ATC codes."""
        config = SyntheticPharmaConfig(n_transactions=50, seed=7)
        txns, _, _ = generate_synthetic_prescriptions(config)
        for txn in txns:
            for item in txn:
                assert item in ATC_CATALOG, f"Unknown ATC code: {item}"

    def test_custom_events(self):
        """Normal: custom regulatory events are used."""
        custom_event = RegulatoryEvent(
            event_id="TEST-001",
            event_type="withdrawal",
            timestamp=50,
            description="Test withdrawal",
            targeted_atc=["C10A"],
            effect_magnitude=0.9,
        )
        config = SyntheticPharmaConfig(
            n_transactions=100, seed=42,
            regulatory_events=[custom_event],
        )
        txns, events, _ = generate_synthetic_prescriptions(config)
        assert len(events) == 1
        assert events[0].event_id == "TEST-001"

    def test_reproducibility(self):
        """Normal: same seed produces same output."""
        config1 = SyntheticPharmaConfig(n_transactions=50, seed=42)
        config2 = SyntheticPharmaConfig(n_transactions=50, seed=42)
        txns1, _, _ = generate_synthetic_prescriptions(config1)
        txns2, _, _ = generate_synthetic_prescriptions(config2)
        assert txns1 == txns2

    def test_minimum_transactions(self):
        """Boundary: single transaction."""
        config = SyntheticPharmaConfig(n_transactions=1, seed=42)
        txns, _, meta = generate_synthetic_prescriptions(config)
        assert len(txns) == 1
        assert len(txns[0]) > 0

    def test_large_dataset(self):
        """Boundary: large number of transactions."""
        config = SyntheticPharmaConfig(n_transactions=5000, seed=42)
        txns, _, _ = generate_synthetic_prescriptions(config)
        assert len(txns) == 5000

    def test_zero_effect_magnitude(self):
        """Boundary: event with zero effect should not change patterns."""
        event = RegulatoryEvent(
            event_id="NOEFFECT",
            event_type="label_change",
            timestamp=50,
            description="No effect event",
            targeted_atc=["C10A"],
            effect_magnitude=0.0,
        )
        config = SyntheticPharmaConfig(
            n_transactions=100, seed=42,
            regulatory_events=[event],
        )
        txns, _, _ = generate_synthetic_prescriptions(config)
        assert len(txns) == 100


# ===================================================================
# ATC Adapter tests
# ===================================================================

class TestATCAdapter:
    """Tests for pharma_adapter module."""

    def test_encode_decode_roundtrip(self):
        """Normal: encode then decode returns original."""
        adapter = ATCAdapter(atc_level=3)
        code = "C09A"
        encoded = adapter.encode_atc(code)
        decoded = adapter.decode_int(encoded)
        assert decoded == code

    def test_truncation_level3(self):
        """Normal: level 3 truncation."""
        adapter = ATCAdapter(atc_level=3)
        assert adapter.truncate_atc("C09AA01") == "C09A"

    def test_truncation_level2(self):
        """Normal: level 2 truncation."""
        adapter = ATCAdapter(atc_level=2)
        assert adapter.truncate_atc("C09AA01") == "C09"

    def test_same_code_same_id(self):
        """Normal: same ATC code gets same integer ID."""
        adapter = ATCAdapter(atc_level=3)
        id1 = adapter.encode_atc("C09A")
        id2 = adapter.encode_atc("C09A")
        assert id1 == id2

    def test_different_codes_different_ids(self):
        """Normal: different codes get different IDs."""
        adapter = ATCAdapter(atc_level=3)
        id1 = adapter.encode_atc("C09A")
        id2 = adapter.encode_atc("C10A")
        assert id1 != id2

    def test_convert_transactions(self):
        """Normal: transaction conversion produces correct format."""
        adapter = ATCAdapter(atc_level=3)
        txns = [["C09A", "C10A"], ["M01A"]]
        converted = adapter.convert_transactions(txns)
        assert len(converted) == 2
        assert len(converted[0]) == 1  # single basket
        assert len(converted[0][0]) == 2  # two items
        assert len(converted[1][0]) == 1  # one item

    def test_invalid_atc_level(self):
        """Error: invalid ATC level raises ValueError."""
        with pytest.raises(ValueError):
            ATCAdapter(atc_level=0)
        with pytest.raises(ValueError):
            ATCAdapter(atc_level=6)

    def test_decode_unknown_id(self):
        """Error: decoding unknown ID raises KeyError."""
        adapter = ATCAdapter(atc_level=3)
        with pytest.raises(KeyError):
            adapter.decode_int(999)

    def test_is_valid_atc(self):
        """Normal: ATC validation."""
        assert is_valid_atc("C09A") is True
        assert is_valid_atc("C09AA01") is True
        assert is_valid_atc("C") is False  # Level 1 alone is too short for the regex
        assert is_valid_atc("C09") is True  # Level 2
        assert is_valid_atc("123") is False
        assert is_valid_atc("") is False


# ===================================================================
# Dense mining tests
# ===================================================================

class TestDenseMining:
    """Tests for pharma_dense_miner module."""

    def test_simple_dense_interval(self):
        """Normal: detect dense interval in clustered timestamps."""
        timestamps = [0, 1, 2, 3, 4, 10, 11, 12, 13, 14]
        intervals = compute_dense_intervals(timestamps, 3, 3)
        assert len(intervals) > 0

    def test_no_dense_interval(self):
        """Normal: sparse timestamps produce no dense intervals."""
        timestamps = [0, 10, 20, 30, 40]
        intervals = compute_dense_intervals(timestamps, 3, 3)
        assert len(intervals) == 0

    def test_empty_timestamps(self):
        """Boundary: empty input returns empty."""
        intervals = compute_dense_intervals([], 3, 3)
        assert intervals == []

    def test_invalid_window(self):
        """Error: window_size < 1 raises ValueError."""
        with pytest.raises(ValueError):
            compute_dense_intervals([1, 2, 3], 0, 1)

    def test_invalid_threshold(self):
        """Error: threshold < 1 raises ValueError."""
        with pytest.raises(ValueError):
            compute_dense_intervals([1, 2, 3], 3, 0)

    def test_item_transaction_map(self):
        """Normal: item map built correctly."""
        txns = [[1, 2], [2, 3], [1, 3]]
        item_map = compute_item_transaction_map(txns)
        assert item_map[1] == [0, 2]
        assert item_map[2] == [0, 1]
        assert item_map[3] == [1, 2]

    def test_find_dense_patterns(self):
        """Normal: find patterns in synthetic data."""
        # Create data with a clear dense co-prescription pattern
        txns = []
        for i in range(50):
            if 10 <= i <= 30:
                txns.append([1, 2, 3])  # Dense region
            else:
                txns.append([4, 5])
        patterns = find_dense_prescription_patterns(txns, 5, 3, 3)
        # Should find at least singleton patterns for items 1, 2, 3
        found_items = set()
        for pat in patterns:
            for item in pat:
                found_items.add(item)
        assert 1 in found_items
        assert 2 in found_items

    def test_support_time_series(self):
        """Normal: support series computed correctly."""
        timestamps = [0, 1, 2, 5, 6]
        series = compute_support_time_series(timestamps, 10, 3)
        assert len(series) == 8  # 10 - 3 + 1
        assert series[0] == 3  # positions 0,1,2 in [0,3)
        assert series[1] == 2  # positions 1,2 in [1,4)

    def test_intersect_sorted_lists(self):
        """Normal: sorted list intersection."""
        result = intersect_sorted_lists([[1, 2, 3, 5], [2, 3, 4, 5]])
        assert result == [2, 3, 5]

    def test_intersect_empty(self):
        """Boundary: empty list intersection."""
        assert intersect_sorted_lists([]) == []


# ===================================================================
# Regulatory contrast tests
# ===================================================================

class TestRegulatoryContrast:
    """Tests for regulatory_contrast module."""

    def test_density_change_decrease(self):
        """Normal: detect support decrease after event."""
        # High support before, low after
        series = [5, 5, 5, 5, 5, 1, 1, 1, 1, 1]
        pre, post, delta = compute_density_change(series, 5, 5)
        assert pre > post
        assert delta < 0

    def test_density_change_increase(self):
        """Normal: detect support increase after event."""
        series = [1, 1, 1, 1, 1, 5, 5, 5, 5, 5]
        pre, post, delta = compute_density_change(series, 5, 5)
        assert post > pre
        assert delta > 0

    def test_density_change_stable(self):
        """Normal: stable support yields near-zero delta."""
        series = [3, 3, 3, 3, 3, 3, 3, 3, 3, 3]
        pre, post, delta = compute_density_change(series, 5, 5)
        assert abs(delta) < 0.01

    def test_permutation_test_significant(self):
        """Normal: clear change yields low p-value."""
        series = [10] * 50 + [0] * 50
        p = permutation_test(series, 50, 20, n_permutations=199, seed=42)
        assert p < 0.1  # Should be significant

    def test_permutation_test_null(self):
        """Normal: constant series yields high p-value."""
        series = [5] * 100
        p = permutation_test(series, 50, 20, n_permutations=99, seed=42)
        assert p > 0.3

    def test_benjamini_hochberg_all_significant(self):
        """Normal: all small p-values rejected."""
        p_values = [0.001, 0.002, 0.003]
        rejected = benjamini_hochberg(p_values, alpha=0.05)
        assert all(rejected)

    def test_benjamini_hochberg_none_significant(self):
        """Normal: all large p-values not rejected."""
        p_values = [0.5, 0.6, 0.7]
        rejected = benjamini_hochberg(p_values, alpha=0.05)
        assert not any(rejected)

    def test_benjamini_hochberg_empty(self):
        """Boundary: empty p-values."""
        assert benjamini_hochberg([], 0.05) == []

    def test_classify_disappearing(self):
        """Normal: negative delta + overlap = disappearing."""
        cls = classify_pattern(-3.0, 0.01, 0.05, 1.0, (1, 2), [1])
        assert cls == "disappearing"

    def test_classify_emerging(self):
        """Normal: positive delta = emerging."""
        cls = classify_pattern(3.0, 0.01, 0.05, 1.0, (3, 4), [1])
        assert cls == "emerging"

    def test_classify_stable_high_pvalue(self):
        """Normal: high p-value = stable regardless of delta."""
        cls = classify_pattern(-3.0, 0.5, 0.05, 1.0, (1, 2), [1])
        assert cls == "stable"

    def test_summarize_results(self):
        """Normal: summary statistics correct."""
        results = [
            ContrastResult((1, 2), "E1", 100, 5.0, 1.0, -4.0, 0.01, "disappearing", True),
            ContrastResult((3, 4), "E1", 100, 1.0, 5.0, 4.0, 0.02, "emerging", False),
            ContrastResult((5,), "E1", 100, 3.0, 3.0, 0.0, 0.8, "stable", False),
        ]
        summary = summarize_results(results)
        assert summary["total_tests"] == 3
        assert summary["disappearing"] == 1
        assert summary["emerging"] == 1
        assert summary["stable"] == 1
        assert summary["targeted_disappearing"] == 1


# ===================================================================
# Integration test
# ===================================================================

class TestIntegration:
    """End-to-end integration test."""

    def test_full_pipeline(self):
        """Integration: generate -> adapt -> mine -> contrast."""
        # Generate
        config = SyntheticPharmaConfig(n_transactions=300, seed=42)
        txns, events, meta = generate_synthetic_prescriptions(config)

        # Adapt
        adapter = ATCAdapter(atc_level=3)
        int_txns = []
        for txn in txns:
            items = sorted(set(adapter.encode_atc(atc) for atc in txn))
            int_txns.append(items)

        # Mine
        patterns = find_dense_prescription_patterns(
            int_txns, window_size=30, threshold=5, max_length=3
        )
        assert len(patterns) > 0, "Should find at least one dense pattern"

        # Build item map for contrast analysis
        item_map = compute_item_transaction_map(int_txns)

        # Contrast
        event_dicts = [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp,
                "targeted_atc": e.targeted_atc,
            }
            for e in events
        ]

        results = run_contrast_analysis(
            dense_patterns=patterns,
            item_transaction_map=item_map,
            n_transactions=len(int_txns),
            window_size=30,
            events=event_dicts,
            atc_id_mapping=adapter.get_mapping(),
            lookback=50,
            n_permutations=99,
            alpha=0.05,
            change_threshold=1.0,
            seed=42,
        )
        assert len(results) > 0
        summary = summarize_results(results)
        assert summary["total_tests"] == len(patterns) * len(events)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
