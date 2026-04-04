"""EX3: Method comparison — heatmap (F1 scores).

6 methods × 5 conditions. Compact, easy cross-method comparison.
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
    "ytick.labelsize": 8,
})

# ---------- Data ----------
conditions = [r"$\beta\!=\!0.3$", "Overlap", "Confound", "Dense", "Short"]
methods    = ["Proposed", "Wilcoxon", "CausalImpact", "ITS", "EventStudy"]

f1 = np.array([
    [0.66, 0.67, 0.68, 0.66, 0.72],  # Proposed
    [0.34, 0.27, 0.14, 0.18, 0.42],  # Wilcoxon
    [0.36, 0.17, 0.22, 0.24, 0.49],  # CausalImpact
    [0.60, 0.40, 0.45, 0.42, 0.77],  # ITS
    [0.41, 0.18, 0.24, 0.29, 0.54],  # EventStudy
])

# ---------- Figure ----------
fig, ax = plt.subplots(figsize=(3.8, 2.4))

im = ax.imshow(f1, cmap="Blues", vmin=0.0, vmax=1.0, aspect="auto")

# Cell annotations
for i in range(len(methods)):
    for j in range(len(conditions)):
        val = f1[i, j]
        txt_color = "white" if val >= 0.55 else "#333333"
        ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                fontsize=7, color=txt_color, fontweight="normal")

# Highlight "Proposed" row with bold border
ax.set_xticks(range(len(conditions)))
ax.set_xticklabels(conditions, rotation=20, ha="right")
ax.set_yticks(range(len(methods)))
ax.set_yticklabels(methods)
ax.tick_params(length=0)

# Bold label for "Proposed"
for label in ax.get_yticklabels():
    if label.get_text() == "Proposed":
        label.set_fontweight("bold")

# Colorbar
cb = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
cb.set_label("F1", fontsize=8)
cb.ax.tick_params(labelsize=7)

# Full box border on axes
for spine in ax.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(0.6)

fig.tight_layout()

out = Path(__file__).resolve().parent
fig.savefig(out / "ex3_method.pdf", bbox_inches="tight", dpi=300)
fig.savefig(out / "ex3_method.png", bbox_inches="tight", dpi=300)
print("Saved ex3_method.pdf/png")
