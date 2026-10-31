"""Euler marginal/component VaR & ES risk budgeting and feasible sizing comparisons.

Public interfaces frozen in D0 for SOLO STEP 8 (B2):
- ``risk_contributions(train_asset_returns, weights, *, confidence, method) -> pd.DataFrame``
- ``compare_feasible_allocations(train_asset_returns, candidates, limits, risk_fn) -> pd.DataFrame``
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantedge.contracts import RiskForecastFn, StrategySpec


def risk_contributions(
    train_asset_returns: pd.DataFrame,
    weights: pd.Series,
    *,
    confidence: float,
    method: str,
) -> pd.DataFrame:
    """Compute marginal, component, and percentage VaR/ES contributions across the 7 ETFs.

    Specification (SOLO STEP 8 / B2):
    - Uses ``var.normal_moments`` (``ddof=1``) for homogeneous un-clipped normal VaR/ES Euler
      decompositions and ``es.empirical_tail_weights`` for historical ES contributions so
      component risks sum identically to total portfolio risk.
    - Preserves negative hedge contributions without ``abs()``; marks percentage contributions
      ``unavailable`` if total risk is zero or nonpositive.
    """
    raise NotImplementedError(
        "risk_contributions is a D0 interface stub scheduled for SOLO STEP 8 (B2)."
    )


def compare_feasible_allocations(
    train_asset_returns: pd.DataFrame,
    candidates: dict[str, pd.Series | StrategySpec],
    limits: dict[str, Any],
    risk_fn: RiskForecastFn,
) -> pd.DataFrame:
    """Evaluate feasible position-sizing alternatives within the 7-ETF allocation universe.

    Specification (SOLO STEP 8 / B2):
    - Redistributes weights exclusively among the seven canonical ETFs (never silently
      introducing cash), reporting constraint feasibility, expected-return assumptions,
      before/after risk, and quantified return/risk trade-offs.
    """
    raise NotImplementedError(
        "compare_feasible_allocations is a D0 interface stub scheduled for SOLO STEP 8 (B2)."
    )
