"""
Tests for Paper O implementation.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dense_pattern_features import (
    DensePatternFeature,
    Event,
    generate_synthetic_data,
    extract_dense_patterns,
    compute_time_binned_features,
)
from cross_attention_model import (
    CrossAttentionConfig,
    CrossAttentionLayer,
    compute_attribution,
    compute_loss,
    train_model_analytical,
    permutation_test_attribution,
    softmax,
    layer_norm,
    sigmoid,
)


# ---------------------------------------------------------------------------
# DensePatternFeature tests
# ---------------------------------------------------------------------------

class TestDensePatternFeature:
    def test_compute_single_interval(self):
        feat = DensePatternFeature(
            itemset=(1, 2),
            intervals=[(10, 20)],
        ).compute()
        assert feat.num_intervals == 1
        assert feat.total_coverage == 11
        assert feat.max_duration == 11
        assert feat.mean_duration == 11.0
        assert feat.first_onset == 10
        assert feat.last_offset == 20

    def test_compute_multiple_intervals(self):
        feat = DensePatternFeature(
            itemset=(3,),
            intervals=[(0, 5), (10, 15), (30, 40)],
        ).compute()
        assert feat.num_intervals == 3
        assert feat.total_coverage == 6 + 6 + 11
        assert feat.max_duration == 11
        assert feat.first_onset == 0
        assert feat.last_offset == 40
        assert feat.gap_mean == pytest.approx((5 + 15) / 2)  # gaps: 10-5=5, 30-15=15

    def test_compute_empty(self):
        feat = DensePatternFeature(itemset=(1,), intervals=[]).compute()
        assert feat.num_intervals == 0
        assert feat.total_coverage == 0

    def test_to_vector_shape(self):
        feat = DensePatternFeature(
            itemset=(1, 2), intervals=[(5, 10)]
        ).compute()
        vec = feat.to_vector()
        assert vec.shape == (DensePatternFeature.vector_dim(),)
        assert vec.shape == (10,)

    def test_feature_names_length(self):
        assert len(DensePatternFeature.feature_names()) == DensePatternFeature.vector_dim()


# ---------------------------------------------------------------------------
# Event tests
# ---------------------------------------------------------------------------

class TestEvent:
    def test_to_vector(self):
        evt = Event(timestamp=50, event_type="promo", magnitude=1.5)
        vec = evt.to_vector(total_time=100)
        assert vec.shape == (Event.vector_dim(),)
        assert vec[0] == pytest.approx(0.5)  # normalized timestamp
        assert vec[1] == 1.5  # magnitude


# ---------------------------------------------------------------------------
# CrossAttentionLayer tests
# ---------------------------------------------------------------------------

class TestCrossAttention:
    def test_forward_shape(self):
        config = CrossAttentionConfig(d_model=16, n_heads=2)
        model = CrossAttentionLayer(config)

        pattern_feat = np.random.randn(5, config.d_pattern)
        event_feat = np.random.randn(3, config.d_event)

        scores, attn = model.forward(pattern_feat, event_feat)
        assert scores.shape == (3, 5)
        assert attn.shape == (2, 3, 5)

    def test_scores_range(self):
        config = CrossAttentionConfig(d_model=16, n_heads=2)
        model = CrossAttentionLayer(config)

        pattern_feat = np.random.randn(4, config.d_pattern)
        event_feat = np.random.randn(2, config.d_event)

        scores, _ = model.forward(pattern_feat, event_feat)
        assert np.all(scores >= 0) and np.all(scores <= 1)

    def test_attention_sums_to_one(self):
        config = CrossAttentionConfig(d_model=16, n_heads=4)
        model = CrossAttentionLayer(config)

        pattern_feat = np.random.randn(6, config.d_pattern)
        event_feat = np.random.randn(3, config.d_event)

        _, attn = model.forward(pattern_feat, event_feat)
        # Each head's attention weights should sum to 1 over patterns
        for h in range(4):
            for e in range(3):
                assert np.sum(attn[h, e]) == pytest.approx(1.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Training tests
# ---------------------------------------------------------------------------

class TestTraining:
    def test_loss_decreases(self):
        config = CrossAttentionConfig(
            d_model=16, n_heads=2, d_ff=32,
            learning_rate=0.01, n_epochs=50, seed=42,
        )
        model = CrossAttentionLayer(config)

        np.random.seed(42)
        pattern_feat = np.random.randn(4, config.d_pattern)
        event_feat = np.random.randn(2, config.d_event)
        targets = np.array([[1, 0, 0, 1], [0, 1, 0, 0]], dtype=np.float64)

        losses = train_model_analytical(
            model, pattern_feat, event_feat, targets, config,
        )

        assert losses[-1] < losses[0], "Loss should decrease during training"

    def test_compute_loss_finite(self):
        config = CrossAttentionConfig(d_model=16, n_heads=2)
        model = CrossAttentionLayer(config)

        pattern_feat = np.random.randn(3, config.d_pattern)
        event_feat = np.random.randn(2, config.d_event)
        targets = np.array([[1, 0, 1], [0, 1, 0]], dtype=np.float64)

        loss = compute_loss(model, pattern_feat, event_feat, targets)
        assert np.isfinite(loss)


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------

class TestUtils:
    def test_softmax(self):
        x = np.array([1.0, 2.0, 3.0])
        s = softmax(x)
        assert s.sum() == pytest.approx(1.0)
        assert np.all(s > 0)

    def test_layer_norm(self):
        x = np.array([[1.0, 2.0, 3.0, 4.0]])
        normed = layer_norm(x)
        assert normed.mean() == pytest.approx(0.0, abs=1e-5)

    def test_sigmoid(self):
        assert sigmoid(np.array([0.0]))[0] == pytest.approx(0.5)
        assert sigmoid(np.array([100.0]))[0] == pytest.approx(1.0, abs=1e-5)
        assert sigmoid(np.array([-100.0]))[0] == pytest.approx(0.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Synthetic data tests
# ---------------------------------------------------------------------------

class TestSyntheticData:
    def test_generate(self):
        path, events, gt = generate_synthetic_data(
            num_transactions=200, num_items=10, num_events=3, seed=42,
        )
        assert len(events) == 3
        assert len(gt) == 3
        assert Path(path).exists()

        import os
        os.unlink(path)

    def test_extract_patterns(self):
        path, events, gt = generate_synthetic_data(
            num_transactions=300, num_items=15, num_events=3, seed=42,
        )
        patterns = extract_dense_patterns(
            path, window_size=10, threshold=3, max_itemset_size=2,
        )
        # Should find at least some patterns
        assert len(patterns) > 0
        for p in patterns:
            assert p.num_intervals > 0
            assert p.total_coverage > 0

        import os
        os.unlink(path)


# ---------------------------------------------------------------------------
# Attribution tests
# ---------------------------------------------------------------------------

class TestAttribution:
    def test_compute_attribution(self):
        config = CrossAttentionConfig(d_model=16, n_heads=2, seed=42)
        model = CrossAttentionLayer(config)

        patterns = [
            DensePatternFeature(itemset=(1,), intervals=[(0, 10)]).compute(),
            DensePatternFeature(itemset=(2, 3), intervals=[(5, 15)]).compute(),
        ]
        events = [
            Event(timestamp=5, event_type="E0"),
            Event(timestamp=50, event_type="E1"),
        ]

        results = compute_attribution(model, patterns, events, total_time=100)
        assert len(results) == 4  # 2 events x 2 patterns
        assert all(0 <= r.attribution_score <= 1 for r in results)

    def test_permutation_test(self):
        patterns = [
            DensePatternFeature(itemset=(1,), intervals=[(0, 10), (30, 40)]).compute(),
        ]
        events = [Event(timestamp=5, event_type="E0")]

        p_values = permutation_test_attribution(
            patterns, events, total_time=100, n_permutations=100,
        )
        assert p_values.shape == (1, 1)
        assert 0 <= p_values[0, 0] <= 1


# ---------------------------------------------------------------------------
# Time-binned features test
# ---------------------------------------------------------------------------

class TestTimeBinned:
    def test_shape(self):
        patterns = [
            DensePatternFeature(itemset=(1,), intervals=[(0, 10)]).compute(),
            DensePatternFeature(itemset=(2,), intervals=[(20, 30)]).compute(),
        ]
        activity = compute_time_binned_features(patterns, total_time=100, num_bins=10)
        assert activity.shape == (10, 2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
