"""Unit, mathematical invariant, and development-period smoke tests for SOLO STEP 5 (C1 VaR & ES)."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm as scipy_norm

from quantedge import (
    AppConfig,
    CANONICAL_TICKERS,
    MANDATE_NAV_USD,
    RiskEstimate,
    RiskForecastFn,
)
from quantedge.data import load_data
from quantedge.es import empirical_tail_weights, empirical_var_and_es
from quantedge.var import (
    SUPPORTED_C1_RISK_MODELS,
    build_development_c1_risk_bundle,
    compare_risk_models_table,
    comparison_table_to_records,
    compute_fixed_exposure_loss_diagnostics,
    describe_window_crisis_coverage,
    estimate_risk,
    get_risk_forecaster,
    normal_moments,
    quantify_monte_carlo_uncertainty,
    resolve_risk_runtime_settings,
    serialize_c1_risk_bundle,
)


def test_normal_moments_exact_known_answer_and_input_validation() -> None:
    """normal_moments computes exact arithmetic mean and ddof=1 covariance and rejects malformed inputs."""
    dates = pd.to_datetime(["2015-01-05", "2015-01-06", "2015-01-07", "2015-01-08"])
    raw_matrix = np.array(
        [
            [0.010, 0.005, -0.010, 0.002, 0.004, 0.015, 0.012],
            [-0.020, -0.015, -0.030, 0.004, 0.008, -0.025, -0.018],
            [0.030, 0.020, 0.040, -0.002, -0.004, 0.035, 0.028],
            [0.000, 0.010, 0.000, 0.000, 0.000, -0.005, -0.002],
        ],
        dtype=np.float64,
    )
    df = pd.DataFrame(raw_matrix, index=dates, columns=list(CANONICAL_TICKERS))

    mean_s, cov_df = normal_moments(df)
    assert tuple(mean_s.index) == CANONICAL_TICKERS
    assert tuple(cov_df.index) == CANONICAL_TICKERS
    assert tuple(cov_df.columns) == CANONICAL_TICKERS

    expected_mean = raw_matrix.mean(axis=0)
    centered = raw_matrix - expected_mean[None, :]
    expected_cov = (centered.T @ centered) / 3.0

    assert np.allclose(mean_s.to_numpy(), expected_mean, atol=1e-16)
    assert np.allclose(cov_df.to_numpy(), expected_cov, atol=1e-16)
    assert mean_s.attrs["ddof"] == 1
    assert mean_s.attrs["n_obs"] == 4
    assert cov_df.attrs["sample_start"] == "2015-01-05"
    assert cov_df.attrs["sample_end"] == "2015-01-08"

    # Reject wrong column order
    scrambled = df[["AGG", "SPY", "EFA", "EEM", "GLD", "XLE", "XLK"]]
    with pytest.raises(ValueError, match="canonical order"):
        normal_moments(scrambled)

    # Reject < 2 rows
    with pytest.raises(ValueError, match="at least 2 observations"):
        normal_moments(df.iloc[:1])

    # Reject NaN and +/-inf
    for bad_val in (float("nan"), float("inf"), float("-inf")):
        bad_df = df.copy()
        bad_df.iloc[1, 0] = bad_val
        with pytest.raises(ValueError, match="non-finite"):
            normal_moments(bad_df)


def test_closed_form_parametric_normal_var_es_and_nonpositive_loss_quantiles() -> None:
    """Parametric normal VaR/ES match exact closed-form Gaussian formulas and preserve negative loss quantiles."""
    dates = pd.bdate_range("2016-01-04", periods=8)
    rng = np.random.default_rng(12345)
    base = rng.normal(loc=0.0005, scale=0.012, size=(8, len(CANONICAL_TICKERS)))
    df = pd.DataFrame(base, index=dates, columns=list(CANONICAL_TICKERS))
    weights = pd.Series(
        {
            "SPY": 0.20,
            "EFA": 0.10,
            "EEM": 0.05,
            "AGG": 0.35,
            "GLD": 0.20,
            "XLE": 0.05,
            "XLK": 0.05,
        },
        index=list(CANONICAL_TICKERS),
        dtype=float,
    )

    mean_s, cov_df = normal_moments(df)
    w_arr = weights.to_numpy(dtype=np.float64)
    mu_p = float(w_arr @ mean_s.to_numpy(dtype=np.float64))
    sigma_p = math.sqrt(float(w_arr @ cov_df.to_numpy(dtype=np.float64) @ w_arr))

    for conf in (0.90, 0.95, 0.99):
        alpha = round(1.0 - conf, 12)
        z_c = float(scipy_norm.ppf(conf))
        phi_z = float(scipy_norm.pdf(z_c))
        expected_var = -mu_p + sigma_p * z_c
        expected_es = -mu_p + sigma_p * (phi_z / alpha)

        est = estimate_risk(df, weights, model="parametric_normal", confidence=conf)
        assert est.status == "ok"
        assert est.reason is None
        assert est.n_obs == 8
        assert est.var_loss is not None and est.es_loss is not None
        assert math.isclose(est.var_loss, expected_var, rel_tol=0.0, abs_tol=1e-15)
        assert math.isclose(est.es_loss, expected_es, rel_tol=0.0, abs_tol=1e-15)
        assert est.es_loss >= est.var_loss
        assert math.isclose(est.diagnostics["var_usd"], expected_var * MANDATE_NAV_USD, abs_tol=1e-8)

    # Positive-shift case: large positive daily returns (+5% +/- ~0.1%) produce negative loss quantiles.
    # Neither Historical, Parametric Normal, nor Monte Carlo Normal may apply abs() or floor to 0.0.
    pos_shift_df = pd.DataFrame(
        0.05 + (base - base.mean(axis=0, keepdims=True)) * 0.05,
        index=dates,
        columns=list(CANONICAL_TICKERS),
    )
    for model_name in SUPPORTED_C1_RISK_MODELS:
        est_pos = estimate_risk(
            pos_shift_df,
            weights,
            model=model_name,
            confidence=0.95,
            seed=202601,
        )
        assert est_pos.status == "ok"
        assert est_pos.var_loss is not None and est_pos.es_loss is not None
        assert est_pos.var_loss < 0.0
        assert est_pos.es_loss < 0.0
        assert est_pos.es_loss >= est_pos.var_loss
        assert est_pos.diagnostics["nonpositive_loss_quantile"] is True


def test_zero_volatility_and_rank_deficient_covariance_handling() -> None:
    """Zero portfolio volatility returns deterministic -mu loss with status='warning' across all 3 C1 models."""
    dates = pd.bdate_range("2016-02-01", periods=6)
    weights = pd.Series(1.0 / 7.0, index=list(CANONICAL_TICKERS), dtype=float)

    for const_ret in (0.0, 0.0025, -0.0040):
        const_df = pd.DataFrame(const_ret, index=dates, columns=list(CANONICAL_TICKERS))
        expected_loss = -const_ret
        for model_name in SUPPORTED_C1_RISK_MODELS:
            est = estimate_risk(
                const_df,
                weights,
                model=model_name,
                confidence=0.99,
                seed=202601,
            )
            assert est.status == "warning"
            assert est.reason is not None and "zero portfolio volatility" in est.reason.lower()
            assert est.var_loss is not None and est.es_loss is not None
            assert math.isclose(est.var_loss, expected_loss, rel_tol=0.0, abs_tol=1e-15)
            assert math.isclose(est.es_loss, expected_loss, rel_tol=0.0, abs_tol=1e-15)
            assert est.diagnostics["zero_portfolio_volatility"] is True

    # Rank-deficient covariance: GLD is constant 0.0 while other assets vary -> portfolio sigma > 0
    rng = np.random.default_rng(999)
    semi_df = pd.DataFrame(
        rng.normal(0.0, 0.01, size=(12, len(CANONICAL_TICKERS))),
        index=pd.bdate_range("2016-03-01", periods=12),
        columns=list(CANONICAL_TICKERS),
    )
    semi_df["GLD"] = 0.0
    for model_name in ("parametric_normal", "monte_carlo_normal"):
        est_semi = estimate_risk(
            semi_df,
            weights,
            model=model_name,
            confidence=0.95,
            seed=202601,
        )
        assert est_semi.status == "ok"
        assert est_semi.var_loss is not None and est_semi.es_loss is not None
        assert est_semi.es_loss > est_semi.var_loss
        assert "GLD" in est_semi.diagnostics["zero_variance_tickers"]
        assert est_semi.diagnostics["covariance_rank_deficient"] is True


def test_empirical_tail_weights_fractional_boundary_ties_and_euler_additivity() -> None:
    """empirical_tail_weights integrates exact worst alpha=1-c mass with fractional boundary and tie sharing."""
    idx_10 = pd.bdate_range("2016-01-04", periods=10)

    # Case 1: n=10, c=0.85 -> alpha=0.15, m = n * alpha = 1.5 (1 full + 0.5 boundary observation)
    # Losses: 0.01, 0.02, ..., 0.10. Worst is 0.10 (weight 1/1.5 = 2/3), 2nd worst is 0.09 (weight 0.5/1.5 = 1/3).
    # Note: linear interpolation quantile is 0.0865, which lies strictly below BOTH 0.09 and 0.10;
    # our order-statistic boundary u_* = 0.09 correctly separates strict exceedance {0.10} from boundary {0.09}.
    losses_distinct = pd.Series(
        [0.01 * i for i in range(1, 11)],
        index=idx_10,
        dtype=float,
    )
    tw_1 = empirical_tail_weights(losses_distinct, 0.85)
    assert list(tw_1.index) == list(idx_10)
    assert math.isclose(float(tw_1.sum()), 1.0, rel_tol=0.0, abs_tol=1e-15)
    assert np.allclose(
        tw_1.to_numpy(),
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0 / 3.0, 2.0 / 3.0],
        atol=1e-15,
    )
    var_1, es_1, _, diag_1 = empirical_var_and_es(losses_distinct, 0.85)
    assert math.isclose(var_1, 0.09, rel_tol=0.0, abs_tol=1e-15)
    assert math.isclose(es_1, 0.29 / 3.0, rel_tol=0.0, abs_tol=1e-15)
    assert math.isclose(es_1, float(tw_1 @ losses_distinct), rel_tol=0.0, abs_tol=1e-15)
    # Naive mean(losses >= VaR) is 0.095 != 0.29 / 3.0 = 0.096666...
    assert math.isclose(diag_1["naive_mean_losses_ge_var_diagnostic"], 0.095, abs_tol=1e-15)
    assert abs(es_1 - diag_1["naive_mean_losses_ge_var_diagnostic"]) > 1e-3

    # Case 2: n=10, c=0.85 (m=1.5) with a 3-way tie at the boundary loss u_* = 0.08
    # Strict exceedance {0.10} gets 2/3; remaining 0.5 obs mass is split equally across the three 0.08 ties (1/9 each).
    losses_tied_frac = pd.Series(
        [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.08, 0.08, 0.10],
        index=idx_10,
        dtype=float,
    )
    tw_2 = empirical_tail_weights(losses_tied_frac, 0.85)
    assert math.isclose(float(tw_2.sum()), 1.0, rel_tol=0.0, abs_tol=1e-15)
    assert np.allclose(
        tw_2.to_numpy(),
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0 / 9.0, 1.0 / 9.0, 1.0 / 9.0, 2.0 / 3.0],
        atol=1e-15,
    )
    var_2, es_2, _, _ = empirical_var_and_es(losses_tied_frac, 0.85)
    assert math.isclose(var_2, 0.08, rel_tol=0.0, abs_tol=1e-15)
    assert math.isclose(es_2, 0.28 / 3.0, rel_tol=0.0, abs_tol=1e-15)

    # Case 3: n=10, c=0.80 (m=2.0 integer tail mass) with a 2-way tie across the boundary u_* = 0.09
    # Strict exceedance {0.10} gets 0.5; the two tied 0.09 observations split the remaining 1.0 slot (0.25 each).
    losses_tied_int = pd.Series(
        [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.09, 0.09, 0.10],
        index=idx_10,
        dtype=float,
    )
    tw_3 = empirical_tail_weights(losses_tied_int, 0.80)
    assert np.allclose(
        tw_3.to_numpy(),
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.25, 0.25, 0.50],
        atol=1e-15,
    )
    _, es_3, _, _ = empirical_var_and_es(losses_tied_int, 0.80)
    assert math.isclose(es_3, 0.095, rel_tol=0.0, abs_tol=1e-15)

    # Case 4: Binary float representation of 1.0 - 0.95 on n=20 must yield exact integer m=1.0 (1 positive weight)
    idx_20 = pd.bdate_range("2016-01-04", periods=20)
    losses_20 = pd.Series(np.linspace(-0.02, 0.05, 20), index=idx_20, dtype=float)
    tw_20 = empirical_tail_weights(losses_20, 0.95)
    assert tw_20.attrs["n_positive_weights"] == 1
    assert math.isclose(float(tw_20.iloc[-1]), 1.0, rel_tol=0.0, abs_tol=1e-15)

    # Case 5: Cross-asset Euler historical ES additivity identity
    rng = np.random.default_rng(202605)
    asset_df = pd.DataFrame(
        rng.normal(0.0002, 0.01, size=(15, len(CANONICAL_TICKERS))),
        index=pd.bdate_range("2016-04-01", periods=15),
        columns=list(CANONICAL_TICKERS),
    )
    w = pd.Series(
        {"SPY": 0.15, "EFA": 0.08, "EEM": 0.04, "AGG": 0.40, "GLD": 0.25, "XLE": 0.04, "XLK": 0.04},
        index=list(CANONICAL_TICKERS),
        dtype=float,
    )
    est_hist = estimate_risk(asset_df, w, model="historical", confidence=0.95)
    port_losses = -(asset_df @ w)
    tail_w = empirical_tail_weights(port_losses, 0.95)
    # Asset-level Euler component ES_i = w_i * (tail_weights @ (-R_i))
    component_es = [
        float(w.loc[t]) * float(tail_w @ (-asset_df[t])) for t in CANONICAL_TICKERS
    ]
    assert est_hist.es_loss is not None
    assert math.isclose(sum(component_es), est_hist.es_loss, rel_tol=0.0, abs_tol=1e-15)


def test_confidence_monotonicity_and_es_ge_var_invariant() -> None:
    """VaR and ES are non-decreasing in confidence (0.90 <= 0.95 <= 0.99) and ES >= VaR for all models."""
    rng = np.random.default_rng(777)
    df = pd.DataFrame(
        rng.normal(-0.0002, 0.011, size=(120, len(CANONICAL_TICKERS))),
        index=pd.bdate_range("2015-01-02", periods=120),
        columns=list(CANONICAL_TICKERS),
    )
    weights = pd.Series(1.0 / 7.0, index=list(CANONICAL_TICKERS), dtype=float)

    for model_name in SUPPORTED_C1_RISK_MODELS:
        estimates = [
            estimate_risk(df, weights, model=model_name, confidence=c, seed=202601)
            for c in (0.90, 0.95, 0.99)
        ]
        for est in estimates:
            assert est.status == "ok"
            assert est.var_loss is not None and est.es_loss is not None
            assert est.es_loss >= est.var_loss - 1e-15

        vars_c = [float(e.var_loss) for e in estimates if e.var_loss is not None]
        ess_c = [float(e.es_loss) for e in estimates if e.es_loss is not None]
        assert vars_c[0] <= vars_c[1] <= vars_c[2]
        assert ess_c[0] <= ess_c[1] <= ess_c[2]


def test_monte_carlo_seed_reproducibility_config_authority_and_analytic_agreement(
    baseline_config: AppConfig,
) -> None:
    """Monte Carlo normal uses config 25,000 draws and seed 202601 by default, is bit-reproducible, and agrees with analytic normal."""
    settings = resolve_risk_runtime_settings(baseline_config)
    assert settings["monte_carlo_simulations"] == 25000
    assert settings["monte_carlo_seed"] == 202601

    rng = np.random.default_rng(2026)
    df = pd.DataFrame(
        rng.normal(0.0003, 0.009, size=(250, len(CANONICAL_TICKERS))),
        index=pd.bdate_range("2015-01-02", periods=250),
        columns=list(CANONICAL_TICKERS),
    )
    weights = pd.Series(
        baseline_config.portfolio.illustrative_weights,
        index=list(CANONICAL_TICKERS),
        dtype=float,
    )

    # Default seed=None resolves to config.seeds.monte_carlo (202601)
    mc_default = estimate_risk(df, weights, model="monte_carlo_normal", confidence=0.95, seed=None)
    mc_explicit = estimate_risk(df, weights, model="monte_carlo_normal", confidence=0.95, seed=202601)
    mc_other = estimate_risk(df, weights, model="monte_carlo_normal", confidence=0.95, seed=202699)

    assert mc_default.var_loss == mc_explicit.var_loss
    assert mc_default.es_loss == mc_explicit.es_loss
    assert mc_default.diagnostics["seed"] == 202601
    assert mc_default.diagnostics["monte_carlo_simulations"] == 25000
    assert mc_default.var_loss != mc_other.var_loss

    # Agreement with closed-form parametric_normal within justified simulation uncertainty
    for conf in (0.90, 0.95, 0.99):
        unc = quantify_monte_carlo_uncertainty(
            df,
            weights,
            confidence=conf,
            base_seed=202601,
            n_replications=32,
        )
        assert abs(unc["primary_seed_var_diff_vs_analytic"]) <= unc["recommended_agreement_tolerance_var"]
        assert abs(unc["primary_seed_es_diff_vs_analytic"]) <= unc["recommended_agreement_tolerance_es"]


def test_forecaster_callbacks_pure_input_isolation_and_invalid_input_rejection() -> None:
    """get_risk_forecaster callbacks depend strictly on passed historical inputs and reject invalid contracts."""
    rng = np.random.default_rng(42)
    full_df = pd.DataFrame(
        rng.normal(0.0001, 0.01, size=(40, len(CANONICAL_TICKERS))),
        index=pd.bdate_range("2016-01-04", periods=40),
        columns=list(CANONICAL_TICKERS),
    )
    train_slice = full_df.iloc[:30].copy()
    # Mutate future rows after row 30 with extreme -50% crashes
    corrupted_future_df = full_df.copy()
    corrupted_future_df.iloc[30:] = -0.50

    weights = pd.Series(1.0 / 7.0, index=list(CANONICAL_TICKERS), dtype=float)

    for model_name in SUPPORTED_C1_RISK_MODELS:
        cb = get_risk_forecaster(model_name)
        assert isinstance(cb, RiskForecastFn)
        est_from_slice = cb(train_slice, weights, confidence=0.99, seed=202601)
        est_from_corrupted_parent = cb(
            corrupted_future_df.iloc[:30],
            weights,
            confidence=0.99,
            seed=202601,
        )
        direct_est = estimate_risk(
            train_slice,
            weights,
            model=model_name,
            confidence=0.99,
            seed=202601,
        )
        assert est_from_slice == est_from_corrupted_parent == direct_est

    # Step 7 EVT dispatch and deferred rolling forecaster
    with pytest.raises(NotImplementedError, match="STEP 7"):
        get_risk_forecaster("evt_pot")
    # Point-in-time EVT POT is active in estimate_risk (train_slice has only 30 obs -> 1 exceedance < 50 min)
    evt_pt_est = estimate_risk(train_slice, weights, model="evt_pot", confidence=0.99)
    assert isinstance(evt_pt_est, RiskEstimate)
    assert evt_pt_est.status == "unavailable"
    assert "insufficient strict exceedances" in evt_pt_est.reason.lower()
    with pytest.raises(ValueError, match="Unsupported risk model"):
        get_risk_forecaster("student_t_garch")
    with pytest.raises(ValueError, match="Unsupported risk model"):
        estimate_risk(train_slice, weights, model="student_t_garch", confidence=0.99)

    # Invalid weights: wrong order, unnormalized sum != 1, NaN/inf
    bad_order_w = weights.reindex(["AGG", "SPY", "EFA", "EEM", "GLD", "XLE", "XLK"])
    with pytest.raises(ValueError, match="canonical ticker order"):
        estimate_risk(train_slice, bad_order_w, model="historical", confidence=0.95)

    unnormalized_w = weights * 1.10
    with pytest.raises(ValueError, match="sum to 1.0"):
        estimate_risk(train_slice, unnormalized_w, model="parametric_normal", confidence=0.95)

    nan_w = weights.copy()
    nan_w.iloc[0] = float("nan")
    with pytest.raises(ValueError, match="non-finite"):
        estimate_risk(train_slice, nan_w, model="historical", confidence=0.95)

    # Insufficient training observations (< 2 rows) return status='unavailable' with None metrics
    for n_short in (0, 1):
        short_est = estimate_risk(
            train_slice.iloc[:n_short],
            weights,
            model="historical",
            confidence=0.95,
        )
        assert short_est.status == "unavailable"
        assert short_est.var_loss is None and short_est.es_loss is None
        assert short_est.n_obs == n_short
        assert short_est.reason is not None and "Insufficient training observations" in short_est.reason


def test_offline_development_period_c1_risk_bundle_and_holdout_guard(
    baseline_config: AppConfig,
) -> None:
    """Offline development-period (<= 2016-12-30) smoke check verifies C1 risk tables, crisis labels, and stationarity."""
    bundle = load_data(baseline_config, offline=True)
    assert bundle.manifest.dataset_id == "qe1_20050101_20261030_r3_6c4633a7ba"

    # Holdout guard must reject full-sample returns extending past 2016-12-30
    with pytest.raises(ValueError, match="Holdout discipline violation"):
        build_development_c1_risk_bundle(bundle.simple_returns, baseline_config)

    dev_end = baseline_config.chronology.development_end
    assert dev_end == "2016-12-30"
    dev_returns = bundle.simple_returns.loc[:dev_end].copy()
    assert len(dev_returns) == 3020
    assert str(dev_returns.index[0].date()) == "2005-01-04"
    assert str(dev_returns.index[-1].date()) == "2016-12-30"

    c1_bundle = build_development_c1_risk_bundle(dev_returns, baseline_config)
    assert c1_bundle["scope"] == "development_only_through_2016_12_30"
    assert c1_bundle["monte_carlo_seed"] == 202601
    assert c1_bundle["monte_carlo_simulations"] == 25000

    # Verify crisis coverage never claims a pre-2017 window includes COVID-19 (2020) or Rate Shock (2022)
    recent_cov = c1_bundle["window_coverage"]["recent_development_1260d"]
    assert recent_cov["sample_start"] == "2011-12-29"
    assert recent_cov["sample_end"] == "2016-12-30"
    assert recent_cov["included_scenarios"] == ()
    assert "gfc_2007_2009" in recent_cov["pre_window_omitted_scenarios"]
    assert set(recent_cov["post_window_scenarios"]) == {"covid_2020", "rate_shock_2022"}

    full_dev_cov = c1_bundle["window_coverage"]["full_development_3020d"]
    assert full_dev_cov["sample_start"] == "2005-01-04"
    assert full_dev_cov["sample_end"] == "2016-12-30"
    assert full_dev_cov["included_scenarios"] == ("gfc_2007_2009",)
    assert set(full_dev_cov["post_window_scenarios"]) == {"covid_2020", "rate_shock_2022"}

    # Verify all comparison tables across windows, portfolios, models, and confidences
    for win_id, expected_n in (("recent_development_1260d", 1260), ("full_development_3020d", 3020)):
        for port_id in ("min_variance", "equal_weight", "benchmark_60_40"):
            tbl = c1_bundle["comparison_tables"][win_id][port_id]
            assert len(tbl) == 9  # 3 models x 3 confidences (0.90, 0.95, 0.99)
            assert (tbl["status"] == "ok").all()
            assert (tbl["n_obs"] == expected_n).all()
            assert (tbl["es_loss"] >= tbl["var_loss"]).all()
            assert (tbl["var_loss"] > 0.0).all()

            m95_99 = c1_bundle["mandatory_95_99_tables"][win_id][port_id]
            assert len(m95_99) == 6
            assert set(m95_99["confidence"].unique()) == {0.95, 0.99}

            # Check fixed-exposure stationarity diagnostics exist for both simple and log1p returns
            stat_df = c1_bundle["fixed_exposure_diagnostics"][win_id][port_id]["stationarity_table"]
            assert len(stat_df) == 2
            assert (stat_df["status"] == "ok").all()


def test_r1_custom_config_propagation_across_primary_estimates_and_uncertainty(
    baseline_config: AppConfig,
) -> None:
    """R1: A genuinely different supplied AppConfig propagates draw count, seed, NAV, and config_hash consistently."""
    rng = np.random.default_rng(50113)
    toy_returns = pd.DataFrame(
        rng.normal(0.0002, 0.01, size=(80, len(CANONICAL_TICKERS))),
        index=pd.bdate_range("2015-01-02", periods=80),
        columns=list(CANONICAL_TICKERS),
    )

    custom_cfg = replace(
        baseline_config,
        mandate=replace(baseline_config.mandate, nav_usd=5_000_000.0),
        portfolio=replace(baseline_config.portfolio, estimation_window_days=20),
        risk=replace(
            baseline_config.risk,
            dashboard_risk_window_days=40,
            monte_carlo_simulations=111,
        ),
        seeds=replace(baseline_config.seeds, monte_carlo=42),
    )
    assert custom_cfg.config_hash != baseline_config.config_hash

    custom_bundle = build_development_c1_risk_bundle(toy_returns, custom_cfg)
    assert custom_bundle["config_hash"] == custom_cfg.config_hash
    assert custom_bundle["monte_carlo_seed"] == 42
    assert custom_bundle["monte_carlo_simulations"] == 111
    assert custom_bundle["nav_usd"] == 5_000_000.0

    # Verify comparison tables and mandatory 95/99 tables use 111 draws, seed 42, nav 5M, and custom config_hash
    for win_id, expected_n in (("recent_development_1260d", 40), ("full_development_3020d", 80)):
        for port_id in ("min_variance", "equal_weight", "benchmark_60_40"):
            tbl = custom_bundle["comparison_tables"][win_id][port_id]
            assert (tbl["n_obs"] == expected_n).all()
            assert (tbl["config_hash"] == custom_cfg.config_hash).all()
            assert tbl.attrs["config_hash"] == custom_cfg.config_hash
            assert tbl.attrs["monte_carlo_seed"] == 42
            assert tbl.attrs["monte_carlo_simulations"] == 111
            assert tbl.attrs["nav_usd"] == 5_000_000.0

            mc_rows = tbl.loc[tbl["model"] == "monte_carlo_normal"]
            assert len(mc_rows) == 3
            assert list(mc_rows["seed"]) == [42, 42, 42]
            assert list(mc_rows["monte_carlo_simulations"]) == [111, 111, 111]

            non_mc_rows = tbl.loc[tbl["model"] != "monte_carlo_normal"]
            assert all(v is None for v in non_mc_rows["seed"])
            assert all(v is None for v in non_mc_rows["monte_carlo_simulations"])

        # Verify MC uncertainty uses the exact same 111 draws, base_seed 42, config_hash, and matches primary seed estimates
        mv_tbl = custom_bundle["comparison_tables"][win_id]["min_variance"]
        for conf, c_key in ((0.90, "c_90"), (0.95, "c_95"), (0.99, "c_99")):
            unc = custom_bundle["mc_uncertainty"][win_id][c_key]
            assert unc["base_seed"] == 42
            assert unc["monte_carlo_simulations_per_rep"] == 111
            assert unc["config_hash"] == custom_cfg.config_hash
            assert unc["nav_usd"] == 5_000_000.0
            assert "M=111 draws" in unc["displayed_precision_note"]
            assert "base_seed=42" in unc["displayed_precision_note"]
            assert "M=25,000" not in unc["displayed_precision_note"]

            mc_row = mv_tbl.loc[
                (mv_tbl["model"] == "monte_carlo_normal") & (np.isclose(mv_tbl["confidence"], conf))
            ].iloc[0]
            assert math.isclose(unc["primary_seed_var_loss"], float(mc_row["var_loss"]), rel_tol=0.0, abs_tol=1e-15)
            assert math.isclose(unc["primary_seed_es_loss"], float(mc_row["es_loss"]), rel_tol=0.0, abs_tol=1e-15)

    # Confirm 111-draw primary estimates differ from 25,000-draw estimates on the same window/weights/seed
    mv_w = pd.Series(custom_bundle["exposures"]["min_variance"]["weights"], index=list(CANONICAL_TICKERS))
    default_mc_est = estimate_risk(toy_returns, mv_w, model="monte_carlo_normal", confidence=0.99, seed=42)
    custom_mc_99 = custom_bundle["comparison_tables"]["full_development_3020d"]["min_variance"].loc[
        lambda d: (d["model"] == "monte_carlo_normal") & np.isclose(d["confidence"], 0.99)
    ].iloc[0]
    assert default_mc_est.diagnostics["monte_carlo_simulations"] == 25000
    assert custom_mc_99["monte_carlo_simulations"] == 111
    assert float(custom_mc_99["var_loss"]) != float(default_mc_est.var_loss)


def test_r2_strict_json_export_baseline_preservation_and_step5_visible_outputs(
    repo_root: Path,
    baseline_config: AppConfig,
) -> None:
    """R2: Saved JSON parses under strict RFC 8259 rules (no NaN/Infinity), preserves all 54 baseline values, and backs visible exports."""
    def reject_non_json_number(token: str) -> None:
        raise ValueError(f"Non-standard JSON numeric token: {token}")

    saved_path = repo_root / "results" / "step5_development_c1_risk_tables.json"
    baseline_copy_path = repo_root / "audit" / "step5_review" / "baseline_step5_results.json"
    assert saved_path.exists()
    assert baseline_copy_path.exists()

    # 1. Strict RFC 8259 JSON parse must succeed with zero NaN/Infinity tokens
    saved_text = saved_path.read_text(encoding="utf-8")
    strict_saved = json.loads(saved_text, parse_constant=reject_non_json_number)
    # Re-dumping with allow_nan=False must also succeed
    json.dumps(strict_saved, allow_nan=False)

    # 2. Compare all 54 saved rows against preserved baseline_step5_results.json
    baseline_raw = json.loads(baseline_copy_path.read_text(encoding="utf-8"))
    row_count = 0
    for win_id, port_map in strict_saved["comparison_tables"].items():
        for port_id, rows in port_map.items():
            base_rows = baseline_raw["comparison_tables"][win_id][port_id]
            assert len(rows) == len(base_rows) == 9
            for row, base_row in zip(rows, base_rows):
                row_count += 1
                assert row["model"] == base_row["model"]
                assert row["confidence"] == base_row["confidence"]
                assert row["status"] == base_row["status"] == "ok"
                assert row["reason"] is None
                if row["model"] == "monte_carlo_normal":
                    assert row["seed"] == 202601
                    assert row["monte_carlo_simulations"] == 25000
                else:
                    assert row["seed"] is None
                    assert row["monte_carlo_simulations"] is None
                for metric_col in (
                    "var_loss",
                    "es_loss",
                    "es_minus_var",
                    "var_pct",
                    "es_pct",
                    "var_usd",
                    "es_usd",
                    "diff_vs_parametric_normal_var",
                    "diff_vs_parametric_normal_es",
                    "diff_vs_parametric_normal_var_bps",
                    "diff_vs_parametric_normal_es_bps",
                    "ratio_to_parametric_normal_var",
                    "ratio_to_parametric_normal_es",
                ):
                    assert row[metric_col] == base_row[metric_col]
    assert row_count == 54

    # 3. Verify comparison_table_to_records rejects corrupted NaN core risk values on status='ok' rows
    sample_df = pd.DataFrame(strict_saved["comparison_tables"]["recent_development_1260d"]["min_variance"])
    corrupted_df = sample_df.copy()
    corrupted_df.loc[0, "var_loss"] = float("nan")
    with pytest.raises(ValueError, match="Invalid non-finite core risk metric"):
        comparison_table_to_records(corrupted_df)

    # 4. Verify Step 5 visible outputs exist in results/step5_c1_preview/ and match manifest SHA-256 digests
    preview_dir = repo_root / "results" / "step5_c1_preview"
    manifest_path = preview_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"), parse_constant=reject_non_json_number)
    assert manifest["config_hash"] == baseline_config.config_hash
    assert manifest["development_end"] == "2016-12-30"
    assert manifest["monte_carlo_seed"] == 202601
    assert manifest["monte_carlo_simulations"] == 25000

    expected_artifacts = {
        "01_c1_risk_comparison_all_confidences.csv",
        "02_c1_mandatory_95_99_comparison.csv",
        "03_c1_fixed_exposures.csv",
        "04_c1_loss_moments_and_stationarity.csv",
        "05_c1_mc_uncertainty_64seeds.csv",
        "06_c1_fixed_exposure_daily_losses.csv",
        "figure_01_c1_var_es_95_99_comparison.png",
        "figure_01_c1_var_es_95_99_comparison.svg",
        "figure_02_c1_fixed_exposure_loss_distribution.png",
        "figure_02_c1_fixed_exposure_loss_distribution.svg",
        "figure_03_c1_mc_sampling_uncertainty.png",
        "figure_03_c1_mc_sampling_uncertainty.svg",
        "index.html",
        "README.md",
        "rendering-requirements.txt",
        "step5_development_c1_risk_tables.json",
    }
    assert expected_artifacts.issubset(set(manifest["artifacts_sha256"].keys()))
    for fname, expected_sha in manifest["artifacts_sha256"].items():
        fpath = preview_dir / fname
        assert fpath.exists(), f"Missing Step 5 preview artifact: {fname}"
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert actual_sha == expected_sha, f"SHA-256 mismatch for {fname}"

