# Literature Survey: Rare Dense Patterns

## 1. Rare / Infrequent Itemset Mining

### 1.1 Foundational Algorithms

| # | Reference | Key Contribution | Relevance |
|---|-----------|-----------------|-----------|
| 1 | Szathmary et al., "Towards Rare Itemset Mining" (2007) | First systematic study of rare itemset mining; introduced Apriori-Rare and Apriori-Inverse | Baseline for rare pattern discovery |
| 2 | Tsang et al., "RP-Tree: Rare Pattern Tree Mining" (2011) | FP-Growth extension for rare itemsets using single min-support threshold | Direct competitor; mines globally rare patterns but ignores temporal density |
| 3 | Haglin & Manning, "On Minimal Infrequent Itemset Mining" (2007) | Formal study of MFI boundary; complexity results | Theoretical foundation for our rarity condition |
| 4 | Gupta et al., "Minimally Infrequent Itemset Mining using Pattern-Growth and Residual Trees" (2012) | IFP-Tree algorithm for minimal infrequent itemsets | Efficient enumeration of infrequent boundary |
| 5 | Bhatt & Patel, "MCRP-Tree: Maximum Constraint Rare Pattern Tree" (2015) | Multiple minimum support thresholds for rare items | Addresses item-level rarity heterogeneity |
| 6 | Koh & Rountree, "Finding Sporadic Rules Using Apriori-Inverse" (2005) | Mining rules with low support but high confidence | Related: sporadic = globally rare + locally confident |
| 7 | Adda et al., "Rare Itemset Mining" (2007) | Survey and taxonomy of rare pattern definitions | Taxonomy reference |

### 1.2 Recent Advances (2023-2026)

| # | Reference | Key Contribution | Relevance |
|---|-----------|-----------------|-----------|
| 8 | Fournier-Viger et al., "Comparative Analysis of Frequent Pattern Mining Algorithms" (2025) | Comprehensive comparison of Apriori, EClaT, FP-Growth, FIN, PrePost+, Pascal, LCMFreq | Benchmark methodology reference |
| 9 | Cuzzocrea et al., "Rare pattern mining: challenges and future perspectives" (2018, Complex & Intell Syst) | Survey identifying open challenges in rare pattern mining | Gap identification source |
| 10 | Kumar et al., "Mining Interesting Infrequent and Frequent Itemsets Based on MLMS Model" (2008) | Multi-level minimum support for mixed frequent/infrequent mining | Relates to our two-threshold approach |

## 2. Anomaly Detection

| # | Reference | Key Contribution | Relevance |
|---|-----------|-----------------|-----------|
| 11 | Liu et al., "Isolation Forest" (2008, ICDM; 2012, TKDD) | Isolation-based anomaly detection; O(n log n) | Alternative approach to rare event detection; point-based, no temporal structure |
| 12 | Breunig et al., "LOF: Identifying Density-Based Local Outliers" (2000, SIGMOD) | Local Outlier Factor; density-based anomaly scoring | Inspiration for local density concept |
| 13 | Scholkopf et al., "One-Class SVM" (2001) | Support vector method for novelty detection | Alternative rare event detector |
| 14 | He et al., "Minimal weighted infrequent itemset mining for outlier detection in uncertain data streams" (2018) | MWIFIM-OD-UDS for rare itemset-based outlier detection | Bridges rare pattern mining and anomaly detection |

## 3. Burst Detection

| # | Reference | Key Contribution | Relevance |
|---|-----------|-----------------|-----------|
| 15 | Kleinberg, "Bursty and Hierarchical Structure in Streams" (2003, DMKD) | Infinite HMM for burst detection in document streams | Core inspiration for temporal density detection |
| 16 | Zhu & Shasha, "StatStream: Statistical Monitoring of Thousands of Data Streams" (2002, VLDB) | Real-time statistical monitoring with sliding windows | Sliding window pattern monitoring |
| 17 | Luo et al., "Mining Recent Temporal Patterns for Event Detection in Multivariate Time Series" (2014, KDD) | Temporal pattern mining for event detection | Combines temporal mining with event detection |

## 4. Temporal / Sliding Window Pattern Mining

| # | Reference | Key Contribution | Relevance |
|---|-----------|-----------------|-----------|
| 18 | Datar et al., "Maintaining Stream Statistics over Sliding Windows" (2002, SIAM) | Exponential histograms for approximate counting in sliding windows | Foundational sliding window technique |
| 19 | Chang & Lee, "A Sliding Window Dual Support Framework for Discovering Emerging Trends" (2003; 2009, KBS) | Dual support counts (supp1, supp2) for trend detection | Related: dual support resembles our local vs global support |
| 20 | R3PStreamSW, "Sliding Window Based Rare Partial Periodic Pattern Mining" (2025, Frontiers Big Data) | Rare periodic patterns in temporal data streams | Very recent; closest related work on rare+temporal patterns |
| 21 | Li et al., "Multi-type concept drift detection under dual-layer variable sliding window in frequent pattern mining" (2023, J Cloud Comput) | Variable sliding window for concept drift in pattern mining | Adaptive window for support variation |

## 5. Anti-Monotonicity and Its Limitations

| # | Reference | Key Contribution | Relevance |
|---|-----------|-----------------|-----------|
| 22 | Agrawal & Srikant, "Fast Algorithms for Mining Association Rules" (1994, VLDB) | Apriori algorithm; downward closure (anti-monotonicity) | Foundation that our work modifies |
| 23 | Pei & Han, "Mining Frequent Itemsets with Convertible Constraints" (2001) | Convertible constraints when anti-monotonicity fails | Technique for non-anti-monotone constraints |
| 24 | Bonchi et al., "Pushing Tougher Constraints in Frequent Pattern Mining" (2005) | Relaxation-based approaches for non-prunable constraints | Related constraint relaxation approach |

## 6. Local Pattern Discovery

| # | Reference | Key Contribution | Relevance |
|---|-----------|-----------------|-----------|
| 25 | Moens & Goethals, "Mining Locally Frequent Itemsets" (2013) | Itemsets frequent in subsets of transactions | Directly related: local vs global frequency |
| 26 | Nakamura et al., "Mining Approximate Patterns with Frequent Locally Optimal Occurrences" (2016) | Locally optimal occurrence-based pattern mining | Local optimality concept |
| 27 | Dong & Li, "Efficient Mining of Emerging Patterns" (1999, KDD) | Emerging patterns: support ratio between datasets | Contrast mining relates to local/global support divergence |
