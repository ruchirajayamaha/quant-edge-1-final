# Data Acquisition, Calendar Hygiene, Return Construction & Quality Diagnostics (Milestone A1)

## 1. Approved Sources, Universe & Frozen Snapshot

- **Canonical allocation universe:** `SPY, EFA, EEM, AGG, GLD, XLE, XLK` (exact column ordering enforced across all tables).
- **Snapshot identifier:** `qe1_20050101_20261030_afb9ce5694` (retrieved `2026-10-31T06:41:10Z`, contract schema `1.0.0`).
- **ETF price series:** Daily split- and dividend-adjusted closes retrieved via `yfinance.download(..., auto_adjust=True, repair=False, keepna=True)` over requested start `2005-01-01` through frozen end date `2026-10-30`. With `auto_adjust=True`, Yahoo Finance places the adjusted close series in `Close` and omits `Adj Close`; `extract_adjusted_closes` explicitly rejects frames where `Adj Close` and `Close` coexist so unadjusted and adjusted prices are never silently mixed.
- **Actual trading-session coverage:** `2005-01-03` (first NYSE trading session of 2005) through `2026-10-30` (`5,492` price sessions; `5,491` complete one-session return intervals from `2005-01-04` to `2026-10-30`). All seven ETFs launched prior to 2005 (`GLD` launched November 2004) and have 100% session coverage over the window.
- **Risk-free proxy (`DTB3`):** Raw 3-Month Treasury Bill Secondary Market Rate retrieved from FRED (`https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3`), preserved in `data/raw/qe1_20050101_20261030_afb9ce5694/fred_dtb3_raw.parquet` (`2004-11-17` to `2026-10-29`, `5,727` weekday rows including `235` US bond-market holiday blank markers).

## 2. Session-Grid Alignment & Missing-Data Discipline

1. **Deterministic NYSE session grid:** Raw ETF observations are aligned onto the expected NYSE regular trading-session calendar (`expected_nyse_sessions`), accounting for all ten regular NYSE holiday rules (including NYSE Rule 7.2 for Saturday New Year's Day and Juneteenth observance beginning in 2022) plus the five documented unplanned/mourning full-day closures since 2005 (`2007-01-02`, `2012-10-29`, `2012-10-30`, `2018-12-05`, `2025-01-09`). Across `[2005-01-03, 2026-10-30]`, observed ETF trading dates match the `5,492` expected NYSE sessions with **0 missing expected sessions** and **0 unexpected non-NYSE dates**.
2. **One-session returns before incomplete-row exclusion:** Returns are computed on the uncollapsed session grid via `P_t / P_{t-1} - 1` with **zero implicit forward-fill** and **no artificial first-day zero** (`2005-01-03` serves solely as the initial price anchor). Any missing price at session `t` invalidates *both* adjacent intervals (`t-1 -> t` and `t -> t+1`) before incomplete return rows are excluded and logged in `excluded_return_rows.parquet`, preventing multi-session moves from ever being mislabelled as one-day returns. In the frozen snapshot, `n_missing_price_cells = 0` and `n_excluded_return_rows = 0` (`uninterrupted_return_sessions = True`).
3. **Past-only risk-free alignment:** `DTB3` quotes (annual percent, 360-day bank-discount basis) are converted to the documented daily fractional approximation `(rate_pct / 100.0) / 252`. To respect FRED H.15 publication timing and prevent same-day look-ahead, each valid observation dated `d` becomes usable at `d + 1 BDay` (`availability_lag_sessions = 1`) and is forward-aligned strictly from past available values (`no_backfill = True`). All `5,491` return dates have valid past-only `rf_daily` coverage (`0` missing aligned rows; raw `DTB3` range `-0.05%` in March 2020 to `5.36%`).

## 3. Simple vs. Log Return Conventions

- **Simple returns (`simple_returns`):** Portfolio return at horizon `t` aggregates linearly across pre-return holdings weights in simple returns:
  $$R_{p,t} = \sum_{i=1}^{7} w_{i,t-} R_{i,t}, \qquad L_t = -R_{p,t}$$
  Because \(\ln(1 + x)\) is strictly concave, \(\sum_i w_{i,t-} \ln(1 + R_{i,t}) \neq \ln(1 + R_{p,t})\) by Jensen's inequality. Simple returns are therefore mandatory for cross-sectional portfolio P&L aggregation and committee simple-loss VaR/ES comparisons.
- **Log returns (`log_returns = log1p(simple_returns)`):** Multi-period compounding is additive in log returns (\(\ln(P_T / P_0) = \sum_{t=1}^T r_t\)), so statistical time-series diagnostics (ADF unit-root tests, correlation tables, and volatility-regime screening) are evaluated on `log_returns`.

## 4. Quality Flagging & Stationarity Findings

Flagging (`quality_flags.parquet`) audits extreme moves and regime shifts while **retaining 100% of valid observations** (`action = 'retain'`):

- **`stale_flat_return_run` (`>= 3` consecutive zero returns):** `0` flags across all 7 ETFs.
- **`large_negative_return` (`simple_return <= -0.05`):** `188` flags across all 7 ETFs (`EEM`: 51, `XLE`: 51, `EFA`: 31, `XLK`: 23, `SPY`: 18, `GLD`: 13, `AGG`: 1), led by `XLE` (`-20.14%` on `2020-03-09`) and `EEM` (`-16.17%` on `2008-10-15`).
- **`robust_mad_jump` (`|r - median| / (1.4826 * MAD) > 8.0`, with safe `MAD = 0` fallback):** `101` flags across all 7 ETFs (`SPY`: 23, `EFA`: 18, `XLE`: 16, `EEM`: 15, `AGG`: 13, `XLK`: 10, `GLD`: 6). Retaining these genuine crisis observations is essential for tail-risk (`VaR`, `ES`, `EVT`) realism.
- **`candidate_structural_break` (causal trailing 63-day vs. prior non-overlapping 252-day log-return volatility ratio `>= 2.5`, 63-day refractory window):** `18` flags across 6 ETFs (`SPY`: 5, `EEM`: 3, `XLE`: 3, `XLK`: 3, `AGG`: 2, `EFA`: 2, `GLD`: 0), clustering around October 2008 (GFC), October 2011 (Eurozone/US downgrade), March–April 2018, March–June 2020 (COVID-19 liquidity shock), and April 2025. These are heuristic regime-shift diagnostics, **not** formal proof of permanent structural breaks.
- **ADF stationarity diagnostics (`adf_stationarity.csv`):** All seven ETFs' daily log-return series strongly reject the unit-root null at the 1% and 5% levels (`ADF` statistics between `-14.42` for `XLE` and `-75.11` for `GLD`, all `p <= 7.86e-27`), alongside severe excess kurtosis (`6.55` in `GLD` up to `55.33` in `AGG`).

## 5. Data & Diagnostic Limitations

1. **Stationarity vs. i.i.d.:** Rejecting an ADF unit root confirms level/mean stationarity (`I(0)`) of daily returns; it does **not** imply i.i.d. returns, Gaussian tails, or constant conditional variance. Volatility clustering and heavy tails motivate unconditional POT-GPD EVT and rolling out-of-sample backtesting in Steps 5–7. (Stationarity of the *actual modelled portfolio return series* will be tested separately in Step 4 once Step 3 weights are constructed.)
2. **`DTB3` daily proxy approximation:** Dividing a 360-day bank-discount annual percentage rate by `252` is a standard daily risk-free proxy, not an exact realized 1-day Treasury bill total return (which would also reflect roll/price convexity and `ACT/360` day-count conventions), and FRED quotes remain subject to holiday gaps and potential vintage revisions.
3. **Adjusted-close execution simplification:** `yfinance` `auto_adjust=True` assumes frictionless reinvestment of cash distributions on ex-dates without withholding taxes, bid-ask spreads, or intraday execution slippage.
