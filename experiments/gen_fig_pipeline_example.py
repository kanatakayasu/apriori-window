"""
Generate a pipeline example figure for the paper.

Shows support time series for a planted pattern with change points,
event windows (planted vs decoy), and attribution results.

Output: paper/manuscript/fig/pipeline_example.pdf
"""
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
_python_dir = str(Path(_root) / "apriori_window_suite" / "python")
for p in [_root, _python_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from experiments.src.gen_synthetic import (
    DecoyEvent,
    PlantedSignal,
    SyntheticConfig,
    generate_synthetic,
)
from apriori_window_basket import (
    compute_item_timestamps_map,
    find_dense_itemsets,
    read_text_file_as_2d_vec_of_integers,
)
from event_attribution import (
    AttributionConfig,
    compute_support_series,
    compute_support_series_all,
    detect_change_points,
    read_events,
    run_attribution_pipeline,
)


def main():
    # ---------------------------------------------------------------
    # 1. Generate synthetic data (E1a-style, seed=0)
    # ---------------------------------------------------------------
    config = SyntheticConfig(
        n_transactions=5000,
        n_items=200,
        p_base=0.03,
        planted_signals=[
            PlantedSignal([1001, 1002], "E1", "Sale", 800, 1200, boost_factor=0.5),
            PlantedSignal([1003, 1004], "E2", "Holiday", 2000, 2400, boost_factor=0.5),
            PlantedSignal([1005, 1006], "E3", "Campaign", 3200, 3600, boost_factor=0.5),
        ],
        decoy_events=[
            DecoyEvent("D1", "Decoy_1", 1500, 1700),
            DecoyEvent("D2", "Decoy_2", 4000, 4200),
        ],
        seed=0,
    )

    out_dir = str(Path(__file__).resolve().parent / "data" / "fig_pipeline_example")
    info = generate_synthetic(config, out_dir)

    # ---------------------------------------------------------------
    # 2. Run Phase 1
    # ---------------------------------------------------------------
    window_size = 50
    min_support = 3
    max_length = 2

    transactions = read_text_file_as_2d_vec_of_integers(info["txn_path"])
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)

    # ---------------------------------------------------------------
    # 3. Compute support time series for the target pattern
    # ---------------------------------------------------------------
    target_pattern = (1001, 1002)
    support_series_map = compute_support_series_all(
        item_transaction_map, frequents, transactions, window_size
    )

    if target_pattern not in support_series_map:
        print(f"ERROR: Pattern {target_pattern} not found in frequents.")
        print(f"Available patterns with 1001: "
              f"{[p for p in support_series_map if 1001 in p]}")
        sys.exit(1)

    series = support_series_map[target_pattern]
    n_points = len(series)
    t_axis = np.arange(n_points)

    # ---------------------------------------------------------------
    # 4. Detect change points
    # ---------------------------------------------------------------
    change_points = detect_change_points(
        series, method="threshold_crossing", threshold=min_support
    )

    # ---------------------------------------------------------------
    # 5. Run attribution pipeline to get significant results
    # ---------------------------------------------------------------
    events = read_events(info["events_path"])
    attr_config = AttributionConfig(
        min_support_range=5,
        n_permutations=5000,
        alpha=0.20,
        correction_method="bh",
        global_correction=True,
        deduplicate_overlap=True,
        seed=0,
    )
    sig_results = run_attribution_pipeline(
        frequents, support_series_map, events, window_size, min_support, attr_config
    )

    # Filter to target pattern
    target_results = [r for r in sig_results if r.pattern == target_pattern]
    print(f"Pattern {target_pattern}: {len(target_results)} significant attributions")
    for r in target_results:
        print(f"  -> {r.event_name} (t={r.change_time}, dir={r.change_direction}, "
              f"p_adj={r.adjusted_p_value:.4f})")

    # ---------------------------------------------------------------
    # 6. Create figure
    # ---------------------------------------------------------------
    # Publication-quality settings for IEEE single column (~3.5 in)
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 8,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,
    })

    fig, ax = plt.subplots(figsize=(3.5, 2.2))

    # Plot support time series
    ax.plot(t_axis, series, color="black", linewidth=0.6, zorder=3)

    # Threshold line
    ax.axhline(y=min_support, color="gray", linestyle=":", linewidth=0.5,
               zorder=2)

    # Event windows
    planted_events = [e for e in events if e.event_id.startswith("E")]
    decoy_events_list = [e for e in events if e.event_id.startswith("D")]

    s_max = max(series)
    y_max = s_max * 1.25  # extra room for labels at top

    # Draw event rectangles and labels
    # Use two label rows to avoid overlap: planted at top, decoy slightly below
    label_y_planted = y_max * 0.97
    label_y_decoy = y_max * 0.88

    for e in planted_events:
        ax.axvspan(e.start, e.end, alpha=0.18, color="#4393E5", zorder=1)
        mid = (e.start + e.end) / 2
        ax.text(mid, label_y_planted, e.event_id + ": " + e.name,
                ha="center", va="top", fontsize=5.5, color="#2060A0",
                fontweight="bold")

    for e in decoy_events_list:
        ax.axvspan(e.start, e.end, alpha=0.12, color="#AAAAAA", zorder=1)
        mid = (e.start + e.end) / 2
        ax.text(mid, label_y_decoy, e.event_id,
                ha="center", va="top", fontsize=5, color="#777777",
                fontstyle="italic")

    # Change points as vertical dashed lines with small triangular markers
    for cp in change_points:
        color = "#D62728" if cp.direction == "up" else "#FF7F0E"
        ax.axvline(x=cp.time, color=color, linestyle="--", linewidth=0.6,
                   alpha=0.7, zorder=4)
        # Small triangle at the threshold crossing
        marker = "^" if cp.direction == "up" else "v"
        ax.plot(cp.time, series[cp.time], marker=marker, markersize=4,
                color=color, zorder=5, markeredgewidth=0.3, markeredgecolor="white")

    # Annotate significant attribution: arrow from label to change point
    for r in target_results:
        # Place annotation to the right, at mid-height
        if r.change_direction == "up":
            text_x = r.change_time - 350
            text_y = s_max * 0.55
        else:
            text_x = r.change_time + 150
            text_y = s_max * 0.55
        ax.annotate(
            f"$p_{{\\mathrm{{adj}}}}={r.adjusted_p_value:.2f}$\n"
            f"$\\rightarrow$ {r.event_name}",
            xy=(r.change_time, series[r.change_time]),
            xytext=(text_x, text_y),
            fontsize=5.5,
            color="#D62728",
            arrowprops=dict(arrowstyle="->", color="#D62728", lw=0.6,
                            connectionstyle="arc3,rad=0.2"),
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      edgecolor="#D62728", linewidth=0.4, alpha=0.85),
            zorder=6,
        )

    # Labels and formatting
    ax.set_xlabel("Transaction index $t$")
    ax.set_ylabel("Support $s_P(t)$")
    ax.set_xlim(0, n_points)
    ax.set_ylim(0, y_max)

    # Legend (center-right, away from data which is on the left)
    legend_elements = [
        mpatches.Patch(facecolor="#4393E5", alpha=0.18, label="Planted event"),
        mpatches.Patch(facecolor="#AAAAAA", alpha=0.12, label="Decoy event"),
        plt.Line2D([0], [0], color="#D62728", linestyle="--", linewidth=0.6,
                   marker="^", markersize=3, label="Change pt. (up)"),
        plt.Line2D([0], [0], color="#FF7F0E", linestyle="--", linewidth=0.6,
                   marker="v", markersize=3, label="Change pt. (down)"),
        plt.Line2D([0], [0], color="gray", linestyle=":", linewidth=0.5,
                   label=f"$\\theta={min_support}$"),
    ]
    ax.legend(handles=legend_elements, loc="center right", framealpha=0.9,
              edgecolor="lightgray", fontsize=5, handlelength=1.5,
              borderpad=0.4, labelspacing=0.3)

    ax.set_title(f"Pattern $({target_pattern[0]},\\,{target_pattern[1]})$",
                 fontsize=9, pad=3)

    plt.tight_layout()

    # Save
    out_path = Path(_root) / "paper" / "manuscript" / "fig" / "pipeline_example.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path))
    print(f"Saved figure to {out_path}")
    plt.close()


if __name__ == "__main__":
    main()
