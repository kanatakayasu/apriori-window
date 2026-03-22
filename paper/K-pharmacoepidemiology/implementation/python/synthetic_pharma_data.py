"""
Synthetic prescription data generator (MIMIC-IV style).

Generates temporal prescription transaction data with:
- ATC-coded medications
- Configurable regulatory events that alter prescription patterns
- Realistic temporal structure (daily/weekly granularity)
"""

import json
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# ATC Code Catalog (Subset for simulation)
# ---------------------------------------------------------------------------

ATC_CATALOG = {
    # Cardiovascular
    "C03A": "Thiazide diuretics",
    "C07A": "Beta-blockers",
    "C08C": "Calcium channel blockers",
    "C09A": "ACE inhibitors",
    "C09C": "ARBs",
    "C10A": "Statins",
    # Analgesics / Anti-inflammatory
    "M01A": "NSAIDs",
    "N02A": "Opioid analgesics",
    "N02B": "Non-opioid analgesics",
    # Diabetes
    "A10A": "Insulins",
    "A10B": "Oral antidiabetics",
    # Antibiotics
    "J01C": "Beta-lactam penicillins",
    "J01D": "Cephalosporins",
    "J01F": "Macrolides",
    "J01M": "Fluoroquinolones",
    # Proton pump inhibitors
    "A02B": "PPIs",
    # Antidepressants
    "N06A": "Antidepressants",
    # Benzodiazepines
    "N05B": "Anxiolytics (benzodiazepines)",
    # Anticoagulants
    "B01A": "Antithrombotic agents",
}

# Common co-prescription patterns (ATC code tuples)
COMMON_PATTERNS = [
    ("C09A", "C10A"),           # ACE inhibitor + statin
    ("C09A", "C03A"),           # ACE inhibitor + diuretic
    ("C07A", "C10A"),           # Beta-blocker + statin
    ("A10B", "C10A"),           # Oral antidiabetic + statin
    ("M01A", "A02B"),           # NSAID + PPI (gastroprotection)
    ("N02A", "N05B"),           # Opioid + benzodiazepine
    ("J01M", "A02B"),           # Fluoroquinolone + PPI
    ("C09A", "C07A", "C10A"),   # Triple cardiovascular
    ("A10A", "A10B", "C10A"),   # Diabetes triple
]


@dataclass
class RegulatoryEvent:
    """Represents an FDA safety communication or regulatory action."""
    event_id: str
    event_type: str  # safety_alert, boxed_warning, withdrawal, label_change
    timestamp: int   # time index
    description: str
    targeted_atc: List[str]
    effect_magnitude: float = 0.5  # fraction reduction in targeted pattern support


@dataclass
class SyntheticPharmaConfig:
    """Configuration for synthetic prescription data generation."""
    n_transactions: int = 1000
    n_unique_atc: int = 20
    base_pattern_prob: float = 0.15
    single_drug_prob: float = 0.35
    regulatory_events: List[RegulatoryEvent] = field(default_factory=list)
    seed: int = 42
    atc_level: int = 3  # ATC hierarchy level (3 or 4)


def default_regulatory_events(n_transactions: int) -> List[RegulatoryEvent]:
    """Create default regulatory events for simulation."""
    t1 = n_transactions // 3
    t2 = 2 * n_transactions // 3

    return [
        RegulatoryEvent(
            event_id="FDA-2024-001",
            event_type="boxed_warning",
            timestamp=t1,
            description="Boxed warning for concurrent opioid-benzodiazepine use",
            targeted_atc=["N02A", "N05B"],
            effect_magnitude=0.85,
        ),
        RegulatoryEvent(
            event_id="FDA-2024-002",
            event_type="safety_alert",
            timestamp=t2,
            description="Safety alert for fluoroquinolone tendon rupture risk",
            targeted_atc=["J01M"],
            effect_magnitude=0.80,
        ),
    ]


def generate_synthetic_prescriptions(
    config: Optional[SyntheticPharmaConfig] = None,
) -> Tuple[List[List[str]], List[RegulatoryEvent], Dict]:
    """
    Generate synthetic prescription transaction data.

    Returns:
        transactions: List of transactions, each a list of ATC codes
        events: List of regulatory events
        metadata: Generation metadata
    """
    if config is None:
        config = SyntheticPharmaConfig()

    rng = random.Random(config.seed)

    if not config.regulatory_events:
        config.regulatory_events = default_regulatory_events(config.n_transactions)

    # Select ATC codes to use
    all_atc = list(ATC_CATALOG.keys())
    selected_atc = all_atc[: min(config.n_unique_atc, len(all_atc))]

    # Build pattern probability schedule
    # Each pattern has a base probability that can be modified by regulatory events
    pattern_probs = {}
    for pat in COMMON_PATTERNS:
        if all(a in selected_atc for a in pat):
            pattern_probs[pat] = config.base_pattern_prob

    transactions: List[List[str]] = []

    for t in range(config.n_transactions):
        drugs_in_transaction: set = set()

        # Add individual drugs
        for atc in selected_atc:
            if rng.random() < config.single_drug_prob:
                drugs_in_transaction.add(atc)

        # Add co-prescription patterns
        for pat, base_prob in pattern_probs.items():
            prob = base_prob

            # Apply regulatory event effects
            for event in config.regulatory_events:
                if t >= event.timestamp:
                    # Check if pattern overlaps with targeted drugs
                    overlap = set(pat) & set(event.targeted_atc)
                    if overlap:
                        prob *= (1.0 - event.effect_magnitude)

            if rng.random() < prob:
                for atc in pat:
                    drugs_in_transaction.add(atc)

        # Ensure non-empty transactions
        if not drugs_in_transaction:
            drugs_in_transaction.add(rng.choice(selected_atc))

        transactions.append(sorted(drugs_in_transaction))

    metadata = {
        "n_transactions": config.n_transactions,
        "n_unique_atc": len(selected_atc),
        "selected_atc": selected_atc,
        "n_patterns": len(pattern_probs),
        "n_events": len(config.regulatory_events),
        "seed": config.seed,
    }

    return transactions, config.regulatory_events, metadata


def save_transactions(
    transactions: List[List[str]],
    output_path: str,
    format: str = "basket",
) -> None:
    """
    Save transactions to file.

    Args:
        transactions: List of transaction item lists
        output_path: Output file path
        format: 'basket' for space-separated items per line,
                'json' for JSON array
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if format == "basket":
        with open(path, "w", encoding="utf-8") as f:
            for txn in transactions:
                f.write(" ".join(txn) + "\n")
    elif format == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(transactions, f, indent=2)
    else:
        raise ValueError(f"Unknown format: {format}")


def save_events(events: List[RegulatoryEvent], output_path: str) -> None:
    """Save regulatory events to JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(e) for e in events], f, indent=2)


if __name__ == "__main__":
    config = SyntheticPharmaConfig(n_transactions=1000, seed=42)
    transactions, events, metadata = generate_synthetic_prescriptions(config)
    print(f"Generated {len(transactions)} transactions")
    print(f"Unique ATC codes: {metadata['n_unique_atc']}")
    print(f"Regulatory events: {len(events)}")
    for e in events:
        print(f"  - {e.event_id} at t={e.timestamp}: {e.description}")
