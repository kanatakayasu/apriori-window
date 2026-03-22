"""
Generate figures for Paper D experiments.
"""

import json
import sys
from pathlib import Path

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = Path(__file__).parent / "figures"
MANUSCRIPT_FIG_DIR = Path(__file__).parent.parent / "manuscript" / "fig"
FIGURES_DIR.mkdir(exist_ok=True)
MANUSCRIPT_FIG_DIR.mkdir(exist_ok=True)


def load_results():
    with open(RESULTS_DIR / "all_results.json") as f:
        return json.load(f)


def fig_e1_recovery(results):
    """E1: Effect recovery accuracy."""
    e1 = results["e1"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    ax1.plot(e1["effect_sizes"], e1["recovered"], "o-", label="Recovered", color="steelblue")
    ax1.plot(e1["effect_sizes"], e1["effect_sizes"], "--", label="True", color="gray", alpha=0.7)
    ax1.set_xlabel("True Effect Size")
    ax1.set_ylabel("Recovered Effect Size")
    ax1.set_title("(a) Effect Recovery")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(e1["effect_sizes"], e1["errors"], "s-", color="coral")
    ax2.set_xlabel("True Effect Size")
    ax2.set_ylabel("Absolute Error")
    ax2.set_title("(b) Estimation Error")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    for d in [FIGURES_DIR, MANUSCRIPT_FIG_DIR]:
        fig.savefig(d / "e1_recovery.pdf", bbox_inches="tight")
        fig.savefig(d / "e1_recovery.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved e1_recovery")


def fig_e2_donors(results):
    """E2: Donor pool size sensitivity."""
    e2 = results["e2"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    ax1.plot(e2["n_donors"], e2["mean_error"], "o-", color="steelblue")
    ax1.set_xlabel("Number of Donors")
    ax1.set_ylabel("Mean Absolute Error")
    ax1.set_title("(a) Estimation Error vs Donors")
    ax1.grid(True, alpha=0.3)

    ax2.plot(e2["n_donors"], e2["mean_p"], "s-", color="coral")
    ax2.axhline(y=0.05, linestyle="--", color="gray", alpha=0.5, label=r"$\alpha=0.05$")
    ax2.set_xlabel("Number of Donors")
    ax2.set_ylabel("Mean p-value")
    ax2.set_title("(b) p-value vs Donors")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    for d in [FIGURES_DIR, MANUSCRIPT_FIG_DIR]:
        fig.savefig(d / "e2_donors.pdf", bbox_inches="tight")
        fig.savefig(d / "e2_donors.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved e2_donors")


def fig_e3_fpr(results):
    """E3: False positive rate."""
    e3 = results["e3"]
    fig, ax = plt.subplots(figsize=(6, 4))

    alphas = e3["alpha_levels"]
    rates = e3["rejection_rates"]

    ax.bar(range(len(alphas)), rates, tick_label=[f"{a}" for a in alphas],
           color="steelblue", alpha=0.8)
    # Expected line
    for i, a in enumerate(alphas):
        ax.plot([i - 0.4, i + 0.4], [a, a], "--", color="coral", linewidth=2)

    ax.set_xlabel(r"Significance Level $\alpha$")
    ax.set_ylabel("Rejection Rate")
    ax.set_title("False Positive Rate (Null Hypothesis True)")
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    for d in [FIGURES_DIR, MANUSCRIPT_FIG_DIR]:
        fig.savefig(d / "e3_fpr.pdf", bbox_inches="tight")
        fig.savefig(d / "e3_fpr.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved e3_fpr")


def fig_e5_comparison(results):
    """E5: SCM vs Permutation power comparison."""
    e5 = results["e5"]
    fig, ax = plt.subplots(figsize=(6, 4))

    methods = ["SCM (Ours)", "Permutation"]
    powers = [e5["scm_power"], e5["perm_power"]]
    colors = ["steelblue", "coral"]

    ax.bar(methods, powers, color=colors, alpha=0.8)
    ax.set_ylabel("Detection Power")
    ax.set_title("SCM vs Permutation Test (Effect=0.2)")
    ax.set_ylim(0, 1.1)
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    for d in [FIGURES_DIR, MANUSCRIPT_FIG_DIR]:
        fig.savefig(d / "e5_comparison.pdf", bbox_inches="tight")
        fig.savefig(d / "e5_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved e5_comparison")


def main():
    if not HAS_MPL:
        print("matplotlib not available, skipping figure generation")
        return

    results = load_results()
    print("Generating figures...")
    fig_e1_recovery(results)
    fig_e2_donors(results)
    fig_e3_fpr(results)
    fig_e5_comparison(results)
    print("Done!")


if __name__ == "__main__":
    main()
