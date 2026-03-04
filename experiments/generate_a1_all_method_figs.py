"""
generate_a1_all_method_figs.py
==============================
A1 (lambda sweep) を対象に、以下を一括生成する:
1) method x lambda x seed の統合CSV
2) method x lambda のseed平均CSV
3) Phase 1 の GTSPR=0 検証CSV
4) 3枚のPNG図

図の仕様:
- a1_time_all_methods.png
  x=lambda, y=time(ms), 系列=全手法（Phase 1 を先頭）
- a1_gtspr_non_phase1.png
  x=lambda, y=GTSPR, 系列=Phase 1 以外
- a1_multi_all_methods.png
  x=lambda, y=多項目パターン数, 系列=全手法
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple


# apriori_window_suite/python/ を import path に追加
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHON_DIR = _REPO_ROOT / "apriori_window_suite" / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from apriori_window_basket import find_dense_itemsets, read_transactions_with_baskets
from run_phase1 import flatten_transactions


A1_TXN_RE = re.compile(r"^A1-P_lambda(?P<lam>[0-9]+(?:\.[0-9]+)?)_seed(?P<seed>[0-9]+)\.txt$")

PHASE1_METHOD = "phase1"
TRAD_METHOD = "apriori_window_flatten"
BASELINE_METHODS = [
    "apriori",
    "fp_growth",
    "eclat",
    "lcm",
    "pfpm",
    "ppfpm_gpf_growth",
    "lpfim",
    "lppm",
]
METHOD_ORDER = [
    PHASE1_METHOD,
    TRAD_METHOD,
    *BASELINE_METHODS,
]
METHOD_LABEL = {
    PHASE1_METHOD: "Phase 1",
    TRAD_METHOD: "Apriori-window (flatten)",
    "apriori": "Apriori",
    "fp_growth": "FP-Growth",
    "eclat": "Eclat",
    "lcm": "LCM",
    "pfpm": "PFPM",
    "ppfpm_gpf_growth": "PPFPM-GPF",
    "lpfim": "LPFIM",
    "lppm": "LPPM",
}


@dataclass(frozen=True)
class A1Case:
    lambda_baskets: float
    seed: int
    stem: str
    txn_path: Path
    gt_path: Path


def lambda_key(value: float) -> str:
    return f"{value:.1f}"


def parse_itemset_key(key: str) -> Tuple[int, ...]:
    if not key:
        return tuple()
    return tuple(sorted(int(x) for x in key.split(",") if x))


def read_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def discover_a1_cases(a1_data_dir: Path) -> List[A1Case]:
    cases: List[A1Case] = []
    for path in sorted(a1_data_dir.glob("A1-P_lambda*_seed*.txt")):
        m = A1_TXN_RE.match(path.name)
        if not m:
            continue
        lam = float(m.group("lam"))
        seed = int(m.group("seed"))
        stem = path.stem
        gt = a1_data_dir / f"{stem}_gt.json"
        if not gt.exists():
            raise FileNotFoundError(f"GT file not found for case: {gt}")
        cases.append(A1Case(lambda_baskets=lam, seed=seed, stem=stem, txn_path=path, gt_path=gt))
    if not cases:
        raise FileNotFoundError(f"No A1 dataset file found in: {a1_data_dir}")
    return sorted(cases, key=lambda c: (c.lambda_baskets, c.seed))


def run_baseline_suite_for_cases(
    cases: Sequence[A1Case],
    out_dir: Path,
    backend: str,
    force: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(cases)
    for idx, case in enumerate(cases, start=1):
        expected = [out_dir / f"{case.stem}_{method}.json" for method in BASELINE_METHODS]
        if (not force) and all(path.exists() for path in expected):
            print(f"[baseline {idx}/{total}] skip existing: {case.stem}")
            continue

        print(f"[baseline {idx}/{total}] run: {case.stem}")
        cmd = [
            sys.executable,
            "-m",
            "baselines.runner.run_stage_a_suite",
            "--input-basket",
            str(case.txn_path),
            "--out-dir",
            str(out_dir),
            "--backend",
            backend,
            "--methods",
            *BASELINE_METHODS,
        ]
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"baseline suite failed: {case.stem} (code={proc.returncode})")


def load_gt_spurious_set(gt_path: Path) -> Set[Tuple[int, ...]]:
    with open(gt_path, encoding="utf-8") as f:
        gt = json.load(f)
    return {
        tuple(sorted(int(x) for x in rec["itemset"]))
        for rec in gt.get("spurious_patterns", [])
        if len(rec.get("itemset", [])) >= 2
    }


def extract_detected_from_aw_result(freq_map: Dict[Tuple[int, ...], object]) -> Set[Tuple[int, ...]]:
    return {tuple(sorted(k)) for k in freq_map.keys() if len(k) >= 2}


def extract_detected_from_baseline_json(result_json: Dict[str, object]) -> Set[Tuple[int, ...]]:
    patterns = result_json.get("result", {}).get("patterns", {})
    if not isinstance(patterns, dict):
        return set()
    detected: Set[Tuple[int, ...]] = set()
    for key in patterns.keys():
        itemset = parse_itemset_key(key)
        if len(itemset) >= 2:
            detected.add(itemset)
    return detected


def compute_gtspr(detected: Set[Tuple[int, ...]], gt_spurious: Set[Tuple[int, ...]]) -> float:
    if not detected:
        return 0.0
    return len(detected & gt_spurious) / len(detected)


def load_a1_time_map(a1_csv: Path) -> Dict[Tuple[str, int], Dict[str, float]]:
    rows = read_csv(a1_csv)
    out: Dict[Tuple[str, int], Dict[str, float]] = {}
    for row in rows:
        lam = lambda_key(float(row["lambda_baskets"]))
        seed = int(row["seed"])
        out[(lam, seed)] = {
            "phase1_time_ms": float(row["phase1_core_ms"]),
            "traditional_time_ms": float(row["trad_total_ms"]),
        }
    return out


def aggregate_seed_rows(
    cases: Sequence[A1Case],
    a1_time_map: Dict[Tuple[str, int], Dict[str, float]],
    baseline_out_dir: Path,
    window_size: int,
    min_support: int,
    max_length: int,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    seed_rows: List[Dict[str, object]] = []
    phase1_checks: List[Dict[str, object]] = []

    total = len(cases)
    for idx, case in enumerate(cases, start=1):
        print(f"[aggregate {idx}/{total}] {case.stem}")

        gt_spurious = load_gt_spurious_set(case.gt_path)
        time_key = (lambda_key(case.lambda_baskets), case.seed)
        if time_key not in a1_time_map:
            raise KeyError(f"Missing A1 time row for {time_key}")
        times = a1_time_map[time_key]

        transactions = read_transactions_with_baskets(str(case.txn_path))
        phase1_freq = find_dense_itemsets(transactions, window_size, min_support, max_length)
        trad_freq = find_dense_itemsets(
            flatten_transactions(transactions), window_size, min_support, max_length
        )
        phase1_detected = extract_detected_from_aw_result(phase1_freq)
        trad_detected = extract_detected_from_aw_result(trad_freq)

        phase1_gtspr = compute_gtspr(phase1_detected, gt_spurious)
        trad_gtspr = compute_gtspr(trad_detected, gt_spurious)

        seed_rows.append(
            {
                "lambda_baskets": case.lambda_baskets,
                "seed": case.seed,
                "method": PHASE1_METHOD,
                "time_ms": times["phase1_time_ms"],
                "gtspr": phase1_gtspr,
                "multi_count": len(phase1_detected),
            }
        )
        seed_rows.append(
            {
                "lambda_baskets": case.lambda_baskets,
                "seed": case.seed,
                "method": TRAD_METHOD,
                "time_ms": times["traditional_time_ms"],
                "gtspr": trad_gtspr,
                "multi_count": len(trad_detected),
            }
        )
        phase1_checks.append(
            {
                "lambda_baskets": case.lambda_baskets,
                "seed": case.seed,
                "phase1_gtspr": phase1_gtspr,
                "is_zero": int(abs(phase1_gtspr) < 1e-12),
            }
        )

        for method in BASELINE_METHODS:
            result_path = baseline_out_dir / f"{case.stem}_{method}.json"
            if not result_path.exists():
                raise FileNotFoundError(f"Baseline result missing: {result_path}")
            with open(result_path, encoding="utf-8") as f:
                result = json.load(f)

            detected = extract_detected_from_baseline_json(result)
            gtspr = compute_gtspr(detected, gt_spurious)
            time_ms = float(result.get("runtime", {}).get("elapsed_ms", 0.0))

            seed_rows.append(
                {
                    "lambda_baskets": case.lambda_baskets,
                    "seed": case.seed,
                    "method": method,
                    "time_ms": time_ms,
                    "gtspr": gtspr,
                    "multi_count": len(detected),
                }
            )

    return seed_rows, phase1_checks


def aggregate_mean_rows(seed_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, object]]] = {}
    for row in seed_rows:
        key = (str(row["method"]), lambda_key(float(row["lambda_baskets"])))
        grouped.setdefault(key, []).append(row)

    lambda_values = sorted({float(row["lambda_baskets"]) for row in seed_rows})
    out: List[Dict[str, object]] = []
    for method in METHOD_ORDER:
        for lam in lambda_values:
            key = (method, lambda_key(lam))
            group = grouped.get(key, [])
            if not group:
                continue
            out.append(
                {
                    "method": method,
                    "lambda_baskets": lam,
                    "n_seed": len(group),
                    "time_ms_mean": mean([float(r["time_ms"]) for r in group]),
                    "gtspr_mean": mean([float(r["gtspr"]) for r in group]),
                    "multi_count_mean": mean([float(r["multi_count"]) for r in group]),
                }
            )
    return out


def plot_lines(
    mean_rows: Sequence[Dict[str, object]],
    methods: Sequence[str],
    y_key: str,
    y_label: str,
    title: str,
    out_path: Path,
) -> None:
    import matplotlib.pyplot as plt

    lambda_values = sorted({float(row["lambda_baskets"]) for row in mean_rows})
    by_method: Dict[str, Dict[str, float]] = {}
    for row in mean_rows:
        method = str(row["method"])
        by_method.setdefault(method, {})
        by_method[method][lambda_key(float(row["lambda_baskets"]))] = float(row[y_key])

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    for method in methods:
        points = by_method.get(method, {})
        if not points:
            continue
        x = []
        y = []
        for lam in lambda_values:
            key = lambda_key(lam)
            if key in points:
                x.append(lam)
                y.append(points[key])
        if not x:
            continue
        ax.plot(x, y, marker="o", linewidth=2, label=METHOD_LABEL.get(method, method))

    ax.set_xlabel("lambda_baskets")
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.set_xticks(lambda_values)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0.0)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate A1 all-method summary and figures")
    parser.add_argument(
        "--a1-csv",
        default="experiments/results/a1_full_20260302/A1_spr.csv",
        help="Path to A1_spr.csv",
    )
    parser.add_argument(
        "--a1-data-dir",
        default="experiments/results/a1_full_20260302_data",
        help="Directory containing A1-P_lambda*_seed*.txt and *_gt.json",
    )
    parser.add_argument(
        "--baseline-out-dir",
        default="baselines/results/a1_full_20260302_methods",
        help="Directory for baseline suite JSON outputs",
    )
    parser.add_argument(
        "--tables-dir",
        default="experiments/reports/tables",
        help="Directory for output CSVs",
    )
    parser.add_argument(
        "--figures-dir",
        default="experiments/reports/figures",
        help="Directory for output PNGs",
    )
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "python", "spmf", "pami"],
        help="Backend passed to baseline suite runner",
    )
    parser.add_argument(
        "--force-baseline-rerun",
        action="store_true",
        help="Rerun baseline suite even if JSON outputs already exist",
    )
    parser.add_argument(
        "--skip-baseline-run",
        action="store_true",
        help="Skip baseline execution and only aggregate existing JSON outputs",
    )
    parser.add_argument("--window-size", type=int, default=500)
    parser.add_argument("--min-support", type=int, default=50)
    parser.add_argument("--max-length", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    a1_csv = Path(args.a1_csv)
    a1_data_dir = Path(args.a1_data_dir)
    baseline_out_dir = Path(args.baseline_out_dir)
    tables_dir = Path(args.tables_dir)
    figures_dir = Path(args.figures_dir)

    cases = discover_a1_cases(a1_data_dir)
    print(f"[info] discovered A1 cases: {len(cases)}")

    if not args.skip_baseline_run:
        run_baseline_suite_for_cases(
            cases=cases,
            out_dir=baseline_out_dir,
            backend=args.backend,
            force=args.force_baseline_rerun,
        )

    a1_time_map = load_a1_time_map(a1_csv)
    seed_rows, phase1_checks = aggregate_seed_rows(
        cases=cases,
        a1_time_map=a1_time_map,
        baseline_out_dir=baseline_out_dir,
        window_size=args.window_size,
        min_support=args.min_support,
        max_length=args.max_length,
    )
    mean_rows = aggregate_mean_rows(seed_rows)

    seed_csv = tables_dir / "A1_all_methods_seed.csv"
    mean_csv = tables_dir / "A1_all_methods_mean.csv"
    check_csv = tables_dir / "A1_phase1_gtspr_check.csv"
    write_csv(
        seed_csv,
        ["lambda_baskets", "seed", "method", "time_ms", "gtspr", "multi_count"],
        seed_rows,
    )
    write_csv(
        mean_csv,
        ["method", "lambda_baskets", "n_seed", "time_ms_mean", "gtspr_mean", "multi_count_mean"],
        mean_rows,
    )
    write_csv(
        check_csv,
        ["lambda_baskets", "seed", "phase1_gtspr", "is_zero"],
        phase1_checks,
    )
    print(f"[out] {seed_csv}")
    print(f"[out] {mean_csv}")
    print(f"[out] {check_csv}")

    nonzero_checks = [row for row in phase1_checks if int(row["is_zero"]) == 0]
    if nonzero_checks:
        print("[error] Phase 1 GTSPR non-zero cases found:")
        for row in nonzero_checks:
            print(
                f"  lambda={row['lambda_baskets']} seed={row['seed']} "
                f"gtspr={row['phase1_gtspr']}"
            )
        raise RuntimeError("Phase 1 GTSPR must be zero for all A1 cases.")
    print("[check] Phase 1 GTSPR is zero for all lambda x seed cases.")

    plot_lines(
        mean_rows=mean_rows,
        methods=METHOD_ORDER,
        y_key="time_ms_mean",
        y_label="mean time (ms)",
        title="A1: Time vs lambda (all methods, seed mean)",
        out_path=figures_dir / "a1_time_all_methods.png",
    )
    plot_lines(
        mean_rows=mean_rows,
        methods=[m for m in METHOD_ORDER if m != PHASE1_METHOD],
        y_key="gtspr_mean",
        y_label="mean GTSPR",
        title="A1: GTSPR vs lambda (non-Phase1 methods, seed mean)",
        out_path=figures_dir / "a1_gtspr_non_phase1.png",
    )
    plot_lines(
        mean_rows=mean_rows,
        methods=METHOD_ORDER,
        y_key="multi_count_mean",
        y_label="mean multi-item pattern count",
        title="A1: Multi-item pattern count vs lambda (all methods, seed mean)",
        out_path=figures_dir / "a1_multi_all_methods.png",
    )
    print(f"[out] {figures_dir / 'a1_time_all_methods.png'}")
    print(f"[out] {figures_dir / 'a1_gtspr_non_phase1.png'}")
    print(f"[out] {figures_dir / 'a1_multi_all_methods.png'}")


if __name__ == "__main__":
    main()
