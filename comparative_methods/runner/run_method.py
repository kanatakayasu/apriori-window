from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict

from .io_utils import (
    dump_result_json,
    read_basket_transactions,
    read_flat_transactions,
    read_timestamped_transactions,
)
from .registry import build_registry
from .types import MethodInput, RunConfig


def _load_transactions(input_format: str, dataset_path: Path):
    if input_format == "flat":
        return read_flat_transactions(dataset_path)
    if input_format == "basket":
        return read_basket_transactions(dataset_path)
    if input_format == "timestamped":
        return read_timestamped_transactions(dataset_path)
    raise ValueError(f"Unknown input_format: {input_format}")


def _parse_config(path: Path) -> RunConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return RunConfig(
        method=raw["method"],
        dataset_path=Path(raw["dataset_path"]),
        input_format=raw.get("input_format", "flat"),
        output_path=Path(raw["output_path"]),
        minsup_count=raw.get("minsup_count"),
        minsup_ratio=raw.get("minsup_ratio"),
        max_length=raw.get("max_length"),
        params=raw.get("params", {}),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one comparative method")
    parser.add_argument("--config", required=True, help="Path to JSON config")
    args = parser.parse_args()

    cfg = _parse_config(Path(args.config))
    registry = build_registry()
    if cfg.method not in registry:
        raise KeyError(f"Unknown method: {cfg.method}. Available={list(registry)}")

    txns = _load_transactions(cfg.input_format, cfg.dataset_path)
    method_input = MethodInput(
        transactions=txns,
        minsup_count=cfg.minsup_count,
        minsup_ratio=cfg.minsup_ratio,
        max_length=cfg.max_length,
        params=cfg.params,
    )

    t0 = time.perf_counter()
    result = registry[cfg.method].run(method_input)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    out = {
        "config": {
            "method": cfg.method,
            "dataset_path": str(cfg.dataset_path),
            "input_format": cfg.input_format,
            "minsup_count": cfg.minsup_count,
            "minsup_ratio": cfg.minsup_ratio,
            "max_length": cfg.max_length,
            "params": cfg.params,
        },
        "runtime": {
            "elapsed_ms": elapsed_ms,
            "n_transactions": len(txns),
        },
        "result": {
            "method": result.method,
            "patterns": {
                ",".join(map(str, k)): v for k, v in result.patterns.items()
            },
            "intervals": {
                ",".join(map(str, k)): intervals
                for k, intervals in result.intervals.items()
            },
            "metadata": result.metadata,
        },
    }
    dump_result_json(cfg.output_path, out)
    print(f"[runner] method={cfg.method} output={cfg.output_path}")


if __name__ == "__main__":
    main()
