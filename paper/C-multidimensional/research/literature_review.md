# Literature Review: Multi-Dimensional Dense Region Mining

## 1. Spatial Scan Statistics

### 1.1 Kulldorff's Spatial Scan Statistic
- **Kulldorff (1997)**: Foundational work extending scan statistics to multidimensional point processes with variable window sizes. Uses circular/elliptical scanning windows with likelihood ratio test. Limitation: fixed geometric shapes cannot capture arbitrary dense regions.
- **Kulldorff (2001)**: Space-time extension using cylindrical windows (circular space x temporal height). Enables prospective surveillance.
- **SaTScan Software**: Implementation supporting Poisson, Bernoulli, and space-time permutation models. Widely used in epidemiology.

### 1.2 Scalable Scan Statistics
- **Matheny & Phillips (2016)**: Scalable spatial scan statistics through sampling. Addresses computational bottleneck of exhaustive window enumeration.
- **Neill (2012)**: Fast subset scan for multivariate event detection. Reduces search space by exploiting linear-time subset scanning property.

### 1.3 Limitations of Scan Statistics
- Restricted to pre-defined window shapes (circular, elliptical, cylindrical)
- Cannot detect irregularly shaped dense regions
- Multiple testing burden grows with number of windows evaluated
- No connection to itemset support or pattern mining

## 2. Dense Subtensor Mining

### 2.1 Core Algorithms
- **DenseAlert (Shin et al., KDD 2017)**: Incremental dense subtensor detection in tensor streams. Maintains density guarantee while processing updates up to 1M times faster than batch algorithms.
- **M-Zoom (Shin et al., TKDD 2018)**: Fast, accurate, flexible algorithms for dense subtensor mining with multiple density measures. Provides lower bound guarantees.
- **D-Cube (Shin et al., VLDB 2017)**: Disk-based dense subtensor detection for tera-scale data. Distributed computation support.

### 2.2 Applications
- Fraud detection (retweet boosting, fake reviews)
- Network attack detection
- Wikipedia vandalism detection
- Anomaly detection in multi-aspect data

### 2.3 Relevance to Our Work
- Dense subtensor = dense sub-block in multi-dimensional array
- Our "dense region" generalizes beyond axis-aligned blocks
- Connection: support surface as a tensor, dense region as superlevel set

## 3. Density-Based Clustering

### 3.1 DBSCAN Family
- **DBSCAN (Ester et al., 1996)**: Density-based spatial clustering. Core concept: eps-neighborhood density. Limitation: single global density threshold.
- **OPTICS (Ankerst et al., 1999)**: Overcomes DBSCAN's fixed-density limitation with reachability ordering. Extracts clusters of varying density.
- **HDBSCAN (Campello et al., 2013)**: Hierarchical extension combining DBSCAN with hierarchical clustering.

### 3.2 Connection to Dense Regions
- DBSCAN clusters = connected dense regions in point space
- Our approach: dense regions in support surface (function space, not point space)
- Key difference: we work on a discretized function (support surface) rather than raw data points

## 4. Co-location Pattern Mining

### 4.1 Foundational Work
- **Shekhar & Huang (2001)**: First formalization of spatial co-location patterns using participation index with anti-monotone property. Apriori-based framework.
- **Yoo & Shekhar (2006)**: Join-based approach for co-location pattern mining, improving efficiency.

### 4.2 Recent Extensions
- **Fuzzy grid cliques (Wang et al., 2022)**: Grid-based discretization for efficient co-location mining.
- **Graph-based methods (2024)**: Integrating geospatial analysis with logical reasoning via graph growth.
- **Hausdorff distance alignment (2024)**: Voronoi tessellation for data-adaptive spatial partitioning.

### 4.3 Relevance
- Co-location patterns identify spatial feature associations
- Our work extends to temporal-spatial support surfaces where "co-location" becomes "co-dense-region"

## 5. Topological Data Analysis & Level Sets

### 5.1 Persistent Homology
- **Edelsbrunner & Harer (2010)**: Computational topology foundations. Superlevel set filtrations capture topological features of functions.
- **Persistence diagrams**: Encode birth/death of topological features across threshold levels.

### 5.2 Level Set Methods
- Superlevel sets {x : f(x) >= theta} naturally define dense regions
- Connected components of superlevel sets = dense regions at threshold theta
- Persistence quantifies robustness of dense regions

### 5.3 Connection to Our Framework
- Support surface S_P(t, x) is a real-valued function on time x space
- Dense regions = connected components of superlevel set {(t,x) : S_P(t,x) >= theta}
- This provides a rigorous topological characterization

## 6. Sweep Line / Sweep Surface Algorithms

### 6.1 Classical Sweep Line
- **Shamos & Hoey (1976)**: Breakthrough O(N log N) algorithm for line segment intersection.
- **Bentley-Ottmann (1979)**: Optimal sweep for segment intersections.
- **Fortune (1987)**: Voronoi diagram construction via sweep line.

### 6.2 Higher-Dimensional Extensions
- Sweep plane in 3D, sweep hyperplane in d dimensions
- Event-driven processing: maintain active structure, process events at sweep positions
- Applicable to our grid-based support surface computation

## 7. Multidimensional Frequent Pattern Mining

### 7.1 Temporal Association Rules
- **Lee et al., 2017**: Mining temporal association rules with frequent itemset trees. Incorporates temporal relations between items.
- **Han et al., textbook**: Advanced pattern mining chapter covering multidimensional and multilevel patterns.

### 7.2 Spatial Frequent Patterns
- **Trajectory pattern mining (Giannotti et al., 2007)**: Frequent trajectory patterns in spatial-temporal databases.
- **Multidimensional organizational networks (2019)**: Frequent pattern mining across multiple network dimensions.

## 8. Related Interval/Region Detection

### 8.1 Our Prior Work (Apriori-Window)
- Dense interval detection in 1D (temporal) support series
- Window-based support counting with Apriori pruning
- Stack-case handling for overlapping windows

### 8.2 Gap: Extension to Multiple Dimensions
- 1D intervals -> 2D/nD regions
- Window becomes a hypercube or more general shape
- Sweep line -> sweep surface for efficient computation
