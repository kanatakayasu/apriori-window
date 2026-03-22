# Gap Analysis: Paper N — Genomics

## Core Research Question

Can sliding-window dense itemset mining on pseudotime-ordered scRNA-seq data
reveal biologically meaningful gene co-expression intervals that existing
trajectory analysis methods miss?

## Methodological Gap

1. **WGCNA** finds gene modules but is static—no temporal localization
2. **tradeSeq / GeneSwitches** analyze individual genes, not co-expression sets
3. **SCENIC** focuses on regulatory networks, not dense temporal co-occurrence
4. **No existing method** combines:
   - Itemset mining (combinatorial co-expression)
   - Temporal windowing (pseudotime intervals)
   - Dense interval detection (support threshold over sliding window)

## Our Contribution

- **Problem formulation**: Define "Dense Gene Co-expression Interval" (DGCI)
  on pseudotime axis
- **Adapter**: Expression threshold binarization → itemset transactions
- **Algorithm**: Apply Apriori-Window to pseudotime-ordered cells
- **Validation**: Compare detected intervals with known differentiation stages
  and pathway annotations

## Novelty Assessment

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Problem formulation | High | DGCI concept is new |
| Algorithm | Medium | Reuse Apriori-Window; novelty in adapter |
| Application domain | High | First application to pseudotime scRNA-seq |
| Experimental validation | Medium | Synthetic + public datasets |

## Dependencies

- **Paper C (Multidimensional)**: May extend to multi-trajectory (branching)
  settings where each branch is a separate pseudotime axis.
