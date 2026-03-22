"""
Paper H: Dense Interval Prediction — 実験スクリプト

実験:
1. 合成データでの予測精度評価
2. IDIT 分布フィッティング比較
3. Hawkes モデル vs ベースライン (Poisson) 比較
4. 持続時間予測精度評価
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation" / "python"))
from dense_prediction import (
    DenseIntervalOccurrenceProcess,
    DensePredictionPipeline,
    DurationPredictor,
    HawkesDenseModel,
    IDITDistributionFitter,
)


def generate_synthetic_intervals(
    n_intervals: int = 20,
    base_gap: float = 30.0,
    gap_std: float = 10.0,
    base_duration: float = 8.0,
    duration_std: float = 3.0,
    self_exciting: bool = True,
    seed: int = 42,
) -> list:
    """合成密集区間列を生成する。"""
    rng = np.random.default_rng(seed)
    intervals = []
    t = 0.0

    for i in range(n_intervals):
        start = int(t)
        duration = max(1, int(rng.normal(base_duration, duration_std)))
        end = start + duration
        intervals.append((start, end))

        gap = max(1, rng.normal(base_gap, gap_std))
        if self_exciting and i > 0:
            # 自己励起: 直前の持続時間が長いほど次の間隔が短い
            gap *= max(0.3, 1.0 - 0.02 * duration)
        t = end + gap

    return intervals


def experiment_1_synthetic_prediction():
    """実験1: 合成データでの予測精度評価"""
    print("=" * 60)
    print("実験 1: 合成データでの予測精度評価")
    print("=" * 60)

    results = {}

    for n in [10, 20, 50]:
        intervals = generate_synthetic_intervals(n_intervals=n, seed=42)
        # Train/test split: 最後の2区間をテスト
        train = intervals[:-2]
        test = intervals[-2:]

        pipeline = DensePredictionPipeline(train, window_size=5)
        result = pipeline.run()

        if "hawkes_prediction" in result:
            pred_next = result["hawkes_prediction"]["mean_next"]
            actual_next = test[0][0]
            error = abs(pred_next - actual_next)
            relative_error = error / actual_next if actual_next > 0 else float("inf")

            results[f"n={n}"] = {
                "predicted_next": pred_next,
                "actual_next": actual_next,
                "absolute_error": error,
                "relative_error": relative_error,
                "hawkes_params": result["hawkes_fit"],
            }
            print(f"  n={n}: predicted={pred_next:.1f}, actual={actual_next}, "
                  f"rel_error={relative_error:.3f}")

    return results


def experiment_2_idit_distribution():
    """実験2: IDIT分布フィッティング比較"""
    print("\n" + "=" * 60)
    print("実験 2: IDIT 分布フィッティング比較")
    print("=" * 60)

    scenarios = {
        "regular": {"base_gap": 30.0, "gap_std": 5.0},
        "variable": {"base_gap": 30.0, "gap_std": 15.0},
        "clustered": {"base_gap": 15.0, "gap_std": 3.0, "self_exciting": True},
    }

    results = {}
    for name, params in scenarios.items():
        intervals = generate_synthetic_intervals(n_intervals=50, **params, seed=123)
        diop = DenseIntervalOccurrenceProcess(intervals, window_size=5)

        if diop.idit and any(v > 0 for v in diop.idit):
            fitter = IDITDistributionFitter(diop.idit)
            fit_results = fitter.fit_all()
            best = fitter.best_distribution()

            results[name] = {
                "best_distribution": best,
                "n_idit": len(diop.idit),
                "mean_idit": float(np.mean(diop.idit)),
                "cv_idit": float(np.std(diop.idit) / np.mean(diop.idit)) if np.mean(diop.idit) > 0 else 0,
                "aic_scores": {k: v.get("aic", None) for k, v in fit_results.items()},
                "ks_pvalues": {k: v.get("ks_pvalue", None) for k, v in fit_results.items()},
            }
            print(f"  {name}: best={best}, CV={results[name]['cv_idit']:.3f}")

    return results


def experiment_3_hawkes_vs_poisson():
    """実験3: Hawkes vs Poisson (ベースライン) 比較"""
    print("\n" + "=" * 60)
    print("実験 3: Hawkes vs Poisson 比較")
    print("=" * 60)

    results = {}

    for exciting in [True, False]:
        label = "self_exciting" if exciting else "poisson_like"
        intervals = generate_synthetic_intervals(
            n_intervals=30, self_exciting=exciting, seed=456
        )

        arrival_times = [float(s) for s, _ in intervals]
        T = float(intervals[-1][1]) * 1.1

        # Hawkes model
        hawkes = HawkesDenseModel()
        h_fit = hawkes.fit(arrival_times, T)

        # Poisson baseline: mu = n/T, alpha=0
        poisson_mu = len(arrival_times) / T
        poisson_ll = sum(np.log(poisson_mu) for _ in arrival_times) - poisson_mu * T

        results[label] = {
            "hawkes_ll": h_fit["log_likelihood"],
            "poisson_ll": float(poisson_ll),
            "ll_improvement": h_fit["log_likelihood"] - float(poisson_ll),
            "hawkes_alpha": h_fit["alpha"],
            "hawkes_mu": h_fit["mu"],
            "hawkes_beta": h_fit["beta"],
        }
        print(f"  {label}: Hawkes LL={h_fit['log_likelihood']:.2f}, "
              f"Poisson LL={poisson_ll:.2f}, "
              f"improvement={h_fit['log_likelihood'] - poisson_ll:.2f}")

    return results


def experiment_4_duration_prediction():
    """実験4: 持続時間予測精度評価"""
    print("\n" + "=" * 60)
    print("実験 4: 持続時間予測精度評価")
    print("=" * 60)

    intervals = generate_synthetic_intervals(n_intervals=40, seed=789)
    durations = [e - s + 5 for s, e in intervals]

    # Leave-one-out cross-validation
    errors = []
    for i in range(len(durations)):
        train = durations[:i] + durations[i + 1:]
        test_val = durations[i]

        if len(train) < 3:
            continue

        pred = DurationPredictor(train)
        result = pred.predict_duration()
        predicted = result["predicted_mean"]
        error = abs(predicted - test_val)
        errors.append(error)

    mae = float(np.mean(errors))
    rmse = float(np.sqrt(np.mean(np.array(errors) ** 2)))
    median_ae = float(np.median(errors))

    # Weibull fit on full data
    full_pred = DurationPredictor(durations)
    fit_result = full_pred.fit_weibull()

    results = {
        "n_intervals": len(durations),
        "mean_duration": float(np.mean(durations)),
        "std_duration": float(np.std(durations)),
        "mae": mae,
        "rmse": rmse,
        "median_ae": median_ae,
        "weibull_shape": fit_result["shape"],
        "weibull_scale": fit_result["scale"],
    }
    print(f"  MAE={mae:.2f}, RMSE={rmse:.2f}, MedianAE={median_ae:.2f}")
    print(f"  Weibull shape={fit_result['shape']:.3f}, scale={fit_result['scale']:.3f}")

    return results


def main():
    all_results = {}

    all_results["exp1_synthetic_prediction"] = experiment_1_synthetic_prediction()
    all_results["exp2_idit_distribution"] = experiment_2_idit_distribution()
    all_results["exp3_hawkes_vs_poisson"] = experiment_3_hawkes_vs_poisson()
    all_results["exp4_duration_prediction"] = experiment_4_duration_prediction()

    # Save results
    out_path = Path(__file__).parent / "results" / "all_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n結果を {out_path} に保存しました。")
    return all_results


if __name__ == "__main__":
    main()
