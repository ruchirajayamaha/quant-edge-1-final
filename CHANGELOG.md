# Changelog

All notable milestone checkpoints for the Quant Edge 1.0 solo implementation are recorded incrementally in this file.

## [0.2.2] - 2026-10-31 — RF-only `r3_release_evidence` Upgrade

### Changed & Fixed
- **Value-versioned RF selection (`src/quantedge/returns.py`, `src/quantedge/rf_evidence.py`):** Added `select_rf_versions_asof`, which picks the most recent eligible observation and then its latest eligible version, so a late revision to an older observation cannot replace a newer quote.
- **Complete vintage evidence (`scripts/pull_rf_vintage_evidence.py`, `scripts/build_rf_release_evidence.py`, `data/reference/rf_evidence/`):** Stitched all `5,142` published DTB3 vintages across request boundaries with exact header validation, at most 12 vintages per request, throttling, and cached resume. Added archived weekly H.15 values for the sparse era and a curated event table separating documented, inferred, and unresolved cases.
- **Evidence-based availability:** Corrected documented closures, omitted Treasury releases, and Good Friday and blank-day overgeneralizations at day level. Sparse history keeps a labelled calendar fallback.
- **Snapshot lineage (`src/quantedge/data.py`, `src/quantedge/config.py`, `src/quantedge/contracts.py`, `scripts/build_data_snapshot.py`):** Removed the hard-coded `_r2_` identifier, added evidence hash pinning to dataset and cache identity, candidate builds that leave the active pointer unchanged, and `activate_snapshot`. `DataBundle` gained optional `rf_provenance` and `rf_accrual_sensitivity` fields; the schema stays `1.1.0` because the additions are optional and `r2` manifests remain valid.
- **Conversion sensitivity:** Added a labelled 91-day accrual series. `/252` remains primary.
- **Wording:** Corrected the description of `r2` from "conservative" to a schedule proxy in current documents and runtime text. Earlier audit documents are preserved as written.
- **Snapshot and tests:** Derived `qe1_20050101_20261030_r3_6c4633a7ba` from `qe1_20050101_20261030_r2_cd2904443b` without any ETF download. Prices and simple/log returns equal `r2` exactly, and all `v1`/`r2` hashes are intact. Test suite expanded to `41/41` passing tests (`tests/test_r3_rf_evidence.py`).

## [0.2.1] - 2026-10-31 — SOLO STEP 2 Bounded Data-Hardening Pass (`r2_hardened`)

### Changed & Fixed
- **Contract & config schema `1.1.0` (`src/quantedge/contracts.py`, `src/quantedge/config.py`, `config.yaml`):** Added explicit `policy_revision` and `parent_dataset_id` provenance on `DataManifest`, optional `ex_post_rf_daily` and `quarantined_prices` fields on `DataBundle`, and validated `unexpected_session_policy`, `require_requested_boundary_coverage`, `rf_alignment_policy`, `rf_decision_timezone`, `rf_decision_cutoff_time`, and `rf_release_time`.
- **RF release-cutoff causality & ex-post separation (`src/quantedge/returns.py`, `src/quantedge/data.py`):** Replaced date-only `obs_date + BDay(1)` matching with explicit UTC timestamp comparison (`available_at <= decision_time`) modelling the preceding NYSE close (`16:00:00 America/New_York`) against verified `release_timestamps` or the conservative Federal Reserve H.15 schedule (`16:15:00 America/New_York` on `expected_federal_reserve_business_days`, excluding all 11 US federal OPM holidays including Columbus Day and Veterans Day, Good Friday, special closures, and blank `DTB3` holiday dates). Persisted the contemporaneous ex-post proxy separately in `rf_daily_ex_post.parquet` and disclosed historical first-release/vintage uncertainty.
- **Requested boundary coverage guard (`src/quantedge/data.py`):** Validated first and last expected NYSE sessions against `requested_start` / `requested_end` and unclipped `calendar_sessions`, rejecting truncated history (`DataUnavailableError`) while handling weekend/holiday bounds cleanly.
- **Unexpected non-NYSE session quarantine (`src/quantedge/data.py`):** Reindexed `prices` strictly onto expected NYSE sessions (removing `.union(observed_prices.index)`), preserving unexpected raw rows in `etf_prices_raw.parquet` and `quarantined_unexpected_prices.parquet` with `action='quarantine_exclude_from_modelling_grid'` so weekend rows never enter one-session returns.
- **Cached RF index validation (`src/quantedge/data.py`):** Removed positional `rf_daily.index = simple_returns.index.copy()` overwriting and added strict `DatetimeIndex` equality validation for `rf_daily.parquet`, `rf_daily_ex_post.parquet`, and `log_returns.parquet` against `simple_returns.index`.
- **Snapshot lineage & regression tests:** Preserved audited snapshot `qe1_20050101_20261030_afb9ce5694` untouched (all 13 SHA-256 hashes verified intact), derived hardened snapshot `qe1_20050101_20261030_r2_cd2904443b` offline via `derive_snapshot_from_existing`, and expanded test suite to `21/21` passing tests (`tests/test_a_data.py`, `tests/test_d_setup.py`).

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
