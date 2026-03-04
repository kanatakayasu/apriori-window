# Metric Definitions

## SPR (Set Pattern Recovery)
Measures how well Phase1 recovers the ground-truth itemset patterns compared to the traditional method.

- **True Positive (TP)**: Pattern found by method that matches a GT pattern
- **False Positive (FP)**: Pattern found by method not in GT
- **False Negative (FN)**: GT pattern not found by method

**Precision** = TP / (TP + FP)
**Recall** = TP / (TP + FN)
**F1** = 2 * Precision * Recall / (Precision + Recall)

## Timing Metrics
- `phase1_core_ms`: find_dense_itemsets only (Phase 1)
- `trad_flatten_ms`: flatten_transactions preprocessing (traditional)
- `trad_core_ms`: find_dense_itemsets only (traditional)
- `trad_total_ms`: trad_flatten_ms + trad_core_ms
