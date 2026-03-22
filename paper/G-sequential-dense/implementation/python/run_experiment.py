"""
Paper G: Sequential Dense Pattern 実験スクリプト

合成データで Sequential Dense Pattern マイニングの性能を評価する。

実験:
  E1: スケーラビリティ（トランザクション数 vs 実行時間）
  E2: パラメータ感度（window_size, threshold, max_gap の影響）
  E3: 従来法（アイテムセット密集パターン）との比較
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Dict, List, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent))

from sequential_dense import (
    build_item_occurrence_map,
    compute_dense_intervals,
    compute_sequential_occurrences,
    find_sequential_dense_patterns,
)


def generate_synthetic_data(
    n_transactions: int,
    n_items: int,
    n_seq_patterns: int = 3,
    pattern_length: int = 3,
    burst_regions: int = 2,
    burst_width: int = 50,
    seed: int = 42,
) -> Tuple[List[List[int]], List[dict]]:
    """
    系列パターンを埋め込んだ合成データを生成する。

    Returns:
      transactions, ground_truth_patterns
    """
    rng = random.Random(seed)
    transactions: List[List[int]] = [[] for _ in range(n_transactions)]

    # 背景ノイズ
    for t in range(n_transactions):
        n_bg = rng.randint(0, 3)
        bg_items = rng.sample(range(n_items), min(n_bg, n_items))
        transactions[t].extend(bg_items)

    ground_truth: List[dict] = []

    # 系列パターンを埋め込む
    for p_idx in range(n_seq_patterns):
        pattern_items = list(range(
            n_items + p_idx * pattern_length,
            n_items + (p_idx + 1) * pattern_length,
        ))

        for b in range(burst_regions):
            center = rng.randint(burst_width, n_transactions - burst_width)
            start = max(0, center - burst_width // 2)
            end = min(n_transactions - pattern_length, center + burst_width // 2)

            for t in range(start, end, pattern_length):
                for offset, item in enumerate(pattern_items):
                    if t + offset < n_transactions:
                        transactions[t + offset].append(item)

            ground_truth.append({
                "pattern": pattern_items,
                "burst_start": start,
                "burst_end": end + pattern_length,
            })

    return transactions, ground_truth


def run_scalability_experiment(
    sizes: List[int] = None,
    window_size: int = 20,
    threshold: int = 3,
    max_length: int = 3,
) -> List[dict]:
    """E1: スケーラビリティ実験"""
    if sizes is None:
        sizes = [500, 1000, 2000, 5000, 10000]

    results = []
    for n in sizes:
        txns, _ = generate_synthetic_data(n_transactions=n, n_items=20, seed=42)
        t0 = time.perf_counter()
        patterns = find_sequential_dense_patterns(
            txns, window_size, threshold, max_length, max_gap=0
        )
        elapsed = (time.perf_counter() - t0) * 1000
        n_patterns = sum(1 for k in patterns if len(k) >= 2)
        results.append({
            "n_transactions": n,
            "elapsed_ms": round(elapsed, 2),
            "n_seq_patterns": n_patterns,
            "n_total_patterns": len(patterns),
        })
        print(f"  N={n:>6}: {elapsed:>8.2f} ms, {n_patterns} seq patterns found")

    return results


def run_parameter_sensitivity(
    n_transactions: int = 2000,
) -> Dict[str, List[dict]]:
    """E2: パラメータ感度実験"""
    txns, _ = generate_synthetic_data(
        n_transactions=n_transactions, n_items=20, seed=42
    )

    results: Dict[str, List[dict]] = {}

    # window_size の影響
    print("  [window_size sweep]")
    ws_results = []
    for ws in [5, 10, 20, 40, 80]:
        t0 = time.perf_counter()
        patterns = find_sequential_dense_patterns(txns, ws, 3, 3, max_gap=0)
        elapsed = (time.perf_counter() - t0) * 1000
        n_seq = sum(1 for k in patterns if len(k) >= 2)
        ws_results.append({
            "window_size": ws,
            "elapsed_ms": round(elapsed, 2),
            "n_seq_patterns": n_seq,
        })
        print(f"    W={ws:>3}: {elapsed:>8.2f} ms, {n_seq} seq patterns")
    results["window_size"] = ws_results

    # threshold の影響
    print("  [threshold sweep]")
    th_results = []
    for th in [2, 3, 5, 8, 10]:
        t0 = time.perf_counter()
        patterns = find_sequential_dense_patterns(txns, 20, th, 3, max_gap=0)
        elapsed = (time.perf_counter() - t0) * 1000
        n_seq = sum(1 for k in patterns if len(k) >= 2)
        th_results.append({
            "threshold": th,
            "elapsed_ms": round(elapsed, 2),
            "n_seq_patterns": n_seq,
        })
        print(f"    T={th:>3}: {elapsed:>8.2f} ms, {n_seq} seq patterns")
    results["threshold"] = th_results

    # max_gap の影響
    print("  [max_gap sweep]")
    mg_results = []
    for mg in [0, 2, 5, 10, 20]:
        t0 = time.perf_counter()
        patterns = find_sequential_dense_patterns(txns, 20, 3, 3, max_gap=mg)
        elapsed = (time.perf_counter() - t0) * 1000
        n_seq = sum(1 for k in patterns if len(k) >= 2)
        mg_results.append({
            "max_gap": mg,
            "elapsed_ms": round(elapsed, 2),
            "n_seq_patterns": n_seq,
        })
        print(f"    G={mg:>3}: {elapsed:>8.2f} ms, {n_seq} seq patterns")
    results["max_gap"] = mg_results

    return results


def run_comparison_experiment(
    n_transactions: int = 2000,
) -> dict:
    """E3: 従来法（アイテムセット密集パターン）との比較"""
    txns, gt = generate_synthetic_data(
        n_transactions=n_transactions, n_items=20, seed=42
    )

    # Sequential Dense Pattern
    t0 = time.perf_counter()
    seq_patterns = find_sequential_dense_patterns(txns, 20, 3, 3, max_gap=0)
    seq_time = (time.perf_counter() - t0) * 1000

    n_seq = sum(1 for k in seq_patterns if len(k) >= 2)
    n_seq_total = len(seq_patterns)

    # アイテムセット密集パターン（順序なし）— 簡易比較
    # 同一アイテムセットでも順序の違いで別パターンとなる系列の優位性を示す
    itemset_patterns: dict = {}
    item_map = build_item_occurrence_map(txns)
    freq_items = sorted(item_map.keys())

    t0 = time.perf_counter()
    # 単一アイテム
    for item in freq_items:
        intervals = compute_dense_intervals(item_map[item], 20, 3)
        if intervals:
            itemset_patterns[(item,)] = intervals

    # ペア（順序なし）
    from itertools import combinations
    for a, b in combinations(freq_items, 2):
        co_occs = sorted(set(item_map[a]) & set(item_map[b]))
        if co_occs:
            intervals = compute_dense_intervals(co_occs, 20, 3)
            if intervals:
                itemset_patterns[(a, b)] = intervals
    itemset_time = (time.perf_counter() - t0) * 1000

    n_itemset = sum(1 for k in itemset_patterns if len(k) >= 2)

    return {
        "sequential": {
            "n_patterns": n_seq,
            "elapsed_ms": round(seq_time, 2),
        },
        "itemset": {
            "n_patterns": n_itemset,
            "elapsed_ms": round(itemset_time, 2),
        },
        "ground_truth_count": len(gt),
    }


def main():
    output_dir = Path(__file__).parent.parent.parent / "experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results = {}

    print("=" * 60)
    print("E1: Scalability Experiment")
    print("=" * 60)
    all_results["E1_scalability"] = run_scalability_experiment()

    print()
    print("=" * 60)
    print("E2: Parameter Sensitivity")
    print("=" * 60)
    all_results["E2_sensitivity"] = run_parameter_sensitivity()

    print()
    print("=" * 60)
    print("E3: Comparison with Itemset Dense Patterns")
    print("=" * 60)
    comp = run_comparison_experiment()
    all_results["E3_comparison"] = comp
    print(f"  Sequential: {comp['sequential']['n_patterns']} patterns in {comp['sequential']['elapsed_ms']:.2f} ms")
    print(f"  Itemset:    {comp['itemset']['n_patterns']} patterns in {comp['itemset']['elapsed_ms']:.2f} ms")

    # 結果を保存
    out_file = output_dir / "G_all_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    main()
