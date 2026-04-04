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


def generate_synthetic(config: SyntheticConfig, out_dir: str, window_size: int = 1000, min_support: int = 5) -> Dict:
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

    # Run Phase 1 to determine exact ground truth intervals (P, I*, E)
    import sys as _sys
    from pathlib import Path as _Path
    _python_dir = str(_Path(__file__).resolve().parent.parent.parent / "apriori_window_suite" / "python")
    if _python_dir not in _sys.path:
        _sys.path.insert(0, _python_dir)
    from apriori_window_basket import find_dense_itemsets

    # max_length = longest planted pattern (all experiments use 2-item patterns)
    _max_gt_len = max((len(sig.pattern) for sig in config.planted_signals), default=2)
    frequents = find_dense_itemsets(transactions, window_size, min_support, _max_gt_len)

    # Build ground truth: (P, I*, E) triples where I* overlaps with event window.
    # For each (pattern, event_id) pair, keep only the LONGEST overlapping interval
    # (most representative; avoids micro-intervals from weak/noisy signals).
    best_intervals: Dict[tuple, Dict] = {}  # key = (pat_tuple, event_id)
    for sig in config.planted_signals:
        pat_key = tuple(sorted(sig.pattern))
        if pat_key in frequents:
            for (iv_start, iv_end) in frequents[pat_key]:
                if iv_start <= sig.event_end and iv_end >= sig.event_start:
                    key = (pat_key, sig.event_id)
                    length = iv_end - iv_start
                    if key not in best_intervals or length > best_intervals[key]["_len"]:
                        best_intervals[key] = {
                            "pattern": sorted(sig.pattern),
                            "interval_start": iv_start,
                            "interval_end": iv_end,
                            "event_id": sig.event_id,
                            "_len": length,
                        }
    ground_truth = [
        {k: v for k, v in entry.items() if k != "_len"}
        for entry in best_intervals.values()
    ]

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
    n_transactions: int = 100_000,
    boost: float = 0.3,
    n_unrelated: int = 2,
    n_decoy: int = 2,
    seed: int = 42,
) -> SyntheticConfig:
    """Create config with all 3 signal types for experiment 1.

    Type A (vocabulary-internal boost): Planted signals of mixed pattern lengths
        (L=2×3, L=3×1, L=4×1) using base-vocabulary items that have baseline
        presence (p_base prob) outside event windows and boosted co-occurrence
        during event windows.
    Type B (unrelated dense): Patterns that become dense during specific
        periods but are NOT associated with any event.
    Type C (decoy events): Events that exist but cause no pattern changes.
    """
    p_base = 0.03
    event_duration = 6_000

    # --- Type A: 3 L=2 (in-vocab) + 1 L=3 + 1 L=4 (out-of-vocab) planted signals ---
    # L=3,4 items are beyond n_items=200 → zero background probability,
    # preventing sub-pattern interference during non-event periods.
    type_a_patterns = [
        ([5, 15], p_base),              # L=2, in-vocab
        ([25, 35], p_base),             # L=2, in-vocab
        ([45, 55], p_base),             # L=2, in-vocab
        ([201, 202, 203], 0.0),         # L=3, out-of-vocab, zero baseline
        ([205, 206, 207, 208], 0.0),    # L=4, out-of-vocab, zero baseline
    ]
    spacing = n_transactions // (len(type_a_patterns) + 1)
    planted = []
    for i, (pat, baseline) in enumerate(type_a_patterns):
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
            baseline_prob=baseline,
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

    E1=[16000,28000] and E2=[24000,36000] overlap in [24000,28000].
    Tests temporal disambiguation by proximity component.
    """
    p_base = 0.03
    return SyntheticConfig(
        n_transactions=100_000,
        n_items=200,
        p_base=p_base,
        planted_signals=[
            PlantedSignal([5, 15], "E1", "Event_1", 16_000, 28_000,
                          boost_factor=0.3, baseline_prob=p_base),
            PlantedSignal([25, 35], "E2", "Event_2", 24_000, 36_000,
                          boost_factor=0.3, baseline_prob=p_base),
            PlantedSignal([45, 55], "E3", "Event_3", 64_000, 76_000,
                          boost_factor=0.3, baseline_prob=p_base),
        ],
        unrelated_dense_patterns=[
            UnrelatedDensePattern([65, 75], 48_000, 54_000, boost_factor=0.3),
            UnrelatedDensePattern([85, 95], 84_000, 90_000, boost_factor=0.3),
        ],
        decoy_events=[
            DecoyEvent("D1", "Decoy_1", 56_000, 62_000),
            DecoyEvent("D2", "Decoy_2", 92_000, 98_000),
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
        n_transactions=100_000,
        n_items=200,
        p_base=p_base,
        planted_signals=[
            PlantedSignal([5, 15], "E1", "Event_1", 22_000, 28_000,
                          boost_factor=0.3, baseline_prob=p_base),
            PlantedSignal([25, 35], "E2", "Event_2", 50_000, 56_000,
                          boost_factor=0.3, baseline_prob=p_base),
            PlantedSignal([45, 55], "E3", "Event_3", 76_000, 82_000,
                          boost_factor=0.3, baseline_prob=p_base),
        ],
        unrelated_dense_patterns=[
            # Deliberately overlap with E1 and E2
            UnrelatedDensePattern([65, 75], 21_000, 29_000, boost_factor=0.3),
            UnrelatedDensePattern([85, 95], 49_000, 57_000, boost_factor=0.3),
        ],
        decoy_events=[
            DecoyEvent("D1", "Decoy_1", 12_000, 18_000),
            DecoyEvent("D2", "Decoy_2", 88_000, 94_000),
        ],
        seed=seed,
    )


def make_ex1_dense_config(seed: int = 42) -> SyntheticConfig:
    """EX1-DENSE: High pattern/event count (2x baseline).

    6 planted + 4 Type B + 4 decoys = heavy multiple-testing burden.
    Shorter events (200) to fit more without forced overlap.
    """
    p_base = 0.03
    n = 100_000
    dur = 4_000
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
    n = 100_000
    dur = 1_600
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
    n_transactions = 100_000
    n_items = 200
    event_duration = 6_000
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


def make_null_config(
    n_transactions: int = 100_000,
    n_events: int = 5,
    event_duration: int = 6_000,
    seed: int = 42,
) -> SyntheticConfig:
    """Null experiment: NO planted signals, only random decoy events.

    Under the null hypothesis, no event causes any pattern change.
    All significant attributions are false positives.
    Used to validate that BH FDR control keeps false discovery rate ≤ α.
    """
    rng = random.Random(seed)
    decoys = []
    for i in range(n_events):
        start = rng.randint(0, n_transactions - event_duration - 1)
        end = start + event_duration
        decoys.append(DecoyEvent(
            event_id=f"D{i+1}",
            event_name=f"NullEvent_{i+1}",
            start=start,
            end=min(end, n_transactions - 1),
        ))

    return SyntheticConfig(
        n_transactions=n_transactions,
        n_items=200,
        p_base=0.03,
        planted_signals=[],       # NO planted signals
        decoy_events=decoys,
        unrelated_dense_patterns=[],  # No Type B either — pure null
        seed=seed,
    )


def make_ex_pattern_length_config(
    pattern_length: int = 2,
    n_transactions: int = 100_000,
    boost: float = 0.3,
    seed: int = 42,
) -> SyntheticConfig:
    """Appendix experiment: vary planted pattern length l ∈ {2, 3, 4}.

    Tests whether the deduplication criterion (⌈l/2⌉ majority overlap) and
    attribution pipeline function correctly beyond 2-itemset patterns.

    Design:
    - 3 planted signals of length `pattern_length`, boost-only (baseline_prob=0).
      Items use IDs above n_items (201+) so they have ZERO base probability.
      This ensures 2-item subsets of l>=3 planted patterns do NOT have higher
      baseline support than the full planted pattern (no spurious dedup preference).
      boost_factor=0.3 → in-event support per window ≈ W*0.3=300 >> θ=100.
    - 2 Type B unrelated dense patterns (l=2), also using IDs above n_items.
      Active windows placed in gaps (≥ 8K from any event window).
    - 2 decoy events in non-overlapping gaps.
    - event_duration=6000, N=100K, W=1000, θ=100 (same as EX1 baseline).
    """
    p_base = 0.03
    event_duration = 6_000
    n_base_items = 200  # items 1..200 have p_base; planted items use IDs > 200

    # Planted signal items: IDs 201+ (above base range → zero base probability)
    # Each signal uses `pattern_length` consecutive IDs with a gap to the next.
    n_planted = 3
    planted = []
    # Event positions: 22000-28000, 47000-53000, 72000-78000 (well-separated)
    event_positions = [
        (22_000, 28_000),
        (47_000, 53_000),
        (72_000, 78_000),
    ]
    for i in range(n_planted):
        base_id = 201 + i * (pattern_length + 2)  # gap of 2 between signal item ranges
        pattern = list(range(base_id, base_id + pattern_length))
        ev_start, ev_end = event_positions[i]
        planted.append(PlantedSignal(
            pattern=pattern,
            event_id=f"E{i+1}",
            event_name=f"Event_{i+1}",
            event_start=ev_start,
            event_end=ev_end,
            boost_factor=boost,
            baseline_prob=0,  # IDs above n_base_items → no base occurrence
        ))

    # Type B: l=2, using IDs above n_base_items, placed in gaps BETWEEN events.
    type_b_slots = [
        (7_000,  13_000),   # gap before E1 (E1 starts at 22K)
        (35_000, 41_000),   # gap between E1-end(28K) and E2-start(47K)
    ]
    unrelated = []
    for i, (ts, te) in enumerate(type_b_slots):
        pat = [251 + i * 10, 261 + i * 10]
        unrelated.append(UnrelatedDensePattern(
            pattern=pat,
            active_start=ts,
            active_end=te,
            boost_factor=boost,
        ))

    # Type C: 2 decoy events, also in safe gap positions
    decoy_slots = [(58_000, 64_000), (86_000, 92_000)]
    decoys = []
    for i, (ds, de) in enumerate(decoy_slots):
        decoys.append(DecoyEvent(f"D{i+1}", f"Decoy_{i+1}", ds, de))

    return SyntheticConfig(
        n_transactions=n_transactions,
        n_items=n_base_items,
        p_base=p_base,
        planted_signals=planted,
        decoy_events=decoys,
        unrelated_dense_patterns=unrelated,
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
