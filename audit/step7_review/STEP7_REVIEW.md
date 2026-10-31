# Step 7 independent review — 2026-10-31

**Numerical implementation checks pass. Finish one bounded documentation/export correction before Step 8.** No estimator rewrite, refit, bootstrap rerun, new dataset or strategy tuning is needed for these findings.

## Verified

- Connected suite independently rerun: **105 passed in 22.28s**.
- Six saved hybrid rows checked independently, including exact rational empirical-body probability integration: max error **5.21e-18**. Both threshold values and strict exceedance counts agree with offline development returns.
- All 18 saved C1 comparison rows match the Step 5 authority **exactly**.
- All **24** bootstrap percentile/count/availability summaries recompute from the stored replicate values. Pure-POT 95% intervals correctly remain unavailable at 58/100 and 62/100 valid replicates, below the required 80.
- All **15 artifact hashes** match, and **75 protected files** remain unchanged. See `CODEX_REVIEW_VERIFICATION.json` and the separate source-data verifier.

## R1 — Section 7 numerical tables and narrative disagree with the authoritative JSON [P1]

`docs/sections/c_var_es_and_evt.md` Section 7 contains incorrect manually transcribed numbers even where the machine-readable outputs are correct. Examples:

| Value | Section 7 | Saved authority |
|---|---:|---:|
| Recent Historical ES90 | 0.6976% | 0.7012616% |
| Recent Historical ES95 | 0.8797% | 0.9061438% |
| Full Historical ES90 | 1.0435% | 0.9688480% |
| Recent hybrid ES95 minus Normal, bps | 109.11 | 10.9107820 |
| Full hybrid ES99 minus Normal, bps | 747.67 | 74.7667561 |

Several USD and EVT point values also differ. Many displayed method differences have a factor-of-ten unit error. One basis point of NAV is 0.0001 of NAV, so differences in loss fractions multiply by 10,000.

The actual hybrid 95% bootstrap intervals are:

| Window | VaR interval (%) | ES interval (%) |
|---|---|---|
| Recent | [0.5166550, 0.6488752] | [0.7598756, 1.0497135] |
| Full | [0.7445693, 0.8853878] | [1.1299235, 1.4515906] |

Section 7 quotes different hybrid intervals. The pasted completion report additionally gives numerical pure-POT 95% intervals despite the authority correctly suppressing them. Generate ALL Section 7 tables and corresponding numeric prose directly from the saved JSON; preserve Sections 1–6. Add a meaningful document/artifact consistency check covering all comparison cells, USD/bps conversions and every bootstrap CI/status/count. The existing verifier checks no numeric body-region outputs and no bootstrap intervals; it must not be described as proving those without additional checks. Codex's supplemental checks above cover the actual saved values independently.

## R2 — Interpretive and implementation claims overstate the evidence [P2]

The pasted report says positive fitted xi confirms Frechet behaviour and rejects Gaussian tails. The recorded moving-block xi percentile intervals are **[-0.12343, 0.49390]** recent and **[-0.00776, 0.43297]** full: both include zero. Positive point estimates are consistent with heavy tails under the fitted model; this alone is not a formal rejection of Gaussianity. QQ/PP plots are descriptive fit diagnostics, not proof of fit quality.

The empirical body is a step CDF with atoms, not a smooth continuous distribution. At the threshold, the right-tail limit matches F(u), but there is generally a left jump at u. Body ES is exact discrete quantile integration plus analytic tail integration, not trapezoidal integration. The bootstrap uses fixed-length moving blocks, not the distinct stationary bootstrap. The current asymptotic iid SE formula is analytic, not covariance extracted from an observed Hessian. Current optimizer settings are maxiter=20,000/maxfun=40,000, rather than the claimed 2,000. The inherited policy is recorded before development fitting but remains unsigned, not completed human preregistration. Correct such claims in docs/handoff/disclosure and the new completion report wherever present.

## Provenance/export completion

The Step 7 manifest records artifact hashes but omits source hashes. Add the current EVT/recorder/exporter and applicable config/contracts/var/es sources, plus the authority digest, after final edits/export. Keep the valid numerical authority and earlier outputs unchanged. Label standalone figures DEVELOPMENT ONLY, fixed exposure and one-day pre-cost units; exact recent bounds begin 2011-12-29, not 2012. No extra financial models are requested.

Use `ANTIGRAVITY_STEP7_FIX_PROMPT.txt`; stop again for review before Step 8. Human validation remains pending.
