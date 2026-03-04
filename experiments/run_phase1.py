"""
run_phase1.py
=============
生成済みトランザクションに対して Phase 1 と従来法（flatten）を実行し、
実行時間・パターン数を計測するライブラリ + CLI。

ライブラリとして使う場合:
    from run_phase1 import run_experiment, flatten_transactions

使用方法（CLI）:
    python run_phase1.py TXN_FILE \
        --window-size 500 \
        --min-support 50 \
        --max-length 4 \
        --output-dir /path/to/out

出力 JSON フォーマット:
    {
        "txn_file": str,
        "window_size": int,
        "min_support": int,
        "max_length": int,
        "phase1": {
            "pattern_count": int,       # len==1 を含む全パターン数
            "pattern_count_multi": int, # len>=2 のみ
            "intervals_count": int,     # 全パターンの密集区間の総数
            "elapsed_ms": float
        },
        "traditional": { ... }          # 同構造
    }
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple


# apriori_window_suite/python/ を sys.path に追加
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHON_DIR = _REPO_ROOT / "apriori_window_suite" / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from apriori_window_basket import (
    find_dense_itemsets,
    read_transactions_with_baskets,
)


# ---------------------------------------------------------------------------
# 従来法のためのフラット化
# ---------------------------------------------------------------------------

def flatten_transactions(
    transactions: List[List[List[int]]],
) -> List[List[List[int]]]:
    """
    全バスケットを1バスケットに統合する（従来法: 1トランザクション=1バスケット）。

    各トランザクションの全バスケットを union して単一 set にまとめる。
    これにより、異なるバスケット由来のアイテムが同一バスケット内に混入し、
    バスケット間の偽共起が発生する（従来法の挙動を再現）。
    """
    result: List[List[List[int]]] = []
    for baskets in transactions:
        if not baskets:
            result.append([])
            continue
        merged = sorted(set(item for basket in baskets for item in basket))
        result.append([merged])
    return result


# ---------------------------------------------------------------------------
# 結果の集計
# ---------------------------------------------------------------------------

def _count_results(frequents: dict) -> dict:
    """頻出アイテムセットの件数・密集区間総数を集計する。"""
    pattern_count = len(frequents)
    pattern_count_multi = sum(1 for k in frequents if len(k) >= 2)
    intervals_count = sum(len(v) for v in frequents.values())
    return {
        "pattern_count": pattern_count,
        "pattern_count_multi": pattern_count_multi,
        "intervals_count": intervals_count,
    }


# ---------------------------------------------------------------------------
# 実験実行（ライブラリ関数）
# ---------------------------------------------------------------------------

def run_experiment(
    transactions: List[List[List[int]]],
    window_size: int,
    min_support: int,
    max_length: int,
) -> Dict:
    """
    Phase 1 と従来法（flatten）を実行し、結果をまとめて返す。

    計測項目:
        phase1_core_ms   : find_dense_itemsets のみ（Phase 1 コア処理）
        trad_flatten_ms  : flatten_transactions のみ（従来法前処理）
        trad_core_ms     : find_dense_itemsets のみ（従来法コア処理）
        trad_total_ms    : trad_flatten_ms + trad_core_ms

    Returns:
        {
            "phase1": {
                "pattern_count": int, "pattern_count_multi": int,
                "intervals_count": int,
                "core_ms": float       # find_dense_itemsets のみ
            },
            "traditional": {
                "pattern_count": int, "pattern_count_multi": int,
                "intervals_count": int,
                "flatten_ms": float,   # flatten_transactions のみ
                "core_ms": float,      # find_dense_itemsets のみ
                "total_ms": float      # flatten + core
            },
            "observed_spurious": int
        }
    """
    # --- Phase 1 ---
    t0 = time.perf_counter()
    phase1_frequents = find_dense_itemsets(
        transactions, window_size, min_support, max_length
    )
    phase1_core_ms = (time.perf_counter() - t0) * 1000.0

    phase1_stats = _count_results(phase1_frequents)
    phase1_stats["core_ms"] = phase1_core_ms

    # --- 従来法 ---
    # 前処理（flatten）の時間を分離して計測
    t0 = time.perf_counter()
    flat_transactions = flatten_transactions(transactions)
    trad_flatten_ms = (time.perf_counter() - t0) * 1000.0

    # コア処理（find_dense_itemsets）の時間
    t0 = time.perf_counter()
    trad_frequents = find_dense_itemsets(
        flat_transactions, window_size, min_support, max_length
    )
    trad_core_ms = (time.perf_counter() - t0) * 1000.0

    trad_stats = _count_results(trad_frequents)
    trad_stats["flatten_ms"] = trad_flatten_ms
    trad_stats["core_ms"] = trad_core_ms
    trad_stats["total_ms"] = trad_flatten_ms + trad_core_ms

    # 従来法が検出して Phase 1 が検出しなかったパターン数（観測された偽共起）
    phase1_keys = set(k for k in phase1_frequents if len(k) >= 2)
    trad_keys = set(k for k in trad_frequents if len(k) >= 2)
    observed_spurious = len(trad_keys - phase1_keys)

    return {
        "phase1": phase1_stats,
        "traditional": trad_stats,
        "observed_spurious": observed_spurious,
    }


# ---------------------------------------------------------------------------
# CLI エントリーポイント
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1 と従来法の実行・計時"
    )
    parser.add_argument("txn_file", help="入力トランザクションファイルのパス")
    parser.add_argument("--window-size", type=int, default=500)
    parser.add_argument("--min-support", type=int, default=50)
    parser.add_argument("--max-length", type=int, default=4)
    parser.add_argument("--output-dir", type=str, default=".")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    txn_path = Path(args.txn_file)
    if not txn_path.exists():
        print(f"[run_phase1] ERROR: {txn_path} not found", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{txn_path.stem}_phase1_results.json"

    print(f"[run_phase1] Reading {txn_path}")
    transactions = read_transactions_with_baskets(str(txn_path))
    print(f"[run_phase1] {len(transactions)} transactions loaded")

    result = run_experiment(
        transactions, args.window_size, args.min_support, args.max_length
    )

    p = result["phase1"]
    t = result["traditional"]
    print(f"[run_phase1] Phase 1   : patterns={p['pattern_count']}, "
          f"multi={p['pattern_count_multi']}, intervals={p['intervals_count']}, "
          f"elapsed={p['elapsed_ms']:.1f}ms")
    print(f"[run_phase1] Traditional: patterns={t['pattern_count']}, "
          f"multi={t['pattern_count_multi']}, intervals={t['intervals_count']}, "
          f"elapsed={t['elapsed_ms']:.1f}ms")
    print(f"[run_phase1] Observed spurious (trad - phase1): {result['observed_spurious']}")

    output = {
        "txn_file": str(txn_path),
        "window_size": args.window_size,
        "min_support": args.min_support,
        "max_length": args.max_length,
        **result,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[run_phase1] Wrote {out_file}")


if __name__ == "__main__":
    main()
