# Quant Edge 1.0 — Data Snapshot & Quality Report (`qe1_20050101_20261030_r3_6c4633a7ba`)

## 1. Snapshot Provenance & Bounds
- **Dataset ID:** `qe1_20050101_20261030_r3_6c4633a7ba`
- **Policy revision:** `r3_release_evidence`
- **Parent dataset ID:** `qe1_20050101_20261030_r2_cd2904443b`
- **Contract schema version:** `1.1.0`
- **Retrieved / derived at (UTC):** `2026-10-31T09:23:12Z`
- **Canonical tickers:** `SPY, EFA, EEM, AGG, GLD, XLE, XLK`
- **Requested start / end:** `2005-01-01` to `2026-10-30`
- **First / last expected NYSE sessions:** `2005-01-03` to `2026-10-30`
- **Actual price session bounds:** `2005-01-03` to `2026-10-30` (`5492` trading sessions on grid)
- **Complete 1-session return bounds:** `2005-01-04` to `2026-10-30` (`5491` sessions)
- **Price adjustment policy:** `auto_adjust_true_close` (`yfinance` `auto_adjust=True`, where `Close` is the split- and dividend-adjusted close series)
- **Session calendar check:** Expected NYSE sessions in requested window [2005-01-01, 2026-10-30]: 5492 ([2005-01-03, 2026-10-30]); leading missing: 0, trailing missing: 0, interior missing: 0; quarantined unexpected non-NYSE dates: 0.

## 2. Boundary Coverage, Quarantine & Missing-Data Accounting vs. Retained Quality Flags
- **Total grid sessions (`prices`):** `5492`
- **Boundary coverage required:** `True` (leading missing expected sessions: `0`, trailing missing expected sessions: `0`, interior missing expected sessions: `0`)
- **Expected NYSE sessions missing across all tickers:** `0`
- **Unexpected non-NYSE observed sessions (`policy=quarantine`):** `0` (quarantined in `quarantined_unexpected_prices.parquet`, excluded from `prices` and returns)
- **Missing price cells `(date, ticker)`:** `0` (by ticker: `{'SPY': 0, 'EFA': 0, 'EEM': 0, 'AGG': 0, 'GLD': 0, 'XLE': 0, 'XLK': 0}`)
- **Initial price anchor row (`2005-01-03`):** `1` session (base price for first 1-day return; never filled with an artificial `0.0` return)
- **Post-anchor return rows excluded due to missing endpoints:** `0`
- **Uninterrupted 1-session return series:** `True`
- **Aligned forward-decision `DTB3` missing rows on return dates:** `0`

> **Hygiene rule:** Missing ETF prices are never forward-filled. Unexpected non-NYSE dates (such as vendor weekend rows) are quarantined for audit and excluded from the `prices` modelling grid. Returns are computed on the uncollapsed NYSE session grid first (`P_t / P_{t-1} - 1`), so any missing price invalidates both adjacent 1-session intervals rather than bridging a multi-day move as a 1-day return. Conversely, outlier and structural-break flags below **retain** all valid observations (`action='retain'`).

### Quality Flag Counts by Rule
| rule | action | count | unique_tickers |
| --- | --- | --- | --- |
| candidate_structural_break | retain | 18 | 6 |
| large_negative_return | retain | 188 | 7 |
| robust_mad_jump | retain | 101 | 7 |

### Quality Flag Counts by Ticker
| ticker | candidate_structural_break | large_negative_return | robust_mad_jump |
| --- | --- | --- | --- |
| AGG | 2 | 1 | 13 |
| EEM | 3 | 51 | 15 |
| EFA | 2 | 31 | 18 |
| GLD | 0 | 13 | 6 |
| SPY | 5 | 18 | 23 |
| XLE | 3 | 51 | 16 |
| XLK | 3 | 23 | 10 |

## 3. Simple vs. Log Return Convention, Synchronous US Close Note & Risk-Free Proxies
- **Simple returns (`simple_returns`):** Used for cross-sectional portfolio aggregation (`R_{p,t} = sum_i w_{i,t-} R_{i,t}`) and committee simple-loss risk (`L_t = -R_{p,t}`), because dollar NAV P&L aggregates linearly across holdings at horizon `t` whereas `sum_i w_i log(1 + R_{i,t}) != log(1 + R_{p,t})` (Jensen's inequality).
- **Log returns (`log_returns = log1p(simple_returns)`):** Additive across time (`log(P_T / P_0) = sum_t r_t`), used for time-series statistical diagnostics (ADF stationarity tests, correlation tables, and volatility-regime screening).
- **US exchange close vs. foreign underlying hours (`EFA`, `EEM`):** All seven ETFs trade synchronously on US exchanges through the `16:00 America/New_York` close, so portfolio execution and NAV valuation share a synchronous US close; however, `EFA` and `EEM` hold foreign equities whose local cash markets close earlier, meaning their `16:00 ET` ETF closes embed US afternoon price discovery / fair-value adjustments relative to local foreign closes.
- **Forward-decision risk-free proxy (`rf_daily.parquet`, policy `r3_versioned_release_evidence_day_level`):** `DTB3` quoted in `annual_percent_discount_basis`, converted via `(rate_pct / 100.0) / 252` (`no_backfill = True`). Decision cutoff for return session t is the preceding NYSE session close at 16:00:00 America/New_York. Each DTB3 observation version is usable from 16:15:00 America/New_York on its availability date. From the daily-vintage era that date is the latest of the evidence calendar, the ALFRED vintage date, and any documented omission date; sparse early history keeps the schedule calendar as a labelled fallback. At each cutoff the most recent eligible observation is selected, using its latest eligible version, with zero backfill.
- **Contemporaneous ex-post risk-free proxy (`rf_daily_ex_post.parquet`):** Matches `obs_date <= t` strictly for ex-post reference (never for forward decisions); differs from `rf_daily` on `4393` of `5491` return sessions.
- **Publication & vintage limitation:** DTB3 is quoted in annual percent on a 360-day bank-discount basis; (rate_pct / 100.0) / 252 is an approximate trading-day risk-free proxy, not an exact realized T-bill holding-period return. Availability is day-level evidence, not a verified intraday first-release time: ALFRED vintage dates can trail or precede the source release. Sparse history before the daily-vintage era is a labelled calendar fallback, and cases marked inferred or unresolved in rf_provenance.parquet are not proven. This is not exact historical point-in-time data.
- **Evidence coverage of selected RF values (`rf_provenance.parquet`):** `{'selected_sessions_by_tier': {'vintage_supported': 3693, 'inferred': 1509, 'calendar_fallback': 288, 'documented': 1}, 'selected_sessions_by_status': {'resolved_day_level': 5203, 'sparse_fallback': 288}, 'versions_by_tier': {'vintage_supported': 3621, 'inferred': 1537, 'calendar_fallback': 314, 'documented': 23, 'unresolved': 2}, 'versions_by_kind': {'initial': 5493, 'revision': 3, 'withdrawal': 1}}`
- **Conversion sensitivity (`rf_daily_accrual_91d_sensitivity.parquet`):** 91-day bill accrual on the same selected quotes, (1/P)^(calendar_days/91)-1 with P=1-d*91/360. A labelled conversion sensitivity under a fixed-term assumption, not the primary RF and not an exact realized Treasury return.

## 4. Augmented Dickey-Fuller (ADF) Stationarity Diagnostics on Log Returns
> **Interpretation caveat:** Rejecting the unit-root null (`p < 0.05`) supports level/mean stationarity (`I(0)`) of daily log returns; it does **not** imply i.i.d. returns, Gaussian tails, or constant conditional variance (volatility clustering remains prominent).

| series | n_obs | adf_stat | p_value | used_lag | crit_5pct | reject_unit_root_5pct | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | 5471 | -16.6643 | 1.56456e-29 | 19 | -2.86207 | True | ok |
| EFA | 5471 | -16.1897 | 4.18273e-29 | 19 | -2.86207 | True | ok |
| EEM | 5471 | -16.1959 | 4.12475e-29 | 19 | -2.86207 | True | ok |
| AGG | 5469 | -15.7907 | 1.10314e-28 | 21 | -2.86207 | True | ok |
| GLD | 5490 | -75.1136 | 0 | 0 | -2.86207 | True | ok |
| XLE | 5462 | -14.4229 | 7.85729e-27 | 28 | -2.86207 | True | ok |
| XLK | 5475 | -18.4195 | 2.17746e-30 | 15 | -2.86207 | True | ok |

## 5. Descriptive Statistics — Simple Returns (Fractions)
| ticker | n_obs | ann_arithmetic_return | ann_geometric_return | ann_volatility | skewness | excess_kurtosis | min | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | 5491 | 0.120318 | 0.107943 | 0.188585 | -0.001220 | 15.456299 | -0.109424 | 0.145198 |
| EFA | 5491 | 0.081064 | 0.060911 | 0.209292 | -0.038978 | 14.267226 | -0.111632 | 0.158876 |
| EEM | 5491 | 0.103987 | 0.068233 | 0.276059 | 0.496907 | 17.731220 | -0.161662 | 0.227699 |
| AGG | 5491 | 0.030527 | 0.029596 | 0.052024 | -1.836302 | 50.512767 | -0.068395 | 0.038688 |
| GLD | 5491 | 0.113756 | 0.101812 | 0.182986 | -0.309590 | 6.389333 | -0.102742 | 0.112905 |
| XLE | 5491 | 0.136209 | 0.096276 | 0.296714 | -0.315928 | 11.622609 | -0.201412 | 0.164746 |
| XLK | 5491 | 0.168434 | 0.153453 | 0.226461 | 0.078087 | 9.699540 | -0.138140 | 0.138983 |

## 6. Descriptive Statistics — Log Returns (Fractions)
| ticker | n_obs | daily_mean | daily_std | ann_volatility | skewness | excess_kurtosis | min | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | 5491 | 0.000407 | 0.011888 | 0.188714 | -0.303617 | 14.789233 | -0.115886 | 0.135577 |
| EFA | 5491 | 0.000235 | 0.013201 | 0.209556 | -0.351530 | 13.666393 | -0.118369 | 0.147451 |
| EEM | 5491 | 0.000262 | 0.017354 | 0.275486 | 0.023184 | 15.507474 | -0.176334 | 0.205142 |
| AGG | 5491 | 0.000116 | 0.003288 | 0.052189 | -2.089215 | 55.331249 | -0.070847 | 0.037958 |
| GLD | 5491 | 0.000385 | 0.011549 | 0.183331 | -0.453438 | 6.550141 | -0.108412 | 0.106974 |
| XLE | 5491 | 0.000365 | 0.018781 | 0.298133 | -0.709154 | 12.930863 | -0.224910 | 0.152503 |
| XLK | 5491 | 0.000567 | 0.014264 | 0.226442 | -0.166952 | 9.381600 | -0.148662 | 0.130136 |

## 7. Full-Sample Log-Return Correlation Matrix
| ticker | SPY | EFA | EEM | AGG | GLD | XLE | XLK |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | 1.0000 | 0.8810 | 0.8176 | 0.0014 | 0.0695 | 0.7048 | 0.9064 |
| EFA | 0.8810 | 1.0000 | 0.8684 | 0.0395 | 0.1800 | 0.6873 | 0.7666 |
| EEM | 0.8176 | 0.8684 | 1.0000 | -0.0100 | 0.1973 | 0.6539 | 0.7433 |
| AGG | 0.0014 | 0.0395 | -0.0100 | 1.0000 | 0.2072 | -0.0525 | -0.0042 |
| GLD | 0.0695 | 0.1800 | 0.1973 | 0.2072 | 1.0000 | 0.1456 | 0.0666 |
| XLE | 0.7048 | 0.6873 | 0.6539 | -0.0525 | 0.1456 | 1.0000 | 0.5365 |
| XLK | 0.9064 | 0.7666 | 0.7433 | -0.0042 | 0.0666 | 0.5365 | 1.0000 |
