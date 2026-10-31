"""Portfolio performance KPIs and CAPM diagnostics (SOLO STEP 4 / A2).

Public interface frozen in D0:
- ``compute_kpis(portfolio_returns, benchmark_returns, market_returns, rf_daily) -> pd.DataFrame``
"""

from __future__ import annotations

import pandas as pd


def compute_kpis(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    market_returns: pd.Series,
    rf_daily: pd.Series | None,
) -> pd.DataFrame:
    """Compute mandatory performance KPIs and CAPM regression metrics.

    Specification (SOLO STEP 4 / A2):
    - Output columns exactly match ``KPI_COLUMNS = ('metric', 'value', 'unit', 'status', 'note')``.
    - Metrics include geometric annual return, arithmetic annual return, annualized volatility,
      Sharpe, Sortino (downside deviation over all observations vs target), Treynor,
      CAPM beta and Jensen alpha (vs ``SPY`` market proxy), Information Ratio / tracking error
      (vs monthly-rebalanced 60/40 ``SPY/AGG`` benchmark), Max Drawdown (including initial
      wealth 1.0), and Calmar ratio.
    - If ``rf_daily`` is missing or incomplete, mark RF-dependent KPIs ``unavailable`` with
      explicit reasons rather than fabricating zeros.
    """
    raise NotImplementedError(
        "compute_kpis is a D0 interface stub scheduled for implementation in SOLO STEP 4 (A2)."
    )
