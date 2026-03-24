"""
Experiment runner for Event Attribution Pipeline.

Orchestrates Phase 1 → support series → attribution pipeline → evaluation.
"""
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
_python_dir = str(Path(_project_root) / "apriori_window_suite" / "python")
_original_dir = str(Path(_project_root) / "apriori_window_original" / "python")
for p in [_project_root, _python_dir, _original_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from apriori_window import (
    compute_item_timestamps_map,
    find_dense_itemsets,
    read_text_file_as_2d_vec_of_integers,
)
from event_attribution import (
    AttributionConfig,
    read_events,
    run_attribution_pipeline_v2,
)
from experiments.src.evaluate import evaluate_false_attribution_rate, evaluate_with_event_name_mapping


@dataclass
class ExperimentResult:
    config: Dict[str, Any]
    n_transactions: int
    n_patterns: int
    n_change_points_total: int
    n_significant: int
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    time_phase1_ms: float
    time_support_series_ms: float
    time_attribution_ms: float
    time_total_ms: float
    significant_attributions: List[Dict]
    true_positive_pairs: List[Dict]
    false_positive_pairs: List[Dict]
    false_negative_pairs: List[Dict]
    false_attribution_rate: float = 0.0
    n_falsely_attributed: int = 0


def run_single_experiment(
    txn_path: str,
    events_path: str,
    gt_path: str,
    window_size: int = 50,
    min_support: int = 5,
    max_length: int = 3,
    config: Optional[AttributionConfig] = None,
    unrelated_path: Optional[str] = None,
) -> ExperimentResult:
    """Run a single experiment and return results with evaluation."""
    if config is None:
        config = AttributionConfig()

    params = {
        "window_size": window_size,
        "min_support": min_support,
        "max_length": max_length,
        "change_method": config.change_method,
        "sigma": config.sigma,
        "max_distance": config.max_distance,
        "min_magnitude": config.min_magnitude,
        "min_relative_change": config.min_relative_change,
        "global_correction": config.global_correction,
        "n_permutations": config.n_permutations,
        "alpha": config.alpha,
        "seed": config.seed,
    }

    # Phase 1
    t0 = time.perf_counter()
    transactions = read_text_file_as_2d_vec_of_integers(txn_path)
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)
    t1 = time.perf_counter()

    # Events
    events = read_events(events_path)

    # Attribution pipeline (v2: dense intervals directly, no full support series)
    results = run_attribution_pipeline_v2(
        frequents, item_transaction_map, events,
        window_size, min_support, len(transactions), config,
    )
    t2 = time.perf_counter()

    # Evaluation
    eval_result = evaluate_with_event_name_mapping(results, gt_path, events_path)

    # Count patterns with len > 1
    n_patterns = sum(1 for k in frequents if len(k) > 1)

    # Serialize significant attributions
    sig_dicts = []
    for r in results:
        sig_dicts.append({
            "pattern": list(r.pattern),
            "change_time": r.change_time,
            "change_direction": r.change_direction,
            "change_magnitude": r.change_magnitude,
            "event_name": r.event_name,
            "event_start": r.event_start,
            "event_end": r.event_end,
            "proximity": r.proximity,
            "attribution_score": r.attribution_score,
            "p_value": r.p_value,
            "adjusted_p_value": r.adjusted_p_value,
        })

    # False attribution rate (Type B unrelated patterns)
    far = 0.0
    n_falsely = 0
    if unrelated_path is not None and Path(unrelated_path).exists():
        fa_result = evaluate_false_attribution_rate(results, unrelated_path, events_path)
        far = fa_result.false_attribution_rate
        n_falsely = fa_result.n_falsely_attributed

    return ExperimentResult(
        config=params,
        n_transactions=len(transactions),
        n_patterns=n_patterns,
        n_change_points_total=0,  # Could count if needed
        n_significant=len(results),
        precision=eval_result.precision,
        recall=eval_result.recall,
        f1=eval_result.f1,
        tp=eval_result.tp,
        fp=eval_result.fp,
        fn=eval_result.fn,
        time_phase1_ms=(t1 - t0) * 1000,
        time_support_series_ms=0.0,  # v2: no separate support series step
        time_attribution_ms=(t2 - t1) * 1000,
        time_total_ms=(t2 - t0) * 1000,
        significant_attributions=sig_dicts,
        true_positive_pairs=eval_result.true_positive_pairs,
        false_positive_pairs=eval_result.false_positive_pairs,
        false_negative_pairs=eval_result.false_negative_pairs,
        false_attribution_rate=far,
        n_falsely_attributed=n_falsely,
    )


def save_result(result: ExperimentResult, path: str):
    """Save experiment result to JSON."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(asdict(result), f, indent=2, default=str)
