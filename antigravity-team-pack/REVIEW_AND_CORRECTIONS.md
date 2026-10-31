# Review of supplied Quant Edge materials

Reviewed: the official 10-page `Quant edge 1.0 Final Challenge 1.pdf`, the 13-page Claude `Quant Edge 1.0 Winning Study Flow and Antigravity Prompt Pack.pdf`, and `initial prompt.txt`. Page references below refer to those supplied PDFs. Originals are unchanged; this directory contains a revised implementation plan and prompts, not the implemented application.

**Assessment:** the original materials capture the mandate and grading well. The main weaknesses are excessive core scope, a sequential plan being reused for four parallel developers, several tail-risk implementation traps, and premature investment conclusions. The corrected pack preserves mandatory requirements while deferring optional extensions.

## What the official brief actually requires

| Requirement | Official pages | Treatment in revised pack |
|---|---|---|
| USD10M conservative endowment; justified horizon, return objective, allocation/constraints and trade-offs | 3-5 | B produces evidence; team determines and substantiates the final decision |
| Markowitz/CAPM and interpreted KPIs | 7 | B allocation/mean-variance, A KPIs/CAPM |
| Historical, parametric and Monte Carlo VaR on same portfolio at95/99%; explain disagreement | 7 | C, with consistent units/windows and honest normal-MC agreement |
| ES and EVT with justified threshold | 7 | C, including diagnostics and explicit unavailable states |
| Selected-model out-of-sample validation: Kupiec, Christoffersen independence, Basel | 7 | A generic rolling engine; one primary model is sufficient core |
| Marginal VaR/ES risk budgeting, position sizing, crisis paths, hypothetical scenario, actionable recommendation | 8 | B evidence; team judgement; D presentation |
| Approved data, adjusted prices, calendar discipline, log statistical returns/simple-return exceptions, flags, stationarity, reproducibility | 9 | A snapshot and audit trail; diagnostics on actual modelling series |
| Required Streamlit controls/panels and plain-language assumptions page | 5-6 | D, with all six requested views |
| Reproducible judge-accessible repo, app,7-15page memo,1-page tear sheet | 6 | D assembly; paginated final artifacts required, not just skeletons |
| AI disclosure and genuine independent human review/understanding | 8-9 | Every owner logs assistance/checks; humans complete validation |

Official grading is correctly copied: decision-making30%, technical rigor25%, software15%, innovation15%, communication/defence15% (p10). A four-session plan does not alter the official five-person team statement (p2). The10-12minute pitch/deck is for the final five selected teams (p6). No submission deadline is stated in the supplied brief; the cover only says Oct2026.

Python3.11, a2005start, DTB3 specifically, exact crisis endpoints,500-day windows,5bps costs, constraint numbers, parquet and any particular optimizer are implementation choices, not imposed official values. Label them as assumptions and justify them. The confidence90/95/99sidebar itself is mandatory; every extra model variant is not.

## Corrections before coding

1. **Separate mandatory work from extensions.** Pack pp7-9 already asks for Student-t variants, GARCH-FHS, conditional EVT, automated thresholds, ES backtests, reverse stress and correlation stress inside otherwise core prompts. These contradict the core-first advice. Keep historical/normal/normal-MC, unconditional EVT and selected-model rolling validation first. Choose at most one extension after the whole core, documents and review work.

2. **Remove predetermined investment conclusions.** Pack p2 suggests the strongest answer is usually accept with an adjusted ES limit; p12 suggests trusting conditional EVT/t models. The official brief requires team-developed, substantiated judgement. Compare actual evidence, report failures and leave the outcome open until humans evaluate it.

3. **Do not infer a return target from inconsistent arithmetic.** Pack p1's4-5%spending plus inflation does not automatically imply5-6%nominal. State spending, inflation, fees and desired capital growth separately, use consistent arithmetic/compounding assumptions and test feasibility. They are not facts supplied by the endowment.

4. **Make conditional EVT's sign explicit.** Pack p8 gives `mu+sigma*q_z` without defining loss versus return orientation. Derivation: if `R=mu+sigma*Z` and the fitted upper tail is `Z_loss=-Z`, then `L=-R=-mu+sigma*Z_loss`; loss VaR and ES therefore use `-mu`. Unconditional POT-GPD is the revised core, so there is no reason to rush this extension.

5. **Fix EVT sample-size and domain constraints.** With500observations a95%threshold gives about25strict exceedances, not the stated minimum50 (pack p8). Use a sufficient window and check actual counts. A fitted95%tail cannot supply90%tail VaR. Return unavailable below the threshold domain; do not silently lower the threshold or substitute another model. To compare EVT against conventional methods, keep the same risk window for all.

6. **Use threshold-adjusted scale stability.** The threshold-stability relation is `beta(v)=beta(u)+xi*(v-u)`, so algebraically `beta(v)-xi*v=beta(u)-xi*u`. Plot that modified scale alongside xi, not a claim that raw beta should remain constant. Also show MRL, counts, QQ/PP and sensitivity. This is the derivation underlying the revised diagnostic. [Primary threshold-stability presentation](https://lbelzile.github.io/EVA2025-choosing-threshold/EVA2025-choosing-threshold.html).

7. **Do not invent GPD goodness-of-fit p-values.** A fitted-GPD AD rule must account for parameter fitting, ideally refitting in each parametric-bootstrap sample; searching thresholds introduces further selection issues. Diagnostics plus justified sensitivity are a practical core. Automated calibrated GOF is an extension, not a one-line generic AD call. [SciPy fitted-distribution GOF documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.goodness_of_fit.html).

8. **Handle GPD limits and uncertainty.** Fix excess location at0, check negative-shape support, use the exponential limit near xi=0 and do not report finite ES when xi>=1. Show uncertainty and dependence/threshold-selection limitations. Fit-only iid intervals are not full uncertainty for clustered financial returns. [SciPy GPD support and parameterization](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.genpareto.html).

9. **Keep the allocation universe fixed.** Pack p9's overlay to AGG/cash introduces cash outside the seven eligible ETFs. The revised core redistributes only among eligible ETFs. A later cash extension needs an explicit interpretation/organiser clarification rather than silently extending the universe.

10. **Distinguish scenario loss from ES.** A deterministic equity shock produces scenario P&L, not a probability-weighted ES estimate. A reverse stress can target a scenario-loss tolerance, or a specified altered return distribution. It cannot simply relabel scenario loss as an ES breach (pack p9).

11. **Prevent selection and timing leakage.** The old plan says no look-ahead but needs interfaces enforcing it. Freeze selection/evaluation boundaries; weights for day t and its forecast must be based on earlier information. Let holdings drift between rebalances and charge stated costs. Historical replay of today's chosen weights is a scenario diagnostic, not investable OOS history. Perturb future data to verify earlier outputs stay fixed.

12. **Keep one-session returns one-session.** Dropping a missing price date and then taking pct_change bridges a gap. Preserve the expected session grid while calculating returns without fill; flag/exclude affected return intervals afterward with counts. Expose interruptions so strategy plots and the250-day diagnostic do not falsely claim complete coverage. Missing-row exclusions and retained suspicious-outlier flags are different operations.

13. **Document RF quote conversion and availability.** DTB3 is a daily series quoted in annual percent on a discount basis. Dividing rate/100by252 is an approximate trading-day proxy, not an exact realized bill return. Preserve raw quotes; choose/document observation availability lag, forward align only from available values, avoid initial backfill and disclose revisions/publication uncertainty. [FRED DTB3 source metadata](https://fred.stlouisfed.org/series/DTB3).

14. **Do not manufacture VaR disagreement.** Normal analytic risk and MC from the same normal mean/covariance should agree within simulation error. Explain measured historical-versus-normal differences; do not call finite simulation noise innovation. Use the same fraction/percentage units, simple-loss mapping, horizon and sample.

15. **Keep Basel applicability exact.** Standard green0-4/yellow5-9/red10+ bands are for250one-day99%forecast/realization pairs. Do not reuse the colors for90/95%or incomplete histories. A99%/250-daydiagnostic can appear separately from the sidebar-selected confidence; expected exceptions are only2.5. This is an educational backtest diagnostic, not regulatory approval or a guarantee. [BIS primary application guidance, MAR99](https://www.bis.org/committees/bcbs/basel-framework/standard/mar/99/inforce/2019-12-15/published/2019-12-15).

16. **Unify risk contributions and total risk.** Euler sums require the same homogeneous risk definition, mean/covariance and empirical ES tail weights. Using Ledoit-Wolf in contributions but sample covariance in the dashboard gives different totals. Historical ES needs a consistent fractional-tail/tie convention. Negative hedge contributions are valid; abs() is not a fix.

17. **Check the original constraint implications.** In the seven-ETF universe, max35%equities implies AGG+GLD>=65%, making the proposed40%AGG+GLD minimum redundant. With each fund capped at40%, AGG and GLD must each be at least25%. This combination is feasible, but forces a substantial gold allocation. Do not report it as inherently infeasible or adopt it without explaining suitability; additional vol/ES caps still need feasibility checks.

18. **Fix practical dependencies and platform assumptions.** The original free-library list omits required yfinance, a YAML parser and a parquet engine. PNG Plotly export can add dependencies that a time-limited core does not need. Verify compatible pinned versions instead of inventing them; use editable/package installation for the src layout and provide Windows PowerShell setup. One-command app launch is after documented setup.

19. **Finish actual submission artifacts and human review.** A Markdown memo skeleton is an interim draft, not a checked7-15pagefinal report. A tear-sheet heading does not guarantee one-page pagination. Fill human reasoning, inspect final exports, complete the true validation record and be ready to defend formulas. AI-generated test logs must not be presented as independent human validation.

## Why this four-way split

A finishes the common data early, then has useful KPI/validation work while B constructs allocations and C develops tails. Backtesting belongs to A so C is not overloaded by EVT plus a second major subsystem. B owns the investor-action evidence: allocation, contributions, sizing and scenarios. D owns the shared baseline and integration, while A/B/C each supply their methodology/limitations, so D does not write every analytical explanation alone.

The roles are balanced by dependency and complexity, not by dividing18old prompts into four equal counts. Separate clones/worktrees, one schema, one snapshot, unique file ownership, milestone handoffs and one integration audit reduce repeated work. Actual usage savings depend on implementation/debugging; no specific Antigravity quota, pricing or model availability has been assumed or verified here.
