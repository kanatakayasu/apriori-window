from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from .types import Transaction


def _parse_int_items(tokens: List[str]) -> Tuple[int, ...]:
    items = sorted({int(tok) for tok in tokens if tok.strip()})
    return tuple(items)


def read_flat_transactions(path: Path) -> List[Transaction]:
    """Read classic transaction DB format: one line = item item item ..."""
    rows: List[Transaction] = []
    with open(path, "r", encoding="utf-8") as f:
        for tid, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            items = _parse_int_items(line.split())
            rows.append(Transaction(tid=tid, items=items, ts=tid))
    return rows


def read_basket_transactions(path: Path) -> List[Transaction]:
    """Read basket format used in this project.

    Example line:
      "1 2 | 3 4 | 8"
    This loader flattens each line into one transaction for pattern-oriented methods.
    """
    rows: List[Transaction] = []
    with open(path, "r", encoding="utf-8") as f:
        for tid, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            all_items: List[str] = []
            for basket in line.split("|"):
                all_items.extend(basket.split())
            items = _parse_int_items(all_items)
            rows.append(Transaction(tid=tid, items=items, ts=tid))
    return rows


def read_timestamped_transactions(path: Path) -> List[Transaction]:
    """Read timestamped format: ts item1 item2 ..."""
    rows: List[Transaction] = []
    with open(path, "r", encoding="utf-8") as f:
        for tid, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            ts = int(parts[0])
            items = _parse_int_items(parts[1:])
            rows.append(Transaction(tid=tid, items=items, ts=ts))
    return rows


def dump_result_json(path: Path, result_dict: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2)
