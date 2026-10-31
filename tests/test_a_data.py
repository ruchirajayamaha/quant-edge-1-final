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
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from quantedge.config import AppConfig, _validate_raw_config
from quantedge.contracts import CANONICAL_TICKERS, QUALITY_FLAG_COLUMNS
from quantedge.data import (
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
    """FRED DTB3 uses (rate/100)/252 units, enforces 1-session lag, and NEVER backfills."""
    fred_csv = "\n".join(
        [
            "observation_date,DTB3",
            "2024-01-04,5.04",
            "2024-01-05,.",
            "2024-01-08,5.292",
        ]
    )
    parsed = parse_fred_dtb3_csv(fred_csv)
    assert parsed.loc["2024-01-05", "raw_value"] == "."
    assert np.isnan(parsed.loc["2024-01-05", "rate_annual_pct"])

    return_dates = pd.DatetimeIndex(
        ["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"],
        name="date",
    )
    rf = align_risk_free_rate(
        parsed["rate_annual_pct"],
        return_dates,
        availability_lag_sessions=1,
        trading_days_per_year=252,
    )

    # 2024-01-04 quote (5.04%) becomes available at 2024-01-04 + 1 BDay = 2024-01-05.
    # Therefore 2024-01-03 AND 2024-01-04 MUST remain NaN (no same-day look-ahead, no backfill!).
    assert np.isnan(rf.loc["2024-01-03"])
    assert np.isnan(rf.loc["2024-01-04"])

    # (5.04 / 100) / 252 = 0.0002 exactly
    assert np.isclose(rf.loc["2024-01-05"], 0.0002, atol=1e-15)
    # On Monday 2024-01-08, Friday 2024-01-05 was '.' and Monday's 5.292% is not yet available (lag=1),
    # so 2024-01-08 still uses 0.0002!
    assert np.isclose(rf.loc["2024-01-08"], 0.0002, atol=1e-15)
    # On Tuesday 2024-01-09, Monday's 5.292% -> (5.292 / 100) / 252 = 0.00021 is active!
    assert np.isclose(rf.loc["2024-01-09"], 0.00021, atol=1e-15)

    # Future perturbation invariance check: altering 2024-01-08 quote cannot affect <= 2024-01-08
    perturbed = parsed["rate_annual_pct"].copy()
    perturbed.loc[pd.Timestamp("2024-01-08")] = 99.0
    rf_perturbed = align_risk_free_rate(
        perturbed,
        return_dates,
        availability_lag_sessions=1,
        trading_days_per_year=252,
    )
    pd.testing.assert_series_equal(rf.iloc[:4], rf_perturbed.iloc[:4])


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


def test_real_repository_snapshot_integrity(baseline_config: AppConfig, repo_root: Path) -> None:
    """Verify the actual persisted Step 2 snapshot in data/processed/ offline."""
    bundle = load_data(baseline_config, offline=True, repo_root=repo_root)
    m = bundle.manifest

    assert tuple(bundle.prices.columns) == CANONICAL_TICKERS
    assert tuple(bundle.simple_returns.columns) == CANONICAL_TICKERS
    assert tuple(bundle.log_returns.columns) == CANONICAL_TICKERS
    assert bundle.prices.index.is_monotonic_increasing and bundle.prices.index.is_unique
    assert bundle.simple_returns.index.is_monotonic_increasing and bundle.simple_returns.index.is_unique
    pd.testing.assert_index_equal(bundle.simple_returns.index, bundle.log_returns.index)
    pd.testing.assert_index_equal(bundle.simple_returns.index, bundle.rf_daily.index)

    assert m.actual_start == "2005-01-03"
    assert len(bundle.simple_returns) > 5000
    assert not bool(bundle.simple_returns.isna().any().any())
    assert not bool(bundle.log_returns.isna().any().any())
    assert np.allclose(
        bundle.log_returns.to_numpy(),
        np.log1p(bundle.simple_returns.to_numpy()),
        rtol=0.0,
        atol=1e-13,
    )

    snap_dir = repo_root / "data" / "processed" / m.dataset_id
    assert (snap_dir / "manifest.json").exists()
    assert (snap_dir / "quality_report.md").exists()
    assert (snap_dir / "adf_stationarity.csv").exists()
    assert (snap_dir / "descriptive_stats_simple.csv").exists()
    assert (snap_dir / "descriptive_stats_log.csv").exists()
    assert (snap_dir / "log_return_correlations.csv").exists()
