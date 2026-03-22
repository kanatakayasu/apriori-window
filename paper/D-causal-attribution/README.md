# Paper D: From Association to Causation

**Title**: From Association to Causation: Synthetic Control for Dense Pattern Attribution

**Venue**: KDD 2027 / AAAI 2027

## Overview

Applies the Synthetic Control Method (Abadie+ 2010) to pattern support time series for causal attribution of support changes to external events.

## Key Concepts

- **Donor Pool**: Item-disjoint patterns as controls
- **Counterfactual Support Trajectory**: Weighted combination of control supports
- **Causal Effect on Support**: Observed minus counterfactual
- **Placebo Tests**: Permutation-based inference

## Structure

```
paper/D-causal-attribution/
  implementation/python/         # SC-DenseAttrib implementation (22 tests)
  experiments/                   # E1-E5 experiments with figures
  manuscript/                    # LaTeX manuscript (compiles to 5 pages)
  research/                      # Literature review and formalization
  pages/                         # GitHub Pages LP
```

## Quick Start

```bash
# Run tests (22 passed)
python3 -m pytest paper/D-causal-attribution/implementation/python/tests/ -v

# Run experiments
python3 paper/D-causal-attribution/experiments/run_all.py

# Compile paper
cd paper/D-causal-attribution/manuscript && latexmk -pdf main.tex
```
