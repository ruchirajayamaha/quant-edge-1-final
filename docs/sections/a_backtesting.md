# Rolling VaR validation — Step 6 / A3

Scope: **development OOS research**, not final holdout validation or an approved
investment recommendation. The inherited primary model is Historical VaR, with
Parametric Normal as a matched comparison. Both use the previous 500 NYSE
asset-return sessions and 95% / 99% confidence. The protocol was appended to the
decision register before these development results were computed. Human economic
choices, independent validation and final evaluation-protocol approval remain pending.

## Forecast and realized-loss timing

For target session t, the callback receives exactly the preceding 500 sessions,
ending strictly before t, and the portfolio's weights known before t's return.
The accepted monthly portfolio engine supplies those weights, including natural
drift between rebalances. Earlier asset observations remain available for risk
training even when the portfolio's active weights start later. Backtesting does
not reoptimize weights or reuse terminal-development weights across history.

The forecast and realization use the same exposure and one-day pre-cost simple-loss
definition: `L_t = -(weights_before[t] @ asset_returns[t])`. Costs remain in the
separately reported net performance path. An exception is strictly `L_t > VaR_t`;
equality is not an exception, and negative loss quantiles are preserved.

For example, at SPY weight 0.3, AGG weight 0.4 and GLD weight 0.3, daily simple
returns -2%, +0.2%, +1% imply gross return -0.22% and gross loss +0.22%.
A forecast VaR of 0.22% is not exceeded; a forecast of 0.20% is exceeded.
Charging a trading cost on one rebalance day does not change this gross-risk test.

Targets include every expected NYSE session between the first and last supplied
weights dates. Missing weights, unavailable or failed forecasts, missing returns
and incomplete 500-session histories remain explicit skipped rows with reasons
and nullable exceptions. Weekends and NYSE holidays are not gaps. A finite warning
VaR can remain eligible even when ES is unavailable. ES forecasts are persisted,
but these exception-count tests validate VaR; they are not an ES calibration test.

## Likelihood tests and finite-sample conventions

Write q = 1-confidence, N for valid pairs, x for exceptions and phat = x/N.
The Kupiec unconditional-coverage statistic is twice the difference between the
Bernoulli log likelihood at phat and at q, compared with asymptotic chi-square(1).
Terms with a zero count contribute zero, including at boundary probabilities.
Zero or all exceptions therefore produce a defined UC statistic rather than a
logarithm error. Skipped observations do not enter N or become non-exceptions.

For independence, count `n00, n01, n10, n11` only across consecutive eligible NYSE
sessions. Never join across a failed row or missing date. The two-state Markov
alternative estimates p01 and p11 separately; the iid null estimates the pooled
exception probability of transition destinations. `LR_ind = 2*(ll_markov-ll_iid)`
uses asymptotic chi-square(1) when identifiable. Unvisited previous states and
insufficient transitions yield explicit unavailable reasons instead of p=1.

Conditional coverage uses the same first-state-conditioned transition likelihood
for its null and alternative: `LR_cc = 2*(ll_markov-ll_transition_null(q))`, with
asymptotic chi-square(2). Its additive identity is
`LR_cc = LR_ind + LR_uc_transition`, where `LR_uc_transition` omits the first
observation. The separately reported headline Kupiec statistic uses all N valid
observations, so it need not add exactly to LR_cc. Transition UC statistics and
test-specific availability are included in exported diagnostics. Conditional
coverage is unavailable for disconnected valid runs under this implementation's
declared contiguous-sample policy.

Expected exception counts, skipped counts and warnings accompany the p-values.
Sparse tails and boundary MLEs weaken asymptotic approximations. A rejection is
evidence against the tested calibration/independence assumption, and a non-rejection
does not prove safety, validate the return model or establish mandate compliance.
No model, lookback or allocation is retuned to improve these test outcomes.

## Educational Basel traffic-light diagnostic

The endpoint is the latest supplied target date, including a failed final target.
The last 250 expected NYSE sessions ending there must all have valid one-day 99%
pairs. The routine never drops gaps or searches backwards for an older usable or
friendlier block. Green corresponds to 0–4 exceptions, yellow to 5–9 and red to
10 or more; the expected count at 99% is 2.5. Inappropriate confidence, mixed
groups, insufficient history and gaps give explicit unavailable/not-applicable
states. This historical educational diagnostic is not bank regulatory approval.

## Reproducibility and sources

The public APIs and shared column schemas are frozen. Generic callbacks use the
accepted Step 5 estimators; no duplicate risk engine is introduced. The seed is
reused deterministically at each origin (common random numbers), so appending
future targets cannot change earlier forecasts. Daily MC and EVT validation are
not implemented or exposed as completed rolling results in this step.

The saved strict JSON is the authority for CSV, figures and summary text. Source
and artifact SHA-256 hashes identify the exact computation and exported preview.
All inputs and observations in this step stop at 2016-12-30; 2017–2026 strategy
selection/evaluation outcomes remain uncomputed.

Method sources: [Christoffersen (1998), Evaluating Interval Forecasts](https://users.ssc.wisc.edu/~bhansen/718/Christoffersen1998.pdf)
and [Basel Committee (January 1996), supervisory backtesting framework](https://www.bis.org/publ/bcbs22.pdf).
The conventions and limitations above state the specific implementation choices.

---

## Hand-checkable likelihood example (`tests/test_a_backtest_diagnostics.py`)

Consider a 12-session 95% ($q = 0.05$) exception indicator sequence on consecutive NYSE sessions:
$$I = (0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0), \qquad N = 12,\quad x = 5,\quad \hat{p} = \frac{5}{12}.$$
- **All-$N$ Kupiec unconditional coverage ($\text{df}=1$):**
  $$\ell_0(q) = 7\log(0.95) + 5\log(0.05) = -15.337218,\quad \ell_1(\hat{p}) = 7\log(7/12) + 5\log(5/12) = -8.150323,$$
  $$\text{LR}_{\text{uc}} = 2(\ell_1 - \ell_0) = 14.373790,\qquad p_{\text{uc}} = 1.4987 \times 10^{-4}.$$
- **First-state-conditioned transition counts across the $T_{\text{trans}} = 11$ consecutive pairs:**
  $$(n_{00}, n_{01}, n_{10}, n_{11}) = (3, 3, 3, 2), \qquad \hat{\pi}_{01} = \frac{3}{6} = 0.50,\quad \hat{\pi}_{11} = \frac{2}{5} = 0.40,\quad \hat{\pi}_{\text{trans}} = \frac{5}{11}.$$
- **Christoffersen Markov independence ($\text{df}=1$) and transition-conditioned conditional coverage ($\text{df}=2$):**
  $$\ell_{\text{markov}} = 3\log(0.5) + 3\log(0.5) + 3\log(0.6) + 2\log(0.4) = -7.523989,$$
  $$\ell_{\text{iid}} = 6\log(6/11) + 5\log(5/11) = -7.589265,\qquad \ell_{\text{trans},0}(0.05) = 6\log(0.95) + 5\log(0.05) = -15.285925,$$
  $$\text{LR}_{\text{ind}} = 2(\ell_{\text{markov}} - \ell_{\text{iid}}) = 0.130552 \ (p_{\text{ind}} = 0.7179),\qquad \text{LR}_{\text{uc,transition}} = 2(\ell_{\text{iid}} - \ell_{\text{trans},0}) = 15.393320,$$
  $$\text{LR}_{\text{cc}} = 2(\ell_{\text{markov}} - \ell_{\text{trans},0}) = \text{LR}_{\text{ind}} + \text{LR}_{\text{uc,transition}} = 15.523872 \ (p_{\text{cc}} = 4.2563 \times 10^{-4}).$$

---

## Development OOS research results (`2007-01-05` to `2016-12-30`, `min_variance`)

- **Persisted authority:** `results/step6_backtest_preview/backtest_results.json` (strict RFC 8259 JSON, `allow_nan=False`)
- **Dataset & config:** `qe1_20050101_20261030_r3_6c4633a7ba` | `config_hash = 587ddbe363589fb6956c23c5fe8b2b544bac81d9224a0b4bb59f60f5fbc0a017`
- **Sample structure:** `3,020` development asset-return sessions (`2005-01-04..2016-12-30`). The accepted monthly-rebalanced `min_variance` path has `2,516` active pre-return weight sessions (`2007-01-05..2016-12-30`). Because full prior asset-return history (`2005-01-04..2007-01-04`, `504` sessions $\ge 500$) is preserved for risk training warmup, the first target date `2007-01-05` trains on `2005-01-10..2007-01-04` (`500` sessions) and all `2,516` active sessions are eligible (`n_valid = 2,516`, `n_skipped = 0`).
- **Actual elapsed wall-clock runtime:** `22.398 s` total in `scripts/record_step6_backtest_results.py` (`historical 95%`: `4.724 s`, `historical 99%`: `4.586 s`, `parametric_normal 95%`: `5.944 s`, `parametric_normal 99%`: `5.833 s`).

### 1. Coverage & Markov transition summary (`2007-01-05..2016-12-30`, $N = 2{,}516$, $T_{\text{trans}} = 2{,}515$, `valid_runs = 1`)

| Model | Confidence | `n_valid` | `n_skipped` | Exceptions (`x`) | Expected (`N*q`) | Observed Rate | `LR_uc` (`p_uc`) | Transitions `(n00, n01, n10, n11)` | `LR_ind` (`p_ind`) | `LR_uc_trans` (`p_uc_trans`) | `LR_cc` (`p_cc`) | Status |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---|
| `historical` | `0.95` | `2,516` | `0` | `127` | `125.80` (`5.00%`) | `5.0477%` | `0.0120` (`0.9127`) | `(2275, 113, 114, 13)` | `6.0692` (`0.0138`) | `0.0005` (`0.9818`) | `6.0697` (`0.0481`) | `ok` |
| `historical` | `0.99` | `2,516` | `0` | `32` | `25.16` (`1.00%`) | `1.2719%` | `1.7296` (`0.1885`) | `(2454, 29, 29, 3)` | `7.2378` (`0.0071`) | `1.7351` (`0.1878`) | `8.9729` (`0.0113`) | `warning` |
| `parametric_normal` | `0.95` | `2,516` | `0` | `127` | `125.80` (`5.00%`) | `5.0477%` | `0.0120` (`0.9127`) | `(2278, 110, 111, 16)` | `11.8642` (`5.72e-4`) | `0.0005` (`0.9818`) | `11.8647` (`0.0027`) | `ok` |
| `parametric_normal` | `0.99` | `2,516` | `0` | `53` | `25.16` (`1.00%`) | `2.1065%` | `23.6062` (`1.18e-6`) | `(2416, 46, 46, 7)` | `15.3308` (`9.02e-5`) | `23.6287` (`1.17e-6`) | `38.9595` (`3.47e-9`) | `ok` |

### 2. Latest 250-session 99% Basel traffic-light diagnostic (`2016-01-06..2016-12-30`)

| Model | Confidence | Block Start | Block End | `n_valid` | Missing / Invalid | Exceptions (`x`) | Expected | Traffic-Light Zone | Status |
|---|---:|---|---|---:|---:|---:|---:|---|---|
| `historical` | `0.99` | `2016-01-06` | `2016-12-30` | `250` | `0 / 0` | `2` | `2.5` | `green` (`0..4`) | `ok` |
| `parametric_normal` | `0.99` | `2016-01-06` | `2016-12-30` | `250` | `0 / 0` | `3` | `2.5` | `green` (`0..4`) | `ok` |

### 3. Yearly exception breakdown (`2007..2016`, `min_variance`)

| Year | `n_valid` | `95%` Expected | `95%` Historical | `95%` Normal | `99%` Expected | `99%` Historical | `99%` Normal |
|---:|---:|---:|---:|---:|---:|---:|---:|
| `2007` | `249` | `12.45` | `18` | `18` | `2.49` | `5` | `6` |
| `2008` | `253` | `12.65` | `30` | `31` | `2.53` | `13` | `18` |
| `2009` | `252` | `12.60` | `8` | `5` | `2.52` | `0` | `1` |
| `2010` | `252` | `12.60` | `5` | `5` | `2.52` | `0` | `2` |
| `2011` | `252` | `12.60` | `20` | `23` | `2.52` | `4` | `10` |
| `2012` | `250` | `12.50` | `4` | `6` | `2.50` | `2` | `2` |
| `2013` | `252` | `12.60` | `12` | `11` | `2.52` | `2` | `3` |
| `2014` | `252` | `12.60` | `5` | `5` | `2.52` | `0` | `2` |
| `2015` | `252` | `12.60` | `15` | `14` | `2.52` | `4` | `6` |
| `2016` | `252` | `12.60` | `10` | `9` | `2.52` | `2` | `3` |
| **Total** | **`2,516`** | **`125.80`** | **`127`** | **`127`** | **`25.16`** | **`32`** | **`53`** |

### 4. Plain-language implications of the actual development results

1. **95% Unconditional Calibration vs. Volatility Clustering:**
   - At 95% confidence, both Historical VaR and Parametric Normal VaR record exactly `127` exceptions out of `2,516` sessions (`5.0477%` vs. `5.00%` expected; Kupiec $\text{LR}_{\text{uc}} = 0.0120, p_{\text{uc}} = 0.9127$). On average over the full decade, 95% exception frequency matches the nominal 5% rate closely.
   - However, exceptions are **not independent over time**: they cluster heavily during regime transitions (`2008` GFC: `30` Historical / `31` Normal vs. `12.65` expected; `2011` Eurozone/US downgrade turmoil: `20` Historical / `23` Normal) and fall well below expectation in calm years (`2009–2010`, `2012`, `2014`, when trailing 500-day windows still carry prior crisis observations). Consequently, Christoffersen's independence test rejects i.i.d. exceptions at 5% significance for both models (`historical 95%`: $\text{LR}_{\text{ind}} = 6.0692, p_{\text{ind}} = 0.0138, p_{\text{cc}} = 0.0481$; `parametric_normal 95%`: $\text{LR}_{\text{ind}} = 11.8642, p_{\text{ind}} = 5.72 \times 10^{-4}, p_{\text{cc}} = 0.0027$).
2. **99% Extreme-Tail Divergence Between Historical and Normal VaR:**
   - At 99% confidence (`25.16` expected exceptions), **Parametric Normal VaR suffers `53` exceptions (`2.1065%`, more than double the nominal 1% rate)**, strongly rejecting unconditional coverage ($\text{LR}_{\text{uc}} = 23.6062, p_{\text{uc}} = 1.18 \times 10^{-6}$), independence ($\text{LR}_{\text{ind}} = 15.3308, p_{\text{ind}} = 9.02 \times 10^{-5}$, with `7` back-to-back exception pairs $n_{11} = 7$), and conditional coverage ($\text{LR}_{\text{cc}} = 38.9595, p_{\text{cc}} = 3.47 \times 10^{-9}$). In `2008` alone, 99% Normal VaR is breached `18` times (`2.53` expected) and in `2011` `10` times (`2.52` expected).
   - **Historical 99% VaR** adapts its empirical tail quantile once extreme losses enter the 500-day window, recording `32` exceptions (`1.2719%`; `13` in `2008` and `4` in `2011`), which does **not** reject unconditional coverage ($\text{LR}_{\text{uc}} = 1.7296, p_{\text{uc}} = 0.1885$). However, because unweighted 500-day historical simulation reacts only after initial crisis shocks occur, it still exhibits volatility clustering ($n_{11} = 3$, $\text{LR}_{\text{ind}} = 7.2378, p_{\text{ind}} = 0.0071$, $\text{LR}_{\text{cc}} = 8.9729, p_{\text{cc}} = 0.0113$, flagged `status = "warning"` because $n_{11} = 3 < 5$ limits asymptotic chi-square accuracy).
3. **Why a Terminal Green Basel Zone Does Not Prove Full-Cycle Safety:**
   - Over the final 250 development sessions (`2016-01-06..2016-12-30`), both 99% Historical VaR (`2` exceptions: `2016-06-24` Brexit vote and `2016-11-10` post-election bond/gold selloff) and 99% Parametric Normal VaR (`3` exceptions) land in the educational Basel **green zone** (`0..4` exceptions vs. `2.5` expected).
   - Comparing that calm-year `2016` green zone against the full `2007–2016` record (`53` exceptions and $p_{\text{cc}} = 3.47 \times 10^{-9}$ for 99% Normal VaR) illustrates why neither a 250-day green zone nor a Kupiec non-rejection may be treated as proof of model adequacy or mandate safety.

