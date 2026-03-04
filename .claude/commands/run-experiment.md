Run a benchmark experiment suite for the apriori_window project.

Steps:
1. Check experiments/configs/ for available experiment configs
2. Ask which experiment to run (exp001, exp010, exp020, or custom)
3. Run the appropriate script from experiments/
4. Save results to experiments/results/ and update experiments/registry/experiments.csv
5. Report summary statistics (precision, recall, F1, timing)

Available experiments:
- exp001: A1-P (λ_baskets sweep)
- exp010: A2-P (G sweep)
- exp020: A3-P (scalability)
