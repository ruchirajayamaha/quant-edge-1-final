"""Build the versioned DTB3 evidence table used by the RF-only r3 policy (offline).

Reads cached ALFRED and archived H.15 responses from audit/rf_research/evidence, stitches every
vintage globally, and writes data/reference/rf_evidence/. Run scripts/pull_rf_vintage_evidence.py
first. Prints the evidence SHA-256 to pin as data.rf_evidence_sha256.

Usage (PowerShell, inside activated Python 3.11 .venv):
    python scripts/build_rf_release_evidence.py
"""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from quantedge.returns import _easter_sunday, expected_federal_reserve_business_days
from quantedge.rf_evidence import (
    DAILY_VINTAGE_START,
    VintageColumn,
    build_daily_publication_calendar,
    build_rf_version_table,
    frame_to_vintage_columns,
    parse_alfred_vintage_csv,
    parse_weekly_h15_bill_row,
    stitch_vintage_versions,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "audit" / "rf_research" / "evidence"
CACHE = EVIDENCE / "alfred_vintage_csv"
ARCHIVE = EVIDENCE / "fed_h15_weekly_archive"
LEDGER = EVIDENCE / "rf_pull_ledger.jsonl"
OUT = ROOT / "data" / "reference" / "rf_evidence"
RAW_RF = ROOT / "data" / "raw" / "qe1_20050101_20261030_r2_cd2904443b" / "fred_dtb3_raw.parquet"
OBS_START = pd.Timestamp("2004-11-17")
OBS_END = pd.Timestamp("2026-10-30")

# Request windows of research-stage files, taken from the scripts that requested them.
LEGACY_WINDOWS: dict[str, tuple[str, str]] = {
    "full_history_snapshots": ("2004-11-17", "2026-10-30"),
    "correction_2020-08-19": ("2020-08-14", "2020-08-31"),
    "correction_2019-02": ("2019-02-22", "2019-03-01"),
    "correction_2018-09-17": ("2018-09-13", "2018-09-21"),
    "correction_2023-09-13": ("2023-09-11", "2023-09-18"),
    "blank_2011-04-22": ("2011-04-19", "2011-05-03"),
    "dec_2025": ("2025-12-19", "2025-12-31"),
    "anomaly_2015-04": ("2015-03-27", "2015-04-08"),
}


def legacy_window(path: Path, frame: pd.DataFrame, published: list[str]) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the request window of a research-stage response."""
    stem = path.stem
    if stem in LEGACY_WINDOWS:
        lo, hi = LEGACY_WINDOWS[stem]
        return pd.Timestamp(lo), pd.Timestamp(hi)
    if stem.startswith("closure_"):
        day = pd.Timestamp(stem.split("_")[1])
        return day - pd.Timedelta(days=30), day + pd.Timedelta(days=12)
    if stem.startswith("chunk_"):
        group = int(stem.split("_")[1])
        start = pd.Timestamp(published[group * 60])
        end = pd.Timestamp(published[min(group * 60 + 59, len(published) - 1)])
        return start - pd.Timedelta(days=60), end
    raise ValueError(f"No request window known for {path.name}.")


def load_vintage_columns(published: list[str]) -> tuple[list[VintageColumn], dict[str, int]]:
    """Parse and validate every cached response into clipped vintage columns."""
    ledger: dict[str, dict] = {}
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            ledger[record["file"]] = record

    columns: list[VintageColumn] = []
    counts = {"ledger_files": 0, "legacy_files": 0}
    for path in sorted(CACHE.glob("*.csv")):
        text = path.read_text(encoding="utf-8")
        if path.name in ledger:
            record = ledger[path.name]
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != record["sha256"]:
                raise ValueError(f"Cached file changed since retrieval: {path.name}.")
            frame = parse_alfred_vintage_csv(text, record["vintages"])
            lo, hi = pd.Timestamp(record["cosd"]), pd.Timestamp(record["coed"])
            counts["ledger_files"] += 1
        else:
            frame = parse_alfred_vintage_csv(text)
            lo, hi = legacy_window(path, frame, published)
            counts["legacy_files"] += 1
        columns.extend(frame_to_vintage_columns(frame, max(lo, OBS_START), min(hi, OBS_END)))
    return columns, counts


def load_archived_values(known: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Read daily 3-month values from archived weekly H.15 pages and map them to weekdays."""
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    first_known = known.loc[known["version_seq"] == 0].set_index("obs_date")["value_pct"]
    for path in sorted(ARCHIVE.glob("h15_*.html")):
        release = pd.Timestamp(path.stem.split("_")[1])
        text = path.read_bytes().decode("utf-8", "replace")
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\r", "")
        try:
            values = parse_weekly_h15_bill_row(text)
        except ValueError as exc:
            failures.append(f"{release.date()}: {exc}")
            continue
        for obs_date, value in values.items():
            if value is None:
                continue
            if obs_date >= release:
                failures.append(f"{release.date()}: column {obs_date.date()} is not before the release")
                continue
            rows.append(
                {
                    "obs_date": obs_date,
                    "value_pct": value,
                    "archive_release_date": release,
                    "source_url": f"https://www.federalreserve.gov/releases/h15/{release.strftime('%Y%m%d')}/",
                }
            )
    table = pd.DataFrame(rows).sort_values(["obs_date", "archive_release_date"]).drop_duplicates("obs_date")
    table = table[table["obs_date"] >= OBS_START].reset_index(drop=True)
    table["alfred_first_value"] = table["obs_date"].map(first_known)
    return table, failures


def merge_archived_first_values(versions: pd.DataFrame, archived: pd.DataFrame) -> pd.DataFrame:
    """Prepend an archived value as the first version when it differs from the first vintage."""
    differs = archived[(archived["value_pct"] - archived["alfred_first_value"]).abs() > 1e-9]
    if differs.empty:
        return versions
    out = versions.copy()
    additions: list[dict[str, object]] = []
    for row in differs.itertuples(index=False):
        out.loc[out["obs_date"] == row.obs_date, "version_seq"] += 1
        additions.append(
            {
                "obs_date": row.obs_date,
                "version_seq": 0,
                "value_pct": row.value_pct,
                "vintage_date": row.archive_release_date,
                "previous_checked_vintage": pd.NaT,
                "exact_vintage": True,
            }
        )
    merged = pd.concat([out, pd.DataFrame(additions)], ignore_index=True)
    return merged.sort_values(["obs_date", "version_seq"], kind="mergesort").reset_index(drop=True)


def main() -> None:
    published = pd.read_csv(EVIDENCE / "dtb3_vintage_dates_alfred.csv")["vintage_date"].tolist()
    columns, file_counts = load_vintage_columns(published)
    retrieved = {c.vintage for c in columns}
    missing = sorted(set(pd.DatetimeIndex(published)) - retrieved)

    versions = stitch_vintage_versions(columns, published)
    versions = versions[(versions["obs_date"] >= OBS_START) & (versions["obs_date"] <= OBS_END)]

    archived, archive_failures = load_archived_values(versions)
    versions = merge_archived_first_values(versions, archived)

    events = pd.read_csv(OUT / "h15_publication_events.csv", parse_dates=["event_date", "effect_obs_date", "floor_date"])
    text = (EVIDENCE / "alfred_release_dates_rid18.txt").read_text(encoding="utf-8")
    release_list = pd.DatetimeIndex(sorted(set(re.findall(r"^(\d{4}-\d{2}-\d{2})\s*$", text, flags=re.M))))
    good_fridays = pd.DatetimeIndex(
        [pd.Timestamp(_easter_sunday(y)) - pd.Timedelta(days=2) for y in range(2004, 2028)]
    )

    raw = pd.read_parquet(RAW_RF)["rate_annual_pct"]
    schedule = expected_federal_reserve_business_days("2004-11-01", "2027-03-31")
    schedule_no_blanks = schedule.difference(pd.DatetimeIndex(raw.index[raw.isna()]))
    daily = build_daily_publication_calendar(
        "2004-11-01", "2027-03-31", events=events, release_list=release_list, good_fridays=good_fridays
    )
    table = build_rf_version_table(
        versions,
        sparse_calendar=schedule_no_blanks,
        daily_calendar=daily,
        schedule_calendar=schedule_no_blanks,
        events=events,
        archived_values=archived,
    )

    # The final live value of every observation must reproduce the audited raw series.
    final = table.sort_values(["obs_date", "version_seq"]).groupby("obs_date").tail(1).set_index("obs_date")["value_pct"]
    aligned = pd.concat([final.rename("final"), raw.rename("raw")], axis=1).loc[OBS_START:OBS_END]
    bad = aligned[~np.isclose(aligned["final"], aligned["raw"], atol=1e-9, equal_nan=True)]

    OUT.mkdir(parents=True, exist_ok=True)
    versions_path = OUT / "dtb3_rf_versions.parquet"
    table.to_parquet(versions_path, engine="pyarrow", index=False)
    archived.to_csv(OUT / "dtb3_archived_h15_values.csv", index=False)
    sha = hashlib.sha256(versions_path.read_bytes()).hexdigest()

    inexact = table[(~table["exact_vintage"]) & (table["version_seq"] > 0)]
    coverage = {
        "evidence_sha256": sha,
        "events_sha256": hashlib.sha256((OUT / "h15_publication_events.csv").read_bytes()).hexdigest(),
        "published_vintages": len(published),
        "vintages_retrieved": len(retrieved),
        "vintages_missing": [d.strftime("%Y-%m-%d") for d in missing],
        "files": file_counts,
        "daily_vintage_start": DAILY_VINTAGE_START.strftime("%Y-%m-%d"),
        "observations": int(table["obs_date"].nunique()),
        "versions": len(table),
        "versions_by_kind": table["version_kind"].value_counts().to_dict(),
        "initial_by_basis": table[table["version_seq"] == 0]["availability_basis"].value_counts().to_dict(),
        "initial_by_tier": table[table["version_seq"] == 0]["evidence_tier"].value_counts().to_dict(),
        "initial_by_status": table[table["version_seq"] == 0]["coverage_status"].value_counts().to_dict(),
        "value_basis": table["value_basis"].value_counts().to_dict(),
        "inexact_initial_versions": [
            f"{r.obs_date.date()} first seen {r.vintage_date.date()}"
            for r in table[(~table["exact_vintage"]) & (table["version_seq"] == 0)].itertuples()
        ],
        "inexact_revisions": [
            f"{r.obs_date.date()} seq {r.version_seq} by {r.vintage_date.date()}" for r in inexact.itertuples()
        ],
        "revisions": [
            f"{r.obs_date.date()} {r.value_pct} {r.version_kind} {r.vintage_date.date()}"
            for r in table[table["version_seq"] > 0].itertuples()
        ],
        "archive_pages_parsed": int(archived["archive_release_date"].nunique()),
        "archive_observations": len(archived),
        "archive_value_differs_from_first_vintage": archived[
            (archived["value_pct"] - archived["alfred_first_value"]).abs() > 1e-9
        ]["obs_date"].dt.strftime("%Y-%m-%d").tolist(),
        "archive_parse_failures": archive_failures,
        "final_value_mismatches_against_r2_raw": [str(i.date()) for i in bad.index],
    }
    (OUT / "evidence_coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    print(json.dumps(coverage, indent=2)[:6000])


if __name__ == "__main__":
    main()
