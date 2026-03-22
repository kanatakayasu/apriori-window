"""
Synthetic scRNA-seq data generator for testing DGCI mining.

Generates pseudotime-ordered single-cell expression data with:
- Known gene co-expression modules activated at specific pseudotime intervals
- Realistic noise and dropout patterns
- Configurable number of cells, genes, and modules
"""

import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Gene catalog (marker genes for hematopoietic differentiation)
# ---------------------------------------------------------------------------

GENE_CATALOG = {
    # Stem cell markers
    "CD34": "Hematopoietic stem cell marker",
    "KIT": "Stem cell factor receptor",
    "GATA2": "Stem cell transcription factor",
    "RUNX1": "Master regulator of hematopoiesis",
    # Erythroid lineage
    "GATA1": "Erythroid transcription factor",
    "KLF1": "Erythroid Kruppel-like factor",
    "HBB": "Beta-globin",
    "HBA1": "Alpha-globin",
    "EPOR": "Erythropoietin receptor",
    "GYPA": "Glycophorin A (erythroid marker)",
    # Myeloid lineage
    "CEBPA": "Myeloid transcription factor",
    "SPI1": "PU.1 myeloid TF",
    "MPO": "Myeloperoxidase",
    "ELANE": "Neutrophil elastase",
    "CSF3R": "G-CSF receptor",
    # Megakaryocyte lineage
    "FLI1": "Megakaryocyte TF",
    "ITGA2B": "CD41 (megakaryocyte marker)",
    "GP1BA": "GPIb-alpha (platelet)",
    "PF4": "Platelet factor 4",
    # Cell cycle
    "MKI67": "Proliferation marker Ki-67",
    "TOP2A": "Topoisomerase II alpha",
    "CDK1": "Cyclin-dependent kinase 1",
    # Housekeeping
    "ACTB": "Beta-actin",
    "GAPDH": "Glyceraldehyde-3-phosphate dehydrogenase",
}

# Known co-expression modules with pseudotime activation windows
GROUND_TRUTH_MODULES = [
    {
        "name": "stem_maintenance",
        "genes": ["CD34", "KIT", "GATA2", "RUNX1"],
        "pseudotime_start": 0.0,
        "pseudotime_end": 0.3,
        "description": "Stem cell gene module active early in pseudotime",
    },
    {
        "name": "erythroid_commitment",
        "genes": ["GATA1", "KLF1", "EPOR"],
        "pseudotime_start": 0.25,
        "pseudotime_end": 0.55,
        "description": "Erythroid commitment TFs activated mid-early",
    },
    {
        "name": "erythroid_maturation",
        "genes": ["HBB", "HBA1", "GYPA"],
        "pseudotime_start": 0.5,
        "pseudotime_end": 0.85,
        "description": "Erythroid maturation genes active mid-late",
    },
    {
        "name": "myeloid_program",
        "genes": ["CEBPA", "SPI1", "MPO"],
        "pseudotime_start": 0.3,
        "pseudotime_end": 0.65,
        "description": "Myeloid differentiation program",
    },
    {
        "name": "proliferation",
        "genes": ["MKI67", "TOP2A", "CDK1"],
        "pseudotime_start": 0.1,
        "pseudotime_end": 0.4,
        "description": "Cell cycle / proliferation module",
    },
]


@dataclass
class SyntheticScRNAConfig:
    """Configuration for synthetic scRNA-seq generation."""

    n_cells: int = 500
    n_background_genes: int = 10
    dropout_rate: float = 0.3
    noise_scale: float = 0.5
    base_expression: float = 1.0
    module_boost: float = 4.0
    seed: int = 42


@dataclass
class SyntheticScRNAResult:
    """Result of synthetic data generation."""

    expression_matrix: List[List[float]]
    gene_names: List[str]
    pseudotime: List[float]
    ground_truth_modules: List[dict]
    config: dict


def generate_synthetic_scrna(
    config: Optional[SyntheticScRNAConfig] = None,
) -> SyntheticScRNAResult:
    """
    Generate synthetic scRNA-seq data with known co-expression modules.

    Returns:
        SyntheticScRNAResult with expression matrix, gene names,
        pseudotime values, and ground truth module definitions.
    """
    if config is None:
        config = SyntheticScRNAConfig()

    rng = random.Random(config.seed)
    n_cells = config.n_cells

    # Collect all genes from modules + background
    module_genes = set()
    for mod in GROUND_TRUTH_MODULES:
        module_genes.update(mod["genes"])

    all_gene_names = sorted(module_genes)
    # Add background genes
    for i in range(config.n_background_genes):
        bg_name = f"BG_{i+1:03d}"
        all_gene_names.append(bg_name)

    n_genes = len(all_gene_names)

    # Generate pseudotime (uniformly spaced with small jitter)
    pseudotime = []
    for i in range(n_cells):
        pt = i / (n_cells - 1) if n_cells > 1 else 0.0
        pt += rng.gauss(0, 0.005)
        pt = max(0.0, min(1.0, pt))
        pseudotime.append(pt)
    pseudotime.sort()

    # Build expression matrix (genes x cells)
    expression_matrix: List[List[float]] = []
    gene_name_to_idx = {g: i for i, g in enumerate(all_gene_names)}

    for gi, gene in enumerate(all_gene_names):
        row: List[float] = []
        for ci in range(n_cells):
            pt = pseudotime[ci]

            # Base expression with noise
            expr = config.base_expression + rng.gauss(0, config.noise_scale)

            # Check if gene is in any active module at this pseudotime
            for mod in GROUND_TRUTH_MODULES:
                if gene in mod["genes"]:
                    ps = mod["pseudotime_start"]
                    pe = mod["pseudotime_end"]
                    if ps <= pt <= pe:
                        # Smooth activation: bell-shaped within interval
                        center = (ps + pe) / 2
                        width = (pe - ps) / 2
                        activation = math.exp(
                            -0.5 * ((pt - center) / (width * 0.6)) ** 2
                        )
                        expr += config.module_boost * activation

            # Dropout
            if rng.random() < config.dropout_rate:
                expr = 0.0
            else:
                expr = max(0.0, expr)

            row.append(round(expr, 4))
        expression_matrix.append(row)

    # Compute ground truth with cell index boundaries
    gt_modules = []
    for mod in GROUND_TRUTH_MODULES:
        start_idx = None
        end_idx = None
        for ci, pt in enumerate(pseudotime):
            if pt >= mod["pseudotime_start"] and start_idx is None:
                start_idx = ci
            if pt <= mod["pseudotime_end"]:
                end_idx = ci
        gt_modules.append(
            {
                "name": mod["name"],
                "genes": mod["genes"],
                "pseudotime_start": mod["pseudotime_start"],
                "pseudotime_end": mod["pseudotime_end"],
                "cell_index_start": start_idx if start_idx is not None else 0,
                "cell_index_end": end_idx if end_idx is not None else n_cells - 1,
                "description": mod["description"],
            }
        )

    return SyntheticScRNAResult(
        expression_matrix=expression_matrix,
        gene_names=all_gene_names,
        pseudotime=pseudotime,
        ground_truth_modules=gt_modules,
        config=asdict(config),
    )


def save_synthetic_data(
    result: SyntheticScRNAResult, output_dir: str
) -> Dict[str, str]:
    """Save synthetic data to files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Expression matrix as JSON
    expr_path = out / "expression_matrix.json"
    with open(expr_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "gene_names": result.gene_names,
                "pseudotime": result.pseudotime,
                "expression": result.expression_matrix,
            },
            f,
            indent=2,
        )

    # Ground truth
    gt_path = out / "ground_truth.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "modules": result.ground_truth_modules,
                "config": result.config,
            },
            f,
            indent=2,
        )

    return {"expression": str(expr_path), "ground_truth": str(gt_path)}


if __name__ == "__main__":
    result = generate_synthetic_scrna()
    paths = save_synthetic_data(result, "paper/N-genomics/experiments/data")
    print(f"Generated synthetic data: {paths}")
    print(f"  Cells: {len(result.pseudotime)}")
    print(f"  Genes: {len(result.gene_names)}")
    print(f"  Modules: {len(result.ground_truth_modules)}")
    for mod in result.ground_truth_modules:
        print(
            f"    {mod['name']}: {mod['genes']} "
            f"[{mod['pseudotime_start']:.2f}, {mod['pseudotime_end']:.2f}]"
        )
