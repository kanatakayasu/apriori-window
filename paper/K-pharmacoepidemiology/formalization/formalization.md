# Formalization: Dense Prescription Patterns and Regulatory Event Attribution

## 1. Prescription Transaction Model

### Definition 1 (ATC Item Mapping)
Let $\mathcal{A}$ denote the set of ATC (Anatomical Therapeutic Chemical) codes at a chosen hierarchical level $\ell \in \{1, 2, 3, 4, 5\}$. Define the mapping function:

$$\phi_\ell : \text{DrugName} \to \mathcal{A}_\ell$$

that maps each prescribed drug to its ATC code truncated at level $\ell$. The item universe is $\mathcal{I} = \mathcal{A}_\ell$.

### Definition 2 (Prescription Transaction)
Given a patient population and a time-ordered sequence of clinical encounters (visits, admissions, or prescription fills), a **prescription transaction** $d_t$ at time index $t$ is:

$$d_t = \{\phi_\ell(\text{drug}) : \text{drug} \in \text{Prescriptions}(t)\} \subseteq \mathcal{I}$$

The set of all drugs prescribed (or dispensed) at time $t$, mapped to their ATC codes. The transaction sequence is $D = [d_1, d_2, \ldots, d_N]$ ordered by time.

**Granularity options**:
- **Visit-level**: Each outpatient visit or hospital admission forms one transaction
- **Day-level**: All prescriptions on the same calendar day form one transaction
- **Week-level**: Aggregated to weekly bins for coarser temporal analysis

### Definition 3 (ATC Hierarchical Levels)
The ATC hierarchy has 5 levels:
- Level 1: Anatomical main group (e.g., C = Cardiovascular)
- Level 2: Therapeutic subgroup (e.g., C09 = ACE inhibitors)
- Level 3: Pharmacological subgroup (e.g., C09A = ACE inhibitors, plain)
- Level 4: Chemical subgroup (e.g., C09AA = ACE inhibitors, plain)
- Level 5: Chemical substance (e.g., C09AA01 = Captopril)

Analysis at level 3 or 4 provides a good balance between specificity and statistical power.

## 2. Dense Prescription Interval

### Definition 4 (Support Time Series)
For a prescription pattern (itemset) $P \subseteq \mathcal{I}$, window size $W \in \mathbb{Z}_{>0}$, and transaction sequence $D$ of length $N$:

$$s_P(t) = |\{d_j \in D : t \leq j < t + W, P \subseteq d_j\}|, \quad t = 0, 1, \ldots, N - W$$

### Definition 5 (Dense Prescription Interval)
A **dense prescription interval** for pattern $P$ with threshold $\theta$ is a maximal contiguous range $[s, e]$ such that:

$$\forall t \in [s, e]: s_P(t) \geq \theta$$

The set of all dense intervals for $P$ is denoted $\mathcal{D}(P, W, \theta)$.

**Clinical interpretation**: A dense prescription interval indicates a time period during which the co-prescription pattern $P$ appears in at least $\theta$ transactions within any window of $W$ consecutive time points. This signals sustained, elevated co-prescribing of the drug combination.

## 3. Regulatory Event Attribution

### Definition 6 (Regulatory Event)
A **regulatory event** $r = (\text{id}, \text{type}, t_r, \mathcal{I}_r)$ consists of:
- A unique identifier
- Event type $\in$ {safety_alert, boxed_warning, withdrawal, label_change, REMS}
- Event timestamp $t_r$
- Targeted drug set $\mathcal{I}_r \subseteq \mathcal{I}$ (ATC codes affected)

The set of regulatory events is $\mathcal{R} = \{r_1, r_2, \ldots, r_K\}$.

### Definition 7 (Pre/Post-Event Windows)
For regulatory event $r$ with timestamp $t_r$ and lookback/lookforward parameter $h$:

$$W^{-}(r) = [t_r - h, t_r - 1] \quad \text{(pre-event window)}$$
$$W^{+}(r) = [t_r, t_r + h - 1] \quad \text{(post-event window)}$$

### Definition 8 (Density Change Score)
For pattern $P$ and regulatory event $r$, the **density change score** is:

$$\Delta(P, r) = \bar{s}_P^{+}(r) - \bar{s}_P^{-}(r)$$

where:

$$\bar{s}_P^{-}(r) = \frac{1}{|W^{-}(r)|} \sum_{t \in W^{-}(r)} s_P(t), \quad \bar{s}_P^{+}(r) = \frac{1}{|W^{+}(r)|} \sum_{t \in W^{+}(r)} s_P(t)$$

### Definition 9 (Contrast Pattern Classification)
Given threshold $\delta > 0$, pattern $P$ is classified relative to event $r$ as:
- **Disappearing** if $\Delta(P, r) < -\delta$ and $P \cap \mathcal{I}_r \neq \emptyset$
- **Emerging** if $\Delta(P, r) > \delta$
- **Stable** if $|\Delta(P, r)| \leq \delta$

## 4. Statistical Testing

### Definition 10 (Permutation Test for Attribution)
To test $H_0$: the density change at $t_r$ is no greater than expected by chance:

1. Compute the observed test statistic $T_{\text{obs}} = |\Delta(P, r)|$
2. Generate $B$ random time points $\{t^{(1)}, \ldots, t^{(B)}\}$ uniformly from valid positions
3. Compute $T^{(b)} = |\Delta(P, r^{(b)})|$ for each permuted event $r^{(b)}$ with timestamp $t^{(b)}$
4. $p\text{-value} = \frac{1 + \sum_{b=1}^{B} \mathbb{1}[T^{(b)} \geq T_{\text{obs}}]}{1 + B}$

### Definition 11 (Multiple Testing Correction)
For $M = |\mathcal{F}| \times |\mathcal{R}|$ hypothesis tests, apply Benjamini-Hochberg FDR control at level $\alpha$:

1. Order $p$-values: $p_{(1)} \leq p_{(2)} \leq \cdots \leq p_{(M)}$
2. Find largest $k$ such that $p_{(k)} \leq \frac{k}{M} \alpha$
3. Reject $H_{(1)}, \ldots, H_{(k)}$

## 5. Theoretical Properties

### Proposition 1 (Detection Power)
For a pattern $P$ with true support change $\mu$ at event time $t_r$, the power to detect the change increases with:
- Window size $W$ (more transactions per window $\Rightarrow$ lower variance)
- Lookback parameter $h$ (more data for mean estimation)
- Magnitude of support change $|\mu|$

Specifically, under Poisson assumptions for transaction counts, the power is approximately:

$$\text{Power} \approx \Phi\left(\frac{|\mu|}{\sqrt{2\lambda/h}} - z_{1-\alpha/2}\right)$$

where $\lambda$ is the baseline support rate and $\Phi$ is the standard normal CDF.

### Proposition 2 (FDR Control)
Under the Benjamini-Hochberg procedure with permutation p-values:
- FDR is controlled at level $\alpha$ when the test statistics under the null are exchangeable
- The number of false positives is bounded: $E[\text{FP}] \leq \alpha \cdot M_0 / M$ where $M_0$ is the number of true nulls

### Proposition 3 (Computational Complexity)
Let $n$ be the number of unique ATC codes, $N$ the number of transactions, $k_{\max}$ the maximum pattern size:
- Candidate generation: $O(\binom{n}{k_{\max}})$ in the worst case, but Apriori pruning reduces to $O(|\mathcal{F}|^2)$
- Dense interval detection per pattern: $O(N \log N)$
- Attribution testing: $O(|\mathcal{F}| \times |\mathcal{R}| \times B)$ for $B$ permutations
- Total: $O(|\mathcal{F}|^2 + |\mathcal{F}| \cdot N \log N + |\mathcal{F}| \cdot |\mathcal{R}| \cdot B)$

## 6. Parameter Guidelines for Pharmacoepidemiology

| Parameter | Recommended Range | Rationale |
|-----------|------------------|-----------|
| ATC level $\ell$ | 3--4 | Balance between specificity and statistical power |
| Window size $W$ | 30--90 (days) or 4--12 (weeks) | Clinically meaningful prescribing periods |
| Threshold $\theta$ | 3--10 | Depends on population size and pattern frequency |
| Lookback $h$ | 90--365 (days) | Capture seasonal variation while detecting change |
| Permutations $B$ | 999--9999 | Precision of p-value estimation |
| FDR level $\alpha$ | 0.05 | Standard significance level |
| Change threshold $\delta$ | 0.5--2.0 | Minimum clinically meaningful support change |
