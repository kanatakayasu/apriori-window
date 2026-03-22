"""
Paper P: LLM Interpretation - 実験実行スクリプト。

sample_basket.txt を用いてモック LLM 解釈パイプラインを実行し、
結果を experiments/results/ に出力する。
"""

import json
import sys
from pathlib import Path

# 実装モジュールの import
impl_dir = Path(__file__).resolve().parents[1] / "implementation" / "python"
sys.path.insert(0, str(impl_dir))

from llm_pattern_interpreter import (
    run_interpretation_pipeline,
    evaluate_interpretations,
    PatternInterpreter,
    extract_pattern_info,
    InterpretationResult,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DATA = REPO_ROOT / "apriori_window_suite" / "data" / "sample_basket.txt"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def run_main_experiment():
    """メイン実験: sample_basket.txt でパイプライン実行。"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 実験条件
    configs = [
        {"window_size": 3, "threshold": 2, "max_length": 3, "label": "small_window"},
        {"window_size": 5, "threshold": 3, "max_length": 3, "label": "medium_window"},
        {"window_size": 10, "threshold": 3, "max_length": 4, "label": "large_window"},
    ]

    all_results = {}

    for cfg in configs:
        label = cfg.pop("label")
        print(f"\n=== 実験: {label} ===")
        print(f"  window_size={cfg['window_size']}, threshold={cfg['threshold']}, "
              f"max_length={cfg['max_length']}")

        result = run_interpretation_pipeline(
            input_path=str(SAMPLE_DATA),
            top_k=10,
            output_path=str(RESULTS_DIR / f"{label}.json"),
            **cfg,
        )

        n_patterns = len(result["interpretations"])
        metrics = result["metrics"]
        print(f"  検出パターン数: {n_patterns}")
        print(f"  平均確信度: {metrics['avg_confidence']:.3f}")
        print(f"  平均要約長: {metrics['avg_summary_length']:.0f} 文字")
        print(f"  時間的記述率: {metrics['has_temporal_info']:.0%}")
        print(f"  仮説生成率: {metrics['has_hypothesis']:.0%}")

        all_results[label] = {
            "config": cfg,
            "n_patterns": n_patterns,
            "metrics": metrics,
        }

        if result["interpretations"]:
            print(f"\n  --- サンプル解釈 ---")
            first = result["interpretations"][0]
            print(f"  パターン: {first['pattern']['itemset']}")
            print(f"  要約: {first['summary']}")

    # 全結果の比較サマリー
    summary_path = RESULTS_DIR / "experiment_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n全結果を {summary_path} に出力しました。")

    return all_results


def run_metadata_experiment():
    """メタデータ付き実験。"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # サンプルメタデータを生成
    # sample_basket.txt 内のアイテムIDを調べて適宜設定
    metadata = [
        {"item_id": 1, "name": "商品A", "category": "カテゴリ1"},
        {"item_id": 2, "name": "商品B", "category": "カテゴリ1"},
        {"item_id": 3, "name": "商品C", "category": "カテゴリ2"},
        {"item_id": 4, "name": "商品D", "category": "カテゴリ2"},
        {"item_id": 5, "name": "商品E", "category": "カテゴリ3"},
    ]

    meta_path = RESULTS_DIR / "sample_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    result = run_interpretation_pipeline(
        input_path=str(SAMPLE_DATA),
        window_size=5,
        threshold=2,
        max_length=3,
        metadata_path=str(meta_path),
        output_path=str(RESULTS_DIR / "with_metadata.json"),
    )

    print(f"\nメタデータ付き実験: {len(result['interpretations'])} パターン解釈")
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("Paper P: LLM Interpretation 実験")
    print("=" * 60)

    run_main_experiment()
    print()
    run_metadata_experiment()
