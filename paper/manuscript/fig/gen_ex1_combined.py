"""EX1 combined: (a) signal strength + (b) structural conditions — side by side."""
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

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(5.5, 2.6))

# ── (a) Signal strength ──────────────────────────────────────────────────────
beta      = [0.1, 0.2, 0.3, 0.4, 0.5]
precision = [0.71, 0.73, 0.69, 0.72, 0.71]
recall    = [0.22, 0.94, 0.93, 0.94, 0.92]
f1        = [0.34, 0.81, 0.79, 0.81, 0.79]
ci_lo     = [0.30, 0.77, 0.74, 0.75, 0.74]
ci_hi     = [0.37, 0.86, 0.84, 0.87, 0.85]

f1_arr    = np.array(f1)
ci_lo_arr = np.array(ci_lo)
ci_hi_arr = np.array(ci_hi)

ax1.fill_between(beta, ci_lo_arr, ci_hi_arr, alpha=0.15, color="#2d3436", zorder=1)
ax1.plot(beta, f1,        "o-",  color="#2d3436", label="F1 (95% CI)")
ax1.plot(beta, precision, "s--", color="#0984e3", label="Precision")
ax1.plot(beta, recall,    "^--", color="#e17055", label="Recall")

ax1.set_xlabel(r"Boost probability $\beta$")
ax1.set_ylabel("Score")
ax1.set_xticks(beta)
ax1.set_xlim(0.05, 0.55)
ax1.set_ylim(0.0, 1.0)
ax1.set_yticks(np.arange(0, 1.1, 0.2))
ax1.yaxis.grid(True, color="#E0E0E0", linewidth=0.5, zorder=0)
ax1.set_axisbelow(True)
ax1.set_title("(a) Signal Strength", pad=4)
for spine in ax1.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(0.6)

ax1.legend(loc="lower right", frameon=True, edgecolor="#cccccc",
           fancybox=False, handletextpad=0.4)

# ── (b) Structural conditions ────────────────────────────────────────────────
conditions = ["OVERLAP", "CONFOUND", "DENSE", "SHORT"]
f1b        = [0.74, 0.70, 0.67, 0.85]
precision2 = [0.64, 0.71, 0.54, 0.78]
recall2    = [0.89, 0.70, 0.89, 0.97]
ci_lo2     = [0.66, 0.60, 0.63, 0.80]
ci_hi2     = [0.81, 0.80, 0.71, 0.91]

x     = np.arange(len(conditions))
width = 0.22
colors = {"F1": "#2d3436", "Precision": "#0984e3", "Recall": "#74b9ff"}

bars_f1 = ax2.bar(x - width, f1b,        width * 0.9,
                  color=colors["F1"],        edgecolor="#1e272e", linewidth=0.5,
                  label="F1", zorder=3)
bars_p  = ax2.bar(x,         precision2,  width * 0.9,
                  color=colors["Precision"], edgecolor="#2980b9", linewidth=0.5,
                  label="Precision", zorder=3)
bars_r  = ax2.bar(x + width, recall2,     width * 0.9,
                  color=colors["Recall"],    edgecolor="#2980b9", linewidth=0.5,
                  label="Recall", zorder=3)

# 95% CI error bars on F1
f1b_arr = np.array(f1b)
err_lo  = f1b_arr - np.array(ci_lo2)
err_hi  = np.array(ci_hi2) - f1b_arr
ax2.errorbar(x - width, f1b_arr, yerr=[err_lo, err_hi], fmt="none",
             color="#636e72", capsize=2.5, linewidth=0.8, zorder=4)

ax2.set_xticks(x)
ax2.set_xticklabels(conditions, rotation=15, ha="right")
ax2.set_ylabel("Score")
ax2.set_ylim(0, 1.15)
ax2.yaxis.grid(True, color="#E0E0E0", linewidth=0.5, zorder=0)
ax2.set_axisbelow(True)
ax2.set_title("(b) Structural Conditions", pad=4)
for spine in ax2.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(0.6)

ax2.legend(loc="upper center", ncol=3, frameon=True, edgecolor="#cccccc",
           fancybox=False, handletextpad=0.4, columnspacing=0.8,
           fontsize=7.0, bbox_to_anchor=(0.5, 1.0))

# ── Save ─────────────────────────────────────────────────────────────────────
fig.tight_layout(w_pad=1.5)

out = Path(__file__).resolve().parent
fig.savefig(out / "ex1_combined.pdf", bbox_inches="tight", dpi=300)
fig.savefig(out / "ex1_combined.png", bbox_inches="tight", dpi=300)
print("Saved ex1_combined.pdf/png")
