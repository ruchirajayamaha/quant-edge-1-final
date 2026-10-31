# Quant Edge 1.0 final-round strategy review

Reviewed at commit `d7ccafe` (clean tree), active dataset `qe1_20050101_20261030_r3_6c4633a7ba`. All 10 PDF pages were read; pages 6-8 and 10 were checked as images because the page 10 text extraction scrambles the rubric. Nothing here is a prediction of ranking. No project return, weight or portfolio result was computed, so the chronology remains unused.

## 1. Verdict

The foundation is strong and the submission does not exist yet.

- **Verified now:** data, calendar, return and RF work. 41 tests pass and r3 is active.
- **Not built:** all 16 analytic functions are `NotImplementedError` stubs. `app/Home.py` is a status page, `results/` is empty, and there is no memo, tear sheet or human validation.
- **The plan is technically careful but under-serves the mandate.** Its trap handling is good. It leaves out income, real return and the optional macro items the rubric names, and it has no way to say accept, adjust or reject.

Five findings matter most, and three of them can quietly damage a polished app:

1. **The planned risk window contains no crisis.** 1,260 sessions back from 2026-10-30 starts on 2021-10-25, so the dashboard EVT would see neither 2008 nor March 2020.
2. **EVT at 90% conflicts with the app requirement.** Page 5 wants VaR, ES and EVT side by side at the same level, with 90/95/99 selectable. The plan shows "unavailable" at 90%.
3. **Income and real growth are missing.** Page 3 names both. Adjusted prices hide income, and `config.yaml` has only null targets.
4. **Provisional constraints leave a narrow box.** With 40% per fund and 35% equities, AGG and GLD are each 25-40%, and equities are forced to 20-35%. The optimiser cannot go more defensive than that.
5. **"Historical weights replayed" could be mistaken for OOS.** Final weights chosen on all data cannot be backtested honestly. The rule must be what is validated.

Recommended differentiator: a **Mandate Feasibility Frontier with uncertainty** that produces the accept/adjust/reject decision, plus one cheap regime-conditioned challenger, **EWMA filtered historical simulation**.

## 2. Requirements matrix

Status means: `verified` (run and checked, by automated checks only, since human validation is pending), `implemented-unverified`, `planned`, `missing`, `ambiguous`. Type: R = official rule, D = official discretion, I = my inference.

| ID | PDF | Obligation | Evidence | Status | Gap | Action | Verification artifact |
|---|---|---|---|---|---|---|---|
| R01 | p2 | R: teams of five | Solo developer; team not recorded | ambiguous | Membership unknown | Record team; assign layer owners | Viva coverage table |
| R02 | p3 | R: end-to-end Python and Streamlit app | `Home.py` stub | planned | No analytics | Steps 3-9 | Page smoke tests |
| R03 | p3, p5 | R: seven funds; single fund or any mix | `config.yaml`, `contracts.py` | verified | None | Keep | Existing tests |
| R04 | p4 | D: defend horizon and allocation | Provisional in config | planned | No reasoning | Human register | Decision register |
| R05 | p4 | D: return objective | All null | missing | No arithmetic | M02, S01 | Objective table |
| R06 | p4 | D: define risk constraints | Caps set; `risk_limits` null | planned | No limits; corners | M05 | Constraint map |
| R07 | p3, p4 | R: income, preservation, real growth, suitability | Not in prompts beyond passing mention | missing | Income, real return absent | M02, M16 | Income table |
| R08 | p4 | R: quantify return/risk trade-offs | B1, B2 | planned | No decision output | S01 | Frontier artifact |
| R09 | p4, p10 | D, but scored: optional macro/industry risk | Optional context only | missing | Rubric names optional items | M16 | Macro evidence page |
| R10 | p4 | R: diversification, risk, tail, stress, resilience | Across prompts | planned | Not traced | M14 | Evidence map |
| R11 | p5 | R: what can go wrong, how bad, how confident | Implicit | planned | Not structured | M12 | Page and tear sheet layout |
| R12 | p5 | R: sidebar for 90/95/99, method, backtest range | D1 | planned | None once built | Keep | AppTest |
| R13 | p5 | R: weights, cumulative return, drawdown | D1 | planned | None | Keep | AppTest |
| R14 | p5 | R: VaR, ES, EVT side by side at same level | D1, C2 | ambiguous | 90% shown unavailable | M07 | 90% test |
| R15 | p5, p7 | R: Kupiec, Christoffersen, traffic light | A3 | planned | Some methods unavailable | M09 | Backtest panel test |
| R16 | p6 | R: stress impact per crisis | B3 | planned | None | Keep | Stress table |
| R17 | p6 | R, graded: plain-language Assumptions & Limitations page | D1 | planned | Risk of jargon | M15 | Human read-through |
| R18 | p6 | R: free toolkit | Pinned free libraries | verified | None | Keep | `requirements.txt` |
| R19 | p6 | R: public or judge-accessible private repo | Private repo exists | ambiguous | Judge access not arranged | Grant or publish at submission (human decision) | Access check |
| R20 | p6 | R: one-command run, or deployed | Documented; stub only | planned | Clean install unproven | M14 | Fresh-venv log |
| R21 | p6 | R: 7-15 page report | None | missing | All | M13 | PDF page count |
| R22 | p6 | R: one-page tear sheet, under five minutes | None | missing | All | M13 | PDF page count |
| R23 | p6 | Conditional: 10-12 minute pitch and deck | None | planned | Final five only | Section 9 | Timed rehearsal |
| R24 | p7 | R: Markowitz and CAPM | Stubs | planned | CAPM input weak | M05, S01 | Unit tests |
| R25 | p7 | R: compute and interpret KPIs | Stub | planned | Interpretation | A2 plus M10 | KPI table |
| R26 | p7 | R: three VaR methods, same portfolio, 95/99 | Stubs | planned | MC sized inconsistently | M08 | C1 tests |
| R27 | p7 | R: explain disagreement, critique assumptions | C1 | planned | Normal MC adds nothing | S03 | Disagreement table |
| R28 | p7 | R: ES with rationale | Stub | planned | None | Keep | C1 tests |
| R29 | p7 | R: EVT, stressed behaviour, justified threshold | Stub | planned | No crisis in window | M06, M07 | EVT diagnostics |
| R30 | p7 | R: OOS backtest of chosen model | Stub | planned | What is tested | M05, M09 | Backtest bundle |
| R31 | p8 | R: risk budgeting using marginal VaR/ES | Stub | planned | None | Keep B2 | Euler tests |
| R32 | p8 | R: crisis paths plus one team scenario | Stub | planned | Rationale thin | M11 | Stress table |
| R33 | p8 | R: one-page plain-English accept/adjust/reject | Tear sheet planned | ambiguous | Overlaps p6 items | M13 | Trace below |
| R34 | p8 | R: AI disclosure with four items | `AI_DISCLOSURE.md` | implemented-unverified | Human validation PENDING | M15 | Completed log |
| R35 | p8-9 | R: humans explain everything; failure can reduce marks or disqualify | None | missing | Highest non-technical risk | M15 | Viva drill record |
| R36 | p9 | R: approved, disclosed sources | Yahoo, FRED | ambiguous | r3 evidence also used ALFRED and Fed H.15 archives | M13 disclosure | Source table |
| R37 | p9 | R: adjusted prices, calendars, flags, reproducible cleaning | Audits, r3 | verified | None | Keep | Existing tests |
| R38 | p9 | R: log returns, stated simple exceptions | Stated in docs | verified | Extend to models | Keep | C1 docs |
| R39 | p9 | R: stationarity of modelling series | Per-asset only | planned | Portfolio series pending | A2 as written | ADF output |
| R40 | p10 | R: rubric criteria | Section 3 | planned | See below | Roadmap | Evidence map |

**Trace for page 8's "one-page plain-English recommendation" (R33).** The brief uses "memo" twice: a 7-15 page report (p6) and a one-page recommendation (p8), alongside a tear sheet (p6). My interpretation is that one page can satisfy both one-page items. The tear sheet leads with the accept/adjust/reject statement in plain English, followed by portfolio and risk metrics, and it is reproduced as page 1 of the report. No third document. This is an inference, so ask the organisers if a channel exists.

**Not found in the PDF:** a deadline, file limits, a deployment requirement or client risk limits. Section numbering skips from 3 to 5 although the page count is complete. Screening-round rules were not imported.

**Source disclosure (R36).** ALFRED is the St. Louis Fed's archival companion to FRED, and H.15 is FRED's source, so this looks low-risk, but the listed name is FRED. Disclose them explicitly. Treasury data was used only as a research cross-check, not as a model input.

## 3. What a serious contender would show

This is a judgement about strength of evidence, not a score prediction.

### Investment decision-making (30%)

- **Excellent:** a committee can state what it is being asked to approve, what it gives up, how it fails, and when to revisit.
- **Current position:** weak on outcome, strong on discipline. B3 supplies a "decision-evidence table", but nothing turns evidence into accept/adjust/reject, and objectives are null.
- **Highest value:** Feasibility Frontier (S01). Acceptance: every limit combination maps to accept, adjust or reject under a rule committed before the evaluation sample is opened.
- **Failure that loses marks:** a technically correct minimum-variance portfolio with no argument for income, real return or why those limits apply.

### Technical rigour (25%)

- **Excellent:** formulas match, sign conventions hold, and independent recomputation agrees. Failures are reported honestly.
- **Current position:** the strongest area. The prompts already cover loss signs, ES tail mass, Euler identity, EVT support, Basel scope and scenario-versus-ES. The gaps are windows and comparisons (section 6).
- **Highest value:** crisis-inclusive tail estimation with same-window comparison (M06, M07). Acceptance: EVT and conventional measures reported on one crisis-inclusive window, with exceedance counts.
- **Failure:** a low 99% VaR from a calm window, presented as tail awareness.

### Software and interface (15%)

- **Excellent:** a judge clones, installs and sees real numbers without waiting or a network.
- **Current position:** architecture is good (library, pipeline, cached bundle), UI unproven.
- **Highest value:** a committed result bundle and page tests (M14). Acceptance: fresh-venv install, offline launch, every page renders from the bundle, all sidebar combinations pass.
- **Failure:** expensive recomputation on load, or "unavailable" in a required panel.

### Innovation and ambition (15%)

- **Excellent:** one extension that changes a decision and survives validation. The rubric's examples are regime-conditioned risk, risk overlays and alternative EVT threshold rules.
- **Current position:** deliberately deferred, which is sensible, but no slot or interface is reserved.
- **Highest value:** S01 and S02. Acceptance: the keep/kill checks in section 5.
- **Failure:** a method collection nobody can defend.

### Communication and defence (15%)

- **Excellent:** any team member can explain any page. Page 9 allows mark reduction or disqualification for failing this.
- **Current position:** missing. The work so far is AI-built and human validation is PENDING throughout.
- **Highest value:** a viva coverage table and recorded drill (M15). Acceptance: each layer has a named owner who rederives its core formula without notes.
- **Failure:** a strong pipeline that the team cannot explain.

## 4. Project thesis (hypothesis only)

> The endowment needs real capital preservation, income and survivable losses. We translate that into explicit return, income and downside limits, and test whether any allocation of the seven funds meets them. Allocation comes from a pre-committed rule. Its downside is measured by several models, validated out of sample and replayed through actual crises. Risk contributions show what to change, and monitoring triggers say when to revisit.

Weights, the best model and the final decision are TO BE DETERMINED EMPIRICALLY. "No allocation meets these limits" is a legitimate and possibly strong outcome.

## 5. Differentiation

The ranks below are subjective prioritisation, not scores. Effort and runtime are based on a synthetic-only probe: a 7-asset ES-limited LP took about 0.01-0.15 s at up to 5,491 scenarios, 1,000 bootstrap evaluations of 12 candidates took under 1 s, and a 3,000-day EWMA filter run took about 0.1 s.

| Candidate | Rubric fit | Financial value | Testability | Effort | Failure risk | Viva burden | Rank |
|---|---|---|---|---|---|---|---:|
| Feasibility frontier with uncertainty | Decision, innovation | High | High | Medium | Low | Low | 1 |
| EWMA filtered historical simulation | Named example | Medium | High | Low | Low | Low | 2 |
| Conditional EVT, GARCH-based | Named example | Medium | Medium | High | Medium | High | 3 |
| Reverse stress | Decision | Medium | High | Low | Low | Low | Absorb into 1 |
| Lagged risk overlay | Named example | Uncertain | Medium | Medium | High | Medium | Defer |
| Copulas, wavelets | Not required | Low here | Medium | High | High | High | Cut |

**Primary: Mandate Feasibility Frontier (S01).** For a grid of downside budgets, an ES-limited LP finds the highest expected-return eligible portfolio.

- ES constraints use the Rockafellar-Uryasev linear form.
- Scenario-loss limits are linear rows, so a reverse-stress question is answered in the same tool at no extra cost.
- Candidates are then evaluated under stationary-bootstrap resampling, which gives uncertainty for ES and objective attainment.
- Three pre-stated return assumption sets show whether the decision depends on the return forecast. This matters because estimation error can swamp optimisation gains.

Classification: standard methods, thoughtfully integrated. It is not a new empirical contribution and must not be described as one.

- **Validation:** LP ES equals the C1 historical ES on the same scenarios. Synthetic infeasible limits return infeasible. Each frontier point satisfies every constraint. Bootstrap seed is fixed and runtime recorded.
- **Keep if:** tests pass and the frontier changes or quantifies at least one committee statement, for example the return cost of tightening a limit.
- **Kill or fall back if:** LP and C1 disagree after debugging, or bootstrap ranges make all candidates indistinguishable. Report that finding.
- **Fallback:** a deterministic table of about five feasible candidates with the same decision rule and no probability layer.

**Complement: EWMA filtered historical simulation (S02).** Returns are scaled by a lagged EWMA volatility and rescaled to current volatility, following Hull and White. It answers the rubric's "regime-conditioned risk" with no new dependency. Use λ=0.94 fixed in advance, and do not tune it on the evaluation sample.

- **Keep if:** it runs on the same days and windows as the primary model. A worse result is still reported.
- **Kill if:** it cannot be defended by a named member. Fall back to the historical and parametric comparison.

**Why not the others.**

- McNeil-Frey conditional EVT is credible but adds rolling GARCH fits and more to defend. Consider it only if S02 and the core are finished and Christoffersen shows clustering S02 does not fix. Its loss-sign warning stays in C2.
- An overlay carries real evidence risk. Cederburg et al. found volatility-managed strategies did not reliably beat unmanaged ones in direct real-time comparison across 103 equity strategies. Cash is also not eligible, and whether AGG can act as a defensive destination has to be tested, especially in the 2022 rate-hiking scenario the brief names.

## 6. Decision quality and scientific defensibility

**Objective arithmetic (framework, illustrative inputs only).** If spending `s` and fees `f` leave NAV annually, the required nominal return is `R = (1+i)(1+g)/(1-s-f) - 1`. With illustrative i=2.5%, g=0.5%, s=4.0%, f=0.3%, R is about 7.6%. Arithmetic mean returns must exceed this by roughly half the variance. These are not client facts. NACUBO reports a 4.7% average effective spending rate for FY23, which is useful context for a sensitivity range, not a data input.

**Constraint audit.** 35% equity cap plus 40% per fund means AGG and GLD are both forced into 25-40%, with total equities 20-35%. The illustrative weights sit on that corner: equities 35%, AGG 40%, GLD 25%. A 25% gold floor is a consequence of two caps rather than a stated belief. Test explicit alternatives, for example a higher AGG cap, on development data. Long-only is a team choice, not an official rule.

**Mandate fit.**

- **AGG:** carries rate risk. The 2022 scenario is the direct test, and its result is TO BE DETERMINED EMPIRICALLY. Estimate sensitivity to FRED yields rather than assuming duration.
- **GLD:** expected to pay no distributions, to be confirmed in the context data. Compare portfolio distribution yield with the spending assumption.
- **Equity overlap:** SPY already holds XLE and XLK exposure. Treat the equity cap at the total level and do not call sector funds independent diversifiers. Holdings data is not in the approved list, so state this qualitatively and show correlations.
- **Benchmarks:** 60/40 and equal weight may breach team limits. Label them as references.
- **CAPM input:** with SPY as market proxy, low-beta AGG and GLD get expected returns near the risk-free rate. Do not present this as a forecast without alternatives.
- **Stability:** report weight paths, turnover and bootstrap weight ranges. A small return gain with unstable weights is a weak recommendation.

**Validation design.**

1. Commit a decision register before opening selection or evaluation data: candidates, primary risk model, windows, selection rule and limits.
2. Development 2005-2016 for design, selection 2017-2020 (1,007 sessions), evaluation 2021-2026 (1,464 sessions), as already provisional.
3. Validate the rule, with `weights_before` from past data only. Final weights are that rule applied at the data end date.
4. Report every candidate tried, not only the winner.
5. Same-sample comparisons only, with sensitivity to window, threshold and constraints.
6. Backtest risk models over the longest valid OOS span for power, and report the evaluation span separately.
7. Label replaying final weights through crises as a scenario. Never call it an investable record.

**Prompt trap audit.**

| Trap | Current prompts | Verdict |
|---|---|---|
| Simple/log P&L, loss sign, `abs()` | COMMON_CONTEXT, C1 | Good, keep |
| Annualisation, Sortino, drawdown wealth | A2 | Good, keep |
| Shared normal moments, empirical ES tail | CONTRACTS, C1 | Good, keep |
| Euler consistency, covariance mismatch | B2, CONTRACTS | Good, keep |
| EVT support, xi limits, modified scale | C2 | Good, keep |
| Exceedance minimum against window | C2 | Good, but the window excludes crises (M06) |
| 90% below threshold | C2 | Honest but conflicts with p5 (M07) |
| Fitted-GPD goodness of fit | C2 | Good, keep |
| Basel 99%/250 scope and low power | A3 | Good, keep |
| Normal MC agreement | C1 | Good, but MC then teaches nothing (S03) |
| RF observation, version, publication | Stale text | Update for r3 (M01) |
| Scenario loss is not ES | B3, CONTRACTS | Good, keep |
| Ledoit-Wolf | B1 suggests it; scikit-learn not installed; config uses sample | Conflict (M05) |
| MC draws | C1 says 50k/100k; config says 25,000 | Conflict (M08) |
| EVT threshold | Config fixes 0.95; C2 uses a grid | Conflict (M07) |

## 7. Committee experience

**First 90 seconds on the landing page, using real outputs only:**

1. One sentence: the decision and our recommendation, written by the team.
2. Three plain answers from page 5: what can go wrong, how bad in USD on 10M, how confident.
3. One frontier chart showing the proposed portfolio, limits and uncertainty.
4. One crisis table: portfolio against 60/40, USD loss per scenario.
5. A single evidence line: backtest period, exception counts and what failed.

**Page order:** Recommendation, Portfolio, Risk, Backtest, Stress, Assumptions & Limitations.

| Figure | What it teaches |
|---|---|
| Frontier with uncertainty band | What each limit costs |
| VaR, ES, EVT bars at chosen level | The gap the brief wants visible (p5) |
| Risk contribution against weight | Which fund is really driving risk |
| Exception timeline | Whether failures cluster |
| Crisis wealth paths | How losses unfold |

Avoid green badges for passed tests: a high p-value is not proof of safety. Show the Basel colour only under its 99%/250-day scope. Limit precision to what estimates support, and show dollars alongside percentages.

## 8. Written deliverables

**Report, 7-15 pages:**

| Pages | Content | Rubric evidence |
|---|---|---|
| 1 | Recommendation, same text as tear sheet | Decision |
| 2 | Client, horizon, objective, limits | Decision |
| 3 | Data, cleaning, calendars, RF | Rigour |
| 4-5 | Construction, KPIs, frontier | Decision, rigour |
| 6-7 | VaR, ES, disagreement | Rigour |
| 8 | EVT and threshold reasoning | Rigour |
| 9 | Backtests, including failures | Rigour |
| 10 | Risk budget and sizing actions | Decision |
| 11 | Stress and macro | Decision |
| 12 | Monitoring triggers | Decision |
| 13 | Assumptions and limitations | Graded |
| 14 | Reproducibility and AI disclosure | Software, rules |

Check the final PDF's page count and read every page. Markdown length is not evidence.

**Tear sheet, one page:** decision; proposed weights; objective and income; risk measures with USD; worst crises; backtest result; three key limitations; triggers.

## 9. Pitch and viva

**Pitch, 10-12 minutes, final five only:**

| Minutes | Content |
|---|---|
| 0-1 | The client's decision and our answer |
| 1-3 | What the mandate requires, in numbers |
| 3-5 | Frontier and what each limit costs |
| 5-7 | How bad, with models and their disagreement |
| 7-9 | Evidence, including what failed |
| 9-10.5 | Crises and what we would change |
| 10.5-11.5 | Triggers and the ask |

**Ten skeptical questions.** These are answer frameworks, not results.

| # | Question | Evidence needed |
|---|---|---|
| 1 | Why is this suitable for a conservative client? | Limits, frontier, crisis table |
| 2 | Does this fund spending after inflation? | Objective arithmetic and income table |
| 3 | Why this much gold, given its income? | Constraint map and alternatives |
| 4 | How did AGG behave in 2022, and why trust it as defence? | Rate sensitivity and 2022 attribution |
| 5 | Why does your MC match parametric? | Same distribution, so it should; show t variant |
| 6 | How was the EVT threshold chosen, and what if it moved? | Diagnostics, sensitivity, exceedance count |
| 7 | Passing Kupiec proves what? | Test meaning, power, exception clusters |
| 8 | How do we know the final test was untouched? | Decision register commit dates |
| 9 | Which fund would you cut first, and why? | Component ES and sizing trade-off |
| 10 | What did AI do, and how did you check it? | Disclosure and human validation record |

## 10. Priorities

**Must fix:** M01-M16 in `PROPOSED_PROMPT_CHANGES.md`.

**Strongest improvements:** S01 frontier, S02 EWMA-FHS, S03 fat-tailed MC, S04 decision rule and triggers.

**Defer or cut:** D01. GARCH-EVT, overlays, ES backtests, 10-day scaling, cash, copulas, wavelets, Student-t beyond S03, extra optimisers.

**Minimum complete defensible submission:** all five layers, the mandatory app, repo, report, tear sheet, human validation, income and real-return arithmetic, crisis-inclusive EVT, decision rule, deterministic candidate table.

**Strongest feasible version:** the above plus S01 with uncertainty, S02, S03 and macro context. Neither version guarantees a result.

**Ordered next actions**

1. Humans answer the decisive inputs below.
2. Apply prompt changes M01-M06 and M16, with S04's rule.
3. Add context data and record the decision register as a commit.
4. Run Steps 3-8 with evidence-preserving checkpoints.
5. Run S01 and S02 only after their dependencies pass.
6. App, then documents, then audit, then viva drills.

**Decisive missing inputs**

- Team membership and who owns each layer.
- The deadline and submission route.
- Whether "mandate as proposed" has any organiser-specified limit.
- Whether judges receive repo access by invitation or the repo must be public.
- Human choices for horizon, spending range and limits.

## 11. Closing

**Change in current prompts:** RF status; mandate coverage for income, real return and macro; constraint and window policy; EVT at 90%; backtest coverage for sidebar methods; the rule-based OOS statement; decision rule; one extension slot.

**Keep:** the solo sequence, data and r3 work, contracts and schema, loss and sign conventions, EVT safeguards, Basel scope, human sign-off boundaries, and core-first ordering.

**Next bounded task:** integrate M01-M06, M16 and S04 into the prompts, without starting Step 3 until the team reviews them.

**What would make the first-place ambition credible in evidence:** a dated decision register; a real accept/adjust/reject outcome tied to limits; crisis-inclusive tail estimates; honest OOS results including failures; a clean-install run; and five people who can each defend the work. We cannot know competitors' work, so credibility is the only thing we control.

## 12. Sources

Search-verified bibliographic details and abstracts unless stated; full texts were not all read.

- [Rockafellar and Uryasev (2000), Optimization of conditional value-at-risk](https://ideas.repec.org/a/rsk/journ4/2161159.html): CVaR optimisation, basis of S01.
- [Hull and White (1998), Incorporating volatility updating into historical simulation](https://www.risk.net/journal-of-risk/2161156/incorporating-volatility-updating-into-the-historical-simulation-method-for-value-at-risk): basis of S02.
- [McNeil and Frey (2000), tail risk for heteroscedastic series](https://www.wu.ac.at/fileadmin/wu/d/i/statmath/Publications/Publications_Frey/Journal_Papers/evt-garch.pdf): deferred conditional EVT.
- [Cederburg et al. (2020), volatility-managed portfolios](https://econpapers.repec.org/RePEc:eee:jfinec:v:138:y:2020:i:1:p:95-117): caution on overlays.
- [DeMiguel, Garlappi and Uppal (2009), Optimal versus naive diversification](https://econpapers.repec.org/RePEc:oup:rfinst:v:22:y:2009:i:5:p:1915-1953): estimation error and the equal-weight reference.
- [Politis and Romano (1994), The stationary bootstrap](https://gnosis.library.ucy.ac.cy/handle/7/57533): uncertainty for dependent returns.
- [Breuer et al. (2009), plausible, severe and useful stress scenarios](https://www.ijcb.org/journal/v5n3/how-find-plausible-severe-and-useful-stress-scenarios): scenario plausibility.
- [Scarrott and MacDonald (2012), EVT threshold review](https://doaj.org/article/b0e7a3fc3d194aedbf2052a4a9020004): threshold rule choices.
- [BIS MAR99 backtesting guidance](https://www.bis.org/committees/bcbs/basel-framework/standard/mar/99/inforce/2019-12-15/published/2019-12-15): cited in existing project review, not rechecked here.
- [SciPy linprog](https://docs.scipy.org/doc/scipy-dev/reference/reference/generated/scipy.optimize.linprog.html): HiGHS solver.
- [yfinance Ticker reference](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html): dividends attribute.
- [NACUBO FY23 spending tables](https://edge.sitecorecloud.io/nacubo1-nacubo-prd-dc8b/media/Nacubo/Documents/EndowmentFiles/2023-NCSE-Public-Tables--Spending-Rates-FINAL.pdf): context for assumption only. The 4.7% figure came from search results and should be confirmed before citing.

Politis-White (2004) block-length selection and a Danielsson et al. model-risk paper could not be confirmed in this session and are not relied upon.
