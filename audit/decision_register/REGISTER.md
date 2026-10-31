# Quant Edge decision register

**Status: DRAFT - human economic choices and evaluation protocol are not signed.** Created 2026-10-31 after the final-round strategy review and before portfolio results. A draft commit records timing only; it is not proof of completed human preregistration. Append amendments with date, reason and evaluation exposure instead of replacing past choices.

## Verified inherited project facts

- Official authority: `Quant edge 1.0 Final Challenge 1.pdf`; numerical client risk limits and final submission deadline were not supplied in it.
- Current verified baseline commit: `d7ccafe7a2cb7f1c4794ac4a5ee221278068dce6`.
- Active dataset: `qe1_20050101_20261030_r3_6c4633a7ba`; schema `1.1.0`; frozen data end `2026-10-30`.
- Eligible assets: SPY, EFA, EEM, AGG, GLD, XLE, XLK. No new cash allocation asset.
- Mandate scale: USD10,000,000. Final recommendation and independent human validation remain pending.
- Coding mode: one developer/checkout. This does not change the official five-member team statement.

## Prior exposure / scope of the later evaluation claim

Whole-history ETF prices, quality flags, extreme asset days, descriptive statistics, correlations and per-asset ADF results were already inspected during data auditing. RF evidence and conversion sensitivities were researched. No portfolio strategy results, final weights or candidate performance have yet been computed in this workflow. Do not later describe the whole final-period dataset as never seen; distinguish retrospective research, rule selection and still-uncomputed strategy evaluation.

## Human mandate inputs - not supplied by AI

| Input | Human choice / range | Status / provenance |
|---|---|---|
| Investment horizon and review cycle | PENDING | Config wording is provisional |
| Spending rule/range and its NAV basis | PENDING | Not a client-supplied fact |
| Inflation assumption/range | PENDING | Forward assumption distinct from ex-post CPI |
| Additional fees/costs and embedded fund-cost treatment | PENDING | Avoid double charging |
| Desired real growth | PENDING | Distinguish objective from observed return |
| Required nominal-return cash-flow convention | PENDING | Derive from choices above |
| Income target and whether capital withdrawals may fund spending | PENDING | Do not equate income yield with total return |
| Daily VaR/ES risk limit(s), confidence and units | PENDING | Fractions/percent/USD must be explicit |
| Drawdown/scenario-loss tolerances | PENDING | Not interchangeable with one-day ES |
| Permitted risk-limit/constraint changes for ADJUST | PENDING | No automatic relaxation |
| Monitoring thresholds and approved actions | PENDING | At least metric/threshold/action |

Cash-flow derivation to choose explicitly: with deductions s/f as fractions of post-return NAV, `(1+R)*(1-s-f)=(1+i)*(1+g)`. With end-year deductions expressed against beginning NAV, `1+R-s-f=(1+i)*(1+g)`. A smoothed spending rule requires its own model. These identities do not turn an arithmetic expected-return forecast into guaranteed net geometric growth.

## Inherited software settings - PROVISIONAL, not human sign-off

| Setting | Existing value / implication | Approval |
|---|---|---|
| Development | 2005-01-01 through 2016-12-30 | PENDING confirmation |
| Selection | 2017-01-03 through 2020-12-31 | PENDING confirmation |
| Final evaluation | 2021-01-04 through 2026-10-30 | PENDING confirmation |
| Portfolio estimation | 504 sessions; sample covariance ddof=1 | Inherited default |
| Rebalancing | Monthly | Execution/turnover convention to record |
| Transaction cost | 5bps one-way | Explicit turnover definition still needed |
| Allocation | Long-only, fully invested; max40% per ETF | Team choice, not an official rule |
| Equity group cap | 35% | Implies AGG+GLD at least65% |
| Defensive minimum | AGG+GLD40% | Redundant under the equity cap |
| Implied feasible ranges | AGG/GLD25-40% each; equities20-35% | Concentration implication, not proof of safety |
| Primary backtest model | Historical VaR | Inherited; confirm before selection/evaluation |
| Backtest window | 500 sessions | Different from dashboard window |
| Current-risk window | 1,260 sessions | Current conditions; includes2022, omitsGFC/COVID |
| Additional risk view | Full-history fixed-exposure sensitivity | Strategy proposal, not official required lookback |
| MC draws | 25,000, configured seed | Check simulation error before choosing displayed precision |
| EVT threshold | 0.95 is provisional | Diagnostic grid/policy to register during implementation |

## Candidate rules and selection protocol - DRAFT

- Core candidates: configured constrained minimum variance; equal-weight reference; monthly60/40SPY/AGG reference. Label reference constraint violations. Any additional rule/constraint variant gets an ID and a reason before its outcomes are inspected.
- Future final weights come from the selected rule applied at the frozen data end. Current-weight historical replay is a scenario, not an investable OOS performance record.
- Selection criterion, priority among return/downside/income/stability, allowed tuning and tie-break rule: **PENDING HUMAN DECISION**.
- Evaluation protocol/model/constraint policy must be committed before strategy selection/evaluation. Changing it later is an amendment and may invalidate the untouched-strategy-test description.
- Essential unresolved numerical choices mean outputs are exploratory; they cannot be relabelled as a final approved mandate.
- Preferred post-core feature: Mandate Feasibility Frontier, only after core tests, with candidate-table fallback. Optional complement: EWMA-FHS. They are not official requirements or novelty claims.

## Conditional recommendation rule - humans must complete

ACCEPT / ADJUST / REJECT refers to the explicitly proposed assumptions and limits, not invented client numbers. Define the tests for acceptance, the changes permitted for adjustment and the maximum tolerance beyond which the team recommends rejection. A computed candidate table supports the team decision; AI does not sign it.

## Team, defence and logistics

| Role coverage | Actual member | Independent check / backup | Status |
|---|---|---|---|
| Data, sources and RF evidence | PENDING | PENDING | Human validation pending |
| Portfolio theory, CAPM and KPIs | PENDING | PENDING | Human validation pending |
| VaR, ES and EVT | PENDING | PENDING | Human validation pending |
| Validation, sizing and stress | PENDING | PENDING | Human validation pending |
| App, memo and committee defence | PENDING | PENDING | Human validation pending |

Actual team membership: PENDING. Deadline/submission route: PENDING. Organiser clarification on numerical mandate limits and one-page recommendation packaging: PENDING. Judge access to the existing private GitHub repository: PENDING. Unknown logistics do not block unrelated mathematical implementation or synthetic tests.

## Change and approval log

| Date | Change | Human owner / evidence | Test exposure |
|---|---|---|---|
| 2026-10-31 | Prepared factual baseline and draft questions during prompt integration | Codex-prepared; not human-approved | Prior exposure disclosed above; no portfolio outcomes computed |
| 2026-10-31 | Clarified that pending human choices do not block Step 3 implementation under inherited provisional config; synthetic/development-period checks may proceed | User requested progress; no economic choice or human sign-off inferred | No portfolio outcomes computed by this clarification; selection/evaluation outcomes remain uninspected |
| 2026-10-31 | Implemented Step 3 (`B1`) portfolio rules (`src/quantedge/portfolio.py`) and recorded explicit execution, turnover, 5bps leg-cost, initial-entry, drawdown, and LP-implied bounds conventions below under inherited provisional config | AI engineering implementation (`SOLO STEP 3`); human economic choices and sign-off remain **PENDING** | Synthetic unit tests + offline `r3` development-period (`2005-01-04..2016-12-30`, active `2007-01-05..2016-12-30`) structural/feasibility smoke check only; selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy outcomes remain uncomputed and uninspected |
| 2026-10-31 | Applied bounded Step 3 review corrections (`R1-R3`): rejected conflicting `objective`/`fixed_weights` specifications upfront, explicitly scoped `PortfolioConstraints` to rebalance targets (`constraint_enforcement_scope = "rebalance_targets_only"`) while adding separate daily pre-return drifted-holdings diagnostics (`summarize_pre_return_holdings_compliance`), and corrected the Frank-Wolfe convex duality-gap inequality in `docs/sections/b_portfolio_construction.md` without modifying any existing development path arrays | AI bounded remediation (`audit/step3_review/ANTIGRAVITY_STEP3_FIX_PROMPT.txt`); human continuous-cap vs. rebalance-target mandate choice and sign-off remain **PENDING** | Synthetic unit tests + bit-identical (`21/21` SHA-256) offline `r3` development-period (`<= 2016-12-30`) verification only; selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy outcomes remain uncomputed and uninspected |
| 2026-10-31 | Implemented Step 4 (`A1b` bounded income/inflation context snapshot `qe1_context_20050101_20261030_a1b_2040bb6e15` in `data/reference/context/` and `A2` performance & CAPM KPIs in `src/quantedge/kpis.py`) and recorded KPI/CAPM/income/CPI conventions below | AI engineering implementation (`SOLO STEP 4`); human mandate choices, selection criterion, and sign-off remain **PENDING** | Synthetic closed-form tests + development-period (`2007-01-05..2016-12-30`, `n=2,516`) KPI, RF-accrual sensitivity, common-completed-month ex-post CPI real return (`2007-02..2016-12`), and distribution-income tables only; selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy outcomes remain uncomputed and uninspected |
| 2026-10-31 | Applied bounded Step 4 review corrections (`R1-R3`): guarded optional zero-target Sortino formatting when all raw returns are non-negative (`R1`), enforced exact NYSE session date-set matching (`obs_dates_m.equals(exp_dates_m)`), explicit missing-prior-CPI exclusion reporting, and performance-independent contiguous interval / endpoint-CPI purchasing-power semantics (`R2`), and enforced `context_dir`-local payload resolution + config/coverage/provenance validation (`R3`) with zero change to development KPI or 119-month real-return values | AI bounded remediation (`audit/step4_review/ANTIGRAVITY_STEP4_FIX_PROMPT.txt`); human mandate choices, selection criterion, and sign-off remain **PENDING** | Synthetic `R1-R3` regression tests + bit-identical development-period (`2007-01-05..2016-12-30`) KPI & 119-month real-return verification only; selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy outcomes remain uncomputed and uninspected |
| 2026-10-31 | Implemented Step 5 (`C1`) Historical, Parametric Normal, and seeded Multivariate Normal Monte Carlo VaR & ES (`src/quantedge/var.py`, `src/quantedge/es.py`), exported development-period (`<= 2016-12-30`) risk tables and MC uncertainty quantification to `results/step5_development_c1_risk_tables.json` and `docs/sections/c_var_es_and_evt.md`, and recorded C1 conventions below | AI engineering implementation (`SOLO STEP 5`); human risk-limit choices, selection criterion, and sign-off remain **PENDING** | Synthetic unit tests (`tests/test_c_var_es.py`) + development-only (`2011-12-29..2016-12-30` recent `1,260d` and `2005-01-04..2016-12-30` full-development `3,020d`) fixed-exposure risk and stationarity checks only; selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy outcomes remain uncomputed and uninspected |
| 2026-10-31 | Implemented Step 6 (`A3`) rolling out-of-sample VaR validation (`rolling_backtest`, `coverage_tests`, `basel_traffic_light` in `src/quantedge/backtest.py` and `src/quantedge/_backtest_diagnostics.py`) under the recorded Step 6 development engineering protocol, persisted development-only (`2007-01-05..2016-12-30`, `N = 2,516`) results and figures to `results/step6_backtest_preview/`, and documented outcomes in `docs/sections/a_backtesting.md` without retuning any model, window, confidence, or strategy | AI engineering implementation (`SOLO STEP 6`); human validation, selection criterion, and final protocol approval remain **PENDING** | Synthetic causality/likelihood/Basel tests (`tests/test_a_backtest.py`, `tests/test_a_backtest_diagnostics.py`) + development-only (`2007-01-05..2016-12-30`, training warmup from `2005-01-10`) rolling 500-session Historical & Parametric Normal `95%`/`99%` VaR backtests on `min_variance` only; selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy outcomes remain uncomputed and uninspected |
| 2026-10-31 | Implemented Step 7 (`C2/C3`) Unconditional POT-GPD EVT (`src/quantedge/evt.py`), threshold diagnostics grid, empirical-body / GPD-tail hybrid, and moving-block bootstrap uncertainty on terminal-development `min_variance` exposure under recorded Step 7 protocol; generated visible outputs in `results/step7_evt_preview/` and documented results in `docs/sections/c_var_es_and_evt.md` | AI engineering implementation (`SOLO STEP 7`); human validation, selection criterion, and threshold policy approval remain **PENDING** | Synthetic closed-form/stability/oracle tests (`tests/test_c_evt.py`, `tests/test_c_var_es.py`, `tests/test_d_setup.py`) + development-only (`2011-12-29..2016-12-30` recent `1,260d` and `2005-01-04..2016-12-30` full `3,020d`) fixed-exposure EVT fits only; selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy outcomes remain uncomputed and uninspected |

## Step 3 (`B1`) recorded implementation conventions - PROVISIONAL, pending human protocol sign-off

- **Implemented core candidate rules (`quantedge.portfolio`):**
  1. `min_variance`: constrained Markowitz minimum variance (`objective="min_variance"`) estimated on trailing `504` trading sessions using primary sample covariance `ddof=1` on isolated C-contiguous `float64` training arrays, with symmetry verification, eigenvalue PSD verification, HiGHS Chebyshev linear-feasibility pre-check, scaled SLSQP solve, and HiGHS Frank-Wolfe convex duality-gap KKT verification. Infeasible constraints or failed solver outputs raise `PortfolioOptimizationError` and are never silently clipped or renormalised.
  2. `equal_weight`: unconstrained `1/7` reference across `SPY, EFA, EEM, AGG, GLD, XLE, XLK` (`mandate_compliance_status = "unconstrained_reference_violates_provisional_caps"`, flagging `71.43%` total equity vs. `35%` provisional cap).
  3. `benchmark_60_40`: unconstrained monthly-rebalanced `60% SPY / 40% AGG` reference running through the single shared `build_portfolio_path` engine (`mandate_compliance_status = "unconstrained_reference_violates_provisional_caps"`, flagging `SPY = 60%` vs. `40%` single-ETF cap and `35%` equity group cap).
- **Execution boundary & causality convention:** For `estimation_window_days = W` (`504` default), initial investment enters at session `pos = W` (`decision_date = index[W - 1]`, strictly using `iloc[0:W]`), holdings drift proportionally via `w_{t+} = w_{t-} * (1 + r_t) / (1 + R_{p,t}^{gross})`, and scheduled monthly (`"M"`) rebalances execute at the first trading session of each new calendar month (`effective_date = t`), decided at the preceding month-end close (`decision_date = t - 1`) using strictly trailing observations through `t - 1`.
- **Explicit turnover, initial-entry & 5bps one-way cost convention:** `turnover_t = sum_i |w_{i,t,target} - w_{i,t,pre}|` (`sum_abs_trade_weights`, i.e., total one-way leg notional traded across buy and sell orders as a fraction of pre-trade NAV), with `w_{t_0,pre} = 0` at initial investment from 100% cash (`turnover_{t_0} = 1.0`, `cost_{t_0} = 5.0 bps = 0.0005`). On interior rebalances reallocating fraction `x` across ETFs, `turnover_t = 2x` (`x` sold + `x` bought; `half_turnover = x` is also recorded in `PortfolioPath.rebalances`) and `cost_t = (5.0 / 10000.0) * turnover_t = 0.0005 * (2x)`. Net daily simple return is `R_{p,t}^{net} = (1 - cost_t) * (1 + R_{p,t}^{gross}) - 1`.
- **Wealth & drawdown convention:** `wealth_t = prod_{s <= t} (1 + R_{p,s}^{net})` anchored from initial pre-entry wealth `1.0`; `drawdown_t = wealth_t / max(1.0, max_{s <= t} wealth_s) - 1.0` explicitly includes initial wealth `1.0`.
- **LP-verified implied bounds under inherited provisional caps (`compute_implied_weight_bounds`):** `AGG in [25%, 40%]`, `GLD in [25%, 40%]`, each equity ETF `in [0%, 35%]`, `EQUITY_TOTAL in [20%, 35%]`, and `DEFENSIVE_TOTAL in [65%, 80%]` (`min_defensive_weight = 40%` is redundant). These remain provisional team defaults awaiting human review, not official mandate rules or proof of safety.
- **Rebalance-target enforcement scope vs. pre-return drifted-holdings monitoring (`R2`):** `PortfolioConstraints` are enforced strictly on **rebalance targets** (`constraint_enforcement_scope = "rebalance_targets_only"`, `mandate_feasible_all_rebalances`). Between scheduled monthly rebalances, drifted holdings are never clipped and no unapproved intraday/daily rebalancing is triggered (`continuous_holdings_cap_policy = "not_enforced_natural_drift_between_scheduled_rebalances_pending_human_policy"`). Daily pre-return holdings compliance is reported separately via `summarize_pre_return_holdings_compliance` (`mandate_feasible_all_pre_return_sessions`, `pre_return_holdings_compliance`, and scope-qualified `mandate_compliance_status`; in development `2007-01-05..2016-12-30`, `min_variance` satisfies `120 / 120` rebalance targets while natural drift causes `1,439 / 2,516` pre-return sessions to exceed `max_weight_per_etf` [`AGG`: `994`, peak `45.14%`; `GLD`: `17`, peak `41.04%`] or `max_equity_weight` [`617` sessions, peak `37.30%`]). Any continuous daily cap-maintenance or drift-band policy remains **PENDING HUMAN DECISION**.
- **Step 4 (`A1b` & `A2`) KPI, CAPM & income/inflation context conventions (`quantedge.kpis`, `data/reference/context/`):**
  1. `compute_kpis(portfolio_returns, benchmark_returns, market_returns, rf_daily)` aligns inputs on common valid trading sessions (`A = 252` trading days/year), marks RF-dependent KPIs `unavailable` (`value = None`) if `rf_daily` is `None` or incomplete (zero RF and future backfill are never invented), separates `geometric_annual_return = prod(1+R_p)^(252/N) - 1` from `arithmetic_annual_return = 252 * mean(R_p)`, computes `sharpe_ratio = sqrt(252) * mean(e_p) / std(e_p, ddof=1)`, defines `downside_deviation = sqrt(252 * (1/N) * sum_{t=1..N} min(0, R_{p,t} - rf_daily_t)^2)` over **all $N$ observations** relative to daily `rf_daily`, estimates CAPM `capm_beta` and linearly annualized `jensen_alpha = 252 * alpha_daily` via OLS with intercept against `SPY` excess returns, computes `tracking_error` and `information_ratio` against the shared monthly-rebalanced `60/40 SPY/AGG` path, and includes initial pre-entry wealth `1.0` in `max_drawdown` and `calmar_ratio`.
  2. Bounded `A1b` context snapshot `qe1_context_20050101_20261030_a1b_2040bb6e15` (`data/reference/context/`, 7 SHA-256-verified files) pairs `yfinance` `auto_adjust=False` split-adjusted `Close` with `actions=True` split-adjusted `Dividends` (verified across all `602` ex-dividend events via `AdjClose_t/AdjClose_{t-1} == Close_t/(Close_{t-1} - Div_t)` within `1.60e-6`) and monthly FRED `CPIAUCSL` (`2004-01..2026-09`, `272` observations; `2025-10` missing `.` on FRED and `2026-10` unreleased at `2026-10-30`). Distribution yields are reported **beside** total return (never added again to `auto_adjust=True` total returns), and `CPIAUCSL` deflates completed common-month wealth ratios strictly ex post (never used as a forward inflation forecast).
- **Step 5 (`C1`) VaR & ES modelling and window conventions (`quantedge.var`, `quantedge.es`, `results/step5_development_c1_risk_tables.json`):**
  1. Fixed-exposure 1-day simple-return loss convention: `R_{p,t} = (train_asset_returns @ weights)_t`, `L_t = -R_{p,t}` before transaction costs (`USD loss = loss_fraction * 10,000,000`). Nonpositive loss quantiles (`<= 0`, net gains) are preserved without `abs()` or zero flooring.
  2. Historical VaR & ES (`empirical_tail_weights`, `empirical_var_and_es`): Historical VaR uses the empirical step-CDF quantile `VaR_c = F_n^{-1}(c) = L_{(ceil(n * c))}` (`method="inverted_cdf"`), and Historical ES equals `float(empirical_tail_weights(losses, c) @ losses)` over the order-statistic boundary `u_* = L_{[ceil(n * (1 - c))]}`, assigning `1 / (n * alpha)` to strict exceedances `L_i > u_*` and splitting the remaining fractional/tied mass `(alpha - k_strict / n) / alpha` equally across all `k_tie >= 1` boundary ties `L_i == u_*`.
  3. Shared normal moments (`normal_moments`, `ddof = 1`): arithmetic sample mean and unbiased sample covariance reused identically across `parametric_normal` (`VaR_c = -mu_p + sigma_p * z_c`, `ES_c = -mu_p + sigma_p * phi(z_c) / (1 - c)`), `monte_carlo_normal` (`M = 25,000` multivariate normal draws via PCG64 `default_rng(seed=202601)`, cached by `(moments_digest, seed, n_simulations)`), and Step 8 (`B2`) normal Euler risk contributions. Degenerate zero volatility (`sigma_p = 0`) returns deterministic `-mu_p` with `status = "warning"`.
  4. Development diagnostic windows (`<= 2016-12-30`): `recent_development_1260d` (`2011-12-29..2016-12-30`, `n = 1,260`, omitting `gfc_2007_2009` and post-2016 `covid_2020`/`rate_shock_2022`) and `full_development_3020d` (`2005-01-04..2016-12-30`, `n = 3,020`, including `gfc_2007_2009` and excluding post-2016 `covid_2020`/`rate_shock_2022`).

Human completion/signature/date: **PENDING**. Formal protocol commit: **PENDING**. No AI or automated test may fill these as completed human actions.

## Step 6 development engineering protocol — recorded 2026-10-31 before outcomes

User authorized executing `NEXT_TASK_STEP6.txt`. Use inherited primary Historical VaR,
previous 500 NYSE asset-return sessions, 95% and 99%, on the accepted drifting
`min_variance` path. Parametric Normal is a matched comparison, not a model-selection
competition. Both are tested against the same gross market loss at weights known
before the target return; costs remain in net performance reporting. A strict
loss-above-VaR observation is an exception. No model, window, weights or confidence
will be retuned on these outcomes. Basel uses the ending 250 consecutive valid
99% one-day pairs, with no backward search around failures. Computation and export
are limited to development through 2016-12-30, labelled development OOS research.
Selection/evaluation outcomes remain uncomputed. This is a recorded inherited
software protocol, **not human economic approval or signed preregistration**.
Human validation, selection criterion and final protocol approval remain PENDING.

## Step 7 (`C2/C3`) EVT threshold and bootstrap policy — recorded 2026-10-31 BEFORE any EVT fit

User authorized executing `NEXT_TASK_STEP7.txt`. This policy is appended before
`evt.py` is implemented or any GPD is fitted to development data
(pre-edit hashes: `audit/step7_review/STEP7_BASELINE.json`).

- **Exposure / windows (identical to Step 5):** terminal-development `min_variance`
  target weights from `results/step5_development_c1_risk_tables.json`; windows
  `recent_development_1260d` (`2011-12-29..2016-12-30`) and `full_development_3020d`
  (`2005-01-04..2016-12-30`). EVT uses exactly the same observations, weights,
  confidence and 1-day horizon as Historical/Normal/MC; no EVT-only window enlargement.
  Neither window contains COVID-2020 or the 2022 rate shock (both are after 2016-12-30).
- **Primary provisional threshold policy (inherited, not tuned):** `u` = empirical
  `0.95` loss quantile under the same `inverted_cdf` order-statistic convention as
  Historical VaR (`u = L_(ceil(0.95 n))`); strict exceedances `L > u`; minimum
  `50` strict exceedances (`config.risk.evt_threshold_quantile`, `evt_min_exceedances`).
  If the minimum is not met, the fit is reported unavailable; the threshold or minimum
  is never lowered silently.
- **Sensitivity grid only:** existing diagnostic grid `0.90, 0.925, 0.95, 0.975`
  (D0 `evt_threshold_diagnostics` default) plus a dense descriptive MRL/stability grid.
  The grid is NOT used to pick a threshold giving the friendliest VaR/ES or backtest.
  If diagnostics fail to support `0.95`, this is recorded as judgement/uncertainty;
  any policy change requires human approval.
- **GPD fit:** excesses `y = L - u` for `L > u`; `scipy.stats.genpareto.fit(y, floc=0)`
  maximum likelihood with a convergence-recording Nelder-Mead optimizer.
- **Pure POT vs body/tail:** pure POT VaR/ES only where `c >= 0.95` and
  `a = (1-c)/p_u <= 1`. 90% is served only by the separately labelled empirical-body /
  GPD-tail helper; a body-region VaR is labelled BODY, never EVT extrapolation.
- **Moving-block bootstrap (fixed before running):** block length `10`, `100`
  replications, seed `config.seeds.evt_bootstrap = 202602`, threshold POLICY fixed at
  the `0.95` quantile with the empirical threshold re-estimated on every resample,
  minimum `50` exceedances per resample, percentile interval reported only if at least
  `80` of `100` replicates produce a finite value. Intervals are conditional on the
  threshold policy and the block-dependence assumption.
- **Not in scope:** rolling/daily EVT, EVT rolling backtests, GARCH/FHS, threshold
  re-selection on outcomes, selection/evaluation-period data.

This is a recorded inherited software policy, **not human approval**. Human validation
of the threshold policy and EVT interpretation remains **PENDING**.

## Step 8 bounded engineering protocol — recorded before outcomes, 2026-10-31

User authorized Codex to implement Step 8 directly. Reuse the terminal-development
minimum-variance exposure from Step 5, not an allocation chosen on later outcomes.
Primary sizing sample is the same recent 1,260 development observations; full
3,020-session sample is a labelled sensitivity. Registered candidate target weights
(SPY, AGG, GLD; other ETFs zero) are: baseline from Step 5; (0.20,0.40,0.40),
(0.35,0.40,0.25), (0.30,0.35,0.35), (0.25,0.35,0.40). These are a bounded feasible
candidate table, not a new optimizer/frontier or selection of an investment winner.
Equal-weight and 60/40 are labelled references with constraint violations visible.
Risk limits remain null/unapproved. Expected-return proxy is the same sample's
arithmetic historical mean times252, not a forward forecast or spending guarantee.
Report 95/99 normal VaR/ES and historical ES Euler allocations. For sizing compare
historical99 risk with unchanged constraints; no cash or cap relaxation.
Historical stress uses the configured GFC/COVID/2022 date windows and terminal-
development initial weights, buy-and-hold with natural drift, compared with60/40.
This explicitly authorized ex-post replay of post-2016 asset returns is scenario
analysis, not selection/evaluation of an investable strategy or untouched holdout
validation. Config's seven-ETF hypothetical vector is an unsigned simultaneous
one-step shock; duration is unspecified, so same-horizon daily comparisons are
illustrative scale context only. No probabilities or ES label for scenario losses.
Human tolerances, monitoring trigger thresholds and final mandate decision remain
PENDING; missing choices do not stop engineering or honestly labelled outputs.

### Step 8 implementation outcome record — no human approval inferred

Implemented 84 Euler contribution rows, 14 candidate comparisons and 8 stress
comparisons from the pre-recorded protocol. Five candidate targets meet supplied
constraints in each development window; the two unconstrained references do not.
Risk-limit compliance remains indeterminate because human limits are null. No
winner or ACCEPT/ADJUST/REJECT recommendation was selected. Post-2016 COVID/2022
exposure is confined to the explicitly authorized fixed-weight ex-post scenarios.
The selection/evaluation strategy-performance protocol and human decisions remain
PENDING. Independent scalar/array oracles and software tests are recorded in
`audit/step8_review/`; this is not independent human validation.
