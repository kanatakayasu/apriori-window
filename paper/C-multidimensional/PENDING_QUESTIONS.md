# Pending Questions - Paper C (Multi-Dimensional Dense Region Mining)

## Open Questions

1. **Real dataset availability**: The spec mentions "store-location Dunnhumby or epidemiological data" for E4. Dunnhumby data exists in `dataset/dunnhumby/` but may not have spatial coordinates. If spatial data is unavailable, E4 will use synthetic spatiotemporal data with realistic parameters instead.

2. **Target venue format**: KDD 2027 vs ICDM 2026 have different page limits (9 vs 8 pages). Currently targeting 8+ pages which satisfies both.

3. **Rust port scope**: The spec says implementation is Python-only in `paper/C-multidimensional/implementation/python/`. No Rust port is planned for this paper branch.
