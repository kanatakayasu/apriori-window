from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Dict, List

from .io_utils import (
    dump_result_json,
    read_basket_transactions,
    read_flat_transactions,
    read_timestamped_transactions,
)
from .registry import build_registry
from .types import MethodInput


def _load(input_format: str, path: Path):
    if input_format == "basket":
        return read_basket_transactions(path)
    if input_format == "flat":
        return read_flat_transactions(path)
    if input_format == "timestamped":
        return read_timestamped_transactions(path)
    raise ValueError(input_format)


def _method_input_format(method: str) -> str:
    if method in {"lpfim", "lppm", "ppfpm_gpf_growth"}:
        return "timestamped"
    return "flat"


def _default_params(method: str) -> Dict:
    if method == "lpfim":
        return {"sigma": 3, "minthd1": 2, "minthd2": 1}
    if method == "lppm":
        return {"maxPer": 10, "maxSoPer": 20, "minDur": 3}
    if method == "pfpm":
        return {"minPer": 1, "maxPer": 10, "minAvg": 1, "maxAvg": 10, "minsup": 3}
    if method == "ppfpm_gpf_growth":
        return {"minSup": 3, "maxPer": 10, "minPR": 0.3}
    return {}


def _convert_rows(lines: List[str], mode: str) -> List[str]:
    # input lines are basket format from this project.
    out: List[str] = []
    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        items = sorted(
            {
                int(x)
                for basket in line.split("|")
                for x in basket.split()
                if x.strip()
            }
        )
        if mode == "flat":
            out.append(" ".join(str(x) for x in items))
        elif mode == "timestamped":
            out.append(f"{idx} " + " ".join(str(x) for x in items))
        else:
            raise ValueError(mode)
    return out


def _prepare_inputs(input_basket: Path, out_dir: Path, stem: str) -> Dict[str, Path]:
    with open(input_basket, "r", encoding="utf-8") as f:
        lines = f.readlines()

    out_dir.mkdir(parents=True, exist_ok=True)
    p_flat = out_dir / f"{stem}.flat.txt"
    p_ts = out_dir / f"{stem}.timestamped.txt"

    p_flat.write_text("\n".join(_convert_rows(lines, "flat")) + "\n", encoding="utf-8")
    p_ts.write_text("\n".join(_convert_rows(lines, "timestamped")) + "\n", encoding="utf-8")

    return {"flat": p_flat, "timestamped": p_ts}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stage A comparative methods suite")
    parser.add_argument("--input-basket", required=True)
    parser.add_argument("--out-dir", default="comparative_methods/results")
    parser.add_argument("--methods", nargs="*", default=[
        "apriori", "fp_growth", "eclat", "lcm", "pfpm", "ppfpm_gpf_growth", "lpfim", "lppm"
    ])
    parser.add_argument("--minsup-count", type=int, default=50)
    parser.add_argument("--max-length", type=int, default=4)
    parser.add_argument("--backend", default="auto", choices=["auto", "python", "spmf", "pami"])
    args = parser.parse_args()

    input_basket = Path(args.input_basket)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prepared = _prepare_inputs(input_basket=input_basket, out_dir=out_dir / "inputs", stem=input_basket.stem)
    registry = build_registry()

    rows: List[Dict[str, object]] = []

    for method in args.methods:
        if method not in registry:
            print(f"[suite] skip unknown method: {method}")
            continue

        fmt = _method_input_format(method)
        dataset_path = prepared[fmt]
        txns = _load(fmt, dataset_path)

        params = _default_params(method)
        params["backend"] = args.backend

        method_input = MethodInput(
            transactions=txns,
            minsup_count=args.minsup_count,
            max_length=args.max_length,
            params=params,
        )

        t0 = time.perf_counter()
        result = registry[method].run(method_input)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        out_json = out_dir / f"{input_basket.stem}_{method}.json"
        dump_result_json(
            out_json,
            {
                "config": {
                    "method": method,
                    "dataset_path": str(dataset_path),
                    "input_format": fmt,
                    "minsup_count": args.minsup_count,
                    "max_length": args.max_length,
                    "params": params,
                },
                "runtime": {"elapsed_ms": elapsed_ms, "n_transactions": len(txns)},
                "result": {
                    "method": result.method,
                    "patterns": {",".join(map(str, k)): v for k, v in result.patterns.items()},
                    "intervals": {",".join(map(str, k)): v for k, v in result.intervals.items()},
                    "metadata": result.metadata,
                },
            },
        )

        rows.append(
            {
                "method": method,
                "input_format": fmt,
                "elapsed_ms": elapsed_ms,
                "pattern_count": len(result.patterns),
                "interval_count": sum(len(v) for v in result.intervals.values()),
                "output_json": str(out_json),
            }
        )
        print(f"[suite] {method}: patterns={len(result.patterns)} elapsed_ms={elapsed_ms:.2f}")

    summary_csv = out_dir / f"{input_basket.stem}_suite_summary.csv"
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "method",
                "input_format",
                "elapsed_ms",
                "pattern_count",
                "interval_count",
                "output_json",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"[suite] wrote summary: {summary_csv}")


if __name__ == "__main__":
    main()
