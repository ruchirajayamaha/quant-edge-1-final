"""Historical crisis replays and explicit 7-ETF hypothetical scenario stress tests.

Public interface frozen in D0 for SOLO STEP 8 (B3):
- ``run_stress_tests(asset_returns, weights, scenarios, *, nav=MANDATE_NAV_USD) -> pd.DataFrame``
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from quantedge.contracts import MANDATE_NAV_USD, StressScenarioSpec


def run_stress_tests(
    asset_returns: pd.DataFrame,
    weights: pd.Series,
    scenarios: Sequence[StressScenarioSpec],
    *,
    nav: float = MANDATE_NAV_USD,
) -> pd.DataFrame:
    """Run historical buy-and-hold crisis replays and one-step hypothetical shock vectors.

    Specification (SOLO STEP 8 / B3):
    - Replays GFC (2007-10-09 to 2009-03-09), COVID (2020-02-19 to 2020-03-23), and
      2022 rate shock (2022-01-03 to 2022-10-14) from initial weights letting holdings drift,
      alongside the 60/40 comparison benchmark, clearly labelled as ex-post scenario replays.
    - Evaluates deterministic hypothetical 7-ETF shock vectors via ``loss = -(weights @ shocks)``,
      never mislabelling deterministic scenario P&L as probability-weighted Expected Shortfall.
    """
    raise NotImplementedError(
        "run_stress_tests is a D0 interface stub scheduled for SOLO STEP 8 (B3)."
    )
