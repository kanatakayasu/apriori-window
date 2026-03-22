"""
scRNA-seq → Transaction Database adapter for dense co-expression mining.

Converts pseudotime-ordered single-cell expression data into integer-coded
transactions compatible with apriori_window_basket.py.
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


class ScRNAAdapter:
    """
    Adapter converting scRNA-seq expression matrices into integer-coded
    transaction databases ordered by pseudotime.
    """

    def __init__(
        self,
        threshold_strategy: str = "quantile",
        threshold_param: float = 0.5,
        min_cells_expressed: int = 10,
    ):
        """
        Args:
            threshold_strategy: "quantile", "median", or "zscore"
            threshold_param: quantile level (0-1), or z-score cutoff
            min_cells_expressed: minimum cells expressing a gene to include it
        """
        if threshold_strategy not in ("quantile", "median", "zscore"):
            raise ValueError(
                f"Unknown strategy: {threshold_strategy}. "
                "Use 'quantile', 'median', or 'zscore'."
            )
        self.threshold_strategy = threshold_strategy
        self.threshold_param = threshold_param
        self.min_cells_expressed = min_cells_expressed
        self._gene_to_int: Dict[str, int] = {}
        self._int_to_gene: Dict[int, str] = {}
        self._next_id: int = 1
        self._thresholds: Dict[str, float] = {}

    def encode_gene(self, gene_name: str) -> int:
        """Encode a gene name to an integer ID."""
        if gene_name not in self._gene_to_int:
            self._gene_to_int[gene_name] = self._next_id
            self._int_to_gene[self._next_id] = gene_name
            self._next_id += 1
        return self._gene_to_int[gene_name]

    def decode_int(self, item_id: int) -> str:
        """Decode an integer ID back to gene name."""
        if item_id not in self._int_to_gene:
            raise KeyError(f"Unknown item ID: {item_id}")
        return self._int_to_gene[item_id]

    def compute_threshold(self, values: List[float]) -> float:
        """Compute expression threshold for a single gene."""
        nonzero = [v for v in values if v > 0]
        if not nonzero:
            return float("inf")

        if self.threshold_strategy == "median":
            nonzero_sorted = sorted(nonzero)
            mid = len(nonzero_sorted) // 2
            if len(nonzero_sorted) % 2 == 0:
                return (nonzero_sorted[mid - 1] + nonzero_sorted[mid]) / 2
            return nonzero_sorted[mid]

        elif self.threshold_strategy == "quantile":
            nonzero_sorted = sorted(nonzero)
            q = self.threshold_param
            idx = q * (len(nonzero_sorted) - 1)
            lo = int(math.floor(idx))
            hi = int(math.ceil(idx))
            if lo == hi:
                return nonzero_sorted[lo]
            frac = idx - lo
            return nonzero_sorted[lo] * (1 - frac) + nonzero_sorted[hi] * frac

        else:  # zscore
            mean_val = sum(nonzero) / len(nonzero)
            if len(nonzero) < 2:
                return mean_val
            var = sum((v - mean_val) ** 2 for v in nonzero) / (len(nonzero) - 1)
            std_val = math.sqrt(var)
            return mean_val + self.threshold_param * std_val

    def transform(
        self,
        expression_matrix: List[List[float]],
        gene_names: List[str],
        pseudotime: List[float],
    ) -> Tuple[List[List[List[int]]], List[str], Dict[str, float]]:
        """
        Transform scRNA-seq data into pseudotime-ordered transactions.

        Args:
            expression_matrix: genes x cells matrix (each row = one gene)
            gene_names: gene name for each row
            pseudotime: pseudotime value for each cell (column)

        Returns:
            transactions: list of single-basket transactions (sorted by pseudotime)
            filtered_genes: list of gene names retained after filtering
            thresholds: computed threshold for each gene
        """
        n_genes = len(expression_matrix)
        n_cells = len(pseudotime)

        if n_genes != len(gene_names):
            raise ValueError(
                f"expression_matrix has {n_genes} rows but "
                f"gene_names has {len(gene_names)} entries"
            )
        if n_cells == 0:
            return [], [], {}

        for row in expression_matrix:
            if len(row) != n_cells:
                raise ValueError("All rows must have the same number of cells")

        # Sort cells by pseudotime
        cell_order = sorted(range(n_cells), key=lambda i: pseudotime[i])

        # Filter genes and compute thresholds
        filtered_gene_indices: List[int] = []
        for gi in range(n_genes):
            n_expressed = sum(1 for v in expression_matrix[gi] if v > 0)
            if n_expressed >= self.min_cells_expressed:
                filtered_gene_indices.append(gi)

        # Reset encoding
        self._gene_to_int.clear()
        self._int_to_gene.clear()
        self._next_id = 1
        self._thresholds.clear()

        for gi in filtered_gene_indices:
            gene = gene_names[gi]
            self.encode_gene(gene)
            threshold = self.compute_threshold(expression_matrix[gi])
            self._thresholds[gene] = threshold

        # Build transactions (pseudotime-ordered, single basket per cell)
        transactions: List[List[List[int]]] = []
        for ci in cell_order:
            basket: List[int] = []
            for gi in filtered_gene_indices:
                gene = gene_names[gi]
                if expression_matrix[gi][ci] >= self._thresholds[gene]:
                    basket.append(self._gene_to_int[gene])
            basket.sort()
            transactions.append([basket])

        return transactions, [gene_names[gi] for gi in filtered_gene_indices], self._thresholds

    def write_transactions(
        self, transactions: List[List[List[int]]], output_path: str
    ) -> None:
        """Write transactions to file in apriori_window format."""
        with open(output_path, "w", encoding="utf-8") as f:
            for cell_baskets in transactions:
                if not cell_baskets or not cell_baskets[0]:
                    f.write("\n")
                else:
                    f.write(" ".join(str(x) for x in cell_baskets[0]) + "\n")

    def decode_results(
        self,
        results: Dict[Tuple[int, ...], List[Tuple[int, int]]],
    ) -> Dict[Tuple[str, ...], List[Tuple[int, int]]]:
        """Convert integer itemset results back to gene names."""
        decoded: Dict[Tuple[str, ...], List[Tuple[int, int]]] = {}
        for itemset, intervals in results.items():
            gene_names = tuple(self.decode_int(i) for i in itemset)
            decoded[gene_names] = intervals
        return decoded

    def get_mapping(self) -> Dict[str, int]:
        """Return gene-to-int mapping."""
        return dict(self._gene_to_int)

    def get_thresholds(self) -> Dict[str, float]:
        """Return computed thresholds."""
        return dict(self._thresholds)
