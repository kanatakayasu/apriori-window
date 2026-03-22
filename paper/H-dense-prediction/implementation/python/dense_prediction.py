"""
Dense Interval Prediction Module

密集区間の発生パターンを点過程・生存分析の枠組みでモデル化し、
次回の密集区間の発生時刻と持続時間を予測する。

概念定義:
- Dense Interval Occurrence Process (DIOP): 密集区間の発生を点過程として捉える
- Inter-Dense Interval Time (IDIT): 連続する密集区間の終了→開始の時間間隔
- Dense Duration: 密集区間の持続時間 (end - start + window_size)
"""

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats
from scipy.optimize import minimize

# Phase 1 モジュールのインポート
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python"))
from apriori_window_basket import (
    compute_dense_intervals,
    find_dense_itemsets,
    read_transactions_with_baskets,
)


# ---------------------------------------------------------------------------
# 1. Dense Interval Occurrence Process (DIOP) — 密集区間発生過程
# ---------------------------------------------------------------------------

class DenseIntervalOccurrenceProcess:
    """
    密集区間の発生系列を点過程としてモデル化する。

    入力: 密集区間リスト [(start, end), ...]
    出力: IDIT 分布, 持続時間分布, 予測
    """

    def __init__(
        self,
        intervals: List[Tuple[int, int]],
        window_size: int,
    ):
        """
        Parameters
        ----------
        intervals : list of (start, end)
            密集区間リスト（ソート済み想定）
        window_size : int
            密集区間検出に使ったウィンドウサイズ
        """
        self.intervals = sorted(intervals)
        self.window_size = window_size
        self.arrival_times = [s for s, _ in self.intervals]
        self.durations = [e - s + window_size for s, e in self.intervals]
        self.idit = self._compute_idit()

    def _compute_idit(self) -> List[float]:
        """
        Inter-Dense Interval Time を計算する。
        IDIT[i] = intervals[i+1].start - intervals[i].end - window_size
        （前の密集区間の実質終了から次の密集区間の開始までの間隔）
        """
        if len(self.intervals) < 2:
            return []
        idit = []
        for i in range(len(self.intervals) - 1):
            _, end_i = self.intervals[i]
            start_next, _ = self.intervals[i + 1]
            gap = start_next - (end_i + self.window_size)
            idit.append(max(0.0, float(gap)))
        return idit

    def summary_statistics(self) -> Dict[str, Any]:
        """DIOP の要約統計量を返す。"""
        result: Dict[str, Any] = {
            "n_intervals": len(self.intervals),
            "total_span": 0,
            "mean_duration": 0.0,
            "std_duration": 0.0,
            "mean_idit": 0.0,
            "std_idit": 0.0,
            "cv_idit": 0.0,
        }
        if not self.intervals:
            return result
        result["total_span"] = self.intervals[-1][1] - self.intervals[0][0]
        if self.durations:
            result["mean_duration"] = float(np.mean(self.durations))
            result["std_duration"] = float(np.std(self.durations, ddof=1)) if len(self.durations) > 1 else 0.0
        if self.idit:
            result["mean_idit"] = float(np.mean(self.idit))
            result["std_idit"] = float(np.std(self.idit, ddof=1)) if len(self.idit) > 1 else 0.0
            if result["mean_idit"] > 0:
                result["cv_idit"] = result["std_idit"] / result["mean_idit"]
        return result


# ---------------------------------------------------------------------------
# 2. IDIT 分布フィッティング
# ---------------------------------------------------------------------------

class IDITDistributionFitter:
    """
    IDIT (Inter-Dense Interval Time) の分布をフィットする。

    候補分布:
    - 指数分布 (Exponential): ポアソン過程仮定
    - ワイブル分布 (Weibull): 経時変化を許容
    - ガンマ分布 (Gamma): 柔軟な形状
    - 対数正規分布 (Log-normal): 右裾が重い場合
    """

    DISTRIBUTIONS = {
        "exponential": stats.expon,
        "weibull": stats.weibull_min,
        "gamma": stats.gamma,
        "lognormal": stats.lognorm,
    }

    def __init__(self, idit_values: Sequence[float]):
        if not idit_values:
            raise ValueError("IDIT values must be non-empty")
        self.data = np.array([v for v in idit_values if v > 0])
        if len(self.data) == 0:
            raise ValueError("All IDIT values are zero; cannot fit distribution")
        self.fit_results: Dict[str, Dict[str, Any]] = {}

    def fit_all(self) -> Dict[str, Dict[str, Any]]:
        """全候補分布をフィットし、AIC/BIC で比較する。"""
        for name, dist in self.DISTRIBUTIONS.items():
            try:
                params = dist.fit(self.data)
                log_likelihood = np.sum(dist.logpdf(self.data, *params))
                k = len(params)
                n = len(self.data)
                aic = 2 * k - 2 * log_likelihood
                bic = k * np.log(n) - 2 * log_likelihood

                # KS検定
                ks_stat, ks_pvalue = stats.kstest(self.data, dist.cdf, args=params)

                self.fit_results[name] = {
                    "params": params,
                    "log_likelihood": float(log_likelihood),
                    "aic": float(aic),
                    "bic": float(bic),
                    "ks_statistic": float(ks_stat),
                    "ks_pvalue": float(ks_pvalue),
                }
            except Exception as e:
                self.fit_results[name] = {"error": str(e)}

        return self.fit_results

    def best_distribution(self, criterion: str = "aic") -> Optional[str]:
        """AIC or BIC で最良の分布を選択する。"""
        if not self.fit_results:
            self.fit_all()
        valid = {k: v for k, v in self.fit_results.items() if "error" not in v}
        if not valid:
            return None
        return min(valid, key=lambda k: valid[k][criterion])


# ---------------------------------------------------------------------------
# 3. Hawkes-Dense モデル — 自己励起点過程による発生時刻予測
# ---------------------------------------------------------------------------

class HawkesDenseModel:
    """
    Hawkes 過程による密集区間の発生時刻予測。

    強度関数:
        lambda(t) = mu + sum_{t_i < t} alpha * beta * exp(-beta * (t - t_i))

    mu: ベースライン強度
    alpha: 自己励起パラメータ (0 < alpha < 1 で定常)
    beta: 減衰率
    """

    def __init__(self, mu: float = 0.1, alpha: float = 0.5, beta: float = 1.0):
        self.mu = mu
        self.alpha = alpha
        self.beta = beta
        self._fitted = False

    def intensity(self, t: float, history: Sequence[float]) -> float:
        """時刻 t での条件付き強度を計算する。"""
        base = self.mu
        excitation = sum(
            self.alpha * self.beta * math.exp(-self.beta * (t - ti))
            for ti in history
            if ti < t
        )
        return base + excitation

    def log_likelihood(self, events: Sequence[float], T: float) -> float:
        """
        対数尤度を計算する。

        Parameters
        ----------
        events : 発生時刻列
        T : 観測期間の長さ
        """
        events = sorted(events)
        if not events:
            return -self.mu * T

        ll = 0.0
        for i, ti in enumerate(events):
            lam = self.intensity(ti, events[:i])
            if lam > 0:
                ll += math.log(lam)
            else:
                ll += math.log(1e-10)

        # 補償項
        compensator = self.mu * T
        for ti in events:
            compensator += self.alpha * (1 - math.exp(-self.beta * (T - ti)))

        ll -= compensator
        return ll

    def fit(self, events: Sequence[float], T: Optional[float] = None) -> Dict[str, float]:
        """
        最尤推定でパラメータを推定する。

        Parameters
        ----------
        events : 発生時刻列
        T : 観測期間の長さ（省略時は最大時刻 * 1.1）
        """
        events = sorted(events)
        if not events:
            raise ValueError("No events to fit")

        if T is None:
            T = events[-1] * 1.1

        def neg_ll(params):
            mu, alpha, beta = params
            if mu <= 0 or alpha <= 0 or alpha >= 1 or beta <= 0:
                return 1e10
            self.mu, self.alpha, self.beta = mu, alpha, beta
            return -self.log_likelihood(events, T)

        result = minimize(
            neg_ll,
            x0=[0.1, 0.3, 1.0],
            method="Nelder-Mead",
            options={"maxiter": 5000, "xatol": 1e-8, "fatol": 1e-8},
        )

        self.mu, self.alpha, self.beta = result.x
        self._fitted = True

        return {
            "mu": float(self.mu),
            "alpha": float(self.alpha),
            "beta": float(self.beta),
            "log_likelihood": float(-result.fun),
            "converged": bool(result.success),
        }

    def predict_next(
        self,
        history: Sequence[float],
        n_samples: int = 1000,
        max_time: float = 1000.0,
    ) -> Dict[str, float]:
        """
        Ogata の thinning algorithm で次回発生時刻を予測する。

        Returns
        -------
        dict with keys:
            mean_next: 予測次回発生時刻の平均
            std_next: 標準偏差
            median_next: 中央値
        """
        if not self._fitted:
            raise RuntimeError("Model must be fitted first")

        history = sorted(history)
        if not history:
            raise ValueError("History must be non-empty")

        t_last = history[-1]
        rng = np.random.default_rng(42)
        next_times = []

        for _ in range(n_samples):
            t = t_last
            found = False
            for _ in range(10000):
                lam_bar = self.intensity(t, history) * 1.5 + 1e-6
                dt = rng.exponential(1.0 / lam_bar)
                t += dt
                if t > t_last + max_time:
                    break
                lam_t = self.intensity(t, history)
                u = rng.uniform()
                if u <= lam_t / lam_bar:
                    next_times.append(t)
                    found = True
                    break
            if not found:
                next_times.append(t_last + max_time)

        arr = np.array(next_times)
        return {
            "mean_next": float(np.mean(arr)),
            "std_next": float(np.std(arr)),
            "median_next": float(np.median(arr)),
            "ci_lower": float(np.percentile(arr, 5)),
            "ci_upper": float(np.percentile(arr, 95)),
        }


# ---------------------------------------------------------------------------
# 4. 持続時間予測 — 生存分析ベース
# ---------------------------------------------------------------------------

class DurationPredictor:
    """
    密集区間の持続時間を生存分析の枠組みで予測する。

    手法:
    - ワイブル回帰 (parametric survival)
    - 経験的生存関数 (Kaplan-Meier 的)
    """

    def __init__(self, durations: Sequence[float]):
        if not durations:
            raise ValueError("Durations must be non-empty")
        self.durations = np.array(durations, dtype=float)
        self.fit_result: Optional[Dict[str, Any]] = None

    def fit_weibull(self) -> Dict[str, Any]:
        """ワイブル分布で持続時間をフィットする。"""
        shape, loc, scale = stats.weibull_min.fit(self.durations, floc=0)
        log_likelihood = np.sum(stats.weibull_min.logpdf(self.durations, shape, loc=loc, scale=scale))

        self.fit_result = {
            "distribution": "weibull",
            "shape": float(shape),
            "scale": float(scale),
            "mean_duration": float(scale * math.gamma(1 + 1 / shape)),
            "median_duration": float(scale * (math.log(2)) ** (1 / shape)),
            "log_likelihood": float(log_likelihood),
        }
        return self.fit_result

    def predict_duration(self, confidence: float = 0.9) -> Dict[str, float]:
        """次回の密集区間持続時間を予測する。"""
        if self.fit_result is None:
            self.fit_weibull()

        shape = self.fit_result["shape"]
        scale = self.fit_result["scale"]
        dist = stats.weibull_min(shape, loc=0, scale=scale)

        return {
            "predicted_mean": float(dist.mean()),
            "predicted_median": float(dist.median()),
            "ci_lower": float(dist.ppf((1 - confidence) / 2)),
            "ci_upper": float(dist.ppf((1 + confidence) / 2)),
        }

    def survival_function(self, t_values: Sequence[float]) -> List[float]:
        """時刻 t における生存確率 S(t) = P(Duration > t) を返す。"""
        if self.fit_result is None:
            self.fit_weibull()
        shape = self.fit_result["shape"]
        scale = self.fit_result["scale"]
        return [float(stats.weibull_min.sf(t, shape, loc=0, scale=scale)) for t in t_values]

    def empirical_survival(self) -> Tuple[np.ndarray, np.ndarray]:
        """経験的生存関数 (Kaplan-Meier 風) を返す。"""
        sorted_d = np.sort(self.durations)
        n = len(sorted_d)
        survival = np.array([(n - i) / n for i in range(n)])
        return sorted_d, survival


# ---------------------------------------------------------------------------
# 5. 統合パイプライン
# ---------------------------------------------------------------------------

class DensePredictionPipeline:
    """
    密集区間マイニング → 予測の統合パイプライン。

    Phase 1 (apriori_window) の出力を受け取り、
    DIOP, IDIT分布フィッティング, Hawkes予測, 持続時間予測を一括実行する。
    """

    def __init__(
        self,
        intervals: List[Tuple[int, int]],
        window_size: int,
        itemset: Optional[Tuple[int, ...]] = None,
    ):
        self.intervals = sorted(intervals)
        self.window_size = window_size
        self.itemset = itemset
        self.diop: Optional[DenseIntervalOccurrenceProcess] = None
        self.idit_fitter: Optional[IDITDistributionFitter] = None
        self.hawkes: Optional[HawkesDenseModel] = None
        self.duration_predictor: Optional[DurationPredictor] = None

    def run(self) -> Dict[str, Any]:
        """全分析を実行して結果を返す。"""
        result: Dict[str, Any] = {
            "itemset": list(self.itemset) if self.itemset else None,
            "n_intervals": len(self.intervals),
        }

        if len(self.intervals) < 3:
            result["error"] = "Not enough intervals for prediction (need >= 3)"
            return result

        # Step 1: DIOP
        self.diop = DenseIntervalOccurrenceProcess(self.intervals, self.window_size)
        result["summary"] = self.diop.summary_statistics()

        # Step 2: IDIT 分布フィッティング
        if self.diop.idit and any(v > 0 for v in self.diop.idit):
            try:
                self.idit_fitter = IDITDistributionFitter(self.diop.idit)
                result["idit_fit"] = self.idit_fitter.fit_all()
                result["best_idit_distribution"] = self.idit_fitter.best_distribution()
            except ValueError:
                result["idit_fit"] = {"error": "Could not fit IDIT distribution"}

        # Step 3: Hawkes 予測
        arrival_times = [float(s) for s, _ in self.intervals]
        try:
            self.hawkes = HawkesDenseModel()
            fit_result = self.hawkes.fit(arrival_times)
            result["hawkes_fit"] = fit_result
            prediction = self.hawkes.predict_next(arrival_times)
            result["hawkes_prediction"] = prediction
        except Exception as e:
            result["hawkes_fit"] = {"error": str(e)}

        # Step 4: 持続時間予測
        durations = self.diop.durations
        if durations and all(d > 0 for d in durations):
            try:
                self.duration_predictor = DurationPredictor(durations)
                result["duration_fit"] = self.duration_predictor.fit_weibull()
                result["duration_prediction"] = self.duration_predictor.predict_duration()
            except Exception as e:
                result["duration_fit"] = {"error": str(e)}

        return result


# ---------------------------------------------------------------------------
# 6. メイン実行
# ---------------------------------------------------------------------------

def run_prediction_pipeline(
    transaction_path: str,
    window_size: int = 5,
    threshold: int = 3,
    max_length: int = 3,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    トランザクションファイルから密集区間を検出し、予測パイプラインを実行する。

    Parameters
    ----------
    transaction_path : トランザクションファイルパス
    window_size : ウィンドウサイズ
    threshold : 密集判定閾値
    max_length : アイテムセットの最大長
    top_k : 分析対象の上位アイテムセット数

    Returns
    -------
    dict : 全アイテムセットの予測結果
    """
    transactions = read_transactions_with_baskets(transaction_path)
    frequents = find_dense_itemsets(transactions, window_size, threshold, max_length)

    # 区間数でソートして上位を選択
    sorted_itemsets = sorted(
        frequents.items(), key=lambda kv: len(kv[1]), reverse=True
    )[:top_k]

    results: Dict[str, Any] = {
        "parameters": {
            "window_size": window_size,
            "threshold": threshold,
            "max_length": max_length,
            "n_transactions": len(transactions),
        },
        "predictions": [],
    }

    for itemset, intervals in sorted_itemsets:
        pipeline = DensePredictionPipeline(intervals, window_size, itemset)
        pred = pipeline.run()
        results["predictions"].append(pred)

    return results


def main():
    """コマンドライン実行。"""
    if len(sys.argv) < 2:
        print("Usage: python dense_prediction.py <transaction_file> [window_size] [threshold]")
        sys.exit(1)

    path = sys.argv[1]
    ws = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    th = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    results = run_prediction_pipeline(path, ws, th)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
