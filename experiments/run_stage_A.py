"""
run_stage_A.py
==============
Stage A 全実験（A1-P/PL, A2-P/PL, A3-P/PL）のオーケストレーター。
subprocess を使わず直接 import して実行するため高速。

使用方法:
    # 全実験
    python experiments/run_stage_A.py

    # 特定の実験のみ
    python experiments/run_stage_A.py --experiments A1
    python experiments/run_stage_A.py --experiments A1 A2

    # 出力先を変更
    python experiments/run_stage_A.py --output-dir /path/to/results

実験設計:
    A1-P  : λ_baskets sweep (Poisson, N=10K, seeds=5)
    A1-PL : λ_baskets sweep (PowerLaw, N=10K, seeds=10)
    A2-P  : G sweep (Poisson, N=10K, λ=2.0, seeds=5)
    A2-PL : G sweep (PowerLaw, N=10K, λ=2.0, seeds=10)
    A3-P  : N sweep (Poisson, λ=2.0, G=10, seeds=3, skip-gt)
    A3-PL : N sweep (PowerLaw, λ=2.0, G=10, seeds=3, skip-gt)

出力 CSV:
    results/A1_spr.csv
        experiment, model, lambda_baskets, seed,
        gt_spr, gt_n_txn_frequent, gt_n_spurious,
        phase1_multi, traditional_multi, observed_spurious,
        phase1_elapsed_ms, traditional_elapsed_ms

    results/A2_spr.csv
        experiment, model, G, seed,
        gt_spr, gt_n_txn_frequent, gt_n_spurious,
        phase1_multi, traditional_multi, observed_spurious,
        phase1_elapsed_ms, traditional_elapsed_ms

    results/A3_timing.csv
        experiment, model, n_transactions, seed,
        phase1_elapsed_ms, traditional_elapsed_ms
"""

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 実験スクリプトのルートを sys.path に追加（同ディレクトリの gen_synthetic, run_phase1 を import）
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from gen_synthetic import (
    compute_ground_truth,
    generate_transactions,
    write_transactions,
)
from run_phase1 import run_experiment

# ---------------------------------------------------------------------------
# 共通実験パラメータ
# ---------------------------------------------------------------------------

COMMON = {
    "n_items": 200,
    "lambda_basket_size": 3.0,
    "alpha_n": 2.5,
    "alpha_k": 2.5,
    "p_same": 0.8,
    "zipf_alpha": 1.2,
    "min_support": 50,
    "window_size": 500,
    "max_length": 4,
}

# ---------------------------------------------------------------------------
# 1ケースの実行（データ生成 + GT + Phase 1 実行）
# ---------------------------------------------------------------------------

def run_one_case(
    model: str,
    n_transactions: int,
    n_categories: int,
    lambda_baskets: float,
    seed: int,
    data_dir: Path,
    prefix: str,
    skip_gt: bool = False,
    save_txn: bool = True,
) -> Dict[str, Any]:
    """
    1パラメータセット × 1シードの実験を実行する。

    Returns:
        {
            "gt": {...} or None,
            "run": {"phase1": {...}, "traditional": {...}, "observed_spurious": int}
        }
    """
    rng = random.Random(seed)

    # --- データ生成 ---
    transactions = generate_transactions(
        n_transactions=n_transactions,
        n_items=COMMON["n_items"],
        n_categories=n_categories,
        lambda_baskets=lambda_baskets,
        lambda_basket_size=COMMON["lambda_basket_size"],
        alpha_n=COMMON["alpha_n"],
        alpha_k=COMMON["alpha_k"],
        p_same=COMMON["p_same"],
        zipf_alpha=COMMON["zipf_alpha"],
        model=model,
        rng=rng,
    )

    # --- ファイル保存（記録用）---
    if save_txn:
        txn_file = data_dir / f"{prefix}_seed{seed}.txt"
        write_transactions(str(txn_file), transactions)

    # --- Ground Truth 計算 ---
    gt: Optional[dict] = None
    if not skip_gt:
        gt = compute_ground_truth(
            transactions, COMMON["min_support"], COMMON["max_length"]
        )
        # GT を JSON 保存
        gt_file = data_dir / f"{prefix}_seed{seed}_gt.json"
        with open(gt_file, "w", encoding="utf-8") as f:
            json.dump(gt, f, ensure_ascii=False)

    # --- Phase 1 / 従来法の実行 ---
    run_result = run_experiment(
        transactions,
        window_size=COMMON["window_size"],
        min_support=COMMON["min_support"],
        max_length=COMMON["max_length"],
    )

    return {"gt": gt, "run": run_result}


# ---------------------------------------------------------------------------
# CSV 書き出しヘルパー
# ---------------------------------------------------------------------------

def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[csv] Wrote {path} ({len(rows)} rows)")


# ---------------------------------------------------------------------------
# 実験 A1: λ_baskets sweep
# ---------------------------------------------------------------------------

A1_FIELDS = [
    "experiment", "model", "lambda_baskets", "seed",
    "gt_spr", "gt_n_txn_frequent", "gt_n_spurious",
    "phase1_multi", "traditional_multi", "observed_spurious",
    "phase1_core_ms",
    "trad_flatten_ms", "trad_core_ms", "trad_total_ms",
]


def run_A1(output_dir: Path, data_dir: Path) -> None:
    print("\n" + "=" * 60)
    print("=== 実験 A1: λ_baskets sweep ===")
    print("=" * 60)

    lambda_values = [1.0, 1.5, 2.0, 3.0, 5.0]
    configs = [
        ("A1-P", "poisson", 5),
    ]

    rows: List[Dict[str, Any]] = []
    total = sum(len(lambda_values) * n_seeds for _, _, n_seeds in configs)
    done = 0

    for exp_name, model, n_seeds in configs:
        print(f"\n--- {exp_name} (model={model}, seeds={n_seeds}) ---")
        for lam in lambda_values:
            for seed in range(n_seeds):
                done += 1
                prefix = f"{exp_name}_lambda{lam}"
                print(f"  [{done}/{total}] {exp_name} lambda={lam} seed={seed}", end=" ")
                t_start = time.perf_counter()

                result = run_one_case(
                    model=model,
                    n_transactions=10000,
                    n_categories=10,
                    lambda_baskets=lam,
                    seed=seed,
                    data_dir=data_dir,
                    prefix=prefix,
                    skip_gt=False,
                )

                elapsed = time.perf_counter() - t_start
                gt = result["gt"]
                run = result["run"]

                gt_spr = gt["spr"] if gt else float("nan")
                gt_n_txn = gt["n_txn_frequent"] if gt else -1
                gt_n_spur = gt["n_spurious"] if gt else -1

                rows.append({
                    "experiment": exp_name,
                    "model": model,
                    "lambda_baskets": lam,
                    "seed": seed,
                    "gt_spr": round(gt_spr, 6),
                    "gt_n_txn_frequent": gt_n_txn,
                    "gt_n_spurious": gt_n_spur,
                    "phase1_multi": run["phase1"]["pattern_count_multi"],
                    "traditional_multi": run["traditional"]["pattern_count_multi"],
                    "observed_spurious": run["observed_spurious"],
                    "phase1_core_ms": round(run["phase1"]["core_ms"], 2),
                    "trad_flatten_ms": round(run["traditional"]["flatten_ms"], 2),
                    "trad_core_ms": round(run["traditional"]["core_ms"], 2),
                    "trad_total_ms": round(run["traditional"]["total_ms"], 2),
                })
                print(f"SPR={gt_spr:.3f} trad={run['traditional']['pattern_count_multi']} "
                      f"p1={run['phase1']['pattern_count_multi']} "
                      f"p1_core={run['phase1']['core_ms']:.0f}ms "
                      f"trad_core={run['traditional']['core_ms']:.0f}ms [{elapsed:.1f}s]")

    write_csv(output_dir / "A1_spr.csv", A1_FIELDS, rows)


# ---------------------------------------------------------------------------
# 実験 A2: G sweep
# ---------------------------------------------------------------------------

A2_FIELDS = [
    "experiment", "model", "G", "seed",
    "gt_spr", "gt_n_txn_frequent", "gt_n_spurious",
    "phase1_multi", "traditional_multi", "observed_spurious",
    "phase1_core_ms",
    "trad_flatten_ms", "trad_core_ms", "trad_total_ms",
]


def run_A2(output_dir: Path, data_dir: Path) -> None:
    print("\n" + "=" * 60)
    print("=== 実験 A2: G (カテゴリ数) sweep ===")
    print("=" * 60)

    g_values = [3, 5, 10, 20, 50]
    configs = [
        ("A2-P", "poisson", 5),
    ]

    rows: List[Dict[str, Any]] = []
    total = sum(len(g_values) * n_seeds for _, _, n_seeds in configs)
    done = 0

    for exp_name, model, n_seeds in configs:
        print(f"\n--- {exp_name} (model={model}, seeds={n_seeds}) ---")
        for g in g_values:
            for seed in range(n_seeds):
                done += 1
                prefix = f"{exp_name}_G{g}"
                print(f"  [{done}/{total}] {exp_name} G={g} seed={seed}", end=" ")
                t_start = time.perf_counter()

                result = run_one_case(
                    model=model,
                    n_transactions=10000,
                    n_categories=g,
                    lambda_baskets=2.0,
                    seed=seed,
                    data_dir=data_dir,
                    prefix=prefix,
                    skip_gt=False,
                )

                elapsed = time.perf_counter() - t_start
                gt = result["gt"]
                run = result["run"]

                gt_spr = gt["spr"] if gt else float("nan")
                gt_n_txn = gt["n_txn_frequent"] if gt else -1
                gt_n_spur = gt["n_spurious"] if gt else -1

                rows.append({
                    "experiment": exp_name,
                    "model": model,
                    "G": g,
                    "seed": seed,
                    "gt_spr": round(gt_spr, 6),
                    "gt_n_txn_frequent": gt_n_txn,
                    "gt_n_spurious": gt_n_spur,
                    "phase1_multi": run["phase1"]["pattern_count_multi"],
                    "traditional_multi": run["traditional"]["pattern_count_multi"],
                    "observed_spurious": run["observed_spurious"],
                    "phase1_core_ms": round(run["phase1"]["core_ms"], 2),
                    "trad_flatten_ms": round(run["traditional"]["flatten_ms"], 2),
                    "trad_core_ms": round(run["traditional"]["core_ms"], 2),
                    "trad_total_ms": round(run["traditional"]["total_ms"], 2),
                })
                print(f"SPR={gt_spr:.3f} G={g} "
                      f"p1_core={run['phase1']['core_ms']:.0f}ms "
                      f"trad_core={run['traditional']['core_ms']:.0f}ms [{elapsed:.1f}s]")

    write_csv(output_dir / "A2_spr.csv", A2_FIELDS, rows)


# ---------------------------------------------------------------------------
# 実験 A3: N sweep（スケーラビリティ）
# ---------------------------------------------------------------------------

A3_FIELDS = [
    "experiment", "model", "n_transactions", "seed",
    "phase1_elapsed_ms", "traditional_elapsed_ms",
    "phase1_multi", "traditional_multi",
]


def run_A3(output_dir: Path, data_dir: Path) -> None:
    print("\n" + "=" * 60)
    print("=== 実験 A3: N_transactions sweep（スケーラビリティ） ===")
    print("=" * 60)

    n_values = [1000, 10000, 100000, 1000000]
    configs = [
        ("A3-P", "poisson"),
    ]
    n_seeds = 3

    rows: List[Dict[str, Any]] = []
    total = len(n_values) * len(configs) * n_seeds
    done = 0

    for exp_name, model in configs:
        print(f"\n--- {exp_name} (model={model}, seeds={n_seeds}) ---")
        for n_txn in n_values:
            for seed in range(n_seeds):
                done += 1
                prefix = f"{exp_name}_N{n_txn}"
                print(f"  [{done}/{total}] {exp_name} N={n_txn} seed={seed}", end=" ", flush=True)
                t_start = time.perf_counter()

                result = run_one_case(
                    model=model,
                    n_transactions=n_txn,
                    n_categories=10,
                    lambda_baskets=2.0,
                    seed=seed,
                    data_dir=data_dir,
                    prefix=prefix,
                    skip_gt=True,     # A3 は計時目的のため GT をスキップ
                    save_txn=True,
                )

                elapsed = time.perf_counter() - t_start
                run = result["run"]

                rows.append({
                    "experiment": exp_name,
                    "model": model,
                    "n_transactions": n_txn,
                    "seed": seed,
                    "phase1_elapsed_ms": round(run["phase1"]["core_ms"], 2),
                    "traditional_elapsed_ms": round(run["traditional"]["total_ms"], 2),
                    "phase1_multi": run["phase1"]["pattern_count_multi"],
                    "traditional_multi": run["traditional"]["pattern_count_multi"],
                })
                print(f"p1={run['phase1']['core_ms']:.0f}ms "
                      f"trad={run['traditional']['total_ms']:.0f}ms "
                      f"[total={elapsed:.1f}s]")

    write_csv(output_dir / "A3_timing.csv", A3_FIELDS, rows)


# ---------------------------------------------------------------------------
# CLI エントリーポイント
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage A 全実験（A1-P/PL, A2-P/PL, A3-P/PL）を実行する"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(_SCRIPT_DIR / "results"),
        help="CSV 出力ディレクトリ（デフォルト: experiments/results）",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="合成データ保存ディレクトリ（デフォルト: <output_dir>/data）",
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=["A1", "A2", "A3"],
        default=["A1", "A2", "A3"],
        help="実行する実験セット（デフォルト: A1 A2 A3）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    output_dir = Path(args.output_dir)
    data_dir = Path(args.data_dir) if args.data_dir else output_dir / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"[stage_A] output_dir={output_dir}")
    print(f"[stage_A] data_dir={data_dir}")
    print(f"[stage_A] experiments={args.experiments}")

    t_total = time.perf_counter()

    if "A1" in args.experiments:
        run_A1(output_dir, data_dir)

    if "A2" in args.experiments:
        run_A2(output_dir, data_dir)

    if "A3" in args.experiments:
        run_A3(output_dir, data_dir)

    elapsed = time.perf_counter() - t_total
    print(f"\n[stage_A] 完了。合計経過時間: {elapsed:.1f}s")
    print(f"[stage_A] 結果: {output_dir}")


if __name__ == "__main__":
    main()
