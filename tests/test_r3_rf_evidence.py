"""Focused tests for the RF-only r3 policy: vintage stitching, as-of selection, and snapshot lineage."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from quantedge.config import AppConfig, _validate_raw_config
from quantedge.data import (
    POLICY_REVISION_R2,
    POLICY_REVISION_R3,
    RF_POLICY_R2,
    RF_POLICY_R3,
    DataUnavailableError,
    activate_snapshot,
    load_data,
)
from quantedge.returns import expected_nyse_sessions, select_rf_versions_asof
from quantedge.rf_evidence import (
    VintageColumn,
    VintageResponseError,
    build_rf_version_table,
    frame_to_vintage_columns,
    parse_alfred_vintage_csv,
    parse_weekly_h15_bill_row,
    rf_accrual_91d_sensitivity,
    stitch_vintage_versions,
)

V1_ID = "qe1_20050101_20261030_afb9ce5694"
R2_ID = "qe1_20050101_20261030_r2_cd2904443b"


def _col(vintage: str, values: dict[str, float], lo: str, hi: str) -> VintageColumn:
    series = pd.Series(values, dtype=float)
    series.index = pd.DatetimeIndex(series.index)
    return VintageColumn(pd.Timestamp(vintage), pd.Timestamp(lo), pd.Timestamp(hi), series)


def _version_rows(rows: list[tuple[str, int, float, str]]) -> pd.DataFrame:
    """Build ``(obs, version, value, available New York timestamp)`` rows."""
    table = pd.DataFrame(rows, columns=["obs_date", "version_seq", "value_pct", "available"])
    table["obs_date"] = pd.to_datetime(table["obs_date"])
    table["available_at_utc"] = (
        pd.to_datetime(table.pop("available")).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    )
    return table


def test_vintage_response_requires_exact_requested_identity() -> None:
    """A same-sized response with different vintages is refused, not just a short one."""
    text = "observation_date,DTB3_20080924,DTB3_20081001\n2008-09-22,1.29,1.29\n2008-09-23,,0.81\n"
    frame = parse_alfred_vintage_csv(text, ["2008-09-24", "2008-10-01"])
    assert list(frame.columns) == [pd.Timestamp("2008-09-24"), pd.Timestamp("2008-10-01")]
    assert np.isnan(frame.loc["2008-09-23", pd.Timestamp("2008-09-24")])

    with pytest.raises(VintageResponseError, match="differ from"):
        parse_alfred_vintage_csv(text, ["2008-09-24", "2008-10-02"])
    with pytest.raises(VintageResponseError, match="differ from"):
        parse_alfred_vintage_csv(text, ["2008-09-24", "2008-10-01", "2008-10-02"])
    with pytest.raises(VintageResponseError, match="differ from"):
        parse_alfred_vintage_csv(text, ["2008-10-01", "2008-09-24"])
    with pytest.raises(VintageResponseError, match="Unexpected vintage column"):
        parse_alfred_vintage_csv("observation_date,DTB6_20081001\n2008-09-22,1.29\n")
    with pytest.raises(VintageResponseError, match="not an ALFRED"):
        parse_alfred_vintage_csv("<html>form</html>")


def test_blank_outside_requested_window_is_not_a_withdrawal() -> None:
    """ALFRED's full-history fallback rows are clipped, and blanks outside a window mean nothing."""
    text = (
        "observation_date,DTB3_20180913,DTB3_20180914\n"
        "1954-01-04,1.33,\n2018-09-12,2.10,2.10\n2018-09-13,,2.11\n"
    )
    frame = parse_alfred_vintage_csv(text)
    columns = frame_to_vintage_columns(frame, "2018-09-10", "2018-09-14")
    assert all(pd.Timestamp("1954-01-04") not in c.values.index for c in columns)

    wide = _col("2018-09-13", {"2018-01-02": 1.5, "2018-09-12": 2.10}, "2018-01-01", "2018-09-13")
    narrow = _col("2018-09-14", {"2018-09-12": 2.10, "2018-09-13": 2.11}, "2018-09-01", "2018-09-14")
    versions = stitch_vintage_versions([wide, narrow], ["2018-09-13", "2018-09-14"])
    assert not versions["value_pct"].isna().any()


def test_chunk_boundary_appearance_change_and_withdrawal_are_detected() -> None:
    """Records in a chunk's FIRST vintage are compared with the previous chunk, never discarded."""
    published = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    chunk_a = [
        _col("2024-01-02", {"2024-01-01": 5.00, "2023-12-29": 4.90}, "2023-11-01", "2024-01-03"),
        _col("2024-01-03", {"2024-01-01": 5.00, "2023-12-29": 4.90}, "2023-11-01", "2024-01-03"),
    ]
    chunk_b = [
        # 2024-01-03 first appears exactly in the first vintage of the second request, the
        # 2023-12-29 value changes there, and 2024-01-01 is withdrawn there.
        _col("2024-01-04", {"2024-01-03": 5.10, "2023-12-29": 4.95}, "2023-11-01", "2024-01-05"),
        _col("2024-01-05", {"2024-01-03": 5.10, "2023-12-29": 4.95}, "2023-11-01", "2024-01-05"),
    ]
    versions = stitch_vintage_versions(chunk_b + chunk_a, published).set_index(["obs_date", "version_seq"])

    appeared = versions.loc[(pd.Timestamp("2024-01-03"), 0)]
    assert appeared["vintage_date"] == pd.Timestamp("2024-01-04")
    assert appeared["value_pct"] == 5.10
    assert bool(appeared["exact_vintage"]) is True

    changed = versions.loc[(pd.Timestamp("2023-12-29"), 1)]
    assert changed["vintage_date"] == pd.Timestamp("2024-01-04")
    assert changed["value_pct"] == 4.95

    withdrawn = versions.loc[(pd.Timestamp("2024-01-01"), 1)]
    assert withdrawn["vintage_date"] == pd.Timestamp("2024-01-04")
    assert np.isnan(withdrawn["value_pct"])
    assert len(versions) == 5


def test_stitch_flags_gaps_duplicates_and_conflicts() -> None:
    """A skipped published vintage is inexact; duplicate retrievals must agree."""
    published = ["2024-01-02", "2024-01-03", "2024-01-04"]
    gap = [
        _col("2024-01-02", {"2023-12-29": 4.90}, "2023-11-01", "2024-01-02"),
        _col("2024-01-04", {"2023-12-29": 4.95}, "2023-11-01", "2024-01-04"),
    ]
    versions = stitch_vintage_versions(gap, published)
    revised = versions[versions["version_seq"] == 1].iloc[0]
    assert bool(revised["exact_vintage"]) is False
    assert revised["previous_checked_vintage"] == pd.Timestamp("2024-01-02")

    same = _col("2024-01-02", {"2023-12-29": 4.90}, "2023-12-01", "2024-01-02")
    versions = stitch_vintage_versions(gap[:1] + [same], published)
    assert len(versions) == 1

    conflict = _col("2024-01-02", {"2023-12-29": 4.91}, "2023-12-01", "2024-01-02")
    with pytest.raises(VintageResponseError, match="Conflicting"):
        stitch_vintage_versions(gap[:1] + [conflict], published)
    with pytest.raises(VintageResponseError, match="outside the published list"):
        stitch_vintage_versions(gap, ["2024-01-02"])


def test_late_revision_to_older_observation_cannot_replace_newer_quote() -> None:
    """Selection takes the newest eligible observation, then that observation's eligible version."""
    table = _version_rows(
        [
            ("2024-01-08", 0, 5.00, "2024-01-09 16:15"),
            ("2024-01-09", 0, 5.10, "2024-01-10 16:15"),
            ("2024-01-08", 1, 4.00, "2024-01-11 16:15"),  # late revision of the OLDER observation
            ("2024-01-09", 1, 5.20, "2024-01-12 16:15"),  # revision of the newest observation
        ]
    )
    dates = pd.DatetimeIndex(["2024-01-11", "2024-01-12", "2024-01-15", "2024-01-16"], name="date")
    sessions = pd.DatetimeIndex(["2024-01-10", "2024-01-11", "2024-01-12", "2024-01-15", "2024-01-16"])
    rf, provenance = select_rf_versions_asof(table, dates, price_sessions=sessions)

    # Cutoff 01-10 16:00: only 01-08 is out. Cutoff 01-11 16:00: 01-09 v0.
    assert provenance.loc["2024-01-11", "obs_date"] == pd.Timestamp("2024-01-08")
    assert provenance.loc["2024-01-12", "value_pct"] == 5.10
    # Cutoff 01-12 16:00: the 01-11 16:15 revision of 01-08 is out, yet 01-09 is still selected.
    assert provenance.loc["2024-01-15", "obs_date"] == pd.Timestamp("2024-01-09")
    assert provenance.loc["2024-01-15", "value_pct"] == 5.10
    # Cutoff 01-15 16:00: the 01-09 revision has become eligible.
    assert provenance.loc["2024-01-16", "value_pct"] == 5.20
    assert provenance.loc["2024-01-16", "version_seq"] == 1
    assert np.isclose(rf.loc["2024-01-16"], 0.052 / 252.0, atol=1e-15)


def test_withdrawal_no_backfill_and_future_invariance() -> None:
    """Withdrawn values drop out, nothing backfills, and future versions leave the past unchanged."""
    table = _version_rows(
        [
            ("2024-01-08", 0, 5.00, "2024-01-09 16:15"),
            ("2024-01-09", 0, 5.10, "2024-01-10 16:15"),
            ("2024-01-09", 1, np.nan, "2024-01-11 16:15"),
        ]
    )
    dates = pd.DatetimeIndex(["2024-01-10", "2024-01-11", "2024-01-12", "2024-01-15"], name="date")
    sessions = pd.DatetimeIndex(["2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12", "2024-01-15"])
    rf, provenance = select_rf_versions_asof(table, dates, price_sessions=sessions)

    assert np.isnan(rf.loc["2024-01-10"])  # cutoff 01-09 16:00 precedes every version
    assert provenance.loc["2024-01-12", "value_pct"] == 5.10
    assert provenance.loc["2024-01-15", "value_pct"] == 5.00  # withdrawal reverts to 01-08

    future = pd.concat(
        [table, _version_rows([("2024-01-12", 0, 99.0, "2024-01-15 16:15"), ("2024-01-08", 1, 77.0, "2024-01-16 09:00")])],
        ignore_index=True,
    )
    rf_future, _ = select_rf_versions_asof(future, dates, price_sessions=sessions)
    pd.testing.assert_series_equal(rf, rf_future)

    naive = table.copy()
    naive["available_at_utc"] = naive["available_at_utc"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        select_rf_versions_asof(naive, dates, price_sessions=sessions)


def test_release_after_close_is_excluded_on_both_sides_of_dst() -> None:
    """Available 16:15 New York stays after a 16:00 cutoff in EST and EDT; 15:59 is before it."""
    for day, next_day in (("2024-01-16", "2024-01-17"), ("2024-07-16", "2024-07-17")):
        table = _version_rows([("2024-01-02", 0, 1.0, "2024-01-03 16:15"), ("2024-07-01", 0, 1.0, "2024-07-02 16:15")])
        late = _version_rows([(day, 0, 7.0, f"{day} 16:15")])
        early = _version_rows([(day, 0, 7.0, f"{day} 15:59")])
        dates = pd.DatetimeIndex([next_day], name="date")
        sessions = pd.DatetimeIndex([day, next_day])
        rf_late, _ = select_rf_versions_asof(pd.concat([table, late], ignore_index=True), dates, price_sessions=sessions)
        rf_early, _ = select_rf_versions_asof(pd.concat([table, early], ignore_index=True), dates, price_sessions=sessions)
        assert np.isclose(rf_late.iloc[0], 0.01 / 252.0, atol=1e-15)
        assert np.isclose(rf_early.iloc[0], 0.07 / 252.0, atol=1e-15)


def _table_inputs() -> dict[str, object]:
    events = pd.DataFrame(
        [
            ("2015-03-05", "no_release_day", "documented", None, None),
            ("2017-01-20", "no_release_day", "inferred", None, None),
            ("2018-09-18", "omitted_treasury_data", "documented", "2018-09-17", "2018-09-19"),
            ("2025-12-24", "release_conflict", "unresolved", "2025-12-23", "2025-12-29"),
        ],
        columns=["event_date", "event_type", "classification", "effect_obs_date", "floor_date"],
    )
    for column in ("event_date", "effect_obs_date", "floor_date"):
        events[column] = pd.to_datetime(events[column])
    schedule = pd.bdate_range("2005-01-03", "2026-12-31")
    closures = pd.DatetimeIndex(events.loc[events["event_type"] == "no_release_day", "event_date"])
    return {
        "sparse_calendar": schedule,
        "daily_calendar": schedule.difference(closures),
        "schedule_calendar": schedule,
        "events": events,
    }


def _version_input(rows: list[tuple[str, int, float, str, bool]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["obs_date", "version_seq", "value_pct", "vintage_date", "exact_vintage"])
    frame["obs_date"] = pd.to_datetime(frame["obs_date"])
    frame["vintage_date"] = pd.to_datetime(frame["vintage_date"])
    frame["previous_checked_vintage"] = pd.NaT
    return frame


def test_version_table_labels_and_sparse_fallback() -> None:
    """Sparse history keeps the calendar and each evidence class stays separately labelled."""
    table = build_rf_version_table(
        _version_input(
            [
                ("2005-01-07", 0, 2.29, "2005-06-28", True),
                ("2005-01-07", 1, 2.28, "2017-11-14", True),
                ("2005-09-01", 0, 3.45, "2005-09-06", True),
                ("2015-03-04", 0, 0.01, "2015-03-06", True),
                ("2017-01-19", 0, 0.51, "2017-01-23", True),
                ("2018-09-17", 0, 2.13, "2018-09-19", True),
                ("2020-02-03", 0, 1.50, "2020-02-04", True),
                ("2009-06-01", 0, 0.14, "2009-06-03", True),
                ("2025-12-23", 0, 3.56, "2025-12-29", True),
            ]
        ),
        **_table_inputs(),
    ).set_index(["obs_date", "version_seq"])

    def row(obs: str, seq: int = 0) -> pd.Series:
        return table.loc[(pd.Timestamp(obs), seq)]

    # Never delayed to the June 2005 first vintage, or to a weekly-era vintage.
    assert row("2005-01-07")["availability_date"] == pd.Timestamp("2005-01-10")
    assert row("2005-01-07")["coverage_status"] == "sparse_fallback"
    assert row("2005-09-01")["availability_date"] == pd.Timestamp("2005-09-02")
    assert row("2005-09-01")["evidence_tier"] == "calendar_fallback"

    # The 2017 correction is not usable before its own vintage date.
    assert row("2005-01-07", 1)["availability_date"] == pd.Timestamp("2017-11-14")
    assert row("2005-01-07", 1)["version_kind"] == "revision"

    assert row("2015-03-04")["availability_date"] == pd.Timestamp("2015-03-06")
    assert row("2015-03-04")["availability_basis"] == "documented_no_release_day"
    assert row("2015-03-04")["evidence_tier"] == "documented"
    assert row("2017-01-19")["availability_basis"] == "inferred_no_release_day"
    assert row("2018-09-17")["availability_basis"] == "documented_omission_floor"
    assert row("2018-09-17")["evidence_tier"] == "documented"
    assert row("2020-02-03")["availability_basis"] == "calendar_and_vintage_same_day"
    assert row("2020-02-03")["evidence_tier"] == "vintage_supported"
    # A later vintage alone is an inference, not proof of a late release.
    assert row("2009-06-01")["availability_date"] == pd.Timestamp("2009-06-03")
    assert row("2009-06-01")["evidence_tier"] == "inferred"
    assert row("2025-12-23")["evidence_tier"] == "unresolved"
    assert row("2025-12-23")["coverage_status"] == "unresolved"

    available = row("2020-02-03")["available_at_utc"]
    assert available == pd.Timestamp("2020-02-04 16:15", tz="America/New_York").tz_convert("UTC")


def test_documented_closure_keeps_its_label_when_a_vintage_is_later_still() -> None:
    """A later vintage sets the date but must not relabel a documented closure as an inference."""
    row = build_rf_version_table(
        _version_input([("2015-03-04", 0, 0.01, "2015-03-09", True)]),
        **_table_inputs(),
    ).iloc[0]
    assert row["availability_date"] == pd.Timestamp("2015-03-09")
    assert row["availability_basis"] == "documented_no_release_day"
    assert row["evidence_tier"] == "documented"


def test_inferred_no_release_day_is_not_labelled_documented() -> None:
    """An absent ALFRED release stays inferred even when the calendar moves the date."""
    table = build_rf_version_table(
        _version_input([("2017-01-19", 0, 0.51, "2017-01-21", True)]),
        **_table_inputs(),
    ).iloc[0]
    assert table["availability_date"] == pd.Timestamp("2017-01-23")
    assert table["availability_basis"] == "inferred_no_release_day"
    assert table["evidence_tier"] == "inferred"


def test_weekly_h15_row_parser_uses_column_position_in_holiday_weeks() -> None:
    """A blank holiday column never shifts values; ``n.a.`` stays missing; paper rows are skipped."""
    text = "\n".join(
        [
            "                                                        *",
            "                                                    2005    2005    2005    2005    2005     Week Ending    2005",
            "                                                     Jul     Jul     Jul     Jul     Jul     Jul     Jul     Jun",
            "        Instruments                                    4       5       6       7       8       8       1",
            "        Commercial paper",
            "                3-month                             2.90    2.91    2.92    2.93    2.94    2.95    2.96",
            "            Treasury bills (secondary market) 3 4",
            "                4-week                                      2.96    2.99    2.94    2.93    2.96    2.90",
            "                3-month                                     3.15    n.a.    3.08    3.10    3.11    3.08",
        ]
    )
    assert parse_weekly_h15_bill_row(text) == {
        pd.Timestamp("2005-07-04"): None,
        pd.Timestamp("2005-07-05"): 3.15,
        pd.Timestamp("2005-07-06"): None,
        pd.Timestamp("2005-07-07"): 3.08,
        pd.Timestamp("2005-07-08"): 3.10,
    }
    with pytest.raises(ValueError, match="header not found"):
        parse_weekly_h15_bill_row("Federal funds 2.79")


def test_accrual_sensitivity_uses_calendar_days_on_selected_quotes() -> None:
    """A Friday-to-Monday interval accrues three calendar days on a 91-day bill."""
    sessions = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-08"])
    quotes = pd.Series([5.0, 5.0], index=sessions[1:])
    accrual = rf_accrual_91d_sensitivity(quotes, sessions)
    price = 1.0 - 0.05 * 91.0 / 360.0
    assert np.isclose(accrual.iloc[0], (1.0 / price) ** (1.0 / 91.0) - 1.0, atol=1e-15)
    assert np.isclose(accrual.iloc[1], (1.0 / price) ** (3.0 / 91.0) - 1.0, atol=1e-15)
    assert accrual.name == "rf_daily_accrual_91d_sensitivity"


@pytest.fixture(scope="module")
def r3_bundle() -> object:
    """Load the real r3 snapshot through the normal offline path."""
    repo_root = Path(__file__).resolve().parents[1]
    return load_data(repo_root / "config.yaml", offline=True, repo_root=repo_root)


def _quote(bundle: object, day: str) -> tuple[pd.Timestamp, float]:
    row = bundle.rf_provenance.loc[day]
    return row["obs_date"], float(row["value_pct"])


def test_real_r3_prices_returns_equal_r2_and_old_hashes_preserved(r3_bundle: object, repo_root: Path) -> None:
    """Prices and returns equal r2 exactly, and v1/r2 stay bit-for-bit intact."""
    processed = repo_root / "data" / "processed"
    m = r3_bundle.manifest
    assert m.policy_revision == POLICY_REVISION_R3
    assert m.parent_dataset_id == R2_ID
    assert "_r3_" in m.dataset_id
    for name, frame in (
        ("prices", r3_bundle.prices),
        ("simple_returns", r3_bundle.simple_returns),
        ("log_returns", r3_bundle.log_returns),
    ):
        parent = pd.read_parquet(processed / R2_ID / f"{name}.parquet")
        pd.testing.assert_frame_equal(frame, parent, check_exact=True)
    assert bundle_rf_is_complete(r3_bundle)

    for dataset, expected in ((V1_ID, 13), (R2_ID, 15)):
        manifest = json.loads((processed / dataset / "manifest.json").read_text(encoding="utf-8"))
        assert len(manifest["file_sha256"]) == expected
        for rel_key, digest in manifest["file_sha256"].items():
            assert hashlib.sha256((repo_root / rel_key).read_bytes()).hexdigest() == digest


def bundle_rf_is_complete(bundle: object) -> bool:
    return not bool(bundle.rf_daily.isna().any()) and bundle.rf_provenance.index.equals(bundle.simple_returns.index)


def test_real_r3_documented_and_inferred_cases(r3_bundle: object) -> None:
    """Closure, omission, and Good Friday sessions select the evidence-supported observation."""
    assert _quote(r3_bundle, "2015-03-09") == (pd.Timestamp("2015-03-03"), 0.02)
    assert _quote(r3_bundle, "2016-01-28") == (pd.Timestamp("2016-01-20"), 0.26)
    assert _quote(r3_bundle, "2019-02-22") == (pd.Timestamp("2019-02-15"), 2.38)
    assert _quote(r3_bundle, "2021-04-06") == (pd.Timestamp("2021-04-01"), 0.02)

    versions = pd.read_parquet(
        Path(__file__).resolve().parents[1]
        / "data" / "raw" / r3_bundle.manifest.dataset_id / "dtb3_rf_versions.parquet"
    ).set_index(["obs_date", "version_seq"])

    def day(obs: str) -> pd.Timestamp:
        return versions.loc[(pd.Timestamp(obs), 0), "availability_date"]

    assert day("2018-09-17") == pd.Timestamp("2018-09-19")
    assert day("2020-08-19") == pd.Timestamp("2020-08-26")
    assert day("2023-08-01") == pd.Timestamp("2023-08-03")
    assert day("2023-09-12") == pd.Timestamp("2023-09-14")
    assert day("2023-11-09") >= pd.Timestamp("2023-11-13")  # no release on the 2023-11-10 holiday
    assert versions.loc[(pd.Timestamp("2025-12-23"), 0), "evidence_tier"] == "unresolved"
    assert versions.loc[(pd.Timestamp("2015-03-04"), 0), "evidence_tier"] == "documented"
    for obs, tier in (("2017-01-19", "inferred"), ("2018-03-01", "inferred")):
        assert versions.loc[(pd.Timestamp(obs), 0), "evidence_tier"] == tier


def test_real_r3_january_2005_uses_original_value(r3_bundle: object) -> None:
    """2005 decisions use the archived 2.29, never the correction published in 2017."""
    obs, value = _quote(r3_bundle, "2005-01-12")
    assert obs == pd.Timestamp("2005-01-07")
    assert value == 2.29
    assert np.isclose(r3_bundle.rf_daily.loc["2005-01-12"], 0.0229 / 252.0, atol=1e-15)
    assert r3_bundle.rf_provenance.loc["2005-01-12", "version_seq"] == 0
    assert r3_bundle.rf_provenance.loc["2005-01-12", "coverage_status"] == "sparse_fallback"

    versions = pd.read_parquet(
        Path(__file__).resolve().parents[1]
        / "data" / "raw" / r3_bundle.manifest.dataset_id / "dtb3_rf_versions.parquet"
    )
    history = versions[versions["obs_date"] == pd.Timestamp("2005-01-07")].sort_values("version_seq")
    assert history["value_pct"].tolist() == [2.29, 2.28]
    assert history.iloc[0]["value_basis"] == "fed_archived_weekly_h15"
    assert history.iloc[1]["availability_date"] >= pd.Timestamp("2017-11-13")


def test_real_r3_no_staleness_jump_in_sparse_era(r3_bundle: object) -> None:
    """Early sessions follow the calendar fallback rather than waiting for June 2005."""
    early = r3_bundle.rf_provenance.loc["2005-01-04":"2006-02-22"]
    assert set(early["coverage_status"]) == {"sparse_fallback"}
    gap = (early.index.to_series() - early["obs_date"]).dt.days
    assert int(gap.max()) <= 7


def test_real_r3_selection_is_causal_and_provenance_is_consistent(r3_bundle: object) -> None:
    """Every selected version was available by its cutoff and reproduces the stored RF."""
    p = r3_bundle.rf_provenance
    assert bool((p["available_at_utc"] <= p["decision_time_utc"]).all())
    assert bool((p["obs_date"] < p.index).all())
    np.testing.assert_allclose(p["value_pct"].to_numpy() / 25200.0, r3_bundle.rf_daily.to_numpy(), rtol=0, atol=1e-16)
    assert r3_bundle.rf_accrual_sensitivity is not None
    assert r3_bundle.rf_accrual_sensitivity.index.equals(r3_bundle.rf_daily.index)
    assert r3_bundle.manifest.rf_convention["conversion_formula"] == "(rate_pct / 100.0) / 252"
    assert "not an exact realized" in r3_bundle.manifest.rf_convention["accrual_sensitivity_note"]
    assert "intraday" in r3_bundle.manifest.rf_convention["limitation_note"]


def _config_dict(repo_root: Path) -> dict:
    return copy.deepcopy(yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8")))


def test_r2_and_r3_caches_are_isolated(r3_bundle: object, repo_root: Path) -> None:
    """Each policy resolves to its own snapshot, and changed evidence never reuses r3."""
    raw_cfg = _config_dict(repo_root)
    raw_cfg["data"]["rf_alignment_policy"] = RF_POLICY_R2
    r2_cfg: AppConfig = _validate_raw_config(raw_cfg)
    r2_bundle = load_data(r2_cfg, offline=True, repo_root=repo_root)
    assert r2_bundle.manifest.dataset_id == R2_ID
    assert r2_bundle.manifest.policy_revision == POLICY_REVISION_R2
    assert r2_bundle.rf_provenance is None
    assert r3_bundle.manifest.rf_convention["alignment_policy"] == RF_POLICY_R3
    assert r3_bundle.manifest.rf_convention["evidence_sha256"]
    assert not r2_bundle.rf_daily.equals(r3_bundle.rf_daily)

    changed = _config_dict(repo_root)
    changed["data"]["rf_evidence_sha256"] = "0" * 64
    with pytest.raises(DataUnavailableError, match="Offline mode"):
        load_data(_validate_raw_config(changed), offline=True, repo_root=repo_root)

    missing = _config_dict(repo_root)
    missing["data"]["rf_evidence_sha256"] = None
    with pytest.raises(ValueError, match="rf_evidence_sha256"):
        _validate_raw_config(missing)


def test_activation_refuses_snapshot_other_than_configured_policy(r3_bundle: object, repo_root: Path) -> None:
    """A snapshot the configured policy does not resolve to cannot become active."""
    pointer = repo_root / "data" / "processed" / "active_snapshot.json"
    before = pointer.read_bytes()
    with pytest.raises(DataUnavailableError, match="resolves to"):
        activate_snapshot(repo_root / "config.yaml", dataset_id=R2_ID, repo_root=repo_root)
    assert pointer.read_bytes() == before


def test_expected_sessions_cover_r3_returns(r3_bundle: object) -> None:
    """The r3 RF index stays on expected NYSE sessions."""
    sessions = expected_nyse_sessions("2005-01-03", "2026-10-30")
    assert r3_bundle.rf_daily.index.isin(sessions).all()
