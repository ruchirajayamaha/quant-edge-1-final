# Changelog

All notable milestone checkpoints for the Quant Edge 1.0 solo implementation are recorded incrementally in this file.

## [0.1.0] - 2026-10-31 — SOLO STEP 1 (D0 Baseline & Project Setup)

### Added
- Initialized local Git repository preserving original challenge PDFs, `initial prompt.txt`, and `antigravity-team-pack/`.
- Created installable `src`-layout package (`pyproject.toml`, `src/quantedge/`) and verified pinned Python 3.11 dependencies (`requirements.txt`).
- Froze contract schema `1.0.0` in `src/quantedge/contracts.py`:
  - Canonical universe `("SPY", "EFA", "EEM", "AGG", "GLD", "XLE", "XLK")` and `MANDATE_NAV_USD = 10_000_000.0`.
  - Typed dataclasses `DataManifest`, `DataBundle`, `PortfolioConstraints`, `StrategySpec`, `PortfolioPath`, `RiskEstimate` (with finite/unavailable invariants), `StressScenarioSpec`, `ResultBundleMetadata`, and `PipelineResultBundle`.
  - Generic `RiskForecastFn` callback protocol and frozen helper signatures `var.normal_moments` (`ddof=1`) and `es.empirical_tail_weights` (aligned worst `1 - c` probability mass with even boundary tie splitting).
- Created `config.yaml` and offline loader/validator/hasher `src/quantedge/config.py` with explicit `PROVISIONAL_*` / `PENDING_HUMAN_DECISION` governance markers.
- Added explicit `NotImplementedError` interface stubs across `data.py`, `returns.py`, `portfolio.py`, `kpis.py`, `var.py`, `es.py`, `evt.py`, `backtest.py`, `risk_budget.py`, `stress.py`, and `pipeline.py`.
- Added minimal honest Step 1 status entrypoint `app/Home.py` (displaying zero fabricated metrics), offline smoke suite `tests/test_d_setup.py`, Windows PowerShell instructions in `README.md`, incremental `AI_DISCLOSURE.md`, and checkpoint `handoff/SOLO.md`.
