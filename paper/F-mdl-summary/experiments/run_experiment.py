"""
Paper F 実験スクリプト: MDL Summary の圧縮性能評価。

実験:
  E1: 合成データでの圧縮率評価
  E2: パターン数削減率の評価
  E3: ウィンドウサイズ感度分析
"""

import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation" / "python"))
from mdl_summary import (
    TemporalCodeEntry,
    build_standard_code_table,
    compression_ratio,
    greedy_mdl_selection,
    mine_temporal_patterns,
    run_mdl_summary,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apriori_window_suite" / "python"))
from apriori_window_basket import read_transactions_with_baskets


# ---------------------------------------------------------------------------
# 合成データ生成
# ---------------------------------------------------------------------------

def generate_synthetic_data(
    num_transactions: int = 200,
    num_items: int = 20,
    num_dense_patterns: int = 3,
    dense_region_length: int = 30,
    pattern_size: int = 3,
    background_density: float = 0.1,
    seed: int = 42,
) -> str:
    """
    密集区間を持つ合成トランザクションデータを生成する。

    Returns:
        一時ファイルのパス
    """
    import random
    random.seed(seed)

    lines = []
    # 密集パターンの定義
    patterns = []
    for i in range(num_dense_patterns):
        items = list(range(i * pattern_size + 1, (i + 1) * pattern_size + 1))
        start = int(num_transactions * (i + 1) / (num_dense_patterns + 2))
        end = start + dense_region_length
        patterns.append((items, start, min(end, num_transactions - 1)))

    for t in range(num_transactions):
        items_in_t = set()

        # 密集パターンの挿入
        for pat_items, start, end in patterns:
            if start <= t <= end:
                items_in_t.update(pat_items)

        # 背景ノイズ
        for item in range(1, num_items + 1):
            if item not in items_in_t and random.random() < background_density:
                items_in_t.add(item)

        if items_in_t:
            lines.append(" ".join(str(x) for x in sorted(items_in_t)))
        else:
            lines.append(str(random.randint(1, num_items)))

    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------------------
# E1: 圧縮率評価
# ---------------------------------------------------------------------------

def experiment_e1_compression():
    """E1: 様々な条件での圧縮率を評価する。"""
    print("=" * 60)
    print("E1: 圧縮率評価")
    print("=" * 60)

    configs = [
        {"num_transactions": 100, "num_dense_patterns": 2, "pattern_size": 2},
        {"num_transactions": 200, "num_dense_patterns": 3, "pattern_size": 3},
        {"num_transactions": 500, "num_dense_patterns": 5, "pattern_size": 3},
        {"num_transactions": 200, "num_dense_patterns": 3, "pattern_size": 4},
    ]

    results = []
    for i, cfg in enumerate(configs):
        path = generate_synthetic_data(**cfg, seed=42 + i)
        try:
            t0 = time.time()
            result = run_mdl_summary(path, window_size=10, min_support=3)
            elapsed = time.time() - t0

            entry = {
                "config": cfg,
                "num_candidates": result["num_candidates"],
                "num_selected": result["num_selected"],
                "compression_ratio": result["metrics"]["compression_ratio"],
                "baseline_length": result["metrics"]["baseline_length"],
                "compressed_length": result["metrics"]["compressed_length"],
                "elapsed_sec": round(elapsed, 4),
            }
            results.append(entry)

            print(f"\n--- Config {i+1}: N={cfg['num_transactions']}, "
                  f"P={cfg['num_dense_patterns']}, |X|={cfg['pattern_size']} ---")
            print(f"  Candidates: {entry['num_candidates']}")
            print(f"  Selected:   {entry['num_selected']}")
            print(f"  Compression ratio: {entry['compression_ratio']:.4f}")
            print(f"  Baseline:   {entry['baseline_length']:.2f} bits")
            print(f"  Compressed: {entry['compressed_length']:.2f} bits")
            print(f"  Time: {elapsed:.4f}s")
        finally:
            os.unlink(path)

    return results


# ---------------------------------------------------------------------------
# E2: パターン数削減率
# ---------------------------------------------------------------------------

def experiment_e2_reduction():
    """E2: MDL 選択によるパターン数削減率を評価する。"""
    print("\n" + "=" * 60)
    print("E2: パターン数削減率")
    print("=" * 60)

    path = generate_synthetic_data(
        num_transactions=300,
        num_dense_patterns=4,
        pattern_size=3,
        num_items=30,
        seed=123,
    )

    results = []
    try:
        transactions = read_transactions_with_baskets(path)
        sct = build_standard_code_table(transactions)

        for max_len in [2, 3, 4]:
            candidates = mine_temporal_patterns(
                transactions, window_size=10, min_support=3,
                max_pattern_length=max_len,
            )
            selected = greedy_mdl_selection(transactions, candidates, sct)

            reduction = 1.0 - len(selected) / max(1, len(candidates))
            entry = {
                "max_pattern_length": max_len,
                "num_candidates": len(candidates),
                "num_selected": len(selected),
                "reduction_rate": round(reduction, 4),
            }
            results.append(entry)

            print(f"\n  max_len={max_len}: {len(candidates)} -> {len(selected)} "
                  f"(reduction: {reduction:.1%})")
    finally:
        os.unlink(path)

    return results


# ---------------------------------------------------------------------------
# E3: ウィンドウサイズ感度分析
# ---------------------------------------------------------------------------

def experiment_e3_sensitivity():
    """E3: ウィンドウサイズの影響を評価する。"""
    print("\n" + "=" * 60)
    print("E3: ウィンドウサイズ感度分析")
    print("=" * 60)

    path = generate_synthetic_data(
        num_transactions=200,
        num_dense_patterns=3,
        pattern_size=3,
        seed=99,
    )

    results = []
    try:
        for ws in [5, 10, 15, 20, 30]:
            result = run_mdl_summary(path, window_size=ws, min_support=3)
            entry = {
                "window_size": ws,
                "num_candidates": result["num_candidates"],
                "num_selected": result["num_selected"],
                "compression_ratio": result["metrics"]["compression_ratio"],
            }
            results.append(entry)

            print(f"\n  W={ws}: candidates={entry['num_candidates']}, "
                  f"selected={entry['num_selected']}, "
                  f"ratio={entry['compression_ratio']:.4f}")
    finally:
        os.unlink(path)

    return results


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    all_results = {}

    all_results["e1_compression"] = experiment_e1_compression()
    all_results["e2_reduction"] = experiment_e2_reduction()
    all_results["e3_sensitivity"] = experiment_e3_sensitivity()

    # 結果を保存
    out_dir = Path(__file__).parent
    out_path = out_dir / "results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n\nResults saved to {out_path}")
    return all_results


if __name__ == "__main__":
    main()
