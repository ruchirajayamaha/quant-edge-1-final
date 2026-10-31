"""Analyse pulled ALFRED DTB3 vintages against the stored r2 RF series (read-only research).

Uses the project's unchanged ``align_risk_free_rate`` with its existing ``release_timestamps`` and
``decision_timestamps`` arguments. Writes results to audit/rf_research/evidence only.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / "src"))
from quantedge.returns import (  # noqa: E402
    _easter_sunday,
    align_risk_free_rate,
    expected_federal_reserve_business_days,
    expected_nyse_sessions,
)

SNAP = "qe1_20050101_20261030_r2_cd2904443b"
raw_tbl = pd.read_parquet(REPO / f"data/raw/{SNAP}/fred_dtb3_raw.parquet")
raw = raw_tbl["rate_annual_pct"]
stored = pd.read_parquet(REPO / f"data/processed/{SNAP}/rf_daily.parquet").iloc[:, 0]
ex_post = pd.read_parquet(REPO / f"data/processed/{SNAP}/rf_daily_ex_post.parquet").iloc[:, 0]
ret_idx = stored.index
prices_idx = pd.read_parquet(REPO / f"data/processed/{SNAP}/prices.parquet").index
res: dict = {}


def load(p):
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    df.columns = [pd.Timestamp(c.split("_")[1]) for c in df.columns]
    return df.apply(pd.to_numeric, errors="coerce")


# 1. First appearance. ALFRED returns at most 12 series per request, so each file holds one run of
# consecutive vintages. First appearance is only known when an observation is absent from the run's
# first vintage and present in a later one.
snap = load(EV / "alfred_vintage_csv" / "full_history_snapshots.csv")
rows = []
all_cols = set()
for p in sorted((EV / "alfred_vintage_csv").glob("*_*.csv")):
    if p.name.startswith("full_history"):
        continue
    df = load(p).sort_index(axis=1)
    all_cols |= set(df.columns)
    for o, r in df.iterrows():
        nz = r.dropna()
        if nz.empty or pd.notna(r.iloc[0]):
            continue
        rows.append({"obs": o, "first_vintage": nz.index[0], "first_value": nz.iloc[0], "run": p.stem})
fa = pd.DataFrame(rows).sort_values(["obs", "first_vintage"]).drop_duplicates("obs").set_index("obs")
vvals = pd.concat([load(p).stack().rename("v") for p in (EV / "alfred_vintage_csv").glob("*_*.csv")]).reset_index()
vvals.columns = ["obs", "vintage", "value"]
vvals = vvals.drop_duplicates(["obs", "vintage"])
g = vvals.groupby("obs")["value"]
first = fa.join(g.nunique().rename("n_distinct"), how="left").join(g.last().rename("last_value"), how="left")
res["coverage"] = {"vintages_retrieved": len(all_cols) + len(snap.columns), "vintages_published": 5142, "requests_chunk": 86, "requests_closure": 29,
                   "max_series_per_request_observed": 12, "observations_with_exact_first_vintage": len(first),
                   "first": str(first.index.min().date()), "last": str(first.index.max().date())}

# 2. Publication lag of first appearance in weekdays, by documentation era
win = first.copy()
win["lag_bd"] = np.busday_count(win.index.values.astype("datetime64[D]"), win.first_vintage.values.astype("datetime64[D]"))
eras = {"2005-06..2006-02 sparse": ("2005-06-29", "2006-02-02"), "2006-02..2010": ("2006-02-03", "2010-12-31"),
        "2011..2014-03": ("2011-01-01", "2014-03-31"), "2014-04..2016-10-10 weekly+daily": ("2014-04-01", "2016-10-10"),
        "2016-10-11.. daily 16:15": ("2016-10-11", "2026-10-30")}
res["first_appearance_lag_weekdays"] = {
    k: {str(int(a)): int(b) for a, b in win.loc[s:e, "lag_bd"].value_counts().sort_index().items()} for k, (s, e) in eras.items()}

# 3. Revisions: within-vintage history, and against the snapshot
rev = first[first.n_distinct > 1]
cmp_ = first.join(raw.rename("snapshot"), how="inner").dropna(subset=["snapshot"])
res["revisions"] = {
    "obs_with_more_than_one_value_seen": len(rev),
    "rows": [{"obs": str(i.date()), "first_vintage": str(r.first_vintage.date()), "first": r.first_value, "last": r.last_value} for i, r in rev.iterrows()][:40],
    "obs_compared_to_snapshot": len(cmp_),
    "first_value_ne_snapshot": int((cmp_.first_value - cmp_.snapshot).abs().gt(1e-9).sum()),
    "last_value_ne_snapshot": int((cmp_.last_value - cmp_.snapshot).abs().gt(1e-9).sum()),
}
res["snapshot_columns_vs_current"] = {
    str(c.date()): {"n": int(snap[c].notna().sum()),
                    "n_ne_current": int((snap[c].reindex(raw.index) - raw).abs().gt(1e-9).sum())} for c in snap.columns}

# 4. Publication calendars. Announced/observed closures come from Fed notices and the ALFRED list.
ann = pd.DatetimeIndex(["2008-12-26", "2009-01-20", "2009-12-24", "2010-02-08", "2010-02-09", "2012-10-29", "2012-10-30",
                        "2013-03-06", "2013-12-10", "2014-01-21", "2014-02-13", "2014-03-03", "2014-03-17", "2014-12-26",
                        "2015-02-17", "2015-03-05", "2016-01-22", "2016-01-25", "2016-01-26", "2019-01-14", "2019-02-20"])
alfred_only = pd.DatetimeIndex(["2017-01-20", "2018-03-02", "2018-12-24", "2020-12-24", "2021-01-20", "2024-12-24"])
closures = ann.union(alfred_only)
gf = pd.DatetimeIndex([pd.Timestamp(_easter_sunday(y)) - pd.Timedelta(days=2) for y in range(2004, 2027)])
sched = expected_federal_reserve_business_days("2004-11-01", "2026-12-31")
res["closures_in_schedule_calendar"] = {str(d.date()): bool(d in sched) for d in closures}
corrected = sched.difference(closures).union(gf).sort_values()
nan_dates = pd.DatetimeIndex(raw.index[raw.isna()])
sched_nonan = sched.difference(nan_dates)   # as the implementation does


def next_pub(obs, cal):
    return cal[np.searchsorted(cal.values, obs.values, side="right")]


vals = raw.dropna()
obs = vals.index
s_code, s_corr = next_pub(obs, sched_nonan), next_pub(obs, corrected)
t = pd.DataFrame({"code": s_code, "corr": s_corr}, index=obs).join(first[["first_vintage"]])
t["code_minus_vint"] = (t.code - t.first_vintage).dt.days
t = t.dropna(subset=["first_vintage"])
t = t[t.first_vintage > pd.Timestamp("2006-02-02")]
res["schedule_vs_first_vintage"] = {
    k: {"n": int(len(t.loc[s:e])), "schedule_before_vintage": int((t.loc[s:e, "code"] < t.loc[s:e, "first_vintage"]).sum()),
        "same_date": int((t.loc[s:e, "code"] == t.loc[s:e, "first_vintage"]).sum()),
        "schedule_after_vintage": int((t.loc[s:e, "code"] > t.loc[s:e, "first_vintage"]).sum())}
    for k, (s, e) in list(eras.items())[1:]}
late = t[t.code > t.first_vintage]
res["schedule_after_vintage_examples"] = [{"obs": str(i.date()), "sched": str(r.code.date()), "vintage": str(r.first_vintage.date())} for i, r in late.tail(25).iterrows()]

# 5. Recompute stored series, then alternatives through the existing interface
NY = "America/New_York"
kw = dict(price_sessions=prices_idx, mode="forward_decision")
base = align_risk_free_rate(raw, ret_idx, **kw)
res["stored_recomputed_exact"] = bool(np.array_equal(base.to_numpy(), stored.to_numpy()))


def ts(day, hhmm):
    return (pd.Timestamp(day) + pd.Timedelta(hours=hhmm[0], minutes=hhmm[1])).tz_localize(NY)


corr_map = {o: ts(p, (16, 15)) for o, p in zip(obs, s_corr)}
rf_corr = align_risk_free_rate(raw, ret_idx, release_timestamps=corr_map, **kw)

# Sensitivity bound for any vintage-date rule: every observation delayed one further publication day.
pos = np.searchsorted(corrected.values, obs.values, side="right") + 1
plus1 = {o: ts(corrected[p], (16, 15)) for o, p in zip(obs, pos)}
rf_plus1 = align_risk_free_rate(raw, ret_idx, release_timestamps=plus1, **kw)
as_first = raw.copy()
ix = first.index.intersection(raw.dropna().index)
as_first.loc[ix] = first.first_value.reindex(ix)


def compare(a, b=stored, since="2006-02-03"):
    x, y = a.loc[since:] * 25200, b.loc[since:] * 25200
    d = x - y
    n = d.abs().gt(1e-9)
    return {"sessions": int(len(d)), "differ": int(n.sum()), "max_abs_quote_pp": round(float(d.abs().max()), 4),
            "worst_date": str(d.abs().idxmax().date()), "mean_quote_diff_bp": round(float(d.mean() * 100), 4),
            "annual_sum_diff_bp": round(float((a.loc[since:].sum() - b.loc[since:].sum()) * 1e4 / (len(d) / 252)), 4)}


res["alt_vs_stored"] = {"closure_corrected": compare(rf_corr, since="2005-01-04"), "one_more_publication_day": compare(rf_plus1, since="2005-01-04"),
                        "ex_post": compare(ex_post, since="2005-01-04")}

# 6. Look-ahead exposure of the stored series: uses an observation not yet released under the corrected calendar
pos_code = pd.Series(np.nan, index=ret_idx, dtype=float)
close_prev = pd.Series(prices_idx[:-1], index=prices_idx[1:]).reindex(ret_idx)
dec = pd.DatetimeIndex(close_prev + pd.Timedelta(hours=16)).tz_localize(NY)
av_code = pd.Series([ts(p, (16, 15)) for p in s_code], index=obs)
av_corr = pd.Series([corr_map[o] for o in obs], index=obs)


def chosen(av):
    # Ties on available time resolve to the newest observation, matching align_risk_free_rate.
    a = pd.DataFrame({"av": av, "o": av.index}).sort_values(["av", "o"], kind="mergesort")
    p = np.searchsorted(a["av"].values, dec.tz_convert("UTC").values, side="right") - 1
    return pd.Series(a["o"].to_numpy()[p], index=ret_idx)


ch_code, ch_corr = chosen(av_code.dt.tz_convert("UTC")), chosen(av_corr.dt.tz_convert("UTC"))
early = ch_code[ch_code > ch_corr]
safe_late = ch_code[ch_code < ch_corr]
rows = []
for dt in early.index:
    q1, q2 = raw[ch_code[dt]], raw[ch_corr[dt]]
    rows.append({"return_date": str(dt.date()), "stored_obs": str(ch_code[dt].date()), "stored_quote": q1,
                 "corrected_obs": str(ch_corr[dt].date()), "corrected_quote": q2, "quote_diff_pp": round(q1 - q2, 2)})
res["stored_uses_unreleased_obs"] = {"sessions": len(early), "changes_value": sum(1 for r in rows if abs(r["quote_diff_pp"]) > 1e-9),
                                     "max_abs_quote_pp": max((abs(r["quote_diff_pp"]) for r in rows), default=0.0), "rows": rows}
res["stored_over_delayed_vs_corrected"] = {"sessions": len(safe_late)}
check = pd.Series(raw.reindex(ch_corr.values).to_numpy() / 25200.0, index=ret_idx)
res["chosen_table_reproduces_series"] = {"stored": bool(np.allclose(raw.reindex(ch_code.values).to_numpy() / 25200.0, base.to_numpy(), rtol=0, atol=1e-15)),
                                         "corrected": bool(np.allclose(check.to_numpy(), rf_corr.to_numpy(), rtol=0, atol=1e-15))}
ch = t[t["corr"] < t.first_vintage].loc["2016-10-11":]
res["post2016_corrected_schedule_before_vintage"] = [f"{i.date()} sched {r['corr'].date()} vint {r.first_vintage.date()}" for i, r in ch.iterrows()]
big = win[win.lag_bd >= 3].loc["2011-01-01":]
res["lag_ge3_since_2011"] = [f"{i.date()}->{r.first_vintage.date()} ({int(r.lag_bd)})" for i, r in big.iterrows()]
same = win[win.lag_bd == 0]
res["lag_zero_rows"] = [f"{i.date()}->{r.first_vintage.date()} run {r.run}" for i, r in same.iterrows()]

# 7. Early closes and DST: real 13:00 cutoffs through decision_timestamps
nyse = expected_nyse_sessions("2004-11-01", "2026-10-30")
early_days = []
for y in range(2005, 2027):
    from quantedge.returns import _nth_weekday_of_month
    tg = pd.Timestamp(_nth_weekday_of_month(y, 11, 3, 4)) + pd.Timedelta(days=1)
    early_days.append(tg)
    for mmdd in (f"{y}-07-03", f"{y}-12-24"):
        early_days.append(pd.Timestamp(mmdd))
early_days = [d for d in early_days if d in nyse]
dec2 = [ts(p, (13, 0)) if p in early_days else ts(p, (16, 0)) for p in close_prev]
rf_early = align_risk_free_rate(raw, ret_idx, decision_timestamps=pd.DatetimeIndex(dec2), mode="forward_decision", price_sessions=prices_idx)
res["early_close_cutoff_test"] = {"candidate_short_days_tested": len(early_days), "series_changed_sessions": int((rf_early - stored).abs().gt(1e-15).sum()),
                                  "note": "Candidate list is deliberately broad; 13:00 applied to every 3-Jul, 24-Dec and post-Thanksgiving session."}
hours = pd.Series(dec.tz_convert("UTC").hour).value_counts().to_dict()
res["dst_decision_utc_hours"] = {int(k): int(v) for k, v in hours.items()}
res["dst_gap_minutes_release_minus_cutoff_same_day"] = 15

# 8. Materiality expressed without touching portfolio returns
d_ann = {k: v["annual_sum_diff_bp"] for k, v in res["alt_vs_stored"].items()}
res["sharpe_delta_at_10pct_vol"] = {k: round(v / 1e4 / 0.10, 6) for k, v in d_ann.items()}
first.to_csv(EV / "dtb3_first_appearance_sample.csv")
cl = {}
for c in sorted(p.stem.split("_")[1] for p in (EV / "alfred_vintage_csv").glob("closure_*.csv")):
    d = pd.Timestamp(c)
    w = first.loc[d - pd.Timedelta(days=9):d + pd.Timedelta(days=9)]
    cl[c] = [f"{i.date()}->{r.first_vintage.date()}" for i, r in w.iterrows()]
res["closure_windows_obs_to_first_vintage"] = cl
(EV / "vintage_analysis_results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
print(json.dumps({k: res[k] for k in ("alt_vs_stored", "stored_over_delayed_vs_corrected", "chosen_table_reproduces_series", "post2016_corrected_schedule_before_vintage", "lag_ge3_since_2011", "lag_zero_rows", "sharpe_delta_at_10pct_vol")}, indent=0, default=str))
u = res["stored_uses_unreleased_obs"]
print({k: u[k] for k in ("sessions", "changes_value", "max_abs_quote_pp")})
for r in u["rows"]:
    print(r)
