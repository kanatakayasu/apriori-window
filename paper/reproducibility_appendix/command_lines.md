# Reproducibility: Commands

## Running All Stage A Experiments

```sh
# Generate synthetic data
python3 experiments/gen_synthetic.py

# Run Phase1 vs Traditional comparison
python3 experiments/run_phase1.py

# Analyze results
python3 experiments/analyze_results.py
```

## Running Rust Implementation

```sh
cd apriori_window_suite
cargo run --release -- phase1 data/settings.json
cargo run --release -- phase2 data/settings_phase2.json
```

## Running Tests

```sh
# Rust
cd apriori_window_suite && cargo test

# Python
python3 -m pytest apriori_window_suite/python/tests/ -v
```
