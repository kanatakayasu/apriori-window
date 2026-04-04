"""Generate null FDR distribution figure (100 seeds)."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

plt.rcParams.update({
    "font.family": "serif",
    "mathtext.fontset": "cm",
    "font.size": 8,
    "axes.labelsize": 9,
    "axes.titlesize": 9,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.labelsize": 8,
    "ytick.labelsize": 7,
})

results_path = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "experiments/results/null_fdr_100seeds/null_fdr_results.json"
)
with open(results_path) as f:
    data = json.load(f)

n_sigs = [s["n_significant"] for s in data["seeds"]]
mean_fdr = data["mean_per_seed_fdr"]
alpha    = data["alpha"]
n_seeds  = data["n_seeds"]

fig, ax = plt.subplots(figsize=(3.5, 2.4))

counts = np.bincount(n_sigs, minlength=max(n_sigs) + 2)
x = np.arange(len(counts))
ax.bar(x, counts, color="#2d3436", edgecolor="#1e272e", linewidth=0.5, zorder=3)

ax.axhline(n_seeds * alpha, color="#e17055", linewidth=1.0, linestyle="--",
           label=rf"$\alpha \times N_{{\mathrm{{seeds}}}} = {n_seeds * alpha:.0f}$")

ax.set_xlabel("False positives per seed")
ax.set_ylabel("Number of seeds")
ax.set_xticks(x)
ax.yaxis.grid(True, color="#E0E0E0", linewidth=0.5, zorder=0)
ax.set_axisbelow(True)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

fig.tight_layout()
fig.subplots_adjust(bottom=0.28)
fig.legend(
    *ax.get_legend_handles_labels(),
    loc="lower center",
    bbox_to_anchor=(0.5, -0.01),
    ncol=1,
    frameon=True,
    edgecolor="#cccccc",
    fancybox=False,
)

out = Path(__file__).resolve().parent
fig.savefig(out / "null_fdr_dist.pdf", bbox_inches="tight", dpi=300)
fig.savefig(out / "null_fdr_dist.png", bbox_inches="tight", dpi=300)
print(f"Saved null_fdr_dist.pdf/png  (mean FDR={mean_fdr:.4f}, alpha={alpha})")
