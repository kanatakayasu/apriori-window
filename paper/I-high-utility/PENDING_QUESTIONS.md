# PENDING_QUESTIONS.md -- Paper I: High-Utility Dense Intervals

## Open Questions

### Q1: Real-data evaluation
- Current experiments use synthetic/semi-synthetic data only.
- For a TKDE/KAIS submission, evaluation on real retail datasets with external utility (e.g., profit margin) is expected.
- Candidates: Foodmart (SPMF), chainstore, or Dunnhumby with estimated profit margins.

### Q2: TWU pruning effectiveness on real data
- In synthetic uniform data, TWU accumulates broadly, limiting pruning.
- Real data with skewed utility distributions (few high-margin items) should show stronger pruning.
- Need empirical validation.

### Q3: One-phase algorithm integration
- Current approach is Apriori-style (candidate generation + test).
- HUI-Miner/EFIM-style one-phase algorithms avoid candidate generation.
- Integration would require adapting utility-list structures for window-level computation.

### Q4: Streaming extension
- The current algorithm is batch-oriented.
- For streaming applications, incremental update of prefix sums and dense intervals is needed.

### Q5: Comparison with LHUIM
- Local High-Utility Itemset Mining (LHUIM) considers utility in sub-databases.
- Direct comparison requires adapting LHUIM to the sliding-window temporal setting.

## Resolved Questions

(none yet)
