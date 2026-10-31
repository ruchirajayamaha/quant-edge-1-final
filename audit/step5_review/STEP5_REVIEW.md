# Step 5 / C1 review - 2026-10-31

**The baseline risk mathematics and all 54 saved comparison rows are independently correct. Address R1-R2 and finish the requested visible exports before Step 6.** Preserve the accepted estimator formulas, empirical-tail rules, original datasets and baseline 25,000-draw results.

This review inspects actual `var.py`, `es.py`, tests, the recorder script and saved result bundle. It creates audit artifacts only; no production estimator/config/data was edited. No selection/evaluation strategy outcomes were computed.

## R1 [P2] Supplied configuration is not propagated to the actual risk engine

Locations: `src/quantedge/var.py:423`, `:1060`, and `:1153`.

`build_development_c1_risk_bundle(asset_returns, config)` reads and reports its supplied config's simulation count/hash and uses that count for the MC-uncertainty helper. But its comparison tables call `estimate_risk`, which always resolves the separately cached default config. The test labelled config-authority tests only the unchanged baseline, so it does not expose this mixed-settings path.

Repro uses a synthetic 80-session 2015 frame and an AppConfig with a 20-day portfolio estimator, 40-day recent risk window, seed 42 and 111 MC draws. The builder returns normally:

| Output | Draw count |
|---|---:|
| Claimed bundle setting | 111 |
| Actual MC comparison rows | 25,000 |
| MC-uncertainty runs | 111 |

Thus the uncertainty corresponds to a different simulation workload from the displayed primary estimates. With the current default config all are 25,000, so existing baseline numbers are valid. The issue matters when a caller supplies a different AppConfig or expects reproducible config-bound results.

Pass one coherent resolved configuration through an internal engine/config-bound helper while preserving frozen D0 public signatures, or explicitly reject unsupported non-default settings before returning any mixed bundle. Avoid a broad API redesign. Test a genuinely different requested draw count and settings/hash consistency, preserving baseline results. Static text about 25,000 draws/precision must either use actual resolved values or be explicitly baseline-only.

## R2 [P2] The exported risk JSON contains non-standard NaN tokens

Location: `scripts/record_step5_c1_results.py:76`; artifact: `results/step5_development_c1_risk_tables.json`.

Mixed-type DataFrame columns convert not-applicable historical/normal `seed` and `monte_carlo_simulations` values to floating NaN. `json.dumps` defaults to allowing them, so the saved file includes entries such as `"seed": NaN`. A strict parse rejects it. Python's permissive default parser masks the interoperability issue; JSON readers used by web/report tools can fail.

Use JSON `null` for genuinely not-applicable metadata, and enforce `allow_nan=False` at serialization. Do not silently turn invalid actual risk estimates into zero or hide a model failure by indiscriminate sanitization. Maintain finite valid risk values and explicit unavailable reasons. Test the actual full export structure with strict parsing. A byte copy of the original artifact is saved as `baseline_step5_results.json` to compare valid numeric values after regeneration.

Numbers such as NaN/Infinity are excluded by [RFC 8259 section 6](https://www.rfc-editor.org/rfc/rfc8259.html#section-6). The demonstrated parser rejection is also recorded in `verification.json`.

## Visible-output delivery gap

The JSON and methodology tables exist, but the requested Step 5 CSV/PNG/SVG exports are not present. During the same bounded correction, export the verified comparison tables and at least (1) a same-exposure 95/99 VaR/ES method comparison and (2) a correctly labelled fixed-exposure loss distribution with selected risk markers. The plotting path must consume computed results, not implement another risk engine. Reuse the isolated Matplotlib tooling already available for the Step 4 previews. This requires no new financial model or final-period evaluation.

## Independent evidence already passed

- Connected suite independently rerun: **69 passed in 12.58s**.
- 450 random discrete-loss cases checked against exact Python Fraction-based quantile/tail integration, including ties, negative losses/gains, fractional mass and permutation equivariance. Maximum ES difference **3.55e-15**.
- All **54** baseline saved risk rows match freshly evaluated estimates **exactly**. Separate scalar sorted-tail integration and standard-library `statistics.NormalDist` formulas agree within **2.08e-17**. Sample bounds/counts and USD conversions also match.
- Default normal and MC estimators use the same fitted moments; nonpositive risk quantiles and zero-volatility warnings are preserved. EVT is honestly deferred. Current exposures are labelled as terminal-development fixed-exposure diagnostics, not a historical OOS investment track record.
- **53/53** market/context file hashes match. Config, requirements, contracts, active pointer and accepted Step 3/4 sources remain unchanged.
- Reported hashes for `var.py`, `es.py` and the saved Step 5 JSON match actual files in this report.

## Next action

Use `ANTIGRAVITY_STEP5_FIX_PROMPT.txt`. One bounded correction/export pass is sufficient for these findings. Do not start rolling backtests, EVT, app work, optional innovations or another data audit. Return actual tests/results and then stop for the user's required review before Step 6. Human validation and committee decisions remain pending.
