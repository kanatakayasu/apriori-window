"""Related work comparison dot chart (Table I visualization)."""
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.labelsize": 10,
    "legend.fontsize": 8,
    "figure.dpi": 300,
})

# Data from Table I (tab:related_comparison)
methods = [
    "Temporal FPM",
    "EP / Contrast",
    "Change Point\nDetection",
    "ITS / Intervention",
    "Event Study",
    "CausalImpact",
    "Wilcoxon",
    "ECA",
    "Statistical FPM",
    "Proposed",
]

features = [
    "Time-series\nchange",
    "Event\nattribution",
    "Many\npatterns",
    "Multiple\ntesting",
    "Dedup-\nlication",
]

# 1 = yes, 0.5 = partial, 0 = no
matrix = np.array([
    # TimeSeries  EventAttr  ManyPat  MultTest  Dedup
    [0, 0, 1, 0, 0],  # Temporal FPM
    [1, 0, 1, 0.5, 0],  # EP/Contrast
    [1, 0, 0, 0, 0],  # Change Point
    [1, 1, 0, 0, 0],  # ITS
    [1, 1, 0, 0, 0],  # Event Study
    [1, 1, 0, 0, 0],  # CausalImpact
    [0, 1, 0, 0, 0],  # Wilcoxon
    [0, 1, 0, 0, 0],  # ECA
    [0, 0, 1, 1, 0],  # Statistical FPM
    [1, 1, 1, 1, 1],  # Proposed
])

fig, ax = plt.subplots(figsize=(3.5, 3.2))

for i in range(len(methods)):
    for j in range(len(features)):
        val = matrix[i, j]
        if i == len(methods) - 1:  # Proposed method
            if val == 1:
                ax.scatter(j, i, s=120, c="#1e40af", marker="o", zorder=3, edgecolors="white", linewidths=0.5)
            else:
                ax.scatter(j, i, s=60, c="white", marker="o", zorder=3, edgecolors="#94a3b8", linewidths=1)
        else:
            if val == 1:
                ax.scatter(j, i, s=80, c="#3b82f6", marker="o", zorder=3, edgecolors="white", linewidths=0.5)
            elif val == 0.5:
                ax.scatter(j, i, s=80, c="#93c5fd", marker="o", zorder=3, edgecolors="white", linewidths=0.5)
            else:
                ax.scatter(j, i, s=40, c="#e2e8f0", marker="o", zorder=3, edgecolors="#cbd5e1", linewidths=0.5)

# Highlight proposed row
ax.axhspan(len(methods) - 1.5, len(methods) - 0.5, color="#eff6ff", zorder=0)

# Grid
for i in range(len(methods)):
    ax.axhline(i, color="#f1f5f9", linewidth=0.5, zorder=0)

ax.set_xticks(range(len(features)))
ax.set_xticklabels(features, fontsize=7)
ax.set_yticks(range(len(methods)))
ax.set_yticklabels(methods, fontsize=7.5)
ax.set_xlim(-0.5, len(features) - 0.5)
ax.set_ylim(-0.5, len(methods) - 0.5)

ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_visible(False)
ax.spines["bottom"].set_visible(False)
ax.tick_params(left=False, bottom=False)

# Legend
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#3b82f6", markersize=8, label="Supported"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#93c5fd", markersize=8, label="Partial"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#e2e8f0", markersize=7,
           markeredgecolor="#cbd5e1", label="Not supported"),
]
ax.legend(handles=legend_elements, loc="lower center", bbox_to_anchor=(0.5, -0.25),
          ncol=3, frameon=False, fontsize=7)

fig.tight_layout()
fig.savefig("related_comparison.pdf", bbox_inches="tight")
fig.savefig("related_comparison.png", bbox_inches="tight", dpi=300)
print("Saved related_comparison.pdf/png")
