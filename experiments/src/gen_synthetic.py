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
    baseline_prob: float = 0.0  # >0 means items appear outside event window too


@dataclass
class UnrelatedDensePattern:
    """Type B signal: dense pattern NOT associated with any event."""
    pattern: List[int]
    active_start: int
    active_end: int
    boost_factor: float = 0.3


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
    unrelated_dense_patterns: List[UnrelatedDensePattern] = field(default_factory=list)
    seed: int = 42
    # Per-item probabilities (Zipf etc.). When set, overrides p_base.
    # Keys are item IDs (1..n_items), values are occurrence probabilities.
    item_probs: Optional[Dict[int, float]] = None
    # Correlated item pairs: (item_a, item_b, correlation_prob).
    # If item_a appears in a transaction, item_b also appears with this prob.
    correlated_pairs: Optional[List[Tuple[int, int, float]]] = None


def generate_synthetic(config: SyntheticConfig, out_dir: str) -> Dict:
    """Generate synthetic dataset with planted signals."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    rng = random.Random(config.seed)
    transactions = []

    for t in range(config.n_transactions):
        items = set()
        # Base items (per-item probs if available, else uniform p_base)
        for item in range(1, config.n_items + 1):
            p = (config.item_probs[item]
                 if config.item_probs and item in config.item_probs
                 else config.p_base)
            if rng.random() < p:
                items.add(item)

        # Planted signals: boost co-occurrence within event window.
        # boost_factor は各アイテムの挿入確率: 1.0 なら確定挿入。
        # baseline_prob > 0 の場合、イベント窓外でも各アイテムが独立に出現する
        # (Type A: vocabulary-internal boost)。
        for sig in config.planted_signals:
            if sig.event_start <= t <= sig.event_end:
                # 全アイテムを同時に挿入（共起として植え込み）
                if rng.random() < min(1.0, sig.boost_factor):
                    for item in sig.pattern:
                        items.add(item)
            elif sig.baseline_prob > 0:
                # Outside event window: each item appears independently
                for item in sig.pattern:
                    if rng.random() < sig.baseline_prob:
                        items.add(item)

        # Unrelated dense patterns (Type B): insert during active period only.
        # These are NOT listed in ground truth — they simulate seasonal/trend
        # patterns that a good method should NOT attribute to any event.
        for udp in config.unrelated_dense_patterns:
            if udp.active_start <= t <= udp.active_end:
                if rng.random() < min(1.0, udp.boost_factor):
                    for item in udp.pattern:
                        items.add(item)

        # Correlated pairs: if item_a present, insert item_b with given prob
        if config.correlated_pairs:
            for item_a, item_b, corr_prob in config.correlated_pairs:
                if item_a in items and rng.random() < corr_prob:
                    items.add(item_b)

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

    # Write unrelated dense patterns info (for evaluation)
    unrelated_info = []
    for udp in config.unrelated_dense_patterns:
        unrelated_info.append({
            "pattern": sorted(udp.pattern),
            "active_start": udp.active_start,
            "active_end": udp.active_end,
            "boost_factor": udp.boost_factor,
        })

    unrelated_path = out_path / "unrelated_patterns.json"
    with open(unrelated_path, "w") as f:
        json.dump(unrelated_info, f, indent=2)

    return {
        "txn_path": str(txn_path),
        "events_path": str(events_path),
        "gt_path": str(gt_path),
        "unrelated_path": str(unrelated_path),
        "n_transactions": config.n_transactions,
        "n_planted": len(config.planted_signals),
        "n_decoy": len(config.decoy_events),
        "n_unrelated": len(config.unrelated_dense_patterns),
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
        seed=seed,
    )


def make_ex1_config(
    n_transactions: int = 5000,
    boost: float = 0.3,
    n_unrelated: int = 2,
    n_decoy: int = 2,
    seed: int = 42,
) -> SyntheticConfig:
    """Create config with all 3 signal types for experiment 1.

    Type A (vocabulary-internal boost): Planted signals using base-vocabulary
        items (IDs 5,15,25,...) that have baseline presence (p_base prob)
        outside event windows and boosted co-occurrence during event windows.
    Type B (unrelated dense): Patterns that become dense during specific
        periods but are NOT associated with any event.
    Type C (decoy events): Events that exist but cause no pattern changes.
    """
    p_base = 0.03
    event_duration = 300

    # --- Type A: 3 vocabulary-internal planted signals ---
    type_a_items = [[5, 15], [25, 35], [45, 55]]
    spacing = n_transactions // (len(type_a_items) + 1)
    planted = []
    for i, pat in enumerate(type_a_items):
        start = spacing * (i + 1) - event_duration // 2
        end = start + event_duration
        start = max(0, start)
        end = min(n_transactions - 1, end)
        planted.append(PlantedSignal(
            pattern=pat,
            event_id=f"E{i+1}",
            event_name=f"Event_{i+1}",
            event_start=start,
            event_end=end,
            boost_factor=boost,
            baseline_prob=p_base,
        ))

    # --- Type B: unrelated dense patterns ---
    rng = random.Random(seed)
    unrelated = []
    type_b_base_items = [[65, 75], [85, 95], [105, 115], [125, 135]]
    for i in range(n_unrelated):
        pat = type_b_base_items[i % len(type_b_base_items)]
        # Place active periods in gaps between planted-signal event windows
        active_start = rng.randint(0, n_transactions - event_duration - 1)
        active_end = active_start + event_duration
        unrelated.append(UnrelatedDensePattern(
            pattern=pat,
            active_start=active_start,
            active_end=min(active_end, n_transactions - 1),
            boost_factor=boost,
        ))

    # --- Type C: decoy events ---
    decoys = []
    for i in range(n_decoy):
        start = rng.randint(0, n_transactions - event_duration - 1)
        end = start + event_duration
        decoys.append(DecoyEvent(
            event_id=f"D{i+1}",
            event_name=f"Decoy_{i+1}",
            start=start,
            end=min(end, n_transactions - 1),
        ))

    return SyntheticConfig(
        n_transactions=n_transactions,
        n_items=200,
        p_base=p_base,
        planted_signals=planted,
        decoy_events=decoys,
        unrelated_dense_patterns=unrelated,
        seed=seed,
    )


def make_ex1_overlap_config(seed: int = 42) -> SyntheticConfig:
    """EX1-OVERLAP: Two planted events with overlapping time windows.

    E1=[800,1400] and E2=[1200,1800] overlap in [1200,1400].
    Tests temporal disambiguation by proximity component.
    """
    p_base = 0.03
    return SyntheticConfig(
        n_transactions=5000,
        n_items=200,
        p_base=p_base,
        planted_signals=[
            PlantedSignal([5, 15], "E1", "Event_1", 800, 1400,
                          boost_factor=0.3, baseline_prob=p_base),
            PlantedSignal([25, 35], "E2", "Event_2", 1200, 1800,
                          boost_factor=0.3, baseline_prob=p_base),
            PlantedSignal([45, 55], "E3", "Event_3", 3200, 3800,
                          boost_factor=0.3, baseline_prob=p_base),
        ],
        unrelated_dense_patterns=[
            UnrelatedDensePattern([65, 75], 2400, 2700, boost_factor=0.3),
            UnrelatedDensePattern([85, 95], 4200, 4500, boost_factor=0.3),
        ],
        decoy_events=[
            DecoyEvent("D1", "Decoy_1", 2800, 3100),
            DecoyEvent("D2", "Decoy_2", 4600, 4900),
        ],
        seed=seed,
    )


def make_ex1_confound_config(seed: int = 42) -> SyntheticConfig:
    """EX1-CONFOUND: Type B patterns deliberately placed near events.

    Type B active windows overlap with planted event windows, creating
    the hardest discrimination case. The pipeline must use the permutation
    test to reject this spurious temporal correlation.
    """
    p_base = 0.03
    return SyntheticConfig(
        n_transactions=5000,
        n_items=200,
        p_base=p_base,
        planted_signals=[
            PlantedSignal([5, 15], "E1", "Event_1", 1100, 1400,
                          boost_factor=0.3, baseline_prob=p_base),
            PlantedSignal([25, 35], "E2", "Event_2", 2500, 2800,
                          boost_factor=0.3, baseline_prob=p_base),
            PlantedSignal([45, 55], "E3", "Event_3", 3800, 4100,
                          boost_factor=0.3, baseline_prob=p_base),
        ],
        unrelated_dense_patterns=[
            # Deliberately overlap with E1 and E2
            UnrelatedDensePattern([65, 75], 1050, 1450, boost_factor=0.3),
            UnrelatedDensePattern([85, 95], 2450, 2850, boost_factor=0.3),
        ],
        decoy_events=[
            DecoyEvent("D1", "Decoy_1", 600, 900),
            DecoyEvent("D2", "Decoy_2", 4400, 4700),
        ],
        seed=seed,
    )


def make_ex1_dense_config(seed: int = 42) -> SyntheticConfig:
    """EX1-DENSE: High pattern/event count (2x baseline).

    6 planted + 4 Type B + 4 decoys = heavy multiple-testing burden.
    Shorter events (200) to fit more without forced overlap.
    """
    p_base = 0.03
    n = 5000
    dur = 200
    items_a = [[5, 15], [25, 35], [45, 55], [105, 115], [125, 135], [145, 155]]
    spacing = n // (len(items_a) + 1)
    planted = []
    for i, pat in enumerate(items_a):
        start = spacing * (i + 1) - dur // 2
        end = start + dur
        planted.append(PlantedSignal(
            pattern=pat, event_id=f"E{i+1}", event_name=f"Event_{i+1}",
            event_start=max(0, start), event_end=min(n - 1, end),
            boost_factor=0.3, baseline_prob=p_base,
        ))

    rng = random.Random(seed)
    items_b = [[65, 75], [85, 95], [165, 175], [185, 195]]
    unrelated = []
    for i, pat in enumerate(items_b):
        s = rng.randint(0, n - dur - 1)
        unrelated.append(UnrelatedDensePattern(pat, s, s + dur, 0.3))

    decoys = []
    for i in range(4):
        s = rng.randint(0, n - dur - 1)
        decoys.append(DecoyEvent(f"D{i+1}", f"Decoy_{i+1}", s, s + dur))

    return SyntheticConfig(
        n_transactions=n, n_items=200, p_base=p_base,
        planted_signals=planted, decoy_events=decoys,
        unrelated_dense_patterns=unrelated, seed=seed,
    )


def make_ex1_short_config(seed: int = 42) -> SyntheticConfig:
    """EX1-SHORT: Short event duration (80 instead of 300).

    Tests sensitivity to transient signals (flash sales, brief campaigns).
    Different from low β: short events boost strongly but briefly.
    """
    p_base = 0.03
    n = 5000
    dur = 80
    items_a = [[5, 15], [25, 35], [45, 55]]
    spacing = n // (len(items_a) + 1)
    planted = []
    for i, pat in enumerate(items_a):
        start = spacing * (i + 1) - dur // 2
        end = start + dur
        planted.append(PlantedSignal(
            pattern=pat, event_id=f"E{i+1}", event_name=f"Event_{i+1}",
            event_start=max(0, start), event_end=min(n - 1, end),
            boost_factor=0.3, baseline_prob=p_base,
        ))

    rng = random.Random(seed)
    unrelated = [
        UnrelatedDensePattern([65, 75], rng.randint(0, n - dur - 1), 0, 0.3),
        UnrelatedDensePattern([85, 95], rng.randint(0, n - dur - 1), 0, 0.3),
    ]
    for u in unrelated:
        u.active_end = u.active_start + dur

    decoys = []
    for i in range(2):
        s = rng.randint(0, n - dur - 1)
        decoys.append(DecoyEvent(f"D{i+1}", f"Decoy_{i+1}", s, s + dur))

    return SyntheticConfig(
        n_transactions=n, n_items=200, p_base=p_base,
        planted_signals=planted, decoy_events=decoys,
        unrelated_dense_patterns=unrelated, seed=seed,
    )


def _zipf_item_probs(
    n_items: int,
    alpha: float = 1.0,
    median_target: float = 0.03,
    max_prob: float = 0.10,
) -> Dict[int, float]:
    """Compute Zipf-distributed per-item probabilities.

    p(item_k) = C / k^alpha, where C is chosen so that the median item
    (k = n_items // 2) has probability ≈ median_target.
    Probabilities are capped at max_prob to prevent head items from
    dominating co-occurrence patterns unrealistically.
    """
    median_rank = n_items // 2
    C = median_target * (median_rank ** alpha)
    probs = {}
    for k in range(1, n_items + 1):
        p = C / (k ** alpha)
        probs[k] = min(p, max_prob)
    return probs


def make_ex6_zipf_config(
    zipf_alpha: float = 1.0,
    seed: int = 42,
) -> SyntheticConfig:
    """EX6 Zipf: Realistic item-frequency distribution.

    Same signal structure as EX1 baseline (3 Type A + 2 Type B + 2 decoy)
    but with Zipf-distributed base item frequencies instead of uniform p_base.
    Planted signal items are chosen from mid-rank items so they are not
    dominated by head items.
    """
    n_transactions = 5000
    n_items = 200
    event_duration = 300
    boost = 0.3
    median_target = 0.03

    item_probs = _zipf_item_probs(n_items, zipf_alpha, median_target)

    # Type A: same item IDs as EX1 for direct comparison.
    # Under Zipf these items have varying baseline frequencies,
    # creating a more realistic and challenging detection scenario.
    type_a_items = [[5, 15], [25, 35], [45, 55]]
    spacing = n_transactions // (len(type_a_items) + 1)
    planted = []
    for i, pat in enumerate(type_a_items):
        start = spacing * (i + 1) - event_duration // 2
        end = start + event_duration
        start = max(0, start)
        end = min(n_transactions - 1, end)
        planted.append(PlantedSignal(
            pattern=pat,
            event_id=f"E{i+1}",
            event_name=f"Event_{i+1}",
            event_start=start,
            event_end=end,
            boost_factor=boost,
            baseline_prob=median_target,
        ))

    # Type B: 2 unrelated dense patterns (high-rank / rare items)
    rng = random.Random(seed)
    type_b_items = [[150, 160], [170, 180]]
    unrelated = []
    for i, pat in enumerate(type_b_items):
        active_start = rng.randint(0, n_transactions - event_duration - 1)
        active_end = active_start + event_duration
        unrelated.append(UnrelatedDensePattern(
            pattern=pat,
            active_start=active_start,
            active_end=min(active_end, n_transactions - 1),
            boost_factor=boost,
        ))

    # Type C: 2 decoy events
    decoys = []
    for i in range(2):
        start = rng.randint(0, n_transactions - event_duration - 1)
        end = start + event_duration
        decoys.append(DecoyEvent(
            event_id=f"D{i+1}",
            event_name=f"Decoy_{i+1}",
            start=start,
            end=min(end, n_transactions - 1),
        ))

    return SyntheticConfig(
        n_transactions=n_transactions,
        n_items=n_items,
        p_base=median_target,  # fallback (item_probs overrides per-item)
        planted_signals=planted,
        decoy_events=decoys,
        unrelated_dense_patterns=unrelated,
        seed=seed,
        item_probs=item_probs,
    )


def make_ex6_correlated_config(
    zipf_alpha: float = 1.0,
    seed: int = 42,
) -> SyntheticConfig:
    """EX6 Correlated: Zipf frequencies + correlated item pairs.

    Same base as make_ex6_zipf_config but adds 5 correlated item pairs
    (e.g., bread+butter pattern). This tests whether Union-Find deduplication
    handles spurious co-occurrence from item correlation.

    Correlated pairs use head items (high frequency) to maximise the chance
    of creating spurious dense itemsets that must be deduplicated.
    """
    config = make_ex6_zipf_config(zipf_alpha=zipf_alpha, seed=seed)

    # Add correlated pairs among head items (rank 1-30).
    # High correlation probability (0.7) to create strong spurious co-occurrence.
    config.correlated_pairs = [
        (1, 2, 0.7),    # top-2 items strongly correlated
        (3, 4, 0.7),
        (5, 10, 0.6),
        (8, 15, 0.6),
        (12, 20, 0.5),
    ]

    return config


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
