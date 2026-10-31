"""Point-in-time Value-at-Risk (VaR) estimation, normal moments helper, and model registry (SOLO STEP 5 / C1).

Public interfaces frozen in D0 for SOLO STEP 5 (C1) and SOLO STEP 7 (C2/C3):
- ``normal_moments(asset_returns) -> tuple[pd.Series, pd.DataFrame]``
- ``estimate_risk(train_asset_returns, weights, *, model, confidence, seed=None) -> RiskEstimate``
- ``get_risk_forecaster(model) -> RiskForecastFn``

Supporting C1 diagnostic, simulation-uncertainty, window-policy, and comparison helpers:
- ``resolve_risk_runtime_settings(config=None, *, seed=None, n_simulations=None) -> dict[str, Any]``
- ``quantify_monte_carlo_uncertainty(train_asset_returns, weights, *, confidence, base_seed=None, n_replications=64, n_simulations=None) -> dict[str, Any]``
- ``describe_window_crisis_coverage(sample_start, sample_end, historical_scenarios=None) -> dict[str, Any]``
- ``compute_fixed_exposure_loss_diagnostics(train_asset_returns, weights, *, portfolio_id="portfolio") -> dict[str, Any]``
- ``compare_risk_models_table(train_asset_returns, weights, *, confidences=..., models=..., seed=None, nav_usd=..., window_id="custom", portfolio_id="portfolio", historical_scenarios=None) -> pd.DataFrame``
- ``build_development_c1_risk_bundle(asset_returns, config) -> dict[str, Any]``

Conventions (SOLO STEP 5 / C1):
- Simple portfolio returns for a fixed exposure ``w`` are ``R_{p,t} = (train_asset_returns @ w)_t``
  and one-day losses before transaction costs are ``L_t = -R_{p,t}``. Positive risk values
  represent losses; nonpositive loss quantiles are preserved without ``abs()`` or zero flooring.
- Simple-return modelling exception: asset simple returns aggregate linearly across portfolio
  holdings (``R_{p,t} = sum_i w_i R_{i,t}``), whereas log returns do not. All committee risk
  models therefore operate on 1-day simple portfolio losses ``L_t = -R_{p,t}``, while log
  returns ``log1p(R_{p,t})`` are inspected in stationarity diagnostics. Under the parametric
  and Monte Carlo normal models, ``R_t ~ N(mu, Sigma)`` is an unbounded continuous
  approximation on ``(-inf, +inf)`` (draws are never truncated at ``-100%``).
- Shared normal moments: ``normal_moments`` computes arithmetic sample mean and sample
  covariance with ``ddof=1``, reused identically by ``parametric_normal``,
  ``monte_carlo_normal``, and Step 8 (``B2``) normal Euler risk contributions.
- Historical VaR & ES: Historical VaR uses the empirical step-CDF quantile
  ``VaR_c = F_n^{-1}(c) = L_{(ceil(n * c))}`` (``method="inverted_cdf"``), and Historical ES
  equals ``float(empirical_tail_weights(losses, c) @ losses)``, integrating the exact worst
  ``alpha = 1 - c`` empirical probability mass with fractional boundary mass and equal splitting
  across boundary ties.
- Monte Carlo Normal VaR & ES: draws ``M = config.risk.monte_carlo_simulations`` (``25,000``)
  multivariate normal 7-ETF return vectors from ``N(mean_series, covariance_frame)`` using a
  deterministic PCG64 generator seeded with ``seed`` (defaulting to ``config.seeds.monte_carlo = 202601``),
  projects ``L_sim = -(R_sim @ w)``, and evaluates ``empirical_var_and_es`` on ``L_sim``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
import hashlib
import json
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm as scipy_norm, skew as scipy_skew, kurtosis as scipy_kurtosis

from quantedge.config import AppConfig, DEFAULT_CONFIG_PATH, load_config
from quantedge.contracts import (
    CANONICAL_TICKERS,
    CORE_RISK_MODELS,
    MANDATE_NAV_USD,
    MANDATORY_COMPARISON_CONFIDENCES,
    RiskEstimate,
    RiskForecastFn,
    SUPPORTED_CONFIDENCE_LEVELS,
    StressScenarioSpec,
)
from quantedge.es import _validate_confidence, empirical_tail_weights, empirical_var_and_es
from quantedge import evt
from quantedge.kpis import run_portfolio_return_stationarity_diagnostics
from quantedge.portfolio import build_portfolio_path, construct_weights, make_core_strategy_specs

SUPPORTED_C1_RISK_MODELS: tuple[str, ...] = (
    "historical",
    "parametric_normal",
    "monte_carlo_normal",
)

_COV_SYMMETRY_TOL: float = 1e-10
_COV_PSD_EIG_TOL: float = 1e-10
_ZERO_VOL_TOL: float = 1e-15
_WEIGHT_SUM_TOL: float = 1e-6


@lru_cache(maxsize=1)
def _load_default_app_config() -> AppConfig:
    """Load and cache the repository baseline ``config.yaml`` once for default risk settings."""
    return load_config(DEFAULT_CONFIG_PATH)


def resolve_risk_runtime_settings(
    config: AppConfig | None = None,
    *,
    seed: int | None = None,
    n_simulations: int | None = None,
) -> dict[str, Any]:
    """Resolve risk horizon, ddof, Monte Carlo draw count, and seed from ``config.yaml``."""
    cfg = config if config is not None else _load_default_app_config()
    horizon_days = int(cfg.risk.horizon_days)
    if horizon_days != 1:
        raise ValueError(f"Only 1-day risk horizon (horizon_days=1) is supported; got {horizon_days!r}.")
    normal_ddof = int(cfg.risk.normal_ddof)
    if normal_ddof != 1:
        raise ValueError(f"Only normal_ddof=1 is supported in C1 contracts; got {normal_ddof!r}.")
    nav_usd = float(cfg.mandate.nav_usd)
    if not math.isfinite(nav_usd) or nav_usd <= 0.0:
        raise ValueError(f"mandate.nav_usd must be finite and > 0; got {nav_usd!r}.")

    if seed is not None:
        if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
            raise TypeError(f"seed must be an integer or None; got {type(seed).__name__}.")
        effective_seed = int(seed)
        seed_source = "caller_explicit_seed"
    else:
        if isinstance(cfg.seeds.monte_carlo, bool) or not isinstance(
            cfg.seeds.monte_carlo, (int, np.integer)
        ):
            raise TypeError("config.seeds.monte_carlo must be an integer.")
        effective_seed = int(cfg.seeds.monte_carlo)
        seed_source = "config.seeds.monte_carlo"

    if n_simulations is not None:
        if (
            isinstance(n_simulations, bool)
            or not isinstance(n_simulations, (int, np.integer))
            or int(n_simulations) < 1
        ):
            raise ValueError(f"n_simulations must be a positive integer; got {n_simulations!r}.")
        effective_sims = int(n_simulations)
        sims_source = "caller_explicit_n_simulations"
    else:
        if (
            isinstance(cfg.risk.monte_carlo_simulations, bool)
            or not isinstance(cfg.risk.monte_carlo_simulations, (int, np.integer))
            or int(cfg.risk.monte_carlo_simulations) < 1
        ):
            raise ValueError(
                f"config.risk.monte_carlo_simulations must be a positive integer; "
                f"got {cfg.risk.monte_carlo_simulations!r}."
            )
        effective_sims = int(cfg.risk.monte_carlo_simulations)
        sims_source = "config.risk.monte_carlo_simulations"

    return {
        "horizon_days": horizon_days,
        "normal_ddof": normal_ddof,
        "monte_carlo_simulations": effective_sims,
        "monte_carlo_simulations_source": sims_source,
        "monte_carlo_seed": effective_seed,
        "monte_carlo_seed_source": seed_source,
        "dashboard_risk_window_days": int(cfg.risk.dashboard_risk_window_days),
        "backtest_window_days": int(cfg.risk.backtest_window_days),
        "nav_usd": nav_usd,
        "config_hash": str(cfg.config_hash),
    }


def _validate_asset_return_frame(
    asset_returns: pd.DataFrame,
    *,
    min_rows: int,
    context: str = "asset_returns",
) -> np.ndarray:
    """Validate canonical 7-ETF columns, ascending unique DatetimeIndex, and finite float values."""
    if not isinstance(asset_returns, pd.DataFrame):
        raise TypeError(f"{context} must be a pandas DataFrame; got {type(asset_returns).__name__}.")
    if tuple(asset_returns.columns) != CANONICAL_TICKERS:
        raise ValueError(
            f"{context} columns must match exact canonical order {CANONICAL_TICKERS}; "
            f"got {tuple(asset_returns.columns)}."
        )
    if not isinstance(asset_returns.index, pd.DatetimeIndex):
        raise ValueError(
            f"{context} must have a pandas DatetimeIndex; got {type(asset_returns.index).__name__}."
        )
    if not asset_returns.index.is_monotonic_increasing or not asset_returns.index.is_unique:
        raise ValueError(f"{context} DatetimeIndex must be strictly ascending and unique.")
    if len(asset_returns) < min_rows:
        raise ValueError(
            f"{context} requires at least {min_rows} observations; got {len(asset_returns)}."
        )
    if len(asset_returns) == 0:
        return np.empty((0, len(CANONICAL_TICKERS)), dtype=np.float64)

    try:
        arr = np.array(
            asset_returns.loc[:, list(CANONICAL_TICKERS)].to_numpy(dtype=np.float64),
            dtype=np.float64,
            copy=True,
            order="C",
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must contain numeric float-convertible return values.") from exc

    if not np.isfinite(arr).all():
        raise ValueError(f"{context} contains NaN or non-finite (+/-inf) return values.")
    return arr


def _validate_portfolio_weights(weights: pd.Series) -> np.ndarray:
    """Validate canonical 7-ETF weight vector without silent reindexing, clipping, or renormalization."""
    if not isinstance(weights, pd.Series):
        raise TypeError(f"weights must be a pandas Series; got {type(weights).__name__}.")
    if len(weights) != len(CANONICAL_TICKERS) or tuple(weights.index) != CANONICAL_TICKERS:
        raise ValueError(
            f"weights index must match exact canonical ticker order {CANONICAL_TICKERS}; "
            f"got {tuple(weights.index)}."
        )
    try:
        w_arr = np.ascontiguousarray(weights.to_numpy(dtype=np.float64), dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("weights must contain numeric float-convertible values.") from exc

    if not np.isfinite(w_arr).all():
        raise ValueError("weights contains NaN or non-finite (+/-inf) values.")

    weight_sum = float(np.sum(w_arr, dtype=np.float64))
    if abs(weight_sum - 1.0) > _WEIGHT_SUM_TOL:
        raise ValueError(
            f"weights must sum to 1.0 within {_WEIGHT_SUM_TOL:g} (never silently renormalized); "
            f"got sum={weight_sum:.12f}."
        )
    return w_arr


def normal_moments(
    asset_returns: pd.DataFrame,
) -> tuple[pd.Series, pd.DataFrame]:
    """Compute shared arithmetic sample mean and sample covariance (``ddof=1``).

    Frozen D0 contract (``CONTRACTS.md``):
    - ``mean_series``: arithmetic sample mean across rows of ``asset_returns`` indexed by
      ``CANONICAL_TICKERS``.
    - ``covariance_frame``: unbiased sample covariance matrix across columns with ``ddof=1``
      on ``CANONICAL_TICKERS x CANONICAL_TICKERS``.
    - Validates canonical ticker order, ascending unique ``DatetimeIndex``, ``n_obs >= 2``,
      finite numeric observations, matrix symmetry, and positive semi-definiteness (PSD).
    - Reused identically across ``parametric_normal``, ``monte_carlo_normal``, and
      Step 8 (``B2``) normal Euler risk-contribution calculations so total risk and
      component sums agree.
    """
    arr = _validate_asset_return_frame(asset_returns, min_rows=2, context="asset_returns")
    n_obs = int(arr.shape[0])

    mean_arr = np.mean(arr, axis=0, dtype=np.float64)
    centered = arr - mean_arr[None, :]
    cov_raw = (centered.T @ centered) / float(n_obs - 1)

    if not (np.isfinite(mean_arr).all() and np.isfinite(cov_raw).all()):
        raise ValueError("Computed sample mean or covariance contains non-finite values.")

    scale = max(1.0, float(np.max(np.abs(cov_raw))))
    max_asym = float(np.max(np.abs(cov_raw - cov_raw.T)))
    if max_asym > _COV_SYMMETRY_TOL * scale:
        raise ValueError(
            f"Sample covariance matrix is materially asymmetric: max |Sigma - Sigma^T| = {max_asym:.3e}."
        )
    cov_sym = 0.5 * (cov_raw + cov_raw.T)

    diag = np.diag(cov_sym)
    if bool(np.any(diag < -1e-12 * scale)):
        raise ValueError(
            f"Sample covariance diagonal contains negative variance: min_diag={float(np.min(diag)):.3e}."
        )

    eigvals = np.linalg.eigvalsh(cov_sym)
    min_eig = float(np.min(eigvals))
    max_eig = float(np.max(eigvals))
    if min_eig < -_COV_PSD_EIG_TOL * scale:
        raise ValueError(
            f"Sample covariance matrix is not positive semi-definite: min_eigenvalue={min_eig:.3e}."
        )

    zero_var_tickers = tuple(
        CANONICAL_TICKERS[i] for i in range(len(CANONICAL_TICKERS)) if float(diag[i]) <= _ZERO_VOL_TOL**2
    )
    rank_deficient = bool(min_eig <= max(1e-15, _ZERO_VOL_TOL * max(1.0, max_eig)))

    sample_start = str(asset_returns.index[0].date())
    sample_end = str(asset_returns.index[-1].date())
    attrs = {
        "n_obs": n_obs,
        "sample_start": sample_start,
        "sample_end": sample_end,
        "ddof": 1,
        "estimator": "sample_ddof1",
        "min_eigenvalue": min_eig,
        "max_eigenvalue": max_eig,
        "max_asymmetry": max_asym,
        "trace": float(np.trace(cov_sym)),
        "zero_variance_tickers": zero_var_tickers,
        "rank_deficient": rank_deficient,
    }

    mean_series = pd.Series(mean_arr, index=list(CANONICAL_TICKERS), name="mean_return", dtype=float)
    mean_series.attrs.update(attrs)

    covariance_frame = pd.DataFrame(
        cov_sym,
        index=list(CANONICAL_TICKERS),
        columns=list(CANONICAL_TICKERS),
        dtype=float,
    )
    covariance_frame.attrs.update(attrs)
    return mean_series, covariance_frame


@lru_cache(maxsize=32)
def _simulate_multivariate_normal_returns_cached(
    moments_digest: str,
    mean_bytes: bytes,
    cov_bytes: bytes,
    seed: int,
    n_simulations: int,
) -> np.ndarray:
    """Deterministically simulate and cache ``(n_simulations, 7)`` multivariate normal asset returns.

    Uses eigendecomposition ``Sigma = V diag(max(lambda, 0)) V^T`` with NumPy's PCG64
    ``default_rng(seed)`` so even rank-deficient PSD covariance matrices are simulated
    without ``LinAlgError`` or ``RuntimeWarning``. The returned array is marked read-only
    so cached draws cannot be mutated by callers.
    """
    _ = moments_digest  # part of cache key for readability
    n_assets = len(CANONICAL_TICKERS)
    mean_arr = np.frombuffer(mean_bytes, dtype=np.float64).reshape(n_assets)
    cov_arr = np.frombuffer(cov_bytes, dtype=np.float64).reshape((n_assets, n_assets))

    eigvals, eigvecs = np.linalg.eigh(cov_arr)
    clipped_eigs = np.maximum(eigvals, 0.0)
    factor = eigvecs * np.sqrt(clipped_eigs)[None, :]

    rng = np.random.default_rng(int(seed))
    z_draws = rng.standard_normal((int(n_simulations), n_assets), dtype=np.float64)
    sim_returns = mean_arr[None, :] + (z_draws @ factor.T)
    sim_returns.setflags(write=False)
    return sim_returns


def _simulate_multivariate_normal_returns(
    mean_series: pd.Series,
    covariance_frame: pd.DataFrame,
    *,
    seed: int,
    n_simulations: int,
) -> np.ndarray:
    """Wrapper converting ``(mean_series, covariance_frame)`` to hashable bytes for cached simulation."""
    mean_arr = np.ascontiguousarray(mean_series.to_numpy(dtype=np.float64), dtype=np.float64)
    cov_arr = np.ascontiguousarray(covariance_frame.to_numpy(dtype=np.float64), dtype=np.float64)
    mean_bytes = mean_arr.tobytes()
    cov_bytes = cov_arr.tobytes()
    digest = hashlib.sha256(mean_bytes + cov_bytes).hexdigest()[:16]
    return _simulate_multivariate_normal_returns_cached(
        digest,
        mean_bytes,
        cov_bytes,
        int(seed),
        int(n_simulations),
    )


def _compute_loss_sample_summary(losses_arr: np.ndarray) -> dict[str, Any]:
    """Compute sample mean, std (ddof=1), skewness, excess kurtosis, and range on 1-day losses."""
    n_obs = int(len(losses_arr))
    loss_mean = float(np.mean(losses_arr, dtype=np.float64))
    loss_std = float(np.std(losses_arr, ddof=1, dtype=np.float64)) if n_obs >= 2 else 0.0
    min_loss = float(np.min(losses_arr))
    max_loss = float(np.max(losses_arr))
    if n_obs >= 3 and loss_std > _ZERO_VOL_TOL:
        loss_skew = float(scipy_skew(losses_arr, bias=False))
    else:
        loss_skew = 0.0
    if n_obs >= 4 and loss_std > _ZERO_VOL_TOL:
        loss_ex_kurt = float(scipy_kurtosis(losses_arr, fisher=True, bias=False))
    else:
        loss_ex_kurt = 0.0

    return {
        "sample_loss_mean": loss_mean,
        "sample_return_mean": float(-loss_mean),
        "sample_loss_std_ddof1": loss_std,
        "sample_loss_skewness": loss_skew,
        "sample_return_skewness": float(-loss_skew),
        "sample_loss_excess_kurtosis": loss_ex_kurt,
        "sample_min_loss": min_loss,
        "sample_max_loss": max_loss,
        "sample_min_simple_return": float(-max_loss),
        "sample_max_simple_return": float(-min_loss),
    }


def _analytic_normal_var_es_from_moments(
    mu_p: float,
    sigma_p: float,
    confidence: float,
    alpha: float,
) -> tuple[float, float, float, float, float]:
    """Compute closed-form normal VaR and ES from portfolio simple-return ``(mu_p, sigma_p)``."""
    z_c = float(scipy_norm.ppf(confidence))
    phi_z = float(scipy_norm.pdf(z_c))
    es_mult = phi_z / alpha
    if sigma_p <= _ZERO_VOL_TOL:
        return float(-mu_p), float(-mu_p), z_c, phi_z, es_mult
    var_loss = float(-mu_p + sigma_p * z_c)
    es_loss = float(-mu_p + sigma_p * es_mult)
    if es_loss < var_loss and (var_loss - es_loss) <= 1e-15 * max(1.0, abs(var_loss)):
        es_loss = var_loss
    return var_loss, es_loss, z_c, phi_z, es_mult


def _estimate_risk_with_settings(
    train_asset_returns: pd.DataFrame,
    weights: pd.Series,
    *,
    model: str,
    confidence: float,
    seed: int | None = None,
    config: AppConfig | None = None,
    n_simulations: int | None = None,
) -> RiskEstimate:
    """Internal risk engine routing a single coherent resolved configuration (`R1`)."""
    if not isinstance(model, str) or model not in CORE_RISK_MODELS:
        raise ValueError(
            f"Unsupported risk model {model!r}; expected one of {CORE_RISK_MODELS}."
        )
    conf, alpha = _validate_confidence(confidence)
    w_arr = _validate_portfolio_weights(weights)

    if model == "evt_pot":
        # EVT POT is scheduled for SOLO STEP 7 (C2/C3) and must not return fabricated C1 results.
        return evt.estimate_evt_pot(
            train_asset_returns,
            weights,
            confidence=conf,
            seed=seed,
        )

    settings = resolve_risk_runtime_settings(
        config,
        seed=seed,
        n_simulations=n_simulations,
    )
    horizon_days = int(settings["horizon_days"])
    nav_usd = float(settings["nav_usd"])

    # Validate DataFrame structure (allowing 0 or 1 rows to return status='unavailable' cleanly)
    x_arr = _validate_asset_return_frame(
        train_asset_returns,
        min_rows=0,
        context="train_asset_returns",
    )
    n_obs = int(x_arr.shape[0])
    sample_start = str(train_asset_returns.index[0].date()) if n_obs > 0 else None
    sample_end = str(train_asset_returns.index[-1].date()) if n_obs > 0 else None

    weight_dict = {ticker: float(w_arr[i]) for i, ticker in enumerate(CANONICAL_TICKERS)}
    base_diagnostics: dict[str, Any] = {
        "model": model,
        "confidence": conf,
        "alpha": alpha,
        "is_supported_sidebar_confidence": bool(
            any(abs(conf - c) <= 1e-9 for c in SUPPORTED_CONFIDENCE_LEVELS)
        ),
        "is_mandatory_comparison_confidence": bool(
            any(abs(conf - c) <= 1e-9 for c in MANDATORY_COMPARISON_CONFIDENCES)
        ),
        "horizon_days": horizon_days,
        "units": "fraction_of_portfolio_nav",
        "nav_usd": nav_usd,
        "loss_convention": "L_t = -(train_asset_returns @ weights)_t; positive values are 1-day pre-cost losses",
        "simple_return_aggregation_note": (
            "Cross-asset portfolio returns aggregate linearly in simple returns "
            "(R_{p,t} = sum_i w_i R_{i,t}); log returns are not additive across assets."
        ),
        "n_obs": n_obs,
        "sample_start": sample_start,
        "sample_end": sample_end,
        "weights": weight_dict,
        "config_hash": settings["config_hash"],
    }

    if n_obs < 2:
        return RiskEstimate(
            model=model,
            confidence=conf,
            horizon_days=horizon_days,
            var_loss=None,
            es_loss=None,
            n_obs=n_obs,
            sample_start=sample_start,
            sample_end=sample_end,
            status="unavailable",
            reason=(
                f"Insufficient training observations (n_obs={n_obs} < 2) for 1-day "
                f"{model} VaR/ES estimation."
            ),
            diagnostics=base_diagnostics,
        )

    port_returns_arr = np.ascontiguousarray(x_arr @ w_arr, dtype=np.float64)
    losses_arr = np.ascontiguousarray(-port_returns_arr, dtype=np.float64)
    losses_series = pd.Series(
        losses_arr,
        index=train_asset_returns.index,
        name="portfolio_loss",
        dtype=float,
    )
    loss_summary = _compute_loss_sample_summary(losses_arr)
    base_diagnostics.update(loss_summary)

    # ------------------------------------------------------------------
    # 1. Historical Simulation (empirical step-CDF quantile + tail integral)
    # ------------------------------------------------------------------
    if model == "historical":
        var_loss, es_loss, _tail_w, emp_diag = empirical_var_and_es(losses_series, conf)
        zero_vol = bool(
            loss_summary["sample_loss_std_ddof1"] <= _ZERO_VOL_TOL
            or float(np.ptp(losses_arr)) <= _ZERO_VOL_TOL
        )
        nonpositive_q = bool(var_loss <= 0.0 or es_loss <= 0.0)
        diag = dict(base_diagnostics)
        diag.update(emp_diag)
        diag.update(
            {
                "zero_portfolio_volatility": zero_vol,
                "nonpositive_loss_quantile": nonpositive_q,
                "var_usd": float(var_loss * nav_usd),
                "es_usd": float(es_loss * nav_usd),
                "es_minus_var": float(es_loss - var_loss),
                "loss_sign_note": (
                    "Nonpositive loss quantile preserved without abs() or zero flooring (tail quantile corresponds to a net gain)."
                    if nonpositive_q
                    else "Positive loss quantile represents a 1-day fractional portfolio loss."
                ),
            }
        )
        if zero_vol:
            return RiskEstimate(
                model=model,
                confidence=conf,
                horizon_days=horizon_days,
                var_loss=var_loss,
                es_loss=es_loss,
                n_obs=n_obs,
                sample_start=sample_start,
                sample_end=sample_end,
                status="warning",
                reason=(
                    "Degenerate zero portfolio volatility (sigma_p = 0.0); "
                    "historical VaR and ES collapse to deterministic loss -mu_p."
                ),
                diagnostics=diag,
            )
        return RiskEstimate(
            model=model,
            confidence=conf,
            horizon_days=horizon_days,
            var_loss=var_loss,
            es_loss=es_loss,
            n_obs=n_obs,
            sample_start=sample_start,
            sample_end=sample_end,
            status="ok",
            reason=None,
            diagnostics=diag,
        )

    # ------------------------------------------------------------------
    # Shared asset moments (ddof=1) for Parametric Normal & Monte Carlo Normal
    # ------------------------------------------------------------------
    mean_series, cov_frame = normal_moments(train_asset_returns)
    mean_arr = mean_series.to_numpy(dtype=np.float64)
    cov_arr = cov_frame.to_numpy(dtype=np.float64)

    mu_p = float(np.dot(w_arr, mean_arr))
    var_p_raw = float(w_arr @ cov_arr @ w_arr)
    cov_scale = max(1.0, float(np.max(np.abs(cov_arr))))
    if var_p_raw < -1e-12 * cov_scale:
        raise ValueError(
            f"Materially negative portfolio variance w^T Sigma w = {var_p_raw:.3e}."
        )
    var_p = 0.0 if var_p_raw <= 0.0 else var_p_raw
    sigma_p = math.sqrt(var_p)
    zero_vol = bool(sigma_p <= _ZERO_VOL_TOL)

    analytic_var, analytic_es, z_c, phi_z, es_mult = _analytic_normal_var_es_from_moments(
        mu_p, sigma_p, conf, alpha
    )

    normal_common_diag = {
        "normal_ddof": 1,
        "portfolio_mu_daily": mu_p,
        "portfolio_variance_daily": var_p,
        "portfolio_sigma_daily": sigma_p,
        "z_c": z_c,
        "phi_z_c": phi_z,
        "normal_es_sigma_multiplier": es_mult,
        "zero_portfolio_volatility": zero_vol,
        "zero_variance_tickers": cov_frame.attrs.get("zero_variance_tickers", ()),
        "covariance_rank_deficient": bool(cov_frame.attrs.get("rank_deficient", False)),
        "covariance_min_eigenvalue": float(cov_frame.attrs.get("min_eigenvalue", 0.0)),
        "unbounded_simple_return_approximation": (
            "Gaussian simple-return model R_p ~ N(mu_p, sigma_p^2) has unbounded support "
            "(-inf, +inf); draws/quantiles are never truncated at -100% simple return."
        ),
    }

    # ------------------------------------------------------------------
    # 2. Parametric Normal (closed-form Gaussian VaR & ES)
    # ------------------------------------------------------------------
    if model == "parametric_normal":
        nonpositive_q = bool(analytic_var <= 0.0 or analytic_es <= 0.0)
        diag = dict(base_diagnostics)
        diag.update(normal_common_diag)
        diag.update(
            {
                "nonpositive_loss_quantile": nonpositive_q,
                "var_usd": float(analytic_var * nav_usd),
                "es_usd": float(analytic_es * nav_usd),
                "es_minus_var": float(analytic_es - analytic_var),
                "loss_sign_note": (
                    "Nonpositive loss quantile preserved without abs() or zero flooring (tail quantile corresponds to a net gain)."
                    if nonpositive_q
                    else "Positive loss quantile represents a 1-day fractional portfolio loss."
                ),
            }
        )
        if zero_vol:
            return RiskEstimate(
                model=model,
                confidence=conf,
                horizon_days=horizon_days,
                var_loss=analytic_var,
                es_loss=analytic_es,
                n_obs=n_obs,
                sample_start=sample_start,
                sample_end=sample_end,
                status="warning",
                reason=(
                    "Degenerate zero portfolio volatility (sigma_p = 0.0); "
                    "parametric normal VaR and ES collapse to deterministic loss -mu_p."
                ),
                diagnostics=diag,
            )
        return RiskEstimate(
            model=model,
            confidence=conf,
            horizon_days=horizon_days,
            var_loss=analytic_var,
            es_loss=analytic_es,
            n_obs=n_obs,
            sample_start=sample_start,
            sample_end=sample_end,
            status="ok",
            reason=None,
            diagnostics=diag,
        )

    # ------------------------------------------------------------------
    # 3. Monte Carlo Normal (seeded 25,000 multivariate normal draws)
    # ------------------------------------------------------------------
    effective_seed = int(settings["monte_carlo_seed"])
    n_simulations = int(settings["monte_carlo_simulations"])
    asymp_var_se = (
        float(sigma_p * math.sqrt(conf * alpha / (float(n_simulations) * (phi_z**2))))
        if sigma_p > _ZERO_VOL_TOL and phi_z > 0.0
        else 0.0
    )

    if zero_vol:
        mc_var = analytic_var
        mc_es = analytic_es
        sim_loss_mean = float(-mu_p)
        sim_loss_std = 0.0
        mc_emp_diag: dict[str, Any] = {
            "var_quantile_method": "inverted_cdf",
            "expected_tail_obs_m": float(n_simulations) * alpha,
        }
    else:
        sim_asset_returns = _simulate_multivariate_normal_returns(
            mean_series,
            cov_frame,
            seed=effective_seed,
            n_simulations=n_simulations,
        )
        sim_port_returns = np.ascontiguousarray(sim_asset_returns @ w_arr, dtype=np.float64)
        sim_losses = np.ascontiguousarray(-sim_port_returns, dtype=np.float64)
        sim_loss_mean = float(np.mean(sim_losses, dtype=np.float64))
        sim_loss_std = float(np.std(sim_losses, ddof=1, dtype=np.float64))
        mc_var, mc_es, _, mc_emp_diag = empirical_var_and_es(
            pd.Series(sim_losses, name="simulated_portfolio_loss", dtype=float),
            conf,
        )

    nonpositive_q = bool(mc_var <= 0.0 or mc_es <= 0.0)
    diag = dict(base_diagnostics)
    diag.update(normal_common_diag)
    diag.update(
        {
            "seed": effective_seed,
            "seed_source": settings["monte_carlo_seed_source"],
            "monte_carlo_simulations": n_simulations,
            "monte_carlo_simulations_source": settings["monte_carlo_simulations_source"],
            "simulation_method": (
                "multivariate_normal_eigh_projection: R_sim ~ N_7(mean_series, covariance_frame) "
                "via PCG64 default_rng(seed), projected as L_sim = -(R_sim @ weights)"
            ),
            "simulated_loss_mean": sim_loss_mean,
            "simulated_loss_std_ddof1": sim_loss_std,
            "simulated_tail_obs_m": float(mc_emp_diag.get("expected_tail_obs_m", n_simulations * alpha)),
            "var_quantile_method": str(mc_emp_diag.get("var_quantile_method", "inverted_cdf")),
            "analytic_normal_var_loss": analytic_var,
            "analytic_normal_es_loss": analytic_es,
            "mc_minus_analytic_var": float(mc_var - analytic_var),
            "mc_minus_analytic_es": float(mc_es - analytic_es),
            "asymptotic_single_seed_var_se": asymp_var_se,
            "nonpositive_loss_quantile": nonpositive_q,
            "var_usd": float(mc_var * nav_usd),
            "es_usd": float(mc_es * nav_usd),
            "es_minus_var": float(mc_es - mc_var),
            "loss_sign_note": (
                "Nonpositive loss quantile preserved without abs() or zero flooring (tail quantile corresponds to a net gain)."
                if nonpositive_q
                else "Positive loss quantile represents a 1-day fractional portfolio loss."
            ),
        }
    )
    if zero_vol:
        return RiskEstimate(
            model=model,
            confidence=conf,
            horizon_days=horizon_days,
            var_loss=mc_var,
            es_loss=mc_es,
            n_obs=n_obs,
            sample_start=sample_start,
            sample_end=sample_end,
            status="warning",
            reason=(
                "Degenerate zero portfolio volatility (sigma_p = 0.0); "
                "Monte Carlo normal VaR and ES collapse to deterministic loss -mu_p."
            ),
            diagnostics=diag,
        )
    return RiskEstimate(
        model=model,
        confidence=conf,
        horizon_days=horizon_days,
        var_loss=mc_var,
        es_loss=mc_es,
        n_obs=n_obs,
        sample_start=sample_start,
        sample_end=sample_end,
        status="ok",
        reason=None,
        diagnostics=diag,
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
      ``'monte_carlo_normal'``, and ``'evt_pot'`` (which delegates to Step 7 ``evt.estimate_evt_pot``).
    - For normal loss risk:
      ``VaR_c = -mu + z_c * sigma`` and ``ES_c = -mu + sigma * phi(z_c) / (1 - c)``.
    - Preserves nonpositive loss quantiles without ``abs()`` masking, and returns
      ``status='unavailable'`` with ``None`` metrics whenever sample size is insufficient.
    """
    return _estimate_risk_with_settings(
        train_asset_returns,
        weights,
        model=model,
        confidence=confidence,
        seed=seed,
    )


class _BoundRiskForecaster:
    """Pure historical-input ``RiskForecastFn`` bound to a single risk model name."""

    def __init__(self, model: str) -> None:
        self.model: str = model
        self.__name__: str = f"forecast_{model}"

    def __call__(
        self,
        train_asset_returns: pd.DataFrame,
        weights: pd.Series,
        *,
        confidence: float,
        seed: int | None = None,
    ) -> RiskEstimate:
        """Forecast one-day simple-return VaR/ES from historical asset returns and fixed weights."""
        return estimate_risk(
            train_asset_returns,
            weights,
            model=self.model,
            confidence=confidence,
            seed=seed,
        )

    def __repr__(self) -> str:
        return f"<RiskForecastFn model={self.model!r}>"


def get_risk_forecaster(model: str) -> RiskForecastFn:
    """Return a ``RiskForecastFn`` callback bound to ``model`` for rolling backtesting.

    Specification (SOLO STEP 5 / C1):
    - Supports ``'historical'``, ``'parametric_normal'``, and ``'monte_carlo_normal'``.
    - ``'evt_pot'`` remains deferred until SOLO STEP 7 (C2/C3) and raises
      ``NotImplementedError`` rather than returning fabricated core results.
    - Any unknown model identifier raises ``ValueError``.
    """
    if not isinstance(model, str) or model not in CORE_RISK_MODELS:
        raise ValueError(
            f"Unsupported risk model {model!r}; expected one of {CORE_RISK_MODELS}."
        )
    if model == "evt_pot":
        raise NotImplementedError(
            "get_risk_forecaster('evt_pot') is deferred until SOLO STEP 7 (C2/C3)."
        )
    return _BoundRiskForecaster(model)


def quantify_monte_carlo_uncertainty(
    train_asset_returns: pd.DataFrame,
    weights: pd.Series,
    *,
    confidence: float,
    base_seed: int | None = None,
    n_replications: int = 64,
    n_simulations: int | None = None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Quantify Monte Carlo VaR/ES sampling uncertainty across independent deterministic seeds.

    Evaluates ``n_replications`` independent PCG64 seeds ``[base_seed + r for r in range(n_replications)]``
    at ``n_simulations`` draws each (defaulting to ``25,000`` from ``config.yaml``) using the same
    fitted asset moments ``normal_moments(train_asset_returns)``. Reports empirical standard errors,
    RMSE vs. closed-form ``parametric_normal``, max absolute discrepancies, 95% simulation intervals,
    and the closed-form asymptotic quantile standard error.
    """
    conf, alpha = _validate_confidence(confidence)
    w_arr = _validate_portfolio_weights(weights)
    if isinstance(n_replications, bool) or not isinstance(n_replications, int) or n_replications < 2:
        raise ValueError(f"n_replications must be an integer >= 2; got {n_replications!r}.")

    settings = resolve_risk_runtime_settings(
        config,
        seed=base_seed,
        n_simulations=n_simulations,
    )
    seed0 = int(settings["monte_carlo_seed"])
    m_draws = int(settings["monte_carlo_simulations"])
    nav_usd = float(settings["nav_usd"])
    config_hash = str(settings["config_hash"])

    mean_series, cov_frame = normal_moments(train_asset_returns)
    mean_arr = mean_series.to_numpy(dtype=np.float64)
    cov_arr = cov_frame.to_numpy(dtype=np.float64)

    mu_p = float(np.dot(w_arr, mean_arr))
    var_p = max(0.0, float(w_arr @ cov_arr @ w_arr))
    sigma_p = math.sqrt(var_p)

    analytic_var, analytic_es, z_c, phi_z, _ = _analytic_normal_var_es_from_moments(
        mu_p, sigma_p, conf, alpha
    )
    asymp_var_se = (
        float(sigma_p * math.sqrt(conf * alpha / (float(m_draws) * (phi_z**2))))
        if sigma_p > _ZERO_VOL_TOL and phi_z > 0.0
        else 0.0
    )

    eigvals, eigvecs = np.linalg.eigh(cov_arr)
    factor = eigvecs * np.sqrt(np.maximum(eigvals, 0.0))[None, :]
    proj_vec = np.ascontiguousarray(factor.T @ w_arr, dtype=np.float64)

    seeds = [seed0 + r for r in range(n_replications)]
    var_reps = np.empty(n_replications, dtype=np.float64)
    es_reps = np.empty(n_replications, dtype=np.float64)

    n_assets = len(CANONICAL_TICKERS)
    for idx, s_val in enumerate(seeds):
        if sigma_p <= _ZERO_VOL_TOL:
            var_reps[idx] = analytic_var
            es_reps[idx] = analytic_es
        else:
            if idx == 0:
                sim_r = _simulate_multivariate_normal_returns(
                    mean_series,
                    cov_frame,
                    seed=s_val,
                    n_simulations=m_draws,
                )
                sim_losses = np.ascontiguousarray(-(sim_r @ w_arr), dtype=np.float64)
            else:
                rng = np.random.default_rng(s_val)
                z_draws = rng.standard_normal((m_draws, n_assets), dtype=np.float64)
                sim_losses = np.ascontiguousarray(-(mu_p + (z_draws @ proj_vec)), dtype=np.float64)
            v_i, e_i, _, _ = empirical_var_and_es(
                pd.Series(sim_losses, dtype=float),
                conf,
            )
            var_reps[idx] = v_i
            es_reps[idx] = e_i

    var_err = var_reps - analytic_var
    es_err = es_reps - analytic_es

    var_se_emp = float(np.std(var_reps, ddof=1, dtype=np.float64))
    es_se_emp = float(np.std(es_reps, ddof=1, dtype=np.float64))
    var_se_bps = float(var_se_emp * 10_000.0)
    es_se_bps = float(es_se_emp * 10_000.0)
    var_se_usd = float(var_se_emp * nav_usd)
    es_se_usd = float(es_se_emp * nav_usd)

    return {
        "confidence": conf,
        "alpha": alpha,
        "n_obs": int(len(train_asset_returns)),
        "sample_start": str(train_asset_returns.index[0].date()),
        "sample_end": str(train_asset_returns.index[-1].date()),
        "base_seed": seed0,
        "n_replications": int(n_replications),
        "monte_carlo_simulations_per_rep": m_draws,
        "nav_usd": nav_usd,
        "config_hash": config_hash,
        "portfolio_mu_daily": mu_p,
        "portfolio_sigma_daily": sigma_p,
        "analytic_normal_var_loss": analytic_var,
        "analytic_normal_es_loss": analytic_es,
        "primary_seed_var_loss": float(var_reps[0]),
        "primary_seed_es_loss": float(es_reps[0]),
        "primary_seed_var_diff_vs_analytic": float(var_err[0]),
        "primary_seed_es_diff_vs_analytic": float(es_err[0]),
        "asymptotic_var_se": asymp_var_se,
        "empirical_var_mean_across_seeds": float(np.mean(var_reps)),
        "empirical_var_se_across_seeds": var_se_emp,
        "empirical_var_rmse_vs_analytic": float(np.sqrt(np.mean(var_err**2))),
        "empirical_var_max_abs_err_vs_analytic": float(np.max(np.abs(var_err))),
        "empirical_var_p025": float(np.quantile(var_reps, 0.025)),
        "empirical_var_p975": float(np.quantile(var_reps, 0.975)),
        "empirical_es_mean_across_seeds": float(np.mean(es_reps)),
        "empirical_es_se_across_seeds": es_se_emp,
        "empirical_es_rmse_vs_analytic": float(np.sqrt(np.mean(es_err**2))),
        "empirical_es_max_abs_err_vs_analytic": float(np.max(np.abs(es_err))),
        "empirical_es_p025": float(np.quantile(es_reps, 0.025)),
        "empirical_es_p975": float(np.quantile(es_reps, 0.975)),
        "empirical_var_se_bps": var_se_bps,
        "empirical_es_se_bps": es_se_bps,
        "empirical_var_se_usd": var_se_usd,
        "empirical_es_se_usd": es_se_usd,
        "recommended_agreement_tolerance_var": float(max(4.0 * asymp_var_se, 4.0 * var_se_emp, 1e-4)),
        "recommended_agreement_tolerance_es": float(max(4.5 * es_se_emp, 1.5e-4)),
        "displayed_precision_note": (
            f"At M={m_draws:,} draws across {int(n_replications)} seeds (base_seed={seed0}), "
            f"empirical 1-SE simulation noise is {var_se_bps:.2f} bps (VaR) / {es_se_bps:.2f} bps (ES) "
            f"of NAV (USD {var_se_usd:,.2f} / USD {es_se_usd:,.2f} on USD {nav_usd:,.0f}); "
            "full float64 values are preserved in tables/JSON."
        ),
    }


def describe_window_crisis_coverage(
    sample_start: str | pd.Timestamp,
    sample_end: str | pd.Timestamp,
    historical_scenarios: Sequence[StressScenarioSpec] | None = None,
) -> dict[str, Any]:
    """Determine actual overlap between ``[sample_start, sample_end]`` and configured crisis windows.

    Never hardcodes crisis claims: a pre-2017 development window is truthfully reported as
    excluding post-2016 COVID-19 (2020) and Rate Shock (2022) scenarios, while a 2012-2016
    recent development window also omits the 2007-2009 GFC.
    """
    start_ts = pd.Timestamp(sample_start)
    end_ts = pd.Timestamp(sample_end)
    if start_ts > end_ts:
        raise ValueError(f"sample_start ({start_ts}) must be <= sample_end ({end_ts}).")

    scenarios = (
        tuple(historical_scenarios)
        if historical_scenarios is not None
        else _load_default_app_config().stress.historical_scenarios
    )

    included_ids: list[str] = []
    excluded_ids: list[str] = []
    pre_window_ids: list[str] = []
    post_window_ids: list[str] = []
    scenario_details: dict[str, dict[str, Any]] = {}

    for sc in scenarios:
        if sc.start_date is None or sc.end_date is None:
            continue
        sc_start = pd.Timestamp(sc.start_date)
        sc_end = pd.Timestamp(sc.end_date)
        if sc_end < start_ts:
            status = "pre_window_omitted"
            excluded_ids.append(sc.scenario_id)
            pre_window_ids.append(sc.scenario_id)
        elif sc_start > end_ts:
            status = "post_window_not_in_sample"
            excluded_ids.append(sc.scenario_id)
            post_window_ids.append(sc.scenario_id)
        elif sc_start >= start_ts and sc_end <= end_ts:
            status = "fully_included"
            included_ids.append(sc.scenario_id)
        else:
            status = "partially_included"
            included_ids.append(sc.scenario_id)

        scenario_details[sc.scenario_id] = {
            "label": sc.label,
            "scenario_start": str(sc_start.date()),
            "scenario_end": str(sc_end.date()),
            "coverage_status": status,
        }

    return {
        "sample_start": str(start_ts.date()),
        "sample_end": str(end_ts.date()),
        "included_scenarios": tuple(included_ids),
        "excluded_scenarios": tuple(excluded_ids),
        "pre_window_omitted_scenarios": tuple(pre_window_ids),
        "post_window_scenarios": tuple(post_window_ids),
        "scenario_details": scenario_details,
    }


def compute_fixed_exposure_loss_diagnostics(
    train_asset_returns: pd.DataFrame,
    weights: pd.Series,
    *,
    portfolio_id: str = "portfolio",
) -> dict[str, Any]:
    """Inspect the fixed-exposure simple/log1p return and 1-day loss series used by ``estimate_risk``.

    Reuses Step 4's ``run_portfolio_return_stationarity_diagnostics`` on the static-weight
    pre-cost return series ``R_{p,t} = (train_asset_returns @ weights)_t`` and explicitly
    distinguishes it from a changing-weight, monthly-rebalanced net strategy return series.
    """
    x_arr = _validate_asset_return_frame(train_asset_returns, min_rows=2, context="train_asset_returns")
    w_arr = _validate_portfolio_weights(weights)

    fixed_returns_arr = np.ascontiguousarray(x_arr @ w_arr, dtype=np.float64)
    fixed_losses_arr = np.ascontiguousarray(-fixed_returns_arr, dtype=np.float64)
    fixed_returns = pd.Series(
        fixed_returns_arr,
        index=train_asset_returns.index,
        name=f"{portfolio_id}_fixed_exposure_simple_return",
        dtype=float,
    )

    adf_df = run_portfolio_return_stationarity_diagnostics(
        fixed_returns,
        series_label=f"{portfolio_id}_fixed_exposure",
    )
    loss_summary = _compute_loss_sample_summary(fixed_losses_arr)

    return {
        "portfolio_id": portfolio_id,
        "series_definition": (
            "fixed_exposure_pre_cost_risk_model_return: R_{p,t} = sum_i w_i R_{i,t} holding "
            "target weights w fixed across all training sessions before transaction costs "
            "(distinct from the drifting, monthly-rebalanced net strategy return series)."
        ),
        "n_obs": int(len(fixed_returns)),
        "sample_start": str(train_asset_returns.index[0].date()),
        "sample_end": str(train_asset_returns.index[-1].date()),
        "weights": {ticker: float(w_arr[i]) for i, ticker in enumerate(CANONICAL_TICKERS)},
        "loss_moments": loss_summary,
        "stationarity_table": adf_df,
    }


def compare_risk_models_table(
    train_asset_returns: pd.DataFrame,
    weights: pd.Series,
    *,
    confidences: Sequence[float] = SUPPORTED_CONFIDENCE_LEVELS,
    models: Sequence[str] = SUPPORTED_C1_RISK_MODELS,
    seed: int | None = None,
    nav_usd: float | None = None,
    window_id: str = "custom",
    portfolio_id: str = "portfolio",
    historical_scenarios: Sequence[StressScenarioSpec] | None = None,
    config: AppConfig | None = None,
    n_simulations: int | None = None,
) -> pd.DataFrame:
    """Build a matched comparison table across C1 risk models and confidence levels on identical data.

    All rows for a given window and ``portfolio_id`` share the exact same ``train_asset_returns``
    dates, fixed ``weights``, resolved runtime configuration, and 1-day pre-cost simple-loss definition.
    """
    _validate_asset_return_frame(train_asset_returns, min_rows=2, context="train_asset_returns")
    _validate_portfolio_weights(weights)

    settings = resolve_risk_runtime_settings(
        config,
        seed=seed,
        n_simulations=n_simulations,
    )
    effective_nav_usd = float(nav_usd) if nav_usd is not None else float(settings["nav_usd"])
    if not math.isfinite(effective_nav_usd) or effective_nav_usd <= 0.0:
        raise ValueError(f"nav_usd must be finite and > 0; got {effective_nav_usd!r}.")

    effective_scenarios = (
        historical_scenarios
        if historical_scenarios is not None
        else (config.stress.historical_scenarios if config is not None else None)
    )
    coverage = describe_window_crisis_coverage(
        train_asset_returns.index[0],
        train_asset_returns.index[-1],
        historical_scenarios=effective_scenarios,
    )

    estimates_by_conf_model: dict[tuple[float, str], RiskEstimate] = {}
    for c_val in confidences:
        conf_clean, _ = _validate_confidence(c_val)
        for m_name in models:
            est = _estimate_risk_with_settings(
                train_asset_returns,
                weights,
                model=m_name,
                confidence=conf_clean,
                seed=seed,
                config=config,
                n_simulations=n_simulations,
            )
            estimates_by_conf_model[(conf_clean, m_name)] = est

    rows: list[dict[str, Any]] = []
    for c_val in confidences:
        conf_clean, alpha_clean = _validate_confidence(c_val)
        norm_est = estimates_by_conf_model.get((conf_clean, "parametric_normal"))
        norm_var = norm_est.var_loss if norm_est is not None else None
        norm_es = norm_est.es_loss if norm_est is not None else None

        for m_name in models:
            est = estimates_by_conf_model[(conf_clean, m_name)]
            v_loss = est.var_loss
            e_loss = est.es_loss
            diag = est.diagnostics

            diff_vs_norm_var = (
                float(v_loss - norm_var)
                if (v_loss is not None and norm_var is not None)
                else None
            )
            diff_vs_norm_es = (
                float(e_loss - norm_es)
                if (e_loss is not None and norm_es is not None)
                else None
            )
            ratio_vs_norm_var = (
                float(v_loss / norm_var)
                if (v_loss is not None and norm_var is not None and abs(norm_var) > _ZERO_VOL_TOL)
                else None
            )
            ratio_vs_norm_es = (
                float(e_loss / norm_es)
                if (e_loss is not None and norm_es is not None and abs(norm_es) > _ZERO_VOL_TOL)
                else None
            )

            rows.append(
                {
                    "window_id": window_id,
                    "portfolio_id": portfolio_id,
                    "model": est.model,
                    "confidence": est.confidence,
                    "alpha": alpha_clean,
                    "is_mandatory_comparison": bool(
                        any(abs(est.confidence - mc) <= 1e-9 for mc in MANDATORY_COMPARISON_CONFIDENCES)
                    ),
                    "horizon_days": est.horizon_days,
                    "n_obs": est.n_obs,
                    "sample_start": str(est.sample_start),
                    "sample_end": str(est.sample_end),
                    "var_loss": v_loss,
                    "es_loss": e_loss,
                    "es_minus_var": (
                        float(e_loss - v_loss) if (v_loss is not None and e_loss is not None) else None
                    ),
                    "var_pct": float(v_loss * 100.0) if v_loss is not None else None,
                    "es_pct": float(e_loss * 100.0) if e_loss is not None else None,
                    "var_usd": float(v_loss * effective_nav_usd) if v_loss is not None else None,
                    "es_usd": float(e_loss * effective_nav_usd) if e_loss is not None else None,
                    "diff_vs_parametric_normal_var": diff_vs_norm_var,
                    "diff_vs_parametric_normal_es": diff_vs_norm_es,
                    "diff_vs_parametric_normal_var_bps": (
                        float(diff_vs_norm_var * 10_000.0) if diff_vs_norm_var is not None else None
                    ),
                    "diff_vs_parametric_normal_es_bps": (
                        float(diff_vs_norm_es * 10_000.0) if diff_vs_norm_es is not None else None
                    ),
                    "ratio_to_parametric_normal_var": ratio_vs_norm_var,
                    "ratio_to_parametric_normal_es": ratio_vs_norm_es,
                    "status": est.status,
                    "reason": est.reason,
                    "seed": int(diag["seed"]) if diag.get("seed") is not None else None,
                    "monte_carlo_simulations": (
                        int(diag["monte_carlo_simulations"])
                        if diag.get("monte_carlo_simulations") is not None
                        else None
                    ),
                    "config_hash": str(diag.get("config_hash", settings["config_hash"])),
                    "included_crisis_scenarios": ",".join(coverage["included_scenarios"]),
                    "excluded_crisis_scenarios": ",".join(coverage["excluded_scenarios"]),
                }
            )

    df = pd.DataFrame(rows)
    for nullable_meta_col in ("reason", "seed", "monte_carlo_simulations"):
        if nullable_meta_col in df.columns:
            df[nullable_meta_col] = pd.Series(
                [r[nullable_meta_col] for r in rows],
                index=df.index,
                dtype=object,
            )
    df.attrs.update(
        {
            "window_id": window_id,
            "portfolio_id": portfolio_id,
            "n_obs": int(len(train_asset_returns)),
            "sample_start": str(train_asset_returns.index[0].date()),
            "sample_end": str(train_asset_returns.index[-1].date()),
            "config_hash": str(settings["config_hash"]),
            "monte_carlo_seed": int(settings["monte_carlo_seed"]),
            "monte_carlo_simulations": int(settings["monte_carlo_simulations"]),
            "nav_usd": effective_nav_usd,
            "crisis_coverage": coverage,
            "weights": {ticker: float(weights.loc[ticker]) for ticker in CANONICAL_TICKERS},
        }
    )
    return df


def comparison_table_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a ``compare_risk_models_table`` DataFrame to RFC-8259-compliant records (`R2`).

    - Non-applicable metadata (``seed`` and ``monte_carlo_simulations`` on non-MC models, and
      ``reason`` on ``status='ok'`` rows) is exported as ``None`` (JSON ``null``), never ``NaN``.
    - Valid ``status='ok'`` risk rows must carry finite ``var_loss``, ``es_loss``, ``var_pct``,
      ``es_pct``, ``var_usd``, and ``es_usd`` values; invalid core risk values are never masked
      as ``0.0`` or silently dropped.
    - Legitimately ``status='unavailable'`` rows must carry a non-empty ``reason`` and ``None``
      for unavailable risk metrics.
    """
    records: list[dict[str, Any]] = []
    core_numeric_cols = (
        "var_loss",
        "es_loss",
        "es_minus_var",
        "var_pct",
        "es_pct",
        "var_usd",
        "es_usd",
    )
    rel_numeric_cols = (
        "diff_vs_parametric_normal_var",
        "diff_vs_parametric_normal_es",
        "diff_vs_parametric_normal_var_bps",
        "diff_vs_parametric_normal_es_bps",
        "ratio_to_parametric_normal_var",
        "ratio_to_parametric_normal_es",
    )

    for raw_row in df.to_dict(orient="records"):
        row = dict(raw_row)
        model_name = str(row.get("model", ""))
        status = str(row.get("status", ""))

        if model_name == "monte_carlo_normal":
            seed_val = row.get("seed")
            sims_val = row.get("monte_carlo_simulations")
            if seed_val is None or pd.isna(seed_val) or sims_val is None or pd.isna(sims_val):
                raise ValueError(
                    "monte_carlo_normal row is missing finite integer seed or monte_carlo_simulations."
                )
            row["seed"] = int(seed_val)
            row["monte_carlo_simulations"] = int(sims_val)
        else:
            row["seed"] = None
            row["monte_carlo_simulations"] = None

        reason_val = row.get("reason")
        if status == "ok":
            row["reason"] = None if (reason_val is None or pd.isna(reason_val)) else str(reason_val)
            for col in core_numeric_cols:
                val = row.get(col)
                if val is None or pd.isna(val) or not math.isfinite(float(val)):
                    raise ValueError(
                        f"Invalid non-finite core risk metric {col}={val!r} on status='ok' row ({model_name})."
                    )
                row[col] = float(val)
            for col in rel_numeric_cols:
                val = row.get(col)
                if val is None or pd.isna(val):
                    row[col] = None
                else:
                    if not math.isfinite(float(val)):
                        raise ValueError(f"Non-finite relative risk metric {col}={val!r}.")
                    row[col] = float(val)
        elif status == "warning":
            if reason_val is None or pd.isna(reason_val) or not str(reason_val).strip():
                raise ValueError(f"status='warning' row ({model_name}) requires a non-empty reason.")
            row["reason"] = str(reason_val)
            if row.get("var_loss") is None or pd.isna(row.get("var_loss")) or not math.isfinite(float(row["var_loss"])):
                raise ValueError(f"status='warning' row ({model_name}) requires finite var_loss.")
            for col in core_numeric_cols + rel_numeric_cols:
                val = row.get(col)
                if val is None or pd.isna(val):
                    row[col] = None
                else:
                    if not math.isfinite(float(val)):
                        raise ValueError(f"Non-finite risk metric {col}={val!r} on warning row.")
                    row[col] = float(val)
        elif status == "unavailable":
            if reason_val is None or pd.isna(reason_val) or not str(reason_val).strip():
                raise ValueError(f"status='unavailable' row ({model_name}) requires a non-empty reason.")
            row["reason"] = str(reason_val)
            for col in core_numeric_cols + rel_numeric_cols:
                val = row.get(col)
                if val is not None and not pd.isna(val):
                    raise ValueError(
                        f"status='unavailable' row ({model_name}) must not carry numeric {col}={val!r}."
                    )
                row[col] = None
        else:
            raise ValueError(f"Unexpected risk row status {status!r}.")

        records.append(row)
    return records


def stationarity_table_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert an ADF stationarity DataFrame into RFC-8259-compliant records without bare ``NaN``."""
    records: list[dict[str, Any]] = []
    for raw_row in df.to_dict(orient="records"):
        row = dict(raw_row)
        status = str(row.get("status", ""))
        reason_val = row.get("reason")
        if status == "ok":
            row["reason"] = None if (reason_val is None or pd.isna(reason_val)) else str(reason_val)
            for float_col in ("adf_stat", "p_value", "crit_1pct", "crit_5pct", "crit_10pct"):
                val = row.get(float_col)
                if val is None or pd.isna(val) or not math.isfinite(float(val)):
                    raise ValueError(f"Non-finite stationarity field {float_col}={val!r} on status='ok' row.")
                row[float_col] = float(val)
            for int_col in ("used_lag", "n_obs"):
                val = row.get(int_col)
                if val is None or pd.isna(val):
                    raise ValueError(f"Missing integer stationarity field {int_col} on status='ok' row.")
                row[int_col] = int(val)
            row["reject_unit_root_5pct"] = bool(row["reject_unit_root_5pct"])
        elif status == "unavailable":
            if reason_val is None or pd.isna(reason_val) or not str(reason_val).strip():
                raise ValueError("status='unavailable' stationarity row requires a non-empty reason.")
            row["reason"] = str(reason_val)
            for col in ("adf_stat", "p_value", "used_lag", "crit_1pct", "crit_5pct", "crit_10pct", "reject_unit_root_5pct"):
                val = row.get(col)
                row[col] = None if (val is None or pd.isna(val)) else val
        else:
            raise ValueError(f"Unexpected stationarity row status {status!r}.")
        records.append(row)
    return records


def serialize_c1_risk_bundle(
    bundle: Mapping[str, Any],
    *,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    """Convert a ``build_development_c1_risk_bundle`` result into a strict RFC-8259 JSON dict (`R2`)."""
    payload: dict[str, Any] = {
        "scope": bundle["scope"],
    }
    if dataset_id is not None:
        payload["dataset_id"] = str(dataset_id)
    elif "dataset_id" in bundle:
        payload["dataset_id"] = str(bundle["dataset_id"])

    payload.update(
        {
            "config_hash": str(bundle["config_hash"]),
            "development_end": str(bundle["development_end"]),
            "monte_carlo_seed": int(bundle["monte_carlo_seed"]),
            "monte_carlo_simulations": int(bundle["monte_carlo_simulations"]),
            "nav_usd": float(bundle["nav_usd"]),
            "exposures": bundle["exposures"],
            "window_coverage": bundle["window_coverage"],
            "comparison_tables": {
                win_id: {
                    port_id: comparison_table_to_records(df)
                    for port_id, df in port_map.items()
                }
                for win_id, port_map in bundle["comparison_tables"].items()
            },
            "mandatory_95_99_tables": {
                win_id: {
                    port_id: comparison_table_to_records(df)
                    for port_id, df in port_map.items()
                }
                for win_id, port_map in bundle["mandatory_95_99_tables"].items()
            },
            "fixed_exposure_diagnostics": {
                win_id: {
                    port_id: {
                        "portfolio_id": diag["portfolio_id"],
                        "series_definition": diag["series_definition"],
                        "n_obs": int(diag["n_obs"]),
                        "sample_start": str(diag["sample_start"]),
                        "sample_end": str(diag["sample_end"]),
                        "weights": diag["weights"],
                        "loss_moments": diag["loss_moments"],
                        "stationarity_table": stationarity_table_to_records(diag["stationarity_table"]),
                    }
                    for port_id, diag in port_map.items()
                }
                for win_id, port_map in bundle["fixed_exposure_diagnostics"].items()
            },
            "changing_weight_strategy_stationarity": {
                port_id: stationarity_table_to_records(df)
                for port_id, df in bundle["changing_weight_strategy_stationarity"].items()
            },
            "mc_uncertainty": bundle["mc_uncertainty"],
        }
    )
    # Enforce RFC 8259 compliance (rejects any NaN / Infinity anywhere in the payload)
    json.dumps(payload, allow_nan=False)
    return payload


def build_development_c1_risk_bundle(
    asset_returns: pd.DataFrame,
    config: AppConfig,
) -> dict[str, Any]:
    """Compute all Step 5 (C1) development-period risk tables, MC uncertainty, and diagnostics.

    Holdout safeguard:
    - Refuses any ``asset_returns`` slice extending beyond ``config.chronology.development_end``
      (``2016-12-30``) so selection (``2017-2020``) and evaluation (``2021-2026``) strategy
      outcomes remain strictly uncomputed and uninspected during Step 5.
    """
    _validate_asset_return_frame(asset_returns, min_rows=2, context="asset_returns")
    dev_end_ts = pd.Timestamp(config.chronology.development_end)
    max_ts = pd.Timestamp(asset_returns.index.max())
    if max_ts > dev_end_ts:
        raise ValueError(
            f"Holdout discipline violation: build_development_c1_risk_bundle requires "
            f"asset_returns <= development_end ({dev_end_ts.date()}); got max date {max_ts.date()}."
        )

    settings = resolve_risk_runtime_settings(config)
    est_win = int(config.portfolio.estimation_window_days)
    recent_win = int(settings["dashboard_risk_window_days"])
    mc_seed = int(settings["monte_carlo_seed"])
    mc_sims = int(settings["monte_carlo_simulations"])
    nav_usd = float(settings["nav_usd"])
    config_hash = str(settings["config_hash"])

    if est_win < 2 or est_win > len(asset_returns):
        raise ValueError(
            f"portfolio.estimation_window_days ({est_win}) must be in [2, {len(asset_returns)}]."
        )
    if recent_win < 2 or recent_win > len(asset_returns):
        raise ValueError(
            f"risk.dashboard_risk_window_days ({recent_win}) must be in [2, {len(asset_returns)}]."
        )

    # 1. Construct development portfolio paths and extract canonical fixed exposures
    core_specs = make_core_strategy_specs(config)
    dev_paths = {
        name: build_portfolio_path(asset_returns, spec, config)
        for name, spec in core_specs.items()
    }
    mv_dev_end_weights = construct_weights(
        asset_returns.iloc[-est_win:],
        config.portfolio.constraints,
        "min_variance",
    )
    eq_weights = construct_weights(
        asset_returns.iloc[-est_win:],
        config.portfolio.constraints,
        "equal_weight",
    )
    bm_weights = construct_weights(
        asset_returns.iloc[-est_win:],
        config.portfolio.constraints,
        "benchmark_60_40",
    )
    mv_last_rebal_row = dev_paths["min_variance"].rebalances.iloc[-1]
    mv_last_rebal_weights = pd.Series(
        {ticker: float(mv_last_rebal_row[ticker]) for ticker in CANONICAL_TICKERS},
        index=list(CANONICAL_TICKERS),
        dtype=float,
    )

    exposures: dict[str, pd.Series] = {
        "min_variance": mv_dev_end_weights,
        "equal_weight": eq_weights,
        "benchmark_60_40": bm_weights,
    }
    exposure_descriptions: dict[str, dict[str, Any]] = {
        "min_variance": {
            "description": (
                f"Constrained minimum-variance target weights estimated on the terminal "
                f"{est_win}-session development window ({asset_returns.index[-est_win].date()}.."
                f"{asset_returns.index[-1].date()})."
            ),
            "estimation_start": str(asset_returns.index[-est_win].date()),
            "estimation_end": str(asset_returns.index[-1].date()),
            "n_estimation_sessions": est_win,
            "weights": {t: float(mv_dev_end_weights.loc[t]) for t in CANONICAL_TICKERS},
            "last_scheduled_rebalance_2016_12_01_weights": {
                t: float(mv_last_rebal_weights.loc[t]) for t in CANONICAL_TICKERS
            },
        },
        "equal_weight": {
            "description": "Unconstrained 1/7 equal-weight reference exposure across all 7 canonical ETFs.",
            "weights": {t: float(eq_weights.loc[t]) for t in CANONICAL_TICKERS},
        },
        "benchmark_60_40": {
            "description": "Unconstrained 60% SPY / 40% AGG reference benchmark exposure.",
            "weights": {t: float(bm_weights.loc[t]) for t in CANONICAL_TICKERS},
        },
    }

    # 2. Define the two C1 diagnostic windows on the development dataset:
    #    - recent_development_1260d: trailing recent_win sessions ending development_end
    #    - full_development_3020d: full development return sample
    windows: dict[str, pd.DataFrame] = {
        "recent_development_1260d": asset_returns.iloc[-recent_win:].copy(),
        "full_development_3020d": asset_returns.copy(),
    }

    comparison_tables: dict[str, dict[str, pd.DataFrame]] = {}
    mandatory_95_99_tables: dict[str, dict[str, pd.DataFrame]] = {}
    fixed_exposure_diagnostics: dict[str, dict[str, dict[str, Any]]] = {}
    mc_uncertainty_by_window: dict[str, dict[str, dict[str, Any]]] = {}

    for win_id, win_df in windows.items():
        comparison_tables[win_id] = {}
        mandatory_95_99_tables[win_id] = {}
        fixed_exposure_diagnostics[win_id] = {}
        mc_uncertainty_by_window[win_id] = {}

        for port_id, w_ser in exposures.items():
            tbl = compare_risk_models_table(
                win_df,
                w_ser,
                confidences=SUPPORTED_CONFIDENCE_LEVELS,
                models=SUPPORTED_C1_RISK_MODELS,
                seed=mc_seed,
                nav_usd=nav_usd,
                window_id=win_id,
                portfolio_id=port_id,
                historical_scenarios=config.stress.historical_scenarios,
                config=config,
                n_simulations=mc_sims,
            )
            comparison_tables[win_id][port_id] = tbl
            sub_tbl = tbl.loc[tbl["is_mandatory_comparison"]].reset_index(drop=True)
            for nullable_meta_col in ("reason", "seed", "monte_carlo_simulations"):
                if nullable_meta_col in sub_tbl.columns:
                    sub_tbl[nullable_meta_col] = pd.Series(
                        [None if pd.isna(v) else (int(v) if nullable_meta_col != "reason" else str(v)) for v in sub_tbl[nullable_meta_col].tolist()],
                        index=sub_tbl.index,
                        dtype=object,
                    )
            mandatory_95_99_tables[win_id][port_id] = sub_tbl

            fixed_exposure_diagnostics[win_id][port_id] = compute_fixed_exposure_loss_diagnostics(
                win_df,
                w_ser,
                portfolio_id=f"{port_id}_{win_id}",
            )

        # Quantify MC sampling error across 64 independent seeds for the primary min_variance exposure
        mc_uncertainty_by_window[win_id] = {
            f"c_{int(round(c * 100))}": quantify_monte_carlo_uncertainty(
                win_df,
                mv_dev_end_weights,
                confidence=c,
                base_seed=mc_seed,
                n_replications=64,
                n_simulations=mc_sims,
                config=config,
            )
            for c in SUPPORTED_CONFIDENCE_LEVELS
        }

    # 3. Also record Step 4 changing-weight net strategy stationarity alongside fixed-exposure
    #    risk-model return stationarity using Step 4's fixed_exposure_returns parameter
    changing_weight_stationarity: dict[str, pd.DataFrame] = {
        port_id: run_portfolio_return_stationarity_diagnostics(
            path.net_returns,
            series_label=port_id,
            fixed_exposure_returns=pd.Series(
                asset_returns.to_numpy(dtype=np.float64)
                @ exposures[port_id].to_numpy(dtype=np.float64),
                index=asset_returns.index,
                name=f"{port_id}_fixed_exposure_simple_return",
                dtype=float,
            ),
        )
        for port_id, path in dev_paths.items()
    }

    return {
        "scope": "development_only_through_2016_12_30",
        "development_end": str(dev_end_ts.date()),
        "config_hash": config_hash,
        "monte_carlo_seed": mc_seed,
        "monte_carlo_simulations": mc_sims,
        "nav_usd": nav_usd,
        "exposures": exposure_descriptions,
        "window_coverage": {
            win_id: describe_window_crisis_coverage(
                win_df.index[0],
                win_df.index[-1],
                historical_scenarios=config.stress.historical_scenarios,
            )
            for win_id, win_df in windows.items()
        },
        "comparison_tables": comparison_tables,
        "mandatory_95_99_tables": mandatory_95_99_tables,
        "fixed_exposure_diagnostics": fixed_exposure_diagnostics,
        "changing_weight_strategy_stationarity": changing_weight_stationarity,
        "mc_uncertainty": mc_uncertainty_by_window,
    }
