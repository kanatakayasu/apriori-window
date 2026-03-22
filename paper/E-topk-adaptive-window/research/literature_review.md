# Literature Review: Parameter-Free Dense Interval Mining with Top-k and Adaptive Windows

## 1. Top-k Frequent Pattern Mining

### 1.1 Top-k Frequent Itemset Mining (without minsup)
Traditional frequent itemset mining (FIM) requires a user-specified minimum support threshold, which is hard to tune without domain knowledge. Top-k FIM replaces this with a more intuitive parameter k (number of desired patterns).

**Key algorithms:**
- **Top-K Miner** (Yadav & Soni, 2016): Discovers top-k identical frequent itemsets without support threshold. Uses equivalence classes to reduce candidate generation.
- **TKFIM** (Fatima et al., 2021): Based on equivalence classes of set theory. No user-specified support threshold needed.
- **BOMO/LOOPBACK** (Fu et al., 2004): Mine N-most interesting itemsets without support threshold. Introduced the concept of mining itemsets ranked by support.

### 1.2 Top-k Sequential Pattern Mining
- **TKS** (Fournier-Viger et al., 2013): Top-k sequential pattern mining using vertical bitmap representation and PMAP (Precedence Map). Outperforms TSP by an order of magnitude.
- **TSP** (Tzvetkov et al., 2003): Early top-k sequential pattern algorithm.

### 1.3 Top-k High Utility Itemset Mining
- **TKO** (Tseng et al., 2015): One-phase algorithm for top-k high utility itemsets.
- **kHMC** (Duong et al., 2016): Novel threshold raising (RIU, CUD, COV) and pruning strategies (EUCPT, TEP). Outperforms TKO and REPT.
- **TKEH** (Krishnamoorthy, 2018): Efficient top-k HUI mining with improved utility-list construction.

### 1.4 Common Techniques
All top-k algorithms share a common strategy: maintain an internal threshold that is progressively raised as better patterns are discovered. The key challenge is raising this threshold quickly to prune the search space effectively.

## 2. Multi-Scale Analysis and Scale-Space Theory

### 2.1 Scale-Space Theory (Lindeberg)
- **Scale-Space Framework** (Lindeberg, 1994): Embedding signals into a family of smoothed signals parameterized by scale. Enables automatic scale selection.
- **Blob Detection** (Lindeberg, 1993): Multi-scale detection of salient structures using scale-space primal sketch. Detects scale-normalized Laplacian extrema.
- **Automatic Scale Selection** (Lindeberg, 1998): Local extrema over scales of gamma-normalized derivatives correspond to interesting structures. Foundation for SIFT.

### 2.2 Wavelet and Dyadic Decomposition
- **Multiresolution Analysis (MRA)** (Mallat & Meyer, 1988/89): Hierarchical decomposition using dyadic scaling (powers of 2).
- **Dyadic Wavelet Transform**: Coefficients at scale tau_j = 2^(j-1). Each level halves frequency band, doubles scale. Provides variable resolution at different times and frequencies.
- **ARAMS** (Association Rules Algorithm based on Multi Scale): Multi-scale data analysis for association rule discovery.

### 2.3 Multi-Scale Time Series Analysis
- **Matrix Profile** (Yeh et al., 2016): State-of-the-art motif discovery. Supports multi-scale via rescaling and AB-join.
- **Variable-Length Motif Discovery** (MAD, Linardi et al., 2020): Discovers motifs at multiple lengths simultaneously.

## 3. Branch-and-Bound in Pattern Mining

### 3.1 General B&B Framework
Three components: search strategy, branching strategy, pruning rules. Maintains bounds to eliminate subproblems that cannot contain optimal solutions.

### 3.2 Applications in Itemset Mining
- **Apriori Property**: Downward-closure guarantees all supersets of infrequent itemsets are infrequent. Natural pruning in B&B.
- **Utility Upper Bounds**: TWU, sub-tree utility, local utility for high utility itemset mining.
- **Coverage-based Pruning** (COV in kHMC): Novel concept of coverage for search space reduction.

### 3.3 Relevance to Dense Interval Mining
The dense interval property is anti-monotone at the item level (multi-item dense intervals are subsets of single-item dense intervals), enabling Apriori-style pruning. Extending to top-k requires maintaining a dynamic threshold as the k-th best score.

## 4. Parameter-Free Mining

### 4.1 Compression-Based Approaches
- **Keogh & Lonardi (2004)**: Pioneering work on parameter-free data mining using Kolmogorov complexity and compression. MDL principle for model selection.
- **Normalized Information Distance (NID)**: Universal similarity metric. Practical implementation via off-the-shelf compressors.

### 4.2 GraphScope
- **Sun et al. (2007)**: Parameter-free mining of large time-evolving graphs. Automatic detection of communities and temporal changes.

### 4.3 User Parameter-Free Sequential Classification
- **Egho et al. (2016)**: Mining sequential classification rules without user parameters.

## 5. Adaptive Window Methods

### 5.1 ADWIN (Adaptive Windowing)
- **Bifet & Gavalda (2007)**: Variable-length window that automatically grows during stable periods and shrinks upon drift detection. Mathematical guarantees on false positive/negative rates. Logarithmic memory via bucket compression.
- **ADWIN-U** (Assis & Souza, 2025): Extension for unsupervised drift detection.
- **Parallel ADWIN** (Grulich et al., 2018): Scalable version for data streams.

### 5.2 Window Size Selection
- **Ermshaus et al. (2022)**: Comprehensive survey of 6 window size selection algorithms for time series analytics (anomaly detection, segmentation, motif discovery).
- **Multi-Window-Finder** (2021): Domain-agnostic window size determination.
- **DTW Window Optimization** (Dau et al., 2018): Optimizing dynamic time warping window width.

### 5.3 Learning from Time-Changing Data
- **Klinkenberg (2004)**: Adaptive windowing for learning from concept-drifting data. Window adjustment based on generalization performance.

## 6. Temporal Pattern Mining

### 6.1 Dense Season Discovery
- **Mining Seasonal Temporal Patterns** (Wen et al., 2022): minDensity parameter for controlling pattern density within seasonal windows.
- **TIRP Mining**: Time-interval related patterns with temporal operators.

### 6.2 Efficient Temporal Mining
- **Ho et al. (2022)**: Mutual information-based temporal pattern mining in big time series (VLDB).
- **Mining Recent Temporal Patterns** (Batal et al., 2012): Event detection in multivariate time series (KDD).

## 7. Summary of Key References (30 papers)

| # | Authors | Year | Title | Venue | Relevance |
|---|---------|------|-------|-------|-----------|
| 1 | Fournier-Viger et al. | 2013 | TKS: Efficient Mining of Top-K Sequential Patterns | ADMA | Top-k sequential |
| 2 | Tseng et al. | 2015 | TKO: Mining Top-K Utility Itemsets in One Phase | TKO | Top-k utility |
| 3 | Duong et al. | 2016 | kHMC: Efficient top-k HUI mining | KBS | Threshold raising |
| 4 | Yadav & Soni | 2016 | Top-K Miner | KAIS | Parameter-free FIM |
| 5 | Fatima et al. | 2021 | TKFIM: Top-K FIM via equivalence classes | PeerJ CS | Parameter-free FIM |
| 6 | Fu et al. | 2004 | Mining without support threshold | TKDE | Foundation |
| 7 | Lindeberg | 1994 | Scale-Space Theory in Computer Vision | Book | Scale-space |
| 8 | Lindeberg | 1998 | Feature Detection with Automatic Scale Selection | IJCV | Scale selection |
| 9 | Lindeberg | 1993 | Scale-Space Primal Sketch | IJCV | Blob detection |
| 10 | Mallat | 1989 | Multiresolution Approximations and Wavelets | Trans. AMS | MRA/dyadic |
| 11 | Yeh et al. | 2016 | Matrix Profile I | ICDM | Multi-scale motif |
| 12 | Linardi et al. | 2020 | Matrix Profile Goes MAD | DMKD | Variable-length |
| 13 | Keogh & Lonardi | 2004 | Towards Parameter-Free Data Mining | KDD | Parameter-free |
| 14 | Bifet & Gavalda | 2007 | Learning from Time-Changing Data with ADWIN | SDM | Adaptive window |
| 15 | Ermshaus et al. | 2022 | Window Size Selection in Unsupervised TS Analytics | AALTD | Window selection |
| 16 | Sun et al. | 2007 | GraphScope: Parameter-free Mining | KDD | Parameter-free |
| 17 | Ho et al. | 2022 | Efficient Temporal Pattern Mining via MI | VLDB | Temporal mining |
| 18 | Batal et al. | 2012 | Mining Recent Temporal Patterns | KDD | Event detection |
| 19 | Wen et al. | 2022 | Mining Seasonal Temporal Patterns | arXiv | Dense seasons |
| 20 | Agrawal & Srikant | 1994 | Fast Algorithms for Mining Association Rules | VLDB | Apriori foundation |
| 21 | Han et al. | 2000 | Mining Frequent Patterns without Candidate Generation | SIGMOD | FP-Growth |
| 22 | Zaki | 2000 | Scalable Algorithms for Association Mining | TKDE | ECLAT |
| 23 | Krishnamoorthy | 2018 | TKEH for top-k HUI mining | APPL INTELL | Top-k utility |
| 24 | Klinkenberg | 2004 | Learning Drifting Concepts | Book chapter | Adaptive window |
| 25 | Assis & Souza | 2025 | ADWIN-U: Unsupervised Drift Detection | KAIS | Adaptive window |
| 26 | Grulich et al. | 2018 | Parallel ADWIN | EDBT | Scalable drift |
| 27 | Dau et al. | 2018 | Optimizing DTW Window Width | DMKD | Window optimization |
| 28 | Egho et al. | 2016 | Parameter-Free Sequential Classification | KAIS | Parameter-free |
| 29 | Pollock | 2014 | Dyadic Wavelets Analysis | Lecture Notes | Dyadic theory |
| 30 | Morrison et al. | 2024 | Efficient Top-k FIM on Massive Data | DSE | Scalable top-k |
