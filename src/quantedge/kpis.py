"""Portfolio performance KPIs, CAPM regression diagnostics, and A1b real-return / income analytics (SOLO STEP 4 / A1b & A2).

Public interface frozen in D0:
- ``compute_kpis(portfolio_returns, benchmark_returns, market_returns, rf_daily) -> pd.DataFrame``

Supporting Step 4 analytical helpers:
- ``compare_rf_kpi_sensitivity(portfolio_returns, benchmark_returns, market_returns, rf_primary, rf_accrual_sensitivity) -> pd.DataFrame``
- ``compute_ex_post_real_return_metrics(portfolio_returns, cpi_monthly) -> pd.DataFrame``
- ``compute_trailing_12m_distribution_yields(split_adjusted_closes, distributions, *, window_calendar_days=365, min_coverage_calendar_days=365) -> tuple[pd.DataFrame, pd.DataFrame]``
- ``summarize_portfolio_distribution_income(weights_before, split_adjusted_closes, distributions, trailing_12m_yields=None) -> pd.DataFrame``
- ``run_portfolio_return_stationarity_diagnostics(portfolio_returns, *, series_label='portfolio', fixed_exposure_returns=None) -> pd.DataFrame``
- ``build_development_kpi_bundle(portfolio_paths, market_returns, rf_daily, *, benchmark_key='benchmark_60_40', rf_accrual_sensitivity=None, context_bundle=None) -> dict[str, Any]``

Mathematical & Governance Conventions:
1. **Date Alignment & Excess Returns:** All series in ``compute_kpis`` are aligned on their
   sorted intersection of valid trading sessions (``common_dates``). Daily excess simple returns
   are ``e_{p,t} = R_{p,t} - rf_daily_t`` and ``e_{m,t} = R_{m,t} - rf_daily_t``. If ``rf_daily``
   is ``None`` or has any missing observations on ``common_dates``, RF-dependent KPIs return
   ``value=None`` and ``status='unavailable'`` with an explicit reason; zero risk-free rates
   and future backfills are never fabricated.
2. **Annualization & Geometric vs. Arithmetic Distinction:** With ``A = 252`` trading days per year:
   - ``geometric_annual_return = prod_{t=1..N}(1 + R_{p,t})^(252 / N) - 1`` measures actual
     compounded multi-period wealth growth.
   - ``arithmetic_annual_return = 252 * mean(R_p)`` and ``annualized_volatility = sqrt(252) * std(R_p, ddof=1)``.
   - ``sharpe_ratio = (252 * mean(e_p)) / (sqrt(252) * std(e_p, ddof=1))`` uses arithmetic
     mean excess return and sample excess-return volatility (``ddof=1``).
3. **All-Observation Sortino Downside Deviation:** Daily shortfall relative to the daily
   risk-free target ``tau_t = rf_daily_t`` is ``d_t = min(0, R_{p,t} - rf_daily_t)``. Downside
   deviation is the annualized square root of the second lower partial moment across **all**
   ``N`` observations: ``downside_deviation = sqrt(252) * sqrt((1 / N) * sum_{t=1..N} d_t^2)``
   (never the standard deviation of negative observations alone).
4. **CAPM OLS & Forward Equilibrium Distinction:** Ex-post OLS regression
   ``e_{p,t} = alpha_daily + beta * e_{m,t} + eps_t`` against market proxy ``SPY`` yields
   realized ``capm_beta`` and linearly annualized ``jensen_alpha = 252 * alpha_daily``.
   Realized in-sample/ex-post alpha is distinct from forward equilibrium CAPM expected-return
   assumptions ``E[R_p] - R_f = beta * (E[R_m] - R_f)`` where forward ``alpha = 0``.
5. **Initial-Wealth Drawdown & Calmar:** Cumulative wealth ``W_t = prod_{s<=t}(1 + R_{p,s})``
   includes initial pre-entry wealth ``1.0`` inside the running peak
   ``Peak_t = max(1.0, max_{s<=t} W_s)``, so a first-day loss registers immediately in
   ``max_drawdown = min_t(W_t / Peak_t - 1) <= 0``, and ``calmar_ratio = geometric_annual_return / abs(max_drawdown)``.
6. **Bounded A1b Income & Real-Return Separation:** Cash distribution yields are computed on
   a compatible split-adjusted share basis (``auto_adjust=False`` ``Close`` and ``Dividends``)
   and reported **beside** total return (never added again to ``auto_adjust=True`` total returns).
   Monthly FRED ``CPIAUCSL`` deflates completed common-month wealth ratios strictly ex post.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from quantedge.contracts import KPI_COLUMNS, PortfolioPath
from quantedge.data import (
    ContextSnapshotBundle,
    compute_trailing_12m_distribution_series,
)
from quantedge.returns import expected_nyse_sessions, run_stationarity_diagnostics

ANNUALIZATION_DAYS: int = 252
ZERO_DENOMINATOR_TOL: float = 1e-12
NEAR_ZERO_BETA_TOL: float = 1e-4

CANONICAL_KPI_METRICS: tuple[str, ...] = (
    "geometric_annual_return",
    "arithmetic_annual_return",
    "annualized_volatility",
    "sharpe_ratio",
    "downside_deviation",
    "sortino_ratio",
    "capm_beta",
    "jensen_alpha",
    "treynor_ratio",
    "tracking_error",
    "information_ratio",
    "max_drawdown",
    "calmar_ratio",
)


def _validate_time_series(series: pd.Series, name: str) -> pd.Series:
    """Validate that ``series`` is a 1D pandas Series with an ascending unique DatetimeIndex."""
    if not isinstance(series, pd.Series):
        raise ValueError(f"{name} must be a pandas Series; got {type(series).__name__}.")
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError(f"{name} must have a pandas DatetimeIndex.")
    if not series.index.is_monotonic_increasing or not series.index.is_unique:
        raise ValueError(f"{name} index must be strictly ascending and unique.")
    coerced = pd.to_numeric(series, errors="coerce").astype(float)
    finite_Or_nan = np.isfinite(coerced.to_numpy(dtype=float)) | np.isnan(coerced.to_numpy(dtype=float))
    if not bool(finite_Or_nan.all()):
        raise ValueError(f"{name} contains non-finite (+/-inf) values.")
    return coerced


def _build_kpi_dataframe(
    rows: list[dict[str, Any]],
    attrs: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Construct a ``KPI_COLUMNS`` DataFrame preserving Python ``None`` for unavailable metrics."""
    df = pd.DataFrame(rows, columns=list(KPI_COLUMNS))
    df["value"] = pd.Series(
        [float(r["value"]) if r["value"] is not None else None for r in rows],
        index=df.index,
        dtype=object,
    )
    if attrs:
        df.attrs.update(attrs)
    return df


def compute_kpis(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    market_returns: pd.Series,
    rf_daily: pd.Series | None,
) -> pd.DataFrame:
    """Compute mandatory performance KPIs and CAPM regression metrics.

    Specification (SOLO STEP 4 / A2):
    - Output columns exactly match ``KPI_COLUMNS = ('metric', 'value', 'unit', 'status', 'note')``.
    - Metrics include geometric annual return, arithmetic annual return, annualized volatility,
      Sharpe, downside deviation and Sortino (over all observations vs daily ``rf_daily`` target),
      CAPM beta and Jensen alpha (vs ``SPY`` market proxy), Treynor, tracking error and
      Information Ratio (vs monthly-rebalanced 60/40 ``SPY/AGG`` benchmark), Max Drawdown
      (including initial wealth ``1.0``), and Calmar ratio.
    - If ``rf_daily`` is ``None`` or incomplete on aligned return dates, RF-dependent KPIs
      return ``value=None`` and ``status='unavailable'`` with explicit reasons rather than
      fabricating zeros or backfilling future risk-free quotes.
    """
    p_raw = _validate_time_series(portfolio_returns, "portfolio_returns")
    b_raw = _validate_time_series(benchmark_returns, "benchmark_returns")
    m_raw = _validate_time_series(market_returns, "market_returns")
    rf_raw = _validate_time_series(rf_daily, "rf_daily") if rf_daily is not None else None

    p_valid = p_raw.dropna()
    b_valid = b_raw.dropna()
    m_valid = m_raw.dropna()

    common_dates = p_valid.index.intersection(b_valid.index).intersection(m_valid.index)
    n_obs = int(len(common_dates))
    n_dropped = int(max(len(p_raw), len(b_raw), len(m_raw)) - n_obs)

    sample_start = str(common_dates[0].date()) if n_obs > 0 else None
    sample_end = str(common_dates[-1].date()) if n_obs > 0 else None
    sample_span = f"{sample_start}..{sample_end} (n={n_obs})" if n_obs > 0 else f"empty (n={n_obs})"
    align_suffix = (
        f"; {n_dropped} unaligned/NaN dates excluded across inputs" if n_dropped > 0 else ""
    )

    alignment_info: dict[str, Any] = {
        "sample_start": sample_start,
        "sample_end": sample_end,
        "n_obs": n_obs,
        "n_portfolio_raw": int(len(p_raw)),
        "n_benchmark_raw": int(len(b_raw)),
        "n_market_raw": int(len(m_raw)),
        "n_dropped_alignment": n_dropped,
        "annualization_days": ANNUALIZATION_DAYS,
    }

    if n_obs < 2:
        reason = (
            f"Insufficient aligned return observations ({sample_span}; minimum n=2 required)"
            f"{align_suffix}."
        )
        unit_map = {
            "geometric_annual_return": "annual_fraction",
            "arithmetic_annual_return": "annual_fraction",
            "annualized_volatility": "annual_fraction",
            "sharpe_ratio": "ratio",
            "downside_deviation": "annual_fraction",
            "sortino_ratio": "ratio",
            "capm_beta": "beta",
            "jensen_alpha": "annual_fraction",
            "treynor_ratio": "annual_fraction_per_unit_beta",
            "tracking_error": "annual_fraction",
            "information_ratio": "ratio",
            "max_drawdown": "fraction",
            "calmar_ratio": "ratio",
        }
        rows = [
            {
                "metric": metric,
                "value": None,
                "unit": unit_map[metric],
                "status": "unavailable",
                "note": reason,
            }
            for metric in CANONICAL_KPI_METRICS
        ]
        alignment_info["rf_status"] = "insufficient_sample"
        alignment_info["n_missing_rf"] = 0
        return _build_kpi_dataframe(rows, attrs={"alignment": alignment_info})

    p_arr = p_valid.reindex(common_dates).to_numpy(dtype=np.float64, copy=True)
    b_arr = b_valid.reindex(common_dates).to_numpy(dtype=np.float64, copy=True)
    m_arr = m_valid.reindex(common_dates).to_numpy(dtype=np.float64, copy=True)

    rf_available = False
    rf_unavail_reason = ""
    rf_arr: np.ndarray | None = None
    n_missing_rf = 0

    if rf_raw is None:
        rf_unavail_reason = (
            f"rf_daily is None on {sample_span}{align_suffix}; RF-dependent KPI marked "
            f"unavailable without fabricating zero risk-free rate."
        )
        alignment_info["rf_status"] = "missing_none"
    else:
        rf_aligned = rf_raw.reindex(common_dates)
        n_missing_rf = int(rf_aligned.isna().sum())
        if n_missing_rf > 0:
            rf_unavail_reason = (
                f"Incomplete rf_daily on {sample_span}{align_suffix}: {n_missing_rf}/{n_obs} "
                f"aligned dates are missing/NaN; no zero fill or future backfill applied."
            )
            alignment_info["rf_status"] = "incomplete_nan"
        else:
            rf_available = True
            rf_arr = rf_aligned.to_numpy(dtype=np.float64, copy=True)
            alignment_info["rf_status"] = "ok"
    alignment_info["n_missing_rf"] = n_missing_rf

    ann = float(ANNUALIZATION_DAYS)
    sqrt_ann = float(np.sqrt(ann))
    rows: list[dict[str, Any]] = []

    # 1. Geometric annual return & wealth trajectory
    gross_factors = 1.0 + p_arr
    geom_return: float | None = None
    wealth_arr: np.ndarray | None = None
    if bool(np.all(gross_factors > 0.0)):
        log_sum = float(np.sum(np.log1p(p_arr)))
        geom_return = float(np.expm1((ann / float(n_obs)) * log_sum))
        wealth_arr = np.cumprod(gross_factors)
        rows.append(
            {
                "metric": "geometric_annual_return",
                "value": geom_return,
                "unit": "annual_fraction",
                "status": "ok",
                "note": (
                    f"Sample {sample_span}{align_suffix}: compounded geometric return "
                    f"prod(1+R_p)^(252/N)-1 (terminal wealth={float(wealth_arr[-1]):.6f}); "
                    f"measures realized multi-period corpus growth net of volatility drag."
                ),
            }
        )
    else:
        rows.append(
            {
                "metric": "geometric_annual_return",
                "value": None,
                "unit": "annual_fraction",
                "status": "unavailable",
                "note": (
                    f"Sample {sample_span}{align_suffix}: one or more gross return factors "
                    f"(1 + R_p) <= 0; compounded geometric return is undefined."
                ),
            }
        )

    # 2. Arithmetic annual return
    mean_p = float(np.mean(p_arr))
    arith_return = float(ann * mean_p)
    rows.append(
        {
            "metric": "arithmetic_annual_return",
            "value": arith_return,
            "unit": "annual_fraction",
            "status": "ok",
            "note": (
                f"Sample {sample_span}{align_suffix}: linearly annualized arithmetic mean "
                f"252 * mean(R_p); exceeds geometric return by ~0.5*sigma^2 volatility drag "
                f"and is not a guaranteed compounded payout rate."
            ),
        }
    )

    # 3. Annualized volatility (ddof=1)
    std_p_daily = float(np.std(p_arr, ddof=1))
    vol_ann = float(sqrt_ann * std_p_daily)
    rows.append(
        {
            "metric": "annualized_volatility",
            "value": vol_ann,
            "unit": "annual_fraction",
            "status": "ok",
            "note": (
                f"Sample {sample_span}{align_suffix}: sqrt(252) * std(R_p, ddof=1); "
                f"measures total symmetric return dispersion (both upside and downside)."
            ),
        }
    )

    # 4-9. RF-dependent KPIs: Sharpe, Downside Deviation, Sortino, CAPM Beta, Jensen Alpha, Treynor
    capm_reg_info: dict[str, Any] = {}
    extra_diag: dict[str, Any] = {}

    if not rf_available or rf_arr is None:
        for metric, unit in (
            ("sharpe_ratio", "ratio"),
            ("downside_deviation", "annual_fraction"),
            ("sortino_ratio", "ratio"),
            ("capm_beta", "beta"),
            ("jensen_alpha", "annual_fraction"),
            ("treynor_ratio", "annual_fraction_per_unit_beta"),
        ):
            rows.append(
                {
                    "metric": metric,
                    "value": None,
                    "unit": unit,
                    "status": "unavailable",
                    "note": rf_unavail_reason,
                }
            )
    else:
        excess_p = p_arr - rf_arr
        mean_ep = float(np.mean(excess_p))
        ann_excess_p = float(ann * mean_ep)
        std_ep_daily = float(np.std(excess_p, ddof=1))
        vol_ep_ann = float(sqrt_ann * std_ep_daily)
        mean_rf_ann = float(ann * np.mean(rf_arr))

        # 4. Sharpe Ratio
        if std_ep_daily <= ZERO_DENOMINATOR_TOL:
            rows.append(
                {
                    "metric": "sharpe_ratio",
                    "value": None,
                    "unit": "ratio",
                    "status": "unavailable",
                    "note": (
                        f"Sample {sample_span}{align_suffix}: zero or near-zero excess-return "
                        f"volatility (std(R_p - rf_daily, ddof=1)={std_ep_daily:.3e} <= "
                        f"{ZERO_DENOMINATOR_TOL:.1e}); Sharpe ratio denominator is zero."
                    ),
                }
            )
        else:
            sharpe_val = float(ann_excess_p / vol_ep_ann)
            sharpe_raw_vol = float(ann_excess_p / vol_ann) if std_p_daily > ZERO_DENOMINATOR_TOL else None
            extra_diag["sharpe_raw_vol_denominator"] = sharpe_raw_vol
            extra_diag["annualized_mean_rf"] = mean_rf_ann
            extra_diag["annualized_excess_return"] = ann_excess_p
            rows.append(
                {
                    "metric": "sharpe_ratio",
                    "value": sharpe_val,
                    "unit": "ratio",
                    "status": "ok",
                    "note": (
                        f"Sample {sample_span}{align_suffix}: sqrt(252) * mean(R_p - rf_daily) / "
                        f"std(R_p - rf_daily, ddof=1) using arithmetic excess mean "
                        f"({ann_excess_p:.4%}/yr over mean RF {mean_rf_ann:.4%}/yr); measures "
                        f"excess return per unit of total volatility."
                    ),
                }
            )

        # 5 & 6. Downside Deviation (all observations vs daily target rf_daily) & Sortino Ratio
        downside_diff_rf = np.minimum(0.0, excess_p)
        dd_daily_rf = float(np.sqrt(np.mean(downside_diff_rf * downside_diff_rf)))
        dd_ann_rf = float(sqrt_ann * dd_daily_rf)
        dd_ann_rf_ddof1 = float(sqrt_ann * np.sqrt(np.sum(downside_diff_rf * downside_diff_rf) / float(n_obs - 1)))

        downside_diff_zero = np.minimum(0.0, p_arr)
        dd_daily_zero = float(np.sqrt(np.mean(downside_diff_zero * downside_diff_zero)))
        dd_ann_zero = float(sqrt_ann * dd_daily_zero)

        n_down_rf = int(np.sum(excess_p < 0.0))
        n_down_zero = int(np.sum(p_arr < 0.0))
        extra_diag.update(
            {
                "downside_target_convention": "rf_daily_t (daily risk-free rate)",
                "downside_divisor_convention": "all_observations_N (LPM2 root-mean-square over all N sessions)",
                "downside_deviation_ddof1": dd_ann_rf_ddof1,
                "sortino_ddof1": float(ann_excess_p / dd_ann_rf_ddof1) if dd_ann_rf_ddof1 > ZERO_DENOMINATOR_TOL else None,
                "downside_deviation_zero_target": dd_ann_zero,
                "sortino_zero_target": float(ann_excess_p / dd_ann_zero) if dd_ann_zero > ZERO_DENOMINATOR_TOL else None,
                "n_downside_obs_below_rf": n_down_rf,
                "n_downside_obs_below_zero": n_down_zero,
            }
        )

        rows.append(
            {
                "metric": "downside_deviation",
                "value": dd_ann_rf,
                "unit": "annual_fraction",
                "status": "ok",
                "note": (
                    f"Sample {sample_span}{align_suffix}: sqrt(252 * (1/N) * sum(min(0, R_p - rf_daily)^2)) "
                    f"across all N={n_obs} sessions ({n_down_rf} sessions below daily RF target; "
                    f"zero-target DD={dd_ann_zero:.4%}); isolates harmful below-target dispersion."
                ),
            }
        )

        if dd_daily_rf <= ZERO_DENOMINATOR_TOL:
            rows.append(
                {
                    "metric": "sortino_ratio",
                    "value": None,
                    "unit": "ratio",
                    "status": "unavailable",
                    "note": (
                        f"Sample {sample_span}{align_suffix}: zero or near-zero downside deviation "
                        f"(dd_daily={dd_daily_rf:.3e} <= {ZERO_DENOMINATOR_TOL:.1e}; all sessions >= "
                        f"daily RF target); Sortino ratio denominator is zero."
                    ),
                }
            )
        else:
            sortino_val = float(ann_excess_p / dd_ann_rf)
            zero_target_sortino_val = extra_diag.get("sortino_zero_target")
            zero_target_sortino_str = (
                f"{zero_target_sortino_val:.4f}"
                if zero_target_sortino_val is not None
                else "unavailable (all raw returns >= 0)"
            )
            rows.append(
                {
                    "metric": "sortino_ratio",
                    "value": sortino_val,
                    "unit": "ratio",
                    "status": "ok",
                    "note": (
                        f"Sample {sample_span}{align_suffix}: 252 * mean(R_p - rf_daily) / "
                        f"downside_deviation over all N={n_obs} sessions (daily target=rf_daily; "
                        f"zero-target Sortino={zero_target_sortino_str}); "
                        f"penalizes downside shortfall without penalizing upside gains."
                    ),
                }
            )

        # 7, 8, 9. CAPM Beta, Jensen Alpha, Treynor Ratio vs SPY market proxy
        if n_obs < 3:
            capm_reason = (
                f"Sample {sample_span}{align_suffix}: insufficient observations (n={n_obs} < 3) "
                f"for 2-parameter CAPM OLS regression with intercept."
            )
            for metric, unit in (
                ("capm_beta", "beta"),
                ("jensen_alpha", "annual_fraction"),
                ("treynor_ratio", "annual_fraction_per_unit_beta"),
            ):
                rows.append(
                    {
                        "metric": metric,
                        "value": None,
                        "unit": unit,
                        "status": "unavailable",
                        "note": capm_reason,
                    }
                )
        else:
            excess_m = m_arr - rf_arr
            mean_em = float(np.mean(excess_m))
            std_em_daily = float(np.std(excess_m, ddof=1))

            if std_em_daily <= ZERO_DENOMINATOR_TOL:
                deg_reason = (
                    f"Sample {sample_span}{align_suffix}: zero or near-zero market (SPY) excess-return "
                    f"volatility (std(R_m - rf_daily, ddof=1)={std_em_daily:.3e} <= "
                    f"{ZERO_DENOMINATOR_TOL:.1e}); CAPM OLS regression is degenerate."
                )
                for metric, unit in (
                    ("capm_beta", "beta"),
                    ("jensen_alpha", "annual_fraction"),
                    ("treynor_ratio", "annual_fraction_per_unit_beta"),
                ):
                    rows.append(
                        {
                            "metric": metric,
                            "value": None,
                            "unit": unit,
                            "status": "unavailable",
                            "note": deg_reason,
                        }
                    )
            else:
                xm = excess_m - mean_em
                yp = excess_p - mean_ep
                s_xx = float(np.dot(xm, xm))
                s_xy = float(np.dot(xm, yp))
                s_yy = float(np.dot(yp, yp))

                beta_val = float(s_xy / s_xx)
                alpha_daily = float(mean_ep - beta_val * mean_em)
                alpha_ann = float(ann * alpha_daily)
                alpha_ann_compound = (
                    float(np.expm1(ann * np.log1p(alpha_daily))) if alpha_daily > -1.0 else None
                )

                residuals = excess_p - (alpha_daily + beta_val * excess_m)
                df_resid = int(n_obs - 2)
                rss = float(np.dot(residuals, residuals))
                s2_eps = float(rss / float(df_resid))
                s_eps = float(np.sqrt(max(0.0, s2_eps)))
                r_squared = float(1.0 - rss / s_yy) if s_yy > ZERO_DENOMINATOR_TOL else 0.0
                r_squared = float(np.clip(r_squared, 0.0, 1.0))

                se_beta = float(np.sqrt(max(0.0, s2_eps / s_xx)))
                se_alpha_daily = float(
                    np.sqrt(max(0.0, s2_eps * (1.0 / float(n_obs) + (mean_em * mean_em) / s_xx)))
                )
                se_alpha_ann = float(ann * se_alpha_daily)

                if se_beta > 1e-15:
                    t_beta = float(beta_val / se_beta)
                    p_beta = float(2.0 * stats.t.sf(abs(t_beta), df=df_resid))
                else:
                    t_beta = None
                    p_beta = None

                if se_alpha_daily > 1e-15:
                    t_alpha = float(alpha_daily / se_alpha_daily)
                    p_alpha = float(2.0 * stats.t.sf(abs(t_alpha), df=df_resid))
                else:
                    t_alpha = None
                    p_alpha = None

                capm_reg_info = {
                    "market_proxy": "SPY",
                    "n_obs": n_obs,
                    "df_resid": df_resid,
                    "beta": beta_val,
                    "beta_se": se_beta,
                    "beta_t_stat": t_beta,
                    "beta_p_value": p_beta,
                    "alpha_daily": alpha_daily,
                    "alpha_annual_linear": alpha_ann,
                    "alpha_annual_compound": alpha_ann_compound,
                    "alpha_se_daily": se_alpha_daily,
                    "alpha_se_annual_linear": se_alpha_ann,
                    "alpha_t_stat": t_alpha,
                    "alpha_p_value": p_alpha,
                    "r_squared": r_squared,
                    "residual_std_daily": s_eps,
                    "annualized_market_excess_return": float(ann * mean_em),
                }

                t_beta_str = f"t={t_beta:.2f}, p={p_beta:.4g}" if t_beta is not None else "exact linear fit (SE=0)"
                t_alpha_str = f"t={t_alpha:.2f}, p={p_alpha:.4g}" if t_alpha is not None else "exact linear fit (SE=0)"

                rows.append(
                    {
                        "metric": "capm_beta",
                        "value": beta_val,
                        "unit": "beta",
                        "status": "ok",
                        "note": (
                            f"Sample {sample_span}{align_suffix}: OLS slope Cov(e_p, e_SPY)/Var(e_SPY) "
                            f"with intercept ({t_beta_str}, R^2={r_squared:.4f}); measures systematic "
                            f"sensitivity to US equity market excess returns."
                        ),
                    }
                )
                rows.append(
                    {
                        "metric": "jensen_alpha",
                        "value": alpha_ann,
                        "unit": "annual_fraction",
                        "status": "ok",
                        "note": (
                            f"Sample {sample_span}{align_suffix}: linearly annualized OLS intercept "
                            f"252 * alpha_daily ({t_alpha_str}; i.i.d. OLS SE assumes homoskedastic "
                            f"residuals). Realized regression intercept, distinct from forward CAPM "
                            f"equilibrium expected return where alpha=0."
                        ),
                    }
                )

                if abs(beta_val) <= NEAR_ZERO_BETA_TOL:
                    rows.append(
                        {
                            "metric": "treynor_ratio",
                            "value": None,
                            "unit": "annual_fraction_per_unit_beta",
                            "status": "unavailable",
                            "note": (
                                f"Sample {sample_span}{align_suffix}: near-zero CAPM beta "
                                f"(beta={beta_val:.6g}, |beta| <= {NEAR_ZERO_BETA_TOL:.1e}); "
                                f"Treynor ratio denominator is near zero and unstable."
                            ),
                        }
                    )
                else:
                    treynor_val = float(ann_excess_p / beta_val)
                    treynor_status = "warning" if beta_val < 0.0 else "ok"
                    beta_sign_note = (
                        "WARNING: negative CAPM beta inverts Treynor sign; inspect excess return and beta separately. "
                        if beta_val < 0.0
                        else ""
                    )
                    rows.append(
                        {
                            "metric": "treynor_ratio",
                            "value": treynor_val,
                            "unit": "annual_fraction_per_unit_beta",
                            "status": treynor_status,
                            "note": (
                                f"Sample {sample_span}{align_suffix}: {beta_sign_note}252 * mean(R_p - rf_daily) "
                                f"/ capm_beta (beta={beta_val:.4f}); measures annualized excess return per unit "
                                f"of systematic SPY market beta."
                            ),
                        }
                    )

    # 10 & 11. Tracking Error & Information Ratio vs shared monthly 60/40 benchmark
    active_arr = p_arr - b_arr
    mean_active = float(np.mean(active_arr))
    ann_active = float(ann * mean_active)
    std_active_daily = float(np.std(active_arr, ddof=1))
    te_ann = float(sqrt_ann * std_active_daily)

    rows.append(
        {
            "metric": "tracking_error",
            "value": te_ann,
            "unit": "annual_fraction",
            "status": "ok",
            "note": (
                f"Sample {sample_span}{align_suffix}: sqrt(252) * std(R_p - R_b, ddof=1) against "
                f"shared monthly-rebalanced 60/40 SPY/AGG benchmark (active mean={ann_active:.4%}/yr); "
                f"quantifies active return dispersion relative to the reference benchmark."
            ),
        }
    )

    if std_active_daily <= ZERO_DENOMINATOR_TOL:
        rows.append(
            {
                "metric": "information_ratio",
                "value": None,
                "unit": "ratio",
                "status": "unavailable",
                "note": (
                    f"Sample {sample_span}{align_suffix}: zero or near-zero tracking error against "
                    f"benchmark (std(R_p - R_b, ddof=1)={std_active_daily:.3e} <= "
                    f"{ZERO_DENOMINATOR_TOL:.1e}); Information Ratio denominator is zero."
                ),
            }
        )
    else:
        ir_val = float(ann_active / te_ann)
        rows.append(
            {
                "metric": "information_ratio",
                "value": ir_val,
                "unit": "ratio",
                "status": "ok",
                "note": (
                    f"Sample {sample_span}{align_suffix}: 252 * mean(R_p - R_b) / tracking_error "
                    f"(active mean={ann_active:.4%}/yr, TE={te_ann:.4%}/yr); measures consistency of "
                    f"active performance relative to the 60/40 benchmark."
                ),
            }
        )

    # 12 & 13. Initial-Wealth-Inclusive Max Drawdown & Calmar Ratio
    drawdown_info: dict[str, Any] = {}
    if wealth_arr is None:
        for metric, unit in (("max_drawdown", "fraction"), ("calmar_ratio", "ratio")):
            rows.append(
                {
                    "metric": metric,
                    "value": None,
                    "unit": unit,
                    "status": "unavailable",
                    "note": (
                        f"Sample {sample_span}{align_suffix}: wealth path contains non-positive "
                        f"gross factor (1 + R_p <= 0); drawdown/Calmar marked unavailable."
                    ),
                }
            )
    else:
        running_peak = np.maximum(1.0, np.maximum.accumulate(wealth_arr))
        dd_series = wealth_arr / running_peak - 1.0
        trough_pos = int(np.argmin(dd_series))
        max_dd = float(dd_series[trough_pos])
        trough_date = str(common_dates[trough_pos].date())

        # Locate the peak date at or before trough_pos (or 'initial_wealth_1.0' if peak is 1.0 before any gain)
        prefix_wealth = wealth_arr[: trough_pos + 1]
        max_prefix_wealth = float(np.max(prefix_wealth))
        if max_prefix_wealth <= 1.0 + 1e-15:
            peak_date = f"initial_wealth_1.0 (before {common_dates[0].date()})"
        else:
            peak_pos = int(np.argmax(prefix_wealth))
            peak_date = str(common_dates[peak_pos].date())

        drawdown_info = {
            "max_drawdown": max_dd,
            "peak_reference": peak_date,
            "trough_date": trough_date,
            "final_wealth": float(wealth_arr[-1]),
            "includes_initial_wealth_1_0": True,
        }

        rows.append(
            {
                "metric": "max_drawdown",
                "value": max_dd,
                "unit": "fraction",
                "status": "ok",
                "note": (
                    f"Sample {sample_span}{align_suffix}: min_t(W_t / max(1.0, max_{{s<=t}} W_s) - 1) "
                    f"including initial wealth 1.0 (peak={peak_date}, trough={trough_date}); "
                    f"worst cumulative peak-to-trough loss experienced by the endowment."
                ),
            }
        )

        if abs(max_dd) <= ZERO_DENOMINATOR_TOL or geom_return is None:
            rows.append(
                {
                    "metric": "calmar_ratio",
                    "value": None,
                    "unit": "ratio",
                    "status": "unavailable",
                    "note": (
                        f"Sample {sample_span}{align_suffix}: zero or near-zero maximum drawdown "
                        f"(|max_drawdown|={abs(max_dd):.3e} <= {ZERO_DENOMINATOR_TOL:.1e}); "
                        f"Calmar ratio denominator is zero."
                    ),
                }
            )
        else:
            calmar_val = float(geom_return / abs(max_dd))
            rows.append(
                {
                    "metric": "calmar_ratio",
                    "value": calmar_val,
                    "unit": "ratio",
                    "status": "ok",
                    "note": (
                        f"Sample {sample_span}{align_suffix}: geometric_annual_return / "
                        f"abs(max_drawdown) ({geom_return:.4%}/yr / {abs(max_dd):.4%}); "
                        f"measures compounded annual growth per unit of worst historical drawdown."
                    ),
                }
            )

    conventions = {
        "annualization_days": ANNUALIZATION_DAYS,
        "excess_return_definition": "e_{p,t} = R_{p,t} - rf_daily_t (aligned trading sessions, no zero fill or future backfill)",
        "sharpe_convention": "sqrt(252) * mean(e_p) / std(e_p, ddof=1) (arithmetic excess mean over excess-return volatility)",
        "sortino_downside_target": "rf_daily_t (daily risk-free rate)",
        "sortino_downside_deviation": "sqrt(252 * (1 / N) * sum_{t=1..N} min(0, R_{p,t} - rf_daily_t)^2) over ALL N observations",
        "capm_ols_convention": "OLS with intercept against SPY excess returns; alpha_annual = 252 * alpha_daily",
        "information_ratio_convention": "252 * mean(R_p - R_b) / (sqrt(252) * std(R_p - R_b, ddof=1)) vs shared monthly 60/40 path",
        "drawdown_convention": "min_t(W_t / max(1.0, max_{s<=t} W_s) - 1) explicitly including initial pre-entry wealth 1.0",
    }

    return _build_kpi_dataframe(
        rows,
        attrs={
            "alignment": alignment_info,
            "conventions": conventions,
            "capm_regression": capm_reg_info,
            "drawdown_summary": drawdown_info,
            "diagnostics": extra_diag,
        },
    )


def compare_rf_kpi_sensitivity(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    market_returns: pd.Series,
    rf_primary: pd.Series,
    rf_accrual_sensitivity: pd.Series,
) -> pd.DataFrame:
    """Compare RF-dependent KPIs under primary ``r3`` (``/252``) vs. 91-day bill accrual sensitivity.

    Both ``rf_primary`` and ``rf_accrual_sensitivity`` are daily approximations of 3-month
    Treasury bill quotes selected causally under ``r3_release_evidence``; neither is an
    exact realized daily Treasury portfolio return.
    """
    kpi_prim = compute_kpis(portfolio_returns, benchmark_returns, market_returns, rf_primary).set_index("metric")
    kpi_accr = compute_kpis(
        portfolio_returns,
        benchmark_returns,
        market_returns,
        rf_accrual_sensitivity,
    ).set_index("metric")

    rf_metrics = (
        "sharpe_ratio",
        "downside_deviation",
        "sortino_ratio",
        "capm_beta",
        "jensen_alpha",
        "treynor_ratio",
    )
    rows: list[dict[str, Any]] = []
    prim_mean_rf = kpi_prim.attrs.get("diagnostics", {}).get("annualized_mean_rf")
    accr_mean_rf = kpi_accr.attrs.get("diagnostics", {}).get("annualized_mean_rf")
    if prim_mean_rf is not None and accr_mean_rf is not None:
        diff_rf = float(accr_mean_rf - prim_mean_rf)
        rows.append(
            {
                "metric": "annualized_mean_rf_proxy",
                "primary_r3_value": float(prim_mean_rf),
                "accrual_91d_value": float(accr_mean_rf),
                "difference": diff_rf,
                "abs_difference": abs(diff_rf),
                "unit": "annual_fraction",
                "status": "ok",
                "note": (
                    "252 * mean(rf_daily): primary /252 trading-day division vs 91-day bill "
                    "calendar-day accrual sensitivity on identical r3 selected DTB3 quotes."
                ),
            }
        )

    for m_name in rf_metrics:
        v_p = kpi_prim.loc[m_name, "value"]
        v_a = kpi_accr.loc[m_name, "value"]
        st_p = str(kpi_prim.loc[m_name, "status"])
        st_a = str(kpi_accr.loc[m_name, "status"])
        unit = str(kpi_prim.loc[m_name, "unit"])
        if v_p is not None and v_a is not None:
            diff = float(v_a) - float(v_p)
            rows.append(
                {
                    "metric": m_name,
                    "primary_r3_value": float(v_p),
                    "accrual_91d_value": float(v_a),
                    "difference": diff,
                    "abs_difference": abs(diff),
                    "unit": unit,
                    "status": "ok" if (st_p == "ok" and st_a == "ok") else "warning",
                    "note": (
                        "Sensitivity of RF-dependent KPI to 91-day bill calendar-day accrual vs "
                        "primary /252 conversion on identical aligned dates."
                    ),
                }
            )
        else:
            rows.append(
                {
                    "metric": m_name,
                    "primary_r3_value": v_p,
                    "accrual_91d_value": v_a,
                    "difference": None,
                    "abs_difference": None,
                    "unit": unit,
                    "status": "unavailable",
                    "note": f"Unavailable under primary ({st_p}) or accrual sensitivity ({st_a}).",
                }
            )
    return pd.DataFrame(rows)


def _contiguous_period_runs(periods: pd.PeriodIndex) -> list[pd.PeriodIndex]:
    """Partition a sorted monthly ``PeriodIndex`` into maximal contiguous calendar-month blocks."""
    if len(periods) == 0:
        return []
    sorted_p = periods.sort_values()
    runs: list[list[pd.Period]] = [[sorted_p[0]]]
    for p in sorted_p[1:]:
        if int((p - runs[-1][-1]).n) == 1:
            runs[-1].append(p)
        else:
            runs.append([p])
    return [pd.PeriodIndex(r, freq="M") for r in runs]


def compute_ex_post_real_return_metrics(
    portfolio_returns: pd.Series,
    cpi_monthly: pd.DataFrame | pd.Series,
    *,
    interval_policy: str = "endpoint_cpi_contiguous_nominal",
) -> pd.DataFrame:
    """Compute explicitly ex-post common-completed-month purchasing-power metrics using FRED ``CPIAUCSL``.

    Rules (SOLO STEP 4 / A1b & A2 + R2 review hardening):
    - Identifies calendar months in ``portfolio_returns`` that match **exact** expected NYSE
      trading session dates of that month (`obs_dates_m.equals(exp_dates_m)` — never row-count
      equality alone, so a missing NYSE session replaced by a non-NYSE date is rejected).
    - Tracks every excluded month and its reason, explicitly including:
      1. Partial or non-NYSE-mismatched portfolio months (`partial_portfolio_months_excluded`),
      2. Complete NYSE months missing a published current-month `CPIAUCSL` print (`missing_current_cpi_months_excluded`),
      3. Complete NYSE months whose immediately preceding baseline month `m - 1` is missing
         `CPIAUCSL` (`missing_prior_cpi_months_excluded`, e.g. `2010-03` when `2010-02` is missing,
         or `2025-11` when `2025-10` is missing), both reported in `unreleased_or_missing_cpi_months_excluded`.
    - Never stitches disconnected monthly CPI/real factors across an internal CPI gap and labels
      their product a full start/end wealth or CPI ratio. Supports two performance-independent
      interval policies:
      * ``interval_policy='endpoint_cpi_contiguous_nominal'`` (default): selects the longest
        contiguous calendar-month block of complete NYSE portfolio months ``[m_start, m_end]``
        with published baseline ``CPI_{m_start - 1}`` and endpoint ``CPI_{m_end}`` (tie-broken by
        latest calendar end, independent of portfolio performance), compounding complete nominal
        returns across all ``N`` contiguous months and deflating by the exact endpoint CPI ratio
        ``CPI_{m_end} / CPI_{m_start - 1}`` over ``N / 12`` years while reporting any unavailable
        intermediate 1-month CPI-change months separately (with ``status='warning'`` when internal
        CPI prints are missing).
      * ``interval_policy='longest_contiguous_cpi_block'``: selects the longest contiguous
        calendar-month block of complete NYSE portfolio months in which every single month ``m``
        has both ``CPI_m`` and ``CPI_{m - 1}`` (tie-broken by latest calendar end, independent of
        portfolio performance).
    - Records any scattered single-month product strictly as a diagnostic labelled
      ``scattered_noncontiguous_monthly_factors_not_an_endpoint_ratio``.
    """
    if interval_policy not in ("endpoint_cpi_contiguous_nominal", "longest_contiguous_cpi_block"):
        raise ValueError(
            "interval_policy must be 'endpoint_cpi_contiguous_nominal' or 'longest_contiguous_cpi_block'; "
            f"got {interval_policy!r}."
        )

    p_clean = _validate_time_series(portfolio_returns, "portfolio_returns").dropna()
    if len(p_clean) < 2:
        rows = [
            {
                "metric": m,
                "value": None,
                "unit": u,
                "status": "unavailable",
                "note": f"Insufficient portfolio return observations (n={len(p_clean)} < 2).",
            }
            for m, u in (
                ("ex_post_nominal_annual_return_common_months", "annual_fraction"),
                ("ex_post_cpi_annual_inflation_common_months", "annual_fraction"),
                ("ex_post_real_annual_return_common_months", "annual_fraction"),
                ("ex_post_real_wealth_multiple_common_months", "multiple"),
            )
        ]
        return _build_kpi_dataframe(rows)

    if isinstance(cpi_monthly, pd.DataFrame):
        if "month_period" in cpi_monthly.columns and "cpi_index" in cpi_monthly.columns:
            cpi_series = pd.Series(
                pd.to_numeric(cpi_monthly["cpi_index"], errors="coerce").to_numpy(dtype=float),
                index=pd.PeriodIndex(cpi_monthly["month_period"].astype(str), freq="M"),
            ).dropna()
        elif "cpi_index" in cpi_monthly.columns:
            dt_idx = pd.to_datetime(cpi_monthly.index)
            cpi_series = pd.Series(
                pd.to_numeric(cpi_monthly["cpi_index"], errors="coerce").to_numpy(dtype=float),
                index=dt_idx.to_period("M"),
            ).dropna()
        else:
            raise ValueError("cpi_monthly DataFrame must contain 'cpi_index' (and optionally 'month_period').")
    elif isinstance(cpi_monthly, pd.Series):
        if isinstance(cpi_monthly.index, pd.PeriodIndex):
            p_idx = cpi_monthly.index.asfreq("M")
        else:
            p_idx = pd.to_datetime(cpi_monthly.index).to_period("M")
        cpi_series = pd.Series(
            pd.to_numeric(cpi_monthly, errors="coerce").to_numpy(dtype=float),
            index=p_idx,
        ).dropna()
    else:
        raise ValueError("cpi_monthly must be a pandas DataFrame or Series.")

    cpi_series = cpi_series[~cpi_series.index.duplicated(keep="last")].sort_index()
    if (cpi_series <= 0.0).any():
        raise ValueError("cpi_monthly index values must be strictly positive.")

    # Determine which calendar months in portfolio_returns match the EXACT expected NYSE session dates
    start_cal = p_clean.index[0].replace(day=1)
    end_cal = (p_clean.index[-1].to_period("M").end_time).normalize()
    all_nyse = expected_nyse_sessions(start_cal, end_cal)
    nyse_periods = all_nyse.to_period("M")

    p_periods = p_clean.index.to_period("M")
    monthly_gross = (1.0 + p_clean).groupby(p_periods).prod()
    all_port_months = monthly_gross.index.sort_values()

    complete_port_list: list[pd.Period] = []
    partial_port_months: list[str] = []
    excluded_months_by_reason: dict[str, dict[str, Any]] = {}

    for m in all_port_months:
        exp_dates_m = pd.DatetimeIndex(all_nyse[nyse_periods == m])
        obs_dates_m = pd.DatetimeIndex(p_clean.index[p_periods == m])
        if len(exp_dates_m) > 0 and obs_dates_m.equals(exp_dates_m):
            complete_port_list.append(m)
        else:
            m_str = str(m)
            partial_port_months.append(m_str)
            missing_nyse_dates = [str(d.date()) for d in exp_dates_m.difference(obs_dates_m)]
            unexpected_dates = [str(d.date()) for d in obs_dates_m.difference(exp_dates_m)]
            reason_code = (
                "non_nyse_or_mismatched_session_dates"
                if (len(obs_dates_m) == len(exp_dates_m) and len(unexpected_dates) > 0)
                else "incomplete_nyse_session_coverage"
            )
            excluded_months_by_reason[m_str] = {
                "reason": reason_code,
                "observed_sessions": int(len(obs_dates_m)),
                "expected_nyse_sessions": int(len(exp_dates_m)),
                "missing_nyse_dates": missing_nyse_dates,
                "unexpected_non_nyse_dates": unexpected_dates,
            }

    complete_port_months = pd.PeriodIndex(complete_port_list, freq="M")

    # Track CPI availability for every complete NYSE portfolio month (current month m AND prior month m - 1)
    missing_current_cpi_months: list[str] = []
    missing_prior_cpi_months: list[str] = []
    single_month_valid_list: list[pd.Period] = []

    for m in complete_port_months:
        m_str = str(m)
        has_curr = bool(m in cpi_series.index)
        has_prev = bool((m - 1) in cpi_series.index)
        if not has_curr:
            missing_current_cpi_months.append(m_str)
            excluded_months_by_reason[m_str] = {
                "reason": "missing_or_unreleased_current_month_cpi",
                "current_cpi_present": False,
                "prior_cpi_present": has_prev,
                "prior_month": str(m - 1),
            }
        elif not has_prev:
            missing_prior_cpi_months.append(m_str)
            excluded_months_by_reason[m_str] = {
                "reason": "missing_prior_month_cpi_baseline",
                "current_cpi_present": True,
                "prior_cpi_present": False,
                "missing_prior_month": str(m - 1),
            }
        else:
            single_month_valid_list.append(m)

    single_month_valid_periods = pd.PeriodIndex(single_month_valid_list, freq="M")
    unreleased_or_missing_cpi_months = [
        str(m)
        for m in complete_port_months
        if (m not in cpi_series.index) or ((m - 1) not in cpi_series.index)
    ]

    # 1. Longest contiguous block of single-month valid CPI-change months (performance-independent)
    contiguous_cpi_runs = _contiguous_period_runs(single_month_valid_periods)
    best_cpi_block = (
        max(contiguous_cpi_runs, key=lambda r: (len(r), r[-1]))
        if len(contiguous_cpi_runs) > 0
        else pd.PeriodIndex([], freq="M")
    )

    # 2. Longest contiguous block of complete NYSE portfolio months with valid start-baseline and end CPI
    contiguous_port_runs = _contiguous_period_runs(complete_port_months)
    candidate_nominal_spans: list[pd.PeriodIndex] = []
    for run in contiguous_port_runs:
        valid_starts = [i for i, m in enumerate(run) if (m - 1) in cpi_series.index]
        valid_ends = [j for j, m in enumerate(run) if m in cpi_series.index]
        if valid_starts and valid_ends and valid_starts[0] <= valid_ends[-1]:
            candidate_nominal_spans.append(run[valid_starts[0] : valid_ends[-1] + 1])

    best_nominal_span = (
        max(candidate_nominal_spans, key=lambda r: (len(r), r[-1]))
        if len(candidate_nominal_spans) > 0
        else pd.PeriodIndex([], freq="M")
    )

    selected_months = (
        best_nominal_span
        if interval_policy == "endpoint_cpi_contiguous_nominal"
        else best_cpi_block
    )

    if len(selected_months) == 0:
        reason = (
            "No completed NYSE portfolio calendar months with valid baseline and endpoint "
            "published CPIAUCSL observations."
        )
        rows = [
            {
                "metric": m,
                "value": None,
                "unit": u,
                "status": "unavailable",
                "note": reason,
            }
            for m, u in (
                ("ex_post_nominal_annual_return_common_months", "annual_fraction"),
                ("ex_post_cpi_annual_inflation_common_months", "annual_fraction"),
                ("ex_post_real_annual_return_common_months", "annual_fraction"),
                ("ex_post_real_wealth_multiple_common_months", "multiple"),
            )
        ]
        return _build_kpi_dataframe(
            rows,
            attrs={
                "common_months_summary": {
                    "interval_policy": interval_policy,
                    "n_common_complete_months": 0,
                    "partial_portfolio_months_excluded": partial_port_months,
                    "missing_current_cpi_months_excluded": missing_current_cpi_months,
                    "missing_prior_cpi_months_excluded": missing_prior_cpi_months,
                    "unreleased_or_missing_cpi_months_excluded": unreleased_or_missing_cpi_months,
                    "excluded_months_by_reason": excluded_months_by_reason,
                }
            },
        )

    # Record any valid single-month CPI-change months excluded because they fall outside the selected contiguous block
    selected_set = set(selected_months)
    outside_selected_block_months: list[str] = []
    for m in single_month_valid_periods:
        if m not in selected_set:
            m_str = str(m)
            outside_selected_block_months.append(m_str)
            if m_str not in excluded_months_by_reason:
                excluded_months_by_reason[m_str] = {
                    "reason": "excluded_outside_selected_contiguous_block",
                    "selected_interval_policy": interval_policy,
                    "selected_span": f"{selected_months[0]}..{selected_months[-1]}",
                }

    n_months = int(len(selected_months))
    first_month_period = selected_months[0]
    last_month_period = selected_months[-1]
    base_cpi_period = first_month_period - 1
    calendar_months_in_span = int((last_month_period - base_cpi_period).n)
    assert n_months == calendar_months_in_span, "Selected month block must be strictly contiguous."

    intermediate_unavailable_months = [
        str(m) for m in selected_months if m not in set(single_month_valid_periods)
    ]
    has_internal_cpi_gaps = len(intermediate_unavailable_months) > 0

    nom_factors = monthly_gross.reindex(selected_months).to_numpy(dtype=np.float64)
    cum_nom = float(np.prod(nom_factors))
    endpoint_cpi_ratio = float(cpi_series.loc[last_month_period] / cpi_series.loc[base_cpi_period])
    if not has_internal_cpi_gaps:
        cpi_curr = cpi_series.reindex(selected_months).to_numpy(dtype=np.float64)
        cpi_prev = cpi_series.reindex(selected_months - 1).to_numpy(dtype=np.float64)
        cpi_factors = cpi_curr / cpi_prev
        real_factors = nom_factors / cpi_factors
        cum_cpi = float(np.prod(cpi_factors))
        cum_real = float(np.prod(real_factors))
    else:
        cum_cpi = endpoint_cpi_ratio
        cum_real = float(cum_nom / cum_cpi)

    years = float(n_months) / 12.0
    ann_nom = float(cum_nom ** (1.0 / years) - 1.0)
    ann_cpi = float(cum_cpi ** (1.0 / years) - 1.0)
    ann_real = float(cum_real ** (1.0 / years) - 1.0)

    first_month = str(first_month_period)
    last_month = str(last_month_period)
    base_cpi_month = str(base_cpi_period)

    # Longest contiguous monthly-CPI-change block summary (always populated for transparency)
    longest_contiguous_cpi_summary: dict[str, Any] = {}
    if len(best_cpi_block) > 0:
        n_cb = int(len(best_cpi_block))
        cb_base = best_cpi_block[0] - 1
        cb_end = best_cpi_block[-1]
        cb_nom = float(np.prod(monthly_gross.reindex(best_cpi_block).to_numpy(dtype=np.float64)))
        cb_cpi = float(cpi_series.loc[cb_end] / cpi_series.loc[cb_base])
        cb_real = float(cb_nom / cb_cpi)
        cb_yrs = float(n_cb) / 12.0
        longest_contiguous_cpi_summary = {
            "first_month": str(best_cpi_block[0]),
            "last_month": str(cb_end),
            "base_cpi_month": str(cb_base),
            "n_months": n_cb,
            "nominal_wealth_multiple": cb_nom,
            "cpi_index_ratio": cb_cpi,
            "real_wealth_multiple": cb_real,
            "ex_post_nominal_annual_return": float(cb_nom ** (1.0 / cb_yrs) - 1.0),
            "ex_post_cpi_annual_inflation": float(cb_cpi ** (1.0 / cb_yrs) - 1.0),
            "ex_post_real_annual_return": float(cb_real ** (1.0 / cb_yrs) - 1.0),
        }

    # Scattered single-month diagnostic (explicitly labelled as non-endpoint when non-contiguous)
    scattered_diag: dict[str, Any] = {}
    if len(single_month_valid_periods) > 0:
        sc_nom = monthly_gross.reindex(single_month_valid_periods).to_numpy(dtype=np.float64)
        sc_cpi = (
            cpi_series.reindex(single_month_valid_periods).to_numpy(dtype=np.float64)
            / cpi_series.reindex(single_month_valid_periods - 1).to_numpy(dtype=np.float64)
        )
        sc_real = sc_nom / sc_cpi
        is_sc_contiguous = len(contiguous_cpi_runs) == 1
        scattered_diag = {
            "classification": (
                "contiguous_monthly_factors_equal_endpoint_ratio"
                if is_sc_contiguous
                else "scattered_noncontiguous_monthly_factors_not_an_endpoint_ratio"
            ),
            "is_contiguous": is_sc_contiguous,
            "months_included": [str(m) for m in single_month_valid_periods],
            "n_single_months": int(len(single_month_valid_periods)),
            "product_of_single_month_nominal_factors": float(np.prod(sc_nom)),
            "product_of_single_month_cpi_factors": float(np.prod(sc_cpi)),
            "product_of_single_month_real_factors": float(np.prod(sc_real)),
            "note": (
                "All valid single-month CPI-change factors are contiguous and telescope to the endpoint ratio."
                if is_sc_contiguous
                else (
                    "WARNING: Non-contiguous single-month factors omit internal missing-CPI months "
                    f"({intermediate_unavailable_months}) and DO NOT equal the endpoint wealth or CPI ratio."
                )
            ),
        }

    # Also record full-active-path diagnostic (including any partial initial entry month) if prior CPI exists
    full_path_diag: dict[str, Any] = {}
    first_all_m = all_port_months[0]
    last_all_m = all_port_months[-1]
    if (first_all_m - 1) in cpi_series.index and last_all_m in cpi_series.index:
        n_all_m = int((last_all_m - (first_all_m - 1)).n)
        interior_complete = (
            list(all_port_months[1:]) == list(pd.period_range(first_all_m + 1, last_all_m, freq="M"))
            and all(m in set(complete_port_months) for m in all_port_months[1:])
        )
        if n_all_m > 0 and interior_complete:
            w_total = float(np.prod(1.0 + p_clean.to_numpy(dtype=np.float64)))
            cpi_ratio_total = float(cpi_series.loc[last_all_m] / cpi_series.loc[first_all_m - 1])
            real_mult_total = float(w_total / cpi_ratio_total)
            yrs_total = float(n_all_m) / 12.0
            full_path_diag = {
                "base_cpi_month": str(first_all_m - 1),
                "end_cpi_month": str(last_all_m),
                "n_calendar_months": n_all_m,
                "nominal_wealth_multiple": w_total,
                "cpi_ratio": cpi_ratio_total,
                "real_wealth_multiple": real_mult_total,
                "ex_post_nominal_annual_return": float(w_total ** (1.0 / yrs_total) - 1.0),
                "ex_post_cpi_annual_inflation": float(cpi_ratio_total ** (1.0 / yrs_total) - 1.0),
                "ex_post_real_annual_return": float(real_mult_total ** (1.0 / yrs_total) - 1.0),
                "has_internal_cpi_gaps": has_internal_cpi_gaps,
                "note": (
                    f"Includes partial initial entry month {first_all_m} (starting {p_clean.index[0].date()}) "
                    f"deflated against endpoint {first_all_m - 1}..{last_all_m} CPIAUCSL."
                ),
            }

    row_status = "warning" if has_internal_cpi_gaps else "ok"
    gap_warning_prefix = (
        f"WARNING: intermediate single-month CPI changes unavailable for {intermediate_unavailable_months} "
        f"(missing current CPI={missing_current_cpi_months}, missing prior CPI={missing_prior_cpi_months}); "
        f"full-span growth computed from contiguous complete NYSE nominal returns and valid endpoint CPI "
        f"{last_month}/{base_cpi_month}. "
        if has_internal_cpi_gaps
        else ""
    )
    span_label = (
        f"common completed months {first_month}..{last_month} "
        f"(n={n_months} contiguous months, base CPI month={base_cpi_month}; "
        f"partial portfolio months excluded={partial_port_months}; "
        f"missing/unreleased CPI months excluded={unreleased_or_missing_cpi_months})"
    )

    rows = [
        {
            "metric": "ex_post_nominal_annual_return_common_months",
            "value": ann_nom,
            "unit": "annual_fraction",
            "status": row_status,
            "note": (
                f"{gap_warning_prefix}Ex-post {span_label}: compounded nominal return "
                f"(W_end/W_base)^(12/{n_months})-1 over contiguous completed NYSE months."
            ),
        },
        {
            "metric": "ex_post_cpi_annual_inflation_common_months",
            "value": ann_cpi,
            "unit": "annual_fraction",
            "status": row_status,
            "note": (
                f"{gap_warning_prefix}Ex-post {span_label}: compounded FRED CPIAUCSL inflation "
                f"(CPI_{last_month}/CPI_{base_cpi_month})^(12/{n_months})-1; historical realized "
                f"inflation, NOT a forward inflation forecast."
            ),
        },
        {
            "metric": "ex_post_real_annual_return_common_months",
            "value": ann_real,
            "unit": "annual_fraction",
            "status": row_status,
            "note": (
                f"{gap_warning_prefix}Ex-post {span_label}: exact Fisher real annual return "
                f"(1 + G_nom)/(1 + pi_CPI) - 1; measures historical purchasing-power growth "
                f"before endowment spending withdrawals."
            ),
        },
        {
            "metric": "ex_post_real_wealth_multiple_common_months",
            "value": cum_real,
            "unit": "multiple",
            "status": row_status,
            "note": (
                f"{gap_warning_prefix}Ex-post {span_label}: cumulative purchasing-power multiple "
                f"(nominal multiple={cum_nom:.6f} / endpoint CPI ratio={cum_cpi:.6f})."
            ),
        },
    ]

    return _build_kpi_dataframe(
        rows,
        attrs={
            "common_months_summary": {
                "interval_policy": interval_policy,
                "first_common_month": first_month,
                "last_common_month": last_month,
                "base_cpi_month": base_cpi_month,
                "n_common_complete_months": n_months,
                "calendar_months_in_span": calendar_months_in_span,
                "is_contiguous_calendar_span": True,
                "has_internal_cpi_gaps": has_internal_cpi_gaps,
                "nominal_wealth_multiple": cum_nom,
                "cpi_index_ratio": cum_cpi,
                "endpoint_cpi_ratio": cum_cpi,
                "real_wealth_multiple": cum_real,
                "partial_portfolio_months_excluded": partial_port_months,
                "missing_current_cpi_months_excluded": missing_current_cpi_months,
                "missing_prior_cpi_months_excluded": missing_prior_cpi_months,
                "unreleased_or_missing_cpi_months_excluded": unreleased_or_missing_cpi_months,
                "intermediate_unavailable_cpi_change_months": intermediate_unavailable_months,
                "outside_selected_block_months_excluded": outside_selected_block_months,
                "excluded_months_by_reason": excluded_months_by_reason,
                "longest_contiguous_monthly_cpi_block": longest_contiguous_cpi_summary,
                "scattered_single_months_diagnostic": scattered_diag,
                "full_active_path_with_prior_cpi_diagnostic": full_path_diag,
            }
        },
    )


def compute_trailing_12m_distribution_yields(
    split_adjusted_closes: pd.DataFrame,
    distributions: pd.DataFrame,
    *,
    window_calendar_days: int = 365,
    min_coverage_calendar_days: int = 365,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute trailing-12-month cash distributions and yields on a compatible split-adjusted share basis."""
    return compute_trailing_12m_distribution_series(
        split_adjusted_closes,
        distributions,
        window_calendar_days=window_calendar_days,
        min_coverage_calendar_days=min_coverage_calendar_days,
    )


def summarize_portfolio_distribution_income(
    weights_before: pd.DataFrame,
    split_adjusted_closes: pd.DataFrame,
    distributions: pd.DataFrame,
    trailing_12m_yields: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarize ex-date cash distribution income and trailing-12M yield for a portfolio path.

    Important Governance Rule (SOLO STEP 4 / A1b & A2):
    - ``DataBundle.simple_returns`` and ``PortfolioPath.net_returns`` already include reinvested
      cash distributions via ``yfinance`` ``auto_adjust=True``.
    - The metrics computed here report the **cash-income component alongside total return**
      (to inform endowment spending coverage without liquidating shares) and must NEVER be
      added a second time to portfolio total returns.
    """
    if not isinstance(weights_before, pd.DataFrame) or weights_before.empty:
        raise ValueError("weights_before must be a non-empty DataFrame.")

    tickers = list(weights_before.columns)
    missing_cols = [
        t for t in tickers if t not in split_adjusted_closes.columns or t not in distributions.columns
    ]
    if missing_cols:
        raise ValueError(f"Missing tickers {missing_cols} in split_adjusted_closes or distributions.")

    common_dates = (
        weights_before.index.intersection(split_adjusted_closes.index)
        .intersection(distributions.index)
        .sort_values()
    )
    if len(common_dates) == 0:
        raise ValueError("No overlapping session dates between weights_before and context price/distribution frames.")

    if trailing_12m_yields is None:
        _, ttm_yield_df = compute_trailing_12m_distribution_series(
            split_adjusted_closes[tickers],
            distributions[tickers],
        )
    else:
        ttm_yield_df = trailing_12m_yields[tickers]

    # Daily ex-date distribution yield fraction of pre-return NAV:
    # sum_i w_{i,t-} * (Dividend_{i,t} / Close_{i,t-1}^{split-adj})
    prev_split_closes = split_adjusted_closes[tickers].shift(1).reindex(common_dates)
    div_aligned = distributions[tickers].reindex(common_dates)
    w_aligned = weights_before[tickers].reindex(common_dates)

    valid_prev_mask = prev_split_closes.notna().all(axis=1)
    valid_ex_dates = common_dates[valid_prev_mask]

    if len(valid_ex_dates) == 0:
        raise ValueError("Preceding session split-adjusted closes are unavailable on aligned portfolio dates.")

    asset_daily_div_yield = div_aligned.loc[valid_ex_dates] / prev_split_closes.loc[valid_ex_dates]
    port_daily_div_yield = (w_aligned.loc[valid_ex_dates] * asset_daily_div_yield).sum(axis=1)
    ann_ex_date_yield = float(ANNUALIZATION_DAYS * port_daily_div_yield.mean())
    n_port_div_sessions = int((port_daily_div_yield > 0.0).sum())

    # Portfolio weighted trailing-12-month distribution yield across sessions with full 365d coverage
    ttm_aligned = ttm_yield_df.reindex(common_dates)
    valid_ttm_mask = ttm_aligned.notna().all(axis=1)
    port_ttm_series = (w_aligned.loc[valid_ttm_mask] * ttm_aligned.loc[valid_ttm_mask]).sum(axis=1)

    mean_ttm_yield = float(port_ttm_series.mean()) if len(port_ttm_series) > 0 else None
    end_ttm_yield = float(port_ttm_series.iloc[-1]) if len(port_ttm_series) > 0 else None

    span = f"{common_dates[0].date()}..{common_dates[-1].date()} (n={len(common_dates)})"
    rows = [
        {
            "metric": "annualized_ex_date_distribution_yield",
            "value": ann_ex_date_yield,
            "unit": "annual_fraction",
            "status": "ok",
            "note": (
                f"Sample {span}: 252 * mean_t(sum_i w_{{i,t-}} * Div_{{i,t}} / Close_{{i,t-1}}^{{split-adj}}) "
                f"across {n_port_div_sessions} ex-dividend sessions. Cash income component already "
                f"embedded in auto_adjust=True total return (never add again to total return)."
            ),
        },
        {
            "metric": "mean_trailing_12m_distribution_yield",
            "value": mean_ttm_yield,
            "unit": "annual_fraction",
            "status": "ok" if mean_ttm_yield is not None else "unavailable",
            "note": (
                f"Sample {span}: average weighted trailing-365d distribution yield "
                f"sum_i w_{{i,t-}} * (TTM_Div_{{i,t}} / Close_{{i,t}}^{{split-adj}}) across "
                f"{len(port_ttm_series)}/{len(common_dates)} sessions with full 365d trailing coverage."
            ),
        },
        {
            "metric": "ending_trailing_12m_distribution_yield",
            "value": end_ttm_yield,
            "unit": "annual_fraction",
            "status": "ok" if end_ttm_yield is not None else "unavailable",
            "note": (
                f"Sample {span}: portfolio weighted trailing-365d distribution yield at sample end "
                f"({common_dates[-1].date()}); indicates run-rate cash yield available for spending before capital withdrawals."
            ),
        },
    ]

    return _build_kpi_dataframe(
        rows,
        attrs={
            "income_summary": {
                "sample_start": str(common_dates[0].date()),
                "sample_end": str(common_dates[-1].date()),
                "n_sessions": int(len(common_dates)),
                "n_ex_dividend_sessions": n_port_div_sessions,
                "annualized_ex_date_distribution_yield": ann_ex_date_yield,
                "mean_trailing_12m_distribution_yield": mean_ttm_yield,
                "ending_trailing_12m_distribution_yield": end_ttm_yield,
                "total_return_double_count_guard": "distributions_embedded_in_adjusted_closes_never_added_to_returns",
            }
        },
    )


def run_portfolio_return_stationarity_diagnostics(
    portfolio_returns: pd.Series,
    *,
    series_label: str = "strategy_path",
    fixed_exposure_returns: pd.Series | None = None,
) -> pd.DataFrame:
    """Run ADF unit-root diagnostics on simple and ``log1p`` portfolio returns.

    Explicitly distinguishes changing-weight strategy path returns from any fixed-exposure
    modelling return series fed into Step 5+ risk estimators.
    """
    p_clean = _validate_time_series(portfolio_returns, "portfolio_returns").dropna()
    series_map: dict[str, pd.Series] = {
        f"{series_label}_simple_return": p_clean,
    }
    if bool((1.0 + p_clean > 0.0).all()):
        series_map[f"{series_label}_log1p_return"] = pd.Series(
            np.log1p(p_clean.to_numpy(dtype=np.float64)),
            index=p_clean.index,
            name=f"{series_label}_log1p_return",
        )

    if fixed_exposure_returns is not None:
        f_clean = _validate_time_series(fixed_exposure_returns, "fixed_exposure_returns").dropna()
        series_map[f"{series_label}_fixed_exposure_simple_return"] = f_clean
        if bool((1.0 + f_clean > 0.0).all()):
            series_map[f"{series_label}_fixed_exposure_log1p_return"] = pd.Series(
                np.log1p(f_clean.to_numpy(dtype=np.float64)),
                index=f_clean.index,
                name=f"{series_label}_fixed_exposure_log1p_return",
            )

    diag_df = run_stationarity_diagnostics(series_map)
    diag_df["note"] = diag_df.apply(
        lambda row: (
            f"[{'fixed_exposure_risk_sample' if 'fixed_exposure' in str(row['series']) else 'changing_weight_strategy_path'}] "
            f"{row['note']}"
        ),
        axis=1,
    )
    return diag_df


def build_development_kpi_bundle(
    portfolio_paths: dict[str, PortfolioPath],
    market_returns: pd.Series,
    rf_daily: pd.Series,
    *,
    benchmark_key: str = "benchmark_60_40",
    rf_accrual_sensitivity: pd.Series | None = None,
    context_bundle: ContextSnapshotBundle | None = None,
) -> dict[str, Any]:
    """Compute matched KPI, RF-sensitivity, real-return, and distribution-income tables across candidate paths."""
    if benchmark_key not in portfolio_paths:
        raise ValueError(f"benchmark_key {benchmark_key!r} not found in portfolio_paths.")

    bench_net = portfolio_paths[benchmark_key].net_returns
    kpis_by_strategy: dict[str, pd.DataFrame] = {}
    rf_sensitivity_by_strategy: dict[str, pd.DataFrame] = {}
    real_returns_by_strategy: dict[str, pd.DataFrame] = {}
    income_by_strategy: dict[str, pd.DataFrame] = {}
    stationarity_by_strategy: dict[str, pd.DataFrame] = {}

    for name, path in portfolio_paths.items():
        kpis_by_strategy[name] = compute_kpis(
            path.net_returns,
            bench_net,
            market_returns,
            rf_daily,
        )
        if rf_accrual_sensitivity is not None:
            rf_sensitivity_by_strategy[name] = compare_rf_kpi_sensitivity(
                path.net_returns,
                bench_net,
                market_returns,
                rf_daily,
                rf_accrual_sensitivity,
            )
        if context_bundle is not None:
            real_returns_by_strategy[name] = compute_ex_post_real_return_metrics(
                path.net_returns,
                context_bundle.cpi_monthly,
            )
            income_by_strategy[name] = summarize_portfolio_distribution_income(
                path.weights_before,
                context_bundle.split_adjusted_closes,
                context_bundle.distributions,
                context_bundle.trailing_12m_yields,
            )
        stationarity_by_strategy[name] = run_portfolio_return_stationarity_diagnostics(
            path.net_returns,
            series_label=name,
        )

    return {
        "kpis": kpis_by_strategy,
        "rf_sensitivity": rf_sensitivity_by_strategy,
        "ex_post_real_returns": real_returns_by_strategy,
        "distribution_income": income_by_strategy,
        "stationarity": stationarity_by_strategy,
    }
