"""Generate figures for Paper C experiments."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "implementation" / "python"))

from multidim_dense import (
    compute_support_surface_naive,
    generate_synthetic_2d,
)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIGURES_DIR = Path(__file__).resolve().parent / "figures"


def fig_e1_support_surface():
    """Generate a heatmap of the support surface for E1."""
    if not HAS_MPL:
        print("  matplotlib not available, skipping figure generation")
        return

    txns, locs = generate_synthetic_2d(
        n_transactions=200, n_items=10, spatial_size=20,
        dense_regions=[{
            "pattern": [0, 1], "t_start": 50, "t_end": 150,
            "x_start": 5, "x_end": 15, "prob": 0.8,
        }],
        item_prob=0.05, seed=42,
    )
    window_sizes = (10, 5)
    grid_shape = (191, 16)
    surface = compute_support_surface_naive(
        txns, locs, frozenset([0, 1]), window_sizes, grid_shape
    )

    fig, ax = plt.subplots(1, 1, figsize=(8, 4))
    im = ax.imshow(surface.T, aspect="auto", origin="lower",
                   cmap="YlOrRd", interpolation="nearest")
    ax.set_xlabel("Time (window position)")
    ax.set_ylabel("Space (window position)")
    ax.set_title("Support Surface $S_{\\{0,1\\}}(t, x)$")
    plt.colorbar(im, ax=ax, label="Support count")

    # Mark threshold contour
    ax.contour(surface.T, levels=[3], colors="blue", linewidths=1.5)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "e1_support_surface.pdf", dpi=150)
    fig.savefig(FIGURES_DIR / "e1_support_surface.png", dpi=150)
    plt.close(fig)
    print("  e1_support_surface.pdf generated")


def fig_e3_scalability():
    """Generate scalability plot from E3 results."""
    if not HAS_MPL:
        return

    results_path = RESULTS_DIR / "all_results.json"
    if not results_path.exists():
        print("  No results file found, run experiments first")
        return

    with open(results_path) as f:
        data = json.load(f)

    e3 = data["e3"]
    data_2d = [r for r in e3 if r["dimensions"] == "2D"]
    data_3d = [r for r in e3 if r["dimensions"] == "3D"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    # 2D: naive vs fast
    ns = [r["n_transactions"] for r in data_2d]
    naive_times = [r["naive_time_ms"] for r in data_2d]
    fast_times = [r["fast_time_ms"] for r in data_2d]

    ax1.plot(ns, naive_times, "o-", label="Na\\\"ive", color="red")
    ax1.plot(ns, fast_times, "s-", label="Sweep Surface", color="blue")
    ax1.set_xlabel("Number of transactions")
    ax1.set_ylabel("Time (ms)")
    ax1.set_title("2D Scalability")
    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 3D
    if data_3d:
        ns_3d = [r["n_transactions"] for r in data_3d]
        times_3d = [r["fast_time_ms"] for r in data_3d]
        ax2.plot(ns_3d, times_3d, "D-", label="Sweep Surface (3D)", color="green")
        ax2.set_xlabel("Number of transactions")
        ax2.set_ylabel("Time (ms)")
        ax2.set_title("3D Scalability")
        ax2.set_xscale("log")
        ax2.set_yscale("log")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "e3_scalability.pdf", dpi=150)
    fig.savefig(FIGURES_DIR / "e3_scalability.png", dpi=150)
    plt.close(fig)
    print("  e3_scalability.pdf generated")


def main():
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating figures...")
    fig_e1_support_surface()
    fig_e3_scalability()
    print("Done.")


if __name__ == "__main__":
    main()
