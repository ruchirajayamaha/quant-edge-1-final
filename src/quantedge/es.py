"""Expected Shortfall (ES) estimation and shared empirical tail-weight helper (SOLO STEP 5 / C1).

Public interface frozen in D0 for SOLO STEP 5 (C1) and SOLO STEP 8 (B2):
- ``empirical_tail_weights(losses, confidence) -> pd.Series``

Supporting helper for historical VaR/ES calculation:
- ``empirical_var_and_es(losses, confidence) -> tuple[float, float, pd.Series, dict[str, Any]]``

Mathematical convention (Acerbi & Tasche 2002; Rockafellar & Uryasev 2002):
- Given ``n >= 1`` finite one-day simple-return loss observations ``L_1, ..., L_n`` (where
  ``L_t = -R_{p,t}`` and each observation carries empirical probability mass ``1 / n``),
  let ``L_{(1)} <= L_{(2)} <= ... <= L_{(n)}`` denote the ascending order statistics and
  ``L_{[1]} >= L_{[2]} >= ... >= L_{[n]}`` denote the descending (worst-first) order statistics.
- The empirical step-CDF quantile at confidence ``c in (0, 1)`` (Hyndman-Fan Type 1 /
  ``method="inverted_cdf"``) is:
  ``VaR_c = F_n^{-1}(c) = inf{x : F_n(x) >= c} = L_{(ceil(n * c))}``.
- Expected Shortfall at confidence ``c`` integrates the empirical quantile function over the
  worst ``alpha = 1 - c`` probability mass:
  ``ES_c = (1 / alpha) * integral_{c}^{1} F_n^{-1}(u) du``.
- Let ``m = n * alpha`` be the (possibly fractional) number of worst observations required
  to cover probability mass ``alpha``, and let ``k_slots = ceil(m)`` in ``{1, ..., n}``.
  The worst-tail order-statistic boundary is ``u_* = L_{[k_slots]} = L_{(n - k_slots + 1)}``.
  (Crucially, ``u_*`` is an actual sample order statistic rather than a linearly interpolated
  value between order statistics, which could otherwise leave ``k_strict > m`` and ``k_tie = 0``
  when ``m`` is fractional.)
- Every observation strictly exceeding ``u_*`` (``L_i > u_*``, count ``k_strict < m``) receives
  full normalized tail weight ``1 / m = 1 / (n * alpha)``.
- The remaining fractional or tied tail mass ``(m - k_strict) / m = (alpha - k_strict / n) / alpha``
  is split equally across all ``k_tie >= 1`` observations tied at ``L_i == u_*``, so each tied
  boundary observation receives weight ``(m - k_strict) / (m * k_tie)``.
- Observations strictly below ``u_*`` receive weight ``0.0``.
- The resulting weights are non-negative, sum to ``1.0``, preserve ``losses.index``, and satisfy
  ``ES_c = float(tail_weights @ losses) >= VaR_c`` identically for every sample and confidence.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

_FLOAT_INT_SNAP_TOL: float = 1e-12


def _validate_confidence(confidence: float) -> tuple[float, float]:
    """Validate ``confidence in (0, 1)`` and return ``(confidence, alpha)`` free of binary float drift."""
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float, np.floating)):
        raise TypeError(
            f"confidence must be a finite float in (0, 1); got {type(confidence).__name__}."
        )
    conf = float(confidence)
    if not math.isfinite(conf) or not (0.0 < conf < 1.0):
        raise ValueError(f"confidence must lie strictly in (0, 1); got {confidence!r}.")

    alpha = 1.0 - conf
    # Snap standard decimal confidences (e.g. 1.0 - 0.95 = 0.050000000000000044) cleanly.
    alpha_rounded = round(alpha, 12)
    if abs(alpha - alpha_rounded) <= _FLOAT_INT_SNAP_TOL and 0.0 < alpha_rounded < 1.0:
        alpha = alpha_rounded
    return conf, alpha


def _validate_losses_series(losses: pd.Series) -> np.ndarray:
    """Validate ``losses`` is a non-empty ``pd.Series`` with unique index and finite numeric values."""
    if not isinstance(losses, pd.Series):
        raise TypeError(f"losses must be a pandas Series; got {type(losses).__name__}.")
    if len(losses) < 1:
        raise ValueError("losses must contain at least 1 observation.")
    if not losses.index.is_unique:
        raise ValueError("losses index must be unique so empirical tail weights align unambiguously.")

    try:
        arr = np.ascontiguousarray(losses.to_numpy(dtype=np.float64), dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("losses must contain numeric float-convertible values.") from exc

    if not np.isfinite(arr).all():
        raise ValueError("losses contains NaN or non-finite (+/-inf) values.")
    return arr


def empirical_tail_weights(
    losses: pd.Series,
    confidence: float,
) -> pd.Series:
    """Return aligned normalized worst-tail observation weights summing to ``1.0``.

    Frozen D0 contract (``CONTRACTS.md``):
    - Integrates the empirical quantile distribution over the worst ``alpha = 1 - confidence``
      probability mass of ``losses`` (each of ``n`` valid observations carries mass ``1 / n``).
    - Observations strictly exceeding the ``confidence`` order-statistic boundary loss ``u_*``
      receive full mass ``1 / (n * alpha)``; remaining fractional boundary mass
      ``(alpha - k_strict / n) / alpha`` is split evenly across all observations tied at ``u_*``.
    - Non-tail observations receive weight ``0.0``; returned ``pd.Series`` preserves
      ``losses.index`` and sums to ``1.0`` so ``float(weights @ losses)`` equals exact
      historical ES and Euler historical ES asset contributions sum identically to total ES.
    """
    conf, alpha = _validate_confidence(confidence)
    loss_arr = _validate_losses_series(losses)
    n_obs = int(len(loss_arr))

    m_raw = float(n_obs) * alpha
    m_snap = float(round(m_raw))
    if m_snap >= 1.0 and abs(m_raw - m_snap) <= _FLOAT_INT_SNAP_TOL * max(1.0, float(n_obs)):
        m = m_snap
    else:
        m = m_raw

    # Ascending order statistics L_(1) <= ... <= L_(n)
    sorted_asc = np.sort(loss_arr, kind="mergesort")

    # Number of descending (worst-first) order-statistic slots needed to cover mass m / n:
    # k_slots = ceil(m) in {1, ..., n_obs}. In 0-based ascending array, index is n_obs - k_slots.
    k_slots = max(1, min(n_obs, int(math.ceil(m - _FLOAT_INT_SNAP_TOL))))
    u_star = float(sorted_asc[n_obs - k_slots])

    # Empirical VaR under step-CDF inverse F_n^{-1}(c) = L_{(ceil(n * c))}
    nc_raw = float(n_obs) * conf
    nc_snap = float(round(nc_raw))
    if 1.0 <= nc_snap <= float(n_obs) and abs(nc_raw - nc_snap) <= _FLOAT_INT_SNAP_TOL * max(
        1.0, float(n_obs)
    ):
        nc = nc_snap
    else:
        nc = nc_raw
    var_rank_1based = max(1, min(n_obs, int(math.ceil(nc - _FLOAT_INT_SNAP_TOL))))
    var_inverted_cdf = float(sorted_asc[var_rank_1based - 1])

    strict_mask = loss_arr > u_star
    tie_mask = loss_arr == u_star
    k_strict = int(np.sum(strict_mask))
    k_tie = int(np.sum(tie_mask))
    if k_tie < 1 or k_strict >= m:
        raise RuntimeError(
            f"Internal order-statistic boundary invariant failed: m={m}, "
            f"k_strict={k_strict}, k_tie={k_tie}, u_star={u_star}."
        )

    w_strict = (1.0 / m) if k_strict > 0 else 0.0
    rem_obs_mass = m - float(k_strict)
    w_tie = rem_obs_mass / (m * float(k_tie))

    weights_arr = np.zeros(n_obs, dtype=np.float64)
    if k_strict > 0:
        weights_arr[strict_mask] = w_strict
    weights_arr[tie_mask] = w_tie

    weight_sum = float(np.sum(weights_arr, dtype=np.float64))
    if not math.isclose(weight_sum, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError(f"Empirical tail weights failed to sum to 1.0; got {weight_sum:.16f}.")

    result = pd.Series(weights_arr, index=losses.index, name="empirical_tail_weight", dtype=float)
    result.attrs.update(
        {
            "confidence": conf,
            "alpha": alpha,
            "n_obs": n_obs,
            "expected_tail_obs_m": float(m),
            "fractional_tail_obs_remainder": float(m - math.floor(m + _FLOAT_INT_SNAP_TOL)),
            "boundary_order_stat_rank_from_worst": int(k_slots),
            "boundary_order_stat_loss": float(u_star),
            "empirical_var_inverted_cdf": float(var_inverted_cdf),
            "empirical_var_rank_ascending_1based": int(var_rank_1based),
            "k_strict": int(k_strict),
            "k_tie": int(k_tie),
            "n_positive_weights": int(k_strict + k_tie),
            "weight_per_strict_exceedance": float(w_strict),
            "weight_per_boundary_tie": float(w_tie),
            "weight_sum": float(weight_sum),
            "boundary_convention": "order_statistic_step_cdf_inverted_cdf",
            "tie_rule": "equal_split_across_boundary_ties",
        }
    )
    return result


def empirical_var_and_es(
    losses: pd.Series,
    confidence: float,
) -> tuple[float, float, pd.Series, dict[str, Any]]:
    """Compute historical VaR, historical ES, aligned tail weights, and quantile diagnostics.

    Conventions:
    - ``var_loss`` uses the empirical step-CDF quantile ``F_n^{-1}(c) = L_{(ceil(n * c))}``
      (Hyndman-Fan Type 1 / ``np.quantile(..., method='inverted_cdf')``), preserving
      negative/zero loss quantiles without ``abs()`` or zero flooring.
    - ``es_loss`` equals ``float(tail_weights @ losses)`` where ``tail_weights`` is produced
      by :func:`empirical_tail_weights`.
    - Also records ``var_linear_interpolated_diagnostic`` and ``naive_tail_mean_diagnostic``
      in the returned diagnostics dictionary so boundary differences when ``n * (1 - c)``
      is fractional or tied are transparent.
    """
    tail_w = empirical_tail_weights(losses, confidence)
    loss_arr = losses.to_numpy(dtype=np.float64)
    w_arr = tail_w.to_numpy(dtype=np.float64)

    var_loss = float(tail_w.attrs["empirical_var_inverted_cdf"])
    es_loss = float(np.dot(w_arr, loss_arr))

    # Numeric guard for tiny floating-point rounding when all tail observations equal var_loss
    if es_loss < var_loss and (var_loss - es_loss) <= 1e-15 * max(1.0, abs(var_loss)):
        es_loss = var_loss

    var_linear = float(np.quantile(loss_arr, float(tail_w.attrs["confidence"]), method="linear"))
    exceed_or_equal = loss_arr[loss_arr >= var_loss]
    naive_mean = float(np.mean(exceed_or_equal)) if len(exceed_or_equal) > 0 else float("nan")

    diag: dict[str, Any] = dict(tail_w.attrs)
    diag.update(
        {
            "var_quantile_method": "inverted_cdf",
            "var_loss_inverted_cdf": var_loss,
            "var_linear_interpolated_diagnostic": var_linear,
            "es_loss_tail_integral": es_loss,
            "naive_mean_losses_ge_var_diagnostic": naive_mean,
            "es_minus_naive_mean_diff": float(es_loss - naive_mean),
            "nonpositive_var_quantile": bool(var_loss <= 0.0),
            "nonpositive_es_quantile": bool(es_loss <= 0.0),
        }
    )
    return var_loss, es_loss, tail_w, diag
