"""
Appendix Experiment: Pattern length robustness (l = 2, 3, 4).

Verifies that the attribution pipeline and deduplication criterion (⌈l/2⌉
majority overlap) function correctly for longer patterns beyond 2-itemsets.
20 seeds × 3 lengths. Results saved for appendix reporting.
"""
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import generate_synthetic, make_ex_pattern_length_config
from experiments.src.run_experiment import AttributionConfig, run_single_experiment

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "ex_pattern_length"
DATA_DIR    = Path(__file__).resolve().parent / "data"    / "ex_pattern_length"
N_SEEDS = 20


def _compute_stats(values):
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0, 0.0, mean, mean
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance)
    se = std / math.sqrt(n)
    t_crit = 2.093  # t_{0.025, df=19}
    ci_lo = max(0.0, mean - t_crit * se)
    ci_hi = min(1.0, mean + t_crit * se)
    return mean, std, se, ci_lo, ci_hi


def run_pattern_length_experiment():
    print("=" * 70)
    print("Appendix: Pattern Length Robustness (l = 2, 3, 4)")
    print(f"  Seeds: {N_SEEDS} per length")
    print("=" * 70)

    all_results = {}

    for length in [2, 3, 4]:
        cond = f"l={length}"
        print(f"\n--- {cond} ---")
        seed_results = []

        for seed in range(N_SEEDS):
            config = make_ex_pattern_length_config(pattern_length=length, seed=seed)
            out_dir = str(DATA_DIR / f"l{length}_seed{seed}")
            info = generate_synthetic(config, out_dir, window_size=1000, min_support=100)

            attr_config = AttributionConfig(
                n_permutations=5000,
                alpha=0.10,
                correction_method="bh",
                global_correction=True,
                deduplicate_overlap=True,
                seed=seed,
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=1000, min_support=100, max_length=length,
                config=attr_config,
                unrelated_path=info.get("unrelated_path"),
            )
            print(f"  seed={seed:2d}: P={result.precision:.2f} R={result.recall:.2f} "
                  f"F1={result.f1:.2f} (TP={result.tp} FP={result.fp} FN={result.fn})")
            seed_results.append(asdict(result))

        f1_vals = [r["f1"] for r in seed_results]
        p_vals  = [r["precision"] for r in seed_results]
        r_vals  = [r["recall"] for r in seed_results]

        avg_f1, std_f1, se_f1, ci_lo, ci_hi = _compute_stats(f1_vals)
        avg_p  = sum(p_vals) / N_SEEDS
        avg_r  = sum(r_vals) / N_SEEDS
        print(f"  Mean: P={avg_p:.2f} R={avg_r:.2f} F1={avg_f1:.2f} "
              f"[95%CI: {ci_lo:.2f}–{ci_hi:.2f}] (std={std_f1:.3f})")

        all_results[cond] = {
            "pattern_length": length,
            "seeds": seed_results,
            "avg_precision": avg_p,
            "avg_recall": avg_r,
            "avg_f1": avg_f1,
            "std_f1": std_f1,
            "se_f1": se_f1,
            "ci95_lower": ci_lo,
            "ci95_upper": ci_hi,
        }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = RESULTS_DIR / "pattern_length_results.json"
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {save_path}")

    print("\n" + "=" * 70)
    print(f"{'Length':<8s} {'Prec':>6s} {'Rec':>6s} {'F1':>6s} {'95%CI':>16s} {'std':>6s}")
    print("-" * 70)
    for cond, data in all_results.items():
        ci = f"[{data['ci95_lower']:.2f}, {data['ci95_upper']:.2f}]"
        print(f"{cond:<8s} {data['avg_precision']:>6.2f} {data['avg_recall']:>6.2f} "
              f"{data['avg_f1']:>6.2f} {ci:>16s} {data['std_f1']:>6.3f}")
    print("=" * 70)
    return all_results


if __name__ == "__main__":
    run_pattern_length_experiment()
