"""
Synthetic data generator for Spatio-Temporal Event Attribution experiments.

Follows the main branch design:
- Type A: Spatially localized event-driven boost (true positives)
- Type B: Event-unrelated dense patterns (should be rejected)
- Type C: Decoy events with no associated pattern changes

Key difference from main: each transaction has a spatial location,
and events have spatial scopes.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np


@dataclass
class STPlantedSignal:
    """Type A: Event-driven spatially localized boost."""
    pattern: List[int]
    event_id: str
    event_name: str
    event_start: int
    event_end: int
    spatial_scope: List[int]       # locations where boost occurs
    boost_factor: float = 0.5      # probability of co-inserting pattern items


@dataclass
class STUnrelatedDense:
    """Type B: Dense pattern unrelated to any event."""
    pattern: List[int]
    active_start: int
    active_end: int
    active_locations: List[int]    # locations where boost occurs
    boost_factor: float = 0.3


@dataclass
class STDecoyEvent:
    """Type C: Event with no associated pattern change."""
    event_id: str
    event_name: str
    start: int
    end: int
    spatial_scope: List[int]


@dataclass
class STSyntheticConfig:
    """Full configuration for synthetic data generation."""
    n_transactions: int = 2000
    n_items: int = 50
    n_locations: int = 20
    p_base: float = 0.03
    planted_signals: List[STPlantedSignal] = field(default_factory=list)
    unrelated_dense: List[STUnrelatedDense] = field(default_factory=list)
    decoy_events: List[STDecoyEvent] = field(default_factory=list)
    seed: int = 42


def generate_st_synthetic(config: STSyntheticConfig, out_dir: str) -> None:
    """Generate synthetic spatio-temporal data."""
    rng = np.random.default_rng(config.seed)
    os.makedirs(out_dir, exist_ok=True)

    transactions = []
    locations = []

    for t in range(config.n_transactions):
        loc = int(rng.integers(0, config.n_locations))  # random location
        locations.append(loc)

        # Base items
        txn = set()
        for item in range(config.n_items):
            if rng.random() < config.p_base:
                txn.add(item)

        # Type A: Planted signals (spatially localized)
        for signal in config.planted_signals:
            if signal.event_start <= t <= signal.event_end:
                if loc in signal.spatial_scope:
                    if rng.random() < signal.boost_factor:
                        for item in signal.pattern:
                            txn.add(item)

        # Type B: Unrelated dense patterns (spatially localized)
        for ud in config.unrelated_dense:
            if ud.active_start <= t <= ud.active_end:
                if loc in ud.active_locations:
                    if rng.random() < ud.boost_factor:
                        for item in ud.pattern:
                            txn.add(item)

        transactions.append(txn)

    # Write transactions
    with open(os.path.join(out_dir, "transactions.txt"), "w") as f:
        for txn in transactions:
            f.write(" ".join(str(x) for x in sorted(txn)) + "\n")

    # Write locations
    with open(os.path.join(out_dir, "locations.txt"), "w") as f:
        for loc in locations:
            f.write(f"{loc}\n")

    # Write events
    events = []
    for s in config.planted_signals:
        events.append({
            "event_id": s.event_id,
            "name": s.event_name,
            "start": s.event_start,
            "end": s.event_end,
            "spatial_scope": s.spatial_scope,
        })
    for d in config.decoy_events:
        events.append({
            "event_id": d.event_id,
            "name": d.event_name,
            "start": d.start,
            "end": d.end,
            "spatial_scope": d.spatial_scope,
        })
    with open(os.path.join(out_dir, "events.json"), "w") as f:
        json.dump(events, f, indent=2)

    # Write ground truth (Type A only)
    gt = []
    for s in config.planted_signals:
        gt.append({
            "pattern": sorted(s.pattern),
            "event_id": s.event_id,
        })
    with open(os.path.join(out_dir, "ground_truth.json"), "w") as f:
        json.dump(gt, f, indent=2)

    # Write unrelated patterns (for FAR calculation)
    unrelated = []
    for ud in config.unrelated_dense:
        unrelated.append({"pattern": sorted(ud.pattern)})
    with open(os.path.join(out_dir, "unrelated_patterns.json"), "w") as f:
        json.dump(unrelated, f, indent=2)

    # Write config
    with open(os.path.join(out_dir, "config.json"), "w") as f:
        json.dump({
            "n_transactions": config.n_transactions,
            "n_items": config.n_items,
            "n_locations": config.n_locations,
            "p_base": config.p_base,
            "seed": config.seed,
            "n_planted": len(config.planted_signals),
            "n_unrelated": len(config.unrelated_dense),
            "n_decoy": len(config.decoy_events),
        }, f, indent=2)


# ---------------------------------------------------------------------------
# Preset configurations (following main branch EX1 design)
# ---------------------------------------------------------------------------

def make_ex1_config(beta: float = 0.3, seed: int = 42) -> STSyntheticConfig:
    """
    EX1 core config: spatially localized vs global events.

    N=20000 with 20 locations → ~1000 txns/location.
    Window=200 → ~10 txns/location/window → boost 0.5 gives ~5 support.
    """
    return STSyntheticConfig(
        n_transactions=20000,
        n_items=50,
        n_locations=20,
        p_base=0.03,
        planted_signals=[
            STPlantedSignal(
                pattern=[5, 15], event_id="E1", event_name="local_campaign",
                event_start=4000, event_end=8000,
                spatial_scope=list(range(0, 10)),
                boost_factor=beta,
            ),
            STPlantedSignal(
                pattern=[25, 35], event_id="E2", event_name="global_campaign",
                event_start=12000, event_end=16000,
                spatial_scope=list(range(0, 20)),  # all locations
                boost_factor=beta,
            ),
        ],
        unrelated_dense=[
            STUnrelatedDense(
                pattern=[40, 45],
                active_start=2000, active_end=3500,
                active_locations=list(range(5, 15)),
                boost_factor=0.4,
            ),
        ],
        decoy_events=[
            STDecoyEvent(
                event_id="D1", event_name="decoy_event",
                start=9000, end=11000,
                spatial_scope=list(range(15, 20)),
            ),
        ],
        seed=seed,
    )


def make_confound_config(beta: float = 0.3, seed: int = 42) -> STSyntheticConfig:
    """Type B pattern active near event time but at DIFFERENT locations."""
    return STSyntheticConfig(
        n_transactions=20000,
        n_items=50,
        n_locations=20,
        p_base=0.03,
        planted_signals=[
            STPlantedSignal(
                pattern=[5, 15], event_id="E1", event_name="local_campaign",
                event_start=4000, event_end=8000,
                spatial_scope=list(range(0, 10)),
                boost_factor=beta,
            ),
        ],
        unrelated_dense=[
            STUnrelatedDense(
                pattern=[40, 45],
                active_start=4200, active_end=7800,  # overlapping time with E1
                active_locations=list(range(12, 20)),  # different locations
                boost_factor=0.4,
            ),
        ],
        decoy_events=[],
        seed=seed,
    )


def make_dense_config(beta: float = 0.3, seed: int = 42) -> STSyntheticConfig:
    """Dense scenario: many signals + many Type B + decoys."""
    return STSyntheticConfig(
        n_transactions=30000,
        n_items=50,
        n_locations=20,
        p_base=0.03,
        planted_signals=[
            STPlantedSignal(
                pattern=[5, 15], event_id="E1", event_name="campaign_A",
                event_start=4000, event_end=8000,
                spatial_scope=list(range(0, 10)),
                boost_factor=beta,
            ),
            STPlantedSignal(
                pattern=[25, 35], event_id="E2", event_name="campaign_B",
                event_start=12000, event_end=16000,
                spatial_scope=list(range(10, 20)),
                boost_factor=beta,
            ),
            STPlantedSignal(
                pattern=[6, 16], event_id="E3", event_name="campaign_C",
                event_start=20000, event_end=24000,
                spatial_scope=list(range(0, 20)),
                boost_factor=beta,
            ),
        ],
        unrelated_dense=[
            STUnrelatedDense(
                pattern=[40, 45], active_start=2000, active_end=3500,
                active_locations=list(range(5, 15)), boost_factor=0.4,
            ),
            STUnrelatedDense(
                pattern=[41, 46], active_start=17000, active_end=19000,
                active_locations=list(range(0, 8)), boost_factor=0.4,
            ),
        ],
        decoy_events=[
            STDecoyEvent("D1", "decoy_1", 9000, 11000, list(range(0, 10))),
            STDecoyEvent("D2", "decoy_2", 26000, 28000, list(range(10, 20))),
        ],
        seed=seed,
    )
