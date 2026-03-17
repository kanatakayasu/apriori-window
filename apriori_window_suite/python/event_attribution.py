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
    direction_match: float
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


@dataclass
class AttributionConfig:
    # Change detection
    change_method: str = "threshold_crossing"
    cusum_drift: float = 0.5
    cusum_h: float = 4.0
    # Attribution scoring
    sigma: Optional[float] = None  # defaults to window_size
    max_distance: Optional[int] = None  # defaults to 2 * window_size
    attribution_threshold: float = 0.1
    # Significance testing
    n_permutations: int = 1000
    alpha: float = 0.05
    correction_method: str = "bonferroni"
    seed: Optional[int] = None


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
# Step 2: Change Point Detection
# ---------------------------------------------------------------------------

def detect_threshold_crossings(
    support_series: List[int],
    threshold: int,
) -> List[ChangePoint]:
    """
    密集区間の開始/終了を変化点として検出する。

    最も単純な変化点検出: サポートが閾値を上回った/下回った時点。
    """
    if not support_series:
        return []

    changes: List[ChangePoint] = []
    prev_dense = False

    for t, s in enumerate(support_series):
        is_dense = s >= threshold
        if is_dense and not prev_dense:
            prev_s = support_series[t - 1] if t > 0 else 0
            changes.append(ChangePoint(
                time=t,
                direction="up",
                magnitude=float(s - prev_s),
                support_before=float(prev_s),
                support_after=float(s),
            ))
        elif not is_dense and prev_dense:
            prev_s = support_series[t - 1] if t > 0 else 0
            changes.append(ChangePoint(
                time=t,
                direction="down",
                magnitude=float(prev_s - s),
                support_before=float(prev_s),
                support_after=float(s),
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


def compute_direction_match(
    change_point: ChangePoint,
    event: Event,
) -> float:
    """
    変化点とイベントの方向整合性を計算する。

    - 上昇 × イベント開始直後 → 1.0
    - 下降 × イベント終了直後 → 1.0
    - 上昇 × イベント開始直前 → 0.5（予兆的）
    - 不整合 → 0.0
    """
    t = change_point.time

    if change_point.direction == "up":
        # イベント開始の直後に上昇
        if t >= event.start:
            return 1.0
        # イベント開始の直前に上昇（予兆）
        elif t < event.start:
            return 0.5
    elif change_point.direction == "down":
        # イベント終了の直後に下降
        if t >= event.end:
            return 1.0
        # イベント終了の直前に下降
        elif t < event.end:
            return 0.5

    return 0.0


def score_attributions(
    pattern: Tuple[int, ...],
    change_points: List[ChangePoint],
    events: List[Event],
    sigma: float,
    max_distance: int,
    attribution_threshold: float = 0.1,
) -> List[AttributionCandidate]:
    """
    変化点-イベント間の帰属スコアを計算し、閾値を超えた候補を返す。
    """
    candidates: List[AttributionCandidate] = []

    for cp in change_points:
        for event in events:
            dist = min(abs(cp.time - event.start), abs(cp.time - event.end))
            if dist > max_distance:
                continue

            prox = compute_proximity(cp.time, event, sigma)
            dir_match = compute_direction_match(cp, event)
            score = prox * dir_match * abs(cp.magnitude)

            if score >= attribution_threshold:
                candidates.append(AttributionCandidate(
                    pattern=pattern,
                    change_point=cp,
                    event=event,
                    proximity=prox,
                    direction_match=dir_match,
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


def permutation_test(
    pattern: Tuple[int, ...],
    change_points: List[ChangePoint],
    events: List[Event],
    sigma: float,
    max_distance: int,
    max_time: int,
    n_permutations: int = 1000,
    alpha: float = 0.05,
    correction_method: str = "bonferroni",
    attribution_threshold: float = 0.1,
    seed: Optional[int] = None,
) -> List[SignificantAttribution]:
    """
    置換検定により有意な帰属を特定する。

    帰無仮説: 変化点の位置はイベントと独立
    """
    import random
    rng = random.Random(seed)

    # 観測統計量: 各 (pattern, event) ペアの帰属スコア合計
    obs_candidates = score_attributions(
        pattern, change_points, events, sigma, max_distance, attribution_threshold
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
            pattern, change_points, shifted_events, sigma, max_distance,
            attribution_threshold
        )

        perm_scores: Dict[str, float] = {}
        for c in perm_candidates:
            key = c.event.event_id
            perm_scores[key] = perm_scores.get(key, 0.0) + c.attribution_score

        for eid, obs_s in obs_scores.items():
            if perm_scores.get(eid, 0.0) >= obs_s:
                perm_counts[eid] += 1

    # p 値計算
    n_hypotheses = len(obs_scores)
    results: List[SignificantAttribution] = []

    for eid, obs_s in obs_scores.items():
        p_value = (perm_counts[eid] + 1) / (n_permutations + 1)

        if correction_method == "bonferroni":
            adj_p = min(1.0, p_value * n_hypotheses)
        else:
            adj_p = p_value

        if adj_p >= alpha:
            continue

        # 対応する最良の候補を取得
        best = max(
            [c for c in obs_candidates if c.event.event_id == eid],
            key=lambda c: c.attribution_score,
        )

        results.append(SignificantAttribution(
            pattern=pattern,
            change_time=best.change_point.time,
            change_direction=best.change_point.direction,
            change_magnitude=best.change_point.magnitude,
            event_name=best.event.name,
            event_start=best.event.start,
            event_end=best.event.end,
            proximity=best.proximity,
            attribution_score=obs_s,
            p_value=p_value,
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
    max_distance = config.max_distance if config.max_distance is not None else 2 * window_size

    all_results: List[SignificantAttribution] = []

    for pattern, series in support_series_map.items():
        if len(pattern) <= 1:
            continue
        if not series:
            continue

        max_time = len(series)

        # Step 2: Change Point Detection
        change_points = detect_change_points(
            series,
            method=config.change_method,
            threshold=threshold,
            cusum_drift=config.cusum_drift,
            cusum_h=config.cusum_h,
        )
        if not change_points:
            continue

        # Step 3 & 4: Attribution + Significance
        sig_results = permutation_test(
            pattern=pattern,
            change_points=change_points,
            events=events,
            sigma=sigma,
            max_distance=max_distance,
            max_time=max_time,
            n_permutations=config.n_permutations,
            alpha=config.alpha,
            correction_method=config.correction_method,
            attribution_threshold=config.attribution_threshold,
            seed=config.seed,
        )
        all_results.extend(sig_results)

    return all_results


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
        read_transactions_with_baskets,
        compute_item_basket_map,
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
    transactions = read_transactions_with_baskets(input_path)
    _, _, item_transaction_map = compute_item_basket_map(transactions)
    frequents = find_dense_itemsets(
        transactions, window_size, min_support, max_length
    )

    # Step 1: サポート時系列構築
    support_series_map = compute_support_series_all(
        item_transaction_map, frequents, transactions, window_size
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
        sigma=at.get("sigma"),
        max_distance=at.get("max_distance"),
        attribution_threshold=at.get("attribution_threshold", 0.1),
        n_permutations=sg.get("n_permutations", 1000),
        alpha=sg.get("alpha", 0.05),
        correction_method=sg.get("correction_method", "bonferroni"),
        seed=sg.get("seed"),
    )

    # Phase 2 実行
    results = run_attribution_pipeline(
        frequents, support_series_map, events, window_size, min_support, config
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
