# Changelog

All notable milestone checkpoints for the Quant Edge 1.0 solo implementation are recorded incrementally in this file.

## [0.2.0] - 2026-10-31 — SOLO STEP 2 (A1 Data Snapshot, Returns & Quality Diagnostics)

### Added
- Implemented `src/quantedge/returns.py`: deterministic NYSE session calendar (`expected_nyse_sessions`), uncollapsed 1-session simple/log return builder (`compute_session_returns`) with post-return incomplete-row exclusion audit (`excluded_return_rows`), past-only lagged FRED `DTB3` aligner (`align_risk_free_rate`, zero backfill), ADF stationarity diagnostics (`run_stationarity_diagnostics`), and descriptive return statistics (`compute_return_descriptive_stats`).
- Implemented `src/quantedge/data.py` and `scripts/build_data_snapshot.py`: `yfinance` `auto_adjust=True` close extractor (`extract_adjusted_closes` rejecting ambiguous raw/adjusted frames), FRED `DTB3` CSV parser preserving missing markers, reproducible quality flagger (`flag_data_quality` with safe `MAD=0` fallback and retained outliers), SHA-256-verified snapshot persistence & offline/network-failure fallback (`load_data`), and Markdown report generator.
- Built and verified frozen snapshot `qe1_20050101_20261030_afb9ce5694` (`2005-01-03` to `2026-10-30`, `5,492` price sessions, `5,491` complete return sessions across all 7 canonical ETFs and aligned `DTB3`) and froze `frozen_end_date: "2026-10-30"` in `config.yaml`.
- Added Step 2 synthetic and snapshot-integrity unit tests (`tests/test_a_data.py`, 9 tests; total suite 17/17 passing) and methodology/limitations section `docs/sections/a_data_quality.md`.

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
