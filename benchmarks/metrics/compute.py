"""Metric computation for benchmark evaluation."""
from typing import Set, Tuple, List


def compute_spr(
    predicted: Set[frozenset],
    ground_truth: Set[frozenset],
) -> Tuple[float, float, float]:
    """Compute precision, recall, F1 for set pattern recovery."""
    if not ground_truth:
        return (1.0, 1.0, 1.0) if not predicted else (0.0, 1.0, 0.0)
    tp = len(predicted & ground_truth)
    fp = len(predicted - ground_truth)
    fn = len(ground_truth - predicted)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)
    return precision, recall, f1
