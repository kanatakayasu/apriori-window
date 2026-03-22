"""
ATT&CK アダプタ。

CICIDS フロー / アラートログを ATT&CK 技術 ID にマッピングし、
Apriori-Window 入力形式のトランザクションに変換する。
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Apriori-Window の密集区間計算を再利用
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python"))
from apriori_window_basket import (
    compute_dense_intervals,
    compute_dense_intervals_with_candidates,
    generate_candidates,
    intersect_sorted_lists,
    prune_candidates,
    read_transactions_with_baskets,
)

from synthetic_cicids import TECHNIQUE_MAP, REVERSE_TECHNIQUE_MAP, APT_PROFILES


def load_transactions(path: str) -> List[List[int]]:
    """トランザクションファイルを読み込む (単一バスケット形式)。"""
    transactions = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                transactions.append([])
            else:
                transactions.append([int(x) for x in line.split()])
    return transactions


def build_item_occurrence_map(
    transactions: List[List[int]],
) -> Dict[int, List[int]]:
    """アイテム → 出現トランザクション ID リストを構築する。"""
    item_map: Dict[int, List[int]] = {}
    for t_id, tx in enumerate(transactions):
        seen = set()
        for item in tx:
            if item not in seen:
                seen.add(item)
                item_map.setdefault(item, []).append(t_id)
    return item_map


def compute_co_occurrence_timestamps(
    items: Tuple[int, ...],
    item_map: Dict[int, List[int]],
) -> List[int]:
    """アイテムセットの共起タイムスタンプを計算する。"""
    lists = [item_map.get(item, []) for item in items]
    if not lists or any(len(l) == 0 for l in lists):
        return []
    return intersect_sorted_lists(lists)


def find_dense_attack_patterns(
    transactions: List[List[int]],
    window_size: int,
    threshold: int,
    max_length: int,
) -> Dict[Tuple[int, ...], List[Tuple[int, int]]]:
    """
    密集攻撃パターンを検出する。

    Apriori-Window のコアアルゴリズムを ATT&CK 技術データに適用。
    """
    item_map = build_item_occurrence_map(transactions)
    frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]] = {}

    current_level: List[Tuple[int, ...]] = []
    singleton_intervals: Dict[int, List[Tuple[int, int]]] = {}

    # 単体技術の密集区間
    for item in sorted(item_map.keys()):
        timestamps = item_map[item]
        if not timestamps:
            continue
        intervals = compute_dense_intervals(timestamps, window_size, threshold)
        singleton_intervals[item] = intervals
        if intervals:
            key = (item,)
            frequents[key] = intervals
            current_level.append(key)

    # 多技術パターン
    k = 2
    while current_level and k <= max_length:
        candidates = generate_candidates(current_level, k)
        candidates = prune_candidates(candidates, set(current_level))
        next_level: List[Tuple[int, ...]] = []

        for candidate in candidates:
            # 単体区間の積集合で候補を絞り込み
            from apriori_window_basket import intersect_interval_lists
            allowed = intersect_interval_lists(
                [singleton_intervals.get(item, []) for item in candidate]
            )
            allowed = [(s, e) for s, e in allowed if e - s >= window_size]
            if not allowed:
                continue

            timestamps = compute_co_occurrence_timestamps(candidate, item_map)
            if not timestamps:
                continue

            intervals = compute_dense_intervals_with_candidates(
                timestamps, window_size, threshold, allowed
            )
            if intervals:
                frequents[candidate] = intervals
                next_level.append(candidate)

        current_level = next_level
        k += 1

    return frequents


def itemset_to_attack_names(itemset: Tuple[int, ...]) -> List[str]:
    """アイテムセットを ATT&CK 技術名に変換する。"""
    return [TECHNIQUE_MAP.get(item, f"Unknown({item})") for item in itemset]


def estimate_campaigns(
    dense_patterns: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    overlap_threshold: float = 0.3,
) -> List[Dict]:
    """
    密集区間の重なりに基づきキャンペーンを推定する。

    Union-Find ベースのクラスタリング。
    """
    # 全密集区間を (itemset, interval) のフラットリストに展開
    entries = []
    for itemset, intervals in dense_patterns.items():
        if len(itemset) < 2:  # 単体技術は除外
            continue
        for interval in intervals:
            entries.append((itemset, interval))

    if not entries:
        return []

    n = len(entries)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # ペアワイズ重なり計算
    for i in range(n):
        for j in range(i + 1, n):
            _, (s1, e1) = entries[i]
            _, (s2, e2) = entries[j]
            overlap_start = max(s1, s2)
            overlap_end = min(e1, e2)
            if overlap_start <= overlap_end:
                overlap_len = overlap_end - overlap_start + 1
                union_len = max(e1, e2) - min(s1, s2) + 1
                if union_len > 0 and overlap_len / union_len >= overlap_threshold:
                    union(i, j)

    # クラスタを集約
    clusters: Dict[int, List[int]] = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(i)

    campaigns = []
    for cluster_id, member_ids in clusters.items():
        techniques = set()
        min_start = float("inf")
        max_end = float("-inf")
        for mid in member_ids:
            itemset, (s, e) = entries[mid]
            techniques.update(itemset)
            min_start = min(min_start, s)
            max_end = max(max_end, e)

        campaigns.append({
            "campaign_id": len(campaigns),
            "techniques": sorted(techniques),
            "technique_names": [TECHNIQUE_MAP.get(t, f"T{t}") for t in sorted(techniques)],
            "start": int(min_start),
            "end": int(max_end),
            "n_patterns": len(member_ids),
        })

    return sorted(campaigns, key=lambda c: c["start"])


def attribute_campaigns(
    campaigns: List[Dict],
    apt_profiles: Dict[str, List[int]] = None,
) -> List[Dict]:
    """
    キャンペーンを既知の APT グループに帰属する。
    Jaccard 類似度ベース。
    """
    if apt_profiles is None:
        apt_profiles = {k: v["techniques"] for k, v in APT_PROFILES.items()}

    results = []
    for campaign in campaigns:
        techs = set(campaign["techniques"])
        scores = {}
        for apt_name, apt_techs in apt_profiles.items():
            apt_set = set(apt_techs)
            intersection = len(techs & apt_set)
            union = len(techs | apt_set)
            scores[apt_name] = intersection / union if union > 0 else 0.0

        best_match = max(scores, key=scores.get)
        results.append({
            **campaign,
            "attribution_scores": scores,
            "best_match": best_match,
            "best_score": scores[best_match],
        })

    return results
