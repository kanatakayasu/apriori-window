# Seed Conventions

## Synthetic Data Generation
- Seeds: 0, 1, 2, 3, 4 (5 seeds for A1/A2; 0,1,2 for A3)
- Seed controls: numpy.random.default_rng(seed)
- Same seed → identical dataset

## Experiment Registry
- Each run records the seed in runs/*/meta.json
- Aggregate results use all seeds (median ± std)
