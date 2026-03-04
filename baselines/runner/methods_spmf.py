from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .adapters.spmf import run_spmf
from .method_base import ComparativeMethod
from .types import Itemset, MethodInput, MethodResult, Transaction

_SUP_RE = re.compile(r"^(.*?)\s+#SUP:\s*([0-9]+)")
_INTERVAL_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")


def _as_spmf_minsup_arg(method_input: MethodInput) -> str:
    if method_input.minsup_ratio is not None:
        return str(method_input.minsup_ratio)
    if method_input.minsup_count is not None:
        return str(method_input.minsup_count)
    raise ValueError("minsup_count or minsup_ratio is required")


def _txns_to_lines(transactions: Sequence[Transaction]) -> List[str]:
    lines: List[str] = []
    for row in transactions:
        lines.append(" ".join(str(x) for x in row.items))
    return lines


def _txns_to_lppm_lines(transactions: Sequence[Transaction]) -> List[str]:
    lines: List[str] = []
    for row in transactions:
        if row.ts is None:
            raise ValueError("timestamped input is required for LPPM")
        item_str = " ".join(str(x) for x in row.items)
        lines.append(f"{item_str} | {row.ts}")
    return lines


def _write_tmp_lines(lines: Iterable[str]) -> Path:
    tmp = tempfile.NamedTemporaryFile(prefix="cmp_spmf_", suffix=".txt", delete=False)
    with open(tmp.name, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line)
            f.write("\n")
    return Path(tmp.name)


def _parse_itemset_support_output(path: Path) -> Dict[Itemset, int]:
    out: Dict[Itemset, int] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = _SUP_RE.match(line)
            if not m:
                continue
            raw_items = m.group(1).strip()
            support = int(m.group(2))
            if raw_items:
                itemset = tuple(sorted(int(x) for x in raw_items.split()))
            else:
                itemset = tuple()
            out[itemset] = support
    return out


def _parse_lppm_output(path: Path) -> Dict[Itemset, List[Tuple[int, int]]]:
    out: Dict[Itemset, List[Tuple[int, int]]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "#" in line:
                left = line.split("#", 1)[0].strip()
            else:
                left = line
            itemset = tuple(sorted(int(x) for x in left.split())) if left else tuple()
            intervals = [(int(a), int(b)) for a, b in _INTERVAL_RE.findall(line)]
            out[itemset] = intervals
    return out


class _SPMFItemsetMethod(ComparativeMethod):
    def __init__(self, name: str, default_algo: str):
        self._name = name
        self._default_algo = default_algo

    @property
    def name(self) -> str:
        return self._name

    def run(self, method_input: MethodInput) -> MethodResult:
        spmf_algo = method_input.params.get("spmf_algorithm", self._default_algo)
        jar_path = method_input.params.get("spmf_jar")

        input_path = _write_tmp_lines(_txns_to_lines(method_input.transactions))
        output_path = _write_tmp_lines([])
        try:
            output_path.write_text("", encoding="utf-8")
            args = [_as_spmf_minsup_arg(method_input)]
            run_info = run_spmf(
                algorithm=spmf_algo,
                input_path=input_path,
                output_path=output_path,
                args=args,
                jar_path=jar_path,
            )
            if run_info["returncode"] != "0":
                raise RuntimeError(
                    f"SPMF {self._name} failed: {run_info['stderr'] or run_info['stdout']}"
                )

            patterns = _parse_itemset_support_output(output_path)
            return MethodResult(
                method=self._name,
                patterns=patterns,
                intervals={},
                metadata={"spmf": run_info, "n_patterns": len(patterns)},
            )
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)


class _SPMFLPPMMethod(ComparativeMethod):
    def __init__(self, name: str = "lppm", default_algo: str = "LPPM_depth"):
        self._name = name
        self._default_algo = default_algo

    @property
    def name(self) -> str:
        return self._name

    def run(self, method_input: MethodInput) -> MethodResult:
        spmf_algo = method_input.params.get("spmf_algorithm", self._default_algo)
        jar_path = method_input.params.get("spmf_jar")

        max_per = method_input.params.get("maxPer")
        min_dur = method_input.params.get("minDur")
        max_so_per = method_input.params.get("maxSoPer")
        if max_per is None or min_dur is None or max_so_per is None:
            raise ValueError("LPPM requires params: maxPer, minDur, maxSoPer")

        # SPMF Local-periodic requires an extra flag for timestamped input.
        # We keep it explicit and default to true.
        ts_flag = str(method_input.params.get("timestamps", "true")).lower()

        input_path = _write_tmp_lines(_txns_to_lppm_lines(method_input.transactions))
        output_path = _write_tmp_lines([])
        try:
            output_path.write_text("", encoding="utf-8")
            args = [str(max_per), str(min_dur), str(max_so_per), ts_flag]
            run_info = run_spmf(
                algorithm=spmf_algo,
                input_path=input_path,
                output_path=output_path,
                args=args,
                jar_path=jar_path,
            )
            if run_info["returncode"] != "0":
                raise RuntimeError(
                    f"SPMF LPPM failed: {run_info['stderr'] or run_info['stdout']}"
                )

            intervals = _parse_lppm_output(output_path)
            patterns = {k: len(v) for k, v in intervals.items()}
            return MethodResult(
                method=self._name,
                patterns=patterns,
                intervals=intervals,
                metadata={"spmf": run_info, "n_patterns": len(intervals)},
            )
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)


class _SPMFPFPMMethod(ComparativeMethod):
    def __init__(self, name: str = "pfpm", default_algo: str = "PFPM"):
        self._name = name
        self._default_algo = default_algo

    @property
    def name(self) -> str:
        return self._name

    def run(self, method_input: MethodInput) -> MethodResult:
        spmf_algo = method_input.params.get("spmf_algorithm", self._default_algo)
        jar_path = method_input.params.get("spmf_jar")

        # Allow fully explicit args when SPMF version differs.
        explicit_args = method_input.params.get("spmf_args")
        if explicit_args is not None:
            args = [str(x) for x in explicit_args]
        else:
            min_per = method_input.params.get("minPer")
            max_per = method_input.params.get("maxPer")
            min_avg = method_input.params.get("minAvg")
            max_avg = method_input.params.get("maxAvg")
            minsup = method_input.params.get(
                "minsup",
                method_input.minsup_count
                if method_input.minsup_count is not None
                else method_input.minsup_ratio,
            )
            if None in (min_per, max_per, min_avg, max_avg, minsup):
                raise ValueError(
                    "PFPM requires either params.spmf_args or "
                    "params[minPer,maxPer,minAvg,maxAvg,minsup]"
                )
            args = [str(min_per), str(max_per), str(min_avg), str(max_avg), str(minsup)]

        input_path = _write_tmp_lines(_txns_to_lines(method_input.transactions))
        output_path = _write_tmp_lines([])
        try:
            output_path.write_text("", encoding="utf-8")
            run_info = run_spmf(
                algorithm=spmf_algo,
                input_path=input_path,
                output_path=output_path,
                args=args,
                jar_path=jar_path,
            )
            if run_info["returncode"] != "0":
                raise RuntimeError(
                    f"SPMF PFPM failed: {run_info['stderr'] or run_info['stdout']}"
                )

            patterns = _parse_itemset_support_output(output_path)
            return MethodResult(
                method=self._name,
                patterns=patterns,
                intervals={},
                metadata={"spmf": run_info, "n_patterns": len(patterns), "args": args},
            )
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)


class _PlaceholderMethod(ComparativeMethod):
    def __init__(self, method_name: str):
        self._name = method_name

    @property
    def name(self) -> str:
        return self._name

    def run(self, method_input: MethodInput) -> MethodResult:
        raise NotImplementedError(
            f"Method '{self._name}' is not implemented yet. "
            "Implement Python logic or add backend adapter."
        )


def build_spmf_method_registry() -> Dict[str, ComparativeMethod]:
    return {
        "apriori": _SPMFItemsetMethod("apriori", "Apriori"),
        "fp_growth": _SPMFItemsetMethod("fp_growth", "FPGrowth_itemsets"),
        "eclat": _SPMFItemsetMethod("eclat", "Eclat"),
        "lcm": _SPMFItemsetMethod("lcm", "LCMFreq"),
        "lppm": _SPMFLPPMMethod(),
        "pfpm": _SPMFPFPMMethod(),
        "ppfpm_gpf_growth": _PlaceholderMethod("ppfpm_gpf_growth"),
        "lpfim": _PlaceholderMethod("lpfim"),
    }
