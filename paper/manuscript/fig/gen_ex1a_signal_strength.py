"""EX1a: Signal strength vs attribution accuracy (line chart).

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
    "lines.linewidth": 1.2,
    "lines.markersize": 5,
})

# Data from Table EX1a (Zipf-1.0, sqrt normalization, 5 seeds avg)
beta = [0.2, 0.3, 0.5]
precision = [0.78, 0.67, 0.57]
recall = [0.73, 0.93, 0.87]
f1 = [0.74, 0.77, 0.69]
far = [0.10, 0.10, 0.20]

fig, ax = plt.subplots(figsize=(3.5, 2.4))

ax.plot(beta, f1, "o-", color="#2d3436", label="F1")
ax.plot(beta, precision, "s--", color="#0984e3", label="Precision")
ax.plot(beta, recall, "^--", color="#e17055", label="Recall")
ax.plot(beta, far, "x:", color="#d63031", label="FAR")

ax.set_xlabel(r"Boost probability $\beta$")
ax.set_ylabel("Score")
ax.set_xticks(beta)
ax.set_ylim(-0.05, 1.08)
ax.set_yticks(np.arange(0, 1.1, 0.2))
ax.yaxis.grid(True, color="#E0E0E0", linewidth=0.5, zorder=0)
ax.set_axisbelow(True)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

fig.tight_layout()
fig.subplots_adjust(bottom=0.28)

# Legend below the plot, outside axes
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
fig.savefig(out / "ex1a_signal_strength.pdf", bbox_inches="tight", dpi=300)
fig.savefig(out / "ex1a_signal_strength.png", bbox_inches="tight", dpi=300)
print("Saved ex1a_signal_strength.pdf/png")
