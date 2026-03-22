# Gap Analysis: Parameter-Free Dense Interval Mining

## Identified Research Gaps

### Gap 1: No Top-k Formulation for Dense Interval Mining
**Current State**: Dense interval mining requires two critical parameters: window size W and support threshold theta. Users must manually tune these, leading to trial-and-error workflows.
**What Exists**: Top-k approaches exist for frequent itemset mining (Top-K Miner, TKFIM), sequential pattern mining (TKS), and high utility mining (TKO, kHMC), but none for dense interval mining.
**Our Contribution**: Define a Dense Coverage Score that enables ranking of (pattern, interval) pairs, and provide a top-k algorithm that eliminates the theta parameter.

### Gap 2: Single-Scale Limitation in Dense Interval Detection
**Current State**: Existing dense interval mining uses a fixed window size W, which cannot capture patterns that are dense at multiple temporal scales simultaneously.
**What Exists**: Scale-space theory (Lindeberg) provides automatic scale selection for image features. Matrix Profile supports multi-scale motif discovery. ADWIN adapts window size for drift detection. However, none combine multi-scale analysis with dense interval mining.
**Our Contribution**: Introduce Scale-Space Dense Ridges -- persistent dense structures across a dyadic scale hierarchy (W, 2W, 4W, ...). These ridges identify patterns with robust temporal density independent of window size choice.

### Gap 3: No Efficient Algorithm for Multi-Scale Dense Enumeration
**Current State**: Naively computing dense intervals at L scales for all candidate patterns has complexity O(L * |candidates| * N), which is prohibitive.
**What Exists**: Branch-and-bound is used in top-k utility mining (kHMC) with threshold raising. Apriori pruning reduces candidate space. But no existing work combines B&B with multi-scale dense interval computation.
**Our Contribution**: Branch-and-Bound Dense Pruning that exploits the anti-monotonicity of dense intervals across both itemset lattice and scale hierarchy. Upper bounds on Dense Coverage Score enable early termination.

### Gap 4: No Unified Framework Bridging Parameter-Free Mining and Temporal Density
**Current State**: Parameter-free mining (Keogh & Lonardi, 2004) focuses on compression-based approaches for clustering/classification. Adaptive windowing (ADWIN) focuses on concept drift. Neither addresses the specific problem of finding temporally dense patterns without parameter tuning.
**What Exists**: Individual solutions for parameter elimination in different mining tasks, but no coherent framework for temporal density.
**Our Contribution**: A unified framework where users specify only k (number of desired patterns) and receive the top-k dense patterns with automatically determined optimal window sizes and density thresholds.

## Positioning Matrix

| Aspect | Existing Work | Our Approach |
|--------|--------------|--------------|
| Parameters | W, theta required | Only k needed |
| Scale | Single fixed W | Dyadic hierarchy W_0, 2W_0, ... |
| Ranking | Support count | Dense Coverage Score |
| Pruning | Apriori only | B&B + scale monotonicity |
| Scale selection | Manual | Automatic via ridge detection |
| Output | All patterns above theta | Top-k ranked patterns |

## Key Technical Challenges

1. **Defining a meaningful ranking criterion**: Dense Coverage Score must balance between interval length (span) and density (count/window ratio).
2. **Proving anti-monotonicity across scales**: The dyadic decomposition must preserve pruning properties.
3. **Efficient multi-scale computation**: Sharing computation across adjacent scales via incremental updates.
4. **Correctness guarantee**: The B&B algorithm must provably return the exact top-k (not approximate).
