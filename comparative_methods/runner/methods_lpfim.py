from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, Iterable, List, Sequence, Tuple

from .method_base import ComparativeMethod
from .types import Itemset, MethodInput, MethodResult, Transaction


@dataclass
class _IntervalState:
    start: int
    end: int
    count: int


def _validate_timestamped(transactions: Sequence[Transaction]) -> None:
    for t in transactions:
        if t.ts is None:
            raise ValueError("LPFIM requires timestamped transactions (ts is required)")


def _normalize_transactions(transactions: Sequence[Transaction]) -> List[Transaction]:
    # Stable sort by timestamp then tid; keep duplicate timestamps in input order.
    return sorted(transactions, key=lambda t: (int(t.ts), t.tid))


def _generate_itemset_counts(
    transactions: Sequence[Transaction], max_length: int
) -> Tuple[Counter[Itemset], Dict[Itemset, List[int]]]:
    counts: Counter[Itemset] = Counter()
    occ: Dict[Itemset, List[int]] = {}
    for row in transactions:
        items = tuple(sorted(set(row.items)))
        upto = min(max_length, len(items))
        for k in range(1, upto + 1):
            for comb in combinations(items, k):
                counts[comb] += 1
                occ.setdefault(comb, []).append(int(row.ts))
    return counts, occ


def _build_intervals(
    ts_list: List[int], sigma_count: int, minthd1: int, minthd2: int
) -> List[Tuple[int, int]]:
    if not ts_list:
        return []

    intervals: List[Tuple[int, int]] = []
    st = _IntervalState(start=ts_list[0], end=ts_list[0], count=1)

    for ts in ts_list[1:]:
        if ts - st.end < minthd1:
            st.end = ts
            st.count += 1
            continue

        # close old interval
        if (st.end - st.start) >= minthd2 and st.count >= sigma_count:
            intervals.append((st.start, st.end))

        # start new interval
        st = _IntervalState(start=ts, end=ts, count=1)

    # close final interval
    if (st.end - st.start) >= minthd2 and st.count >= sigma_count:
        intervals.append((st.start, st.end))

    return intervals


class LPFIMMethod(ComparativeMethod):
    """LPFIM baseline (project decision: support is count-based)."""

    @property
    def name(self) -> str:
        return "lpfim"

    def run(self, method_input: MethodInput) -> MethodResult:
        _validate_timestamped(method_input.transactions)

        txns = _normalize_transactions(method_input.transactions)
        max_length = int(method_input.max_length or method_input.params.get("max_length", 4))

        sigma_count = int(
            method_input.params.get(
                "sigma",
                method_input.minsup_count if method_input.minsup_count is not None else 1,
            )
        )
        minthd1 = int(method_input.params.get("minthd1", 1))
        minthd2 = int(method_input.params.get("minthd2", 0))
        tau = method_input.params.get("tau")

        counts, occurrences = _generate_itemset_counts(txns, max_length=max_length)

        patterns: Dict[Itemset, int] = {}
        intervals: Dict[Itemset, List[Tuple[int, int]]] = {}
        for itemset, cnt in counts.items():
            if cnt < sigma_count:
                continue
            ivals = _build_intervals(
                occurrences[itemset],
                sigma_count=sigma_count,
                minthd1=minthd1,
                minthd2=minthd2,
            )
            if not ivals:
                continue
            patterns[itemset] = cnt
            intervals[itemset] = ivals

        return MethodResult(
            method=self.name,
            patterns=patterns,
            intervals=intervals,
            metadata={
                "impl": "python_lpfim_baseline",
                "decision": "support_count_based",
                "params": {
                    "sigma": sigma_count,
                    "tau": tau,
                    "minthd1": minthd1,
                    "minthd2": minthd2,
                    "max_length": max_length,
                },
                "n_patterns": len(patterns),
            },
        )
