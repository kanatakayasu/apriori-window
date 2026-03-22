"""
Transaction Embedding Module for Dense Interval Detection Foundation Model.

This module implements:
1. Transaction Embedding: Maps each transaction to a dense vector
2. Dense Interval Token (DIT): Special token marking dense interval boundaries
3. Pre-training Objective: Masked transaction modeling + dense interval prediction

NumPy-based implementation (no PyTorch dependency).
"""

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Phase 1 module import
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python"))
from apriori_window_basket import (
    compute_dense_intervals,
    find_dense_itemsets,
    read_transactions_with_baskets,
)


# ===========================================================================
# 1. Transaction Embedding
# ===========================================================================

class TransactionEmbedding:
    """
    トランザクション埋め込み: 各トランザクションを固定次元ベクトルに変換する。

    手法:
        - アイテムごとの学習可能な埋め込みベクトルの平均プーリング
        - 位置符号化 (sinusoidal) を加算
        - 正規化

    Parameters:
        vocab_size: アイテム語彙数
        embed_dim: 埋め込み次元数
        max_len: 最大トランザクション数 (位置符号化用)
    """

    def __init__(self, vocab_size: int, embed_dim: int = 64, max_len: int = 10000,
                 seed: int = 42):
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        self.max_len = max_len
        rng = np.random.RandomState(seed)

        # アイテム埋め込み行列: Xavier初期化
        scale = math.sqrt(2.0 / (vocab_size + embed_dim))
        self.item_embeddings = rng.randn(vocab_size, embed_dim).astype(np.float32) * scale

        # 位置符号化 (sinusoidal)
        self.pos_encoding = self._sinusoidal_encoding(max_len, embed_dim)

    @staticmethod
    def _sinusoidal_encoding(max_len: int, embed_dim: int) -> np.ndarray:
        """Sinusoidal positional encoding (Vaswani et al., 2017)."""
        pe = np.zeros((max_len, embed_dim), dtype=np.float32)
        position = np.arange(max_len, dtype=np.float32).reshape(-1, 1)
        div_term = np.exp(
            np.arange(0, embed_dim, 2, dtype=np.float32) * -(math.log(10000.0) / embed_dim)
        )
        pe[:, 0::2] = np.sin(position * div_term)
        pe[:, 1::2] = np.cos(position * div_term)
        return pe

    def embed_transaction(self, items: List[int], position: int) -> np.ndarray:
        """
        単一トランザクションを埋め込みベクトルに変換する。

        Args:
            items: トランザクション内のアイテムID列
            position: トランザクションの時間位置 (0-indexed)

        Returns:
            embed_dim次元のベクトル
        """
        if not items:
            vec = np.zeros(self.embed_dim, dtype=np.float32)
        else:
            valid_items = [i for i in items if 0 <= i < self.vocab_size]
            if not valid_items:
                vec = np.zeros(self.embed_dim, dtype=np.float32)
            else:
                vec = self.item_embeddings[valid_items].mean(axis=0)

        # 位置符号化を加算
        pos_idx = min(position, self.max_len - 1)
        vec = vec + self.pos_encoding[pos_idx]

        # L2正規化
        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec = vec / norm
        return vec

    def embed_all_transactions(
        self, transactions: List[List[List[int]]]
    ) -> np.ndarray:
        """
        全トランザクションを埋め込む。

        Args:
            transactions: トランザクション列 (バスケット構造)

        Returns:
            (T, embed_dim) の行列
        """
        T = len(transactions)
        embeddings = np.zeros((T, self.embed_dim), dtype=np.float32)
        for t, baskets in enumerate(transactions):
            # 全バスケットのアイテムをフラット化
            items = []
            for basket in baskets:
                items.extend(basket)
            embeddings[t] = self.embed_transaction(items, t)
        return embeddings


# ===========================================================================
# 2. Dense Interval Token (DIT)
# ===========================================================================

class DenseIntervalToken:
    """
    密集区間トークン: 密集区間の時間的特性を符号化するトークン表現。

    各密集区間 (s, e) に対して以下の特徴を抽出:
        - 開始位置 (正規化)
        - 終了位置 (正規化)
        - 持続時間 (正規化)
        - 区間内平均密度
        - 周期性指標

    Parameters:
        token_dim: トークン次元数
        total_length: 全トランザクション数 (正規化用)
    """

    def __init__(self, token_dim: int = 64, total_length: int = 1000):
        self.token_dim = token_dim
        self.total_length = max(total_length, 1)

    def encode_interval(
        self,
        interval: Tuple[int, int],
        itemset: Tuple[int, ...],
        timestamps: List[int],
        window_size: int,
    ) -> np.ndarray:
        """
        単一の密集区間をトークンベクトルに変換する。

        Args:
            interval: (start, end) 密集区間
            itemset: 対象アイテムセット
            timestamps: アイテムセットの出現タイムスタンプ
            window_size: ウィンドウサイズ

        Returns:
            token_dim次元のベクトル
        """
        s, e = interval
        T = self.total_length

        # 基本特徴 (5次元)
        start_norm = s / T
        end_norm = e / T
        duration_norm = (e - s + 1) / T
        # 区間内のイベント数
        count_in = sum(1 for ts in timestamps if s <= ts <= e + window_size)
        density = count_in / max(e - s + 1, 1)
        center_norm = ((s + e) / 2) / T

        features = np.array([start_norm, end_norm, duration_norm, density, center_norm],
                            dtype=np.float32)

        # token_dim に拡張: 特徴をフーリエ基底で展開
        token = np.zeros(self.token_dim, dtype=np.float32)
        for i, feat in enumerate(features):
            for j in range(self.token_dim // (len(features) * 2)):
                idx_sin = i * (self.token_dim // len(features)) + 2 * j
                idx_cos = idx_sin + 1
                if idx_sin < self.token_dim:
                    freq = (j + 1) * math.pi
                    token[idx_sin] = math.sin(freq * feat)
                if idx_cos < self.token_dim:
                    token[idx_cos] = math.cos(freq * feat)

        # L2正規化
        norm = np.linalg.norm(token)
        if norm > 1e-8:
            token = token / norm
        return token

    def encode_all_intervals(
        self,
        dense_results: Dict[Tuple[int, ...], List[Tuple[int, int]]],
        item_timestamps: Dict[int, List[int]],
        window_size: int,
    ) -> Tuple[np.ndarray, List[Tuple[Tuple[int, ...], Tuple[int, int]]]]:
        """
        全密集区間をトークン行列に変換する。

        Returns:
            tokens: (N, token_dim) の行列
            labels: 各トークンに対応する (itemset, interval) のリスト
        """
        tokens_list = []
        labels = []

        for itemset, intervals in dense_results.items():
            # タイムスタンプ取得 (単体/多体で分岐)
            if len(itemset) == 1:
                ts = item_timestamps.get(itemset[0], [])
            else:
                ts = item_timestamps.get(itemset[0], [])
                # 簡易実装: 最初のアイテムのタイムスタンプで代用

            for interval in intervals:
                token = self.encode_interval(interval, itemset, ts, window_size)
                tokens_list.append(token)
                labels.append((itemset, interval))

        if tokens_list:
            tokens = np.stack(tokens_list)
        else:
            tokens = np.zeros((0, self.token_dim), dtype=np.float32)

        return tokens, labels


# ===========================================================================
# 3. Self-Attention Layer (NumPy)
# ===========================================================================

def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Numerically stable softmax."""
    e_x = np.exp(x - np.max(x, axis=axis, keepdims=True))
    return e_x / (e_x.sum(axis=axis, keepdims=True) + 1e-12)


def layer_norm(x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Layer normalization."""
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return (x - mean) / np.sqrt(var + eps)


class MultiHeadSelfAttention:
    """
    マルチヘッド自己注意機構 (NumPy実装)。

    Parameters:
        d_model: モデル次元
        n_heads: ヘッド数
        seed: 乱数シード
    """

    def __init__(self, d_model: int = 64, n_heads: int = 4, seed: int = 42):
        assert d_model % n_heads == 0
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_head = d_model // n_heads

        rng = np.random.RandomState(seed)
        scale = math.sqrt(2.0 / d_model)

        # Q, K, V 射影行列
        self.W_Q = rng.randn(d_model, d_model).astype(np.float32) * scale
        self.W_K = rng.randn(d_model, d_model).astype(np.float32) * scale
        self.W_V = rng.randn(d_model, d_model).astype(np.float32) * scale
        self.W_O = rng.randn(d_model, d_model).astype(np.float32) * scale

    def forward(self, x: np.ndarray, mask: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Forward pass.

        Args:
            x: (seq_len, d_model) 入力系列
            mask: (seq_len,) バイナリマスク (0=masked)

        Returns:
            output: (seq_len, d_model)
            attn_weights: (n_heads, seq_len, seq_len)
        """
        seq_len = x.shape[0]

        Q = x @ self.W_Q  # (seq_len, d_model)
        K = x @ self.W_K
        V = x @ self.W_V

        # マルチヘッドに reshape
        Q = Q.reshape(seq_len, self.n_heads, self.d_head).transpose(1, 0, 2)  # (n_heads, seq_len, d_head)
        K = K.reshape(seq_len, self.n_heads, self.d_head).transpose(1, 0, 2)
        V = V.reshape(seq_len, self.n_heads, self.d_head).transpose(1, 0, 2)

        # Scaled dot-product attention
        scale = math.sqrt(self.d_head)
        scores = np.matmul(Q, K.transpose(0, 2, 1)) / scale  # (n_heads, seq_len, seq_len)

        if mask is not None:
            # mask shape: (seq_len,) -> broadcast to (1, 1, seq_len)
            mask_2d = mask.reshape(1, 1, seq_len)
            scores = scores + (1 - mask_2d) * (-1e9)

        attn_weights = softmax(scores, axis=-1)
        context = np.matmul(attn_weights, V)  # (n_heads, seq_len, d_head)

        # ヘッド結合
        context = context.transpose(1, 0, 2).reshape(seq_len, self.d_model)
        output = context @ self.W_O

        return output, attn_weights


# ===========================================================================
# 4. Foundation Model for Dense Interval Detection
# ===========================================================================

class TransactionFoundationModel:
    """
    トランザクション基盤モデル: 事前学習 + 密集区間検出。

    アーキテクチャ:
        1. TransactionEmbedding: トランザクション→ベクトル
        2. MultiHeadSelfAttention x L層: 系列内の依存関係を捕捉
        3. Dense Interval Head: 各位置での密集スコアを出力

    事前学習タスク:
        - Masked Transaction Modeling (MTM):
          ランダムにトランザクションをマスクし、周辺コンテキストから復元
        - Dense Interval Prediction (DIP):
          各位置が密集区間内かどうかを二値分類
    """

    def __init__(
        self,
        vocab_size: int,
        embed_dim: int = 64,
        n_heads: int = 4,
        n_layers: int = 2,
        max_len: int = 10000,
        seed: int = 42,
    ):
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        self.n_heads = n_heads
        self.n_layers = n_layers

        self.embedding = TransactionEmbedding(vocab_size, embed_dim, max_len, seed)
        self.attention_layers = [
            MultiHeadSelfAttention(embed_dim, n_heads, seed + i)
            for i in range(n_layers)
        ]

        rng = np.random.RandomState(seed + 100)
        scale = math.sqrt(2.0 / embed_dim)

        # MTM head: 埋め込みから元トランザクション特徴を復元
        self.mtm_head = rng.randn(embed_dim, embed_dim).astype(np.float32) * scale

        # DIP head: 密集スコア予測 (1次元出力)
        self.dip_head = rng.randn(embed_dim, 1).astype(np.float32) * scale
        self.dip_bias = np.zeros(1, dtype=np.float32)

    def encode(self, transactions: List[List[List[int]]]) -> np.ndarray:
        """
        トランザクション列を符号化する。

        Args:
            transactions: バスケット構造付きトランザクション列

        Returns:
            (T, embed_dim) の符号化行列
        """
        # 1. トランザクション埋め込み
        x = self.embedding.embed_all_transactions(transactions)

        # 2. Self-Attention層を適用
        for layer in self.attention_layers:
            residual = x
            out, _ = layer.forward(x)
            x = layer_norm(residual + out)

        return x

    def predict_dense_scores(self, transactions: List[List[List[int]]]) -> np.ndarray:
        """
        各トランザクション位置の密集スコアを予測する。

        Returns:
            (T,) の密集スコア配列 (sigmoid適用済み)
        """
        encoded = self.encode(transactions)
        logits = encoded @ self.dip_head + self.dip_bias  # (T, 1)
        scores = 1.0 / (1.0 + np.exp(-logits.squeeze()))  # sigmoid
        return scores

    def pretrain_mtm(
        self,
        transactions: List[List[List[int]]],
        mask_ratio: float = 0.15,
        n_epochs: int = 10,
        lr: float = 0.001,
        seed: int = 42,
    ) -> List[float]:
        """
        Masked Transaction Modeling による事前学習。

        マスクされたトランザクションの埋め込みを周辺コンテキストから復元する。

        Returns:
            エポックごとの損失リスト
        """
        rng = np.random.RandomState(seed)
        T = len(transactions)
        if T == 0:
            return []

        # ターゲット埋め込み (マスク前)
        target_embeddings = self.embedding.embed_all_transactions(transactions)

        losses = []
        for epoch in range(n_epochs):
            # マスク生成
            mask = np.ones(T, dtype=np.float32)
            n_mask = max(1, int(T * mask_ratio))
            mask_indices = rng.choice(T, size=n_mask, replace=False)
            mask[mask_indices] = 0

            # マスクされた入力を作成
            x = target_embeddings.copy()
            x[mask_indices] = 0  # マスク位置をゼロベクトルに

            # Self-Attention
            for layer in self.attention_layers:
                residual = x
                out, _ = layer.forward(x, mask)
                x = layer_norm(residual + out)

            # MTM head による復元
            predicted = x @ self.mtm_head  # (T, embed_dim)

            # マスク位置のみの損失計算 (MSE)
            diff = predicted[mask_indices] - target_embeddings[mask_indices]
            loss = float(np.mean(diff ** 2))
            losses.append(loss)

            # 簡易SGD更新 (MTM headのみ)
            # grad = d(loss)/d(W) where predicted = x @ W
            # loss = mean((x@W - target)^2), grad = 2/n * x^T @ (x@W - target)
            x_masked = x[mask_indices]  # (n_mask, embed_dim)
            grad = 2 * (x_masked.T @ diff) / n_mask  # (embed_dim, embed_dim)
            # Gradient clipping
            grad_norm = np.linalg.norm(grad)
            if grad_norm > 1.0:
                grad = grad / grad_norm
            self.mtm_head -= lr * grad

        return losses

    def pretrain_dip(
        self,
        transactions: List[List[List[int]]],
        dense_labels: np.ndarray,
        n_epochs: int = 20,
        lr: float = 0.01,
        seed: int = 42,
    ) -> List[float]:
        """
        Dense Interval Prediction による事前学習。

        各位置が密集区間内 (1) か外 (0) かを二値分類する。

        Args:
            dense_labels: (T,) 密集区間ラベル

        Returns:
            エポックごとの損失リスト
        """
        T = len(transactions)
        if T == 0:
            return []

        losses = []
        for epoch in range(n_epochs):
            # 順伝播
            encoded = self.encode(transactions)
            logits = (encoded @ self.dip_head + self.dip_bias).squeeze()  # (T,)
            probs = 1.0 / (1.0 + np.exp(-logits))  # sigmoid

            # Binary cross-entropy
            eps = 1e-7
            probs_clipped = np.clip(probs, eps, 1 - eps)
            bce = -np.mean(
                dense_labels * np.log(probs_clipped)
                + (1 - dense_labels) * np.log(1 - probs_clipped)
            )
            losses.append(float(bce))

            # 勾配計算・更新 (DIP headのみ)
            error = probs - dense_labels  # (T,)
            grad_w = encoded.T @ error.reshape(-1, 1) / T  # (embed_dim, 1)
            grad_b = np.mean(error)
            self.dip_head -= lr * grad_w
            self.dip_bias -= lr * grad_b

        return losses

    def detect_dense_intervals(
        self,
        transactions: List[List[List[int]]],
        score_threshold: float = 0.5,
        min_length: int = 3,
    ) -> List[Tuple[int, int]]:
        """
        基盤モデルの密集スコアから密集区間を検出する。

        連続してスコアが閾値を超える区間を密集区間として返す。

        Args:
            score_threshold: 密集判定閾値
            min_length: 最小区間長

        Returns:
            密集区間 (start, end) のリスト
        """
        scores = self.predict_dense_scores(transactions)
        intervals = []
        in_dense = False
        start = 0

        for t in range(len(scores)):
            if scores[t] >= score_threshold:
                if not in_dense:
                    in_dense = True
                    start = t
            else:
                if in_dense:
                    if t - start >= min_length:
                        intervals.append((start, t - 1))
                    in_dense = False

        if in_dense and len(scores) - start >= min_length:
            intervals.append((start, len(scores) - 1))

        return intervals


# ===========================================================================
# 5. Evaluation Utilities
# ===========================================================================

def compute_interval_iou(
    pred_intervals: List[Tuple[int, int]],
    true_intervals: List[Tuple[int, int]],
    total_length: int,
) -> Dict[str, float]:
    """
    密集区間検出の評価指標を計算する。

    Returns:
        precision, recall, f1, iou
    """
    pred_set = set()
    for s, e in pred_intervals:
        for t in range(s, e + 1):
            pred_set.add(t)

    true_set = set()
    for s, e in true_intervals:
        for t in range(s, e + 1):
            true_set.add(t)

    if not pred_set and not true_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "iou": 1.0}

    intersection = len(pred_set & true_set)
    union = len(pred_set | true_set)

    precision = intersection / len(pred_set) if pred_set else 0.0
    recall = intersection / len(true_set) if true_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    iou = intersection / union if union > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1, "iou": iou}


def generate_dense_labels(
    intervals: List[Tuple[int, int]],
    total_length: int,
    window_size: int = 0,
) -> np.ndarray:
    """
    密集区間から各位置のバイナリラベルを生成する。

    Args:
        intervals: 密集区間リスト
        total_length: 全長
        window_size: ウィンドウサイズ (密集期間 = [s, e+W])

    Returns:
        (total_length,) のバイナリ配列
    """
    labels = np.zeros(total_length, dtype=np.float32)
    for s, e in intervals:
        actual_end = min(e + window_size, total_length - 1)
        labels[s:actual_end + 1] = 1.0
    return labels


# ===========================================================================
# 6. Comparison with Traditional Method
# ===========================================================================

def compare_with_traditional(
    transactions: List[List[List[int]]],
    window_size: int,
    threshold: int,
    max_length: int,
    model: TransactionFoundationModel,
    score_threshold: float = 0.5,
) -> Dict[str, any]:
    """
    従来法 (Apriori-Window) と基盤モデルの密集区間検出を比較する。

    Returns:
        比較結果の辞書
    """
    # 従来法で密集区間を検出
    traditional_results = find_dense_itemsets(
        transactions, window_size, threshold, max_length
    )

    # 全密集区間をフラット化
    all_traditional_intervals = []
    for itemset, intervals in traditional_results.items():
        all_traditional_intervals.extend(intervals)

    # 密集ラベルを生成
    T = len(transactions)
    dense_labels = generate_dense_labels(all_traditional_intervals, T, window_size)

    # 基盤モデルを事前学習
    mtm_losses = model.pretrain_mtm(transactions, n_epochs=10)
    dip_losses = model.pretrain_dip(transactions, dense_labels, n_epochs=20)

    # 基盤モデルで密集区間を検出
    model_intervals = model.detect_dense_intervals(
        transactions, score_threshold=score_threshold, min_length=3
    )

    # 評価
    metrics = compute_interval_iou(model_intervals, all_traditional_intervals, T)

    return {
        "traditional_intervals": all_traditional_intervals,
        "model_intervals": model_intervals,
        "metrics": metrics,
        "mtm_losses": mtm_losses,
        "dip_losses": dip_losses,
        "n_traditional_patterns": len(traditional_results),
        "n_traditional_intervals": len(all_traditional_intervals),
        "n_model_intervals": len(model_intervals),
        "dense_ratio": float(dense_labels.mean()),
    }
