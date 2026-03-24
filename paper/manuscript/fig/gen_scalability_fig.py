#!/usr/bin/env python3
"""Generate scalability figure (2 panels) for IEEE-format paper."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from pathlib import Path

# ---------- data ----------

# Table IX: Data Size Scaling
N_labels = ['1K', '5K', '10K', '50K', '100K', '500K', '1M']
N_vals   = [1e3, 5e3, 1e4, 5e4, 1e5, 5e5, 1e6]
phase1   = [0.2, 0.9, 1.8, 9.5, 19.2, 102, 217]
attrib   = [0.01, 0.1, 0.3, 2.1, 5.1, 53, 154]
total    = [0.2, 1.0, 2.1, 11.6, 24.4, 155, 370]

# Table X: Event Count Scaling
E_vals      = [1, 3, 5, 10, 20]
attrib_ms   = [7, 28, 57, 128, 678]
total_s     = [0.9, 0.9, 1.0, 1.1, 1.8]
f1          = [1.00, 1.00, 0.80, 0.91, 0.36]

# ---------- style ----------

plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 7,
    'axes.labelsize': 8,
    'axes.titlesize': 8,
    'legend.fontsize': 6.5,
    'xtick.labelsize': 6.5,
    'ytick.labelsize': 6.5,
    'lines.linewidth': 1.2,
    'lines.markersize': 4,
})

C_PHASE1 = '#1f77b4'   # blue
C_ATTRIB = '#ff7f0e'   # orange
C_TOTAL  = '#2ca02c'   # green
C_F1     = '#d62728'    # red
C_REF    = '#888888'

fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.16, 2.8))

# ===== Panel (a): Data Size Scaling (log-log) =====

ax_a.loglog(N_vals, phase1, 'o-',  color=C_PHASE1, label='Phase 1')
ax_a.loglog(N_vals, attrib, 's--', color=C_ATTRIB, label='Attribution')
ax_a.loglog(N_vals, total,  'D-',  color=C_TOTAL,  label='Total')

# O(N) reference line — anchored to pass through (1e3, 0.2)
ref_x = np.array([1e3, 1e6])
ref_y = 0.2 * (ref_x / 1e3)
ax_a.loglog(ref_x, ref_y, '--', color=C_REF, linewidth=0.8, label='$O(N)$ ref.')

ax_a.set_xlabel('Number of transactions $N$')
ax_a.set_ylabel('Time (s)')
ax_a.set_title('(a) Data Size $N$')
ax_a.legend(loc='upper left', frameon=False)

# Custom x-tick labels
ax_a.set_xticks(N_vals)
ax_a.set_xticklabels(N_labels)
ax_a.xaxis.set_minor_formatter(ticker.NullFormatter())

ax_a.spines['top'].set_visible(False)
ax_a.spines['right'].set_visible(False)

# ===== Panel (b): Event Count Scaling (x linear, y log) =====

ax_b.set_yscale('log')
ln1 = ax_b.plot(E_vals, attrib_ms, 'o-', color=C_ATTRIB, label='Attribution (ms)')
ax_b.set_xlabel('Number of events $|\\mathcal{E}|$')
ax_b.set_ylabel('Attribution time (ms)')
ax_b.set_title('(b) Event Count $|\\mathcal{E}|$')

ax_b.set_xticks(E_vals)

ax_b.spines['top'].set_visible(False)

# Right y-axis for F1
ax_b2 = ax_b.twinx()
ln2 = ax_b2.plot(E_vals, f1, 's--', color=C_F1, label='F1')
ax_b2.set_ylabel('F1 Score')
ax_b2.set_ylim(0, 1.05)
ax_b2.spines['top'].set_visible(False)

# Combined legend
lns = ln1 + ln2
labs = [l.get_label() for l in lns]
ax_b.legend(lns, labs, loc='center left', frameon=False)

# ---------- save ----------

plt.tight_layout()

out_dir = Path(__file__).resolve().parent
for ext in ('pdf', 'png'):
    out = out_dir / f'scalability.{ext}'
    fig.savefig(out, bbox_inches='tight', dpi=300)
    print(f'Saved: {out}')

plt.close(fig)
