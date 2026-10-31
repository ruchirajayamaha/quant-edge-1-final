"""Focused synthetic and snapshot-integrity tests for SOLO STEP 2 (milestone A1).

Covers:
1. NYSE session calendar rules (including Rule 7.2 Saturday New Year, Juneteenth >= 2022,
   and documented special closures).
2. yfinance auto_adjust=True MultiIndex extraction and raw/adjusted mix rejection.
3. One-session simple & log return calculation BEFORE incomplete-row exclusion (no price
   forward-fill, no artificial first-day zero, no multi-session gap bridging).
4. FRED DTB3 CSV parsing, fractional (rate/100)/252 units, lag-1 past-only alignment,
   zero initial backfill, and future-perturbation invariance.
5. Quality flagging (stale runs, robust-MAD jumps with safe MAD=0 handling, large negatives,
   candidate structural breaks) retaining all valid return rows.
6. ADF stationarity diagnostics and degenerate-series edge cases.
7. Offline cache round-trip, network-failure fallback banner, and SHA-256 tamper detection.
8. Real repository market-data snapshot integrity.
"""

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
from quantedge.contracts import CANONICAL_TICKERS, QUALITY_FLAG_COLUMNS
from quantedge.data import (
    RF_POLICY_R2,
    DataUnavailableError,
    build_session_price_grid,
    extract_adjusted_closes,
    flag_data_quality,
    load_data,
    parse_fred_dtb3_csv,
)
from quantedge.returns import (
    align_risk_free_rate,
    compute_session_returns,
    expected_federal_reserve_business_days,
    expected_nyse_sessions,
    run_stationarity_diagnostics,
)


def _make_synthetic_prices(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Create strictly positive deterministic 7-ETF prices across ``dates``."""
    n = len(dates)
    rng = np.random.default_rng(20260131)
    cols: dict[str, np.ndarray] = {}
    for idx, ticker in enumerate(CANONICAL_TICKERS):
        steps = rng.normal(loc=0.0002 * (idx + 1), scale=0.006 + 0.001 * idx, size=n)
        steps[0] = 0.0
        cols[ticker] = 100.0 * np.cumprod(1.0 + steps)
    return pd.DataFrame(cols, index=dates)


def test_nyse_calendar_known_holidays_and_special_closures() -> None:
    """NYSE calendar handles Rule 7.2 Dec 31, Juneteenth start year, and special closures."""
    cal = expected_nyse_sessions("2004-12-30", "2025-01-15")

    # NYSE Rule 7.2: when Jan 1 is Saturday (2005, 2011, 2022), preceding Friday Dec 31 is OPEN
    assert pd.Timestamp("2004-12-31") in cal
    assert pd.Timestamp("2010-12-31") in cal
    assert pd.Timestamp("2021-12-31") in cal

    # Sunday Jan 1 observed on Monday Jan 2 (2006, 2023)
    assert pd.Timestamp("2006-01-02") not in cal
    assert pd.Timestamp("2023-01-02") not in cal

    # Juneteenth: NYSE was OPEN on Friday 2021-06-18 and CLOSED starting in 2022 (2022-06-20)
    assert pd.Timestamp("2021-06-18") in cal
    assert pd.Timestamp("2022-06-20") not in cal

    # Documented unplanned / mourning NYSE closures
    assert pd.Timestamp("2007-01-02") not in cal  # Ford mourning
    assert pd.Timestamp("2012-10-29") not in cal  # Hurricane Sandy
    assert pd.Timestamp("2012-10-30") not in cal  # Hurricane Sandy
    assert pd.Timestamp("2018-12-05") not in cal  # G.H.W. Bush mourning
    assert pd.Timestamp("2025-01-09") not in cal  # Jimmy Carter mourning


def test_extract_adjusted_closes_multiindex_shapes_and_raw_mix_rejection() -> None:
    """Handles group_by='column' and 'ticker', tz normalization, and rejects Adj Close/Close mix."""
    tz_dates = pd.DatetimeIndex(
        [
            "2024-01-02 00:00:00-05:00",
            "2024-01-03 00:00:00-05:00",
            "2024-01-04 00:00:00-05:00",
        ]
    )
    base = _make_synthetic_prices(pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]))

    # 1. group_by='column' MultiIndex: (Field, Ticker)
    col_tuples = []
    col_arrays = []
    for field in ("Close", "Volume"):
        for ticker in reversed(CANONICAL_TICKERS):  # shuffled ticker order to verify canonical ordering
            col_tuples.append((field, ticker))
            vals = base[ticker].to_numpy() if field == "Close" else np.full(3, 1_000_000.0)
            col_arrays.append(vals)
    mi_col = pd.DataFrame(
        np.column_stack(col_arrays),
        index=tz_dates,
        columns=pd.MultiIndex.from_tuples(col_tuples),
    )
    extracted_1 = extract_adjusted_closes(mi_col)
    assert tuple(extracted_1.columns) == CANONICAL_TICKERS
    assert extracted_1.index.tz is None
    pd.testing.assert_frame_equal(extracted_1, base, check_names=False, check_freq=False)

    # 2. group_by='ticker' MultiIndex: (Ticker, Field)
    tkr_tuples = []
    tkr_arrays = []
    for ticker in CANONICAL_TICKERS:
        for field in ("Open", "Close"):
            tkr_tuples.append((ticker, field))
            tkr_arrays.append(base[ticker].to_numpy())
    mi_tkr = pd.DataFrame(
        np.column_stack(tkr_arrays),
        index=tz_dates,
        columns=pd.MultiIndex.from_tuples(tkr_tuples),
    )
    extracted_2 = extract_adjusted_closes(mi_tkr)
    pd.testing.assert_frame_equal(extracted_2, base, check_names=False, check_freq=False)

    # 3. Ambiguous auto_adjust=False frame with BOTH 'Close' and 'Adj Close' MUST fail
    ambig_tuples = [("Close", t) for t in CANONICAL_TICKERS] + [
        ("Adj Close", t) for t in CANONICAL_TICKERS
    ]
    ambig_df = pd.DataFrame(
        np.ones((3, len(ambig_tuples))) * 100.0,
        index=tz_dates,
        columns=pd.MultiIndex.from_tuples(ambig_tuples),
    )
    with pytest.raises(ValueError, match="Adj Close"):
        extract_adjusted_closes(ambig_df)

    # 4. Non-positive price MUST fail
    bad_neg = base.copy()
    bad_neg.iloc[1, 0] = 0.0
    with pytest.raises(ValueError, match="positive"):
        extract_adjusted_closes(bad_neg)

    # 5. Completely failed all-NaN ticker MUST raise DataUnavailableError
    bad_nan = base.copy()
    bad_nan["GLD"] = np.nan
    with pytest.raises(DataUnavailableError, match="GLD"):
        extract_adjusted_closes(bad_nan)


def test_session_returns_single_ticker_gap_invalidates_both_adjacent_returns() -> None:
    """Missing price at t invalidates BOTH t-1->t and t->t+1 without bridging or ffill."""
    sessions = expected_nyse_sessions("2024-01-02", "2024-01-08")  # 5 sessions: Jan 2,3,4,5,8
    assert len(sessions) == 5
    prices = _make_synthetic_prices(sessions)

    # Set hand-computable trajectory on EEM with a missing price on session index 2 (2024-01-04)
    prices["EEM"] = [100.0, 102.0, np.nan, 105.0, 106.05]

    simple_ret, log_ret, excluded = compute_session_returns(prices)

    # Anchor date 2024-01-02 is NOT in returns (no artificial 0.0);
    # 2024-01-04 (t) AND 2024-01-05 (t+1) MUST BOTH be excluded!
    expected_valid_dates = pd.DatetimeIndex(["2024-01-03", "2024-01-08"], name="date")
    pd.testing.assert_index_equal(simple_ret.index, expected_valid_dates)
    pd.testing.assert_index_equal(log_ret.index, expected_valid_dates)

    assert np.isclose(simple_ret.loc["2024-01-03", "EEM"], 0.02, atol=1e-12)
    assert np.isclose(simple_ret.loc["2024-01-08", "EEM"], 0.01, atol=1e-12)
    np.testing.assert_allclose(log_ret.to_numpy(), np.log1p(simple_ret.to_numpy()), rtol=0, atol=1e-14)

    assert len(excluded) == 2
    assert list(excluded["date"]) == [pd.Timestamp("2024-01-04"), pd.Timestamp("2024-01-05")]
    assert list(excluded["reason"]) == ["missing_price_at_t", "missing_price_at_t_minus_1"]
    assert simple_ret.attrs["uninterrupted_sessions"] is False
    assert simple_ret.attrs["n_excluded_return_rows"] == 2


def test_session_grid_detects_missing_nyse_session_across_all_tickers() -> None:
    """Dropping an entire NYSE trading day from raw vendor data does NOT create a fake 1-day return."""
    full_sessions = expected_nyse_sessions("2024-01-02", "2024-01-08")
    vendor_prices = _make_synthetic_prices(full_sessions).drop(index=pd.Timestamp("2024-01-04"))

    grid_prices, missing_expected, unexpected_obs = build_session_price_grid(vendor_prices)
    assert list(missing_expected) == [pd.Timestamp("2024-01-04")]
    assert len(unexpected_obs) == 0
    assert pd.Timestamp("2024-01-04") in grid_prices.index
    assert bool(grid_prices.loc["2024-01-04"].isna().all())

    simple_ret, _, excluded = compute_session_returns(grid_prices)
    assert list(simple_ret.index) == [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-08")]
    assert len(excluded) == 2


def test_past_only_rf_alignment_lag_units_and_no_backfill() -> None:
    """FRED DTB3 uses (rate/100)/252 units, enforces 16:15 ET H.15 <= prev 16:00 ET close, and NEVER backfills."""
    fred_csv = "\n".join(
        [
            "observation_date,DTB3",
            "2024-01-03,5.04",
            "2024-01-04,5.166",
            "2024-01-05,.",
            "2024-01-08,5.292",
        ]
    )
    parsed = parse_fred_dtb3_csv(fred_csv)
    assert parsed.loc["2024-01-05", "raw_value"] == "."
    assert np.isnan(parsed.loc["2024-01-05", "rate_annual_pct"])

    return_dates = pd.DatetimeIndex(
        [
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-08",
            "2024-01-09",
            "2024-01-10",
            "2024-01-11",
        ],
        name="date",
    )
    rf = align_risk_free_rate(
        parsed["rate_annual_pct"],
        return_dates,
        availability_lag_sessions=1,
        trading_days_per_year=252,
    )

    # 2024-01-03 quote (5.04%) posts on Thu 2024-01-04 at 16:15 EST, which is AFTER
    # Thu 2024-01-04 16:00 EST (the decision cutoff for return date Fri 2024-01-05!).
    # Therefore 2024-01-03, 2024-01-04, AND 2024-01-05 remain NaN with zero backfill!
    assert np.isnan(rf.loc["2024-01-03"])
    assert np.isnan(rf.loc["2024-01-04"])
    assert np.isnan(rf.loc["2024-01-05"])

    # For Mon 2024-01-08 (decision_time = Fri 2024-01-05 16:00 EST):
    # - 2024-01-03 (5.04% -> 0.0002) posted Thu 2024-01-04 16:15 EST <= Fri 16:00 EST -> available!
    # - 2024-01-04 (5.166% -> 0.000205) posted Fri 2024-01-05 16:15 EST > Fri 16:00 EST -> excluded!
    assert np.isclose(rf.loc["2024-01-08"], 0.0002, atol=1e-15)

    # Because 2024-01-05 is '.' (explicit holiday/non-publication marker in the feed),
    # 2024-01-04 (5.166% -> 0.000205) does not publish until Mon 2024-01-08 16:15 EST (> Mon 16:00 EST).
    # Thus Tue 2024-01-09 (decision_time = Mon 2024-01-08 16:00 EST) still uses 0.0002,
    # Wed 2024-01-10 (decision_time = Tue 2024-01-09 16:00 EST) uses 0.000205,
    # and Thu 2024-01-11 (decision_time = Wed 2024-01-10 16:00 EST) uses Mon's 5.292% -> 0.00021!
    assert np.isclose(rf.loc["2024-01-09"], 0.0002, atol=1e-15)
    assert np.isclose(rf.loc["2024-01-10"], 0.000205, atol=1e-15)
    assert np.isclose(rf.loc["2024-01-11"], 0.00021, atol=1e-15)

    # Future perturbation invariance check: altering 2024-01-08 quote cannot affect <= 2024-01-10
    perturbed = parsed["rate_annual_pct"].copy()
    perturbed.loc[pd.Timestamp("2024-01-08")] = 99.0
    rf_perturbed = align_risk_free_rate(
        perturbed,
        return_dates,
        availability_lag_sessions=1,
        trading_days_per_year=252,
    )
    pd.testing.assert_series_equal(rf.iloc[:6], rf_perturbed.iloc[:6])


def test_quality_flags_retain_all_returns_and_handle_zero_mad_safely() -> None:
    """MAD==0 series never divide by zero, flags match schema, and flagged returns stay retained."""
    n_sessions = 340
    sessions = pd.bdate_range("2022-01-03", periods=n_sessions)
    rng = np.random.default_rng(202602)

    ret_data: dict[str, np.ndarray] = {}
    for ticker in CANONICAL_TICKERS:
        ret_data[ticker] = rng.normal(0.0003, 0.008, size=n_sessions)

    # SPY: completely flat zero returns (MAD == 0, IQR == 0, std == 0)
    ret_data["SPY"] = np.zeros(n_sessions, dtype=float)

    # AGG: mostly zero returns (MAD == 0, IQR == 0) with one -12% crash spike (std > 0)
    agg_arr = np.zeros(n_sessions, dtype=float)
    agg_arr[150] = -0.12
    ret_data["AGG"] = agg_arr

    # XLK: volatility regime shift (260 days at 0.25% vol -> 80 days at 1.50% vol, ~6x jump)
    xlk_low = rng.normal(0.0, 0.0025, size=260)
    xlk_high = rng.normal(0.0, 0.0150, size=n_sessions - 260)
    ret_data["XLK"] = np.concatenate([xlk_low, xlk_high])

    simple_ret = pd.DataFrame(ret_data, index=sessions)
    log_ret = pd.DataFrame(np.log1p(simple_ret.to_numpy()), index=sessions, columns=CANONICAL_TICKERS)

    # Reconstruct matching synthetic prices (n_sessions + 1 rows)
    anchor_date = pd.DatetimeIndex([sessions[0] - pd.offsets.BDay(1)])
    price_idx = anchor_date.append(sessions)
    price_vals = np.vstack([np.ones((1, len(CANONICAL_TICKERS))), np.cumprod(1.0 + simple_ret.to_numpy(), axis=0)]) * 100.0
    prices = pd.DataFrame(price_vals, index=price_idx, columns=CANONICAL_TICKERS)
    rf_daily = pd.Series(0.00015, index=sessions, name="rf_daily")

    simple_before = simple_ret.copy()
    flags = flag_data_quality(prices, simple_ret, log_ret, rf_daily)

    assert tuple(flags.columns) == QUALITY_FLAG_COLUMNS
    # Flagging MUST NOT mutate or drop any return observation
    pd.testing.assert_frame_equal(simple_ret, simple_before)

    # SPY all-zero series: stale_flat_return_run triggered, zero robust_mad_jump crashes or false positives
    spy_rules = set(flags.loc[flags["ticker"] == "SPY", "rule"])
    assert "stale_flat_return_run" in spy_rules
    assert "robust_mad_jump" not in spy_rules

    # AGG mostly-zero + -12% spike: MAD==0 fallback catches both robust_mad_jump and large_negative_return
    agg_spike_flags = flags.loc[(flags["ticker"] == "AGG") & (flags["date"] == sessions[150])]
    assert {"robust_mad_jump", "large_negative_return"}.issubset(set(agg_spike_flags["rule"]))
    assert set(agg_spike_flags["action"]) == {"retain"}

    # XLK regime jump: candidate_structural_break flagged with action='retain'
    xlk_breaks = flags.loc[(flags["ticker"] == "XLK") & (flags["rule"] == "candidate_structural_break")]
    assert len(xlk_breaks) >= 1
    assert set(xlk_breaks["action"]) == {"retain"}


def test_stationarity_diagnostics_and_edge_cases() -> None:
    """ADF rejects unit root on stationary noise with non-i.i.d. note and handles degenerate inputs."""
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2020-01-01", periods=400)
    stationary = pd.Series(rng.normal(0.0, 0.01, size=400), index=idx)
    short_series = pd.Series([0.01, -0.01, 0.005], index=idx[:3])
    const_series = pd.Series(np.zeros(100), index=idx[:100])

    diag = run_stationarity_diagnostics(
        {
            "stationary_log_ret": stationary,
            "too_short": short_series,
            "constant": const_series,
        }
    ).set_index("series")

    assert diag.loc["stationary_log_ret", "status"] == "ok"
    assert bool(diag.loc["stationary_log_ret", "reject_unit_root_5pct"]) is True
    assert "does NOT imply i.i.d." in str(diag.loc["stationary_log_ret", "note"])

    assert diag.loc["too_short", "status"] == "unavailable"
    assert diag.loc["constant", "status"] == "unavailable"


def test_offline_cache_roundtrip_network_fallback_and_sha256_tamper_rejection(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """load_data handles absent cache, SHA-256 verified cache reuse, network fallback, and tampering."""
    raw_cfg = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))
    test_cfg_dict = copy.deepcopy(raw_cfg)
    test_cfg_dict["data"]["rf_alignment_policy"] = RF_POLICY_R2
    test_cfg_dict["data"]["requested_start"] = "2024-01-02"
    test_cfg_dict["data"]["frozen_end_date"] = None
    test_cfg_dict["data"]["raw_dir"] = str(tmp_path / "data" / "raw")
    test_cfg_dict["data"]["processed_dir"] = str(tmp_path / "data" / "processed")
    test_cfg = _validate_raw_config(test_cfg_dict)

    # 1. Absent cache in offline mode -> explicit DataUnavailableError
    with pytest.raises(DataUnavailableError, match="Offline mode"):
        load_data(test_cfg, offline=True, repo_root=tmp_path)

    # 2. Mock live download once -> persists verified snapshot
    sessions = expected_nyse_sessions("2024-01-02", "2024-03-15")
    synth_prices = _make_synthetic_prices(sessions)
    synth_rf_csv = "observation_date,DTB3\n2023-12-29,5.25\n2024-02-01,5.30\n"
    synth_rf = parse_fred_dtb3_csv(synth_rf_csv)

    monkeypatch.setattr("quantedge.data._download_etf_adjusted_closes", lambda cfg: synth_prices)
    monkeypatch.setattr("quantedge.data._download_fred_dtb3", lambda cfg: synth_rf)

    created = load_data(test_cfg, offline=False, repo_root=tmp_path)
    assert created.manifest.offline_cache_used is False
    assert len(created.manifest.file_sha256) >= 11

    # 3. Offline load succeeds with zero network access
    def _fail_network(cfg: AppConfig) -> pd.DataFrame:
        raise RuntimeError("Simulated total network outage")

    monkeypatch.setattr("quantedge.data._download_etf_adjusted_closes", _fail_network)
    monkeypatch.setattr("quantedge.data._download_fred_dtb3", _fail_network)

    loaded_offline = load_data(test_cfg, offline=True, repo_root=tmp_path)
    assert loaded_offline.manifest.dataset_id == created.manifest.dataset_id
    assert loaded_offline.manifest.offline_cache_used is True
    pd.testing.assert_frame_equal(loaded_offline.simple_returns, created.simple_returns)

    # 4. Refresh during network failure falls back to verified cache with dated warning note
    fallback = load_data(test_cfg, offline=False, refresh=True, repo_root=tmp_path)
    assert fallback.manifest.offline_cache_used is True
    assert any("WARNING" in note for note in fallback.manifest.notes)

    # 5. Tampering with a persisted parquet file invalidates SHA-256 and blocks offline load
    prices_parquet = tmp_path / "data" / "processed" / created.manifest.dataset_id / "prices.parquet"
    prices_parquet.write_bytes(b"corrupted-parquet-payload")
    with pytest.raises(DataUnavailableError):
        load_data(test_cfg, offline=True, repo_root=tmp_path)


def test_rf_availability_cutoff_after_close_holidays_and_ex_post_distinction() -> None:
    """Finding 1: 16:15 ET H.15 release > 16:00 ET NYSE close, Fed holidays, verified timestamps, ex-post vs forward."""
    # 1. Audited Oct 2026 forecast-origin cutoff example (t = Fri 2026-10-30, decision_time = Thu 2026-10-29 16:00 EDT)
    oct_csv = "\n".join(
        [
            "observation_date,DTB3",
            "2026-10-07,4.03",
            "2026-10-08,4.05",
            "2026-10-09,4.06",
            "2026-10-12,",  # Columbus Day: NYSE open, Federal Reserve Board H.15 closed!
            "2026-10-13,4.09",
            "2026-10-14,4.10",
            "2026-10-27,4.05",
            "2026-10-28,4.01",
            "2026-10-29,4.00",
        ]
    )
    parsed = parse_fred_dtb3_csv(oct_csv)
    nyse_sessions = expected_nyse_sessions("2026-10-07", "2026-10-30")
    # Confirm NYSE is OPEN on Columbus Day 2026-10-12 whereas Fed H.15 business calendar is CLOSED
    assert pd.Timestamp("2026-10-12") in nyse_sessions
    fed_days = expected_federal_reserve_business_days("2026-10-07", "2026-10-30")
    assert pd.Timestamp("2026-10-12") not in fed_days

    return_dates = nyse_sessions[1:]
    rf_fwd = align_risk_free_rate(
        parsed["rate_annual_pct"],
        return_dates,
        mode="forward_decision",
        price_sessions=nyse_sessions,
    )
    rf_exp = align_risk_free_rate(
        parsed["rate_annual_pct"],
        return_dates,
        mode="ex_post",
        price_sessions=nyse_sessions,
    )

    assert rf_fwd.attrs["rf_mode"] == "forward_decision_cutoff_proxy"
    assert rf_exp.attrs["rf_mode"] == "ex_post_contemporaneous_proxy_not_for_forward_decisions"

    # On Fri 2026-10-30 (decision_time = Thu 2026-10-29 16:00 EDT):
    # - 2026-10-29 (4.00%) posts Fri 2026-10-30 16:15 EDT -> excluded
    # - 2026-10-28 (4.01%) posts Thu 2026-10-29 16:15 EDT (> 16:00 EDT!) -> excluded
    # - 2026-10-27 (4.05%) posts Wed 2026-10-28 16:15 EDT (<= Thu 16:00 EDT) -> SELECTED!
    assert np.isclose(rf_fwd.loc["2026-10-30"], (4.05 / 100.0) / 252.0, atol=1e-15)
    assert np.isclose(rf_exp.loc["2026-10-30"], (4.00 / 100.0) / 252.0, atol=1e-15)

    # Columbus Day week (distinct rates uniquely fingerprint each observation date):
    # - Mon 2026-10-12 (decision_time = Fri 2026-10-09 16:00 EDT): Thu Oct 8 (4.05%) posts at
    #   Fri Oct 9 16:15 EDT (> 16:00), so Wed Oct 7 (4.03%, posted Thu Oct 8 16:15 EDT) is active!
    # - Tue 2026-10-13 (decision_time = Mon 2026-10-12 16:00 EDT): Fri Oct 9 (4.06%) did NOT post
    #   on Columbus Day Mon Oct 12, so Thu Oct 8 (4.05%, posted Fri Oct 9 16:15 EDT) is active!
    # - Wed 2026-10-14 (decision_time = Tue 2026-10-13 16:00 EDT): Fri Oct 9 (4.06%) posts at
    #   Tue Oct 13 16:15 EDT (> Tue 16:00 EDT!), so Thu Oct 8 (4.05%) REMAINS active!
    # - Thu 2026-10-15 (decision_time = Wed 2026-10-14 16:00 EDT): Fri Oct 9 (4.06%) is now active!
    assert np.isclose(rf_fwd.loc["2026-10-12"], (4.03 / 100.0) / 252.0, atol=1e-15)
    assert np.isclose(rf_fwd.loc["2026-10-13"], (4.05 / 100.0) / 252.0, atol=1e-15)
    assert np.isclose(rf_fwd.loc["2026-10-14"], (4.05 / 100.0) / 252.0, atol=1e-15)
    assert np.isclose(rf_fwd.loc["2026-10-15"], (4.06 / 100.0) / 252.0, atol=1e-15)

    # 2. OPM Saturday Veterans Day observed on Friday 2023-11-10 (SIFMA & NYSE open, Fed Board closed!)
    vet_series = pd.Series(
        [5.40, 5.42, 5.45],
        index=pd.DatetimeIndex(["2023-11-08", "2023-11-09", "2023-11-10"]),
    )
    vet_nyse = expected_nyse_sessions("2023-11-08", "2023-11-15")
    assert pd.Timestamp("2023-11-10") in vet_nyse
    assert pd.Timestamp("2023-11-10") not in expected_federal_reserve_business_days(
        "2023-11-08", "2023-11-15"
    )
    rf_vet = align_risk_free_rate(
        vet_series,
        vet_nyse[1:],
        mode="forward_decision",
        price_sessions=vet_nyse,
    )
    # On Mon 2023-11-13 (decision_time = Fri 2023-11-10 16:00 EST), Thu 2023-11-09 (5.42%) was NOT
    # published on Fri 2023-11-10 because Fri 2023-11-10 was the OPM Veterans Day federal holiday;
    # Wed 2023-11-08 (5.40%, published Thu 2023-11-09 16:15 EST) remains active on Mon 2023-11-13
    # and Tue 2023-11-14, advancing to 5.45% on Wed 2023-11-15!
    assert np.isclose(rf_vet.loc["2023-11-13"], (5.40 / 100.0) / 252.0, atol=1e-15)
    assert np.isclose(rf_vet.loc["2023-11-14"], (5.40 / 100.0) / 252.0, atol=1e-15)
    assert np.isclose(rf_vet.loc["2023-11-15"], (5.45 / 100.0) / 252.0, atol=1e-15)

    # 3. Verified release_timestamps before vs after 16:00 ET cutoff & naive rejection
    early_verified = {
        pd.Timestamp("2026-10-28"): pd.Timestamp("2026-10-29 15:45:00-04:00"),
    }
    rf_early = align_risk_free_rate(
        parsed["rate_annual_pct"],
        return_dates,
        mode="forward_decision",
        price_sessions=nyse_sessions,
        release_timestamps=early_verified,
    )
    assert np.isclose(rf_early.loc["2026-10-30"], (4.01 / 100.0) / 252.0, atol=1e-15)

    after_close_verified = {
        pd.Timestamp("2026-10-28"): pd.Timestamp("2026-10-29 16:00:01-04:00"),
    }
    rf_after = align_risk_free_rate(
        parsed["rate_annual_pct"],
        return_dates,
        mode="forward_decision",
        price_sessions=nyse_sessions,
        release_timestamps=after_close_verified,
    )
    assert np.isclose(rf_after.loc["2026-10-30"], (4.05 / 100.0) / 252.0, atol=1e-15)

    with pytest.raises(ValueError, match="timezone-aware"):
        align_risk_free_rate(
            parsed["rate_annual_pct"],
            return_dates,
            mode="forward_decision",
            release_timestamps={pd.Timestamp("2026-10-28"): pd.Timestamp("2026-10-29 15:00:00")},
        )


def test_requested_boundary_coverage_rejects_truncation_and_handles_weekends_holidays(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 2: Start/end truncation fails fast while requested weekend/holiday bounds pass cleanly."""
    # 1. Start truncation reproduction: only Oct 2026 rows returned for requested_start='2005-01-01'
    oct_only_sessions = expected_nyse_sessions("2026-10-01", "2026-10-30")
    truncated_prices = _make_synthetic_prices(oct_only_sessions)
    with pytest.raises(DataUnavailableError, match="start boundary coverage failed"):
        build_session_price_grid(
            truncated_prices,
            requested_start="2005-01-01",
            requested_end="2026-10-30",
        )

    # End-to-end through load_data: truncated download MUST raise DataUnavailableError (not pass!)
    raw_cfg = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))
    trunc_cfg_dict = copy.deepcopy(raw_cfg)
    trunc_cfg_dict["data"]["rf_alignment_policy"] = RF_POLICY_R2
    trunc_cfg_dict["data"]["requested_start"] = "2005-01-01"
    trunc_cfg_dict["data"]["frozen_end_date"] = "2026-10-30"
    trunc_cfg_dict["data"]["raw_dir"] = str(tmp_path / "trunc_raw")
    trunc_cfg_dict["data"]["processed_dir"] = str(tmp_path / "trunc_proc")
    trunc_cfg = _validate_raw_config(trunc_cfg_dict)

    monkeypatch.setattr("quantedge.data._download_etf_adjusted_closes", lambda cfg: truncated_prices)
    monkeypatch.setattr(
        "quantedge.data._download_fred_dtb3",
        lambda cfg: parse_fred_dtb3_csv("observation_date,DTB3\n2026-09-25,4.10\n"),
    )
    with pytest.raises(DataUnavailableError, match="start boundary coverage failed"):
        load_data(trunc_cfg, offline=False, repo_root=tmp_path)

    # 2. End truncation: download stops at 2024-02-29 when requested_end is 2024-03-28
    early_stop_prices = _make_synthetic_prices(expected_nyse_sessions("2024-01-02", "2024-02-29"))
    with pytest.raises(DataUnavailableError, match="end boundary coverage failed"):
        build_session_price_grid(
            early_stop_prices,
            requested_start="2024-01-02",
            requested_end="2024-03-28",
        )

    # 3. Single-ticker missingness on first expected session fails boundary coverage
    partial_first = _make_synthetic_prices(expected_nyse_sessions("2024-01-02", "2024-01-10"))
    partial_first.iloc[0, partial_first.columns.get_loc("GLD")] = np.nan
    with pytest.raises(DataUnavailableError, match="GLD"):
        build_session_price_grid(
            partial_first,
            requested_start="2024-01-02",
            requested_end="2024-01-10",
        )

    # 4. Explicit calendar_sessions is NOT clipped back to observed endpoints
    cal_sessions = expected_nyse_sessions("2024-01-02", "2024-01-10")
    missing_first = _make_synthetic_prices(cal_sessions[1:])
    with pytest.raises(DataUnavailableError, match="start boundary coverage failed"):
        build_session_price_grid(missing_first, calendar_sessions=cal_sessions)

    # 5. Requested weekend/holiday bounds (Sat 2005-01-01 to MLK Mon 2005-01-17) pass cleanly
    jan2005_sessions = expected_nyse_sessions("2005-01-01", "2005-01-17")
    assert jan2005_sessions[0] == pd.Timestamp("2005-01-03")
    assert jan2005_sessions[-1] == pd.Timestamp("2005-01-14")
    jan2005_prices = _make_synthetic_prices(jan2005_sessions)
    grid, miss_exp, unexp_obs = build_session_price_grid(
        jan2005_prices,
        requested_start="2005-01-01",
        requested_end="2005-01-17",
    )
    assert len(miss_exp) == 0 and len(unexp_obs) == 0
    diag = grid.attrs["session_grid_diagnostics"]
    assert diag["n_leading_missing_sessions"] == 0
    assert diag["n_trailing_missing_sessions"] == 0


def test_unexpected_weekend_session_quarantined_and_excluded_from_returns(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 3: Bogus Saturday row is preserved for audit but quarantined out of prices and 1-day returns."""
    raw_dates = pd.DatetimeIndex(["2024-01-05", "2024-01-06", "2024-01-08"], name="date")
    vendor_df = pd.DataFrame(
        {
            ticker: np.array([100.0, 150.0, 102.0], dtype=float)
            for ticker in CANONICAL_TICKERS
        },
        index=raw_dates,
    )

    # Policy 'error' rejects unexpected weekend sessions
    with pytest.raises(ValueError, match="2024-01-06"):
        build_session_price_grid(
            vendor_df,
            requested_start="2024-01-05",
            requested_end="2024-01-08",
            unexpected_session_policy="error",
        )

    # Policy 'quarantine' excludes Saturday from modelling grid and returns while recording it
    raw_cfg = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))
    q_cfg_dict = copy.deepcopy(raw_cfg)
    q_cfg_dict["data"]["rf_alignment_policy"] = RF_POLICY_R2
    q_cfg_dict["data"]["requested_start"] = "2024-01-05"
    q_cfg_dict["data"]["frozen_end_date"] = "2024-01-08"
    q_cfg_dict["data"]["raw_dir"] = str(tmp_path / "q_raw")
    q_cfg_dict["data"]["processed_dir"] = str(tmp_path / "q_proc")
    q_cfg = _validate_raw_config(q_cfg_dict)

    monkeypatch.setattr("quantedge.data._download_etf_adjusted_closes", lambda cfg: vendor_df)
    monkeypatch.setattr(
        "quantedge.data._download_fred_dtb3",
        lambda cfg: parse_fred_dtb3_csv("observation_date,DTB3\n2023-12-28,5.04\n"),
    )

    bundle = load_data(q_cfg, offline=False, repo_root=tmp_path)

    # Modelling prices grid has ONLY Fri 2024-01-05 and Mon 2024-01-08 (NO Saturday!)
    assert list(bundle.prices.index) == [pd.Timestamp("2024-01-05"), pd.Timestamp("2024-01-08")]
    # Simple returns has ONLY Mon 2024-01-08 with exact Fri->Mon return 102/100 - 1 = +0.02
    assert list(bundle.simple_returns.index) == [pd.Timestamp("2024-01-08")]
    np.testing.assert_allclose(bundle.simple_returns.iloc[0].to_numpy(), 0.02, rtol=0, atol=1e-14)

    # Raw parquet and quarantined_prices preserve Saturday 2024-01-06 (150.0) for audit
    assert bundle.quarantined_prices is not None
    assert list(bundle.quarantined_prices.index) == [pd.Timestamp("2024-01-06")]
    np.testing.assert_allclose(bundle.quarantined_prices.iloc[0].to_numpy(), 150.0, rtol=0, atol=1e-14)
    raw_saved = pd.read_parquet(
        tmp_path / "q_raw" / bundle.manifest.dataset_id / "etf_prices_raw.parquet"
    )
    assert pd.Timestamp("2024-01-06") in raw_saved.index
    assert bundle.manifest.row_exclusions["n_quarantined_unexpected_sessions"] == 1
    assert bundle.manifest.row_exclusions["quarantined_unexpected_dates"] == ["2024-01-06"]

    q_flags = bundle.quality_flags.loc[
        bundle.quality_flags["rule"] == "unexpected_non_nyse_session"
    ]
    assert len(q_flags) == len(CANONICAL_TICKERS)
    assert set(q_flags["action"]) == {"quarantine_exclude_from_modelling_grid"}


def test_cached_rf_shifted_index_with_valid_sha256_is_rejected(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 4: Same-length shifted or RangeIndex rf_daily.parquet with valid SHA-256 fails logical index check."""
    raw_cfg = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))
    cfg_dict = copy.deepcopy(raw_cfg)
    cfg_dict["data"]["rf_alignment_policy"] = RF_POLICY_R2
    cfg_dict["data"]["requested_start"] = "2024-01-02"
    cfg_dict["data"]["frozen_end_date"] = "2024-02-15"
    cfg_dict["data"]["raw_dir"] = str(tmp_path / "idx_raw")
    cfg_dict["data"]["processed_dir"] = str(tmp_path / "idx_proc")
    test_cfg = _validate_raw_config(cfg_dict)

    sessions = expected_nyse_sessions("2024-01-02", "2024-02-15")
    monkeypatch.setattr(
        "quantedge.data._download_etf_adjusted_closes",
        lambda cfg: _make_synthetic_prices(sessions),
    )
    monkeypatch.setattr(
        "quantedge.data._download_fred_dtb3",
        lambda cfg: parse_fred_dtb3_csv("observation_date,DTB3\n2023-12-20,5.25\n2024-01-15,5.20\n"),
    )

    created = load_data(test_cfg, offline=False, repo_root=tmp_path)
    ds_id = created.manifest.dataset_id
    snap_dir = tmp_path / "idx_proc" / ds_id
    rf_parquet = snap_dir / "rf_daily.parquet"
    manifest_json = snap_dir / "manifest.json"

    def _rewrite_rf_and_update_manifest_hash(new_rf_df: pd.DataFrame) -> None:
        new_rf_df.to_parquet(rf_parquet, engine="pyarrow", index=True)
        new_sha = hashlib.sha256(rf_parquet.read_bytes()).hexdigest()
        m_data = json.loads(manifest_json.read_text(encoding="utf-8"))
        matched_keys = [k for k in m_data["file_sha256"] if k.endswith("rf_daily.parquet")]
        assert len(matched_keys) == 1
        m_data["file_sha256"][matched_keys[0]] = new_sha
        manifest_json.write_text(json.dumps(m_data, indent=2, sort_keys=True), encoding="utf-8")

    # 1. Same-length DatetimeIndex shifted by +1 business day with recomputed valid SHA-256
    orig_rf_df = pd.read_parquet(rf_parquet, engine="pyarrow")
    shifted_rf_df = orig_rf_df.copy()
    shifted_rf_df.index = shifted_rf_df.index + pd.offsets.BDay(1)
    assert len(shifted_rf_df) == len(created.simple_returns)
    _rewrite_rf_and_update_manifest_hash(shifted_rf_df)

    with pytest.raises(DataUnavailableError, match="rf_daily.parquet index does not match"):
        load_data(test_cfg, offline=True, repo_root=tmp_path)

    # 2. Same-length RangeIndex with recomputed valid SHA-256
    range_rf_df = orig_rf_df.reset_index(drop=True)
    assert len(range_rf_df) == len(created.simple_returns)
    _rewrite_rf_and_update_manifest_hash(range_rf_df)

    with pytest.raises(DataUnavailableError, match="rf_daily.parquet index does not match"):
        load_data(test_cfg, offline=True, repo_root=tmp_path)


def test_real_repository_snapshot_integrity_and_preserved_v1_audit_snapshot(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify preserved r2 hardened snapshot, preserved v1 audited snapshot hashes, and policy isolation."""
    r2_cfg_dict = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))
    r2_cfg_dict["data"]["rf_alignment_policy"] = RF_POLICY_R2
    bundle = load_data(_validate_raw_config(r2_cfg_dict), offline=True, repo_root=repo_root)
    m = bundle.manifest

    assert m.dataset_id.startswith("qe1_20050101_20261030_r2_")
    assert m.policy_revision == "r2_hardened"
    assert m.parent_dataset_id == "qe1_20050101_20261030_afb9ce5694"
    assert m.schema_version == "1.1.0"
    assert (
        m.rf_convention["alignment_policy"]
        == "h15_schedule_1615_ny_before_prev_nyse_close_1600_ny"
    )

    assert tuple(bundle.prices.columns) == CANONICAL_TICKERS
    assert tuple(bundle.simple_returns.columns) == CANONICAL_TICKERS
    assert tuple(bundle.log_returns.columns) == CANONICAL_TICKERS
    assert bundle.prices.index.is_monotonic_increasing and bundle.prices.index.is_unique
    assert bundle.simple_returns.index.is_monotonic_increasing and bundle.simple_returns.index.is_unique
    pd.testing.assert_index_equal(bundle.simple_returns.index, bundle.log_returns.index)
    pd.testing.assert_index_equal(bundle.simple_returns.index, bundle.rf_daily.index)
    assert bundle.ex_post_rf_daily is not None
    pd.testing.assert_index_equal(bundle.simple_returns.index, bundle.ex_post_rf_daily.index)

    # Confirm forward-decision vs ex-post RF values on audited final session 2026-10-30
    assert np.isclose(bundle.rf_daily.loc["2026-10-30"], (4.05 / 100.0) / 252.0, atol=1e-15)
    assert np.isclose(
        bundle.ex_post_rf_daily.loc["2026-10-30"], (4.00 / 100.0) / 252.0, atol=1e-15
    )
    assert m.rf_convention["n_days_forward_differs_from_ex_post"] > 4000

    assert m.actual_start == "2005-01-03"
    assert m.actual_end == "2026-10-30"
    assert len(bundle.prices) == 5492
    assert len(bundle.simple_returns) == 5491
    assert not bool(bundle.simple_returns.isna().any().any())
    assert not bool(bundle.log_returns.isna().any().any())
    assert not bool(bundle.rf_daily.isna().any())
    assert np.allclose(
        bundle.log_returns.to_numpy(),
        np.log1p(bundle.simple_returns.to_numpy()),
        rtol=0.0,
        atol=1e-13,
    )

    snap_dir = repo_root / "data" / "processed" / m.dataset_id
    assert (snap_dir / "manifest.json").exists()
    assert (snap_dir / "quality_report.md").exists()
    assert (snap_dir / "rf_daily_ex_post.parquet").exists()
    assert (snap_dir / "quarantined_unexpected_prices.parquet").exists()
    assert (snap_dir / "adf_stationarity.csv").exists()
    assert (snap_dir / "descriptive_stats_simple.csv").exists()
    assert (snap_dir / "descriptive_stats_log.csv").exists()
    assert (snap_dir / "log_return_correlations.csv").exists()

    # Verify preserved Step 2 v1 snapshot qe1_20050101_20261030_afb9ce5694 is untouched bit-for-bit
    v1_id = "qe1_20050101_20261030_afb9ce5694"
    v1_manifest_path = repo_root / "data" / "processed" / v1_id / "manifest.json"
    assert v1_manifest_path.exists()
    v1_manifest = json.loads(v1_manifest_path.read_text(encoding="utf-8"))
    assert v1_manifest["schema_version"] == "1.0.0"
    assert len(v1_manifest["file_sha256"]) == 13
    for rel_key, expected_sha in v1_manifest["file_sha256"].items():
        fpath = repo_root / Path(rel_key)
        assert fpath.exists(), f"Preserved v1 file missing: {fpath}"
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert actual_sha == expected_sha, f"Preserved v1 file modified: {rel_key}"

    # Verify policy isolation: an active_snapshot.json pointing ONLY to a v1.0.0 snapshot is
    # never returned under the v1.1.0 hardened RF policy.
    iso_proc = tmp_path / "iso_processed"
    iso_v1_dir = iso_proc / v1_id
    iso_v1_dir.mkdir(parents=True)
    (iso_v1_dir / "manifest.json").write_text(
        v1_manifest_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (iso_proc / "active_snapshot.json").write_text(
        json.dumps({"dataset_id": v1_id, "manifest_relpath": f"{v1_id}/manifest.json"}),
        encoding="utf-8",
    )
    raw_cfg = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))
    iso_cfg_dict = copy.deepcopy(raw_cfg)
    iso_cfg_dict["data"]["rf_alignment_policy"] = RF_POLICY_R2
    iso_cfg_dict["data"]["processed_dir"] = str(iso_proc)
    iso_cfg = _validate_raw_config(iso_cfg_dict)
    with pytest.raises(DataUnavailableError, match="Offline mode"):
        load_data(iso_cfg, offline=True, repo_root=repo_root)
