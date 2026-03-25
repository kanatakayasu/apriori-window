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
c_input = '#E8F0FE'
c_step = '#FFF3E0'
c_output = '#E8F5E9'
c_border_input = '#4285F4'
c_border_step = '#FB8C00'
c_border_output = '#43A047'

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

# Baseline support ~3
baseline = np.random.poisson(3, N).astype(float)

# Event 1: boost at t=50-90
event1_start, event1_end = 50, 90
for i in range(event1_start, event1_end):
    baseline[i] += np.random.poisson(5)

# Smooth with simple moving average (no scipy dependency)
kernel = np.ones(10) / 10
support = np.convolve(baseline, kernel, mode='same')

ax2.plot(t, support, color='#1565C0', linewidth=1.0, alpha=0.9)
ax2.set_xlabel('Transaction index $t$', fontsize=7)
ax2.set_ylabel('Support $s_P(t)$', fontsize=7)
ax2.tick_params(labelsize=6)

# Mark threshold
theta = 4.5
ax2.axhline(y=theta, color='#999', linestyle='--', linewidth=0.8, alpha=0.7)
ax2.text(195, theta + 0.3, '$\\theta$', fontsize=7, ha='right', color='#666')

# Mark change points
cp_up = 48
cp_down = 92
ax2.axvline(x=cp_up, color='#E53935', linestyle=':', linewidth=1.0, alpha=0.8)
ax2.axvline(x=cp_down, color='#E53935', linestyle=':', linewidth=1.0, alpha=0.8)
ax2.annotate('$\\tau_{\\uparrow}$', xy=(cp_up, support[cp_up]),
             xytext=(cp_up - 15, support[cp_up] + 1.5),
             fontsize=7, color='#E53935', fontweight='bold',
             arrowprops=dict(arrowstyle='->', color='#E53935', lw=0.8))
ax2.annotate('$\\tau_{\\downarrow}$', xy=(cp_down, support[cp_down]),
             xytext=(cp_down + 8, support[cp_down] + 2.0),
             fontsize=7, color='#E53935', fontweight='bold',
             arrowprops=dict(arrowstyle='->', color='#E53935', lw=0.8))

# Mark event period
ax2.axvspan(event1_start, event1_end, alpha=0.12, color='#FF9800')
ax2.annotate('Event $e$', xy=((event1_start + event1_end)/2, 1.0),
             fontsize=7, ha='center', color='#E65100', fontweight='bold')

# Mark magnitude
mag_y_high = np.mean(support[cp_up:cp_up+20])
mag_y_low = np.mean(support[cp_up-20:cp_up])
ax2.annotate('', xy=(38, mag_y_high), xytext=(38, mag_y_low),
             arrowprops=dict(arrowstyle='<->', color='#43A047', lw=1.2))
ax2.text(33, (mag_y_high + mag_y_low)/2, 'mag', fontsize=6, color='#2E7D32',
         ha='right', fontweight='bold')

# Proximity annotation
ax2.annotate('', xy=(cp_up, 0.5), xytext=(event1_start, 0.5),
             arrowprops=dict(arrowstyle='<->', color='#7B1FA2', lw=0.8))
ax2.text((cp_up + event1_start)/2, 1.2, 'prox', fontsize=6, color='#7B1FA2',
         ha='center', fontweight='bold')

ax2.set_ylim(0, max(support) + 2)
ax2.set_xlim(0, N)

plt.tight_layout(pad=0.5)
plt.savefig('/Users/kanata/Documents/GitHub/mining/apriori-window/paper/manuscript/fig/pipeline_overview.pdf',
            bbox_inches='tight', dpi=300)
plt.savefig('/Users/kanata/Documents/GitHub/mining/apriori-window/paper/manuscript/fig/pipeline_overview.png',
            bbox_inches='tight', dpi=300)
print("Figure saved.")
