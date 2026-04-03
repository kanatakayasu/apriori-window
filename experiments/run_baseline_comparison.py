"""
Baseline comparison experiment for reviewer response.

A1: Wilcoxon+BH baseline vs Proposed pipeline
    - EX1 conditions (β sensitivity + structural conditions)
    - Same data, same Phase 1, same deduplication
    - Compare P/R/F1/FAR

A2: Random baseline for EX3 coupon consistency
    - Dunnhumby data: expected coupon consistency rate under random attribution
"""
import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from experiments.src.gen_synthetic import (
    generate_synthetic,
    make_ex1_confound_config,
    make_ex1_config,
    make_ex1_dense_config,
    make_ex1_overlap_config,
    make_ex1_short_config,
    make_ex6_zipf_config,
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
from experiments.src.wilcoxon_baseline import run_wilcoxon_baseline, WilcoxonResult
from experiments.src.causalimpact_baseline import run_causalimpact_baseline, CausalImpactResult

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "baseline_comparison"
DATA_DIR = Path(__file__).resolve().parent / "data" / "baseline_comparison"
N_SEEDS = 5


def _eval_baseline(
    baseline_results: list,
    gt_path: str,
    events_path: str,
    unrelated_path: str = None,
):
    """Evaluate baseline results using the same metrics.

    Works for both WilcoxonResult and CausalImpactResult (any object with
    .pattern and .event_name attributes).
    """
    predicted = [{"pattern": list(r.pattern), "event_name": r.event_name}
                 for r in baseline_results]
    eval_result = evaluate_with_event_name_mapping(predicted, gt_path, events_path)

    far = 0.0
    n_falsely = 0
    if unrelated_path and Path(unrelated_path).exists():
        fa = evaluate_false_attribution_rate(predicted, unrelated_path, events_path)
        far = fa.false_attribution_rate
        n_falsely = fa.n_falsely_attributed

    return {
        "precision": eval_result.precision,
        "recall": eval_result.recall,
        "f1": eval_result.f1,
        "tp": eval_result.tp,
        "fp": eval_result.fp,
        "fn": eval_result.fn,
        "n_significant": len(baseline_results),
        "false_attribution_rate": far,
        "n_falsely_attributed": n_falsely,
    }


# Keep backward-compatible alias
_eval_wilcoxon = _eval_baseline


def run_a1_beta_sensitivity():
    """A1: Compare Proposed vs Wilcoxon on β sensitivity (EX1a conditions)."""
    print("=" * 80)
    print("A1: β Sensitivity — Proposed vs Wilcoxon+BH vs CausalImpact Baseline")
    print("=" * 80)

    betas = [0.2, 0.3, 0.5]
    all_results = {}

    for beta in betas:
        print(f"\n--- β = {beta} ---")
        proposed_seeds = []
        wilcoxon_seeds = []
        ci_seeds = []

        for seed in range(N_SEEDS):
            # Generate Zipf data (same as EX1)
            synth_config = make_ex6_zipf_config(zipf_alpha=1.0, seed=seed)
            # Override boost factor
            for sig in synth_config.planted_signals:
                sig.boost_factor = beta
            for udp in synth_config.unrelated_dense_patterns:
                udp.boost_factor = beta

            out_dir = str(DATA_DIR / f"beta{beta}_seed{seed}")
            info = generate_synthetic(synth_config, out_dir)

            # --- Proposed pipeline ---
            attr_config = AttributionConfig(
                min_support_range=10, n_permutations=5000, alpha=0.10,
                correction_method="bh", global_correction=True,
                deduplicate_overlap=True, seed=seed,
                magnitude_normalization="sqrt",
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=5, max_length=100,
                config=attr_config,
                unrelated_path=info.get("unrelated_path"),
            )
            proposed_seeds.append({
                "precision": result.precision, "recall": result.recall,
                "f1": result.f1, "far": result.false_attribution_rate,
                "n_pred": result.n_significant,
            })

            # --- Wilcoxon baseline ---
            wilcoxon_results = run_wilcoxon_baseline(
                info["txn_path"], info["events_path"],
                window_size=50, min_support=5, max_length=100,
                alpha=0.10, min_support_range=10, deduplicate=True,
            )
            w_eval = _eval_baseline(
                wilcoxon_results, info["gt_path"],
                info["events_path"], info.get("unrelated_path"),
            )
            wilcoxon_seeds.append({
                "precision": w_eval["precision"], "recall": w_eval["recall"],
                "f1": w_eval["f1"], "far": w_eval["false_attribution_rate"],
                "n_pred": w_eval["n_significant"],
            })

            # --- CausalImpact baseline ---
            ci_results = run_causalimpact_baseline(
                info["txn_path"], info["events_path"],
                window_size=50, min_support=5, max_length=100,
                alpha=0.10, min_support_range=10, deduplicate=True,
            )
            ci_eval = _eval_baseline(
                ci_results, info["gt_path"],
                info["events_path"], info.get("unrelated_path"),
            )
            ci_seeds.append({
                "precision": ci_eval["precision"], "recall": ci_eval["recall"],
                "f1": ci_eval["f1"], "far": ci_eval["false_attribution_rate"],
                "n_pred": ci_eval["n_significant"],
            })

            print(f"  seed={seed}: Proposed   P={result.precision:.2f} R={result.recall:.2f} "
                  f"F1={result.f1:.2f} FAR={result.false_attribution_rate:.2f} #={result.n_significant}")
            print(f"           Wilcoxon   P={w_eval['precision']:.2f} R={w_eval['recall']:.2f} "
                  f"F1={w_eval['f1']:.2f} FAR={w_eval['false_attribution_rate']:.2f} #={w_eval['n_significant']}")
            print(f"           CausalImp  P={ci_eval['precision']:.2f} R={ci_eval['recall']:.2f} "
                  f"F1={ci_eval['f1']:.2f} FAR={ci_eval['false_attribution_rate']:.2f} #={ci_eval['n_significant']}")

        # Averages
        for name, seeds in [("Proposed", proposed_seeds), ("Wilcoxon", wilcoxon_seeds), ("CausalImp", ci_seeds)]:
            avg = {k: sum(s[k] for s in seeds) / len(seeds)
                   for k in ["precision", "recall", "f1", "far"]}
            print(f"  {name} AVG: P={avg['precision']:.2f} R={avg['recall']:.2f} "
                  f"F1={avg['f1']:.2f} FAR={avg['far']:.2f}")

        all_results[f"beta_{beta}"] = {
            "proposed": proposed_seeds,
            "wilcoxon": wilcoxon_seeds,
            "causalimpact": ci_seeds,
        }

    return all_results


def run_a1_structural():
    """A1: Compare Proposed vs Wilcoxon on structural conditions (EX1b)."""
    print("\n" + "=" * 80)
    print("A1: Structural Conditions — Proposed vs Wilcoxon+BH vs CausalImpact")
    print("=" * 80)

    conditions = {
        "OVERLAP": make_ex1_overlap_config,
        "CONFOUND": make_ex1_confound_config,
        "DENSE": make_ex1_dense_config,
        "SHORT": make_ex1_short_config,
    }

    all_results = {}

    for cond_name, config_fn in conditions.items():
        print(f"\n--- {cond_name} ---")
        proposed_seeds = []
        wilcoxon_seeds = []
        ci_seeds = []

        for seed in range(N_SEEDS):
            synth_config = config_fn(seed=seed)
            # Add Zipf distribution
            synth_config.item_probs = _zipf_item_probs(
                synth_config.n_items, alpha=1.0, median_target=0.03
            )

            out_dir = str(DATA_DIR / f"{cond_name.lower()}_seed{seed}")
            info = generate_synthetic(synth_config, out_dir)

            # --- Proposed pipeline ---
            attr_config = AttributionConfig(
                min_support_range=10, n_permutations=5000, alpha=0.10,
                correction_method="bh", global_correction=True,
                deduplicate_overlap=True, seed=seed,
                magnitude_normalization="sqrt",
            )
            result = run_single_experiment(
                info["txn_path"], info["events_path"], info["gt_path"],
                window_size=50, min_support=5, max_length=100,
                config=attr_config,
                unrelated_path=info.get("unrelated_path"),
            )
            proposed_seeds.append({
                "precision": result.precision, "recall": result.recall,
                "f1": result.f1, "far": result.false_attribution_rate,
                "n_pred": result.n_significant,
            })

            # --- Wilcoxon baseline ---
            wilcoxon_results = run_wilcoxon_baseline(
                info["txn_path"], info["events_path"],
                window_size=50, min_support=5, max_length=100,
                alpha=0.10, min_support_range=10, deduplicate=True,
            )
            w_eval = _eval_baseline(
                wilcoxon_results, info["gt_path"],
                info["events_path"], info.get("unrelated_path"),
            )
            wilcoxon_seeds.append({
                "precision": w_eval["precision"], "recall": w_eval["recall"],
                "f1": w_eval["f1"], "far": w_eval["false_attribution_rate"],
                "n_pred": w_eval["n_significant"],
            })

            # --- CausalImpact baseline ---
            ci_results = run_causalimpact_baseline(
                info["txn_path"], info["events_path"],
                window_size=50, min_support=5, max_length=100,
                alpha=0.10, min_support_range=10, deduplicate=True,
            )
            ci_eval = _eval_baseline(
                ci_results, info["gt_path"],
                info["events_path"], info.get("unrelated_path"),
            )
            ci_seeds.append({
                "precision": ci_eval["precision"], "recall": ci_eval["recall"],
                "f1": ci_eval["f1"], "far": ci_eval["false_attribution_rate"],
                "n_pred": ci_eval["n_significant"],
            })

            print(f"  seed={seed}: Proposed   P={result.precision:.2f} R={result.recall:.2f} "
                  f"F1={result.f1:.2f} FAR={result.false_attribution_rate:.2f}")
            print(f"           Wilcoxon   P={w_eval['precision']:.2f} R={w_eval['recall']:.2f} "
                  f"F1={w_eval['f1']:.2f} FAR={w_eval['false_attribution_rate']:.2f}")
            print(f"           CausalImp  P={ci_eval['precision']:.2f} R={ci_eval['recall']:.2f} "
                  f"F1={ci_eval['f1']:.2f} FAR={ci_eval['false_attribution_rate']:.2f}")

        for name, seeds in [("Proposed", proposed_seeds), ("Wilcoxon", wilcoxon_seeds), ("CausalImp", ci_seeds)]:
            avg = {k: sum(s[k] for s in seeds) / len(seeds)
                   for k in ["precision", "recall", "f1", "far"]}
            print(f"  {name} AVG: P={avg['precision']:.2f} R={avg['recall']:.2f} "
                  f"F1={avg['f1']:.2f} FAR={avg['far']:.2f}")

        all_results[cond_name] = {
            "proposed": proposed_seeds,
            "wilcoxon": wilcoxon_seeds,
            "causalimpact": ci_seeds,
        }

    return all_results


def run_a2_random_baseline():
    """A2: Random baseline for Dunnhumby coupon consistency.

    Compute expected coupon consistency rate if pattern-event pairs
    were assigned randomly.
    """
    print("\n" + "=" * 80)
    print("A2: Random Baseline for Coupon Consistency (Dunnhumby)")
    print("=" * 80)

    dunnhumby_dir = Path(_root) / "dataset" / "dunnhumby" / "raw"
    coupon_path = dunnhumby_dir / "coupon.csv"
    campaign_desc_path = dunnhumby_dir / "campaign_desc.csv"

    if not coupon_path.exists():
        print(f"  [SKIP] Dunnhumby data not found at {dunnhumby_dir}")
        return None

    import csv
    import random

    # Load coupon data: campaign → set of product IDs
    campaign_products = defaultdict(set)
    with open(coupon_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            campaign_products[row["CAMPAIGN"]].add(int(row["PRODUCT_ID"]))

    # Load campaign descriptions for type classification
    campaign_types = {}
    if campaign_desc_path.exists():
        with open(campaign_desc_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                campaign_types[row["CAMPAIGN"]] = row.get("DESCRIPTION", "")

    # Classify campaigns into TypeA/B/C based on coupon count
    type_a_campaigns = set()  # Large-scale: > 3000 coupon products
    type_b_campaigns = set()  # Targeted: 200-2000
    type_c_campaigns = set()  # Niche: < 200 or 200-1500

    for camp, products in campaign_products.items():
        n = len(products)
        if n >= 3000:
            type_a_campaigns.add(camp)
        elif n >= 200:
            type_b_campaigns.add(camp)
        else:
            type_c_campaigns.add(camp)

    # Collect all unique product IDs in the dataset
    all_products = set()
    for products in campaign_products.values():
        all_products |= products

    # Read actual EX3 results if available
    ex3_results_path = Path(_root) / "experiments" / "results"
    # We'll compute the random baseline analytically

    print(f"\n  Campaigns: {len(campaign_products)} total")
    print(f"  TypeA (large): {len(type_a_campaigns)} campaigns")
    print(f"  TypeB (targeted): {len(type_b_campaigns)} campaigns")
    print(f"  TypeC (niche): {len(type_c_campaigns)} campaigns")
    print(f"  Total unique coupon products: {len(all_products)}")

    # Analytical random baseline:
    # If a pattern (a, b) is randomly attributed to campaign c,
    # the probability that at least one item matches a coupon product is:
    # P(match) = 1 - P(neither matches) = 1 - ((N-|C_c|)/N * (N-|C_c|-1)/(N-1))
    # where N = total products in dataset, |C_c| = coupon products for campaign c
    #
    # But we need the product space. Let's use the actual product IDs from
    # the transaction data.

    # Load transaction data to get the actual product universe
    txn_path = dunnhumby_dir / "transactions.txt"
    product_universe = set()
    if txn_path.exists():
        with open(txn_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    for item in line.split():
                        product_universe.add(int(item))

    if not product_universe:
        # Fallback: use products from coupon data
        # Load from original dunnhumby transaction_data.csv
        td_path = dunnhumby_dir / "transaction_data.csv"
        if td_path.exists():
            with open(td_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    product_universe.add(int(row["PRODUCT_ID"]))

    N = len(product_universe) if product_universe else 92339  # fallback from paper

    print(f"  Product universe size: {N}")

    # Compute expected random consistency rate per campaign type
    print(f"\n  {'Type':<10s} {'Campaigns':<12s} {'Avg Coupon Prods':<20s} {'P(random match)':<18s}")
    print("  " + "-" * 60)

    type_map = {
        "TypeA": type_a_campaigns,
        "TypeB": type_b_campaigns,
        "TypeC": type_c_campaigns,
    }

    random_rates = {}
    for type_name, camps in type_map.items():
        if not camps:
            continue
        probs = []
        sizes = []
        for camp in camps:
            c = len(campaign_products[camp])
            sizes.append(c)
            # P(at least 1 of 2 random items is in coupon set)
            # = 1 - P(both not in coupon set)
            # = 1 - comb(N-c, 2) / comb(N, 2)
            if N > 1 and c < N:
                p_none = ((N - c) / N) * ((N - c - 1) / (N - 1))
                p_match = 1.0 - p_none
            else:
                p_match = 1.0
            probs.append(p_match)

        avg_size = sum(sizes) / len(sizes)
        avg_prob = sum(probs) / len(probs)
        random_rates[type_name] = avg_prob
        print(f"  {type_name:<10s} {len(camps):<12d} {avg_size:<20.0f} {avg_prob:<18.4f}")

    # Monte Carlo verification
    print(f"\n  Monte Carlo verification (10000 random pairs):")
    rng = random.Random(42)
    product_list = sorted(product_universe) if product_universe else list(range(1, N + 1))

    for type_name, camps in type_map.items():
        if not camps:
            continue
        n_trials = 10000
        n_match = 0
        camp_list = sorted(camps)
        for _ in range(n_trials):
            camp = rng.choice(camp_list)
            coupon_set = campaign_products[camp]
            a = rng.choice(product_list)
            b = rng.choice(product_list)
            if a in coupon_set or b in coupon_set:
                n_match += 1
        empirical_rate = n_match / n_trials
        print(f"  {type_name}: {empirical_rate:.4f} (analytical: {random_rates.get(type_name, 0):.4f})")

    return random_rates


def main():
    t0 = time.time()

    # A1: β sensitivity
    beta_results = run_a1_beta_sensitivity()

    # A1: structural conditions
    struct_results = run_a1_structural()

    # A2: random baseline
    random_rates = run_a2_random_baseline()

    elapsed = time.time() - t0

    # Save all results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_results = {
        "a1_beta": beta_results,
        "a1_structural": struct_results,
        "a2_random_rates": random_rates,
        "elapsed_seconds": elapsed,
    }
    save_path = str(RESULTS_DIR / "baseline_comparison_results.json")
    with open(save_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Summary table
    print("\n" + "=" * 80)
    print("SUMMARY: Proposed vs Wilcoxon+BH vs CausalImpact Baseline")
    print("=" * 80)
    print(f"{'Condition':<14s} {'Method':<12s} {'P':>6s} {'R':>6s} {'F1':>6s} {'FAR':>6s}")
    print("-" * 56)

    for section, results in [("β sensitivity", beta_results), ("Structural", struct_results)]:
        if not results:
            continue
        for cond, data in results.items():
            for method_name, method_key in [("Proposed", "proposed"), ("Wilcoxon", "wilcoxon"), ("CausalImp", "causalimpact")]:
                seeds = data[method_key]
                avg_p = sum(s["precision"] for s in seeds) / len(seeds)
                avg_r = sum(s["recall"] for s in seeds) / len(seeds)
                avg_f1 = sum(s["f1"] for s in seeds) / len(seeds)
                avg_far = sum(s["far"] for s in seeds) / len(seeds)
                print(f"{cond:<14s} {method_name:<12s} {avg_p:>6.2f} {avg_r:>6.2f} "
                      f"{avg_f1:>6.2f} {avg_far:>6.2f}")
            print("-" * 56)

    print(f"\nTotal time: {elapsed:.0f}s")
    print(f"Results saved to: {save_path}")


if __name__ == "__main__":
    main()
