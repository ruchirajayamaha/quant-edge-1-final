# RF research recommendation: DTB3 availability and conversion

Review date: 2026-10-31. Active dataset: `qe1_20050101_20261030_r2_cd2904443b`. No code, configuration, dataset or active pointer was changed. Both snapshots still pass their manifest hashes (13/13 and 15/15), and the active pointer is unchanged. New files are only under `audit/rf_research/`.

## Verdict

**Step 3 can proceed now.** Minimum-variance construction uses prices only. `portfolio.py` has no RF input, and nothing below changes prices or returns.

**The schedule assumption has a proven defect, but it is economically negligible.**
- `rf_daily` used an unreleased observation on **25 sessions** because of Board closures. At least **4 more** value-changing sessions come from Treasury data missing from a release. The largest error is 5 bp of annual quote, and the total effect is about **-0.0015 bp per year**.
- "Conservative" is therefore not an accurate description of the current series. It is a schedule proxy with known exceptions.

**The conversion matters more than the timing, though it is still small.** `/252` understates 91-day bill accrual by about 8 bp per year over 2021-2026, and by 15 bp in 2024.

**Exact intraday point-in-time data cannot be claimed.** Day-level vintage evidence is available without a key; historical release timestamps are not.

Recommendation: start Step 3 on r2, then derive an `r3` RF-only snapshot before Step 4 makes any "publication-aware" claim. Keep DTB3, and report the conversion as a sensitivity.

## Q1. Can we get vintages and release evidence?

Yes at day level, without a key, with limits.

| Route | Tested result |
|---|---|
| `alfredgraph.csv?id=DTB3,...&vintage_date=...` | **Works without a key** and honours vintages. Silently returns only the **first 12 series** per request. |
| `fredgraph.csv?...&vintage_date=2008-10-01` | **Do not use for vintages.** It returned rows through 2008-10-01, while ALFRED's vintage for that date ends at 2008-09-29. Column header stayed `DTB3`. |
| ALFRED `release/downloaddates?rid=18&ff=txt` | Works. 4,049 dates, 1996-12-09 to 2026-10-30. |
| ALFRED `series/downloaddata?seid=DTB3` | Page works and lists 5,142 DTB3 vintages from 2005 (first 2005-06-28). Scripted POST failed: one returned the form, one HTTP 500. Route dropped. |
| FRED API `series/vintagedates`, `series/observations` | **Needs a registered key.** No-key call returned error 400, "Variable api_key is not set". No key was used or invented. |
| Fed dated H.15 archives and notices | Work without a key. |
| Wayback captures | HTTP 429 on two capture requests. Stopped; nothing obtained. |

Sample actually pulled: about 125 ALFRED GET requests, about 1,320 of 5,142 vintages, and exact first appearance for 1,281 observations (1,232 from 2006-02 onward). 29 of the runs deliberately target unusual days, so lag tails below are overstated. A full pull would take about 430 GETs. I stopped short of that because this was a bounded check.

**Coverage and gaps**
- ALFRED has no DTB3 vintage before 2005-06-28, so values through that date have no true first-release record.
- Vintages are about weekly until 2006-02, then roughly daily (about 245 a year).
- The H.15 release list is weekly until 2014, then daily from about 2014-04.

**Revision evidence**
- All 1,280 comparable sampled first values equal the snapshot.
- Twelve full-history vintages show exactly 3 differences before 2017, and all 3 are in the Fed's [2017 correction table](https://www.federalreserve.gov/releases/h15/historical-data-correction.htm): 2004-11-23 (2.13 to 2.15), 2004-11-30 (2.20 to 2.19), 2005-01-07 (2.29 to 2.28). The snapshot holds the corrected values.
- Only 2005-01-07 falls in the return period. Stored RF for 2005-01-12 uses 2.28 where 2.29 was then published.
- The value check is a sample, not proof for every observation. The yearly snapshots catch lasting revisions, not ones made and undone between them.
- One transient case: 2011-04-22 (a blank day) showed 0.06 in the 2011-05-02 and 05-03 vintages, then went blank again.

## Q2. Four dates that must stay separate

| Concept | Evidence | Limit |
|---|---|---|
| **Observation date** | Treasury says quotes are taken by the New York Fed [at about 3:30 PM](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics). | Quote time, not publication. |
| **Source publication** | [H.15 page](https://www.federalreserve.gov/releases/h15/): 4:15pm Monday-Friday, not on holidays or when the Board is closed. A dated notice gives the same time on 2016-10-11. Archives say "For use at 2:30 p.m." on sampled Monday releases in 2006, 2008 and 2010. | Sampled 2013-2016 archive pages give no time. Tuesday-Friday daily-update hours before 2016-10 are undocumented. |
| **FRED update time** | One value: 2026-10-30 3:16 PM CDT (16:16 ET). | Latest update only, so not a historical record. |
| **ALFRED vintage date** | Day-level only. | Not first publication; it can be wrong in **both** directions. |

Proof that a vintage date is not first publication:
- **Too late:** the Fed's [2008-12-22 Monday release](https://www.federalreserve.gov/releases/h15/20081222/) (2:30 p.m.) contains the 12-19 value; ALFRED first shows it on 12-23.
- **Too early:** obs 2015-04-01 and 2015-04-02 appear in vintages dated the same day, which conflicts with next-day publication.
- **List conflict, Sandy:** ALFRED lists 2012-10-29 as an H.15 date, but the [Fed notice](https://www.federalreserve.gov/feeds/h15.html) says the Board was closed. The list contains the dates "when any series from this release was revised".
- **List conflict, January 2016:** 2016-01-22 is listed, yet the notice says the release moved and DTB3 did not update until 01-27.
- **Not a timestamp:** the H.15 XML feed shows `16:15:00-05:00` in October, when New York is on -04:00, and items carry `12:00:00-05:00`. Those are labels, not measurements.

## Q3. Is the schedule reasonable?

**Key finding: the hour does not create look-ahead.** Observation `d` is assumed available at `d+1` 16:15 but is first used at the `d+2` 16:00 close, almost a full day later. Any release during `d+1` gives the same result, and an earlier release only makes us over-delay. Look-ahead needs a **missed publication day**, so the unknown hour is not a safety problem. Day-level evidence is what matters.

| Case | Status | Evidence |
|---|---|---|
| Ordinary days, 2016-10 onward | Supported at day level | 567 of 580 sampled first vintages equal the scheduled date. |
| Ordinary days, 2013 to 2016-09 | Supported at day level | 276 of 293 equal it, 14 come later and 3 come earlier. |
| Ordinary days, 2006 to about 2012 | **Unverified, not proven unsafe** | Vintages come after the schedule on all 259 samples in 2006-2010, 43 of 45 in 2011 and 13 of 54 in 2012, mostly `d+2`. Only 12 of the 70 late cases in 2011-2016 are closure-window runs. The Monday 2:30 p.m. proof shows vintages can trail publication, but Tuesday-Friday behaviour is unknown. |
| Board closures | **Proven defect** | 27 scheduled days had no release: 21 per Fed notices, 6 from ALFRED absence only (2017-01-20, 2018-03-02, 2018-12-24, 2020-12-24, 2021-01-20, 2024-12-24). Causes 25 stored sessions, 19 of them value-changing. Example: return 2016-01-28 uses 01-25 (0.31), but the corrected value is 01-20 (0.26). |
| Treasury data omitted from H.15 | **Proven defect** | Fed notices for 2018-09-17, 2020-08-19, 2023-08-01 and 2023-09-12. |
| Late December 2025 | **Unresolved conflict** | H.15 dates 12-24 and 12-26 are listed, but DTB3 first updates on 12-29. Treated conservatively in the materiality figure. |
| Good Friday and blank DTB3 days | **Unnecessary delay, safe** | Releases exist on most recent Good Fridays (for example 2021-04-02, but not 2015-04-03). The code skips these days and also treats blank DTB3 dates as non-publication. 22 sessions over-delayed. |
| Saturday-holiday Fridays, Juneteenth 2021, 2025-01-09 | Correct | ALFRED shows no release on 2023-11-10, 2021-06-18 or 2025-01-09. |
| Early equity closes | No effect | 13:00 cutoffs on 45 candidate days changed 0 sessions, because no assumed release falls between 13:00 and 16:00. |
| DST | No defect | Both times are New York local, so the 15-minute gap holds. Cutoffs fall at 20:00 or 21:00 UTC. |
| Federal closure with release anyway | Do not over-generalise | The Fed listed H.15 as releasing on schedule on 2018-03-21. |

Materiality, with no portfolio returns inspected so the frozen chronology stays untouched:

| Change from stored `rf_daily` | Sessions changed | Largest quote change | Annual effect | Sharpe effect at 10% vol |
|---|---:|---:|---:|---:|
| Closures and Good Friday corrected | 33 | 0.05 pp | -0.0004 bp | about 0 |
| Plus omitted-data cases | 37 | 0.05 pp | -0.0015 bp | about 0 |
| Upper sensitivity: one more day everywhere | 3,721 | 0.81 pp | -0.035 bp | -0.00004 |

The third row shows that even if the unverified 2006-2012 period were a full day late, the effect would remain negligible.

## Q4. Options

| Option | Effort | Removes | Does not remove |
|---|---|---|---|
| **A. Keep r2, fix wording** | Minutes | Misleading "conservative" wording | The proven sessions |
| **B. Evidence calendar** (closures, Good Friday, omission overrides) | About 2 hours | Every case found here | Unannounced misses; sampled days only for omissions |
| **C. B plus full first-vintage table** (recommended) | About half a day; one 430-GET pull | Day-level dependence on schedule alone from 2006-02 | Vintage-date errors; adds about one day of possibly unneeded delay through about 2012; sparse era remains schedule-based |
| **D. Verified intraday timestamps** | Not feasible | Nothing obtainable | No historical source was found. Also unnecessary given the Q3 finding. |

None of these delivers exact point-in-time history. Option C earns a narrower true claim: *no observation is used before the later of a documented publication calendar and its first ALFRED vintage date, from 2006-02 onward.*

A registered FRED key might replace the 430 GETs with `output_type=4` (Initial Release Only). That is documented but untested here.

## Q5. Conversion is a separate issue

DTB3 is a [360-day bank-discount quote](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_bill_rates&field_tdr_date_value_month=202610) based on par, not a return. H.15 footnote 4 confirms "On a discount basis".

| Daily conversion, 2005-2026 | Annualised |
|---|---:|
| `rate / 252` (stored) | 1.798% |
| Discount on actual/360 | 1.827% |
| 91-day bill accrual, `(1/P)^(days/91) - 1`, `P = 1 - d*91/360` | 1.836% |
| Mark-to-market, 91-to-90-day bill | 1.832% |

- The gap to accrual averages 3.8 bp a year, peaks at **15.2 bp in 2024**, and is **8.0 bp a year over 2021-2026** (Sharpe about -0.008 at 10% vol). `/252` also ignores calendar days: Mondays accrue about 1.5 bp on average against 0.7 bp under `/252`, up to 4.9 bp in one session.
- **No yield conversion is a realised return.** Mark-to-market moved from -18 to +21 bp around 2008-09-17 to 09-19. An exact figure needs actual bill prices by security. The accrual also assumes a fixed 91-day term, while the bill's real remaining term varies; I did not quantify that effect.
- **Alternatives:**
  - Treasury's 13-week discount equals DTB3 on all 710 days compared (2008, 2020, 2026). It adds no independent information, and Treasury is not on the project's approved core source list.
  - Its coupon-equivalent matches the formula within 0.013 pp.
  - `DGS3MO` is FRED-eligible but is an interpolated par yield, not an instrument: about 5.3 bp above DTB3 on average and up to 13 bp from coupon-equivalent. Switching changes the quote basis, not the realism.

**Recommendation:** keep DTB3 and the frozen `/252` as primary for comparability. Add 91-day accrual as a labelled sensitivity. Changing the primary formula is a team decision.

For realised KPIs, which need no availability rule, the rate for interval `t-1 to t` is the quote at `t-1`. `rf_daily_ex_post` uses the quote dated `t`. The difference is about 0.0003 pp a year, so this is a documentation point only.

## Q6. Does anything block Step 3?

**No.**
- **Not blocked:** minimum variance, equal weight, 60/40, return paths, weights, turnover, costs and drawdown. All are price-only.
- **Usable with disclosure in Step 3:** frontier or CAPM expected-return framing at rebalance dates. Use `rf_daily` and do not describe it as point-in-time.
- **Affected later:** Step 4 Sharpe, Sortino, Treynor and alpha may use the proxy, but the report should state the conversion sensitivity. Only the wording "publication-aware", "conservative" or "no look-ahead" for RF is restricted until r3 exists.

## Recommended minimal design (not implemented)

Rule, using the existing `release_timestamps` argument so the alignment logic stays unchanged:

`available_at(d) = max(next calendar publication day, first_vintage_date(d)) at 16:15 New York`

- Apply `first_vintage_date` only from 2006-02-03. Earlier dates use the calendar, otherwise everything before 2005-06-28 would wrongly wait for that first vintage date.
- The calendar is Federal holidays plus an evidence closure list. Good Friday stays publishable, and blank DTB3 dates no longer block publication.
- Values stay as in the raw snapshot. Do not import withdrawn vintage values such as 2011-04-22.

| Area | Change |
|---|---|
| `scripts/` | New one-off evidence builder, at most 12 vintages per request, throttled to 1 request per second. |
| `data/raw/<new id>/` | New `dtb3_release_evidence.parquet`: obs date, first vintage, calendar date, available_at, evidence type, source URL. |
| `data.py:758` | Map a new policy ID. |
| `data.py:1560` | Pass `release_timestamps`. |
| `data.py:872` | Dataset ID has `_r2_` hard-coded; derive it from the revision. |
| `data.py:848, 894, 1516, 1684, 1807` | Revision defaults and arguments. |
| `data.py:1086` | Update the verification label to say day-level, intraday unverified. |
| `config.py:358` | Allow the new policy ID. |
| `config.yaml` | New policy and evidence path. |
| Step 4 KPI notes | Report the accrual sensitivity. |
| Docs | Correct the "conservative" wording in docs and manifest text; keep old audits as written. |

**Versioning:** create `r3_release_evidence` with `parent_dataset_id` set to r2, derived offline. Do not overwrite v1 or r2. Move the active pointer only after human sign-off. Bump the schema only if contract fields change. Weights built on r2 stay valid because prices and returns are identical.

**Acceptance tests**
1. Prices, simple and log returns equal r2 exactly, and v1/r2 hashes are unchanged.
2. Closures: return 2015-03-09 uses obs 03-03 (0.02), 2016-01-28 uses 01-20 (0.26), 2019-02-22 uses 02-15 (2.38).
3. Good Friday: return 2021-04-06 uses obs 04-01 (0.02), not 03-31 (0.03).
4. No-release days stay excluded: obs 2023-11-09 is not available on 2023-11-10.
5. Omissions: obs 2018-09-17, 2020-08-19, 2023-08-01 and 2023-09-12 are not used before their documented dates.
6. For every observation from 2006-02-03, `available_at` is on or after both first vintage and calendar date.
7. Sparse era: from 2005-01-04 there are no missing RF rows and no staleness jump caused by the 2005-06-28 vintage.
8. Withdrawn 2011-04-22 is not used.
9. Future-perturbation invariance holds, and 13:00 early-close cutoffs change nothing.
10. Evidence file hash is in the manifest, and the r2 and r3 caches cannot be confused.
11. Pull guard: fail if a response has fewer vintage columns than requested, which protects against the silent 12-series cap.

## What cannot be verified

| Gap | What would resolve it |
|---|---|
| Actual release time of any historical H.15, and Tuesday-Friday hours before 2016-10 | Fed web logs or a written Board reply. Not needed for safety. |
| 2006 to about 2012: whether `d+2` vintages reflect FRED ingestion or real Fed timing | Dated daily-update archive, or capture timestamps (blocked in this run). |
| True first values before 2005-06-28 | Archived H.15 pages, value by value. |
| Unannounced misses outside the samples, and all first vintages | The 430-GET pull. |
| December 2025 conflict | Board or Treasury confirmation. |
| FRED API limits for `output_type=4` | A registered key. Terms were not reviewed. |
| Independent human validation | Team review. Still pending. |

## Method notes and failures

- Direct requests to FRED and ALFRED web hosts using a generic browser user-agent failed with resets or timeouts. Plain Python `requests` with its default user-agent worked. The cause was not established.
- One script of mine tried Chrome impersonation against those hosts. The permission system blocked it before it ran, and I did not retry it or use any equivalent. All data here comes from ordinary requests or the standard fetch tool.
- My first ALFRED pull assumed 60 vintages per request. The server returned 12, so the first lag results were wrong and I discarded them. The remaining data is treated as a sample.
- My first unreleased-session count was 30 because of a tie-sorting bug. The fixed count of 25 reproduces both the stored and corrected series exactly.

## Sources and evidence

Primary sources:
- [ALFRED DTB3](https://alfred.stlouisfed.org/series?seid=DTB3)
- [ALFRED help](https://alfred.stlouisfed.org/help)
- [ALFRED H.15 release dates](https://alfred.stlouisfed.org/release/downloaddates?rid=18)
- [FRED series_vintagedates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)
- [FRED series_observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- [FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
- [FRED API keys](https://fred.stlouisfed.org/docs/api/api_key.html)
- [H.15 current release](https://www.federalreserve.gov/releases/h15/)
- [H.15 notices feed](https://www.federalreserve.gov/feeds/h15.html)
- [H.15 2017 corrections](https://www.federalreserve.gov/releases/h15/historical-data-correction.htm)
- [Treasury interest rate statistics](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics)

Local evidence:
- `evidence/vintage_analysis_results.json`
- `evidence/conversion_results.json`
- `evidence/final_checks.json`
- `evidence/dtb3_first_appearance_sample.csv`
- `evidence/dtb3_vintage_dates_alfred.csv`
- `evidence/alfred_release_dates_rid18.txt`
- `evidence/fed_2017_3m_bill_corrections.csv`
- `evidence/alfred_vintage_csv/`
- `scripts/`, which reproduces the vintage pulls and analysis
