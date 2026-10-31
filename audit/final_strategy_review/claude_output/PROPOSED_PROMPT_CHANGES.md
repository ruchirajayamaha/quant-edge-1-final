# Proposed Antigravity prompt changes

Status: **proposed and unapplied.** No prompt, code, config or data file was changed. Reviewed at commit `d7ccafe`, dataset `qe1_20050101_20261030_r3_6c4633a7ba`.

Effort: S = one focused task, M = one milestone, L = several milestones. Timing: Now = before Step 3; Core = inside Steps 3-10; Post-core = only after the core passes.

Requirement IDs refer to the matrix in `FINAL_ROUND_REVIEW.md`.

## Runtime contract impact

These proposals touch shared interfaces. Apply them once, across callers, in the step that needs them. Older design documents never authorise downgrading schema `1.1.0` or replacing r3.

| Area | Change | Needed by |
|---|---|---|
| `config.yaml` | Add spending, inflation, fee and growth ranges; `long_risk_window_start`; `evt_threshold_grid` replacing `evt_threshold_quantile`; reconcile MC draws | M02, M06, M07, M08 |
| `contracts.py` | Add optional `RiskModelName` values `ewma_fhs` and `monte_carlo_t`; `CORE_RISK_MODELS` stays unchanged | S02, S03 |
| `data/reference/context/` | New hashed context files, separate from ETF snapshots | M16 |
| `audit/decision_register/` | New dated register files | M05, S04 |

---

## Group 1: must fix

### M01. Current status and RF wording

| Field | Detail |
|---|---|
| Target | `COMMON_CONTEXT.md` first and second paragraphs; `CONTRACTS.md` DataBundle `rf_daily` bullet; `SOLO_START_HERE.md` opening |
| Weakness | The pack still reads as pre-implementation. The `rf_daily` text says "chosen availability lag", which r3 replaced. |
| Serves | R37, technical rigour |
| Input / output | Live handoff / aligned prompts |
| Acceptance | No prompt describes r2 as active or RF as lag-based |
| Effort / timing | S / Now. Pays for itself by preventing regression. |

Insert into `COMMON_CONTEXT.md` after the first paragraph:

```text
CURRENT STATE: Read handoff/SOLO.md first. Steps 1-2 and the RF-only r3 upgrade are complete.
Active dataset: qe1_20050101_20261030_r3_6c4633a7ba. Runtime schema: 1.1.0.
Do not rebuild, redownload, downgrade or replace completed work because an older document
differs. If a prompt and the runtime contract conflict, stop and record it in the handoff.
```

Replace the `CONTRACTS.md` `rf_daily` bullet with:

```text
- rf_daily: Series on return dates, fractional approximate trading-day proxy from DTB3,
  (rate_pct/100)/252. Under r3 each decision uses the newest eligible observation and that
  observation's latest eligible version. Per-return evidence is in rf_provenance. Availability
  is day-level, not an intraday first-release time, and this is not exact point-in-time data.
  rf_accrual_sensitivity is a labelled sensitivity, never the primary series. Neither is a
  realized Treasury return.
```

### M02. Mandate coverage

| Field | Detail |
|---|---|
| Target | `COMMON_CONTEXT.md`, "Required core" |
| Weakness | Page 3 names income and real growth; the core list does not. The rubric scores optional items. |
| Serves | R05, R07, R09, decision-making |
| Input / output | Human ranges / objective table |
| Acceptance | Every recommended candidate shows nominal, real, income and downside figures |
| Effort / timing | S / Now |

Add to "Required core":

```text
- Mandate coverage: for each candidate report nominal return, real return, distribution income
  and downside together. Page 3 requires capital preservation, income generation and sustainable
  real growth, with resilience under stress. Adjusted prices include income in return, so income
  is measured separately.
- Return objective: required nominal return R = (1+i)(1+g)/(1-s-f) - 1, where i is inflation,
  g is desired real growth, s is spending and f is fees. All four are human assumptions tested as
  ranges, never client facts. State arithmetic versus geometric basis.
- Optional macro and industry items: include a bounded evidence page. The rubric assesses them.
```

### M03. Extension slot

| Field | Detail |
|---|---|
| Target | `COMMON_CONTEXT.md`, "Scope and working style", first bullet |
| Weakness | All extensions are deferred with no decision made, so core interfaces may not support one. |
| Serves | Innovation |
| Input / output | This review / chosen extensions |
| Acceptance | Prompts name exactly one primary and one complement |
| Effort / timing | S / Now. Removes the open extension menu. |

Replace the bullet with:

```text
- Core first. Selected extensions: S01 Mandate Feasibility Frontier (primary) and S02 EWMA filtered
  historical simulation (complement). Build them only after their dependencies pass. Keep Step 3
  and Step 5 interfaces able to accept them. Everything else stays deferred: GARCH-based conditional
  EVT, risk overlays, automated threshold goodness-of-fit, formal ES backtests, 10-day scaling,
  cash positions, copulas and wavelets.
```

### M04. Solo sequence

| Field | Detail |
|---|---|
| Target | `SOLO_START_HERE.md` order table and step mapping |
| Weakness | No pre-registration or context-data step; extension has no place; team roles absent. |
| Serves | R01, R35, all rubric areas |
| Input / output | Human inputs / updated sequence |
| Acceptance | Each new step has a named specification and checkpoint |
| Effort / timing | S / Now |

Add to the step mapping:

```text
2b. Context data: 01_A_DATA_VALIDATION.txt A1b. Income and macro files, hashed, separate from ETF
    snapshots. Do not change the active dataset.
2c. Decision register: 02_B_PORTFOLIO_DECISIONS.txt B0. Humans commit assumptions before Step 3
    results exist. The agent prepares the file and never fills in human judgement.
5b. Regime-conditioned challenger: 03_C_RISK_EVT.txt C4. Only after C1 passes.
8b. Feasibility frontier: 02_B_PORTFOLIO_DECISIONS.txt B4. Only after B2, B3 and C2 pass.
11. Viva drills: each named team member explains and rederives their layer. Humans only.

Coding by one developer does not change the official team requirement. Every team member must be
able to explain the submission. Keep a table of layer owners in handoff/SOLO.md.
```

### M05. Portfolio construction, constraints and honest OOS

| Field | Detail |
|---|---|
| Target | `02_B_PORTFOLIO_DECISIONS.txt`, new B0 and B1 items 1, 3, 5 |
| Weakness | Provisional caps force AGG and GLD to 25-40% and equities to 20-35%. B1 suggests Ledoit-Wolf, but scikit-learn is not installed and config uses sample covariance. OOS is implied for weights rather than the rule. |
| Serves | R06, R24, R30, decision-making, rigour |
| Input / output | Human limits, r3 / register, constraint map, rule-based paths |
| Acceptance | Register commit predates Step 3 results; final weights equal the rule applied at data end; future-data perturbation changes nothing earlier |
| Effort / timing | M / Now for B0, Core for the rest. Removes the Ledoit-Wolf requirement. |

Insert before B1:

```text
B0 - DECISION REGISTER (BEFORE ANY PORTFOLIO RESULT)
Create audit/decision_register/REGISTER.md with sections for humans to complete: horizon; spending,
inflation, fee and real-growth ranges; risk limits; candidate rules; primary risk model; windows;
selection rule; decision rule. Commit it before running Step 3. Later changes are appended with a
date and reason, never overwritten. Record the commit hash in handoff/SOLO.md. Do not invent values.
```

Replace B1 item 1's covariance sentence with:

```text
Use the configured sample covariance (ddof=1) as primary. With 7 assets and a 504-day window this is
adequate. A shrinkage covariance is an optional, labelled sensitivity. Do not add a dependency for it.
```

Add to B1 item 3:

```text
Publish a constraint map: the bounds implied for every ETF and for total equities. Under the provisional
caps, AGG and GLD each lie in 25-40% and total equities in 20-35%, so a more defensive portfolio
cannot be reached. Treat this as a finding. Test named alternative caps on development data only.
Long-only is a team choice, not an official rule.
```

Replace B1 item 5 with:

```text
5. Validate RULES, not hindsight weights. Each candidate is a rule that produces weights from past
data at each rebalance. Development, selection and evaluation boundaries stay frozen. The recommended
portfolio is the selected rule applied at the data end date. Replaying those final weights through
history is a scenario and must be labelled so, never an investable record. Report every candidate
tried. Do not open the evaluation sample until the selection rule in the register is committed.
```

Add to B1 item 1:

```text
With SPY as market proxy, CAPM gives low-beta assets returns near the risk-free rate. Show this as a
model implication, and state any equity risk premium as an assumption. Use more than one
expected-return set when comparing candidates.
```

### M06. Risk window policy

| Field | Detail |
|---|---|
| Target | `CONTRACTS.md`, RiskEstimate section; `04_D_LEAD_APP.txt` D0 item 3; `config.yaml` note |
| Weakness | The last 1,260 sessions start on 2021-10-25, with neither 2008 nor March 2020. |
| Serves | R29, technical rigour, tail awareness |
| Input / output | r3 returns / two labelled windows |
| Acceptance | All comparison methods share a window; output states start, end, n and which crises are inside |
| Effort / timing | S / Now, applied in Step 5 |

Insert into `CONTRACTS.md`:

```text
RISK WINDOWS. Report two labelled fixed-exposure windows for every method:
- Long crisis-inclusive window: from the first complete return session. This is the default for
  tail reporting, because a conservative client needs crises in the sample.
- Recent window: the configured 1,260 sessions. It starts on 2021-10-25 and contains neither the 2008
  crisis nor March 2020. Label it "recent conditions only".
Every comparison uses one window across all methods. State sample start, end, count and whether each
named crisis is included. Long samples mix regimes; say so.
```

### M07. EVT availability at 90%

| Field | Detail |
|---|---|
| Target | `03_C_RISK_EVT.txt` C2; `04_D_LEAD_APP.txt` D1; `config.yaml` `evt_threshold_quantile` |
| Weakness | Page 5 asks for VaR, ES and EVT side by side at a selectable level. C2 uses 90-95% thresholds and D1 shows 90% as unavailable. Config fixes 0.95 while C2 uses a grid. |
| Serves | R14, R29, innovation (alternative threshold rule) |
| Input / output | Long window / threshold table |
| Acceptance | Selecting 90/95/99 each displays a value or a diagnostic refusal tied to a real failure, never a design gap |
| Effort / timing | S / Core |

Replace the C2 threshold grid sentence with:

```text
Threshold grid: configurable 85/87.5/90/92.5/95 percentiles, as a starting set rather than a
justification. A threshold must lie below the requested confidence, so 90% needs u below the 90th
percentile. Choose the threshold from diagnostics on development data and record the reasoning. If
the preferred u is above the 90th percentile, keep it for 95/99 and show 90% from a lower diagnosed
threshold, labelled as such. Show results from two threshold rules as the alternative-rule evidence:
the diagnostic choice and a fixed-quantile rule. Only report 90% unavailable if the lower threshold
itself fails its checks, and show the reason.
```

Replace in D1 "EVT90%may be unavailable for a higher threshold: display the reason":

```text
At every confidence level show VaR, ES and EVT together on one window and label the threshold used.
```

### M08. Monte Carlo settings

| Field | Detail |
|---|---|
| Target | `03_C_RISK_EVT.txt` C1 item 4; `config.yaml` `monte_carlo_simulations` |
| Weakness | C1 says about 50k/100k. Config says 25,000. |
| Serves | R26, rigour |
| Input / output | Config / one documented value |
| Acceptance | Reported simulation standard error is below displayed precision |
| Effort / timing | S / Core |

```text
Use one configured draw count. Report the simulation standard error of VaR and ES, and choose the
count so that error is small relative to displayed precision. Store the seed and count in diagnostics.
```

### M09. Backtest coverage

| Field | Detail |
|---|---|
| Target | `01_A_DATA_VALIDATION.txt` A3; `04_D_LEAD_APP.txt` D1; `CONTRACTS.md` Rolling backtest |
| Weakness | The sidebar selects a method but D1 can show "unavailable". The rolling cost is small, so the gap is unnecessary. Short spans give weak power. |
| Serves | R15, R30, rigour |
| Input / output | Forecast callbacks / cached rows for every sidebar method |
| Acceptance | Every sidebar method and range returns Kupiec and Christoffersen, or a real insufficient-data reason |
| Effort / timing | M / Core. Removes the "historical only" fallback text. |

Replace the "Primary core backtest" sentence in `CONTRACTS.md` with:

```text
Primary model: the one named in the decision register before the evaluation sample is opened. Compute
and cache rolling forecasts for every sidebar method at 90/95/99, so no selectable method lacks a
backtest. Normal Monte Carlo may reuse a fixed draw matrix so it stays cheap. Report two spans: the
longest valid OOS span, for power, and the frozen evaluation span. Do not choose the primary model
from evaluation results. Report failures plainly. Include an exception timeline.
```

### M10. KPI inputs

| Field | Detail |
|---|---|
| Target | `01_A_DATA_VALIDATION.txt` A2 |
| Weakness | Prompt predates r3 and has no real-return or uncertainty statistics. |
| Serves | R25, decision-making |
| Input / output | Paths, r3, context data / KPI table |
| Acceptance | Table states RF series used, sample and any sensitivity |
| Effort / timing | S / Core |

```text
Use bundle.rf_daily as primary RF. Report the effect of rf_accrual_sensitivity on Sharpe as a labelled
sensitivity. Add real annual return using the context inflation series, and label its monthly basis.
Interpret each KPI in one plain sentence for the committee. Report sample dates beside every value.
```

### M11. Hypothetical scenario

| Field | Detail |
|---|---|
| Target | `02_B_PORTFOLIO_DECISIONS.txt` B3 |
| Weakness | The illustrative vector has no evidence behind its magnitudes. |
| Serves | R32, decision-making |
| Input / output | Macro context, historical moves / justified vector |
| Acceptance | Each of seven shocks has a written reason and comparison with an observed move |
| Effort / timing | S / Core |

```text
Justify each hypothetical shock. Compare its size with observed moves for that ETF and name the macro
story. Check whether the joint move is plausible relative to observed correlations, and say so if it
is deliberately extreme. Humans own the final scenario. Report USD loss on 10M and per-ETF P&L.
```

### M12. App structure

| Field | Detail |
|---|---|
| Target | `04_D_LEAD_APP.txt` D1 |
| Weakness | Recommendation is last, and the three committee questions on page 5 are not structured. |
| Serves | R11, software, communication |
| Input / output | Result bundle / ordered pages |
| Acceptance | A new reader finds the decision, USD downside and confidence on the first screen |
| Effort / timing | S / Core |

```text
Open on Recommendation. Show: the team's decision sentence; answers to what can go wrong, how bad in
USD on 10M, and how confident we are; one frontier chart; one crisis table; one evidence line with
backtest dates and exceptions. Then Portfolio, Risk, Backtest, Stress, Assumptions & Limitations.
Avoid green pass badges. A high p-value is not proof of safety. Show only precision the estimates
support. Show the Basel colour only for its valid 99%/250-day scope.
```

### M13. Documents and source disclosure

| Field | Detail |
|---|---|
| Target | `04_D_LEAD_APP.txt` D3 |
| Weakness | Page 8's one-page recommendation is not traced. r3 evidence sources need listing. |
| Serves | R21, R22, R33, R36 |
| Input / output | Result bundle / report, tear sheet |
| Acceptance | Page counts verified on final PDFs; every source listed |
| Effort / timing | M / Core |

```text
The tear sheet opens with the plain-English accept/adjust/reject statement, then weights, risk metrics
and key limitations. It satisfies both one-page items (pages 6 and 8) and is reproduced as page 1 of
the report. Do not create a third document. Record this interpretation in the report.
Follow the blueprint in audit/final_strategy_review/claude_output/FINAL_ROUND_REVIEW.md section 8.
Add a source table: Yahoo via yfinance; FRED; ALFRED and archived Federal Reserve H.15 pages, used
only as RF release evidence; any context-only reference. Check final PDF page counts and read every
page. Report anything unverified as incomplete.
```

### M14. Final audit

| Field | Detail |
|---|---|
| Target | `05_INTEGRATE_AND_AUDIT.txt` |
| Weakness | No requirement-level trace, committed result bundle or fresh-install proof. |
| Serves | R10, R19, R20, software |
| Input / output | Integrated repo / audit report |
| Acceptance | Every matrix row has a real artifact or is listed open |
| Effort / timing | M / Core |

Add as items:

```text
11. Update the requirements matrix from FINAL_ROUND_REVIEW.md. Mark a row verified only with a real
artifact. Placeholders, unrun checks and drafts stay open.
12. Fresh-install check: new venv, documented setup, `streamlit run app/Home.py`, offline, from a clean
clone. A committed result bundle must let every page render without recomputation. Record the
exact commands and outcomes. Exercise every sidebar combination with Streamlit AppTest.
13. Confirm the judge access route. Do not publish or change repository visibility without a human
instruction.
```

### M15. Human validation and limitations page

| Field | Detail |
|---|---|
| Target | `COMMON_CONTEXT.md` closing bullet; `04_D_LEAD_APP.txt` D3; `SOLO_START_HERE.md` |
| Weakness | Page 9 permits mark reduction or disqualification. All validation is PENDING, and no plan exists to resolve it. |
| Serves | R17, R34, R35, communication |
| Input / output | Team / validation log, drill record |
| Acceptance | Each layer has a named human who recomputed one value and explained it unaided |
| Effort / timing | M / Core, human time |

```text
Human validation is a planned workstream, not a closing note. Prepare for each layer: the formula, a
hand-checkable example, a value to recompute without the library, and likely questions. Humans perform
and record the checks, with name, date and result. Never mark this complete on their behalf.
The Assumptions & Limitations page uses plain language with no undefined terms, and says what each
limitation could do to the decision. Humans must read it before it is called final.
```

### M16. Context data

| Field | Detail |
|---|---|
| Target | `01_A_DATA_VALIDATION.txt`, new A1b |
| Weakness | No data supports income, real return or rate sensitivity. Page 9 allows FRED macro series for stress construction. |
| Serves | R07, R09, decision-making, technical rigour |
| Input / output | Approved sources / hashed context files |
| Acceptance | ETF and RF files unchanged; hashes recorded; each series has a stated use |
| Effort / timing | S / Now, before Step 3. Keep it to the listed series. |

```text
A1b - CONTEXT DATA (DO NOT CHANGE ETF OR RF SNAPSHOTS)
Create data/reference/context/ with hashes and retrieval times:
- Distributions for all seven ETFs through 2026-10-30, from yfinance Ticker dividends.
- FRED: CPIAUCSL, T10YIE, DGS2, DGS10, DFII10, BAA10Y. Confirm each series exists before use.
Compute trailing 12-month distribution yield per ETF. GLD is expected to show no distributions;
report what the data shows. Macro series are monthly or daily context, not vintage-aware decision
inputs, unless stated otherwise. Note that CPI is published with a lag. Use them for three purposes
only: the real-return objective, AGG's empirical rate sensitivity, and scenario reasoning.
Do not add them as optimiser signals.
```

---

## Group 2: strongest competitive improvements

### S01. Mandate Feasibility Frontier

| Field | Detail |
|---|---|
| Target | `02_B_PORTFOLIO_DECISIONS.txt`, new B4 |
| Weakness | Nothing links evidence to the required decision. |
| Serves | Decision-making, innovation, R08 |
| Input / output | B1 rules, C1 ES, B3 scenarios, register / `frontier` table and chart |
| Acceptance | LP ES equals C1 historical ES on the same scenarios within a stated tolerance; synthetic infeasible limits return infeasible; each point satisfies every constraint; runtime recorded |
| Effort / timing | M / Post-core, medium risk. Paid for by the deferred list in D01. |

```text
B4 - MANDATE FEASIBILITY FRONTIER
Purpose: show which return and downside combinations any eligible portfolio can meet, and what each
limit costs. Standard methods, integrated for this decision. Do not claim novelty.
1. For a grid of daily ES budgets, maximise expected return subject to the register's portfolio
constraints, using the Rockafellar-Uryasev LP with scipy.optimize.linprog(method="highs").
2. Add scenario-loss limits as linear rows: -weights @ shocks <= limit. This also answers reverse
stress: which limit binds, and what allocation meets it.
3. Repeat for each of three pre-stated expected-return sets: CAPM with a stated premium, a
building-block set from current yields, and a shrunk historical mean.
4. For selected candidates, resample with a stationary bootstrap (documented mean block length, fixed
seed) to report ranges for ES and for attainment of the return objective. Do not re-optimise inside
the bootstrap unless runtime allows, and label what was fixed.
5. Mark infeasible regions plainly. Infeasible is a result, not a bug.
Use training data for design. Report selection and evaluation outcomes separately.
FALLBACK: if tests fail or ranges make candidates indistinguishable, report that finding and use a
deterministic table of about five feasible candidates under the same decision rule.
```

### S02. EWMA filtered historical simulation

| Field | Detail |
|---|---|
| Target | `03_C_RISK_EVT.txt`, new C4; `contracts.py` optional model |
| Weakness | No regime-conditioned estimate, although the rubric names it. |
| Serves | Innovation, rigour, R27 |
| Input / output | Portfolio losses / `ewma_fhs` callback and backtest rows |
| Acceptance | No-look-ahead perturbation test; known-answer test; same dates and windows as the primary model |
| Effort / timing | S / Post-core, low risk. No new dependency. |

```text
C4 - EWMA FILTERED HISTORICAL SIMULATION (OPTIONAL MODEL, AFTER C1)
For portfolio returns r_t, sigma2_t = lambda*sigma2_(t-1) + (1-lambda)*r_(t-1)^2, using data before t
only. lambda = 0.94 is fixed in advance and not tuned on selection or evaluation data. Standardise
z_t = r_t/sigma_t, take the empirical loss quantile of z over the window, and rescale by the volatility
forecast for the target day. Compute ES from the same standardised tail.
Register it as model "ewma_fhs" through the existing callback. Compare on identical days and windows
with the primary model, using Kupiec, Christoffersen and exception clustering. Report a worse result
honestly. If a team member cannot defend it, drop it and keep the historical/parametric comparison.
```

### S03. Fat-tailed Monte Carlo control

| Field | Detail |
|---|---|
| Target | `03_C_RISK_EVT.txt` C1 item 5 |
| Weakness | Normal MC must match parametric, so the required three-way comparison teaches little. |
| Serves | R27, rigour |
| Input / output | Moments / `monte_carlo_t` estimate |
| Acceptance | Converges to normal as degrees of freedom grow; scaled to the same covariance |
| Effort / timing | S / Core-late, low risk |

```text
Keep normal Monte Carlo as the required control: it should match parametric within simulation error,
and that agreement is a check, not a finding. Add one labelled variant, multivariate Student-t with the
same mean and covariance and degrees of freedom estimated on training data, to show what the normal
tail assumption costs. Do not call it a separate required method.
```

### S04. Decision rule and monitoring triggers

| Field | Detail |
|---|---|
| Target | `02_B_PORTFOLIO_DECISIONS.txt` B3 closing paragraph; register |
| Weakness | "Accept/adjust/reject" has no pre-committed meaning. The brief gives no numeric client limits. |
| Serves | R33, decision-making |
| Input / output | Human limits, frontier / decision |
| Acceptance | Rule committed before evaluation; outcome reproducible from artifacts |
| Effort / timing | S / Now for the rule, Core for triggers |

```text
Humans define in the register, before evaluation:
- ACCEPT: an eligible portfolio meets the proposed objective and all proposed limits, across the
  agreed return assumptions.
- ADJUST: none does, but a stated limit change restores feasibility. Report the change and its cost.
- REJECT: no change within committee tolerance achieves the objective.
Provide at least three monitoring triggers, each with a metric, a threshold, and an action. Thresholds
are human choices. Do not preselect the outcome.
```

---

## Group 3: defer or cut

### D01. Scope control

| Field | Detail |
|---|---|
| Target | `COMMON_CONTEXT.md`, `03_C_RISK_EVT.txt` closing, `SOLO_START_HERE.md` |
| Serves | Protects the core and viva |
| Acceptance | No deferred item appears in a Step 3-10 task without a logged decision |
| Timing | Now |

| Item | Decision | Reason |
|---|---|---|
| GARCH-based conditional EVT | Defer | Only if S02 and all core work finish, and clustering persists |
| Lagged risk overlay | Defer | Weak evidence; cash ineligible; adds tuning risk |
| Automated threshold goodness-of-fit | Cut | Calibration burden; two threshold rules suffice |
| Formal ES backtests | Defer | Beyond the brief's listed tests |
| 10-day scaling | Cut | One-day horizon is the defined comparison |
| Cash | Cut | Not an eligible fund |
| Copulas, wavelets | Cut | Screening-round items; no value case here |
| Risk parity, minimum-CVaR candidates | Defer | The frontier covers the decision |
| Separate third one-page document | Cut | Tear sheet covers it (M13) |

## What stays unchanged

- Data, calendar, r3 and test work.
- Schema `1.1.0` and shared interfaces, apart from the additions above.
- Loss signs, simple-return aggregation and log diagnostics.
- Historical ES tail helper, normal moments, Euler requirements.
- GPD formulas, xi limits, support checks and bootstrap conditions.
- Kupiec and Christoffersen boundary handling and Basel scope.
- Scenario-versus-ES distinction.
- Pipeline-only orchestration and no analytics in Streamlit.
- Human sign-off boundaries.
