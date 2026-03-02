from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


Itemset = Tuple[int, ...]
Interval = Tuple[int, int]


@dataclass
class Transaction:
    """Single transaction event used by comparative methods."""

    tid: int
    items: Tuple[int, ...]
    ts: Optional[int] = None


@dataclass
class MethodInput:
    """Normalized input bundle passed to one comparative method."""

    transactions: Sequence[Transaction]
    minsup_count: Optional[int] = None
    minsup_ratio: Optional[float] = None
    max_length: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MethodResult:
    """Unified output envelope.

    patterns: support-oriented methods use this.
    intervals: interval-aware methods use this.
    metadata: runtime stats and method specific values.
    """

    method: str
    patterns: Dict[Itemset, int] = field(default_factory=dict)
    intervals: Dict[Itemset, List[Interval]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunConfig:
    """Configuration loaded from JSON for runner CLI."""

    method: str
    dataset_path: Path
    input_format: str
    output_path: Path
    minsup_count: Optional[int] = None
    minsup_ratio: Optional[float] = None
    max_length: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)
