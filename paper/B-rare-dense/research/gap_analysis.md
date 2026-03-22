# Gap Analysis: Rare Dense Patterns

## Executive Summary

Existing literature addresses rare pattern mining and temporal pattern mining as **separate** problems. No existing work combines (1) global rarity conditions with (2) local temporal density conditions in a unified framework. This paper fills that gap.

## Gap Map

### Gap 1: No Temporal Dimension in Rare Pattern Mining

| Aspect | Current State | Our Contribution |
|--------|--------------|------------------|
| RP-Growth, Apriori-Rare, MFI algorithms | Mine globally rare itemsets from flat transaction databases | Add temporal sliding window to detect *when* rare patterns become locally dense |
| Output | Static set of rare itemsets | Rare itemsets + their dense intervals (temporal localization) |

**Why this matters**: A globally rare itemset {luxury_item_A, luxury_item_B} that co-occurs in 0.1% of all transactions is noise to standard frequent pattern mining. But if those co-occurrences cluster in a 2-week window (e.g., during a flash sale), this burst is highly informative. Current rare pattern miners cannot detect this.

### Gap 2: Anomaly Detection Methods Lack Pattern Structure

| Aspect | Current State | Our Contribution |
|--------|--------------|------------------|
| Isolation Forest, LOF | Detect anomalous *points* or *instances* | Detect anomalous *itemset co-occurrence patterns* over time |
| Granularity | Individual transactions/data points | Itemset-level temporal patterns |
| Interpretability | Anomaly score per point | Named itemset + time interval |

**Why this matters**: Isolation Forest can flag individual transactions as anomalous, but cannot identify that "items {A, B, C} co-occurred densely during weeks 15-17 despite being globally rare." Our approach provides structured, interpretable outputs.

### Gap 3: Anti-Monotonicity Blocks Rare Pattern Discovery in Apriori

| Aspect | Current State | Our Contribution |
|--------|--------------|------------------|
| Standard Apriori | Prunes candidates with support < threshold | Recovers candidates that are globally rare but locally dense |
| Anti-monotonicity | Used aggressively; eliminates all low-support candidates | Weak Anti-Monotonicity: preserves candidates with at least one dense interval |
| Completeness | Complete for frequent patterns only | Complete for Rare Dense Patterns (proven) |

**Why this matters**: Standard Apriori with global support threshold will *never* discover rare dense patterns because they are pruned in the first pass. Our two-phase approach with modified anti-monotonicity recovers these patterns.

### Gap 4: Burst Detection Lacks Itemset Structure

| Aspect | Current State | Our Contribution |
|--------|--------------|------------------|
| Kleinberg (2003) | Detects bursts in univariate event streams | Detects dense intervals of multi-item co-occurrence patterns |
| Input | Single event type | Multiple items forming combinatorial patterns |
| Pruning | None (single stream) | Apriori-based pruning over itemset lattice |

**Why this matters**: Kleinberg's burst detection works on individual event types. Extending it to itemset co-occurrences requires combinatorial search over the itemset lattice, which our framework handles efficiently.

### Gap 5: Dual Support Frameworks Lack Formal Guarantees

| Aspect | Current State | Our Contribution |
|--------|--------------|------------------|
| Chang & Lee (2003) | Dual support for emerging pattern detection | Formal definition of Rare Dense Pattern with completeness theorem |
| R3PStreamSW (2025) | Rare periodic patterns in streams | Different problem: periodicity vs density |
| Theoretical guarantees | Heuristic approaches | Proven Weak Anti-Monotonicity + completeness of two-phase mining |

## Research Questions

1. **RQ1**: Can we define a class of patterns that are globally rare but locally dense, and mine them completely?
2. **RQ2**: What is the correct modification of anti-monotonicity that enables efficient pruning while preserving completeness for rare dense patterns?
3. **RQ3**: How do rare dense patterns compare to patterns found by existing rare pattern miners and anomaly detectors?
4. **RQ4**: Does two-phase mining scale to large transaction databases?

## Novelty Claims

1. **Novel Problem Definition**: First formal definition of Rare Dense Patterns combining global rarity and local temporal density
2. **Weak Anti-Monotonicity**: New pruning property that generalizes classical anti-monotonicity for the rare dense setting
3. **Two-Phase Mining Algorithm**: Complete algorithm with provable guarantees for mining all rare dense patterns
4. **Empirical Validation**: First systematic evaluation comparing rare dense pattern mining against rare pattern miners, anomaly detectors, and standard frequent pattern miners
