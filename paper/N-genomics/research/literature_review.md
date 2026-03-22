# Literature Review: Dense Gene Co-expression Intervals on Pseudotime in scRNA-seq

## 1. Background

Single-cell RNA sequencing (scRNA-seq) enables transcriptomic profiling at
single-cell resolution. Pseudotime analysis orders cells along a continuous
trajectory representing biological processes such as differentiation,
cell-cycle progression, or response to perturbation.

## 2. Key Prior Work

### 2.1 Pseudotime Inference
- **Monocle / Monocle 3** (Trapnell et al., 2014; Cao et al., 2019):
  Reversed graph embedding for trajectory inference.
- **Slingshot** (Street et al., 2018): Principal curves on cluster-based
  minimum spanning tree.
- **PAGA** (Wolf et al., 2019): Partition-based graph abstraction for
  trajectory connectivity.
- **DPT** (Haghverdi et al., 2016): Diffusion pseudotime using random-walk
  distances on k-NN graph.

### 2.2 Gene Co-expression Analysis
- **WGCNA** (Langfelder & Horvath, 2008): Weighted gene co-expression network
  analysis—identifies modules of correlated genes across samples.
  Limitation: static, no temporal dimension.
- **scLink** (Li & Li, 2021): Network inference for scRNA-seq using
  regularized Gaussian model.
- **SCENIC** (Aibar et al., 2017): Regulatory network inference combining
  co-expression with motif analysis.

### 2.3 Temporal / Trajectory-aware Co-expression
- **tradeSeq** (Van den Berge et al., 2020): GAM-based differential
  expression along trajectories. Gene-level, not co-expression.
- **GeneSwitches** (Cao et al., 2020): Binary gene switching along
  pseudotime. Identifies on/off transitions but not co-expression patterns.
- **CellRank** (Lange et al., 2022): Combines RNA velocity with pseudotime
  for fate decision analysis.
- **Condiments** (de Boer & Hicks, 2024): Differential topology across
  conditions along trajectories.

### 2.4 Dense Itemset Mining in Bioinformatics
- **Frequent itemset mining on gene expression**: Creighton & Hanash (2003)
  applied association rule mining to discretized microarray data.
- **Temporal pattern mining**: Limited application to pseudotime-ordered
  scRNA-seq data.

## 3. Gap Analysis

| Aspect | Existing Methods | Gap |
|--------|-----------------|-----|
| Temporal co-expression | WGCNA (static), tradeSeq (single gene) | No method detects *intervals* of dense co-expression along pseudotime |
| Pseudotime structure | Monocle, Slingshot | Trajectory inference well-solved; downstream analysis limited to DE |
| Itemset mining + bio | Creighton 2003 (microarray, static) | Not applied to pseudotime-ordered single-cell data |
| Dense interval detection | Apriori-Window (our method) | Not yet applied to genomics domain |

## 4. Research Opportunity

**No existing method identifies contiguous pseudotime intervals where specific
gene sets are densely co-expressed.** Our Apriori-Window framework can fill
this gap by:

1. Discretizing gene expression (threshold-based binarization)
2. Treating each cell (ordered by pseudotime) as a transaction
3. Applying sliding-window dense interval mining
4. Detecting biologically meaningful co-expression "waves" along
   differentiation trajectories

## 5. Key References

1. Trapnell et al., "The dynamics and regulators of cell fate decisions are revealed by pseudotemporal ordering of single cells," Nature Biotechnology, 2014.
2. Street et al., "Slingshot: cell lineage and pseudotime inference for single-cell transcriptomics," BMC Genomics, 2018.
3. Van den Berge et al., "Trajectory-based differential expression analysis for single-cell sequencing data," Nature Communications, 2020.
4. Langfelder & Horvath, "WGCNA: an R package for weighted correlation network analysis," BMC Bioinformatics, 2008.
5. Aibar et al., "SCENIC: single-cell regulatory network inference and clustering," Nature Methods, 2017.
6. Cao et al., "GeneSwitches: ordering gene expression changes in pseudotime," Bioinformatics, 2020.
7. Lange et al., "CellRank for directed single-cell fate mapping," Nature Methods, 2022.
8. Creighton & Hanash, "Mining gene expression databases for association rules," Bioinformatics, 2003.
9. Wolf et al., "PAGA: graph abstraction reconciles clustering with trajectory inference," Genome Biology, 2019.
10. Haghverdi et al., "Diffusion pseudotime robustly reconstructs lineage branching," Nature Methods, 2016.
