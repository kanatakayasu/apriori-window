# Paper A: Anti-Dense Intervals and Contrast Dense Patterns

**Title**: Anti-Dense Intervals and Contrast Dense Patterns: Symmetric Extensions of Dense Interval Mining

**Venue Target**: DSAA 2026 / ICDM 2026

## Status Dashboard

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Research | DONE | 25 papers surveyed, gap analysis complete |
| Phase 2: Formalization | DONE | 4 definitions, 3 theorems, complexity analysis |
| Phase 3: Implementation | DONE | Python prototype, tests passing |
| Phase 4: Experiments | DONE | E1-E5 executed, figures generated |
| Phase 5: Paper Writing | DONE | 8+ pages, full manuscript |
| Phase 6: GitHub Pages | DONE | Landing page created |

## Directory Structure

```
paper/A-anti-dense-contrast/
  README.md                    <- This file
  PENDING_QUESTIONS.md         <- Open questions
  research/
    gap_analysis.md            <- Literature survey & gap analysis
  implementation/
    python/
      anti_dense_interval.py   <- Anti-dense interval detection
      contrast_dense.py        <- Contrast dense pattern classification
      tests/
        test_anti_dense.py     <- Unit tests for anti-dense
        test_contrast_dense.py <- Unit tests for contrast
  experiments/
    configs/                   <- Experiment configurations
    results/                   <- Raw results
    figures/                   <- Generated figures
    analysis.md                <- Experiment analysis
  manuscript/
    refs.bib                   <- Bibliography
    sec/                       <- LaTeX sections
    fig/                       <- Figures
    alg/                       <- Algorithm pseudocode
  pages/
    index.html                 <- GitHub Pages landing page
```

## Quick Commands

```sh
# Run tests
python3 -m pytest paper/A-anti-dense-contrast/implementation/python/tests/ -v

# Run experiments
python3 paper/A-anti-dense-contrast/experiments/run_all.py
```
