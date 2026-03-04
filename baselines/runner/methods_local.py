from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import combinations
from typing import Dict, List, Sequence, Tuple

from .method_base import ComparativeMethod
from .types import Itemset, MethodInput, MethodResult, Transaction


def _norm_txns(transactions: Sequence[Transaction]) -> List[Transaction]:
    out: List[Transaction] = []
    for i, row in enumerate(transactions):
        items = tuple(sorted(set(int(x) for x in row.items)))
        ts = int(row.ts) if row.ts is not None else i
        out.append(Transaction(tid=i, items=items, ts=ts))
    return sorted(out, key=lambda t: (int(t.ts), t.tid))


def _minsup_count(inp: MethodInput, n_txn: int) -> int:
    if inp.minsup_count is not None:
        return int(inp.minsup_count)
    if inp.minsup_ratio is not None:
        return max(1, int(math.ceil(inp.minsup_ratio * n_txn)))
    return 1


def _enumerate_itemsets(
    txns: Sequence[Transaction], max_length: int
) -> Tuple[Counter[Itemset], Dict[Itemset, List[int]]]:
    counts: Counter[Itemset] = Counter()
    ts_map: Dict[Itemset, List[int]] = defaultdict(list)
    for row in txns:
        upto = min(max_length, len(row.items))
        for k in range(1, upto + 1):
            for comb in combinations(row.items, k):
                counts[comb] += 1
                ts_map[comb].append(int(row.ts))
    return counts, ts_map


def _periods(ts_list: List[int], ts_fin: int) -> List[int]:
    if not ts_list:
        return []
    out = [ts_list[0] - 0]
    for i in range(1, len(ts_list)):
        out.append(ts_list[i] - ts_list[i - 1])
    out.append(ts_fin - ts_list[-1])
    return out


class _PatternBase(ComparativeMethod):
    def __init__(self, method_name: str):
        self._name = method_name

    @property
    def name(self) -> str:
        return self._name

    def run(self, method_input: MethodInput) -> MethodResult:
        txns = _norm_txns(method_input.transactions)
        minsup = _minsup_count(method_input, len(txns))
        max_length = int(method_input.max_length or method_input.params.get("max_length", 4))
        counts, _ = _enumerate_itemsets(txns, max_length=max_length)
        patterns = {k: v for k, v in counts.items() if v >= minsup}
        return MethodResult(
            method=self.name,
            patterns=patterns,
            intervals={},
            metadata={
                "impl": f"python_{self.name}",
                "minsup_count": minsup,
                "max_length": max_length,
                "n_patterns": len(patterns),
            },
        )


class AprioriLocalMethod(_PatternBase):
    def __init__(self):
        super().__init__("apriori")


class FPGrowthLocalMethod(_PatternBase):
    def __init__(self):
        super().__init__("fp_growth")


class EclatLocalMethod(_PatternBase):
    def __init__(self):
        super().__init__("eclat")


class LCMLocalMethod(_PatternBase):
    def __init__(self):
        super().__init__("lcm")


class PFPMLocalMethod(ComparativeMethod):
    @property
    def name(self) -> str:
        return "pfpm"

    def run(self, method_input: MethodInput) -> MethodResult:
        txns = _norm_txns(method_input.transactions)
        minsup = int(method_input.params.get("minsup", _minsup_count(method_input, len(txns))))
        max_length = int(method_input.max_length or method_input.params.get("max_length", 4))
        min_per = int(method_input.params.get("minPer", 1))
        max_per = int(method_input.params.get("maxPer", 10**9))
        min_avg = float(method_input.params.get("minAvg", 0))
        max_avg = float(method_input.params.get("maxAvg", 10**9))

        counts, ts_map = _enumerate_itemsets(txns, max_length=max_length)
        ts_fin = max(int(t.ts) for t in txns) if txns else 0

        patterns: Dict[Itemset, int] = {}
        stats: Dict[str, Dict[str, float]] = {}
        for itemset, sup in counts.items():
            if sup < minsup:
                continue
            p = _periods(ts_map[itemset], ts_fin)
            if not p:
                continue
            pmin, pmax = min(p), max(p)
            pavg = sum(p) / len(p)
            if pmin >= min_per and pmax <= max_per and min_avg <= pavg <= max_avg:
                patterns[itemset] = sup
                stats[",".join(map(str, itemset))] = {
                    "minPer": pmin,
                    "maxPer": pmax,
                    "avgPer": pavg,
                }

        return MethodResult(
            method=self.name,
            patterns=patterns,
            intervals={},
            metadata={
                "impl": "python_pfpm",
                "params": {
                    "minsup": minsup,
                    "minPer": min_per,
                    "maxPer": max_per,
                    "minAvg": min_avg,
                    "maxAvg": max_avg,
                },
                "periodicity": stats,
                "n_patterns": len(patterns),
            },
        )


class PPFPMGPFGrowthLocalMethod(ComparativeMethod):
    @property
    def name(self) -> str:
        return "ppfpm_gpf_growth"

    def run(self, method_input: MethodInput) -> MethodResult:
        txns = _norm_txns(method_input.transactions)
        minsup = int(method_input.params.get("minSup", _minsup_count(method_input, len(txns))))
        max_length = int(method_input.max_length or method_input.params.get("max_length", 4))
        max_per = int(method_input.params.get("maxPer", 10**9))
        min_pr = float(method_input.params.get("minPR", 0.0))

        counts, ts_map = _enumerate_itemsets(txns, max_length=max_length)
        ts_fin = max(int(t.ts) for t in txns) if txns else 0

        patterns: Dict[Itemset, int] = {}
        periodic_ratio: Dict[str, float] = {}
        for itemset, sup in counts.items():
            if sup < minsup:
                continue
            p = _periods(ts_map[itemset], ts_fin)
            if not p:
                continue
            ip = sum(1 for x in p if x <= max_per)
            pr = ip / len(p)
            if pr >= min_pr:
                patterns[itemset] = sup
                periodic_ratio[",".join(map(str, itemset))] = pr

        return MethodResult(
            method=self.name,
            patterns=patterns,
            intervals={},
            metadata={
                "impl": "python_ppfpm",
                "decision": "definition_based",
                "params": {"minSup": minsup, "maxPer": max_per, "minPR": min_pr},
                "periodic_ratio": periodic_ratio,
                "n_patterns": len(patterns),
            },
        )


class LPPMLocalMethod(ComparativeMethod):
    @property
    def name(self) -> str:
        return "lppm"

    def run(self, method_input: MethodInput) -> MethodResult:
        txns = _norm_txns(method_input.transactions)
        max_length = int(method_input.max_length or method_input.params.get("max_length", 4))
        max_per = int(method_input.params.get("maxPer", 10))
        max_so_per = int(method_input.params.get("maxSoPer", 0))
        min_dur = int(method_input.params.get("minDur", 1))

        counts, ts_map = _enumerate_itemsets(txns, max_length=max_length)

        intervals: Dict[Itemset, List[Tuple[int, int]]] = {}
        patterns: Dict[Itemset, int] = {}

        for itemset, ts_list in ts_map.items():
            if len(ts_list) < 2:
                continue
            st = ts_list[0]
            prev = ts_list[0]
            so = 0
            ints: List[Tuple[int, int]] = []
            for ts in ts_list[1:]:
                gap = ts - prev
                if gap > max_per:
                    so += gap - max_per
                if so > max_so_per:
                    if (prev - st) >= min_dur:
                        ints.append((st, prev))
                    st = ts
                    so = 0
                prev = ts
            if (prev - st) >= min_dur:
                ints.append((st, prev))

            if ints:
                intervals[itemset] = ints
                patterns[itemset] = counts[itemset]

        return MethodResult(
            method=self.name,
            patterns=patterns,
            intervals=intervals,
            metadata={
                "impl": "python_lppm_baseline",
                "params": {"maxPer": max_per, "maxSoPer": max_so_per, "minDur": min_dur},
                "n_patterns": len(patterns),
            },
        )
