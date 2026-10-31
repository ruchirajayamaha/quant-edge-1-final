"""Portfolio weight optimization and drifting return-path construction (SOLO STEP 3 / B1).

Public interfaces frozen in D0:
- ``build_portfolio_path(asset_returns, strategy_spec, config) -> PortfolioPath``
- ``construct_weights(train_asset_returns, constraints, objective) -> pd.Series``
"""

from __future__ import annotations

import pandas as pd

from quantedge.config import AppConfig
from quantedge.contracts import PortfolioConstraints, PortfolioPath, StrategySpec


def build_portfolio_path(
    asset_returns: pd.DataFrame,
    strategy_spec: StrategySpec,
    config: AppConfig,
) -> PortfolioPath:
    """Construct a drifting portfolio return path under strict pre-return weight timing.

    Specification (SOLO STEP 3 / B1):
    - Decision at session close ``t-1`` uses only ``asset_returns`` through ``t-1`` to set
      ``weights_before.loc[t]`` for session ``t``'s close-to-close simple return.
    - Between scheduled rebalances, holdings weights drift proportionally with realized
      simple asset returns.
    - Rebalance turnover and transaction costs apply at the documented rebalance boundary.
    - Single shared engine used for constrained candidates, equal-weight reference, and
      the canonical monthly-rebalanced 60/40 ``SPY/AGG`` comparison benchmark.
    """
    raise NotImplementedError(
        "build_portfolio_path is a D0 interface stub scheduled for SOLO STEP 3 (B1)."
    )


def construct_weights(
    train_asset_returns: pd.DataFrame,
    constraints: PortfolioConstraints,
    objective: str,
) -> pd.Series:
    """Optimize or construct canonical-ticker portfolio weights from historical training data.

    Specification (SOLO STEP 3 / B1):
    - Returns a ``pd.Series`` indexed by ``CANONICAL_TICKERS`` using strictly past
      ``train_asset_returns``.
    - Supports core Markowitz constrained minimum-variance, mean-variance trade-off
      points, and reference allocations, verifying constraint feasibility explicitly.
    """
    raise NotImplementedError(
        "construct_weights is a D0 interface stub scheduled for SOLO STEP 3 (B1)."
    )
