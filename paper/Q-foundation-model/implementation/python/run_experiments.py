"""
Paper Q: Transaction Foundation Model - Experiment Runner.

Experiments:
    E1: Masked Transaction Modeling (MTM) pre-training convergence
    E2: Dense Interval Prediction (DIP) accuracy
    E3: Foundation Model vs Traditional Apriori-Window comparison
    E4: Scalability analysis (varying transaction count)
    E5: Embedding quality analysis
"""

import json
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from transaction_embedding import (
    TransactionFoundationModel,
    TransactionEmbedding,
    DenseIntervalToken,
    compare_with_traditional,
    compute_interval_iou,
    generate_dense_labels,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python"))
from apriori_window_basket import (
    compute_dense_intervals,
    find_dense_itemsets,
)


# ===========================================================================
# Synthetic Data Generation
# ===========================================================================

def generate_synthetic_transactions(
    n_transactions: int = 500,
    n_items: int = 50,
    dense_intervals: List[Tuple[int, int, List[int]]] = None,
    base_density: float = 0.1,
    dense_density: float = 0.5,
    seed: int = 42,
) -> Tuple[List[List[List[int]]], List[Tuple[int, int]]]:
    """
    合成トランザクションデータを生成する。

    Args:
        n_transactions: トランザクション数
        n_items: アイテム種類数
        dense_intervals: [(start, end, items), ...] 密集区間定義
        base_density: ベースラインのアイテム出現確率
        dense_density: 密集区間内のアイテム出現確率
        seed: 乱数シード

    Returns:
        transactions, true_intervals
    """
    rng = np.random.RandomState(seed)

    if dense_intervals is None:
        dense_intervals = [
            (50, 100, [1, 2, 3]),
            (200, 250, [5, 10, 15]),
            (350, 400, [2, 7, 12]),
        ]

    transactions = []
    true_intervals = [(s, e) for s, e, _ in dense_intervals]

    for t in range(n_transactions):
        items = []
        # ベースラインアイテム
        for item in range(n_items):
            if rng.random() < base_density:
                items.append(item)

        # 密集区間内の追加アイテム
        for s, e, dense_items in dense_intervals:
            if s <= t <= e:
                for item in dense_items:
                    if rng.random() < dense_density and item not in items:
                        items.append(item)

        if not items:
            items = [rng.randint(0, n_items)]

        transactions.append([sorted(items)])

    return transactions, true_intervals


# ===========================================================================
# E1: MTM Pre-training Convergence
# ===========================================================================

def run_e1_mtm_convergence(seed: int = 42) -> Dict:
    """MTM事前学習の収束性を評価する。"""
    print("=== E1: MTM Pre-training Convergence ===")

    transactions, _ = generate_synthetic_transactions(
        n_transactions=300, n_items=50, seed=seed
    )

    model = TransactionFoundationModel(
        vocab_size=50, embed_dim=32, n_heads=4, n_layers=2, seed=seed
    )

    start_time = time.perf_counter()
    losses = model.pretrain_mtm(
        transactions, mask_ratio=0.15, n_epochs=30, lr=0.001, seed=seed
    )
    elapsed = time.perf_counter() - start_time

    results = {
        "experiment": "E1_MTM_Convergence",
        "n_transactions": len(transactions),
        "n_epochs": len(losses),
        "initial_loss": losses[0] if losses else None,
        "final_loss": losses[-1] if losses else None,
        "loss_reduction_ratio": (losses[0] - losses[-1]) / losses[0] if losses and losses[0] > 0 else 0,
        "losses": losses,
        "elapsed_sec": elapsed,
        "converged": losses[-1] < losses[0] * 0.5 if losses else False,
    }

    print(f"  Initial loss: {results['initial_loss']:.4f}")
    print(f"  Final loss:   {results['final_loss']:.4f}")
    print(f"  Reduction:    {results['loss_reduction_ratio']:.2%}")
    print(f"  Elapsed:      {elapsed:.3f}s")
    return results


# ===========================================================================
# E2: DIP Accuracy
# ===========================================================================

def run_e2_dip_accuracy(seed: int = 42) -> Dict:
    """密集区間予測の精度を評価する。"""
    print("=== E2: DIP Accuracy ===")

    transactions, true_intervals = generate_synthetic_transactions(
        n_transactions=500, n_items=50, seed=seed
    )
    T = len(transactions)
    window_size = 10
    dense_labels = generate_dense_labels(true_intervals, T, window_size)

    model = TransactionFoundationModel(
        vocab_size=50, embed_dim=32, n_heads=4, n_layers=2, seed=seed
    )

    # 事前学習
    model.pretrain_mtm(transactions, n_epochs=10, seed=seed)
    dip_losses = model.pretrain_dip(
        transactions, dense_labels, n_epochs=30, lr=0.01, seed=seed
    )

    # 予測
    scores = model.predict_dense_scores(transactions)

    # 閾値ごとのF1を計算
    best_f1 = 0
    best_threshold = 0.5
    threshold_results = []

    for thr in [0.3, 0.4, 0.5, 0.6, 0.7]:
        pred_labels = (scores >= thr).astype(float)
        tp = np.sum((pred_labels == 1) & (dense_labels == 1))
        fp = np.sum((pred_labels == 1) & (dense_labels == 0))
        fn = np.sum((pred_labels == 0) & (dense_labels == 1))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        threshold_results.append({
            "threshold": thr,
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
        })
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = thr

    # AUC近似 (5点台形法)
    tpr_list = []
    fpr_list = []
    for thr in np.linspace(0, 1, 50):
        pred = (scores >= thr).astype(float)
        tp = np.sum((pred == 1) & (dense_labels == 1))
        fp = np.sum((pred == 1) & (dense_labels == 0))
        fn = np.sum((pred == 0) & (dense_labels == 1))
        tn = np.sum((pred == 0) & (dense_labels == 0))
        tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        tpr_list.append(float(tpr))
        fpr_list.append(float(fpr))

    # Manual trapezoidal integration (numpy 2.x removed np.trapz)
    fpr_arr = np.array(fpr_list)
    tpr_arr = np.array(tpr_list)
    # Sort by fpr
    sorted_idx = np.argsort(fpr_arr)
    fpr_sorted = fpr_arr[sorted_idx]
    tpr_sorted = tpr_arr[sorted_idx]
    auc = float(np.abs(np.sum(
        (fpr_sorted[1:] - fpr_sorted[:-1]) * (tpr_sorted[1:] + tpr_sorted[:-1]) / 2
    )))

    results = {
        "experiment": "E2_DIP_Accuracy",
        "n_transactions": T,
        "dense_ratio": float(dense_labels.mean()),
        "dip_losses": dip_losses,
        "best_threshold": best_threshold,
        "best_f1": best_f1,
        "auc": auc,
        "threshold_results": threshold_results,
    }

    print(f"  Dense ratio:    {results['dense_ratio']:.2%}")
    print(f"  Best F1:        {best_f1:.4f} (threshold={best_threshold})")
    print(f"  AUC:            {auc:.4f}")
    return results


# ===========================================================================
# E3: Foundation Model vs Traditional
# ===========================================================================

def run_e3_comparison(seed: int = 42) -> Dict:
    """基盤モデルと従来法の比較実験。"""
    print("=== E3: Foundation Model vs Traditional ===")

    transactions, true_intervals = generate_synthetic_transactions(
        n_transactions=500, n_items=50, seed=seed
    )

    model = TransactionFoundationModel(
        vocab_size=50, embed_dim=32, n_heads=4, n_layers=2, seed=seed
    )

    window_size = 10
    threshold = 3
    max_length = 3

    start_trad = time.perf_counter()
    trad_results = find_dense_itemsets(transactions, window_size, threshold, max_length)
    time_trad = time.perf_counter() - start_trad

    # 従来法の密集区間
    trad_intervals = []
    for itemset, intervals in trad_results.items():
        trad_intervals.extend(intervals)

    # 基盤モデル学習 + 推論
    T = len(transactions)
    dense_labels = generate_dense_labels(trad_intervals, T, window_size)

    start_model = time.perf_counter()
    model.pretrain_mtm(transactions, n_epochs=10, seed=seed)
    model.pretrain_dip(transactions, dense_labels, n_epochs=20, seed=seed)
    model_intervals = model.detect_dense_intervals(transactions, score_threshold=0.5, min_length=3)
    time_model = time.perf_counter() - start_model

    metrics = compute_interval_iou(model_intervals, trad_intervals, T)

    results = {
        "experiment": "E3_Comparison",
        "n_transactions": T,
        "traditional": {
            "n_patterns": len(trad_results),
            "n_intervals": len(trad_intervals),
            "time_sec": time_trad,
        },
        "foundation_model": {
            "n_intervals": len(model_intervals),
            "time_sec": time_model,
            "intervals": [(s, e) for s, e in model_intervals],
        },
        "comparison_metrics": metrics,
    }

    print(f"  Traditional: {len(trad_results)} patterns, {len(trad_intervals)} intervals ({time_trad:.3f}s)")
    print(f"  Foundation:  {len(model_intervals)} intervals ({time_model:.3f}s)")
    print(f"  IoU: {metrics['iou']:.4f}, F1: {metrics['f1']:.4f}")
    return results


# ===========================================================================
# E4: Scalability Analysis
# ===========================================================================

def run_e4_scalability(seed: int = 42) -> Dict:
    """スケーラビリティ分析。"""
    print("=== E4: Scalability Analysis ===")

    sizes = [100, 200, 500, 1000, 2000]
    timing_results = []

    for n in sizes:
        transactions, _ = generate_synthetic_transactions(
            n_transactions=n, n_items=50, seed=seed
        )

        model = TransactionFoundationModel(
            vocab_size=50, embed_dim=32, n_heads=4, n_layers=2, seed=seed
        )

        # 符号化時間
        start = time.perf_counter()
        model.encode(transactions)
        encode_time = time.perf_counter() - start

        # 事前学習時間 (5エポック)
        start = time.perf_counter()
        model.pretrain_mtm(transactions, n_epochs=5, seed=seed)
        pretrain_time = time.perf_counter() - start

        # 推論時間
        start = time.perf_counter()
        model.predict_dense_scores(transactions)
        infer_time = time.perf_counter() - start

        entry = {
            "n_transactions": n,
            "encode_time_sec": encode_time,
            "pretrain_time_sec": pretrain_time,
            "inference_time_sec": infer_time,
        }
        timing_results.append(entry)
        print(f"  T={n:5d}: encode={encode_time:.4f}s, pretrain={pretrain_time:.4f}s, infer={infer_time:.4f}s")

    results = {
        "experiment": "E4_Scalability",
        "timing_results": timing_results,
    }
    return results


# ===========================================================================
# E5: Embedding Quality Analysis
# ===========================================================================

def run_e5_embedding_quality(seed: int = 42) -> Dict:
    """埋め込み品質の分析。"""
    print("=== E5: Embedding Quality Analysis ===")

    transactions, true_intervals = generate_synthetic_transactions(
        n_transactions=500, n_items=50, seed=seed
    )

    model = TransactionFoundationModel(
        vocab_size=50, embed_dim=32, n_heads=4, n_layers=2, seed=seed
    )

    # 事前学習前の埋め込み
    embeddings_before = model.encode(transactions)

    # 事前学習
    dense_labels = generate_dense_labels(true_intervals, len(transactions), window_size=10)
    model.pretrain_mtm(transactions, n_epochs=10, seed=seed)
    model.pretrain_dip(transactions, dense_labels, n_epochs=20, seed=seed)

    # 事前学習後の埋め込み
    embeddings_after = model.encode(transactions)

    # 密集区間内外の埋め込みの分離度を計算
    dense_mask = dense_labels > 0.5
    non_dense_mask = ~dense_mask

    def compute_separation(embeddings: np.ndarray) -> float:
        if dense_mask.sum() == 0 or non_dense_mask.sum() == 0:
            return 0.0
        dense_mean = embeddings[dense_mask].mean(axis=0)
        non_dense_mean = embeddings[non_dense_mask].mean(axis=0)
        distance = float(np.linalg.norm(dense_mean - non_dense_mean))
        return distance

    sep_before = compute_separation(embeddings_before)
    sep_after = compute_separation(embeddings_after)

    # コサイン類似度: 密集区間内のトランザクション間
    def mean_cosine_similarity(embeddings: np.ndarray, mask: np.ndarray) -> float:
        subset = embeddings[mask]
        if len(subset) < 2:
            return 0.0
        norms = np.linalg.norm(subset, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        normed = subset / norms
        sim_matrix = normed @ normed.T
        n = len(subset)
        total = sim_matrix.sum() - n  # exclude diagonal
        return float(total / (n * (n - 1))) if n > 1 else 0.0

    intra_sim_before = mean_cosine_similarity(embeddings_before, dense_mask)
    intra_sim_after = mean_cosine_similarity(embeddings_after, dense_mask)

    results = {
        "experiment": "E5_Embedding_Quality",
        "n_transactions": len(transactions),
        "n_dense": int(dense_mask.sum()),
        "n_non_dense": int(non_dense_mask.sum()),
        "separation_before": sep_before,
        "separation_after": sep_after,
        "separation_improvement": sep_after - sep_before,
        "intra_dense_cosine_before": intra_sim_before,
        "intra_dense_cosine_after": intra_sim_after,
    }

    print(f"  Separation before: {sep_before:.4f}")
    print(f"  Separation after:  {sep_after:.4f}")
    print(f"  Improvement:       {sep_after - sep_before:+.4f}")
    print(f"  Intra-dense cosine before: {intra_sim_before:.4f}")
    print(f"  Intra-dense cosine after:  {intra_sim_after:.4f}")
    return results


# ===========================================================================
# Main
# ===========================================================================

def main():
    results_dir = Path(__file__).parent.parent.parent / "experiments"
    results_dir.mkdir(parents=True, exist_ok=True)

    all_results = {}
    seed = 42

    all_results["E1"] = run_e1_mtm_convergence(seed)
    print()
    all_results["E2"] = run_e2_dip_accuracy(seed)
    print()
    all_results["E3"] = run_e3_comparison(seed)
    print()
    all_results["E4"] = run_e4_scalability(seed)
    print()
    all_results["E5"] = run_e5_embedding_quality(seed)
    print()

    # 結果をJSON出力
    output_path = results_dir / "all_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)

    print(f"All results saved to {output_path}")
    return all_results


if __name__ == "__main__":
    main()
