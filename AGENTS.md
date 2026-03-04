# AGENTS.md — apriori_window

This file defines agent roles for AI-assisted development of the apriori_window project.
Compatible with Claude Code, Cursor, Copilot, and other AI coding assistants.

## Roles

### Architect
- System design and algorithm planning
- Task decomposition into modules
- Design decision documentation (docs/decisions/)
- Ensures Phase1/Phase2 design constraints are maintained

### Researcher
- Literature review and baseline evaluation
- Maintains `baselines/methods/*.md` and `baselines/research/`
- Documents comparative method properties and limitations
- Identifies gaps in `benchmarks/` definitions

### Coder
- Implements features following Python → Rust workflow
- Python prototype in `apriori_window_suite/python/`
- Rust port in `apriori_window_suite/src/`
- Must not break test baselines (see CLAUDE.md §7)
- Uses `/impl-feature` skill for structured implementation

### Experimenter
- Runs benchmarks defined in `benchmarks/suites/`
- Uses configs in `experiments/configs/`
- Records results in `experiments/registry/experiments.csv`
- Outputs to `runs/` (gitignored) and aggregates to `experiments/reports/`
- Uses `/run-experiment` skill

### Writer
- Drafts and revises paper in `paper/`
- Generates figures via `tools/scripts/gen_figs.py`
- Maintains `paper/reproducibility_appendix/`
- Uses `/write-paper` skill

## Skills

See `.agents/skills/` for available skills:
- `/impl-feature` — New algorithm feature (Python prototype → Rust)
- `/run-experiment` — Execute benchmark suite
- `/debug-test` — Debug failing tests
- `/write-paper` — Paper writing and revision
- `/git-workflow` — Commit and PR workflow

## Conventions

- Work on `dev_takayasu` branch; PRs target `main`
- Python tests: `pytest apriori_window_suite/python/tests/`
- Rust tests: `cd apriori_window_suite && cargo test`
- 1 commit per intent (prototype / port / test / doc separate)
