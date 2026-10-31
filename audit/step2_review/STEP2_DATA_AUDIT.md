# Step 2 data audit - before portfolio construction

**Verdict: the stored ETF price/return snapshot is a suitable foundation for this project's next analytical stages. Its integrity, return arithmetic, required universe and historical crisis coverage passed this audit. The risk-free alignment must be corrected or explicitly restricted to an ex-post approximation before claiming publication-aware, no-look-ahead investment decisions. Three data-loader guards also need tightening. This is a conditional pass, not a claim that every provider quote is error-free.**

Audit date: 2026-10-31. Dataset: `qe1_20050101_20261030_afb9ce5694`. Reviewed actual local parquet files, manifest, configuration, acquisition/return code, existing tests and fresh samples from the approved public sources. Source data, configuration and implementation code were not changed. Only separate audit evidence was written under `audit/step2_review/` and temporary source-check output under `tmp/source_audit/`.

## Verified results

| Check | Result |
|---|---|
| Seven prescribed ETFs in canonical order | SPY, EFA, EEM, AGG, GLD, XLE, XLK |
| Price history | 5,492 sessions x 7 ETFs, 2005-01-03 through 2026-10-30 |
| Complete simple/log returns | 5,491 sessions x 7 ETFs, 2005-01-04 through 2026-10-30 |
| Price validity | All 38,444 stored prices finite and positive; zero missing cells |
| Date/return validity | Unique ascending dates; zero missing/nonfinite returns; no return <= -100% |
| Raw adjusted-close file versus processed prices | Exact equality |
| Manifest file integrity | All 13 SHA-256 checks match |
| Independently recomputed simple returns | Maximum absolute error 0 |
| Independently recomputed log returns / log1p(simple) | Maximum absolute error 0 |
| Stored RF file index, checked before the loader can change it | Exactly matches the return index in this snapshot |
| RF arithmetic under the current stated BDay-lag rule | Independent recomputation matches; this validates the implemented rule, not publication-time correctness |
| Exported descriptive statistics/correlations | Match independent recomputation to floating-point rounding, approximately 1e-15 |
| Crisis coverage across all seven ETFs | GFC 356 return rows; COVID 24; 2022 rate-shock 198, under the configured exact windows |
| Quality flags | 307 retained rule hits: 188 large negatives, 101 robust-MAD jumps, 18 candidate breaks |
| Existing test suite, independently rerun | 17 passed in 2.75s |
| Dependency consistency | `pip check`: no broken requirements |

The 307 flags are rule hits, not proof of 307 corrupt prices. Some observations can trigger more than one rule. They must not be deleted just to make results look smoother. Extreme crises are exactly the observations a tail-risk study needs to investigate and retain when valid.

Fresh source checks used `auto_adjust=False` and the returned `Adj Close`, avoiding the project's own adjusted-close extraction helper:

| Fresh-source sample | Compared | Maximum relative price difference |
|---|---:|---:|
| Seven ETFs, 2020-03-06 through 2020-03-18 | 63 values | 4.98e-7 |
| Seven ETFs, 2026-10-19 through 2026-10-30 | 70 values | 0 |
| AGG around its 2008-10-10 extreme | 3 values | 8.75e-7 |
| GLD around its 2026-01-30 extreme | 3 values | 0 |
| FRED DTB3, recent finite common dates | 9 rates | Exact equality in annual-percent units |

All 139 fresh Yahoo price cells were obtained and compared; the largest relative price difference was about 0.00008755%, well below 1 basis point. These checks support consistency with the current approved provider and the adjustment mapping. They do not establish independent-vendor accuracy for the entire history. Five latest DTB3 observations also matched the Federal Reserve's H.15 table directly; see `h15_manual_spotcheck.json`.

Initial source requests inside the restricted network failed DNS; the bounded public-source check subsequently succeeded with network access. An initial pytest attempt encountered an unwritable sandbox temporary directory (15 passed, two fixture setup errors). Repeating the same suite with a fresh workspace-only `--basetemp` produced the 17-pass result; no source patch was needed for that environment issue.

## Finding 1 - RF observation dates are not publication timestamps

Priority: **P2, material before forward use of RF or a strict point-in-time claim.** Location: `src/quantedge/returns.py:350`, with date-only matching at line 362.

The implementation declares observation date plus one ordinary business day to be `available_date`. That is a chosen date lag; it does not prove that the value had actually been published by the configured forecast origin, the preceding equity close.

Concrete stored example: `rf_daily[2026-10-30] * 100 * 252 = 4.00`, selected from the DTB3 observation dated 2026-10-29. The Federal Reserve states that H.15 is posted at 4:15 pm; FRED currently shows that observation last updated on 2026-10-30 at 3:16 pm CDT, or 4:16 pm New York time. A last-update time is not a reconstructed first-publication vintage, so we must not pretend we have validated the entire historical release calendar. It does establish that the present date-only alignment lacks the timestamp/vintage evidence needed for its availability claim. A value published after the decision close cannot be used at that close simply because its observation date is earlier.

Sources: [Federal Reserve H.15 release and schedule](https://www.federalreserve.gov/releases/h15/), [FRED DTB3 metadata and update time](https://fred.stlouisfed.org/series/DTB3).

Required resolution: distinguish the approximate ex-post RF proxy from an as-of-decision series. For any forward use, require `available_at <= decision_time`, using actual release information or an explicitly conservative, documented lag/calendar assumption, and disclose remaining vintage limitations. Do not merely rename BDay(1) as publication-aware. Test a release after 16:00 New York time, holidays and the forecast-origin cutoff. Do not choose an arbitrary new lag without checking the timestamps.

Scope: this finding does not invalidate the seven ETF prices or their computed returns. Price-only minimum-variance construction does not need RF; forward CAPM/return-target/Sharpe-driven decisions cannot inherit a strict no-look-ahead claim from the existing alignment. The existing series can be preserved as a clearly labelled ex-post proxy.

## Finding 2 - download-boundary truncation is not detected

Priority: **P2 robustness issue; not missing history in the current snapshot.** Locations: `src/quantedge/data.py:146` and `src/quantedge/data.py:216`.

Leading/trailing all-NaN rows are removed, and the expected session grid is then bounded by the first/last observed dates. An incomplete download can therefore redefine the audit interval and still report zero missing sessions. Reproduction: input consisting only of October 2026 reports zero missing expected sessions even though the configured requested history begins in 2005. Even an explicitly supplied calendar is clipped back to the observed endpoints at line 224.

Fix: validate against the requested first and last expected completed exchange sessions. Count/report boundary shortfalls separately; fail or flag required-history truncation. Do not require a quote on a requested weekend/holiday. Keep the current frozen snapshot unchanged because its actual endpoints were verified.

## Finding 3 - unexpected dates remain in one-day return calculations

Priority: **P2 robustness issue; no such dates exist in the current snapshot.** Location: `src/quantedge/data.py:229`.

The return grid unions expected exchange sessions with unexpected observed dates. A synthetic Friday/Saturday/Monday input retains Saturday and creates returns dated Saturday and Monday, despite reporting Saturday as unexpected. Flagging an invalid session does not make the resulting intervals valid one-session returns.

Fix: retain unexpected source rows in a separate audit record, but block/review them or exclude them explicitly from the expected-session modelling grid. Never silently treat them as valid trading sessions. Add a regression test preserving the raw unexpected observation and documenting the action taken.

## Finding 4 - cache loader can conceal RF index misalignment

Priority: **P2 validation gap; current serialized RF dates were independently checked and are correct.** Location: `src/quantedge/data.py:988`.

The cache loader overwrites the saved RF index with `simple_returns.index`. That can make a wrongly dated serialized series appear aligned. Hashes confirm file consistency with a manifest, not correct logical date association.

Fix: validate stored RF/return index equality and reject a mismatch; do not repair it by positional reassignment. Test a same-length RF table with shifted dates and a corresponding updated synthetic manifest, so the logical check is exercised instead of just checksum rejection.

## Project suitability and remaining limits

- The prescribed universe and 2005-start history support the required GFC/COVID/rate-shock replays and later rolling estimation. Tail-model fit quality, chosen portfolio stationarity and forecast performance still need their own tests once those models exist.
- Stationarity test rejection is evidence against a unit root, not proof of Gaussian, iid or constant-volatility data. Per-asset diagnostics do not replace the later actual-portfolio check.
- The custom expected-session calendar matched this snapshot and the tested special closures. No separate exchange-calendar package comparison was performed; neither `exchange_calendars` nor `pandas_market_calendars` is installed.
- The ETF raw file preserves adjusted closes, not the full unadjusted OHLC/dividend/split payload. Fresh sampled Adj Close responses give additional adjustment evidence, not exhaustive historical corporate-action verification.
- EFA/EEM are US-traded ETFs with foreign underlying markets; a common US listing calendar does not remove underlying-market non-synchronous pricing effects. Document that limitation for daily correlations and risk modelling.
- DTB3's `(annual_percent / 100) / 252` conversion is an approximate discount-basis RF proxy, not a directly investable cash asset or exact realized daily T-bill return. [FRED series definition](https://fred.stlouisfed.org/series/DTB3).
- This audit was AI-assisted code/data review plus automated checks. Independent human validation remains pending. No final portfolio recommendation or competition-readiness claim is made.

## Suggested next action

Use `ANTIGRAVITY_FIX_PROMPT.txt` for a bounded Step 2 hardening pass before resuming the solo plan. Preserve the existing raw snapshot. If an alignment policy changes, create a separately versioned derived snapshot/manifest rather than overwriting the audited artifacts. Include transformation/policy identity in the revision and verify that cache selection cannot silently return the old policy.

Evidence files: `snapshot_facts.json`, `source_spotcheck_result.json`, `h15_manual_spotcheck.json`, `guard_reproductions.json`, `pytest_verified_output.txt`, and the sampled source parquet/CSV files in this audit directory. `source_spotcheck.py` reproduces the bounded public-source check. The original implementation and data remain untouched.
