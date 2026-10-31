"""Expected Shortfall (ES) estimation and shared empirical tail-weight helper.

Public interface frozen in D0 for SOLO STEP 5 (C1) and SOLO STEP 8 (B2):
- ``empirical_tail_weights(losses, confidence) -> pd.Series``
"""

from __future__ import annotations

import pandas as pd


def empirical_tail_weights(
    losses: pd.Series,
    confidence: float,
) -> pd.Series:
    """Return aligned normalized worst-tail observation weights summing to ``1.0``.

    Frozen D0 contract (``CONTRACTS.md``):
    - Integrates the empirical quantile distribution over the worst ``alpha = 1 - confidence``
      probability mass of ``losses`` (each of ``n`` valid observations carries mass ``1 / n``).
    - Observations strictly exceeding the ``confidence`` boundary loss receive full mass
      ``1 / (n * alpha)``; remaining fractional boundary mass ``(alpha - k_strict / n) / alpha``
      is split evenly across all observations tied at the boundary quantile.
    - Non-tail observations receive weight ``0.0``; returned ``pd.Series`` preserves
      ``losses.index`` and sums to ``1.0`` so ``float(weights @ losses)`` equals exact
      historical ES and Euler historical ES asset contributions sum identically to total ES.
    """
    raise NotImplementedError(
        "empirical_tail_weights is a D0 interface stub scheduled for SOLO STEP 5 (C1)."
    )
