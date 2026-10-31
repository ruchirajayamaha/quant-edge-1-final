"""Unit, mathematical invariant, and development-period smoke tests for SOLO STEP 3 (B1)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantedge import (
    AppConfig,
    CANONICAL_TICKERS,
    PortfolioConstraints,
    StrategySpec,
)
from quantedge.data import load_data
from quantedge.portfolio import (
    PortfolioOptimizationError,
    _solve_min_variance_from_covariance,
    build_portfolio_path,
    check_weight_feasibility,
    compute_implied_weight_bounds,
    construct_weights,
    make_core_strategy_specs,
    summarize_pre_return_holdings_compliance,
)


def _make_exact_diagonal_cov_returns(
    sigmas: dict[str, float],
    *,
    n_obs: int = 16,
    start_date: str = "2020-01-02",
) -> pd.DataFrame:
    """Build deterministic zero-mean orthogonal returns whose sample ``cov(ddof=1)`` is exact diagonal."""
    assert n_obs >= 9, "Need at least 9 rows for 7 zero-mean orthogonal basis columns."
    rng = np.random.default_rng(20261031)
    raw = rng.standard_normal((n_obs, len(CANONICAL_TICKERS)))
    # Project out the constant vector 1 so every column has exact zero sample mean, then orthonormalize.
    centered = raw - raw.mean(axis=0, keepdims=True)
    q, _ = np.linalg.qr(centered)
    # Re-center and re-orthonormalize once to guarantee mean == 0 and Q^T Q == I to ~1e-16.
    q = q - q.mean(axis=0, keepdims=True)
    q, _ = np.linalg.qr(q)
    scale = np.sqrt(float(n_obs - 1))
    cols = {
        ticker: q[:, idx] * scale * float(sigmas[ticker])
        for idx, ticker in enumerate(CANONICAL_TICKERS)
    }
    dates = pd.bdate_range(start_date, periods=n_obs)
    return pd.DataFrame(cols, index=dates, columns=list(CANONICAL_TICKERS))


def test_known_answer_min_variance_interior_and_cap_binding() -> None:
    """Minimum-variance weights match exact closed-form KKT solutions for interior and cap-active cases."""
    # Case 1: Interior unconstrained-equivalent inverse-variance weights w_i propto 1 / sigma_i^2.
    sigmas_interior = {
        "SPY": 0.012,
        "EFA": 0.014,
        "EEM": 0.018,
        "AGG": 0.008,
        "GLD": 0.010,
        "XLE": 0.020,
        "XLK": 0.015,
    }
    train_interior = _make_exact_diagonal_cov_returns(sigmas_interior)
    cov_check = train_interior.cov(ddof=1).to_numpy()
    expected_diag = np.array([sigmas_interior[t] ** 2 for t in CANONICAL_TICKERS])
    assert np.allclose(cov_check, np.diag(expected_diag), atol=1e-15)

    loose_constraints = PortfolioConstraints(
        long_only=True,
        fully_invested=True,
        min_weight_per_etf=0.0,
        max_weight_per_etf=0.80,
        max_equity_weight=0.95,
        min_defensive_weight=0.05,
    )
    w_interior = construct_weights(train_interior, loose_constraints, "min_variance")
    inv_var = 1.0 / expected_diag
    analytic_interior = inv_var / inv_var.sum()

    assert tuple(w_interior.index) == CANONICAL_TICKERS
    assert np.allclose(w_interior.to_numpy(), analytic_interior, atol=1e-9)
    assert w_interior.attrs["mandate_feasible"] is True
    assert w_interior.attrs["solver_status"] == "optimal"

    # Case 2: Provisional mandate constraints where AGG upper cap (0.40) binds, GLD sits strictly
    # interior at 1/3, and the 5 identical-variance equities split 4/15 equally (4/75 each).
    sigmas_partial_cap = {
        "SPY": 0.020,
        "EFA": 0.020,
        "EEM": 0.020,
        "AGG": 0.002,
        "GLD": 0.008,
        "XLE": 0.020,
        "XLK": 0.020,
    }
    train_partial = _make_exact_diagonal_cov_returns(sigmas_partial_cap)
    provisional_constraints = PortfolioConstraints()
    w_partial = construct_weights(train_partial, provisional_constraints, "min_variance")
    analytic_partial = pd.Series(
        {
            "SPY": 4.0 / 75.0,
            "EFA": 4.0 / 75.0,
            "EEM": 4.0 / 75.0,
            "AGG": 0.40,
            "GLD": 1.0 / 3.0,
            "XLE": 4.0 / 75.0,
            "XLK": 4.0 / 75.0,
        },
        index=CANONICAL_TICKERS,
    )
    assert np.allclose(w_partial.to_numpy(), analytic_partial.to_numpy(), atol=1e-8)

    # Case 3: Both max_equity_weight (0.35 -> 0.07 each) and AGG max_weight_per_etf (0.40) bind,
    # forcing GLD onto its implied lower bound 1 - 0.35 - 0.40 = 0.25.
    sigmas_double_cap = {
        "SPY": 0.003,
        "EFA": 0.003,
        "EEM": 0.003,
        "AGG": 0.005,
        "GLD": 0.025,
        "XLE": 0.003,
        "XLK": 0.003,
    }
    train_double = _make_exact_diagonal_cov_returns(sigmas_double_cap)
    w_double = construct_weights(train_double, provisional_constraints, "min_variance")
    analytic_double = pd.Series(
        {
            "SPY": 0.07,
            "EFA": 0.07,
            "EEM": 0.07,
            "AGG": 0.40,
            "GLD": 0.25,
            "XLE": 0.07,
            "XLK": 0.07,
        },
        index=CANONICAL_TICKERS,
    )
    assert np.allclose(w_double.to_numpy(), analytic_double.to_numpy(), atol=1e-8)


def test_implied_provisional_bounds_and_reference_violation_labelling(
    baseline_config: AppConfig,
    synthetic_asset_returns: pd.DataFrame,
) -> None:
    """Provisional caps imply AGG/GLD in [25%, 40%] and equities in [20%, 35%]; references are labelled."""
    constraints = baseline_config.portfolio.constraints
    bounds_df = compute_implied_weight_bounds(constraints).set_index("name")

    for def_ticker in ("AGG", "GLD"):
        assert np.isclose(bounds_df.loc[def_ticker, "implied_min"], 0.25, atol=1e-9)
        assert np.isclose(bounds_df.loc[def_ticker, "implied_max"], 0.40, atol=1e-9)
        assert bool(bounds_df.loc[def_ticker, "min_tightened_by_interaction"]) is True

    for eq_ticker in ("SPY", "EFA", "EEM", "XLE", "XLK"):
        assert np.isclose(bounds_df.loc[eq_ticker, "implied_min"], 0.00, atol=1e-9)
        assert np.isclose(bounds_df.loc[eq_ticker, "implied_max"], 0.35, atol=1e-9)
        assert bool(bounds_df.loc[eq_ticker, "max_tightened_by_interaction"]) is True

    assert np.isclose(bounds_df.loc["EQUITY_TOTAL", "implied_min"], 0.20, atol=1e-9)
    assert np.isclose(bounds_df.loc["EQUITY_TOTAL", "implied_max"], 0.35, atol=1e-9)
    assert np.isclose(bounds_df.loc["DEFENSIVE_TOTAL", "implied_min"], 0.65, atol=1e-9)
    assert np.isclose(bounds_df.loc["DEFENSIVE_TOTAL", "implied_max"], 0.80, atol=1e-9)

    # Equal-weight reference (5/7 = 71.43% equities > 35% cap)
    w_eq = construct_weights(synthetic_asset_returns, constraints, "equal_weight")
    assert np.allclose(w_eq.to_numpy(), np.full(7, 1.0 / 7.0), atol=1e-12)
    assert w_eq.attrs["mandate_feasible"] is False
    assert (
        w_eq.attrs["mandate_compliance_label"]
        == "unconstrained_reference_violates_provisional_caps"
    )
    assert any("max_equity_weight" in msg for msg in w_eq.attrs["mandate_violations"])

    # 60/40 SPY/AGG reference (SPY = 60% > 40% single-ETF cap and > 35% equity cap)
    w_60_40 = construct_weights(synthetic_asset_returns, constraints, "benchmark_60_40")
    assert np.isclose(w_60_40["SPY"], 0.60) and np.isclose(w_60_40["AGG"], 0.40)
    assert np.isclose(w_60_40.drop(["SPY", "AGG"]).abs().sum(), 0.0)
    assert w_60_40.attrs["mandate_feasible"] is False
    assert (
        w_60_40.attrs["mandate_compliance_label"]
        == "unconstrained_reference_violates_provisional_caps"
    )
    assert any("max_weight_per_etf" in msg for msg in w_60_40.attrs["mandate_violations"])
    assert any("max_equity_weight" in msg for msg in w_60_40.attrs["mandate_violations"])


def test_infeasible_constraints_and_invalid_inputs_raise_without_silent_repair(
    synthetic_asset_returns: pd.DataFrame,
) -> None:
    """Infeasible constraint sets and non-PSD/asymmetric covariances raise PortfolioOptimizationError."""
    infeasible_cases = [
        # 7 * 0.10 = 0.70 < 1.0
        PortfolioConstraints(max_weight_per_etf=0.10),
        # equities <= 0.15 and AGG + GLD <= 0.80 -> total <= 0.95 < 1.0
        PortfolioConstraints(max_weight_per_etf=0.40, max_equity_weight=0.15),
        # 7 * 0.20 = 1.40 > 1.0
        PortfolioConstraints(min_weight_per_etf=0.20, max_weight_per_etf=0.40),
        # AGG + GLD >= 0.85 while each <= 0.40 -> max defensive is 0.80 < 0.85
        PortfolioConstraints(max_weight_per_etf=0.40, min_defensive_weight=0.85),
    ]
    for bad_constraints in infeasible_cases:
        with pytest.raises(PortfolioOptimizationError):
            construct_weights(synthetic_asset_returns, bad_constraints, "min_variance")
        with pytest.raises(PortfolioOptimizationError):
            compute_implied_weight_bounds(bad_constraints)

    # Single observation cannot estimate sample covariance with ddof=1
    with pytest.raises(PortfolioOptimizationError, match="at least 2 observations"):
        construct_weights(synthetic_asset_returns.iloc[:1], PortfolioConstraints(), "min_variance")

    # Indefinite (non-PSD) symmetric matrix must fail explicitly
    bad_psd = np.eye(7, dtype=float) * 1e-4
    bad_psd[0, 0] = -1e-4
    with pytest.raises(PortfolioOptimizationError, match="not positive semi-definite"):
        _solve_min_variance_from_covariance(bad_psd, PortfolioConstraints())

    # Asymmetric matrix must fail symmetry verification
    bad_sym = np.eye(7, dtype=float) * 1e-4
    bad_sym[0, 1] = 5e-5
    with pytest.raises(PortfolioOptimizationError, match="symmetry"):
        _solve_min_variance_from_covariance(bad_sym, PortfolioConstraints())

    # Permuted ticker order must fail fast
    permuted = synthetic_asset_returns.loc[:, ["AGG", "SPY", "EFA", "EEM", "GLD", "XLE", "XLK"]]
    with pytest.raises(ValueError, match="canonical order"):
        construct_weights(permuted, PortfolioConstraints(), "min_variance")


def test_hand_calculated_drift_turnover_5bps_costs_and_initial_wealth_drawdown(
    baseline_config: AppConfig,
) -> None:
    """Exact 4-day hand-checked path verifies drift, monthly rebalance, 5 bps cost, and day-1 drawdown."""
    dates = pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"])
    returns = pd.DataFrame(0.0, index=dates, columns=list(CANONICAL_TICKERS))
    # Day 0 (2024-01-30): SPY -5%, AGG +2.5% -> negative initial day tests initial wealth 1.0 drawdown
    returns.loc["2024-01-30", "SPY"] = -0.05
    returns.loc["2024-01-30", "AGG"] = 0.025
    # Day 1 (2024-01-31): SPY +10%, AGG 0% -> drifts weights further away from 60/40 before Feb 1
    returns.loc["2024-01-31", "SPY"] = 0.10
    returns.loc["2024-01-31", "AGG"] = 0.00
    # Day 2 (2024-02-01, month boundary rebalance back to 60/40): SPY +1%, AGG -0.5%
    returns.loc["2024-02-01", "SPY"] = 0.01
    returns.loc["2024-02-01", "AGG"] = -0.005
    # Day 3 (2024-02-02, drift day): SPY -2%, AGG 0%
    returns.loc["2024-02-02", "SPY"] = -0.02
    returns.loc["2024-02-02", "AGG"] = 0.00

    spec = StrategySpec(
        strategy_id="bm_60_40_handcheck",
        objective="benchmark_60_40",
        rebalance_frequency="M",
        estimation_window_days=None,
    )
    path = build_portfolio_path(returns, spec, baseline_config)

    # Hand-derived exact numbers:
    # Day 0: w_before = (0.60, 0.40); turnover = 1.0; cost = 0.0005
    gross_0 = 0.60 * (-0.05) + 0.40 * 0.025  # -0.02
    cost_0 = 0.0005
    net_0 = (1.0 - cost_0) * (1.0 + gross_0) - 1.0  # -0.02049
    wealth_0 = 1.0 + net_0  # 0.97951
    dd_0 = wealth_0 / 1.0 - 1.0  # -0.02049 (strictly < 0 because initial wealth 1.0 is included)
    w_spy_d1 = 0.60 * 0.95 / (1.0 + gross_0)  # 0.57 / 0.98 = 57/98
    w_agg_d1 = 0.40 * 1.025 / (1.0 + gross_0)  # 0.41 / 0.98 = 41/98

    # Day 1 (drift, no rebalance): turnover = 0.0; cost = 0.0
    gross_1 = w_spy_d1 * 0.10 + w_agg_d1 * 0.0  # 5.7 / 98
    net_1 = gross_1
    wealth_1 = wealth_0 * (1.0 + net_1)
    peak_1 = max(1.0, wealth_0, wealth_1)
    dd_1 = wealth_1 / peak_1 - 1.0
    w_spy_pre_feb = w_spy_d1 * 1.10 / (1.0 + gross_1)  # 62.7 / 103.7
    w_agg_pre_feb = w_agg_d1 * 1.00 / (1.0 + gross_1)  # 41.0 / 103.7

    # Day 2 (2024-02-01 monthly rebalance back to 0.60 / 0.40):
    turn_2 = abs(0.60 - w_spy_pre_feb) + abs(0.40 - w_agg_pre_feb)  # 0.96 / 103.7
    cost_2 = 0.0005 * turn_2
    gross_2 = 0.60 * 0.01 + 0.40 * (-0.005)  # +0.004
    net_2 = (1.0 - cost_2) * (1.0 + gross_2) - 1.0
    wealth_2 = wealth_1 * (1.0 + net_2)
    peak_2 = max(1.0, wealth_0, wealth_1, wealth_2)
    dd_2 = wealth_2 / peak_2 - 1.0
    w_spy_d3 = 0.60 * 1.01 / (1.0 + gross_2)
    w_agg_d3 = 0.40 * 0.995 / (1.0 + gross_2)

    # Day 3 (drift):
    gross_3 = w_spy_d3 * (-0.02) + w_agg_d3 * 0.0
    net_3 = gross_3
    wealth_3 = wealth_2 * (1.0 + net_3)
    peak_3 = max(1.0, wealth_0, wealth_1, wealth_2, wealth_3)
    dd_3 = wealth_3 / peak_3 - 1.0

    assert np.allclose(path.weights_before["SPY"].to_numpy(), [0.60, w_spy_d1, 0.60, w_spy_d3], atol=1e-14)
    assert np.allclose(path.weights_before["AGG"].to_numpy(), [0.40, w_agg_d1, 0.40, w_agg_d3], atol=1e-14)
    assert np.allclose(path.weights_before.sum(axis=1).to_numpy(), np.ones(4), atol=1e-14)
    assert np.allclose(path.turnover.to_numpy(), [1.0, 0.0, turn_2, 0.0], atol=1e-14)
    assert np.allclose(path.costs.to_numpy(), [cost_0, 0.0, cost_2, 0.0], atol=1e-15)
    assert np.allclose(path.gross_returns.to_numpy(), [gross_0, gross_1, gross_2, gross_3], atol=1e-14)
    assert np.allclose(path.net_returns.to_numpy(), [net_0, net_1, net_2, net_3], atol=1e-14)
    assert np.allclose(path.wealth.to_numpy(), [wealth_0, wealth_1, wealth_2, wealth_3], atol=1e-14)
    assert np.allclose(path.drawdown.to_numpy(), [dd_0, dd_1, dd_2, dd_3], atol=1e-14)
    assert path.drawdown.iloc[0] < -0.02  # Proves initial wealth 1.0 is included on day 0
    assert len(path.rebalances) == 2
    assert np.isclose(path.rebalances.loc[1, "half_turnover"], 0.5 * turn_2, atol=1e-14)


def test_future_data_invariance_and_shared_benchmark_engine(
    baseline_config: AppConfig,
) -> None:
    """Perturbing returns on or after session t never alters weights_before.loc[:t] or prior rebalances."""
    rng = np.random.default_rng(202603)
    dates = pd.bdate_range("2023-01-02", periods=95)
    base_returns = pd.DataFrame(
        rng.normal(loc=0.0003, scale=0.011, size=(len(dates), len(CANONICAL_TICKERS))),
        index=dates,
        columns=list(CANONICAL_TICKERS),
    )

    specs = make_core_strategy_specs(baseline_config, estimation_window_days=20)
    paths_base = {
        name: build_portfolio_path(base_returns, spec, baseline_config)
        for name, spec in specs.items()
    }

    # All three core candidates run through the single shared engine on identical dates/rebalances
    assert paths_base["min_variance"].weights_before.index.equals(
        paths_base["equal_weight"].weights_before.index
    )
    assert paths_base["min_variance"].weights_before.index.equals(
        paths_base["benchmark_60_40"].weights_before.index
    )
    assert paths_base["min_variance"].rebalances["effective_date"].equals(
        paths_base["benchmark_60_40"].rebalances["effective_date"]
    )

    # Test future-data invariance at both a rebalance boundary date and an interior drift date
    reb_cut = pd.Timestamp(paths_base["min_variance"].rebalances["effective_date"].iloc[2])
    drift_cut = paths_base["min_variance"].weights_before.index[35]

    for cut_date in (reb_cut, drift_cut):
        perturbed = base_returns.copy()
        # Mutate returns ON cut_date and every future date >= cut_date
        future_mask = perturbed.index >= cut_date
        perturbed.loc[future_mask, :] = -0.18
        perturbed.loc[future_mask, "AGG"] = 0.09
        perturbed.loc[future_mask, "GLD"] = 0.14

        path_pert = build_portfolio_path(perturbed, specs["min_variance"], baseline_config)
        path_orig = paths_base["min_variance"]

        # weights_before, turnover, and costs ON and BEFORE cut_date must be bit-for-bit identical
        pd.testing.assert_frame_equal(
            path_orig.weights_before.loc[:cut_date],
            path_pert.weights_before.loc[:cut_date],
            check_exact=True,
        )
        pd.testing.assert_series_equal(
            path_orig.turnover.loc[:cut_date],
            path_pert.turnover.loc[:cut_date],
            check_exact=True,
        )
        pd.testing.assert_series_equal(
            path_orig.costs.loc[:cut_date],
            path_pert.costs.loc[:cut_date],
            check_exact=True,
        )

        # Realized returns, wealth, and drawdown strictly BEFORE cut_date must be bit-for-bit identical
        strictly_prior = path_orig.gross_returns.index < cut_date
        pd.testing.assert_series_equal(
            path_orig.gross_returns.loc[strictly_prior],
            path_pert.gross_returns.loc[strictly_prior],
            check_exact=True,
        )
        pd.testing.assert_series_equal(
            path_orig.wealth.loc[strictly_prior],
            path_pert.wealth.loc[strictly_prior],
            check_exact=True,
        )

        orig_reb = path_orig.rebalances.loc[
            path_orig.rebalances["effective_date"] <= cut_date
        ].reset_index(drop=True)
        pert_reb = path_pert.rebalances.loc[
            path_pert.rebalances["effective_date"] <= cut_date
        ].reset_index(drop=True)
        pd.testing.assert_frame_equal(orig_reb, pert_reb, check_exact=True)


def test_corrupted_solver_result_is_rejected_never_clipped_or_renormalized(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_asset_returns: pd.DataFrame,
) -> None:
    """If an underlying solver ever returns an out-of-bounds or unnormalized vector, raise rather than clip/renormalize."""
    import quantedge.portfolio as portfolio_mod
    from scipy.optimize import OptimizeResult

    # 1. Rank-deficient 5-row sample covariance solves cleanly under real SLSQP + HiGHS KKT check
    w_rank_def = construct_weights(synthetic_asset_returns, PortfolioConstraints(), "min_variance")
    assert check_weight_feasibility(w_rank_def, PortfolioConstraints(), tol=1e-7)["feasible"] is True
    assert w_rank_def.attrs["duality_gap_scaled"] <= 1e-7

    # 2. Simulate a buggy solver claiming success=True with a slightly negative weight and sum != 1
    bad_vector = np.array([-0.01, 0.10, 0.10, 0.41, 0.41, 0.00, 0.00], dtype=float)
    monkeypatch.setattr(
        portfolio_mod,
        "minimize",
        lambda *args, **kwargs: OptimizeResult(
            x=bad_vector.copy(),
            success=True,
            status=0,
            message="mocked invalid solver output",
        ),
    )
    with pytest.raises(PortfolioOptimizationError, match="without clipping/renormalization"):
        construct_weights(synthetic_asset_returns, PortfolioConstraints(), "min_variance")


def test_fixed_weights_path_and_invalid_fixed_weight_rejection(
    baseline_config: AppConfig,
    synthetic_asset_returns: pd.DataFrame,
) -> None:
    """Custom fixed_weights share build_portfolio_path and reject non-canonical, negative, or unnormalized dicts."""
    illus_spec = StrategySpec(
        strategy_id="illustrative_provisional",
        objective="fixed_weights",
        rebalance_frequency="M",
        estimation_window_days=None,
        fixed_weights=baseline_config.portfolio.illustrative_weights,
        provisional=True,
    )
    path = build_portfolio_path(synthetic_asset_returns, illus_spec, baseline_config)
    assert len(path.gross_returns) == len(synthetic_asset_returns)
    assert path.metadata["constraint_enforcement_scope"] == "rebalance_targets_only"
    assert path.metadata["mandate_feasible_all_rebalances"] is True
    assert (
        path.metadata["rebalance_target_compliance_status"]
        == "rebalance_targets_within_provisional_caps"
    )
    assert path.metadata["mandate_compliance_status"] in (
        "rebalance_targets_and_pre_return_holdings_within_provisional_caps",
        "rebalance_targets_feasible_with_post_trade_drift_cap_breaches_provisional",
    )

    # Non-canonical ticker rejected
    bad_ticker = dict(baseline_config.portfolio.illustrative_weights)
    bad_ticker["QQQ"] = 0.0
    with pytest.raises(ValueError, match="non-canonical"):
        build_portfolio_path(
            synthetic_asset_returns,
            StrategySpec(
                strategy_id="bad1",
                objective="fixed_weights",
                estimation_window_days=None,
                fixed_weights=bad_ticker,
            ),
            baseline_config,
        )

    # Weights not summing to 1.0 rejected
    bad_sum = dict(baseline_config.portfolio.illustrative_weights)
    bad_sum["SPY"] = bad_sum["SPY"] + 0.05
    with pytest.raises(ValueError, match="sum to 1.0"):
        build_portfolio_path(
            synthetic_asset_returns,
            StrategySpec(
                strategy_id="bad2",
                objective="fixed_weights",
                estimation_window_days=None,
                fixed_weights=bad_sum,
            ),
            baseline_config,
        )


def test_r1_conflicting_objective_and_fixed_weights_rejected_before_execution(
    baseline_config: AppConfig,
    synthetic_asset_returns: pd.DataFrame,
) -> None:
    """R1: fixed_weights overrides on min_variance, equal_weight, or mismatched 60/40 fail fast."""
    feasible_override = dict(baseline_config.portfolio.illustrative_weights)
    cap_violating_override = {t: 0.0 for t in CANONICAL_TICKERS}
    cap_violating_override["SPY"] = 1.0

    # min_variance must reject both feasible and cap-violating fixed_weights overrides
    for label, override in (("feasible", feasible_override), ("violating", cap_violating_override)):
        with pytest.raises(ValueError, match="Conflicting StrategySpec"):
            build_portfolio_path(
                synthetic_asset_returns,
                StrategySpec(
                    strategy_id=f"conflict_minvar_{label}",
                    objective="min_variance",
                    estimation_window_days=2,
                    covariance_estimator="unsupported_probe",
                    fixed_weights=override,
                ),
                baseline_config,
            )

    # covariance_estimator validation on min_variance cannot be bypassed either
    with pytest.raises(ValueError, match="Unsupported covariance_estimator"):
        build_portfolio_path(
            synthetic_asset_returns,
            StrategySpec(
                strategy_id="bad_cov_est",
                objective="min_variance",
                estimation_window_days=2,
                covariance_estimator="unsupported_probe",
                fixed_weights=None,
            ),
            baseline_config,
        )

    # equal_weight must reject both feasible and cap-violating fixed_weights overrides
    for label, override in (("feasible", feasible_override), ("violating", cap_violating_override)):
        with pytest.raises(ValueError, match="Conflicting StrategySpec"):
            build_portfolio_path(
                synthetic_asset_returns,
                StrategySpec(
                    strategy_id=f"conflict_eq_{label}",
                    objective="equal_weight",
                    estimation_window_days=None,
                    fixed_weights=override,
                ),
                baseline_config,
            )

    # benchmark_60_40 rejects non-60/40 fixed_weights overrides while allowing None or configured 60/40
    with pytest.raises(ValueError, match="Conflicting StrategySpec"):
        build_portfolio_path(
            synthetic_asset_returns,
            StrategySpec(
                strategy_id="conflict_bm",
                objective="benchmark_60_40",
                estimation_window_days=None,
                fixed_weights=cap_violating_override,
            ),
            baseline_config,
        )

    valid_bm_none = build_portfolio_path(
        synthetic_asset_returns,
        StrategySpec(
            strategy_id="valid_bm_none",
            objective="benchmark_60_40",
            estimation_window_days=None,
            fixed_weights=None,
        ),
        baseline_config,
    )
    assert np.isclose(valid_bm_none.weights_before.iloc[0]["SPY"], 0.60)
    assert np.isclose(valid_bm_none.weights_before.iloc[0]["AGG"], 0.40)

    # Explicit fixed_weights objective remains the supported channel for custom allocations
    custom_violating_path = build_portfolio_path(
        synthetic_asset_returns,
        StrategySpec(
            strategy_id="explicit_fixed_all_spy",
            objective="fixed_weights",
            estimation_window_days=None,
            fixed_weights=cap_violating_override,
        ),
        baseline_config,
    )
    assert custom_violating_path.metadata["objective"] == "fixed_weights"
    assert custom_violating_path.metadata["mandate_feasible_all_rebalances"] is False
    assert (
        custom_violating_path.metadata["mandate_compliance_status"]
        == "rebalance_targets_violate_provisional_caps"
    )


def test_r2_target_vs_drifted_holdings_compliance_and_no_breach_control(
    baseline_config: AppConfig,
) -> None:
    """R2: cap-feasible rebalance targets that drift past caps are reported separately without clipping."""
    # 1. Target-feasible allocation (equities = 0.35, AGG = 0.35, GLD = 0.30) that drifts above 0.35
    dates = pd.to_datetime(["2024-01-10", "2024-01-11", "2024-01-12", "2024-02-01"])
    drift_returns = pd.DataFrame(0.0, index=dates, columns=list(CANONICAL_TICKERS))
    drift_returns.loc["2024-01-10", "SPY"] = 0.20  # SPY 0.15 -> 0.18/1.03; equities 0.35 -> 0.38/1.03

    drift_spec = StrategySpec(
        strategy_id="drift_breach_probe",
        objective="fixed_weights",
        rebalance_frequency="M",
        estimation_window_days=None,
        fixed_weights=baseline_config.portfolio.illustrative_weights,
    )
    drift_path = build_portfolio_path(drift_returns, drift_spec, baseline_config)

    assert drift_path.metadata["constraint_enforcement_scope"] == "rebalance_targets_only"
    assert drift_path.metadata["mandate_feasible_all_rebalances"] is True
    assert (
        drift_path.metadata["rebalance_target_compliance_status"]
        == "rebalance_targets_within_provisional_caps"
    )
    assert drift_path.metadata["mandate_feasible_all_pre_return_sessions"] is False
    assert (
        drift_path.metadata["mandate_compliance_status"]
        == "rebalance_targets_feasible_with_post_trade_drift_cap_breaches_provisional"
    )

    diag = drift_path.metadata["pre_return_holdings_compliance"]
    assert diag["scope"] == "pre_return_holdings_all_active_sessions"
    assert diag["n_active_sessions"] == 4
    assert diag["n_breach_sessions"] == 2
    assert diag["n_compliant_sessions"] == 2
    assert diag["breach_dates"] == ("2024-01-11", "2024-01-12")
    assert diag["violated_constraints"] == ("max_equity_weight",)
    assert diag["breach_counts_by_constraint"]["max_equity_weight"] == 2
    assert np.isclose(diag["max_exposures"]["max_equity_group_weight"], 0.38 / 1.03, atol=1e-14)
    # Weights are NOT clipped and no unapproved mid-month daily trades occur
    assert np.isclose(drift_path.weights_before.loc["2024-01-11", "SPY"], 0.18 / 1.03, atol=1e-14)
    assert drift_path.turnover.loc["2024-01-11"] == 0.0
    assert drift_path.turnover.loc["2024-01-12"] == 0.0

    # 2. No-breach control: interior target (equities = 0.30, AGG = 0.35, GLD = 0.35) with mild drift
    interior_weights = {
        "SPY": 0.10,
        "EFA": 0.05,
        "EEM": 0.05,
        "AGG": 0.35,
        "GLD": 0.35,
        "XLE": 0.05,
        "XLK": 0.05,
    }
    calm_returns = pd.DataFrame(0.001, index=dates, columns=list(CANONICAL_TICKERS))
    calm_returns["AGG"] = -0.001
    ctrl_path = build_portfolio_path(
        calm_returns,
        StrategySpec(
            strategy_id="no_breach_control",
            objective="fixed_weights",
            rebalance_frequency="M",
            estimation_window_days=None,
            fixed_weights=interior_weights,
        ),
        baseline_config,
    )
    assert ctrl_path.metadata["mandate_feasible_all_rebalances"] is True
    assert ctrl_path.metadata["mandate_feasible_all_pre_return_sessions"] is True
    assert (
        ctrl_path.metadata["mandate_compliance_status"]
        == "rebalance_targets_and_pre_return_holdings_within_provisional_caps"
    )
    ctrl_diag = ctrl_path.metadata["pre_return_holdings_compliance"]
    assert ctrl_diag["n_breach_sessions"] == 0
    assert ctrl_diag["breach_dates"] == ()
    assert ctrl_diag["violated_constraints"] == ()
    assert summarize_pre_return_holdings_compliance(
        ctrl_path.weights_before,
        baseline_config.portfolio.constraints,
    )["n_breach_sessions"] == 0


def test_offline_r3_development_period_smoke_check(baseline_config: AppConfig) -> None:
    """Offline development-period (<= 2016-12-30) smoke check on r3 verifies core paths without touching holdouts."""
    import hashlib

    bundle = load_data(baseline_config, offline=True)
    assert bundle.manifest.dataset_id == "qe1_20050101_20261030_r3_6c4633a7ba"

    # Strictly slice to development_end (2016-12-30); never touch 2017-2020 selection or 2021-2026 evaluation.
    dev_end = baseline_config.chronology.development_end
    assert dev_end == "2016-12-30"
    dev_returns = bundle.simple_returns.loc[:dev_end].copy()
    assert dev_returns.index[0] == pd.Timestamp("2005-01-04")
    assert dev_returns.index[-1] == pd.Timestamp("2016-12-30")
    assert len(dev_returns) == 3020

    core_specs = make_core_strategy_specs(baseline_config)
    paths = {
        name: build_portfolio_path(dev_returns, spec, baseline_config)
        for name, spec in core_specs.items()
    }

    # Pre-fix Step 3 SHA-256 digests prove R1-R3 reporting/validation fixes leave every path array bit-identical
    expected_sha256 = {
        "min_variance": {
            "weights_before": "1362e3ce3cb636bb50149a03c8bdafc8d249df3f56f8a37497a989a8e348cdbb",
            "gross_returns": "284ab78bccf6a1ad5b111157056aee9a2613c33370824013e8cc243b48da30e9",
            "net_returns": "1fb28442c39d073a78ab101db35f63f61a7054ce07ee5de4a60a3ad18d727987",
            "turnover": "6164bd1c53bb72b4899de0d58c17e163a002de89f4fb2248876c83718727811e",
            "costs": "3dddc50f7ba58b9afba154b320af43a9b5c1415000e1927fb8c86a583eb1a192",
            "wealth": "a210f36945a935c53eb1572e0bbc28dc25268dc2501e47dba707c37a7b009870",
            "drawdown": "4bc4e8f183f55cb215288da8763b1076edd868d28ef89436509a36d143647f43",
        },
        "equal_weight": {
            "weights_before": "6543ba09d9b30e3a613bb99bc3ca764385f91d56c754ff02f06bd4ff361b6d73",
            "gross_returns": "f4aa591b4ecc2ea3179a08abf41b3902dd53f10e8d3ca7ad254418fafa161878",
            "net_returns": "b0f10c75a22d49c816cf57ee2a746262c676955ec47f2f5bcfa43e00668c997d",
            "turnover": "d68ffc964725f159dca92f71797cd0581671d10c0532e0b774bae4af72736a87",
            "costs": "ba3d6455befd13b159b93ff474f8adc2588c99c4ca5fe393379828768c190e77",
            "wealth": "325e5340a77cf765151a02edcfd9039670f0df74e94d6713605ec9f00bb177a6",
            "drawdown": "a4aa0845f8cad6768400d9cb0ed61c2856fa70501a77ce4828d15bccaaca988b",
        },
        "benchmark_60_40": {
            "weights_before": "d7155044641abe588cffb871c91edf46121ef96efb0d28e9ad1733362289fa41",
            "gross_returns": "82f7b7cdacf5a0d14049e09078c7402429f4d21c2a61f50cdec70d717bcd5ce7",
            "net_returns": "610cc5efcfc52ee248709fa7d38f38b71553ab29fb82c02557f171820d976c2c",
            "turnover": "1acc3bf663f5e8f89c505d39d77574b0ce3345c7ecfa6676a30bd034a2be9c03",
            "costs": "01b41bb1aed1bd139e5bfd2ec77a29b43be4edea8bf0048352e169b9121f569d",
            "wealth": "c5c05200de2c8c898c9a0cd2dafb9c85d84e7f020f2a1d47349228e7fe3af2d3",
            "drawdown": "a17396712c42c2460514ba6baf52eb8485dce643fba95cb32187b4518ece8c32",
        },
    }

    for name, path in paths.items():
        assert path.metadata["active_start"] == "2007-01-05"
        assert path.metadata["active_end"] == "2016-12-30"
        assert path.metadata["n_active_sessions"] == 2516
        assert path.metadata["n_rebalances"] == 120
        assert tuple(path.weights_before.columns) == CANONICAL_TICKERS
        assert np.allclose(path.weights_before.sum(axis=1).to_numpy(), 1.0, atol=1e-11)
        assert np.isfinite(path.gross_returns.to_numpy()).all()
        assert np.isfinite(path.net_returns.to_numpy()).all()
        assert np.isfinite(path.wealth.to_numpy()).all()
        assert bool((path.wealth > 0.0).all())
        assert bool((path.drawdown <= 1e-15).all())
        assert bool((path.rebalances["decision_date"] < path.rebalances["effective_date"]).all())
        assert bool((path.rebalances["train_end"] < path.rebalances["effective_date"]).all())
        assert bool((path.rebalances["effective_date"] <= pd.Timestamp("2016-12-30")).all())
        assert bool((path.rebalances["n_train_obs"] == 504).all()), f"Unexpected train window in {name}"
        for field_name, exp_digest in expected_sha256[name].items():
            actual_bytes = getattr(path, field_name).to_numpy(dtype="float64").tobytes()
            assert hashlib.sha256(actual_bytes).hexdigest() == exp_digest, f"{name}.{field_name} changed"

    min_var_path = paths["min_variance"]
    assert min_var_path.metadata["constraint_enforcement_scope"] == "rebalance_targets_only"
    assert min_var_path.metadata["mandate_feasible_all_rebalances"] is True
    assert (
        min_var_path.metadata["rebalance_target_compliance_status"]
        == "rebalance_targets_within_provisional_caps"
    )
    assert min_var_path.metadata["mandate_feasible_all_pre_return_sessions"] is False
    assert (
        min_var_path.metadata["mandate_compliance_status"]
        == "rebalance_targets_feasible_with_post_trade_drift_cap_breaches_provisional"
    )
    dev_holdings_diag = min_var_path.metadata["pre_return_holdings_compliance"]
    assert dev_holdings_diag["n_breach_sessions"] == 1439
    assert np.isclose(dev_holdings_diag["max_exposures"]["max_single_etf_weight"], 0.4513928828216966, atol=1e-12)
    assert np.isclose(dev_holdings_diag["max_exposures"]["max_equity_group_weight"], 0.37298300491046316, atol=1e-12)

    for _, row in min_var_path.rebalances.iterrows():
        w_row = pd.Series({t: float(row[t]) for t in CANONICAL_TICKERS})
        feas = check_weight_feasibility(w_row, baseline_config.portfolio.constraints, tol=1e-7)
        assert feas["feasible"] is True
        assert 0.25 - 1e-7 <= float(row["AGG"]) <= 0.40 + 1e-7
        assert 0.25 - 1e-7 <= float(row["GLD"]) <= 0.40 + 1e-7
        assert 0.20 - 1e-7 <= float(row["equity_weight"]) <= 0.35 + 1e-7

    for ref_name in ("equal_weight", "benchmark_60_40"):
        ref_path = paths[ref_name]
        assert ref_path.metadata["is_reference_benchmark"] is True
        assert ref_path.metadata["mandate_feasible_all_rebalances"] is False
        assert (
            ref_path.metadata["mandate_compliance_status"]
            == "unconstrained_reference_violates_provisional_caps"
        )
        assert len(ref_path.metadata["mandate_violations_summary"]) >= 1
