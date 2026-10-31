# Review of the proposed RF-only r3

**Decision: implement an RF-only r3 before RF-dependent Step 4. Price-only minimum-variance Step 3 remains unblocked. Approve the research direction with the additional conditions below, rather than copying the proposed date-only design unchanged.**

Reviewed on 2026-10-31: the actual research report, saved evidence, analysis scripts, current r2 configuration and relevant primary Federal Reserve pages. No source/config/dataset changes were made in this review. Existing audits remain historical records; their earlier schedule-safety assessment does not supersede the new evidence.

## Confirmed reason to improve r2

Federal Reserve notices explicitly postponed H.15 releases on January 22, 25 and 26, 2016. The actual r2 RF for return session 2016-01-28 annualizes to 0.31%, from observation January 25. The research's archived vintages place its appearance on January 27; under the project's assumed 16:15 release and 16:00 preceding-close cutoff it cannot be used at that decision origin. This supports a genuine release-calendar correction, not just wording changes. [Federal Reserve H.15 notices](https://www.federalreserve.gov/feeds/h15.html).

## Conditions for implementation

1. **Handle rate values as well as release dates.** The research proposes retaining the latest raw values while delaying their availability. That does not remove revision look-ahead. The Federal Reserve documents observation 2005-01-07 changing from 2.29% to 2.28%; the correction notice is dated November 13, 2017. Use supported as-of vintage values and archived original values, not a later correction at an earlier decision date. Sparse or unresolved history must remain explicitly labelled. [Correction table](https://www.federalreserve.gov/releases/h15/historical-data-correction.htm), [correction announcement](https://www.federalreserve.gov/feeds/h15.html).

2. **Stitch request chunks globally.** The current research analysis skips records already present in each chunk's first vintage. That was useful for sampled first-appearance inference but is unsafe as the complete-history builder: it can miss appearances exactly at request boundaries. Sort and deduplicate all actual vintage headers globally, validate requested/returned vintage identities, and evaluate transitions across adjacent chunks. Reuse cached chunks and the observed 12-column request limit.

3. **Preserve coverage distinctions.** Day-level vintage evidence is not an exact first-publication timestamp. Do not apply ALFRED's first June 2005 vintage date to every older observation. Mark archived-evidence, vintage-supported, calendar-fallback and unresolved cases separately; publish coverage counts. Keep assumptions visible for the sparse early era.

4. **Separate documented defects from inferred cases.** The 25 closure-affected sessions include six based on ALFRED absence alone, not independently documented Board closures. The evidence review maps 19 to explicit notices. Report confirmed, inferred and unresolved groups separately. The reported -0.00146 bp/year is a signed sample-average difference, not a worst-case bound; it includes cancellation and assumed cases. Report absolute/per-session changes too.

5. **Keep conversion sensitivity separate.** Retain DTB3 and `/252` as the existing primary convention. A 91-day accrual calculation is a labelled assumption-based sensitivity, not an exact realized Treasury return. It need not expand the RF availability fix into another research project.

## Acceptance evidence

Preserve v1/r2 hashes; prices and simple/log returns must be identical. Verify closure and omitted-release cases, the January 2005 revision, a first appearance at a 12-vintage chunk boundary, sparse-history labels/no artificial June 2005 staleness jump, version-aware as-of selection, policy-aware hashing/cache isolation and normal offline loading. Save per-return provenance so the selected observation, selected vintage/value and availability evidence can be inspected.

Construct candidate r3 separately. Activate it only after the actual integrity, regression and offline checks pass; preserve both older snapshots and disclose remaining gaps. Automated verification must not be recorded as human validation. A new RF snapshot does not require recomputing price-only portfolio paths.
