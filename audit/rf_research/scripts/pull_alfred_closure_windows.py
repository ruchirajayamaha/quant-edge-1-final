"""Targeted ALFRED pull around documented closures/holiday cases (max 12 vintages per request)."""
import pathlib, sys, time
import pandas as pd, requests

ROOT = pathlib.Path(__file__).resolve().parents[1] / "evidence"
OUT = ROOT / "alfred_vintage_csv"
vs = pd.DatetimeIndex(pd.read_csv(ROOT / "dtb3_vintage_dates_alfred.csv")["vintage_date"])
cases = ["2008-12-26", "2009-01-20", "2009-12-24", "2010-02-09", "2012-10-30", "2013-03-06", "2013-12-10", "2014-01-21",
         "2014-02-13", "2014-03-03", "2014-03-17", "2014-12-26", "2015-02-17", "2015-03-05", "2016-01-26", "2017-01-20",
         "2018-03-02", "2018-03-21", "2018-12-24", "2019-01-14", "2019-02-20", "2020-12-24", "2021-01-20", "2024-12-24",
         "2016-03-25", "2021-04-02", "2023-11-10", "2021-06-18", "2025-01-09"]
done = 0
for c in cases:
    d = pd.Timestamp(c)
    w = vs[(vs >= d - pd.Timedelta(days=9)) & (vs <= d + pd.Timedelta(days=9))][:12].strftime("%Y-%m-%d").tolist()
    n = len(w)
    cosd = (d - pd.Timedelta(days=30)).strftime("%Y-%m-%d"); coed = (d + pd.Timedelta(days=12)).strftime("%Y-%m-%d")
    url = ("https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=" + ",".join(["DTB3"] * n) + "&cosd=" + ",".join([cosd] * n)
           + "&coed=" + ",".join([coed] * n) + "&vintage_date=" + ",".join(w))
    r = requests.get(url, timeout=120)
    if r.status_code != 200 or not r.text.startswith("observation_date"):
        print("STOP", c, r.status_code, r.text[:160]); sys.exit(1)
    (OUT / f"closure_{c}.csv").write_text(r.text, encoding="utf-8"); done += 1
    time.sleep(1.0)
print("requests", done)
