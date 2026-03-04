from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from .adapters.rust_mining import run_rust_mining
from .method_base import ComparativeMethod
from .types import MethodInput, MethodResult, Transaction


def _write_input(transactions: Sequence[Transaction], fmt: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(prefix="cmp_rust_", suffix=".txt", delete=False)
    p = Path(tmp.name)
    with open(p, "w", encoding="utf-8") as f:
        for idx, row in enumerate(transactions):
            items = " ".join(str(x) for x in sorted(set(row.items)))
            if fmt == "flat":
                f.write(items + "\n")
            elif fmt == "timestamped":
                ts = row.ts if row.ts is not None else idx
                f.write(f"{ts} {items}\n")
            elif fmt == "basket":
                f.write(items + "\n")
            else:
                raise ValueError(f"unknown fmt={fmt}")
    return p


def _parse_itemset_key(key: str) -> Tuple[int, ...]:
    if not key:
        return tuple()
    return tuple(sorted(int(x) for x in key.split(",") if x))


class RustMethod(ComparativeMethod):
    def __init__(self, method_name: str, input_format: str):
        self._name = method_name
        self._format = input_format

    @property
    def name(self) -> str:
        return self._name

    def run(self, method_input: MethodInput) -> MethodResult:
        params = dict(method_input.params)
        params.setdefault("minsup_count", method_input.minsup_count)
        params.setdefault("minsup_ratio", method_input.minsup_ratio)
        params.setdefault("max_length", method_input.max_length)

        input_path = _write_input(method_input.transactions, self._format)
        try:
            out = run_rust_mining(
                method=self._name,
                input_path=input_path,
                input_format=self._format,
                params=params,
            )
        finally:
            input_path.unlink(missing_ok=True)

        patterns = {
            _parse_itemset_key(k): int(v)
            for k, v in out.get("patterns", {}).items()
            if k != ""
        }
        intervals = {
            _parse_itemset_key(k): [tuple(pair) for pair in vals]
            for k, vals in out.get("intervals", {}).items()
            if k != ""
        }
        metadata = out.get("metadata", {})
        metadata["runner"] = out.get("_runner", {})

        return MethodResult(
            method=self._name,
            patterns=patterns,
            intervals=intervals,
            metadata=metadata,
        )
