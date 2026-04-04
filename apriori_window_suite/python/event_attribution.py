"""
Event Attribution Pipeline — Phase 2

サポート時系列の変化点検出と外部イベントへの帰属。
設計文書: doc/temporal_relation_pipeline.md

使い方:
    python3 event_attribution.py [settings.json]
"""
import json
import math
import sys
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# Phase 1 モジュールを import
_parent = str(Path(__file__).resolve().parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)


# ---------------------------------------------------------------------------
# データ型
# ---------------------------------------------------------------------------

@dataclass
class Event:
    event_id: str
    name: str
    start: int
    end: int


@dataclass
class ChangePoint:
    time: int
    direction: str  # "up" or "down"
    magnitude: float
    support_before: float = 0.0
    support_after: float = 0.0


@dataclass
class AttributionCandidate:
    pattern: Tuple[int, ...]
    change_point: ChangePoint
    event: Event
    proximity: float
    attribution_score: float


@dataclass
class SignificantAttribution:
    pattern: Tuple[int, ...]
    change_time: int
    change_direction: str
    change_magnitude: float
    event_name: str
    event_start: int
    event_end: int
    proximity: float
    attribution_score: float
    p_value: float
    adjusted_p_value: float
    interval_start: int = 0
    interval_end: int = 0


@dataclass
class AttributionConfig:
    # Change detection
    change_method: str = "threshold_crossing"
    cusum_drift: float = 0.5
    cusum_h: float = 4.0
    min_magnitude: float = 0.0  # 変化点の最小変化量フィルタ
    min_relative_change: float = 0.0  # 最小相対変化量 (|Δ|/max(1, before))
    min_support_range: int = 0  # パターンのサポート振幅 (max-min) の最小値
    # Attribution scoring
    sigma: Optional[float] = None  # defaults to window_size
    # max_distance は廃止: prox の指数減衰が距離フィルタを兼ねるため不要
    attribution_threshold: float = 0.1
    use_effect_size: bool = False  # スコアに相対変化量を組み込む
    magnitude_normalization: str = "none"  # "none", "sqrt", "full" — mag正規化方式
    # Significance testing
    n_permutations: int = 1000
    alpha: float = 0.05
    correction_method: str = "bonferroni"
    global_correction: bool = True  # 全パターン横断の多重検定補正
    seed: Optional[int] = None
    # Post-processing
    deduplicate_overlap: bool = False  # アイテム重複パターンの重複排除
    # Ablation
    ablation_mode: Optional[str] = None  # スコア構成要素アブレーション
    # Pattern length filter
    min_pattern_length: int = 2  # パイプライン処理対象の最小パターン長 (1で単一アイテムも処理)


# ---------------------------------------------------------------------------
# Step 1: Support Time Series Construction
# ---------------------------------------------------------------------------

def compute_support_series(
    timestamps: Sequence[int],
    window_size: int,
    n_transactions: int,
) -> List[int]:
    """
    各ウィンドウ位置 t のサポート s_P(t) を計算する。

    s_P(t) = |{ts in timestamps : t <= ts < t + window_size}|

    Args:
        timestamps: パターンの出現トランザクション ID（ソート済み）
        window_size: スライディングウィンドウ幅
        n_transactions: トランザクション総数

    Returns:
        長さ max(0, n_transactions - window_size + 1) の整数リスト

    .. deprecated::
        Phase 2 v2 パイプラインでは不要。dense_intervals_to_change_points() を使用。
    """
    length = max(0, n_transactions - window_size + 1)
    series = []
    for t in range(length):
        left = bisect_left(timestamps, t)
        right = bisect_right(timestamps, t + window_size - 1)
        series.append(right - left)
    return series


def compute_support_series_all(
    item_transaction_map: Dict[int, List[int]],
    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    transactions: List,
    window_size: int,
) -> Dict[Tuple[int, ...], List[int]]:
    """
    全パターンのサポート時系列を計算する。

    Phase 1 の item_transaction_map を利用してパターンの出現トランザクションを
    特定し、各パターンについてサポート時系列を生成する。

    .. deprecated::
        Phase 2 v2 パイプラインでは不要。run_attribution_pipeline_v2() を使用。
    """
    from apriori_window_basket import intersect_sorted_lists

    n_transactions = len(transactions)
    result = {}

    for itemset in frequents:
        items = list(itemset)
        if len(items) == 1:
            ts = item_transaction_map.get(items[0], [])
        else:
            lists = [item_transaction_map.get(item, []) for item in items]
            ts = intersect_sorted_lists(lists)
        result[itemset] = compute_support_series(ts, window_size, n_transactions)

    return result


# ---------------------------------------------------------------------------
# Step 1v2: Dense Intervals → Change Points (Phase 1 出力を直接利用)
# ---------------------------------------------------------------------------

def _local_support(timestamps: Sequence[int], t: int, window_size: int) -> int:
    """位置 t でのサポートを bisect で O(log n) 計算する。"""
    left = bisect_left(timestamps, t)
    right = bisect_right(timestamps, t + window_size - 1)
    return right - left


def dense_intervals_to_change_points(
    intervals: List[Tuple[int, int]],
    timestamps: Sequence[int],
    window_size: int,
    n_transactions: int,
    level_window: int = 20,
) -> List[ChangePoint]:
    """
    Phase 1 の密集区間リストから変化点を直接生成する。

    Phase 1 は密集条件を満たすウィンドウ左端 l の連続区間 (s, e) を出力する。
    各区間について:
      - 位置 s で "up" 変化点を生成
      - 位置 e+1 で "down" 変化点を生成（e+1 < max_pos の場合）

    magnitude は交差前後の level_window 幅の平均サポート差（レベルシフト量）。
    局所サポートは bisect で O(log n) で計算する。

    Args:
        intervals: Phase 1 出力の密集区間リスト [(s1, e1), (s2, e2), ...]
        timestamps: パターンの出現トランザクション ID（ソート済み）
        window_size: スライディングウィンドウ幅
        n_transactions: トランザクション総数
        level_window: magnitude 計算用のレベルウィンドウ幅

    Returns:
        変化点のリスト
    """
    max_pos = max(0, n_transactions - window_size + 1)
    if max_pos == 0 or not intervals:
        return []

    changes: List[ChangePoint] = []

    for s, e in intervals:
        # "up" change point at position s
        if 0 <= s < max_pos:
            before_start = max(0, s - level_window)
            after_end = min(max_pos, s + level_window)
            n_before = s - before_start
            n_after = after_end - s
            if n_before > 0:
                mean_before = sum(
                    _local_support(timestamps, t, window_size)
                    for t in range(before_start, s)
                ) / n_before
            else:
                mean_before = 0.0
            if n_after > 0:
                mean_after = sum(
                    _local_support(timestamps, t, window_size)
                    for t in range(s, after_end)
                ) / n_after
            else:
                mean_after = 0.0
            mag = mean_after - mean_before
            changes.append(ChangePoint(
                time=s,
                direction="up",
                magnitude=max(1.0, mag),
                support_before=mean_before,
                support_after=mean_after,
            ))

        # "down" change point at position e+1
        down_pos = e + 1
        if 0 < down_pos < max_pos:
            before_start = max(0, down_pos - level_window)
            after_end = min(max_pos, down_pos + level_window)
            n_before = down_pos - before_start
            n_after = after_end - down_pos
            if n_before > 0:
                mean_before = sum(
                    _local_support(timestamps, t, window_size)
                    for t in range(before_start, down_pos)
                ) / n_before
            else:
                mean_before = 0.0
            if n_after > 0:
                mean_after = sum(
                    _local_support(timestamps, t, window_size)
                    for t in range(down_pos, after_end)
                ) / n_after
            else:
                mean_after = 0.0
            mag = mean_before - mean_after
            changes.append(ChangePoint(
                time=down_pos,
                direction="down",
                magnitude=max(1.0, mag),
                support_before=mean_before,
                support_after=mean_after,
            ))

    return changes


def _get_pattern_timestamps(
    pattern: Tuple[int, ...],
    item_transaction_map: Dict[int, List[int]],
) -> List[int]:
    """パターンの出現トランザクション ID リストを取得する。"""
    from apriori_window_basket import intersect_sorted_lists

    items = list(pattern)
    if len(items) == 1:
        return list(item_transaction_map.get(items[0], []))
    else:
        lists = [item_transaction_map.get(item, []) for item in items]
        return intersect_sorted_lists(lists)


# ---------------------------------------------------------------------------
# Step 2: Change Point Detection
# ---------------------------------------------------------------------------

def detect_threshold_crossings(
    support_series: List[int],
    threshold: int,
    level_window: int = 20,
) -> List[ChangePoint]:
    """
    密集区間の開始/終了を変化点として検出する。

    最も単純な変化点検出: サポートが閾値を上回った/下回った時点。
    magnitude は交差前後の level_window 幅の平均サポート差（レベルシフト量）。
    """
    if not support_series:
        return []

    n = len(support_series)
    changes: List[ChangePoint] = []
    prev_dense = False

    for t, s in enumerate(support_series):
        is_dense = s >= threshold
        if is_dense and not prev_dense:
            # レベルシフト量: 交差後の平均 - 交差前の平均
            before_start = max(0, t - level_window)
            after_end = min(n, t + level_window)
            mean_before = sum(support_series[before_start:t]) / max(1, t - before_start)
            mean_after = sum(support_series[t:after_end]) / max(1, after_end - t)
            mag = mean_after - mean_before
            changes.append(ChangePoint(
                time=t,
                direction="up",
                magnitude=max(1.0, mag),
                support_before=mean_before,
                support_after=mean_after,
            ))
        elif not is_dense and prev_dense:
            before_start = max(0, t - level_window)
            after_end = min(n, t + level_window)
            mean_before = sum(support_series[before_start:t]) / max(1, t - before_start)
            mean_after = sum(support_series[t:after_end]) / max(1, after_end - t)
            mag = mean_before - mean_after
            changes.append(ChangePoint(
                time=t,
                direction="down",
                magnitude=max(1.0, mag),
                support_before=mean_before,
                support_after=mean_after,
            ))
        prev_dense = is_dense

    return changes


def detect_cusum(
    support_series: List[int],
    drift: float = 0.5,
    h: float = 4.0,
) -> List[ChangePoint]:
    """
    CUSUM (Cumulative Sum) によるレベルシフト検出。

    Args:
        support_series: サポート時系列
        drift: 許容ドリフト（小さいほど感度が高い）
        h: 判定閾値（大きいほど偽陽性が少ない）
    """
    if not support_series or len(support_series) < 2:
        return []

    mean = sum(support_series) / len(support_series)
    s_pos = 0.0
    s_neg = 0.0
    changes: List[ChangePoint] = []

    for t, x in enumerate(support_series):
        s_pos = max(0.0, s_pos + (x - mean) - drift)
        s_neg = max(0.0, s_neg - (x - mean) - drift)

        if s_pos > h:
            prev_s = support_series[t - 1] if t > 0 else 0
            changes.append(ChangePoint(
                time=t,
                direction="up",
                magnitude=s_pos,
                support_before=float(prev_s),
                support_after=float(x),
            ))
            s_pos = 0.0

        if s_neg > h:
            prev_s = support_series[t - 1] if t > 0 else 0
            changes.append(ChangePoint(
                time=t,
                direction="down",
                magnitude=s_neg,
                support_before=float(prev_s),
                support_after=float(x),
            ))
            s_neg = 0.0

    return changes


def detect_change_points(
    support_series: List[int],
    method: str = "threshold_crossing",
    threshold: int = 2,
    cusum_drift: float = 0.5,
    cusum_h: float = 4.0,
) -> List[ChangePoint]:
    """変化点検出のディスパッチ関数。"""
    if method == "threshold_crossing":
        return detect_threshold_crossings(support_series, threshold)
    elif method == "cusum":
        return detect_cusum(support_series, cusum_drift, cusum_h)
    else:
        raise ValueError(f"Unknown change detection method: {method}")


# ---------------------------------------------------------------------------
# Step 3: Event Attribution Scoring
# ---------------------------------------------------------------------------

def compute_proximity(
    change_time: int,
    event: Event,
    sigma: float,
) -> float:
    """変化点とイベントの時間的近接度を計算する。"""
    dist = min(abs(change_time - event.start), abs(change_time - event.end))
    return math.exp(-dist / sigma) if sigma > 0 else (1.0 if dist == 0 else 0.0)


def score_attributions(
    pattern: Tuple[int, ...],
    change_points: List[ChangePoint],
    events: List[Event],
    sigma: float,
    attribution_threshold: float = 0.1,
    use_effect_size: bool = False,
    ablation_mode: Optional[str] = None,
    magnitude_normalization: str = "none",
) -> List[AttributionCandidate]:
    """
    変化点-イベント間の帰属スコアを計算し、閾値を超えた候補を返す。

    帰属スコア A = prox × mag（近接度 × 変化量）。
    prox の指数減衰 exp(-d/σ) が距離に応じた重み付けを行うため、
    ハード距離カットオフ (max_distance) は不要。

    use_effect_size=True の場合、magnitude の代わりに相対変化量
    (magnitude / max(1, support_before)) を使用する。これにより高ベースライン
    パターンの弱い変動が抑制される。

    ablation_mode: スコア構成要素のアブレーション設定（None=Full）。
        "no_prox"  : mag only  (prox=1.0)
        "no_mag"   : prox only (mag=1.0)
        "mag_only" : mag only  (prox=1.0)
        "prox_only": prox only (mag=1.0)
    """
    candidates: List[AttributionCandidate] = []

    for cp in change_points:
        for event in events:
            prox = compute_proximity(cp.time, event, sigma)
            if magnitude_normalization == "sqrt":
                mag = abs(cp.magnitude) / math.sqrt(max(1.0, cp.support_before))
            elif magnitude_normalization == "full" or use_effect_size:
                mag = abs(cp.magnitude) / max(1.0, cp.support_before)
            else:
                mag = abs(cp.magnitude)

            # Apply ablation overrides
            if ablation_mode in ("no_prox", "mag_only"):
                score = mag
            elif ablation_mode in ("no_mag", "prox_only"):
                score = prox
            else:
                score = prox * mag

            if score >= attribution_threshold:
                candidates.append(AttributionCandidate(
                    pattern=pattern,
                    change_point=cp,
                    event=event,
                    proximity=prox,
                    attribution_score=score,
                ))

    return candidates


# ---------------------------------------------------------------------------
# Step 4: Statistical Significance Testing
# ---------------------------------------------------------------------------

def circular_shift_events(
    events: List[Event],
    offset: int,
    max_time: int,
) -> List[Event]:
    """イベント時刻を円形シフトする。"""
    shifted = []
    for e in events:
        duration = e.end - e.start
        new_start = (e.start + offset) % max_time
        new_end = new_start + duration
        if new_end >= max_time:
            new_end = max_time - 1
        shifted.append(Event(
            event_id=e.event_id,
            name=e.name,
            start=new_start,
            end=new_end,
        ))
    return shifted


@dataclass
class _RawTestResult:
    """置換検定の中間結果（alpha 判定前）。"""
    pattern: Tuple[int, ...]
    change_point: ChangePoint
    event: Event
    proximity: float
    obs_score: float
    p_value: float
    interval_start: int = 0
    interval_end: int = 0


def permutation_test_raw(
    pattern: Tuple[int, ...],
    change_points: List[ChangePoint],
    events: List[Event],
    sigma: float,
    max_time: int,
    n_permutations: int = 1000,
    attribution_threshold: float = 0.1,
    seed: Optional[int] = None,
    use_effect_size: bool = False,
    ablation_mode: Optional[str] = None,
    magnitude_normalization: str = "none",
    interval_start: int = 0,
    interval_end: int = 0,
) -> List[_RawTestResult]:
    """
    置換検定を実行し、未補正 p 値を返す（alpha 判定はしない）。

    帰無仮説: 変化点の位置はイベントと独立
    """
    import random
    rng = random.Random(seed)

    obs_candidates = score_attributions(
        pattern, change_points, events, sigma, attribution_threshold,
        use_effect_size=use_effect_size, ablation_mode=ablation_mode,
        magnitude_normalization=magnitude_normalization,
    )
    if not obs_candidates:
        return []

    # ペアごとの観測スコア合計
    obs_scores: Dict[str, float] = {}
    for c in obs_candidates:
        key = c.event.event_id
        obs_scores[key] = obs_scores.get(key, 0.0) + c.attribution_score

    # 置換分布の構築
    perm_counts: Dict[str, int] = {k: 0 for k in obs_scores}

    for _ in range(n_permutations):
        offset = rng.randint(1, max_time - 1)
        shifted_events = circular_shift_events(events, offset, max_time)
        perm_candidates = score_attributions(
            pattern, change_points, shifted_events, sigma,
            attribution_threshold, use_effect_size=use_effect_size,
            ablation_mode=ablation_mode,
            magnitude_normalization=magnitude_normalization,
        )

        perm_scores: Dict[str, float] = {}
        for c in perm_candidates:
            key = c.event.event_id
            perm_scores[key] = perm_scores.get(key, 0.0) + c.attribution_score

        for eid, obs_s in obs_scores.items():
            if perm_scores.get(eid, 0.0) >= obs_s:
                perm_counts[eid] += 1

    # 未補正 p 値を返す
    results: List[_RawTestResult] = []
    for eid, obs_s in obs_scores.items():
        p_value = (perm_counts[eid] + 1) / (n_permutations + 1)
        best = max(
            [c for c in obs_candidates if c.event.event_id == eid],
            key=lambda c: c.attribution_score,
        )
        results.append(_RawTestResult(
            pattern=pattern,
            change_point=best.change_point,
            event=best.event,
            proximity=best.proximity,
            obs_score=obs_s,
            p_value=p_value,
            interval_start=interval_start,
            interval_end=interval_end,
        ))

    return results


def permutation_test(
    pattern: Tuple[int, ...],
    change_points: List[ChangePoint],
    events: List[Event],
    sigma: float,
    max_time: int,
    n_permutations: int = 1000,
    alpha: float = 0.05,
    correction_method: str = "bonferroni",
    attribution_threshold: float = 0.1,
    seed: Optional[int] = None,
    use_effect_size: bool = False,
    ablation_mode: Optional[str] = None,
    magnitude_normalization: str = "none",
) -> List[SignificantAttribution]:
    """
    置換検定により有意な帰属を特定する（後方互換ラッパー）。

    帰無仮説: 変化点の位置はイベントと独立
    """
    raw_results = permutation_test_raw(
        pattern, change_points, events, sigma,
        max_time, n_permutations, attribution_threshold, seed,
        use_effect_size=use_effect_size, ablation_mode=ablation_mode,
        magnitude_normalization=magnitude_normalization,
    )
    if not raw_results:
        return []

    n_hypotheses = len(raw_results)
    results: List[SignificantAttribution] = []

    for r in raw_results:
        if correction_method == "bonferroni":
            adj_p = min(1.0, r.p_value * n_hypotheses)
        else:
            adj_p = r.p_value

        if adj_p >= alpha:
            continue

        results.append(SignificantAttribution(
            pattern=r.pattern,
            change_time=r.change_point.time,
            change_direction=r.change_point.direction,
            change_magnitude=r.change_point.magnitude,
            event_name=r.event.name,
            event_start=r.event.start,
            event_end=r.event.end,
            proximity=r.proximity,
            attribution_score=r.obs_score,
            p_value=r.p_value,
            adjusted_p_value=adj_p,
        ))

    return results


# ---------------------------------------------------------------------------
# Pipeline 統合
# ---------------------------------------------------------------------------

def run_attribution_pipeline(
    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    support_series_map: Dict[Tuple[int, ...], List[int]],
    events: List[Event],
    window_size: int,
    threshold: int,
    config: Optional[AttributionConfig] = None,
) -> List[SignificantAttribution]:
    """
    Event Attribution Pipeline を実行する。

    Args:
        frequents: Phase 1 出力（パターン → 密集区間リスト）
        support_series_map: 各パターンのサポート時系列
        events: 外部イベントリスト
        window_size: Phase 1 のウィンドウサイズ
        threshold: Phase 1 の最小サポート
        config: パイプライン設定

    Returns:
        有意な帰属のリスト
    """
    if config is None:
        config = AttributionConfig()

    sigma = config.sigma if config.sigma is not None else float(window_size)

    # グローバル補正が有効な場合: まず全パターンの p 値を収集してから判定
    if config.global_correction:
        return _run_pipeline_global(
            support_series_map, events, window_size, threshold, sigma,
            config,
        )

    # per-pattern 補正（後方互換）
    all_results: List[SignificantAttribution] = []

    for pattern, series in support_series_map.items():
        if len(pattern) < config.min_pattern_length:
            continue
        if not series:
            continue

        max_time = len(series)

        change_points = _detect_and_filter(series, threshold, config)
        if not change_points:
            continue

        sig_results = permutation_test(
            pattern=pattern,
            change_points=change_points,
            events=events,
            sigma=sigma,
            max_time=max_time,
            n_permutations=config.n_permutations,
            alpha=config.alpha,
            correction_method=config.correction_method,
            attribution_threshold=config.attribution_threshold,
            seed=config.seed,
            ablation_mode=config.ablation_mode,
        )
        all_results.extend(sig_results)

    return all_results


def _detect_and_filter(
    series: List[int],
    threshold: int,
    config: AttributionConfig,
) -> List[ChangePoint]:
    """変化点検出 + 品質フィルタ（magnitude / 相対変化量）。"""
    change_points = detect_change_points(
        series,
        method=config.change_method,
        threshold=threshold,
        cusum_drift=config.cusum_drift,
        cusum_h=config.cusum_h,
    )
    if config.min_magnitude > 0:
        change_points = [cp for cp in change_points
                         if cp.magnitude >= config.min_magnitude]
    if config.min_relative_change > 0:
        change_points = [
            cp for cp in change_points
            if cp.magnitude / max(1.0, cp.support_before) >= config.min_relative_change
        ]
    return change_points


def _detect_and_filter_from_intervals(
    intervals: List[Tuple[int, int]],
    timestamps: Sequence[int],
    window_size: int,
    n_transactions: int,
    config: AttributionConfig,
) -> List[ChangePoint]:
    """密集区間から変化点を生成 + 品質フィルタ（magnitude / 相対変化量）。"""
    change_points = dense_intervals_to_change_points(
        intervals, timestamps, window_size, n_transactions,
    )
    if config.min_magnitude > 0:
        change_points = [cp for cp in change_points
                         if cp.magnitude >= config.min_magnitude]
    if config.min_relative_change > 0:
        change_points = [
            cp for cp in change_points
            if cp.magnitude / max(1.0, cp.support_before) >= config.min_relative_change
        ]
    return change_points


def _run_pipeline_global(
    support_series_map: Dict[Tuple[int, ...], List[int]],
    events: List[Event],
    window_size: int,
    threshold: int,
    sigma: float,
    config: AttributionConfig,
) -> List[SignificantAttribution]:
    """全パターン横断でグローバル多重検定補正を行うパイプライン。"""
    # Step 2-3: 全パターンの未補正 p 値を収集
    all_raw: List[_RawTestResult] = []

    for pattern, series in support_series_map.items():
        if len(pattern) < config.min_pattern_length:
            continue
        if not series:
            continue

        # サポート振幅フィルタ: 変動の小さいパターンをスキップ
        if config.min_support_range > 0:
            s_range = max(series) - min(series)
            if s_range < config.min_support_range:
                continue

        max_time = len(series)
        change_points = _detect_and_filter(series, threshold, config)
        if not change_points:
            continue

        raw_results = permutation_test_raw(
            pattern=pattern,
            change_points=change_points,
            events=events,
            sigma=sigma,
            max_time=max_time,
            n_permutations=config.n_permutations,
            attribution_threshold=config.attribution_threshold,
            seed=config.seed,
            use_effect_size=config.use_effect_size,
            ablation_mode=config.ablation_mode,
            magnitude_normalization=config.magnitude_normalization,
        )
        all_raw.extend(raw_results)

    if not all_raw:
        return []

    # Step 4: グローバル多重検定補正
    n_total_hypotheses = len(all_raw)
    results: List[SignificantAttribution] = []

    if config.correction_method == "bh":
        # Benjamini-Hochberg step-up (FDR制御)
        sorted_raw = sorted(all_raw, key=lambda r: r.p_value)
        # Step-down adjusted p-values: adj_p[k] = min(adj_p[k+1], p[k]*m/k)
        adj_p_list = [0.0] * n_total_hypotheses
        for i in range(n_total_hypotheses - 1, -1, -1):
            rank = i + 1
            raw_adj = sorted_raw[i].p_value * n_total_hypotheses / rank
            if i == n_total_hypotheses - 1:
                adj_p_list[i] = min(1.0, raw_adj)
            else:
                adj_p_list[i] = min(adj_p_list[i + 1], min(1.0, raw_adj))
        for i, r in enumerate(sorted_raw):
            if adj_p_list[i] < config.alpha:
                results.append(_raw_to_significant(r, adj_p_list[i]))
    else:
        # Bonferroni (FWER制御)
        for r in all_raw:
            adj_p = min(1.0, r.p_value * n_total_hypotheses)
            if adj_p < config.alpha:
                results.append(_raw_to_significant(r, adj_p))

    # Step 5: アイテム重複パターンの重複排除
    if config.deduplicate_overlap and results:
        results = _deduplicate_by_item_overlap(results)

    return results


def run_attribution_pipeline_v2(
    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    item_transaction_map: Dict[int, List[int]],
    events: List[Event],
    window_size: int,
    threshold: int,
    n_transactions: int,
    config: Optional[AttributionConfig] = None,
) -> List[SignificantAttribution]:
    """
    Event Attribution Pipeline v2: Phase 1 の密集区間を直接利用する。

    compute_support_series_all() による全サポート時系列の再計算を省略し、
    Phase 1 が出力した密集区間 (s, e) から変化点を直接生成する。

    Args:
        frequents: Phase 1 出力（パターン → 密集区間リスト）
        item_transaction_map: Phase 1 のアイテム → トランザクション ID マップ
        events: 外部イベントリスト
        window_size: Phase 1 のウィンドウサイズ
        threshold: Phase 1 の最小サポート
        n_transactions: トランザクション総数
        config: パイプライン設定

    Returns:
        有意な帰属のリスト
    """
    if config is None:
        config = AttributionConfig()

    sigma = config.sigma if config.sigma is not None else float(window_size)

    if config.global_correction:
        return _run_pipeline_global_v2(
            frequents, item_transaction_map, events, window_size,
            threshold, n_transactions, sigma, config,
        )

    # per-pattern 補正
    max_pos = max(0, n_transactions - window_size + 1)
    all_results: List[SignificantAttribution] = []

    for pattern, intervals in frequents.items():
        if len(pattern) < config.min_pattern_length:
            continue
        if not intervals:
            continue

        timestamps = _get_pattern_timestamps(pattern, item_transaction_map)
        change_points = _detect_and_filter_from_intervals(
            intervals, timestamps, window_size, n_transactions, config,
        )
        if not change_points:
            continue

        sig_results = permutation_test(
            pattern=pattern,
            change_points=change_points,
            events=events,
            sigma=sigma,
            max_time=max_pos,
            n_permutations=config.n_permutations,
            alpha=config.alpha,
            correction_method=config.correction_method,
            attribution_threshold=config.attribution_threshold,
            seed=config.seed,
            ablation_mode=config.ablation_mode,
        )
        all_results.extend(sig_results)

    return all_results


def _run_pipeline_global_v2(
    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    item_transaction_map: Dict[int, List[int]],
    events: List[Event],
    window_size: int,
    threshold: int,
    n_transactions: int,
    sigma: float,
    config: AttributionConfig,
) -> List[SignificantAttribution]:
    """全パターン横断でグローバル多重検定補正を行うパイプライン (v2: 密集区間直接利用)。"""
    max_pos = max(0, n_transactions - window_size + 1)
    all_raw: List[_RawTestResult] = []

    for pattern, intervals in frequents.items():
        if len(pattern) < config.min_pattern_length:
            continue
        if not intervals:
            continue

        # min_support_range フィルタ:
        # 密集区間が存在するパターンは support >= threshold の区間を持つ。
        # support range >= threshold なので、min_support_range <= threshold なら常に通過。
        if config.min_support_range > threshold:
            # 精密なフィルタが必要 — 密集区間内外のサポートを局所計算
            timestamps = _get_pattern_timestamps(pattern, item_transaction_map)
            # 密集区間内の最大サポート（区間の中央付近）
            max_sup = 0
            for s, e in intervals:
                mid = (s + e) // 2
                sup = _local_support(timestamps, mid, window_size)
                if sup > max_sup:
                    max_sup = sup
            # 密集区間外の最小サポート（区間から遠い位置）
            min_sup = max_sup  # 初期値
            # 区間外の候補位置: 先頭、末尾、区間間のギャップ中点
            candidate_positions = [0, max(0, max_pos - 1)]
            sorted_intervals = sorted(intervals)
            for i in range(len(sorted_intervals) - 1):
                gap_mid = (sorted_intervals[i][1] + sorted_intervals[i + 1][0]) // 2
                candidate_positions.append(gap_mid)
            for pos in candidate_positions:
                if 0 <= pos < max_pos:
                    sup = _local_support(timestamps, pos, window_size)
                    if sup < min_sup:
                        min_sup = sup
            s_range = max_sup - min_sup
            if s_range < config.min_support_range:
                continue
            # timestamps already computed
        else:
            timestamps = _get_pattern_timestamps(pattern, item_transaction_map)

        # (P, I, E) 設計: 密集区間ごとに独立して置換検定を実施
        for iv_start, iv_end in intervals:
            change_points = _detect_and_filter_from_intervals(
                [(iv_start, iv_end)], timestamps, window_size, n_transactions, config,
            )
            if not change_points:
                continue

            raw_results = permutation_test_raw(
                pattern=pattern,
                change_points=change_points,
                events=events,
                sigma=sigma,
                max_time=max_pos,
                n_permutations=config.n_permutations,
                attribution_threshold=config.attribution_threshold,
                seed=config.seed,
                use_effect_size=config.use_effect_size,
                ablation_mode=config.ablation_mode,
                magnitude_normalization=config.magnitude_normalization,
                interval_start=iv_start,
                interval_end=iv_end,
            )
            all_raw.extend(raw_results)

    if not all_raw:
        return []

    # Step 4: グローバル多重検定補正
    n_total_hypotheses = len(all_raw)
    results: List[SignificantAttribution] = []

    if config.correction_method == "bh":
        sorted_raw = sorted(all_raw, key=lambda r: r.p_value)
        adj_p_list = [0.0] * n_total_hypotheses
        for i in range(n_total_hypotheses - 1, -1, -1):
            rank = i + 1
            raw_adj = sorted_raw[i].p_value * n_total_hypotheses / rank
            if i == n_total_hypotheses - 1:
                adj_p_list[i] = min(1.0, raw_adj)
            else:
                adj_p_list[i] = min(adj_p_list[i + 1], min(1.0, raw_adj))
        for i, r in enumerate(sorted_raw):
            if adj_p_list[i] < config.alpha:
                results.append(_raw_to_significant(r, adj_p_list[i]))
    else:
        for r in all_raw:
            adj_p = min(1.0, r.p_value * n_total_hypotheses)
            if adj_p < config.alpha:
                results.append(_raw_to_significant(r, adj_p))

    if config.deduplicate_overlap and results:
        results = _deduplicate_by_item_overlap(results)

    return results


def _deduplicate_by_item_overlap(
    results: List[SignificantAttribution],
) -> List[SignificantAttribution]:
    """
    同一イベントに帰属されたパターンのうち、アイテムが重複するものを
    Union-Find でクラスタリングし、各クラスタから最高スコアのパターンのみ残す。

    前処理: 同一 (パターン, イベント) ペアが複数区間で有意な場合、
    最高スコアの区間のみ代表として残す（区間ごとの重複を除去）。

    Phase 1: 長さ l のパターン同士は、共有アイテム数 >= ceil(l/2) のとき辺を張る。
    |P| = 2: ceil(2/2) = 1（1アイテム共有で結合）
    |P| = 3: ceil(3/2) = 2（2アイテム以上共有で結合）

    Phase 2: 異なる長さのパターン間で部分集合関係がある場合（A ⊂ B）、
    同一イベントへの帰属であればクラスタリングし最高スコアを残す。
    これにより、交差シグナルパターン（異なる信号のアイテムを跨ぐパターン）も
    同一イベント内の強いパターンに統合される。
    """
    from collections import defaultdict
    import math

    # 前処理: 同一 (pattern, event) ペアは最高スコアの区間のみ残す
    best_per_pair: Dict[Tuple, "SignificantAttribution"] = {}
    for r in results:
        key = (tuple(r.pattern), r.event_name)
        if key not in best_per_pair or r.attribution_score > best_per_pair[key].attribution_score:
            best_per_pair[key] = r
    candidates = list(best_per_pair.values())

    # Phase 1 & 2: イベント単位でパターン間のアイテム重複に基づく Union-Find
    by_event: Dict[str, List["SignificantAttribution"]] = defaultdict(list)
    for r in candidates:
        by_event[r.event_name].append(r)

    deduplicated: List[SignificantAttribution] = []

    for _event_name, event_results in by_event.items():
        # Group by pattern length for length-stratified dedup (Phase 1)
        by_length: Dict[int, List[SignificantAttribution]] = defaultdict(list)
        for r in event_results:
            by_length[len(r.pattern)].append(r)

        phase1_results: List[SignificantAttribution] = []
        for l, length_results in by_length.items():
            n = len(length_results)
            if n <= 1:
                phase1_results.extend(length_results)
                continue

            # Union-Find
            parent = list(range(n))

            def find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def union(a: int, b: int) -> None:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb

            threshold = math.ceil(l / 2)

            for i in range(n):
                set_i = set(length_results[i].pattern)
                for j in range(i + 1, n):
                    set_j = set(length_results[j].pattern)
                    if len(set_i & set_j) >= threshold:
                        union(i, j)

            clusters: Dict[int, List[SignificantAttribution]] = defaultdict(list)
            for i in range(n):
                clusters[find(i)].append(length_results[i])

            for cluster in clusters.values():
                best = max(cluster, key=lambda r: r.attribution_score)
                phase1_results.append(best)

        # Phase 2: Cross-length subset dedup within the same event
        n2 = len(phase1_results)
        if n2 <= 1:
            deduplicated.extend(phase1_results)
            continue

        parent2 = list(range(n2))

        def find2(x: int) -> int:
            while parent2[x] != x:
                parent2[x] = parent2[parent2[x]]
                x = parent2[x]
            return x

        def union2(a: int, b: int) -> None:
            ra, rb = find2(a), find2(b)
            if ra != rb:
                parent2[ra] = rb

        sets2 = [set(r.pattern) for r in phase1_results]
        for i in range(n2):
            for j in range(i + 1, n2):
                if sets2[i] <= sets2[j] or sets2[j] <= sets2[i]:
                    union2(i, j)

        clusters2: Dict[int, List[SignificantAttribution]] = defaultdict(list)
        for i in range(n2):
            clusters2[find2(i)].append(phase1_results[i])

        for cluster in clusters2.values():
            # Prefer highest attribution score; break ties by longer (more specific) pattern.
            best = max(cluster, key=lambda r: (r.attribution_score, len(r.pattern)))
            deduplicated.append(best)

    return deduplicated


def _raw_to_significant(r: _RawTestResult, adj_p: float) -> SignificantAttribution:
    return SignificantAttribution(
        pattern=r.pattern,
        change_time=r.change_point.time,
        change_direction=r.change_point.direction,
        change_magnitude=r.change_point.magnitude,
        event_name=r.event.name,
        event_start=r.event.start,
        event_end=r.event.end,
        proximity=r.proximity,
        attribution_score=r.obs_score,
        p_value=r.p_value,
        adjusted_p_value=adj_p,
        interval_start=r.interval_start,
        interval_end=r.interval_end,
    )


# ---------------------------------------------------------------------------
# イベント読み込み
# ---------------------------------------------------------------------------

def read_events(path: str) -> List[Event]:
    """JSON 形式のイベントファイルを読み込む。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    events = []
    seen_ids = set()
    for entry in raw:
        eid = entry["event_id"]
        if eid in seen_ids:
            raise ValueError(f"Duplicate event_id: {eid}")
        seen_ids.add(eid)
        s = entry["start"]
        e = entry["end"]
        if s > e:
            raise ValueError(f"event_id={eid}: start({s}) > end({e})")
        events.append(Event(
            event_id=eid,
            name=entry.get("name", ""),
            start=s,
            end=e,
        ))
    return events


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------

def main():
    """コマンドライン実行。"""
    import time

    settings_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parent.parent / "data" / "settings_phase2.json"
    )

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    from apriori_window_basket import (
        read_text_file_as_2d_vec_of_integers,
        compute_item_timestamps_map,
        find_dense_itemsets,
    )

    # Phase 1 実行
    input_dir = settings["input_file"]["dir"]
    input_file = settings["input_file"]["file_name"]
    input_path = str(Path(input_dir) / input_file)

    params = settings["apriori_parameters"]
    window_size = params["window_size"]
    min_support = params["min_support"]
    max_length = params["max_length"]

    start = time.perf_counter()
    transactions = read_text_file_as_2d_vec_of_integers(input_path)
    item_transaction_map = compute_item_timestamps_map(transactions)
    frequents = find_dense_itemsets(
        transactions, window_size, min_support, max_length
    )

    # イベント読み込み
    event_cfg = settings.get("event_file", {})
    event_path = str(Path(event_cfg.get("dir", ".")) / event_cfg.get("file_name", "events.json"))
    events = read_events(event_path)

    # パイプライン設定
    attr_params = settings.get("event_attribution_parameters", {})
    cd = attr_params.get("change_detection", {})
    at = attr_params.get("attribution", {})
    sg = attr_params.get("significance", {})

    config = AttributionConfig(
        change_method=cd.get("method", "threshold_crossing"),
        cusum_drift=cd.get("cusum_drift", 0.5),
        cusum_h=cd.get("cusum_h", 4.0),
        min_magnitude=cd.get("min_magnitude", 0.0),
        min_relative_change=cd.get("min_relative_change", 0.0),
        sigma=at.get("sigma"),
        attribution_threshold=at.get("attribution_threshold", 0.1),
        n_permutations=sg.get("n_permutations", 1000),
        alpha=sg.get("alpha", 0.05),
        correction_method=sg.get("correction_method", "bonferroni"),
        global_correction=sg.get("global_correction", True),
        seed=sg.get("seed"),
    )

    # Phase 2 実行 (v2: 密集区間を直接利用、サポート時系列の再計算を省略)
    n_transactions = len(transactions)
    results = run_attribution_pipeline_v2(
        frequents, item_transaction_map, events, window_size, min_support,
        n_transactions, config
    )

    elapsed = time.perf_counter() - start
    print(f"有意な帰属: {len(results)} 件")
    print(f"Elapsed time: {elapsed * 1000:.3f} ms")

    for r in results:
        print(
            f"  {r.pattern} t={r.change_time} ({r.change_direction}) "
            f"→ {r.event_name} p_adj={r.adjusted_p_value:.4f}"
        )


if __name__ == "__main__":
    main()
