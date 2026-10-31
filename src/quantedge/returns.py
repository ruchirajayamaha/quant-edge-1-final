"""Session-aware simple/log return construction, RF alignment, and stationarity checks.

Interfaces declared in D0 for SOLO STEP 2 (A1) and SOLO STEP 4 (A2):
- ``compute_session_returns(prices) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]``
- ``align_risk_free_rate(raw_dtb3_annual_pct, return_dates, ...) -> pd.Series``
- ``run_stationarity_diagnostics(series_map) -> pd.DataFrame``
"""

from __future__ import annotations

import pandas as pd


def compute_session_returns(
    prices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute one-session simple and log returns without implicit price fill.

    Specification (SOLO STEP 2 / A1):
    - Calculate ``simple_returns = P_t / P_{t-1} - 1`` on the uncollapsed session grid
      with no artificial first-day zero and no implicit forward fill.
    - Any missing price invalidates adjacent one-session returns requiring it; exclude
      and record affected return rows only AFTER calculating returns so multi-session
      moves are never mislabelled as one-day returns.
    - Calculate ``log_returns = log1p(simple_returns)`` on the exact same index/columns.
    - Return ``(simple_returns, log_returns, excluded_return_rows)``.
    """
    raise NotImplementedError(
        "compute_session_returns is a D0 interface stub scheduled for SOLO STEP 2 (A1)."
    )


def align_risk_free_rate(
    raw_dtb3_annual_pct: pd.Series,
    return_dates: pd.DatetimeIndex,
    *,
    availability_lag_sessions: int = 1,
    trading_days_per_year: int = 252,
) -> pd.Series:
    """Align raw annual-percent DTB3 quotes to return dates using past-only values.

    Specification (SOLO STEP 2 / A1):
    - Convert annual-percent discount-basis quote via ``(rate_pct / 100.0) / trading_days_per_year``
      as an explicitly documented trading-day risk-free proxy.
    - Apply ``availability_lag_sessions`` and forward-align from past available observations only;
      never backfill initial missing values from future quotes.
    """
    raise NotImplementedError(
        "align_risk_free_rate is a D0 interface stub scheduled for SOLO STEP 2 (A1)."
    )


def run_stationarity_diagnostics(
    series_map: dict[str, pd.Series],
) -> pd.DataFrame:
    """Run Augmented Dickey-Fuller (ADF) stationarity diagnostics on named return series.

    Specification (SOLO STEP 2 / A1 and SOLO STEP 4 / A2):
    - Report ADF test statistic, p-value, used lags, observation count, and plain-language
      interpretation without claiming stationarity implies iid or constant volatility.
    """
    raise NotImplementedError(
        "run_stationarity_diagnostics is a D0 interface stub scheduled for SOLO STEP 2 (A1)."
    )
