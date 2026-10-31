# Shared interfaces - freeze before parallel implementation

This file describes integration conventions. Existing runtime definitions in src/quantedge/contracts.py (currently schema 1.1.0), config and handoff/SOLO.md are authoritative for implemented interfaces. D0/A1/r3 are complete; do not recreate them from this older skeleton. Proposed future additions are introduced together with their callers and tests, not by silently replacing existing dataclasses. In solo mode one developer owns all areas below; the ownership table is for explicitly chosen parallel work only.

## Ownership

| Owner | Code | Tests and supporting files |
|---|---|---|
| A | `src/quantedge/{data,returns,kpis,backtest}.py` | `tests/test_a_*.py`, `docs/sections/a_*.md`, `handoff/A.md`, data snapshot/quality outputs |
| B | `src/quantedge/{portfolio,risk_budget,stress}.py` | `tests/test_b_*.py`, `docs/sections/b_*.md`, `handoff/B.md` |
| C | `src/quantedge/{var,es,evt}.py` | `tests/test_c_*.py`, `docs/sections/c_*.md`, `handoff/C.md` |
| D | `contracts.py`, `config.py`, `pipeline.py`, `__init__.py`, dependency/build files, config, app, scripts, integration tests, exports, root docs | `tests/test_d_*.py`, `handoff/D.md`, release checklist |

Each owner creates only their own tests; D owns shared `conftest.py`. Generated files use dataset/config-specific directories. A/B/C never edit shared exports to make an import convenient.

## DataBundle

The implemented DataBundle includes these concepts; inspect the current dataclass for exact field names and optional r3 additions:

- `prices`: adjusted close DataFrame on the documented expected shared US trading sessions, ascending unique DatetimeIndex, columns exactly `SPY,EFA,EEM,AGG,GLD,XLE,XLK`; missing observations remain flagged before return calculation.
- `simple_returns`: complete one-session DataFrame `P_t/P_(t-1)-1`, calculated on the uncollapsed session grid with no implicit fill; no artificial first-day zero. A missing price invalidates returns needing either endpoint. Exclude/count those affected rows only after calculation, rather than dropping price dates first and mislabelling a multi-session return as one-day. Expose gaps so a performance path or250-day test is not falsely labelled uninterrupted.
- `log_returns`: same index/columns as simple returns, `log1p(simple_returns)`.
- `rf_daily`: fractional DTB3/252 approximate trading-day proxy. Under r3 select the newest eligible observation and its latest eligible value version; provenance distinguishes documented, vintage-supported, inferred, sparse-fallback and unresolved evidence. This is day-level evidence, not exact historical intraday availability. Keep `ex_post_rf_daily`, `rf_provenance` and `rf_accrual_sensitivity` separate using their runtime names. Neither the primary proxy nor the accrual sensitivity is an exact realized Treasury return.
- `quality_flags`: tidy table with date/ticker/rule/value/action; flagging must not automatically remove a return.
- `manifest`: dataset ID, requested and actual bounds, UTC retrieval time, source URLs, adjustment setting, row exclusions, per-file SHA256, RF conversion/availability convention and schema version.

The downloadable end bound may be exclusive. Persist actual final observations, not just the requested date. A creates the snapshot once; D distributes it by the team's agreed mechanism without requiring a new download per clone. No secrets go into it.

The current ETF/RF snapshot is already built and verified. Future income/inflation context belongs in a separate hashed data/reference/context/ snapshot with source, bounds, retrieval time, units and use classification. It must not modify r3 or become an unlagged optimizer signal. See A1b.

Public interfaces, with exact Python details frozen by D:

```python
load_data(config, *, offline: bool = False) -> DataBundle
compute_kpis(portfolio_returns, benchmark_returns, market_returns, rf_daily) -> pd.DataFrame
```

KPI result columns: `metric,value,unit,status,note`. SPY is the CAPM market proxy; 60/40 SPY/AGG is a monthly-rebalanced comparison benchmark, not an eligible single ETF. Use comparable dates. State arithmetic/geometric and annualization conventions per metric. A and B agree once on a single return-path implementation in `portfolio.py`; do not duplicate benchmark engines.

## PortfolioPath

Dataclass fields:

- `weights_before`: date x canonical-ticker weights, known before each corresponding close-to-close return.
- `gross_returns`, `net_returns`: daily simple Series.
- `turnover`, `costs`: daily fractions of NAV under one documented convention.
- `wealth`, `drawdown`: derived from net returns, with initial wealth 1 included in drawdown calculations.
- `rebalances`: table including decision date, execution timing, training bounds, weights, solver status and constraint feasibility.
- `metadata`: strategy ID, parameters, train/selection/evaluation boundaries, benchmark/rebalancing/cost convention.

```python
build_portfolio_path(asset_returns, strategy_spec, config) -> PortfolioPath
construct_weights(train_asset_returns, constraints, objective) -> pd.Series
```

At close t-1, a decision using data through t-1 can set weights for the t return under the disclosed execution approximation. Costs apply at the same documented rebalance boundary. Never use t's return to determine its own weights. Bootstrap/fixtures can be synthetic; production output cannot.

Core portfolio candidates: constrained minimum variance, equal-weight reference and monthly 60/40 comparison. Show mean-variance/frontier trade-offs and CAPM expected-return assumptions. Reference portfolios may violate proposed mandate constraints: label that and do not recommend them as feasible without checking. A useful minimum-CVaR candidate is optional after this core.

Validate a registered allocation rule, not hindsight-selected final weights. The final proposed allocation is the selected rule applied at the data end. The register distinguishes prior full-sample asset-data diagnostics from still-uncomputed strategy evaluation: do not claim the entire dataset was never seen. Sample covariance ddof=1 is the current configured primary; optional shrinkage requires an explicit dependency/validation decision, not an implicit requirement.

## RiskEstimate and forecast callback

D creates fields:

`model,confidence,horizon_days,var_loss,es_loss,n_obs,sample_start,sample_end,status,reason,diagnostics`

- Values are fractional **one-day simple-return losses**, before transaction costs. USD = loss fraction x portfolio NAV, with USD10M clearly labelled as the mandate scale.
- `status` is `ok`, `warning` or `unavailable`. Unavailable metrics are None, never zero. Nonfinite ES from xi>=1 is explicitly diagnosed rather than exported as a finite number.
- Diagnostics include model units/assumptions, thresholds and exceedance counts where relevant, simulation seed/count, and warnings. A dashboard must not hide diagnostics just because the estimate is numeric.

```python
estimate_risk(train_asset_returns, weights, *, model, confidence, seed) -> RiskEstimate
```

C supplies a registry/callback for `historical`, `parametric_normal`, `monte_carlo_normal`, `evt_pot`. A generic callback has signature:

```python
forecast_fn(train_asset_returns, weights, *, confidence, seed) -> RiskEstimate
```

C forms simple portfolio returns as `train_asset_returns @ weights` for the *exposure being forecast*. All methods compared on the dashboard use identical weights, date window, confidence and horizon. Log returns remain available for statistical diagnostics; simple-return risk models are an explicitly documented aggregation/P&L exception. Do not mix a log-loss quantile with a simple-loss quantile in the same comparison.

WINDOWS: report (1) registered recent-window current risk and (2) a labelled full-history crisis-inclusive fixed-exposure sensitivity. Show each window's dates, counts and actual crisis coverage. Recent 1,260 sessions omit GFC/COVID but include 2022. Never use the final full sample in an earlier rolling forecast. A long-window sensitivity is our strategy choice, not an official fixed-lookback requirement. Both views use matched observations across methods.

EVT confidence support: C2 defines an explicitly labelled empirical-body/GPD-tail model when the requested quantile is below the fitted tail. Do not force a lower threshold merely to populate the 90% selector, extrapolate a GPD into the body or disguise body estimates as pure tail extrapolation. Numerical/fit failures, infinite ES and insufficient data remain legitimate unavailable states with reasons.

For normal loss risk: `VaR=-mu + z_c*sigma`; `ES=-mu + sigma*phi(z_c)/(1-c)`. Multivariate normal MC uses the SAME asset mean/covariance and the same ddof convention as the normal analytic method. Agreement within simulation error is expected.

Historical ES uses the integral of the empirical quantile over the worst `1-c` mass, allowing fractional mass at the boundary. C exports one shared tail-weight helper for B's historical ES contributions. Specify its signature in D0; B uses the helper rather than a different tail definition. Normal/historical VaR quantile conventions must also be stated.

Freeze C's shared helpers in D0: `var.normal_moments(asset_returns) -> (mean_series, covariance_frame)` uses arithmetic sample means and sample covariance with ddof=1; `es.empirical_tail_weights(losses, confidence) -> pd.Series` returns aligned normalized worst-tail weights summing to1, with a defined tie rule. B uses the same moments for normal Euler contributions and the same tail weights for historical ES. Portfolio optimization may separately use shrinkage covariance, explicitly labelled; that must not silently replace the risk estimator's moments.

## Rolling backtest

```python
rolling_backtest(asset_returns, weights_before, forecast_fn, *, confidence, window, seed) -> pd.DataFrame
coverage_tests(backtest_rows) -> pd.DataFrame
basel_traffic_light(backtest_rows_99) -> dict
```

For target date t:

1. Slice exactly the prior `window` observations; assert `train_end < t`.
2. Obtain `weights_before.loc[t]`; build the forecast from the slice and those weights.
3. Realized market loss is `-(weights_before.loc[t] @ asset_returns.loc[t])`.
4. Exceedance is strictly `realized_loss > forecast_var`. Net strategy return including costs is reported separately in performance, so forecasts are not tested against a different P&L definition.

Rows: `date,model,confidence,forecast_var,forecast_es,realized_loss,exceedance,train_start,train_end,status,reason`. Invalid/skipped rows are retained with reasons; do not encode missing forecasts as non-exceedances. D supplies dataset/config/code IDs on persistence.

Required core backtest: the primary model registered before selection/evaluation, at 95% and 99%, with the generic callback engine. Target historical/normal/MC coverage before exposing them as selectable backtest methods; cache forecasts and report actual runtime. Report the longest valid OOS span and the frozen final evaluation span separately, with different purposes clearly labelled. Optional EVT/FHS enters the backtest selector only after its rolling callback is implemented/validated; a risk-only estimate is not silently relabelled as a backtest. Every exposed backtest choice must work or give a genuine sample/fit reason. The official brief requires validation of the chosen model, not daily refitting every extension. Retain legitimate unavailable states rather than fabricating passes.

Basel standard colors are only for 250 consecutive valid one-day 99% forecast/realization pairs: green0-4, yellow5-9, red10+. Do not cherry-pick valid days around missing forecasts. Otherwise return insufficient/not applicable. Display the 99%/250-day diagnostic separately from the sidebar-selected 90%/95% tests. Label this an educational diagnostic, not bank regulatory approval. State small-sample power limitations.

## Risk budgeting, sizing and stress

```python
risk_contributions(train_asset_returns, weights, *, confidence, method) -> pd.DataFrame
compare_feasible_allocations(train_asset_returns, candidates, limits, risk_fn) -> pd.DataFrame
run_stress_tests(asset_returns, weights, scenarios, *, nav) -> pd.DataFrame
```

Contributions include ticker, weight, marginal risk, component risk and percentage contribution plus total/risk-model metadata. B uses homogeneous un-clipped normal VaR/ES formulas or C's exact empirical ES tail weights so Euler allocation is internally consistent. Negative hedge contributions are allowed; percentage contributions are unavailable when total risk is zero.

Position sizing redistributes weights among eligible ETFs while preserving all constraints. Show feasible/infeasible status, expected-return assumption, before/after risk and return sacrificed. Do not silently introduce cash or recommend an infeasible candidate.

Stress: replay GFC2007-10-09 to2009-03-09, COVID2020-02-19 to2020-03-23 and rate shock2022-01-03 to2022-10-14. These exact windows are team choices. Include the pre-window price needed for the first daily return and initial NAV in drawdown. Baseline is a buy-and-hold replay from initial current weights, letting them drift; label it an ex-post scenario, not historical strategy performance. Report scenario total return, maximum drawdown, worst day, USD loss, per-asset P&L contributions and the same calculation for60/40.

One hypothetical shock vector must explicitly name all seven tickers. Example, illustrative and unsigned: SPY/EFA/EEM -25%, AGG -12%, GLD +10%, XLE +20%, XLK -30%. One-step loss is `-weights @ shocks`. Team must justify assumptions. No deterministic scenario loss may be called ES without a specified probability distribution.

## Integration, artifacts and changes

D's `pipeline.py` is the only orchestrator. Library functions do not import Streamlit. Pages do not independently download, optimize, fit EVT or compute alternate versions of metrics. UI test fixtures are explicitly labelled and never enter final exports.

Every result bundle includes dataset ID, config hash, code version, forecast/cost conventions and computation time. Exported memo/tear sheet values must come from the same bundle as the app. Human-written return objectives, horizon, constraints and recommendation remain distinguishable from calculated facts.

The bundle additionally records context-snapshot ID, decision-register version, risk-window ID, EVT body/tail construction and simulation draw count/seed/uncertainty where used. These are future metadata additions coordinated with implementation; no runtime schema is changed by this prompt update. A frozen reference bundle supports offline demonstration while real controls still recompute/retrieve the correct selected configuration.

If a shared interface needs a change: owner writes current contract, proposed change, reason and callers affected into their handoff; D applies it once and announces a new schema version. No parallel ad-hoc edits.
