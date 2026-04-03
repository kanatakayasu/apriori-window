"""EX2b: Ablation analysis — stepwise pipeline addition (3 panels).

Style: top-conference (NeurIPS / KDD / ICML) grouped bar chart.
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
    "lines.linewidth": 1.0,
})

# ---------- Data (Table EX2b) ----------
conditions = [r"$\beta\!=\!0.3$", "CONFOUND", "DENSE"]
methods = ["Naive", "+PermTest", "+BH", "Full"]

f1 = {
    "Naive":     [0.02, 0.02, 0.03],
    "+PermTest": [0.03, 0.02, 0.03],
    "+BH":       [0.71, 0.56, 0.66],
    "Full":      [0.77, 0.81, 0.70],
}
far = {
    "Naive":     [0.80, 1.00, 0.95],
    "+PermTest": [0.40, 1.00, 0.60],
    "+BH":       [0.20, 1.00, 0.45],
    "Full":      [0.10, 0.40, 0.45],
}
pred = {
    "Naive":     [270, 303, 438],
    "+PermTest": [224, 265, 413],
    "+BH":       [5, 9, 11],
    "Full":      [4, 4, 10],
}

# ---------- Colors & hatches ----------
colors   = ["#bdc3c7", "#74b9ff", "#0984e3", "#2d3436"]
hatches  = ["//",  "",  "",  ""]
edgecols = ["#7f8c8d", "#2980b9", "#0652DD", "#1e272e"]

x = np.arange(len(conditions))
n = len(methods)
width = 0.18
offsets = np.array([-(n-1)/2 + i for i in range(n)]) * width

# ---------- Figure (3 panels) ----------
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(7.16, 2.6))

panels = [
    (ax1, f1,   "F1",    "(a) F1",    False),
    (ax2, far,  "FAR",   "(b) FAR",   False),
    (ax3, pred, r"\#Pred", "(c) \#Predictions", True),
]

for panel_idx, (ax, data, ylabel, title, use_log) in enumerate(panels):
    for i, method in enumerate(methods):
        bars = ax.bar(
            x + offsets[i],
            data[method],
            width * 0.88,
            color=colors[i],
            edgecolor=edgecols[i],
            linewidth=0.6,
            hatch=hatches[i],
            label=method if panel_idx == 0 else None,
            zorder=3,
        )

    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    ax.set_xticklabels(conditions)
    ax.set_title(title, pad=6)

    if use_log:
        ax.set_yscale("log")
        ax.set_ylim(1, 800)
    else:
        ax.set_ylim(0, 1.15)

    ax.yaxis.grid(True, color="#E0E0E0", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

# Shared legend — bottom centre
handles, labels = ax1.get_legend_handles_labels()
fig.legend(
    handles, labels,
    loc="lower center",
    ncol=4,
    frameon=True,
    edgecolor="#cccccc",
    fancybox=False,
    bbox_to_anchor=(0.5, -0.01),
    columnspacing=1.2,
    handletextpad=0.4,
)

fig.tight_layout(rect=[0, 0.08, 1, 1], w_pad=1.5)

out = Path(__file__).resolve().parent
fig.savefig(out / "ex2b_ablation.pdf", bbox_inches="tight", dpi=300)
fig.savefig(out / "ex2b_ablation.png", bbox_inches="tight", dpi=300)
print("Saved ex2b_ablation.pdf/png")
