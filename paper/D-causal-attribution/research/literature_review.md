# Literature Review: Causal Attribution for Dense Patterns

## Core References

### Synthetic Control Methods
1. **Abadie & Gardeazabal (2003)** - "The Economic Costs of Conflict: A Case Study of the Basque Country" - Introduced synthetic control for comparative case studies.
2. **Abadie, Diamond & Hainmueller (2010)** - "Synthetic Control Methods for Comparative Case Studies: Estimating the Effect of California's Tobacco Control Program" - Formalized SCM with optimization framework.
3. **Abadie, Diamond & Hainmueller (2015)** - "Comparative Politics and the Synthetic Control Method" - Extended SCM theory and placebo tests.

### Difference-in-Differences
4. **Card & Krueger (1994)** - Classic DiD for minimum wage studies.
5. **Angrist & Pischke (2009)** - "Mostly Harmless Econometrics" - DiD framework and assumptions.

### Causal Impact / Bayesian Structural Time Series
6. **Brodersen et al. (2015)** - "Inferring causal impact using Bayesian structural time series" - CausalImpact package; Bayesian approach to counterfactual estimation for intervention time series.

### Rubin Causal Model
7. **Rubin (1974)** - Potential outcomes framework.
8. **Imbens & Rubin (2015)** - "Causal Inference for Statistics, Social, and Biomedical Sciences" - Comprehensive treatment.

### Frequent Pattern Mining + Temporal
9. **Agrawal & Srikant (1994)** - Apriori algorithm.
10. **Han, Pei & Yin (2000)** - FP-Growth.
11. Existing work in this repository - Dense interval detection via sliding window Apriori.

## Research Gap

No existing work applies synthetic control methods to **pattern support time series**. The key insight is:

- Dense interval detection identifies *when* a pattern's support changes
- But it cannot attribute the change to a specific external event (causal claim)
- SCM provides a principled counterfactual framework: "What would support have been without the event?"

The challenge is constructing a valid **donor pool** from other patterns whose support trajectories are unaffected by the event. We propose using **item-disjoint patterns** as controls, ensuring no shared items with the treated pattern.

## Key Theoretical Contributions

1. **Donor Pool Construction via Item Disjointness** - Novel criterion for selecting control patterns
2. **Counterfactual Support Trajectory** - Weighted combination of control pattern supports
3. **Causal Effect on Support** - Difference between observed and counterfactual trajectories
4. **Permutation-based Inference** - Placebo tests using donor reassignment
