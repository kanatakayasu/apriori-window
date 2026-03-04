# Timing Protocol

## Rules
1. Measure wall-clock time using Python's `time.perf_counter()`
2. Warm-up: run once before measurement (for JIT/cache effects)
3. Report median of 3 runs for single-process methods
4. Exclude I/O time from core algorithm timing where possible

## Metrics Captured
- `phase1_core_ms`: Phase1 find_dense_itemsets only
- `trad_flatten_ms`: Traditional method flatten step
- `trad_core_ms`: Traditional find_dense_itemsets only
- `trad_total_ms`: flatten + core

## Environment
- Machine spec stored in runs/*/meta.json
- CPU: single-threaded unless noted
- Memory: no swap
