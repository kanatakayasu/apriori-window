# Gap Analysis: Multi-Dimensional Dense Region Mining

## Identified Gaps

### Gap 1: No Unified Framework for Multi-Dimensional Support Surfaces
**Existing work**: Spatial scan statistics (SaTScan) operate on point data with fixed window shapes. Dense subtensor mining (DenseAlert, M-Zoom) works on discrete tensors. DBSCAN clusters raw point data. Apriori-Window detects dense intervals in 1D support series.

**Gap**: No framework unifies the concept of a "support surface" -- a real-valued function S_P(t, x_1, ..., x_d) measuring pattern frequency across multiple dimensions -- and defines dense regions as its superlevel sets.

**Our contribution**: Define support surfaces formally, characterize dense regions as connected components of superlevel sets, and provide algorithms for their efficient detection.

### Gap 2: Shape-Agnostic Dense Region Detection
**Existing work**: SaTScan requires circular/elliptical windows. Dense subtensor mining finds axis-aligned blocks. DBSCAN finds arbitrary shapes but in point space, not function space.

**Gap**: No algorithm detects arbitrarily-shaped dense regions in discretized support surfaces without restricting to geometric primitives.

**Our contribution**: The sweep surface algorithm processes grid cells in dimension order, detecting connected components of the superlevel set regardless of shape.

### Gap 3: Dimension Decomposability Theory
**Existing work**: Tensor decomposition (CP, Tucker) decomposes tensors algebraically. Spatial scan statistics treat space-time as a product space but scan exhaustively.

**Gap**: No formal theory characterizes when a multi-dimensional dense region detection problem can be decomposed into lower-dimensional sub-problems without loss.

**Our contribution**: The Dimension Decomposability Theorem provides sufficient conditions for exact decomposition and bounds on approximation error when conditions are not met.

### Gap 4: Dense Region Containment (Anti-Monotonicity in Multi-D)
**Existing work**: Apriori property (if P is not frequent, no superset of P is frequent) is well-established for 1D support. No multi-dimensional analog exists for dense regions.

**Gap**: The containment relationship between dense regions of itemsets and their subsets has not been formalized in multi-dimensional settings.

**Our contribution**: The Dense Region Containment Theorem proves that dense regions of an itemset P are contained within the intersection of dense regions of all (|P|-1)-subsets, enabling Apriori-style pruning in multi-dimensional space.

### Gap 5: Scalable Multi-Dimensional Dense Region Mining
**Existing work**: SaTScan has O(N^2) complexity for spatial scans. Dense subtensor methods scale to tera-scale but only find axis-aligned blocks. 1D sweep line is O(N log N) but no multi-dimensional sweep surface analog exists for support-based density.

**Gap**: No algorithm achieves sub-quadratic complexity for arbitrary-shape dense region detection in multi-dimensional support surfaces.

**Our contribution**: The sweep surface algorithm with grid discretization achieves O(G * alpha(G)) complexity where G is the grid size and alpha is the inverse Ackermann function (from union-find), compared to O(G^2) for naive pairwise comparison.

## Positioning Matrix

| Approach | Dimensions | Shape | Pruning | Complexity | Support-Based |
|----------|-----------|-------|---------|------------|---------------|
| SaTScan | 2-3 | Circle/Ellipse | LRT | O(N^2) | No (count) |
| DenseAlert | Any | Axis-aligned block | Density bound | O(nnz) | No (entry) |
| DBSCAN | Any | Arbitrary | MinPts | O(N log N) | No (points) |
| Apriori-Window (1D) | 1 | Interval | Apriori | O(N) | Yes |
| **Ours** | **Any** | **Arbitrary** | **Containment** | **O(G alpha(G))** | **Yes** |

## Research Questions

1. **RQ1**: How can support surfaces and their dense regions be formally defined in a multi-dimensional setting?
2. **RQ2**: Under what conditions can multi-dimensional dense region detection be decomposed into lower-dimensional sub-problems?
3. **RQ3**: How does the sweep surface algorithm compare to baseline approaches in accuracy and scalability?
4. **RQ4**: Does dimension decomposition maintain detection quality in practice?
