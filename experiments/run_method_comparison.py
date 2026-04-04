"""
EX3: Method Comparison Experiment.

Compare 7 methods that replace Steps 1-3-4 of the proposed pipeline.
All methods share Phase 1 (Apriori-window), amplitude filter, BH correction,
and Union-Find deduplication (Step 5).

Methods:
  1. Proposed (change point proximity + permutation test)
  2. Wilcoxon rank-sum test (distribution comparison)
  3. CausalImpact (counterfactual model)
  4. ITS (segmented regression)
  5. Event Study (abnormal support)
  6. EP/Contrast (support rate comparison)
  7. ECA (change point-event coincidence) — uses proposed Step 1
"""
import json
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import (
    generate_synthetic,
    make_ex6_zipf_config,
    make_ex1_confound_config,
    make_ex1_dense_config,
    make_ex1_overlap_config,
    make_ex1_short_config,
    _zipf_item_probs,
)
from experiments.src.run_experiment import (
    AttributionConfig,
    run_single_experiment,
)
from experiments.src.evaluate import (
    evaluate_false_attribution_rate,
    evaluate_with_event_name_mapping,
)
from experiments.src.wilcoxon_baseline import run_wilcoxon_baseline
from experiments.src.causalimpact_baseline import run_causalimpact_baseline
from experiments.src.method_baselines import (
    run_its_baseline,
    run_event_study_baseline,
    run_eca_baseline,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "method_comparison"
DATA_DIR = Path(__file__).resolve().parent / "data" / "method_comparison"
N_SEEDS = 10

COMMON_PARAMS = dict(
    window_size=1000, min_support=5, max_length=2,
    alpha=0.10, deduplicate=True,
)


def _eval_baseline(results, gt_path, events_path, unrelated_path=None):
    """Evaluate baseline results (any object with .pattern and .event_name)."""
    predicted = [{"pattern": list(r.pattern), "event_name": r.event_name}
                 for r in results]
    eval_result = evaluate_with_event_name_mapping(predicted, gt_path, events_path)
    far = 0.0
    if unrelated_path and Path(unrelated_path).exists():
        fa = evaluate_false_attribution_rate(predicted, unrelated_path, events_path)
        far = fa.false_attribution_rate
    return {
        "precision": eval_result.precision, "recall": eval_result.recall,
        "f1": eval_result.f1, "far": far, "n_pred": len(results),
    }


def _run_all_methods(info, seed):
    """Run all 7 methods on one dataset, return dict of results."""
    results = {}

    # 1. Proposed
    attr_config = AttributionConfig(
        n_permutations=5000, alpha=0.10,
        correction_method="bh", global_correction=True,
        deduplicate_overlap=True, seed=seed,
        magnitude_normalization="sqrt",
    )
    r = run_single_experiment(
        info["txn_path"], info["events_path"], info["gt_path"],
        window_size=1000, min_support=5, max_length=2,
        config=attr_config, unrelated_path=info.get("unrelated_path"),
    )
    results["Proposed"] = {
        "precision": r.precision, "recall": r.recall,
        "f1": r.f1, "far": r.false_attribution_rate, "n_pred": r.n_significant,
    }

    # 2-6: Baselines that replace Steps 1-3-4
    baseline_fns = {
        "Wilcoxon": run_wilcoxon_baseline,
        "CausalImpact": run_causalimpact_baseline,
        "ITS": run_its_baseline,
        "EventStudy": run_event_study_baseline,
    }
    for name, fn in baseline_fns.items():
        bl_results = fn(info["txn_path"], info["events_path"], **COMMON_PARAMS)
        results[name] = _eval_baseline(
            bl_results, info["gt_path"],
            info["events_path"], info.get("unrelated_path"),
        )

    # 7. ECA (uses proposed Step 1, replaces Steps 3-4)
    eca_results = run_eca_baseline(info["txn_path"], info["events_path"], **COMMON_PARAMS)
    results["ECA"] = _eval_baseline(
        eca_results, info["gt_path"],
        info["events_path"], info.get("unrelated_path"),
    )

    return results


METHOD_ORDER = ["Proposed", "Wilcoxon", "CausalImpact", "ITS", "EventStudy", "ECA"]


def run_comparison():
    """Run comparison on default + structural conditions."""
    print("=" * 90)
    print("EX3: Method Comparison — 7 Methods")
    print("=" * 90)

    conditions = {}

    # Default condition (beta=0.3)
    conditions["β=0.3"] = lambda seed: make_ex6_zipf_config(zipf_alpha=1.0, seed=seed)

    # Structural conditions
    struct_fns = {
        "OVERLAP": make_ex1_overlap_config,
        "CONFOUND": make_ex1_confound_config,
        "DENSE": make_ex1_dense_config,
        "SHORT": make_ex1_short_config,
    }

    all_results = {}

    for cond_name, config_fn in [("β=0.3", conditions["β=0.3"])] + list(struct_fns.items()):
        print(f"\n--- {cond_name} ---")
        method_seeds = {m: [] for m in METHOD_ORDER}

        for seed in range(N_SEEDS):
            if cond_name == "β=0.3":
                synth_config = config_fn(seed)
            else:
                synth_config = config_fn(seed=seed)
                synth_config.item_probs = _zipf_item_probs(
                    synth_config.n_items, alpha=1.0, median_target=0.03
                )

            out_dir = str(DATA_DIR / f"{cond_name.lower().replace('=','')}_seed{seed}")
            info = generate_synthetic(synth_config, out_dir, window_size=1000, min_support=5)

            seed_results = _run_all_methods(info, seed)

            for method in METHOD_ORDER:
                method_seeds[method].append(seed_results[method])

            # Print per-seed
            for method in METHOD_ORDER:
                r = seed_results[method]
                print(f"  seed={seed} {method:<14s} P={r['precision']:.2f} R={r['recall']:.2f} "
                      f"F1={r['f1']:.2f} FAR={r['far']:.2f} #={r['n_pred']}")

        # Print averages
        print(f"\n  {'Method':<14s} {'P':>6s} {'R':>6s} {'F1':>6s} {'FAR':>6s}")
        print("  " + "-" * 40)
        for method in METHOD_ORDER:
            seeds = method_seeds[method]
            avg = {k: sum(s[k] for s in seeds) / len(seeds)
                   for k in ["precision", "recall", "f1", "far"]}
            print(f"  {method:<14s} {avg['precision']:>6.2f} {avg['recall']:>6.2f} "
                  f"{avg['f1']:>6.2f} {avg['far']:>6.2f}")

        all_results[cond_name] = {m: method_seeds[m] for m in METHOD_ORDER}

    return all_results


def main():
    t0 = time.time()
    results = run_comparison()
    elapsed = time.time() - t0

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "method_comparison_results.json")
    with open(save_path, "w") as f:
        json.dump({"results": results, "elapsed_seconds": elapsed}, f, indent=2)

    print(f"\nTotal time: {elapsed:.0f}s")
    print(f"Results saved to: {save_path}")


if __name__ == "__main__":
    main()
