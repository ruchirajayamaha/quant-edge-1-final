"""Session-aware simple/log return construction, NYSE calendar, RF alignment, and ADF diagnostics.

Implemented in SOLO STEP 2 (milestone A1).

Mathematical & Data-Hygiene Conventions:
- Portfolio cross-sectional aggregation at horizon ``t`` is exact in simple returns
  (``R_{p,t} = sum_i w_{i,t-} R_{i,t}``), and committee loss risk uses simple portfolio
  losses (``L_t = -R_{p,t}``). Weighted asset log returns must NEVER be summed as the
  portfolio log return because ``log`` is strictly concave (Jensen's inequality).
- Multi-period compounding is additive in log returns ``r_{i,t} = log(1 + R_{i,t})``,
  so statistical time-series diagnostics (ADF unit-root tests, correlation tables) run
  on ``log_returns``.
- Returns are computed on the uncollapsed trading-session price grid with ZERO implicit
  forward-fill. Any missing price at session ``t`` invalidates both ``t-1 -> t`` and
  ``t -> t+1`` one-session returns; incomplete rows are excluded and counted only AFTER
  return calculation so multi-session moves are never mislabelled as one-day returns.
- FRED ``DTB3`` quotes (annual percent, discount basis) are converted via the documented
  daily proxy ``(rate_pct / 100.0) / trading_days_per_year``. Forward-decision alignment
  models the actual decision cutoff (preceding NYSE close, ``16:00:00 America/New_York``)
  against verified release timestamps or the Federal Reserve H.15 publication schedule
  proxy (``16:15:00 America/New_York`` on the next Federal Reserve business day, requiring
  ``available_at <= decision_time`` with zero backfill), explicitly distinct from the
  contemporaneous ex-post daily proxy (``mode='ex_post'``). That schedule misses Board
  closures and omitted Treasury data, so ``select_rf_versions_asof`` applies the
  evidence-based, value-versioned ``r3_release_evidence`` policy instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, time, timedelta
import inspect
from typing import Any, Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

RFAlignmentMode = Literal["forward_decision", "ex_post", "legacy_bday_lag"]

_ADFULLER_SUPPORTS_RESULT_OBJECT: bool = "result_object" in inspect.signature(adfuller).parameters

EXCLUDED_RETURN_COLUMNS: tuple[str, ...] = (
    "date",
    "session_position",
    "missing_price_tickers_t",
    "missing_price_tickers_t_minus_1",
    "invalid_return_tickers",
    "n_invalid_tickers",
    "reason",
)

ADF_DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "series",
    "n_obs",
    "adf_stat",
    "p_value",
    "used_lag",
    "crit_1pct",
    "crit_5pct",
    "crit_10pct",
    "reject_unit_root_5pct",
    "status",
    "note",
)

# Documented NYSE unplanned / special full-day closures since 2005-01-01:
# - 2007-01-02: National Day of Mourning for President Gerald R. Ford
# - 2012-10-29 & 2012-10-30: Hurricane Sandy
# - 2018-12-05: National Day of Mourning for President George H.W. Bush
# - 2025-01-09: National Day of Mourning for President Jimmy Carter
NYSE_SPECIAL_CLOSURES: frozenset[date] = frozenset(
    {
        date(2007, 1, 2),
        date(2012, 10, 29),
        date(2012, 10, 30),
        date(2018, 12, 5),
        date(2025, 1, 9),
    }
)


def _easter_sunday(year: int) -> date:
    """Compute Gregorian Easter Sunday using the anonymous Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> date:
    """Return the ``nth`` (1-based) occurrence of ``weekday`` (0=Mon..6=Sun) in ``month``."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (nth - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the final occurrence of ``weekday`` (0=Mon..6=Sun) in ``month``."""
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _observe_fixed_holiday(holiday: date, *, allow_prior_year_friday: bool = True) -> date | None:
    """Apply NYSE Rule 7.2 weekend observance for fixed-date holidays."""
    if holiday.weekday() == 5:  # Saturday -> preceding Friday (except Dec 31 accounting year-end)
        observed = holiday - timedelta(days=1)
        if not allow_prior_year_friday and observed.year < holiday.year:
            return None
        return observed
    if holiday.weekday() == 6:  # Sunday -> following Monday
        return holiday + timedelta(days=1)
    return holiday


def _nyse_holidays_for_year(year: int) -> set[date]:
    """Return full-day NYSE holidays and documented special closures for ``year``."""
    holidays: set[date] = set()

    # 1. New Year's Day (NYSE Rule 7.2: Saturday Jan 1 is NOT observed on Dec 31)
    nyd = _observe_fixed_holiday(date(year, 1, 1), allow_prior_year_friday=False)
    if nyd is not None:
        holidays.add(nyd)

    # 2. Martin Luther King, Jr. Day (3rd Monday in January)
    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))

    # 3. Washington's Birthday / Presidents' Day (3rd Monday in February)
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))

    # 4. Good Friday (2 days before Easter Sunday)
    holidays.add(_easter_sunday(year) - timedelta(days=2))

    # 5. Memorial Day (last Monday in May)
    holidays.add(_last_weekday_of_month(year, 5, 0))

    # 6. Juneteenth National Independence Day (observed by NYSE starting in 2022)
    if year >= 2022:
        juneteenth = _observe_fixed_holiday(date(year, 6, 19))
        if juneteenth is not None:
            holidays.add(juneteenth)

    # 7. Independence Day (July 4)
    july4 = _observe_fixed_holiday(date(year, 7, 4))
    if july4 is not None:
        holidays.add(july4)

    # 8. Labor Day (1st Monday in September)
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))

    # 9. Thanksgiving Day (4th Thursday in November)
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))

    # 10. Christmas Day (December 25)
    xmas = _observe_fixed_holiday(date(year, 12, 25))
    if xmas is not None:
        holidays.add(xmas)

    for closure in NYSE_SPECIAL_CLOSURES:
        if closure.year == year:
            holidays.add(closure)

    return holidays


def expected_nyse_sessions(
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
) -> pd.DatetimeIndex:
    """Construct the expected NYSE regular trading-session ``DatetimeIndex`` over ``[start_date, end_date]``."""
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    if end_ts < start_ts:
        raise ValueError(f"end_date ({end_ts}) must be >= start_date ({start_ts}).")

    weekdays = pd.bdate_range(start=start_ts, end=end_ts, freq="B")
    holidays: set[pd.Timestamp] = set()
    for yr in range(start_ts.year, end_ts.year + 1):
        for h in _nyse_holidays_for_year(yr):
            holidays.add(pd.Timestamp(h))

    sessions = weekdays[~weekdays.isin(holidays)]
    sessions.name = "date"
    return sessions


def _observe_federal_fixed_holiday(holiday: date) -> date:
    """Apply US OPM (5 U.S.C. 6103) weekend observance for federal holidays (Sat->Fri, Sun->Mon)."""
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _federal_holidays_for_year(year: int) -> set[date]:
    """Return US Federal Reserve / OPM non-publication holidays plus documented market closures.

    Covers all 11 US federal holidays (including Columbus Day and Veterans Day when NYSE is open
    but the Federal Reserve Board H.15 release does not publish, as well as Friday Dec 31 when
    New Year's Day falls on Saturday and Juneteenth starting in 2021), plus Good Friday and
    documented special national closures. This is a schedule, not release evidence: it omits
    unscheduled Board closures and skips some Good Fridays on which H.15 was in fact released.
    """
    holidays: set[date] = set()

    # 1. New Year's Day (OPM rule: Saturday Jan 1 of year+1 is observed on Friday Dec 31 of year)
    nyd_curr = _observe_federal_fixed_holiday(date(year, 1, 1))
    if nyd_curr.year == year:
        holidays.add(nyd_curr)
    nyd_next = _observe_federal_fixed_holiday(date(year + 1, 1, 1))
    if nyd_next.year == year:
        holidays.add(nyd_next)

    # 2. Martin Luther King, Jr. Day (3rd Monday in January)
    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))

    # 3. Washington's Birthday (3rd Monday in February)
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))

    # 4. Good Friday (SIFMA/Treasury market closure guard; H.15 is often still released)
    holidays.add(_easter_sunday(year) - timedelta(days=2))

    # 5. Memorial Day (last Monday in May)
    holidays.add(_last_weekday_of_month(year, 5, 0))

    # 6. Juneteenth National Independence Day (federal holiday starting in June 2021)
    if year >= 2021:
        holidays.add(_observe_federal_fixed_holiday(date(year, 6, 19)))

    # 7. Independence Day (July 4)
    holidays.add(_observe_federal_fixed_holiday(date(year, 7, 4)))

    # 8. Labor Day (1st Monday in September)
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))

    # 9. Columbus Day (2nd Monday in October — NYSE open, Federal Reserve Board H.15 closed)
    holidays.add(_nth_weekday_of_month(year, 10, 0, 2))

    # 10. Veterans Day (November 11 — NYSE open, Federal Reserve Board H.15 closed)
    holidays.add(_observe_federal_fixed_holiday(date(year, 11, 11)))

    # 11. Thanksgiving Day (4th Thursday in November)
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))

    # 12. Christmas Day (December 25)
    holidays.add(_observe_federal_fixed_holiday(date(year, 12, 25)))

    for closure in NYSE_SPECIAL_CLOSURES:
        if closure.year == year:
            holidays.add(closure)

    return holidays


def expected_federal_reserve_business_days(
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
) -> pd.DatetimeIndex:
    """Construct scheduled Federal Reserve H.15 publication business days over ``[start_date, end_date]``."""
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    if end_ts < start_ts:
        raise ValueError(f"end_date ({end_ts}) must be >= start_date ({start_ts}).")

    weekdays = pd.bdate_range(start=start_ts, end=end_ts, freq="B")
    holidays: set[pd.Timestamp] = set()
    for yr in range(start_ts.year, end_ts.year + 1):
        for h in _federal_holidays_for_year(yr):
            holidays.add(pd.Timestamp(h))

    pub_days = weekdays[~weekdays.isin(holidays)]
    pub_days.name = "date"
    return pub_days


def _preceding_close_decision_times_utc(
    normalized_targets: pd.DatetimeIndex,
    price_sessions: pd.DatetimeIndex | None,
    decision_timezone: str,
    cutoff_t: time,
) -> pd.DatetimeIndex:
    """Return the preceding NYSE session's decision cutoff, in UTC, for each return date."""
    tz = ZoneInfo(decision_timezone)
    base_nyse = expected_nyse_sessions(
        normalized_targets[0] - pd.Timedelta(days=20),
        normalized_targets[-1],
    )
    if price_sessions is not None:
        if not isinstance(price_sessions, pd.DatetimeIndex) or len(price_sessions) == 0:
            raise ValueError("price_sessions, when supplied, must be a non-empty DatetimeIndex.")
        norm_ps = (
            price_sessions.tz_convert(decision_timezone).tz_localize(None)
            if price_sessions.tz is not None
            else price_sessions
        ).normalize()
        norm_ps = pd.DatetimeIndex(norm_ps).sort_values().unique()
        session_pool = base_nyse[base_nyse < norm_ps[0]].append(norm_ps)
    else:
        session_pool = base_nyse

    prev_pos = (
        np.searchsorted(session_pool.to_numpy(), normalized_targets.to_numpy(), side="left") - 1
    )
    if np.any(prev_pos < 0):
        raise ValueError(
            "Could not determine preceding NYSE trading session prior to earliest return date."
        )
    prev_dates = session_pool[prev_pos]
    cutoff_delta = pd.Timedelta(
        hours=cutoff_t.hour,
        minutes=cutoff_t.minute,
        seconds=cutoff_t.second,
        microseconds=cutoff_t.microsecond,
    )
    return (prev_dates + cutoff_delta).tz_localize(tz).tz_convert("UTC")


def compute_session_returns(
    prices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute one-session simple and log returns without implicit price fill.

    Args:
        prices: Adjusted close ``DataFrame`` on an uncollapsed trading-session grid
            with a unique, strictly ascending ``DatetimeIndex`` and strictly positive
            observed prices.

    Returns:
        Tuple ``(simple_returns, log_returns, excluded_return_rows)`` where:
        - ``simple_returns``: Complete one-session ``P_t / P_{t-1} - 1`` rows only.
        - ``log_returns``: ``log1p(simple_returns)`` with identical index and columns.
        - ``excluded_return_rows``: Tidy audit table of post-anchor sessions excluded
          due to missing endpoint prices at ``t`` or ``t-1`` (exposing continuity gaps).
    """
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        raise ValueError("prices must be a non-empty pandas DataFrame.")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("prices.index must be a pandas DatetimeIndex.")
    if not prices.index.is_monotonic_increasing or not prices.index.is_unique:
        raise ValueError("prices.index must be strictly ascending and unique.")
    if prices.columns.duplicated().any() or len(prices.columns) == 0:
        raise ValueError("prices must have non-empty unique ticker columns.")
    if len(prices) < 2:
        raise ValueError("prices must contain at least 2 trading sessions to compute returns.")

    numeric_prices = prices.astype(float)
    observed_vals = numeric_prices.to_numpy()[~np.isnan(numeric_prices.to_numpy())]
    if observed_vals.size == 0:
        raise ValueError("prices contains zero finite observed values.")
    if np.any(~np.isfinite(observed_vals)) or np.any(observed_vals <= 0.0):
        raise ValueError("All observed (non-NaN) prices must be finite and strictly positive (> 0).")

    # Uncollapsed one-session return calculation with ZERO implicit fill:
    # A missing price at session t invalidates both t-1 -> t and t -> t+1 returns.
    prev_prices = numeric_prices.shift(1)
    raw_simple = numeric_prices.div(prev_prices) - 1.0

    # Row 0 is the initial price anchor (never turned into an artificial 0.0 return).
    post_anchor_simple = raw_simple.iloc[1:]
    post_anchor_prices_t = numeric_prices.iloc[1:]
    post_anchor_prices_prev = prev_prices.iloc[1:]

    incomplete_mask = post_anchor_simple.isna().any(axis=1)
    excluded_records: list[dict[str, object]] = []
    tickers = list(numeric_prices.columns)

    for pos_offset, (dt, is_incomplete) in enumerate(incomplete_mask.items(), start=1):
        if not is_incomplete:
            continue
        miss_t = [t for t in tickers if pd.isna(post_anchor_prices_t.at[dt, t])]
        miss_prev = [t for t in tickers if pd.isna(post_anchor_prices_prev.at[dt, t])]
        inv_ret = [t for t in tickers if pd.isna(post_anchor_simple.at[dt, t])]
        if miss_t and miss_prev:
            reason = "missing_price_at_both_endpoints"
        elif miss_t:
            reason = "missing_price_at_t"
        else:
            reason = "missing_price_at_t_minus_1"

        excluded_records.append(
            {
                "date": dt,
                "session_position": int(pos_offset),
                "missing_price_tickers_t": ",".join(miss_t),
                "missing_price_tickers_t_minus_1": ",".join(miss_prev),
                "invalid_return_tickers": ",".join(inv_ret),
                "n_invalid_tickers": len(inv_ret),
                "reason": reason,
            }
        )

    if excluded_records:
        excluded_return_rows = pd.DataFrame(excluded_records, columns=list(EXCLUDED_RETURN_COLUMNS))
    else:
        excluded_return_rows = pd.DataFrame(columns=list(EXCLUDED_RETURN_COLUMNS))

    simple_returns = post_anchor_simple.loc[~incomplete_mask].copy()
    simple_returns.index.name = "date"

    if not simple_returns.empty and bool((simple_returns <= -1.0).any().any()):
        raise ValueError("Observed simple return <= -1.0 encountered; cannot compute finite log1p.")

    log_returns = pd.DataFrame(
        np.log1p(simple_returns.to_numpy(dtype=float)),
        index=simple_returns.index.copy(),
        columns=simple_returns.columns.copy(),
    )

    uninterrupted = bool(excluded_return_rows.empty)
    simple_returns.attrs["uninterrupted_sessions"] = uninterrupted
    simple_returns.attrs["n_excluded_return_rows"] = int(len(excluded_return_rows))
    log_returns.attrs["uninterrupted_sessions"] = uninterrupted
    log_returns.attrs["n_excluded_return_rows"] = int(len(excluded_return_rows))

    return simple_returns, log_returns, excluded_return_rows


def align_risk_free_rate(
    raw_dtb3_annual_pct: pd.Series,
    return_dates: pd.DatetimeIndex,
    *,
    availability_lag_sessions: int = 1,
    trading_days_per_year: int = 252,
    mode: RFAlignmentMode = "forward_decision",
    price_sessions: pd.DatetimeIndex | None = None,
    decision_timezone: str = "America/New_York",
    decision_cutoff_time_ny: str = "16:00:00",
    release_time_ny: str = "16:15:00",
    release_timestamps: pd.Series | Mapping[Any, Any] | None = None,
    decision_timestamps: pd.Series | pd.DatetimeIndex | None = None,
    require_verified_releases: bool = False,
) -> pd.Series:
    """Align raw annual-percent DTB3 quotes to return dates using past-only values.

    Formula & Release-Cutoff Conventions:
    - Daily fractional approximation: ``rf_daily = (rate_annual_pct / 100.0) / trading_days_per_year``.
      ``DTB3`` is quoted in annual percent on a 360-day bank-discount basis; dividing by
      ``252`` is an explicitly disclosed trading-day risk-free proxy, not an exact realized
      Treasury-bill holding-period return.
    - ``mode='forward_decision'`` (default):
      Models the actual portfolio/forecast decision cutoff for return date ``t``, which is the
      preceding NYSE session close strictly ``< t`` at ``decision_cutoff_time_ny`` (default
      ``16:00:00 America/New_York``), or explicit timezone-aware ``decision_timestamps``.
      Each valid ``DTB3`` observation dated ``d`` becomes usable at ``available_at``:
      * If ``release_timestamps`` provides a verified timezone-aware timestamp for ``d``, that
        exact release timestamp is used.
      * Otherwise (unless ``require_verified_releases=True``), ``available_at`` is assumed to be
        the ``availability_lag_sessions``-th Federal Reserve H.15 publication business day
        strictly after ``d`` (skipping all 11 US federal holidays including Columbus Day and
        Veterans Day, Good Friday, documented special closures, and any explicit ``NaN`` holiday
        dates in ``raw_dtb3_annual_pct``) at ``release_time_ny`` (default ``16:15:00 America/New_York``).
        Because ``16:15 ET > 16:00 ET``, an observation published on decision day ``t_{-1}`` at
        ``16:15 ET`` is NOT available before the ``16:00 ET`` close of ``t_{-1}``.
      Return date ``t`` receives the most recent valid observation satisfying
      ``available_at <= decision_time`` with zero backfill.
    - ``mode='ex_post'``:
      Contemporaneous ex-post daily proxy matching ``obs_date <= t`` (zero backfill). Explicitly
      tagged ``ex_post_contemporaneous_proxy_not_for_forward_decisions`` so it is never confused
      with release-time-available decision inputs.
    - ``mode='legacy_bday_lag'``:
      Date-only ``obs_date + BDay(L) <= t`` calculation retained solely for audit comparison;
      tagged ``legacy_bday_date_only_not_publication_verified``.
    """
    if not isinstance(return_dates, pd.DatetimeIndex):
        raise ValueError("return_dates must be a pandas DatetimeIndex.")
    if not return_dates.is_monotonic_increasing or not return_dates.is_unique:
        raise ValueError("return_dates must be strictly ascending and unique.")
    if availability_lag_sessions < 0:
        raise ValueError(f"availability_lag_sessions must be >= 0; got {availability_lag_sessions}")
    if trading_days_per_year <= 0:
        raise ValueError(f"trading_days_per_year must be > 0; got {trading_days_per_year}")
    if mode not in ("forward_decision", "ex_post", "legacy_bday_lag"):
        raise ValueError(
            f"Unsupported RF alignment mode {mode!r}; expected 'forward_decision', 'ex_post', or 'legacy_bday_lag'."
        )

    tz = ZoneInfo(decision_timezone)
    cutoff_t = time.fromisoformat(decision_cutoff_time_ny)
    release_t = time.fromisoformat(release_time_ny)

    series_name = "rf_daily_ex_post" if mode == "ex_post" else "rf_daily"
    rf_mode_tag = (
        "forward_decision_cutoff_proxy"
        if mode == "forward_decision"
        else (
            "ex_post_contemporaneous_proxy_not_for_forward_decisions"
            if mode == "ex_post"
            else "legacy_bday_date_only_not_publication_verified"
        )
    )

    normalized_targets = (
        return_dates.tz_convert(decision_timezone).tz_localize(None)
        if return_dates.tz is not None
        else return_dates
    ).normalize()

    if raw_dtb3_annual_pct is None or raw_dtb3_annual_pct.empty or len(normalized_targets) == 0:
        empty_s = pd.Series(np.nan, index=return_dates.copy(), name=series_name, dtype=float)
        empty_s.attrs["rf_mode"] = rf_mode_tag
        return empty_s

    raw_series = pd.to_numeric(raw_dtb3_annual_pct, errors="coerce")
    obs_idx = pd.to_datetime(raw_series.index)
    if obs_idx.tz is not None:
        obs_idx = obs_idx.tz_convert(decision_timezone).tz_localize(None)
    obs_idx = pd.DatetimeIndex(obs_idx).normalize()

    all_raw_df = (
        pd.DataFrame(
            {
                "obs_date": obs_idx,
                "rate_pct": raw_series.to_numpy(dtype=float),
            }
        )
        .sort_values("obs_date", kind="mergesort")
        .drop_duplicates(subset=["obs_date"], keep="last")
    )
    explicit_nan_dates = pd.DatetimeIndex(
        all_raw_df.loc[all_raw_df["rate_pct"].isna(), "obs_date"]
    )
    obs_df = all_raw_df.dropna(subset=["rate_pct"]).copy()

    if obs_df.empty:
        empty_s = pd.Series(np.nan, index=return_dates.copy(), name=series_name, dtype=float)
        empty_s.attrs["rf_mode"] = rf_mode_tag
        return empty_s

    obs_df["rf_daily"] = (obs_df["rate_pct"] / 100.0) / float(trading_days_per_year)

    if mode == "ex_post":
        target_df = pd.DataFrame({"target_date": normalized_targets})
        merged = pd.merge_asof(
            target_df,
            obs_df[["obs_date", "rf_daily"]],
            left_on="target_date",
            right_on="obs_date",
            direction="backward",
            allow_exact_matches=True,
        )
        aligned = pd.Series(
            merged["rf_daily"].to_numpy(dtype=float),
            index=return_dates.copy(),
            name=series_name,
            dtype=float,
        )
        aligned.attrs["rf_mode"] = rf_mode_tag
        return aligned

    if mode == "legacy_bday_lag":
        if availability_lag_sessions == 0:
            obs_df["available_date"] = obs_df["obs_date"]
        else:
            obs_df["available_date"] = obs_df["obs_date"] + pd.offsets.BDay(
                availability_lag_sessions
            )
        obs_df = obs_df.sort_values(["available_date", "obs_date"], kind="mergesort")
        obs_df = obs_df.drop_duplicates(subset=["available_date"], keep="last")
        target_df = pd.DataFrame({"target_date": normalized_targets})
        merged = pd.merge_asof(
            target_df,
            obs_df[["available_date", "rf_daily"]],
            left_on="target_date",
            right_on="available_date",
            direction="backward",
            allow_exact_matches=True,
        )
        aligned = pd.Series(
            merged["rf_daily"].to_numpy(dtype=float),
            index=return_dates.copy(),
            name=series_name,
            dtype=float,
        )
        aligned.attrs["rf_mode"] = rf_mode_tag
        return aligned

    # mode == "forward_decision": enforce available_at <= decision_time in UTC
    if decision_timestamps is not None:
        if isinstance(decision_timestamps, pd.Series):
            if decision_timestamps.index.equals(return_dates) or decision_timestamps.index.equals(
                normalized_targets
            ):
                dec_idx = pd.DatetimeIndex(decision_timestamps)
            else:
                raise ValueError("decision_timestamps Series index must match return_dates.")
        elif isinstance(decision_timestamps, pd.DatetimeIndex):
            if len(decision_timestamps) != len(return_dates):
                raise ValueError(
                    f"decision_timestamps length ({len(decision_timestamps)}) must match "
                    f"return_dates length ({len(return_dates)})."
                )
            dec_idx = decision_timestamps
        else:
            raise TypeError("decision_timestamps must be a pandas Series or DatetimeIndex.")

        if dec_idx.tz is None or bool(dec_idx.isna().any()):
            raise ValueError("decision_timestamps must contain non-null timezone-aware timestamps.")
        decision_utc = dec_idx.tz_convert("UTC")
    else:
        decision_utc = _preceding_close_decision_times_utc(
            normalized_targets, price_sessions, decision_timezone, cutoff_t
        )

    cal_start = obs_df["obs_date"].min()
    cal_end = max(obs_df["obs_date"].max(), normalized_targets.max()) + pd.Timedelta(
        days=35 + 7 * max(availability_lag_sessions, 1)
    )
    fed_bdays = expected_federal_reserve_business_days(cal_start, cal_end)
    pub_days = fed_bdays[~fed_bdays.isin(explicit_nan_dates)]
    if len(pub_days) == 0:
        raise ValueError("No candidate Federal Reserve H.15 publication business days available.")

    if availability_lag_sessions == 0:
        pub_pos = np.searchsorted(pub_days.to_numpy(), obs_df["obs_date"].to_numpy(), side="left")
    else:
        pub_pos = np.searchsorted(
            pub_days.to_numpy(),
            obs_df["obs_date"].to_numpy(),
            side="right",
        ) + (availability_lag_sessions - 1)

    if np.any(pub_pos >= len(pub_days)):
        raise ValueError("Insufficient future publication calendar horizon for RF availability.")

    sched_pub_dates = pub_days[pub_pos]
    release_delta = pd.Timedelta(
        hours=release_t.hour,
        minutes=release_t.minute,
        seconds=release_t.second,
        microseconds=release_t.microsecond,
    )
    sched_avail_utc = (sched_pub_dates + release_delta).tz_localize(tz).tz_convert("UTC")

    verified_map: dict[pd.Timestamp, pd.Timestamp] = {}
    if release_timestamps is not None:
        items_iter = (
            release_timestamps.items()
            if isinstance(release_timestamps, (pd.Series, Mapping))
            else None
        )
        if items_iter is None:
            raise TypeError("release_timestamps must be a pandas Series or Mapping.")
        for raw_k, raw_v in items_iter:
            if pd.isna(raw_v):
                continue
            k_ts = pd.Timestamp(raw_k)
            if k_ts.tzinfo is not None:
                k_ts = k_ts.tz_convert(tz).tz_localize(None)
            k_norm = k_ts.normalize()

            v_ts = pd.Timestamp(raw_v)
            if v_ts.tzinfo is None:
                raise ValueError(
                    f"release_timestamps[{raw_k!r}] = {raw_v!r} is timezone-naive; "
                    f"verified release timestamps must be timezone-aware."
                )
            verified_map[k_norm] = v_ts.tz_convert("UTC")

    avail_list: list[pd.Timestamp] = []
    for obs_d, sched_ts in zip(obs_df["obs_date"], sched_avail_utc, strict=True):
        if obs_d in verified_map:
            avail_list.append(verified_map[obs_d])
        elif require_verified_releases:
            avail_list.append(pd.NaT)
        else:
            avail_list.append(sched_ts)

    obs_df["available_utc"] = pd.DatetimeIndex(avail_list, tz="UTC")
    obs_df = obs_df.dropna(subset=["available_utc"]).copy()
    if obs_df.empty:
        empty_s = pd.Series(np.nan, index=return_dates.copy(), name=series_name, dtype=float)
        empty_s.attrs["rf_mode"] = rf_mode_tag
        return empty_s

    obs_df = obs_df.sort_values(["available_utc", "obs_date"], kind="mergesort")
    obs_df = obs_df.drop_duplicates(subset=["available_utc"], keep="last")

    target_df = pd.DataFrame(
        {
            "orig_pos": np.arange(len(normalized_targets), dtype=int),
            "decision_utc": decision_utc,
        }
    ).sort_values("decision_utc", kind="mergesort")

    merged = pd.merge_asof(
        target_df,
        obs_df[["available_utc", "rf_daily"]],
        left_on="decision_utc",
        right_on="available_utc",
        direction="backward",
        allow_exact_matches=True,
    ).sort_values("orig_pos", kind="mergesort")

    aligned = pd.Series(
        merged["rf_daily"].to_numpy(dtype=float),
        index=return_dates.copy(),
        name=series_name,
        dtype=float,
    )
    aligned.attrs["rf_mode"] = rf_mode_tag
    return aligned


def select_rf_versions_asof(
    version_table: pd.DataFrame,
    return_dates: pd.DatetimeIndex,
    *,
    trading_days_per_year: int = 252,
    price_sessions: pd.DatetimeIndex | None = None,
    decision_timezone: str = "America/New_York",
    decision_cutoff_time_ny: str = "16:00:00",
) -> tuple[pd.Series, pd.DataFrame]:
    """Select the value known at each decision cutoff from versioned DTB3 observations.

    For return date ``t`` the decision cutoff is the preceding NYSE session close. Among versions
    with ``available_at_utc <= decision_time``, each observation keeps its latest eligible version
    and withdrawn observations drop out. The most recent remaining OBSERVATION date is selected,
    never the most recently available version, so a late revision to an older observation cannot
    replace a newer quote. There is no backfill: a session with nothing eligible stays ``NaN``.

    Args:
        version_table: Rows with ``obs_date``, ``version_seq``, ``value_pct`` (``NaN`` marks a
            withdrawal) and timezone-aware ``available_at_utc``. Other columns pass through to
            the provenance table.
        return_dates: Ascending unique return session dates.
        trading_days_per_year: Daily proxy divisor.
        price_sessions: Optional session grid used to locate the preceding close.
        decision_timezone: IANA timezone of the cutoff.
        decision_cutoff_time_ny: Local cutoff time.

    Returns:
        ``(rf_daily, provenance)`` indexed by ``return_dates``. Provenance holds the decision
        cutoff, selected observation, value and version, and the version's evidence labels.
    """
    if not isinstance(return_dates, pd.DatetimeIndex):
        raise ValueError("return_dates must be a pandas DatetimeIndex.")
    if not return_dates.is_monotonic_increasing or not return_dates.is_unique:
        raise ValueError("return_dates must be strictly ascending and unique.")
    if trading_days_per_year <= 0:
        raise ValueError(f"trading_days_per_year must be > 0; got {trading_days_per_year}")
    table = version_table.reset_index(drop=True)
    if table["available_at_utc"].dt.tz is None:
        raise ValueError("available_at_utc must be timezone-aware.")

    decisions = _preceding_close_decision_times_utc(
        return_dates.normalize(),
        price_sessions,
        decision_timezone,
        time.fromisoformat(decision_cutoff_time_ny),
    )
    order = table.sort_values(
        ["available_at_utc", "obs_date", "version_seq"], kind="mergesort"
    ).index.to_numpy()
    available = table["available_at_utc"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()[order]
    obs_dates = table["obs_date"].to_numpy()[order]
    values = table["value_pct"].to_numpy(dtype=float)[order]
    versions = table["version_seq"].to_numpy(dtype=int)[order]

    latest: dict[np.datetime64, int] = {}
    live: set[np.datetime64] = set()
    selected = np.full(len(return_dates), -1, dtype=int)
    pointer = 0
    for i, cutoff in enumerate(decisions.tz_localize(None).to_numpy()):
        while pointer < len(order) and available[pointer] <= cutoff:
            obs = obs_dates[pointer]
            if obs not in latest or versions[pointer] >= versions[latest[obs]]:
                latest[obs] = pointer
                if np.isnan(values[pointer]):
                    live.discard(obs)
                else:
                    live.add(obs)
            pointer += 1
        if live:
            selected[i] = latest[max(live)]

    has_value = selected >= 0
    picked = table.iloc[order[selected[has_value]]]
    provenance = pd.DataFrame(index=pd.DatetimeIndex(return_dates, name="date"))
    provenance["decision_time_utc"] = decisions
    for column in table.columns:
        filled = pd.Series(picked[column].to_numpy(), index=return_dates[has_value]).reindex(return_dates)
        provenance[column] = filled.to_numpy()
    provenance["available_at_utc"] = pd.to_datetime(provenance["available_at_utc"], utc=True)
    rf_daily = pd.Series(
        (provenance["value_pct"].to_numpy(dtype=float) / 100.0) / float(trading_days_per_year),
        index=return_dates.copy(),
        name="rf_daily",
        dtype=float,
    )
    rf_daily.attrs["rf_mode"] = "versioned_release_evidence_day_level"
    provenance["rf_daily"] = rf_daily.to_numpy()
    return rf_daily, provenance


def run_stationarity_diagnostics(
    series_map: dict[str, pd.Series],
) -> pd.DataFrame:
    """Run Augmented Dickey-Fuller (ADF) unit-root diagnostics on named time series.

    Note: Rejecting a unit root indicates mean/level stationarity compatible with ``I(0)``
    behaviour; it does NOT imply i.i.d. observations, normality, or constant conditional
    volatility (GARCH/volatility clustering remains present in daily financial returns).
    """
    rows: list[dict[str, object]] = []
    for name, series in series_map.items():
        clean = pd.to_numeric(series, errors="coerce").dropna().astype(float)
        n_obs = int(len(clean))
        if n_obs < 20:
            rows.append(
                {
                    "series": name,
                    "n_obs": n_obs,
                    "adf_stat": np.nan,
                    "p_value": np.nan,
                    "used_lag": np.nan,
                    "crit_1pct": np.nan,
                    "crit_5pct": np.nan,
                    "crit_10pct": np.nan,
                    "reject_unit_root_5pct": None,
                    "status": "unavailable",
                    "note": f"Insufficient valid observations ({n_obs} < 20) for ADF test.",
                }
            )
            continue

        if float(clean.std(ddof=1)) <= 1e-15:
            rows.append(
                {
                    "series": name,
                    "n_obs": n_obs,
                    "adf_stat": np.nan,
                    "p_value": np.nan,
                    "used_lag": np.nan,
                    "crit_1pct": np.nan,
                    "crit_5pct": np.nan,
                    "crit_10pct": np.nan,
                    "reject_unit_root_5pct": None,
                    "status": "unavailable",
                    "note": "Constant / zero-variance series; ADF regression is degenerate.",
                }
            )
            continue

        adf_kwargs: dict[str, object] = {"regression": "c", "autolag": "AIC"}
        if _ADFULLER_SUPPORTS_RESULT_OBJECT:
            adf_kwargs["result_object"] = False
        adf_stat, p_val, used_lag, n_used, crit_vals, _ = adfuller(
            clean.to_numpy(dtype=float),
            **adf_kwargs,
        )
        reject_5pct = bool(float(p_val) < 0.05)
        if reject_5pct:
            note = (
                "Unit-root null rejected at 5% (level compatible with I(0)); "
                "does NOT imply i.i.d. returns or constant conditional volatility."
            )
        else:
            note = "Failed to reject unit-root null at 5%; inspect trend/non-stationarity."

        rows.append(
            {
                "series": name,
                "n_obs": int(n_used),
                "adf_stat": float(adf_stat),
                "p_value": float(p_val),
                "used_lag": int(used_lag),
                "crit_1pct": float(crit_vals["1%"]),
                "crit_5pct": float(crit_vals["5%"]),
                "crit_10pct": float(crit_vals["10%"]),
                "reject_unit_root_5pct": reject_5pct,
                "status": "ok",
                "note": note,
            }
        )

    return pd.DataFrame(rows, columns=list(ADF_DIAGNOSTIC_COLUMNS))


def compute_return_descriptive_stats(
    returns_df: pd.DataFrame,
    *,
    return_kind: Literal["simple", "log"] = "simple",
    annualization_days: int = 252,
) -> pd.DataFrame:
    """Compute per-ticker descriptive return statistics (fractions, ddof=1)."""
    rows: list[dict[str, object]] = []
    for ticker in returns_df.columns:
        s = pd.to_numeric(returns_df[ticker], errors="coerce").dropna().astype(float)
        n = int(len(s))
        if n == 0:
            continue
        mean_d = float(s.mean())
        std_d = float(s.std(ddof=1)) if n > 1 else np.nan
        ann_arith = mean_d * float(annualization_days)
        if return_kind == "simple":
            ann_geom = float(np.expm1(np.log1p(s).mean() * float(annualization_days)))
        else:
            ann_geom = float(np.expm1(mean_d * float(annualization_days)))
        ann_vol = std_d * float(np.sqrt(annualization_days)) if np.isfinite(std_d) else np.nan

        rows.append(
            {
                "ticker": str(ticker),
                "return_kind": return_kind,
                "n_obs": n,
                "start_date": s.index[0].strftime("%Y-%m-%d"),
                "end_date": s.index[-1].strftime("%Y-%m-%d"),
                "daily_mean": mean_d,
                "daily_std": std_d,
                "ann_arithmetic_return": ann_arith,
                "ann_geometric_return": ann_geom,
                "ann_volatility": ann_vol,
                "skewness": float(s.skew()) if n > 2 else np.nan,
                "excess_kurtosis": float(s.kurt()) if n > 3 else np.nan,
                "min": float(s.min()),
                "q01": float(s.quantile(0.01)),
                "q05": float(s.quantile(0.05)),
                "median": float(s.median()),
                "q95": float(s.quantile(0.95)),
                "q99": float(s.quantile(0.99)),
                "max": float(s.max()),
            }
        )

    return pd.DataFrame(rows)
