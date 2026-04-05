"""Generate pipeline overview figure for the paper."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

fig, axes = plt.subplots(1, 2, figsize=(7.16, 3.2), gridspec_kw={'width_ratios': [1.1, 1.0]})

# ===== Left panel: Pipeline block diagram =====
ax = axes[0]
ax.set_xlim(0, 10)
ax.set_ylim(0, 12)
ax.axis('off')
ax.set_title('(a) Pipeline Overview', fontsize=9, fontweight='bold', pad=6)

# Colors
c_input = '#FFFFFF'
c_step = '#E3F2FD'
c_output = '#FFFFFF'
c_border_input = '#333333'
c_border_step = '#1565C0'
c_border_output = '#333333'

boxes = [
    # (x, y, w, h, text, bg_color, border_color)
    (0.5, 10.2, 9, 1.2, 'Input: Patterns $\\mathcal{F}$, Dense Intervals, Events $\\mathcal{E}$', c_input, c_border_input),
    (0.5, 8.2, 9, 1.4, 'Step 1–2: Change Point Extraction\n& Magnitude Evaluation', c_step, c_border_step),
    (0.5, 6.2, 9, 1.4, 'Step 3: Attribution Scoring\n$A = \\mathrm{prox} \\times \\mathrm{mag}$', c_step, c_border_step),
    (0.5, 4.2, 9, 1.4, 'Step 4: Circular-Shift Permutation Test\n& Global BH Correction', c_step, c_border_step),
    (0.5, 2.2, 9, 1.4, 'Step 5: Union-Find Deduplication\n(Item-Overlap Graph)', c_step, c_border_step),
    (0.5, 0.2, 9, 1.4, 'Output: Significant Attributions\n$(P, e)$ pairs with FDR $\\leq \\alpha$', c_output, c_border_output),
]

for (x, y, w, h, text, bg, bc) in boxes:
    rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15",
                          facecolor=bg, edgecolor=bc, linewidth=1.5)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=6.5,
            linespacing=1.4)

# Arrows between boxes
for i in range(5):
    y_from = boxes[i][1]
    y_to = boxes[i+1][1] + boxes[i+1][3]
    ax.annotate('', xy=(5, y_to + 0.05), xytext=(5, y_from - 0.05),
                arrowprops=dict(arrowstyle='->', color='#555', lw=1.5))

# ===== Right panel: Concrete example =====
ax2 = axes[1]
ax2.set_title('(b) Attribution Example', fontsize=9, fontweight='bold', pad=6)

# Generate example support time series
np.random.seed(42)
N = 200
t = np.arange(N)

# Baseline support ~2
baseline = np.random.poisson(2, N).astype(float)

# Support boost at t=45–130 (change point detectable ~t=45, event at t=70–110)
boost_start = 45
event1_start, event1_end = 70, 110
for i in range(boost_start, 130):
    factor = 5 if i < event1_end else max(0, 5 - (i - event1_end) * 0.4)
    baseline[i] += np.random.poisson(max(1, int(factor)))

# Smooth
kernel = np.ones(8) / 8
support = np.convolve(baseline, kernel, mode='same')

ax2.plot(t, support, color='#000000', linewidth=1.0, alpha=0.9)
ax2.set_xlabel('Transaction index $t$', fontsize=7)
ax2.set_ylabel('Support $s_P(t)$', fontsize=7)
ax2.tick_params(labelsize=6)

# Change point τ↑ at the rise (t=47)
cp_up = 47
ax2.axvline(x=cp_up, color='#1565C0', linestyle=':', linewidth=1.0, alpha=0.8)
ax2.annotate('$\\tau_{\\uparrow}$', xy=(cp_up, support[cp_up]),
             xytext=(cp_up + 12, support[cp_up] + 0.5),
             fontsize=8, color='#1565C0', fontweight='bold',
             arrowprops=dict(arrowstyle='->', color='#1565C0', lw=0.8))

# Event period (shaded)
ax2.axvspan(event1_start, event1_end, alpha=0.15, color='#999999')
ax2.text((event1_start + event1_end) / 2, 0.6, 'Event $e$',
         fontsize=8, ha='center', color='#000000', fontweight='bold')

# Magnitude arrow (before vs after change point)
mag_y_low = np.mean(support[cp_up - 20:cp_up])
mag_y_high = np.mean(support[cp_up + 5:cp_up + 30])
mag_x = cp_up - 6
ax2.annotate('', xy=(mag_x, mag_y_high), xytext=(mag_x, mag_y_low),
             arrowprops=dict(arrowstyle='<->', color='#1565C0', lw=1.5))
ax2.text(mag_x - 4, (mag_y_high + mag_y_low) / 2, 'mag', fontsize=7,
         color='#0D47A1', ha='right', fontweight='bold')

# Proximity arrow (τ↑ → event start — 23 unit gap, clearly visible)
prox_y = 1.5
ax2.annotate('', xy=(event1_start, prox_y), xytext=(cp_up, prox_y),
             arrowprops=dict(arrowstyle='<->', color='#1565C0', lw=1.2))
ax2.text((cp_up + event1_start) / 2, prox_y + 0.5, 'prox', fontsize=7,
         color='#0D47A1', ha='center', fontweight='bold')

ax2.set_ylim(0, max(support) + 2)
ax2.set_xlim(0, N)

plt.tight_layout(pad=0.5)
plt.savefig('/Users/kanata/Documents/GitHub/mining/apriori-window/paper/manuscript/fig/pipeline_overview.pdf',
            bbox_inches='tight', dpi=300)
plt.savefig('/Users/kanata/Documents/GitHub/mining/apriori-window/paper/manuscript/fig/pipeline_overview.png',
            bbox_inches='tight', dpi=300)
print("Figure saved.")
