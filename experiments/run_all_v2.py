"""
V2 Experiment Suite: Normalization-aware experiment design.

EX1: Normalization method selection (none/sqrt/full × uniform/Zipf)
EX2: Core attribution accuracy (optimal norm per data type)
EX3: Ablation analysis (score components + pipeline steps)
EX4: Dunnhumby real data (sqrt)

Outputs: experiments/results/v2/
"""
import json
import sys
import time
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import (
    generate_synthetic,
    make_ex1_config,
    make_ex1_overlap_config,
    make_ex1_confound_config,
    make_ex1_dense_config,
    make_ex1_short_config,
    make_ex6_zipf_config,
    make_ex6_correlated_config,
    DecoyEvent,
    PlantedSignal,
    SyntheticConfig,
    UnrelatedDensePattern,
)
from experiments.src.run_experiment import (
    AttributionConfig,
    run_single_experiment,
    run_naive_experiment,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "v2"
DATA_DIR = Path(__file__).resolve().parent / "data" / "v2"
N_SEEDS = 5


def make_attr_config(seed, norm="none", **overrides):
    """Attribution config with specified normalization."""
    cfg = dict(
        min_support_range=5,
        n_permutations=5000,
        alpha=0.10,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=seed,
        magnitude_normalization=norm,
    )
    cfg.update(overrides)
    return AttributionConfig(**cfg)


def avg_metrics(seed_results):
    n = len(seed_results)
    return {
        "avg_precision": sum(r["precision"] for r in seed_results) / n,
        "avg_recall": sum(r["recall"] for r in seed_results) / n,
        "avg_f1": sum(r["f1"] for r in seed_results) / n,
        "avg_far": sum(r["false_attribution_rate"] for r in seed_results) / n,
    }


def run_condition(cond_name, config_fn, attr_config_fn, window=50, minsup=3):
    seed_results = []
    for seed in range(N_SEEDS):
        config = config_fn(seed)
        out_dir = str(DATA_DIR / f"{cond_name}_seed{seed}")
        info = generate_synthetic(config, out_dir)
        attr_config = attr_config_fn(seed)
        result = run_single_experiment(
            info["txn_path"], info["events_path"], info["gt_path"],
            window_size=window, min_support=minsup, max_length=100,
            config=attr_config,
            unrelated_path=info.get("unrelated_path"),
        )
        seed_results.append(asdict(result))
    avg = avg_metrics(seed_results)
    print(f"  {cond_name}: P={avg['avg_precision']:.2f} R={avg['avg_recall']:.2f} "
          f"F1={avg['avg_f1']:.2f} FAR={avg['avg_far']:.2f}")
    return {"seeds": seed_results, **avg}


# =====================================================================
# EX1: Normalization Method Selection
# =====================================================================
def run_ex1():
    print("\n" + "=" * 60)
    print("EX1: Normalization Method Selection")
    print("=" * 60)

    NORMS = ["none", "sqrt", "full"]
    CONDITIONS = {
        "uniform": {
            "config_fn": lambda seed: make_ex1_config(boost=0.3, seed=seed),
            "minsup": 3,
        },
        "zipf_1.0": {
            "config_fn": lambda seed: make_ex6_zipf_config(zipf_alpha=1.0, seed=seed),
            "minsup": 5,
        },
        "zipf_1.5": {
            "config_fn": lambda seed: make_ex6_zipf_config(zipf_alpha=1.5, seed=seed),
            "minsup": 5,
        },
        "correlated": {
            "config_fn": lambda seed: make_ex6_correlated_config(seed=seed),
            "minsup": 5,
        },
    }

    results = {}
    for cond_name, cond_cfg in CONDITIONS.items():
        cond_results = {}
        for norm in NORMS:
            cond_results[norm] = run_condition(
                f"ex1_{cond_name}_{norm}",
                cond_cfg["config_fn"],
                lambda seed, n=norm: make_attr_config(seed, norm=n),
                minsup=cond_cfg["minsup"],
            )
        results[cond_name] = cond_results
    return results


# =====================================================================
# EX2a: Beta sweep (uniform → none)
# =====================================================================
def run_ex2a():
    print("\n" + "=" * 60)
    print("EX2a: Beta Sweep (uniform → none)")
    print("=" * 60)
    results = {}
    for beta in [0.1, 0.2, 0.3, 0.5]:
        results[f"beta_{beta}"] = run_condition(
            f"ex2a_beta{beta}",
            lambda seed, b=beta: make_ex1_config(boost=b, seed=seed),
            lambda seed: make_attr_config(seed, norm="none"),
        )
    return results


# =====================================================================
# EX2b: Structural conditions (uniform → none)
# =====================================================================
def run_ex2b():
    print("\n" + "=" * 60)
    print("EX2b: Structural Conditions (uniform → none)")
    print("=" * 60)
    CONDITIONS = {
        "OVERLAP":  make_ex1_overlap_config,
        "CONFOUND": make_ex1_confound_config,
        "DENSE":    make_ex1_dense_config,
        "SHORT":    make_ex1_short_config,
    }
    results = {}
    for name, fn in CONDITIONS.items():
        results[name] = run_condition(
            f"ex2b_{name}",
            lambda seed, f=fn: f(seed=seed),
            lambda seed: make_attr_config(seed, norm="none"),
        )
    return results


# =====================================================================
# EX2c: Zipf distributions (Zipf → sqrt)
# =====================================================================
def run_ex2c():
    print("\n" + "=" * 60)
    print("EX2c: Zipf Distributions (Zipf → sqrt)")
    print("=" * 60)
    CONDITIONS = {
        "zipf_1.0": lambda seed: make_ex6_zipf_config(zipf_alpha=1.0, seed=seed),
        "zipf_1.5": lambda seed: make_ex6_zipf_config(zipf_alpha=1.5, seed=seed),
        "correlated": lambda seed: make_ex6_correlated_config(seed=seed),
    }
    results = {}
    for name, fn in CONDITIONS.items():
        results[name] = run_condition(
            f"ex2c_{name}",
            fn,
            lambda seed: make_attr_config(seed, norm="sqrt"),
            minsup=5,
        )
    return results


# =====================================================================
# EX3a: Score component ablation (uniform → none)
# =====================================================================
def run_ex3a():
    print("\n" + "=" * 60)
    print("EX3a: Score Component Ablation (uniform → none)")
    print("=" * 60)

    ABLATION_MODES = OrderedDict([
        ("Full", None),
        ("mag_only", "no_prox"),
        ("prox_only", "no_mag"),
    ])

    def _make_scenario_a(seed):
        return SyntheticConfig(
            n_transactions=5000, n_items=200, p_base=0.03,
            planted_signals=[
                PlantedSignal([5, 15], "E1", "Sale", 750, 1250,
                              boost_factor=0.4, baseline_prob=0.03),
            ],
            unrelated_dense_patterns=[
                UnrelatedDensePattern([5, 15], 3000, 3400, boost_factor=0.4),
            ],
            decoy_events=[], seed=seed,
        )

    def _make_scenario_b(seed):
        return SyntheticConfig(
            n_transactions=5000, n_items=200, p_base=0.03,
            planted_signals=[
                PlantedSignal([5, 15], "E1", "BigSale", 800, 1200,
                              boost_factor=0.5, baseline_prob=0.03),
                PlantedSignal([5, 15], "E2", "SmallPromo", 2500, 2900,
                              boost_factor=0.1, baseline_prob=0.03),
            ],
            unrelated_dense_patterns=[], decoy_events=[], seed=seed,
        )

    SCENARIOS = {"A_prox_required": _make_scenario_a, "B_mag_required": _make_scenario_b}
    results = {}

    for sc_name, sc_fn in SCENARIOS.items():
        sc_results = {}
        for abl_name, abl_mode in ABLATION_MODES.items():
            seed_results = []
            for seed in range(N_SEEDS):
                config = sc_fn(seed)
                out_dir = str(DATA_DIR / f"ex3a_{sc_name}_{abl_name}_seed{seed}")
                info = generate_synthetic(config, out_dir)
                attr_config = make_attr_config(seed, norm="none", ablation_mode=abl_mode)
                result = run_single_experiment(
                    info["txn_path"], info["events_path"], info["gt_path"],
                    window_size=50, min_support=3, max_length=100,
                    config=attr_config,
                    unrelated_path=info.get("unrelated_path"),
                )
                seed_results.append(asdict(result))
            avg = avg_metrics(seed_results)
            print(f"  {sc_name} / {abl_name}: F1={avg['avg_f1']:.2f}")
            sc_results[abl_name] = {"seeds": seed_results, **avg}
        results[sc_name] = sc_results
    return results


# =====================================================================
# EX3b: Pipeline step ablation (uniform → none)
# =====================================================================
def run_ex3b():
    print("\n" + "=" * 60)
    print("EX3b: Pipeline Step Ablation (uniform → none)")
    print("=" * 60)

    CONDITIONS = {
        "beta_0.3": lambda seed: make_ex1_config(boost=0.3, seed=seed),
        "CONFOUND": lambda seed: make_ex1_confound_config(seed=seed),
        "DENSE":    lambda seed: make_ex1_dense_config(seed=seed),
    }

    METHODS = OrderedDict([
        ("Naive", dict(naive=True)),
        ("+PermTest", dict(naive=False, global_correction=False, deduplicate_overlap=False)),
        ("+BH", dict(naive=False, global_correction=True, deduplicate_overlap=False)),
        ("Full", dict(naive=False, global_correction=True, deduplicate_overlap=True)),
    ])

    results = {}
    for cond_name, config_fn in CONDITIONS.items():
        cond_results = {}
        for method_name, method_cfg in METHODS.items():
            seed_results = []
            for seed in range(N_SEEDS):
                config = config_fn(seed)
                out_dir = str(DATA_DIR / f"ex3b_{cond_name}_seed{seed}")
                info = generate_synthetic(config, out_dir)

                if method_cfg.get("naive"):
                    attr_config = AttributionConfig(
                        min_support_range=5, seed=seed,
                        magnitude_normalization="none",
                    )
                    result = run_naive_experiment(
                        info["txn_path"], info["events_path"], info["gt_path"],
                        window_size=50, min_support=3, max_length=100,
                        config=attr_config,
                        unrelated_path=info.get("unrelated_path"),
                    )
                else:
                    attr_config = make_attr_config(
                        seed, norm="none",
                        global_correction=method_cfg["global_correction"],
                        deduplicate_overlap=method_cfg["deduplicate_overlap"],
                    )
                    result = run_single_experiment(
                        info["txn_path"], info["events_path"], info["gt_path"],
                        window_size=50, min_support=3, max_length=100,
                        config=attr_config,
                        unrelated_path=info.get("unrelated_path"),
                    )
                seed_results.append(asdict(result))

            avg = avg_metrics(seed_results)
            avg["avg_n_pred"] = sum(r["n_significant"] for r in seed_results) / N_SEEDS
            print(f"  {cond_name} / {method_name}: P={avg['avg_precision']:.2f} "
                  f"R={avg['avg_recall']:.2f} F1={avg['avg_f1']:.2f} "
                  f"FAR={avg['avg_far']:.2f} #pred={avg['avg_n_pred']:.0f}")
            cond_results[method_name] = {"seeds": seed_results, **avg}
        results[cond_name] = cond_results
    return results


# =====================================================================
# Main
# =====================================================================
if __name__ == "__main__":
    all_results = {}

    all_results["ex1"] = run_ex1()
    all_results["ex2a"] = run_ex2a()
    all_results["ex2b"] = run_ex2b()
    all_results["ex2c"] = run_ex2c()
    all_results["ex3a"] = run_ex3a()
    all_results["ex3b"] = run_ex3b()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(str(RESULTS_DIR / "all_v2_results.json"), "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Final summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)

    print("\n--- EX1: Normalization Selection ---")
    for cond, cond_data in all_results["ex1"].items():
        for norm, v in cond_data.items():
            print(f"  {cond}/{norm}: P={v['avg_precision']:.2f} R={v['avg_recall']:.2f} "
                  f"F1={v['avg_f1']:.2f} FAR={v['avg_far']:.2f}")

    print("\n--- EX2a: Beta Sweep (none) ---")
    for k, v in all_results["ex2a"].items():
        print(f"  {k}: P={v['avg_precision']:.2f} R={v['avg_recall']:.2f} "
              f"F1={v['avg_f1']:.2f} FAR={v['avg_far']:.2f}")

    print("\n--- EX2b: Structural (none) ---")
    for k, v in all_results["ex2b"].items():
        print(f"  {k}: P={v['avg_precision']:.2f} R={v['avg_recall']:.2f} "
              f"F1={v['avg_f1']:.2f} FAR={v['avg_far']:.2f}")

    print("\n--- EX2c: Zipf (sqrt) ---")
    for k, v in all_results["ex2c"].items():
        print(f"  {k}: P={v['avg_precision']:.2f} R={v['avg_recall']:.2f} "
              f"F1={v['avg_f1']:.2f} FAR={v['avg_far']:.2f}")

    print("\n--- EX3a: Score Ablation (none) ---")
    for sc, sc_data in all_results["ex3a"].items():
        for abl, v in sc_data.items():
            print(f"  {sc}/{abl}: F1={v['avg_f1']:.2f}")

    print("\n--- EX3b: Pipeline Steps (none) ---")
    for cond, cond_data in all_results["ex3b"].items():
        for meth, v in cond_data.items():
            print(f"  {cond}/{meth}: P={v['avg_precision']:.2f} R={v['avg_recall']:.2f} "
                  f"F1={v['avg_f1']:.2f} FAR={v['avg_far']:.2f} #={v.get('avg_n_pred', '?'):.0f}")

    print("\nDone. Results saved to", RESULTS_DIR / "all_v2_results.json")
