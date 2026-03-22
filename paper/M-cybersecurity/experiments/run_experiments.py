"""
Paper M: Cybersecurity 実験実行スクリプト。

E1: 密集パターン検出性能
E2: パラメータ感度分析
E3: キャンペーン推定精度
E4: 脅威帰属精度
"""

import json
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apriori_window_suite" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation" / "python"))

from synthetic_cicids import (
    APT_PROFILES,
    TECHNIQUE_MAP,
    generate_synthetic_cicids,
)
from attack_adapter import (
    attribute_campaigns,
    estimate_campaigns,
    find_dense_attack_patterns,
    itemset_to_attack_names,
)

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = Path(__file__).parent / "figures"


def run_e1_dense_pattern_detection():
    """E1: 密集パターン検出性能。"""
    print("=" * 60)
    print("E1: Dense ATT&CK Pattern Detection")
    print("=" * 60)

    txs, gt = generate_synthetic_cicids(n_transactions=500, seed=42)

    window_size = 20
    threshold = 10
    max_length = 4

    start = time.perf_counter()
    patterns = find_dense_attack_patterns(txs, window_size, threshold, max_length)
    elapsed = (time.perf_counter() - start) * 1000

    # 統計
    singletons = {k: v for k, v in patterns.items() if len(k) == 1}
    pairs = {k: v for k, v in patterns.items() if len(k) == 2}
    triples = {k: v for k, v in patterns.items() if len(k) == 3}
    quads = {k: v for k, v in patterns.items() if len(k) == 4}

    total_intervals = sum(len(v) for v in patterns.values())

    results = {
        "experiment": "E1",
        "params": {
            "n_transactions": 500,
            "window_size": window_size,
            "threshold": threshold,
            "max_length": max_length,
        },
        "results": {
            "total_patterns": len(patterns),
            "singleton_patterns": len(singletons),
            "pair_patterns": len(pairs),
            "triple_patterns": len(triples),
            "quad_patterns": len(quads),
            "total_intervals": total_intervals,
            "elapsed_ms": round(elapsed, 2),
        },
        "top_patterns": [],
    }

    # Top patterns (multi-item)
    multi = {k: v for k, v in patterns.items() if len(k) >= 2}
    sorted_multi = sorted(multi.items(), key=lambda kv: len(kv[1]), reverse=True)
    for itemset, intervals in sorted_multi[:10]:
        results["top_patterns"].append({
            "techniques": list(itemset),
            "technique_names": itemset_to_attack_names(itemset),
            "n_intervals": len(intervals),
            "intervals": [(s, e) for s, e in intervals],
        })

    print(f"  Total patterns: {len(patterns)}")
    print(f"  Singletons: {len(singletons)}, Pairs: {len(pairs)}, "
          f"Triples: {len(triples)}, Quads: {len(quads)}")
    print(f"  Total intervals: {total_intervals}")
    print(f"  Elapsed: {elapsed:.2f} ms")

    return results, patterns


def run_e2_parameter_sensitivity():
    """E2: パラメータ感度分析。"""
    print("\n" + "=" * 60)
    print("E2: Parameter Sensitivity Analysis")
    print("=" * 60)

    txs, _ = generate_synthetic_cicids(n_transactions=500, seed=42)

    # Window size sensitivity
    window_results = []
    for w in [5, 10, 15, 20, 25, 30, 40, 50]:
        patterns = find_dense_attack_patterns(txs, w, threshold=10, max_length=3)
        multi = {k: v for k, v in patterns.items() if len(k) >= 2}
        window_results.append({
            "window_size": w,
            "total_patterns": len(patterns),
            "multi_patterns": len(multi),
            "total_intervals": sum(len(v) for v in patterns.values()),
        })
        print(f"  W={w}: {len(patterns)} patterns, {len(multi)} multi-item")

    # Threshold sensitivity
    threshold_results = []
    for th in [3, 5, 8, 10, 12, 15, 20]:
        patterns = find_dense_attack_patterns(txs, window_size=20, threshold=th, max_length=3)
        multi = {k: v for k, v in patterns.items() if len(k) >= 2}
        threshold_results.append({
            "threshold": th,
            "total_patterns": len(patterns),
            "multi_patterns": len(multi),
            "total_intervals": sum(len(v) for v in patterns.values()),
        })
        print(f"  θ={th}: {len(patterns)} patterns, {len(multi)} multi-item")

    results = {
        "experiment": "E2",
        "window_sensitivity": window_results,
        "threshold_sensitivity": threshold_results,
    }

    return results


def run_e3_campaign_estimation():
    """E3: キャンペーン推定精度。"""
    print("\n" + "=" * 60)
    print("E3: Campaign Estimation Accuracy")
    print("=" * 60)

    txs, gt = generate_synthetic_cicids(n_transactions=500, seed=42)
    patterns = find_dense_attack_patterns(txs, window_size=20, threshold=10, max_length=4)

    # 異なる overlap_threshold でのキャンペーン数
    overlap_results = []
    for alpha in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
        campaigns = estimate_campaigns(patterns, overlap_threshold=alpha)
        overlap_results.append({
            "overlap_threshold": alpha,
            "n_campaigns": len(campaigns),
            "campaigns": [{
                "id": c["campaign_id"],
                "start": c["start"],
                "end": c["end"],
                "n_techniques": len(c["techniques"]),
                "technique_names": c["technique_names"],
            } for c in campaigns],
        })
        print(f"  α={alpha}: {len(campaigns)} campaigns")

    # メイン結果 (α=0.3)
    campaigns = estimate_campaigns(patterns, overlap_threshold=0.3)

    # Ground truth との比較
    gt_campaigns = gt["campaigns"]
    gt_ranges = [(c["start_bin"], c["end_bin"]) for c in gt_campaigns]

    matched = 0
    for c in campaigns:
        for gs, ge in gt_ranges:
            if c["start"] <= ge and c["end"] >= gs:
                matched += 1
                break

    results = {
        "experiment": "E3",
        "overlap_analysis": overlap_results,
        "main_results": {
            "overlap_threshold": 0.3,
            "detected_campaigns": len(campaigns),
            "ground_truth_campaigns": len(gt_campaigns),
            "matched_campaigns": matched,
        },
        "campaigns_detail": [{
            "id": c["campaign_id"],
            "start": c["start"],
            "end": c["end"],
            "techniques": c["techniques"],
            "technique_names": c["technique_names"],
            "n_patterns": c["n_patterns"],
        } for c in campaigns],
    }

    print(f"  Detected: {len(campaigns)}, GT: {len(gt_campaigns)}, Matched: {matched}")

    return results, campaigns


def run_e4_threat_attribution():
    """E4: 脅威帰属精度。"""
    print("\n" + "=" * 60)
    print("E4: Threat Attribution Accuracy")
    print("=" * 60)

    txs, gt = generate_synthetic_cicids(n_transactions=500, seed=42)
    patterns = find_dense_attack_patterns(txs, window_size=20, threshold=10, max_length=4)
    campaigns = estimate_campaigns(patterns, overlap_threshold=0.3)
    attributed = attribute_campaigns(campaigns)

    # Ground truth のキャンペーン - APT マッピング
    gt_mapping = {}
    for c in gt["campaigns"]:
        gt_mapping[(c["start_bin"], c["end_bin"])] = c["apt_name"]

    correct = 0
    total = len(attributed)
    attribution_details = []

    for r in attributed:
        expected_apt = None
        for (gs, ge), apt in gt_mapping.items():
            if r["start"] <= ge and r["end"] >= gs:
                expected_apt = apt
                break

        is_correct = expected_apt == r["best_match"] if expected_apt else None
        if is_correct:
            correct += 1

        attribution_details.append({
            "campaign_id": r["campaign_id"],
            "start": r["start"],
            "end": r["end"],
            "predicted": r["best_match"],
            "expected": expected_apt,
            "correct": is_correct,
            "scores": r["attribution_scores"],
            "best_score": r["best_score"],
        })

        status = "OK" if is_correct else ("MISS" if is_correct is False else "N/A")
        print(f"  Campaign {r['campaign_id']}: predicted={r['best_match']}, "
              f"expected={expected_apt}, score={r['best_score']:.3f} [{status}]")

    accuracy = correct / total if total > 0 else 0.0

    results = {
        "experiment": "E4",
        "summary": {
            "total_campaigns": total,
            "correct_attributions": correct,
            "accuracy": round(accuracy, 4),
        },
        "details": attribution_details,
    }

    print(f"\n  Attribution accuracy: {correct}/{total} = {accuracy:.1%}")

    return results


def generate_figures(e1_results, e2_results, e3_results, e1_patterns):
    """実験結果の図表を生成する。"""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Figure 1: Support time series for top patterns
    fig, ax = plt.subplots(figsize=(10, 4))
    multi = {k: v for k, v in e1_patterns.items() if len(k) >= 2}
    sorted_multi = sorted(multi.items(), key=lambda kv: len(kv[1]), reverse=True)

    for idx, (itemset, intervals) in enumerate(sorted_multi[:5]):
        names = itemset_to_attack_names(itemset)
        label = "+".join(names)
        for s, e in intervals:
            ax.barh(idx, e - s + 1, left=s, height=0.6, alpha=0.7)
        ax.text(-5, idx, label, ha="right", va="center", fontsize=7)

    ax.set_xlabel("Time Bin")
    ax.set_title("Dense ATT&CK Technique Co-occurrence Intervals (Top 5)")
    ax.set_yticks([])
    plt.tight_layout()
    plt.savefig(str(FIGURES_DIR / "fig1_dense_intervals.png"), dpi=150)
    plt.close()

    # Figure 2: Parameter sensitivity heatmap
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    ws = e2_results["window_sensitivity"]
    ax1.plot([r["window_size"] for r in ws],
             [r["multi_patterns"] for r in ws], "o-", color="steelblue")
    ax1.set_xlabel("Window Size (W)")
    ax1.set_ylabel("Multi-item Dense Patterns")
    ax1.set_title("Window Size Sensitivity")

    ts = e2_results["threshold_sensitivity"]
    ax2.plot([r["threshold"] for r in ts],
             [r["multi_patterns"] for r in ts], "s-", color="coral")
    ax2.set_xlabel("Density Threshold (θ)")
    ax2.set_ylabel("Multi-item Dense Patterns")
    ax2.set_title("Threshold Sensitivity")

    plt.tight_layout()
    plt.savefig(str(FIGURES_DIR / "fig2_sensitivity.png"), dpi=150)
    plt.close()

    # Figure 3: Campaign detection and attribution summary
    fig, ax = plt.subplots(figsize=(8, 4))
    overlap_data = e3_results["overlap_analysis"]
    alphas = [r["overlap_threshold"] for r in overlap_data]
    n_camps = [r["n_campaigns"] for r in overlap_data]
    ax.bar(range(len(alphas)), n_camps, color="mediumpurple", alpha=0.8)
    ax.set_xticks(range(len(alphas)))
    ax.set_xticklabels([f"{a}" for a in alphas])
    ax.set_xlabel("Overlap Threshold (α)")
    ax.set_ylabel("Number of Campaigns")
    ax.set_title("Campaign Count vs. Overlap Threshold")
    ax.axhline(y=4, color="red", linestyle="--", alpha=0.5, label="Ground Truth (4)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(str(FIGURES_DIR / "fig3_campaign_summary.png"), dpi=150)
    plt.close()

    print(f"\nFigures saved to {FIGURES_DIR}")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # E1
    e1_results, e1_patterns = run_e1_dense_pattern_detection()
    with open(RESULTS_DIR / "e1_results.json", "w") as f:
        json.dump(e1_results, f, indent=2, ensure_ascii=False)

    # E2
    e2_results = run_e2_parameter_sensitivity()
    with open(RESULTS_DIR / "e2_results.json", "w") as f:
        json.dump(e2_results, f, indent=2, ensure_ascii=False)

    # E3
    e3_results, campaigns = run_e3_campaign_estimation()
    with open(RESULTS_DIR / "e3_results.json", "w") as f:
        json.dump(e3_results, f, indent=2, ensure_ascii=False)

    # E4
    e4_results = run_e4_threat_attribution()
    with open(RESULTS_DIR / "e4_results.json", "w") as f:
        json.dump(e4_results, f, indent=2, ensure_ascii=False)

    # Figures
    generate_figures(e1_results, e2_results, e3_results, e1_patterns)

    print("\n" + "=" * 60)
    print("All experiments completed!")
    print(f"Results: {RESULTS_DIR}")
    print(f"Figures: {FIGURES_DIR}")


if __name__ == "__main__":
    main()
