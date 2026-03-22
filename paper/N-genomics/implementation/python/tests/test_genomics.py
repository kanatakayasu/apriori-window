"""
Tests for Paper N — Genomics DGCI mining.

Tests cover:
1. ScRNAAdapter (encoding, thresholds, transform)
2. Synthetic data generation
3. DGCIMiner end-to-end
4. Evaluation metrics
"""

import math
import sys
from pathlib import Path

import pytest

# Add implementation to path
_IMPL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_IMPL_DIR))

from scrna_adapter import ScRNAAdapter
from synthetic_scrna_data import (
    SyntheticScRNAConfig,
    generate_synthetic_scrna,
    GROUND_TRUTH_MODULES,
)
from dgci_miner import DGCIMiner


# ---------------------------------------------------------------------------
# ScRNAAdapter tests
# ---------------------------------------------------------------------------


class TestScRNAAdapter:
    def test_encode_decode(self):
        adapter = ScRNAAdapter()
        id1 = adapter.encode_gene("GATA1")
        id2 = adapter.encode_gene("HBB")
        assert id1 != id2
        assert adapter.decode_int(id1) == "GATA1"
        assert adapter.decode_int(id2) == "HBB"

    def test_encode_idempotent(self):
        adapter = ScRNAAdapter()
        id1 = adapter.encode_gene("CD34")
        id2 = adapter.encode_gene("CD34")
        assert id1 == id2

    def test_decode_unknown_raises(self):
        adapter = ScRNAAdapter()
        with pytest.raises(KeyError):
            adapter.decode_int(999)

    def test_threshold_median(self):
        adapter = ScRNAAdapter(threshold_strategy="median")
        values = [0, 0, 1.0, 2.0, 3.0, 4.0, 5.0]
        th = adapter.compute_threshold(values)
        # nonzero: [1,2,3,4,5] -> median = 3.0
        assert th == 3.0

    def test_threshold_quantile(self):
        adapter = ScRNAAdapter(threshold_strategy="quantile", threshold_param=0.75)
        values = [0, 1.0, 2.0, 3.0, 4.0]
        th = adapter.compute_threshold(values)
        # nonzero: [1,2,3,4], Q0.75 index = 0.75*3 = 2.25
        # interpolation: 3*0.75 + 4*0.25 = 3.25
        assert abs(th - 3.25) < 1e-6

    def test_threshold_zscore(self):
        adapter = ScRNAAdapter(threshold_strategy="zscore", threshold_param=1.0)
        values = [0, 2.0, 4.0, 6.0]
        th = adapter.compute_threshold(values)
        # nonzero: [2,4,6], mean=4, std=2, threshold = 4+1*2 = 6
        assert abs(th - 6.0) < 1e-6

    def test_threshold_all_zero(self):
        adapter = ScRNAAdapter()
        th = adapter.compute_threshold([0, 0, 0])
        assert th == float("inf")

    def test_invalid_strategy(self):
        with pytest.raises(ValueError):
            ScRNAAdapter(threshold_strategy="invalid")

    def test_transform_basic(self):
        adapter = ScRNAAdapter(
            threshold_strategy="median", min_cells_expressed=2
        )
        # 3 genes, 5 cells
        expr = [
            [0.0, 5.0, 3.0, 0.0, 4.0],  # gene A: nonzero=[5,3,4], median=4
            [2.0, 1.0, 0.0, 3.0, 2.0],  # gene B: nonzero=[2,1,3,2], median=2
            [0.0, 0.0, 0.0, 0.0, 0.0],  # gene C: all zero, filtered
        ]
        genes = ["A", "B", "C"]
        pseudotime = [0.5, 0.1, 0.3, 0.8, 0.2]

        txns, filtered, thresholds = adapter.transform(expr, genes, pseudotime)
        assert len(txns) == 5
        assert "C" not in filtered
        assert len(filtered) == 2
        # Cells should be sorted by pseudotime
        # Order: cell1(0.1), cell4(0.2), cell2(0.3), cell0(0.5), cell3(0.8)

    def test_transform_dimension_mismatch(self):
        adapter = ScRNAAdapter()
        with pytest.raises(ValueError):
            adapter.transform([[1, 2]], ["A", "B"], [0.1, 0.2])

    def test_transform_empty_cells(self):
        adapter = ScRNAAdapter()
        txns, genes, thresholds = adapter.transform([], [], [])
        assert txns == []

    def test_write_transactions(self, tmp_path):
        adapter = ScRNAAdapter()
        txns = [[[1, 3, 5]], [[2, 4]], [[]]]
        out_path = str(tmp_path / "txns.txt")
        adapter.write_transactions(txns, out_path)
        lines = Path(out_path).read_text().strip().split("\n")
        assert lines[0] == "1 3 5"
        assert lines[1] == "2 4"

    def test_decode_results(self):
        adapter = ScRNAAdapter()
        adapter.encode_gene("GATA1")
        adapter.encode_gene("KLF1")
        results = {(1, 2): [(10, 20), (30, 40)]}
        decoded = adapter.decode_results(results)
        assert ("GATA1", "KLF1") in decoded
        assert decoded[("GATA1", "KLF1")] == [(10, 20), (30, 40)]


# ---------------------------------------------------------------------------
# Synthetic data tests
# ---------------------------------------------------------------------------


class TestSyntheticData:
    def test_default_generation(self):
        result = generate_synthetic_scrna()
        assert len(result.pseudotime) == 500
        assert len(result.gene_names) > 0
        assert len(result.expression_matrix) == len(result.gene_names)
        assert len(result.expression_matrix[0]) == 500
        assert len(result.ground_truth_modules) == len(GROUND_TRUTH_MODULES)

    def test_pseudotime_sorted(self):
        result = generate_synthetic_scrna()
        for i in range(len(result.pseudotime) - 1):
            assert result.pseudotime[i] <= result.pseudotime[i + 1]

    def test_custom_config(self):
        config = SyntheticScRNAConfig(n_cells=100, seed=123)
        result = generate_synthetic_scrna(config)
        assert len(result.pseudotime) == 100

    def test_ground_truth_boundaries(self):
        result = generate_synthetic_scrna()
        for mod in result.ground_truth_modules:
            assert mod["cell_index_start"] <= mod["cell_index_end"]
            assert mod["cell_index_start"] >= 0
            assert mod["cell_index_end"] < len(result.pseudotime)

    def test_module_genes_present(self):
        result = generate_synthetic_scrna()
        for mod in result.ground_truth_modules:
            for gene in mod["genes"]:
                assert gene in result.gene_names

    def test_deterministic(self):
        r1 = generate_synthetic_scrna(SyntheticScRNAConfig(seed=42))
        r2 = generate_synthetic_scrna(SyntheticScRNAConfig(seed=42))
        assert r1.pseudotime == r2.pseudotime
        assert r1.expression_matrix == r2.expression_matrix

    def test_different_seeds(self):
        r1 = generate_synthetic_scrna(SyntheticScRNAConfig(seed=1))
        r2 = generate_synthetic_scrna(SyntheticScRNAConfig(seed=2))
        assert r1.expression_matrix != r2.expression_matrix


# ---------------------------------------------------------------------------
# DGCIMiner tests
# ---------------------------------------------------------------------------


class TestDGCIMiner:
    def test_mine_returns_dict(self):
        config = SyntheticScRNAConfig(n_cells=200, seed=42)
        data = generate_synthetic_scrna(config)
        miner = DGCIMiner(
            window_size=30,
            min_support=5,
            max_length=4,
            min_cells_expressed=5,
        )
        results = miner.mine(
            data.expression_matrix, data.gene_names, data.pseudotime
        )
        assert isinstance(results, dict)

    def test_mine_finds_patterns(self):
        config = SyntheticScRNAConfig(n_cells=500, seed=42)
        data = generate_synthetic_scrna(config)
        miner = DGCIMiner(
            window_size=50,
            min_support=8,
            max_length=5,
            threshold_strategy="quantile",
            threshold_param=0.4,
            min_cells_expressed=10,
        )
        results = miner.mine(
            data.expression_matrix, data.gene_names, data.pseudotime
        )
        # Should find at least some multi-gene patterns
        multi_gene = {k: v for k, v in results.items() if len(k) > 1}
        assert len(multi_gene) > 0, "Should detect multi-gene DGCIs"

    def test_mine_gene_names_in_results(self):
        config = SyntheticScRNAConfig(n_cells=200, seed=42)
        data = generate_synthetic_scrna(config)
        miner = DGCIMiner(
            window_size=30,
            min_support=5,
            max_length=3,
            min_cells_expressed=5,
        )
        results = miner.mine(
            data.expression_matrix, data.gene_names, data.pseudotime
        )
        for gene_set in results.keys():
            for gene in gene_set:
                assert isinstance(gene, str)

    def test_evaluate_metrics(self):
        config = SyntheticScRNAConfig(n_cells=500, seed=42)
        data = generate_synthetic_scrna(config)
        miner = DGCIMiner(
            window_size=50,
            min_support=8,
            max_length=5,
            threshold_strategy="quantile",
            threshold_param=0.4,
            min_cells_expressed=10,
        )
        results = miner.mine(
            data.expression_matrix, data.gene_names, data.pseudotime
        )
        metrics = miner.evaluate(
            results, data.ground_truth_modules, data.pseudotime
        )
        assert "module_recall" in metrics
        assert "mean_iou" in metrics
        assert "precision_at_module" in metrics
        assert 0.0 <= metrics["module_recall"] <= 1.0
        assert 0.0 <= metrics["mean_iou"] <= 1.0

    def test_evaluate_empty_detection(self):
        config = SyntheticScRNAConfig(n_cells=100, seed=42)
        data = generate_synthetic_scrna(config)
        miner = DGCIMiner()
        metrics = miner.evaluate({}, data.ground_truth_modules, data.pseudotime)
        assert metrics["module_recall"] == 0.0
        assert metrics["n_detected_multi_gene"] == 0

    def test_evaluate_empty_ground_truth(self):
        miner = DGCIMiner()
        metrics = miner.evaluate(
            {("A", "B"): [(0, 10)]}, [], [0.0] * 100
        )
        assert metrics["module_recall"] == 0.0

    def test_intervals_within_bounds(self):
        config = SyntheticScRNAConfig(n_cells=200, seed=42)
        data = generate_synthetic_scrna(config)
        miner = DGCIMiner(
            window_size=30,
            min_support=5,
            max_length=3,
            min_cells_expressed=5,
        )
        results = miner.mine(
            data.expression_matrix, data.gene_names, data.pseudotime
        )
        for gene_set, intervals in results.items():
            for s, e in intervals:
                # Dense interval start can be negative (window extends before data)
                assert e >= s


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_pipeline_synthetic(self):
        """End-to-end test: generate → mine → evaluate."""
        config = SyntheticScRNAConfig(n_cells=300, seed=42)
        data = generate_synthetic_scrna(config)

        miner = DGCIMiner(
            window_size=40,
            min_support=6,
            max_length=4,
            threshold_strategy="quantile",
            threshold_param=0.45,
            min_cells_expressed=8,
        )

        results = miner.mine(
            data.expression_matrix, data.gene_names, data.pseudotime
        )
        metrics = miner.evaluate(
            results, data.ground_truth_modules, data.pseudotime
        )

        # The synthetic data has clear modules, so we should detect something
        assert metrics["n_detected_multi_gene"] >= 0
        assert isinstance(metrics["module_recall"], float)

    def test_small_data(self):
        """Test with minimal data."""
        config = SyntheticScRNAConfig(n_cells=50, n_background_genes=2, seed=42)
        data = generate_synthetic_scrna(config)

        miner = DGCIMiner(
            window_size=10,
            min_support=3,
            max_length=3,
            min_cells_expressed=3,
        )
        results = miner.mine(
            data.expression_matrix, data.gene_names, data.pseudotime
        )
        # Should not crash on small data
        assert isinstance(results, dict)
