"""Unconditional Peaks-Over-Threshold Generalized Pareto (POT-GPD) EVT tail models (SOLO STEP 7 / C2-C3).

Public interfaces frozen in D0 for SOLO STEP 7 (C2/C3):
- ``estimate_evt_pot(train_asset_returns, weights, *, confidence, seed=None, ...) -> RiskEstimate``
- ``evt_threshold_diagnostics(losses, *, candidate_quantiles=..., min_exceedances=50) -> pd.DataFrame``

Supporting Step 7 helpers (new, additive):
- ``fit_gpd_tail(losses, *, threshold_quantile=0.95, min_exceedances=50) -> GPDTailFit``
- ``pot_var_es(fit, confidence) -> dict``                      (pure POT tail only)
- ``body_tail_cdf(fit, x)`` / ``body_tail_quantile(fit, c)`` / ``body_tail_es(fit, c)``
- ``estimate_evt_body_tail(train_asset_returns, weights, *, confidence, ...) -> RiskEstimate``
  (explicitly labelled empirical-body / GPD-tail construction; NOT pure EVT below ``u``)
- ``gpd_qq_pp_table(fit) -> pd.DataFrame``                     (descriptive QQ/PP data, no p-values)
- ``bootstrap_evt_tail_uncertainty(losses, *, ...) -> dict``   (cached moving-block bootstrap)

Conventions
-----------
- Losses are 1-day fixed-exposure simple-return losses ``L_t = -(R @ w)_t`` (positive = loss).
- Threshold ``u`` is the empirical ``q`` loss quantile under the same step-CDF order-statistic
  convention used by Historical VaR: ``u = L_(ceil(n q))`` (``n q`` snapped to an integer within
  ``1e-12 * n``). Exceedances are STRICT, ``L > u``; ``N_u`` counts them and ``p_u = N_u / n``.
  Ties at ``u`` therefore never enter the excess sample and can make ``p_u < 1 - q``.
- Excesses ``y = L - u`` (``L > u``) are fitted by maximum likelihood with
  ``scipy.stats.genpareto.fit(y, floc=0)``: location fixed at ``0``, shape ``xi`` (scipy ``c``),
  scale ``beta > 0``. Support is ``y >= 0`` for ``xi >= 0`` and ``0 <= y <= -beta / xi`` for
  ``xi < 0`` (finite upper loss endpoint ``u - beta / xi``).
- Pure POT (``a = (1 - c) / p_u``, valid only for ``c >= q`` and ``a <= 1``):
  ``VaR_c = u + (beta / xi) (a^(-xi) - 1)`` evaluated stably as ``u + beta * expm1(-xi log a) / xi``
  with the exponential limit ``u - beta log a`` at ``xi = 0``; ``ES_c = (VaR_c + beta - xi u) / (1 - xi)``
  only for ``xi < 1`` (``xi >= 1`` -> ES ``None`` + warning). At ``a = 1`` (``c = 1 - p_u``)
  ``VaR_c = u`` exactly ("threshold boundary").
- Body/tail hybrid: CDF ``F(x) = F_n(x)`` for ``x <= u`` (empirical step CDF, mass ``1 - p_u``) and
  ``F(x) = 1 - p_u * S_GPD(x - u)`` for ``x > u`` (tail mass ``p_u``); continuous at ``u`` because
  ``F_n(u) = 1 - p_u`` under strict exceedances. Quantiles below the boundary use the step-CDF
  inverse ``L_(ceil(n c))`` and are labelled BODY (not EVT extrapolation). ES integrates the
  body quantile segment (including the partial order-statistic mass at the lower end) plus
  the fitted GPD upper tail ``p_u (u + beta / (1 - xi))``.
- Unconditional EVT assumes approximately independent, identically distributed exceedances.
  Financial losses cluster (Step 6 rejected independence for every Historical/Normal
  comparison), so all EVT results here are unconditional development diagnostics.
"""

from __future__ import annotations

from collections.abc import Sequence
import copy
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import math
from typing import Any
import warnings

import numpy as np
import pandas as pd
from scipy import optimize
from scipy.stats import genpareto

from quantedge.contracts import RiskEstimate
from quantedge.es import _validate_confidence

EVT_POT_MODEL: str = "evt_pot"
EVT_BODY_TAIL_MODEL: str = "evt_body_tail_hybrid"
DEFAULT_THRESHOLD_GRID: tuple[float, ...] = (0.90, 0.925, 0.95, 0.975)

_SNAP_TOL: float = 1e-12
_A_BOUNDARY_TOL: float = 1e-12
_XI_EXACT_ZERO_TOL: float = 1e-12
_XI_NONREGULAR: float = -0.5
_MIN_ALLOWED_EXCEEDANCES: int = 3
_MAX_BOOTSTRAP_REPLICATIONS: int = 2000
_OPTIMIZER_SETTINGS: dict[str, float | int] = {
    "xtol": 1e-10,
    "ftol": 1e-12,
    "maxiter": 20000,
    "maxfun": 40000,
}
_LOCAL_OPT_REL_STEP: float = 1e-4
_LOCAL_OPT_LOGLIK_TOL: float = 1e-7


# ----------------------------------------------------------------------------------------
# Validation helpers
# ----------------------------------------------------------------------------------------


def _validate_loss_values(losses: Any, *, context: str = "losses") -> np.ndarray:
    """Return a private finite float64 copy of a 1-D loss sample (pd.Series or array-like)."""
    if isinstance(losses, pd.DataFrame):
        raise TypeError(f"{context} must be one-dimensional (pd.Series or 1-D array); got DataFrame.")
    if isinstance(losses, pd.Series):
        if not losses.index.is_unique:
            raise ValueError(f"{context} index must be unique.")
        raw = losses.to_numpy()
    else:
        raw = np.asarray(losses)
    if raw.ndim != 1:
        raise ValueError(f"{context} must be one-dimensional; got shape {raw.shape}.")
    if raw.dtype == bool or (raw.dtype == object and any(isinstance(v, bool) for v in raw)):
        raise TypeError(f"{context} must contain numeric (non-boolean) values.")
    try:
        arr = np.array(raw, dtype=np.float64, copy=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must contain numeric float-convertible values.") from exc
    if arr.size < 2:
        raise ValueError(f"{context} requires at least 2 observations; got {arr.size}.")
    if not np.isfinite(arr).all():
        raise ValueError(f"{context} contains NaN or non-finite (+/-inf) values.")
    return arr


def _validate_threshold_quantile(threshold_quantile: Any) -> float:
    if isinstance(threshold_quantile, bool) or not isinstance(
        threshold_quantile, (int, float, np.floating)
    ):
        raise TypeError("threshold_quantile must be a float in (0, 1).")
    q = float(threshold_quantile)
    if not math.isfinite(q) or not (0.0 < q < 1.0):
        raise ValueError(f"threshold_quantile must lie strictly in (0, 1); got {threshold_quantile!r}.")
    return q


def _validate_min_exceedances(min_exceedances: Any) -> int:
    if isinstance(min_exceedances, bool) or not isinstance(min_exceedances, (int, np.integer)):
        raise TypeError("min_exceedances must be an integer.")
    m = int(min_exceedances)
    if m < _MIN_ALLOWED_EXCEEDANCES:
        raise ValueError(
            f"min_exceedances must be >= {_MIN_ALLOWED_EXCEEDANCES} for a two-parameter GPD fit; got {m}."
        )
    return m


def _validate_seed(seed: Any) -> int | None:
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError(f"seed must be an integer or None; got {type(seed).__name__}.")
    return int(seed)


def _snapped_rank(n_obs: int, prob: float) -> int:
    """Return 1-based step-CDF rank ``ceil(n * prob)`` with ``es.py``-consistent float snapping."""
    raw = float(n_obs) * float(prob)
    snap = float(round(raw))
    value = snap if abs(raw - snap) <= _SNAP_TOL * max(1.0, float(n_obs)) else raw
    return max(1, min(n_obs, int(math.ceil(value - _SNAP_TOL))))


# ----------------------------------------------------------------------------------------
# GPD tail fit
# ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GPDTailFit:
    """Immutable record of one POT-GPD fit at an empirical quantile threshold."""

    threshold_quantile: float
    min_exceedances: int
    n_obs: int
    threshold: float
    threshold_rank: int
    n_exceedances: int
    n_ties_at_threshold: int
    p_u: float
    tail_boundary_confidence: float
    mean_excess: float | None
    mean_excess_se: float | None
    n_unique_excesses: int
    xi: float | None
    beta: float | None
    modified_scale: float | None
    xi_se_asymptotic_iid: float | None
    beta_se_asymptotic_iid: float | None
    upper_support_loss: float | None
    loglik: float | None
    optimizer: dict[str, Any]
    status: str
    reasons: tuple[str, ...]
    sorted_losses: np.ndarray = field(repr=False, compare=False)
    excesses: np.ndarray = field(repr=False, compare=False)

    @property
    def is_usable(self) -> bool:
        """True when parameters are valid for VaR (status ``ok`` or ``warning``)."""
        return self.status in ("ok", "warning") and self.xi is not None and self.beta is not None

    def to_record(self) -> dict[str, Any]:
        """Return a strict-JSON-ready summary (no arrays)."""
        return {
            "threshold_quantile": self.threshold_quantile,
            "min_exceedances": self.min_exceedances,
            "n_obs": self.n_obs,
            "threshold": self.threshold,
            "threshold_rank": self.threshold_rank,
            "n_exceedances": self.n_exceedances,
            "n_ties_at_threshold": self.n_ties_at_threshold,
            "p_u": self.p_u,
            "tail_boundary_confidence": self.tail_boundary_confidence,
            "mean_excess": self.mean_excess,
            "mean_excess_se": self.mean_excess_se,
            "n_unique_excesses": self.n_unique_excesses,
            "xi": self.xi,
            "beta": self.beta,
            "modified_scale": self.modified_scale,
            "xi_se_asymptotic_iid": self.xi_se_asymptotic_iid,
            "beta_se_asymptotic_iid": self.beta_se_asymptotic_iid,
            "upper_support_loss": self.upper_support_loss,
            "loglik": self.loglik,
            "optimizer": dict(self.optimizer),
            "status": self.status,
            "reasons": list(self.reasons),
        }


def _gpd_loglik(excesses: np.ndarray, xi: float, beta: float) -> float:
    if not (math.isfinite(xi) and math.isfinite(beta)) or beta <= 0.0:
        return -math.inf
    with np.errstate(all="ignore"):
        vals = genpareto.logpdf(excesses, xi, loc=0.0, scale=beta)
    total = float(np.sum(vals))
    return total if math.isfinite(total) else -math.inf


def _fit_gpd_mle(excesses: np.ndarray) -> tuple[float, float, dict[str, Any]]:
    """Fit ``genpareto`` with ``floc=0`` via a convergence-recording Nelder-Mead optimizer."""
    record: dict[str, Any] = {}

    def _recording_fmin(func, x0, args=(), disp=0):  # noqa: ANN001 - scipy optimizer protocol
        xopt, fopt, n_iter, n_fev, warnflag = optimize.fmin(
            func,
            x0,
            args=args,
            disp=0,
            full_output=True,
            xtol=float(_OPTIMIZER_SETTINGS["xtol"]),
            ftol=float(_OPTIMIZER_SETTINGS["ftol"]),
            maxiter=int(_OPTIMIZER_SETTINGS["maxiter"]),
            maxfun=int(_OPTIMIZER_SETTINGS["maxfun"]),
        )
        record.update(
            {
                "method": "scipy.optimize.fmin (Nelder-Mead) via genpareto.fit(floc=0)",
                "start": [float(v) for v in np.atleast_1d(x0)],
                "objective_min": float(fopt),
                "iterations": int(n_iter),
                "function_evaluations": int(n_fev),
                "warnflag": int(warnflag),
                "converged": bool(int(warnflag) == 0),
                **{k: _OPTIMIZER_SETTINGS[k] for k in ("xtol", "ftol", "maxiter", "maxfun")},
            }
        )
        return xopt

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with np.errstate(all="ignore"):
            c_hat, loc_hat, scale_hat = genpareto.fit(excesses, floc=0.0, optimizer=_recording_fmin)
    if float(loc_hat) != 0.0:
        raise RuntimeError(f"genpareto.fit returned non-zero location {loc_hat!r} despite floc=0.")
    return float(c_hat), float(scale_hat), record


def _local_optimum_check(excesses: np.ndarray, xi: float, beta: float, loglik: float) -> bool:
    """Check that small coordinate perturbations do not materially increase the log-likelihood."""
    step_xi = _LOCAL_OPT_REL_STEP * max(1.0, abs(xi))
    step_beta = _LOCAL_OPT_REL_STEP * beta
    tol = _LOCAL_OPT_LOGLIK_TOL * max(1.0, abs(loglik))
    for dxi, dbeta in ((step_xi, 0.0), (-step_xi, 0.0), (0.0, step_beta), (0.0, -step_beta)):
        if _gpd_loglik(excesses, xi + dxi, beta + dbeta) > loglik + tol:
            return False
    return True


def _build_fit(sorted_losses: np.ndarray, q: float, min_exc: int) -> GPDTailFit:
    n_obs = int(sorted_losses.size)
    rank = _snapped_rank(n_obs, q)
    u = float(sorted_losses[rank - 1])
    exceed_mask = sorted_losses > u
    excess_losses = sorted_losses[exceed_mask]
    n_exc = int(excess_losses.size)
    n_ties = int(np.sum(sorted_losses == u))
    p_u = float(n_exc) / float(n_obs)
    excesses = np.ascontiguousarray(excess_losses - u, dtype=np.float64)
    excesses.setflags(write=False)
    sorted_ro = sorted_losses.copy()
    sorted_ro.setflags(write=False)
    n_unique = int(np.unique(excesses).size)

    mean_excess = float(np.mean(excesses)) if n_exc >= 1 else None
    mean_excess_se = (
        float(np.std(excesses, ddof=1) / math.sqrt(n_exc)) if n_exc >= 2 else None
    )

    base = dict(
        threshold_quantile=q,
        min_exceedances=min_exc,
        n_obs=n_obs,
        threshold=u,
        threshold_rank=rank,
        n_exceedances=n_exc,
        n_ties_at_threshold=n_ties,
        p_u=p_u,
        tail_boundary_confidence=float(1.0 - p_u),
        mean_excess=mean_excess,
        mean_excess_se=mean_excess_se,
        n_unique_excesses=n_unique,
        sorted_losses=sorted_ro,
        excesses=excesses,
    )
    empty_params = dict(
        xi=None,
        beta=None,
        modified_scale=None,
        xi_se_asymptotic_iid=None,
        beta_se_asymptotic_iid=None,
        upper_support_loss=None,
        loglik=None,
    )

    if n_exc < min_exc:
        return GPDTailFit(
            **base,
            **empty_params,
            optimizer={},
            status="unavailable",
            reasons=(
                f"insufficient strict exceedances: N_u={n_exc} < min_exceedances={min_exc} at "
                f"threshold quantile {q:g} (threshold and minimum are never lowered silently)",
            ),
        )
    if n_unique < 3 or float(np.ptp(excesses)) <= 0.0:
        return GPDTailFit(
            **base,
            **empty_params,
            optimizer={},
            status="unavailable",
            reasons=(f"degenerate excess sample: only {n_unique} distinct excess values",),
        )

    try:
        xi, beta, opt = _fit_gpd_mle(excesses)
    except Exception as exc:  # pragma: no cover - defensive; scipy FitError etc.
        return GPDTailFit(
            **base,
            **empty_params,
            optimizer={"error": f"{type(exc).__name__}: {exc}"},
            status="unavailable",
            reasons=(f"GPD maximum-likelihood fit failed: {type(exc).__name__}",),
        )

    reasons: list[str] = []
    fatal = False
    if not (math.isfinite(xi) and math.isfinite(beta)):
        fatal = True
        reasons.append("non-finite fitted GPD parameters")
    elif beta <= 0.0:
        fatal = True
        reasons.append(f"non-positive fitted scale beta={beta!r}")
    if not opt.get("converged", False):
        fatal = True
        reasons.append(f"optimizer did not converge (warnflag={opt.get('warnflag')})")

    loglik = _gpd_loglik(excesses, xi, beta) if not fatal else -math.inf
    upper_support = None
    if not fatal:
        if xi <= -1.0:
            fatal = True
            reasons.append(f"xi={xi:.6g} <= -1: likelihood non-regular/unbounded; fit rejected")
        elif xi < 0.0:
            upper_support_excess = -beta / xi
            upper_support = float(u + upper_support_excess)
            if float(np.max(excesses)) > upper_support_excess * (1.0 + 1e-10):
                fatal = True
                reasons.append("observed excess lies beyond fitted finite upper support")
        if not math.isfinite(loglik):
            fatal = True
            reasons.append("non-finite log-likelihood at fitted parameters (support violation)")
    opt = dict(opt)
    if not fatal:
        opt["local_optimum_check_passed"] = _local_optimum_check(excesses, xi, beta, loglik)
        if not opt["local_optimum_check_passed"]:
            fatal = True
            reasons.append("fitted parameters failed the local log-likelihood optimality check")

    if fatal:
        return GPDTailFit(
            **base,
            **empty_params,
            optimizer=opt,
            status="unavailable",
            reasons=tuple(reasons),
        )

    status = "ok"
    if xi >= 1.0:
        status = "warning"
        reasons.append(f"xi={xi:.6g} >= 1: GPD mean is infinite, so ES is unavailable")
    elif xi <= _XI_NONREGULAR:
        status = "warning"
        reasons.append(f"xi={xi:.6g} <= -0.5: MLE asymptotics non-regular; standard errors omitted")
    if n_ties > 1:
        reasons.append(
            f"{n_ties} observations tied at threshold u; ties are excluded from strict exceedances"
        )

    if xi > _XI_NONREGULAR:
        xi_se = float((1.0 + xi) / math.sqrt(n_exc))
        beta_se = float(beta * math.sqrt(2.0 * (1.0 + xi) / n_exc))
    else:
        xi_se = None
        beta_se = None

    return GPDTailFit(
        **base,
        xi=float(xi),
        beta=float(beta),
        modified_scale=float(beta - xi * u),
        xi_se_asymptotic_iid=xi_se,
        beta_se_asymptotic_iid=beta_se,
        upper_support_loss=upper_support,
        loglik=float(loglik),
        optimizer=opt,
        status=status,
        reasons=tuple(reasons),
    )


def fit_gpd_tail(
    losses: pd.Series | np.ndarray | Sequence[float],
    *,
    threshold_quantile: float = 0.95,
    min_exceedances: int = 50,
) -> GPDTailFit:
    """Fit a GPD to strict exceedances above the empirical ``threshold_quantile`` loss.

    Never lowers the threshold or minimum count: insufficient, degenerate, non-converged,
    non-positive-scale or support-violating fits return ``status='unavailable'`` with reasons.
    The input is copied and never mutated.
    """
    arr = _validate_loss_values(losses)
    q = _validate_threshold_quantile(threshold_quantile)
    m = _validate_min_exceedances(min_exceedances)
    return _build_fit(np.sort(arr, kind="mergesort"), q, m)


# ----------------------------------------------------------------------------------------
# Pure POT VaR / ES
# ----------------------------------------------------------------------------------------


def _gpd_excess_quantile(xi: float, beta: float, a: float) -> float:
    """Return GPD excess quantile ``beta * (a^(-xi) - 1) / xi`` at tail probability ``a``."""
    if a == 1.0:
        return 0.0
    log_a = math.log(a)
    if abs(xi) <= _XI_EXACT_ZERO_TOL:
        return float(-beta * log_a)
    return float(beta * math.expm1(-xi * log_a) / xi)


def _snap_a(alpha: float, p_u: float) -> float:
    a = alpha / p_u
    if abs(a - 1.0) <= _A_BOUNDARY_TOL:
        return 1.0
    return float(a)


def pot_var_es(fit: GPDTailFit, confidence: float) -> dict[str, Any]:
    """Pure POT-GPD VaR/ES at ``confidence`` (never extrapolated below the tail boundary).

    Returns a dict with ``status`` in {'ok', 'warning', 'unavailable'}, ``var_loss``,
    ``es_loss`` (``None`` when unavailable or when ``xi >= 1``), ``a``, ``region`` and ``reason``.
    """
    conf, alpha = _validate_confidence(confidence)
    out: dict[str, Any] = {
        "construction": "pure_pot_gpd_tail",
        "confidence": conf,
        "alpha": alpha,
        "a": None,
        "region": None,
        "var_loss": None,
        "es_loss": None,
        "status": "unavailable",
        "reason": None,
    }
    if not fit.is_usable:
        out["reason"] = "GPD fit unavailable: " + "; ".join(fit.reasons)
        return out
    if conf < fit.threshold_quantile - _SNAP_TOL:
        out["reason"] = (
            f"confidence {conf:g} is below threshold quantile {fit.threshold_quantile:g}: pure POT "
            "tail inference is not defined in the body (use the labelled body/tail helper)"
        )
        return out
    a = _snap_a(alpha, fit.p_u)
    out["a"] = a
    if a > 1.0:
        out["reason"] = (
            f"confidence {conf:g} is below the actual empirical tail boundary 1 - p_u = "
            f"{fit.tail_boundary_confidence:.12g} (a={a:.12g} > 1); pure POT unavailable"
        )
        return out
    xi = float(fit.xi)  # type: ignore[arg-type]
    beta = float(fit.beta)  # type: ignore[arg-type]
    u = float(fit.threshold)
    var_loss = float(u + _gpd_excess_quantile(xi, beta, a))
    out["var_loss"] = var_loss
    out["region"] = "threshold_boundary" if a == 1.0 else "tail"
    reasons: list[str] = [r for r in fit.reasons]
    if xi < 1.0:
        es_loss = float((var_loss + beta - xi * u) / (1.0 - xi))
        if es_loss < var_loss and (var_loss - es_loss) <= 1e-15 * max(1.0, abs(var_loss)):
            es_loss = var_loss
        out["es_loss"] = es_loss
        out["status"] = "warning" if fit.status == "warning" else "ok"
    else:
        out["es_loss"] = None
        out["status"] = "warning"
        reasons.append("ES unavailable: xi >= 1 implies an infinite GPD mean")
    out["reason"] = "; ".join(reasons) if reasons else None
    return out


# ----------------------------------------------------------------------------------------
# Empirical-body / GPD-tail hybrid distribution
# ----------------------------------------------------------------------------------------


def _require_usable(fit: GPDTailFit) -> tuple[float, float, float]:
    if not fit.is_usable:
        raise ValueError("Body/tail distribution requires a usable GPD fit: " + "; ".join(fit.reasons))
    return float(fit.xi), float(fit.beta), float(fit.threshold)  # type: ignore[arg-type]


def body_tail_cdf(fit: GPDTailFit, x: float | np.ndarray) -> float | np.ndarray:
    """Hybrid CDF: empirical step CDF for ``x <= u`` and ``1 - p_u * S_GPD(x - u)`` above ``u``."""
    xi, beta, u = _require_usable(fit)
    x_arr = np.asarray(x, dtype=np.float64)
    n = fit.n_obs
    body = np.searchsorted(fit.sorted_losses, x_arr, side="right") / float(n)
    with np.errstate(all="ignore"):
        tail = 1.0 - fit.p_u * genpareto.sf(np.maximum(x_arr - u, 0.0), xi, loc=0.0, scale=beta)
    result = np.where(x_arr <= u, body, tail)
    return float(result) if result.ndim == 0 else result


def _body_tail_region(fit: GPDTailFit, alpha: float) -> tuple[str, float]:
    a = _snap_a(alpha, fit.p_u)
    if a == 1.0:
        return "threshold_boundary", a
    return ("tail", a) if a < 1.0 else ("body", a)


def body_tail_quantile(fit: GPDTailFit, confidence: float) -> float:
    """Hybrid quantile: GPD tail for ``c >= 1 - p_u``; step-CDF body ``L_(ceil(n c))`` below."""
    xi, beta, u = _require_usable(fit)
    conf, alpha = _validate_confidence(confidence)
    region, a = _body_tail_region(fit, alpha)
    if region == "body":
        rank = _snapped_rank(fit.n_obs, conf)
        return float(fit.sorted_losses[rank - 1])
    return float(u + _gpd_excess_quantile(xi, beta, a))


def _body_quantile_integral(fit: GPDTailFit, conf: float) -> float:
    """Integrate the step-CDF body quantile over ``(c, 1 - p_u]`` with partial lower mass."""
    n = fit.n_obs
    upper_rank = n - fit.n_exceedances  # (1 - p_u) = upper_rank / n exactly
    k0 = _snapped_rank(n, conf)
    if k0 > upper_rank:
        return 0.0
    ks = np.arange(k0, upper_rank + 1, dtype=np.float64)
    left = np.maximum((ks - 1.0) / n, conf)
    right = ks / n
    lengths = np.clip(right - left, 0.0, None)
    values = fit.sorted_losses[k0 - 1 : upper_rank]
    return float(np.dot(values, lengths))


def body_tail_es(fit: GPDTailFit, confidence: float) -> dict[str, Any]:
    """Hybrid ES with explicit body and tail contributions (``es_loss=None`` if ``xi >= 1``)."""
    xi, beta, u = _require_usable(fit)
    conf, alpha = _validate_confidence(confidence)
    region, a = _body_tail_region(fit, alpha)
    var_loss = body_tail_quantile(fit, conf)
    tail_mean_infinite = xi >= 1.0
    if region in ("tail", "threshold_boundary"):
        es = None if tail_mean_infinite else float((var_loss + beta - xi * u) / (1.0 - xi))
        body_mass, body_integral = 0.0, 0.0
        tail_mass = alpha
        tail_integral = None if es is None else float(es * alpha)
    else:
        body_mass = float(fit.tail_boundary_confidence - conf)
        body_integral = _body_quantile_integral(fit, conf)
        tail_mass = fit.p_u
        tail_integral = None if tail_mean_infinite else float(fit.p_u * (u + beta / (1.0 - xi)))
        es = None if tail_integral is None else float((body_integral + tail_integral) / alpha)
    if es is not None and es < var_loss and (var_loss - es) <= 1e-15 * max(1.0, abs(var_loss)):
        es = var_loss
    return {
        "construction": "empirical_body_gpd_tail_hybrid",
        "confidence": conf,
        "alpha": alpha,
        "a": a,
        "region": region,
        "var_label": (
            "BODY_EMPIRICAL_QUANTILE_NOT_EVT_EXTRAPOLATION" if region == "body" else "GPD_TAIL"
        ),
        "var_loss": var_loss,
        "es_loss": es,
        "body_probability_mass": body_mass,
        "tail_probability_mass": tail_mass,
        "body_quantile_integral": body_integral,
        "tail_quantile_integral": tail_integral,
        "tail_share_of_es_mass": float(tail_mass / alpha),
        "es_status": "unavailable_xi_ge_1" if es is None else "finite",
    }


# ----------------------------------------------------------------------------------------
# Portfolio-level estimators
# ----------------------------------------------------------------------------------------


def portfolio_losses(train_asset_returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Validated fixed-exposure losses ``L = -(train_asset_returns @ weights)`` (C1 validators)."""
    from quantedge.var import _validate_asset_return_frame, _validate_portfolio_weights

    x_arr = _validate_asset_return_frame(train_asset_returns, min_rows=0, context="train_asset_returns")
    w_arr = _validate_portfolio_weights(weights)
    return pd.Series(
        np.ascontiguousarray(-(x_arr @ w_arr), dtype=np.float64),
        index=train_asset_returns.index,
        name="portfolio_loss",
        dtype=float,
    )


def _estimate_common(
    train_asset_returns: pd.DataFrame,
    weights: pd.Series,
    confidence: float,
    seed: int | None,
    threshold_quantile: float,
    min_exceedances: int,
    model: str,
) -> tuple[float, float, pd.Series, dict[str, Any]]:
    conf, alpha = _validate_confidence(confidence)
    q = _validate_threshold_quantile(threshold_quantile)
    m = _validate_min_exceedances(min_exceedances)
    seed_clean = _validate_seed(seed)
    losses = portfolio_losses(train_asset_returns, weights)
    n_obs = int(len(losses))
    diag: dict[str, Any] = {
        "model": model,
        "confidence": conf,
        "alpha": alpha,
        "horizon_days": 1,
        "units": "fraction_of_portfolio_nav",
        "loss_convention": "L_t = -(train_asset_returns @ weights)_t; positive values are 1-day pre-cost losses",
        "threshold_quantile": q,
        "min_exceedances": m,
        "threshold_convention": "u = L_(ceil(n q)) step-CDF order statistic; strict exceedances L > u",
        "gpd_fit": "scipy.stats.genpareto.fit(excess, floc=0) maximum likelihood",
        "seed": seed_clean,
        "seed_note": "MLE fit is deterministic; seed recorded but unused",
        "n_obs": n_obs,
        "weights": {str(k): float(v) for k, v in weights.items()},
        "unconditional_iid_assumption": (
            "Unconditional POT-GPD ignores volatility clustering/dependence in exceedances."
        ),
    }
    return conf, alpha, losses, diag


def _sample_bounds(losses: pd.Series) -> tuple[str | None, str | None]:
    if len(losses) == 0:
        return None, None
    idx = losses.index
    if isinstance(idx, pd.DatetimeIndex):
        return str(idx[0].date()), str(idx[-1].date())
    return str(idx[0]), str(idx[-1])


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
    - Requires ``a = (1 - c) / p_u <= 1``: below the actual empirical tail boundary
      ``1 - p_u`` (possible with ties at ``u``) pure tail inference is unavailable.
    """
    conf, _alpha, losses, diag = _estimate_common(
        train_asset_returns, weights, confidence, seed, threshold_quantile, min_exceedances, EVT_POT_MODEL
    )
    n_obs = int(len(losses))
    start, end = _sample_bounds(losses)

    def _unavailable(reason: str, extra: dict[str, Any] | None = None) -> RiskEstimate:
        d = dict(diag)
        d.update(extra or {})
        d["construction"] = "pure_pot_gpd_tail"
        return RiskEstimate(
            model=EVT_POT_MODEL,
            confidence=conf,
            horizon_days=1,
            var_loss=None,
            es_loss=None,
            n_obs=n_obs,
            sample_start=start,
            sample_end=end,
            status="unavailable",
            reason=reason,
            diagnostics=d,
        )

    if n_obs < 2:
        return _unavailable(f"Insufficient training observations (n_obs={n_obs} < 2) for EVT POT.")
    if conf < diag["threshold_quantile"] - _SNAP_TOL:
        return _unavailable(
            f"confidence {conf:g} < threshold_quantile {diag['threshold_quantile']:g}: pure POT tail "
            "inference is unavailable in the loss body; the empirical-body/GPD-tail hybrid must be "
            "requested explicitly (estimate_evt_body_tail)."
        )
    fit = fit_gpd_tail(
        losses, threshold_quantile=diag["threshold_quantile"], min_exceedances=diag["min_exceedances"]
    )
    res = pot_var_es(fit, conf)
    extra = {"fit": fit.to_record(), "a": res["a"], "region": res["region"]}
    if res["status"] == "unavailable":
        return _unavailable(str(res["reason"]), extra)
    d = dict(diag)
    d.update(extra)
    d["construction"] = "pure_pot_gpd_tail"
    d["es_status"] = "finite" if res["es_loss"] is not None else "unavailable_xi_ge_1"
    return RiskEstimate(
        model=EVT_POT_MODEL,
        confidence=conf,
        horizon_days=1,
        var_loss=res["var_loss"],
        es_loss=res["es_loss"],
        n_obs=n_obs,
        sample_start=start,
        sample_end=end,
        status=res["status"],
        reason=res["reason"],
        diagnostics=d,
    )


def estimate_evt_body_tail(
    train_asset_returns: pd.DataFrame,
    weights: pd.Series,
    *,
    confidence: float,
    seed: int | None = None,
    threshold_quantile: float = 0.95,
    min_exceedances: int = 50,
) -> RiskEstimate:
    """Explicitly labelled empirical-body / GPD-tail VaR and ES (supports 90/95/99%).

    Body-region VaR (``c < 1 - p_u``) is the empirical step-CDF quantile and is labelled BODY,
    not EVT extrapolation; ES integrates the body segment plus the fitted GPD tail. Tail-region
    results coincide with :func:`estimate_evt_pot`.
    """
    conf, _alpha, losses, diag = _estimate_common(
        train_asset_returns, weights, confidence, seed, threshold_quantile, min_exceedances,
        EVT_BODY_TAIL_MODEL,
    )
    n_obs = int(len(losses))
    start, end = _sample_bounds(losses)
    diag["construction"] = "empirical_body_gpd_tail_hybrid"
    if n_obs < 2:
        return RiskEstimate(
            model=EVT_BODY_TAIL_MODEL, confidence=conf, horizon_days=1, var_loss=None, es_loss=None,
            n_obs=n_obs, sample_start=start, sample_end=end, status="unavailable",
            reason=f"Insufficient training observations (n_obs={n_obs} < 2).", diagnostics=diag,
        )
    fit = fit_gpd_tail(
        losses, threshold_quantile=diag["threshold_quantile"], min_exceedances=diag["min_exceedances"]
    )
    diag["fit"] = fit.to_record()
    if not fit.is_usable:
        return RiskEstimate(
            model=EVT_BODY_TAIL_MODEL, confidence=conf, horizon_days=1, var_loss=None, es_loss=None,
            n_obs=n_obs, sample_start=start, sample_end=end, status="unavailable",
            reason="GPD tail fit unavailable: " + "; ".join(fit.reasons), diagnostics=diag,
        )
    res = body_tail_es(fit, conf)
    diag.update(res)
    reasons = list(fit.reasons)
    if res["region"] == "body":
        reasons.append("VaR lies in the empirical BODY (below 1 - p_u); it is not EVT extrapolation")
    status = "ok" if fit.status == "ok" else "warning"
    if res["es_loss"] is None:
        status = "warning"
        reasons.append("ES unavailable: xi >= 1 implies an infinite GPD tail mean")
    return RiskEstimate(
        model=EVT_BODY_TAIL_MODEL,
        confidence=conf,
        horizon_days=1,
        var_loss=res["var_loss"],
        es_loss=res["es_loss"],
        n_obs=n_obs,
        sample_start=start,
        sample_end=end,
        status=status,
        reason="; ".join(reasons) if reasons else None,
        diagnostics=diag,
    )


# ----------------------------------------------------------------------------------------
# Threshold diagnostics and QQ/PP data
# ----------------------------------------------------------------------------------------

THRESHOLD_DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "candidate_quantile",
    "n_obs",
    "threshold",
    "threshold_rank",
    "n_exceedances",
    "n_ties_at_threshold",
    "exceedance_fraction",
    "tail_boundary_confidence",
    "meets_min_exceedances",
    "mean_excess",
    "mean_excess_se",
    "n_unique_excesses",
    "xi",
    "beta",
    "modified_scale",
    "xi_se_asymptotic_iid",
    "beta_se_asymptotic_iid",
    "upper_support_loss",
    "loglik",
    "optimizer_converged",
    "optimizer_iterations",
    "status",
    "reason",
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
    - ``mean_excess`` (MRL) is reported whenever at least one strict exceedance exists; GPD
      parameters are fitted only when ``n_exceedances >= min_exceedances``.
    - Asymptotic standard errors assume iid exceedances (``xi > -0.5``) and are labelled as such.
    """
    if not isinstance(losses, pd.Series):
        raise TypeError(f"losses must be a pandas Series; got {type(losses).__name__}.")
    arr = _validate_loss_values(losses)
    m = _validate_min_exceedances(min_exceedances)
    if isinstance(candidate_quantiles, (str, bytes)) or len(candidate_quantiles) == 0:
        raise ValueError("candidate_quantiles must be a non-empty sequence of floats in (0, 1).")
    qs = [_validate_threshold_quantile(q) for q in candidate_quantiles]
    if len(set(qs)) != len(qs):
        raise ValueError("candidate_quantiles must be unique.")
    sorted_losses = np.sort(arr, kind="mergesort")
    rows: list[dict[str, Any]] = []
    for q in qs:
        fit = _build_fit(sorted_losses, q, m)
        rows.append(
            {
                "candidate_quantile": q,
                "n_obs": fit.n_obs,
                "threshold": fit.threshold,
                "threshold_rank": fit.threshold_rank,
                "n_exceedances": fit.n_exceedances,
                "n_ties_at_threshold": fit.n_ties_at_threshold,
                "exceedance_fraction": fit.p_u,
                "tail_boundary_confidence": fit.tail_boundary_confidence,
                "meets_min_exceedances": bool(fit.n_exceedances >= m),
                "mean_excess": fit.mean_excess,
                "mean_excess_se": fit.mean_excess_se,
                "n_unique_excesses": fit.n_unique_excesses,
                "xi": fit.xi,
                "beta": fit.beta,
                "modified_scale": fit.modified_scale,
                "xi_se_asymptotic_iid": fit.xi_se_asymptotic_iid,
                "beta_se_asymptotic_iid": fit.beta_se_asymptotic_iid,
                "upper_support_loss": fit.upper_support_loss,
                "loglik": fit.loglik,
                "optimizer_converged": fit.optimizer.get("converged"),
                "optimizer_iterations": fit.optimizer.get("iterations"),
                "status": fit.status,
                "reason": "; ".join(fit.reasons) if fit.reasons else None,
            }
        )
    df = pd.DataFrame(rows, columns=list(THRESHOLD_DIAGNOSTIC_COLUMNS))
    for col in ("mean_excess", "mean_excess_se", "xi", "beta", "modified_scale",
                "xi_se_asymptotic_iid", "beta_se_asymptotic_iid", "upper_support_loss",
                "loglik", "optimizer_converged", "optimizer_iterations", "reason"):
        df[col] = pd.Series([r[col] for r in rows], index=df.index, dtype=object)
    df.attrs.update(
        {
            "min_exceedances": m,
            "gof_p_values": "not computed (no calibrated GOF test for estimated GPD parameters)",
            "standard_error_note": "asymptotic iid inverse-Fisher SEs; ignore dependence and threshold uncertainty",
        }
    )
    return df


def gpd_qq_pp_table(fit: GPDTailFit) -> pd.DataFrame:
    """Return descriptive QQ/PP coordinates for the fitted excesses (plotting positions ``(i-0.5)/N``)."""
    xi, beta, u = _require_usable(fit)
    y = np.sort(np.asarray(fit.excesses, dtype=np.float64))
    n_exc = int(y.size)
    p = (np.arange(1, n_exc + 1, dtype=np.float64) - 0.5) / n_exc
    with np.errstate(all="ignore"):
        model_q = genpareto.ppf(p, xi, loc=0.0, scale=beta)
        model_cdf = genpareto.cdf(y, xi, loc=0.0, scale=beta)
    df = pd.DataFrame(
        {
            "rank": np.arange(1, n_exc + 1),
            "plotting_position": p,
            "empirical_excess": y,
            "model_quantile_excess": model_q,
            "empirical_loss": y + u,
            "model_quantile_loss": model_q + u,
            "model_cdf_at_empirical": model_cdf,
        }
    )
    df.attrs.update(
        {
            "threshold": u,
            "xi": xi,
            "beta": beta,
            "n_exceedances": n_exc,
            "descriptive_max_abs_pp_deviation": float(np.max(np.abs(model_cdf - p))),
            "gof_p_value": None,
            "note": "Descriptive only; no fitted-distribution GOF p-value is reported.",
        }
    )
    return df


# ----------------------------------------------------------------------------------------
# Moving-block bootstrap (cached)
# ----------------------------------------------------------------------------------------


def _risk_at(fit: GPDTailFit, conf: float) -> dict[str, Any]:
    pure = pot_var_es(fit, conf)
    if fit.is_usable:
        hyb = body_tail_es(fit, conf)
        hyb_status = "ok" if hyb["es_loss"] is not None else "warning"
        hyb_var, hyb_es, hyb_region = hyb["var_loss"], hyb["es_loss"], hyb["region"]
    else:
        hyb_status, hyb_var, hyb_es, hyb_region = "unavailable", None, None, None

    if conf >= fit.threshold_quantile - _SNAP_TOL:
        return {
            "method": "pure_pot",
            "var": pure["var_loss"],
            "es": pure["es_loss"],
            "status": pure["status"],
            "region": pure["region"],
            "reason": pure["reason"],
            "hybrid_var": hyb_var,
            "hybrid_es": hyb_es,
            "hybrid_status": hyb_status,
            "hybrid_region": hyb_region,
        }
    return {
        "method": "body_tail_hybrid",
        "var": hyb_var,
        "es": hyb_es,
        "status": hyb_status,
        "region": hyb_region,
        "reason": None if fit.is_usable else "; ".join(fit.reasons),
        "hybrid_var": hyb_var,
        "hybrid_es": hyb_es,
        "hybrid_status": hyb_status,
        "hybrid_region": hyb_region,
    }


def _percentile_summary(values: list[float], min_ok: int) -> dict[str, Any]:
    n = len(values)
    if n < min_ok:
        return {"n_finite": n, "p025": None, "median": None, "p975": None,
                "interval_status": f"unavailable: {n} finite replicates < required {min_ok}"}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "n_finite": n,
        "p025": float(np.quantile(arr, 0.025)),
        "median": float(np.quantile(arr, 0.5)),
        "p975": float(np.quantile(arr, 0.975)),
        "interval_status": "ok",
    }


def _count_labels(labels: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label in labels:
        key = "none" if label is None else str(label)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


@lru_cache(maxsize=16)
def _bootstrap_cached(
    dataset_id: str,
    exposure_id: str,
    config_hash: str,
    policy_id: str,
    losses_sha256: str,
    losses_bytes: bytes,
    confidences: tuple[float, ...],
    threshold_quantile: float,
    min_exceedances: int,
    block_length: int,
    n_replications: int,
    seed: int,
    min_successful: int,
) -> dict[str, Any]:
    arr = np.frombuffer(losses_bytes, dtype=np.float64)
    n = int(arr.size)
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block_length))
    offsets = np.arange(block_length)
    replicates: list[dict[str, Any]] = []
    for rep in range(n_replications):
        starts = rng.integers(0, n - block_length + 1, size=n_blocks)
        idx = (starts[:, None] + offsets[None, :]).ravel()[:n]
        fit = _build_fit(np.sort(arr[idx], kind="mergesort"), threshold_quantile, min_exceedances)
        rec: dict[str, Any] = {
            "replicate": rep,
            "fit_status": fit.status,
            "fit_reasons": list(fit.reasons),
            "threshold": fit.threshold,
            "n_exceedances": fit.n_exceedances,
            "n_ties_at_threshold": fit.n_ties_at_threshold,
            "p_u": fit.p_u,
            "tail_boundary_confidence": fit.tail_boundary_confidence,
            "xi": fit.xi,
            "beta": fit.beta,
            "modified_scale": fit.modified_scale,
            "risk": {},
        }
        for c in confidences:
            rec["risk"][f"{c:.4f}"] = _risk_at(fit, c)
        replicates.append(rec)

    usable = [r for r in replicates if r["fit_status"] in ("ok", "warning")]
    n_xi_ge_1_fits = sum(1 for r in usable if r["xi"] is not None and float(r["xi"]) >= 1.0)
    summary: dict[str, Any] = {
        "n_replications": n_replications,
        "n_successful_fits": len(usable),
        "n_failed_fits": n_replications - len(usable),
        "n_fits_with_xi_ge_1": n_xi_ge_1_fits,
        "failed_fit_reasons": sorted(
            {"; ".join(r["fit_reasons"]) for r in replicates if r["fit_status"] == "unavailable"}
        ),
        "xi": _percentile_summary([float(r["xi"]) for r in usable], min_successful),
        "beta": _percentile_summary([float(r["beta"]) for r in usable], min_successful),
        "modified_scale": _percentile_summary(
            [float(r["modified_scale"]) for r in usable if r["modified_scale"] is not None],
            min_successful,
        ),
        "threshold": _percentile_summary([float(r["threshold"]) for r in replicates], min_successful),
        "by_confidence": {},
    }
    for c in confidences:
        key = f"{c:.4f}"
        risks = [r["risk"][key] for r in replicates]
        var_vals = [float(x["var"]) for x in risks if x["var"] is not None]
        es_vals = [float(x["es"]) for x in risks if x["es"] is not None]
        hyb_var_vals = [float(x["hybrid_var"]) for x in risks if x["hybrid_var"] is not None]
        hyb_es_vals = [float(x["hybrid_es"]) for x in risks if x["hybrid_es"] is not None]
        n_es_inf = sum(
            1 for r, x in zip(replicates, risks)
            if x["var"] is not None and x["es"] is None and r["xi"] is not None and r["xi"] >= 1.0
        )
        n_tie_boundary_unavail = sum(
            1 for r, x in zip(replicates, risks)
            if r["fit_status"] in ("ok", "warning")
            and x["var"] is None
            and x["method"] == "pure_pot"
            and r["tail_boundary_confidence"] > c + _SNAP_TOL
        )
        summary["by_confidence"][key] = {
            "confidence": c,
            "method": risks[0]["method"] if risks else None,
            "n_var_available": len(var_vals),
            "n_var_unavailable": n_replications - len(var_vals),
            "n_var_unavailable_resample_tie_below_tail_boundary": n_tie_boundary_unavail,
            "n_es_finite": len(es_vals),
            "n_es_unavailable_infinite_xi_ge_1": n_es_inf,
            "n_es_unavailable_other": n_replications - len(es_vals) - n_es_inf,
            "regions": _count_labels([x["region"] for x in risks]),
            "var": _percentile_summary(var_vals, min_successful),
            "es": _percentile_summary(es_vals, min_successful),
            "body_tail_hybrid": {
                "n_var_available": len(hyb_var_vals),
                "n_es_finite": len(hyb_es_vals),
                "n_es_unavailable_infinite_xi_ge_1": sum(
                    1 for r, x in zip(replicates, risks)
                    if x["hybrid_var"] is not None and x["hybrid_es"] is None
                    and r["xi"] is not None and r["xi"] >= 1.0
                ),
                "regions": _count_labels([x["hybrid_region"] for x in risks]),
                "var": _percentile_summary(hyb_var_vals, min_successful),
                "es": _percentile_summary(hyb_es_vals, min_successful),
            },
        }
    return {
        "cache_key": {
            "dataset_id": dataset_id,
            "exposure_id": exposure_id,
            "config_hash": config_hash,
            "policy_id": policy_id,
            "losses_sha256": losses_sha256,
            "n_obs": n,
            "confidences": list(confidences),
            "threshold_quantile": threshold_quantile,
            "min_exceedances": min_exceedances,
            "block_length": block_length,
            "n_replications": n_replications,
            "seed": seed,
            "min_successful_replications": min_successful,
        },
        "method": (
            "moving-block bootstrap: ceil(n/b) blocks of length b with uniform start positions "
            "0..n-b drawn by numpy PCG64 default_rng(seed), concatenated and truncated to n; each "
            "resample re-estimates the empirical threshold under the FIXED quantile policy and "
            "refits the GPD independently"
        ),
        "threshold_policy": f"fixed quantile policy q={threshold_quantile:g}; u re-estimated per resample",
        "interval": "percentile 2.5% / 97.5% of finite replicate values",
        "interpretation": (
            "Conditional on the threshold policy and the block-dependence assumption; does not "
            "capture threshold-selection uncertainty or regime change."
        ),
        "summary": summary,
        "replicates": replicates,
    }


def bootstrap_evt_tail_uncertainty(
    losses: pd.Series | np.ndarray | Sequence[float],
    *,
    confidences: Sequence[float] = (0.90, 0.95, 0.99),
    threshold_quantile: float = 0.95,
    min_exceedances: int = 50,
    block_length: int = 10,
    n_replications: int = 100,
    seed: int = 202602,
    min_successful_replications: int | None = None,
    dataset_id: str = "unspecified",
    exposure_id: str = "unspecified",
    config_hash: str = "unspecified",
    policy_id: str = "provisional_q95_min50",
) -> dict[str, Any]:
    """Bounded, deterministic, cached moving-block bootstrap of POT-GPD tail risk.

    Confidences ``>= threshold_quantile`` use pure POT; lower confidences use the labelled
    body/tail hybrid (hybrid summaries are also recorded at every confidence so boundary-tie
    effects on pure POT at ``c = threshold_quantile`` can be compared directly). Intervals are
    reported only when at least ``min_successful_replications`` (default
    ``ceil(0.8 * n_replications)``) finite replicate values exist. Results are cached by
    (dataset/exposure/config/policy IDs, loss-bytes SHA-256, confidences, block length,
    replications, seed, minimum); a deep copy is returned so callers cannot mutate the cache.
    """
    arr = _validate_loss_values(losses)
    q = _validate_threshold_quantile(threshold_quantile)
    m = _validate_min_exceedances(min_exceedances)
    n = int(arr.size)
    if isinstance(block_length, bool) or not isinstance(block_length, (int, np.integer)):
        raise TypeError("block_length must be an integer.")
    if not (1 <= int(block_length) <= n):
        raise ValueError(f"block_length must lie in [1, n={n}]; got {block_length}.")
    if isinstance(n_replications, bool) or not isinstance(n_replications, (int, np.integer)):
        raise TypeError("n_replications must be an integer.")
    if not (1 <= int(n_replications) <= _MAX_BOOTSTRAP_REPLICATIONS):
        raise ValueError(
            f"n_replications must lie in [1, {_MAX_BOOTSTRAP_REPLICATIONS}] (bounded); got {n_replications}."
        )
    seed_clean = _validate_seed(seed)
    if seed_clean is None:
        raise TypeError("seed must be an explicit integer for a reproducible bootstrap.")
    if min_successful_replications is None:
        min_ok = int(math.ceil(0.8 * int(n_replications)))
    else:
        if isinstance(min_successful_replications, bool) or not isinstance(
            min_successful_replications, (int, np.integer)
        ):
            raise TypeError("min_successful_replications must be an integer or None.")
        min_ok = int(min_successful_replications)
        if not (1 <= min_ok <= int(n_replications)):
            raise ValueError("min_successful_replications must lie in [1, n_replications].")
    confs = tuple(_validate_confidence(c)[0] for c in confidences)
    if len(confs) == 0 or len(set(confs)) != len(confs):
        raise ValueError("confidences must be a non-empty sequence of unique values.")
    data = np.ascontiguousarray(arr, dtype=np.float64).tobytes()
    digest = hashlib.sha256(data).hexdigest()
    result = _bootstrap_cached(
        str(dataset_id),
        str(exposure_id),
        str(config_hash),
        str(policy_id),
        digest,
        data,
        confs,
        q,
        m,
        int(block_length),
        int(n_replications),
        seed_clean,
        min_ok,
    )
    return copy.deepcopy(result)
