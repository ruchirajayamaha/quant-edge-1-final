"""Final research checks: omitted-Treasury-data cases, known revisions and timing materiality (read-only)."""
import json, pathlib, re, html, sys
import numpy as np, pandas as pd
ROOT = pathlib.Path(__file__).resolve().parents[1]; EV = ROOT / "evidence"; REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / "src"))
from quantedge.returns import _easter_sunday, align_risk_free_rate, expected_federal_reserve_business_days
SNAP = "qe1_20050101_20261030_r2_cd2904443b"
raw = pd.read_parquet(REPO / f"data/raw/{SNAP}/fred_dtb3_raw.parquet")["rate_annual_pct"]
stored = pd.read_parquet(REPO / f"data/processed/{SNAP}/rf_daily.parquet").iloc[:, 0]
px = pd.read_parquet(REPO / f"data/processed/{SNAP}/prices.parquet").index
def load(n):
    d = pd.read_csv(EV / "alfred_vintage_csv" / n, index_col=0, parse_dates=True); return d
for n, lo, hi in [("correction_2018-09-17.csv", "2018-09-13", "2018-09-21"), ("correction_2023-09-13.csv", "2023-09-11", "2023-09-18"),
                  ("blank_2011-04-22.csv", "2011-04-19", "2011-05-03"), ("dec_2025.csv", "2025-12-19", "2025-12-31")]:
    print(n); print(load(n).loc[lo:hi].to_string())
s = (EV / "fed_h15_annc_d.html").read_bytes().decode("utf-8", "replace")
s = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", s))))
i = s.find("Updated Treasury rates for August 2, 2023"); print(">>", s[i:i + 330])
snap = pd.read_csv(EV / "alfred_vintage_csv" / "full_history_snapshots.csv", index_col=0, parse_dates=True).apply(pd.to_numeric, errors="coerce")
c = snap.iloc[:, 6]; d = (c.reindex(raw.index) - raw); print("2016-12-30 vintage vs current:", d[d.abs() > 1e-9].to_dict())

closures = pd.DatetimeIndex(["2008-12-26", "2009-01-20", "2009-12-24", "2010-02-08", "2010-02-09", "2012-10-29", "2012-10-30", "2013-03-06", "2013-12-10", "2014-01-21",
    "2014-02-13", "2014-03-03", "2014-03-17", "2014-12-26", "2015-02-17", "2015-03-05", "2016-01-22", "2016-01-25", "2016-01-26", "2019-01-14", "2019-02-20",
    "2017-01-20", "2018-03-02", "2018-12-24", "2020-12-24", "2021-01-20", "2024-12-24"])
gf = pd.DatetimeIndex([pd.Timestamp(_easter_sunday(y)) - pd.Timedelta(days=2) for y in range(2004, 2027)])
cal = expected_federal_reserve_business_days("2004-11-01", "2026-12-31").difference(closures).union(gf).sort_values()
vals = raw.dropna(); obs = vals.index
pub = cal[np.searchsorted(cal.values, obs.values, side="right")]
ts = lambda d: (pd.Timestamp(d) + pd.Timedelta(hours=16, minutes=15)).tz_localize("America/New_York")
m = {o: ts(p) for o, p in zip(obs, pub)}
base = align_risk_free_rate(raw, stored.index, release_timestamps=m, price_sessions=px, mode="forward_decision")
over = {"2018-09-17": "2018-09-19", "2020-08-19": "2020-08-26", "2023-08-01": "2023-08-03", "2023-09-12": "2023-09-14", "2025-12-23": "2025-12-29", "2025-12-24": "2025-12-29"}
m2 = dict(m)
for k, v in over.items(): m2[pd.Timestamp(k)] = ts(v)
ext = align_risk_free_rate(raw, stored.index, release_timestamps=m2, price_sessions=px, mode="forward_decision")
def cmp(a, b):
    q = (a - b) * 25200; return {"differ": int(q.abs().gt(1e-9).sum()), "max_quote_pp": round(float(q.abs().max()), 3), "ann_bp": round(float((a - b).sum() * 1e4 / (len(a) / 252)), 5)}
r = {"corrected_vs_stored": cmp(base, stored), "extended_vs_stored": cmp(ext, stored), "extended_vs_corrected": cmp(ext, base)}
conv = json.loads((EV / "conversion_results.json").read_text())["by_year_bp"]
ev = [conv[str(y)]["gap_bp"] for y in range(2021, 2027)]
r["conversion_gap_bp_per_year_evaluation_window"] = round(sum(ev) / 5.82, 2)
r["conversion_sharpe_delta_at_10pct_vol_evaluation_window"] = round(-sum(ev) / 5.82 / 1e4 / 0.10, 4)
(EV / "final_checks.json").write_text(json.dumps(r, indent=1)); print(r)
