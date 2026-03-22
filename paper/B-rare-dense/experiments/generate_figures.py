"""Generate figures for Paper B experiments."""

import json
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("matplotlib not available, generating text-based summaries instead")

results_dir = Path(__file__).parent / "results"
fig_dir = Path(__file__).parent / "figures"
fig_dir.mkdir(exist_ok=True)


def load_json(name):
    with open(results_dir / name) as f:
        return json.load(f)


def fig_e1():
    """E1: Recovery rate bar chart."""
    data = load_json("e1_recovery.json")
    if not HAS_MPL:
        return
    seeds = [r["seed"] for r in data["results"]]
    rdp_rec = [r["rdp_recovery"] * 100 for r in data["results"]]
    aw_rec = [r["aw_recovery"] * 100 for r in data["results"]]
    rdp_total = [r["rdp_total_patterns"] for r in data["results"]]
    aw_total = [r["aw_total_patterns"] for r in data["results"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    x = range(len(seeds))
    w = 0.35
    ax1.bar([i - w/2 for i in x], rdp_rec, w, label="RDP (Ours)", color="#2196F3")
    ax1.bar([i + w/2 for i in x], aw_rec, w, label="Apriori-Window", color="#FF9800")
    ax1.set_xlabel("Seed")
    ax1.set_ylabel("Recovery Rate (%)")
    ax1.set_title("(a) Ground Truth Recovery")
    ax1.set_xticks(x)
    ax1.set_xticklabels(seeds)
    ax1.set_ylim(0, 110)
    ax1.legend()

    ax2.bar([i - w/2 for i in x], rdp_total, w, label="RDP (Ours)", color="#2196F3")
    ax2.bar([i + w/2 for i in x], aw_total, w, label="Apriori-Window", color="#FF9800")
    ax2.set_xlabel("Seed")
    ax2.set_ylabel("Total Multi-item Patterns")
    ax2.set_title("(b) Output Size")
    ax2.set_xticks(x)
    ax2.set_xticklabels(seeds)
    ax2.legend()

    plt.tight_layout()
    plt.savefig(fig_dir / "e1_recovery.pdf", bbox_inches="tight")
    plt.savefig(fig_dir / "e1_recovery.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved e1_recovery.pdf/png")


def fig_e2():
    """E2: Pruning efficiency."""
    data = load_json("e2_pruning.json")
    if not HAS_MPL:
        return

    seeds = [r["seed"] for r in data["results"]]
    phase1 = [r["rdp_phase1_candidates"] for r in data["results"]]
    final = [r["rdp_final_patterns"] for r in data["results"]]
    filtered = [r["rdp_filtered_out"] for r in data["results"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    x = range(len(seeds))
    ax1.bar(x, phase1, label="Phase 1 (Locally Dense)", color="#FF9800", alpha=0.8)
    ax1.bar(x, final, label="Phase 2 (Rare Dense)", color="#2196F3", alpha=0.8)
    ax1.set_xlabel("Seed")
    ax1.set_ylabel("Pattern Count")
    ax1.set_title("(a) Two-Phase Filtering Effect")
    ax1.set_xticks(x)
    ax1.set_xticklabels(seeds)
    ax1.legend()

    # Filtering ratio
    ratios = [f / p * 100 if p > 0 else 0 for f, p in zip(filtered, phase1)]
    ax2.bar(x, ratios, color="#4CAF50")
    ax2.set_xlabel("Seed")
    ax2.set_ylabel("Filtered Out (%)")
    ax2.set_title("(b) Phase 2 Filtering Ratio")
    ax2.set_xticks(x)
    ax2.set_xticklabels(seeds)
    ax2.set_ylim(0, 100)

    plt.tight_layout()
    plt.savefig(fig_dir / "e2_pruning.pdf", bbox_inches="tight")
    plt.savefig(fig_dir / "e2_pruning.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved e2_pruning.pdf/png")


def fig_e3():
    """E3: Scalability plot."""
    data = load_json("e3_scalability.json")
    if not HAS_MPL:
        return

    ns = [r["n_transactions"] for r in data["results"]]
    times = [r["time_ms"] for r in data["results"]]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(ns, times, "o-", color="#2196F3", linewidth=2, markersize=8)
    ax.set_xlabel("Number of Transactions (N)")
    ax.set_ylabel("Runtime (ms)")
    ax.set_title("Scalability of Two-Phase RDP Mining")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(fig_dir / "e3_scalability.pdf", bbox_inches="tight")
    plt.savefig(fig_dir / "e3_scalability.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved e3_scalability.pdf/png")


def main():
    print("Generating figures...")
    fig_e1()
    fig_e2()
    fig_e3()
    print("Done.")


if __name__ == "__main__":
    main()
