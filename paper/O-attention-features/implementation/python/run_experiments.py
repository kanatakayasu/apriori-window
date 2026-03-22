"""
Experiment runner for Paper O: Cross-Attention Event Attribution.

Experiments:
  E1: Synthetic data - known event attribution recovery accuracy
  E2: Attention weight interpretability evaluation
  E3: Comparison with permutation test baseline
  E4: Scalability analysis
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# Ensure local imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dense_pattern_features import (
    DensePatternFeature,
    Event,
    extract_dense_patterns,
    generate_synthetic_data,
    compute_time_binned_features,
)
from cross_attention_model import (
    CrossAttentionConfig,
    CrossAttentionLayer,
    compute_attribution,
    compute_loss,
    train_model_analytical,
    permutation_test_attribution,
    AttributionResult,
)


# ---------------------------------------------------------------------------
# Evaluation metrics
# ---------------------------------------------------------------------------

def precision_at_k(
    attribution_results: List[AttributionResult],
    ground_truth: Dict[str, List[Tuple[int, ...]]],
    k: int = 10,
) -> float:
    """Precision@K: fraction of top-K attributions that are correct."""
    top_k = attribution_results[:k]
    correct = 0
    for r in top_k:
        if r.event_type in ground_truth:
            if r.pattern_itemset in ground_truth[r.event_type]:
                correct += 1
    return correct / k if k > 0 else 0.0


def recall_at_k(
    attribution_results: List[AttributionResult],
    ground_truth: Dict[str, List[Tuple[int, ...]]],
    k: int = 10,
) -> float:
    """Recall@K: fraction of true attributions recovered in top-K."""
    total_true = sum(len(v) for v in ground_truth.values())
    if total_true == 0:
        return 0.0

    top_k = attribution_results[:k]
    recovered = set()
    for r in top_k:
        if r.event_type in ground_truth:
            if r.pattern_itemset in ground_truth[r.event_type]:
                recovered.add((r.event_type, r.pattern_itemset))

    return len(recovered) / total_true


def ndcg_at_k(
    attribution_results: List[AttributionResult],
    ground_truth: Dict[str, List[Tuple[int, ...]]],
    k: int = 10,
) -> float:
    """NDCG@K for attribution ranking quality."""
    relevance = []
    for r in attribution_results[:k]:
        if r.event_type in ground_truth:
            if r.pattern_itemset in ground_truth[r.event_type]:
                relevance.append(1.0)
            else:
                relevance.append(0.0)
        else:
            relevance.append(0.0)

    # DCG
    dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(relevance))

    # Ideal DCG
    total_true = sum(len(v) for v in ground_truth.values())
    ideal_rel = [1.0] * min(total_true, k) + [0.0] * max(0, k - total_true)
    idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_rel))

    return dcg / idcg if idcg > 0 else 0.0


def attribution_auc(
    scores: np.ndarray,
    targets: np.ndarray,
) -> float:
    """Compute AUC for binary attribution predictions."""
    from itertools import product

    flat_scores = scores.ravel()
    flat_targets = targets.ravel()

    pos_scores = flat_scores[flat_targets == 1]
    neg_scores = flat_scores[flat_targets == 0]

    if len(pos_scores) == 0 or len(neg_scores) == 0:
        return 0.5

    # Mann-Whitney U statistic
    correct = 0
    total = len(pos_scores) * len(neg_scores)
    for ps in pos_scores:
        correct += np.sum(ps > neg_scores)
        correct += 0.5 * np.sum(ps == neg_scores)

    return float(correct / total)


# ---------------------------------------------------------------------------
# E1: Known Event Attribution Recovery
# ---------------------------------------------------------------------------

def run_e1(seeds: List[int] = [42, 123, 456, 789, 1024]) -> Dict:
    """
    E1: Evaluate attribution recovery accuracy on synthetic data.

    Multiple seeds, measure Precision@K, Recall@K, NDCG@K, AUC.
    """
    print("=" * 60)
    print("E1: Known Event Attribution Recovery")
    print("=" * 60)

    all_metrics = {
        "precision_at_5": [], "precision_at_10": [],
        "recall_at_5": [], "recall_at_10": [],
        "ndcg_at_10": [], "auc": [],
    }

    for seed in seeds:
        print(f"\n--- Seed {seed} ---")
        path, events, gt = generate_synthetic_data(
            num_transactions=500, num_items=20, num_events=5,
            event_effect_window=30, seed=seed,
        )

        patterns = extract_dense_patterns(
            path, window_size=10, threshold=3, max_itemset_size=2, min_support=3,
        )

        if not patterns:
            print(f"  No patterns found for seed {seed}, skipping")
            os.unlink(path)
            continue

        print(f"  Found {len(patterns)} patterns, {len(events)} events")

        total_time = 500
        pattern_features = np.vstack([p.to_vector() for p in patterns])
        event_features = np.vstack([e.to_vector(total_time) for e in events])

        # Build target matrix
        targets = np.zeros((len(events), len(patterns)))
        for i, evt in enumerate(events):
            for j, pat in enumerate(patterns):
                if evt.event_type in gt and pat.itemset in gt[evt.event_type]:
                    targets[i, j] = 1.0

        # Train model
        config = CrossAttentionConfig(
            d_model=32, n_heads=4, d_ff=64,
            learning_rate=0.005, n_epochs=200, seed=seed,
        )
        model = CrossAttentionLayer(config)
        losses = train_model_analytical(
            model, pattern_features, event_features, targets, config,
        )

        # Evaluate
        results = compute_attribution(model, patterns, events, total_time)
        scores, _ = model.forward(pattern_features, event_features)

        p5 = precision_at_k(results, gt, k=5)
        p10 = precision_at_k(results, gt, k=10)
        r5 = recall_at_k(results, gt, k=5)
        r10 = recall_at_k(results, gt, k=10)
        n10 = ndcg_at_k(results, gt, k=10)
        auc = attribution_auc(scores, targets)

        all_metrics["precision_at_5"].append(p5)
        all_metrics["precision_at_10"].append(p10)
        all_metrics["recall_at_5"].append(r5)
        all_metrics["recall_at_10"].append(r10)
        all_metrics["ndcg_at_10"].append(n10)
        all_metrics["auc"].append(auc)

        print(f"  P@5={p5:.3f} P@10={p10:.3f} R@5={r5:.3f} R@10={r10:.3f} NDCG@10={n10:.3f} AUC={auc:.3f}")
        print(f"  Final loss: {losses[-1]:.4f}")

        os.unlink(path)

    # Aggregate
    result = {}
    for k, vals in all_metrics.items():
        if vals:
            result[k] = {"mean": float(np.mean(vals)), "std": float(np.std(vals))}
        else:
            result[k] = {"mean": 0.0, "std": 0.0}

    print(f"\n--- E1 Summary ---")
    for k, v in result.items():
        print(f"  {k}: {v['mean']:.3f} +/- {v['std']:.3f}")

    return result


# ---------------------------------------------------------------------------
# E2: Attention Weight Interpretability
# ---------------------------------------------------------------------------

def run_e2(seed: int = 42) -> Dict:
    """
    E2: Evaluate attention weight interpretability.

    Measures:
    - Attention entropy (lower = more focused = more interpretable)
    - Head specialization (variance across heads)
    - Alignment between attention weights and ground truth
    """
    print("\n" + "=" * 60)
    print("E2: Attention Weight Interpretability")
    print("=" * 60)

    path, events, gt = generate_synthetic_data(
        num_transactions=500, num_items=20, num_events=5,
        event_effect_window=30, seed=seed,
    )

    patterns = extract_dense_patterns(
        path, window_size=10, threshold=3, max_itemset_size=2, min_support=3,
    )

    if not patterns:
        os.unlink(path)
        return {"error": "no patterns found"}

    total_time = 500
    pattern_features = np.vstack([p.to_vector() for p in patterns])
    event_features = np.vstack([e.to_vector(total_time) for e in events])

    # Build targets and train
    targets = np.zeros((len(events), len(patterns)))
    for i, evt in enumerate(events):
        for j, pat in enumerate(patterns):
            if evt.event_type in gt and pat.itemset in gt[evt.event_type]:
                targets[i, j] = 1.0

    config = CrossAttentionConfig(
        d_model=32, n_heads=4, d_ff=64,
        learning_rate=0.005, n_epochs=200, seed=seed,
    )
    model = CrossAttentionLayer(config)
    train_model_analytical(model, pattern_features, event_features, targets, config)

    # Get attention weights
    _, attn_weights = model.forward(pattern_features, event_features)
    # attn_weights: (n_heads, n_events, n_patterns)

    # Entropy per head
    head_entropies = []
    for h in range(attn_weights.shape[0]):
        # Average entropy over events
        entropies = []
        for i in range(attn_weights.shape[1]):
            w = attn_weights[h, i]
            w = w + 1e-10
            entropy = -np.sum(w * np.log2(w))
            entropies.append(entropy)
        head_entropies.append(float(np.mean(entropies)))

    # Head specialization: std of attention weights across heads
    mean_attn_per_head = attn_weights.mean(axis=(1, 2))  # (n_heads,)
    head_specialization = float(np.std(mean_attn_per_head))

    # Attention-ground truth alignment
    # Average attention weight on true pairs vs false pairs
    avg_attn = attn_weights.mean(axis=0)  # (n_events, n_patterns)
    true_mask = targets > 0
    false_mask = targets == 0

    attn_on_true = float(avg_attn[true_mask].mean()) if true_mask.any() else 0.0
    attn_on_false = float(avg_attn[false_mask].mean()) if false_mask.any() else 0.0
    alignment_ratio = attn_on_true / (attn_on_false + 1e-10)

    result = {
        "head_entropies": head_entropies,
        "mean_entropy": float(np.mean(head_entropies)),
        "max_possible_entropy": float(np.log2(len(patterns))),
        "head_specialization": head_specialization,
        "attn_on_true_pairs": attn_on_true,
        "attn_on_false_pairs": attn_on_false,
        "alignment_ratio": alignment_ratio,
    }

    print(f"  Head entropies: {[f'{e:.3f}' for e in head_entropies]}")
    print(f"  Mean entropy: {result['mean_entropy']:.3f} (max possible: {result['max_possible_entropy']:.3f})")
    print(f"  Head specialization (std): {head_specialization:.4f}")
    print(f"  Attn on true pairs: {attn_on_true:.4f}")
    print(f"  Attn on false pairs: {attn_on_false:.4f}")
    print(f"  Alignment ratio: {alignment_ratio:.3f}")

    os.unlink(path)
    return result


# ---------------------------------------------------------------------------
# E3: Comparison with Permutation Test
# ---------------------------------------------------------------------------

def run_e3(seeds: List[int] = [42, 123, 456]) -> Dict:
    """
    E3: Compare cross-attention attribution with permutation test baseline.
    """
    print("\n" + "=" * 60)
    print("E3: Cross-Attention vs Permutation Test")
    print("=" * 60)

    ca_aucs = []
    pt_aucs = []

    for seed in seeds:
        print(f"\n--- Seed {seed} ---")
        path, events, gt = generate_synthetic_data(
            num_transactions=500, num_items=20, num_events=5,
            event_effect_window=30, seed=seed,
        )

        patterns = extract_dense_patterns(
            path, window_size=10, threshold=3, max_itemset_size=2, min_support=3,
        )

        if not patterns:
            os.unlink(path)
            continue

        total_time = 500
        pattern_features = np.vstack([p.to_vector() for p in patterns])
        event_features = np.vstack([e.to_vector(total_time) for e in events])

        # Ground truth
        targets = np.zeros((len(events), len(patterns)))
        for i, evt in enumerate(events):
            for j, pat in enumerate(patterns):
                if evt.event_type in gt and pat.itemset in gt[evt.event_type]:
                    targets[i, j] = 1.0

        # Cross-attention model
        config = CrossAttentionConfig(
            d_model=32, n_heads=4, d_ff=64,
            learning_rate=0.005, n_epochs=200, seed=seed,
        )
        model = CrossAttentionLayer(config)
        train_model_analytical(model, pattern_features, event_features, targets, config)
        ca_scores, _ = model.forward(pattern_features, event_features)
        ca_auc = attribution_auc(ca_scores, targets)

        # Permutation test baseline
        pt_pvalues = permutation_test_attribution(
            patterns, events, total_time, n_permutations=500, seed=seed,
        )
        pt_scores = 1 - pt_pvalues  # Convert p-values to scores
        pt_auc = attribution_auc(pt_scores, targets)

        ca_aucs.append(ca_auc)
        pt_aucs.append(pt_auc)

        print(f"  Cross-Attention AUC: {ca_auc:.3f}")
        print(f"  Permutation Test AUC: {pt_auc:.3f}")
        print(f"  Improvement: {ca_auc - pt_auc:+.3f}")

        os.unlink(path)

    result = {
        "cross_attention": {
            "auc_mean": float(np.mean(ca_aucs)) if ca_aucs else 0.0,
            "auc_std": float(np.std(ca_aucs)) if ca_aucs else 0.0,
        },
        "permutation_test": {
            "auc_mean": float(np.mean(pt_aucs)) if pt_aucs else 0.0,
            "auc_std": float(np.std(pt_aucs)) if pt_aucs else 0.0,
        },
    }

    print(f"\n--- E3 Summary ---")
    print(f"  CA  AUC: {result['cross_attention']['auc_mean']:.3f} +/- {result['cross_attention']['auc_std']:.3f}")
    print(f"  PT  AUC: {result['permutation_test']['auc_mean']:.3f} +/- {result['permutation_test']['auc_std']:.3f}")

    return result


# ---------------------------------------------------------------------------
# E4: Scalability Analysis
# ---------------------------------------------------------------------------

def run_e4() -> Dict:
    """
    E4: Measure runtime scaling with number of patterns and events.
    """
    print("\n" + "=" * 60)
    print("E4: Scalability Analysis")
    print("=" * 60)

    configs = [
        {"n_tx": 200, "n_items": 10, "n_events": 3, "label": "Small"},
        {"n_tx": 500, "n_items": 20, "n_events": 5, "label": "Medium"},
        {"n_tx": 1000, "n_items": 30, "n_events": 10, "label": "Large"},
        {"n_tx": 2000, "n_items": 40, "n_events": 15, "label": "XLarge"},
    ]

    results = []

    for cfg in configs:
        print(f"\n--- {cfg['label']}: {cfg['n_tx']} tx, {cfg['n_items']} items, {cfg['n_events']} events ---")

        t0 = time.time()
        path, events, gt = generate_synthetic_data(
            num_transactions=cfg["n_tx"],
            num_items=cfg["n_items"],
            num_events=cfg["n_events"],
            event_effect_window=30,
            seed=42,
        )
        t_gen = time.time() - t0

        t0 = time.time()
        patterns = extract_dense_patterns(
            path, window_size=10, threshold=3, max_itemset_size=2, min_support=3,
        )
        t_extract = time.time() - t0

        if not patterns:
            os.unlink(path)
            results.append({
                "label": cfg["label"],
                "n_patterns": 0,
                "error": "no patterns",
            })
            continue

        total_time = cfg["n_tx"]
        pattern_features = np.vstack([p.to_vector() for p in patterns])
        event_features = np.vstack([e.to_vector(total_time) for e in events[:cfg["n_events"]]])

        targets = np.zeros((len(events[:cfg["n_events"]]), len(patterns)))

        t0 = time.time()
        config_model = CrossAttentionConfig(
            d_model=32, n_heads=4, d_ff=64,
            learning_rate=0.005, n_epochs=100, seed=42,
        )
        model = CrossAttentionLayer(config_model)
        train_model_analytical(model, pattern_features, event_features, targets, config_model)
        t_train = time.time() - t0

        t0 = time.time()
        _ = compute_attribution(model, patterns, events[:cfg["n_events"]], total_time)
        t_infer = time.time() - t0

        r = {
            "label": cfg["label"],
            "n_transactions": cfg["n_tx"],
            "n_items": cfg["n_items"],
            "n_events": cfg["n_events"],
            "n_patterns": len(patterns),
            "time_data_gen_s": round(t_gen, 4),
            "time_feature_extract_s": round(t_extract, 4),
            "time_train_s": round(t_train, 4),
            "time_inference_s": round(t_infer, 4),
            "time_total_s": round(t_gen + t_extract + t_train + t_infer, 4),
        }
        results.append(r)

        print(f"  Patterns: {len(patterns)}")
        print(f"  Data gen:    {t_gen:.4f}s")
        print(f"  Extraction:  {t_extract:.4f}s")
        print(f"  Training:    {t_train:.4f}s")
        print(f"  Inference:   {t_infer:.4f}s")

        os.unlink(path)

    return {"scalability": results}


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_all_experiments() -> Dict:
    """Run all experiments and return combined results."""
    all_results = {}

    all_results["e1_attribution_recovery"] = run_e1()
    all_results["e2_interpretability"] = run_e2()
    all_results["e3_comparison"] = run_e3()
    all_results["e4_scalability"] = run_e4()

    return all_results


if __name__ == "__main__":
    results = run_all_experiments()

    # Save results
    out_dir = Path(__file__).resolve().parent.parent.parent / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "all_results.json"

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {out_path}")
