"""Support time series example: illustrates what the pipeline detects."""
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
from matplotlib.patches import FancyArrowPatch

matplotlib.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.labelsize": 10,
    "legend.fontsize": 8,
    "figure.dpi": 300,
})

np.random.seed(42)

N = 5000
W = 50
T = N - W + 1

# Generate synthetic support time series for pattern P = {5, 15}
# Base: Poisson noise around baseline
p_base = 0.03
baseline = W * p_base**2  # ~0.045 expected for pair under independence
support = np.random.poisson(lam=baseline, size=T).astype(float)

# Event 1: boost at [1000, 1300]
event1_start, event1_end = 1000, 1300
beta1 = 0.3
boost1 = W * (p_base + beta1)**2 - baseline
support[event1_start:event1_end] += np.random.poisson(lam=boost1, size=event1_end - event1_start)

# Event 2: boost at [3000, 3300]
event2_start, event2_end = 3000, 3300
beta2 = 0.15
boost2 = W * (p_base + beta2)**2 - baseline
support[event2_start:event2_end] += np.random.poisson(lam=boost2, size=event2_end - event2_start)

# Type B: unrelated dense region at [2000, 2250] (no event)
typeb_start, typeb_end = 2000, 2250
boost_b = W * (p_base + 0.25)**2 - baseline
support[typeb_start:typeb_end] += np.random.poisson(lam=boost_b, size=typeb_end - typeb_start)

# Smooth slightly for visual clarity
from scipy.ndimage import uniform_filter1d
support_smooth = uniform_filter1d(support, size=5)

# Threshold
theta = 3

fig, ax = plt.subplots(figsize=(7.16, 2.2))

# Support time series
ax.plot(range(T), support_smooth, color="#475569", linewidth=0.5, alpha=0.8, label=r"$s_P(t)$")
ax.axhline(theta, color="#dc2626", linewidth=0.8, linestyle="--", alpha=0.6, label=r"$\theta$ = " + str(theta))

# Event regions
ax.axvspan(event1_start, event1_end, alpha=0.15, color="#2563eb", label="Event E1")
ax.axvspan(event2_start, event2_end, alpha=0.15, color="#059669", label="Event E2")

# Type B region (no event)
ax.axvspan(typeb_start, typeb_end, alpha=0.10, color="#f59e0b",
           label="Type B (no event)")

# Change points (up arrows at event starts, down arrows at event ends)
cp_style = dict(fontsize=8, fontweight="bold", ha="center")
arrow_y = max(support_smooth) * 0.92

# Event 1 change points
ax.annotate(r"$\tau_{\uparrow}$", xy=(event1_start, theta),
            xytext=(event1_start, arrow_y),
            arrowprops=dict(arrowstyle="->", color="#2563eb", lw=1.2),
            color="#2563eb", **cp_style)
ax.annotate(r"$\tau_{\downarrow}$", xy=(event1_end, theta),
            xytext=(event1_end, arrow_y),
            arrowprops=dict(arrowstyle="->", color="#2563eb", lw=1.2),
            color="#2563eb", **cp_style)

# Event 2 change points
ax.annotate(r"$\tau_{\uparrow}$", xy=(event2_start, theta),
            xytext=(event2_start, arrow_y * 0.75),
            arrowprops=dict(arrowstyle="->", color="#059669", lw=1.2),
            color="#059669", **cp_style)
ax.annotate(r"$\tau_{\downarrow}$", xy=(event2_end, theta),
            xytext=(event2_end, arrow_y * 0.75),
            arrowprops=dict(arrowstyle="->", color="#059669", lw=1.2),
            color="#059669", **cp_style)

# Type B change points (detected but should be rejected)
ax.annotate(r"$\tau_{\uparrow}$" + "\n(rejected)", xy=(typeb_start, theta),
            xytext=(typeb_start - 100, arrow_y * 0.85),
            arrowprops=dict(arrowstyle="->", color="#f59e0b", lw=1.0, linestyle="--"),
            color="#f59e0b", fontsize=7, ha="center")

ax.set_xlabel("Window position $t$")
ax.set_ylabel(r"Support $s_P(t)$")
ax.set_xlim(0, T)
ax.set_ylim(-0.5, max(support_smooth) * 1.15)
ax.legend(loc="upper right", ncol=3, framealpha=0.9, fontsize=7)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(axis="y", alpha=0.2)

fig.tight_layout()
fig.savefig("support_timeseries_example.pdf", bbox_inches="tight")
fig.savefig("support_timeseries_example.png", bbox_inches="tight", dpi=300)
print("Saved support_timeseries_example.pdf/png")
