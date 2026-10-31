"""Versioned DTB3 release evidence: ALFRED parsing, global stitching, and day-level availability.

Implemented for the RF-only ``r3_release_evidence`` policy.

Conventions:
- An ALFRED vintage date is day-level evidence, not a first-publication timestamp. It can trail
  or precede the source release, so it is combined with a publication calendar conservatively.
- A blank cell only means "not published or withdrawn" inside the window actually requested.
  ALFRED returns a vintage's full history when the requested window holds no data for it, so
  every column is clipped to its request window before use.
- Vintages are stitched globally in date order. An appearance at a request boundary is compared
  with the previous published vintage, wherever that vintage was retrieved from.
- Sparse early history keeps the publication calendar and an explicit fallback label. It is never
  delayed to the first June 2005 vintage.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import io
import re

import numpy as np
import pandas as pd

from quantedge.returns import expected_federal_reserve_business_days

# Vintages are about weekly until this date, then published on each H.15 update.
DAILY_VINTAGE_START: pd.Timestamp = pd.Timestamp("2006-02-23")
# ALFRED silently returns only the first 12 series of a longer request.
MAX_VINTAGES_PER_REQUEST: int = 12

VERSION_COLUMNS: tuple[str, ...] = (
    "obs_date",
    "version_seq",
    "value_pct",
    "vintage_date",
    "previous_checked_vintage",
    "exact_vintage",
)
RF_VERSION_TABLE_COLUMNS: tuple[str, ...] = (
    "obs_date",
    "version_seq",
    "version_kind",
    "value_pct",
    "vintage_date",
    "exact_vintage",
    "calendar_date",
    "availability_date",
    "available_at_utc",
    "availability_basis",
    "value_basis",
    "evidence_tier",
    "coverage_status",
)
EVENT_COLUMNS: tuple[str, ...] = (
    "event_date",
    "event_type",
    "classification",
    "effect_obs_date",
    "floor_date",
    "source_url",
    "note",
)

_VINTAGE_COLUMN = re.compile(r"^(?P<series>[A-Z0-9]+)_(?P<ymd>\d{8})$")


class VintageResponseError(ValueError):
    """Raised when an ALFRED response does not match the vintages that were requested."""


@dataclass(frozen=True)
class VintageColumn:
    """One vintage's values, clipped to the observation window that was actually requested."""

    vintage: pd.Timestamp
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    values: pd.Series


def parse_alfred_vintage_csv(
    csv_text: str,
    requested_vintages: Sequence[str] | None = None,
    *,
    series_id: str = "DTB3",
) -> pd.DataFrame:
    """Parse ``alfredgraph.csv`` text, validating exact vintage identity and order.

    Args:
        csv_text: Raw response body.
        requested_vintages: ``YYYY-MM-DD`` vintages requested, in order. A count match is not
            enough; the returned headers must equal this list exactly.
        series_id: Expected series identifier in every column header.

    Returns:
        Observation-by-vintage ``DataFrame`` with ``Timestamp`` columns and float values.
    """
    if not csv_text or not csv_text.startswith("observation_date,"):
        raise VintageResponseError("Response is not an ALFRED observation CSV.")
    frame = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
    returned: list[pd.Timestamp] = []
    for col in frame.columns[1:]:
        match = _VINTAGE_COLUMN.match(col)
        if match is None or match["series"] != series_id:
            raise VintageResponseError(f"Unexpected vintage column {col!r}.")
        returned.append(pd.Timestamp(match["ymd"]))
    if not returned:
        raise VintageResponseError("Response holds no vintage columns.")
    if requested_vintages is not None:
        requested = [pd.Timestamp(v) for v in requested_vintages]
        if returned != requested:
            raise VintageResponseError(
                f"Returned vintages {[d.strftime('%Y-%m-%d') for d in returned[:14]]} differ from "
                f"requested {[d.strftime('%Y-%m-%d') for d in requested[:14]]}."
            )
    if len(set(returned)) != len(returned):
        raise VintageResponseError("Response repeats a vintage column.")

    out = frame.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    out.columns = returned
    out.index = pd.DatetimeIndex(pd.to_datetime(frame.iloc[:, 0]), name="obs_date")
    return out


def frame_to_vintage_columns(
    frame: pd.DataFrame,
    window_start: str | pd.Timestamp,
    window_end: str | pd.Timestamp,
) -> list[VintageColumn]:
    """Clip each vintage column to the requested observation window."""
    start, end = pd.Timestamp(window_start), pd.Timestamp(window_end)
    columns: list[VintageColumn] = []
    for vintage in frame.columns:
        col = frame[vintage]
        values = col.loc[(col.index >= start) & (col.index <= end)].dropna()
        columns.append(VintageColumn(pd.Timestamp(vintage), start, end, values.astype(float)))
    return columns


def _merge_same_vintage(items: list[VintageColumn]) -> tuple[dict[pd.Timestamp, float], list[tuple[pd.Timestamp, pd.Timestamp]]]:
    """Combine retrievals of one vintage and reject any disagreement inside overlapping windows."""
    merged: dict[pd.Timestamp, float] = {}
    windows = [(c.window_start, c.window_end) for c in items]
    for col in items:
        for obs, value in col.values.items():
            obs_ts = pd.Timestamp(obs)
            if obs_ts in merged and not np.isclose(merged[obs_ts], float(value), atol=1e-9):
                raise VintageResponseError(f"Conflicting values for {obs_ts.date()} in {col.vintage.date()}.")
            merged[obs_ts] = float(value)
    for col in items:
        for obs in merged:
            if col.window_start <= obs <= col.window_end and obs not in col.values.index:
                raise VintageResponseError(f"Blank/value conflict for {obs.date()} in {col.vintage.date()}.")
    return merged, windows


def stitch_vintage_versions(
    columns: Iterable[VintageColumn],
    published_vintages: Sequence[str | pd.Timestamp],
) -> pd.DataFrame:
    """Reduce vintage columns to one row per observation version, across request boundaries.

    A version is recorded when an observation first appears, changes value, or is withdrawn.
    ``exact_vintage`` is ``True`` only when the previous published vintage also covered that
    observation, so the change is pinned to one vintage. Otherwise the true change date lies in
    ``(previous_checked_vintage, vintage_date]``.
    """
    by_vintage: dict[pd.Timestamp, list[VintageColumn]] = {}
    for col in columns:
        by_vintage.setdefault(col.vintage, []).append(col)

    published = sorted({pd.Timestamp(v) for v in published_vintages})
    unknown = sorted(set(by_vintage) - set(published))
    if unknown:
        raise VintageResponseError(f"Vintages outside the published list: {unknown[:5]}.")
    previous_published = {v: published[i - 1] for i, v in enumerate(published) if i > 0}

    state: dict[pd.Timestamp, float] = {}
    last_checked: dict[pd.Timestamp, pd.Timestamp] = {}
    next_seq: dict[pd.Timestamp, int] = {}
    rows: list[dict[str, object]] = []

    def record(obs: pd.Timestamp, value: float, vintage: pd.Timestamp) -> None:
        prior = previous_published.get(vintage)
        checked = last_checked.get(obs)
        prior_covered = any(
            col.window_start <= obs <= col.window_end for col in by_vintage.get(prior, [])
        )
        if prior_covered:
            checked = prior
        # An observation dated after the previous vintage cannot have appeared in it.
        exact = prior is None or prior_covered or obs > prior
        rows.append(
            {
                "obs_date": obs,
                "version_seq": next_seq.get(obs, 0),
                "value_pct": value,
                "vintage_date": vintage,
                "previous_checked_vintage": checked if checked is not None else pd.NaT,
                "exact_vintage": bool(exact),
            }
        )
        next_seq[obs] = next_seq.get(obs, 0) + 1
        state[obs] = value

    for vintage in sorted(by_vintage):
        merged, windows = _merge_same_vintage(by_vintage[vintage])

        def covered(obs: pd.Timestamp) -> bool:
            return any(lo <= obs <= hi for lo, hi in windows)

        for obs in sorted(merged):
            value = merged[obs]
            current = state.get(obs)
            if current is None or np.isnan(current) or not np.isclose(current, value, atol=1e-9):
                record(obs, value, vintage)
        for obs in sorted(state):
            if not np.isnan(state[obs]) and obs not in merged and covered(obs):
                record(obs, float("nan"), vintage)
        for obs in set(merged) | {o for o in state if covered(o)}:
            last_checked[obs] = vintage

    out = pd.DataFrame(rows, columns=list(VERSION_COLUMNS))
    if out.empty:
        return out
    out["vintage_date"] = pd.to_datetime(out["vintage_date"])
    out["previous_checked_vintage"] = pd.to_datetime(out["previous_checked_vintage"])
    return out.sort_values(["obs_date", "version_seq"], kind="mergesort").reset_index(drop=True)


_MONTH_TOKEN = re.compile(r"\b(Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)\b")


def parse_weekly_h15_bill_row(page_text: str) -> dict[pd.Timestamp, float | None]:
    """Return an archived weekly H.15 page's daily 3-month bill values, keyed by column date.

    ``page_text`` keeps the fixed-width line layout of the archived table. A holiday column is
    left blank rather than marked, so values are matched to dates by horizontal position. A
    blank or ``n.a.`` daily column maps to ``None``.
    """
    lines = page_text.splitlines()
    month_at = next((i for i, line in enumerate(lines) if len(_MONTH_TOKEN.findall(line)) >= 5), None)
    if month_at is None:
        raise ValueError("Column header not found in archived H.15 page.")
    months = _MONTH_TOKEN.findall(lines[month_at])

    year_line = next((ln for ln in reversed(lines[:month_at]) if "Week Ending" in ln), "")
    years = re.findall(r"\b(?:19|20)\d{2}\b", year_line.split("Week Ending")[0])
    day_line = next(
        (ln for ln in lines[month_at:month_at + 3] if len(re.findall(r"(?<![\d.])\d{1,2}\*?(?![\d.])", ln)) >= 5),
        None,
    )
    if day_line is None or not years or len(months) < len(years):
        raise ValueError(f"Unreadable column header: {years} {months}.")
    day_matches = list(re.finditer(r"(?<![\d.])(\d{1,2})\*?(?![\d.])", day_line))[: len(years)]
    if len(day_matches) != len(years):
        raise ValueError(f"Header has {len(day_matches)} day columns for {len(years)} years.")
    columns = [
        (m.end(1), pd.Timestamp(f"{m.group(1)} {month[:3]} {year}"))
        for m, month, year in zip(day_matches, months[: len(years)], years, strict=True)
    ]
    if [d for _, d in columns] != sorted(d for _, d in columns):
        raise ValueError(f"Column dates are not ascending: {columns}.")

    section = next((i for i, ln in enumerate(lines) if "Treasury bills (secondary market)" in ln), None)
    if section is None:
        raise ValueError("Treasury bill section not found in archived H.15 page.")
    row = next((ln for ln in lines[section:section + 5] if ln.strip().startswith("3-month")), None)
    if row is None:
        raise ValueError("3-month bill row not found in archived H.15 page.")

    values: dict[pd.Timestamp, float | None] = {date: None for _, date in columns}
    for match in re.finditer(r"n\.a\.|-?\d+\.\d+", row):
        distances = [abs(end - match.end()) for end, _ in columns]
        nearest = int(np.argmin(distances))
        if distances[nearest] <= 3 and match.group(0) != "n.a.":
            values[columns[nearest][1]] = float(match.group(0))
    return values


def _next_on_calendar(obs: pd.DatetimeIndex, calendar: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Return the first calendar date strictly after each observation date."""
    return calendar[np.searchsorted(calendar.values, obs.values, side="right")]


def build_daily_publication_calendar(
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    events: pd.DataFrame,
    release_list: pd.DatetimeIndex,
    good_fridays: pd.DatetimeIndex,
) -> pd.DatetimeIndex:
    """Build the publication calendar for the daily-vintage era.

    Starts from the schedule, removes closures, and adds a Good Friday only when ALFRED lists a
    release on that date. Pre-2014 release lists are weekly, so they cannot add one.
    """
    calendar = expected_federal_reserve_business_days(start, end)
    closures = pd.DatetimeIndex(events.loc[events["event_type"] == "no_release_day", "event_date"])
    listed = good_fridays.intersection(release_list[release_list >= pd.Timestamp("2014-04-01")])
    return calendar.difference(closures).union(listed).sort_values()


def build_rf_version_table(
    versions: pd.DataFrame,
    *,
    sparse_calendar: pd.DatetimeIndex,
    daily_calendar: pd.DatetimeIndex,
    schedule_calendar: pd.DatetimeIndex,
    events: pd.DataFrame,
    archived_values: pd.DataFrame | None = None,
    release_time: str = "16:15:00",
    timezone: str = "America/New_York",
    daily_vintage_start: pd.Timestamp = DAILY_VINTAGE_START,
) -> pd.DataFrame:
    """Assign day-level availability and evidence labels to every observation version.

    Rules:
    - Sparse era (first vintage before ``daily_vintage_start``): the first version keeps the
      schedule calendar and is labelled as a fallback.
    - Daily era: ``availability = max(calendar date, vintage date, documented floor)``.
    - Revisions and withdrawals become usable no earlier than their own vintage date.
    - Each version is also held back to its observation's first availability.
    """
    if versions.empty:
        raise ValueError("versions is empty.")
    first_rows = versions.loc[versions["version_seq"] == 0].set_index("obs_date")
    obs_all = pd.DatetimeIndex(first_rows.index)
    release_delta = pd.Timedelta(release_time)

    sparse_next = pd.Series(_next_on_calendar(obs_all, sparse_calendar), index=obs_all)
    daily_next = pd.Series(_next_on_calendar(obs_all, daily_calendar), index=obs_all)
    schedule_next = pd.Series(_next_on_calendar(obs_all, schedule_calendar), index=obs_all)

    floors = events.dropna(subset=["effect_obs_date", "floor_date"]).set_index("effect_obs_date")
    closure_rows = events.loc[events["event_type"] == "no_release_day"].set_index("event_date")

    archived = archived_values.set_index("obs_date") if archived_values is not None else None
    rows: list[dict[str, object]] = []
    first_available: dict[pd.Timestamp, pd.Timestamp] = {}

    for row in versions.itertuples(index=False):
        obs = pd.Timestamp(row.obs_date)
        vintage = pd.Timestamp(row.vintage_date)
        is_first = int(row.version_seq) == 0
        sparse = pd.Timestamp(first_rows.at[obs, "vintage_date"]) < daily_vintage_start

        if sparse:
            calendar_date = sparse_next[obs]
        else:
            calendar_date = daily_next[obs]

        if is_first and sparse:
            date, basis, tier, status = calendar_date, "calendar_fallback_sparse_vintages", "calendar_fallback", "sparse_fallback"
        elif is_first:
            floor = floors["floor_date"].get(obs)
            date = max(calendar_date, vintage)
            basis, tier, status = "calendar_and_vintage_same_day", "vintage_supported", "resolved_day_level"
            if vintage > calendar_date:
                basis, tier = "vintage_later_than_calendar", "inferred"
            elif vintage < calendar_date:
                basis = "calendar_later_than_vintage"
            schedule_date = schedule_next[obs]
            if calendar_date > schedule_date:
                missed = closure_rows.loc[(closure_rows.index >= schedule_date) & (closure_rows.index < calendar_date)]
                kinds = set(missed["classification"])
                if "documented" in kinds:
                    basis, tier = "documented_no_release_day", "documented"
                elif "inferred" in kinds:
                    basis, tier = "inferred_no_release_day", "inferred"
            if floor is not None and pd.Timestamp(floor) >= date:
                date = pd.Timestamp(floor)
                kind = floors.loc[[obs], "classification"].iloc[0]
                if kind == "documented":
                    basis, tier = "documented_omission_floor", "documented"
                else:
                    basis, tier, status = "unresolved_source_conflict_floor", "unresolved", "unresolved"
        else:
            date = max(vintage, first_available[obs])
            kind = "withdrawal" if np.isnan(row.value_pct) else "revision"
            basis = f"{kind}_vintage_date"
            tier = "vintage_supported" if bool(row.exact_vintage) else "inferred"
            status = "resolved_day_level" if bool(row.exact_vintage) else "unresolved"
            if sparse and vintage < daily_vintage_start:
                status = "sparse_fallback"
                tier = "calendar_fallback"

        if is_first:
            first_available[obs] = pd.Timestamp(date)

        if is_first:
            value_basis = "alfred_first_vintage"
            if archived is not None and obs in archived.index:
                value_basis = "fed_archived_weekly_h15"
            elif vintage == versions["vintage_date"].min():
                value_basis = "alfred_earliest_archive_first_release_unverified"
        elif np.isnan(row.value_pct):
            value_basis = "alfred_withdrawal"
        else:
            value_basis = "alfred_revision_vintage"

        available = (pd.Timestamp(date) + release_delta).tz_localize(timezone).tz_convert("UTC")
        rows.append(
            {
                "obs_date": obs,
                "version_seq": int(row.version_seq),
                "version_kind": (
                    "initial" if is_first else ("withdrawal" if np.isnan(row.value_pct) else "revision")
                ),
                "value_pct": float(row.value_pct),
                "vintage_date": vintage,
                "exact_vintage": bool(row.exact_vintage),
                "calendar_date": pd.Timestamp(calendar_date),
                "availability_date": pd.Timestamp(date),
                "available_at_utc": available,
                "availability_basis": basis,
                "value_basis": value_basis,
                "evidence_tier": tier,
                "coverage_status": status,
            }
        )

    table = pd.DataFrame(rows, columns=list(RF_VERSION_TABLE_COLUMNS))
    return table.sort_values(["obs_date", "version_seq"], kind="mergesort").reset_index(drop=True)


def rf_accrual_91d_sensitivity(
    quote_pct: pd.Series,
    price_sessions: pd.DatetimeIndex,
) -> pd.Series:
    """Convert selected discount quotes to a 91-day bill accrual over each session interval.

    ``P = 1 - d * 91 / 360`` and ``r = (1 / P) ** (calendar_days / 91) - 1``. This assumes a fixed
    91-day term and is a conversion sensitivity only, not an exact realized Treasury return.
    """
    sessions = pd.DatetimeIndex(price_sessions).sort_values()
    positions = sessions.get_indexer(quote_pct.index)
    if np.any(positions < 1):
        raise ValueError("Every return date must have a preceding price session.")
    days = pd.Series(
        (quote_pct.index - sessions[positions - 1]).days.astype(float),
        index=quote_pct.index,
    )
    price = 1.0 - (quote_pct.astype(float) / 100.0) * 91.0 / 360.0
    out = (1.0 / price) ** (days / 91.0) - 1.0
    out.name = "rf_daily_accrual_91d_sensitivity"
    return out
