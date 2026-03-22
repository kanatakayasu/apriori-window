# Formalization: Dense Gene Co-expression Intervals on Pseudotime

## 1. Problem Setting

### 1.1 Definitions

**Definition 1 (Pseudotime-Ordered Cell Sequence).**
Let $\mathcal{C} = \{c_1, c_2, \ldots, c_n\}$ be a set of $n$ cells ordered by
pseudotime $\tau(c_1) \leq \tau(c_2) \leq \cdots \leq \tau(c_n)$.

**Definition 2 (Gene Universe and Expression Binarization).**
Let $\mathcal{G} = \{g_1, g_2, \ldots, g_m\}$ be the gene universe.
For cell $c_i$ and gene $g_j$, let $x_{ij} \in \mathbb{R}_{\geq 0}$ be the
normalized expression value. Define the binarized indicator:

$$b_{ij} = \begin{cases} 1 & \text{if } x_{ij} \geq \theta_j \\ 0 & \text{otherwise} \end{cases}$$

where $\theta_j$ is the expression threshold for gene $g_j$.

**Definition 3 (Transaction).**
The transaction for cell $c_i$ is $T_i = \{g_j \in \mathcal{G} \mid b_{ij} = 1\}$.

**Definition 4 (Transaction Database on Pseudotime).**
The pseudotime-ordered transaction database is $\mathcal{D} = (T_1, T_2, \ldots, T_n)$
where cells are sorted by pseudotime index.

### 1.2 Dense Gene Co-expression Interval (DGCI)

**Definition 5 (Support in Window).**
For a gene set $S \subseteq \mathcal{G}$ and pseudotime window $[l, l+W]$
(where $W$ is the window size in pseudotime index units), the window support is:

$$\text{sup}(S, l, W) = |\{i \mid l \leq i \leq l+W,\; S \subseteq T_i\}|$$

**Definition 6 (Dense Interval).**
A contiguous pseudotime index interval $[s, e]$ is a *dense interval* for
gene set $S$ with parameters $(W, \sigma)$ if:

$$\forall l \in [s, e]: \text{sup}(S, l, W) \geq \sigma$$

and $[s, e]$ is maximal (cannot be extended in either direction while
maintaining the density condition).

**Definition 7 (Dense Gene Co-expression Interval, DGCI).**
A DGCI is a pair $(S, [s, e])$ where $S$ is a gene set and $[s, e]$ is a
dense interval for $S$. The actual pseudotime span is
$[\tau(c_s), \tau(c_{e+W})]$.

## 2. Problem Statement

**Problem (DGCI Mining).**
Given a pseudotime-ordered transaction database $\mathcal{D}$, window size $W$,
support threshold $\sigma$, and maximum itemset size $k_{\max}$, find all
DGCIs $(S, [s, e])$ such that $|S| \leq k_{\max}$.

## 3. Algorithm

### 3.1 Adapter: scRNA-seq → Transaction Database

1. **Input**: Gene-by-cell expression matrix $X \in \mathbb{R}^{m \times n}$,
   pseudotime vector $\boldsymbol{\tau} \in \mathbb{R}^n$.
2. **Sort** cells by pseudotime: $c_{\pi(1)}, \ldots, c_{\pi(n)}$.
3. **Binarize**: For each gene $g_j$, compute threshold $\theta_j$
   (e.g., median, quantile, or adaptive).
4. **Output**: Transaction database $\mathcal{D}$.

### 3.2 Threshold Strategies

| Strategy | Definition | Use case |
|----------|-----------|----------|
| Global median | $\theta_j = \text{median}(\{x_{ij} \mid x_{ij} > 0\})$ | Simple baseline |
| Quantile-$q$ | $\theta_j = Q_q(\{x_{ij} \mid x_{ij} > 0\})$ | Adjustable sensitivity |
| z-score | $\theta_j = \mu_j + z \cdot \sigma_j$ | Highlights overexpression |

### 3.3 Mining

Apply Apriori-Window (find_dense_itemsets) to $\mathcal{D}$ with
parameters $(W, \sigma, k_{\max})$.

## 4. Complexity

**Theorem 1.** The time complexity of DGCI mining is
$O(n \cdot |\mathcal{F}| \cdot W)$ where $|\mathcal{F}|$ is the number of
frequent gene sets and $n$ is the number of cells.

*Proof.* For each frequent gene set, the sliding window scan visits at most
$n$ positions, each requiring $O(W)$ count operations (or $O(\log n)$ with
binary search on sorted occurrence lists). The Apriori candidate generation
is bounded by $|\mathcal{F}|^2$ but pruned effectively. $\square$

**Theorem 2 (Apriori Monotonicity Preservation).**
If gene set $S$ has no dense interval, then no superset $S' \supset S$ has
a dense interval. This follows directly from $S \subseteq T_i \Rightarrow
S' \subseteq T_i$ being more restrictive.

## 5. Biological Interpretation

A DGCI $(S, [s, e])$ indicates that gene set $S$ is simultaneously expressed
in a concentrated cluster of cells within the pseudotime window $[s, e+W]$.
This corresponds to:

- **Coordinated regulatory programs** during differentiation
- **Transient pathway activation** at specific developmental stages
- **Co-regulation modules** that are temporally localized

## 6. Evaluation Metrics

1. **Biological coherence**: Gene Ontology (GO) enrichment of detected gene sets
2. **Temporal precision**: Overlap with known differentiation stage boundaries
3. **Comparison with WGCNA**: Static modules vs. temporally localized DGCIs
4. **Sensitivity analysis**: Effect of $W$, $\sigma$, and $\theta$ on results
