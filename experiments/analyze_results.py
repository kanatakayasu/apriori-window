"""
analyze_results.py
==================
Stage A の実験結果 CSV を読み込み、集計テーブルを出力する。

使用方法:
    # A1/A2/A3 を分析（CSV が results_dir 直下にある場合）
    python experiments/analyze_results.py --results-dir experiments/results/a1_full_20260302

    # A1 のみ分析し、method x lambda 集計と図を生成
    python experiments/analyze_results.py --experiments A1 \
      --results-dir experiments/results/a1_full_20260302
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


METHOD_ORDER = {"phase1": 0, "traditional": 1}
METHOD_LABEL = {"phase1": "Phase 1", "traditional": "Traditional"}


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def mean(values: List[float]) -> float:
    if not values:
        return float("nan")
    return sum(values) / len(values)


def std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def fmt_mean(values: List[float], digits: int = 2) -> str:
    if not values:
        return "N/A"
    return f"{mean(values):.{digits}f}"


def fmt_mean_std(values: List[float], digits: int = 3) -> str:
    if not values:
        return "N/A"
    return f"{mean(values):.{digits}f} ± {std(values):.{digits}f}"


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


def to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = value.strip().lower()
    if text in ("", "nan"):
        return None
    return float(text)


def to_int(value: Optional[str]) -> Optional[int]:
    parsed = to_float(value)
    if parsed is None:
        return None
    return int(parsed)


def resolve_result_csv(results_dir: Path, filename: str) -> Path:
    direct = results_dir / filename
    if direct.exists():
        return direct

    recursive = sorted(results_dir.rglob(filename))
    if not recursive:
        return direct

    chosen = max(recursive, key=lambda p: p.stat().st_mtime)
    print(f"  [INFO] {filename} was resolved from nested path: {chosen}")
    return chosen


def build_a1_long_rows(rows: List[Dict[str, str]]) -> List[Dict[str, object]]:
    long_rows: List[Dict[str, object]] = []
    for row in rows:
        lam = to_float(row.get("lambda_baskets"))
        seed = to_int(row.get("seed"))
        gt_spr = to_float(row.get("gt_spr"))
        observed_spurious = to_float(row.get("observed_spurious"))
        if lam is None or seed is None:
            continue

        common = {
            "experiment": row.get("experiment", ""),
            "model": row.get("model", ""),
            "lambda_baskets": lam,
            "seed": seed,
            "gt_spr": gt_spr,
        }

        phase1_multi = to_float(row.get("phase1_multi"))
        phase1_time = to_float(row.get("phase1_core_ms"))
        if phase1_multi is not None and phase1_time is not None:
            long_rows.append(
                {
                    **common,
                    "method": "phase1",
                    "multi_count": phase1_multi,
                    "time_ms": phase1_time,
                    "observed_spurious": None,
                }
            )

        trad_multi = to_float(row.get("traditional_multi"))
        trad_time = to_float(row.get("trad_total_ms"))
        if trad_multi is not None and trad_time is not None:
            long_rows.append(
                {
                    **common,
                    "method": "traditional",
                    "multi_count": trad_multi,
                    "time_ms": trad_time,
                    "observed_spurious": observed_spurious,
                }
            )

    return long_rows


def summarize_a1_by_method_lambda(long_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[str, str, str, float], List[Dict[str, object]]] = defaultdict(list)
    for row in long_rows:
        key = (
            str(row["experiment"]),
            str(row["model"]),
            str(row["method"]),
            float(row["lambda_baskets"]),
        )
        grouped[key].append(row)

    summary_rows: List[Dict[str, object]] = []
    for key in sorted(
        grouped.keys(),
        key=lambda x: (x[0], x[1], x[3], METHOD_ORDER.get(x[2], 99)),
    ):
        experiment, model, method, lam = key
        grp = grouped[key]
        multi_vals = [float(r["multi_count"]) for r in grp if r.get("multi_count") is not None]
        time_vals = [float(r["time_ms"]) for r in grp if r.get("time_ms") is not None]
        gt_vals = [float(r["gt_spr"]) for r in grp if r.get("gt_spr") is not None]
        obs_vals = [float(r["observed_spurious"]) for r in grp if r.get("observed_spurious") is not None]
        seed_vals = [int(r["seed"]) for r in grp if r.get("seed") is not None]

        summary_rows.append(
            {
                "experiment": experiment,
                "model": model,
                "method": method,
                "lambda_baskets": lam,
                "n_seed": len(seed_vals),
                "multi_mean": mean(multi_vals),
                "multi_std": std(multi_vals),
                "time_mean_ms": mean(time_vals),
                "time_std_ms": std(time_vals),
                "gt_spr_mean": mean(gt_vals),
                "gt_spr_std": std(gt_vals),
                "observed_spurious_mean": mean(obs_vals) if obs_vals else "",
                "observed_spurious_std": std(obs_vals) if obs_vals else "",
            }
        )
    return summary_rows


def sanitize_slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()


def plot_a1_method_lambda(summary_rows: List[Dict[str, object]], figures_dir: Path) -> List[Path]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [WARNING] matplotlib がないためプロット生成をスキップします")
        return []

    grouped: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)
    for row in summary_rows:
        grouped[(str(row["experiment"]), str(row["model"]))].append(row)

    output_paths: List[Path] = []
    figures_dir.mkdir(parents=True, exist_ok=True)

    for (experiment, model), rows in sorted(grouped.items()):
        by_method: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        for row in rows:
            by_method[str(row["method"])].append(row)

        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
        ax_multi, ax_time = axes

        for method in sorted(by_method.keys(), key=lambda m: METHOD_ORDER.get(m, 99)):
            pts = sorted(by_method[method], key=lambda r: float(r["lambda_baskets"]))
            x = [float(r["lambda_baskets"]) for r in pts]
            y_multi = [float(r["multi_mean"]) for r in pts]
            e_multi = [float(r["multi_std"]) for r in pts]
            y_time = [float(r["time_mean_ms"]) for r in pts]
            e_time = [float(r["time_std_ms"]) for r in pts]
            label = METHOD_LABEL.get(method, method)

            ax_multi.errorbar(x, y_multi, yerr=e_multi, marker="o", capsize=3, linewidth=2, label=label)
            ax_time.errorbar(x, y_time, yerr=e_time, marker="o", capsize=3, linewidth=2, label=label)

        ax_multi.set_title("A1 Multi-Item Patterns")
        ax_multi.set_xlabel("lambda_baskets")
        ax_multi.set_ylabel("mean pattern count")
        ax_multi.grid(alpha=0.3)

        ax_time.set_title("A1 Runtime")
        ax_time.set_xlabel("lambda_baskets")
        ax_time.set_ylabel("mean time (ms)")
        ax_time.grid(alpha=0.3)
        ax_time.legend(loc="upper left")

        slug = f"{sanitize_slug(experiment)}_{sanitize_slug(model)}"
        out_path = figures_dir / f"A1_method_lambda_{slug}.png"
        fig.savefig(out_path, dpi=180)
        plt.close(fig)
        output_paths.append(out_path)

    return output_paths


def analyze_A1(results_dir: Path, tables_dir: Path, figures_dir: Path, skip_plot: bool) -> None:
    print("\n" + "=" * 70)
    print("【A1】method x lambda で集計（seed平均）")
    print("=" * 70)

    path = resolve_result_csv(results_dir, "A1_spr.csv")
    rows = read_csv(path)
    if not rows:
        print(f"  [WARNING] {path} が見つかりません")
        return

    long_rows = build_a1_long_rows(rows)
    summary_rows = summarize_a1_by_method_lambda(long_rows)

    long_csv = tables_dir / "A1_by_method_lambda_seed.csv"
    summary_csv = tables_dir / "A1_by_method_lambda_summary.csv"
    write_csv(
        long_csv,
        [
            "experiment",
            "model",
            "lambda_baskets",
            "method",
            "seed",
            "multi_count",
            "time_ms",
            "gt_spr",
            "observed_spurious",
        ],
        long_rows,
    )
    write_csv(
        summary_csv,
        [
            "experiment",
            "model",
            "method",
            "lambda_baskets",
            "n_seed",
            "multi_mean",
            "multi_std",
            "time_mean_ms",
            "time_std_ms",
            "gt_spr_mean",
            "gt_spr_std",
            "observed_spurious_mean",
            "observed_spurious_std",
        ],
        summary_rows,
    )

    print(f"  [OUT] {long_csv}")
    print(f"  [OUT] {summary_csv}")

    table_rows: List[List[str]] = []
    for row in summary_rows:
        obs_text = (
            f"{float(row['observed_spurious_mean']):.2f}"
            if row.get("observed_spurious_mean") not in ("", None)
            else "-"
        )
        table_rows.append(
            [
                f"{float(row['lambda_baskets']):.1f}",
                METHOD_LABEL.get(str(row["method"]), str(row["method"])),
                str(int(row["n_seed"])),
                f"{float(row['multi_mean']):.2f} +- {float(row['multi_std']):.2f}",
                f"{float(row['time_mean_ms']):.2f} +- {float(row['time_std_ms']):.2f}",
                f"{float(row['gt_spr_mean']):.3f} +- {float(row['gt_spr_std']):.3f}",
                obs_text,
            ]
        )
    print_table(
        ["lambda", "method", "seeds", "multi(mean+-std)", "time_ms(mean+-std)", "gt_spr(mean+-std)", "obs_spur(mean)"],
        table_rows,
        title="A1 Summary by method x lambda",
    )

    if not skip_plot:
        out_paths = plot_a1_method_lambda(summary_rows, figures_dir)
        for out_path in out_paths:
            print(f"  [OUT] {out_path}")

    expected = {
        float(row["lambda_baskets"]): int(row["n_seed"])
        for row in summary_rows
        if str(row["method"]) == "phase1"
    }
    seed_count_ok = all(
        int(row["n_seed"]) == expected.get(float(row["lambda_baskets"]), int(row["n_seed"]))
        for row in summary_rows
    )
    print(f"  [CHECK] method x lambda ごとの seed 数整合: {'OK' if seed_count_ok else 'FAIL'}")


def analyze_A2(results_dir: Path) -> None:
    print("\n" + "=" * 70)
    print("【A2】G sweep - gt_spr と observed_spurious")
    print("=" * 70)

    path = resolve_result_csv(results_dir, "A2_spr.csv")
    rows = read_csv(path)
    if not rows:
        print(f"  [WARNING] {path} が見つかりません")
        return

    for model_label, exp_name in [("poisson", "A2-P")]:
        subset = [r for r in rows if r.get("experiment") == exp_name]
        if not subset:
            continue

        print(f"\n--- {exp_name} (model={model_label}) ---")

        g_vals = sorted(set(int(r["G"]) for r in subset))
        table_rows = []
        for g in g_vals:
            grp = [r for r in subset if int(r["G"]) == g]
            gt_sprs = [float(r["gt_spr"]) for r in grp if r["gt_spr"] not in ("", "nan")]
            obs_spurs = [float(r["observed_spurious"]) for r in grp if r["observed_spurious"] not in ("", "nan")]
            p1_multi = [float(r["phase1_multi"]) for r in grp if r["phase1_multi"] not in ("", "nan")]
            trad_multi = [float(r["traditional_multi"]) for r in grp if r["traditional_multi"] not in ("", "nan")]
            table_rows.append(
                [
                    f"G={g}",
                    f"n={len(grp)}",
                    fmt_mean_std(gt_sprs, 3),
                    fmt_mean(obs_spurs, 1),
                    fmt_mean(p1_multi, 1),
                    fmt_mean(trad_multi, 1),
                ]
            )

        print_table(
            ["G", "seeds", "gt_spr (mean+-std)", "obs_spurious", "phase1_multi", "traditional_multi"],
            table_rows,
        )


def analyze_A3(results_dir: Path) -> None:
    print("\n" + "=" * 70)
    print("【A3】N sweep - 実行時間")
    print("=" * 70)

    path = resolve_result_csv(results_dir, "A3_timing.csv")
    rows = read_csv(path)
    if not rows:
        print(f"  [WARNING] {path} が見つかりません")
        return

    for model_label, exp_name in [("poisson", "A3-P")]:
        subset = [r for r in rows if r.get("experiment") == exp_name]
        if not subset:
            continue

        print(f"\n--- {exp_name} (model={model_label}) ---")
        n_vals = sorted(set(int(r["n_transactions"]) for r in subset))
        table_rows = []
        for n in n_vals:
            grp = [r for r in subset if int(r["n_transactions"]) == n]
            p1_ms = [float(r["phase1_elapsed_ms"]) for r in grp if r["phase1_elapsed_ms"] not in ("", "nan")]
            trad_ms = [float(r["traditional_elapsed_ms"]) for r in grp if r["traditional_elapsed_ms"] not in ("", "nan")]
            ratio = mean(trad_ms) / mean(p1_ms) if mean(p1_ms) > 0 else float("nan")
            table_rows.append(
                [
                    f"{n}",
                    f"{len(grp)}",
                    f"{fmt_mean(p1_ms, 0)} ms",
                    f"{fmt_mean(trad_ms, 0)} ms",
                    f"{ratio:.2f}" if not math.isnan(ratio) else "N/A",
                ]
            )
        print_table(["N", "seeds", "phase1", "traditional", "trad/p1"], table_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage A 実験結果 CSV を集計して表示する")
    script_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "--results-dir",
        type=str,
        default=str(script_dir / "results"),
        help="CSV が置かれているディレクトリ（直下 or 再帰探索）",
    )
    parser.add_argument(
        "--tables-dir",
        type=str,
        default=str(script_dir / "reports" / "tables"),
        help="集計 CSV の出力先",
    )
    parser.add_argument(
        "--figures-dir",
        type=str,
        default=str(script_dir / "reports" / "figures"),
        help="図の出力先",
    )
    parser.add_argument(
        "--skip-plot",
        action="store_true",
        help="A1 プロット出力をスキップ",
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
    tables_dir = Path(args.tables_dir)
    figures_dir = Path(args.figures_dir)

    print(f"結果ディレクトリ: {results_dir}")
    print(f"テーブル出力先: {tables_dir}")
    print(f"図出力先: {figures_dir}")

    if "A1" in args.experiments:
        analyze_A1(results_dir=results_dir, tables_dir=tables_dir, figures_dir=figures_dir, skip_plot=args.skip_plot)
    if "A2" in args.experiments:
        analyze_A2(results_dir=results_dir)
    if "A3" in args.experiments:
        analyze_A3(results_dir=results_dir)

    print("\n分析完了。")


if __name__ == "__main__":
    main()
