# Performance KPIs, CAPM Regression Diagnostics & Bounded Income/Inflation Context (Milestones A1b & A2)

## 1. Alignment, Excess-Return & Annualization Conventions (`src/quantedge/kpis.py`)

All performance and CAPM metrics in `compute_kpis(portfolio_returns, benchmark_returns, market_returns, rf_daily)` are computed on the sorted intersection of valid trading sessions (`common_dates`) across `portfolio_returns` ($R_{p,t}$), `benchmark_returns` ($R_{b,t}$, the shared monthly-rebalanced `60/40 SPY/AGG` path from `build_portfolio_path`), and `market_returns` ($R_{m,t}$, canonical CAPM market proxy `SPY`), with $A = 252$ trading days per year:

1. **Missing or incomplete risk-free handling & input validation (zero fabrication guard):**
   - Daily excess simple returns are $e_{p,t} = R_{p,t} - R_{f,t}$ and $e_{m,t} = R_{m,t} - R_{f,t}$, where $R_{f,t}$ is the primary `r3` causally aligned `DTB3/252` daily proxy (`bundle.rf_daily`).
   - Any non-finite `+/-inf` value in `portfolio_returns`, `benchmark_returns`, `market_returns`, or `rf_daily` is rejected upfront with `ValueError`.
   - If `rf_daily` is `None` or contains any missing/`NaN` values on `common_dates`, all RF-dependent metrics (`sharpe_ratio`, `downside_deviation`, `sortino_ratio`, `capm_beta`, `jensen_alpha`, `treynor_ratio`) return `value = None` and `status = "unavailable"` with an explicit count of missing dates. Zero risk-free rates and future backfills are never invented.
   - When all raw portfolio returns are non-negative ($R_{p,t} \ge 0$) while some observations fall below the daily risk-free rate ($R_{p,t} < R_{f,t}$), the primary RF-target `downside_deviation` and `sortino_ratio` remain finite and `"ok"`, while the optional zero-target Sortino diagnostic (`sortino_zero_target = None`) is safely formatted as `"unavailable (all raw returns >= 0)"` (`R1`).
2. **Geometric vs. arithmetic return distinction:**
   - **Geometric annual return (`geometric_annual_return`):**
     $$G_{\text{ann}} = \left(\prod_{t=1}^{N} (1 + R_{p,t})\right)^{252 / N} - 1 = \exp\!\left(\frac{252}{N}\sum_{t=1}^{N}\ln(1 + R_{p,t})\right) - 1.$$
     Measures actual compounded multi-year wealth growth net of volatility drag.
   - **Arithmetic annual return (`arithmetic_annual_return`):**
     $$\bar{R}_{p,\text{ann}} = 252 \bar{R}_p = \frac{252}{N}\sum_{t=1}^{N} R_{p,t}.$$
     Used in the numerator of linear single-period reward-to-risk ratios (`Sharpe`, `Sortino`, `Treynor`, `Information Ratio`); exceeds $G_{\text{ann}}$ by approximately $\frac{1}{2}\sigma_{p,\text{ann}}^2$ and must not be interpreted as a guaranteed compounded spending rate.

---

## 2. Mandatory KPI Definitions, Edge-Case Guards & Decision Implications

| Metric (`metric`) | Formula ($A = 252$, $N$ aligned sessions) | Unit | Degenerate / Unavailable Guard | Plain-Language Committee Decision Implication |
|---|---|---|---|---|
| `geometric_annual_return` | $\big(\prod_{t=1}^N (1 + R_{p,t})\big)^{252/N} - 1$ | `annual_fraction` | $N < 2$ or any $1 + R_{p,t} \le 0$ | Realized compounded rate at which endowment corpus grew before spending withdrawals. |
| `arithmetic_annual_return` | $252 \bar{R}_p$ | `annual_fraction` | $N < 2$ | Expected 1-year uncompounded return proxy before volatility drag. |
| `annualized_volatility` | $\sqrt{252} \, s_{ddof=1}(R_p)$ | `annual_fraction` | $N < 2$ | Total symmetric annual return dispersion (both upside and downside). |
| `sharpe_ratio` | $\frac{252 \bar{e}_p}{\sqrt{252} \, s_{ddof=1}(e_p)} = \sqrt{252}\frac{\bar{e}_p}{s_{ddof=1}(e_p)}$ | `ratio` | `rf_daily` missing/incomplete or $s_{ddof=1}(e_p) \le 10^{-12}$ | Arithmetic excess return earned per unit of total return volatility. |
| `downside_deviation` | $\sqrt{252} \sqrt{\frac{1}{N}\sum_{t=1}^N \min(0, \, R_{p,t} - R_{f,t})^2}$ | `annual_fraction` | `rf_daily` missing/incomplete | Root-mean-square shortfall below the daily risk-free target across **all $N$ sessions** (never negative-only SD). |
| `sortino_ratio` | $\frac{252 \bar{e}_p}{\text{downside\_deviation}}$ | `ratio` | `rf_daily` missing/incomplete or $\text{DD}_{\text{daily}} \le 10^{-12}$ | Excess return per unit of harmful below-RF downside dispersion, without penalizing upside gains. |
| `capm_beta` | $\frac{\sum_{t=1}^N (e_{p,t} - \bar{e}_p)(e_{m,t} - \bar{e}_m)}{\sum_{t=1}^N (e_{m,t} - \bar{e}_m)^2}$ vs. `SPY` | `beta` | $N < 3$, `rf_daily` missing, or $s_{ddof=1}(e_m) \le 10^{-12}$ | Systematic sensitivity to US equity market (`SPY`) excess fluctuations. |
| `jensen_alpha` | $252 \big(\bar{e}_p - \hat{\beta}_p \bar{e}_m\big)$ | `annual_fraction` | $N < 3$, `rf_daily` missing, or $s_{ddof=1}(e_m) \le 10^{-12}$ | Realized annualized excess return unexplained by static `SPY` market beta. |
| `treynor_ratio` | $\frac{252 \bar{e}_p}{\hat{\beta}_p}$ | `annual_fraction_per_unit_beta` | $\|\hat{\beta}_p\| \le 10^{-4}$ (`unavailable`); $\hat{\beta}_p < 0$ (`warning`) | Annualized excess return earned per unit of systematic `SPY` beta exposure. |
| `tracking_error` | $\sqrt{252} \, s_{ddof=1}(R_p - R_b)$ vs. `60/40` path | `annual_fraction` | $N < 2$ | Annualized standard deviation of active return deviations from the monthly `60/40 SPY/AGG` reference. |
| `information_ratio` | $\frac{252 \overline{(R_p - R_b)}}{\text{tracking\_error}}$ | `ratio` | $\text{TE}_{\text{daily}} \le 10^{-12}$ (e.g., `60/40` vs. itself) | Active return per unit of active tracking risk relative to the `60/40` benchmark. |
| `max_drawdown` | $\min_{1 \le t \le N} \left(\frac{W_t}{\max(1.0, \, \max_{1 \le s \le t} W_s)} - 1\right)$ | `fraction` | $N < 2$ or non-positive gross factor | Worst peak-to-trough fractional loss from any prior peak (explicitly including initial wealth $1.0$). |
| `calmar_ratio` | $\frac{G_{\text{ann}}}{\|\text{max\_drawdown}\|}$ | `ratio` | $\|\text{max\_drawdown}\| \le 10^{-12}$ or $G_{\text{ann}}$ unavailable | Compounded annual growth rate per unit of worst historical peak-to-trough drawdown. |

### CAPM Regression vs. Forward Equilibrium Framing & OLS Limitations
- **Realized regression vs. forward equilibrium:** The CAPM OLS equation $e_{p,t} = \alpha_{\text{daily}} + \beta_p e_{m,t} + \varepsilon_t$ estimates **ex-post realized** market sensitivity $\hat{\beta}_p$ and intercept $\hat{\alpha}_{\text{daily}}$ over a historical window. In forward equilibrium CAPM expected-return modelling ($\mathbb{E}[R_p] - R_f = \beta_p (\mathbb{E}[R_m] - R_f)$), equilibrium $\alpha = 0$ by construction and lower-beta defensive portfolios (`min_variance` $\hat{\beta}_p \approx 0.289$) carry lower forward expected return in exchange for reduced systematic equity drawdown risk.
- **OLS intercept annualization & $t$-statistic limitations:** Linearly scaling $\hat{\alpha}_{\text{ann}} = 252 \hat{\alpha}_{\text{daily}}$ and $\operatorname{SE}(\hat{\alpha}_{\text{ann}}) = 252 \operatorname{SE}(\hat{\alpha}_{\text{daily}})$ leaves the $t$-ratio $t_\alpha = \hat{\alpha}_{\text{daily}} / \operatorname{SE}(\hat{\alpha}_{\text{daily}})$ invariant (compound alternative $(1 + \hat{\alpha}_{\text{daily}})^{252} - 1$ is also recorded in `df.attrs["capm_regression"]`). Classical OLS standard errors assume i.i.d. homoskedastic residuals; under daily GARCH volatility clustering and regime shifts, OLS $t$-statistics can overstate statistical significance, and over a 10-year sample ($N = 2,516$) even a $+3.80\%/\text{yr}$ annualized intercept has $t = 1.89$ ($p = 0.0594$, borderline at $5\%$).

---

## 3. Bounded `A1b` Income & Inflation Context (`data/reference/context/`)

The bounded `A1b` context snapshot (`context_id = "qe1_context_20050101_20261030_a1b_2040bb6e15"`) is stored in `data/reference/context/` (`7` SHA-256-verified files in `context_manifest.json`) without modifying `r3`, `r2`, `v1`, or `data/processed/active_snapshot.json`:

1. **Compatible Share/Split Basis for ETF Distribution Yields:**
   - Using `yfinance.download(..., auto_adjust=False, actions=True)`, `extract_split_adjusted_closes_and_distributions` extracts split-adjusted (non-dividend-adjusted) `Close` ($P_{i,t}^{\text{split-adj}}$), cash `Dividends` per split-adjusted share ($D_{i,t}^{\text{split-adj}}$), and `Stock Splits`.
   - Dividing historical cash dividends by `auto_adjust=True` `Close` (`Adj Close`) is rejected with `ValueError` because `Adj Close` in early years is scaled down by cumulative future dividend reinvestment factors, which would artificially inflate historical yields.
   - Across all `602` positive ex-dividend events (`SPY`: `87`, `EFA`: `41`, `EEM`: `44`, `AGG`: `261`, `XLE`: `88`, `XLK`: `81`; `GLD`: `0` as a physical gold bullion trust) and all `5` stock splits (`EFA` 3:1 on `2005-06-09`, `EEM` 3:1 on `2005-06-09` and `2008-07-24`, `XLE` and `XLK` 2:1 on `2025-12-05`), the exact total-return factor identity
     $$\frac{\text{AdjClose}_{i,t}}{\text{AdjClose}_{i,t-1}} = \frac{P_{i,t}^{\text{split-adj}}}{P_{i,t-1}^{\text{split-adj}} - D_{i,t}^{\text{split-adj}}}$$
     holds with maximum absolute discrepancy $\le 1.60 \times 10^{-6}$.
   - **No double counting:** Because `DataBundle.simple_returns` (`auto_adjust=True`) already reinvests cash distributions into total return, `summarize_portfolio_distribution_income` reports cash distribution yields **beside** total return (to evaluate how much of an endowment spending rule can be funded from cash distributions without selling ETF shares) and never adds them to `PortfolioPath.net_returns`.
2. **Monthly FRED `CPIAUCSL` & Ex-Post Common-Completed-Month Real Returns (`R2`):**
   - `parse_fred_cpi_csv` ingests FRED `CPIAUCSL` (`Index 1982-1984=100, Seasonally Adjusted`, `2004-01` through `2026-09`, `272` valid monthly observations; `2025-10` is missing `.` on FRED because BLS could not collect October 2025 reference data, and `2026-10` was unreleased at the `2026-10-30` freeze date).
   - `compute_ex_post_real_return_metrics` verifies **exact NYSE session date membership** (`obs_dates_m.equals(exp_dates_m)` — never row-count equality alone, so a missing NYSE session replaced by a non-NYSE date is rejected) and records every excluded month and reason (`partial_portfolio_months_excluded`, `missing_current_cpi_months_excluded`, `missing_prior_cpi_months_excluded`, `unreleased_or_missing_cpi_months_excluded`, and `excluded_months_by_reason`).
   - Disconnected single-month CPI/real factors across an internal missing CPI month are **never** multiplied together and called a full start/end wealth or CPI ratio. Under the default performance-independent policy (`interval_policy="endpoint_cpi_contiguous_nominal"`), `compute_ex_post_real_return_metrics` selects the longest contiguous calendar-month block $[m_{\text{start}}, m_{\text{end}}]$ of complete NYSE portfolio months with valid baseline $\text{CPI}_{m_{\text{start}}-1}$ and endpoint $\text{CPI}_{m_{\text{end}}}$, compounding complete nominal returns across all $N$ contiguous months and deflating by the exact endpoint CPI ratio $\text{CPI}_{m_{\text{end}}} / \text{CPI}_{m_{\text{start}}-1}$ over $N/12$ years while flagging any unavailable intermediate 1-month CPI-change months (`status="warning"`). Under `interval_policy="longest_contiguous_cpi_block"`, it selects the longest contiguous calendar-month block in which every single month $m$ has both $\text{CPI}_m$ and $\text{CPI}_{m-1}$. Any scattered single-month product is recorded strictly as a diagnostic labelled `scattered_noncontiguous_monthly_factors_not_an_endpoint_ratio`:
     $$1 + R_{p,m}^{\text{real}} = \frac{\prod_{t \in m}(1 + R_{p,t})}{\text{CPI}_m / \text{CPI}_{m-1}}, \qquad G_{\text{real,ann}} = \frac{1 + G_{\text{nom,common\_months}}}{1 + \pi_{\text{CPI,common\_months}}} - 1.$$
3. **Context Cache File Resolution & Config/Provenance Compatibility (`R3`):**
   - `_try_load_verified_context_cache` resolves every manifest entry strictly inside `context_dir` once, verifies its SHA-256 digest, and reads that exact resolved `Path` object (never hashing `base_dir` originals while reading an altered copy in `context_dir`).
   - Validates `schema_version`, `tickers`, ETF parent provenance (`parent_price_dataset_id` against `processed_dir`), and NYSE session coverage (`requested_start` through `frozen_end_date`). By default (`slice_to_config=False`), a config coverage mismatch (such as `frozen_end_date="2016-12-30"` against the `2026-10-30` snapshot) raises `DataUnavailableError`; when `slice_to_config=True` is explicitly passed, it returns an explicitly bounded compatible view with truthful `context_id` and `bounded_view` metadata without overriding `offline=True`.

---

## 4. Hand-Checkable Viva Walkthrough (4-Session Closed-Form Example)

In `tests/test_a_kpis.py::test_hand_calculated_kpis_exact_closed_form`, consider $N = 4$ sessions (`2020-01-06..2020-01-09`) with constant $R_{f,t} = 0.001$:
- Market (`SPY`) excess returns: $e_m = [-0.02, \, +0.02, \, -0.02, \, +0.02]^\top \implies \bar{e}_m = 0$, $S_{xx} = \sum e_{m,t}^2 = 0.0016$.
- Portfolio excess returns constructed with $\alpha_{\text{daily}} = 0.002$, $\beta_p = 0.5$, and orthogonal residual $\varepsilon = [+0.01, \, +0.01, \, -0.01, \, -0.01]^\top$:
  $$e_p = [0.002, \; 0.022, \; -0.018, \; 0.002]^\top, \qquad R_p = e_p + 0.001 = [0.003, \; 0.023, \; -0.017, \; 0.003]^\top.$$
- **Arithmetic & Geometric Returns:** $\bar{R}_p = 0.003 \implies \bar{R}_{p,\text{ann}} = 252 \times 0.003 = 0.756$; terminal wealth $W_4 = 1.003 \times 1.023 \times 0.983 \times 1.003 = 1.011651704447 \implies G_{\text{ann}} = W_4^{63} - 1 \approx 1.074623447$.
- **Volatility & Sharpe:** $s_{ddof=1}(R_p) = s_{ddof=1}(e_p) = \sqrt{0.0008 / 3} \implies \sigma_{\text{ann}} = \sqrt{0.0672} \approx 0.259229628$, $\bar{e}_{p,\text{ann}} = 252 \times 0.002 = 0.504 \implies \text{Sharpe} = 0.504 / \sqrt{0.0672} \approx 1.944222210$.
- **All-Observation Downside Deviation & Sortino:** Only session 3 is below $R_{f,t}$ ($e_{p,3} = -0.018$), so over all $N = 4$ sessions:
  $$\sigma_{\text{down,daily}} = \sqrt{\frac{0^2 + 0^2 + (-0.018)^2 + 0^2}{4}} = \frac{0.018}{2} = 0.009, \qquad \sigma_{\text{down,ann}} = 0.009\sqrt{252} \approx 0.142870571, \qquad \text{Sortino} = \frac{0.504}{0.009\sqrt{252}} \approx 3.527668415.$$
- **CAPM Beta, Alpha & Treynor:** $\hat{\beta}_p = S_{xy} / S_{xx} = 0.0008 / 0.0016 = 0.50$, $\hat{\alpha}_{\text{ann}} = 252 \times 0.002 = 0.504$, $\text{Treynor} = 0.504 / 0.50 = 1.008$.
- **Tracking Error & Information Ratio:** With active returns $a = R_p - R_b = [0.002, \, 0.010, \, -0.010, \, 0.002]^\top$, $\bar{a} = 0.001$, $s_{ddof=1}(a) = \sqrt{0.000068} \implies \text{TE}_{\text{ann}} = \sqrt{252 \times 0.000068} \approx 0.130904545$, $\text{IR} = 0.252 / \text{TE}_{\text{ann}} \approx 1.925066842$.
- **Max Drawdown & Calmar:** Peak wealth is $W_2 = 1.026069$, trough is $W_3 = 1.026069 \times 0.983 \implies \text{MDD} = -0.017$, $\text{Calmar} = G_{\text{ann}} / 0.017 \approx 63.21314394$.

---

## 5. Development-Period (`2007-01-05..2016-12-30`, `n = 2,516`) KPI & Context Summary

All real-data evaluations in Step 4 are restricted strictly to the **development period through `2016-12-30`** (`504`-session initial burn-in `2005-01-04..2007-01-04`; active out-of-sample sessions `2007-01-05..2016-12-30`, `n = 2,516`, `120` monthly rebalances, net of `5.0` bps one-way leg turnover costs). Selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy performance remain uncomputed and uninspected.

### Table 5A — Core Mandatory KPIs (`r3` Primary `rf_daily`, Net of `5.0` bps Costs)

| Metric (`metric`) | Unit | `min_variance` (Provisional Target-Constrained) | `equal_weight` (Unconstrained `1/7` Reference) | `benchmark_60_40` (Unconstrained `60/40 SPY/AGG` Reference) |
|---|---|---:|---:|---:|
| `geometric_annual_return` | `annual_fraction` | **`0.066534`** (`6.653%`) | `0.054482` (`5.448%`) | `0.060696` (`6.070%`) |
| `arithmetic_annual_return` | `annual_fraction` | **`0.068266`** (`6.827%`) | `0.068711` (`6.871%`) | `0.066344` (`6.634%`) |
| `annualized_volatility` | `annual_fraction` | **`0.087699`** (`8.770%`) | `0.177114` (`17.711%`) | `0.121903` (`12.190%`) |
| `sharpe_ratio` | `ratio` | **`0.702785`** | `0.350511` | `0.489780` |
| `downside_deviation` | `annual_fraction` | **`0.061270`** (`6.127%`) | `0.124734` (`12.473%`) | `0.085606` (`8.561%`) |
| `sortino_ratio` | `ratio` | **`1.005979`** | `0.497707` | `0.697553` |
| `capm_beta` (vs. `SPY`) | `beta` | **`0.289289`** ($t = 47.50$) | `0.795676` ($t = 134.11$) | `0.575706` ($t = 281.85$) |
| `jensen_alpha` (vs. `SPY`) | `annual_fraction` | **`0.038028`** (`+3.803%`, $t = 1.89$) | `-0.002853` (`-0.285%`, $t = -0.15$) | `0.012732` (`+1.273%`, $t = 1.88$) |
| `treynor_ratio` | `annual_fraction_per_unit_beta` | **`0.213061`** | `0.078023` | `0.103724` |
| `tracking_error` (vs. `60/40`) | `annual_fraction` | **`0.082873`** (`8.287%`) | `0.076889` (`7.689%`) | `0.000000` (`0.000%`) |
| `information_ratio` (vs. `60/40`) | `ratio` | **`0.023188`** | `0.030780` | `None` (`unavailable`: zero TE) |
| `max_drawdown` (incl. `1.0`) | `fraction` | **`-0.221756`** (`-22.176%`, trough `2008-10-27`) | `-0.432621` (`-43.262%`, trough `2008-11-20`) | `-0.357806` (`-35.781%`, trough `2009-03-09`) |
| `calmar_ratio` | `ratio` | **`0.300031`** | `0.125935` | `0.169634` |

### Table 5B — `r3` Primary (`/252`) vs. 91-Day Bill Accrual Sensitivity (`2007-01-05..2016-12-30`)

| Metric | `min_variance` Primary `/252` | `min_variance` 91d Accrual | Difference (`Accrual - Primary`) | `equal_weight` Difference | `benchmark_60_40` Difference |
|---|---:|---:|---:|---:|---:|
| `annualized_mean_rf_proxy` | `0.006629849` | `0.006780044` | `+0.000150195` | `+0.000150195` | `+0.000150195` |
| `sharpe_ratio` | `0.702785055` | `0.701035686` | `-0.001749369` | `-0.000861598` | `-0.001237380` |
| `downside_deviation` | `0.061269726` | `0.061269416` | `-0.000000311` | `+0.000001082` | `-0.000004028` |
| `sortino_ratio` | `1.005979150` | `1.003532859` | `-0.002446291` | `-0.001208430` | `-0.001721766` |
| `capm_beta` | `0.289288753` | `0.289304538` | `+0.000015785` | `+0.000018940` | `+0.000001496` |
| `jensen_alpha` | `0.038027720` | `0.037919689` | `-0.000108031` | `-0.000032231` | `-0.000063849` |
| `treynor_ratio` | `0.213060710` | `0.212529926` | `-0.000530784` | `-0.000190617` | `-0.000261158` |

### Table 5C — Ex-Post Real Returns (`119` Complete Common Months `2007-02..2016-12`, Base CPI `2007-01`) & Distribution Income

| Metric | `min_variance` | `equal_weight` | `benchmark_60_40` | Scope / Interpretation Note |
|---|---:|---:|---:|---|
| `ex_post_nominal_annual_return_common_months` | `0.065401` (`6.540%`) | `0.052987` (`5.299%`) | `0.060444` (`6.044%`) | Complete NYSE months `2007-02..2016-12` (`2007-01` partial entry month excluded) |
| `ex_post_cpi_annual_inflation_common_months` | `0.017928` (`1.793%`) | `0.017928` (`1.793%`) | `0.017928` (`1.793%`) | Compounded `CPIAUCSL` (`2007-01` to `2016-12`, ratio `1.192689`) |
| `ex_post_real_annual_return_common_months` | **`0.046637`** (`4.664%`) | `0.034442` (`3.444%`) | `0.041768` (`4.177%`) | Exact Fisher real growth $(1+G_{\text{nom}})/(1+\pi_{\text{CPI}}) - 1$ before spending |
| `ex_post_real_wealth_multiple_common_months` | **`1.571493`** | `1.399052` | `1.500473` | Cumulative purchasing-power multiple over `119` complete months |
| `annualized_ex_date_distribution_yield` | `0.019038` (`1.904%`) | `0.019545` (`1.955%`) | `0.025632` (`2.563%`) | Embedded cash yield on ex-dates (lower in `min_variance` due to `25–40%` zero-yield `GLD`) |
| `mean_trailing_12m_distribution_yield` | `0.019159` (`1.916%`) | `0.019670` (`1.967%`) | `0.025806` (`2.581%`) | Average trailing-365d cash yield across `2,516` active sessions |
| `ending_trailing_12m_distribution_yield` (`2016-12-30`) | `0.016579` (`1.658%`) | `0.019202` (`1.920%`) | `0.021740` (`2.174%`) | Run-rate cash distribution yield at development end (`2016-12-30`) |
| Strategy return ADF $t$-stat (`simple` / `log1p`) | `-11.6047` / `-11.5646` | `-11.2221` / `-11.0411` | `-11.2606` / `-11.0908` | Statistics only; refer to the verified JSON for p-values/lags. Unit-root rejection does not imply i.i.d. or constant volatility. |

---

## 6. Disclosed Limitations & Deferred Risk-Window Diagnostics

1. **Both RF series are approximations:** Neither the primary `DTB3 / 252` proxy nor the 91-day bill accrual sensitivity represents the exact daily mark-to-market total return of a rolled T-bill account.
2. **Latest-vintage seasonally adjusted CPI:** FRED `CPIAUCSL` reflects retrospective BLS seasonal-adjustment revisions and is used strictly for ex-post completed-month purchasing-power measurement, never as a point-in-time trading signal or forward inflation forecast.
3. **Distribution yield vs. total return & `GLD` zero yield:** Because `min_variance` holds `25%–40%` in zero-dividend `GLD` under provisional caps, its cash distribution yield (`~1.90%/yr` in development) is lower than `60/40 SPY/AGG` (`~2.56%/yr`); an endowment spending rule exceeding `~1.9%/yr` therefore requires funding the remainder from capital appreciation via periodic share sales.
4. **Fixed-exposure risk-window stationarity deferred to Step 5+:** Per `NEXT_TASK_STEP4.txt`, `run_portfolio_return_stationarity_diagnostics` is verified on the development strategy paths in Step 4, while fixed-exposure stationarity diagnostics on the Step 5+ risk-estimation windows remain scheduled for Step 5+ when risk samples are evaluated.

Verified numerical source: `audit/step4_review/CODEX_VERIFIED_STEP4_RESULTS.json`. Table 5B and the ADF row were refreshed by Codex from actual development computations; use the saved tables rather than copied chat figures.
