"""Market-data snapshot acquisition, caching, SHA-256 provenance, and quality flagging.

Implemented in SOLO STEP 2 (milestone A1).

Responsibilities:
- Fetch dividend- and split-adjusted daily closes for the canonical 7-ETF universe
  (``SPY, EFA, EEM, AGG, GLD, XLE, XLK``) via ``yfinance`` with ``auto_adjust=True``
  (rejecting ambiguous raw/adjusted frames) and FRED ``DTB3`` quotes.
- Align raw ETF observations onto the documented NYSE regular trading-session grid
  without implicit forward-fill, compute one-session simple and log returns BEFORE
  excluding incomplete return intervals, and align past-only ``DTB3`` daily proxies.
- Flag missing prices, unexpected non-NYSE dates, stale/flat return runs, robust-MAD
  jumps (with safe ``MAD=0`` fallback), large negative returns, and candidate
  volatility-regime structural breaks while RETAINING all valid return observations.
- Persist one reusable, SHA-256-verified parquet snapshot, quality/ADF tables,
  Markdown quality report, and JSON ``DataManifest``.
- Support deterministic cache reuse and graceful offline / network-failure fallback
  without ever fabricating synthetic production data.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from quantedge.config import AppConfig, DEFAULT_CONFIG_PATH, _validate_raw_config, load_config
from quantedge.contracts import (
    CANONICAL_TICKERS,
    CONTRACT_SCHEMA_VERSION,
    QUALITY_FLAG_COLUMNS,
    DataBundle,
    DataManifest,
)
from quantedge.rf_evidence import RF_VERSION_TABLE_COLUMNS, rf_accrual_91d_sensitivity
from quantedge.returns import (
    EXCLUDED_RETURN_COLUMNS,
    RFAlignmentMode,
    align_risk_free_rate,
    compute_return_descriptive_stats,
    compute_session_returns,
    expected_nyse_sessions,
    run_stationarity_diagnostics,
    select_rf_versions_asof,
)

RF_POLICY_R2: str = "h15_schedule_1615_ny_before_prev_nyse_close_1600_ny"
RF_POLICY_R3: str = "r3_versioned_release_evidence_day_level"
POLICY_REVISION_R2: str = "r2_hardened"
POLICY_REVISION_R3: str = "r3_release_evidence"


class DataUnavailableError(RuntimeError):
    """Raised when market data cannot be retrieved and no verified matching cache exists."""


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file on disk."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_session_index(idx: pd.Index) -> pd.DatetimeIndex:
    """Convert a price or observation index into tz-naive normalized US session dates."""
    dt_idx = pd.to_datetime(idx)
    if not isinstance(dt_idx, pd.DatetimeIndex):
        dt_idx = pd.DatetimeIndex(dt_idx)
    if dt_idx.tz is not None:
        dt_idx = dt_idx.tz_convert("America/New_York").tz_localize(None)
    normalized = dt_idx.normalize()
    normalized.name = "date"
    return normalized


def extract_adjusted_closes(
    raw_yf_frame: pd.DataFrame,
    tickers: Sequence[str] = CANONICAL_TICKERS,
) -> pd.DataFrame:
    """Extract canonical adjusted close columns from a ``yfinance`` ``auto_adjust=True`` frame.

    With ``yfinance.download(..., auto_adjust=True)``, Yahoo's dividend- and split-adjusted
    close series is returned under the ``'Close'`` field and ``'Adj Close'`` is omitted.
    If ``'Adj Close'`` coexists alongside ``'Close'`` (indicating ``auto_adjust=False``),
    this function raises ``ValueError`` rather than silently mixing raw and adjusted closes.
    """
    if not isinstance(raw_yf_frame, pd.DataFrame) or raw_yf_frame.empty:
        raise DataUnavailableError("yfinance returned an empty or non-DataFrame response.")

    canonical = list(tickers)

    if isinstance(raw_yf_frame.columns, pd.MultiIndex):
        if raw_yf_frame.columns.nlevels != 2:
            raise ValueError(
                f"Expected 2-level MultiIndex from yfinance; got {raw_yf_frame.columns.nlevels} levels."
            )
        lvl0 = set(map(str, raw_yf_frame.columns.get_level_values(0)))
        lvl1 = set(map(str, raw_yf_frame.columns.get_level_values(1)))

        if "Close" in lvl0:
            if "Adj Close" in lvl0:
                raise ValueError(
                    "Raw/unadjusted yfinance frame detected ('Adj Close' present alongside 'Close' "
                    "in level 0); expected auto_adjust=True frame where 'Close' is the adjusted series."
                )
            close_df = raw_yf_frame["Close"].copy()
        elif "Close" in lvl1:
            if "Adj Close" in lvl1:
                raise ValueError(
                    "Raw/unadjusted yfinance frame detected ('Adj Close' present alongside 'Close' "
                    "in level 1); expected auto_adjust=True frame where 'Close' is the adjusted series."
                )
            close_df = raw_yf_frame.xs("Close", axis=1, level=1).copy()
        else:
            raise ValueError(
                f"Could not locate 'Close' price field in yfinance MultiIndex columns: {lvl0} / {lvl1}."
            )
    else:
        col_names = set(map(str, raw_yf_frame.columns))
        if "Adj Close" in col_names and "Close" in col_names:
            raise ValueError(
                "Raw/unadjusted frame detected ('Adj Close' present alongside 'Close'); "
                "expected auto_adjust=True adjusted closes."
            )
        close_df = raw_yf_frame.copy()

    close_df.columns = [str(c) for c in close_df.columns]
    missing_cols = [t for t in canonical if t not in close_df.columns]
    if missing_cols:
        raise DataUnavailableError(
            f"yfinance response is missing canonical ETF column(s): {missing_cols}."
        )

    close_df = close_df[canonical].apply(pd.to_numeric, errors="coerce").astype(float)
    close_df.index = _normalize_session_index(close_df.index)
    close_df = close_df.sort_index(kind="mergesort")

    if close_df.index.duplicated().any():
        dup_dates = close_df.index[close_df.index.duplicated()].unique().strftime("%Y-%m-%d").tolist()
        raise ValueError(f"Duplicate trading-session dates in extracted prices: {dup_dates[:5]}")

    # Drop leading/trailing rows where ALL tickers are NaN (e.g. unopened session placeholder)
    all_nan_rows = close_df.isna().all(axis=1)
    if bool(all_nan_rows.all()):
        raise DataUnavailableError("Extracted ETF price table contains only NaN values.")
    first_valid_idx = close_df.index[~all_nan_rows][0]
    last_valid_idx = close_df.index[~all_nan_rows][-1]
    close_df = close_df.loc[first_valid_idx:last_valid_idx].copy()

    completely_missing_tickers = [t for t in canonical if bool(close_df[t].isna().all())]
    if completely_missing_tickers:
        raise DataUnavailableError(
            f"Failed ticker download (all-NaN series) for: {completely_missing_tickers}."
        )

    observed_vals = close_df.to_numpy()[~np.isnan(close_df.to_numpy())]
    if np.any(~np.isfinite(observed_vals)) or np.any(observed_vals <= 0.0):
        raise ValueError("Extracted ETF prices contain non-positive or non-finite observations.")

    return close_df


def parse_fred_dtb3_csv(csv_text: str) -> pd.DataFrame:
    """Parse FRED ``DTB3`` CSV payload while preserving raw strings and missing ``'.'``/empty markers."""
    if not csv_text or not csv_text.strip():
        raise DataUnavailableError("Empty CSV payload received for FRED DTB3.")

    raw_df = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
    if raw_df.shape[1] < 2:
        raise ValueError(f"Unexpected FRED CSV shape {raw_df.shape}; expected date and DTB3 columns.")

    date_col = raw_df.columns[0]
    val_col = "DTB3" if "DTB3" in raw_df.columns else raw_df.columns[1]

    parsed_dates = pd.to_datetime(raw_df[date_col].astype(str).str.strip(), errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError("Invalid observation dates encountered in FRED DTB3 CSV.")

    raw_vals = raw_df[val_col].astype(str).str.strip()
    numeric_vals = pd.to_numeric(raw_vals, errors="coerce")

    out = pd.DataFrame(
        {
            "raw_value": raw_vals.to_numpy(dtype=object),
            "rate_annual_pct": numeric_vals.to_numpy(dtype=float),
        },
        index=pd.DatetimeIndex(parsed_dates).normalize(),
    )
    out.index.name = "obs_date"
    out = out.sort_index(kind="mergesort")
    out = out[~out.index.duplicated(keep="last")]

    if int(out["rate_annual_pct"].notna().sum()) == 0:
        raise DataUnavailableError("FRED DTB3 CSV contained zero numeric rate observations.")

    return out


def build_session_price_grid(
    observed_prices: pd.DataFrame,
    *,
    requested_start: str | pd.Timestamp | None = None,
    requested_end: str | pd.Timestamp | None = None,
    calendar_sessions: pd.DatetimeIndex | None = None,
    require_boundary_coverage: bool | None = None,
    unexpected_session_policy: Literal["quarantine", "error"] = "quarantine",
) -> tuple[pd.DataFrame, pd.DatetimeIndex, pd.DatetimeIndex]:
    """Reindex observed prices onto the shared NYSE trading-session grid WITHOUT fill.

    Hardened Step 2 Guards:
    - Validates first and last expected NYSE trading sessions against requested bounds
      (``requested_start`` / ``requested_end``) or explicit ``calendar_sessions`` without
      clipping expected sessions back to observed endpoints. Weekend and NYSE-holiday
      request bounds map naturally to the first/last expected NYSE sessions without
      requiring quotes on closed dates.
    - Quarantines (or rejects when ``unexpected_session_policy='error'``) unexpected
      non-NYSE dates (such as Saturday/weekend vendor rows) so they NEVER enter the
      ``prices`` modelling grid or contaminate one-session returns via index union.

    Returns:
        ``(grid_prices, missing_expected_sessions, unexpected_observed_sessions)``
    """
    if not isinstance(observed_prices, pd.DataFrame) or observed_prices.empty:
        raise ValueError("observed_prices cannot be empty.")
    if unexpected_session_policy not in ("quarantine", "error"):
        raise ValueError(
            f"unexpected_session_policy must be 'quarantine' or 'error'; got {unexpected_session_policy!r}."
        )

    obs = observed_prices.copy()
    obs.index = _normalize_session_index(obs.index)
    if not obs.index.is_monotonic_increasing or not obs.index.is_unique:
        obs = obs.sort_index(kind="mergesort")
        if obs.index.duplicated().any():
            raise ValueError("observed_prices index contains duplicate session dates.")

    req_start_ts = (
        pd.Timestamp(requested_start).normalize() if requested_start is not None else None
    )
    req_end_ts = pd.Timestamp(requested_end).normalize() if requested_end is not None else None
    if req_start_ts is not None and req_end_ts is not None and req_end_ts < req_start_ts:
        raise ValueError(
            f"requested_end ({req_end_ts.strftime('%Y-%m-%d')}) must be >= "
            f"requested_start ({req_start_ts.strftime('%Y-%m-%d')})."
        )

    if calendar_sessions is not None:
        expected = _normalize_session_index(calendar_sessions).sort_values().unique()
        expected.name = "date"
    else:
        bound_start = req_start_ts if req_start_ts is not None else obs.index[0]
        bound_end = req_end_ts if req_end_ts is not None else obs.index[-1]
        if bound_end < bound_start:
            raise DataUnavailableError(
                f"Observed price bounds [{obs.index[0].strftime('%Y-%m-%d')}, "
                f"{obs.index[-1].strftime('%Y-%m-%d')}] fall outside requested bounds "
                f"[{bound_start.strftime('%Y-%m-%d')}, {bound_end.strftime('%Y-%m-%d')}]."
            )
        expected = expected_nyse_sessions(bound_start, bound_end)

    if len(expected) == 0:
        raise DataUnavailableError(
            "Requested date window contains zero expected NYSE regular trading sessions."
        )

    enforce_boundaries = (
        bool(require_boundary_coverage)
        if require_boundary_coverage is not None
        else (req_start_ts is not None or req_end_ts is not None or calendar_sessions is not None)
    )
    check_start_boundary = enforce_boundaries and (
        req_start_ts is not None or calendar_sessions is not None
    )
    check_end_boundary = enforce_boundaries and (
        req_end_ts is not None or calendar_sessions is not None
    )

    # Identify unexpected non-NYSE dates in the window under evaluation.
    if calendar_sessions is not None or (req_start_ts is not None and req_end_ts is not None):
        scoped_obs_idx = obs.index
        if req_start_ts is not None:
            scoped_obs_idx = scoped_obs_idx[scoped_obs_idx >= req_start_ts]
        if req_end_ts is not None:
            scoped_obs_idx = scoped_obs_idx[scoped_obs_idx <= req_end_ts]
    else:
        scoped_obs_idx = obs.index
        if req_start_ts is not None:
            scoped_obs_idx = scoped_obs_idx[scoped_obs_idx >= req_start_ts]
        if req_end_ts is not None:
            scoped_obs_idx = scoped_obs_idx[scoped_obs_idx <= req_end_ts]

    unexpected_observed = scoped_obs_idx.difference(expected)
    unexpected_observed.name = "date"

    if len(unexpected_observed) > 0 and unexpected_session_policy == "error":
        bad_dates = [d.strftime("%Y-%m-%d") for d in unexpected_observed[:10]]
        raise ValueError(
            f"Observed ETF prices contain {len(unexpected_observed)} unexpected non-NYSE session "
            f"date(s) under unexpected_session_policy='error': {bad_dates}"
        )

    # CRITICAL: Reindex onto expected NYSE sessions ONLY (never union unexpected weekend dates)
    # and with NO fill so missing sessions remain explicit NaNs.
    grid_prices = obs.reindex(expected)
    grid_prices.index.name = "date"

    all_missing_mask = grid_prices.isna().all(axis=1)
    missing_expected = grid_prices.index[all_missing_mask]
    missing_expected.name = "date"

    any_present_mask = ~all_missing_mask
    if not bool(any_present_mask.any()):
        raise DataUnavailableError(
            f"Zero expected NYSE sessions in [{expected[0].strftime('%Y-%m-%d')}, "
            f"{expected[-1].strftime('%Y-%m-%d')}] contain observed ETF prices."
        )

    first_present_session = grid_prices.index[any_present_mask][0]
    last_present_session = grid_prices.index[any_present_mask][-1]
    leading_missing = expected[expected < first_present_session]
    trailing_missing = expected[expected > last_present_session]
    interior_missing = missing_expected[
        (missing_expected >= first_present_session) & (missing_expected <= last_present_session)
    ]

    first_session_missing_tickers = [
        str(t) for t in grid_prices.columns if pd.isna(grid_prices.iloc[0][t])
    ]
    last_session_missing_tickers = [
        str(t) for t in grid_prices.columns if pd.isna(grid_prices.iloc[-1][t])
    ]

    if check_start_boundary and (
        len(leading_missing) > 0 or len(first_session_missing_tickers) > 0
    ):
        raise DataUnavailableError(
            f"Requested start boundary coverage failed: first expected NYSE session is "
            f"{expected[0].strftime('%Y-%m-%d')} (requested_start="
            f"{req_start_ts.strftime('%Y-%m-%d') if req_start_ts is not None else 'calendar_sessions[0]'}), "
            f"first observed NYSE session is {first_present_session.strftime('%Y-%m-%d')}, "
            f"leading_missing_sessions={len(leading_missing)}, "
            f"missing_tickers_on_first_expected_session={first_session_missing_tickers}."
        )

    if check_end_boundary and (len(trailing_missing) > 0 or len(last_session_missing_tickers) > 0):
        raise DataUnavailableError(
            f"Requested end boundary coverage failed: last expected NYSE session is "
            f"{expected[-1].strftime('%Y-%m-%d')} (requested_end="
            f"{req_end_ts.strftime('%Y-%m-%d') if req_end_ts is not None else 'calendar_sessions[-1]'}), "
            f"last observed NYSE session is {last_present_session.strftime('%Y-%m-%d')}, "
            f"trailing_missing_sessions={len(trailing_missing)}, "
            f"missing_tickers_on_last_expected_session={last_session_missing_tickers}."
        )

    grid_prices.attrs["session_grid_diagnostics"] = {
        "requested_start": req_start_ts.strftime("%Y-%m-%d") if req_start_ts is not None else None,
        "requested_end": req_end_ts.strftime("%Y-%m-%d") if req_end_ts is not None else None,
        "first_expected_session": expected[0].strftime("%Y-%m-%d"),
        "last_expected_session": expected[-1].strftime("%Y-%m-%d"),
        "n_leading_missing_sessions": int(len(leading_missing)),
        "leading_missing_sessions": [d.strftime("%Y-%m-%d") for d in leading_missing],
        "n_trailing_missing_sessions": int(len(trailing_missing)),
        "trailing_missing_sessions": [d.strftime("%Y-%m-%d") for d in trailing_missing],
        "n_interior_missing_sessions": int(len(interior_missing)),
        "interior_missing_sessions": [d.strftime("%Y-%m-%d") for d in interior_missing],
        "first_session_missing_tickers": first_session_missing_tickers,
        "last_session_missing_tickers": last_session_missing_tickers,
        "unexpected_session_policy": unexpected_session_policy,
        "n_unexpected_quarantined_sessions": int(len(unexpected_observed)),
        "unexpected_quarantined_dates": [d.strftime("%Y-%m-%d") for d in unexpected_observed],
    }

    return grid_prices, missing_expected, unexpected_observed


def flag_data_quality(
    prices: pd.DataFrame,
    simple_returns: pd.DataFrame,
    log_returns: pd.DataFrame,
    rf_daily: pd.Series,
    *,
    unexpected_sessions: pd.DatetimeIndex | None = None,
    quarantined_prices: pd.DataFrame | None = None,
    min_flat_run: int = 3,
    mad_z_threshold: float = 8.0,
    large_negative_threshold: float = -0.05,
    break_short_window: int = 63,
    break_long_window: int = 252,
    break_vol_ratio_threshold: float = 2.5,
) -> pd.DataFrame:
    """Evaluate reproducible data-quality and structural diagnostic rules WITHOUT removing returns.

    Rules:
    - ``missing_price``: ``NaN`` cell on the uncollapsed ``prices`` grid
      (``action='exclude_adjacent_returns'``).
    - ``unexpected_non_nyse_session``: Observed price date outside expected NYSE calendar,
      preserved in raw/quarantine audit artifacts and excluded from the ``prices`` modelling
      grid (``action='quarantine_exclude_from_modelling_grid'``).
    - ``stale_flat_return_run``: Consecutive zero simple returns (``|r| <= 1e-12``) of length
      ``>= min_flat_run`` (``action='retain'``).
    - ``robust_mad_jump``: ``|r - median(r)| / scale > mad_z_threshold`` where
      ``scale = 1.4826 * MAD`` with safe ``MAD == 0`` fallback to ``IQR / 1.349`` then
      sample ``std(ddof=1)`` (``action='retain'``).
    - ``large_negative_return``: Single-day simple return ``<= large_negative_threshold``
      (``action='retain'``).
    - ``candidate_structural_break``: Causal trailing ``break_short_window`` log-return
      volatility >= ``break_vol_ratio_threshold`` times immediately preceding non-overlapping
      ``break_long_window`` volatility, deduplicated with a ``break_short_window`` cooldown.
      Explicitly a diagnostic flag, NOT proof of a permanent structural break (``action='retain'``).
    - ``missing_aligned_rf``: Return session where past-only aligned ``rf_daily`` is ``NaN``
      (``action='mark_rf_kpis_unavailable_if_needed'``).
    """
    records: list[dict[str, object]] = []

    # 1. Missing prices on uncollapsed session grid
    for ticker in prices.columns:
        miss_dates = prices.index[prices[ticker].isna()]
        for dt in miss_dates:
            records.append(
                {
                    "date": pd.Timestamp(dt),
                    "ticker": str(ticker),
                    "rule": "missing_price",
                    "value": np.nan,
                    "action": "exclude_adjacent_returns",
                }
            )

    # 2. Quarantined unexpected non-NYSE sessions (preserved in raw/quarantine, excluded from grid)
    if quarantined_prices is not None and not quarantined_prices.empty:
        for dt in quarantined_prices.index:
            emitted_for_dt = False
            for ticker in quarantined_prices.columns:
                val = quarantined_prices.at[dt, ticker]
                if pd.notna(val):
                    records.append(
                        {
                            "date": pd.Timestamp(dt),
                            "ticker": str(ticker),
                            "rule": "unexpected_non_nyse_session",
                            "value": float(val),
                            "action": "quarantine_exclude_from_modelling_grid",
                        }
                    )
                    emitted_for_dt = True
            if not emitted_for_dt:
                records.append(
                    {
                        "date": pd.Timestamp(dt),
                        "ticker": "ALL",
                        "rule": "unexpected_non_nyse_session",
                        "value": np.nan,
                        "action": "quarantine_exclude_from_modelling_grid",
                    }
                )
    elif unexpected_sessions is not None and len(unexpected_sessions) > 0:
        for dt in unexpected_sessions:
            records.append(
                {
                    "date": pd.Timestamp(dt),
                    "ticker": "ALL",
                    "rule": "unexpected_non_nyse_session",
                    "value": np.nan,
                    "action": "quarantine_exclude_from_modelling_grid",
                }
            )

    # 3. Return-level diagnostic flags (never erase or alter simple_returns / log_returns)
    for ticker in simple_returns.columns:
        s_ret = simple_returns[ticker].astype(float)
        if s_ret.empty:
            continue

        # 3a. Stale / flat sequences
        is_flat = s_ret.abs() <= 1e-12
        streak = 0
        for dt, flat_flag in is_flat.items():
            if bool(flat_flag):
                streak += 1
                if streak >= min_flat_run:
                    records.append(
                        {
                            "date": pd.Timestamp(dt),
                            "ticker": str(ticker),
                            "rule": "stale_flat_return_run",
                            "value": float(streak),
                            "action": "retain",
                        }
                    )
            else:
                streak = 0

        # 3b. Robust MAD jump outliers with safe MAD == 0 handling
        vals = s_ret.to_numpy(dtype=float)
        med = float(np.median(vals))
        abs_dev = np.abs(vals - med)
        mad = float(np.median(abs_dev))
        sigma_mad = 1.4826 * mad

        scale: float | None = None
        if sigma_mad > 1e-12:
            scale = sigma_mad
        else:
            q75, q25 = np.percentile(vals, [75.0, 25.0])
            sigma_iqr = float((q75 - q25) / 1.349)
            if sigma_iqr > 1e-12:
                scale = sigma_iqr
            elif len(vals) > 1:
                sigma_std = float(np.std(vals, ddof=1))
                if sigma_std > 1e-12:
                    scale = sigma_std

        if scale is not None and scale > 1e-12:
            z_scores = abs_dev / scale
            jump_mask = z_scores > mad_z_threshold
            for dt, ret_val in s_ret.loc[jump_mask].items():
                records.append(
                    {
                        "date": pd.Timestamp(dt),
                        "ticker": str(ticker),
                        "rule": "robust_mad_jump",
                        "value": float(ret_val),
                        "action": "retain",
                    }
                )

        # 3c. Large negative single-session simple returns
        neg_mask = s_ret <= large_negative_threshold
        for dt, ret_val in s_ret.loc[neg_mask].items():
            records.append(
                {
                    "date": pd.Timestamp(dt),
                    "ticker": str(ticker),
                    "rule": "large_negative_return",
                    "value": float(ret_val),
                    "action": "retain",
                }
            )

        # 3d. Candidate volatility-regime structural breaks (causal, flagged not proven)
        if ticker in log_returns.columns and len(log_returns) >= (break_short_window + break_long_window):
            l_ret = log_returns[ticker].astype(float)
            short_vol = l_ret.rolling(window=break_short_window, min_periods=break_short_window).std(ddof=1)
            prior_long_vol = (
                l_ret.shift(break_short_window)
                .rolling(window=break_long_window, min_periods=break_long_window)
                .std(ddof=1)
            )
            valid_denom = prior_long_vol > 1e-12
            vol_ratio = pd.Series(np.nan, index=l_ret.index, dtype=float)
            vol_ratio.loc[valid_denom] = short_vol.loc[valid_denom] / prior_long_vol.loc[valid_denom]

            last_flagged_pos = -break_short_window - 1
            for pos, (dt, ratio_val) in enumerate(vol_ratio.items()):
                if np.isfinite(ratio_val) and ratio_val >= break_vol_ratio_threshold:
                    if (pos - last_flagged_pos) >= break_short_window:
                        records.append(
                            {
                                "date": pd.Timestamp(dt),
                                "ticker": str(ticker),
                                "rule": "candidate_structural_break",
                                "value": float(ratio_val),
                                "action": "retain",
                            }
                        )
                        last_flagged_pos = pos

    # 4. Missing aligned risk-free observations
    if rf_daily is not None and not rf_daily.empty:
        for dt in rf_daily.index[rf_daily.isna()]:
            records.append(
                {
                    "date": pd.Timestamp(dt),
                    "ticker": "DTB3",
                    "rule": "missing_aligned_rf",
                    "value": np.nan,
                    "action": "mark_rf_kpis_unavailable_if_needed",
                }
            )

    if records:
        flags_df = pd.DataFrame(records, columns=list(QUALITY_FLAG_COLUMNS))
        flags_df["date"] = pd.to_datetime(flags_df["date"])
        flags_df["ticker"] = flags_df["ticker"].astype(str)
        flags_df["rule"] = flags_df["rule"].astype(str)
        flags_df["value"] = pd.to_numeric(flags_df["value"], errors="coerce").astype(float)
        flags_df["action"] = flags_df["action"].astype(str)
        flags_df = flags_df.sort_values(["date", "ticker", "rule"], kind="mergesort").reset_index(drop=True)
    else:
        flags_df = pd.DataFrame(
            {
                "date": pd.Series(dtype="datetime64[ns]"),
                "ticker": pd.Series(dtype="object"),
                "rule": pd.Series(dtype="object"),
                "value": pd.Series(dtype="float64"),
                "action": pd.Series(dtype="object"),
            },
            columns=list(QUALITY_FLAG_COLUMNS),
        )

    return flags_df


def _markdown_table(df: pd.DataFrame, *, float_fmt: str = "{:.6f}") -> str:
    """Format a small pandas DataFrame as a GitHub-flavored Markdown table without extra deps."""
    if df.empty:
        return "_None_\n"
    cols = [str(c) for c in df.columns]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines = [header, sep]
    for _, row in df.iterrows():
        cells: list[str] = []
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                cells.append("NaN")
            elif isinstance(val, (float, np.floating)):
                cells.append(float_fmt.format(float(val)))
            else:
                cells.append(str(val))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def generate_quality_report_markdown(
    bundle: DataBundle,
    adf_df: pd.DataFrame,
    simple_stats: pd.DataFrame,
    log_stats: pd.DataFrame,
    corr_df: pd.DataFrame,
) -> str:
    """Render a human-readable Markdown data-quality and stationarity report for the snapshot."""
    m = bundle.manifest
    excl = m.row_exclusions

    flag_summary = (
        bundle.quality_flags.groupby(["rule", "action"], dropna=False)
        .agg(count=("ticker", "count"), unique_tickers=("ticker", "nunique"))
        .reset_index()
        if not bundle.quality_flags.empty
        else pd.DataFrame(columns=["rule", "action", "count", "unique_tickers"])
    )

    per_ticker_flags = (
        bundle.quality_flags.pivot_table(
            index="ticker",
            columns="rule",
            values="action",
            aggfunc="count",
            fill_value=0,
        ).reset_index()
        if not bundle.quality_flags.empty
        else pd.DataFrame()
    )

    corr_disp = corr_df.reset_index().rename(columns={"index": "ticker"})
    adf_disp = adf_df[
        [
            "series",
            "n_obs",
            "adf_stat",
            "p_value",
            "used_lag",
            "crit_5pct",
            "reject_unit_root_5pct",
            "status",
        ]
    ]
    stats_disp = simple_stats[
        [
            "ticker",
            "n_obs",
            "ann_arithmetic_return",
            "ann_geometric_return",
            "ann_volatility",
            "skewness",
            "excess_kurtosis",
            "min",
            "max",
        ]
    ]
    log_disp = log_stats[
        [
            "ticker",
            "n_obs",
            "daily_mean",
            "daily_std",
            "ann_volatility",
            "skewness",
            "excess_kurtosis",
            "min",
            "max",
        ]
    ]

    lines = [
        f"# Quant Edge 1.0 — Data Snapshot & Quality Report (`{m.dataset_id}`)",
        "",
        "## 1. Snapshot Provenance & Bounds",
        f"- **Dataset ID:** `{m.dataset_id}`",
        f"- **Policy revision:** `{m.policy_revision}`",
        f"- **Parent dataset ID:** `{m.parent_dataset_id or 'none (primary download)'}`",
        f"- **Contract schema version:** `{m.schema_version}`",
        f"- **Retrieved / derived at (UTC):** `{m.retrieved_at_utc}`",
        f"- **Canonical tickers:** `{', '.join(m.tickers)}`",
        f"- **Requested start / end:** `{m.requested_start}` to `{m.requested_end or 'latest_available_frozen_on_snapshot'}`",
        f"- **First / last expected NYSE sessions:** `{excl.get('first_expected_nyse_session', m.actual_start)}` to `{excl.get('last_expected_nyse_session', m.actual_end)}`",
        f"- **Actual price session bounds:** `{m.actual_start}` to `{m.actual_end}` (`{len(bundle.prices)}` trading sessions on grid)",
        f"- **Complete 1-session return bounds:** `{bundle.simple_returns.index[0].strftime('%Y-%m-%d')}` to `{bundle.simple_returns.index[-1].strftime('%Y-%m-%d')}` (`{len(bundle.simple_returns)}` sessions)",
        f"- **Price adjustment policy:** `{m.price_adjustment}` (`yfinance` `auto_adjust=True`, where `Close` is the split- and dividend-adjusted close series)",
        f"- **Session calendar check:** {m.session_calendar_note}",
        "",
        "## 2. Boundary Coverage, Quarantine & Missing-Data Accounting vs. Retained Quality Flags",
        f"- **Total grid sessions (`prices`):** `{excl['n_price_grid_sessions']}`",
        f"- **Boundary coverage required:** `{excl.get('require_requested_boundary_coverage', True)}` (leading missing expected sessions: `{excl.get('n_leading_missing_expected_sessions', 0)}`, trailing missing expected sessions: `{excl.get('n_trailing_missing_expected_sessions', 0)}`, interior missing expected sessions: `{excl.get('n_interior_missing_expected_sessions', excl['n_missing_expected_nyse_sessions'])}`)",
        f"- **Expected NYSE sessions missing across all tickers:** `{excl['n_missing_expected_nyse_sessions']}`",
        f"- **Unexpected non-NYSE observed sessions (`policy={excl.get('unexpected_session_policy', 'quarantine')}`):** `{excl['n_unexpected_observed_sessions']}` (quarantined in `quarantined_unexpected_prices.parquet`, excluded from `prices` and returns)",
        f"- **Missing price cells `(date, ticker)`:** `{excl['n_missing_price_cells']}` (by ticker: `{excl['missing_price_cells_by_ticker']}`)",
        f"- **Initial price anchor row (`{m.actual_start}`):** `1` session (base price for first 1-day return; never filled with an artificial `0.0` return)",
        f"- **Post-anchor return rows excluded due to missing endpoints:** `{excl['n_excluded_return_rows']}`",
        f"- **Uninterrupted 1-session return series:** `{excl['uninterrupted_return_sessions']}`",
        f"- **Aligned forward-decision `DTB3` missing rows on return dates:** `{excl['n_missing_aligned_rf_rows']}`",
        "",
        "> **Hygiene rule:** Missing ETF prices are never forward-filled. Unexpected non-NYSE dates (such as vendor weekend rows) are quarantined for audit and excluded from the `prices` modelling grid. Returns are computed on the uncollapsed NYSE session grid first (`P_t / P_{t-1} - 1`), so any missing price invalidates both adjacent 1-session intervals rather than bridging a multi-day move as a 1-day return. Conversely, outlier and structural-break flags below **retain** all valid observations (`action='retain'`).",
        "",
        "### Quality Flag Counts by Rule",
        _markdown_table(flag_summary, float_fmt="{:.4f}"),
        "### Quality Flag Counts by Ticker",
        _markdown_table(per_ticker_flags, float_fmt="{:.0f}"),
        "## 3. Simple vs. Log Return Convention, Synchronous US Close Note & Risk-Free Proxies",
        "- **Simple returns (`simple_returns`):** Used for cross-sectional portfolio aggregation (`R_{p,t} = sum_i w_{i,t-} R_{i,t}`) and committee simple-loss risk (`L_t = -R_{p,t}`), because dollar NAV P&L aggregates linearly across holdings at horizon `t` whereas `sum_i w_i log(1 + R_{i,t}) != log(1 + R_{p,t})` (Jensen's inequality).",
        "- **Log returns (`log_returns = log1p(simple_returns)`):** Additive across time (`log(P_T / P_0) = sum_t r_t`), used for time-series statistical diagnostics (ADF stationarity tests, correlation tables, and volatility-regime screening).",
        "- **US exchange close vs. foreign underlying hours (`EFA`, `EEM`):** All seven ETFs trade synchronously on US exchanges through the `16:00 America/New_York` close, so portfolio execution and NAV valuation share a synchronous US close; however, `EFA` and `EEM` hold foreign equities whose local cash markets close earlier, meaning their `16:00 ET` ETF closes embed US afternoon price discovery / fair-value adjustments relative to local foreign closes.",
        f"- **Forward-decision risk-free proxy (`rf_daily.parquet`, policy `{m.rf_convention.get('alignment_policy')}`):** `{m.rf_convention['series']}` quoted in `{m.rf_convention['quote_basis']}`, converted via `{m.rf_convention['conversion_formula']}` (`no_backfill = {m.rf_convention['no_backfill']}`). {m.rf_convention['lag_rule']}",
        f"- **Contemporaneous ex-post risk-free proxy (`rf_daily_ex_post.parquet`):** Matches `obs_date <= t` strictly for ex-post reference (never for forward decisions); differs from `rf_daily` on `{m.rf_convention.get('n_days_forward_differs_from_ex_post', 0)}` of `{len(bundle.simple_returns)}` return sessions.",
        f"- **Publication & vintage limitation:** {m.rf_convention['limitation_note']}",
        *_rf_evidence_report_lines(m),
        "",
        "## 4. Augmented Dickey-Fuller (ADF) Stationarity Diagnostics on Log Returns",
        "> **Interpretation caveat:** Rejecting the unit-root null (`p < 0.05`) supports level/mean stationarity (`I(0)`) of daily log returns; it does **not** imply i.i.d. returns, Gaussian tails, or constant conditional variance (volatility clustering remains prominent).",
        "",
        _markdown_table(adf_disp, float_fmt="{:.6g}"),
        "## 5. Descriptive Statistics — Simple Returns (Fractions)",
        _markdown_table(stats_disp, float_fmt="{:.6f}"),
        "## 6. Descriptive Statistics — Log Returns (Fractions)",
        _markdown_table(log_disp, float_fmt="{:.6f}"),
        "## 7. Full-Sample Log-Return Correlation Matrix",
        _markdown_table(corr_disp, float_fmt="{:.4f}"),
    ]
    return "\n".join(lines)


def _rf_evidence_report_lines(m: DataManifest) -> list[str]:
    """Render the coverage and conversion lines of a versioned RF snapshot's quality report."""
    coverage = m.rf_convention.get("evidence_coverage")
    if not coverage:
        return []
    return [
        f"- **Evidence coverage of selected RF values (`rf_provenance.parquet`):** `{coverage}`",
        (
            f"- **Conversion sensitivity (`{m.rf_convention['accrual_sensitivity_file']}`):** "
            f"{m.rf_convention['accrual_sensitivity_note']}"
        ),
    ]


def _rf_policy_revision(rf_alignment_policy: str) -> str:
    """Return the snapshot policy revision implied by the configured RF policy."""
    return POLICY_REVISION_R3 if rf_alignment_policy == RF_POLICY_R3 else POLICY_REVISION_R2


def _rf_policy_to_mode(rf_alignment_policy: str) -> RFAlignmentMode:
    """Map configuration ``rf_alignment_policy`` identifier to ``align_risk_free_rate`` mode."""
    if rf_alignment_policy in (RF_POLICY_R2, RF_POLICY_R3):
        return "forward_decision"
    if rf_alignment_policy == "ex_post_same_date":
        return "ex_post"
    if rf_alignment_policy == "legacy_bday_lag":
        return "legacy_bday_lag"
    raise ValueError(f"Unsupported rf_alignment_policy: {rf_alignment_policy!r}")


def _resolve_config_and_base_dir(
    config: AppConfig | dict[str, Any] | Path | str,
    repo_root: Path | None,
) -> tuple[AppConfig, Path]:
    """Normalize ``config`` into ``AppConfig`` and determine base directory for relative data paths."""
    if isinstance(config, AppConfig):
        base_dir = repo_root if repo_root is not None else DEFAULT_CONFIG_PATH.parent
        return config, base_dir
    if isinstance(config, (Path, str)):
        cfg_path = Path(config).resolve()
        cfg = load_config(cfg_path)
        base_dir = repo_root if repo_root is not None else cfg_path.parent
        return cfg, base_dir
    if isinstance(config, dict):
        cfg = _validate_raw_config(config)
        base_dir = repo_root if repo_root is not None else DEFAULT_CONFIG_PATH.parent
        return cfg, base_dir
    raise TypeError(f"Unsupported config argument type: {type(config)!r}")


def _resolve_dir(path_str: str, base_dir: Path) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (base_dir / p).resolve()


def _download_etf_adjusted_closes(cfg: AppConfig) -> pd.DataFrame:
    """Download 7-ETF adjusted closes from Yahoo Finance using ``auto_adjust=True``."""
    end_arg: str | None = None
    if cfg.data.frozen_end_date is not None:
        # yfinance end bound is exclusive; add 1 calendar day then slice <= frozen_end_date.
        excl_end = pd.Timestamp(cfg.data.frozen_end_date) + pd.Timedelta(days=1)
        end_arg = excl_end.strftime("%Y-%m-%d")

    try:
        raw_yf = yf.download(
            tickers=list(cfg.mandate.canonical_tickers),
            start=cfg.data.requested_start,
            end=end_arg,
            auto_adjust=True,
            actions=False,
            repair=False,
            keepna=True,
            progress=False,
            group_by="column",
            threads=False,
            multi_level_index=True,
            timeout=30,
        )
    except Exception as exc:
        raise DataUnavailableError(f"Yahoo Finance download failed: {exc}") from exc

    if raw_yf is None or raw_yf.empty:
        raise DataUnavailableError("Yahoo Finance returned no price rows.")

    closes = extract_adjusted_closes(raw_yf, tickers=cfg.mandate.canonical_tickers)
    closes = closes.loc[closes.index >= pd.Timestamp(cfg.data.requested_start)].copy()
    if cfg.data.frozen_end_date is not None:
        closes = closes.loc[closes.index <= pd.Timestamp(cfg.data.frozen_end_date)].copy()
    if len(closes) < 2:
        raise DataUnavailableError("Insufficient ETF price rows returned for requested date bounds.")
    return closes


def _download_fred_dtb3(cfg: AppConfig) -> pd.DataFrame:
    """Download raw FRED ``DTB3`` annual-percent observations over HTTPS."""
    try:
        resp = requests.get(cfg.data.fred_csv_url, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        raise DataUnavailableError(f"FRED DTB3 download failed from {cfg.data.fred_csv_url}: {exc}") from exc
    return parse_fred_dtb3_csv(resp.text)


def _build_dataset_id(
    cfg: AppConfig,
    actual_end: str,
    prices: pd.DataFrame,
    raw_rf: pd.DataFrame | None,
    *,
    policy_revision: str = POLICY_REVISION_R2,
) -> str:
    """Compute a deterministic policy-aware dataset identifier from bounds, policy, and content hashes."""
    hasher = hashlib.sha256()
    policy_meta = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "policy_revision": policy_revision,
        "price_adjustment": cfg.data.price_adjustment,
        "unexpected_session_policy": cfg.data.unexpected_session_policy,
        "require_requested_boundary_coverage": cfg.data.require_requested_boundary_coverage,
        "rf_alignment_policy": cfg.data.rf_alignment_policy,
        "rf_availability_lag_sessions": cfg.data.rf_availability_lag_sessions,
        "rf_trading_days_per_year": cfg.data.rf_trading_days_per_year,
        "rf_decision_timezone": cfg.data.rf_decision_timezone,
        "rf_decision_cutoff_time": cfg.data.rf_decision_cutoff_time,
        "rf_release_time": cfg.data.rf_release_time,
    }
    if cfg.data.rf_alignment_policy == RF_POLICY_R3:
        policy_meta["rf_evidence_sha256"] = cfg.data.rf_evidence_sha256
    hasher.update(json.dumps(policy_meta, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    hasher.update(prices.to_csv(float_format="%.12g").encode("utf-8"))
    if raw_rf is not None and not raw_rf.empty:
        hasher.update(raw_rf.to_csv(float_format="%.12g").encode("utf-8"))
    short_sha = hasher.hexdigest()[:10]
    s_clean = cfg.data.requested_start.replace("-", "")
    e_clean = actual_end.replace("-", "")
    revision_tag = policy_revision.split("_", 1)[0]
    return f"qe1_{s_clean}_{e_clean}_{revision_tag}_{short_sha}"


def _persist_snapshot(
    *,
    cfg: AppConfig,
    base_dir: Path,
    raw_dir: Path,
    processed_dir: Path,
    observed_prices: pd.DataFrame,
    raw_rf_trimmed: pd.DataFrame | None,
    grid_prices: pd.DataFrame,
    quarantined_prices: pd.DataFrame,
    missing_expected_sessions: pd.DatetimeIndex,
    unexpected_sessions: pd.DatetimeIndex,
    simple_returns: pd.DataFrame,
    log_returns: pd.DataFrame,
    excluded_return_rows: pd.DataFrame,
    rf_daily: pd.Series,
    ex_post_rf_daily: pd.Series,
    quality_flags: pd.DataFrame,
    retrieved_at_utc: str,
    policy_revision: str = POLICY_REVISION_R2,
    parent_dataset_id: str | None = None,
    extra_notes: Sequence[str] = (),
    rf_version_table: pd.DataFrame | None = None,
    rf_provenance: pd.DataFrame | None = None,
    rf_accrual_sensitivity: pd.Series | None = None,
    activate: bool = True,
) -> DataBundle:
    """Write raw & processed snapshot files, compute SHA-256 hashes, and write ``manifest.json``.

    With ``activate=False`` the snapshot is a candidate: the active pointer is left unchanged.
    """
    actual_start = grid_prices.index[0].strftime("%Y-%m-%d")
    actual_end = grid_prices.index[-1].strftime("%Y-%m-%d")

    dataset_id = _build_dataset_id(
        cfg,
        actual_end,
        grid_prices,
        raw_rf_trimmed,
        policy_revision=policy_revision,
    )
    if parent_dataset_id is not None and dataset_id == parent_dataset_id:
        raise ValueError(
            f"Derived snapshot dataset_id ({dataset_id}) collided with preserved parent_dataset_id."
        )

    snap_raw_dir = raw_dir / dataset_id
    snap_proc_dir = processed_dir / dataset_id
    snap_raw_dir.mkdir(parents=True, exist_ok=True)
    snap_proc_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[Path] = []

    if rf_version_table is not None:
        versions_path = snap_raw_dir / "dtb3_rf_versions.parquet"
        rf_version_table.to_parquet(versions_path, engine="pyarrow", index=False)
        written_files.append(versions_path)
    if rf_provenance is not None:
        provenance_path = snap_proc_dir / "rf_provenance.parquet"
        rf_provenance.to_parquet(provenance_path, engine="pyarrow", index=True)
        written_files.append(provenance_path)
    if rf_accrual_sensitivity is not None:
        accrual_path = snap_proc_dir / "rf_daily_accrual_91d_sensitivity.parquet"
        rf_accrual_sensitivity.to_frame().to_parquet(accrual_path, engine="pyarrow", index=True)
        written_files.append(accrual_path)

    raw_prices_path = snap_raw_dir / "etf_prices_raw.parquet"
    observed_prices.to_parquet(raw_prices_path, engine="pyarrow", index=True)
    written_files.append(raw_prices_path)

    if raw_rf_trimmed is not None:
        raw_rf_path = snap_raw_dir / "fred_dtb3_raw.parquet"
        raw_rf_trimmed.to_parquet(raw_rf_path, engine="pyarrow", index=True)
        written_files.append(raw_rf_path)

    prices_path = snap_proc_dir / "prices.parquet"
    quarantined_path = snap_proc_dir / "quarantined_unexpected_prices.parquet"
    simple_path = snap_proc_dir / "simple_returns.parquet"
    log_path = snap_proc_dir / "log_returns.parquet"
    rf_path = snap_proc_dir / "rf_daily.parquet"
    rf_ex_post_path = snap_proc_dir / "rf_daily_ex_post.parquet"
    flags_path = snap_proc_dir / "quality_flags.parquet"
    excl_path = snap_proc_dir / "excluded_return_rows.parquet"

    quarantined_to_save = quarantined_prices.copy()
    quarantined_to_save.index = _normalize_session_index(quarantined_to_save.index)
    for tkr in grid_prices.columns:
        if tkr in quarantined_to_save.columns:
            quarantined_to_save[tkr] = pd.to_numeric(
                quarantined_to_save[tkr], errors="coerce"
            ).astype(float)
    quarantined_to_save = quarantined_to_save.reindex(columns=list(grid_prices.columns)).astype(float)

    grid_prices.to_parquet(prices_path, engine="pyarrow", index=True)
    quarantined_to_save.to_parquet(quarantined_path, engine="pyarrow", index=True)
    simple_returns.to_parquet(simple_path, engine="pyarrow", index=True)
    log_returns.to_parquet(log_path, engine="pyarrow", index=True)
    rf_daily.to_frame(name="rf_daily").to_parquet(rf_path, engine="pyarrow", index=True)
    ex_post_rf_daily.to_frame(name="rf_daily_ex_post").to_parquet(
        rf_ex_post_path, engine="pyarrow", index=True
    )
    quality_flags.to_parquet(flags_path, engine="pyarrow", index=False)

    excl_to_save = excluded_return_rows.copy()
    if excl_to_save.empty:
        excl_to_save = pd.DataFrame(
            {
                "date": pd.Series(dtype="datetime64[ns]"),
                "session_position": pd.Series(dtype="int64"),
                "missing_price_tickers_t": pd.Series(dtype="object"),
                "missing_price_tickers_t_minus_1": pd.Series(dtype="object"),
                "invalid_return_tickers": pd.Series(dtype="object"),
                "n_invalid_tickers": pd.Series(dtype="int64"),
                "reason": pd.Series(dtype="object"),
            },
            columns=list(EXCLUDED_RETURN_COLUMNS),
        )
    else:
        excl_to_save["date"] = pd.to_datetime(excl_to_save["date"])
    excl_to_save.to_parquet(excl_path, engine="pyarrow", index=False)

    written_files.extend(
        [
            prices_path,
            quarantined_path,
            simple_path,
            log_path,
            rf_path,
            rf_ex_post_path,
            flags_path,
            excl_path,
        ]
    )

    # Diagnostics & quality summary artifacts
    adf_df = run_stationarity_diagnostics(
        {ticker: log_returns[ticker] for ticker in log_returns.columns}
    )
    simple_stats = compute_return_descriptive_stats(
        simple_returns,
        return_kind="simple",
        annualization_days=cfg.portfolio.annualization_days,
    )
    log_stats = compute_return_descriptive_stats(
        log_returns,
        return_kind="log",
        annualization_days=cfg.portfolio.annualization_days,
    )
    corr_df = log_returns.corr()

    adf_path = snap_proc_dir / "adf_stationarity.csv"
    s_stats_path = snap_proc_dir / "descriptive_stats_simple.csv"
    l_stats_path = snap_proc_dir / "descriptive_stats_log.csv"
    corr_path = snap_proc_dir / "log_return_correlations.csv"

    adf_df.to_csv(adf_path, index=False)
    simple_stats.to_csv(s_stats_path, index=False)
    log_stats.to_csv(l_stats_path, index=False)
    corr_df.to_csv(corr_path, index=True)
    written_files.extend([adf_path, s_stats_path, l_stats_path, corr_path])

    grid_diag: dict[str, Any] = dict(grid_prices.attrs.get("session_grid_diagnostics", {}))
    missing_by_ticker = {str(t): int(grid_prices[t].isna().sum()) for t in grid_prices.columns}
    row_exclusions: dict[str, Any] = {
        "n_price_grid_sessions": int(len(grid_prices)),
        "n_initial_anchor_rows": 1,
        "require_requested_boundary_coverage": bool(cfg.data.require_requested_boundary_coverage),
        "first_expected_nyse_session": str(grid_diag.get("first_expected_session", actual_start)),
        "last_expected_nyse_session": str(grid_diag.get("last_expected_session", actual_end)),
        "n_leading_missing_expected_sessions": int(grid_diag.get("n_leading_missing_sessions", 0)),
        "leading_missing_expected_dates": list(grid_diag.get("leading_missing_sessions", [])),
        "n_trailing_missing_expected_sessions": int(
            grid_diag.get("n_trailing_missing_sessions", 0)
        ),
        "trailing_missing_expected_dates": list(grid_diag.get("trailing_missing_sessions", [])),
        "n_interior_missing_expected_sessions": int(
            grid_diag.get("n_interior_missing_sessions", len(missing_expected_sessions))
        ),
        "first_session_missing_tickers": list(grid_diag.get("first_session_missing_tickers", [])),
        "last_session_missing_tickers": list(grid_diag.get("last_session_missing_tickers", [])),
        "n_missing_expected_nyse_sessions": int(len(missing_expected_sessions)),
        "missing_expected_nyse_dates": [d.strftime("%Y-%m-%d") for d in missing_expected_sessions],
        "unexpected_session_policy": cfg.data.unexpected_session_policy,
        "n_unexpected_observed_sessions": int(len(unexpected_sessions)),
        "unexpected_observed_dates": [d.strftime("%Y-%m-%d") for d in unexpected_sessions],
        "n_quarantined_unexpected_sessions": int(len(quarantined_to_save)),
        "quarantined_unexpected_dates": [
            d.strftime("%Y-%m-%d") for d in quarantined_to_save.index
        ],
        "n_missing_price_cells": int(grid_prices.isna().sum().sum()),
        "missing_price_cells_by_ticker": missing_by_ticker,
        "n_rows_with_any_missing_price": int(grid_prices.isna().any(axis=1).sum()),
        "n_excluded_return_rows": int(len(excluded_return_rows)),
        "n_complete_return_rows": int(len(simple_returns)),
        "uninterrupted_return_sessions": bool(excluded_return_rows.empty),
        "n_missing_aligned_rf_rows": int(rf_daily.isna().sum()),
        "n_missing_ex_post_rf_rows": int(ex_post_rf_daily.isna().sum()),
        "n_raw_rf_missing_dot_rows": (
            int(raw_rf_trimmed["rate_annual_pct"].isna().sum())
            if raw_rf_trimmed is not None
            else None
        ),
    }

    both_rf_valid = rf_daily.notna() & ex_post_rf_daily.notna()
    n_rf_diff_days = int(
        (
            both_rf_valid
            & ~np.isclose(
                rf_daily.to_numpy(dtype=float),
                ex_post_rf_daily.to_numpy(dtype=float),
                rtol=0.0,
                atol=1e-15,
                equal_nan=True,
            )
        ).sum()
    )

    if cfg.data.rf_alignment_policy == RF_POLICY_R3:
        release_calendar = (
            "evidence_calendar_documented_and_inferred_no_release_days_alfred_listed_good_fridays"
        )
        verification = "day_level_vintage_and_notice_evidence_intraday_unverified"
        lag_rule = (
            f"Decision cutoff for return session t is the preceding NYSE session close at "
            f"{cfg.data.rf_decision_cutoff_time} {cfg.data.rf_decision_timezone}. Each DTB3 "
            f"observation version is usable from {cfg.data.rf_release_time} "
            f"{cfg.data.rf_decision_timezone} on its availability date. From the daily-vintage era "
            f"that date is the latest of the evidence calendar, the ALFRED vintage date, and any "
            f"documented omission date; sparse early history keeps the schedule calendar as a "
            f"labelled fallback. At each cutoff the most recent eligible observation is selected, "
            f"using its latest eligible version, with zero backfill."
        )
        limitation_note = (
            "DTB3 is quoted in annual percent on a 360-day bank-discount basis; "
            "(rate_pct / 100.0) / 252 is an approximate trading-day risk-free proxy, not an exact "
            "realized T-bill holding-period return. Availability is day-level evidence, not a "
            "verified intraday first-release time: ALFRED vintage dates can trail or precede the "
            "source release. Sparse history before the daily-vintage era is a labelled calendar "
            "fallback, and cases marked inferred or unresolved in rf_provenance.parquet are not "
            "proven. This is not exact historical point-in-time data."
        )
    else:
        release_calendar = (
            "us_federal_reserve_h15_opm_holidays_plus_good_friday_and_special_closures"
        )
        verification = "unverified_schedule_proxy_alfred_vintages_not_fetched"
        lag_rule = (
            f"Decision cutoff for return session t is the preceding NYSE session close at "
            f"{cfg.data.rf_decision_cutoff_time} {cfg.data.rf_decision_timezone}. Under "
            f"policy={cfg.data.rf_alignment_policy}, observation dated d becomes usable on the "
            f"{cfg.data.rf_availability_lag_sessions}-th Federal Reserve H.15 publication "
            f"business day strictly after d at {cfg.data.rf_release_time} "
            f"{cfg.data.rf_decision_timezone}, requiring available_at <= decision_time "
            f"(backward merge_asof; zero backfill). Contemporaneous ex-post proxy (obs_date <= t) "
            f"is stored separately in rf_daily_ex_post.parquet."
        )
        limitation_note = (
            "DTB3 is quoted in annual percent on a 360-day bank-discount basis; "
            "(rate_pct / 100.0) / 252 is an approximate trading-day risk-free proxy, not an "
            "exact realized T-bill holding-period return. Historical first-release timestamps "
            "and ALFRED vintage revisions were NOT individually verified across 2004-2026; "
            "forward-decision availability uses a Federal Reserve H.15 16:15 America/New_York "
            "schedule proxy and US federal holiday calendar, which misses Board closures and "
            "omitted Treasury data."
        )

    rf_convention: dict[str, Any] = {
        "series": cfg.data.fred_rf_series,
        "quote_basis": cfg.data.rf_quote_basis,
        "conversion_formula": cfg.data.rf_conversion_formula,
        "trading_days_per_year": cfg.data.rf_trading_days_per_year,
        "alignment_policy": cfg.data.rf_alignment_policy,
        "availability_lag_sessions": cfg.data.rf_availability_lag_sessions,
        "decision_timezone": cfg.data.rf_decision_timezone,
        "decision_cutoff_time": cfg.data.rf_decision_cutoff_time,
        "assumed_h15_release_time": cfg.data.rf_release_time,
        "release_calendar": release_calendar,
        "release_timestamp_verification": verification,
        "ex_post_series_file": "rf_daily_ex_post.parquet",
        "n_days_forward_differs_from_ex_post": n_rf_diff_days,
        "lag_rule": lag_rule,
        "no_backfill": cfg.data.rf_no_backfill,
        "limitation_note": limitation_note,
    }
    if rf_version_table is not None and rf_provenance is not None:
        rf_convention.update(
            {
                "evidence_sha256": cfg.data.rf_evidence_sha256,
                "evidence_source_path": cfg.data.rf_evidence_path,
                "evidence_coverage": {
                    "selected_sessions_by_tier": rf_provenance["evidence_tier"].value_counts().to_dict(),
                    "selected_sessions_by_status": rf_provenance["coverage_status"].value_counts().to_dict(),
                    "versions_by_tier": rf_version_table["evidence_tier"].value_counts().to_dict(),
                    "versions_by_kind": rf_version_table["version_kind"].value_counts().to_dict(),
                },
                "accrual_sensitivity_file": "rf_daily_accrual_91d_sensitivity.parquet",
                "accrual_sensitivity_note": (
                    "91-day bill accrual on the same selected quotes, (1/P)^(calendar_days/91)-1 with "
                    "P=1-d*91/360. A labelled conversion sensitivity under a fixed-term assumption, "
                    "not the primary RF and not an exact realized Treasury return."
                ),
            }
        )

    cal_note = (
        f"Expected NYSE sessions in requested window [{cfg.data.requested_start}, "
        f"{cfg.data.frozen_end_date or actual_end}]: {len(grid_prices)} "
        f"([{row_exclusions['first_expected_nyse_session']}, "
        f"{row_exclusions['last_expected_nyse_session']}]); "
        f"leading missing: {row_exclusions['n_leading_missing_expected_sessions']}, "
        f"trailing missing: {row_exclusions['n_trailing_missing_expected_sessions']}, "
        f"interior missing: {row_exclusions['n_interior_missing_expected_sessions']}; "
        f"quarantined unexpected non-NYSE dates: {len(quarantined_to_save)}."
    )

    prelim_manifest = DataManifest(
        dataset_id=dataset_id,
        schema_version=CONTRACT_SCHEMA_VERSION,
        requested_start=cfg.data.requested_start,
        requested_end=cfg.data.frozen_end_date,
        actual_start=actual_start,
        actual_end=actual_end,
        retrieved_at_utc=retrieved_at_utc,
        tickers=tuple(cfg.mandate.canonical_tickers),
        source_urls={
            "etf_prices": "https://finance.yahoo.com (via yfinance.download, auto_adjust=True)",
            "risk_free": cfg.data.fred_csv_url,
        },
        price_adjustment=cfg.data.price_adjustment,
        row_exclusions=row_exclusions,
        file_sha256={},
        rf_convention=rf_convention,
        session_calendar_note=cal_note,
        offline_cache_used=False,
        notes=tuple(extra_notes),
        policy_revision=policy_revision,
        parent_dataset_id=parent_dataset_id,
    )

    prelim_bundle = DataBundle(
        prices=grid_prices,
        simple_returns=simple_returns,
        log_returns=log_returns,
        rf_daily=rf_daily,
        quality_flags=quality_flags,
        manifest=prelim_manifest,
        raw_rf_quotes=raw_rf_trimmed,
        excluded_return_rows=excl_to_save,
        ex_post_rf_daily=ex_post_rf_daily,
        quarantined_prices=quarantined_to_save,
        rf_provenance=rf_provenance,
        rf_accrual_sensitivity=rf_accrual_sensitivity,
    )

    report_md = generate_quality_report_markdown(
        prelim_bundle,
        adf_df=adf_df,
        simple_stats=simple_stats,
        log_stats=log_stats,
        corr_df=corr_df,
    )
    report_path = snap_proc_dir / "quality_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    written_files.append(report_path)

    file_sha256: dict[str, str] = {}
    for fpath in sorted(written_files):
        try:
            rel_key = fpath.resolve().relative_to(base_dir.resolve()).as_posix()
        except ValueError:
            rel_key = fpath.name
        file_sha256[rel_key] = _sha256_file(fpath)

    final_manifest = replace(prelim_manifest, file_sha256=file_sha256)
    manifest_path = snap_proc_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(final_manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if activate:
        _write_active_pointer(processed_dir, final_manifest, cfg.data.rf_alignment_policy)

    return replace(prelim_bundle, manifest=final_manifest)


def _write_active_pointer(
    processed_dir: Path,
    manifest: DataManifest,
    rf_alignment_policy: str,
) -> None:
    """Point ``active_snapshot.json`` at ``manifest``'s snapshot."""
    pointer_payload = {
        "dataset_id": manifest.dataset_id,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "policy_revision": manifest.policy_revision,
        "parent_dataset_id": manifest.parent_dataset_id,
        "rf_alignment_policy": rf_alignment_policy,
        "manifest_relpath": f"{manifest.dataset_id}/manifest.json",
        "actual_start": manifest.actual_start,
        "actual_end": manifest.actual_end,
        "retrieved_at_utc": manifest.retrieved_at_utc,
    }
    (processed_dir / "active_snapshot.json").write_text(
        json.dumps(pointer_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def activate_snapshot(
    config: AppConfig | dict[str, Any] | Path | str,
    *,
    dataset_id: str,
    repo_root: Path | None = None,
) -> DataBundle:
    """Point the active snapshot at ``dataset_id`` after it loads as the configured policy's cache.

    Loading re-verifies every SHA-256 hash and logical index, so a tampered or policy-mismatched
    candidate is refused and the existing pointer is left unchanged.
    """
    cfg, base_dir = _resolve_config_and_base_dir(config, repo_root)
    processed_dir = _resolve_dir(cfg.data.processed_dir, base_dir)
    bundle = load_data(cfg, offline=True, repo_root=base_dir)
    if bundle.manifest.dataset_id != dataset_id:
        raise DataUnavailableError(
            f"Configured policy resolves to {bundle.manifest.dataset_id}, not {dataset_id}."
        )
    _write_active_pointer(processed_dir, bundle.manifest, cfg.data.rf_alignment_policy)
    return bundle


def _validate_cached_bundle_tables(
    *,
    dataset_id: str,
    cfg: AppConfig,
    prices: pd.DataFrame,
    simple_returns: pd.DataFrame,
    log_returns: pd.DataFrame,
    rf_frame: pd.DataFrame,
    rf_ex_post_frame: pd.DataFrame | None,
    rf_provenance: pd.DataFrame | None = None,
    rf_accrual_frame: pd.DataFrame | None = None,
) -> tuple[pd.Series, pd.Series | None]:
    """Validate logical indices and columns of SHA-256-verified cached parquet tables.

    Never overwrites ``rf_daily.index`` positionally; any mismatched or non-DatetimeIndex
    ``rf_daily`` / ``rf_daily_ex_post`` / ``log_returns`` index, or provenance that disagrees
    with ``rf_daily``, raises ``DataUnavailableError``.
    """
    canonical_cols = tuple(cfg.mandate.canonical_tickers)
    if tuple(prices.columns) != canonical_cols:
        raise DataUnavailableError(
            f"Cached snapshot {dataset_id} has invalid prices columns {tuple(prices.columns)}."
        )
    if (
        not isinstance(prices.index, pd.DatetimeIndex)
        or prices.index.tz is not None
        or not prices.index.is_monotonic_increasing
        or not prices.index.is_unique
    ):
        raise DataUnavailableError(
            f"Cached snapshot {dataset_id} has invalid or non-monotonic prices DatetimeIndex."
        )

    expected_end_bound = (
        cfg.data.frozen_end_date
        if cfg.data.frozen_end_date is not None
        else prices.index[-1].strftime("%Y-%m-%d")
    )
    expected_sessions = expected_nyse_sessions(cfg.data.requested_start, expected_end_bound)
    unexpected_in_grid = prices.index.difference(expected_sessions)
    if len(unexpected_in_grid) > 0:
        raise DataUnavailableError(
            f"Cached snapshot {dataset_id} contains unexpected non-NYSE dates in prices grid: "
            f"{[d.strftime('%Y-%m-%d') for d in unexpected_in_grid[:5]]}."
        )
    if cfg.data.require_requested_boundary_coverage:
        if not prices.index.equals(expected_sessions):
            raise DataUnavailableError(
                f"Cached snapshot {dataset_id} prices index [{prices.index[0].strftime('%Y-%m-%d')}, "
                f"{prices.index[-1].strftime('%Y-%m-%d')}] ({len(prices)} rows) does not match "
                f"expected NYSE sessions [{expected_sessions[0].strftime('%Y-%m-%d')}, "
                f"{expected_sessions[-1].strftime('%Y-%m-%d')}] ({len(expected_sessions)} rows)."
            )
        if bool(prices.iloc[0].isna().any()) or bool(prices.iloc[-1].isna().any()):
            raise DataUnavailableError(
                f"Cached snapshot {dataset_id} is missing ticker observations on boundary NYSE sessions."
            )

    if tuple(simple_returns.columns) != canonical_cols or tuple(log_returns.columns) != canonical_cols:
        raise DataUnavailableError(
            f"Cached snapshot {dataset_id} has invalid return columns."
        )
    if (
        not isinstance(simple_returns.index, pd.DatetimeIndex)
        or simple_returns.index.tz is not None
        or not simple_returns.index.is_monotonic_increasing
        or not simple_returns.index.is_unique
    ):
        raise DataUnavailableError(
            f"Cached snapshot {dataset_id} has invalid simple_returns DatetimeIndex."
        )
    if not isinstance(log_returns.index, pd.DatetimeIndex) or not log_returns.index.equals(
        simple_returns.index
    ):
        raise DataUnavailableError(
            f"Cached snapshot {dataset_id} failed logical index validation: "
            f"log_returns.parquet index does not match simple_returns.parquet index."
        )

    if "rf_daily" not in rf_frame.columns:
        raise DataUnavailableError(
            f"Cached snapshot {dataset_id} rf_daily.parquet is missing 'rf_daily' column."
        )
    if (
        not isinstance(rf_frame.index, pd.DatetimeIndex)
        or rf_frame.index.tz is not None
        or not rf_frame.index.equals(simple_returns.index)
    ):
        raise DataUnavailableError(
            f"Cached snapshot {dataset_id} failed logical index validation: "
            f"rf_daily.parquet index does not match simple_returns.parquet index."
        )
    rf_daily = rf_frame["rf_daily"].astype(float).copy()
    rf_daily.name = "rf_daily"

    ex_post_rf_daily: pd.Series | None = None
    if rf_ex_post_frame is not None:
        if "rf_daily_ex_post" not in rf_ex_post_frame.columns:
            raise DataUnavailableError(
                f"Cached snapshot {dataset_id} rf_daily_ex_post.parquet is missing 'rf_daily_ex_post' column."
            )
        if (
            not isinstance(rf_ex_post_frame.index, pd.DatetimeIndex)
            or rf_ex_post_frame.index.tz is not None
            or not rf_ex_post_frame.index.equals(simple_returns.index)
        ):
            raise DataUnavailableError(
                f"Cached snapshot {dataset_id} failed logical index validation: "
                f"rf_daily_ex_post.parquet index does not match simple_returns.parquet index."
            )
        ex_post_rf_daily = rf_ex_post_frame["rf_daily_ex_post"].astype(float).copy()
        ex_post_rf_daily.name = "rf_daily_ex_post"

    for name, frame in (("rf_provenance", rf_provenance), ("rf_accrual", rf_accrual_frame)):
        if frame is not None and not frame.index.equals(simple_returns.index):
            raise DataUnavailableError(
                f"Cached snapshot {dataset_id} failed logical index validation: "
                f"{name} index does not match simple_returns.parquet index."
            )
    if rf_provenance is not None and not np.array_equal(
        rf_provenance["rf_daily"].to_numpy(dtype=float),
        rf_daily.to_numpy(dtype=float),
        equal_nan=True,
    ):
        raise DataUnavailableError(
            f"Cached snapshot {dataset_id} rf_provenance disagrees with rf_daily.parquet."
        )

    return rf_daily, ex_post_rf_daily


def _try_load_verified_cache(
    *,
    cfg: AppConfig,
    base_dir: Path,
    raw_dir: Path,
    processed_dir: Path,
    offline_flag: bool,
    fallback_warning: str | None = None,
) -> DataBundle | None:
    """Locate, policy-match, SHA-256-verify, and logically index-validate a snapshot on disk."""
    if not processed_dir.exists():
        return None

    candidate_manifests: list[Path] = []
    pointer_path = processed_dir / "active_snapshot.json"
    if pointer_path.exists():
        try:
            ptr = json.loads(pointer_path.read_text(encoding="utf-8"))
            rel = ptr.get("manifest_relpath")
            if rel:
                p = processed_dir / str(rel)
                if p.exists():
                    candidate_manifests.append(p)
        except Exception:
            pass

    for p in sorted(processed_dir.glob("*/manifest.json"), reverse=True):
        if p not in candidate_manifests:
            candidate_manifests.append(p)

    expected_last_nyse: str | None = None
    if cfg.data.frozen_end_date is not None:
        exp_cal = expected_nyse_sessions(cfg.data.requested_start, cfg.data.frozen_end_date)
        if len(exp_cal) == 0:
            raise DataUnavailableError(
                f"Requested date window [{cfg.data.requested_start}, {cfg.data.frozen_end_date}] "
                f"contains zero expected NYSE sessions."
            )
        expected_last_nyse = exp_cal[-1].strftime("%Y-%m-%d")

    for manifest_path in candidate_manifests:
        try:
            raw_m = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if raw_m.get("schema_version") != CONTRACT_SCHEMA_VERSION:
            continue
        if tuple(raw_m.get("tickers", ())) != tuple(cfg.mandate.canonical_tickers):
            continue
        if raw_m.get("requested_start") != cfg.data.requested_start:
            continue
        if raw_m.get("price_adjustment") != cfg.data.price_adjustment:
            continue

        row_excl = raw_m.get("row_exclusions", {})
        if row_excl.get("unexpected_session_policy") != cfg.data.unexpected_session_policy:
            continue
        if bool(row_excl.get("require_requested_boundary_coverage", True)) != bool(
            cfg.data.require_requested_boundary_coverage
        ):
            continue

        rf_conv = raw_m.get("rf_convention", {})
        if (
            rf_conv.get("series") != cfg.data.fred_rf_series
            or int(rf_conv.get("trading_days_per_year", -1)) != cfg.data.rf_trading_days_per_year
            or int(rf_conv.get("availability_lag_sessions", -1))
            != cfg.data.rf_availability_lag_sessions
            or rf_conv.get("alignment_policy") != cfg.data.rf_alignment_policy
            or rf_conv.get("decision_timezone") != cfg.data.rf_decision_timezone
            or rf_conv.get("decision_cutoff_time") != cfg.data.rf_decision_cutoff_time
            or rf_conv.get("assumed_h15_release_time") != cfg.data.rf_release_time
        ):
            continue
        if raw_m.get("policy_revision") != _rf_policy_revision(cfg.data.rf_alignment_policy):
            continue
        if (
            cfg.data.rf_alignment_policy == RF_POLICY_R3
            and rf_conv.get("evidence_sha256") != cfg.data.rf_evidence_sha256
        ):
            continue

        if expected_last_nyse is not None and raw_m.get("actual_end") != expected_last_nyse:
            continue

        # Verify SHA-256 integrity of every recorded snapshot file
        file_sha256: dict[str, str] = dict(raw_m.get("file_sha256", {}))
        if not file_sha256:
            continue

        checksum_ok = True
        for rel_key, expected_sha in file_sha256.items():
            target_file = (base_dir / Path(rel_key)).resolve()
            if not target_file.exists():
                target_file = manifest_path.parent / Path(rel_key).name
            if not target_file.exists() or _sha256_file(target_file) != expected_sha:
                checksum_ok = False
                break
        if not checksum_ok:
            continue

        snap_proc_dir = manifest_path.parent
        dataset_id = str(raw_m["dataset_id"])
        snap_raw_dir = raw_dir / dataset_id

        prices = pd.read_parquet(snap_proc_dir / "prices.parquet", engine="pyarrow")
        simple_returns = pd.read_parquet(snap_proc_dir / "simple_returns.parquet", engine="pyarrow")
        log_returns = pd.read_parquet(snap_proc_dir / "log_returns.parquet", engine="pyarrow")
        rf_frame = pd.read_parquet(snap_proc_dir / "rf_daily.parquet", engine="pyarrow")

        rf_ex_post_path = snap_proc_dir / "rf_daily_ex_post.parquet"
        rf_ex_post_frame = (
            pd.read_parquet(rf_ex_post_path, engine="pyarrow") if rf_ex_post_path.exists() else None
        )
        provenance_path = snap_proc_dir / "rf_provenance.parquet"
        rf_provenance = (
            pd.read_parquet(provenance_path, engine="pyarrow") if provenance_path.exists() else None
        )
        accrual_path = snap_proc_dir / "rf_daily_accrual_91d_sensitivity.parquet"
        rf_accrual_frame = (
            pd.read_parquet(accrual_path, engine="pyarrow") if accrual_path.exists() else None
        )

        rf_daily, ex_post_rf_daily = _validate_cached_bundle_tables(
            dataset_id=dataset_id,
            cfg=cfg,
            prices=prices,
            simple_returns=simple_returns,
            log_returns=log_returns,
            rf_frame=rf_frame,
            rf_ex_post_frame=rf_ex_post_frame,
            rf_provenance=rf_provenance,
            rf_accrual_frame=rf_accrual_frame,
        )

        quarantined_path = snap_proc_dir / "quarantined_unexpected_prices.parquet"
        quarantined_prices = (
            pd.read_parquet(quarantined_path, engine="pyarrow")
            if quarantined_path.exists()
            else pd.DataFrame(
                columns=list(prices.columns),
                index=pd.DatetimeIndex([], name="date"),
                dtype=float,
            )
        )

        quality_flags = pd.read_parquet(snap_proc_dir / "quality_flags.parquet", engine="pyarrow")
        excluded_return_rows = pd.read_parquet(
            snap_proc_dir / "excluded_return_rows.parquet",
            engine="pyarrow",
        )

        raw_rf_path = snap_raw_dir / "fred_dtb3_raw.parquet"
        raw_rf_quotes = (
            pd.read_parquet(raw_rf_path, engine="pyarrow") if raw_rf_path.exists() else None
        )

        uninterrupted = bool(excluded_return_rows.empty)
        simple_returns.attrs["uninterrupted_sessions"] = uninterrupted
        simple_returns.attrs["n_excluded_return_rows"] = int(len(excluded_return_rows))
        log_returns.attrs["uninterrupted_sessions"] = uninterrupted
        log_returns.attrs["n_excluded_return_rows"] = int(len(excluded_return_rows))

        notes = list(raw_m.get("notes", ()))
        if fallback_warning:
            notes.append(fallback_warning)

        manifest = DataManifest(
            dataset_id=dataset_id,
            schema_version=str(raw_m["schema_version"]),
            requested_start=str(raw_m["requested_start"]),
            requested_end=raw_m.get("requested_end"),
            actual_start=str(raw_m["actual_start"]),
            actual_end=str(raw_m["actual_end"]),
            retrieved_at_utc=str(raw_m["retrieved_at_utc"]),
            tickers=tuple(raw_m["tickers"]),
            source_urls=dict(raw_m["source_urls"]),
            price_adjustment=str(raw_m["price_adjustment"]),
            row_exclusions=dict(raw_m["row_exclusions"]),
            file_sha256=file_sha256,
            rf_convention=dict(raw_m["rf_convention"]),
            session_calendar_note=str(raw_m.get("session_calendar_note", "")),
            offline_cache_used=bool(offline_flag or fallback_warning is not None),
            notes=tuple(notes),
            policy_revision=str(raw_m.get("policy_revision", POLICY_REVISION_R2)),
            parent_dataset_id=raw_m.get("parent_dataset_id"),
        )

        return DataBundle(
            prices=prices,
            simple_returns=simple_returns,
            log_returns=log_returns,
            rf_daily=rf_daily,
            quality_flags=quality_flags,
            manifest=manifest,
            raw_rf_quotes=raw_rf_quotes,
            excluded_return_rows=excluded_return_rows,
            ex_post_rf_daily=ex_post_rf_daily,
            quarantined_prices=quarantined_prices,
            rf_provenance=rf_provenance,
            rf_accrual_sensitivity=(
                rf_accrual_frame.iloc[:, 0].astype(float).copy() if rf_accrual_frame is not None else None
            ),
        )

    return None


def _load_rf_evidence(cfg: AppConfig, base_dir: Path) -> pd.DataFrame:
    """Load the versioned RF evidence table after checking the configured SHA-256 pin."""
    if not cfg.data.rf_evidence_path or not cfg.data.rf_evidence_sha256:
        raise DataUnavailableError("The r3 RF policy requires rf_evidence_path and rf_evidence_sha256.")
    path = _resolve_dir(cfg.data.rf_evidence_path, base_dir)
    if not path.exists():
        raise DataUnavailableError(f"RF evidence table not found: {path}")
    actual = _sha256_file(path)
    if actual != cfg.data.rf_evidence_sha256:
        raise DataUnavailableError(
            f"RF evidence SHA-256 {actual} does not match configured {cfg.data.rf_evidence_sha256}."
        )
    table = pd.read_parquet(path, engine="pyarrow")
    missing = [c for c in RF_VERSION_TABLE_COLUMNS if c not in table.columns]
    if missing:
        raise DataUnavailableError(f"RF evidence table is missing columns: {missing}.")
    return table


def _build_and_persist_from_raw(
    *,
    cfg: AppConfig,
    base_dir: Path,
    raw_dir: Path,
    processed_dir: Path,
    observed_prices: pd.DataFrame,
    raw_rf: pd.DataFrame | None,
    retrieved_at_utc: str,
    policy_revision: str = POLICY_REVISION_R2,
    parent_dataset_id: str | None = None,
    extra_notes: Sequence[str] = (),
    activate: bool = True,
) -> DataBundle:
    """Apply hardened Step 2 session, boundary, quarantine, return, RF, and quality builders."""
    obs = observed_prices.copy()
    obs.index = _normalize_session_index(obs.index)
    obs = obs.sort_index(kind="mergesort")
    if obs.index.duplicated().any():
        raise ValueError("Duplicate dates encountered in raw ETF observed_prices.")

    canonical = list(cfg.mandate.canonical_tickers)
    missing_cols = [t for t in canonical if t not in obs.columns]
    if missing_cols:
        raise DataUnavailableError(f"Raw ETF price table missing canonical columns: {missing_cols}.")
    obs = obs[canonical].apply(pd.to_numeric, errors="coerce").astype(float)

    grid_prices, missing_expected, unexpected_obs = build_session_price_grid(
        obs,
        requested_start=cfg.data.requested_start,
        requested_end=cfg.data.frozen_end_date,
        require_boundary_coverage=cfg.data.require_requested_boundary_coverage,
        unexpected_session_policy=cfg.data.unexpected_session_policy,
    )
    quarantined_prices = obs.reindex(unexpected_obs).copy()
    quarantined_prices.index.name = "date"

    simple_returns, log_returns, excluded_return_rows = compute_session_returns(grid_prices)

    actual_end = grid_prices.index[-1].strftime("%Y-%m-%d")
    if raw_rf is not None and not raw_rf.empty:
        rf_copy = raw_rf.copy()
        rf_copy.index = pd.DatetimeIndex(pd.to_datetime(rf_copy.index)).normalize()
        rf_copy.index.name = "obs_date"
        rf_copy = rf_copy.sort_index(kind="mergesort")
        raw_rf_trimmed: pd.DataFrame | None = rf_copy.loc[
            (rf_copy.index >= (pd.Timestamp(cfg.data.requested_start) - pd.Timedelta(days=45)))
            & (rf_copy.index <= pd.Timestamp(actual_end))
        ].copy()
    else:
        raw_rf_trimmed = None

    primary_rf_mode = _rf_policy_to_mode(cfg.data.rf_alignment_policy)
    rf_version_table: pd.DataFrame | None = None
    rf_provenance: pd.DataFrame | None = None
    rf_accrual_sensitivity: pd.Series | None = None
    if raw_rf_trimmed is not None and not raw_rf_trimmed.empty:
        if cfg.data.rf_alignment_policy == RF_POLICY_R3:
            rf_version_table = _load_rf_evidence(cfg, base_dir)
            covered = pd.DatetimeIndex(rf_version_table["obs_date"].unique())
            uncovered = raw_rf_trimmed["rate_annual_pct"].dropna().index.difference(covered)
            if len(uncovered) > 0:
                raise DataUnavailableError(
                    f"RF evidence does not cover {len(uncovered)} raw DTB3 observation(s), "
                    f"first {uncovered[0].strftime('%Y-%m-%d')}."
                )
            rf_daily, rf_provenance = select_rf_versions_asof(
                rf_version_table,
                simple_returns.index,
                trading_days_per_year=cfg.data.rf_trading_days_per_year,
                price_sessions=grid_prices.index,
                decision_timezone=cfg.data.rf_decision_timezone,
                decision_cutoff_time_ny=cfg.data.rf_decision_cutoff_time,
            )
            rf_accrual_sensitivity = rf_accrual_91d_sensitivity(
                rf_provenance["value_pct"], grid_prices.index
            )
        else:
            rf_daily = align_risk_free_rate(
                raw_rf_trimmed["rate_annual_pct"],
                simple_returns.index,
                availability_lag_sessions=cfg.data.rf_availability_lag_sessions,
                trading_days_per_year=cfg.data.rf_trading_days_per_year,
                mode=primary_rf_mode,
                price_sessions=grid_prices.index,
                decision_timezone=cfg.data.rf_decision_timezone,
                decision_cutoff_time_ny=cfg.data.rf_decision_cutoff_time,
                release_time_ny=cfg.data.rf_release_time,
            )
        ex_post_rf_daily = align_risk_free_rate(
            raw_rf_trimmed["rate_annual_pct"],
            simple_returns.index,
            availability_lag_sessions=cfg.data.rf_availability_lag_sessions,
            trading_days_per_year=cfg.data.rf_trading_days_per_year,
            mode="ex_post",
            price_sessions=grid_prices.index,
            decision_timezone=cfg.data.rf_decision_timezone,
            decision_cutoff_time_ny=cfg.data.rf_decision_cutoff_time,
            release_time_ny=cfg.data.rf_release_time,
        )
    else:
        rf_daily = pd.Series(np.nan, index=simple_returns.index.copy(), name="rf_daily", dtype=float)
        ex_post_rf_daily = pd.Series(
            np.nan, index=simple_returns.index.copy(), name="rf_daily_ex_post", dtype=float
        )

    quality_flags = flag_data_quality(
        prices=grid_prices,
        simple_returns=simple_returns,
        log_returns=log_returns,
        rf_daily=rf_daily,
        unexpected_sessions=unexpected_obs,
        quarantined_prices=quarantined_prices,
    )

    return _persist_snapshot(
        cfg=cfg,
        base_dir=base_dir,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        observed_prices=obs,
        raw_rf_trimmed=raw_rf_trimmed,
        grid_prices=grid_prices,
        quarantined_prices=quarantined_prices,
        missing_expected_sessions=missing_expected,
        unexpected_sessions=unexpected_obs,
        simple_returns=simple_returns,
        log_returns=log_returns,
        excluded_return_rows=excluded_return_rows,
        rf_daily=rf_daily,
        ex_post_rf_daily=ex_post_rf_daily,
        quality_flags=quality_flags,
        retrieved_at_utc=retrieved_at_utc,
        policy_revision=policy_revision,
        parent_dataset_id=parent_dataset_id,
        extra_notes=extra_notes,
        rf_version_table=rf_version_table,
        rf_provenance=rf_provenance,
        rf_accrual_sensitivity=rf_accrual_sensitivity,
        activate=activate,
    )


def derive_snapshot_from_existing(
    config: AppConfig | dict[str, Any] | Path | str,
    *,
    source_dataset_id: str,
    repo_root: Path | None = None,
    activate: bool = True,
) -> DataBundle:
    """Derive a policy-revision snapshot offline from a preserved, SHA-256-verified raw snapshot.

    Verifies every SHA-256 hash recorded in ``source_dataset_id``'s ``manifest.json`` before
    reading ``etf_prices_raw.parquet`` and ``fred_dtb3_raw.parquet``, performs zero network
    downloads, and leaves ``source_dataset_id`` untouched on disk. With ``activate=False`` the
    result is a candidate and the active pointer is left unchanged.
    """
    cfg, base_dir = _resolve_config_and_base_dir(config, repo_root)
    raw_dir = _resolve_dir(cfg.data.raw_dir, base_dir)
    processed_dir = _resolve_dir(cfg.data.processed_dir, base_dir)

    src_manifest_path = processed_dir / source_dataset_id / "manifest.json"
    if not src_manifest_path.exists():
        raise DataUnavailableError(
            f"Preserved source snapshot manifest not found: {src_manifest_path}"
        )

    src_manifest = json.loads(src_manifest_path.read_text(encoding="utf-8"))
    src_hashes: dict[str, str] = dict(src_manifest.get("file_sha256", {}))
    if not src_hashes:
        raise DataUnavailableError(
            f"Preserved source snapshot {source_dataset_id} has empty file_sha256 table."
        )

    for rel_key, expected_sha in src_hashes.items():
        target_file = (base_dir / Path(rel_key)).resolve()
        if not target_file.exists():
            target_file = src_manifest_path.parent / Path(rel_key).name
        if not target_file.exists() or _sha256_file(target_file) != expected_sha:
            raise DataUnavailableError(
                f"SHA-256 verification failed for preserved source file {rel_key} in {source_dataset_id}."
            )

    src_raw_dir = raw_dir / source_dataset_id
    src_prices_path = src_raw_dir / "etf_prices_raw.parquet"
    if not src_prices_path.exists():
        raise DataUnavailableError(f"Preserved raw ETF parquet not found: {src_prices_path}")

    observed_prices = pd.read_parquet(src_prices_path, engine="pyarrow")
    src_rf_path = src_raw_dir / "fred_dtb3_raw.parquet"
    raw_rf = pd.read_parquet(src_rf_path, engine="pyarrow") if src_rf_path.exists() else None

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    src_retrieved = str(src_manifest.get("retrieved_at_utc", "unknown"))
    policy_revision = _rf_policy_revision(cfg.data.rf_alignment_policy)
    note = (
        f"Derived offline at {now_utc} from preserved audited raw snapshot "
        f"{source_dataset_id} (originally retrieved {src_retrieved}) without network redownload "
        f"under {policy_revision} policy."
    )

    return _build_and_persist_from_raw(
        cfg=cfg,
        base_dir=base_dir,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        observed_prices=observed_prices,
        raw_rf=raw_rf,
        retrieved_at_utc=now_utc,
        policy_revision=policy_revision,
        parent_dataset_id=source_dataset_id,
        extra_notes=(note,),
        activate=activate,
    )


def load_data(
    config: AppConfig | dict[str, Any] | Path | str,
    *,
    offline: bool = False,
    refresh: bool = False,
    repo_root: Path | None = None,
) -> DataBundle:
    """Load a verified cached market-data snapshot or fetch/build one from approved sources.

    Args:
        config: ``AppConfig``, path to ``config.yaml``, or raw config dictionary.
        offline: When ``True``, forbid network access and require a verified matching
            cached snapshot on disk (raising ``DataUnavailableError`` if absent or logically invalid).
        refresh: When ``True`` (and ``offline=False``), attempt a fresh download before
            falling back to any matching verified cache on network/truncation error.
        repo_root: Optional base directory override for resolving relative ``data/`` paths.

    Returns:
        Frozen ``DataBundle`` with uncollapsed NYSE session ``prices``, quarantined unexpected
        observations, one-session ``simple_returns`` and ``log_returns``, cutoff-valid
        ``rf_daily``, separate contemporaneous ``ex_post_rf_daily``, retained ``quality_flags``,
        ``DataManifest``, ``raw_rf_quotes``, and ``excluded_return_rows``.
    """
    cfg, base_dir = _resolve_config_and_base_dir(config, repo_root)
    raw_dir = _resolve_dir(cfg.data.raw_dir, base_dir)
    processed_dir = _resolve_dir(cfg.data.processed_dir, base_dir)

    if offline:
        cached = _try_load_verified_cache(
            cfg=cfg,
            base_dir=base_dir,
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            offline_flag=True,
        )
        if cached is not None:
            return cached
        raise DataUnavailableError(
            f"Offline mode requested, but no verified matching data snapshot was found in "
            f"{processed_dir}. Run load_data(config, offline=False) with internet access or "
            f"derive_snapshot_from_existing(...) to create the policy-matching snapshot."
        )

    if not refresh:
        cached = _try_load_verified_cache(
            cfg=cfg,
            base_dir=base_dir,
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            offline_flag=False,
        )
        if cached is not None:
            return cached

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    extra_notes: list[str] = []

    try:
        observed_prices = _download_etf_adjusted_closes(cfg)
        # Validate requested boundary coverage BEFORE accepting a live download over any verified cache.
        build_session_price_grid(
            observed_prices,
            requested_start=cfg.data.requested_start,
            requested_end=cfg.data.frozen_end_date,
            require_boundary_coverage=cfg.data.require_requested_boundary_coverage,
            unexpected_session_policy=cfg.data.unexpected_session_policy,
        )
    except Exception as price_exc:
        fallback_msg = (
            f"WARNING [{now_utc}]: Network ETF retrieval or boundary validation failed "
            f"({price_exc}); loaded verified cached snapshot."
        )
        cached = _try_load_verified_cache(
            cfg=cfg,
            base_dir=base_dir,
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            offline_flag=True,
            fallback_warning=fallback_msg,
        )
        if cached is not None:
            return cached
        raise DataUnavailableError(
            f"Market data download/validation failed ({price_exc}) and no verified cached snapshot "
            f"exists in {processed_dir}."
        ) from price_exc

    raw_rf: pd.DataFrame | None = None
    try:
        raw_rf = _download_fred_dtb3(cfg)
    except Exception as rf_exc:
        cached = _try_load_verified_cache(
            cfg=cfg,
            base_dir=base_dir,
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            offline_flag=True,
            fallback_warning=(
                f"WARNING [{now_utc}]: FRED DTB3 retrieval failed ({rf_exc}); "
                f"loaded verified cached snapshot."
            ),
        )
        if cached is not None:
            return cached
        extra_notes.append(
            f"WARNING [{now_utc}]: FRED DTB3 retrieval failed ({rf_exc}); rf_daily populated "
            f"with NaN so price-risk analytics remain available while RF-dependent KPIs report unavailable."
        )

    return _build_and_persist_from_raw(
        cfg=cfg,
        base_dir=base_dir,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        observed_prices=observed_prices,
        raw_rf=raw_rf,
        retrieved_at_utc=now_utc,
        policy_revision=_rf_policy_revision(cfg.data.rf_alignment_policy),
        parent_dataset_id=None,
        extra_notes=extra_notes,
    )
