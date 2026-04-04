"""
Evaluation metrics for Event Attribution experiments.

Computes Precision, Recall, F1 against known ground truth.
"""
import json
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple


@dataclass
class EvalResult:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    true_positive_pairs: List[Dict]
    false_positive_pairs: List[Dict]
    false_negative_pairs: List[Dict]


def _pattern_key(pattern) -> Tuple[int, ...]:
    """Normalize pattern to sorted tuple for comparison."""
    if isinstance(pattern, (list, tuple)):
        return tuple(sorted(int(x) for x in pattern))
    return pattern


def evaluate(
    predicted: List[Dict],
    ground_truth_path: str,
) -> EvalResult:
    """
    Evaluate attribution results against ground truth.

    Args:
        predicted: List of SignificantAttribution-like dicts with 'pattern' and 'event_name'
                   or objects with those attributes.
        ground_truth_path: Path to ground truth JSON with [{"pattern": [...], "event_id": "..."}]

    Returns:
        EvalResult with precision/recall/F1 and detail lists.
    """
    with open(ground_truth_path, "r") as f:
        gt_raw = json.load(f)

    # Build ground truth set: (pattern_tuple, interval_start, interval_end, event_id)
    gt_set: Set[Tuple[Tuple[int, ...], int, int, str]] = set()
    for entry in gt_raw:
        pat = _pattern_key(entry["pattern"])
        iv_s = entry.get("interval_start", 0)
        iv_e = entry.get("interval_end", 0)
        gt_set.add((pat, iv_s, iv_e, entry["event_id"]))

    # Build predicted set
    pred_pairs: List[Tuple[Tuple[int, ...], int, int, str]] = []
    for p in predicted:
        if hasattr(p, "pattern"):
            pat = _pattern_key(p.pattern)
            eid = getattr(p, "event_id", None) or getattr(p, "event_name", "")
            iv_s = getattr(p, "interval_start", 0)
            iv_e = getattr(p, "interval_end", 0)
        else:
            pat = _pattern_key(p["pattern"])
            eid = p.get("event_id", p.get("event_name", ""))
            iv_s = p.get("interval_start", 0)
            iv_e = p.get("interval_end", 0)
        pred_pairs.append((pat, iv_s, iv_e, eid))

    pred_set = set(pred_pairs)

    tp_set = gt_set & pred_set
    fp_set = pred_set - gt_set
    fn_set = gt_set - pred_set

    tp = len(tp_set)
    fp = len(fp_set)
    fn = len(fn_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return EvalResult(
        tp=tp, fp=fp, fn=fn,
        precision=precision, recall=recall, f1=f1,
        true_positive_pairs=[{"pattern": list(p), "interval_start": iv_s, "interval_end": iv_e, "event_id": e} for p, iv_s, iv_e, e in tp_set],
        false_positive_pairs=[{"pattern": list(p), "interval_start": iv_s, "interval_end": iv_e, "event_id": e} for p, iv_s, iv_e, e in fp_set],
        false_negative_pairs=[{"pattern": list(p), "interval_start": iv_s, "interval_end": iv_e, "event_id": e} for p, iv_s, iv_e, e in fn_set],
    )


def evaluate_with_event_name_mapping(
    predicted: List,
    ground_truth_path: str,
    events_path: str,
) -> EvalResult:
    """
    Evaluate when predicted results use event_name instead of event_id.

    Loads events.json to build name→id mapping.
    """
    with open(events_path, "r") as f:
        events = json.load(f)

    name_to_id = {e["name"]: e["event_id"] for e in events}

    # Convert predicted to use event_id
    converted = []
    for p in predicted:
        if hasattr(p, "pattern"):
            pat = list(p.pattern)
            name = p.event_name
        else:
            pat = p["pattern"]
            name = p.get("event_name", "")

        eid = name_to_id.get(name, name)
        iv_s = getattr(p, "interval_start", 0) if hasattr(p, "interval_start") else p.get("interval_start", 0)
        iv_e = getattr(p, "interval_end", 0) if hasattr(p, "interval_end") else p.get("interval_end", 0)
        converted.append({"pattern": pat, "event_id": eid, "interval_start": iv_s, "interval_end": iv_e})

    return evaluate(converted, ground_truth_path)


@dataclass
class FalseAttributionResult:
    """Result of false attribution rate evaluation for Type B (unrelated) patterns."""
    n_unrelated_patterns: int
    n_falsely_attributed: int
    false_attribution_rate: float
    falsely_attributed_details: List[Dict]


def evaluate_false_attribution_rate(
    predicted: List,
    unrelated_path: str,
    events_path: str,
) -> FalseAttributionResult:
    """
    Evaluate how many unrelated (Type B) patterns are falsely attributed.

    For each predicted significant attribution, checks if its pattern matches
    any known unrelated pattern. A match means the pipeline incorrectly
    attributed a pattern that has no true causal link to the event.

    Args:
        predicted: List of SignificantAttribution-like dicts/objects with
                   'pattern' and 'event_name' (or 'event_id').
        unrelated_path: Path to unrelated_patterns.json
                        (list of dicts with "pattern" key).
        events_path: Path to events.json for name→id mapping.

    Returns:
        FalseAttributionResult with false attribution rate and details.
    """
    with open(unrelated_path, "r") as f:
        unrelated_raw = json.load(f)

    with open(events_path, "r") as f:
        events = json.load(f)

    name_to_id = {e["name"]: e["event_id"] for e in events}

    # Build set of unrelated pattern keys
    unrelated_set: Set[Tuple[int, ...]] = set()
    for entry in unrelated_raw:
        unrelated_set.add(_pattern_key(entry["pattern"]))

    n_unrelated = len(unrelated_set)

    # Check each prediction against unrelated patterns
    falsely_attributed: List[Dict] = []
    seen: Set[Tuple[Tuple[int, ...], str]] = set()
    for p in predicted:
        if hasattr(p, "pattern"):
            pat = _pattern_key(p.pattern)
            name = getattr(p, "event_name", "")
            eid = getattr(p, "event_id", None) or name_to_id.get(name, name)
        else:
            pat = _pattern_key(p["pattern"])
            name = p.get("event_name", "")
            eid = p.get("event_id", name_to_id.get(name, name))

        if pat in unrelated_set:
            key = (pat, eid)
            if key not in seen:
                seen.add(key)
                falsely_attributed.append({
                    "pattern": list(pat),
                    "event_id": eid,
                    "event_name": name,
                })

    n_falsely = len({pat for pat, _ in seen})  # unique patterns falsely attributed
    rate = n_falsely / max(1, n_unrelated)

    return FalseAttributionResult(
        n_unrelated_patterns=n_unrelated,
        n_falsely_attributed=n_falsely,
        false_attribution_rate=rate,
        falsely_attributed_details=falsely_attributed,
    )
