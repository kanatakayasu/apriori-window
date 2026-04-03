"""EX3: Method comparison — grouped bar chart (F1 + FAR, 2 panels).

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
    "legend.fontsize": 7,
    "lines.linewidth": 1.0,
})

# ---------- Data (Table EX3, 6 methods) ----------
conditions = [r"$\beta\!=\!0.3$", "OVLP", "CNFND", "DENSE", "SHORT"]
methods = ["Proposed", "Wilcoxon", "CausalImpact", "ITS",
           "EventStudy", "ECA"]

f1 = {
    "Proposed":     [0.77, 0.84, 0.81, 0.70, 0.84],
    "Wilcoxon":     [0.54, 0.69, 0.19, 0.35, 0.47],
    "CausalImpact": [0.47, 0.53, 0.22, 0.32, 0.53],
    "ITS":          [0.81, 0.70, 0.39, 0.59, 0.71],
    "EventStudy":   [0.60, 0.68, 0.25, 0.49, 0.63],
    "ECA":          [0.23, 0.00, 0.00, 0.25, 0.27],
}
far = {
    "Proposed":     [0.10, 0.00, 0.40, 0.45, 0.30],
    "Wilcoxon":     [0.60, 0.60, 1.00, 0.75, 0.80],
    "CausalImpact": [0.50, 0.90, 1.00, 0.90, 0.80],
    "ITS":          [0.40, 0.40, 0.90, 0.60, 0.40],
    "EventStudy":   [0.10, 0.90, 1.00, 0.55, 0.40],
    "ECA":          [0.00, 0.00, 0.10, 0.00, 0.00],
}

# ---------- Colors ----------
colors = [
    "#2d3436",  # Proposed (dark)
    "#e17055",  # Wilcoxon
    "#fdcb6e",  # CausalImpact
    "#0984e3",  # ITS
    "#74b9ff",  # EventStudy
    "#bdc3c7",  # ECA
]
edgecols = [
    "#1e272e",
    "#d35400",
    "#e0a800",
    "#0652DD",
    "#2980b9",
    "#7f8c8d",
]
hatches = ["", "", "", "", "", "//"]

x = np.arange(len(conditions))
n = len(methods)
width = 0.13
offsets = np.array([-(n - 1) / 2 + i for i in range(n)]) * width

# ---------- Figure (2 panels) ----------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.16, 2.8))

panels = [
    (ax1, f1,  "F1",  "(a) F1"),
    (ax2, far, "FAR", "(b) FAR"),
]

for panel_idx, (ax, data, ylabel, title) in enumerate(panels):
    for i, method in enumerate(methods):
        ax.bar(
            x + offsets[i],
            data[method],
            width * 0.88,
            color=colors[i],
            edgecolor=edgecols[i],
            linewidth=0.5,
            hatch=hatches[i],
            label=method if panel_idx == 0 else None,
            zorder=3,
        )

    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    ax.set_xticklabels(conditions)
    ax.set_title(title, pad=6)
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
    ncol=6,
    frameon=True,
    edgecolor="#cccccc",
    fancybox=False,
    bbox_to_anchor=(0.5, -0.01),
    columnspacing=0.8,
    handletextpad=0.3,
)

fig.tight_layout(rect=[0, 0.09, 1, 1], w_pad=1.5)

out = Path(__file__).resolve().parent
fig.savefig(out / "ex3_method.pdf", bbox_inches="tight", dpi=300)
fig.savefig(out / "ex3_method.png", bbox_inches="tight", dpi=300)
print("Saved ex3_method.pdf/png")
