# Step 8 / B2–B3 implementation and verification — 2026-10-31

**Step 8 is implemented and technically verified. STOP before Step 9.** Human economic inputs, independent human validation and final protocol/recommendation approval remain pending.

Implemented frozen public APIs in `risk_budget.py` and `stress.py` without modifying accepted Step 1–7 engines, config, contracts or data. Normal VaR/ES Euler components include the mean term and shared ddof=1 moments. Historical ES uses the exact shared fractional/tied tail convention. Negative hedge components remain signed; undefined percentages and zero-volatility gradients have explicit states. Allocation comparisons evaluate supplied constraints and optional risk limits without cash, constraint relaxation or selecting a winner.

Historical stress compounds per-asset holdings from initial weights and NAV1, allowing buy-and-hold drift; the initial wealth anchor enters drawdown. Signed asset P&L reconciles to total. All configured GFC/COVID/2022 sessions are required. Hypothetical shocks explicitly name all seven ETFs and remain a deterministic one-step scenario with unassigned duration/probability, not ES. Post-2016 returns were used only in the user's authorized fixed-exposure ex-post stress scenarios; no post-2016 strategy selection/evaluation performance was computed.

## Evidence

- Focused tests: **18 passed**, including independent finite-difference derivatives, Euler identities, fractional/tied historical tails, hedge signs, nonpositive totals, zero-volatility gradient ambiguity, real constraint/risk-limit checks, hand-calculated buy-and-hold drift, drawdown anchor, all-ETF attribution, missing-session rejection and deterministic shock gains/losses.
- Connected suite: **127 passed in 18.16s**. `pip check`: no broken requirements.
- Independent scalar/array verifier: **84 contribution rows, 14 allocations and 8 stress rows** agree. Max absolute differences: total contribution 1.04e-17, marginal 2.78e-17, allocation risk 6.94e-18, stress return/drawdown 4.45e-16. Per-asset USD attribution reconciles separately.
- All **53 source-data hashes** and **87 protected prior-step files** match. Frozen public signatures are retained, and later `pipeline.run_pipeline` remains an explicit Step 9 stub.
- Saved strict JSON authority, **5 CSV tables**, **3 PNG/SVG figures**, offline HTML, JSON-generated methodology and source/artifact manifest. All three figures were visually inspected; source/artifact hashes verified after final export.
- No network downloads, new dependencies, optional frontier/FHS, Git commit or GitHub push were needed.

## Actual illustrative findings

At the frozen terminal-development allocation (SPY33.9337%, AGG40%, GLD26.0663%), recent-window HS99 ES is 1.5018% of NAV/day; full-development sensitivity is 2.1595%. Some allocations with less equity and more GLD have higher historical ES. The equity-cap candidate has lower recent-window ES but higher full-window ES, so the bounded table does not establish a universally preferable allocation.

| Ex-post scenario | Frozen development allocation total return | Maximum drawdown | 60/40 total return |
|---|---:|---:|---:|
| GFC | -9.2350% | -20.7586% | -29.9942% |
| COVID | -12.6783% | -14.6021% | -20.5882% |
| 2022 rate shock | -17.1045% | -17.1045% | -20.5751% |
| Hypothetical joint repricing | -10.6768% | -10.6768% one-step only | -19.8000% |

These are ex-post replay/assumption outputs, not a submitted final recommendation or forecast of future losses. The five candidate targets meet supplied allocation constraints in both windows; equal-weight and60/40 are labelled constraint-breaching references. Actual human VaR/ES limits are null, so risk-limit compliance remains indeterminate. Economic monitoring thresholds are pending rather than fabricated; the engineering data-quality trigger is separate.

Actual numerical authority: `results/step8_risk_stress_preview/step8_results.json`.
Methodology: `docs/sections/b_risk_budget_and_stress.md`.
Reproducible independent checks: `audit/step8_review/verify_step8_results.py`.
Final evidence and hashes: `CODEX_CLOSURE_CHECKPOINT.json`.
