from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


def _parse_itemset_key(key: str) -> Tuple[int, ...]:
    if not key:
        return tuple()
    return tuple(sorted(int(x) for x in key.split(",") if x))


def _load_result(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_gt(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _gt_sets(gt: Dict) -> Tuple[Set[Tuple[int, ...]], Set[Tuple[int, ...]]]:
    true_set: Set[Tuple[int, ...]] = set()
    spurious_set: Set[Tuple[int, ...]] = set()

    for rec in gt.get("true_frequent_patterns", []):
        true_set.add(tuple(sorted(int(x) for x in rec["itemset"])))
    for rec in gt.get("spurious_patterns", []):
        spurious_set.add(tuple(sorted(int(x) for x in rec["itemset"])))

    return true_set, spurious_set


def _derive_gt_path(result: Dict, gt_dir: Path) -> Path:
    stem = Path(result["config"]["dataset_path"]).stem
    return gt_dir / f"{stem}_gt.json"


def aggregate_one(result: Dict, gt: Optional[Dict], min_itemset_size: int) -> Dict[str, object]:
    method = result["config"]["method"]
    dataset_path = result["config"]["dataset_path"]
    patterns_map = result["result"].get("patterns", {})
    intervals_map = result["result"].get("intervals", {})

    detected = {
        _parse_itemset_key(k)
        for k in patterns_map.keys()
        if len(_parse_itemset_key(k)) >= min_itemset_size
    }
    interval_count = 0
    for k, v in intervals_map.items():
        itemset = _parse_itemset_key(k)
        if len(itemset) >= min_itemset_size:
            interval_count += len(v)

    row: Dict[str, object] = {
        "method": method,
        "dataset_path": dataset_path,
        "elapsed_ms": result["runtime"].get("elapsed_ms", 0.0),
        "n_transactions": result["runtime"].get("n_transactions", 0),
        "pattern_count": len(detected),
        "interval_count": interval_count,
        "spr_detected": "",
        "true_recall": "",
        "detected_spurious_count": "",
        "gt_true_count": "",
        "gt_spurious_count": "",
    }

    if gt is not None:
        true_set, spurious_set = _gt_sets(gt)
        detected_spurious = detected & spurious_set
        detected_true = detected & true_set

        spr = (len(detected_spurious) / len(detected)) if detected else 0.0
        rec = (len(detected_true) / len(true_set)) if true_set else 0.0

        row.update(
            {
                "spr_detected": spr,
                "true_recall": rec,
                "detected_spurious_count": len(detected_spurious),
                "gt_true_count": len(true_set),
                "gt_spurious_count": len(spurious_set),
            }
        )

    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate Stage A comparative outputs")
    parser.add_argument("--results-glob", required=True)
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--gt-dir", default=None, help="Directory containing *_gt.json")
    parser.add_argument("--min-itemset-size", type=int, default=2)
    args = parser.parse_args()

    files = sorted(Path(p) for p in glob.glob(args.results_glob))
    if not files:
        raise FileNotFoundError(f"No files matched: {args.results_glob}")

    gt_dir = Path(args.gt_dir) if args.gt_dir else None

    rows: List[Dict[str, object]] = []
    for fpath in files:
        result = _load_result(fpath)
        gt = None
        if gt_dir is not None:
            gt_path = _derive_gt_path(result, gt_dir)
            gt = _load_gt(gt_path)
        rows.append(aggregate_one(result=result, gt=gt, min_itemset_size=args.min_itemset_size))

    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "method",
        "dataset_path",
        "elapsed_ms",
        "n_transactions",
        "pattern_count",
        "interval_count",
        "spr_detected",
        "true_recall",
        "detected_spurious_count",
        "gt_true_count",
        "gt_spurious_count",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"[aggregate] wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
