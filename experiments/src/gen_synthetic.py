"""
Synthetic data generator for Event Attribution experiments.

Generates:
  1. Transaction file (single-basket format)
  2. Events JSON file
  3. Ground truth JSON (pattern → event_id pairs)
"""
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class PlantedSignal:
    pattern: List[int]
    event_id: str
    event_name: str
    event_start: int
    event_end: int
    boost_factor: float = 5.0


@dataclass
class DecoyEvent:
    event_id: str
    event_name: str
    start: int
    end: int


@dataclass
class SyntheticConfig:
    n_transactions: int = 10000
    n_items: int = 500
    p_base: float = 0.02
    planted_signals: List[PlantedSignal] = field(default_factory=list)
    decoy_events: List[DecoyEvent] = field(default_factory=list)
    seed: int = 42


def generate_synthetic(config: SyntheticConfig, out_dir: str) -> Dict:
    """Generate synthetic dataset with planted signals."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    rng = random.Random(config.seed)
    transactions = []

    for t in range(config.n_transactions):
        items = set()
        # Base items
        for item in range(1, config.n_items + 1):
            if rng.random() < config.p_base:
                items.add(item)

        # Planted signals: boost co-occurrence within event window.
        # Planted items use IDs outside the base vocabulary (1001+) so they
        # ONLY appear during the event window, preventing spurious patterns
        # containing planted items from inflating false positives.
        # boost_factor は各アイテムの挿入確率: 1.0 なら確定挿入。
        for sig in config.planted_signals:
            if sig.event_start <= t <= sig.event_end:
                # 全アイテムを同時に挿入（共起として植え込み）
                if rng.random() < min(1.0, sig.boost_factor):
                    for item in sig.pattern:
                        items.add(item)

        transactions.append(sorted(items))

    # Write transactions
    txn_path = out_path / "transactions.txt"
    with open(txn_path, "w") as f:
        for txn in transactions:
            f.write(" ".join(str(x) for x in txn) + "\n")

    # Write events
    events = []
    for sig in config.planted_signals:
        events.append({
            "event_id": sig.event_id,
            "name": sig.event_name,
            "start": sig.event_start,
            "end": sig.event_end,
        })
    for dec in config.decoy_events:
        events.append({
            "event_id": dec.event_id,
            "name": dec.event_name,
            "start": dec.start,
            "end": dec.end,
        })

    events_path = out_path / "events.json"
    with open(events_path, "w") as f:
        json.dump(events, f, indent=2)

    # Write ground truth
    ground_truth = []
    for sig in config.planted_signals:
        ground_truth.append({
            "pattern": sorted(sig.pattern),
            "event_id": sig.event_id,
        })

    gt_path = out_path / "ground_truth.json"
    with open(gt_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    return {
        "txn_path": str(txn_path),
        "events_path": str(events_path),
        "gt_path": str(gt_path),
        "n_transactions": config.n_transactions,
        "n_planted": len(config.planted_signals),
        "n_decoy": len(config.decoy_events),
    }


def make_default_config(
    n_transactions: int = 10000,
    n_planted: int = 5,
    n_decoy: int = 5,
    boost: float = 5.0,
    event_duration: int = 200,
    seed: int = 42,
) -> SyntheticConfig:
    """Create a default synthetic config with well-separated planted signals."""
    rng = random.Random(seed)
    spacing = n_transactions // (n_planted + 1)

    planted = []
    for i in range(n_planted):
        start = spacing * (i + 1) - event_duration // 2
        end = start + event_duration
        start = max(0, start)
        end = min(n_transactions - 1, end)
        # Each pattern uses distinct items to avoid overlap
        base_item = 10 + i * 10
        pattern = [base_item, base_item + 1]
        planted.append(PlantedSignal(
            pattern=pattern,
            event_id=f"E{i+1}",
            event_name=f"Event_{i+1}",
            event_start=start,
            event_end=end,
            boost_factor=boost,
        ))

    decoys = []
    for i in range(n_decoy):
        start = rng.randint(0, n_transactions - event_duration - 1)
        end = start + event_duration
        decoys.append(DecoyEvent(
            event_id=f"D{i+1}",
            event_name=f"Decoy_{i+1}",
            start=start,
            end=end,
        ))

    return SyntheticConfig(
        n_transactions=n_transactions,
        planted_signals=planted,
        decoy_events=decoys,
        boost_factor=boost,
        seed=seed,
    )


def inject_events_into_real_data(
    input_path: str,
    out_dir: str,
    patterns_to_boost: List[List[int]],
    event_duration: int = 500,
    boost_factor: float = 3.0,
    n_decoy: int = 5,
    seed: int = 42,
) -> Dict:
    """Inject synthetic events into a real dataset by boosting specific patterns."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    # Read original transactions
    with open(input_path, "r") as f:
        lines = f.readlines()

    n_transactions = len(lines)
    spacing = n_transactions // (len(patterns_to_boost) + 1)

    planted_signals = []
    for i, pattern in enumerate(patterns_to_boost):
        start = spacing * (i + 1) - event_duration // 2
        end = start + event_duration
        start = max(0, start)
        end = min(n_transactions - 1, end)
        planted_signals.append(PlantedSignal(
            pattern=pattern,
            event_id=f"E{i+1}",
            event_name=f"RealEvent_{i+1}",
            event_start=start,
            event_end=end,
            boost_factor=boost_factor,
        ))

    # Modify transactions by boosting pattern items within event windows
    new_lines = []
    for t, line in enumerate(lines):
        line = line.strip()
        if not line:
            new_lines.append("")
            continue
        items = set(int(x) for x in line.split())
        for sig in planted_signals:
            if sig.event_start <= t <= sig.event_end:
                for item in sig.pattern:
                    if rng.random() < min(1.0, boost_factor * 0.3):
                        items.add(item)
        new_lines.append(" ".join(str(x) for x in sorted(items)))

    txn_path = out_path / "transactions.txt"
    with open(txn_path, "w") as f:
        for line in new_lines:
            f.write(line + "\n")

    # Events
    events = []
    for sig in planted_signals:
        events.append({
            "event_id": sig.event_id,
            "name": sig.event_name,
            "start": sig.event_start,
            "end": sig.event_end,
        })

    decoys = []
    for i in range(n_decoy):
        start = rng.randint(0, n_transactions - event_duration - 1)
        end = start + event_duration
        ev = {"event_id": f"D{i+1}", "name": f"Decoy_{i+1}", "start": start, "end": end}
        events.append(ev)
        decoys.append(ev)

    events_path = out_path / "events.json"
    with open(events_path, "w") as f:
        json.dump(events, f, indent=2)

    ground_truth = [{"pattern": sorted(sig.pattern), "event_id": sig.event_id}
                    for sig in planted_signals]
    gt_path = out_path / "ground_truth.json"
    with open(gt_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    return {
        "txn_path": str(txn_path),
        "events_path": str(events_path),
        "gt_path": str(gt_path),
        "n_transactions": n_transactions,
        "n_planted": len(planted_signals),
        "n_decoy": n_decoy,
    }
