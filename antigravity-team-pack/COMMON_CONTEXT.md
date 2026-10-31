# Shared project context - give once to every session

We are implementing the Quant Edge 1.0 competition brief for a conservative USD 10M university endowment. Build clear Python 3.11 analytics and a Streamlit interface; the team must understand and defend every material result. The official challenge PDF is authoritative. This pack corrects and reduces the earlier Claude implementation plan. It does not reduce mandatory competition requirements.

Universe, in canonical order: SPY, EFA, EEM, AGG, GLD, XLE, XLK. Only these ETFs are allocation assets. Approved core sources: Yahoo Finance via yfinance and FRED; optional World Bank/IMF context must be disclosed. Use adjusted prices, a 2005-01-01 requested start, one frozen actual data end date and one shared snapshot. Never invent results or silently change sources. DTB3 is the team's chosen risk-free proxy, not an exact daily investment return.

Required core:
- Markowitz mean-variance, CAPM and interpreted Sharpe, Sortino, Treynor, Jensen alpha, Information Ratio, Max Drawdown and Calmar.
- Same-portfolio historical, parametric-normal and seeded normal Monte Carlo VaR at 95% and 99%; ES; unconditional POT-GPD EVT with justified threshold and limitations.
- Strictly out-of-sample rolling validation of a selected primary VaR model, including Kupiec, Christoffersen independence and Basel traffic light.
- Marginal/component VaR and ES contributions, feasible position-sizing alternatives, historical crisis paths plus one explicit hypothetical scenario, and quantified return/risk trade-offs.
- Sidebar confidence 90/95/99, method and backtest range; portfolio, risk, backtest, stress, assumptions/limitations and recommendation views.
- Reproducible repo, one-command app launch after setup, actual 7-15-page memo, actual one-page tear sheet and honest AI disclosure. A live pitch/deck is required if selected among the final five teams.

Conventions:
- Prices/returns share sorted, unique trading-date indices. Returns and weights are fractions, not percentages. Use simple asset returns for aggregation and simple portfolio losses for committee risk comparisons; also compute log returns and run statistical diagnostics on them. Explain each simple-return exception.
- Portfolio return at t uses weights BEFORE the return at t; let weights drift between documented rebalances. Never sum weighted asset log returns as the exact portfolio log return.
- Loss = negative simple portfolio return. Positive risk amounts represent losses. Never use abs() to hide a sign error. Preserve and explain any nonpositive loss quantile rather than misreporting a gain as loss.
- No estimator, optimizer, threshold selector or regime rule forecasting day t may inspect day t or later. Freeze development/validation/evaluation split before evaluating results. Do not choose the best model/strategy from the reported final test sample and call it an untouched test.
- Flag suspicious data; retain outliers unless an explicit, reproducible, logged correction is justified. Missing-data exclusions must be counted separately. No price forward-fill by default; no risk-free backfill from future values.
- Explain units, horizon, samples, cost assumptions and model failures in outputs. Unsupported calculations return unavailable with a reason, not a fabricated zero or silent substitute.

Engineering:
- All analytical logic in typed, documented src/quantedge functions; I/O stays in data/pipeline adapters; Streamlit calls the library. Formulas and assumptions belong in docstrings.
- D alone owns shared schemas, config, dependency files, pipeline, app integration and top-level docs. A/B/C edit only their owned files and uniquely named tests/docs/handoffs. Request shared changes through handoff notes.
- Relevant numeric tests with known answers, edge cases and explicit no-look-ahead checks are required. Do not create tests just to mirror implementation. Do not claim tests or human reviews ran if they did not.
- Free libraries only. D must include actual runtime dependencies, including yfinance, PyYAML and a parquet engine if used; verify compatible pinned versions on Python 3.11. Do not invent a lockfile or claim clean-install success without running it.
- Cache by dataset ID, config hash, model parameters, seed and code version. On network failure, use matching cached data with its date/banner; if no cache exists, display unavailable and retrieval instructions.
- Every role supplies its methodology, limitations, test evidence and AI-generated-component record. Human validation remains PENDING until performed by the team.

Scope and working style:
- Core first. Extra optimizers, Student-t variants, GARCH, conditional EVT, automatic threshold GOF, formal ES backtests, regime overlays, 10-day scaling and reverse stress are deferred. One justified extension may be selected after the core passes.
- Inspect only your owned files and named interfaces. Do the next named milestone, run relevant checks and stop at its checkpoint. A milestone checkpoint is not a new request for user permission; continue when its inputs are available.
- Do not repeatedly restate the whole project, ask five general questions or audit the entire repo. Use documented provisional choices where the brief allows discretion. Report a genuine blocker and continue independent work.
- End each milestone with: changed files; tests actually run and outcome; produced dataset/artifact IDs; unresolved issues; next milestone. Update your handoff file so a new session can resume without chat history.
- Do not select a final investment recommendation or fabricate team judgement. Produce evidence and alternatives for the humans to evaluate and sign off.
