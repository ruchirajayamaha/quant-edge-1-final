"""Q5 research checks: DTB3 conversion error, source identity and series comparison (read-only)."""
import io, json, pathlib
import numpy as np, pandas as pd, requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"
REPO = ROOT.parents[1]
SNAP = "qe1_20050101_20261030_r2_cd2904443b"
raw = pd.read_parquet(REPO / f"data/raw/{SNAP}/fred_dtb3_raw.parquet")["rate_annual_pct"].dropna()
idx = pd.read_parquet(REPO / f"data/processed/{SNAP}/simple_returns.parquet").index
rf = pd.read_parquet(REPO / f"data/processed/{SNAP}/rf_daily.parquet").iloc[:, 0]
ex = pd.read_parquet(REPO / f"data/processed/{SNAP}/rf_daily_ex_post.parquet").iloc[:, 0]
res = {}

# Rate known at start of each return interval (prior session's quote), carried across gaps.
prev_sessions = pd.Series(pd.DatetimeIndex([pd.Timestamp("2005-01-03")]).append(idx[:-1]), index=idx)
q = raw.reindex(raw.index.union(prev_sessions.values)).ffill().reindex(prev_sessions.values)
q.index = idx
d = q / 100.0
P91 = 1.0 - d * 91.0 / 360.0
days = pd.Series((idx - prev_sessions.values).days, index=idx, dtype=float)
accr = (1.0 / P91) ** (days / 91.0) - 1.0          # actual/actual accrual on a 91-day bill
simple252 = d / 252.0                              # current formula on the same rate
act360 = d * days / 360.0                          # discount rate on actual/360, no price adjustment
bey = 365.0 * d / (360.0 - d * 91.0)               # coupon-equivalent, 91-day, 365-day year

yrs = len(idx) / 252.0
def ann(s): return float(np.expm1(np.log1p(s).sum() / ((idx[-1] - prev_sessions.iloc[0]).days / 365.25)))
res["annualised_compound_2005_2026"] = {
    "stored_forward_div252": ann(rf), "stored_ex_post_div252": ann(ex),
    "start_of_interval_div252": ann(simple252), "act360": ann(act360), "accrual_91d_actual": ann(accr)}
by = pd.DataFrame({"div252": np.log1p(simple252), "accrual": np.log1p(accr)}).groupby(idx.year).sum()
by = np.expm1(by) * 1e4
by["gap_bp"] = by["accrual"] - by["div252"]
res["by_year_bp"] = by.round(2).to_dict("index")
res["gap_bp_summary"] = {"mean": float(by.gap_bp.iloc[:-1].mean()), "max": float(by.gap_bp.iloc[:-1].max()),
                         "max_year": int(by.gap_bp.iloc[:-1].idxmax())}
res["bey_minus_discount_pp"] = {"at_4.00": float(365 * .04 / (360 - .04 * 91) * 100 - 4), "at_5.30": float(365 * .053 / (360 - .053 * 91) * 100 - 5.3)}
ms = pd.DataFrame({"accr": accr, "div252": simple252})
res["single_session_abs_err_bp"] = {"max": float((ms.accr - ms.div252).abs().max() * 1e4),
    "weekday_sat_sun_share_note": "Fri->Mon interval accrues 3 calendar days; /252 accrues one equal step"}
print(ms.assign(wd=idx.dayofweek).groupby("wd").mean().mul(1e4).round(4))

# Mark-to-market one-day return on a constant 91->90 day bill, versus accrual
dq = raw.reindex(raw.index.union(idx)).ffill().reindex(idx) / 100.0
P1 = 1.0 - dq * (91.0 - days) / 360.0
mtm = P1 / P91 - 1.0
res["mtm_vs_accrual"] = {"mtm_daily_std_bp": float(mtm.std() * 1e4), "accrual_daily_std_bp": float(accr.std() * 1e4),
                         "mtm_min_bp": float(mtm.min() * 1e4), "mtm_max_bp": float(mtm.max() * 1e4),
                         "mtm_max_date": str(mtm.idxmax().date()), "mtm_min_date": str(mtm.idxmin().date()),
                         "ann_compound_mtm": ann(mtm.dropna())}

# Primary-source identity checks with Treasury bill rates and FRED DGS3MO
sample = {}
for y in (2008, 2020, 2026):
    u = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_bill_rates&field_tdr_date_value={y}&page&_format=csv"
    r = requests.get(u, timeout=60)
    print(y, r.status_code, r.headers.get("content-type"), len(r.content))
    if r.status_code != 200 or "Date" not in r.text[:40]:
        sample[y] = {"status": r.status_code}
        continue
    (EV / f"treasury_bill_rates_{y}.csv").write_text(r.text, encoding="utf-8")
    t = pd.read_csv(io.StringIO(r.text)); t["Date"] = pd.to_datetime(t["Date"]); t = t.set_index("Date").sort_index()
    bcol = [c for c in t.columns if c.startswith("13 WEEKS BANK")][0]; ccol = [c for c in t.columns if c.startswith("13 WEEKS COUPON")][0]
    j = pd.concat([t[bcol].rename("tsy"), raw.rename("dtb3"), t[ccol].rename("tsy_ce")], axis=1, join="inner")
    fit = 365 * j.dtb3 / 100 / (360 - j.dtb3 / 100 * 91) * 100
    sample[y] = {"n": len(j), "n_equal_discount": int((j.tsy - j.dtb3).abs().lt(0.0051).sum()), "max_abs_disc_diff": float((j.tsy - j.dtb3).abs().max()),
                 "max_abs_ce_formula_err_pp": float((j.tsy_ce - fit).abs().max()), "mean_ce_minus_disc_pp": float((j.tsy_ce - j.tsy).mean())}
res["treasury_vs_dtb3"] = sample
r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO", timeout=60)
print("DGS3MO", r.status_code, len(r.content))
if r.status_code == 200 and r.text.startswith("observation_date"):
    (EV / "fred_DGS3MO_current.csv").write_text(r.text, encoding="utf-8")
    g = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True)["DGS3MO"]
    g = pd.to_numeric(g, errors="coerce").dropna()
    b = (365 * (raw / 100) / (360 - raw / 100 * 91) * 100).rename("bey")
    j = pd.concat([g.rename("dgs"), b, raw.rename("dtb3")], axis=1, join="inner").loc["2005":]
    res["dgs3mo_vs_dtb3"] = {"n": len(j), "mean_dgs_minus_dtb3_pp": float((j.dgs - j.dtb3).mean()), "mean_dgs_minus_bey_pp": float((j.dgs - j.bey).mean()),
                             "p99_abs_dgs_minus_bey_pp": float((j.dgs - j.bey).abs().quantile(.99)), "max_abs_dgs_minus_bey_pp": float((j.dgs - j.bey).abs().max())}
(EV / "conversion_results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
print(json.dumps(res, indent=1, default=str)[:4200])
