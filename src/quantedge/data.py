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
from typing import Any

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
from quantedge.returns import (
    EXCLUDED_RETURN_COLUMNS,
    align_risk_free_rate,
    compute_return_descriptive_stats,
    compute_session_returns,
    expected_nyse_sessions,
    run_stationarity_diagnostics,
)


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
    calendar_sessions: pd.DatetimeIndex | None = None,
) -> tuple[pd.DataFrame, pd.DatetimeIndex, pd.DatetimeIndex]:
    """Reindex observed prices onto the shared NYSE trading-session grid WITHOUT fill.

    Returns:
        ``(grid_prices, missing_expected_sessions, unexpected_observed_sessions)``
    """
    if observed_prices.empty:
        raise ValueError("observed_prices cannot be empty.")

    actual_start = observed_prices.index[0]
    actual_end = observed_prices.index[-1]
    expected = (
        calendar_sessions
        if calendar_sessions is not None
        else expected_nyse_sessions(actual_start, actual_end)
    )
    expected = _normalize_session_index(expected)
    expected = expected[(expected >= actual_start) & (expected <= actual_end)]

    missing_expected = expected.difference(observed_prices.index)
    unexpected_observed = observed_prices.index.difference(expected)

    full_grid = expected.union(observed_prices.index).sort_values()
    full_grid.name = "date"

    # Reindex with NO fill so missing sessions remain explicit NaNs
    grid_prices = observed_prices.reindex(full_grid)
    return grid_prices, missing_expected, unexpected_observed


def flag_data_quality(
    prices: pd.DataFrame,
    simple_returns: pd.DataFrame,
    log_returns: pd.DataFrame,
    rf_daily: pd.Series,
    *,
    unexpected_sessions: pd.DatetimeIndex | None = None,
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
    - ``unexpected_non_nyse_session``: Observed price date outside expected NYSE calendar
      (``action='retain_and_review'``).
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

    # 2. Unexpected non-NYSE sessions (if any)
    if unexpected_sessions is not None and len(unexpected_sessions) > 0:
        for dt in unexpected_sessions:
            records.append(
                {
                    "date": pd.Timestamp(dt),
                    "ticker": "ALL",
                    "rule": "unexpected_non_nyse_session",
                    "value": np.nan,
                    "action": "retain_and_review",
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
        f"- **Contract schema version:** `{m.schema_version}`",
        f"- **Retrieved at (UTC):** `{m.retrieved_at_utc}`",
        f"- **Canonical tickers:** `{', '.join(m.tickers)}`",
        f"- **Requested start / end:** `{m.requested_start}` to `{m.requested_end or 'latest_available_frozen_on_snapshot'}`",
        f"- **Actual price session bounds:** `{m.actual_start}` to `{m.actual_end}` (`{len(bundle.prices)}` trading sessions on grid)",
        f"- **Complete 1-session return bounds:** `{bundle.simple_returns.index[0].strftime('%Y-%m-%d')}` to `{bundle.simple_returns.index[-1].strftime('%Y-%m-%d')}` (`{len(bundle.simple_returns)}` sessions)",
        f"- **Price adjustment policy:** `{m.price_adjustment}` (`yfinance` `auto_adjust=True`, where `Close` is the split- and dividend-adjusted close series)",
        f"- **Session calendar check:** {m.session_calendar_note}",
        "",
        "## 2. Missing-Data Accounting vs. Retained Quality Flags",
        f"- **Total grid sessions (`prices`):** `{excl['n_price_grid_sessions']}`",
        f"- **Expected NYSE sessions missing across all tickers:** `{excl['n_missing_expected_nyse_sessions']}`",
        f"- **Unexpected non-NYSE observed sessions:** `{excl['n_unexpected_observed_sessions']}`",
        f"- **Missing price cells `(date, ticker)`:** `{excl['n_missing_price_cells']}` (by ticker: `{excl['missing_price_cells_by_ticker']}`)",
        f"- **Initial price anchor row (`{m.actual_start}`):** `1` session (base price for first 1-day return; never filled with an artificial `0.0` return)",
        f"- **Post-anchor return rows excluded due to missing endpoints:** `{excl['n_excluded_return_rows']}`",
        f"- **Uninterrupted 1-session return series:** `{excl['uninterrupted_return_sessions']}`",
        f"- **Aligned `DTB3` risk-free missing rows on return dates:** `{excl['n_missing_aligned_rf_rows']}`",
        "",
        "> **Hygiene rule:** Missing ETF prices are never forward-filled. Returns are computed on the uncollapsed session grid first (`P_t / P_{t-1} - 1`), so any missing price invalidates both adjacent 1-session intervals rather than bridging a multi-day move as a 1-day return. Conversely, outlier and structural-break flags below **retain** all valid observations (`action='retain'`).",
        "",
        "### Quality Flag Counts by Rule",
        _markdown_table(flag_summary, float_fmt="{:.4f}"),
        "### Quality Flag Counts by Ticker",
        _markdown_table(per_ticker_flags, float_fmt="{:.0f}"),
        "## 3. Simple vs. Log Return Convention & Risk-Free Proxy",
        "- **Simple returns (`simple_returns`):** Used for cross-sectional portfolio aggregation (`R_{p,t} = sum_i w_{i,t-} R_{i,t}`) and committee simple-loss risk (`L_t = -R_{p,t}`), because dollar NAV P&L aggregates linearly across holdings at horizon `t` whereas `sum_i w_i log(1 + R_{i,t}) != log(1 + R_{p,t})` (Jensen's inequality).",
        "- **Log returns (`log_returns = log1p(simple_returns)`):** Additive across time (`log(P_T / P_0) = sum_t r_t`), used for time-series statistical diagnostics (ADF stationarity tests, correlation tables, and volatility-regime screening).",
        f"- **Risk-free proxy (`DTB3`):** `{m.rf_convention['series']}` quoted in `{m.rf_convention['quote_basis']}`, converted via `{m.rf_convention['conversion_formula']}` with `availability_lag_sessions = {m.rf_convention['availability_lag_sessions']}` business days and past-only forward alignment (`no_backfill = {m.rf_convention['no_backfill']}`). Limitation: dividing an annualized 360-day bank-discount rate by 252 is a standard daily trading-day approximation, not an exact realized T-bill total return, and FRED series remain subject to publication lags/holiday gaps.",
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
    requested_start: str,
    actual_end: str,
    prices: pd.DataFrame,
    raw_rf: pd.DataFrame | None,
) -> str:
    """Compute a deterministic dataset identifier from bounds and content hashes."""
    hasher = hashlib.sha256()
    hasher.update(prices.to_csv(float_format="%.12g").encode("utf-8"))
    if raw_rf is not None and not raw_rf.empty:
        hasher.update(raw_rf.to_csv(float_format="%.12g").encode("utf-8"))
    short_sha = hasher.hexdigest()[:10]
    s_clean = requested_start.replace("-", "")
    e_clean = actual_end.replace("-", "")
    return f"qe1_{s_clean}_{e_clean}_{short_sha}"


def _persist_snapshot(
    *,
    cfg: AppConfig,
    base_dir: Path,
    raw_dir: Path,
    processed_dir: Path,
    observed_prices: pd.DataFrame,
    raw_rf: pd.DataFrame | None,
    grid_prices: pd.DataFrame,
    missing_expected_sessions: pd.DatetimeIndex,
    unexpected_sessions: pd.DatetimeIndex,
    simple_returns: pd.DataFrame,
    log_returns: pd.DataFrame,
    excluded_return_rows: pd.DataFrame,
    rf_daily: pd.Series,
    quality_flags: pd.DataFrame,
    retrieved_at_utc: str,
    extra_notes: Sequence[str] = (),
) -> DataBundle:
    """Write raw & processed snapshot files, compute SHA-256 hashes, and write ``manifest.json``."""
    actual_start = grid_prices.index[0].strftime("%Y-%m-%d")
    actual_end = grid_prices.index[-1].strftime("%Y-%m-%d")

    # Trim preserved raw_rf up through actual_end (keeping pre-2005 history for lag-1 availability on day 1)
    if raw_rf is not None and not raw_rf.empty:
        raw_rf_trimmed = raw_rf.loc[
            (raw_rf.index >= (pd.Timestamp(cfg.data.requested_start) - pd.Timedelta(days=45)))
            & (raw_rf.index <= pd.Timestamp(actual_end))
        ].copy()
    else:
        raw_rf_trimmed = None

    dataset_id = _build_dataset_id(
        cfg.data.requested_start,
        actual_end,
        grid_prices,
        raw_rf_trimmed,
    )

    snap_raw_dir = raw_dir / dataset_id
    snap_proc_dir = processed_dir / dataset_id
    snap_raw_dir.mkdir(parents=True, exist_ok=True)
    snap_proc_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[Path] = []

    raw_prices_path = snap_raw_dir / "etf_prices_raw.parquet"
    observed_prices.to_parquet(raw_prices_path, engine="pyarrow", index=True)
    written_files.append(raw_prices_path)

    if raw_rf_trimmed is not None:
        raw_rf_path = snap_raw_dir / "fred_dtb3_raw.parquet"
        raw_rf_trimmed.to_parquet(raw_rf_path, engine="pyarrow", index=True)
        written_files.append(raw_rf_path)

    prices_path = snap_proc_dir / "prices.parquet"
    simple_path = snap_proc_dir / "simple_returns.parquet"
    log_path = snap_proc_dir / "log_returns.parquet"
    rf_path = snap_proc_dir / "rf_daily.parquet"
    flags_path = snap_proc_dir / "quality_flags.parquet"
    excl_path = snap_proc_dir / "excluded_return_rows.parquet"

    grid_prices.to_parquet(prices_path, engine="pyarrow", index=True)
    simple_returns.to_parquet(simple_path, engine="pyarrow", index=True)
    log_returns.to_parquet(log_path, engine="pyarrow", index=True)
    rf_daily.to_frame(name="rf_daily").to_parquet(rf_path, engine="pyarrow", index=True)
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

    written_files.extend([prices_path, simple_path, log_path, rf_path, flags_path, excl_path])

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

    missing_by_ticker = {str(t): int(grid_prices[t].isna().sum()) for t in grid_prices.columns}
    row_exclusions: dict[str, Any] = {
        "n_price_grid_sessions": int(len(grid_prices)),
        "n_initial_anchor_rows": 1,
        "n_missing_expected_nyse_sessions": int(len(missing_expected_sessions)),
        "missing_expected_nyse_dates": [d.strftime("%Y-%m-%d") for d in missing_expected_sessions],
        "n_unexpected_observed_sessions": int(len(unexpected_sessions)),
        "unexpected_observed_dates": [d.strftime("%Y-%m-%d") for d in unexpected_sessions],
        "n_missing_price_cells": int(grid_prices.isna().sum().sum()),
        "missing_price_cells_by_ticker": missing_by_ticker,
        "n_rows_with_any_missing_price": int(grid_prices.isna().any(axis=1).sum()),
        "n_excluded_return_rows": int(len(excluded_return_rows)),
        "n_complete_return_rows": int(len(simple_returns)),
        "uninterrupted_return_sessions": bool(excluded_return_rows.empty),
        "n_missing_aligned_rf_rows": int(rf_daily.isna().sum()),
        "n_raw_rf_missing_dot_rows": (
            int(raw_rf_trimmed["rate_annual_pct"].isna().sum()) if raw_rf_trimmed is not None else None
        ),
    }

    rf_convention: dict[str, Any] = {
        "series": cfg.data.fred_rf_series,
        "quote_basis": cfg.data.rf_quote_basis,
        "conversion_formula": cfg.data.rf_conversion_formula,
        "trading_days_per_year": cfg.data.rf_trading_days_per_year,
        "availability_lag_sessions": cfg.data.rf_availability_lag_sessions,
        "lag_rule": (
            "Observation dated d becomes usable at d + availability_lag_sessions * BDay "
            "(past-only merge_asof backward; zero backfill)."
        ),
        "no_backfill": cfg.data.rf_no_backfill,
        "limitation_note": (
            "DTB3 is quoted in annual percent on a 360-day bank-discount basis; "
            "(rate_pct / 100.0) / 252 is an approximate trading-day risk-free proxy, "
            "not an exact realized T-bill holding-period return, and remains subject to "
            "FRED publication timing and holiday omissions."
        ),
    }

    cal_note = (
        f"Expected NYSE sessions in [{actual_start}, {actual_end}]: "
        f"{len(grid_prices) - len(unexpected_sessions)}; "
        f"missing expected NYSE sessions: {len(missing_expected_sessions)}; "
        f"unexpected observed dates: {len(unexpected_sessions)}."
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

    pointer_path = processed_dir / "active_snapshot.json"
    pointer_payload = {
        "dataset_id": dataset_id,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "manifest_relpath": f"{dataset_id}/manifest.json",
        "actual_start": actual_start,
        "actual_end": actual_end,
        "retrieved_at_utc": retrieved_at_utc,
    }
    pointer_path.write_text(
        json.dumps(pointer_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return replace(prelim_bundle, manifest=final_manifest)


def _try_load_verified_cache(
    *,
    cfg: AppConfig,
    base_dir: Path,
    raw_dir: Path,
    processed_dir: Path,
    offline_flag: bool,
    fallback_warning: str | None = None,
) -> DataBundle | None:
    """Locate, config-match, and SHA-256-verify an existing snapshot on disk."""
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

        rf_conv = raw_m.get("rf_convention", {})
        if (
            rf_conv.get("series") != cfg.data.fred_rf_series
            or int(rf_conv.get("trading_days_per_year", -1)) != cfg.data.rf_trading_days_per_year
            or int(rf_conv.get("availability_lag_sessions", -1))
            != cfg.data.rf_availability_lag_sessions
        ):
            continue

        if cfg.data.frozen_end_date is not None and raw_m.get("actual_end") != cfg.data.frozen_end_date:
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
        rf_daily = rf_frame["rf_daily"].copy()
        rf_daily.index = simple_returns.index.copy()
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
        )

    return None


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
            cached snapshot on disk (raising ``DataUnavailableError`` if absent).
        refresh: When ``True`` (and ``offline=False``), attempt a fresh download before
            falling back to any matching verified cache on network error.
        repo_root: Optional base directory override for resolving relative ``data/`` paths.

    Returns:
        Frozen ``DataBundle`` with uncollapsed session ``prices``, one-session
        ``simple_returns`` and ``log_returns``, past-only ``rf_daily``, retained
        ``quality_flags``, ``DataManifest``, ``raw_rf_quotes``, and ``excluded_return_rows``.
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
            f"{processed_dir}. Run load_data(config, offline=False) with internet access to "
            f"create the reusable snapshot."
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
    except Exception as price_exc:
        fallback_msg = (
            f"WARNING [{now_utc}]: Network ETF retrieval failed ({price_exc}); "
            f"loaded verified cached snapshot."
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
            f"Market data download failed ({price_exc}) and no verified cached snapshot "
            f"exists in {processed_dir}."
        ) from price_exc

    raw_rf: pd.DataFrame | None = None
    try:
        raw_rf = _download_fred_dtb3(cfg)
    except Exception as rf_exc:
        # If a full cached snapshot exists when refresh failed on FRED, prefer verified cache;
        # otherwise preserve valid ETF price-risk data and mark RF unavailable per D1/A1 spec.
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

    grid_prices, missing_expected, unexpected_obs = build_session_price_grid(observed_prices)
    simple_returns, log_returns, excluded_return_rows = compute_session_returns(grid_prices)

    if raw_rf is not None:
        rf_daily = align_risk_free_rate(
            raw_rf["rate_annual_pct"],
            simple_returns.index,
            availability_lag_sessions=cfg.data.rf_availability_lag_sessions,
            trading_days_per_year=cfg.data.rf_trading_days_per_year,
        )
    else:
        rf_daily = pd.Series(np.nan, index=simple_returns.index, name="rf_daily", dtype=float)

    quality_flags = flag_data_quality(
        prices=grid_prices,
        simple_returns=simple_returns,
        log_returns=log_returns,
        rf_daily=rf_daily,
        unexpected_sessions=unexpected_obs,
    )

    return _persist_snapshot(
        cfg=cfg,
        base_dir=base_dir,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        observed_prices=observed_prices,
        raw_rf=raw_rf,
        grid_prices=grid_prices,
        missing_expected_sessions=missing_expected,
        unexpected_sessions=unexpected_obs,
        simple_returns=simple_returns,
        log_returns=log_returns,
        excluded_return_rows=excluded_return_rows,
        rf_daily=rf_daily,
        quality_flags=quality_flags,
        retrieved_at_utc=now_utc,
        extra_notes=extra_notes,
    )
