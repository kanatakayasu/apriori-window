"""
Tests for Dense Interval Prediction Module.
"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dense_prediction import (
    DenseIntervalOccurrenceProcess,
    DensePredictionPipeline,
    DurationPredictor,
    HawkesDenseModel,
    IDITDistributionFitter,
)


# ---------------------------------------------------------------------------
# DenseIntervalOccurrenceProcess
# ---------------------------------------------------------------------------

class TestDIOP:
    def test_empty_intervals(self):
        diop = DenseIntervalOccurrenceProcess([], window_size=5)
        assert diop.idit == []
        assert diop.durations == []
        stats = diop.summary_statistics()
        assert stats["n_intervals"] == 0

    def test_single_interval(self):
        diop = DenseIntervalOccurrenceProcess([(10, 15)], window_size=5)
        assert diop.idit == []
        assert diop.durations == [10]  # 15 - 10 + 5
        stats = diop.summary_statistics()
        assert stats["n_intervals"] == 1
        assert stats["mean_duration"] == 10.0

    def test_two_intervals_idit(self):
        # interval1: (10, 15), actual end = 15 + 5 = 20
        # interval2: (30, 35), gap = 30 - 20 = 10
        diop = DenseIntervalOccurrenceProcess([(10, 15), (30, 35)], window_size=5)
        assert len(diop.idit) == 1
        assert diop.idit[0] == 10.0

    def test_overlapping_intervals_zero_idit(self):
        # interval1: (0, 5), actual end = 5 + 5 = 10
        # interval2: (8, 12), gap = 8 - 10 = -2 → max(0, -2) = 0
        diop = DenseIntervalOccurrenceProcess([(0, 5), (8, 12)], window_size=5)
        assert len(diop.idit) == 1
        assert diop.idit[0] == 0.0

    def test_multiple_intervals(self):
        intervals = [(0, 5), (20, 25), (50, 60), (100, 110)]
        diop = DenseIntervalOccurrenceProcess(intervals, window_size=5)
        assert diop.arrival_times == [0, 20, 50, 100]
        assert len(diop.idit) == 3
        assert len(diop.durations) == 4
        stats = diop.summary_statistics()
        assert stats["n_intervals"] == 4
        assert stats["cv_idit"] > 0

    def test_unsorted_input_is_sorted(self):
        diop = DenseIntervalOccurrenceProcess([(30, 35), (10, 15)], window_size=5)
        assert diop.intervals == [(10, 15), (30, 35)]


# ---------------------------------------------------------------------------
# IDITDistributionFitter
# ---------------------------------------------------------------------------

class TestIDITFitter:
    def test_fit_exponential_data(self):
        rng = np.random.default_rng(42)
        data = rng.exponential(scale=10.0, size=100)
        fitter = IDITDistributionFitter(data.tolist())
        results = fitter.fit_all()
        assert "exponential" in results
        assert "aic" in results["exponential"]
        best = fitter.best_distribution()
        assert best is not None

    def test_fit_all_returns_all_distributions(self):
        rng = np.random.default_rng(123)
        data = rng.gamma(shape=2.0, scale=5.0, size=200)
        fitter = IDITDistributionFitter(data.tolist())
        results = fitter.fit_all()
        for dist_name in ["exponential", "weibull", "gamma", "lognormal"]:
            assert dist_name in results

    def test_empty_data_raises(self):
        with pytest.raises(ValueError):
            IDITDistributionFitter([])

    def test_all_zeros_raises(self):
        with pytest.raises(ValueError):
            IDITDistributionFitter([0.0, 0.0, 0.0])

    def test_best_distribution_bic(self):
        rng = np.random.default_rng(99)
        data = rng.exponential(scale=5.0, size=50)
        fitter = IDITDistributionFitter(data.tolist())
        fitter.fit_all()
        best_aic = fitter.best_distribution("aic")
        best_bic = fitter.best_distribution("bic")
        assert best_aic is not None
        assert best_bic is not None


# ---------------------------------------------------------------------------
# HawkesDenseModel
# ---------------------------------------------------------------------------

class TestHawkes:
    def test_intensity_baseline(self):
        model = HawkesDenseModel(mu=1.0, alpha=0.5, beta=1.0)
        lam = model.intensity(0.0, [])
        assert lam == 1.0

    def test_intensity_with_history(self):
        model = HawkesDenseModel(mu=1.0, alpha=0.5, beta=1.0)
        lam = model.intensity(1.0, [0.0])
        expected = 1.0 + 0.5 * 1.0 * math.exp(-1.0)
        assert abs(lam - expected) < 1e-10

    def test_log_likelihood_no_events(self):
        model = HawkesDenseModel(mu=0.5, alpha=0.3, beta=1.0)
        ll = model.log_likelihood([], T=10.0)
        assert ll == pytest.approx(-5.0)

    def test_fit_synthetic_hawkes(self):
        # Generate simple event data
        events = [1.0, 3.0, 5.0, 8.0, 12.0, 15.0, 18.0, 22.0, 25.0, 30.0]
        model = HawkesDenseModel()
        result = model.fit(events, T=35.0)
        assert "mu" in result
        assert "alpha" in result
        assert "beta" in result
        assert result["mu"] > 0

    def test_predict_next_after_fit(self):
        events = [1.0, 3.0, 5.0, 8.0, 12.0, 15.0, 18.0, 22.0, 25.0, 30.0]
        model = HawkesDenseModel()
        model.fit(events, T=35.0)
        pred = model.predict_next(events, n_samples=100, max_time=50.0)
        assert pred["mean_next"] > 30.0
        assert pred["ci_lower"] < pred["ci_upper"]

    def test_predict_without_fit_raises(self):
        model = HawkesDenseModel()
        with pytest.raises(RuntimeError):
            model.predict_next([1.0, 2.0])

    def test_fit_empty_raises(self):
        model = HawkesDenseModel()
        with pytest.raises(ValueError):
            model.fit([])


# ---------------------------------------------------------------------------
# DurationPredictor
# ---------------------------------------------------------------------------

class TestDurationPredictor:
    def test_fit_weibull(self):
        durations = [5.0, 7.0, 10.0, 3.0, 8.0, 12.0, 6.0, 9.0]
        pred = DurationPredictor(durations)
        result = pred.fit_weibull()
        assert result["distribution"] == "weibull"
        assert result["shape"] > 0
        assert result["scale"] > 0
        assert result["mean_duration"] > 0

    def test_predict_duration(self):
        durations = [5.0, 7.0, 10.0, 3.0, 8.0, 12.0, 6.0, 9.0]
        pred = DurationPredictor(durations)
        result = pred.predict_duration()
        assert result["predicted_mean"] > 0
        assert result["ci_lower"] < result["ci_upper"]

    def test_survival_function(self):
        durations = [5.0, 7.0, 10.0, 3.0, 8.0]
        pred = DurationPredictor(durations)
        sf = pred.survival_function([0.0, 5.0, 100.0])
        assert sf[0] > sf[1] > sf[2]
        assert sf[0] == pytest.approx(1.0, abs=0.01)
        assert sf[2] < 0.01

    def test_empirical_survival(self):
        durations = [3.0, 5.0, 7.0, 10.0]
        pred = DurationPredictor(durations)
        times, surv = pred.empirical_survival()
        assert len(times) == 4
        assert surv[0] == 1.0
        assert surv[-1] == 0.25

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            DurationPredictor([])


# ---------------------------------------------------------------------------
# DensePredictionPipeline
# ---------------------------------------------------------------------------

class TestPipeline:
    def test_too_few_intervals(self):
        pipeline = DensePredictionPipeline([(0, 5), (10, 15)], window_size=5)
        result = pipeline.run()
        assert "error" in result

    def test_full_pipeline(self):
        intervals = [
            (0, 5), (20, 28), (50, 55), (80, 90),
            (120, 130), (160, 165), (200, 210),
        ]
        pipeline = DensePredictionPipeline(intervals, window_size=5, itemset=(1, 2))
        result = pipeline.run()
        assert result["n_intervals"] == 7
        assert "summary" in result
        assert "hawkes_fit" in result
        assert "duration_fit" in result

    def test_pipeline_with_itemset(self):
        intervals = [(0, 5), (20, 25), (50, 55), (80, 85)]
        pipeline = DensePredictionPipeline(intervals, window_size=5, itemset=(3, 7, 11))
        result = pipeline.run()
        assert result["itemset"] == [3, 7, 11]
