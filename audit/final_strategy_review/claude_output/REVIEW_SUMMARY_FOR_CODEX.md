# Review summary for Codex

Reviewed commit `d7ccafe`, dataset `qe1_20050101_20261030_r3_6c4633a7ba`. All 10 PDF pages were read, and 41 tests pass. All 16 analytic functions are still stubs. There is no memo, tear sheet, result bundle or human validation. Full detail: `FINAL_ROUND_REVIEW.md`. Paste-ready text: `PROPOSED_PROMPT_CHANGES.md`. Nothing was applied.

## Essential corrections

1. **Window excludes crises.** The last 1,260 sessions start on 2021-10-25, missing 2008 and March 2020. Report a long crisis-inclusive window as the tail default, plus a labelled recent window. Each comparison uses one window (M06).
2. **EVT at 90%.** Page 5 wants VaR, ES and EVT side by side at selectable 90/95/99. The plan shows unavailable at 90%. Add thresholds below the 90th percentile, and resolve config's fixed 0.95 against C2's grid (M07).
3. **Mandate gaps.** Page 3 requires income and real growth, and the rubric assesses optional macro items. Add hashed dividend and FRED context data, separate from ETF snapshots, and objective arithmetic `R=(1+i)(1+g)/(1-s-f)-1` (M02, M16).
4. **Constraints form a corner.** The provisional caps force AGG and GLD to 25-40% and equities to 20-35%. Publish a constraint map and test named alternatives on development data (M05).
5. **Validate rules, not hindsight weights.** Final weights are the rule applied at data end. Replay is a scenario. Commit a dated decision register before Step 3 results (M05).
6. **Backtest every sidebar method.** Remove "unavailable" states. Report longest OOS and frozen evaluation spans (M09).
7. **Prompt conflicts.** Ledoit-Wolf against sample covariance with no scikit-learn, and MC draws 50k/100k against config 25,000 (M05, M08).
8. **Stale RF text.** Update to r3 wording (M01).
9. **Page 8 trace.** The tear sheet carries the plain-English accept/adjust/reject statement and is also report page 1. No third document. This is an interpretation (M13).
10. **Source disclosure.** List ALFRED and Fed H.15 archives as RF evidence (M13).
11. **Human defence.** Page 9 allows mark reduction or disqualification. Make validation and viva drills a planned workstream, with named layer owners (M04, M15).

## Top differentiator

**Primary: Mandate Feasibility Frontier (S01).** An ES-limited LP (Rockafellar-Uryasev, `scipy` HiGHS) finds the best eligible return for each downside budget. Scenario-loss limits are linear rows, so reverse stress comes with it. Three expected-return sets and a stationary bootstrap show whether the decision is robust. It maps directly to accept, adjust or reject, which serves the 30% criterion and innovation. A synthetic-only probe solved the LP in under 0.2 s at 5,491 scenarios. This is integrated standard methodology, not a novelty claim.

- **Keep if:** LP ES matches C1 ES, infeasibility tests pass, and it changes or quantifies a committee statement.
- **Fallback:** a deterministic table of about five candidates under the same decision rule.

**Complement: EWMA filtered historical simulation (S02).** It covers the rubric's regime-conditioned example, needs no new dependency, and uses fixed λ=0.94. Report a worse result honestly. Drop it if nobody can defend it.

**Defer or cut:** GARCH-based EVT, overlays, ES backtests, 10-day scaling, cash, copulas, wavelets.

## Decisions still empirical

These are TO BE DETERMINED EMPIRICALLY: final weights; best risk model; whether any portfolio meets the limits; accept, adjust or reject; EVT threshold; backtest outcomes; whether S01 or S02 adds decision value.

## Human inputs needed

- Team members and layer owners.
- Deadline and submission route.
- Whether organisers define "mandate as proposed" limits.
- Judge repo access.
- Horizon, spending range and limits.

## Ordered next actions

1. Humans answer the inputs above.
2. Apply M01-M06, M16 and S04 to prompts.
3. Build context data and commit the decision register.
4. Run Steps 3-8 with existing checkpoints.
5. Build S01 and S02 only after dependencies pass.
6. Build the app, then documents, then the audit with fresh-install proof.
7. Run human viva drills.

Keep the solo sequence, schema `1.1.0`, r3, sign conventions, EVT and Basel safeguards, and human sign-off rules. No ranking is implied or guaranteed.
