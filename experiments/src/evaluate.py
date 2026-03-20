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

    # Build ground truth set: (pattern_tuple, event_id)
    gt_set: Set[Tuple[Tuple[int, ...], str]] = set()
    for entry in gt_raw:
        pat = _pattern_key(entry["pattern"])
        gt_set.add((pat, entry["event_id"]))

    # Build predicted set
    pred_pairs: List[Tuple[Tuple[int, ...], str]] = []
    for p in predicted:
        if hasattr(p, "pattern"):
            pat = _pattern_key(p.pattern)
            # event_id might be stored via event_name matching
            eid = getattr(p, "event_id", None) or getattr(p, "event_name", "")
        else:
            pat = _pattern_key(p["pattern"])
            eid = p.get("event_id", p.get("event_name", ""))
        pred_pairs.append((pat, eid))

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
        true_positive_pairs=[{"pattern": list(p), "event_id": e} for p, e in tp_set],
        false_positive_pairs=[{"pattern": list(p), "event_id": e} for p, e in fp_set],
        false_negative_pairs=[{"pattern": list(p), "event_id": e} for p, e in fn_set],
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
        converted.append({"pattern": pat, "event_id": eid})

    return evaluate(converted, ground_truth_path)
