"""Download and cache DTB3 vintage evidence for the RF-only r3 policy (public, no key).

Reuses valid cached responses, requests at most 12 vintages at a time, throttles requests, validates
exact vintage headers, and stops at the first failure. Rerun to resume.

Usage (PowerShell, inside activated Python 3.11 .venv):
    python scripts/pull_rf_vintage_evidence.py vintages
    python scripts/pull_rf_vintage_evidence.py grid
    python scripts/pull_rf_vintage_evidence.py archives
    python scripts/pull_rf_vintage_evidence.py refine --lo 2017-10-20 --hi 2017-12-11 \\
        --cosd 2004-11-22 --coed 2005-01-10
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import pandas as pd
import requests

from quantedge.rf_evidence import (
    MAX_VINTAGES_PER_REQUEST,
    VintageResponseError,
    parse_alfred_vintage_csv,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "audit" / "rf_research" / "evidence"
CACHE = EVIDENCE / "alfred_vintage_csv"
ARCHIVE = EVIDENCE / "fed_h15_weekly_archive"
LEDGER = EVIDENCE / "rf_pull_ledger.jsonl"
BASE_URL = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
OBS_START = "2004-11-17"
TRAILING_DAYS = 60
GRID_STEP = 60
PAUSE_SECONDS = 1.2


def published_vintages() -> list[str]:
    return pd.read_csv(EVIDENCE / "dtb3_vintage_dates_alfred.csv")["vintage_date"].tolist()


def cached_vintages() -> set[str]:
    found: set[str] = set()
    for path in CACHE.glob("*.csv"):
        if path.name == "full_history_snapshots.csv":
            continue
        header = path.open(encoding="utf-8").readline().strip().split(",")[1:]
        found |= {f"{c[5:9]}-{c[9:11]}-{c[11:13]}" for c in header}
    return found


def fetch(vintages: list[str], cosd: str, coed: str, path: Path) -> None:
    """Fetch one validated request, or exit at the first failure so the run can be resumed."""
    if len(vintages) > MAX_VINTAGES_PER_REQUEST:
        raise ValueError(f"Refusing {len(vintages)} vintages; ALFRED silently truncates at 12.")
    n = len(vintages)
    url = (
        f"{BASE_URL}?id={','.join(['DTB3'] * n)}&cosd={','.join([cosd] * n)}"
        f"&coed={','.join([coed] * n)}&vintage_date={','.join(vintages)}"
    )
    response = requests.get(url, timeout=120)
    if response.status_code != 200:
        print(f"STOP {path.name}: HTTP {response.status_code} {response.text[:160]!r}")
        sys.exit(1)
    try:
        parse_alfred_vintage_csv(response.text, vintages)
    except VintageResponseError as exc:
        print(f"STOP {path.name}: {exc}")
        sys.exit(1)
    path.write_text(response.text, encoding="utf-8")
    record = {
        "file": path.name,
        "vintages": vintages,
        "cosd": cosd,
        "coed": coed,
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    time.sleep(PAUSE_SECONDS)


def pull_vintages() -> None:
    """Fill every published vintage missing from the cache, with a trailing observation window."""
    missing = sorted(set(published_vintages()) - cached_vintages())
    print(f"missing vintages: {len(missing)}")
    done = 0
    for i in range(0, len(missing), MAX_VINTAGES_PER_REQUEST):
        batch = missing[i : i + MAX_VINTAGES_PER_REQUEST]
        cosd = (pd.Timestamp(batch[0]) - pd.Timedelta(days=TRAILING_DAYS)).strftime("%Y-%m-%d")
        fetch(batch, cosd, batch[-1], CACHE / f"full_{batch[0]}.csv")
        done += 1
    print(f"requests: {done}; remaining vintages: {len(set(published_vintages()) - cached_vintages())}")


def pull_grid() -> None:
    """Fetch a sparse full-history grid so revisions older than the trailing window are found."""
    vintages = published_vintages()
    grid = vintages[::GRID_STEP] + [vintages[-1]]
    done = 0
    for i in range(0, len(grid), MAX_VINTAGES_PER_REQUEST):
        batch = grid[i : i + MAX_VINTAGES_PER_REQUEST]
        path = CACHE / f"grid_{batch[0]}.csv"
        if path.exists():
            continue
        fetch(batch, OBS_START, "2026-10-30", path)
        done += 1
    print(f"grid requests: {done}; grid vintages: {len(grid)}")


def pull_archives() -> None:
    """Fetch archived weekly H.15 pages covering the sparse-vintage era."""
    ARCHIVE.mkdir(exist_ok=True)
    text = (EVIDENCE / "alfred_release_dates_rid18.txt").read_text(encoding="utf-8")
    listed = re.findall(r"^(\d{4}-\d{2}-\d{2})\s*$", text, flags=re.M)
    dates = [d for d in listed if "2004-11-22" <= d <= "2006-03-06"]
    print(f"archive pages: {len(dates)}")
    failures: list[str] = []
    for d in dates:
        path = ARCHIVE / f"h15_{d}.html"
        if path.exists():
            continue
        url = f"https://www.federalreserve.gov/releases/h15/{d.replace('-', '')}/"
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            path.write_bytes(response.content)
        elif response.status_code == 404:
            failures.append(d)
        else:
            print(f"STOP {d}: HTTP {response.status_code}")
            sys.exit(1)
        time.sleep(PAUSE_SECONDS)
    print(f"archive pages missing: {failures}")


def pull_refine(lo: str, hi: str, cosd: str, coed: str) -> None:
    """Fetch every vintage in a bracket over a narrow window to pin an older revision's date."""
    bracket = [v for v in published_vintages() if lo <= v <= hi]
    done = 0
    for i in range(0, len(bracket), MAX_VINTAGES_PER_REQUEST):
        batch = bracket[i : i + MAX_VINTAGES_PER_REQUEST]
        path = CACHE / f"refine_{cosd}_{batch[0]}.csv"
        if path.exists():
            continue
        fetch(batch, cosd, coed, path)
        done += 1
    print(f"refine requests: {done}; vintages in bracket: {len(bracket)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["vintages", "grid", "archives", "refine"])
    for flag in ("--lo", "--hi", "--cosd", "--coed"):
        parser.add_argument(flag)
    args = parser.parse_args()
    if args.action == "refine":
        pull_refine(args.lo, args.hi, args.cosd, args.coed)
    else:
        {"vintages": pull_vintages, "grid": pull_grid, "archives": pull_archives}[args.action]()


if __name__ == "__main__":
    main()
