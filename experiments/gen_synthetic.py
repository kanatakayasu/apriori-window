"""
gen_synthetic.py
================
合成トランザクションデータの生成ライブラリ + CLI。

使用方法（CLI）:
    python gen_synthetic.py \
        --model poisson \
        --n-transactions 10000 \
        --n-items 200 \
        --g 10 \
        --lambda-baskets 2.0 \
        --lambda-basket-size 3.0 \
        --alpha-n 2.5 \
        --alpha-k 2.5 \
        --p-same 0.8 \
        --zipf-alpha 1.2 \
        --min-support 50 \
        --max-length 4 \
        --seed 0 \
        --output-dir /path/to/out \
        --prefix A1_P_lambda2.0 \
        [--skip-gt]

ライブラリとして使う場合:
    from gen_synthetic import generate_transactions, compute_ground_truth, write_transactions

出力ファイル:
    {output_dir}/{prefix}_seed{seed}.txt       : トランザクションファイル
    {output_dir}/{prefix}_seed{seed}_gt.json   : Ground Truth (SPR 等)

トランザクションファイル形式:
    1行 = 1トランザクション
    " | " でバスケットを区切る（apriori_window_basket.py の read_transactions_with_baskets と互換）
"""

import argparse
import json
import math
import random
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Poisson サンプラー（Knuth アルゴリズム）
# ---------------------------------------------------------------------------

def sample_poisson(lam: float, rng: random.Random) -> int:
    """Poisson(λ) からサンプリング（Knuth アルゴリズム）。"""
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= rng.random()
    return k - 1


def sample_poisson_min1(lam: float, rng: random.Random) -> int:
    """Poisson(λ) からサンプリングし、最小値を 1 にクリップ。"""
    return max(1, sample_poisson(lam, rng))


# ---------------------------------------------------------------------------
# PowerLaw サンプラー（逆変換法）
# ---------------------------------------------------------------------------

def sample_powerlaw_min1(alpha: float, rng: random.Random) -> int:
    """
    連続冪乗則 p(x) ∝ x^{-α}（x >= 1）から離散サンプルを生成。

    逆変換法:
        x = (1 - u)^{-1 / (α - 1)}  (α > 1)
    最小値は 1、最大値は 10000 にクリップ。
    """
    if alpha <= 1:
        raise ValueError("alpha must be > 1 for powerlaw sampling.")
    u = max(rng.random(), 1e-10)
    x = (1.0 - u) ** (-1.0 / (alpha - 1.0))
    return max(1, min(int(x), 10000))


# ---------------------------------------------------------------------------
# Zipf 重みの事前計算
# ---------------------------------------------------------------------------

def compute_zipf_weights(n_items: int, zipf_alpha: float) -> List[float]:
    """アイテム 0..n_items-1 の Zipf 重みを返す（正規化なし）。"""
    return [1.0 / ((i + 1) ** zipf_alpha) for i in range(n_items)]


# ---------------------------------------------------------------------------
# アイテムカテゴリの割り当て
# ---------------------------------------------------------------------------

def build_category_items(n_items: int, n_categories: int) -> Dict[int, List[int]]:
    """カテゴリ → アイテムリスト の辞書を構築（均等割り当て）。"""
    cat_items: Dict[int, List[int]] = defaultdict(list)
    for item in range(n_items):
        cat_items[item % n_categories].append(item)
    return dict(cat_items)


# ---------------------------------------------------------------------------
# 1バスケットのアイテムサンプリング
# ---------------------------------------------------------------------------

def sample_basket(
    k: int,
    main_cat: int,
    cat_items: Dict[int, List[int]],
    all_items: List[int],
    zipf_weights: List[float],
    p_same: float,
    rng: random.Random,
) -> List[int]:
    """
    1バスケットに含まれる k アイテムをサンプリングする。

    - p_same の確率で main_cat から、1-p_same の確率で全アイテムから選ぶ
    - 重複を除いてソート済みリストを返す
    """
    items_in_cat = cat_items[main_cat]
    cat_zipf_weights = [zipf_weights[item] for item in items_in_cat]

    sampled: set = set()
    attempts = 0
    max_attempts = k * 20
    while len(sampled) < k and attempts < max_attempts:
        attempts += 1
        if rng.random() < p_same and items_in_cat:
            chosen = rng.choices(items_in_cat, weights=cat_zipf_weights, k=1)[0]
        else:
            chosen = rng.choices(all_items, weights=zipf_weights, k=1)[0]
        sampled.add(chosen)

    return sorted(sampled)


# ---------------------------------------------------------------------------
# トランザクション生成（メイン関数）
# ---------------------------------------------------------------------------

def generate_transactions(
    n_transactions: int,
    n_items: int,
    n_categories: int,
    lambda_baskets: float,
    lambda_basket_size: float,
    alpha_n: float,
    alpha_k: float,
    p_same: float,
    zipf_alpha: float,
    model: str,
    rng: random.Random,
) -> List[List[List[int]]]:
    """
    合成トランザクションを生成する。

    Args:
        n_transactions: トランザクション数
        n_items: アイテム語彙サイズ
        n_categories: カテゴリ数
        lambda_baskets: Poisson モデル時の平均バスケット数（PowerLaw では alpha_n を使用）
        lambda_basket_size: Poisson モデル時の平均バスケット内アイテム数
        alpha_n: PowerLaw モデル時のバスケット数指数（α > 1）
        alpha_k: PowerLaw モデル時のアイテム数指数（α > 1）
        p_same: 同一カテゴリから選ぶ確率
        zipf_alpha: Zipf 分布の指数
        model: "poisson" または "powerlaw"
        rng: 乱数生成器

    Returns:
        transactions[t][b][i]: トランザクション t のバスケット b のアイテム i
    """
    all_items = list(range(n_items))
    zipf_weights = compute_zipf_weights(n_items, zipf_alpha)
    cat_items = build_category_items(n_items, n_categories)
    n_cats = len(cat_items)

    transactions: List[List[List[int]]] = []

    for _ in range(n_transactions):
        # バスケット数のサンプリング
        if model == "poisson":
            n_baskets = sample_poisson_min1(lambda_baskets, rng)
        else:
            n_baskets = sample_powerlaw_min1(alpha_n, rng)

        baskets: List[List[int]] = []
        for _ in range(n_baskets):
            # バスケット内アイテム数のサンプリング
            if model == "poisson":
                k = sample_poisson_min1(lambda_basket_size, rng)
            else:
                k = sample_powerlaw_min1(alpha_k, rng)

            main_cat = rng.randint(0, n_cats - 1)
            basket = sample_basket(
                k, main_cat, cat_items, all_items, zipf_weights, p_same, rng
            )
            baskets.append(basket)

        transactions.append(baskets)

    return transactions


# ---------------------------------------------------------------------------
# トランザクションファイルの書き出し・読み込み
# ---------------------------------------------------------------------------

def write_transactions(path: str, transactions: List[List[List[int]]]) -> None:
    """トランザクションをファイルに書き出す（" | " でバスケット区切り）。"""
    with open(path, "w", encoding="utf-8") as f:
        for baskets in transactions:
            if not baskets:
                f.write("\n")
                continue
            basket_strs = [" ".join(str(item) for item in basket) for basket in baskets]
            f.write(" | ".join(basket_strs) + "\n")


# ---------------------------------------------------------------------------
# Ground Truth (SPR) の計算
# ---------------------------------------------------------------------------

def compute_ground_truth(
    transactions: List[List[List[int]]],
    min_support: int,
    max_length: int,
) -> dict:
    """
    Ground Truth を計算する。

    定義:
        true_support(S)  = 同一バスケット内に S の全アイテムが含まれるバスケットの数
        txn_support(S)   = S の全アイテムが（バスケット横断で）1トランザクション内に
                           含まれるトランザクションの数
        spurious(S)      = true_support(S) < min_support <= txn_support(S)

    高速化:
        - Apriori プルーニング: 単体アイテムの支持度 >= min_support のアイテムのみを対象に
          組み合わせを生成する。lambda が大きく txn_support の組み合わせ爆発が起きる場合に有効。

    Returns:
        {
            "n_transactions": int,
            "n_baskets_total": int,
            "avg_baskets_per_txn": float,
            "spr": float,
            "n_txn_frequent": int,
            "n_spurious": int,
            "true_frequent_patterns": [...],  # 最大 1000件
            "spurious_patterns": [...],        # 最大 1000件
        }
    """
    n_transactions = len(transactions)
    n_baskets_total = 0

    # ステップ1: 単体アイテムの true_support / txn_support を収集
    item_basket_support: Dict[int, int] = defaultdict(int)  # basket-level
    item_txn_support: Dict[int, int] = defaultdict(int)     # txn-level

    for baskets in transactions:
        n_baskets_total += len(baskets)
        txn_seen: set = set()
        for basket in baskets:
            basket_seen: set = set()
            for item in basket:
                if item not in basket_seen:
                    basket_seen.add(item)
                    item_basket_support[item] += 1
                if item not in txn_seen:
                    txn_seen.add(item)
                    item_txn_support[item] += 1

    # Apriori プルーニング: 単体アイテムをフィルタ
    # true_support または txn_support のどちらかが min_support 以上のアイテムだけを考慮
    candidate_items = sorted(
        item for item in item_txn_support if item_txn_support[item] >= min_support
    )

    if not candidate_items or max_length < 2:
        return {
            "n_transactions": n_transactions,
            "n_baskets_total": n_baskets_total,
            "avg_baskets_per_txn": n_baskets_total / n_transactions if n_transactions else 0.0,
            "spr": 0.0,
            "n_txn_frequent": 0,
            "n_spurious": 0,
            "true_frequent_patterns": [],
            "spurious_patterns": [],
        }

    candidate_set = set(candidate_items)

    # ステップ2: 多アイテムセットの true_support / txn_support を収集
    true_support: Dict[Tuple[int, ...], int] = defaultdict(int)
    txn_support: Dict[Tuple[int, ...], int] = defaultdict(int)

    for baskets in transactions:
        # バスケット単位
        for basket in baskets:
            basket_set = sorted(item for item in set(basket) if item in candidate_set)
            if len(basket_set) < 2:
                continue
            for length in range(2, min(max_length, len(basket_set)) + 1):
                for combo in combinations(basket_set, length):
                    true_support[combo] += 1

        # トランザクション単位
        txn_items = sorted(item for item in set(
            item for basket in baskets for item in basket
        ) if item in candidate_set)
        if len(txn_items) < 2:
            continue
        for length in range(2, min(max_length, len(txn_items)) + 1):
            for combo in combinations(txn_items, length):
                txn_support[combo] += 1

    # txn_support >= min_support の全アイテムセット
    txn_frequent = {s for s, cnt in txn_support.items() if cnt >= min_support}
    n_txn_frequent = len(txn_frequent)

    # spurious: txn_frequent だが true_support < min_support
    spurious_patterns = [
        s for s in txn_frequent if true_support.get(s, 0) < min_support
    ]
    n_spurious = len(spurious_patterns)

    spr = n_spurious / n_txn_frequent if n_txn_frequent > 0 else 0.0

    # true_frequent: true_support >= min_support
    true_frequent_patterns = [
        s for s, cnt in true_support.items() if cnt >= min_support
    ]

    # 出力件数を 1000 件に制限
    true_frequent_list = [
        {
            "itemset": list(s),
            "true_support": true_support[s],
            "txn_support": txn_support.get(s, 0),
        }
        for s in sorted(true_frequent_patterns)[:1000]
    ]
    spurious_list = [
        {
            "itemset": list(s),
            "true_support": true_support.get(s, 0),
            "txn_support": txn_support[s],
        }
        for s in sorted(spurious_patterns)[:1000]
    ]

    return {
        "n_transactions": n_transactions,
        "n_baskets_total": n_baskets_total,
        "avg_baskets_per_txn": n_baskets_total / n_transactions if n_transactions else 0.0,
        "spr": spr,
        "n_txn_frequent": n_txn_frequent,
        "n_spurious": n_spurious,
        "true_frequent_patterns": true_frequent_list,
        "spurious_patterns": spurious_list,
    }


# ---------------------------------------------------------------------------
# CLI エントリーポイント
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="合成トランザクションデータを生成し Ground Truth (SPR) を計算する"
    )
    parser.add_argument(
        "--model", choices=["poisson", "powerlaw"], default="poisson",
        help="生成モデル",
    )
    parser.add_argument("--n-transactions", type=int, default=10000)
    parser.add_argument("--n-items", type=int, default=200)
    parser.add_argument("--g", type=int, default=10, help="カテゴリ数")
    parser.add_argument("--lambda-baskets", type=float, default=2.0)
    parser.add_argument("--lambda-basket-size", type=float, default=3.0)
    parser.add_argument("--alpha-n", type=float, default=2.5)
    parser.add_argument("--alpha-k", type=float, default=2.5)
    parser.add_argument("--p-same", type=float, default=0.8)
    parser.add_argument("--zipf-alpha", type=float, default=1.2)
    parser.add_argument("--min-support", type=int, default=50)
    parser.add_argument("--max-length", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-dir", type=str, default=".")
    parser.add_argument("--prefix", type=str, default="synthetic")
    parser.add_argument(
        "--skip-gt", action="store_true",
        help="Ground Truth 計算をスキップ（大規模データの計時専用）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    txn_file = output_dir / f"{args.prefix}_seed{args.seed}.txt"
    gt_file = output_dir / f"{args.prefix}_seed{args.seed}_gt.json"

    print(f"[gen] model={args.model}, n_transactions={args.n_transactions}, "
          f"lambda_baskets={args.lambda_baskets}, G={args.g}, seed={args.seed}")

    transactions = generate_transactions(
        n_transactions=args.n_transactions,
        n_items=args.n_items,
        n_categories=args.g,
        lambda_baskets=args.lambda_baskets,
        lambda_basket_size=args.lambda_basket_size,
        alpha_n=args.alpha_n,
        alpha_k=args.alpha_k,
        p_same=args.p_same,
        zipf_alpha=args.zipf_alpha,
        model=args.model,
        rng=rng,
    )

    write_transactions(str(txn_file), transactions)
    print(f"[gen] Wrote {txn_file}")

    if not args.skip_gt:
        print("[gen] Computing Ground Truth (SPR)...")
        gt = compute_ground_truth(transactions, args.min_support, args.max_length)
        gt["params"] = vars(args)
        with open(gt_file, "w", encoding="utf-8") as f:
            json.dump(gt, f, ensure_ascii=False, indent=2)
        print(f"[gen] SPR={gt['spr']:.4f} (spurious={gt['n_spurious']}, "
              f"txn_frequent={gt['n_txn_frequent']})")
        print(f"[gen] Wrote {gt_file}")
    else:
        print("[gen] Skipping Ground Truth computation (--skip-gt)")


if __name__ == "__main__":
    main()
