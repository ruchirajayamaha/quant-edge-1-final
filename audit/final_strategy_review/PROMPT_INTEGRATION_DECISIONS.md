# Final-round prompt review: integration decisions

Date: 2026-10-31. Inputs: Claude's three unchanged files in `claude_output/`, the official 10-page final brief and the existing project at `d7ccafe`. This pass edits prompts/planning documents only. Runtime code, config, dependencies, active pointer and r3 data are preserved. Portfolio construction has not started. This is a stronger implementation plan, not evidence that missing application/report work is already complete.

## What was accepted

The investor mandate needs explicit income/real-growth evidence, a transparent allocation-rule decision, interpreted risks, credible evaluation and human defence. The preferred post-core differentiator is the **Mandate Feasibility Frontier**, backed by a deterministic candidate-table fallback. **EWMA-FHS** is an optional cheap complement. Both must earn inclusion through tests, actual runtime and a decision-usefulness check; neither is an official required method or an originality claim.

The official rubric remains decision-making30%, correctness25%, software15%, innovation15%, communication15%. The implementation cannot claim high marks because data tests pass while all analytical functions and final deliverables remain unbuilt. Human economic choices, validation, team coverage and access/submission logistics stay visibly pending.

## Important qualifications to the review

1. **Recent data is not crisis-free.** The recent window omits GFC/COVID but includes the prescribed2022rate shock. The brief gives lookback discretion. We keep registered recent current-risk estimates and add a full-history fixed-exposure crisis sensitivity, comparing methods on matched samples in each. Long samples mix regimes and cannot be used in earlier forecasts or automatically replace current-risk estimation.
2. **Do not force a low EVT threshold to fill90%.** The plan now uses a labelled empirical-body/GPD-tail construction with valid tail mass, quantile conventions and ES integration. Below the threshold, VaR is a body estimate, not pure EVT extrapolation. Fit failures/infinite ES remain honest. Lower thresholds can be tested, not presumed valid.
3. **Macro breadth is optional.** Mandate income/real-growth interpretation is important, but six extra FRED series are not mandatory. Our bounded income/CPI context snapshot is separate, before KPIs; additional macro data needs a named question. It does not block price-only portfolio implementation or become an unlagged signal.
4. **Objective formula depends on cash-flow timing.** Both `(1+R)*(1-s-f)=(1+i)*(1+g)` and `1+R-s-f=(1+i)*(1+g)` are valid under different stated deduction bases. Neither is universally the correct endowment model. Distinguish arithmetic forecasts, geometric outcomes, embedded fund costs and extra fees.
5. **Required validation is the chosen model.** We target supported HS/normal/MC rolling choices for a useful UI; every optional model is not a new official backtesting obligation. Do not remove genuine insufficient-data/fit states, fabricate passes or relabel primary results. Only expose supported backtest callbacks.
6. **Normal MC agreement is useful.** It verifies simulation/aggregation. Student-t MC stays a deferred sensitivity, rather than mandatory extra complexity just to produce different bars.
7. **Scenario bounds are not automatically reverse stress.** Fixed scenario inequalities can constrain the LP. A reverse-stress claim needs a defined severity variable/direction and breach tolerance; it is omitted unless actually solved.
8. **One-page packaging is an interpretation.** A self-contained executive recommendation can be reused as the tear sheet/report opening, but we do not claim a confirmed organiser waiver or ban a separate export. Trace both literal requirements and retain all required content.
9. **Prior exposure is disclosed.** Full-history asset data diagnostics were already inspected. The register cannot claim an untouched-in-every-way dataset; it can document uncomputed strategy outcomes and freeze future selection/evaluation rules. A draft commit is not human sign-off.

## Disposition of every proposed block

| Claude ID | Decision / integrated location |
|---|---|
| M01 | Accepted: current r3/solo/runtime authority in common context, contracts and guide |
| M02 | Accepted with conditional cash-flow derivation and separate income/real-growth coverage; optional macro remains optional |
| M03 | Qualified: frontier preferred after core, FHS optional; not two mandatory extensions |
| M04 | Qualified: B0 before results, A1b before KPIs, human work throughout; context is not a blocker to price-only Step3 |
| M05 | Accepted: register, covariance consistency, implied-bounds map, rule-based OOS and honest prior exposure |
| M06 | Modified: two labelled windows; recent primary plus crisis sensitivity, not a forced full-history-only default |
| M07 | Modified: empirical body/GPD tail plus diagnostics, not automatic lower-threshold fitting |
| M08 | Accepted: one config draw count; quantify MC error/adapt precision |
| M09 | Qualified: primary required; supported UI callbacks/cache targeted; no fabricated availability |
| M10 | Accepted: r3 primary convention, separate accrual sensitivity, aligned ex-post real/income interpretation |
| M11 | Accepted: seven shock rationales and same-horizon comparisons; joint plausibility/intentional severity stated |
| M12 | Accepted: decision-first app, USD downside/confidence, optional frontier with core-table fallback |
| M13 | Qualified: traced one-page interpretation, actual pagination, production/evidence/context source disclosure |
| M14 | Accepted with finite representative control coverage, real fresh-install checks, reference bundle and evidenced access |
| M15 | Accepted: planned human checks, five-role defence coverage and practice; no fabricated validation |
| M16 | Narrowed: income/CPI core mandate context; other series question-driven and optional |
| S01 | Preferred post-core: feasible LP, exact shared empirical ES, uncertainty limits and fallback |
| S02 | Optional post-core: explicitly initialised/lagged EWMA-FHS; no discrete-regime claim |
| S03 | Deferred: normal MC remains a meaningful control; t variant only after an explicit value/effort decision |
| S04 | Accepted as human-defined proposal-relative decision/monitoring rule; no invented client limits |
| D01 | Scope control retained; no blanket claim that a third export is prohibited or scenario rows solve reverse stress |

## Next bounded task

`audit/decision_register/REGISTER.md` is prepared as a **DRAFT**, with verified project facts and inherited provisional settings. **Clarification after user feedback: start Step 3 now using `antigravity-team-pack/NEXT_TASK_STEP3.txt`.** The factual register already exists; a separate B0 human-input approval round is unnecessary for portfolio implementation and synthetic/development-period checks. Human choices remain pending alongside engineering work. Record the protocol before inspecting selection/evaluation strategy outcomes; do not invent economic judgement or label provisional output as an approved mandate. The older decision-register task is reference-only.

Then follow the revised solo sequence: registered/exploratory status -> portfolio rules -> bounded income/inflation context and KPIs -> risk -> validation -> EVT -> decision evidence -> qualified extensions -> app -> actual documents/audit/human defence.

## Technical grounding and limits

- [Rockafellar-Uryasev, Optimization of Conditional Value-at-Risk](https://sites.math.washington.edu/~rtr/papers/rtr179-CVaR1.pdf): the proposed empirical-CVaR optimization is standard methodology, not a novelty claim.
- [SciPy linprog](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html): the existing SciPy/HiGHS route can represent linear scenario/risk constraints; real implementation/runtime still needs measurement.
- [McNeil-Frey tail-risk paper, section2.2](https://www.wu.ac.at/fileadmin/wu/d/i/statmath/Publications/Publications_Frey/Journal_Papers/evt-garch.pdf): the POT quantile inversion is for probabilities beyond its tail threshold. The bulk/tail extension in our prompt is a proposed explicit modelling construction requiring its own boundary/integration tests, not a claim that this paper validated our future code.
- [SciPy GPD parameterization/support](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.genpareto.html): keep support and exponential-limit safeguards.

No unconfirmed NACUBO spending average, inaccessible reference or competitors' private work is used as a factual advantage. Synthetic timing in Claude's review is not a guarantee for a full real-data optimization/bootstrap pipeline. Final recommendation, future model performance and ranking remain empirical/human questions.
