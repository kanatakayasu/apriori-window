# Paper B: Rare Dense Patterns

**Title**: Rare Dense Patterns: Mining Locally Dense but Globally Rare Itemsets
**Venue**: KDD 2026 / SDM 2026
**Branch**: `paper/B-rare-dense`

## Status Dashboard

| Phase | Status | Deliverables |
|-------|--------|-------------|
| Phase 1: Research | DONE | literature_survey.md, gap_analysis.md, refs.bib |
| Phase 2: Formalization | DONE | sec/03_problem_definition.tex |
| Phase 3: Implementation | DONE | rare_dense_miner.py, tests (10 passed) |
| Phase 4: Experiments | DONE | E1-E4 results, figures, analysis.md |
| Phase 5: Paper Writing | DONE | Full manuscript (8+ pages) |
| Phase 6: GitHub Pages | DONE | pages/index.html |

## Key Concepts

- **Rare Dense Pattern (RDP)**: An itemset that is globally rare (support < max_sup) but has at least one temporally dense interval (local support >= theta within window W)
- **Global Rarity Condition**: Overall support across all transactions is below a maximum threshold
- **Local Density Condition**: Within at least one sliding window position, co-occurrence count meets minimum threshold
- **Two-Phase Mining**: Phase 1 discovers locally dense patterns (low threshold); Phase 2 filters to retain only globally rare ones

## Directory Structure

```
paper/B-rare-dense/
  README.md                  <- This file
  PENDING_QUESTIONS.md       <- Open questions
  research/
    literature_survey.md     <- 27 papers surveyed
    gap_analysis.md          <- 5 gaps identified
  implementation/
    python/
      rare_dense_miner.py    <- Core algorithm
      tests/
        test_rare_dense.py   <- 10 tests
  experiments/
    configs/                 <- Experiment configurations
    results/                 <- Raw results (JSON)
    figures/                 <- Generated plots
    analysis.md              <- Results analysis
  manuscript/
    main.tex                 <- Paper entry point
    refs.bib                 <- Bibliography (27 entries)
    sec/                     <- Section files
    alg/                     <- Algorithm pseudocode
    fig/                     <- Figures
  pages/
    index.html               <- Landing page
```
