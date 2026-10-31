"""Euler marginal/component VaR & ES risk budgeting and feasible sizing comparisons.

Public interfaces frozen in D0 for SOLO STEP 8 (B2):
- ``risk_contributions(train_asset_returns, weights, *, confidence, method) -> pd.DataFrame``
- ``compare_feasible_allocations(train_asset_returns, candidates, limits, risk_fn) -> pd.DataFrame``
"""

from __future__ import annotations

from typing import Any

import math
import numpy as np
import pandas as pd
from scipy.stats import norm

from quantedge.contracts import CANONICAL_TICKERS, RISK_CONTRIBUTION_COLUMNS, PortfolioConstraints, RiskEstimate, RiskForecastFn, StrategySpec
from quantedge.es import _validate_confidence, empirical_tail_weights
from quantedge.portfolio import check_weight_feasibility, construct_weights
from quantedge.var import normal_moments, _validate_asset_return_frame, _validate_portfolio_weights


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
    conf, alpha = _validate_confidence(confidence)
    arr = _validate_asset_return_frame(train_asset_returns, min_rows=2, context="train_asset_returns")
    w = _validate_portfolio_weights(weights)
    allowed = ("normal_var", "normal_es", "historical_es")
    if method not in allowed:
        raise ValueError(f"method must be one of {allowed}")
    note = "1-day pre-cost signed Euler components; no absolute-value transformation."
    marginal: np.ndarray | None
    status = "ok"
    if method == "historical_es":
        losses = pd.Series(-(arr @ w), index=train_asset_returns.index)
        tail = empirical_tail_weights(losses, conf).to_numpy(dtype=float)
        marginal = -(arr.T @ tail)
        total = float(losses.to_numpy() @ tail)
        note += " Exact shared worst-probability-mass ES; equal-weight boundary ties give a subgradient."
    else:
        mean, covariance = normal_moments(train_asset_returns)
        mu = mean.to_numpy()
        cov = covariance.to_numpy()
        sigma = math.sqrt(max(float(w @ cov @ w), 0.0))
        z = float(norm.ppf(conf))
        factor = z if method == "normal_var" else float(norm.pdf(z) / alpha)
        total = -float(mu @ w) + factor * sigma
        if sigma <= 1e-15 and float(np.max(np.abs(cov))) > 1e-24:
            marginal = None
            status = "unavailable"
            note += " Zero portfolio volatility with risky individual assets: normal risk gradient is undefined."
        else:
            marginal = -mu if sigma <= 1e-15 else -mu + factor * (cov @ w) / sigma
            if sigma <= 1e-15:
                status = "warning"
                note += " Deterministic zero covariance; only the mean-loss component remains."
    components = None if marginal is None else w * marginal
    if components is not None and not math.isclose(float(components.sum()), total, rel_tol=1e-10, abs_tol=1e-13):
        raise ArithmeticError("Euler component sum does not match total risk")
    percentage_defined = components is not None and total > 1e-15
    if not percentage_defined:
        if status == "ok":
            status = "warning"
        note += " Percentage contributions unavailable for nonpositive/near-zero total risk or undefined gradient."
    rows = []
    for i, ticker in enumerate(CANONICAL_TICKERS):
        rows.append(dict(ticker=ticker, weight=float(w[i]),
                         marginal_risk=None if marginal is None else float(marginal[i]),
                         component_risk=None if components is None else float(components[i]),
                         pct_contribution=None if not percentage_defined else float(components[i] / total),
                         total_risk=total, method=method, confidence=conf, status=status, note=note))
    out = pd.DataFrame(rows, columns=RISK_CONTRIBUTION_COLUMNS, dtype=object)
    out.attrs.update(n_obs=len(arr), sample_start=str(train_asset_returns.index[0].date()),
                     sample_end=str(train_asset_returns.index[-1].date()),
                     units="fraction_of_NAV; pct_contribution is fraction_of_total_risk",
                     euler_sum=None if components is None else float(components.sum()),
                     percentage_status="ok" if percentage_defined else "unavailable")
    return out


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
    arr = _validate_asset_return_frame(train_asset_returns, min_rows=2, context="train_asset_returns")
    if not candidates or not all(isinstance(k, str) and k for k in candidates):
        raise ValueError("candidates must have nonempty string IDs")
    allowed_keys = {"constraints", "baseline_id", "confidence", "max_var_loss", "max_es_loss", "annualization_days", "seed"}
    if not isinstance(limits, dict) or set(limits) - allowed_keys:
        raise ValueError(f"limits keys must be from {sorted(allowed_keys)}")
    constraints = limits.get("constraints")
    if not isinstance(constraints, PortfolioConstraints):
        raise ValueError("limits['constraints'] must explicitly provide PortfolioConstraints")
    conf, _ = _validate_confidence(limits.get("confidence", 0.99))
    annual = limits.get("annualization_days", 252)
    if isinstance(annual, bool) or not isinstance(annual, (int, float)) or not math.isfinite(annual) or annual <= 0:
        raise ValueError("annualization_days must be positive and finite")
    for key in ("max_var_loss", "max_es_loss"):
        value = limits.get(key)
        if value is not None and (isinstance(value, bool) or not math.isfinite(value) or value < 0):
            raise ValueError(f"{key} must be a nonnegative finite loss fraction or None")
    baseline_id = limits.get("baseline_id", next(iter(candidates)))
    if baseline_id not in candidates:
        raise ValueError("baseline_id must be an evaluated candidate")
    rows = []
    for candidate_id, candidate in candidates.items():
        row = {"candidate_id": candidate_id, "baseline_id": baseline_id, "confidence": conf,
               "constraint_feasible": False, "risk_limits_status": "unavailable",
               "risk_limits_met": None, "feasible_under_supplied_tests": None,
               "var_loss": None, "es_loss": None, "expected_annual_return_proxy": None,
               "status": "unavailable", "reason": None, "weights": None,
               "expected_return_assumption": "annualization_days times same-window arithmetic sample mean; not a forward forecast"}
        try:
            if isinstance(candidate, StrategySpec):
                if candidate.constraints is not None and candidate.constraints != constraints:
                    raise ValueError("StrategySpec constraints conflict with comparison constraints")
                if candidate.fixed_weights is not None:
                    if candidate.objective not in ("fixed_weights", "benchmark_60_40"):
                        raise ValueError("StrategySpec fixed weights conflict with objective")
                    if set(candidate.fixed_weights) != set(CANONICAL_TICKERS):
                        raise ValueError("StrategySpec fixed weights must include exactly seven ETFs")
                    candidate_weights = pd.Series(candidate.fixed_weights).reindex(CANONICAL_TICKERS)
                else:
                    if candidate.covariance_estimator != "sample_ddof1":
                        raise ValueError("Unsupported StrategySpec covariance estimator")
                    train = train_asset_returns
                    if candidate.estimation_window_days is not None:
                        size = candidate.estimation_window_days
                        if isinstance(size, bool) or not isinstance(size, int) or size < 2 or size > len(train):
                            raise ValueError("StrategySpec estimation window unavailable/invalid")
                        train = train.iloc[-size:]
                    candidate_weights = construct_weights(train.copy(), constraints, candidate.objective)
            elif isinstance(candidate, pd.Series):
                candidate_weights = candidate.copy()
            else:
                raise ValueError("candidate must be canonical pd.Series or StrategySpec")
            w = _validate_portfolio_weights(candidate_weights)
            check = check_weight_feasibility(candidate_weights, constraints)
            row.update(weights={t: float(w[i]) for i, t in enumerate(CANONICAL_TICKERS)},
                       constraint_feasible=check["feasible"], constraint_violations=check["violations"],
                       expected_annual_return_proxy=float(arr.mean(axis=0) @ w * annual))
            estimate = risk_fn(train_asset_returns.copy(), candidate_weights.copy(), confidence=conf, seed=limits.get("seed"))
            if not isinstance(estimate, RiskEstimate) or abs(estimate.confidence-conf) > 1e-12 or estimate.horizon_days != 1:
                raise ValueError("risk callback must return matching one-day RiskEstimate")
            if estimate.n_obs != len(arr) or pd.Timestamp(estimate.sample_start) != train_asset_returns.index[0] or pd.Timestamp(estimate.sample_end) != train_asset_returns.index[-1]:
                raise ValueError("risk callback sample bounds/count mismatch")
            row.update(var_loss=estimate.var_loss, es_loss=estimate.es_loss, model=estimate.model,
                       status=estimate.status, reason=estimate.reason)
            supplied = [(key, metric) for key, metric in (("max_var_loss", "var_loss"), ("max_es_loss", "es_loss")) if limits.get(key) is not None]
            if not supplied:
                row["risk_limits_status"] = "not_supplied_pending_human_input"
            elif any(row[metric] is None for _, metric in supplied):
                row["risk_limits_status"] = "unavailable_risk_estimate"
            else:
                row["risk_limits_met"] = all(row[metric] <= limits[key] for key, metric in supplied)
                row["risk_limits_status"] = "meets_supplied_limits" if row["risk_limits_met"] else "breaches_supplied_limits"
            if not row["constraint_feasible"]:
                row["feasible_under_supplied_tests"] = False
            elif row["risk_limits_met"] is not None:
                row["feasible_under_supplied_tests"] = row["risk_limits_met"]
        except Exception as exc:
            row.update(status="unavailable", reason=f"{type(exc).__name__}: {exc}")
        rows.append(row)
    baseline = next(row for row in rows if row["candidate_id"] == baseline_id)
    for row in rows:
        row["baseline_weights"] = baseline["weights"]
        row["weight_change"] = None if row["weights"] is None or baseline["weights"] is None else {t: row["weights"][t]-baseline["weights"][t] for t in CANONICAL_TICKERS}
        for name in ("var_loss", "es_loss"):
            row[f"reduction_{name}"] = None if row[name] is None or baseline[name] is None else baseline[name]-row[name]
        row["annual_return_proxy_sacrificed"] = None if row["expected_annual_return_proxy"] is None or baseline["expected_annual_return_proxy"] is None else baseline["expected_annual_return_proxy"]-row["expected_annual_return_proxy"]
        reduction = row["reduction_es_loss"]
        row["annual_return_proxy_sacrificed_per_daily_es_reduction"] = None if reduction is None or reduction <= 1e-15 or row["annual_return_proxy_sacrificed"] is None else row["annual_return_proxy_sacrificed"]/reduction
    out = pd.DataFrame(rows, dtype=object)
    out.attrs.update(sample_start=str(train_asset_returns.index[0].date()), sample_end=str(train_asset_returns.index[-1].date()),
                     n_obs=len(arr), annualization_days=annual, approval="PENDING; no automatic candidate selection",
                     units="risk fractions/day; arithmetic return proxy fraction/year; ratio mixes stated horizons")
    return out
