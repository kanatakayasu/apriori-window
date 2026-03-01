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
import sys
import time
from dataclasses import dataclass
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
