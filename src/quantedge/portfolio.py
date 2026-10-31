"""Portfolio weight optimization and drifting return-path construction (SOLO STEP 3 / B1).

Public interfaces frozen in D0:
- ``build_portfolio_path(asset_returns, strategy_spec, config) -> PortfolioPath``
- ``construct_weights(train_asset_returns, constraints, objective) -> pd.Series``

Supporting helpers for constraint feasibility, implied mandate bounds, pre-return
holdings drift monitoring, and core candidate specifications:
- ``PortfolioOptimizationError``
- ``check_weight_feasibility(weights, constraints, *, tol=1e-7, is_reference=False) -> dict[str, Any]``
- ``summarize_pre_return_holdings_compliance(weights_before, constraints, *, tol=1e-7) -> dict[str, Any]``
- ``compute_implied_weight_bounds(constraints, *, tol=1e-9) -> pd.DataFrame``
- ``make_core_strategy_specs(config) -> dict[str, StrategySpec]``

Conventions (SOLO STEP 3 / B1):
- Canonical 7-ETF ordering ``("SPY", "EFA", "EEM", "AGG", "GLD", "XLE", "XLK")`` is
  enforced everywhere.
- Strict causality: every rebalance effective on session ``t`` uses only asset returns
  strictly prior to ``t`` (``train_end <= decision_date < effective_date``) to set
  ``weights_before.loc[t]``.
- Constraint enforcement scope: ``PortfolioConstraints`` are enforced on **rebalance
  targets** at trade boundaries. Between scheduled rebalances, holdings drift naturally
  with realized simple returns: ``w_{t+} = w_{t-} * (1 + r_t) / (1 + R_{p,t}^{gross})``.
  Pre-return drifted holdings compliance across all active sessions is monitored and
  reported separately without clipping weights or forcing unapproved intraday/daily trades.
- Turnover convention: ``turnover_t = sum_i |w_{i,t,target} - w_{i,t,pre}|`` represents
  total one-way leg notional traded across buy and sell orders as a fraction of pre-trade
  NAV, with ``w_{t_0,pre} = 0`` at initial entry from 100% cash (so initial investment
  buys ``1.0`` of NAV -> ``turnover = 1.0``, and an interior swap of ``x`` out of one ETF
  into another trades ``x`` sell + ``x`` buy -> ``turnover = 2x`` and ``half_turnover = x``).
- Transaction cost & net return convention: each traded leg pays
  ``c_one_way = transaction_cost_bps_one_way / 10_000.0`` (``5.0 bps = 0.0005``), so
  ``cost_t = c_one_way * turnover_t`` and
  ``net_return_t = (1.0 - cost_t) * (1.0 + gross_return_t) - 1.0``.
- Wealth starts from initial pre-entry capital ``1.0``, and drawdown includes initial
  wealth ``1.0``: ``drawdown_t = wealth_t / max(1.0, max_{s <= t} wealth_s) - 1.0``.
- Infeasible constraints or failed optimizations raise ``PortfolioOptimizationError``
  and are NEVER repaired by silent clipping or renormalization.
"""

from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linprog, minimize

from quantedge.config import AppConfig
from quantedge.contracts import (
    CANONICAL_TICKERS,
    DEFENSIVE_TICKERS,
    EQUITY_TICKERS,
    PortfolioConstraints,
    PortfolioPath,
    StrategySpec,
)

SUPPORTED_CONSTRUCTION_OBJECTIVES: tuple[str, ...] = (
    "min_variance",
    "equal_weight",
    "benchmark_60_40",
)
SUPPORTED_PATH_OBJECTIVES: tuple[str, ...] = (
    "min_variance",
    "equal_weight",
    "benchmark_60_40",
    "fixed_weights",
)
SUPPORTED_REBALANCE_FREQUENCIES: tuple[str, ...] = ("M", "Q", "A", "Y", "D", "NONE", "BUY_AND_HOLD")

DEFAULT_BENCHMARK_60_40_WEIGHTS: dict[str, float] = {
    "SPY": 0.60,
    "EFA": 0.00,
    "EEM": 0.00,
    "AGG": 0.40,
    "GLD": 0.00,
    "XLE": 0.00,
    "XLK": 0.00,
}

_EQUITY_INDICES: tuple[int, ...] = tuple(CANONICAL_TICKERS.index(t) for t in EQUITY_TICKERS)
_DEFENSIVE_INDICES: tuple[int, ...] = tuple(CANONICAL_TICKERS.index(t) for t in DEFENSIVE_TICKERS)
_EQUITY_MASK: np.ndarray = np.array(
    [1.0 if ticker in EQUITY_TICKERS else 0.0 for ticker in CANONICAL_TICKERS],
    dtype=float,
)
_DEFENSIVE_MASK: np.ndarray = np.array(
    [1.0 if ticker in DEFENSIVE_TICKERS else 0.0 for ticker in CANONICAL_TICKERS],
    dtype=float,
)

TURNOVER_CONVENTION_DESCRIPTION: str = (
    "sum_abs_trade_weights: turnover_t = sum_i |w_target,i - w_pre,i| with w_pre = 0 at "
    "initial entry from 100% cash (initial investment turnover = 1.0; interior rebalance "
    "reallocating fraction x across assets has turnover = 2x and half_turnover = x)."
)
COST_CONVENTION_DESCRIPTION: str = (
    "one_way_leg_notional_bps: cost_t = (transaction_cost_bps_one_way / 10000.0) * turnover_t; "
    "net_return_t = (1.0 - cost_t) * (1.0 + gross_return_t) - 1.0."
)
DRAWDOWN_CONVENTION_DESCRIPTION: str = (
    "initial_wealth_1_included: wealth_t = prod_{s<=t} (1.0 + net_return_s); "
    "drawdown_t = wealth_t / max(1.0, max_{s<=t} wealth_s) - 1.0."
)


class PortfolioOptimizationError(ValueError):
    """Raised when portfolio constraints are infeasible or optimization verification fails."""


def _validate_constraints_object(constraints: PortfolioConstraints) -> None:
    """Validate structural finiteness of ``PortfolioConstraints`` parameters."""
    if not isinstance(constraints, PortfolioConstraints):
        raise TypeError(
            f"constraints must be a PortfolioConstraints instance; got {type(constraints).__name__}."
        )
    if not math.isfinite(constraints.min_weight_per_etf):
        raise PortfolioOptimizationError("min_weight_per_etf must be finite.")
    if constraints.max_weight_per_etf is not None and not math.isfinite(constraints.max_weight_per_etf):
        raise PortfolioOptimizationError("max_weight_per_etf must be finite when set.")
    if constraints.max_equity_weight is not None and not math.isfinite(constraints.max_equity_weight):
        raise PortfolioOptimizationError("max_equity_weight must be finite when set.")
    if constraints.min_defensive_weight is not None and not math.isfinite(
        constraints.min_defensive_weight
    ):
        raise PortfolioOptimizationError("min_defensive_weight must be finite when set.")


def _validate_return_frame(
    returns_df: pd.DataFrame,
    *,
    min_rows: int,
    check_gt_minus_one: bool = False,
    context: str = "asset_returns",
) -> None:
    """Validate canonical ticker order, ascending unique DatetimeIndex, and finite returns."""
    if not isinstance(returns_df, pd.DataFrame):
        raise TypeError(f"{context} must be a pandas DataFrame; got {type(returns_df).__name__}.")
    if tuple(returns_df.columns) != CANONICAL_TICKERS:
        raise ValueError(
            f"{context} columns must match exact canonical order {CANONICAL_TICKERS}; "
            f"got {tuple(returns_df.columns)}."
        )
    if not isinstance(returns_df.index, pd.DatetimeIndex):
        raise ValueError(
            f"{context} must have a pandas DatetimeIndex; got {type(returns_df.index).__name__}."
        )
    if not returns_df.index.is_monotonic_increasing or not returns_df.index.is_unique:
        raise ValueError(f"{context} DatetimeIndex must be strictly ascending and unique.")
    if len(returns_df) < min_rows:
        if min_rows >= 2 and context == "train_asset_returns":
            raise PortfolioOptimizationError(
                f"{context} requires at least {min_rows} observations for sample covariance "
                f"(ddof=1); got {len(returns_df)}."
            )
        raise ValueError(f"{context} requires at least {min_rows} rows; got {len(returns_df)}.")
    if len(returns_df) > 0:
        arr = returns_df.to_numpy(dtype=float)
        if not np.isfinite(arr).all():
            raise ValueError(f"{context} contains NaN or non-finite return values.")
        if check_gt_minus_one and not bool((arr > -1.0).all()):
            raise ValueError(f"{context} simple returns must all be strictly greater than -1.0.")


def _effective_lower_bound(constraints: PortfolioConstraints) -> float:
    """Return effective per-ETF lower bound combining ``long_only`` and ``min_weight_per_etf``."""
    return (
        max(0.0, float(constraints.min_weight_per_etf))
        if constraints.long_only
        else float(constraints.min_weight_per_etf)
    )


def check_weight_feasibility(
    weights: pd.Series | dict[str, float],
    constraints: PortfolioConstraints,
    *,
    tol: float = 1e-7,
    is_reference: bool = False,
) -> dict[str, Any]:
    """Evaluate a 7-ETF weight vector against ``constraints`` without modifying ``weights``.

    Returns a dictionary containing ``feasible`` (bool), ``violations`` (list of human-readable
    reasons), ``compliance_label`` (scoped to a single target/holdings vector), and summary
    group/single-asset weights.
    """
    _validate_constraints_object(constraints)
    if tol < 0.0 or not math.isfinite(tol):
        raise ValueError(f"tol must be finite and >= 0; got {tol!r}.")

    if isinstance(weights, dict):
        if set(weights.keys()) != set(CANONICAL_TICKERS):
            raise ValueError(
                f"weights dict must contain exact canonical tickers {CANONICAL_TICKERS}; "
                f"got {tuple(weights.keys())}."
            )
        series = pd.Series({t: float(weights[t]) for t in CANONICAL_TICKERS}, dtype=float)
    elif isinstance(weights, pd.Series):
        if tuple(weights.index) != CANONICAL_TICKERS:
            raise ValueError(
                f"weights Series index must match exact canonical order {CANONICAL_TICKERS}; "
                f"got {tuple(weights.index)}."
            )
        series = weights.astype(float)
    else:
        raise TypeError(f"weights must be a pandas Series or dict; got {type(weights).__name__}.")

    vals = series.to_numpy(dtype=float)
    violations: list[str] = []
    if not np.isfinite(vals).all():
        violations.append("weights contain NaN or non-finite values")
        return {
            "feasible": False,
            "violations": violations,
            "compliance_label": "invalid_nonfinite_weights",
            "total_weight": float("nan"),
            "equity_weight": float("nan"),
            "defensive_weight": float("nan"),
            "min_single_weight": float("nan"),
            "max_single_weight": float("nan"),
        }

    total_w = float(vals.sum())
    equity_w = float(np.dot(_EQUITY_MASK, vals))
    defensive_w = float(np.dot(_DEFENSIVE_MASK, vals))
    lower_bound = _effective_lower_bound(constraints)

    if constraints.fully_invested and abs(total_w - 1.0) > tol:
        violations.append(
            f"total weight {total_w:.6f} violates fully_invested=1.0 (|sum - 1| = {abs(total_w - 1.0):.2e})"
        )

    for idx, ticker in enumerate(CANONICAL_TICKERS):
        w_i = float(vals[idx])
        if w_i < lower_bound - tol:
            violations.append(
                f"{ticker} weight {w_i:.6f} is below lower bound {lower_bound:.6f}"
            )
        if constraints.max_weight_per_etf is not None and w_i > constraints.max_weight_per_etf + tol:
            violations.append(
                f"{ticker} weight {w_i:.6f} exceeds max_weight_per_etf {constraints.max_weight_per_etf:.6f}"
            )

    if constraints.max_equity_weight is not None and equity_w > constraints.max_equity_weight + tol:
        violations.append(
            f"equity group weight {equity_w:.6f} exceeds max_equity_weight {constraints.max_equity_weight:.6f}"
        )

    if (
        constraints.min_defensive_weight is not None
        and defensive_w < constraints.min_defensive_weight - tol
    ):
        violations.append(
            f"defensive group weight {defensive_w:.6f} is below min_defensive_weight "
            f"{constraints.min_defensive_weight:.6f}"
        )

    feasible = len(violations) == 0
    if feasible:
        label = (
            "target_within_provisional_caps"
            if constraints.provisional
            else "target_within_mandate_caps"
        )
    elif is_reference:
        label = (
            "unconstrained_reference_violates_provisional_caps"
            if constraints.provisional
            else "unconstrained_reference_violates_mandate_constraints"
        )
    else:
        label = (
            "target_violates_provisional_caps"
            if constraints.provisional
            else "target_violates_mandate_constraints"
        )

    return {
        "feasible": feasible,
        "violations": violations,
        "compliance_label": label,
        "total_weight": total_w,
        "equity_weight": equity_w,
        "defensive_weight": defensive_w,
        "min_single_weight": float(vals.min()),
        "max_single_weight": float(vals.max()),
    }


def summarize_pre_return_holdings_compliance(
    weights_before: pd.DataFrame,
    constraints: PortfolioConstraints,
    *,
    tol: float = 1e-7,
) -> dict[str, Any]:
    """Monitor pre-return holdings ``weights_before`` across all active sessions against ``constraints``.

    Separates observed daily pre-return holdings compliance (which includes natural drift
    between scheduled rebalances) from rebalance-target feasibility. Does not alter or clip
    any weights.
    """
    _validate_constraints_object(constraints)
    if tol < 0.0 or not math.isfinite(tol):
        raise ValueError(f"tol must be finite and >= 0; got {tol!r}.")
    _validate_return_frame(
        weights_before,
        min_rows=1,
        check_gt_minus_one=False,
        context="weights_before",
    )

    arr = weights_before.loc[:, list(CANONICAL_TICKERS)].to_numpy(dtype=np.float64)
    n_sessions, n_assets = arr.shape
    dates_iso = [ts.strftime("%Y-%m-%d") for ts in weights_before.index]

    total_w = arr.sum(axis=1)
    equity_w = arr @ _EQUITY_MASK
    defensive_w = arr @ _DEFENSIVE_MASK
    lower_bound = _effective_lower_bound(constraints)

    breach_full_inv = (
        np.abs(total_w - 1.0) > tol
        if constraints.fully_invested
        else np.zeros(n_sessions, dtype=bool)
    )
    breach_min_etf_mat = arr < (lower_bound - tol)
    breach_min_etf = breach_min_etf_mat.any(axis=1)

    if constraints.max_weight_per_etf is not None:
        breach_max_etf_mat = arr > (float(constraints.max_weight_per_etf) + tol)
        breach_max_etf = breach_max_etf_mat.any(axis=1)
    else:
        breach_max_etf_mat = np.zeros((n_sessions, n_assets), dtype=bool)
        breach_max_etf = np.zeros(n_sessions, dtype=bool)

    breach_max_eq = (
        equity_w > (float(constraints.max_equity_weight) + tol)
        if constraints.max_equity_weight is not None
        else np.zeros(n_sessions, dtype=bool)
    )
    breach_min_def = (
        defensive_w < (float(constraints.min_defensive_weight) - tol)
        if constraints.min_defensive_weight is not None
        else np.zeros(n_sessions, dtype=bool)
    )

    any_breach = (
        breach_full_inv | breach_min_etf | breach_max_etf | breach_max_eq | breach_min_def
    )
    n_breach = int(any_breach.sum())
    n_compliant = int(n_sessions - n_breach)
    breach_indices = np.flatnonzero(any_breach)
    breach_dates = tuple(dates_iso[int(i)] for i in breach_indices)

    counts_by_constraint: dict[str, int] = {
        "fully_invested": int(breach_full_inv.sum()),
        "min_weight_per_etf": int(breach_min_etf.sum()),
        "max_weight_per_etf": int(breach_max_etf.sum()),
        "max_equity_weight": int(breach_max_eq.sum()),
        "min_defensive_weight": int(breach_min_def.sum()),
    }
    violated_constraints = tuple(
        name for name, count in counts_by_constraint.items() if count > 0
    )

    ticker_upper_breaches: dict[str, int] = {
        CANONICAL_TICKERS[col_idx]: int(breach_max_etf_mat[:, col_idx].sum())
        for col_idx in range(n_assets)
        if int(breach_max_etf_mat[:, col_idx].sum()) > 0
    }
    ticker_lower_breaches: dict[str, int] = {
        CANONICAL_TICKERS[col_idx]: int(breach_min_etf_mat[:, col_idx].sum())
        for col_idx in range(n_assets)
        if int(breach_min_etf_mat[:, col_idx].sum()) > 0
    }

    max_row, max_col = np.unravel_index(int(np.argmax(arr)), arr.shape)
    min_row, min_col = np.unravel_index(int(np.argmin(arr)), arr.shape)
    max_eq_idx = int(np.argmax(equity_w))
    min_def_idx = int(np.argmin(defensive_w))

    max_exposures: dict[str, Any] = {
        "max_single_etf_weight": float(arr[max_row, max_col]),
        "max_single_etf_ticker": CANONICAL_TICKERS[int(max_col)],
        "max_single_etf_date": dates_iso[int(max_row)],
        "min_single_etf_weight": float(arr[min_row, min_col]),
        "min_single_etf_ticker": CANONICAL_TICKERS[int(min_col)],
        "min_single_etf_date": dates_iso[int(min_row)],
        "max_weight_by_ticker": {
            CANONICAL_TICKERS[col_idx]: float(arr[:, col_idx].max())
            for col_idx in range(n_assets)
        },
        "max_equity_group_weight": float(equity_w[max_eq_idx]),
        "max_equity_group_date": dates_iso[max_eq_idx],
        "min_equity_group_weight": float(equity_w.min()),
        "max_defensive_group_weight": float(defensive_w.max()),
        "min_defensive_group_weight": float(defensive_w[min_def_idx]),
        "min_defensive_group_date": dates_iso[min_def_idx],
    }

    return {
        "scope": "pre_return_holdings_all_active_sessions",
        "n_active_sessions": int(n_sessions),
        "n_compliant_sessions": n_compliant,
        "n_breach_sessions": n_breach,
        "all_pre_return_sessions_within_caps": bool(n_breach == 0),
        "breach_session_fraction": float(n_breach) / float(n_sessions),
        "first_breach_date": breach_dates[0] if breach_dates else None,
        "last_breach_date": breach_dates[-1] if breach_dates else None,
        "breach_dates": breach_dates,
        "breach_counts_by_constraint": counts_by_constraint,
        "breach_counts_by_ticker_upper_cap": ticker_upper_breaches,
        "breach_counts_by_ticker_lower_bound": ticker_lower_breaches,
        "violated_constraints": violated_constraints,
        "max_exposures": max_exposures,
    }


def _build_linear_constraint_matrices(
    constraints: PortfolioConstraints,
) -> tuple[list[tuple[float | None, float | None]], np.ndarray | None, np.ndarray | None, np.ndarray | None, np.ndarray | None]:
    """Assemble ``(bounds, A_ub, b_ub, A_eq, b_eq)`` for 7-ETF linear feasibility and KKT LPs."""
    _validate_constraints_object(constraints)
    n_assets = len(CANONICAL_TICKERS)
    lb = _effective_lower_bound(constraints)
    ub = float(constraints.max_weight_per_etf) if constraints.max_weight_per_etf is not None else None
    if ub is not None and lb > ub + 1e-12:
        raise PortfolioOptimizationError(
            f"Infeasible per-ETF bounds: effective lower bound {lb:.6f} exceeds "
            f"max_weight_per_etf {ub:.6f}."
        )
    if ub is None and not constraints.fully_invested:
        raise PortfolioOptimizationError(
            "Unbounded portfolio domain: max_weight_per_etf is None while fully_invested is False."
        )
    if ub is None and lb >= 0.0 and constraints.fully_invested:
        # Under long-only + sum(w)=1, each weight is naturally bounded above by 1.0 - 6*lb.
        ub_eff: float | None = max(1.0, 1.0 - (n_assets - 1) * lb)
    else:
        ub_eff = ub

    bounds: list[tuple[float | None, float | None]] = [(lb, ub_eff) for _ in range(n_assets)]

    a_ub_rows: list[np.ndarray] = []
    b_ub_vals: list[float] = []
    if constraints.max_equity_weight is not None:
        a_ub_rows.append(_EQUITY_MASK.copy())
        b_ub_vals.append(float(constraints.max_equity_weight))
    if constraints.min_defensive_weight is not None:
        a_ub_rows.append(-_DEFENSIVE_MASK.copy())
        b_ub_vals.append(-float(constraints.min_defensive_weight))

    a_ub = np.vstack(a_ub_rows) if a_ub_rows else None
    b_ub = np.array(b_ub_vals, dtype=float) if b_ub_vals else None

    if constraints.fully_invested:
        a_eq: np.ndarray | None = np.ones((1, n_assets), dtype=float)
        b_eq: np.ndarray | None = np.array([1.0], dtype=float)
    else:
        a_eq = None
        b_eq = None

    return bounds, a_ub, b_ub, a_eq, b_eq


def compute_implied_weight_bounds(
    constraints: PortfolioConstraints,
    *,
    tol: float = 1e-9,
) -> pd.DataFrame:
    """Solve exact LP-implied lower and upper bounds for each ETF and group under ``constraints``.

    Raises ``PortfolioOptimizationError`` if the linear constraint set is empty/infeasible.
    Under the provisional defaults (``long_only=True``, ``fully_invested=True``,
    ``max_weight_per_etf=0.40``, ``max_equity_weight=0.35``, ``min_defensive_weight=0.40``),
    this proves ``AGG in [0.25, 0.40]``, ``GLD in [0.25, 0.40]``, each equity ETF
    ``in [0.00, 0.35]``, ``EQUITY_TOTAL in [0.20, 0.35]``, and ``DEFENSIVE_TOTAL in [0.65, 0.80]``.
    """
    bounds, a_ub, b_ub, a_eq, b_eq = _build_linear_constraint_matrices(constraints)
    n_assets = len(CANONICAL_TICKERS)
    lb = _effective_lower_bound(constraints)
    ub_configured = (
        float(constraints.max_weight_per_etf)
        if constraints.max_weight_per_etf is not None
        else float("inf")
    )

    probes: list[tuple[str, str, np.ndarray, float, float]] = []
    for idx, ticker in enumerate(CANONICAL_TICKERS):
        direction = np.zeros(n_assets, dtype=float)
        direction[idx] = 1.0
        group = "equity" if ticker in EQUITY_TICKERS else "defensive"
        probes.append((ticker, group, direction, lb, ub_configured))

    eq_cfg_max = (
        float(constraints.max_equity_weight)
        if constraints.max_equity_weight is not None
        else float("inf")
    )
    def_cfg_min = (
        float(constraints.min_defensive_weight)
        if constraints.min_defensive_weight is not None
        else -float("inf")
    )
    probes.append(("EQUITY_TOTAL", "group_summary", _EQUITY_MASK.copy(), 5.0 * lb, eq_cfg_max))
    probes.append(
        ("DEFENSIVE_TOTAL", "group_summary", _DEFENSIVE_MASK.copy(), def_cfg_min, 2.0 * ub_configured)
    )

    rows: list[dict[str, Any]] = []
    for name, group, direction, cfg_min, cfg_max in probes:
        res_min = linprog(
            c=direction,
            A_ub=a_ub,
            b_ub=b_ub,
            A_eq=a_eq,
            b_eq=b_eq,
            bounds=bounds,
            method="highs",
        )
        if not res_min.success or res_min.x is None:
            raise PortfolioOptimizationError(
                f"PortfolioConstraints are linearly infeasible (HiGHS status={res_min.status}: "
                f"{res_min.message})."
            )
        res_max = linprog(
            c=-direction,
            A_ub=a_ub,
            b_ub=b_ub,
            A_eq=a_eq,
            b_eq=b_eq,
            bounds=bounds,
            method="highs",
        )
        if not res_max.success or res_max.x is None:
            raise PortfolioOptimizationError(
                f"PortfolioConstraints are linearly infeasible or unbounded above on {name} "
                f"(HiGHS status={res_max.status}: {res_max.message})."
            )
        imp_min = float(np.dot(direction, res_min.x))
        imp_max = float(np.dot(direction, res_max.x))
        if abs(imp_min) <= tol:
            imp_min = 0.0
        if abs(imp_max) <= tol:
            imp_max = 0.0
        rows.append(
            {
                "name": name,
                "category": group,
                "configured_min": float(cfg_min) if math.isfinite(cfg_min) else None,
                "configured_max": float(cfg_max) if math.isfinite(cfg_max) else None,
                "implied_min": imp_min,
                "implied_max": imp_max,
                "min_tightened_by_interaction": bool(
                    math.isfinite(cfg_min) and imp_min > cfg_min + 1e-7
                ),
                "max_tightened_by_interaction": bool(
                    math.isfinite(cfg_max) and imp_max < cfg_max - 1e-7
                ),
            }
        )

    return pd.DataFrame(rows)


def _find_chebyshev_interior_start(
    constraints: PortfolioConstraints,
    bounds: list[tuple[float | None, float | None]],
    a_ub: np.ndarray | None,
    b_ub: np.ndarray | None,
    a_eq: np.ndarray | None,
    b_eq: np.ndarray | None,
) -> np.ndarray:
    """Compute a strictly feasible interior starting vector ``w0`` via a 1-slack Chebyshev LP."""
    n_assets = len(CANONICAL_TICKERS)
    # Decision vector z = [w_0, ..., w_6, s], maximizing slack margin s in [0, 1].
    c = np.zeros(n_assets + 1, dtype=float)
    c[-1] = -1.0

    ub_rows: list[np.ndarray] = []
    ub_rhs: list[float] = []
    for idx, (lb, ub) in enumerate(bounds):
        if lb is not None:
            row = np.zeros(n_assets + 1, dtype=float)
            row[idx] = -1.0
            row[-1] = 1.0
            ub_rows.append(row)
            ub_rhs.append(-float(lb))
        if ub is not None:
            row = np.zeros(n_assets + 1, dtype=float)
            row[idx] = 1.0
            row[-1] = 1.0
            ub_rows.append(row)
            ub_rhs.append(float(ub))

    if a_ub is not None and b_ub is not None:
        for row_idx in range(a_ub.shape[0]):
            row = np.zeros(n_assets + 1, dtype=float)
            row[:n_assets] = a_ub[row_idx]
            row[-1] = 1.0
            ub_rows.append(row)
            ub_rhs.append(float(b_ub[row_idx]))

    a_ub_ext = np.vstack(ub_rows) if ub_rows else None
    b_ub_ext = np.array(ub_rhs, dtype=float) if ub_rhs else None

    if a_eq is not None and b_eq is not None:
        a_eq_ext = np.hstack([a_eq, np.zeros((a_eq.shape[0], 1), dtype=float)])
        b_eq_ext: np.ndarray | None = b_eq
    else:
        a_eq_ext = None
        b_eq_ext = None

    ext_bounds: list[tuple[float | None, float | None]] = [
        (lb, ub) for (lb, ub) in bounds
    ] + [(0.0, 1.0)]

    res = linprog(
        c=c,
        A_ub=a_ub_ext,
        b_ub=b_ub_ext,
        A_eq=a_eq_ext,
        b_eq=b_eq_ext,
        bounds=ext_bounds,
        method="highs",
    )
    if not res.success or res.x is None:
        raise PortfolioOptimizationError(
            f"PortfolioConstraints have no feasible allocation (HiGHS status={res.status}: "
            f"{res.message}; constraints={constraints})."
        )
    w0 = np.asarray(res.x[:n_assets], dtype=float)
    feas = check_weight_feasibility(pd.Series(w0, index=CANONICAL_TICKERS), constraints, tol=1e-7)
    if not feas["feasible"]:
        raise PortfolioOptimizationError(
            f"Initial LP feasibility check failed constraint verification: {feas['violations']}"
        )
    return w0


def _compute_qp_duality_gap(
    sigma_scaled: np.ndarray,
    w_cand: np.ndarray,
    bounds: list[tuple[float | None, float | None]],
    a_ub: np.ndarray | None,
    b_ub: np.ndarray | None,
    a_eq: np.ndarray | None,
    b_eq: np.ndarray | None,
) -> float:
    """Compute exact Frank-Wolfe convex duality gap ``max_{v in P} grad(w)^T (w - v)`` via HiGHS."""
    grad = 2.0 * (sigma_scaled @ w_cand)
    res = linprog(
        c=grad,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if not res.success or res.x is None:
        return float("inf")
    v_opt = np.asarray(res.x, dtype=float)
    gap = float(np.dot(grad, w_cand - v_opt))
    return max(0.0, gap)


def _solve_min_variance_from_covariance(
    raw_covariance: np.ndarray,
    constraints: PortfolioConstraints,
    *,
    feasibility_tol: float = 1e-7,
    kkt_gap_tol: float = 1e-7,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve ``min w^T Sigma w`` over ``constraints`` with PSD, feasibility, and KKT checks.

    Never clips or renormalizes an infeasible optimizer output.
    """
    _validate_constraints_object(constraints)
    n_assets = len(CANONICAL_TICKERS)
    cov_arr = np.asarray(raw_covariance, dtype=float)
    if cov_arr.shape != (n_assets, n_assets):
        raise PortfolioOptimizationError(
            f"Covariance matrix must have shape {(n_assets, n_assets)}; got {cov_arr.shape}."
        )
    if not np.isfinite(cov_arr).all():
        raise PortfolioOptimizationError("Covariance matrix contains NaN or non-finite entries.")

    sym_err = float(np.max(np.abs(cov_arr - cov_arr.T)))
    scale_ref = max(1.0, float(np.max(np.abs(cov_arr))))
    if sym_err > 1e-10 * scale_ref:
        raise PortfolioOptimizationError(
            f"Covariance matrix failed symmetry verification (max |Sigma - Sigma^T| = {sym_err:.3e})."
        )
    sigma = 0.5 * (cov_arr + cov_arr.T)

    eigvals = np.linalg.eigvalsh(sigma)
    eig_scale = max(1.0, float(np.max(np.abs(eigvals))))
    psd_tol = 1e-11 * eig_scale
    min_eig = float(eigvals[0])
    max_eig = float(eigvals[-1])
    if min_eig < -psd_tol:
        raise PortfolioOptimizationError(
            f"Covariance matrix is not positive semi-definite (min eigenvalue = {min_eig:.3e} < {-psd_tol:.3e})."
        )

    bounds, a_ub, b_ub, a_eq, b_eq = _build_linear_constraint_matrices(constraints)
    w_cheb = _find_chebyshev_interior_start(constraints, bounds, a_ub, b_ub, a_eq, b_eq)

    avg_diag = float(np.trace(sigma)) / float(n_assets)
    if avg_diag <= 1e-30 and max_eig <= 1e-30:
        # Degenerate identically-zero covariance matrix: every feasible vector achieves 0 variance.
        return w_cheb, {
            "solver": "highs_chebyshev_zero_covariance",
            "solver_status": "optimal",
            "duality_gap_scaled": 0.0,
            "min_eigenvalue": min_eig,
            "max_eigenvalue": max_eig,
            "symmetry_error": sym_err,
            "portfolio_variance": 0.0,
        }

    scale_factor = 1.0 / max(avg_diag, max_eig, 1e-30)
    sigma_scaled = sigma * scale_factor

    slsqp_constraints: list[dict[str, Any]] = []
    if constraints.fully_invested:
        ones = np.ones(n_assets, dtype=float)
        slsqp_constraints.append(
            {
                "type": "eq",
                "fun": lambda w, a=ones: float(np.dot(a, w) - 1.0),
                "jac": lambda _w, a=ones: a,
            }
        )
    if constraints.max_equity_weight is not None:
        cap_eq = float(constraints.max_equity_weight)
        slsqp_constraints.append(
            {
                "type": "ineq",
                "fun": lambda w, m=_EQUITY_MASK, c=cap_eq: float(c - np.dot(m, w)),
                "jac": lambda _w, m=_EQUITY_MASK: -m,
            }
        )
    if constraints.min_defensive_weight is not None:
        floor_def = float(constraints.min_defensive_weight)
        slsqp_constraints.append(
            {
                "type": "ineq",
                "fun": lambda w, m=_DEFENSIVE_MASK, f=floor_def: float(np.dot(m, w) - f),
                "jac": lambda _w, m=_DEFENSIVE_MASK: m,
            }
        )

    starts: list[np.ndarray] = [w_cheb]
    diag_lp = linprog(
        c=np.maximum(0.0, np.diag(sigma_scaled)),
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if diag_lp.success and diag_lp.x is not None:
        w_diag = np.asarray(diag_lp.x, dtype=float)
        starts.append(0.5 * w_cheb + 0.5 * w_diag)
        starts.append(w_diag)

    def obj_fn(w: np.ndarray) -> float:
        return float(w @ (sigma_scaled @ w))

    def obj_jac(w: np.ndarray) -> np.ndarray:
        return 2.0 * (sigma_scaled @ w)

    best_w: np.ndarray | None = None
    best_obj: float = float("inf")
    best_gap: float = float("inf")
    last_message: str = "no_candidate_evaluated"

    for w_start in starts:
        res = minimize(
            fun=obj_fn,
            x0=w_start,
            jac=obj_jac,
            method="SLSQP",
            bounds=bounds,
            constraints=slsqp_constraints,
            options={"ftol": 1e-14, "maxiter": 1000},
        )
        last_message = f"success={res.success}, status={res.status}, message={res.message}"
        if not res.success or res.x is None:
            continue
        w_cand = np.asarray(res.x, dtype=float)
        # Strict rule: check raw solver output directly without clipping or renormalizing.
        feas = check_weight_feasibility(
            pd.Series(w_cand, index=CANONICAL_TICKERS),
            constraints,
            tol=feasibility_tol,
        )
        if not feas["feasible"]:
            last_message = f"SLSQP candidate infeasible: {feas['violations']}"
            continue
        gap = _compute_qp_duality_gap(sigma_scaled, w_cand, bounds, a_ub, b_ub, a_eq, b_eq)
        cand_obj = obj_fn(w_cand)
        if gap <= kkt_gap_tol and cand_obj < best_obj:
            best_w = w_cand
            best_obj = cand_obj
            best_gap = gap
            if best_gap <= 1e-11:
                break

    if best_w is None:
        raise PortfolioOptimizationError(
            "Constrained minimum-variance optimization failed to produce a KKT-verified "
            f"feasible weight vector without clipping/renormalization ({last_message})."
        )

    return best_w, {
        "solver": "scipy.optimize.minimize(SLSQP)+highs_kkt_verified",
        "solver_status": "optimal",
        "duality_gap_scaled": float(best_gap),
        "min_eigenvalue": min_eig,
        "max_eigenvalue": max_eig,
        "symmetry_error": sym_err,
        "portfolio_variance": float(best_w @ (sigma @ best_w)),
    }


def _attach_weight_attrs(
    weights: pd.Series,
    *,
    objective: str,
    constraints: PortfolioConstraints,
    solver_meta: dict[str, Any],
    feasibility: dict[str, Any],
) -> pd.Series:
    """Attach audit/diagnostic attributes to a canonical weight ``Series``."""
    weights.attrs["objective"] = objective
    weights.attrs["provisional_constraints"] = bool(constraints.provisional)
    weights.attrs["mandate_feasible"] = bool(feasibility["feasible"])
    weights.attrs["mandate_compliance_label"] = str(feasibility["compliance_label"])
    weights.attrs["mandate_violations"] = tuple(feasibility["violations"])
    weights.attrs["equity_weight"] = float(feasibility["equity_weight"])
    weights.attrs["defensive_weight"] = float(feasibility["defensive_weight"])
    for key, val in solver_meta.items():
        weights.attrs[key] = val
    return weights


def _build_reference_weights(
    objective: str,
    constraints: PortfolioConstraints,
    *,
    benchmark_60_40_map: dict[str, float] | None = None,
    fixed_weights_map: dict[str, float] | None = None,
) -> tuple[pd.Series, dict[str, Any], dict[str, Any]]:
    """Construct canonical reference or fixed weights and evaluate mandate cap compliance."""
    _validate_constraints_object(constraints)
    if fixed_weights_map is not None:
        unknown = set(fixed_weights_map.keys()) - set(CANONICAL_TICKERS)
        if unknown:
            raise ValueError(
                f"fixed_weights contains non-canonical tickers {sorted(unknown)}; "
                f"allowed tickers are {CANONICAL_TICKERS}."
            )
        if objective == "benchmark_60_40":
            raw_map = {t: float(fixed_weights_map.get(t, 0.0)) for t in CANONICAL_TICKERS}
        else:
            if set(fixed_weights_map.keys()) != set(CANONICAL_TICKERS):
                raise ValueError(
                    f"fixed_weights must specify all seven canonical tickers {CANONICAL_TICKERS}; "
                    f"got {tuple(fixed_weights_map.keys())}."
                )
            raw_map = {t: float(fixed_weights_map[t]) for t in CANONICAL_TICKERS}
        w_series = pd.Series(raw_map, index=CANONICAL_TICKERS, dtype=float, name="weights")
        vals = w_series.to_numpy(dtype=float)
        if not np.isfinite(vals).all():
            raise ValueError("fixed_weights contains NaN or non-finite values.")
        if abs(float(vals.sum()) - 1.0) > 1e-7:
            raise ValueError(
                f"fixed_weights must sum to 1.0 (fully invested); got {float(vals.sum()):.8f}."
            )
        if constraints.long_only and bool((vals < -1e-9).any()):
            raise ValueError("fixed_weights cannot contain negative weights when long_only=True.")
    elif objective == "equal_weight":
        w_val = 1.0 / float(len(CANONICAL_TICKERS))
        w_series = pd.Series(
            {t: w_val for t in CANONICAL_TICKERS},
            index=CANONICAL_TICKERS,
            dtype=float,
            name="weights",
        )
    elif objective == "benchmark_60_40":
        src = benchmark_60_40_map if benchmark_60_40_map is not None else DEFAULT_BENCHMARK_60_40_WEIGHTS
        unknown = set(src.keys()) - set(CANONICAL_TICKERS)
        if unknown:
            raise ValueError(f"benchmark_60_40 weights contain non-canonical tickers {sorted(unknown)}.")
        raw_map = {t: float(src.get(t, 0.0)) for t in CANONICAL_TICKERS}
        w_series = pd.Series(raw_map, index=CANONICAL_TICKERS, dtype=float, name="weights")
        if abs(float(w_series.sum()) - 1.0) > 1e-7:
            raise ValueError(
                f"benchmark_60_40 weights must sum to 1.0; got {float(w_series.sum()):.8f}."
            )
    else:
        raise ValueError(
            f"Unsupported reference/fixed objective {objective!r}; expected one of "
            f"{SUPPORTED_PATH_OBJECTIVES}."
        )

    is_ref_obj = objective in ("equal_weight", "benchmark_60_40")
    feas = check_weight_feasibility(w_series, constraints, tol=1e-7, is_reference=is_ref_obj)
    solver_meta = {
        "solver": "analytic_reference" if is_ref_obj else "fixed_weights",
        "solver_status": "analytic_reference" if is_ref_obj else "fixed_weights",
        "covariance_estimator": "none",
    }
    _attach_weight_attrs(
        w_series,
        objective=objective,
        constraints=constraints,
        solver_meta=solver_meta,
        feasibility=feas,
    )
    return w_series, solver_meta, feas


def construct_weights(
    train_asset_returns: pd.DataFrame,
    constraints: PortfolioConstraints,
    objective: str,
) -> pd.Series:
    """Optimize or construct canonical-ticker portfolio weights from historical training data.

    Specification (SOLO STEP 3 / B1):
    - Returns a ``pd.Series`` indexed by ``CANONICAL_TICKERS`` using strictly past
      ``train_asset_returns``.
    - Supports ``objective="min_variance"`` (configured constrained Markowitz minimum
      variance with sample covariance ``ddof=1``, symmetry/eigenvalue/PSD check, HiGHS
      linear feasibility pre-check, SLSQP solve, and KKT duality-gap verification),
      ``objective="equal_weight"`` (``1/7`` across canonical ETFs), and
      ``objective="benchmark_60_40"`` (``60% SPY / 40% AGG``).
    - Reference portfolios that breach ``constraints`` carry explicit violation metadata
      in ``weights.attrs``; ``min_variance`` strictly enforces ``constraints`` and raises
      ``PortfolioOptimizationError`` if infeasible (never silently clipping/renormalizing).
    """
    _validate_constraints_object(constraints)
    if objective not in SUPPORTED_CONSTRUCTION_OBJECTIVES:
        raise ValueError(
            f"Unsupported portfolio objective {objective!r}; expected one of "
            f"{SUPPORTED_CONSTRUCTION_OBJECTIVES}."
        )

    if objective == "min_variance":
        _validate_return_frame(
            train_asset_returns,
            min_rows=2,
            check_gt_minus_one=False,
            context="train_asset_returns",
        )
        # Copy into an isolated C-contiguous float64 array so BLAS/SIMD reduction order
        # depends strictly on the training values and never on parent DataFrame memory layout.
        x_train = np.array(
            train_asset_returns.loc[:, list(CANONICAL_TICKERS)].to_numpy(dtype=np.float64),
            dtype=np.float64,
            copy=True,
            order="C",
        )
        x_centered = x_train - x_train.mean(axis=0, keepdims=True)
        raw_cov = (x_centered.T @ x_centered) / float(x_train.shape[0] - 1)
        w_opt, solver_meta = _solve_min_variance_from_covariance(
            raw_cov,
            constraints,
        )
        solver_meta["covariance_estimator"] = "sample_ddof1"
        w_series = pd.Series(w_opt, index=CANONICAL_TICKERS, dtype=float, name="weights")
        feas = check_weight_feasibility(w_series, constraints, tol=1e-7)
        if not feas["feasible"]:
            raise PortfolioOptimizationError(
                f"Optimizer output failed post-solve feasibility check: {feas['violations']}"
            )
        return _attach_weight_attrs(
            w_series,
            objective=objective,
            constraints=constraints,
            solver_meta=solver_meta,
            feasibility=feas,
        )

    _validate_return_frame(
        train_asset_returns,
        min_rows=1,
        check_gt_minus_one=False,
        context="train_asset_returns",
    )
    w_ref, _, _ = _build_reference_weights(objective, constraints)
    return w_ref


def make_core_strategy_specs(
    config: AppConfig,
    *,
    estimation_window_days: int | None = None,
) -> dict[str, StrategySpec]:
    """Return the three core registered Step 3 candidate ``StrategySpec`` definitions.

    By default all three candidates share ``config.portfolio.estimation_window_days`` (``504``)
    and ``config.portfolio.rebalance_frequency`` (``"M"``) so their out-of-sample paths run on
    identical session dates through the single shared ``build_portfolio_path`` engine.
    """
    win = (
        config.portfolio.estimation_window_days
        if estimation_window_days is None
        else int(estimation_window_days)
    )
    freq = config.portfolio.rebalance_frequency
    cov_est = config.portfolio.covariance_estimator_default
    constraints = config.portfolio.constraints
    bench_map = {
        ticker: float(config.mandate.benchmark_60_40_weights.get(ticker, 0.0))
        for ticker in CANONICAL_TICKERS
    }
    return {
        "min_variance": StrategySpec(
            strategy_id="min_variance",
            objective="min_variance",
            rebalance_frequency=freq,
            estimation_window_days=win,
            covariance_estimator=cov_est,
            constraints=constraints,
            fixed_weights=None,
            target_annual_return=None,
            provisional=True,
        ),
        "equal_weight": StrategySpec(
            strategy_id="equal_weight",
            objective="equal_weight",
            rebalance_frequency=freq,
            estimation_window_days=win,
            covariance_estimator=cov_est,
            constraints=constraints,
            fixed_weights=None,
            target_annual_return=None,
            provisional=True,
        ),
        "benchmark_60_40": StrategySpec(
            strategy_id="benchmark_60_40",
            objective="benchmark_60_40",
            rebalance_frequency=freq,
            estimation_window_days=win,
            covariance_estimator=cov_est,
            constraints=constraints,
            fixed_weights=bench_map,
            target_annual_return=None,
            provisional=True,
        ),
    }


def _is_scheduled_rebalance_boundary(
    dates: pd.DatetimeIndex,
    pos: int,
    frequency: str,
) -> bool:
    """Return True if ``dates[pos]`` (``pos >= 1``) begins a new rebalance period."""
    if pos <= 0:
        return False
    cur = dates[pos]
    prev = dates[pos - 1]
    if frequency == "M":
        return (cur.year, cur.month) != (prev.year, prev.month)
    if frequency == "Q":
        return (cur.year, (cur.month - 1) // 3) != (prev.year, (prev.month - 1) // 3)
    if frequency in ("A", "Y"):
        return cur.year != prev.year
    if frequency == "D":
        return True
    if frequency in ("NONE", "BUY_AND_HOLD"):
        return False
    raise ValueError(
        f"Unsupported rebalance_frequency {frequency!r}; expected one of "
        f"{SUPPORTED_REBALANCE_FREQUENCIES}."
    )


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
    if not isinstance(strategy_spec, StrategySpec):
        raise TypeError(
            f"strategy_spec must be a StrategySpec instance; got {type(strategy_spec).__name__}."
        )
    if not isinstance(config, AppConfig):
        raise TypeError(f"config must be an AppConfig instance; got {type(config).__name__}.")
    if not strategy_spec.strategy_id or not str(strategy_spec.strategy_id).strip():
        raise ValueError("strategy_spec.strategy_id must be a non-empty string.")

    objective = str(strategy_spec.objective).strip()
    if objective not in SUPPORTED_PATH_OBJECTIVES:
        raise ValueError(
            f"Unsupported strategy_spec.objective {objective!r}; expected one of "
            f"{SUPPORTED_PATH_OBJECTIVES}."
        )
    if objective in ("min_variance", "equal_weight"):
        if strategy_spec.fixed_weights is not None:
            raise ValueError(
                f"Conflicting StrategySpec: fixed_weights must be None when "
                f"objective={objective!r}; use objective='fixed_weights' for custom "
                "fixed allocations."
            )
    elif objective == "fixed_weights":
        if strategy_spec.fixed_weights is None:
            raise ValueError(
                "strategy_spec.fixed_weights is required when objective='fixed_weights'."
            )
    elif objective == "benchmark_60_40":
        if strategy_spec.fixed_weights is not None:
            unknown = set(strategy_spec.fixed_weights.keys()) - set(CANONICAL_TICKERS)
            if unknown:
                raise ValueError(
                    f"fixed_weights contains non-canonical tickers {sorted(unknown)}; "
                    f"allowed tickers are {CANONICAL_TICKERS}."
                )
            cfg_bench = {
                t: float(config.mandate.benchmark_60_40_weights.get(t, 0.0))
                for t in CANONICAL_TICKERS
            }
            supplied_bench = {
                t: float(strategy_spec.fixed_weights.get(t, 0.0))
                for t in CANONICAL_TICKERS
            }
            if any(
                not math.isfinite(supplied_bench[t]) or abs(supplied_bench[t] - cfg_bench[t]) > 1e-9
                for t in CANONICAL_TICKERS
            ):
                raise ValueError(
                    "Conflicting StrategySpec: fixed_weights on objective='benchmark_60_40' "
                    "must match config.mandate.benchmark_60_40_weights (60% SPY / 40% AGG) "
                    "or be None; use objective='fixed_weights' for custom allocations."
                )

    if strategy_spec.target_annual_return is not None:
        raise ValueError(
            "target_annual_return frontier/target-return optimization is not active in Step 3 "
            "core paths; keep target_annual_return=None."
        )

    freq = str(strategy_spec.rebalance_frequency or config.portfolio.rebalance_frequency).upper().strip()
    if freq not in SUPPORTED_REBALANCE_FREQUENCIES:
        raise ValueError(
            f"Unsupported rebalance_frequency {freq!r}; expected one of "
            f"{SUPPORTED_REBALANCE_FREQUENCIES}."
        )

    eff_constraints = (
        strategy_spec.constraints
        if strategy_spec.constraints is not None
        else config.portfolio.constraints
    )
    _validate_constraints_object(eff_constraints)

    cost_bps = float(config.portfolio.transaction_cost_bps_one_way)
    if not math.isfinite(cost_bps) or cost_bps < 0.0 or cost_bps >= 10_000.0:
        raise ValueError(
            f"transaction_cost_bps_one_way must lie in [0, 10000); got {cost_bps!r}."
        )
    cost_rate = cost_bps / 10_000.0

    _validate_return_frame(
        asset_returns,
        min_rows=1,
        check_gt_minus_one=True,
        context="asset_returns",
    )

    requires_estimation = objective == "min_variance"
    if requires_estimation:
        if strategy_spec.covariance_estimator != "sample_ddof1":
            raise ValueError(
                f"Unsupported covariance_estimator {strategy_spec.covariance_estimator!r}; "
                "Step 3 configured primary estimator is 'sample_ddof1'."
            )
        raw_win = (
            config.portfolio.estimation_window_days
            if strategy_spec.estimation_window_days is None
            else int(strategy_spec.estimation_window_days)
        )
        if raw_win < 2:
            raise PortfolioOptimizationError(
                f"min_variance requires estimation_window_days >= 2 for ddof=1; got {raw_win}."
            )
        burn_in = raw_win
    else:
        if strategy_spec.estimation_window_days is None:
            burn_in = 0
        else:
            burn_in = int(strategy_spec.estimation_window_days)
            if burn_in < 0:
                raise ValueError(
                    f"estimation_window_days must be >= 0 or None; got {burn_in}."
                )

    n_total = len(asset_returns)
    if n_total <= burn_in:
        raise ValueError(
            f"asset_returns length ({n_total}) must strictly exceed estimation_window_days "
            f"({burn_in}) so at least one out-of-sample session can be evaluated."
        )

    dates = asset_returns.index
    ret_matrix = np.array(
        asset_returns.loc[:, list(CANONICAL_TICKERS)].to_numpy(dtype=np.float64),
        dtype=np.float64,
        copy=True,
        order="C",
    )
    n_active = n_total - burn_in
    n_assets = len(CANONICAL_TICKERS)

    weights_before_arr = np.empty((n_active, n_assets), dtype=float)
    gross_arr = np.empty(n_active, dtype=float)
    net_arr = np.empty(n_active, dtype=float)
    turnover_arr = np.zeros(n_active, dtype=float)
    costs_arr = np.zeros(n_active, dtype=float)

    rebalance_records: list[dict[str, Any]] = []
    drifted_weights = np.zeros(n_assets, dtype=float)

    for out_idx, pos in enumerate(range(burn_in, n_total)):
        effective_date = dates[pos]
        is_initial = out_idx == 0
        is_rebalance = is_initial or _is_scheduled_rebalance_boundary(dates, pos, freq)

        if is_rebalance:
            if pos >= 1:
                decision_date: pd.Timestamp | Any = dates[pos - 1]
                if not (decision_date < effective_date):
                    raise AssertionError("Causality invariant violated: decision_date >= effective_date.")
            else:
                decision_date = pd.NaT

            if burn_in > 0:
                train_slice = asset_returns.iloc[pos - burn_in : pos]
                train_start: pd.Timestamp | Any = train_slice.index[0]
                train_end: pd.Timestamp | Any = train_slice.index[-1]
                n_train_obs = int(len(train_slice))
                if not (train_end < effective_date):
                    raise AssertionError("Causality invariant violated: train_end >= effective_date.")
            else:
                train_slice = asset_returns.iloc[0:0]
                train_start = pd.NaT
                train_end = pd.NaT
                n_train_obs = 0

            if objective == "min_variance":
                target_series = construct_weights(train_slice, eff_constraints, "min_variance")
                feas = check_weight_feasibility(target_series, eff_constraints, tol=1e-7)
                solver_meta = {
                    "solver": target_series.attrs.get("solver", "SLSQP"),
                    "solver_status": target_series.attrs.get("solver_status", "optimal"),
                }
            elif objective == "equal_weight":
                target_series, solver_meta, feas = _build_reference_weights(
                    "equal_weight",
                    eff_constraints,
                )
            elif objective == "benchmark_60_40":
                target_series, solver_meta, feas = _build_reference_weights(
                    "benchmark_60_40",
                    eff_constraints,
                    benchmark_60_40_map=config.mandate.benchmark_60_40_weights,
                    fixed_weights_map=strategy_spec.fixed_weights,
                )
            elif objective == "fixed_weights":
                target_series, solver_meta, feas = _build_reference_weights(
                    "fixed_weights",
                    eff_constraints,
                    fixed_weights_map=strategy_spec.fixed_weights,
                )
            else:  # pragma: no cover - guarded above
                raise ValueError(f"Unsupported objective {objective!r}.")

            target_w = target_series.to_numpy(dtype=float)
            pre_trade_w = np.zeros(n_assets, dtype=float) if is_initial else drifted_weights
            trade_w = target_w - pre_trade_w
            sum_abs_trade = float(np.abs(trade_w).sum())
            half_turn = 0.5 * sum_abs_trade
            cost_t = cost_rate * sum_abs_trade

            w_before = target_w
            turnover_arr[out_idx] = sum_abs_trade
            costs_arr[out_idx] = cost_t

            if is_initial and pos == 0:
                exec_timing = "initial_entry_pre_sample_applied_first_session"
            elif is_initial:
                exec_timing = "initial_entry_decided_at_prior_close_applied_next_session"
            else:
                exec_timing = config.chronology.execution_assumption

            rec: dict[str, Any] = {
                "decision_date": decision_date,
                "effective_date": effective_date,
                "is_initial_investment": bool(is_initial),
                "execution_timing": exec_timing,
                "train_start": train_start,
                "train_end": train_end,
                "n_train_obs": n_train_obs,
                "turnover": sum_abs_trade,
                "half_turnover": half_turn,
                "cost_fraction": cost_t,
                "solver_status": str(solver_meta.get("solver_status", "unknown")),
                "mandate_feasible": bool(feas["feasible"]),
                "mandate_compliance_label": str(feas["compliance_label"]),
                "mandate_violations": "; ".join(feas["violations"]),
                "equity_weight": float(feas["equity_weight"]),
                "defensive_weight": float(feas["defensive_weight"]),
            }
            for idx, ticker in enumerate(CANONICAL_TICKERS):
                rec[ticker] = float(target_w[idx])
            rebalance_records.append(rec)
        else:
            w_before = drifted_weights
            cost_t = 0.0

        weights_before_arr[out_idx, :] = w_before
        r_vec = ret_matrix[pos, :]
        gross_t = float(np.dot(w_before, r_vec))
        gross_factor = 1.0 + gross_t
        if gross_factor <= 0.0:
            raise PortfolioOptimizationError(
                f"Portfolio gross return factor (1 + R_gross) reached {gross_factor:.6e} on "
                f"{effective_date.strftime('%Y-%m-%d')}; holdings drift is undefined."
            )
        net_t = float((1.0 - cost_t) * gross_factor - 1.0)
        gross_arr[out_idx] = gross_t
        net_arr[out_idx] = net_t

        drifted_weights = w_before * (1.0 + r_vec) / gross_factor

    active_dates = dates[burn_in:]
    weights_before_df = pd.DataFrame(
        weights_before_arr,
        index=active_dates,
        columns=list(CANONICAL_TICKERS),
        dtype=float,
    )
    gross_series = pd.Series(gross_arr, index=active_dates, dtype=float, name="gross_return")
    net_series = pd.Series(net_arr, index=active_dates, dtype=float, name="net_return")
    turnover_series = pd.Series(turnover_arr, index=active_dates, dtype=float, name="turnover")
    costs_series = pd.Series(costs_arr, index=active_dates, dtype=float, name="cost")

    wealth_series = (1.0 + net_series).cumprod()
    wealth_series.name = "wealth"
    running_peak = np.maximum(1.0, wealth_series.cummax())
    drawdown_series = wealth_series / running_peak - 1.0
    drawdown_series.name = "drawdown"

    rebalances_df = pd.DataFrame(rebalance_records)
    all_feasible = bool(rebalances_df["mandate_feasible"].all())
    unique_violations: list[str] = []
    for v_str in rebalances_df["mandate_violations"]:
        if v_str:
            for part in str(v_str).split("; "):
                if part and part not in unique_violations:
                    unique_violations.append(part)

    is_reference = objective in ("equal_weight", "benchmark_60_40")
    pre_return_compliance = summarize_pre_return_holdings_compliance(
        weights_before_df,
        eff_constraints,
        tol=1e-7,
    )
    all_pre_return_within_caps = bool(
        pre_return_compliance["all_pre_return_sessions_within_caps"]
    )

    if all_feasible:
        rebalance_target_status = (
            "rebalance_targets_within_provisional_caps"
            if eff_constraints.provisional
            else "rebalance_targets_within_mandate_caps"
        )
        if all_pre_return_within_caps:
            compliance_status = (
                "rebalance_targets_and_pre_return_holdings_within_provisional_caps"
                if eff_constraints.provisional
                else "rebalance_targets_and_pre_return_holdings_within_mandate_caps"
            )
        else:
            compliance_status = (
                "rebalance_targets_feasible_with_post_trade_drift_cap_breaches_provisional"
                if eff_constraints.provisional
                else "rebalance_targets_feasible_with_post_trade_drift_cap_breaches"
            )
    elif is_reference:
        rebalance_target_status = (
            "unconstrained_reference_violates_provisional_caps"
            if eff_constraints.provisional
            else "unconstrained_reference_violates_mandate_constraints"
        )
        compliance_status = rebalance_target_status
    else:
        rebalance_target_status = (
            "rebalance_targets_violate_provisional_caps"
            if eff_constraints.provisional
            else "rebalance_targets_violate_mandate_constraints"
        )
        compliance_status = rebalance_target_status

    try:
        implied_bounds_records: list[dict[str, Any]] | str = compute_implied_weight_bounds(
            eff_constraints
        ).to_dict(orient="records")
    except PortfolioOptimizationError as exc:
        implied_bounds_records = f"infeasible_constraints: {exc}"

    metadata: dict[str, Any] = {
        "strategy_id": str(strategy_spec.strategy_id),
        "objective": objective,
        "provisional": bool(strategy_spec.provisional or eff_constraints.provisional),
        "is_reference_benchmark": bool(is_reference),
        "rebalance_frequency": freq,
        "estimation_window_days": burn_in,
        "covariance_estimator": (
            strategy_spec.covariance_estimator if requires_estimation else "none"
        ),
        "canonical_tickers": CANONICAL_TICKERS,
        "execution_assumption": config.chronology.execution_assumption,
        "initial_investment_convention": (
            "enter_from_100pct_cash_at_first_active_session_with_pre_trade_weights_zero"
        ),
        "turnover_convention": TURNOVER_CONVENTION_DESCRIPTION,
        "cost_convention": COST_CONVENTION_DESCRIPTION,
        "drawdown_convention": DRAWDOWN_CONVENTION_DESCRIPTION,
        "transaction_cost_bps_one_way": cost_bps,
        "active_start": active_dates[0].strftime("%Y-%m-%d"),
        "active_end": active_dates[-1].strftime("%Y-%m-%d"),
        "n_active_sessions": int(n_active),
        "n_rebalances": int(len(rebalances_df)),
        "constraint_enforcement_scope": "rebalance_targets_only",
        "continuous_holdings_cap_policy": (
            "not_enforced_holdings_drift_naturally_between_scheduled_rebalances_"
            "continuous_cap_mandate_pending_human_decision"
        ),
        "mandate_feasible_all_rebalances": all_feasible,
        "rebalance_target_compliance_status": rebalance_target_status,
        "mandate_feasible_all_pre_return_sessions": all_pre_return_within_caps,
        "pre_return_holdings_compliance": pre_return_compliance,
        "mandate_compliance_status": compliance_status,
        "mandate_violations_summary": tuple(unique_violations),
        "constraints": asdict(eff_constraints),
        "implied_mandate_bounds": implied_bounds_records,
        "chronology_boundaries": {
            "status": config.chronology.status,
            "development_start": config.chronology.development_start,
            "development_end": config.chronology.development_end,
            "selection_start": config.chronology.selection_start,
            "selection_end": config.chronology.selection_end,
            "evaluation_start": config.chronology.evaluation_start,
            "evaluation_end": config.chronology.evaluation_end,
        },
        "config_hash": config.config_hash,
    }

    return PortfolioPath(
        weights_before=weights_before_df,
        gross_returns=gross_series,
        net_returns=net_series,
        turnover=turnover_series,
        costs=costs_series,
        wealth=wealth_series,
        drawdown=drawdown_series,
        rebalances=rebalances_df,
        metadata=metadata,
    )
