"""Historical crisis replays and explicit 7-ETF hypothetical scenario stress tests.

Public interface frozen in D0 for SOLO STEP 8 (B3):
- ``run_stress_tests(asset_returns, weights, scenarios, *, nav=MANDATE_NAV_USD) -> pd.DataFrame``
"""

from __future__ import annotations

from collections.abc import Sequence

import math
import numpy as np
import pandas as pd

from quantedge.contracts import CANONICAL_TICKERS, MANDATE_NAV_USD, STRESS_SCENARIO_COLUMNS, StressScenarioSpec
from quantedge.returns import expected_nyse_sessions
from quantedge.var import _validate_asset_return_frame, _validate_portfolio_weights


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
    # Validate shape/dates once. Per-scenario missing/nonfinite inputs remain explicit.
    if not isinstance(asset_returns, pd.DataFrame) or tuple(asset_returns.columns) != CANONICAL_TICKERS:
        raise ValueError("asset_returns must have canonical seven ticker columns")
    idx = asset_returns.index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is not None or idx.hasnans or not idx.is_unique or not idx.is_monotonic_increasing or not idx.equals(idx.normalize()):
        raise ValueError("asset_returns requires sorted unique normalized timezone-naive DatetimeIndex")
    w = _validate_portfolio_weights(weights)
    if (w < -1e-10).any():
        raise ValueError("Stress buy-and-hold replay requires long-only initial holdings")
    if isinstance(nav, bool) or not math.isfinite(nav) or nav <= 0:
        raise ValueError("nav must be positive and finite")
    if not all(isinstance(s, StressScenarioSpec) for s in scenarios):
        raise ValueError("scenarios must contain StressScenarioSpec objects")
    if len({s.scenario_id for s in scenarios}) != len(scenarios):
        raise ValueError("scenario IDs must be unique")
    rows, daily_paths, attributions = [], {}, {}
    for scenario in scenarios:
        row = {k: None for k in STRESS_SCENARIO_COLUMNS}
        row.update(scenario_id=scenario.scenario_id, scenario_type=scenario.scenario_type,
                   portfolio_id=weights.name or "fixed_exposure", start_date=scenario.start_date,
                   end_date=scenario.end_date, status="unavailable", note=None)
        try:
            if scenario.scenario_type == "historical":
                if scenario.start_date is None or scenario.end_date is None:
                    raise ValueError("Historical scenario needs both endpoints")
                start, end = pd.Timestamp(scenario.start_date), pd.Timestamp(scenario.end_date)
                if start > end or start != start.normalize() or end != end.normalize():
                    raise ValueError("Invalid historical scenario endpoints")
                dates = expected_nyse_sessions(start, end)
                if not len(dates) or dates[0] != start or dates[-1] != end:
                    raise ValueError("Historical endpoints must be NYSE sessions")
                sample = asset_returns.loc[(idx >= start) & (idx <= end)]
                if not sample.index.equals(dates):
                    raise ValueError("Missing or unexpected historical scenario sessions; no gap stitching")
                values = _validate_asset_return_frame(sample, min_rows=1, context="scenario asset returns")
                if (values < -1.0).any():
                    raise ValueError("Simple asset return cannot be below -100%")
                growth = np.cumprod(1.0 + values, axis=0)
                # Holdings are initial weights times each asset's cumulative total-return factor.
                wealth = growth @ w
                before = np.r_[1.0, wealth[:-1]]
                if (before <= 0).any():
                    raise ValueError("Portfolio depleted before scenario end; subsequent return undefined")
                returns = wealth / before - 1.0
                peaks = np.maximum.accumulate(np.r_[1.0, wealth])[1:]
                drawdown = wealth / peaks - 1.0
                total = float(wealth[-1]-1.0)
                contributions = w * (growth[-1]-1.0)
                row.update(total_return=total, max_drawdown=float(drawdown.min()), worst_day_return=float(returns.min()),
                           usd_loss=float(-nav*total), status="ok",
                           note="EX-POST SCENARIO REPLAY: initial fixed allocation, buy-and-hold drift; return on start date included using its stored preceding-close return; no costs. Not historical strategy/OOS performance.")
                daily_paths[scenario.scenario_id] = pd.DataFrame({"date": dates, "wealth": wealth,
                    "daily_return": returns, "drawdown": drawdown})
            elif scenario.scenario_type == "hypothetical":
                if scenario.shocks is None or set(scenario.shocks) != set(CANONICAL_TICKERS):
                    raise ValueError("Hypothetical shocks must name exactly all seven ETFs")
                shocks = np.array([scenario.shocks[t] for t in CANONICAL_TICKERS], dtype=float)
                if not np.isfinite(shocks).all() or (shocks < -1).any():
                    raise ValueError("Hypothetical simple-return shocks must be finite and >= -100%")
                contributions = w * shocks
                total = float(contributions.sum())
                row.update(total_return=total, max_drawdown=min(total, 0.0), worst_day_return=total,
                           usd_loss=float(-nav*total), status="warning" if scenario.provisional else "ok",
                           note="DETERMINISTIC ONE-STEP SHOCK; horizon unspecified (not a daily forecast); drawdown is initial-to-final one-step loss, no path inferred; not ES. " + scenario.rationale)
            else:
                raise ValueError("Unknown scenario type")
            if not math.isclose(float(contributions.sum()), row["total_return"], abs_tol=1e-12):
                raise ArithmeticError("Asset attribution does not sum to scenario return")
            attributions[scenario.scenario_id] = pd.DataFrame({"ticker": CANONICAL_TICKERS,
                "initial_weight": w, "return_contribution": contributions, "usd_pnl": nav*contributions})
        except (ValueError, TypeError, ArithmeticError) as exc:
            row["note"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    out = pd.DataFrame(rows, columns=STRESS_SCENARIO_COLUMNS, dtype=object)
    out.attrs.update(nav_usd=nav, initial_weights={t: float(w[i]) for i,t in enumerate(CANONICAL_TICKERS)},
                     daily_paths=daily_paths, attributions=attributions,
                     convention="initial NAV included; buy-and-hold historical replay; signed P&L; no transaction costs")
    return out
