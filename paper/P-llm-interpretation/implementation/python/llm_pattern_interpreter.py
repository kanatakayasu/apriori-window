"""
LLM-based Dense Itemset Pattern Interpreter.

密集アイテムセットパターンの検出結果を LLM に入力し、
自然言語による解釈を自動生成するモジュール。

実際の LLM API 呼び出しは行わず、プロンプトテンプレートと
モック応答で動作する。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Phase 1 モジュールの import
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apriori_window_suite" / "python"))
from apriori_window_basket import (  # noqa: E402
    find_dense_itemsets,
    read_transactions_with_baskets,
)


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------

@dataclass
class PatternInfo:
    """密集パターンの構造化情報。"""
    itemset: Tuple[int, ...]
    intervals: List[Tuple[int, int]]
    support_ratio: float  # 密集区間のカバー率
    interval_count: int
    total_span: int  # 全区間の合計幅
    max_gap: int  # 最大ギャップ幅

    def to_dict(self) -> Dict[str, Any]:
        return {
            "itemset": list(self.itemset),
            "intervals": [list(iv) for iv in self.intervals],
            "support_ratio": self.support_ratio,
            "interval_count": self.interval_count,
            "total_span": self.total_span,
            "max_gap": self.max_gap,
        }


@dataclass
class InterpretationResult:
    """LLM による解釈結果。"""
    pattern: PatternInfo
    summary: str  # 1文要約
    temporal_description: str  # 時間的特徴の説明
    business_hypothesis: str  # ビジネス仮説
    confidence: float  # 解釈の確信度 (0-1)
    prompt_used: str  # 使用したプロンプト
    raw_response: str  # LLM の生応答

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["pattern"] = self.pattern.to_dict()
        return d


@dataclass
class ItemMetadata:
    """アイテムのメタデータ（商品名等）。"""
    item_id: int
    name: str
    category: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ItemMetadata":
        return ItemMetadata(
            item_id=int(d["item_id"]),
            name=str(d["name"]),
            category=str(d.get("category", "")),
        )


# ---------------------------------------------------------------------------
# プロンプトテンプレート
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """あなたはデータマイニングの専門家です。
トランザクションデータから検出された密集アイテムセットパターンについて、
分かりやすい自然言語での解釈を提供してください。

密集アイテムセットとは、特定の時間ウィンドウ内で共起頻度が閾値を超える
アイテムの組み合わせが、連続する時間区間にわたって観測されるパターンです。

以下の形式で回答してください:
1. 要約: パターンの1文要約
2. 時間的特徴: 密集区間の時間的な特徴
3. ビジネス仮説: なぜこのパターンが生じたかの仮説
4. 確信度: 解釈の確信度 (0.0-1.0)
"""

PATTERN_PROMPT_TEMPLATE = """以下の密集アイテムセットパターンを解釈してください。

【パターン情報】
- アイテムセット: {itemset_desc}
- 密集区間数: {interval_count}
- 密集区間: {intervals_desc}
- カバー率: {support_ratio:.1%}
- 合計密集期間: {total_span} トランザクション
- 最大ギャップ: {max_gap} トランザクション

【コンテキスト】
- データ期間: トランザクション 0 ~ {max_transaction}
- ウィンドウサイズ: {window_size}
- 密集閾値: {threshold}
{metadata_section}
"""

COMPARATIVE_PROMPT_TEMPLATE = """以下の複数パターンを比較分析してください。

{patterns_section}

【分析観点】
1. パターン間の時間的重なり
2. 共通アイテムの有無
3. ビジネス的な関連性の仮説
"""

BATCH_PROMPT_TEMPLATE = """以下の {n_patterns} 件のパターンを一括で要約してください。

{patterns_section}

各パターンについて1文ずつ要約し、全体の傾向も述べてください。
"""


# ---------------------------------------------------------------------------
# パターン情報抽出
# ---------------------------------------------------------------------------

def extract_pattern_info(
    itemset: Tuple[int, ...],
    intervals: List[Tuple[int, int]],
    total_transactions: int,
) -> PatternInfo:
    """密集パターンから構造化情報を抽出する。"""
    if not intervals:
        return PatternInfo(
            itemset=itemset,
            intervals=[],
            support_ratio=0.0,
            interval_count=0,
            total_span=0,
            max_gap=0,
        )

    total_span = sum(e - s + 1 for s, e in intervals)
    support_ratio = total_span / max(total_transactions, 1)

    max_gap = 0
    sorted_ivs = sorted(intervals)
    for i in range(1, len(sorted_ivs)):
        gap = sorted_ivs[i][0] - sorted_ivs[i - 1][1]
        max_gap = max(max_gap, gap)

    return PatternInfo(
        itemset=itemset,
        intervals=intervals,
        support_ratio=support_ratio,
        interval_count=len(intervals),
        total_span=total_span,
        max_gap=max_gap,
    )


# ---------------------------------------------------------------------------
# プロンプト生成
# ---------------------------------------------------------------------------

def build_pattern_prompt(
    pattern: PatternInfo,
    window_size: int,
    threshold: int,
    max_transaction: int,
    metadata: Optional[Dict[int, ItemMetadata]] = None,
) -> str:
    """単一パターン用のプロンプトを構築する。"""
    if metadata:
        items_desc = ", ".join(
            f"{metadata[i].name} (ID={i})" if i in metadata else f"Item {i}"
            for i in pattern.itemset
        )
        metadata_section = "\n【アイテム情報】\n" + "\n".join(
            f"- {metadata[i].name}: カテゴリ={metadata[i].category}"
            for i in pattern.itemset
            if i in metadata
        )
    else:
        items_desc = ", ".join(f"Item {i}" for i in pattern.itemset)
        metadata_section = ""

    intervals_desc = ", ".join(
        f"[{s}, {e}]" for s, e in pattern.intervals
    )

    return PATTERN_PROMPT_TEMPLATE.format(
        itemset_desc=items_desc,
        interval_count=pattern.interval_count,
        intervals_desc=intervals_desc,
        support_ratio=pattern.support_ratio,
        total_span=pattern.total_span,
        max_gap=pattern.max_gap,
        max_transaction=max_transaction,
        window_size=window_size,
        threshold=threshold,
        metadata_section=metadata_section,
    )


def build_comparative_prompt(
    patterns: List[PatternInfo],
    window_size: int,
    threshold: int,
    max_transaction: int,
    metadata: Optional[Dict[int, ItemMetadata]] = None,
) -> str:
    """複数パターン比較用のプロンプトを構築する。"""
    sections = []
    for i, p in enumerate(patterns, 1):
        sub_prompt = build_pattern_prompt(
            p, window_size, threshold, max_transaction, metadata
        )
        sections.append(f"--- パターン {i} ---\n{sub_prompt}")

    return COMPARATIVE_PROMPT_TEMPLATE.format(
        patterns_section="\n".join(sections)
    )


def build_batch_prompt(
    patterns: List[PatternInfo],
    metadata: Optional[Dict[int, ItemMetadata]] = None,
) -> str:
    """バッチ要約用のプロンプトを構築する。"""
    sections = []
    for i, p in enumerate(patterns, 1):
        if metadata:
            items_desc = ", ".join(
                metadata[it].name if it in metadata else f"Item {it}"
                for it in p.itemset
            )
        else:
            items_desc = ", ".join(f"Item {it}" for it in p.itemset)

        intervals_desc = ", ".join(f"[{s},{e}]" for s, e in p.intervals)
        sections.append(
            f"パターン{i}: {{{items_desc}}} | "
            f"区間: {intervals_desc} | "
            f"カバー率: {p.support_ratio:.1%}"
        )

    return BATCH_PROMPT_TEMPLATE.format(
        n_patterns=len(patterns),
        patterns_section="\n".join(sections),
    )


# ---------------------------------------------------------------------------
# モック LLM 応答生成
# ---------------------------------------------------------------------------

def _generate_mock_response(
    pattern: PatternInfo,
    metadata: Optional[Dict[int, ItemMetadata]] = None,
) -> Dict[str, Any]:
    """モック LLM 応答を生成する（API 非依存のデモ用）。"""
    if metadata:
        items_str = "と".join(
            metadata[i].name if i in metadata else f"アイテム{i}"
            for i in pattern.itemset
        )
    else:
        items_str = "と".join(f"アイテム{i}" for i in pattern.itemset)

    # 時間的特徴の判定
    if pattern.interval_count == 1:
        temporal_type = "単一連続"
        temporal_desc = (
            f"{items_str}の共起は、トランザクション{pattern.intervals[0][0]}から"
            f"{pattern.intervals[0][1]}までの連続した期間に集中しています。"
            f"この一貫した密集パターンは、安定した需要や継続的な"
            f"プロモーション効果を示唆しています。"
        )
    elif pattern.interval_count <= 3:
        temporal_type = "断続的"
        temporal_desc = (
            f"{items_str}の共起は{pattern.interval_count}つの離散的な期間に"
            f"観測されました。最大{pattern.max_gap}トランザクションの"
            f"ギャップがあり、季節性や周期的なキャンペーンの影響が"
            f"考えられます。"
        )
    else:
        temporal_type = "高頻度断続"
        temporal_desc = (
            f"{items_str}の共起は{pattern.interval_count}つの期間に分散して"
            f"観測されており、散発的だが繰り返し発生するパターンです。"
            f"外部イベントへの反復的な反応や、顧客セグメントの"
            f"入れ替わりが原因として考えられます。"
        )

    # カバー率に基づく確信度
    if pattern.support_ratio > 0.3:
        confidence = 0.85
        hypothesis = (
            f"{items_str}はデータ期間の{pattern.support_ratio:.0%}をカバーする"
            f"強いパターンです。定番商品の組み合わせ、または長期的な"
            f"バンドル販売戦略の結果と推測されます。"
        )
    elif pattern.support_ratio > 0.1:
        confidence = 0.70
        hypothesis = (
            f"{items_str}は中程度のカバー率（{pattern.support_ratio:.0%}）を持ち、"
            f"特定の条件下で活性化するパターンです。季節商品の組み合わせや"
            f"期間限定のクロスセル施策が背景にある可能性があります。"
        )
    else:
        confidence = 0.55
        hypothesis = (
            f"{items_str}のカバー率は{pattern.support_ratio:.0%}と低く、"
            f"限定的な条件でのみ出現するニッチなパターンです。"
            f"特定顧客セグメントの行動や一時的なトレンドの反映と"
            f"考えられます。"
        )

    summary = (
        f"{items_str}は{temporal_type}パターンを示し、"
        f"データ期間の{pattern.support_ratio:.0%}で密集的に共起しています。"
    )

    return {
        "summary": summary,
        "temporal_description": temporal_desc,
        "business_hypothesis": hypothesis,
        "confidence": confidence,
    }


def _generate_mock_comparative_response(
    patterns: List[PatternInfo],
    metadata: Optional[Dict[int, ItemMetadata]] = None,
) -> str:
    """比較分析のモック応答を生成する。"""
    lines = []
    # 時間的重なりの分析
    all_items = set()
    for p in patterns:
        all_items.update(p.itemset)

    common_items = set(patterns[0].itemset)
    for p in patterns[1:]:
        common_items &= set(p.itemset)

    lines.append("【比較分析結果】")
    lines.append(f"分析対象: {len(patterns)}パターン")
    lines.append(f"全ユニークアイテム数: {len(all_items)}")

    if common_items:
        if metadata:
            common_names = ", ".join(
                metadata[i].name if i in metadata else f"Item {i}"
                for i in common_items
            )
        else:
            common_names = ", ".join(f"Item {i}" for i in common_items)
        lines.append(f"共通アイテム: {common_names}")
        lines.append("共通アイテムが存在するため、関連する購買行動の可能性が高い。")
    else:
        lines.append("共通アイテムなし。独立した購買パターンの可能性が高い。")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# メイン API
# ---------------------------------------------------------------------------

class PatternInterpreter:
    """密集パターン解釈器。"""

    def __init__(
        self,
        window_size: int,
        threshold: int,
        max_transaction: int,
        metadata: Optional[Dict[int, ItemMetadata]] = None,
        llm_backend: str = "mock",
    ):
        self.window_size = window_size
        self.threshold = threshold
        self.max_transaction = max_transaction
        self.metadata = metadata
        self.llm_backend = llm_backend

    def interpret_pattern(
        self, pattern: PatternInfo
    ) -> InterpretationResult:
        """単一パターンを解釈する。"""
        prompt = build_pattern_prompt(
            pattern,
            self.window_size,
            self.threshold,
            self.max_transaction,
            self.metadata,
        )

        if self.llm_backend == "mock":
            mock = _generate_mock_response(pattern, self.metadata)
            return InterpretationResult(
                pattern=pattern,
                summary=mock["summary"],
                temporal_description=mock["temporal_description"],
                business_hypothesis=mock["business_hypothesis"],
                confidence=mock["confidence"],
                prompt_used=SYSTEM_PROMPT + "\n" + prompt,
                raw_response=json.dumps(mock, ensure_ascii=False),
            )
        else:
            raise NotImplementedError(
                f"LLM backend '{self.llm_backend}' is not implemented. "
                "Use 'mock' for demonstration."
            )

    def interpret_all(
        self,
        frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]],
        top_k: int = 10,
    ) -> List[InterpretationResult]:
        """全パターンを解釈する（上位 top_k 件）。"""
        patterns = []
        for itemset, intervals in frequents.items():
            if len(itemset) < 2:
                continue
            info = extract_pattern_info(
                itemset, intervals, self.max_transaction
            )
            patterns.append(info)

        # カバー率でソート
        patterns.sort(key=lambda p: p.support_ratio, reverse=True)
        patterns = patterns[:top_k]

        return [self.interpret_pattern(p) for p in patterns]

    def compare_patterns(
        self,
        patterns: List[PatternInfo],
    ) -> str:
        """複数パターンを比較分析する。"""
        if self.llm_backend == "mock":
            return _generate_mock_comparative_response(
                patterns, self.metadata
            )
        else:
            raise NotImplementedError(
                f"LLM backend '{self.llm_backend}' is not implemented."
            )

    def batch_summarize(
        self,
        frequents: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    ) -> str:
        """全パターンのバッチ要約を生成する。"""
        patterns = []
        for itemset, intervals in frequents.items():
            if len(itemset) < 2:
                continue
            info = extract_pattern_info(
                itemset, intervals, self.max_transaction
            )
            patterns.append(info)

        patterns.sort(key=lambda p: p.support_ratio, reverse=True)

        if self.llm_backend == "mock":
            lines = [f"全{len(patterns)}パターンの要約:"]
            for i, p in enumerate(patterns, 1):
                mock = _generate_mock_response(p, self.metadata)
                lines.append(f"{i}. {mock['summary']}")

            if patterns:
                avg_cover = sum(p.support_ratio for p in patterns) / len(patterns)
                lines.append(
                    f"\n全体傾向: 平均カバー率{avg_cover:.1%}、"
                    f"パターン数{len(patterns)}件。"
                )
            return "\n".join(lines)
        else:
            raise NotImplementedError(
                f"LLM backend '{self.llm_backend}' is not implemented."
            )


# ---------------------------------------------------------------------------
# 評価指標
# ---------------------------------------------------------------------------

@dataclass
class InterpretationMetrics:
    """解釈品質の評価指標。"""
    pattern_count: int
    avg_confidence: float
    coverage_correlation: float  # カバー率と確信度の相関
    avg_summary_length: float
    has_temporal_info: float  # 時間的記述を含む割合
    has_hypothesis: float  # 仮説を含む割合


def evaluate_interpretations(
    results: List[InterpretationResult],
) -> InterpretationMetrics:
    """解釈結果の品質を評価する。"""
    if not results:
        return InterpretationMetrics(0, 0, 0, 0, 0, 0)

    n = len(results)
    avg_conf = sum(r.confidence for r in results) / n
    avg_len = sum(len(r.summary) for r in results) / n

    # カバー率と確信度の相関（簡易版: ピアソン相関）
    covers = [r.pattern.support_ratio for r in results]
    confs = [r.confidence for r in results]
    if n > 1:
        mean_c = sum(covers) / n
        mean_f = sum(confs) / n
        cov = sum((c - mean_c) * (f - mean_f) for c, f in zip(covers, confs))
        var_c = sum((c - mean_c) ** 2 for c in covers)
        var_f = sum((f - mean_f) ** 2 for f in confs)
        denom = (var_c * var_f) ** 0.5
        corr = cov / denom if denom > 0 else 0
    else:
        corr = 0

    has_temporal = sum(1 for r in results if len(r.temporal_description) > 0) / n
    has_hyp = sum(1 for r in results if len(r.business_hypothesis) > 0) / n

    return InterpretationMetrics(
        pattern_count=n,
        avg_confidence=avg_conf,
        coverage_correlation=corr,
        avg_summary_length=avg_len,
        has_temporal_info=has_temporal,
        has_hypothesis=has_hyp,
    )


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------

def run_interpretation_pipeline(
    input_path: str,
    window_size: int = 5,
    threshold: int = 3,
    max_length: int = 3,
    top_k: int = 10,
    metadata_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """解釈パイプラインを実行する。"""
    transactions = read_transactions_with_baskets(input_path)
    max_t = len(transactions) - 1

    # メタデータの読み込み
    metadata = None
    if metadata_path:
        with open(metadata_path, "r", encoding="utf-8") as f:
            meta_list = json.load(f)
        metadata = {
            m["item_id"]: ItemMetadata.from_dict(m)
            for m in meta_list
        }

    # Phase 1: 密集パターン検出
    frequents = find_dense_itemsets(
        transactions, window_size, threshold, max_length
    )

    # Phase 2: LLM 解釈
    interpreter = PatternInterpreter(
        window_size=window_size,
        threshold=threshold,
        max_transaction=max_t,
        metadata=metadata,
    )

    results = interpreter.interpret_all(frequents, top_k=top_k)
    metrics = evaluate_interpretations(results)
    batch_summary = interpreter.batch_summarize(frequents)

    output = {
        "parameters": {
            "window_size": window_size,
            "threshold": threshold,
            "max_length": max_length,
            "top_k": top_k,
            "total_transactions": len(transactions),
        },
        "interpretations": [r.to_dict() for r in results],
        "metrics": asdict(metrics),
        "batch_summary": batch_summary,
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    return output


def main() -> None:
    """CLI エントリポイント。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="LLM-based Dense Itemset Pattern Interpreter"
    )
    parser.add_argument("input", help="Transaction file path")
    parser.add_argument("--window-size", "-w", type=int, default=5)
    parser.add_argument("--threshold", "-t", type=int, default=3)
    parser.add_argument("--max-length", "-m", type=int, default=3)
    parser.add_argument("--top-k", "-k", type=int, default=10)
    parser.add_argument("--metadata", help="Item metadata JSON path")
    parser.add_argument("--output", "-o", help="Output JSON path")

    args = parser.parse_args()

    result = run_interpretation_pipeline(
        input_path=args.input,
        window_size=args.window_size,
        threshold=args.threshold,
        max_length=args.max_length,
        top_k=args.top_k,
        metadata_path=args.metadata,
        output_path=args.output,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
