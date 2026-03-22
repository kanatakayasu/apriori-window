# Pending Questions — Paper E

## Formalization
1. **Density ratio scaling**: The current threshold scaling $\theta_\ell = \lceil \theta_0 \cdot 2^\ell \rceil$ maintains constant density ratio. Should we also consider sub-linear scaling (e.g., $\theta_\ell = \lceil \theta_0 \cdot 2^{\ell/2} \rceil$) to allow sparser density at coarser scales?

2. **Ridge connectivity**: We use 4-connected BFS for ridge detection. Would 8-connectivity (including diagonal neighbors in the scale-position plane) be more appropriate for capturing gradual scale transitions?

## Implementation
3. **Incremental MSDCS**: For streaming applications, can we efficiently update MSDCS as new transactions arrive without full recomputation?

4. **Non-dyadic scales**: The current implementation only considers powers-of-2 window sizes. Would interpolating between dyadic levels improve resolution without significant computational overhead?

## Experiments
5. **Real data evaluation**: E1-E4 use synthetic data. Need to run on real datasets (retail.txt, kosarak.txt) to validate practical utility. The current implementation may need optimization for datasets with thousands of items.

6. **Comparison with Matrix Profile**: How does our multi-scale approach compare with Matrix Profile's variable-length motif discovery in terms of discovered patterns?

## Paper
7. **Venue selection**: VLDB 2027 vs ICDM 2027 — which venue better fits the contribution? VLDB emphasizes scalability/systems, ICDM emphasizes algorithms/theory.

8. **Page budget**: Current draft is approximately 8 pages. May need expansion of experiments section for top venues.
