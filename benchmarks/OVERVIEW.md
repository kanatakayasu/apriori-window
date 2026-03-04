# Benchmarks

Experiment suite definitions, dataset metadata, metric specifications, and evaluation protocols.

## Structure

- `suites/`: Experiment suite YAML definitions (main, ablation, scalability)
- `datasets/`: Dataset metadata and provenance (YAML per dataset)
- `metrics/`: Metric definitions and computation code
- `protocol/`: I/O spec, timing rules, seed conventions

## Usage

Suite YAML files declare experiment parameters. The actual execution is handled by
`experiments/run_stage_A.py` and related scripts, which read these definitions.

## Suites

| Suite | Description |
|-------|-------------|
| `main.yaml` | Primary experiments: A1-P, A2-P, A3-P |
| `ablation.yaml` | Ablation study experiments |
| `scalability.yaml` | Scalability benchmarks (A3-P) |
