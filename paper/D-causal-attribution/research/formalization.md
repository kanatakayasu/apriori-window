# Formal Theory: Synthetic Control for Dense Pattern Attribution

## Problem Setting

Let $\mathcal{D} = \{T_1, T_2, \ldots, T_N\}$ be a sequence of $N$ transactions.
For a pattern (itemset) $P$, define the windowed support at position $t$ with window size $W$:

$$\sigma_P(t) = \frac{|\{i \in [t, t+W) : P \subseteq T_i\}|}{W}$$

This gives a support time series $\mathbf{s}_P = (\sigma_P(1), \sigma_P(2), \ldots, \sigma_P(N-W+1))$.

## Definitions

### Definition 1: Donor Pool
Given a treated pattern $P^*$ and a set of candidate patterns $\mathcal{P}$, the **donor pool** is:

$$\mathcal{D}(P^*) = \{P \in \mathcal{P} : P \cap P^* = \emptyset\}$$

where $P \cap P^*$ denotes the intersection of item sets.

### Definition 2: Counterfactual Support Trajectory
Given an intervention time $t_0$ and donor pool $\mathcal{D}(P^*)$ with $J$ donors, the **counterfactual support trajectory** is:

$$\hat{\sigma}_{P^*}^{CF}(t) = \sum_{j=1}^{J} w_j \cdot \sigma_{P_j}(t), \quad t \geq t_0$$

where weights $\mathbf{w} = (w_1, \ldots, w_J)$ are obtained by minimizing pre-intervention fit:

$$\mathbf{w}^* = \arg\min_{\mathbf{w}} \sum_{t=1}^{t_0-1} \left(\sigma_{P^*}(t) - \sum_{j=1}^{J} w_j \cdot \sigma_{P_j}(t)\right)^2$$

subject to $w_j \geq 0$ and $\sum_j w_j = 1$.

### Definition 3: Causal Effect on Support
The **causal effect** at time $t \geq t_0$ is:

$$\tau(t) = \sigma_{P^*}(t) - \hat{\sigma}_{P^*}^{CF}(t)$$

The **cumulative causal effect** is:

$$\mathcal{T} = \sum_{t=t_0}^{T} \tau(t)$$

### Definition 4: Item-Disjoint Pattern Control
A pattern $P_j$ is a valid control for $P^*$ if:
1. $P_j \cap P^* = \emptyset$ (item disjointness)
2. Pre-intervention RMSPE of $P_j$ fit is below threshold $\delta$

## Theorem 1: Unbiasedness under Parallel Trends
If the parallel trends assumption holds for item-disjoint patterns (i.e., absent the intervention, all patterns in the donor pool would have experienced the same proportional change in support), then $\hat{\tau}$ is an unbiased estimator of the true causal effect.

## Theorem 2: Placebo Test Validity
Under the null hypothesis of no causal effect, the probability that the treated pattern's post-intervention RMSPE exceeds that of a randomly chosen donor is $1/(J+1)$, providing an exact p-value.

## Algorithm Complexity
- Donor pool construction: $O(|\mathcal{P}| \cdot |P^*|)$
- Weight optimization (quadratic programming): $O(J^2 \cdot t_0)$
- Placebo tests: $O(J \cdot (J^2 \cdot t_0))$ (repeat for each donor)
- Total: $O(J^3 \cdot t_0)$
