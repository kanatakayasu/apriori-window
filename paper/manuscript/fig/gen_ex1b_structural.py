"""EX1b: Structural conditions — grouped bar chart (F1 + FAR).

Style: top-conference, matching EX2b ablation figure.
"""
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
    "legend.fontsize": 7.5,
})

# Data from EX1 full run (N=100K, W=1000, θ=100, 5 seeds avg)
conditions = ["OVERLAP", "CONFOUND", "DENSE", "SHORT"]
f1        = [0.80, 0.69, 0.65, 0.79]
far       = [0.80, 0.40, 0.65, 0.60]
precision = [0.68, 0.70, 0.53, 0.67]
recall    = [1.00, 0.68, 0.87, 1.00]

x = np.arange(len(conditions))
width = 0.20

colors = {
    "F1":        "#2d3436",
    "Precision": "#0984e3",
    "Recall":    "#74b9ff",
    "FAR":       "#d63031",
}

fig, ax = plt.subplots(figsize=(3.5, 2.4))

ax.bar(x - 1.5 * width, f1,        width * 0.9, color=colors["F1"],        edgecolor="#1e272e", linewidth=0.5, label="F1", zorder=3)
ax.bar(x - 0.5 * width, precision,  width * 0.9, color=colors["Precision"], edgecolor="#2980b9", linewidth=0.5, label="Precision", zorder=3)
ax.bar(x + 0.5 * width, recall,     width * 0.9, color=colors["Recall"],    edgecolor="#2980b9", linewidth=0.5, label="Recall", zorder=3)
ax.bar(x + 1.5 * width, far,        width * 0.9, color=colors["FAR"],       edgecolor="#c0392b", linewidth=0.5, label="FAR", hatch="//", zorder=3)

ax.set_xticks(x)
ax.set_xticklabels(conditions)
ax.set_ylabel("Score")
ax.set_ylim(0, 1.08)
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
    ncol=4,
    frameon=True,
    edgecolor="#cccccc",
    fancybox=False,
    columnspacing=1.0,
    handletextpad=0.4,
)

out = Path(__file__).resolve().parent
fig.savefig(out / "ex1b_structural.pdf", bbox_inches="tight", dpi=300)
fig.savefig(out / "ex1b_structural.png", bbox_inches="tight", dpi=300)
print("Saved ex1b_structural.pdf/png")
