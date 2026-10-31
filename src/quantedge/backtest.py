"""Out-of-sample rolling VaR validation, Kupiec/Christoffersen tests, and Basel diagnostic.

Public interfaces frozen in D0 for SOLO STEP 6 (A3):
- ``rolling_backtest(asset_returns, weights_before, forecast_fn, *, confidence, window, seed=None) -> pd.DataFrame``
- ``coverage_tests(backtest_rows) -> pd.DataFrame``
- ``basel_traffic_light(backtest_rows_99) -> dict[str, Any]``
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np
import pandas as pd

from quantedge._backtest_diagnostics import (
    basel_traffic_light as _basel_traffic_light_impl,
    coverage_tests as _coverage_tests_impl,
)
from quantedge.contracts import (
    BACKTEST_COLUMNS,
    CANONICAL_TICKERS,
    RiskEstimate,
    RiskForecastFn,
)
from quantedge.returns import expected_nyse_sessions

_WEIGHT_SUM_TOL: float = 1e-6
_WEIGHT_MIN_TOL: float = -1e-7


def derive_origin_seed(base_seed: int, target_date: str | pd.Timestamp) -> int:
    """Derive a deterministic 31-bit non-negative seed from ``(base_seed, target_date)``."""
    if isinstance(base_seed, bool) or not isinstance(base_seed, (int, np.integer)):
        raise TypeError(f"base_seed must be an integer; got {type(base_seed).__name__}.")
    if int(base_seed) < 0:
        raise ValueError(f"base_seed must be >= 0; got {base_seed!r}.")
    ts_iso = pd.Timestamp(target_date).normalize().strftime("%Y-%m-%d")
    payload = f"quantedge_backtest_v1|{int(base_seed)}|{ts_iso}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:4], byteorder="big") & 0x7FFF_FFFF


def _validate_datetime_index(index: pd.Index, *, name: str) -> pd.DatetimeIndex:
    """Validate that ``index`` is a non-empty, timezone-naive, normalized ascending ``DatetimeIndex``."""
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"{name} must have a pandas DatetimeIndex; got {type(index).__name__}.")
    if len(index) == 0:
        raise ValueError(f"{name} DatetimeIndex cannot be empty.")
    if index.tz is not None:
        raise ValueError(f"{name} DatetimeIndex must be timezone-naive.")
    if index.isna().any():
        raise ValueError(f"{name} DatetimeIndex contains NaT values.")
    norm = index.normalize()
    if not norm.equals(index):
        raise ValueError(f"{name} DatetimeIndex must contain normalized midnight session dates.")
    if not norm.is_monotonic_increasing:
        raise ValueError(f"{name} DatetimeIndex must be sorted in strictly ascending chronological order.")
    if norm.has_duplicates:
        raise ValueError(f"{name} DatetimeIndex contains duplicate session dates.")
    return norm


def _validate_canonical_frame(df: pd.DataFrame, *, name: str) -> pd.DataFrame:
    """Validate a canonical 7-ETF DataFrame and return an isolated deep copy."""
    if not isinstance(df, pd.DataFrame):
        raise ValueError(f"{name} must be a pandas DataFrame; got {type(df).__name__}.")
    norm_index = _validate_datetime_index(df.index, name=name)
    if tuple(df.columns) != CANONICAL_TICKERS:
        raise ValueError(
            f"{name} columns must match CANONICAL_TICKERS in exact canonical order "
            f"{CANONICAL_TICKERS}; got {tuple(df.columns)}."
        )
    out = df.copy(deep=True)
    out.index = norm_index
    for col in CANONICAL_TICKERS:
        if not pd.api.types.is_numeric_dtype(out[col].dtype) or pd.api.types.is_bool_dtype(out[col].dtype):
            raise ValueError(f"{name} column {col!r} must have a numeric float/int dtype; got {out[col].dtype}.")
    return out


def _validate_confidence_param(confidence: float) -> float:
    """Validate confidence parameter in (0, 1)."""
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float, np.floating, np.integer)):
        raise ValueError(f"confidence must be a finite float in (0, 1); got {confidence!r}.")
    conf = float(confidence)
    if not math.isfinite(conf) or not (0.0 < conf < 1.0):
        raise ValueError(f"confidence must lie strictly in (0, 1); got {confidence!r}.")
    return round(conf, 12)


def _format_backtest_dataframe(rows: list[dict[str, Any]], *, attrs: dict[str, Any]) -> pd.DataFrame:
    """Construct a ``BACKTEST_COLUMNS`` DataFrame preserving ``None``, ``bool``, and ``Timestamp`` types."""
    if not rows:
        df = pd.DataFrame(columns=list(BACKTEST_COLUMNS))
        df.attrs.update(attrs)
        return df

    df = pd.DataFrame(rows, columns=list(BACKTEST_COLUMNS))
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    for col in ("forecast_var", "forecast_es", "realized_loss", "exceedance", "train_start", "train_end", "reason"):
        df[col] = pd.Series([r[col] for r in rows], index=df.index, dtype=object)
    df.attrs.update(attrs)
    return df


def rolling_backtest(
    asset_returns: pd.DataFrame,
    weights_before: pd.DataFrame,
    forecast_fn: RiskForecastFn,
    *,
    confidence: float,
    window: int,
    seed: int | None = None,
) -> pd.DataFrame:
    """Run strictly out-of-sample rolling one-day VaR/ES validation via generic callback.

    Specification (SOLO STEP 6 / A3):
    - Targets include every expected NYSE session between the first and last supplied
      ``weights_before`` dates (plus any extra supplied dates, marked unavailable).
    - For target session ``t``, slices strictly the prior ``window`` sessions, asserts
      ``train_end < t``, forecasts risk for exposure ``weights_before.loc[t]``, and compares
      against realized gross market loss ``-(weights_before.loc[t] @ asset_returns.loc[t])``.
    - Exceedance is strictly ``realized_loss > forecast_var``; invalid/skipped rows are
      retained with ``status='unavailable'``, an explicit ``reason``, and ``exceedance=None``.
    - Output columns match ``BACKTEST_COLUMNS``.
    """
    returns_df = _validate_canonical_frame(asset_returns, name="asset_returns")
    weights_df = _validate_canonical_frame(weights_before, name="weights_before")
    conf = _validate_confidence_param(confidence)

    if isinstance(window, bool) or not isinstance(window, (int, np.integer)) or int(window) < 2:
        raise ValueError(f"window must be an integer >= 2; got {window!r}.")
    win = int(window)

    if seed is not None:
        if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or int(seed) < 0:
            raise ValueError(f"seed must be a non-negative integer or None; got {seed!r}.")
        base_seed: int | None = int(seed)
    else:
        base_seed = None

    if not callable(forecast_fn):
        raise ValueError("forecast_fn must be a callable RiskForecastFn.")

    overall_start = min(returns_df.index[0], weights_df.index[0])
    overall_end = max(returns_df.index[-1], weights_df.index[-1])
    nyse_grid = expected_nyse_sessions(overall_start, overall_end)
    nyse_pos: dict[pd.Timestamp, int] = {ts: idx for idx, ts in enumerate(nyse_grid)}

    # Target sessions: all expected NYSE sessions between first and last weights date,
    # unioned with any extra supplied weights dates so no requested row is dropped.
    expected_weight_nyse = expected_nyse_sessions(weights_df.index[0], weights_df.index[-1])
    target_dates = expected_weight_nyse.union(weights_df.index).sort_values()

    return_index = returns_df.index
    return_pos_map: dict[pd.Timestamp, int] = {ts: idx for idx, ts in enumerate(return_index)}
    return_nyse_idx = np.array([nyse_pos.get(ts, -1) for ts in return_index], dtype=np.int64)
    return_date_strs: list[str] = [ts.strftime("%Y-%m-%d") for ts in return_index]
    return_matrix = np.ascontiguousarray(returns_df.to_numpy(dtype=np.float64), dtype=np.float64)
    return_row_finite = np.all(np.isfinite(return_matrix), axis=1)

    weight_pos_map: dict[pd.Timestamp, int] = {ts: idx for idx, ts in enumerate(weights_df.index)}
    weight_matrix = np.ascontiguousarray(weights_df.to_numpy(dtype=np.float64), dtype=np.float64)
    weight_row_finite = np.all(np.isfinite(weight_matrix), axis=1)
    canonical_cols = list(CANONICAL_TICKERS)

    initial_model_hint = getattr(forecast_fn, "model", None)
    discovered_model: str | None = (
        str(initial_model_hint).strip()
        if isinstance(initial_model_hint, str) and str(initial_model_hint).strip()
        else None
    )

    raw_rows: list[dict[str, Any]] = []

    for target_ts in target_dates:
        target_str = target_ts.strftime("%Y-%m-%d")

        # 1. Verify target date is a genuine NYSE trading session
        target_nyse_idx = nyse_pos.get(target_ts, -1)
        if target_nyse_idx < 0:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": None,
                    "exceedance": None,
                    "train_start": None,
                    "train_end": None,
                    "status": "unavailable",
                    "reason": (
                        f"non_nyse_target_session: {target_str} "
                        "is not a scheduled NYSE trading session."
                    ),
                }
            )
            continue

        # 2. Verify weights_before row exists and is finite/valid at session t
        w_row_idx = weight_pos_map.get(target_ts, -1)
        if w_row_idx < 0:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": None,
                    "exceedance": None,
                    "train_start": None,
                    "train_end": None,
                    "status": "unavailable",
                    "reason": (
                        f"missing_weights_before_session: scheduled NYSE session {target_str} "
                        "is missing from weights_before."
                    ),
                }
            )
            continue

        w_arr = weight_matrix[w_row_idx]
        if not weight_row_finite[w_row_idx]:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": None,
                    "exceedance": None,
                    "train_start": None,
                    "train_end": None,
                    "status": "unavailable",
                    "reason": f"missing_or_non_finite_weights: weights_before at {target_str} contains NaN/inf.",
                }
            )
            continue

        w_sum = float(np.sum(w_arr, dtype=np.float64))
        if abs(w_sum - 1.0) > _WEIGHT_SUM_TOL or float(np.min(w_arr)) < _WEIGHT_MIN_TOL:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": None,
                    "exceedance": None,
                    "train_start": None,
                    "train_end": None,
                    "status": "unavailable",
                    "reason": (
                        f"invalid_weights_before: weights at {target_str} "
                        f"have sum={w_sum:.8f}, min={float(np.min(w_arr)):.8f}."
                    ),
                }
            )
            continue

        # 3. Locate strictly prior asset returns (preserving full prior history before weights_before.index[0])
        prior_end_pos = int(return_index.searchsorted(target_ts, side="left"))
        target_ret_pos = return_pos_map.get(target_ts, -1)

        # Evaluate whether realized return at t is present, finite, and not a gap-spanning return
        realized_loss: float | None = None
        realized_error_reason: str | None = None
        if target_ret_pos < 0:
            realized_error_reason = (
                f"missing_target_asset_returns: target session {target_str} "
                "is absent from asset_returns."
            )
        elif not return_row_finite[target_ret_pos]:
            realized_error_reason = (
                f"non_finite_target_asset_returns: asset_returns at {target_str} "
                "contains NaN or inf."
            )
        else:
            r_t = return_matrix[target_ret_pos]
            if prior_end_pos > 0:
                prev_nyse = int(return_nyse_idx[prior_end_pos - 1])
                prev_str = return_date_strs[prior_end_pos - 1]
                if prev_nyse < 0:
                    realized_error_reason = (
                        f"non_nyse_session_in_asset_returns: {prev_str} "
                        "preceding target is not an NYSE session."
                    )
                elif target_nyse_idx - prev_nyse != 1:
                    expected_prev = nyse_grid[target_nyse_idx - 1].strftime("%Y-%m-%d")
                    realized_error_reason = (
                        f"missing_nyse_session_before_target: expected preceding NYSE session {expected_prev} "
                        f"before {target_str}, but found {prev_str} "
                        "(gap-spanning return rejected as 1-day pair)."
                    )
                else:
                    realized_loss = -float(r_t @ w_arr)
            else:
                realized_loss = -float(r_t @ w_arr)

        # 4. Check training window length
        if prior_end_pos < win:
            t_start = return_index[0] if prior_end_pos > 0 else None
            t_end = return_index[prior_end_pos - 1] if prior_end_pos > 0 else None
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": t_start,
                    "train_end": t_end,
                    "status": "unavailable",
                    "reason": (
                        f"insufficient_training_history: need {win} prior asset-return sessions "
                        f"before {target_str}, found {prior_end_pos}."
                    ),
                }
            )
            continue

        train_start_pos = prior_end_pos - win
        train_end_pos = prior_end_pos - 1
        train_start_ts = return_index[train_start_pos]
        train_end_ts = return_index[train_end_pos]
        train_start_str = return_date_strs[train_start_pos]
        train_end_str = return_date_strs[train_end_pos]

        # Strict causality assertion: train_end < t
        assert train_end_ts < target_ts, f"Look-ahead violation: train_end {train_end_ts} >= target {target_ts}"

        # 5. Verify NYSE session continuity across [train_start_ts, ..., train_end_ts, target_ts]
        slice_nyse_idx = return_nyse_idx[train_start_pos:prior_end_pos]
        if np.any(slice_nyse_idx < 0):
            bad_dates = [
                return_date_strs[train_start_pos + k]
                for k in range(win)
                if slice_nyse_idx[k] < 0
            ]
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": None,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": (
                        f"non_nyse_session_in_training_window: non-NYSE dates {bad_dates[:3]} "
                        f"found in training window [{train_start_str}, {train_end_str}]."
                    ),
                }
            )
            continue

        if target_nyse_idx - int(slice_nyse_idx[-1]) != 1:
            expected_prev = nyse_grid[target_nyse_idx - 1].strftime("%Y-%m-%d")
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": None,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": (
                        f"missing_nyse_session_before_target: expected preceding NYSE session {expected_prev} "
                        f"before {target_str}, found {train_end_str}."
                    ),
                }
            )
            continue

        if int(slice_nyse_idx[-1]) - int(slice_nyse_idx[0]) != win - 1:
            n_missing = (int(slice_nyse_idx[-1]) - int(slice_nyse_idx[0])) - (win - 1)
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": (
                        f"missing_nyse_session_in_training_window: {n_missing} missing NYSE session(s) "
                        f"inside training window [{train_start_str}, {train_end_str}]."
                    ),
                }
            )
            continue

        # 6. Check finite values inside the training window
        if not np.all(return_row_finite[train_start_pos:prior_end_pos]):
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": (
                        f"non_finite_training_returns: NaN or inf in training window "
                        f"[{train_start_str}, {train_end_str}]."
                    ),
                }
            )
            continue

        # 7. Invoke generic RiskForecastFn on isolated copies of training returns and pre-return weights
        train_arg = pd.DataFrame(
            return_matrix[train_start_pos:prior_end_pos].copy(),
            index=return_index[train_start_pos:prior_end_pos],
            columns=canonical_cols,
            copy=False,
        )
        weights_arg = pd.Series(
            w_arr.copy(),
            index=canonical_cols,
            name=target_ts,
            dtype=float,
            copy=False,
        )

        try:
            est = forecast_fn(
                train_arg,
                weights_arg,
                confidence=conf,
                seed=base_seed,
            )
        except NotImplementedError:
            raise
        except Exception as exc:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": f"forecast_callback_error: {type(exc).__name__}: {exc}",
                }
            )
            continue

        if not isinstance(est, RiskEstimate):
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": f"forecast_callback_invalid_return_type: expected RiskEstimate, got {type(est).__name__}.",
                }
            )
            continue

        est_model = str(est.model).strip() if isinstance(est.model, str) else ""
        if not est_model:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": "forecast_callback_missing_model_name: RiskEstimate.model is empty.",
                }
            )
            continue

        if discovered_model is None:
            discovered_model = est_model
        elif est_model != discovered_model:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": (
                        f"forecast_callback_model_mismatch: callback returned model={est_model!r}, "
                        f"expected {discovered_model!r}."
                    ),
                }
            )
            continue

        if abs(float(est.confidence) - conf) > 1e-9:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": (
                        f"forecast_callback_confidence_mismatch: requested confidence={conf}, "
                        f"callback returned {est.confidence}."
                    ),
                }
            )
            continue

        if int(est.horizon_days) != 1:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": f"forecast_callback_horizon_mismatch: expected 1-day horizon, got {est.horizon_days}.",
                }
            )
            continue

        if int(est.n_obs) != win:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": f"forecast_callback_n_obs_mismatch: expected n_obs={win}, got {est.n_obs}.",
                }
            )
            continue

        if est.sample_start is not None and pd.Timestamp(est.sample_start).normalize() != train_start_ts:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": (
                        f"forecast_callback_sample_start_mismatch: expected {train_start_str}, "
                        f"got {est.sample_start}."
                    ),
                }
            )
            continue

        if est.sample_end is not None and pd.Timestamp(est.sample_end).normalize() != train_end_ts:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": None,
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": (
                        f"forecast_callback_sample_end_mismatch: expected {train_end_str}, "
                        f"got {est.sample_end}."
                    ),
                }
            )
            continue

        # 8. Distinguish unavailable forecast vs eligible warning/ok forecast
        if est.status == "unavailable" or est.var_loss is None or not math.isfinite(float(est.var_loss)):
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": None,
                    "forecast_es": (
                        float(est.es_loss)
                        if (est.es_loss is not None and math.isfinite(float(est.es_loss)))
                        else None
                    ),
                    "realized_loss": realized_loss,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": est.reason or "forecast_var_unavailable",
                }
            )
            continue

        f_var = float(est.var_loss)
        f_es = float(est.es_loss) if (est.es_loss is not None and math.isfinite(float(est.es_loss))) else None

        if realized_loss is None:
            raw_rows.append(
                {
                    "date": target_ts,
                    "model": discovered_model,
                    "confidence": conf,
                    "forecast_var": f_var,
                    "forecast_es": f_es,
                    "realized_loss": None,
                    "exceedance": None,
                    "train_start": train_start_ts,
                    "train_end": train_end_ts,
                    "status": "unavailable",
                    "reason": realized_error_reason or "missing_realized_loss",
                }
            )
            continue

        is_exceedance = bool(realized_loss > f_var)
        row_status = "warning" if est.status == "warning" else "ok"
        row_reason = (est.reason or "warning_forecast_status") if row_status == "warning" else None

        raw_rows.append(
            {
                "date": target_ts,
                "model": discovered_model,
                "confidence": conf,
                "forecast_var": f_var,
                "forecast_es": f_es,
                "realized_loss": realized_loss,
                "exceedance": is_exceedance,
                "train_start": train_start_ts,
                "train_end": train_end_ts,
                "status": row_status,
                "reason": row_reason,
            }
        )

    final_model = discovered_model or str(getattr(forecast_fn, "__name__", "unknown_model"))
    for r in raw_rows:
        if r["model"] is None:
            r["model"] = final_model

    attrs = {
        "confidence": conf,
        "window": win,
        "horizon_days": 1,
        "loss_convention": "gross_market_loss = -(weights_before[t] @ asset_returns[t]); pre-cost",
        "target_policy": "all expected NYSE sessions between first and last supplied weights date",
        "calendar": "shared expected_nyse_sessions",
        "seed": base_seed,
        "seed_policy": "same base seed at each origin; deterministic common random numbers; independent of future target count",
        "model": final_model,
        "target_start": weights_df.index[0].strftime("%Y-%m-%d"),
        "target_end": weights_df.index[-1].strftime("%Y-%m-%d"),
    }
    return _format_backtest_dataframe(raw_rows, attrs=attrs)


def coverage_tests(backtest_rows: pd.DataFrame) -> pd.DataFrame:
    """Compute Kupiec unconditional coverage, Christoffersen independence, and conditional coverage LR tests."""
    return _coverage_tests_impl(backtest_rows)


def basel_traffic_light(backtest_rows_99: pd.DataFrame) -> dict[str, Any]:
    """Evaluate educational Basel traffic-light diagnostic on 250 consecutive valid 99% 1-day pairs."""
    return _basel_traffic_light_impl(backtest_rows_99)
