#!/usr/bin/env python3
"""Generate parameter sensitivity figure (2 panels) for IEEE paper."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# ---------- Data ----------
# Table VI: Window Size W
W_vals  = [10, 20, 50, 100, 200]
W_F1    = [0.75, 0.81, 0.71, 0.62, 0.00]
W_FAR   = [0.67, 0.33, 0.50, 0.33, 0.00]

# Table VII: Significance Level alpha
A_vals  = [0.01, 0.05, 0.10, 0.20, 0.30]
A_F1    = [0.00, 0.29, 0.76, 0.71, 0.71]
A_FAR   = [0.00, 0.17, 0.17, 0.50, 0.50]

# ---------- Style ----------
COLOR_F1  = '#1565C0'
COLOR_FAR = '#E53935'
FONT_LABEL = 8
FONT_TICK  = 7
FONT_TITLE = 8
FONT_LEGEND = 7
MARKER_SIZE = 5
LINE_WIDTH  = 1.2

plt.rcParams.update({
    'font.family': 'serif',
    'mathtext.fontset': 'cm',
    'axes.linewidth': 0.6,
    'xtick.major.width': 0.5,
    'ytick.major.width': 0.5,
    'xtick.major.size': 3,
    'ytick.major.size': 3,
})

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.16, 2.8))

# ---------- Panel (a): Window Size W ----------
x_w = range(len(W_vals))
ax1.plot(x_w, W_F1,  color=COLOR_F1,  marker='o', markersize=MARKER_SIZE,
         linewidth=LINE_WIDTH, linestyle='-',  label='F1')
ax1.plot(x_w, W_FAR, color=COLOR_FAR, marker='^', markersize=MARKER_SIZE,
         linewidth=LINE_WIDTH, linestyle='--', label='FAR')
ax1.set_xticks(x_w)
ax1.set_xticklabels([str(v) for v in W_vals], fontsize=FONT_TICK)
ax1.set_xlabel('$W$', fontsize=FONT_LABEL)
ax1.set_ylabel('Score', fontsize=FONT_LABEL)
ax1.set_ylim(-0.05, 1.05)
ax1.set_title('(a) Window Size $W$', fontsize=FONT_TITLE)
ax1.tick_params(axis='y', labelsize=FONT_TICK)
ax1.yaxis.grid(True, color='#E0E0E0', linewidth=0.5)
ax1.set_axisbelow(True)
ax1.legend(fontsize=FONT_LEGEND, frameon=True, edgecolor='#CCCCCC',
           fancybox=False, loc='upper right')

# ---------- Panel (b): Significance Level alpha ----------
x_a = range(len(A_vals))
ax2.plot(x_a, A_F1,  color=COLOR_F1,  marker='o', markersize=MARKER_SIZE,
         linewidth=LINE_WIDTH, linestyle='-',  label='F1')
ax2.plot(x_a, A_FAR, color=COLOR_FAR, marker='^', markersize=MARKER_SIZE,
         linewidth=LINE_WIDTH, linestyle='--', label='FAR')
ax2.set_xticks(x_a)
ax2.set_xticklabels([str(v) for v in A_vals], fontsize=FONT_TICK)
ax2.set_xlabel(r'$\alpha$', fontsize=FONT_LABEL)
ax2.set_ylabel('Score', fontsize=FONT_LABEL)
ax2.set_ylim(-0.05, 1.05)
ax2.set_title(r'(b) Significance Level $\alpha$', fontsize=FONT_TITLE)
ax2.tick_params(axis='y', labelsize=FONT_TICK)
ax2.yaxis.grid(True, color='#E0E0E0', linewidth=0.5)
ax2.set_axisbelow(True)
ax2.legend(fontsize=FONT_LEGEND, frameon=True, edgecolor='#CCCCCC',
           fancybox=False, loc='upper right')

# ---------- Save ----------
fig.tight_layout(w_pad=2.5)
out_dir = Path(__file__).resolve().parent
fig.savefig(out_dir / 'sensitivity.pdf', bbox_inches='tight', dpi=300)
fig.savefig(out_dir / 'sensitivity.png', bbox_inches='tight', dpi=300)
print(f"Saved: {out_dir / 'sensitivity.pdf'}")
print(f"Saved: {out_dir / 'sensitivity.png'}")
