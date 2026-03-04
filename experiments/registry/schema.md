# Experiment Registry Schema

## experiments.csv columns
| Column | Description |
|--------|-------------|
| exp_id | Experiment ID (exp###) |
| suite | Suite name from benchmarks/suites/ |
| config | Config YAML path |
| commit | Git commit hash at run time |
| dataset | Dataset name |
| run_dir | Path to runs/ output directory |
| status | pending / running / completed / failed |
| notes | Free text notes |
| created_at | ISO 8601 timestamp |
