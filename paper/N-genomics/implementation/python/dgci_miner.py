"""
Dense Gene Co-expression Interval (DGCI) Miner.

Integrates scRNA-seq adapter with apriori_window_basket to detect
temporally localized gene co-expression patterns along pseudotime.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add apriori_window_suite to path for importing
_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "apriori_window_suite" / "python"))

from apriori_window_basket import find_dense_itemsets  # noqa: E402

from scrna_adapter import ScRNAAdapter  # noqa: E402
from synthetic_scrna_data import (  # noqa: E402
    SyntheticScRNAConfig,
    generate_synthetic_scrna,
)


class DGCIMiner:
    """
    Dense Gene Co-expression Interval miner for scRNA-seq data.

    Pipeline:
        1. Adapt scRNA-seq data (binarize, order by pseudotime)
        2. Mine dense itemsets using Apriori-Window
        3. Map results back to gene names
        4. Evaluate against ground truth (if available)
    """

    def __init__(
        self,
        window_size: int = 50,
        min_support: int = 10,
        max_length: int = 5,
        threshold_strategy: str = "quantile",
        threshold_param: float = 0.5,
        min_cells_expressed: int = 10,
    ):
        self.window_size = window_size
        self.min_support = min_support
        self.max_length = max_length
        self.adapter = ScRNAAdapter(
            threshold_strategy=threshold_strategy,
            threshold_param=threshold_param,
            min_cells_expressed=min_cells_expressed,
        )

    def mine(
        self,
        expression_matrix: List[List[float]],
        gene_names: List[str],
        pseudotime: List[float],
    ) -> Dict[Tuple[str, ...], List[Tuple[int, int]]]:
        """
        Run the full DGCI mining pipeline.

        Returns:
            Dictionary mapping gene set tuples to lists of dense intervals.
        """
        # Step 1: Adapt data
        transactions, filtered_genes, thresholds = self.adapter.transform(
            expression_matrix, gene_names, pseudotime
        )

        # Step 2: Mine dense itemsets
        raw_results = find_dense_itemsets(
            transactions,
            self.window_size,
            self.min_support,
            self.max_length,
        )

        # Step 3: Decode results to gene names
        decoded = self.adapter.decode_results(raw_results)

        return decoded

    def evaluate(
        self,
        detected: Dict[Tuple[str, ...], List[Tuple[int, int]]],
        ground_truth_modules: List[dict],
        pseudotime: List[float],
    ) -> Dict[str, object]:
        """
        Evaluate detected DGCIs against ground truth modules.

        Returns evaluation metrics:
        - module_recall: fraction of GT modules with >= 1 matching DGCI
        - interval_iou: average IoU between matched GT and detected intervals
        - precision_at_module: fraction of multi-gene DGCIs matching a GT module
        """
        n_cells = len(pseudotime)

        # Filter to multi-gene itemsets only
        multi_gene_dgcis = {
            k: v for k, v in detected.items() if len(k) > 1
        }

        # Check each GT module
        matched_modules = 0
        iou_scores = []

        for gt_mod in ground_truth_modules:
            gt_genes = set(gt_mod["genes"])
            gt_start = gt_mod["cell_index_start"]
            gt_end = gt_mod["cell_index_end"]

            best_iou = 0.0
            found = False

            for gene_set, intervals in multi_gene_dgcis.items():
                detected_genes = set(gene_set)

                # Check gene overlap (at least 2 genes in common)
                overlap = gt_genes & detected_genes
                if len(overlap) < 2:
                    continue

                found = True
                # Compute temporal IoU for best matching interval
                for s, e in intervals:
                    # The detected interval covers cells [s, e + W]
                    det_start = s
                    det_end = min(e + self.window_size, n_cells - 1)

                    inter_start = max(gt_start, det_start)
                    inter_end = min(gt_end, det_end)
                    intersection = max(0, inter_end - inter_start + 1)

                    union_start = min(gt_start, det_start)
                    union_end = max(gt_end, det_end)
                    union = union_end - union_start + 1

                    iou = intersection / union if union > 0 else 0.0
                    best_iou = max(best_iou, iou)

            if found:
                matched_modules += 1
                iou_scores.append(best_iou)

        # Precision: fraction of multi-gene DGCIs matching any GT module
        matched_dgcis = 0
        for gene_set, intervals in multi_gene_dgcis.items():
            detected_genes = set(gene_set)
            for gt_mod in ground_truth_modules:
                gt_genes = set(gt_mod["genes"])
                if len(gt_genes & detected_genes) >= 2:
                    matched_dgcis += 1
                    break

        n_gt = len(ground_truth_modules)
        n_detected = len(multi_gene_dgcis)

        return {
            "n_ground_truth_modules": n_gt,
            "n_detected_multi_gene": n_detected,
            "module_recall": matched_modules / n_gt if n_gt > 0 else 0.0,
            "mean_iou": (
                sum(iou_scores) / len(iou_scores) if iou_scores else 0.0
            ),
            "precision_at_module": (
                matched_dgcis / n_detected if n_detected > 0 else 0.0
            ),
            "matched_modules": matched_modules,
            "matched_dgcis": matched_dgcis,
        }


def run_demo() -> Dict:
    """Run a demo on synthetic data."""
    config = SyntheticScRNAConfig(n_cells=500, seed=42)
    data = generate_synthetic_scrna(config)

    miner = DGCIMiner(
        window_size=50,
        min_support=10,
        max_length=5,
        threshold_strategy="quantile",
        threshold_param=0.5,
        min_cells_expressed=10,
    )

    detected = miner.mine(
        data.expression_matrix,
        data.gene_names,
        data.pseudotime,
    )

    evaluation = miner.evaluate(
        detected,
        data.ground_truth_modules,
        data.pseudotime,
    )

    return {
        "detected_dgcis": {
            " + ".join(k): [(s, e) for s, e in v]
            for k, v in detected.items()
            if len(k) > 1
        },
        "evaluation": evaluation,
        "config": data.config,
    }


if __name__ == "__main__":
    result = run_demo()
    print(json.dumps(result, indent=2))
