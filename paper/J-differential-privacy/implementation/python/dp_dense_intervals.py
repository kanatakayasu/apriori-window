"""
Differentially Private Dense Interval Mining (DP-DIM)

差分プライバシー密集区間マイニング: スライディングウィンドウ密集区間検出に
差分プライバシー保証を付与する。

Key concepts:
  - Window Sensitivity (窓感度): ウィンドウカウントクエリに対する
    1レコード追加/削除の最大影響量。
  - DP Dense Interval (DP密集区間): ノイズ付きカウントが閾値を超える
    時間区間で、(epsilon, delta)-差分プライバシーを満たす。
  - Threshold Stability (閾値安定性): ノイズ後も閾値判定が反転しにくい
    条件。安定マージンを導入。
  - Privacy Budget Composition (プライバシ予算合成): 複数ウィンドウクエリ
    にわたる逐次合成・高度合成定理。

Author: Paper J pipeline
Date: 2026-03-22
"""

import json
import math
import sys
import time
from bisect import bisect_left, bisect_right
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Import Phase 1 utilities
# ---------------------------------------------------------------------------
sys.path.insert(
    0, str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python")
)
from apriori_window_basket import (
    compute_dense_intervals,
    compute_dense_intervals_with_candidates,
    generate_candidates,
    intersect_interval_lists,
    intersect_sorted_lists,
    prune_candidates,
    read_transactions_with_baskets,
    compute_item_basket_map,
    basket_ids_to_transaction_ids,
)


# ============================================================================
# 1. Window Sensitivity (窓感度)
# ============================================================================

def compute_window_sensitivity(window_size: int) -> int:
    """
    ウィンドウカウントクエリの感度を計算する。

    1つのトランザクションを追加/削除すると、そのトランザクションを含む
    すべてのウィンドウに影響する。各ウィンドウにおけるカウント変化は最大1。
    しかし1つのトランザクションは最大1つのウィンドウ位置にしか影響しない
    (ウィンドウは左端位置 l で定義され、トランザクション t は
    l <= t <= l + W のウィンドウに含まれる)。

    単一ウィンドウクエリの感度 = 1。
    全ウィンドウにわたるグローバル感度 = 1 (各ウィンドウは独立にカウント)。

    Parameters
    ----------
    window_size : int
        ウィンドウサイズ W

    Returns
    -------
    int
        グローバル感度 Delta_f
    """
    # 単一アイテムの場合、1トランザクションの追加/削除で
    # 各ウィンドウカウントは最大1変化する
    return 1


def compute_itemset_window_sensitivity(itemset_size: int) -> int:
    """
    アイテムセットのウィンドウカウントクエリ感度。

    k-アイテムセットの共起カウントにおいても、1トランザクションの
    追加/削除で各ウィンドウカウントは最大1しか変化しない。

    Parameters
    ----------
    itemset_size : int
        アイテムセットのサイズ k

    Returns
    -------
    int
        グローバル感度
    """
    return 1


# ============================================================================
# 2. Laplace Mechanism for Window Counts
# ============================================================================

def add_laplace_noise(
    count: int,
    sensitivity: int,
    epsilon: float,
    rng: Optional[np.random.Generator] = None,
) -> float:
    """
    ラプラスメカニズムでカウントにノイズを付加する。

    Parameters
    ----------
    count : int
        真のカウント
    sensitivity : int
        クエリ感度
    epsilon : float
        プライバシーパラメータ
    rng : np.random.Generator, optional
        乱数生成器

    Returns
    -------
    float
        ノイズ付きカウント
    """
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    if rng is None:
        rng = np.random.default_rng()
    scale = sensitivity / epsilon
    noise = rng.laplace(0, scale)
    return count + noise


def add_gaussian_noise(
    count: int,
    sensitivity: int,
    epsilon: float,
    delta: float,
    rng: Optional[np.random.Generator] = None,
) -> float:
    """
    ガウスメカニズムでカウントにノイズを付加する ((epsilon, delta)-DP)。

    sigma = sensitivity * sqrt(2 * ln(1.25/delta)) / epsilon

    Parameters
    ----------
    count : int
        真のカウント
    sensitivity : int
        クエリ感度
    epsilon : float
        プライバシーパラメータ
    delta : float
        失敗確率パラメータ
    rng : np.random.Generator, optional
        乱数生成器

    Returns
    -------
    float
        ノイズ付きカウント
    """
    if epsilon <= 0 or delta <= 0 or delta >= 1:
        raise ValueError("epsilon must be positive, 0 < delta < 1")
    if rng is None:
        rng = np.random.default_rng()
    sigma = sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon
    noise = rng.normal(0, sigma)
    return count + noise


# ============================================================================
# 3. Privacy Budget Composition (プライバシ予算合成)
# ============================================================================

class PrivacyAccountant:
    """
    プライバシ予算管理。逐次合成・高度合成をサポート。

    Attributes
    ----------
    total_epsilon : float
        消費済みプライバシ予算 (逐次合成)
    total_delta : float
        消費済み delta
    queries : List[Tuple[float, float]]
        (epsilon_i, delta_i) のログ
    """

    def __init__(self, budget_epsilon: float, budget_delta: float = 0.0):
        self.budget_epsilon = budget_epsilon
        self.budget_delta = budget_delta
        self.total_epsilon = 0.0
        self.total_delta = 0.0
        self.queries: List[Tuple[float, float]] = []

    def consume(self, epsilon: float, delta: float = 0.0) -> None:
        """予算を消費する。超過時は例外。"""
        self.total_epsilon += epsilon
        self.total_delta += delta
        self.queries.append((epsilon, delta))
        if self.total_epsilon > self.budget_epsilon + 1e-12:
            raise PrivacyBudgetExhausted(
                f"Budget exhausted: used {self.total_epsilon:.6f} > "
                f"budget {self.budget_epsilon:.6f}"
            )
        if self.total_delta > self.budget_delta + 1e-12 and self.budget_delta > 0:
            raise PrivacyBudgetExhausted(
                f"Delta budget exhausted: used {self.total_delta:.6f} > "
                f"budget {self.budget_delta:.6f}"
            )

    def remaining_epsilon(self) -> float:
        return max(0.0, self.budget_epsilon - self.total_epsilon)

    def remaining_delta(self) -> float:
        return max(0.0, self.budget_delta - self.total_delta)

    def advanced_composition_epsilon(self, k: int, delta_prime: float) -> float:
        """
        高度合成定理によるk回クエリの合計 epsilon。

        各クエリが epsilon_0-DP のとき:
          total_epsilon = epsilon_0 * sqrt(2k * ln(1/delta_prime)) + k * epsilon_0 * (e^{epsilon_0} - 1)

        Parameters
        ----------
        k : int
            クエリ回数
        delta_prime : float
            合成の失敗確率

        Returns
        -------
        float
            合計 epsilon
        """
        if not self.queries:
            return 0.0
        eps0 = self.queries[0][0]  # 均一 epsilon を仮定
        term1 = eps0 * math.sqrt(2 * k * math.log(1.0 / delta_prime))
        term2 = k * eps0 * (math.exp(eps0) - 1)
        return term1 + term2

    def num_queries(self) -> int:
        return len(self.queries)


class PrivacyBudgetExhausted(Exception):
    """プライバシ予算超過例外。"""
    pass


# ============================================================================
# 4. Threshold Stability (閾値安定性)
# ============================================================================

def compute_stability_margin(
    sensitivity: int,
    epsilon: float,
    confidence: float = 0.95,
) -> float:
    """
    閾値安定性マージンを計算する。

    ラプラスノイズのもとで、真のカウントが閾値から stability_margin 以上
    離れていれば、confidence の確率で閾値判定が反転しない。

    Laplace(0, b) で |noise| < b * ln(1/(1-p)) となる確率が p。
    b = sensitivity / epsilon。

    Parameters
    ----------
    sensitivity : int
        クエリ感度
    epsilon : float
        プライバシーパラメータ
    confidence : float
        信頼度 (default: 0.95)

    Returns
    -------
    float
        安定性マージン
    """
    b = sensitivity / epsilon
    return b * math.log(1.0 / (1.0 - confidence))


def is_threshold_stable(
    noisy_count: float,
    threshold: int,
    stability_margin: float,
) -> bool:
    """
    閾値判定が安定かどうかを判定する。

    |noisy_count - threshold| >= stability_margin なら安定。

    Parameters
    ----------
    noisy_count : float
        ノイズ付きカウント
    threshold : int
        密集閾値
    stability_margin : float
        安定性マージン

    Returns
    -------
    bool
        安定なら True
    """
    return abs(noisy_count - threshold) >= stability_margin


# ============================================================================
# 5. DP Dense Interval Detection
# ============================================================================

def compute_dp_window_count(
    timestamps: Sequence[int],
    window_left: int,
    window_size: int,
    epsilon_per_query: float,
    sensitivity: int = 1,
    rng: Optional[np.random.Generator] = None,
) -> float:
    """
    単一ウィンドウのDP付きカウントを返す。

    Parameters
    ----------
    timestamps : Sequence[int]
        ソート済みタイムスタンプ列
    window_left : int
        ウィンドウ左端
    window_size : int
        ウィンドウサイズ
    epsilon_per_query : float
        このクエリに割り当てる epsilon
    sensitivity : int
        感度 (default: 1)
    rng : np.random.Generator, optional

    Returns
    -------
    float
        ノイズ付きカウント
    """
    start_idx = bisect_left(timestamps, window_left)
    end_idx = bisect_right(timestamps, window_left + window_size)
    true_count = end_idx - start_idx
    return add_laplace_noise(true_count, sensitivity, epsilon_per_query, rng)


def compute_dp_dense_intervals(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
    epsilon: float,
    mechanism: str = "laplace",
    delta: float = 1e-6,
    stability_confidence: float = 0.9,
    seed: Optional[int] = None,
) -> Tuple[List[Tuple[int, int]], PrivacyAccountant]:
    """
    差分プライバシー付き密集区間検出。

    全ウィンドウ位置でノイズ付きカウントを計算し、
    閾値を超える連続区間を抽出する。

    プライバシ予算配分:
      - N個のユニークウィンドウ位置に対して epsilon / N ずつ配分 (逐次合成)
      - または Sparse Vector Technique による予算節約

    Parameters
    ----------
    timestamps : Sequence[int]
        ソート済みタイムスタンプ列
    window_size : int
        ウィンドウサイズ
    threshold : int
        密集閾値
    epsilon : float
        総プライバシ予算
    mechanism : str
        "laplace" or "gaussian"
    delta : float
        ガウスメカニズム用 delta
    stability_confidence : float
        閾値安定性の信頼度
    seed : int, optional
        乱数シード

    Returns
    -------
    Tuple[List[Tuple[int, int]], PrivacyAccountant]
        (密集区間リスト, プライバシ会計)
    """
    if not timestamps:
        accountant = PrivacyAccountant(epsilon, delta if mechanism == "gaussian" else 0.0)
        return [], accountant

    ts = sorted(set(timestamps))
    rng = np.random.default_rng(seed)

    # ウィンドウ位置: 各ユニークタイムスタンプを左端とする
    window_positions = list(range(ts[0], ts[-1] + 1))
    n_queries = len(window_positions)

    if n_queries == 0:
        accountant = PrivacyAccountant(epsilon, delta if mechanism == "gaussian" else 0.0)
        return [], accountant

    # 予算配分
    eps_per_query = epsilon / n_queries
    delta_total = delta if mechanism == "gaussian" else 0.0
    delta_per_query = delta_total / n_queries if delta_total > 0 else 0.0

    accountant = PrivacyAccountant(epsilon, delta_total)
    sensitivity = compute_window_sensitivity(window_size)
    stability_margin = compute_stability_margin(sensitivity, eps_per_query, stability_confidence)

    # 全ウィンドウのノイズ付きカウント計算
    ts_list = list(timestamps)  # bisect用
    intervals: List[Tuple[int, int]] = []
    in_dense = False
    start: Optional[int] = None
    end: Optional[int] = None

    for l in window_positions:
        start_idx = bisect_left(ts_list, l)
        end_idx = bisect_right(ts_list, l + window_size)
        true_count = end_idx - start_idx

        if mechanism == "laplace":
            noisy_count = add_laplace_noise(true_count, sensitivity, eps_per_query, rng)
            accountant.consume(eps_per_query)
        else:
            noisy_count = add_gaussian_noise(
                true_count, sensitivity, eps_per_query, delta_per_query, rng
            )
            accountant.consume(eps_per_query, delta_per_query)

        dense = noisy_count >= threshold

        if dense:
            if not in_dense:
                in_dense = True
                start = l
                end = l
            else:
                end = l
        else:
            if in_dense and start is not None and end is not None:
                intervals.append((start, end))
            in_dense = False
            start = None
            end = None

    if in_dense and start is not None and end is not None:
        intervals.append((start, end))

    return intervals, accountant


# ============================================================================
# 6. Sparse Vector Technique (SVT) for Budget-Efficient Detection
# ============================================================================

def sparse_vector_dense_intervals(
    timestamps: Sequence[int],
    window_size: int,
    threshold: int,
    epsilon: float,
    max_above: int = 100,
    seed: Optional[int] = None,
) -> Tuple[List[Tuple[int, int]], int]:
    """
    Sparse Vector Technique による予算効率的な密集区間検出。

    SVT は「閾値を超えるクエリ」だけにカウントを消費する。
    最大 max_above 回の above-threshold 応答で打ち切り。

    予算配分: epsilon/2 をノイズ閾値、epsilon/2 を各クエリノイズに使用。

    Parameters
    ----------
    timestamps : Sequence[int]
        ソート済みタイムスタンプ列
    window_size : int
        ウィンドウサイズ
    threshold : int
        密集閾値
    epsilon : float
        総プライバシ予算
    max_above : int
        最大 above-threshold 回数
    seed : int, optional
        乱数シード

    Returns
    -------
    Tuple[List[Tuple[int, int]], int]
        (密集区間リスト, above-threshold回数)
    """
    if not timestamps:
        return [], 0

    ts = sorted(set(timestamps))
    ts_list = list(timestamps)
    rng = np.random.default_rng(seed)

    # SVT 予算配分
    eps_threshold = epsilon / 2
    eps_query = epsilon / (2 * max_above) if max_above > 0 else epsilon / 2

    # ノイズ付き閾値
    noisy_threshold = threshold + rng.laplace(0, 1.0 / eps_threshold)

    window_positions = list(range(ts[0], ts[-1] + 1))
    intervals: List[Tuple[int, int]] = []
    in_dense = False
    start: Optional[int] = None
    end: Optional[int] = None
    above_count = 0

    for l in window_positions:
        if above_count >= max_above:
            break

        start_idx = bisect_left(ts_list, l)
        end_idx = bisect_right(ts_list, l + window_size)
        true_count = end_idx - start_idx

        noisy_count = true_count + rng.laplace(0, 2.0 * max_above / epsilon)
        dense = noisy_count >= noisy_threshold

        if dense:
            above_count += 1
            if not in_dense:
                in_dense = True
                start = l
                end = l
            else:
                end = l
        else:
            if in_dense and start is not None and end is not None:
                intervals.append((start, end))
            in_dense = False
            start = None
            end = None

    if in_dense and start is not None and end is not None:
        intervals.append((start, end))

    return intervals, above_count


# ============================================================================
# 7. DP Itemset Mining (Apriori + DP)
# ============================================================================

def mine_dp_dense_itemsets(
    transactions: List[List[List[int]]],
    window_size: int,
    threshold: int,
    max_length: int,
    epsilon: float,
    mechanism: str = "laplace",
    delta: float = 1e-6,
    seed: Optional[int] = None,
) -> Tuple[Dict[Tuple[int, ...], List[Tuple[int, int]]], PrivacyAccountant]:
    """
    差分プライバシー付きアイテムセット密集区間マイニング。

    Apriori の各レベルでプライバシ予算を分割する。
    level 1 (単体アイテム): epsilon / max_length
    level k: epsilon / max_length

    Parameters
    ----------
    transactions : トランザクションデータ
    window_size : ウィンドウサイズ
    threshold : 密集閾値
    max_length : 最大アイテムセットサイズ
    epsilon : 総プライバシ予算
    mechanism : "laplace" or "gaussian"
    delta : ガウスメカニズム用 delta
    seed : 乱数シード

    Returns
    -------
    Tuple[Dict, PrivacyAccountant]
    """
    rng = np.random.default_rng(seed)
    eps_per_level = epsilon / max_length
    total_delta = delta if mechanism == "gaussian" else 0.0
    accountant = PrivacyAccountant(epsilon, total_delta)

    item_basket_map, basket_to_transaction, item_transaction_map = compute_item_basket_map(
        transactions
    )

    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]] = {}
    current_level: List[Tuple[int, ...]] = []
    singleton_intervals: Dict[int, List[Tuple[int, int]]] = {}

    # --- Level 1: 単体アイテム ---
    for item in sorted(item_transaction_map.keys()):
        timestamps = item_transaction_map[item]
        if not timestamps:
            continue

        dp_intervals, item_accountant = compute_dp_dense_intervals(
            timestamps,
            window_size,
            threshold,
            eps_per_level,
            mechanism=mechanism,
            delta=total_delta / max_length if total_delta > 0 else 0.0,
            seed=rng.integers(0, 2**31),
        )

        # 非DP の singleton intervals も計算 (枝刈り用、プライバシ影響なし: 候補絞り込みのみに使用)
        singleton_intervals[item] = compute_dense_intervals(
            timestamps, window_size, threshold
        )

        if dp_intervals:
            key = (item,)
            frequents[key] = dp_intervals
            current_level.append(key)

    # 予算消費を記録
    accountant.consume(eps_per_level, total_delta / max_length if total_delta > 0 else 0.0)

    # --- Level 2+: multi-item ---
    k = 2
    while current_level and k <= max_length:
        candidates = generate_candidates(current_level, k)
        candidates = prune_candidates(candidates, set(current_level))
        next_level: List[Tuple[int, ...]] = []

        if not candidates:
            break

        eps_this_level = eps_per_level
        eps_per_candidate = eps_this_level / max(len(candidates), 1)

        for candidate in candidates:
            # 枝刈り: singleton intervals の積集合
            if not all(item in singleton_intervals for item in candidate):
                continue
            allowed_ranges = intersect_interval_lists(
                [singleton_intervals[item] for item in candidate]
            )
            allowed_ranges = [
                (s, e) for (s, e) in allowed_ranges if e - s >= window_size
            ]
            if not allowed_ranges:
                continue

            # 共起タイムスタンプ
            basket_id_lists = [item_basket_map.get(item, []) for item in candidate]
            if any(not bl for bl in basket_id_lists):
                continue
            co_basket_ids = intersect_sorted_lists(basket_id_lists)
            timestamps = basket_ids_to_transaction_ids(co_basket_ids, basket_to_transaction)

            if not timestamps:
                continue

            dp_intervals, _ = compute_dp_dense_intervals(
                timestamps,
                window_size,
                threshold,
                eps_per_candidate,
                mechanism=mechanism,
                delta=total_delta / (max_length * max(len(candidates), 1)) if total_delta > 0 else 0.0,
                seed=rng.integers(0, 2**31),
            )

            if dp_intervals:
                frequents[candidate] = dp_intervals
                next_level.append(candidate)

        accountant.consume(eps_this_level, total_delta / max_length if total_delta > 0 else 0.0)
        current_level = next_level
        k += 1

    return frequents, accountant


# ============================================================================
# 8. Synthetic Data Generation
# ============================================================================

def generate_synthetic_dp_data(
    n_transactions: int = 500,
    n_items: int = 20,
    dense_itemset: Tuple[int, ...] = (1, 2, 3),
    dense_start: int = 100,
    dense_end: int = 200,
    dense_prob: float = 0.8,
    background_prob: float = 0.1,
    seed: int = 42,
) -> List[List[List[int]]]:
    """
    テスト用合成データ生成。

    dense_start..dense_end の区間で dense_itemset の共起確率を高くする。

    Parameters
    ----------
    n_transactions : int
        トランザクション数
    n_items : int
        アイテム数
    dense_itemset : Tuple[int, ...]
        注入する密集アイテムセット
    dense_start, dense_end : int
        密集区間
    dense_prob : float
        密集区間でのアイテム出現確率
    background_prob : float
        背景出現確率
    seed : int
        乱数シード

    Returns
    -------
    List[List[List[int]]]
        トランザクションデータ (1トランザクション = 1バスケット)
    """
    rng = np.random.default_rng(seed)
    transactions: List[List[List[int]]] = []

    for t in range(n_transactions):
        items: List[int] = []
        for item in range(1, n_items + 1):
            if item in dense_itemset and dense_start <= t <= dense_end:
                if rng.random() < dense_prob:
                    items.append(item)
            else:
                if rng.random() < background_prob:
                    items.append(item)
        transactions.append([items] if items else [[]])

    return transactions


# ============================================================================
# 9. Accuracy Metrics
# ============================================================================

def interval_jaccard(
    intervals_a: List[Tuple[int, int]],
    intervals_b: List[Tuple[int, int]],
    domain_end: int,
) -> float:
    """
    2つの区間集合のヤッカード類似度を計算する。

    各位置を dense/non-dense に分類し、集合のJaccardを計算。

    Parameters
    ----------
    intervals_a, intervals_b : List[Tuple[int, int]]
        区間リスト
    domain_end : int
        ドメイン終端

    Returns
    -------
    float
        Jaccard 類似度 [0, 1]
    """
    set_a: Set[int] = set()
    for s, e in intervals_a:
        for p in range(s, e + 1):
            set_a.add(p)

    set_b: Set[int] = set()
    for s, e in intervals_b:
        for p in range(s, e + 1):
            set_b.add(p)

    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0

    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def compute_precision_recall(
    true_intervals: List[Tuple[int, int]],
    pred_intervals: List[Tuple[int, int]],
    domain_end: int,
) -> Tuple[float, float, float]:
    """
    位置ベースの precision, recall, F1 を計算する。

    Returns
    -------
    Tuple[float, float, float]
        (precision, recall, f1)
    """
    true_set: Set[int] = set()
    for s, e in true_intervals:
        for p in range(s, e + 1):
            true_set.add(p)

    pred_set: Set[int] = set()
    for s, e in pred_intervals:
        for p in range(s, e + 1):
            pred_set.add(p)

    if not pred_set:
        return (0.0, 0.0, 0.0) if true_set else (1.0, 1.0, 1.0)
    if not true_set:
        return (0.0, 0.0, 0.0)

    tp = len(true_set & pred_set)
    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(true_set) if true_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


# ============================================================================
# 10. Main entry point
# ============================================================================

def run_dp_mining(
    input_path: str,
    window_size: int = 50,
    threshold: int = 5,
    max_length: int = 3,
    epsilon: float = 1.0,
    mechanism: str = "laplace",
    delta: float = 1e-6,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    ファイルからデータを読み込みDP密集区間マイニングを実行する。

    Returns
    -------
    Dict[str, Any]
        結果辞書 (itemsets, accountant info, etc.)
    """
    transactions = read_transactions_with_baskets(input_path)
    start_time = time.perf_counter()

    dp_results, accountant = mine_dp_dense_itemsets(
        transactions,
        window_size,
        threshold,
        max_length,
        epsilon,
        mechanism=mechanism,
        delta=delta,
        seed=seed,
    )

    elapsed = time.perf_counter() - start_time

    # 非DP結果も計算 (比較用)
    from apriori_window_basket import find_dense_itemsets

    true_results = find_dense_itemsets(transactions, window_size, threshold, max_length)

    # 精度計算
    domain_end = len(transactions)
    accuracy_report: Dict[str, Any] = {}
    for itemset, dp_intervals in dp_results.items():
        true_intervals = true_results.get(itemset, [])
        jaccard = interval_jaccard(dp_intervals, true_intervals, domain_end)
        p, r, f1 = compute_precision_recall(true_intervals, dp_intervals, domain_end)
        accuracy_report[str(itemset)] = {
            "jaccard": jaccard,
            "precision": p,
            "recall": r,
            "f1": f1,
            "dp_interval_count": len(dp_intervals),
            "true_interval_count": len(true_intervals),
        }

    return {
        "dp_itemsets": {str(k): v for k, v in dp_results.items()},
        "true_itemsets": {str(k): v for k, v in true_results.items()},
        "accuracy": accuracy_report,
        "privacy": {
            "epsilon": epsilon,
            "delta": delta,
            "mechanism": mechanism,
            "total_consumed_epsilon": accountant.total_epsilon,
            "total_consumed_delta": accountant.total_delta,
            "num_queries": accountant.num_queries(),
        },
        "elapsed_sec": elapsed,
    }


if __name__ == "__main__":
    # デモ実行
    print("Generating synthetic data...")
    data = generate_synthetic_dp_data(
        n_transactions=300,
        dense_itemset=(1, 2),
        dense_start=50,
        dense_end=150,
        dense_prob=0.9,
        background_prob=0.05,
        seed=42,
    )
    print(f"Generated {len(data)} transactions")

    from apriori_window_basket import find_dense_itemsets

    # 非DP
    true_result = find_dense_itemsets(data, 30, 5, 3)
    print(f"\nNon-DP results: {len(true_result)} itemsets")
    for itemset, intervals in sorted(true_result.items()):
        if len(itemset) > 1:
            print(f"  {itemset}: {intervals}")

    # DP
    for eps in [0.5, 1.0, 2.0, 5.0]:
        dp_result, acc = mine_dp_dense_itemsets(
            data, 30, 5, 3, epsilon=eps, seed=42
        )
        print(f"\nDP (epsilon={eps}): {len(dp_result)} itemsets, "
              f"consumed epsilon={acc.total_epsilon:.4f}")
        for itemset, intervals in sorted(dp_result.items()):
            if len(itemset) > 1:
                true_intervals = true_result.get(itemset, [])
                j = interval_jaccard(intervals, true_intervals, 300)
                print(f"  {itemset}: {intervals} (Jaccard={j:.3f})")
