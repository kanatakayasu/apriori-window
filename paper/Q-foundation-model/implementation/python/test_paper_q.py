"""Paper Q: Transaction Foundation Model - Unit Tests."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from transaction_embedding import (
    TransactionFoundationModel,
    TransactionEmbedding,
    DenseIntervalToken,
    MultiHeadSelfAttention,
    compute_interval_iou,
    generate_dense_labels,
    softmax,
    layer_norm,
)
from run_experiments import generate_synthetic_transactions


# ===========================================================================
# TransactionEmbedding Tests
# ===========================================================================

class TestTransactionEmbedding:
    def test_init(self):
        emb = TransactionEmbedding(vocab_size=100, embed_dim=32)
        assert emb.item_embeddings.shape == (100, 32)
        assert emb.pos_encoding.shape == (10000, 32)

    def test_embed_transaction_basic(self):
        emb = TransactionEmbedding(vocab_size=50, embed_dim=16)
        vec = emb.embed_transaction([1, 2, 3], position=0)
        assert vec.shape == (16,)
        assert not np.allclose(vec, 0)

    def test_embed_empty_transaction(self):
        emb = TransactionEmbedding(vocab_size=50, embed_dim=16)
        vec = emb.embed_transaction([], position=0)
        assert vec.shape == (16,)

    def test_embed_normalized(self):
        emb = TransactionEmbedding(vocab_size=50, embed_dim=16)
        vec = emb.embed_transaction([1, 2, 3], position=5)
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    def test_position_encoding_differs(self):
        emb = TransactionEmbedding(vocab_size=50, embed_dim=16)
        vec0 = emb.embed_transaction([1], position=0)
        vec1 = emb.embed_transaction([1], position=100)
        assert not np.allclose(vec0, vec1)

    def test_embed_all_transactions(self):
        emb = TransactionEmbedding(vocab_size=50, embed_dim=16)
        transactions = [[[1, 2]], [[3, 4]], [[5]]]
        result = emb.embed_all_transactions(transactions)
        assert result.shape == (3, 16)


# ===========================================================================
# DenseIntervalToken Tests
# ===========================================================================

class TestDenseIntervalToken:
    def test_encode_interval(self):
        dit = DenseIntervalToken(token_dim=32, total_length=100)
        token = dit.encode_interval(
            interval=(10, 30), itemset=(1, 2), timestamps=[10, 15, 20, 25, 30],
            window_size=5
        )
        assert token.shape == (32,)

    def test_encode_normalized(self):
        dit = DenseIntervalToken(token_dim=32, total_length=100)
        token = dit.encode_interval(
            interval=(10, 30), itemset=(1,), timestamps=[10, 20, 30],
            window_size=5
        )
        norm = np.linalg.norm(token)
        assert abs(norm - 1.0) < 1e-5

    def test_different_intervals_differ(self):
        dit = DenseIntervalToken(token_dim=32, total_length=100)
        t1 = dit.encode_interval((10, 30), (1,), [10, 20, 30], 5)
        t2 = dit.encode_interval((50, 70), (1,), [50, 60, 70], 5)
        assert not np.allclose(t1, t2)


# ===========================================================================
# MultiHeadSelfAttention Tests
# ===========================================================================

class TestMultiHeadSelfAttention:
    def test_forward_shape(self):
        attn = MultiHeadSelfAttention(d_model=32, n_heads=4)
        x = np.random.randn(10, 32).astype(np.float32)
        output, weights = attn.forward(x)
        assert output.shape == (10, 32)
        assert weights.shape == (4, 10, 10)

    def test_attention_weights_sum_to_one(self):
        attn = MultiHeadSelfAttention(d_model=16, n_heads=2)
        x = np.random.randn(5, 16).astype(np.float32)
        _, weights = attn.forward(x)
        for h in range(2):
            row_sums = weights[h].sum(axis=-1)
            np.testing.assert_allclose(row_sums, 1.0, atol=1e-5)

    def test_masked_attention(self):
        attn = MultiHeadSelfAttention(d_model=16, n_heads=2)
        x = np.random.randn(5, 16).astype(np.float32)
        mask = np.array([1, 1, 1, 0, 0], dtype=np.float32)
        _, weights = attn.forward(x, mask)
        # Masked positions should have near-zero attention
        for h in range(2):
            assert weights[h][0, 3] < 0.01
            assert weights[h][0, 4] < 0.01


# ===========================================================================
# Foundation Model Tests
# ===========================================================================

class TestTransactionFoundationModel:
    def test_init(self):
        model = TransactionFoundationModel(vocab_size=50, embed_dim=32)
        assert model.vocab_size == 50
        assert model.embed_dim == 32

    def test_encode(self):
        model = TransactionFoundationModel(vocab_size=50, embed_dim=16, n_layers=1)
        transactions = [[[1, 2]], [[3, 4]], [[5, 6]]]
        encoded = model.encode(transactions)
        assert encoded.shape == (3, 16)

    def test_predict_dense_scores(self):
        model = TransactionFoundationModel(vocab_size=50, embed_dim=16)
        transactions = [[[i]] for i in range(20)]
        scores = model.predict_dense_scores(transactions)
        assert scores.shape == (20,)
        assert np.all(scores >= 0) and np.all(scores <= 1)

    def test_mtm_pretraining_reduces_loss(self):
        transactions, _ = generate_synthetic_transactions(
            n_transactions=100, n_items=30, seed=42
        )
        model = TransactionFoundationModel(vocab_size=30, embed_dim=16, n_layers=1, seed=42)
        losses = model.pretrain_mtm(transactions, n_epochs=20, lr=0.001, seed=42)
        assert len(losses) == 20
        # Loss should decrease
        assert losses[-1] < losses[0]

    def test_dip_pretraining(self):
        transactions, true_intervals = generate_synthetic_transactions(
            n_transactions=200, n_items=30, seed=42
        )
        model = TransactionFoundationModel(vocab_size=30, embed_dim=16, n_layers=1, seed=42)
        labels = generate_dense_labels(true_intervals, len(transactions), window_size=10)
        losses = model.pretrain_dip(transactions, labels, n_epochs=20, lr=0.01, seed=42)
        assert len(losses) == 20

    def test_detect_dense_intervals(self):
        model = TransactionFoundationModel(vocab_size=50, embed_dim=16, seed=42)
        transactions = [[[1, 2]] for _ in range(50)]
        intervals = model.detect_dense_intervals(transactions, score_threshold=0.5, min_length=2)
        assert isinstance(intervals, list)
        for s, e in intervals:
            assert s <= e


# ===========================================================================
# Utility Tests
# ===========================================================================

class TestUtilities:
    def test_softmax(self):
        x = np.array([1.0, 2.0, 3.0])
        result = softmax(x)
        assert abs(result.sum() - 1.0) < 1e-6
        assert result[2] > result[1] > result[0]

    def test_layer_norm(self):
        x = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        result = layer_norm(x)
        assert result.shape == x.shape
        # After layer norm, each row should have ~0 mean, ~1 var
        np.testing.assert_allclose(result.mean(axis=-1), 0, atol=1e-5)
        np.testing.assert_allclose(result.var(axis=-1), 1.0, atol=1e-3)

    def test_generate_dense_labels(self):
        intervals = [(10, 20), (30, 40)]
        labels = generate_dense_labels(intervals, 100, window_size=5)
        assert labels.shape == (100,)
        assert labels[10] == 1.0
        assert labels[25] == 1.0  # 20 + 5 = 25
        assert labels[0] == 0.0

    def test_compute_interval_iou_perfect(self):
        pred = [(10, 20)]
        true = [(10, 20)]
        metrics = compute_interval_iou(pred, true, 100)
        assert metrics["iou"] == 1.0
        assert metrics["f1"] == 1.0

    def test_compute_interval_iou_no_overlap(self):
        pred = [(10, 20)]
        true = [(30, 40)]
        metrics = compute_interval_iou(pred, true, 100)
        assert metrics["iou"] == 0.0

    def test_compute_interval_iou_partial(self):
        pred = [(10, 25)]
        true = [(15, 30)]
        metrics = compute_interval_iou(pred, true, 100)
        assert 0 < metrics["iou"] < 1
        assert 0 < metrics["f1"] < 1


# ===========================================================================
# Synthetic Data Tests
# ===========================================================================

class TestSyntheticData:
    def test_generate_basic(self):
        transactions, intervals = generate_synthetic_transactions(
            n_transactions=100, n_items=20, seed=42
        )
        assert len(transactions) == 100
        assert len(intervals) == 3

    def test_generate_has_items(self):
        transactions, _ = generate_synthetic_transactions(
            n_transactions=50, n_items=20, seed=42
        )
        for t in transactions:
            assert len(t) >= 1
            assert len(t[0]) >= 1

    def test_dense_intervals_have_more_items(self):
        """密集区間内のトランザクションは密集アイテムをより多く含むべき。"""
        transactions, _ = generate_synthetic_transactions(
            n_transactions=500, n_items=50,
            dense_intervals=[(100, 200, [1, 2, 3])],
            base_density=0.05, dense_density=0.8,
            seed=42,
        )
        # Count item 1 in dense vs non-dense regions
        count_dense = sum(1 for t in range(100, 201) if 1 in transactions[t][0])
        count_non_dense = sum(1 for t in range(300, 401) if 1 in transactions[t][0])
        assert count_dense > count_non_dense


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
