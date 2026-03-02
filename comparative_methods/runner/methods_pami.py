from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from .method_base import ComparativeMethod
from .types import Itemset, MethodInput, MethodResult, Transaction


def _write_pami_input(transactions: Sequence[Transaction]) -> Path:
    """Write PAMI input: timestamp first, tab-delimited."""
    tmp = tempfile.NamedTemporaryFile(prefix="cmp_pami_", suffix=".txt", delete=False)
    with open(tmp.name, "w", encoding="utf-8") as f:
        for row in transactions:
            ts = row.ts if row.ts is not None else row.tid + 1
            items = "\t".join(str(x) for x in sorted(set(row.items)))
            f.write(f"{ts}\t{items}\n")
    return Path(tmp.name)


def _import_gpf_class():
    try:
        from PAMI.partialPeriodicFrequentPattern.basic import GPFgrowth as mod  # type: ignore
    except Exception as e:
        raise ImportError(
            "PAMI GPFgrowth module not found. Install pami and verify module path."
        ) from e

    for cls_name in ("GPFgrowth", "GPFGrowth", "GPFGrowth"):
        if hasattr(mod, cls_name):
            return getattr(mod, cls_name)
    raise ImportError("Could not resolve GPFgrowth class in PAMI module")


def _coerce_itemset(key: Any) -> Itemset:
    if isinstance(key, tuple):
        return tuple(sorted(int(x) for x in key))
    if isinstance(key, list):
        return tuple(sorted(int(x) for x in key))
    if isinstance(key, str):
        # PAMI keys are often tab/space separated string.
        toks = [tok for tok in key.replace(",", " ").replace("\t", " ").split() if tok]
        return tuple(sorted(int(x) for x in toks))
    raise ValueError(f"Unsupported itemset key type: {type(key)}")


def _coerce_support(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, dict):
        # best-effort: support may be under various names
        for k in ("support", "sup", "count"):
            if k in value:
                return int(value[k])
        # fallback to first numeric value
        for v in value.values():
            if isinstance(v, (int, float)):
                return int(v)
    if isinstance(value, (list, tuple)):
        for v in value:
            if isinstance(v, (int, float)):
                return int(v)
    # unknown format: keep as 0, metadata will contain raw object
    return 0


class PPFPMGPFGrowthMethod(ComparativeMethod):
    """PPFPM baseline via PAMI GPFgrowth (decision #2)."""

    @property
    def name(self) -> str:
        return "ppfpm_gpf_growth"

    def run(self, method_input: MethodInput) -> MethodResult:
        gpf_cls = _import_gpf_class()

        min_sup = method_input.params.get(
            "minSup",
            method_input.minsup_count if method_input.minsup_count is not None else 1,
        )
        max_per = method_input.params.get("maxPer")
        min_pr = method_input.params.get("minPR")
        if max_per is None or min_pr is None:
            raise ValueError("PPFPM requires params: maxPer, minPR (and minSup)")

        input_path = _write_pami_input(method_input.transactions)
        try:
            kwargs = {
                "iFile": str(input_path),
                "minSup": min_sup,
                "maxPer": max_per,
                "minPR": min_pr,
                "sep": "\t",
            }
            model = gpf_cls(**kwargs)

            # PAMI variants differ in method naming.
            if hasattr(model, "mine"):
                model.mine()
            elif hasattr(model, "startMine"):
                model.startMine()
            else:
                raise RuntimeError("GPFgrowth object has neither mine() nor startMine()")

            if not hasattr(model, "getPatterns"):
                raise RuntimeError("GPFgrowth object does not expose getPatterns()")

            raw_patterns = model.getPatterns()
            patterns: Dict[Itemset, int] = {}
            raw_values: Dict[str, Any] = {}
            if isinstance(raw_patterns, dict):
                for k, v in raw_patterns.items():
                    itemset = _coerce_itemset(k)
                    patterns[itemset] = _coerce_support(v)
                    raw_values[",".join(map(str, itemset))] = v
            else:
                raise RuntimeError("Unsupported getPatterns() return type")

            return MethodResult(
                method=self.name,
                patterns=patterns,
                intervals={},
                metadata={
                    "impl": "pami_gpfgrowth",
                    "decision": "definition_plus_examples_plus_pami",
                    "params": {
                        "minSup": min_sup,
                        "maxPer": max_per,
                        "minPR": min_pr,
                    },
                    "raw_patterns": raw_values,
                    "n_patterns": len(patterns),
                },
            )
        finally:
            input_path.unlink(missing_ok=True)
