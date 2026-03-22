# Pending Questions: Paper D - Causal Attribution

## Open Questions

1. **Real-data validation**: Dunnhumby data is not available in git. Need to confirm access and format for E4 real-data variant.

2. **Donor pool size requirement**: The minimum p-value is 1/(J+1). With typical retail datasets, how many item-disjoint patterns can be expected? May need to relax the disjointness criterion.

3. **Multiple interventions**: The current framework handles a single intervention. Extension to multiple sequential interventions needs formalization.

4. **Parallel trends validation**: How to empirically validate the parallel trends assumption for pattern support series? Pre-treatment fit (RMSPE) is necessary but not sufficient.

5. **Comparison with CausalImpact**: Should we add a comparison with Brodersen et al. (2015) Bayesian approach? Requires specifying a state-space model for support series.

## Resolved

(None yet)
