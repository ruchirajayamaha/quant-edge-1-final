# Portfolio Construction, Provisional Mandate Bounds & Drifting Return Paths (Milestone B1)

## 1. Universe, Core Candidate Rules & Prospective Rule Discipline

All portfolio rules operate on the canonical seven-ETF allocation universe in frozen order:

$$\text{CANONICAL\_TICKERS} = (\text{SPY}, \text{EFA}, \text{EEM}, \text{AGG}, \text{GLD}, \text{XLE}, \text{XLK}),$$

partitioned into five equity ETFs ($\text{EQUITY\_TICKERS} = \{\text{SPY}, \text{EFA}, \text{EEM}, \text{XLE}, \text{XLK}\}$) and two defensive ETFs ($\text{DEFENSIVE\_TICKERS} = \{\text{AGG}, \text{GLD}\}$), with no synthetic eighth cash asset added silently.

### Prospective Rule Validation vs. Ex-Post Weight Selection
In `src/quantedge/portfolio.py`, an investable strategy is validated as a **prospective allocation rule** $\mathcal{R}: \mathcal{I}_{t-1} \mapsto w_{t,\text{target}}$ mapping strictly past market returns through session close $t-1$ to target holdings weights effective across session $t$'s close-to-close simple return. Under the project's governance register (`audit/decision_register/REGISTER.md`):
- Future final proposed weights come from applying the selected rule at the frozen data end (`2026-10-30`) once the selection/evaluation protocol is signed.
- Replaying constant current weights backward through historical crises (Step 8 / `B3`) is an ex-post fixed-exposure stress scenario, **not** an out-of-sample investable performance record.

### Core Step 3 Candidate Rules (`make_core_strategy_specs`)
All candidates run through the **single shared `build_portfolio_path` engine** so rebalance dates, drift mechanics, transaction-cost deductions, wealth compounding, and drawdown accounting are identical across strategies and benchmarks:

1. **Constrained Markowitz Minimum Variance (`objective="min_variance"`):** Minimizes trailing sample return variance $w^\top \hat{\Sigma}_{t-1} w$ over a rolling `504`-session (~2-year) lookback window using `sample_ddof1` covariance subject to all active `PortfolioConstraints`.
2. **Equal-Weight 7-ETF Reference (`objective="equal_weight"`):** Allocates $1/7 \approx 14.2857\%$ to each canonical ETF at every rebalance boundary. Explicitly labelled as an unconstrained reference (`unconstrained_reference_violates_provisional_caps`) because its $5/7 \approx 71.43\%$ equity share exceeds the provisional $35\%$ equity cap.
3. **Canonical Monthly `60/40 SPY/AGG` Reference (`objective="benchmark_60_40"`):** Rebalances monthly to $60\%$ `SPY` and $40\%$ `AGG` ($0\%$ in `EFA, EEM, GLD, XLE, XLK`). Explicitly labelled as an unconstrained reference (`unconstrained_reference_violates_provisional_caps`) because `SPY = 60%` breaches both the provisional $40\%$ single-ETF cap and the provisional $35\%$ total equity cap.
4. **Custom Fixed-Weight Paths (`objective="fixed_weights"`):** Evaluates any fully invested 7-ETF allocation dictionary (such as `config.portfolio.illustrative_weights`, clearly tagged provisional/illustrative) under identical monthly rebalancing, drift, and cost rules while checking and labelling constraint compliance. Conflicting specifications (e.g., attaching a `fixed_weights` override dictionary to `objective="min_variance"` or `"equal_weight"`, or passing a non-`60/40` dictionary to `"benchmark_60_40"`) are rejected upfront with `ValueError` so an unoptimized fixed vector can never be mislabelled as minimum variance or bypass `covariance_estimator` validation.

---

## 2. Markowitz Mean-Variance Optimization, CAPM Framing & Endowment Cash-Flow Context

### Constrained Minimum-Variance Optimization & Numerical Verification
At decision close $t-1$, given the strictly prior $T \times 7$ simple-return matrix $X_{t-1}$ ($T = 504$ by default, $T \ge 2$ required), `construct_weights` forms the unbiased (`ddof=1`) sample covariance matrix on an isolated C-contiguous `float64` buffer:

$$\hat{\Sigma}_{t-1} = \frac{1}{T - 1} (X_{t-1} - \mathbf{1}\bar{x}_{t-1}^\top)^\top (X_{t-1} - \mathbf{1}\bar{x}_{t-1}^\top).$$

Isolating the training buffer in C-order guarantees 0-ULP bit-for-bit invariance of $\hat{\Sigma}_{t-1}$ and resulting weights regardless of parent `DataFrame` slicing or future rows. Before and after optimization, `_solve_min_variance_from_covariance` enforces five strict numerical guards:

1. **Symmetry check:** Verifies $\max_{i,j} |\hat{\Sigma}_{ij} - \hat{\Sigma}_{ji}| \le 10^{-10} \max(1, \|\hat{\Sigma}\|_\infty)$ before applying exact symmetrization $\Sigma = \frac{1}{2}(\hat{\Sigma} + \hat{\Sigma}^\top)$.
2. **Eigenvalue / PSD check:** Computes ascending real eigenvalues $\lambda_1 \le \dots \le \lambda_7$ via `numpy.linalg.eigvalsh` and rejects indefinite matrices ($\lambda_1 < -10^{-11} \max(1, \max_k |\lambda_k|)$) with `PortfolioOptimizationError`, while permitting rank-deficient positive semi-definite sample covariances when $2 \le T \le 7$.
3. **HiGHS Chebyshev linear feasibility pre-check:** Solves a 1-slack Chebyshev center linear program via `scipy.optimize.linprog(method="highs")` over the exact linear constraint polytope $\mathcal{P}$. Empty/infeasible constraint sets fail deterministically before nonlinear optimization starts, and feasible sets obtain a well-centered interior warm start $w_0 \in \mathcal{P}$.
4. **Scale-normalized SLSQP solve:** Normalizes $\tilde{\Sigma} = \Sigma / \max(\operatorname{tr}(\Sigma)/7, \lambda_7)$ so objective values and analytical gradients $\nabla f(w) = 2\tilde{\Sigma} w$ are $\mathcal{O}(1)$ independent of daily variance scale ($\sim 10^{-5}$), preventing premature `ftol` termination in `scipy.optimize.minimize(..., method="SLSQP", ftol=1e-14)`.
5. **Raw feasibility & Frank-Wolfe KKT duality-gap verification (no silent repair):** Raw solver output $w^*$ is checked directly via `check_weight_feasibility(w^*, constraints, tol=1e-7)` **without clipping negative weights or renormalizing sums**, and a 7-variable HiGHS LP computes the exact convex Frank-Wolfe duality gap for $f(w) = w^\top \tilde{\Sigma} w$ with gradient $\nabla f(w) = 2\tilde{\Sigma} w$ ([Jaggi 2013, Section 2, Eq. 2](https://proceedings.mlr.press/v28/jaggi13.pdf)):

$$0 \le f(w^*) - \min_{v \in \mathcal{P}} f(v) \le \max_{v \in \mathcal{P}} \; (2\tilde{\Sigma} w^*)^\top (w^* - v) = \text{FW\_gap}(w^*).$$

Because $f(v) - f(w^*) = (2\tilde{\Sigma} w^*)^\top (v - w^*) + (v - w^*)^\top \tilde{\Sigma} (v - w^*) \ge (2\tilde{\Sigma} w^*)^\top (v - w^*)$ for $\tilde{\Sigma} \succeq 0$, the primal suboptimality $f(w^*) - f_{\text{opt}}$ is upper-bounded by $\text{FW\_gap}(w^*)$ directly (without an extra factor of $2$; e.g., for $f(x) = x^2$ on $[1, 2]$ at $x = 2$, $f(2) - f(1) = 3 \le \text{FW\_gap}(2) = 4$, whereas $2(f(2) - f(1)) = 6 \not\le 4$). Any candidate failing `SLSQP` convergence (`ftol = 1e-14`), raw feasibility (`tol = 1e-7`), or $\text{FW\_gap}(w^*) \le 10^{-7}$ raises `PortfolioOptimizationError`.

### Why Minimum Variance Is Primary in Step 3 & Mean-Variance / CAPM Framing
In classical Markowitz mean-variance theory, tracing efficient trade-offs $\min_w \{ w^\top \Sigma w - \gamma \mu^\top w \}$ requires estimating both expected returns $\mu$ and covariances $\Sigma$. At daily/monthly horizons, sample mean returns $\hat{\mu}$ exhibit large standard errors ($\text{SE}(\hat{\mu}) = \sigma / \sqrt{T_{\text{years}}}$), causing unconstrained mean-seeking optimizers to act as "error maximizers" concentrating into recent winners. Minimum variance isolates the covariance structure $\Sigma$—which is estimated far more reliably at daily frequency—while avoiding noisy sample-mean extrapolation. (Optional covariance shrinkage remains a deferred sensitivity rather than a reason to add `scikit-learn` to the core stack.)

When expected-return trade-offs are evaluated in committee decision analysis (Steps 4 and 8), equilibrium **CAPM framing** separates systematic market exposure from sample-mean noise by declaring an explicit forward market risk premium $\text{ERP} = \mathbb{E}[R_m] - R_f$ relative to market proxy `SPY`:

$$\mathbb{E}[R_i] - R_f = \beta_{i,m} \big(\mathbb{E}[R_m] - R_f\big), \qquad \beta_{i,m} = \frac{\operatorname{Cov}(R_i - R_f, R_m - R_f)}{\operatorname{Var}(R_m - R_f)}.$$

Under CAPM, defensive assets with low or near-zero equity beta (`AGG`, `GLD`) lower portfolio variance and equity beta $\beta_p = \sum_{i=1}^7 w_i \beta_{i,m}$, trading lower equilibrium expected return for reduced systematic drawdown exposure.

### Endowment Cash-Flow Identity Context (`PENDING` Human Inputs)
Connecting portfolio nominal total return $R$ to an endowment spending rule requires human governance choices for spending rate $s$, non-embedded advisory/operating fee rate $f$, forward inflation assumption $i$, and target real corpus growth $g$ (`audit/decision_register/REGISTER.md`, all currently `PENDING`):
- **Post-return NAV deduction basis:** $(1 + R)(1 - s - f) = (1 + i)(1 + g)$.
- **Beginning-of-year NAV deduction basis:** $1 + R - s - f = (1 + i)(1 + g)$.

ETF expense ratios are already embedded in observed adjusted-close NAV returns and must not be subtracted a second time in $f$; moreover, an arithmetic expected-return assumption $\mathbb{E}[R]$ exceeds compounded geometric growth by approximately $\frac{1}{2}\sigma_p^2$ under volatility drag.

---

## 3. Provisional Mandate Constraints & LP-Implied Bounds Map

All numerical mandate constraints in `config.yaml` (`portfolio.constraints`) are **provisional team assumptions** (`PROVISIONAL_TEAM_INPUT_REQUIRED`), not client-supplied rules from the competition brief. Solving the exact coordinate extremes over the linear constraint polytope via `compute_implied_weight_bounds` reveals tight interaction bounds:

| Asset / Group | Category | Configured Min | Configured Max | LP-Implied Min | LP-Implied Max | Binding Interaction Mechanism |
|---|---|---:|---:|---:|---:|---|
| `SPY` | Equity | `0.00` | `0.40` | **`0.00`** | **`0.35`** | Tightened from `0.40` to `0.35` by `max_equity_weight = 0.35` |
| `EFA` | Equity | `0.00` | `0.40` | **`0.00`** | **`0.35`** | Tightened from `0.40` to `0.35` by `max_equity_weight = 0.35` |
| `EEM` | Equity | `0.00` | `0.40` | **`0.00`** | **`0.35`** | Tightened from `0.40` to `0.35` by `max_equity_weight = 0.35` |
| `AGG` | Defensive | `0.00` | `0.40` | **`0.25`** | **`0.40`** | `AGG + GLD >= 0.65` and `GLD <= 0.40` force `AGG >= 0.25` |
| `GLD` | Defensive | `0.00` | `0.40` | **`0.25`** | **`0.40`** | `AGG + GLD >= 0.65` and `AGG <= 0.40` force `GLD >= 0.25` |
| `XLE` | Equity | `0.00` | `0.40` | **`0.00`** | **`0.35`** | Tightened from `0.40` to `0.35` by `max_equity_weight = 0.35` |
| `XLK` | Equity | `0.00` | `0.40` | **`0.00`** | **`0.35`** | Tightened from `0.40` to `0.35` by `max_equity_weight = 0.35` |
| `EQUITY_TOTAL` | Group (`5` ETFs) | `0.00` | `0.35` | **`0.20`** | **`0.35`** | `AGG <= 0.40` and `GLD <= 0.40` cap defensive sum at `0.80` (`1 - 0.80 = 0.20`) |
| `DEFENSIVE_TOTAL` | Group (`AGG + GLD`) | `0.40` | `0.80` | **`0.65`** | **`0.80`** | `1 - max_equity_weight = 0.65`, making `min_defensive_weight = 0.40` redundant |

**Governance interpretation:** Under these provisional caps, every feasible portfolio holds `65%–80%` combined in `AGG + GLD`, at least `25%` in **each** of `AGG` and `GLD`, and `20%–35%` in total equities. This narrow feasible corridor reflects a conservative defensive bias; it is **not** automatic proof of safety during simultaneous bond/gold/rate sell-offs (e.g., the 2022 rate shock, to be stress-tested in Step 8).

---

## 4. Prospective Timing, Holdings Drift, Turnover, 5 bps Costs & Drawdown Equations

For an input return table indexed by trading sessions $t_0, t_1, \dots, t_{N-1}$ with estimation burn-in $W$ (`504` for core matched comparisons, or `0` when `estimation_window_days=None` on non-estimated reference slices), active out-of-sample sessions run from $k = W$ to $N - 1$:

1. **Rebalance schedule (`rebalance_frequency = "M"`):**
   - **Initial entry ($k = W$):** Enters from $100\%$ cash ($w_{t_W,\text{pre}} = \mathbf{0}$). When $W > 0$, target weights are decided at session close $t_{W-1}$ using strictly `iloc[0:W]`.
   - **Scheduled monthly rebalances ($k > W$):** Triggers whenever $(t_k.\text{year}, t_k.\text{month}) \neq (t_{k-1}.\text{year}, t_{k-1}.\text{month})$. Target weights are decided at prior month-end close $t_{k-1}$ using strictly `iloc[k - W : k]` (`train_end = t_{k-1} < effective_date = t_k`) and set `weights_before.loc[t_k]`.
   - **Non-rebalance sessions:** No trades execute (`turnover = 0`, `cost = 0`), and `weights_before.loc[t_k]` equals the prior session's end-of-day drifted weights $w_{t_{k-1}+}$.

2. **Turnover & `5.0` bps one-way leg-notional transaction cost:**
   Let $\Delta w_{t_k} = w_{t_k,\text{target}} - w_{t_k,\text{pre}}$ on rebalance sessions (and $\Delta w_{t_k} = \mathbf{0}$ otherwise). We define `turnover` everywhere as total one-way order notional traded across buy and sell legs as a fraction of pre-trade NAV:

   $$\text{turnover}_{t_k} = \sum_{i=1}^{7} \left| w_{i,t_k,\text{target}} - w_{i,t_k,\text{pre}} \right|, \qquad \text{half\_turnover}_{t_k} = \frac{1}{2}\text{turnover}_{t_k}.$$

   Each buy leg and each sell leg pays `transaction_cost_bps_one_way = 5.0` bps ($c = 0.0005$):

   $$\text{cost}_{t_k} = \frac{5.0}{10{,}000} \times \text{turnover}_{t_k} = 0.0005 \times \text{turnover}_{t_k}.$$

   - *Initial investment from 100% cash:* $w_{t_W,\text{pre}} = \mathbf{0} \implies \text{turnover}_{t_W} = \sum_i w_{i,t_W,\text{target}} = 1.0 \implies \text{cost}_{t_W} = 0.0005$ (`5.0` bps, or USD `5,000` on USD `10,000,000`).
   - *Interior rebalance swapping fraction $x$ out of one ETF into another:* Executes $x$ sell notional + $x$ buy notional $\implies \text{turnover} = 2x$, $\text{half\_turnover} = x$, and $\text{cost} = 0.0005 \times 2x$ (`5` bps on the sell leg + `5` bps on the buy leg).

3. **Gross return, multiplicative net return & natural holdings drift:**
   With pre-return weights $w_{t_k-} = \text{weights\_before}[t_k]$ and simple asset returns $r_{t_k}$:

   $$R_{p,t_k}^{\text{gross}} = \sum_{i=1}^{7} w_{i,t_k-} \, r_{i,t_k}, \qquad R_{p,t_k}^{\text{net}} = (1 - \text{cost}_{t_k})\big(1 + R_{p,t_k}^{\text{gross}}\big) - 1,$$

   $$w_{i,t_k+} = \frac{w_{i,t_k-}(1 + r_{i,t_k})}{1 + R_{p,t_k}^{\text{gross}}}.$$

4. **Wealth & initial-wealth-inclusive drawdown:**
   Starting from pre-entry capital $W_{\text{init}} = 1.0$:

   $$W_{t_k} = \prod_{s=W}^{k} \big(1 + R_{p,t_s}^{\text{net}}\big), \qquad \text{Peak}_{t_k} = \max\!\Big(1.0, \; \max_{W \le s \le k} W_{t_s}\Big), \qquad \text{DD}_{t_k} = \frac{W_{t_k}}{\text{Peak}_{t_k}} - 1.$$

   Including `1.0` inside $\text{Peak}_{t_k}$ ensures an immediate loss on the first invested session registers accurately as a negative drawdown rather than being masked as `0.0`.

---

## 5. Hand-Checkable Viva Walkthrough (4-Session Drift, Rebalance & Cost Example)

Consider the `60/40 SPY/AGG` rule (`estimation_window_days=None`, `rebalance_frequency="M"`, `5.0` bps one-way cost) over four sessions crossing the January/February month boundary (verified to `1e-14` in `tests/test_b_portfolio.py::test_hand_calculated_drift_turnover_5bps_costs_and_initial_wealth_drawdown`):

1. **Session 0 (`2024-01-30`, initial entry from cash):**
   - Pre-return weights: $w_{\text{SPY}} = 0.60$, $w_{\text{AGG}} = 0.40$ (all other ETFs `0.0`).
   - Initial entry from cash: $\text{turnover}_0 = |0.60 - 0| + |0.40 - 0| = 1.0 \implies \text{cost}_0 = 0.0005$.
   - Realized asset returns: $r_{\text{SPY}} = -5.0\%$, $r_{\text{AGG}} = +2.5\%$.
   - Gross return: $R_{p,0}^{\text{gross}} = 0.60(-0.05) + 0.40(0.025) = -0.03 + 0.01 = -0.020000$ (`-2.00%`).
   - Net return: $R_{p,0}^{\text{net}} = (1 - 0.0005)(1 - 0.02) - 1 = 0.9995 \times 0.98 - 1 = -0.020490$ (`-2.049%`).
   - Wealth & drawdown: $W_0 = 0.979510$; since $\text{Peak}_0 = \max(1.0, 0.979510) = 1.0$, $\text{DD}_0 = -0.020490$.
   - End-of-day drifted weights entering `2024-01-31`:
     $$w_{\text{SPY},0+} = \frac{0.60 \times 0.95}{0.98} = \frac{57}{98} \approx 0.581633, \qquad w_{\text{AGG},0+} = \frac{0.40 \times 1.025}{0.98} = \frac{41}{98} \approx 0.418367.$$

2. **Session 1 (`2024-01-31`, interior month-end drift session — no trade during session 1):**
   - `weights_before` equals $(57/98, \, 41/98)$, $\text{turnover}_1 = 0$, $\text{cost}_1 = 0$.
   - Realized asset returns: $r_{\text{SPY}} = +10.0\%$, $r_{\text{AGG}} = 0.0\%$.
   - Gross & net return: $R_{p,1}^{\text{gross}} = R_{p,1}^{\text{net}} = \frac{57}{98}(0.10) + \frac{41}{98}(0) = \frac{5.7}{98} \approx +0.058163$.
   - End-of-day drifted weights at January close (before the February 1 rebalance):
     $$w_{\text{SPY,pre}} = \frac{(57/98) \times 1.10}{1 + 5.7/98} = \frac{62.7}{103.7} \approx 0.604629, \qquad w_{\text{AGG,pre}} = \frac{41.0}{103.7} \approx 0.395371.$$

3. **Session 2 (`2024-02-01`, first session of February — scheduled monthly rebalance back to `60/40`):**
   - Trade vector: $\Delta w_{\text{SPY}} = 0.60 - \frac{62.7}{103.7} = -\frac{0.48}{103.7}$, $\Delta w_{\text{AGG}} = 0.40 - \frac{41.0}{103.7} = +\frac{0.48}{103.7}$.
   - Turnover: $\text{turnover}_2 = \left|-\frac{0.48}{103.7}\right| + \left|+\frac{0.48}{103.7}\right| = \frac{0.96}{103.7} \approx 0.009257$ ($\text{half\_turnover}_2 = \frac{0.48}{103.7} \approx 0.004629$).
   - Cost: $\text{cost}_2 = 0.0005 \times \frac{0.96}{103.7} \approx 4.6287 \times 10^{-6}$ (`0.046` bps of NAV).
   - `weights_before` resets to $(0.60, \, 0.40)$ for `2024-02-01`'s return ($+1.0\%$ `SPY`, $-0.5\%$ `AGG` $\implies R_{p,2}^{\text{gross}} = +0.004$), and drifts again entering `2024-02-02`.

---

## 6. Rebalance-Target vs. Drifted-Holdings Scope, Development Verification & Limitations

- **Rebalance-target enforcement scope vs. pre-return drifted-holdings monitoring:** `PortfolioConstraints` in Step 3 apply strictly to **rebalance targets** (`constraint_enforcement_scope = "rebalance_targets_only"`, tracked by `mandate_feasible_all_rebalances` and `rebalance_target_compliance_status`). Between monthly rebalances, holdings drift naturally without clipping or unapproved intraday/daily rebalancing; `summarize_pre_return_holdings_compliance` monitors all daily pre-return `weights_before` rows separately (`mandate_feasible_all_pre_return_sessions`, `pre_return_holdings_compliance`, and scope-qualified `mandate_compliance_status`). Whether the investor mandate requires rebalance-date caps or continuous daily cap maintenance with drift bands is a separate `PENDING` human governance choice in `audit/decision_register/REGISTER.md`.
- **Development-only real-data smoke verification (`r3`):** Using `load_data(config, offline=True)` on `qe1_20050101_20261030_r3_6c4633a7ba` sliced strictly to `2005-01-04..2016-12-30` (`3,020` return sessions), all three core candidates (`min_variance`, `equal_weight`, `benchmark_60_40`) produce `2,516` active out-of-sample sessions (`2007-01-05` through `2016-12-30`) across `120` rebalance events (`1` initial entry + `119` monthly boundaries). For `min_variance`, `120 / 120` rebalance targets satisfy all provisional caps (`AGG, GLD in [0.25, 0.40]`, `equities in [0.20, 0.35]`), while natural inter-rebalance drift causes `1,439 / 2,516` daily pre-return sessions (`2007-01-08` first breach, `2016-12-28` last breach) to exceed a rebalance cap: `1,010` sessions exceed the `40%` single-ETF upper cap (`AGG`: `994` sessions, peak `45.1393%` on `2008-10-23`; `GLD`: `17` sessions, peak `41.0441%`) and `617` sessions exceed the `35%` equity-group cap (peak `37.2983%` on `2015-02-23`), with `0` breaches of `fully_invested`, `long_only`, or `min_defensive_weight` (minimum defensive share `62.7017%`). Path-wide compliance is therefore reported cleanly as `rebalance_targets_feasible_with_post_trade_drift_cap_breaches_provisional`. Selection (`2017-01-03..2020-12-31`) and evaluation (`2021-01-04..2026-10-30`) strategy performance remain uncomputed and uninspected.
- **Disclosed limitations:**
  1. **Close-to-next-session execution approximation:** Under `rebalance_decided_at_period_end_close_applied_next_session`, a decision computed from period-end close prices $P_{t-1}$ sets pre-return weights for the close-to-close return $P_t / P_{t-1} - 1$ at flat `5.0` bps one-way leg cost, abstracting from overnight gap slippage between close $t-1$ and next-day execution or size-dependent market impact.
  2. **Inter-rebalance drift beyond target caps:** Because monthly targets often bind at `40.0%` (`AGG` or `GLD`) or `35.0%` (equities), any positive relative asset move on subsequent days pushes drifted pre-return weights slightly above the rebalance cap until the next month-start rebalance unless an explicit interior buffer or drift-band policy is later adopted by the human team.
  3. **Sample covariance regime lag:** A rolling `504`-session equal-weighted sample covariance reacts gradually to sudden volatility spikes and forgets crises after ~2 years; tail-risk models (`VaR`, `ES`, `EVT`) and rolling validation in Steps 5–7 address non-normality and crisis tail thickness directly.
  4. **Pending KPI/risk comparisons & human governance:** Sharpe, Sortino, CAPM alpha/beta, VaR/ES, and stress comparisons remain deferred to Steps 4–8 (`kpis.py`, `var.py`, `es.py`, `risk_budget.py`, `stress.py`) so stubbed metrics are never duplicated or fabricated. All mandate constraints and return/risk targets remain provisional awaiting human sign-off in `audit/decision_register/REGISTER.md`.
