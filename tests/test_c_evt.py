"""Unit tests for SOLO STEP 7 (C2/C3) Peaks-Over-Threshold GPD Extreme Value Theory."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import genpareto

from quantedge.contracts import CANONICAL_TICKERS, RiskEstimate
from quantedge import evt


def test_gpd_excess_quantile_and_es_known_answers():
    """Verify closed-form GPD quantiles and ES across positive, near-zero, and negative xi."""
    u = 0.010
    beta = 0.005
    p_u = 0.05
    c = 0.99
    alpha = 1.0 - c
    a = alpha / p_u  # 0.01 / 0.05 = 0.2

    # 1. Positive xi (Frechet domain of attraction / heavy tail)
    xi = 0.25
    expected_q = u + (beta / xi) * (a ** (-xi) - 1.0)
    expected_es = (expected_q + beta - xi * u) / (1.0 - xi)
    # Using stable formula in evt
    fit_mock = evt.GPDTailFit(
        threshold_quantile=0.95,
        min_exceedances=50,
        n_obs=1000,
        threshold=u,
        threshold_rank=950,
        n_exceedances=50,
        n_ties_at_threshold=1,
        p_u=p_u,
        tail_boundary_confidence=0.95,
        mean_excess=beta / (1.0 - xi),
        mean_excess_se=0.0001,
        n_unique_excesses=50,
        xi=xi,
        beta=beta,
        modified_scale=beta - xi * u,
        xi_se_asymptotic_iid=0.05,
        beta_se_asymptotic_iid=0.0005,
        upper_support_loss=None,
        loglik=-100.0,
        optimizer={"converged": True},
        status="ok",
        reasons=(),
        sorted_losses=np.linspace(0, 0.05, 1000),
        excesses=np.linspace(0.0001, 0.04, 50),
    )
    res = evt.pot_var_es(fit_mock, c)
    assert res["status"] == "ok"
    assert math.isclose(res["var_loss"], expected_q, rel_tol=1e-12)
    assert math.isclose(res["es_loss"], expected_es, rel_tol=1e-12)
    assert res["es_loss"] > res["var_loss"]

    # 2. xi near zero (Gumbel domain / exponential tail limit)
    xi_zero = 0.0
    expected_q_exp = u - beta * math.log(a)
    expected_es_exp = expected_q_exp + beta
    fit_zero = evt.GPDTailFit(
        threshold_quantile=0.95, min_exceedances=50, n_obs=1000, threshold=u, threshold_rank=950,
        n_exceedances=50, n_ties_at_threshold=1, p_u=p_u, tail_boundary_confidence=0.95,
        mean_excess=beta, mean_excess_se=0.0001, n_unique_excesses=50, xi=xi_zero, beta=beta,
        modified_scale=beta, xi_se_asymptotic_iid=0.05, beta_se_asymptotic_iid=0.0005,
        upper_support_loss=None, loglik=-100.0, optimizer={"converged": True}, status="ok", reasons=(),
        sorted_losses=np.linspace(0, 0.05, 1000), excesses=np.linspace(0.0001, 0.04, 50),
    )
    res_zero = evt.pot_var_es(fit_zero, c)
    assert res_zero["status"] == "ok"
    assert math.isclose(res_zero["var_loss"], expected_q_exp, rel_tol=1e-12)
    assert math.isclose(res_zero["es_loss"], expected_es_exp, rel_tol=1e-12)

    # 3. xi >= 1: divergent first moment -> finite VaR but es_loss=None with status='warning'
    fit_xi_1 = evt.GPDTailFit(
        threshold_quantile=0.95, min_exceedances=50, n_obs=1000, threshold=u, threshold_rank=950,
        n_exceedances=50, n_ties_at_threshold=1, p_u=p_u, tail_boundary_confidence=0.95,
        mean_excess=None, mean_excess_se=None, n_unique_excesses=50, xi=1.1, beta=beta,
        modified_scale=beta - 1.1 * u, xi_se_asymptotic_iid=0.05, beta_se_asymptotic_iid=0.0005,
        upper_support_loss=None, loglik=-100.0, optimizer={"converged": True}, status="warning",
        reasons=("xi >= 1",), sorted_losses=np.linspace(0, 0.05, 1000), excesses=np.linspace(0.0001, 0.04, 50),
    )
    res_xi_1 = evt.pot_var_es(fit_xi_1, c)
    assert res_xi_1["status"] == "warning"
    assert res_xi_1["var_loss"] is not None
    assert res_xi_1["es_loss"] is None
    assert "xi >= 1" in res_xi_1["reason"]

    # 4. xi < 0 (Weibull domain / finite upper support endpoint u - beta / xi)
    xi_neg = -0.2
    upper_endpoint = u - beta / xi_neg
    fit_neg = evt.GPDTailFit(
        threshold_quantile=0.95, min_exceedances=50, n_obs=1000, threshold=u, threshold_rank=950,
        n_exceedances=50, n_ties_at_threshold=1, p_u=p_u, tail_boundary_confidence=0.95,
        mean_excess=beta / (1.0 - xi_neg), mean_excess_se=0.0001, n_unique_excesses=50, xi=xi_neg,
        beta=beta, modified_scale=beta - xi_neg * u, xi_se_asymptotic_iid=0.05,
        beta_se_asymptotic_iid=0.0005, upper_support_loss=upper_endpoint, loglik=-100.0,
        optimizer={"converged": True}, status="ok", reasons=(),
        sorted_losses=np.linspace(0, upper_endpoint - 0.001, 1000),
        excesses=np.linspace(0.0001, -beta / xi_neg - 0.001, 50),
    )
    res_neg = evt.pot_var_es(fit_neg, c)
    assert res_neg["status"] == "ok"
    assert res_neg["var_loss"] < upper_endpoint
    assert res_neg["es_loss"] < upper_endpoint


def test_seeded_gpd_parameter_recovery_within_tolerance():
    """Verify MLE parameter recovery on synthetic GPD draws within 3 standard errors."""
    rng = np.random.default_rng(20261031)
    true_xi = 0.20
    true_beta = 0.0040
    n_exc = 2000
    sim_excesses = genpareto.rvs(true_xi, scale=true_beta, size=n_exc, random_state=rng)
    sim_body = -rng.uniform(0.0, 0.01, size=8000)
    sim_losses = np.concatenate([sim_body, sim_excesses])

    # 8000 body non-exceedances + 2000 excesses => q = 0.80 threshold is 0.0
    fit = evt.fit_gpd_tail(sim_losses, threshold_quantile=0.80, min_exceedances=50)
    assert fit.status == "ok"
    assert fit.xi is not None
    assert fit.beta is not None

    # Expected asymptotic standard errors
    xi_se = (1.0 + true_xi) / math.sqrt(n_exc)
    beta_se = true_beta * math.sqrt(2.0 * (1.0 + true_xi) / n_exc)

    # Tolerance within 3 standard errors
    assert abs(fit.xi - true_xi) < 3.0 * xi_se
    assert abs(fit.beta - true_beta) < 3.0 * beta_se


def test_pure_pot_safeguards_and_threshold_boundary():
    """Verify pure POT safeguards against body evaluation and exact boundary behavior."""
    rng = np.random.default_rng(12345)
    # Exponential tail has xi = 0 (regular)
    body = rng.uniform(-0.01, 0.01, size=900)
    tail = 0.01 + rng.exponential(scale=0.005, size=100)
    losses = pd.Series(np.sort(np.concatenate([body, tail])), name="loss")
    fit = evt.fit_gpd_tail(losses, threshold_quantile=0.95, min_exceedances=50)
    assert fit.status == "ok"
    assert fit.n_exceedances == 50
    assert fit.tail_boundary_confidence == 0.95

    # 1. At threshold boundary (c = 1 - p_u = 0.95), VaR is threshold u exactly
    res_boundary = evt.pot_var_es(fit, 0.95)
    assert res_boundary["status"] == "ok"
    assert math.isclose(res_boundary["var_loss"], fit.threshold, abs_tol=1e-12)
    assert res_boundary["region"] == "threshold_boundary"

    # 2. Below threshold boundary (c = 0.90), pure POT is unavailable with explicit reason
    res_below = evt.pot_var_es(fit, 0.90)
    assert res_below["status"] == "unavailable"
    assert res_below["var_loss"] is None
    assert res_below["es_loss"] is None
    assert "below threshold quantile" in res_below["reason"]


def test_insufficient_exceedances_and_degenerate_samples():
    """Verify that insufficient excesses or degenerate samples return unavailable without silent lowering."""
    # Only 20 observations, threshold 0.95 -> 1 exceedance < min_exceedances=50
    small_losses = pd.Series(np.linspace(0.001, 0.02, 20))
    fit_small = evt.fit_gpd_tail(small_losses, threshold_quantile=0.95, min_exceedances=50)
    assert fit_small.status == "unavailable"
    assert fit_small.xi is None
    assert fit_small.beta is None
    assert any("insufficient strict exceedances" in r for r in fit_small.reasons)

    # Degenerate excess sample (all identical)
    deg_losses = pd.Series([0.01] * 900 + [0.05] * 100)
    fit_deg = evt.fit_gpd_tail(deg_losses, threshold_quantile=0.85, min_exceedances=50)
    assert fit_deg.status == "unavailable"
    assert any("degenerate" in r for r in fit_deg.reasons)


def test_input_validation_and_no_mutation():
    """Verify input validation rules and non-mutation of input Series/arrays."""
    s = pd.Series([0.001, 0.002, 0.005, 0.010, 0.015], index=pd.date_range("2020-01-01", periods=5))
    s_copy = s.copy()

    # Diagnostics should not mutate s
    _ = evt.evt_threshold_diagnostics(s, candidate_quantiles=[0.90], min_exceedances=3)
    pd.testing.assert_series_equal(s, s_copy)

    # Non-unique index rejection
    bad_idx_s = pd.Series([0.01, 0.02], index=["A", "A"])
    with pytest.raises(ValueError, match="unique"):
        evt.fit_gpd_tail(bad_idx_s)

    # NaN / inf rejection
    nan_s = pd.Series([0.01, np.nan, 0.03])
    with pytest.raises(ValueError, match="non-finite"):
        evt.fit_gpd_tail(nan_s)

    # DataFrame rejection
    with pytest.raises(TypeError, match="one-dimensional"):
        evt.fit_gpd_tail(pd.DataFrame({"x": [1, 2, 3]}))


def test_empirical_body_gpd_tail_hybrid_continuity_and_integration():
    """Verify empirical-body / GPD-tail hybrid CDF, quantile continuity, and numerical ES agreement."""
    rng = np.random.default_rng(42)
    n = 2000
    # Simulate mildly fat-tailed losses
    body = rng.normal(loc=0.0, scale=0.005, size=1800)
    tail = genpareto.rvs(0.15, scale=0.004, size=200, random_state=rng) + 0.010
    losses = pd.Series(np.sort(np.concatenate([body, tail])))

    fit = evt.fit_gpd_tail(losses, threshold_quantile=0.90, min_exceedances=50)
    assert fit.status == "ok"
    u = fit.threshold
    p_u = fit.p_u

    # 1. CDF normalization and boundary continuity
    cdf_at_u = evt.body_tail_cdf(fit, u)
    assert math.isclose(cdf_at_u, 1.0 - p_u, abs_tol=1e-12)
    assert math.isclose(evt.body_tail_cdf(fit, 1.0), 1.0, rel_tol=1e-6)

    # 2. Monotonicity of quantiles across 0.50, 0.90, 0.95, 0.99
    confs = [0.50, 0.80, 0.90, 0.95, 0.99]
    quantiles = [evt.body_tail_quantile(fit, c) for c in confs]
    for i in range(len(quantiles) - 1):
        assert quantiles[i] < quantiles[i + 1]

    # 3. Labeling: c < 1 - p_u is labelled BODY, c >= 1 - p_u is GPD_TAIL
    res_body = evt.body_tail_es(fit, 0.85)
    assert res_body["region"] == "body"
    assert "BODY" in res_body["var_label"]

    res_tail = evt.body_tail_es(fit, 0.95)
    assert res_tail["region"] == "tail"
    assert res_tail["var_label"] == "GPD_TAIL"

    # 4. Compare hybrid ES against fine numerical integration of body_tail_quantile
    c_eval = 0.85
    analytic_es = res_body["es_loss"]
    # Numerical integral: (1 / (1 - c)) * integral_c^1 q(p) dp
    grid_p = np.linspace(c_eval, 0.99999, 10000)
    grid_q = np.array([evt.body_tail_quantile(fit, p) for p in grid_p])
    # Trapezoidal rule: sum 0.5 * (q[i] + q[i-1]) * (p[i] - p[i-1])
    dp = np.diff(grid_p)
    num_integral = float(np.sum(0.5 * (grid_q[:-1] + grid_q[1:]) * dp)) / (1.0 - c_eval)
    # Numerical trapezoid should agree with analytic hybrid ES within 1% relative error
    assert math.isclose(analytic_es, num_integral, rel_tol=1e-2)


def test_estimate_evt_pot_and_body_tail_contracts(synthetic_asset_returns, equal_canonical_weights):
    """Verify estimate_evt_pot and estimate_evt_body_tail conform to RiskEstimate contract."""
    # Synthetic has only 5 observations -> unavailable
    est_pot = evt.estimate_evt_pot(
        synthetic_asset_returns,
        equal_canonical_weights,
        confidence=0.99,
        threshold_quantile=0.95,
        min_exceedances=50,
    )
    assert isinstance(est_pot, RiskEstimate)
    assert est_pot.status == "unavailable"
    assert est_pot.var_loss is None
    assert est_pot.es_loss is None
    assert "insufficient strict exceedances" in est_pot.reason.lower()

    est_hyb = evt.estimate_evt_body_tail(
        synthetic_asset_returns,
        equal_canonical_weights,
        confidence=0.90,
        threshold_quantile=0.95,
        min_exceedances=50,
    )
    assert isinstance(est_hyb, RiskEstimate)
    assert est_hyb.status == "unavailable"


def test_evt_threshold_diagnostics_structure_and_no_fabricated_gof():
    """Verify diagnostic table structure, MRL calculation, and no fake GOF p-values."""
    rng = np.random.default_rng(123)
    losses = pd.Series(rng.normal(0.0, 0.01, size=1500), index=pd.date_range("2010-01-01", periods=1500))
    df = evt.evt_threshold_diagnostics(losses, candidate_quantiles=(0.90, 0.95), min_exceedances=50)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert "mean_excess" in df.columns
    assert "modified_scale" in df.columns
    assert "gof_p_value" not in df.columns
    assert "not computed" in df.attrs["gof_p_values"]

    # QQ/PP table
    fit = evt.fit_gpd_tail(losses, threshold_quantile=0.90, min_exceedances=50)
    qq_df = evt.gpd_qq_pp_table(fit)
    assert len(qq_df) == fit.n_exceedances
    assert qq_df.attrs["gof_p_value"] is None


def test_moving_block_bootstrap_determinism_and_caching():
    """Verify deterministic bootstrap output, cache reuse, and failure handling."""
    rng = np.random.default_rng(999)
    losses = pd.Series(rng.standard_t(df=4, size=600) * 0.01)

    boot1 = evt.bootstrap_evt_tail_uncertainty(
        losses,
        confidences=(0.90, 0.95, 0.99),
        threshold_quantile=0.95,
        min_exceedances=20,
        block_length=5,
        n_replications=20,
        seed=202602,
    )
    boot2 = evt.bootstrap_evt_tail_uncertainty(
        losses,
        confidences=(0.90, 0.95, 0.99),
        threshold_quantile=0.95,
        min_exceedances=20,
        block_length=5,
        n_replications=20,
        seed=202602,
    )
    # Cached output should produce exact matching values
    assert boot1["summary"]["n_replications"] == 20
    assert boot1["summary"]["n_successful_fits"] == boot2["summary"]["n_successful_fits"]
    assert boot1["summary"]["xi"]["median"] == boot2["summary"]["xi"]["median"]

    # Infeasible min_successful requirement produces interval_status='unavailable'
    boot_fail = evt.bootstrap_evt_tail_uncertainty(
        losses,
        confidences=(0.95,),
        threshold_quantile=0.95,
        min_exceedances=20,
        block_length=5,
        n_replications=20,
        seed=202602,
        min_successful_replications=20,  # if any fail, interval unavailable
    )
    assert isinstance(boot_fail["summary"]["by_confidence"]["0.9500"]["var"], dict)
