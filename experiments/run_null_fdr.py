"""
Null Experiment: FDR Validation — Does the BH procedure control false discoveries
when no event causes any pattern change?

Design:
  - 5000 transactions, 200 items, p_base=0.03 (same as EX1)
  - 5 random events (decoy only, no planted signals)
  - Pipeline runs with α=0.10, BH correction, B=5000 permutations
  - Under null: all significant attributions are false positives
  - Repeat across 20 seeds

Expected outcome: empirical FDR ≤ α across seeds.
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import generate_synthetic, make_null_config
from experiments.src.run_experiment import AttributionConfig, run_single_experiment

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "null_fdr"
DATA_DIR = Path(__file__).resolve().parent / "data" / "null_fdr"
N_SEEDS = 20


def run_null_fdr():
    """Run null FDR validation experiment."""
    print("=" * 70)
    print("Null Experiment: FDR Validation")
    print(f"  Seeds: {N_SEEDS}")
    print("  No planted signals — all significant attributions are false positives")
    print("=" * 70)

    seed_results = []

    for seed in range(N_SEEDS):
        config = make_null_config(n_events=5, seed=seed)
        out_dir = str(DATA_DIR / f"seed{seed}")
        info = generate_synthetic(config, out_dir)

        attr_config = AttributionConfig(
            min_support_range=5,
            n_permutations=5000,
            alpha=0.10,
            correction_method="bh",
            global_correction=True,
            deduplicate_overlap=True,
            seed=seed,
        )
        result = run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=50, min_support=3, max_length=2,
            config=attr_config,
        )

        # Under null: ground truth is empty, so TP=0, FP=n_significant, FN=0
        n_sig = result.n_significant
        print(f"  seed={seed}: n_patterns={result.n_patterns}, "
              f"n_significant={n_sig}, FP={result.fp}")

        seed_results.append({
            "seed": seed,
            "n_patterns": result.n_patterns,
            "n_significant": n_sig,
            "fp": result.fp,
        })

    # Summary
    avg_sig = sum(r["n_significant"] for r in seed_results) / len(seed_results)
    max_sig = max(r["n_significant"] for r in seed_results)
    n_zero = sum(1 for r in seed_results if r["n_significant"] == 0)
    avg_patterns = sum(r["n_patterns"] for r in seed_results) / len(seed_results)

    summary = {
        "n_seeds": N_SEEDS,
        "alpha": 0.10,
        "avg_n_patterns": avg_patterns,
        "avg_n_significant": avg_sig,
        "max_n_significant": max_sig,
        "n_seeds_zero_significant": n_zero,
        "seeds": seed_results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = str(RESULTS_DIR / "null_fdr_results.json")
    with open(save_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'=' * 70}")
    print(f"Null FDR Summary (α=0.10):")
    print(f"  Average patterns tested: {avg_patterns:.1f}")
    print(f"  Average significant: {avg_sig:.2f}")
    print(f"  Max significant: {max_sig}")
    print(f"  Seeds with 0 significant: {n_zero}/{N_SEEDS}")
    print(f"{'=' * 70}")
    print(f"Results saved to {save_path}")

    return summary


if __name__ == "__main__":
    run_null_fdr()
