"""
event_correlator.py — Phase 2: 密集区間 × 外部イベント 時間的関係付け

設計書: doc/phase2_impl_plan.md

Phase 1 の find_dense_itemsets が返す frequents と
JSON 形式のイベントリストを突き合わせ、以下 6 種の時間的関係を列挙する:
  DenseFollowsEvent  (DFE) : 密集終了直後にイベント開始
  EventFollowsDense  (EFD) : イベント終了直後に密集開始
  DenseContainsEvent (DCE) : 密集がイベントを包含
  EventContainsDense (ECD) : イベントが密集を包含
  DenseOverlapsEvent (DOE) : 密集が先に始まり部分重複
  EventOverlapsDense (EOD) : イベントが先に始まり部分重複
"""
import csv
import json
import math
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# apriori_window_basket は同じ python/ ディレクトリにある
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apriori_window_basket import (  # noqa: E402
    find_dense_itemsets,
    read_transactions_with_baskets,
)

# ---------------------------------------------------------------------------
# 型定義
# ---------------------------------------------------------------------------

Frequents = Dict[Tuple[int, ...], List[Tuple[int, int]]]


@dataclass
class Event:
    event_id: str
    name: str
    start: int  # inclusive（トランザクション ID）
    end: int    # inclusive（トランザクション ID）


@dataclass
class RelationMatch:
    itemset: Tuple[int, ...]
    dense_start: int
    dense_end: int
    event: Event
    relation_type: str          # "DenseFollowsEvent" 等
    overlap_length: Optional[int]  # DOE / EOD のみ。他は None

# ---------------------------------------------------------------------------
# イベントファイル読み込み
# ---------------------------------------------------------------------------

def read_events(path: str) -> List[Event]:
    """
    JSON 形式のイベントファイルを読み込む。

    バリデーション:
        - event_id の一意性を確認（重複 → ValueError）
        - start <= end を確認（逆転 → ValueError）
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    events: List[Event] = []
    seen_ids: set = set()
    for entry in raw:
        eid = entry["event_id"]
        if eid in seen_ids:
            raise ValueError(f"Duplicate event_id: {eid!r}")
        seen_ids.add(eid)
        s, e = int(entry["start"]), int(entry["end"])
        if s > e:
            raise ValueError(f"event_id={eid!r}: start({s}) > end({e})")
        events.append(Event(event_id=eid, name=entry["name"], start=s, end=e))

    return events

# ---------------------------------------------------------------------------
# 時間的関係の判定ロジック
# ---------------------------------------------------------------------------

def satisfies_follows(te_i: int, ts_j: int, epsilon: int) -> bool:
    """
    Follows(I → J): I が終わった直後に J が始まる。
    条件: te_i - epsilon <= ts_j <= te_i + epsilon
    """
    return te_i - epsilon <= ts_j <= te_i + epsilon


def satisfies_contains(
    ts_i: int, te_i: int, ts_j: int, te_j: int, epsilon: int
) -> bool:
    """
    Contains(I ⊇ J): I が J を包含する。
    条件: ts_i <= ts_j  かつ  te_i + epsilon >= te_j
    """
    return ts_i <= ts_j and te_i + epsilon >= te_j


def satisfies_overlaps(
    ts_i: int,
    te_i: int,
    ts_j: int,
    te_j: int,
    epsilon: int,
    d_0: int,
) -> Tuple[bool, Optional[int]]:
    """
    Overlaps(I ⊙ J): I が先に始まり J と部分的に重なる。
    条件:
        ts_i < ts_j                   # I が先
        te_i - ts_j >= d_0 - epsilon  # 重複長 >= d_0（許容誤差あり）
        te_i < te_j + epsilon         # 完全包含でない

    返り値: (成立するか, 重複長 te_i - ts_j)
    """
    if ts_i >= ts_j:
        return False, None
    overlap = te_i - ts_j
    if overlap < d_0 - epsilon:
        return False, None
    if te_i >= te_j + epsilon:
        return False, None
    return True, overlap

# ---------------------------------------------------------------------------
# マッチング（総当たり）
# ---------------------------------------------------------------------------

def match_all(
    frequents: Frequents,
    events: List[Event],
    epsilon: int,
    d_0: int,
) -> List[RelationMatch]:
    """
    全密集区間 × 全イベントの総当たりマッチング。

    計算量: O(|frequents| × avg_intervals × |events|)
    各ペアで 6 種の関係を判定し、成立するもの全てを結果リストに追加する。
    """
    results: List[RelationMatch] = []

    for itemset, intervals in frequents.items():
        for (ts_i, te_i) in intervals:
            for event in events:
                ts_j, te_j = event.start, event.end

                # --- Follows 系（2 方向）---
                if satisfies_follows(te_i, ts_j, epsilon):
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, event, "DenseFollowsEvent", None)
                    )
                if satisfies_follows(te_j, ts_i, epsilon):
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, event, "EventFollowsDense", None)
                    )

                # --- Contains 系（2 方向）---
                if satisfies_contains(ts_i, te_i, ts_j, te_j, epsilon):
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, event, "DenseContainsEvent", None)
                    )
                if satisfies_contains(ts_j, te_j, ts_i, te_i, epsilon):
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, event, "EventContainsDense", None)
                    )

                # --- Overlaps 系（2 方向）---
                ok, ovl = satisfies_overlaps(ts_i, te_i, ts_j, te_j, epsilon, d_0)
                if ok:
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, event, "DenseOverlapsEvent", ovl)
                    )
                ok, ovl = satisfies_overlaps(ts_j, te_j, ts_i, te_i, epsilon, d_0)
                if ok:
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, event, "EventOverlapsDense", ovl)
                    )

    # ソート: アイテム数降順 → dense_start 昇順 → event_id 昇順 → relation_type 昇順
    results.sort(
        key=lambda m: (
            -len(m.itemset),
            m.dense_start,
            m.event.event_id,
            m.relation_type,
        )
    )
    return results

# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

def _format_itemset(itemset: Tuple[int, ...]) -> str:
    """Phase 1 と同じ形式: "[{1, 2}]" """
    body = ", ".join(str(i) for i in itemset)
    return f"[{{{body}}}]"


def write_relations_csv(
    path: str,
    results: List[RelationMatch],
    epsilon: int,
    d_0: int,
) -> None:
    """
    relations.csv を書き出す。

    カラム:
        pattern_components, dense_start, dense_end,
        event_id, event_name, relation_type,
        overlap_length, epsilon, d_0
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([
            "pattern_components", "dense_start", "dense_end",
            "event_id", "event_name", "relation_type",
            "overlap_length", "epsilon", "d_0",
        ])
        for m in results:
            writer.writerow([
                _format_itemset(m.itemset),
                m.dense_start,
                m.dense_end,
                m.event.event_id,
                m.event.name,
                m.relation_type,
                "" if m.overlap_length is None else m.overlap_length,
                epsilon,
                d_0,
            ])

# ---------------------------------------------------------------------------
# Stage 1: Mutual Information Pre-filter
# ---------------------------------------------------------------------------

def _to_binary_series(
    intervals: List[Tuple[int, int]], t_min: int, t_max: int,
) -> List[int]:
    """区間リストを [t_min, t_max] 上の二値時系列に変換する。"""
    length = t_max - t_min + 1
    series = [0] * length
    for s, e in intervals:
        lo = max(s, t_min) - t_min
        hi = min(e, t_max) - t_min
        for t in range(lo, hi + 1):
            series[t] = 1
    return series


def compute_mi(x: List[int], y: List[int]) -> float:
    """二値時系列 x, y の相互情報量 I(X;Y) を計算する。"""
    n = len(x)
    if n == 0:
        return 0.0
    # 同時分布の計数
    counts = [[0, 0], [0, 0]]
    for i in range(n):
        counts[x[i]][y[i]] += 1
    mi = 0.0
    for a in range(2):
        for b in range(2):
            p_xy = counts[a][b] / n
            if p_xy == 0:
                continue
            p_x = sum(counts[a]) / n
            p_y = (counts[0][b] + counts[1][b]) / n
            if p_x == 0 or p_y == 0:
                continue
            mi += p_xy * math.log(p_xy / (p_x * p_y))
    return mi


def compute_mi_scores(
    frequents: Frequents,
    events: List[Event],
    time_resolution: int = 1,
) -> Dict[Tuple[Tuple[int, ...], str], float]:
    """
    全 (パターン, イベント) ペアの MI スコアを計算する。

    返り値: {(itemset_key, event_id): mi_score}
    """
    if not frequents or not events:
        return {}

    # 時間軸の範囲を決定
    all_starts = []
    all_ends = []
    for intervals in frequents.values():
        for s, e in intervals:
            all_starts.append(s)
            all_ends.append(e)
    for ev in events:
        all_starts.append(ev.start)
        all_ends.append(ev.end)
    t_min = min(all_starts)
    t_max = max(all_ends)

    # パターンごとの二値時系列を事前計算
    pattern_series: Dict[Tuple[int, ...], List[int]] = {}
    for itemset, intervals in frequents.items():
        pattern_series[itemset] = _to_binary_series(intervals, t_min, t_max)

    # イベントごとの二値時系列を事前計算
    event_series: Dict[str, List[int]] = {}
    for ev in events:
        event_series[ev.event_id] = _to_binary_series(
            [(ev.start, ev.end)], t_min, t_max
        )

    # MI 計算
    scores: Dict[Tuple[Tuple[int, ...], str], float] = {}
    for itemset in frequents:
        x = pattern_series[itemset]
        for ev in events:
            y = event_series[ev.event_id]
            scores[(itemset, ev.event_id)] = compute_mi(x, y)
    return scores


def mi_prefilter(
    frequents: Frequents,
    events: List[Event],
    mi_threshold: float = 0.01,
    time_resolution: int = 1,
) -> Tuple[Dict[Tuple[Tuple[int, ...], str], float], List[Tuple[Tuple[int, ...], str]]]:
    """
    Stage 1: MI スコアを計算し、閾値以上のペアのみ返す。

    返り値: (全スコア辞書, 通過ペアリスト)
    """
    scores = compute_mi_scores(frequents, events, time_resolution)
    passed = [pair for pair, mi in scores.items() if mi > mi_threshold]
    return scores, passed


# ---------------------------------------------------------------------------
# Stage 2: Sweep Line Matching
# ---------------------------------------------------------------------------

def match_sweep_line(
    frequents: Frequents,
    events: List[Event],
    epsilon: int,
    d_0: int,
    candidate_pairs: Optional[List[Tuple[Tuple[int, ...], str]]] = None,
) -> List[RelationMatch]:
    """
    Stage 2: 走査線アルゴリズムで Allen 関係を判定する。

    candidate_pairs が指定された場合、そのペアのみ判定する。
    None の場合は全ペアを判定する（Stage 0 相当）。

    計算量: O((n + m) log(n + m) + K)
    """
    # candidate_pairs からイベントIDセットをパターンごとに構築
    if candidate_pairs is not None:
        pair_set: Dict[Tuple[int, ...], set] = {}
        for itemset, eid in candidate_pairs:
            pair_set.setdefault(itemset, set()).add(eid)
    else:
        pair_set = None

    # イベントを event_id → Event のマップに
    event_map: Dict[str, Event] = {ev.event_id: ev for ev in events}

    results: List[RelationMatch] = []

    for itemset, intervals in frequents.items():
        # このパターンの候補イベント
        if pair_set is not None:
            if itemset not in pair_set:
                continue
            target_events = [event_map[eid] for eid in pair_set[itemset] if eid in event_map]
        else:
            target_events = events

        if not target_events or not intervals:
            continue

        # イベントポイントを作成してソート
        # (time, type, data) の形式
        # type: 0 = dense_start, 1 = event_start, 2 = dense_end, 3 = event_end
        points = []
        for idx, (s, e) in enumerate(intervals):
            points.append((s, 0, idx))  # dense start
            points.append((e, 2, idx))  # dense end
        for ev in target_events:
            points.append((ev.start, 1, ev.event_id))  # event start
            points.append((ev.end, 3, ev.event_id))    # event end
        points.sort(key=lambda p: (p[0], p[1]))

        # 走査線: 各密集区間とアクティブなイベントの関係をチェック
        # 実装上は区間同士の重なり検出 → Allen 関係判定
        # 効率的なアプローチ: 密集区間ごとに近傍イベントを探索
        sorted_intervals = sorted(enumerate(intervals), key=lambda x: x[1][0])
        sorted_events = sorted(target_events, key=lambda e: e.start)

        # 二ポインタで近傍ペアを列挙
        ev_idx = 0
        for _, (ts_i, te_i) in sorted_intervals:
            # イベントポインタを密集区間の範囲に合わせる
            # ts_j <= te_i + epsilon の最初のイベントから探索
            while ev_idx > 0 and sorted_events[ev_idx - 1].start > te_i + epsilon:
                ev_idx -= 1
            # 開始位置を巻き戻す（前方にもマッチがある可能性）
            scan_idx = 0
            for scan_idx_candidate in range(len(sorted_events)):
                if sorted_events[scan_idx_candidate].end >= ts_i - epsilon:
                    scan_idx = scan_idx_candidate
                    break
            else:
                continue

            for j in range(scan_idx, len(sorted_events)):
                ev = sorted_events[j]
                ts_j, te_j = ev.start, ev.end

                # このイベントが密集区間から離れすぎたら終了
                if ts_j > te_i + epsilon and te_j < ts_i - epsilon:
                    # まだ後方に overlaps 等がある可能性があるので continue
                    pass
                if ts_j > te_i + epsilon + (te_i - ts_i):
                    break

                # 6 関係を判定
                if satisfies_follows(te_i, ts_j, epsilon):
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, ev, "DenseFollowsEvent", None)
                    )
                if satisfies_follows(te_j, ts_i, epsilon):
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, ev, "EventFollowsDense", None)
                    )
                if satisfies_contains(ts_i, te_i, ts_j, te_j, epsilon):
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, ev, "DenseContainsEvent", None)
                    )
                if satisfies_contains(ts_j, te_j, ts_i, te_i, epsilon):
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, ev, "EventContainsDense", None)
                    )
                ok, ovl = satisfies_overlaps(ts_i, te_i, ts_j, te_j, epsilon, d_0)
                if ok:
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, ev, "DenseOverlapsEvent", ovl)
                    )
                ok, ovl = satisfies_overlaps(ts_j, te_j, ts_i, te_i, epsilon, d_0)
                if ok:
                    results.append(
                        RelationMatch(itemset, ts_i, te_i, ev, "EventOverlapsDense", ovl)
                    )

    results.sort(
        key=lambda m: (-len(m.itemset), m.dense_start, m.event.event_id, m.relation_type)
    )
    return results


# ---------------------------------------------------------------------------
# Stage 3: Permutation-based Significance Testing
# ---------------------------------------------------------------------------

@dataclass
class SignificantRelation:
    """Stage 3 出力: 有意な時間的関係。"""
    itemset: Tuple[int, ...]
    event_id: str
    relation_type: str
    observed_count: int
    p_value: float
    adjusted_p_value: float
    effect_size: float
    mi_score: Optional[float] = None


def _cyclic_shift_events(
    events: List[Event], offset: int, t_min: int, t_max: int,
) -> List[Event]:
    """イベント群を循環シフトする。"""
    span = t_max - t_min + 1
    shifted = []
    for ev in events:
        new_start = t_min + (ev.start - t_min + offset) % span
        new_end = t_min + (ev.end - t_min + offset) % span
        # 循環で折り返す場合は元の長さを保持
        if new_end < new_start:
            new_end = new_start + (ev.end - ev.start)
            if new_end > t_max:
                new_end = t_max
        shifted.append(Event(
            event_id=ev.event_id, name=ev.name,
            start=new_start, end=new_end,
        ))
    return shifted


def _count_relations(
    results: List[RelationMatch],
) -> Dict[Tuple[Tuple[int, ...], str, str], int]:
    """(itemset, event_id, relation_type) ごとのマッチ数を集計する。"""
    counts: Dict[Tuple[Tuple[int, ...], str, str], int] = {}
    for m in results:
        key = (m.itemset, m.event.event_id, m.relation_type)
        counts[key] = counts.get(key, 0) + 1
    return counts


def permutation_test(
    frequents: Frequents,
    events: List[Event],
    epsilon: int,
    d_0: int,
    n_permutations: int = 1000,
    alpha: float = 0.05,
    correction_method: str = "westfall_young",
    seed: Optional[int] = None,
    match_fn=None,
    mi_scores: Optional[Dict[Tuple[Tuple[int, ...], str], float]] = None,
) -> List[SignificantRelation]:
    """
    Stage 3: 置換検定で有意な時間的関係のみ抽出する。

    match_fn: マッチング関数（デフォルト: match_all）。Stage 2 通過後に呼ぶ場合は
              match_sweep_line を渡す。
    """
    if match_fn is None:
        match_fn = match_all

    if seed is not None:
        random.seed(seed)

    # 時間軸の範囲
    all_times = []
    for intervals in frequents.values():
        for s, e in intervals:
            all_times.extend([s, e])
    for ev in events:
        all_times.extend([ev.start, ev.end])
    if not all_times:
        return []
    t_min = min(all_times)
    t_max = max(all_times)

    # 観測統計量
    observed_results = match_fn(frequents, events, epsilon, d_0)
    observed_counts = _count_relations(observed_results)

    if not observed_counts:
        return []

    # 置換テスト
    perm_exceed: Dict[Tuple[Tuple[int, ...], str, str], int] = {
        k: 0 for k in observed_counts
    }
    # Westfall-Young: 各置換での最大統計量を記録
    max_stats_per_perm: List[float] = []

    span = t_max - t_min + 1

    for j in range(n_permutations):
        offset = random.randint(1, span - 1)
        shifted_events = _cyclic_shift_events(events, offset, t_min, t_max)
        perm_results = match_fn(frequents, shifted_events, epsilon, d_0)
        perm_counts = _count_relations(perm_results)

        max_stat = 0.0
        for key, c_obs in observed_counts.items():
            c_perm = perm_counts.get(key, 0)
            if c_perm >= c_obs:
                perm_exceed[key] += 1
            if c_perm > max_stat:
                max_stat = c_perm
        max_stats_per_perm.append(max_stat)

    # p 値計算
    raw_p: Dict[Tuple[Tuple[int, ...], str, str], float] = {}
    for key, c_obs in observed_counts.items():
        raw_p[key] = (perm_exceed[key] + 1) / (n_permutations + 1)

    # 多重検定補正
    adjusted_p: Dict[Tuple[Tuple[int, ...], str, str], float] = {}
    if correction_method == "bonferroni":
        n_tests = len(observed_counts)
        for key, p in raw_p.items():
            adjusted_p[key] = min(1.0, p * n_tests)
    else:
        # Westfall-Young stepdown
        sorted_keys = sorted(raw_p.keys(), key=lambda k: raw_p[k])
        max_stats_sorted = sorted(max_stats_per_perm, reverse=True)
        for key in sorted_keys:
            c_obs = observed_counts[key]
            exceed_count = sum(1 for ms in max_stats_per_perm if ms >= c_obs)
            adjusted_p[key] = (exceed_count + 1) / (n_permutations + 1)

    # 有意な関係のみ抽出
    significant: List[SignificantRelation] = []
    for key, adj_p in adjusted_p.items():
        itemset, event_id, relation_type = key
        c_obs = observed_counts[key]
        p_raw = raw_p[key]

        # 効果量: c_obs / E[c_perm]
        expected = sum(
            _count_relations(
                match_fn(
                    frequents,
                    _cyclic_shift_events(events, random.randint(1, span - 1), t_min, t_max),
                    epsilon, d_0,
                )
            ).get(key, 0)
            for _ in range(0)  # 期待値は置換分布の平均で近似
        )
        # 近似: perm_exceed から推定
        mean_perm = (n_permutations - perm_exceed[key]) * c_obs / max(n_permutations, 1)
        if mean_perm > 0:
            effect = c_obs / mean_perm
        else:
            effect = float(c_obs) if c_obs > 0 else 0.0

        mi = None
        if mi_scores is not None:
            mi = mi_scores.get((itemset, event_id))

        if adj_p < alpha:
            significant.append(SignificantRelation(
                itemset=itemset,
                event_id=event_id,
                relation_type=relation_type,
                observed_count=c_obs,
                p_value=p_raw,
                adjusted_p_value=adj_p,
                effect_size=effect,
                mi_score=mi,
            ))

    significant.sort(key=lambda s: (s.adjusted_p_value, -len(s.itemset)))
    return significant


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    """4 段パイプラインの設定。"""
    epsilon: int = 0
    d_0: int = 0
    # Stage 1
    stage1_enabled: bool = True
    mi_threshold: float = 0.01
    time_resolution: int = 1
    # Stage 2
    stage2_enabled: bool = True
    # Stage 3
    stage3_enabled: bool = True
    n_permutations: int = 1000
    shuffle_strategy: str = "cyclic_shift"
    alpha: float = 0.05
    correction_method: str = "westfall_young"
    seed: Optional[int] = None


@dataclass
class PipelineResult:
    """パイプラインの全段階の結果。"""
    # Stage 0
    brute_force_results: List[RelationMatch]
    # Stage 1
    mi_scores: Optional[Dict[Tuple[Tuple[int, ...], str], float]] = None
    mi_passed_pairs: Optional[List[Tuple[Tuple[int, ...], str]]] = None
    # Stage 2
    sweep_results: Optional[List[RelationMatch]] = None
    # Stage 3
    significant_relations: Optional[List[SignificantRelation]] = None


def run_pipeline(
    frequents: Frequents,
    events: List[Event],
    config: Optional[PipelineConfig] = None,
) -> PipelineResult:
    """
    4 段パイプラインを実行する。

    Stage 0: Brute-Force Baseline（常に実行 — 検証用）
    Stage 1: MI Pre-filter（config.stage1_enabled）
    Stage 2: Sweep Line Matching（config.stage2_enabled）
    Stage 3: Permutation-based Significance Testing（config.stage3_enabled）
    """
    if config is None:
        config = PipelineConfig()

    # Stage 0: Brute-Force
    brute_force = match_all(frequents, events, config.epsilon, config.d_0)

    result = PipelineResult(brute_force_results=brute_force)

    # Stage 1: MI Pre-filter
    candidate_pairs = None
    mi_scores_dict = None
    if config.stage1_enabled:
        mi_scores_dict, passed = mi_prefilter(
            frequents, events,
            mi_threshold=config.mi_threshold,
            time_resolution=config.time_resolution,
        )
        result.mi_scores = mi_scores_dict
        result.mi_passed_pairs = passed
        candidate_pairs = passed

    # Stage 2: Sweep Line Matching
    if config.stage2_enabled:
        sweep = match_sweep_line(
            frequents, events, config.epsilon, config.d_0,
            candidate_pairs=candidate_pairs,
        )
        result.sweep_results = sweep
    else:
        # Stage 2 無効時は Stage 0 結果を通す（候補ペアフィルタのみ適用）
        if candidate_pairs is not None:
            pair_set = set(candidate_pairs)
            result.sweep_results = [
                m for m in brute_force
                if (m.itemset, m.event.event_id) in pair_set
            ]
        else:
            result.sweep_results = brute_force

    # Stage 3: Permutation-based Significance Testing
    if config.stage3_enabled:
        match_fn = match_all  # 置換テストでは brute-force で正確に計算
        sig = permutation_test(
            frequents, events, config.epsilon, config.d_0,
            n_permutations=config.n_permutations,
            alpha=config.alpha,
            correction_method=config.correction_method,
            seed=config.seed,
            match_fn=match_fn,
            mi_scores=mi_scores_dict,
        )
        result.significant_relations = sig

    return result


# ---------------------------------------------------------------------------
# CSV 出力（パイプライン対応）
# ---------------------------------------------------------------------------

def write_significant_csv(
    path: str,
    relations: List[SignificantRelation],
    epsilon: int,
    d_0: int,
) -> None:
    """Stage 3 の有意な関係を CSV に書き出す。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([
            "pattern_components", "event_id", "relation_type",
            "observed_count", "p_value", "adjusted_p_value",
            "effect_size", "mi_score", "epsilon", "d_0",
        ])
        for r in relations:
            writer.writerow([
                _format_itemset(r.itemset),
                r.event_id,
                r.relation_type,
                r.observed_count,
                f"{r.p_value:.6f}",
                f"{r.adjusted_p_value:.6f}",
                f"{r.effect_size:.4f}",
                f"{r.mi_score:.6f}" if r.mi_score is not None else "",
                epsilon,
                d_0,
            ])


# ---------------------------------------------------------------------------
# settings.json からの一括実行
# ---------------------------------------------------------------------------

def _write_patterns_csv(
    path: str,
    frequents: Frequents,
) -> None:
    """Phase 1 のパターン出力を CSV に書き出す（Phase 1 の run_from_settings と同じ形式）。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("pattern_components,pattern_gaps,pattern_size,intervals_count,intervals\n")
        for itemset, intervals in sorted(
            frequents.items(), key=lambda kv: (-len(kv[0]), kv[0])
        ):
            if len(itemset) <= 1:
                continue
            body = ", ".join(str(i) for i in itemset)
            pattern_components = f'"[{{{body}}}]"'
            pattern_gaps = '"[]"'
            count = len(intervals)
            if count == 0:
                intervals_str = '""'
            else:
                joined = ";".join(f"({s},{e})" for s, e in intervals)
                intervals_str = f'"{joined}"'
            f.write(
                f"{pattern_components},{pattern_gaps},{len(itemset)},{count},{intervals_str}\n"
            )


def run_from_settings(settings_path: str) -> Tuple[str, Optional[str]]:
    """
    settings.json を読み込んで Phase 1 → Phase 2 を実行する。

    event_file が設定されていない場合は Phase 1 のみ実行する（後退互換）。

    返り値: (patterns_csv_path, relations_csv_path or None)
    """
    settings = json.loads(Path(settings_path).read_text(encoding="utf-8"))

    # --- パス解決 ---
    input_path = Path(settings["input_file"]["dir"]) / settings["input_file"]["file_name"]
    output_dir = settings["output_files"]["dir"]
    patterns_name = settings["output_files"]["patterns_output_file_name"]
    patterns_path = str(Path(output_dir) / patterns_name)

    window_size = int(settings["apriori_parameters"]["window_size"])
    min_support = int(settings["apriori_parameters"]["min_support"])
    max_length = int(settings["apriori_parameters"]["max_length"])

    # --- Phase 1 ---
    transactions = read_transactions_with_baskets(str(input_path))
    frequents = find_dense_itemsets(transactions, window_size, min_support, max_length)
    _write_patterns_csv(patterns_path, frequents)

    # --- Phase 2（event_file がある場合のみ）---
    event_file_cfg = settings.get("event_file")
    if event_file_cfg is None:
        return patterns_path, None

    event_path = Path(event_file_cfg["dir"]) / event_file_cfg["file_name"]
    trp = settings.get("temporal_relation_parameters", {})
    epsilon = int(trp.get("epsilon", 0))
    d_0 = int(trp.get("d_0", 0))

    events = read_events(str(event_path))
    results = match_all(frequents, events, epsilon, d_0)

    relations_name = settings["output_files"]["relations_output_file_name"]
    relations_path = str(Path(output_dir) / relations_name)
    write_relations_csv(relations_path, results, epsilon, d_0)

    return patterns_path, relations_path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    default_settings = Path(__file__).resolve().parents[1] / "data" / "settings_phase2.json"
    settings_path = sys.argv[1] if len(sys.argv) > 1 else str(default_settings)

    start = time.perf_counter()
    p_path, r_path = run_from_settings(settings_path)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    print(f"パターン出力: {p_path}")
    if r_path:
        print(f"関係出力:     {r_path}")
    print(f"Elapsed time: {elapsed_ms:.3f} ms")


if __name__ == "__main__":
    main()
