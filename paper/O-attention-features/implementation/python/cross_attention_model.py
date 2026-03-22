"""
Cross-Attention Event Attribution Model (NumPy implementation).

Implements scaled dot-product cross-attention for aligning event features
with dense pattern features, producing attribution scores.

Paper O: "Learning Event Attribution with Cross-Attention and Dense Pattern Featurization"
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

import numpy as np

from dense_pattern_features import (
    DensePatternFeature,
    Event,
    compute_time_binned_features,
)


# ---------------------------------------------------------------------------
# Utility: softmax, layer norm
# ---------------------------------------------------------------------------

def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Numerically stable softmax."""
    e_x = np.exp(x - np.max(x, axis=axis, keepdims=True))
    return e_x / (e_x.sum(axis=axis, keepdims=True) + 1e-12)


def layer_norm(x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Simple layer normalization along last axis."""
    mean = x.mean(axis=-1, keepdims=True)
    std = x.std(axis=-1, keepdims=True)
    return (x - mean) / (std + eps)


def relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0, x)


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))


# ---------------------------------------------------------------------------
# Cross-Attention Layer
# ---------------------------------------------------------------------------

@dataclass
class CrossAttentionConfig:
    """Configuration for the cross-attention model."""
    d_model: int = 32         # internal dimension
    d_pattern: int = 10       # input pattern feature dim (from DensePatternFeature)
    d_event: int = 3          # input event feature dim
    n_heads: int = 4          # number of attention heads
    d_ff: int = 64            # feed-forward hidden dim
    learning_rate: float = 0.01
    n_epochs: int = 200
    seed: int = 42


class CrossAttentionLayer:
    """
    Single-layer cross-attention: queries from events, keys/values from patterns.

    This is a simplified NumPy implementation of the Transformer cross-attention
    mechanism, suitable for small-scale event attribution tasks.
    """

    def __init__(self, config: CrossAttentionConfig):
        self.config = config
        self.rng = np.random.RandomState(config.seed)

        d = config.d_model
        h = config.n_heads
        dk = d // h

        # Projection matrices
        scale = 0.1

        # Project pattern features to d_model
        self.W_pattern = self.rng.randn(config.d_pattern, d) * scale
        self.b_pattern = np.zeros(d)

        # Project event features to d_model
        self.W_event = self.rng.randn(config.d_event, d) * scale
        self.b_event = np.zeros(d)

        # Query (from events), Key/Value (from patterns)
        self.W_Q = self.rng.randn(d, d) * scale
        self.W_K = self.rng.randn(d, d) * scale
        self.W_V = self.rng.randn(d, d) * scale
        self.W_O = self.rng.randn(d, d) * scale

        # FFN
        self.W_ff1 = self.rng.randn(d, config.d_ff) * scale
        self.b_ff1 = np.zeros(config.d_ff)
        self.W_ff2 = self.rng.randn(config.d_ff, d) * scale
        self.b_ff2 = np.zeros(d)

        # Output head: d_model -> 1 (attribution score)
        self.W_out = self.rng.randn(d, 1) * scale
        self.b_out = np.zeros(1)

    def _multi_head_attention(
        self, Q: np.ndarray, K: np.ndarray, V: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Scaled dot-product multi-head attention.

        Args:
            Q: (n_events, d_model) - queries from events
            K: (n_patterns, d_model) - keys from patterns
            V: (n_patterns, d_model) - values from patterns

        Returns:
            output: (n_events, d_model)
            attn_weights: (n_heads, n_events, n_patterns)
        """
        d = self.config.d_model
        h = self.config.n_heads
        dk = d // h

        # Linear projections
        Qp = Q @ self.W_Q  # (n_events, d)
        Kp = K @ self.W_K  # (n_patterns, d)
        Vp = V @ self.W_V  # (n_patterns, d)

        n_e = Q.shape[0]
        n_p = K.shape[0]

        # Reshape for multi-head: (n, d) -> (h, n, dk)
        Qp = Qp.reshape(n_e, h, dk).transpose(1, 0, 2)   # (h, n_e, dk)
        Kp = Kp.reshape(n_p, h, dk).transpose(1, 0, 2)    # (h, n_p, dk)
        Vp = Vp.reshape(n_p, h, dk).transpose(1, 0, 2)    # (h, n_p, dk)

        # Scaled dot-product attention
        scores = np.matmul(Qp, Kp.transpose(0, 2, 1)) / np.sqrt(dk)  # (h, n_e, n_p)
        attn_weights = softmax(scores, axis=-1)  # (h, n_e, n_p)

        # Weighted sum of values
        context = np.matmul(attn_weights, Vp)  # (h, n_e, dk)

        # Concatenate heads
        context = context.transpose(1, 0, 2).reshape(n_e, d)  # (n_e, d)

        # Output projection
        output = context @ self.W_O  # (n_e, d)

        return output, attn_weights

    def forward(
        self,
        pattern_features: np.ndarray,
        event_features: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Forward pass of the cross-attention model.

        Args:
            pattern_features: (n_patterns, d_pattern) - dense pattern feature vectors
            event_features: (n_events, d_event) - event feature vectors

        Returns:
            scores: (n_events, n_patterns) - attribution scores
            attn_weights: (n_heads, n_events, n_patterns) - attention weights
        """
        # Project to d_model
        P = pattern_features @ self.W_pattern + self.b_pattern  # (n_p, d)
        E = event_features @ self.W_event + self.b_event        # (n_e, d)

        P = layer_norm(P)
        E = layer_norm(E)

        # Cross-attention: events attend to patterns
        attn_out, attn_weights = self._multi_head_attention(E, P, P)

        # Residual + layer norm
        E2 = layer_norm(E + attn_out)

        # FFN
        ff = relu(E2 @ self.W_ff1 + self.b_ff1) @ self.W_ff2 + self.b_ff2
        E3 = layer_norm(E2 + ff)

        # Compute pairwise scores: each event-pattern pair
        # E3: (n_e, d), P: (n_p, d)
        # Score(e, p) = sigmoid(e^T W_score p)
        # Use bilinear scoring
        raw_scores = E3 @ self.W_out  # (n_e, 1) for global event embedding
        # Better: pairwise dot product
        pairwise = E3 @ P.T  # (n_e, n_p)
        scores = sigmoid(pairwise)

        return scores, attn_weights

    def get_params(self) -> List[np.ndarray]:
        """Return list of all trainable parameter arrays."""
        return [
            self.W_pattern, self.b_pattern,
            self.W_event, self.b_event,
            self.W_Q, self.W_K, self.W_V, self.W_O,
            self.W_ff1, self.b_ff1, self.W_ff2, self.b_ff2,
            self.W_out, self.b_out,
        ]


# ---------------------------------------------------------------------------
# Training with numerical gradient
# ---------------------------------------------------------------------------

def compute_loss(
    model: CrossAttentionLayer,
    pattern_features: np.ndarray,
    event_features: np.ndarray,
    targets: np.ndarray,
) -> float:
    """
    Binary cross-entropy loss.

    Args:
        targets: (n_events, n_patterns) binary ground-truth attribution matrix
    """
    scores, _ = model.forward(pattern_features, event_features)
    eps = 1e-7
    scores = np.clip(scores, eps, 1 - eps)
    loss = -np.mean(targets * np.log(scores) + (1 - targets) * np.log(1 - scores))
    return float(loss)


def train_model(
    model: CrossAttentionLayer,
    pattern_features: np.ndarray,
    event_features: np.ndarray,
    targets: np.ndarray,
    config: CrossAttentionConfig,
) -> List[float]:
    """
    Train model using numerical gradient descent.

    Returns list of loss values per epoch.
    """
    losses = []
    lr = config.learning_rate
    eps_grad = 1e-4

    params = model.get_params()

    for epoch in range(config.n_epochs):
        loss = compute_loss(model, pattern_features, event_features, targets)
        losses.append(loss)

        if epoch % 50 == 0:
            print(f"  Epoch {epoch:4d} | Loss: {loss:.4f}")

        # Numerical gradient for each parameter
        for param in params:
            grad = np.zeros_like(param)
            # Sample subset of parameters for efficiency
            flat = param.ravel()
            n_sample = min(len(flat), 50)  # Only update a subset each step
            indices = np.random.choice(len(flat), n_sample, replace=False)

            for idx in indices:
                old_val = flat[idx]

                flat[idx] = old_val + eps_grad
                loss_plus = compute_loss(model, pattern_features, event_features, targets)

                flat[idx] = old_val - eps_grad
                loss_minus = compute_loss(model, pattern_features, event_features, targets)

                flat[idx] = old_val
                grad_val = (loss_plus - loss_minus) / (2 * eps_grad)

                flat[idx] -= lr * grad_val

    return losses


# ---------------------------------------------------------------------------
# Faster analytical gradient approach (for better convergence)
# ---------------------------------------------------------------------------

def train_model_analytical(
    model: CrossAttentionLayer,
    pattern_features: np.ndarray,
    event_features: np.ndarray,
    targets: np.ndarray,
    config: CrossAttentionConfig,
) -> List[float]:
    """
    Train using a simpler gradient approach on the bilinear scoring.

    For the sigmoid(E @ P^T) scoring, we can compute gradients analytically
    for the projection matrices.
    """
    losses = []
    lr = config.learning_rate

    for epoch in range(config.n_epochs):
        # Forward
        P = pattern_features @ model.W_pattern + model.b_pattern
        E = event_features @ model.W_event + model.b_event
        P = layer_norm(P)
        E = layer_norm(E)

        pairwise = E @ P.T
        scores = sigmoid(pairwise)

        eps = 1e-7
        scores_clipped = np.clip(scores, eps, 1 - eps)
        loss = -np.mean(
            targets * np.log(scores_clipped) +
            (1 - targets) * np.log(1 - scores_clipped)
        )
        losses.append(float(loss))

        if epoch % 50 == 0:
            print(f"  Epoch {epoch:4d} | Loss: {loss:.4f}")

        # Gradient of BCE w.r.t. pairwise scores
        d_scores = (scores_clipped - targets) / (scores_clipped * (1 - scores_clipped) + eps)
        d_pairwise = d_scores * scores_clipped * (1 - scores_clipped)
        d_pairwise /= (targets.shape[0] * targets.shape[1])

        # Gradient w.r.t. E and P (before layer norm, simplified)
        dE = d_pairwise @ P   # (n_e, d)
        dP = d_pairwise.T @ E  # (n_p, d)

        # Update projection matrices
        model.W_event -= lr * (event_features.T @ dE)
        model.b_event -= lr * dE.sum(axis=0)
        model.W_pattern -= lr * (pattern_features.T @ dP)
        model.b_pattern -= lr * dP.sum(axis=0)

    return losses


# ---------------------------------------------------------------------------
# Attribution scoring (inference)
# ---------------------------------------------------------------------------

@dataclass
class AttributionResult:
    """Result of event-pattern attribution."""
    event_type: str
    event_timestamp: int
    pattern_itemset: Tuple[int, ...]
    attribution_score: float
    attention_weights: Dict[str, float]  # head_name -> weight


def compute_attribution(
    model: CrossAttentionLayer,
    patterns: List[DensePatternFeature],
    events: List[Event],
    total_time: int,
) -> List[AttributionResult]:
    """
    Compute attribution scores between all events and patterns.

    Returns:
        List of AttributionResult sorted by score (descending).
    """
    if not patterns or not events:
        return []

    pattern_features = np.vstack([p.to_vector() for p in patterns])
    event_features = np.vstack([e.to_vector(total_time) for e in events])

    scores, attn_weights = model.forward(pattern_features, event_features)
    # scores: (n_events, n_patterns)
    # attn_weights: (n_heads, n_events, n_patterns)

    results = []
    for i, evt in enumerate(events):
        for j, pat in enumerate(patterns):
            head_weights = {
                f"head_{h}": float(attn_weights[h, i, j])
                for h in range(attn_weights.shape[0])
            }
            results.append(AttributionResult(
                event_type=evt.event_type,
                event_timestamp=evt.timestamp,
                pattern_itemset=pat.itemset,
                attribution_score=float(scores[i, j]),
                attention_weights=head_weights,
            ))

    results.sort(key=lambda r: r.attribution_score, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Baseline: Permutation Test (for comparison)
# ---------------------------------------------------------------------------

def permutation_test_attribution(
    patterns: List[DensePatternFeature],
    events: List[Event],
    total_time: int,
    n_permutations: int = 1000,
    seed: int = 42,
) -> np.ndarray:
    """
    Baseline attribution via permutation test.

    For each event-pattern pair, test whether the temporal overlap
    between event window and pattern intervals is significantly
    greater than chance.

    Returns:
        p_values: (n_events, n_patterns) matrix of p-values
    """
    rng = np.random.RandomState(seed)
    n_events = len(events)
    n_patterns = len(patterns)
    p_values = np.ones((n_events, n_patterns))

    for i, evt in enumerate(events):
        evt_window = 30  # effect window
        evt_start = evt.timestamp
        evt_end = evt.timestamp + evt_window

        for j, pat in enumerate(patterns):
            # Observed overlap
            obs_overlap = 0
            for s, e in pat.intervals:
                overlap = max(0, min(e, evt_end) - max(s, evt_start) + 1)
                obs_overlap += overlap

            if obs_overlap == 0:
                continue

            # Permutation: randomly shift pattern intervals
            count_ge = 0
            for _ in range(n_permutations):
                shift = rng.randint(0, total_time)
                perm_overlap = 0
                for s, e in pat.intervals:
                    dur = e - s
                    ns = (s + shift) % total_time
                    ne = ns + dur
                    overlap = max(0, min(ne, evt_end) - max(ns, evt_start) + 1)
                    perm_overlap += overlap
                if perm_overlap >= obs_overlap:
                    count_ge += 1

            p_values[i, j] = (count_ge + 1) / (n_permutations + 1)

    return p_values
