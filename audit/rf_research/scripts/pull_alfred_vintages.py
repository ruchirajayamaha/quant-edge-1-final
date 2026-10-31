"""Bounded no-key ALFRED DTB3 vintage pull for the RF research review (read-only research).

Chunks the published DTB3 vintage dates into GET requests against alfredgraph.csv,
writes raw responses under evidence/alfred_vintage_csv/, and stops at the first failure.
"""
import pathlib, sys, time
import pandas as pd, requests

ROOT = pathlib.Path(__file__).resolve().parents[1] / "evidence"
OUT = ROOT / "alfred_vintage_csv"
BASE = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
CHUNK = 60
vs = pd.read_csv(ROOT / "dtb3_vintage_dates_alfred.csv")["vintage_date"].tolist()


def get(vints, cosd, coed, path):
    n = len(vints)
    q = {"id": ",".join(["DTB3"] * n), "cosd": ",".join([cosd] * n), "coed": ",".join([coed] * n),
         "vintage_date": ",".join(vints)}
    url = BASE + "?" + "&".join(f"{k}={v}" for k, v in q.items())
    r = requests.get(url, timeout=120)
    ct = r.headers.get("content-type", "")
    if r.status_code != 200 or "csv" not in ct or not r.text.startswith("observation_date"):
        print("STOP", path.name, r.status_code, ct, r.text[:200])
        sys.exit(1)
    path.write_text(r.text, encoding="utf-8")
    return r.text.count("\n")


# Sample A: full-history snapshots for persistent-revision detection.
snap = ["2005-06-28", "2006-12-29", "2008-12-31", "2010-12-30", "2012-12-31", "2014-12-31",
        "2016-12-30", "2018-12-31", "2020-12-31", "2022-12-30", "2024-12-31", "2026-10-30"]
snap = [max((v for v in vs if v <= s)) for s in snap]
print("snapshots", snap, get(snap, "2004-11-17", "2026-10-30", OUT / "full_history_snapshots.csv"))

# Sample B: every vintage, chunked, with a 60-day trailing observation window.
n = 0
for i in range(0, len(vs), CHUNK):
    c = vs[i:i + CHUNK]
    cosd = (pd.Timestamp(c[0]) - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    p = OUT / f"chunk_{i // CHUNK:03d}.csv"
    if p.exists():
        continue
    get(c, cosd, c[-1], p)
    n += 1
    time.sleep(1.0)
print("requests", n, "files", len(list(OUT.glob("chunk_*.csv"))))
