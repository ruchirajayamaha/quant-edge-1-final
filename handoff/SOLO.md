# Quant Edge 1.0 — Solo Checkpoint (`handoff/SOLO.md`)

- **Workflow mode and branch:** Single-developer solo mode (`SOLO OVERRIDE` active; single checkout on branch `main`; no parallel clones/branches)
- **Milestone commit history (`main`):**
  - Step 1 (`D0` setup): `8e21cafedab6f9c07b77f1445c7c49f19b6ee01e` (`8e21caf`)
  - Step 2 (`A1` initial snapshot & quality): `8882ed153dfa5f97fd361fce5514a2afa53cd9ea` (`8882ed1`)
  - Step 2 bounded data-hardening pass (`r2_hardened`, `audit/step2_review/` remediation): recorded in current Step 2 hardening commit on `main`
- **Contract / schema version:** `1.1.0` (`CONTRACT_SCHEMA_VERSION = "1.1.0"`, package `quantedge==0.1.0`; frozen D0 analytical callback/helper signatures preserved; coordinated `DataManifest` / `DataBundle` / `DataConfig` provenance & policy fields added)
- **Completed steps / milestones:**
  - **SOLO STEP 1 — Project Setup** (`04_D_LEAD_APP.txt` milestone `D0`)
  - **SOLO STEP 2 — Data + data-quality checks** (`01_A_DATA_VALIDATION.txt` milestone `A1`)
  - **SOLO STEP 2 Bounded Data-Hardening Pass (`r2_hardened`)** (`audit/step2_review/ANTIGRAVITY_FIX_PROMPT.txt`)
- **Next bounded task:** **SOLO STEP 3 — Portfolio construction** (`02_B_PORTFOLIO_DECISIONS.txt` milestone `B1`)
- **Active hardened dataset ID / preserved audited dataset ID / bounds / manifest locations:**
  - **Active hardened `dataset_id` (`r2_hardened`, schema `1.1.0`):** `qe1_20050101_20261030_r2_cd2904443b` (derived offline at `2026-10-31T07:32:17Z` from `parent_dataset_id = "qe1_20050101_20261030_afb9ce5694"` without ETF redownload)
    - Active pointer: `data/processed/active_snapshot.json` -> `qe1_20050101_20261030_r2_cd2904443b/manifest.json`
    - Active manifest: `data/processed/qe1_20050101_20261030_r2_cd2904443b/manifest.json` (`15` SHA-256-verified files)
    - Active raw directory: `data/raw/qe1_20050101_20261030_r2_cd2904443b/` (`etf_prices_raw.parquet`, `fred_dtb3_raw.parquet`)
    - Active processed & report directory: `data/processed/qe1_20050101_20261030_r2_cd2904443b/` (`prices.parquet`, `quarantined_unexpected_prices.parquet`, `simple_returns.parquet`, `log_returns.parquet`, `rf_daily.parquet`, `rf_daily_ex_post.parquet`, `quality_flags.parquet`, `excluded_return_rows.parquet`, `adf_stationarity.csv`, `descriptive_stats_simple.csv`, `descriptive_stats_log.csv`, `log_return_correlations.csv`, `quality_report.md`)
  - **Preserved audited baseline `dataset_id` (`v1`, schema `1.0.0`):** `qe1_20050101_20261030_afb9ce5694` (retrieved `2026-10-31T06:41:10Z`; preserved untouched in `data/raw/qe1_20050101_20261030_afb9ce5694/` and `data/processed/qe1_20050101_20261030_afb9ce5694/` with all `13` SHA-256 hashes verified intact against `audit/step2_review/snapshot_facts.json`; isolated by schema/policy cache matching so `1.0.0` is never loaded under `1.1.0`)
  - Requested bounds: `2005-01-01` to frozen end date `2026-10-30`
  - Actual ETF price session bounds: `2005-01-03` to `2026-10-30` (`5,492` expected NYSE trading sessions across `SPY, EFA, EEM, AGG, GLD, XLE, XLK`; `0` leading, `0` trailing, and `0` interior missing expected sessions; `0` quarantined unexpected non-NYSE sessions)
  - Complete 1-session simple/log return bounds: `2005-01-04` to `2026-10-30` (`5,491` uninterrupted 1-session intervals)
  - Raw FRED `DTB3` preserved bounds: `2004-11-17` to `2026-10-29` (`5,727` weekday observations, `235` US bond-market holiday blank markers preserved; `5,491` valid forward-decision `rf_daily` values and `5,491` valid separate `rf_daily_ex_post` values with `0` missing rows and `0` backfill; forward-decision and ex-post series differ on `4,354` of `5,491` sessions)
- **Config hash / seeds / result bundle IDs:**
  - `config_hash` (SHA-256 of canonicalized `config.yaml` at schema `1.1.0`): `41eec42fd85616539a89edbe646a60529cfe4c1ab436b5dcb7c1dd732bb48ce4` (prior `1.0.0` hash was `fcd3d8fc7e9f8514465f52d73fccd48b705c82c9cc4fc7b5b389b9fe4afbe0e6`)
  - Seeds (`config.yaml`): `global_seed=20261031`, `monte_carlo=202601`, `evt_bootstrap=202602`, `backtest=202603`
  - Result bundle IDs: `NONE` (full pipeline scheduled for Step 9)

---

## Step 2 Summary — Audit Hardening Fixes, Missing Data, Quality Flags & Stationarity

1. **Four targeted Step 2 audit fixes (`r2_hardened`):**
   - **Finding 1 — RF release-cutoff availability & ex-post separation:** Replaced date-only `obs_date + BDay(1)` matching with explicit UTC timestamp comparison (`available_at <= decision_time`) in `align_risk_free_rate`. Return session `t` uses decision cutoff `preceding NYSE session close` (`16:00:00 America/New_York`). Unless verified `release_timestamps` are provided, `DTB3` observation `d` is conservatively assigned `16:15:00 America/New_York` on the next Federal Reserve H.15 publication business day (`expected_federal_reserve_business_days`, skipping all 11 US federal OPM holidays including Columbus Day and Veterans Day, Good Friday, documented special closures, and raw blank `DTB3` holiday dates). Because `16:15 ET > 16:00 ET`, observations posted on decision day `t_{-1}` at `16:15 ET` are excluded at `t_{-1}` close (e.g., on `2026-10-30`, `rf_daily` uses `2026-10-27` `4.05%` rather than `2026-10-28` `4.01%` or `2026-10-29` `4.00%`). Contemporaneous ex-post `DTB3` (`obs_date <= t`) is persisted separately in `rf_daily_ex_post.parquet`, and historical first-release/ALFRED vintage uncertainty is explicitly disclosed.
   - **Finding 2 — Requested boundary coverage validation:** `build_session_price_grid` validates first and last expected NYSE sessions against `requested_start` / `requested_end` and never clips an explicit `calendar_sessions` back to observed endpoints. Weekend and NYSE-holiday request bounds pass cleanly when expected NYSE sessions are covered, whereas truncated downloads or missing boundary tickers raise `DataUnavailableError`.
   - **Finding 3 — Unexpected non-NYSE session quarantine:** Removed `.union(observed_prices.index)` so unexpected vendor weekend/holiday dates never enter `prices` or contaminate one-session returns; unexpected rows remain preserved in `etf_prices_raw.parquet` and `quarantined_unexpected_prices.parquet` with `rule='unexpected_non_nyse_session'` and `action='quarantine_exclude_from_modelling_grid'` (or raise `ValueError` under `unexpected_session_policy='error'`).
   - **Finding 4 — Cached RF logical index validation:** Removed positional `rf_daily.index = simple_returns.index.copy()` overwriting in `_try_load_verified_cache` and added `_validate_cached_bundle_tables`, verifying `DatetimeIndex` equality of `rf_daily.parquet`, `rf_daily_ex_post.parquet`, and `log_returns.parquet` against `simple_returns.index` even when file SHA-256 hashes match.
2. **NYSE calendar & missing-data accounting (separate from retained outlier flags):**
   - Expected NYSE sessions in `[2005-01-01, 2026-10-30]` (`[2005-01-03, 2026-10-30]`): `5,492`; leading/trailing/interior missing expected sessions: `0 / 0 / 0`; quarantined unexpected non-NYSE observed dates: `0`.
   - Missing ETF price cells `(date, ticker)`: `0` across all 7 tickers; initial anchor row (`2005-01-03`): `1`; post-anchor excluded return rows: `0` (`uninterrupted_return_sessions = True`).
   - Raw FRED `DTB3` holiday blank rows: `235` preserved in `fred_dtb3_raw.parquet`; aligned `rf_daily` and `rf_daily_ex_post` missing rows on return dates: `0`.
3. **Retained quality flags (`quality_flags.parquet`, `307` total rows, all `action='retain'`):**
   - `stale_flat_return_run` (`>= 3` consecutive zero simple returns): `0`
   - `large_negative_return` (`simple_return <= -0.05`): `188` across 7 ETFs (`EEM: 51, XLE: 51, EFA: 31, XLK: 23, SPY: 18, GLD: 13, AGG: 1`; worst single-day drop `XLE -20.14%` on `2020-03-09`)
   - `robust_mad_jump` (`|r - median| / (1.4826 * MAD) > 8.0` with safe `MAD=0` fallback): `101` across 7 ETFs (`SPY: 23, EFA: 18, XLE: 16, EEM: 15, AGG: 13, XLK: 10, GLD: 6`)
   - `candidate_structural_break` (causal trailing 63d vs prior non-overlapping 252d log-return vol ratio `>= 2.5`, 63d cooldown; heuristic flag, not proof): `18` across 6 ETFs (`SPY: 5, EEM: 3, XLE: 3, XLK: 3, AGG: 2, EFA: 2, GLD: 0`)
4. **ADF stationarity on log returns (`adf_stationarity.csv`):**
   - All 7 ETFs reject the unit-root null at 1% and 5% (`SPY -16.66`, `EFA -16.19`, `EEM -16.20`, `AGG -15.79`, `GLD -75.11`, `XLE -14.42`, `XLK -18.42`; all `p <= 7.86e-27`), documented with the explicit caveat that `I(0)` stationarity does **not** imply i.i.d. returns or constant conditional volatility (excess kurtosis ranges from `6.55` in `GLD` to `55.33` in `AGG`).

---

## Implemented vs. Remaining Stub Public APIs

- **Implemented (Steps 1–2 + `r2` Hardening):**
  - `quantedge.config.{load_config, compute_config_hash, list_provisional_items}`
  - `quantedge.data.{load_data, derive_snapshot_from_existing, extract_adjusted_closes, parse_fred_dtb3_csv, build_session_price_grid, flag_data_quality, generate_quality_report_markdown, DataUnavailableError}`
  - `quantedge.returns.{expected_nyse_sessions, expected_federal_reserve_business_days, compute_session_returns, align_risk_free_rate, run_stationarity_diagnostics, compute_return_descriptive_stats}`
- **Remaining `NotImplementedError` stubs (Steps 3–9):**
  - `quantedge.portfolio.{build_portfolio_path, construct_weights}` (Step 3 / `B1`)
  - `quantedge.kpis.compute_kpis` (Step 4 / `A2`)
  - `quantedge.var.{normal_moments, estimate_risk, get_risk_forecaster}` (Step 5 / `C1`)
  - `quantedge.es.empirical_tail_weights` (Step 5 / `C1`)
  - `quantedge.backtest.{rolling_backtest, coverage_tests, basel_traffic_light}` (Step 6 / `A3`)
  - `quantedge.evt.{estimate_evt_pot, evt_threshold_diagnostics}` (Step 7 / `C2-C3`)
  - `quantedge.risk_budget.{risk_contributions, compare_feasible_allocations}` (Step 8 / `B2`)
  - `quantedge.stress.run_stress_tests` (Step 8 / `B3`)
  - `quantedge.pipeline.run_pipeline` (Step 9 / `D1-D2`)

---

## Decisions Still Provisional (Awaiting Human Team Review & Sign-Off)

1. `mandate.investment_horizon` (`PROVISIONAL_TEAM_INPUT_REQUIRED`)
2. `mandate.return_target` (`PROVISIONAL_TEAM_INPUT_REQUIRED`, `null` nominal/spending/inflation targets)
3. `mandate.final_recommendation` (`PENDING_HUMAN_DECISION`, `decision: null`)
4. `chronology` (`PROVISIONAL_FROZEN_BEFORE_EVALUATION`: dev `2005-01-01..2016-12-30`, selection `2017-01-03..2020-12-31`, evaluation `2021-01-04..2026-10-30`; must stay frozen before inspecting Step 3/4 performance!)
5. `portfolio.illustrative_weights` (`ILLUSTRATIVE_ONLY_NOT_A_RECOMMENDATION`, `provisional: true`)
6. `portfolio.constraints` (`PROVISIONAL_TEAM_INPUT_REQUIRED`: max 40% per ETF, max 35% total equities -> forces `AGG >= 25%` and `GLD >= 25%`)
7. `portfolio.risk_limits` (`PROVISIONAL_TEAM_INPUT_REQUIRED`, `null`)
8. `stress.hypothetical_scenario` (`PROVISIONAL_TEAM_INPUT_REQUIRED`, 7-ETF shock vector & crisis window choices)
9. Implementation defaults: `dashboard_risk_window_days: 1260`, `backtest_window_days: 500`, `transaction_cost_bps_one_way: 5.0`, `DTB3` `(rate_pct / 100.0) / 252` under `h15_schedule_1615_ny_before_prev_nyse_close_1600_ny` (`16:15 ET` H.15 release on Federal Reserve business days vs `16:00 ET` preceding NYSE close).

---

## Tests & Checks Actually Run (Step 2 Hardening Pass, Python `3.11.16` `.venv`)

1. `.\.venv\Scripts\python.exe scripts/build_data_snapshot.py --derive-from qe1_20050101_20261030_afb9ce5694` -> Exit `0`; verified all `13` SHA-256 hashes of preserved `qe1_20050101_20261030_afb9ce5694` and derived hardened snapshot `qe1_20050101_20261030_r2_cd2904443b` offline (`15` SHA-256-hashed files, `5,492` price sessions, `5,491` complete return & aligned RF sessions, `4,354` sessions where forward-decision RF differs from ex-post RF).
2. `.\.venv\Scripts\pytest.exe -v` -> **`21 passed in 3.45s`** (`0` failures, `0` warnings; also verified with `--basetemp tmp/pytest_sandbox_check` -> `21 passed in 3.32s`):
   - `tests/test_a_data.py` (13 passed): all original 9 tests plus 4 new hardening regression suites covering (a) `16:15 ET > 16:00 ET` forecast-origin cutoff, Columbus Day & OPM Friday Veterans Day Federal Reserve closures, verified `release_timestamps` before/after close, and `forward_decision` vs `ex_post` separation; (b) start/end boundary truncation & missing boundary ticker rejection + weekend/holiday bound handling + unclipped `calendar_sessions`; (c) unexpected Saturday row quarantine (`quarantined_unexpected_prices.parquet`, `quality_flags`) and exclusion from `prices`/`simple_returns` (`Mon/Fri - 1` uncontaminated) + `unexpected_session_policy='error'`; (d) same-length shifted `DatetimeIndex` and `RangeIndex` `rf_daily.parquet` rejection with valid recomputed SHA-256 manifest hashes; and (e) active `r2` offline verification, bit-for-bit preservation of all 13 `qe1_20050101_20261030_afb9ce5694` SHA-256 hashes, and `1.0.0` vs `1.1.0` cache policy isolation.
   - `tests/test_d_setup.py` (8 passed): schema `1.1.0`, AST Streamlit-isolation check across all 14 `src/quantedge/*.py` modules, config determinism (`41eec42fd85616539a89edbe646a60529cfe4c1ab436b5dcb7c1dd732bb48ce4`), provisional items, malformed config rejection, `RiskEstimate` invariants, frozen helper signatures, and `NotImplementedError` across all 16 remaining Step 3–9 stubs.

---

## Remaining Limitations, Blockers & Documentation Paths

- **Real blockers:** None.
- **Remaining disclosed limitations:**
  1. Historical first-release timestamps and ALFRED vintage revisions for `DTB3` were **not** individually verified across 2004–2026; `rf_daily` uses a conservative Federal Reserve H.15 publication schedule proxy (`16:15 America/New_York` on US Federal Reserve business days vs `16:00 America/New_York` preceding NYSE close), and `(rate_pct / 100.0) / 252` remains an approximate trading-day proxy for a 360-day bank-discount T-bill quote.
  2. All 7 ETFs share a synchronous `16:00 America/New_York` US exchange close, whereas the underlying foreign cash markets of `EFA` and `EEM` close earlier in local time.
  3. Per-asset log-return ADF rejection (`I(0)`) does not imply i.i.d. returns or constant conditional volatility; stationarity of the *actual modelled fixed-weight portfolio return series* will be tested separately in Step 4.
- **Methodology / limitations / audit / AI-log paths:** `docs/sections/a_data_quality.md`, `data/processed/qe1_20050101_20261030_r2_cd2904443b/quality_report.md`, `audit/step2_review/STEP2_DATA_AUDIT.md` (preserved untouched), `AI_DISCLOSURE.md`, `CHANGELOG.md`.
- **Human validation:** **PENDING** (AI review/audits and automated `pytest` runs do not count as completed independent human validation).

---

## AI Log Entries

| Step | Tool / model if known | Purpose | Generated or materially changed components | Checks actually performed by AI | Human validation performed/status |
|---|---|---|---|---|---|
| SOLO STEP 1 | Google Antigravity coding assistant | D0 baseline setup, frozen contracts, config, stubs, Python 3.11 `.venv`, PowerShell docs, setup tests | `.gitignore`, `pyproject.toml`, `requirements.txt`, `config.yaml`, `src/quantedge/*.py`, `app/Home.py`, `tests/test_d_setup.py`, `README.md`, `AI_DISCLOSURE.md`, `CHANGELOG.md` | `pip check`, `pytest -v` (8/8), runtime wheel import check, `AppTest` smoke test | **PENDING** |
| SOLO STEP 2 | Google Antigravity coding assistant | A1 data snapshot (`yfinance` + FRED `DTB3`), NYSE session grid, 1-session simple/log returns, lag-1 RF alignment, `MAD=0`-safe quality flags, ADF/stats/correlation outputs, tests & docs | `src/quantedge/returns.py`, `src/quantedge/data.py`, `scripts/build_data_snapshot.py`, `config.yaml`, `tests/test_a_data.py`, `tests/test_d_setup.py`, `docs/sections/a_data_quality.md`, `data/{raw,processed}/qe1_20050101_20261030_afb9ce5694/*` | `scripts/build_data_snapshot.py --refresh`, offline SHA-256 reload check, `pytest -v` (17/17 passed, 0 warnings) | **PENDING** |
| SOLO STEP 2 Hardening Pass | External Step 2 audit (`audit/step2_review/*`) + Google Antigravity coding assistant | Targeted remediation of 4 Step 2 audit findings (RF decision-cutoff vs ex-post separation & Fed holiday calendar, requested boundary truncation guard, unexpected weekend session quarantine, cached RF logical index check) & offline `r2` snapshot derivation preserving `v1` | `config.yaml`, `src/quantedge/{contracts,config,returns,data}.py`, `scripts/build_data_snapshot.py`, `tests/{test_a_data,test_d_setup}.py`, `docs/sections/a_data_quality.md`, `README.md`, `AI_DISCLOSURE.md`, `CHANGELOG.md`, `data/{raw,processed}/qe1_20050101_20261030_r2_cd2904443b/*` | `scripts/build_data_snapshot.py --derive-from qe1_20050101_20261030_afb9ce5694`, `v1` 13-file SHA-256 integrity check, `pytest -v` (21/21 passed, 0 warnings) | **PENDING** |

---

## Next Step Instructions (`SOLO STEP 3`)

Implement **SOLO STEP 3 — Portfolio construction** using `antigravity-team-pack/02_B_PORTFOLIO_DECISIONS.txt` milestone `B1` and `CONTRACTS.md` (`PortfolioPath` / `portfolio.py`), reusing the active hardened snapshot `qe1_20050101_20261030_r2_cd2904443b` (`load_data(config, offline=True)`):
1. Freeze development/selection/evaluation chronology before evaluating performance.
2. Implement `construct_weights` and `build_portfolio_path` with strict pre-return weight timing (`weights_before.loc[t]` decided using data strictly through `t-1`), natural holdings drift between scheduled rebalances, and documented one-way transaction costs (`5.0` bps).
3. Support core portfolio candidates: constrained Markowitz minimum-variance, mean-variance frontier trade-offs / CAPM expected-return framing, equal-weight reference (explicitly flagging any provisional mandate constraint violation), and canonical monthly-rebalanced `60/40 SPY/AGG` comparison benchmark using the single shared return-path engine.
4. Defer metric/risk comparison tables that depend on Step 4 (`compute_kpis`) and Step 5 (`estimate_risk`) to Step 8 rather than duplicating or fabricating metrics.
5. Add focused no-look-ahead, weight-drift, cost, and constraint-feasibility tests in `tests/test_b_portfolio.py` and incremental methodology notes in `docs/sections/b_portfolio_construction.md`.
