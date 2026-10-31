# QuantEdge 1.0 — Step 7 (C2/C3) EVT POT-GPD Tail Preview

**Scope:** DEVELOPMENT PERIOD ONLY (through `2016-12-30`).
Unconditional Peaks-Over-Threshold Generalized Pareto Distribution (POT-GPD) tail risk modeling
and moving-block bootstrap uncertainty for the terminal-development `min_variance` portfolio exposure.

- **Dataset ID:** `qe1_20050101_20261030_r3_6c4633a7ba`
- **Config Hash:** `587ddbe363589fb6956c23c5fe8b2b544bac81d9224a0b4bb59f60f5fbc0a017`
- **Portfolio NAV:** `USD 10,000,000.00`
- **Primary Threshold Policy:** Empirical `q = 0.95` loss quantile, `min_exceedances = 50` (provisional; human approval PENDING).
- **Uncertainty Policy:** Moving-block bootstrap (`block_length = 10`, `n_replications = 100`, `seed = 202602`).
- **Authority File:** `step7_recorded_results.json`

## Deliverables
- `tables/table_01_risk_model_comparison.{csv,md}`: Matched 90%, 95%, 99% VaR and ES across Historical, Parametric Normal, Monte Carlo, and EVT (POT and Hybrid).
- `tables/table_02_threshold_diagnostics.{csv,md}`: Threshold grid diagnostics (MRL, xi, beta, modified scale beta - xi*u).
- `tables/table_03_bootstrap_uncertainty.{csv,md}`: 95% moving-block bootstrap confidence intervals.
- `tables/table_04_qq_pp_*.csv`: Empirical vs fitted GPD quantiles and probabilities.
- `figures/figure_01_threshold_stability_and_mrl.{png,svg}`: MRL and parameter stability plots.
- `figures/figure_02_gpd_tail_qq_pp_diagnostics.{png,svg}`: QQ and PP calibration plots.
- `figures/figure_03_risk_model_and_uncertainty_comparison.{png,svg}`: Visual risk and bootstrap error comparison.
