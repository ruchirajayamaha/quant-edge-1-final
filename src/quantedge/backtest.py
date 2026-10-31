"""Out-of-sample rolling VaR validation, Kupiec/Christoffersen tests, and Basel diagnostic.

Public interfaces frozen in D0 for SOLO STEP 6 (A3):
- ``rolling_backtest(asset_returns, weights_before, forecast_fn, *, confidence, window, seed=None) -> pd.DataFrame``
- ``coverage_tests(backtest_rows) -> pd.DataFrame``
- ``basel_traffic_light(backtest_rows_99) -> dict[str, Any]``
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantedge.contracts import RiskForecastFn


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
    - For target session ``t``, slices strictly the prior ``window`` sessions, asserts
      ``train_end < t``, forecasts risk for exposure ``weights_before.loc[t]``, and compares
      against realized gross market loss ``-(weights_before.loc[t] @ asset_returns.loc[t])``.
    - Exceedance is strictly ``realized_loss > forecast_var``; invalid/skipped rows are
      retained with ``status`` and ``reason`` (never encoded as non-exceedances).
    - Output columns match ``BACKTEST_COLUMNS``.
    """
    raise NotImplementedError(
        "rolling_backtest is a D0 interface stub scheduled for SOLO STEP 6 (A3)."
    )


def coverage_tests(backtest_rows: pd.DataFrame) -> pd.DataFrame:
    """Compute Kupiec unconditional coverage, Christoffersen independence, and conditional coverage LR tests."""
    raise NotImplementedError(
        "coverage_tests is a D0 interface stub scheduled for SOLO STEP 6 (A3)."
    )


def basel_traffic_light(backtest_rows_99: pd.DataFrame) -> dict[str, Any]:
    """Evaluate educational Basel traffic-light diagnostic on 250 consecutive valid 99% 1-day pairs.

    Specification (SOLO STEP 6 / A3):
    - Standard zones (green 0-4, yellow 5-9, red 10+) apply ONLY to 250 consecutive valid
      one-day 99% forecast/realization pairs without cherry-picking around gaps.
    - Returns explicit insufficient/not-applicable status when continuity, sample length,
      or confidence requirements are not met.
    """
    raise NotImplementedError(
        "basel_traffic_light is a D0 interface stub scheduled for SOLO STEP 6 (A3)."
    )
