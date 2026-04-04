"""EX1b: Structural conditions — grouped bar chart (F1 / Precision / Recall).

Style: top-conference, matching EX2b ablation figure.
Data: 20-seed results.
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

# Data from EX1 20-seed run (N=100K, W=1000, θ=100)
conditions = ["OVERLAP", "CONFOUND", "DENSE", "SHORT"]
f1        = [0.74, 0.70, 0.67, 0.85]
precision = [0.64, 0.71, 0.54, 0.78]
recall    = [0.89, 0.70, 0.89, 0.97]
# 95% CI for F1
ci_lo     = [0.66, 0.60, 0.63, 0.80]
ci_hi     = [0.81, 0.80, 0.71, 0.91]

x = np.arange(len(conditions))
width = 0.22

colors = {
    "F1":        "#2d3436",
    "Precision": "#0984e3",
    "Recall":    "#74b9ff",
}

fig, ax = plt.subplots(figsize=(3.5, 2.4))

bars_f1 = ax.bar(x - width, f1,        width * 0.9, color=colors["F1"],        edgecolor="#1e272e", linewidth=0.5, label="F1", zorder=3)
bars_p  = ax.bar(x,         precision,  width * 0.9, color=colors["Precision"], edgecolor="#2980b9", linewidth=0.5, label="Precision", zorder=3)
bars_r  = ax.bar(x + width, recall,     width * 0.9, color=colors["Recall"],    edgecolor="#2980b9", linewidth=0.5, label="Recall", zorder=3)

# Add 95% CI error bars on F1 bars
f1_arr = np.array(f1)
err_lo = f1_arr - np.array(ci_lo)
err_hi = np.array(ci_hi) - f1_arr
ax.errorbar(x - width, f1_arr, yerr=[err_lo, err_hi], fmt="none",
            color="#636e72", capsize=2.5, linewidth=0.8, zorder=4)

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
    ncol=3,
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
