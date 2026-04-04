"""EX3: Method comparison — grouped bar chart (F1 only).

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

# ---------- Data (EX3 full run, N=100K, W=1000, θ=100, 5 seeds avg) ----------
conditions = [r"$\beta\!=\!0.3$", "Overlap", "Confound", "Dense", "Short"]
methods = ["Proposed", "Wilcoxon", "CausalImpact", "ITS",
           "EventStudy", "ECA"]

f1 = {
    "Proposed":     [0.66, 0.67, 0.68, 0.66, 0.72],
    "Wilcoxon":     [0.34, 0.27, 0.14, 0.18, 0.42],
    "CausalImpact": [0.36, 0.17, 0.22, 0.24, 0.49],
    "ITS":          [0.60, 0.40, 0.45, 0.42, 0.77],
    "EventStudy":   [0.41, 0.18, 0.24, 0.29, 0.54],
    "ECA":          [0.00, 0.16, 0.15, 0.00, 0.28],
}

# ---------- Colors (grayscale-friendly: distinct luminance levels) ----------
# Each method gets a unique hatch pattern for grayscale printing (IEEE requirement)
colors = [
    "#1a1a1a",  # Proposed (near-black)
    "#c0392b",  # Wilcoxon (dark red → ~30% gray)
    "#e67e22",  # CausalImpact (orange → ~55% gray)
    "#2471a3",  # ITS (blue → ~40% gray)
    "#148f77",  # EventStudy (green → ~45% gray)
    "#aab7b8",  # ECA (light gray → ~70% gray)
]
edgecols = [
    "#000000",
    "#922b21",
    "#ca6f1e",
    "#1a5276",
    "#0e6655",
    "#717d7e",
]
# Distinct hatch patterns ensure legibility in black-and-white printing
hatches = ["", "///", "\\\\", "|||", "---", "xxx"]

x = np.arange(len(conditions))
n = len(methods)
width = 0.13
offsets = np.array([-(n - 1) / 2 + i for i in range(n)]) * width

# ---------- Figure (single panel) ----------
fig, ax = plt.subplots(figsize=(3.8, 2.8))

for i, method in enumerate(methods):
    ax.bar(
        x + offsets[i],
        f1[method],
        width * 0.88,
        color=colors[i],
        edgecolor=edgecols[i],
        linewidth=0.5,
        hatch=hatches[i],
        label=method,
        zorder=3,
    )

ax.set_ylabel("F1")
ax.set_xticks(x)
ax.set_xticklabels(conditions)
ax.set_ylim(0, 1.15)
ax.yaxis.grid(True, color="#E0E0E0", linewidth=0.5, zorder=0)
ax.set_axisbelow(True)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

handles, labels = ax.get_legend_handles_labels()
fig.legend(
    handles, labels,
    loc="lower center",
    ncol=3,
    frameon=True,
    edgecolor="#cccccc",
    fancybox=False,
    bbox_to_anchor=(0.5, -0.01),
    columnspacing=0.8,
    handletextpad=0.3,
)

fig.tight_layout(rect=[0, 0.18, 1, 1])

out = Path(__file__).resolve().parent
fig.savefig(out / "ex3_method.pdf", bbox_inches="tight", dpi=300)
fig.savefig(out / "ex3_method.png", bbox_inches="tight", dpi=300)
print("Saved ex3_method.pdf/png")
