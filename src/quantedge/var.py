"""Point-in-time Value-at-Risk (VaR) estimation, normal moments helper, and model registry.

Public interfaces frozen in D0 for SOLO STEP 5 (C1) and SOLO STEP 7 (C2/C3):
- ``normal_moments(asset_returns) -> tuple[pd.Series, pd.DataFrame]``
- ``estimate_risk(train_asset_returns, weights, *, model, confidence, seed=None) -> RiskEstimate``
- ``get_risk_forecaster(model) -> RiskForecastFn``
"""

from __future__ import annotations

import pandas as pd

from quantedge.contracts import RiskEstimate, RiskForecastFn


def normal_moments(
    asset_returns: pd.DataFrame,
) -> tuple[pd.Series, pd.DataFrame]:
    """Compute shared arithmetic sample mean and sample covariance (``ddof=1``).

    Frozen D0 contract (``CONTRACTS.md``):
    - ``mean_series``: arithmetic sample mean across rows of ``asset_returns``.
    - ``covariance_frame``: sample covariance matrix across columns with ``ddof=1``.
    - Reused identically across ``parametric_normal``, ``monte_carlo_normal``, and
      normal Euler risk-contribution calculations so total risk and component sums agree.
    """
    raise NotImplementedError(
        "normal_moments is a D0 interface stub scheduled for SOLO STEP 5 (C1)."
    )


def estimate_risk(
    train_asset_returns: pd.DataFrame,
    weights: pd.Series,
    *,
    model: str,
    confidence: float,
    seed: int | None = None,
) -> RiskEstimate:
    """Estimate one-day simple-return VaR and ES for a fixed portfolio exposure.

    Specification (SOLO STEP 5 / C1 and SOLO STEP 7 / C2):
    - Forms simple portfolio returns ``R_p = train_asset_returns @ weights`` and losses
      ``L = -R_p`` (positive numbers represent losses before transaction costs).
    - Dispatches ``model`` among ``'historical'``, ``'parametric_normal'``,
      ``'monte_carlo_normal'``, and ``'evt_pot'``.
    - For normal loss risk:
      ``VaR_c = -mu + z_c * sigma`` and ``ES_c = -mu + sigma * phi(z_c) / (1 - c)``.
    - Preserves nonpositive loss quantiles without ``abs()`` masking, and returns
      ``status='unavailable'`` with ``None`` metrics whenever model assumptions/domain fail.
    """
    raise NotImplementedError(
        "estimate_risk is a D0 interface stub scheduled for SOLO STEP 5 (C1)."
    )


def get_risk_forecaster(model: str) -> RiskForecastFn:
    """Return a ``RiskForecastFn`` callback bound to ``model`` for rolling backtesting."""
    raise NotImplementedError(
        "get_risk_forecaster is a D0 interface stub scheduled for SOLO STEP 5 (C1)."
    )
