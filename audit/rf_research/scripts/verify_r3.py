"""Independent verification of an r3 snapshot against its evidence table and r2 parent (read-only).

Deliberately avoids select_rf_versions_asof: every session is recomputed by brute-force filtering.
Usage: python audit/rf_research/scripts/verify_r3.py <r3_dataset_id>
"""
import hashlib, json, pathlib, sys
import numpy as np, pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[3]
R2 = "qe1_20050101_20261030_r2_cd2904443b"
V1 = "qe1_20050101_20261030_afb9ce5694"
R3 = sys.argv[1]
proc, raw_dir = REPO / "data" / "processed", REPO / "data" / "raw"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
res: dict = {"r3": R3, "parent": R2}

# 1. Hashes
for ds in (V1, R2, R3):
    m = json.loads((proc / ds / "manifest.json").read_text(encoding="utf-8"))
    bad = [k for k, v in m["file_sha256"].items() if sha(REPO / k) != v]
    res[f"hashes_{ds}"] = {"files": len(m["file_sha256"]), "bad": bad}
m3 = json.loads((proc / R3 / "manifest.json").read_text(encoding="utf-8"))
res["manifest"] = {k: m3[k] for k in ("policy_revision", "parent_dataset_id", "schema_version")}
res["evidence_sha_matches_manifest"] = sha(raw_dir / R3 / "dtb3_rf_versions.parquet") == m3["rf_convention"]["evidence_sha256"]

# 2. ETF identity with the parent, including raw files
for name in ("prices", "simple_returns", "log_returns", "quality_flags", "excluded_return_rows"):
    a, b = pd.read_parquet(proc / R3 / f"{name}.parquet"), pd.read_parquet(proc / R2 / f"{name}.parquet")
    res[f"identical_{name}"] = bool(a.equals(b))
res["identical_raw_etf"] = pd.read_parquet(raw_dir / R3 / "etf_prices_raw.parquet").equals(pd.read_parquet(raw_dir / R2 / "etf_prices_raw.parquet"))
res["identical_raw_dtb3"] = pd.read_parquet(raw_dir / R3 / "fred_dtb3_raw.parquet").equals(pd.read_parquet(raw_dir / R2 / "fred_dtb3_raw.parquet"))
res["identical_ex_post_rf"] = pd.read_parquet(proc / R3 / "rf_daily_ex_post.parquet").iloc[:, 0].equals(pd.read_parquet(proc / R2 / "rf_daily_ex_post.parquet").iloc[:, 0])

# 3. Brute-force recomputation
versions = pd.read_parquet(raw_dir / R3 / "dtb3_rf_versions.parquet")
rf3 = pd.read_parquet(proc / R3 / "rf_daily.parquet").iloc[:, 0]
rf2 = pd.read_parquet(proc / R2 / "rf_daily.parquet").iloc[:, 0]
prov = pd.read_parquet(proc / R3 / "rf_provenance.parquet")
sessions = pd.read_parquet(proc / R3 / "prices.parquet").index
prev = pd.Series(sessions[:-1], index=sessions[1:])
cut = (prev + pd.Timedelta(hours=16)).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
wrong, obs_chosen = [], {}
for day in rf3.index:
    ok = versions[versions["available_at_utc"] <= cut[day]]
    last = ok.sort_values(["obs_date", "version_seq"]).groupby("obs_date").tail(1).dropna(subset=["value_pct"])
    row = last.loc[last["obs_date"].idxmax()]
    obs_chosen[day] = row["obs_date"]
    if not np.isclose(row["value_pct"] / 25200.0, rf3[day], rtol=0, atol=1e-15) or row["obs_date"] != prov.at[day, "obs_date"]:
        wrong.append(str(day.date()))
res["bruteforce_sessions"] = len(rf3)
res["bruteforce_mismatches"] = wrong
res["all_selected_available_by_cutoff"] = bool((prov["available_at_utc"] <= prov["decision_time_utc"]).all())
res["missing_rf_sessions"] = int(rf3.isna().sum())
res["accrual_formula_error_max"] = float(
    (pd.read_parquet(proc / R3 / "rf_daily_accrual_91d_sensitivity.parquet").iloc[:, 0]
     - ((1.0 / (1.0 - prov["value_pct"] / 100.0 * 91.0 / 360.0)) ** ((prov.index - prev.reindex(prov.index).values).days.values / 91.0) - 1.0)).abs().max()
)

# 3b. Stitching regressions against raw responses, independent of the stitch code
ev = REPO / "audit" / "rf_research" / "evidence"
sample = pd.read_csv(ev / "dtb3_first_appearance_sample.csv", parse_dates=["obs", "first_vintage"]).set_index("obs")
first_v = versions[versions["version_seq"] == 0].set_index("obs_date")["vintage_date"]
common = sample.index.intersection(first_v.index)
res["research_sample_first_vintage_agreement"] = {"compared": len(common), "disagree": int((sample.loc[common, "first_vintage"] != first_v.loc[common]).sum())}
boundary = {pd.Timestamp(line.split(",")[1][5:]) for p in (ev / "alfred_vintage_csv").glob("full_*.csv") for line in [p.open(encoding="utf-8").readline().strip()]}
res["initial_versions_first_seen_in_a_requests_first_column"] = int(first_v.isin(boundary).sum())
res["request_first_columns"] = len(boundary)

# 3c. Future-data invariance on the real table
sys.path.insert(0, str(REPO / "src"))
from quantedge.returns import select_rf_versions_asof
split = pd.Timestamp("2015-01-02", tz="UTC")
altered = versions.copy()
altered.loc[altered["available_at_utc"] > split, "value_pct"] = 99.0
base_series, _ = select_rf_versions_asof(versions, rf3.index, price_sessions=sessions)
alt_series, _ = select_rf_versions_asof(altered, rf3.index, price_sessions=sessions)
before = cut.reindex(rf3.index) <= split
res["future_invariance_sessions_checked"] = int(before.sum())
res["future_invariance_changed"] = int((base_series[before] != alt_series[before]).sum())

# 4. Representative cases, printed for inspection
cases = ["2005-01-12", "2008-09-22", "2015-03-09", "2016-01-28", "2017-01-24", "2018-09-20", "2019-02-22", "2020-08-24", "2021-04-06", "2023-09-15", "2023-11-13", "2025-12-29", "2026-10-30"]
cols = ["decision_time_utc", "obs_date", "version_seq", "value_pct", "vintage_date", "availability_date", "availability_basis", "evidence_tier", "coverage_status"]
res["cases"] = {c: {k: str(prov.at[pd.Timestamp(c), k]) for k in cols} | {"r2_quote": round(float(rf2[c] * 25200), 4)} for c in cases}

# 5. r2 selection, to separate what changed and why
rawq = pd.read_parquet(raw_dir / R2 / "fred_dtb3_raw.parquet")["rate_annual_pct"]
sys.path.insert(0, str(REPO / "src"))
from quantedge.returns import expected_federal_reserve_business_days
cal = expected_federal_reserve_business_days("2004-11-01", "2027-03-31").difference(pd.DatetimeIndex(rawq.index[rawq.isna()]))
vals = rawq.dropna()
pub = cal[np.searchsorted(cal.values, vals.index.values, side="right")]
av = (pub + pd.Timedelta(hours=16, minutes=15)).tz_localize("America/New_York").tz_convert("UTC")
tab = pd.DataFrame({"av": av, "o": vals.index}).sort_values(["av", "o"])
pos = np.searchsorted(tab["av"].values, cut.reindex(rf3.index).values, side="right") - 1
r2obs = pd.Series(tab["o"].to_numpy()[pos], index=rf3.index)
res["r2_selection_reproduced"] = bool(np.allclose(vals.reindex(r2obs.values).to_numpy() / 25200.0, rf2.to_numpy(), rtol=0, atol=1e-15))

first = versions[versions["version_seq"] == 0].set_index("obs_date")
frame = pd.DataFrame({"r2_obs": r2obs, "r3_obs": prov["obs_date"], "r2_q": rf2 * 25200, "r3_q": rf3 * 25200})
frame["diff_bp"] = (frame["r3_q"] - frame["r2_q"]) * 100
frame["daily_diff_bp"] = (rf3 - rf2) * 1e4
frame["r2_basis"] = frame["r2_obs"].map(first["availability_basis"])
frame["r2_tier"] = frame["r2_obs"].map(first["evidence_tier"])
def group(r):
    if r.r3_obs < r.r2_obs:
        return f"r2_too_early:{r.r2_tier}:{r.r2_basis}"
    if r.r3_obs > r.r2_obs:
        return "r2_over_delayed"
    return "same_obs_value_version" if abs(r.diff_bp) > 1e-9 else "unchanged"
frame["group"] = [group(r) for r in frame.itertuples()]
changed = frame[frame["group"] != "unchanged"]
def stats(x):
    return {"sessions": len(x), "value_changed": int((x.diff_bp.abs() > 1e-9).sum()), "signed_mean_quote_bp": round(float(x.diff_bp.mean()), 4),
            "mean_abs_quote_bp": round(float(x.diff_bp.abs().mean()), 4), "max_abs_quote_bp": round(float(x.diff_bp.abs().max()), 4),
            "max_abs_daily_return_bp": round(float(x.daily_diff_bp.abs().max()), 5), "first": str(x.index.min().date()), "last": str(x.index.max().date())}
res["changes_by_group"] = {k: stats(g) for k, g in changed.groupby("group")}
res["changes_all"] = stats(changed)
n = len(frame)
res["overall"] = {"sessions": n, "sessions_changed_any_selection": len(changed), "sessions_value_changed": int((frame.diff_bp.abs() > 1e-9).sum()),
                  "signed_annual_bp": round(float((rf3 - rf2).sum() * 1e4 / (n / 252)), 5), "absolute_annual_bp": round(float((rf3 - rf2).abs().sum() * 1e4 / (n / 252)), 5),
                  "signed_mean_quote_bp_all_sessions": round(float(frame.diff_bp.mean()), 4), "mean_abs_quote_bp_all_sessions": round(float(frame.diff_bp.abs().mean()), 4),
                  "max_abs_quote_bp": round(float(frame.diff_bp.abs().max()), 3), "worst_date": str(frame.diff_bp.abs().idxmax().date()),
                  "by_era_mean_abs_quote_bp": {str(y): round(float(g.diff_bp.abs().mean()), 3) for y, g in frame.groupby(frame.index.year)}}
acc = pd.read_parquet(proc / R3 / "rf_daily_accrual_91d_sensitivity.parquet").iloc[:, 0]
gap = (acc - rf3) * 1e4
res["accrual_sensitivity"] = {"annual_gap_bp_full": round(float(gap.sum() / (n / 252)), 3), "annual_gap_bp_2021_2026": round(float(gap.loc["2021":].sum() / (len(gap.loc["2021":]) / 252)), 3),
                              "max_abs_session_bp": round(float(gap.abs().max()), 3)}
res["selected_sessions_by_tier"] = prov["evidence_tier"].value_counts().to_dict()
res["selected_sessions_by_status"] = prov["coverage_status"].value_counts().to_dict()
res["selected_sessions_by_basis"] = prov["availability_basis"].value_counts().to_dict()
res["selected_sessions_by_value_basis"] = prov["value_basis"].value_counts().to_dict()
res["selected_version_gt0"] = int((prov["version_seq"] > 0).sum())
(REPO / "audit" / "rf_research" / "evidence" / "r3_verification.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
print(json.dumps(res, indent=1, default=str))
