"""Unconditional Peaks-Over-Threshold Generalized Pareto (POT-GPD) EVT tail models.

Public interfaces frozen in D0 for SOLO STEP 7 (C2/C3):
- ``estimate_evt_pot(train_asset_returns, weights, *, confidence, seed=None, ...) -> RiskEstimate``
- ``evt_threshold_diagnostics(losses, *, candidate_quantiles=..., min_exceedances=50) -> pd.DataFrame``
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from quantedge.contracts import RiskEstimate


def estimate_evt_pot(
    train_asset_returns: pd.DataFrame,
    weights: pd.Series,
    *,
    confidence: float,
    seed: int | None = None,
    threshold_quantile: float = 0.95,
    min_exceedances: int = 50,
) -> RiskEstimate:
    """Estimate unconditional POT-GPD tail VaR and ES on simple portfolio losses.

    Specification (SOLO STEP 7 / C2-C3):
    - Requires ``confidence >= threshold_quantile`` and at least ``min_exceedances`` strict
      exceedances above threshold ``u``; otherwise returns ``status='unavailable'`` with
      ``None`` risk values and explicit diagnostic reason (never lowers ``u`` silently).
    - Fixes GPD excess location at ``0.0``, handles the ``xi -> 0`` exponential limit and
      negative-shape support bounds, and diagnoses ``xi >= 1`` (divergent first moment)
      via ``es_loss=None`` and ``status='warning'`` rather than exporting nonfinite ES.
    """
    raise NotImplementedError(
        "estimate_evt_pot is a D0 interface stub scheduled for SOLO STEP 7 (C2/C3)."
    )


def evt_threshold_diagnostics(
    losses: pd.Series,
    *,
    candidate_quantiles: Sequence[float] = (0.90, 0.925, 0.95, 0.975),
    min_exceedances: int = 50,
) -> pd.DataFrame:
    """Compute Mean Residual Life (MRL), exceedance counts, and modified-scale stability diagnostics.

    Specification (SOLO STEP 7 / C2-C3):
    - Evaluates threshold-adjusted modified scale ``beta(u) - xi * u`` alongside ``xi``
      across candidate thresholds without fabricating generic uncalibrated GOF p-values.
    """
    raise NotImplementedError(
        "evt_threshold_diagnostics is a D0 interface stub scheduled for SOLO STEP 7 (C2/C3)."
    )
