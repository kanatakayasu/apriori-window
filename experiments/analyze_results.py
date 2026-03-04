"""
analyze_results.py
==================
Stage A の実験結果 CSV を読み込み、集計テーブルをターミナルに出力する。

使用方法:
    # 全 CSV を分析（デフォルト: experiments/results/）
    python experiments/analyze_results.py

    # 出力先を指定
    python experiments/analyze_results.py --results-dir /path/to/results

    # 特定の実験のみ
    python experiments/analyze_results.py --experiments A1
    python experiments/analyze_results.py --experiments A1 A2

出力:
    - A1: λ_baskets ごとの gt_spr 平均±標準偏差、observed_spurious 平均
    - A2: G ごとの gt_spr 平均±標準偏差、observed_spurious 平均
    - A3: N_transactions ごとの Phase 1 / 従来法の実行時間（平均 ms）
    - 検証チェック結果（単調性、traditional >= phase1 等）
"""

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# CSV 読み込みヘルパー
# ---------------------------------------------------------------------------

def read_csv(path: Path) -> List[Dict[str, str]]:
    """CSV ファイルを読み込み、行のリスト（dict）を返す。存在しなければ None。"""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# 統計ヘルパー
# ---------------------------------------------------------------------------

def mean(values: List[float]) -> float:
    if not values:
        return float("nan")
    return sum(values) / len(values)


def std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def fmt_mean_std(values: List[float], digits: int = 4) -> str:
    if not values:
        return "N/A"
    return f"{mean(values):.{digits}f} ± {std(values):.{digits}f}"


def fmt_mean(values: List[float], digits: int = 1) -> str:
    if not values:
        return "N/A"
    return f"{mean(values):.{digits}f}"


# ---------------------------------------------------------------------------
# テーブル表示ヘルパー
# ---------------------------------------------------------------------------

def print_table(headers: List[str], rows: List[List[str]], title: str = "") -> None:
    if title:
        print(f"\n{title}")
        print("-" * len(title))
    col_widths = [
        max(len(h), max((len(str(r[i])) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in col_widths))
    for row in rows:
        print(fmt.format(*[str(x) for x in row]))


# ---------------------------------------------------------------------------
# A1 分析: λ_baskets sweep
# ---------------------------------------------------------------------------

def analyze_A1(results_dir: Path) -> None:
    print("\n" + "=" * 70)
    print("【A1】λ_baskets sweep — SPR (gt_spr) と observed_spurious")
    print("=" * 70)

    path = results_dir / "A1_spr.csv"
    rows = read_csv(path)
    if not rows:
        print(f"  [WARNING] {path} が見つかりません")
        return

    # model × experiment × lambda_baskets でグループ化
    for model_label, exp_name in [("poisson", "A1-P")]:
        subset = [r for r in rows if r["experiment"] == exp_name]
        if not subset:
            continue

        print(f"\n--- {exp_name} (model={model_label}) ---")

        lambda_vals = sorted(set(float(r["lambda_baskets"]) for r in subset))

        table_rows = []
        for lam in lambda_vals:
            g = [r for r in subset if float(r["lambda_baskets"]) == lam]
            gt_sprs = [float(r["gt_spr"]) for r in g if r["gt_spr"] not in ("", "nan")]
            obs_spurs = [int(r["observed_spurious"]) for r in g if r["observed_spurious"] not in ("", "nan")]
            p1_multi = [int(r["phase1_multi"]) for r in g if r["phase1_multi"] not in ("", "nan")]
            trad_multi = [int(r["traditional_multi"]) for r in g if r["traditional_multi"] not in ("", "nan")]
            p1_ms = [float(r["phase1_elapsed_ms"]) for r in g if r["phase1_elapsed_ms"] not in ("", "nan")]
            trad_ms = [float(r["traditional_elapsed_ms"]) for r in g if r["traditional_elapsed_ms"] not in ("", "nan")]

            table_rows.append([
                f"λ={lam}",
                f"n={len(g)}",
                fmt_mean_std(gt_sprs),
                fmt_mean(obs_spurs, 1),
                fmt_mean(p1_multi, 1),
                fmt_mean(trad_multi, 1),
                fmt_mean(p1_ms, 0) + "ms",
            ])

        print_table(
            ["lambda", "seeds", "gt_spr (mean±std)", "obs_spurious", "p1_multi", "trad_multi", "p1_time"],
            table_rows,
        )

        # 検証チェック: gt_spr の単調増加
        mean_sprs = []
        for lam in lambda_vals:
            g = [r for r in subset if float(r["lambda_baskets"]) == lam]
            sprs = [float(r["gt_spr"]) for r in g if r["gt_spr"] not in ("", "nan")]
            mean_sprs.append((lam, mean(sprs)))

        monotone = all(
            mean_sprs[i][1] <= mean_sprs[i + 1][1]
            for i in range(len(mean_sprs) - 1)
        )
        print(f"\n  [CHECK] gt_spr 単調増加: {'✓ OK' if monotone else '✗ FAIL'}")
        print(f"  [CHECK] traditional >= phase1 (全行): ", end="")
        ok = all(
            int(r.get("traditional_multi", 0)) >= int(r.get("phase1_multi", 0))
            for r in subset
        )
        print("✓ OK" if ok else "✗ FAIL")


# ---------------------------------------------------------------------------
# A2 分析: G sweep
# ---------------------------------------------------------------------------

def analyze_A2(results_dir: Path) -> None:
    print("\n" + "=" * 70)
    print("【A2】G (カテゴリ数) sweep — SPR と observed_spurious")
    print("=" * 70)

    path = results_dir / "A2_spr.csv"
    rows = read_csv(path)
    if not rows:
        print(f"  [WARNING] {path} が見つかりません")
        return

    for model_label, exp_name in [("poisson", "A2-P")]:
        subset = [r for r in rows if r["experiment"] == exp_name]
        if not subset:
            continue

        print(f"\n--- {exp_name} (model={model_label}) ---")

        g_vals = sorted(set(int(r["G"]) for r in subset))

        table_rows = []
        for g in g_vals:
            grp = [r for r in subset if int(r["G"]) == g]
            gt_sprs = [float(r["gt_spr"]) for r in grp if r["gt_spr"] not in ("", "nan")]
            obs_spurs = [int(r["observed_spurious"]) for r in grp if r["observed_spurious"] not in ("", "nan")]
            p1_multi = [int(r["phase1_multi"]) for r in grp if r["phase1_multi"] not in ("", "nan")]
            trad_multi = [int(r["traditional_multi"]) for r in grp if r["traditional_multi"] not in ("", "nan")]

            table_rows.append([
                f"G={g}",
                f"n={len(grp)}",
                fmt_mean_std(gt_sprs),
                fmt_mean(obs_spurs, 1),
                fmt_mean(p1_multi, 1),
                fmt_mean(trad_multi, 1),
            ])

        print_table(
            ["G", "seeds", "gt_spr (mean±std)", "obs_spurious", "p1_multi", "trad_multi"],
            table_rows,
        )

        # G が大きいほど SPR が下がる（カテゴリが細かいほど偽共起が発生しにくい）傾向の確認
        mean_sprs = []
        for g in g_vals:
            grp = [r for r in subset if int(r["G"]) == g]
            sprs = [float(r["gt_spr"]) for r in grp if r["gt_spr"] not in ("", "nan")]
            mean_sprs.append((g, mean(sprs)))

        # 単調減少（G増加→SPR減少）チェック
        monotone_down = all(
            mean_sprs[i][1] >= mean_sprs[i + 1][1]
            for i in range(len(mean_sprs) - 1)
        )
        print(f"\n  [CHECK] G 増加 → gt_spr 単調減少: {'✓ OK' if monotone_down else '△ 非単調（裾の重い分布などで乱れあり）'}")
        print(f"  [CHECK] traditional >= phase1 (全行): ", end="")
        ok = all(
            int(r.get("traditional_multi", 0)) >= int(r.get("phase1_multi", 0))
            for r in subset
        )
        print("✓ OK" if ok else "✗ FAIL")


# ---------------------------------------------------------------------------
# A3 分析: N sweep（スケーラビリティ）
# ---------------------------------------------------------------------------

def analyze_A3(results_dir: Path) -> None:
    print("\n" + "=" * 70)
    print("【A3】N_transactions sweep — 実行時間（スケーラビリティ）")
    print("=" * 70)

    path = results_dir / "A3_timing.csv"
    rows = read_csv(path)
    if not rows:
        print(f"  [WARNING] {path} が見つかりません")
        return

    for model_label, exp_name in [("poisson", "A3-P")]:
        subset = [r for r in rows if r["experiment"] == exp_name]
        if not subset:
            continue

        print(f"\n--- {exp_name} (model={model_label}) ---")

        n_vals = sorted(set(int(r["n_transactions"]) for r in subset))

        table_rows = []
        for n in n_vals:
            grp = [r for r in subset if int(r["n_transactions"]) == n]
            p1_ms = [float(r["phase1_elapsed_ms"]) for r in grp if r["phase1_elapsed_ms"] not in ("", "nan")]
            trad_ms = [float(r["traditional_elapsed_ms"]) for r in grp if r["traditional_elapsed_ms"] not in ("", "nan")]

            speedup = mean(trad_ms) / mean(p1_ms) if mean(p1_ms) > 0 else float("nan")

            table_rows.append([
                f"N={n:>9,}",
                f"n={len(grp)}",
                fmt_mean(p1_ms, 0) + " ms",
                fmt_mean(trad_ms, 0) + " ms",
                f"{speedup:.2f}x" if not math.isnan(speedup) else "N/A",
            ])

        print_table(
            ["N", "seeds", "phase1 (mean)", "traditional (mean)", "trad/p1 ratio"],
            table_rows,
        )

        # スケーラビリティチェック: N が 10 倍になると時間が 10-50 倍になることを確認
        print(f"\n  [INFO] N が 10 倍になると実行時間がどう変化するか:")
        for i in range(len(n_vals) - 1):
            n_cur = n_vals[i]
            n_nxt = n_vals[i + 1]
            grp_cur = [r for r in subset if int(r["n_transactions"]) == n_cur]
            grp_nxt = [r for r in subset if int(r["n_transactions"]) == n_nxt]
            p1_cur = mean([float(r["phase1_elapsed_ms"]) for r in grp_cur])
            p1_nxt = mean([float(r["phase1_elapsed_ms"]) for r in grp_nxt])
            if p1_cur > 0:
                ratio = p1_nxt / p1_cur
                scale = n_nxt / n_cur
                print(f"    N={n_cur:>8,} → N={n_nxt:>10,} (×{scale:.0f}): "
                      f"phase1 時間比 = {ratio:.1f}x")


# ---------------------------------------------------------------------------
# CLI エントリーポイント
# ---------------------------------------------------------------------------

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        description="Stage A 実験結果 CSV を読み込み集計テーブルを出力する"
    )
    _SCRIPT_DIR = Path(__file__).resolve().parent
    parser.add_argument(
        "--results-dir",
        type=str,
        default=str(_SCRIPT_DIR / "results"),
        help="CSV が置かれているディレクトリ（デフォルト: experiments/results）",
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=["A1", "A2", "A3"],
        default=["A1", "A2", "A3"],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir)

    print(f"結果ディレクトリ: {results_dir}")

    if "A1" in args.experiments:
        analyze_A1(results_dir)

    if "A2" in args.experiments:
        analyze_A2(results_dir)

    if "A3" in args.experiments:
        analyze_A3(results_dir)

    print("\n分析完了。")


if __name__ == "__main__":
    main()
