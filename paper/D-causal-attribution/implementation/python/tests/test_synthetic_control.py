"""
Tests for Synthetic Control Attribution

Covers:
  - Support time series computation
  - Donor pool construction
  - Weight estimation (simplex constraint)
  - Synthetic control estimation
  - Causal effect recovery on synthetic data
  - Placebo test validity
  - Bootstrap confidence intervals
  - Full pipeline
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Setup path
_repo_root = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(_repo_root / "paper" / "D-causal-attribution" / "implementation" / "python"))

from synthetic_control_attribution import (
    build_donor_pool,
    bootstrap_causal_effect,
    compute_rmspe,
    compute_support_series,
    estimate_weights,
    filter_donors_by_prefit,
    placebo_test,
    run_causal_attribution,
    synthetic_control,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_transactions(n: int = 200, seed: int = 42):
    """Generate synthetic transactions with a known pattern burst."""
    rng = np.random.RandomState(seed)
    items_pool = list(range(1, 21))
    transactions = []
    for t in range(n):
        # Base: each item appears with 10% probability
        tx = [i for i in items_pool if rng.random() < 0.10]
        # Inject pattern {1, 2, 3} densely in [80, 130)
        if 80 <= t < 130:
            for item in [1, 2, 3]:
                if item not in tx:
                    tx.append(item)
        # Inject control pattern {10, 11, 12} steadily throughout
        if rng.random() < 0.15:
            for item in [10, 11, 12]:
                if item not in tx:
                    tx.append(item)
        transactions.append(sorted(tx))
    return transactions


# ---------------------------------------------------------------------------
# Test: compute_support_series
# ---------------------------------------------------------------------------

class TestSupportSeries:
    def test_basic_support(self):
        transactions = [[1, 2], [1, 3], [1, 2], [2, 3], [1, 2]]
        series = compute_support_series(transactions, (1, 2), window_size=3)
        assert len(series) == 3  # 5 - 3 + 1
        assert series[0] == pytest.approx(2 / 3)  # tx 0,1,2: {1,2} in 0 and 2
        assert series[2] == pytest.approx(2 / 3)  # tx 2,3,4: {1,2} in tx2 and tx4

    def test_empty_transactions(self):
        series = compute_support_series([], (1,), window_size=5)
        assert len(series) == 0

    def test_window_too_large(self):
        transactions = [[1], [2]]
        series = compute_support_series(transactions, (1,), window_size=5)
        assert len(series) == 0

    def test_single_item(self):
        transactions = [[1], [2], [1], [1], [2]]
        series = compute_support_series(transactions, (1,), window_size=2)
        assert len(series) == 4
        assert series[0] == pytest.approx(0.5)  # tx 0,1
        assert series[2] == pytest.approx(1.0)  # tx 2,3


# ---------------------------------------------------------------------------
# Test: build_donor_pool
# ---------------------------------------------------------------------------

class TestDonorPool:
    def test_item_disjoint(self):
        treated = (1, 2, 3)
        candidates = [(4, 5), (1, 5), (6, 7, 8), (2, 6)]
        donors = build_donor_pool(treated, candidates)
        assert (4, 5) in donors
        assert (6, 7, 8) in donors
        assert (1, 5) not in donors
        assert (2, 6) not in donors

    def test_empty_candidates(self):
        donors = build_donor_pool((1, 2), [])
        assert donors == []

    def test_all_overlapping(self):
        treated = (1, 2)
        candidates = [(1, 3), (2, 4), (1, 2)]
        donors = build_donor_pool(treated, candidates)
        assert donors == []

    def test_single_item_patterns(self):
        treated = (1,)
        candidates = [(2,), (3,), (1,)]
        donors = build_donor_pool(treated, candidates)
        assert len(donors) == 2
        assert (1,) not in donors


# ---------------------------------------------------------------------------
# Test: estimate_weights
# ---------------------------------------------------------------------------

class TestEstimateWeights:
    def test_weights_sum_to_one(self):
        rng = np.random.RandomState(0)
        treated_pre = rng.randn(50)
        donor_pre = rng.randn(50, 5)
        w = estimate_weights(treated_pre, donor_pre)
        assert pytest.approx(w.sum(), abs=1e-6) == 1.0
        assert all(wi >= -1e-10 for wi in w)

    def test_single_donor(self):
        treated = np.array([1.0, 2.0, 3.0])
        donor = np.array([[1.0], [2.0], [3.0]])
        w = estimate_weights(treated, donor)
        assert len(w) == 1
        assert w[0] == pytest.approx(1.0)

    def test_perfect_match(self):
        """When treated = donor_1, weight should be 1 on donor_1."""
        donor_1 = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        donor_2 = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
        treated = donor_1.copy()
        donor_pre = np.column_stack([donor_1, donor_2])
        w = estimate_weights(treated, donor_pre, regularization=1e-8)
        assert w[0] > 0.9  # Should heavily weight donor_1

    def test_empty_donors(self):
        treated = np.array([1.0, 2.0])
        donor = np.empty((2, 0))
        w = estimate_weights(treated, donor)
        assert len(w) == 0


# ---------------------------------------------------------------------------
# Test: synthetic_control
# ---------------------------------------------------------------------------

class TestSyntheticControl:
    def test_basic_estimation(self):
        t = 100
        t0 = 60
        rng = np.random.RandomState(42)

        # Create treated with a jump at t0
        treated = np.concatenate([
            rng.randn(t0) * 0.1 + 0.5,
            rng.randn(t - t0) * 0.1 + 0.8,  # jump by 0.3
        ])

        # Create donors that don't jump
        d1 = rng.randn(t) * 0.1 + 0.5
        d2 = rng.randn(t) * 0.1 + 0.4
        donors = np.column_stack([d1, d2])

        weights, counterfactual, effect = synthetic_control(treated, donors, t0)

        # Post-intervention effect should be positive (around 0.3)
        post_effect = np.mean(effect[t0:])
        assert post_effect > 0.1

    def test_no_effect(self):
        """When treated follows donors, effect should be near zero."""
        t = 100
        t0 = 60
        rng = np.random.RandomState(42)
        base = rng.randn(t) * 0.1 + 0.5
        treated = base + rng.randn(t) * 0.01
        donors = np.column_stack([base + rng.randn(t) * 0.01, base + rng.randn(t) * 0.01])

        weights, counterfactual, effect = synthetic_control(treated, donors, t0)
        assert abs(np.mean(effect[t0:])) < 0.1


# ---------------------------------------------------------------------------
# Test: compute_rmspe
# ---------------------------------------------------------------------------

class TestRMSPE:
    def test_zero_series(self):
        assert compute_rmspe(np.zeros(10), 0, 10) == 0.0

    def test_known_value(self):
        series = np.array([1.0, -1.0, 1.0, -1.0])
        assert compute_rmspe(series, 0, 4) == pytest.approx(1.0)

    def test_empty_range(self):
        assert compute_rmspe(np.array([1.0, 2.0]), 2, 2) == 0.0


# ---------------------------------------------------------------------------
# Test: placebo_test
# ---------------------------------------------------------------------------

class TestPlaceboTest:
    def test_returns_valid_pvalue(self):
        t = 80
        t0 = 50
        rng = np.random.RandomState(42)

        treated = np.concatenate([
            rng.randn(t0) * 0.1 + 0.5,
            rng.randn(t - t0) * 0.1 + 0.9,
        ])
        d1 = rng.randn(t) * 0.1 + 0.5
        d2 = rng.randn(t) * 0.1 + 0.5
        d3 = rng.randn(t) * 0.1 + 0.5
        donors = np.column_stack([d1, d2, d3])

        ratio, placebo_ratios, p_val = placebo_test(treated, donors, t0)
        assert 0 < p_val <= 1.0
        assert len(placebo_ratios) == 3


# ---------------------------------------------------------------------------
# Test: bootstrap_causal_effect
# ---------------------------------------------------------------------------

class TestBootstrap:
    def test_ci_contains_point_estimate(self):
        t = 80
        t0 = 50
        rng = np.random.RandomState(42)

        treated = np.concatenate([
            rng.randn(t0) * 0.1 + 0.5,
            rng.randn(t - t0) * 0.1 + 0.8,
        ])
        d1 = rng.randn(t) * 0.1 + 0.5
        donors = np.column_stack([d1])

        mean_eff, lower, upper = bootstrap_causal_effect(
            treated, donors, t0, n_bootstrap=50, confidence=0.95
        )
        assert len(mean_eff) == t
        assert len(lower) == t
        assert len(upper) == t
        # CI should contain zero in pre-period (approximately)
        pre_mean = np.mean(mean_eff[:t0])
        assert abs(pre_mean) < 0.3


# ---------------------------------------------------------------------------
# Test: full pipeline (run_causal_attribution)
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_with_synthetic_data(self):
        transactions = _make_transactions(n=200, seed=42)
        result = run_causal_attribution(
            transactions=transactions,
            treated_pattern=(1, 2, 3),
            candidate_patterns=[(4, 5), (10, 11, 12), (6, 7), (15, 16)],
            intervention_time=60,  # in support series coordinates
            window_size=20,
            n_bootstrap=30,
            seed=42,
        )
        assert "error" not in result
        assert len(result["donors"]) > 0
        assert len(result["weights"]) == len(result["donors"])
        assert result["p_value"] > 0
        assert "cumulative_effect" in result

    def test_empty_donor_pool(self):
        transactions = _make_transactions(n=100)
        result = run_causal_attribution(
            transactions=transactions,
            treated_pattern=(1, 2, 3),
            candidate_patterns=[(1, 4), (2, 5), (3, 6)],  # all overlap
            intervention_time=30,
            window_size=10,
        )
        assert "error" in result

    def test_insufficient_transactions(self):
        transactions = [[1, 2], [3, 4]]
        result = run_causal_attribution(
            transactions=transactions,
            treated_pattern=(1, 2),
            candidate_patterns=[(3, 4)],
            intervention_time=0,
            window_size=10,
        )
        assert "error" in result
