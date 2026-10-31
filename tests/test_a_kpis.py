"""Unit and development-only integration tests for SOLO STEP 4 (A1b Context & A2 KPIs/CAPM)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantedge.config import AppConfig
from quantedge.contracts import CANONICAL_TICKERS, KPI_COLUMNS
from quantedge.data import (
    DataUnavailableError,
    extract_split_adjusted_closes_and_distributions,
    load_context_data,
    load_data,
    parse_fred_cpi_csv,
)
from quantedge.kpis import (
    CANONICAL_KPI_METRICS,
    build_development_kpi_bundle,
    compare_rf_kpi_sensitivity,
    compute_ex_post_real_return_metrics,
    compute_kpis,
    compute_trailing_12m_distribution_yields,
    run_portfolio_return_stationarity_diagnostics,
    summarize_portfolio_distribution_income,
)
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs
from quantedge.returns import expected_nyse_sessions


def test_hand_calculated_kpis_exact_closed_form() -> None:
    """Verify all 13 KPIs against an exact 4-session closed-form hand calculation."""
    dates = pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09"])

    # Daily risk-free rate = 0.001 (0.1%/day)
    rf = pd.Series([0.001, 0.001, 0.001, 0.001], index=dates, name="rf_daily")

    # Market excess return e_m = [-0.02, +0.02, -0.02, +0.02], mean(e_m) = 0.0
    e_m = np.array([-0.02, 0.02, -0.02, 0.02], dtype=np.float64)
    market_ret = pd.Series(e_m + 0.001, index=dates, name="SPY")

    # Portfolio excess return: alpha_daily = 0.002, beta = 0.5, orthogonal residual = [+0.01, +0.01, -0.01, -0.01]
    # e_p = [0.002, 0.022, -0.018, 0.002], R_p = [0.003, 0.023, -0.017, 0.003]
    eps = np.array([0.01, 0.01, -0.01, -0.01], dtype=np.float64)
    e_p = 0.002 + 0.5 * e_m + eps
    port_ret = pd.Series(e_p + 0.001, index=dates, name="portfolio")

    # Benchmark return R_b chosen so active return a = R_p - R_b = [+0.002, +0.010, -0.010, +0.002]
    active = np.array([0.002, 0.010, -0.010, 0.002], dtype=np.float64)
    bench_ret = pd.Series(port_ret.to_numpy() - active, index=dates, name="benchmark_60_40")

    kpi_df = compute_kpis(port_ret, bench_ret, market_ret, rf)
    assert tuple(kpi_df.columns) == KPI_COLUMNS
    assert tuple(kpi_df["metric"]) == CANONICAL_KPI_METRICS
    assert (kpi_df["status"] == "ok").all()

    by_metric = kpi_df.set_index("metric")["value"].to_dict()

    # Hand-computed expected values
    w_terminal = 1.003 * 1.023 * 0.983 * 1.003
    exp_geom = w_terminal ** (252.0 / 4.0) - 1.0
    exp_arith = 252.0 * 0.003
    exp_vol = np.sqrt(252.0) * np.sqrt(0.0008 / 3.0)
    exp_sharpe = (252.0 * 0.002) / exp_vol

    # All-observation downside deviation relative to rf_daily:
    # Only day 3 has e_p = -0.018 < 0 => sqrt((1/4) * (-0.018)^2) = 0.018 / 2 = 0.009
    exp_dd_daily = 0.009
    exp_dd_ann = np.sqrt(252.0) * exp_dd_daily
    exp_sortino = (252.0 * 0.002) / exp_dd_ann

    # CAPM OLS: exact beta = 0.5, alpha_daily = 0.002 => alpha_annual = 252 * 0.002 = 0.504
    exp_beta = 0.5
    exp_alpha = 252.0 * 0.002
    exp_treynor = (252.0 * 0.002) / 0.5

    # Active return a = [0.002, 0.010, -0.010, 0.002], mean = 0.001, var(ddof=1) = 0.000204 / 3 = 0.000068
    exp_te = np.sqrt(252.0 * 0.000068)
    exp_ir = (252.0 * 0.001) / exp_te

    # Wealth path = [1.003, 1.026069, 1.008625827, 1.011651704...]: peak at day 2, trough at day 3 => MDD = -0.017
    exp_mdd = -0.017
    exp_calmar = exp_geom / 0.017

    assert np.isclose(by_metric["geometric_annual_return"], exp_geom, atol=1e-14)
    assert np.isclose(by_metric["arithmetic_annual_return"], exp_arith, atol=1e-14)
    assert np.isclose(by_metric["annualized_volatility"], exp_vol, atol=1e-14)
    assert np.isclose(by_metric["sharpe_ratio"], exp_sharpe, atol=1e-14)
    assert np.isclose(by_metric["downside_deviation"], exp_dd_ann, atol=1e-14)
    assert np.isclose(by_metric["sortino_ratio"], exp_sortino, atol=1e-14)
    assert np.isclose(by_metric["capm_beta"], exp_beta, atol=1e-14)
    assert np.isclose(by_metric["jensen_alpha"], exp_alpha, atol=1e-14)
    assert np.isclose(by_metric["treynor_ratio"], exp_treynor, atol=1e-14)
    assert np.isclose(by_metric["tracking_error"], exp_te, atol=1e-14)
    assert np.isclose(by_metric["information_ratio"], exp_ir, atol=1e-14)
    assert np.isclose(by_metric["max_drawdown"], exp_mdd, atol=1e-14)
    assert np.isclose(by_metric["calmar_ratio"], exp_calmar, atol=1e-14)


def test_initial_wealth_drawdown_captures_first_day_loss() -> None:
    """A loss on session 1 followed by monotone recovery must record day-1 drawdown against initial wealth 1.0."""
    dates = pd.to_datetime(["2020-02-03", "2020-02-04", "2020-02-05"])
    # Day 1 drops -10% (wealth = 0.90), then rises +5% (0.945) and +2% (0.9639)
    port_ret = pd.Series([-0.10, 0.05, 0.02], index=dates)
    bench_ret = pd.Series([-0.05, 0.03, 0.01], index=dates)
    market_ret = pd.Series([-0.08, 0.04, 0.01], index=dates)
    rf = pd.Series([0.0, 0.0, 0.0], index=dates)

    kpi_df = compute_kpis(port_ret, bench_ret, market_ret, rf).set_index("metric")
    assert np.isclose(float(kpi_df.loc["max_drawdown", "value"]), -0.10, atol=1e-14)
    assert "initial_wealth_1.0" in kpi_df.attrs["drawdown_summary"]["peak_reference"]
    assert kpi_df.attrs["drawdown_summary"]["trough_date"] == "2020-02-03"


def test_missing_or_incomplete_rf_and_index_alignment_never_fabricates_zeros() -> None:
    """Missing or incomplete rf_daily marks RF-dependent KPIs unavailable (None) without zero-filling."""
    dates_p = pd.to_datetime(["2020-03-02", "2020-03-03", "2020-03-04", "2020-03-05", "2020-03-06"])
    dates_bm = pd.to_datetime(["2020-03-03", "2020-03-04", "2020-03-05", "2020-03-06"])

    port_ret = pd.Series([0.01, -0.02, 0.015, -0.005, 0.01], index=dates_p)
    bench_ret = pd.Series([-0.01, 0.01, -0.002, 0.008], index=dates_bm)
    market_ret = pd.Series([-0.015, 0.02, -0.004, 0.012], index=dates_bm)

    # Case 1: rf_daily is None
    df_none = compute_kpis(port_ret, bench_ret, market_ret, None).set_index("metric")
    assert df_none.attrs["alignment"]["n_obs"] == 4
    assert df_none.attrs["alignment"]["n_dropped_alignment"] == 1

    rf_dep = ("sharpe_ratio", "downside_deviation", "sortino_ratio", "capm_beta", "jensen_alpha", "treynor_ratio")
    rf_indep = (
        "geometric_annual_return",
        "arithmetic_annual_return",
        "annualized_volatility",
        "tracking_error",
        "information_ratio",
        "max_drawdown",
        "calmar_ratio",
    )
    for m in rf_dep:
        assert df_none.loc[m, "status"] == "unavailable"
        assert df_none.loc[m, "value"] is None
    for m in rf_indep:
        assert df_none.loc[m, "status"] == "ok"
        assert isinstance(df_none.loc[m, "value"], float)

    # Case 2: rf_daily has 1 missing observation on the 4 aligned dates
    rf_incomplete = pd.Series([0.0001, np.nan, 0.0001, 0.0001], index=dates_bm)
    df_inc = compute_kpis(port_ret, bench_ret, market_ret, rf_incomplete).set_index("metric")
    assert df_inc.attrs["alignment"]["n_missing_rf"] == 1
    for m in rf_dep:
        assert df_inc.loc[m, "status"] == "unavailable"
        assert df_inc.loc[m, "value"] is None
        assert "1/4" in str(df_inc.loc[m, "note"])


def test_degenerate_denominators_short_samples_and_negative_beta_warning() -> None:
    """Zero volatility, zero downside, zero TE, zero drawdown, near-zero/negative beta, and short samples are handled explicitly."""
    dates_1 = pd.to_datetime(["2020-04-01"])
    s1 = pd.Series([0.01], index=dates_1)
    df_1 = compute_kpis(s1, s1, s1, s1)
    assert (df_1["status"] == "unavailable").all()
    assert all(v is None for v in df_1["value"])

    # n=2: CAPM OLS (beta/alpha/Treynor) unavailable due to df_resid = n - 2 = 0
    dates_2 = pd.to_datetime(["2020-04-01", "2020-04-02"])
    p2 = pd.Series([0.01, -0.01], index=dates_2)
    b2 = pd.Series([0.005, -0.005], index=dates_2)
    m2 = pd.Series([0.02, -0.02], index=dates_2)
    rf2 = pd.Series([0.0, 0.0], index=dates_2)
    df_2 = compute_kpis(p2, b2, m2, rf2).set_index("metric")
    assert df_2.loc["sharpe_ratio", "status"] == "ok"
    for capm_m in ("capm_beta", "jensen_alpha", "treynor_ratio"):
        assert df_2.loc[capm_m, "status"] == "unavailable"
        assert df_2.loc[capm_m, "value"] is None

    # All strictly positive excess returns, constant excess return, and identical benchmark (p == b)
    dates_4 = pd.to_datetime(["2020-04-01", "2020-04-02", "2020-04-03", "2020-04-06"])
    p_const = pd.Series([0.01, 0.01, 0.01, 0.01], index=dates_4)
    m_var = pd.Series([-0.01, 0.02, -0.02, 0.01], index=dates_4)
    rf_zero = pd.Series([0.0, 0.0, 0.0, 0.0], index=dates_4)
    df_deg = compute_kpis(p_const, p_const, m_var, rf_zero).set_index("metric")

    assert df_deg.loc["annualized_volatility", "value"] == 0.0
    assert df_deg.loc["sharpe_ratio", "status"] == "unavailable"
    assert df_deg.loc["sharpe_ratio", "value"] is None
    assert df_deg.loc["downside_deviation", "value"] == 0.0
    assert df_deg.loc["sortino_ratio", "status"] == "unavailable"
    assert df_deg.loc["sortino_ratio", "value"] is None
    assert np.isclose(float(df_deg.loc["capm_beta", "value"]), 0.0, atol=1e-15)
    assert df_deg.loc["treynor_ratio", "status"] == "unavailable"
    assert df_deg.loc["treynor_ratio", "value"] is None
    assert df_deg.loc["tracking_error", "value"] == 0.0
    assert df_deg.loc["information_ratio", "status"] == "unavailable"
    assert df_deg.loc["information_ratio", "value"] is None
    assert df_deg.loc["max_drawdown", "value"] == 0.0
    assert df_deg.loc["calmar_ratio", "status"] == "unavailable"
    assert df_deg.loc["calmar_ratio", "value"] is None

    # Negative beta portfolio: beta = -0.5 => Treynor has status='warning'
    p_neg_beta = pd.Series(0.001 - 0.5 * m_var.to_numpy(), index=dates_4)
    df_neg = compute_kpis(p_neg_beta, p_const, m_var, rf_zero).set_index("metric")
    assert np.isclose(float(df_neg.loc["capm_beta", "value"]), -0.5, atol=1e-14)
    assert df_neg.loc["treynor_ratio", "status"] == "warning"
    assert np.isclose(float(df_neg.loc["treynor_ratio", "value"]), (252.0 * 0.001) / -0.5, atol=1e-14)


def test_a1b_split_basis_validation_and_failed_fetch_rejection() -> None:
    """A1b extraction rejects auto_adjust=True frames, empty dividend fetches, and mismatched share bases."""
    dates = pd.bdate_range("2020-01-02", periods=5)
    tickers = list(CANONICAL_TICKERS)

    # Build a valid synthetic MultiIndex actions frame where day 2 has a $1.00 dividend on Close_1 = $100.0
    fields = ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits"]
    col_Idx = pd.MultiIndex.from_product([fields, tickers], names=["Price", "Ticker"])
    valid_raw = pd.DataFrame(100.0, index=dates, columns=col_Idx)
    valid_raw["Dividends"] = 0.0
    valid_raw["Stock Splits"] = 0.0

    for t in tickers:
        if t != "GLD":
            valid_raw.loc[dates[2], ("Dividends", t)] = 1.0
            # Before ex-date (dates[0], dates[1]), Adj Close is scaled by (100 - 1) / 100 = 0.99
            valid_raw.loc[dates[0], ("Adj Close", t)] = 99.0
            valid_raw.loc[dates[1], ("Adj Close", t)] = 99.0

    close_df, div_df, split_df, verif = extract_split_adjusted_closes_and_distributions(valid_raw)
    assert close_df.shape == (5, 7)
    assert div_df.loc[dates[2], "SPY"] == 1.0
    assert div_df["GLD"].sum() == 0.0
    assert verif["max_ex_div_factor_abs_diff_by_ticker"]["SPY"] < 1e-12

    # 1. Reject auto_adjust=True frame (missing 'Adj Close')
    no_adj = valid_raw.drop(columns=["Adj Close"], level=0)
    with pytest.raises(ValueError, match="auto_adjust=False"):
        extract_split_adjusted_closes_and_distributions(no_adj)

    # 2. Reject failed/empty dividend fetch (0 dividends across dividend-paying ETFs)
    zero_divs = valid_raw.copy()
    zero_divs["Dividends"] = 0.0
    with pytest.raises(DataUnavailableError, match="refusing to treat an empty or failed dividend fetch"):
        extract_split_adjusted_closes_and_distributions(zero_divs)

    # 3. Reject corrupted share/split basis where Dividend does not match Close vs Adj Close factor
    bad_basis = valid_raw.copy()
    bad_basis.loc[dates[2], ("Dividends", "SPY")] = 5.0  # 5% dividend while Adj Close factor is 1%
    with pytest.raises(ValueError, match="Share/split basis mismatch"):
        extract_split_adjusted_closes_and_distributions(bad_basis)

    # 4. Trailing-12M yield calculation on a 400-calendar-day synthetic series
    long_dates = pd.date_range("2020-01-01", periods=400, freq="D")
    closes_long = pd.DataFrame(100.0, index=long_dates, columns=tickers)
    divs_long = pd.DataFrame(0.0, index=long_dates, columns=tickers)
    divs_long.loc["2020-03-15", "SPY"] = 1.50
    divs_long.loc["2020-09-15", "SPY"] = 1.50
    ttm_d, ttm_y = compute_trailing_12m_distribution_yields(closes_long, divs_long)
    # Before 2020-01-01 + 365 days = 2020-12-31, values are NaN
    assert ttm_y.loc["2020-12-30", "SPY"] != ttm_y.loc["2020-12-30", "SPY"]  # NaN
    assert np.isclose(float(ttm_d.loc["2021-01-05", "SPY"]), 3.0, atol=1e-14)
    assert np.isclose(float(ttm_y.loc["2021-01-05", "SPY"]), 0.03, atol=1e-14)


def test_a1b_ex_post_real_returns_common_months_and_missing_cpi_handling() -> None:
    """Ex-post real return metrics align strictly on completed common months and never extrapolate missing CPI."""
    # Construct daily portfolio returns covering:
    # - 2020-01: partial month (only last 3 NYSE sessions of Jan 2020) -> must be excluded as partial
    # - 2020-02: complete NYSE month with total gross return = 1.045 (+4.5%)
    # - 2020-03: complete NYSE month with total gross return = 1.020 (+2.0%)
    # - 2020-04: complete NYSE month, but 2020-04 CPI is unreleased/missing -> must be excluded
    nyse_jan = expected_nyse_sessions("2020-01-01", "2020-01-31")[-3:]
    nyse_feb = expected_nyse_sessions("2020-02-01", "2020-02-29")
    nyse_mar = expected_nyse_sessions("2020-03-01", "2020-03-31")
    nyse_apr = expected_nyse_sessions("2020-04-01", "2020-04-30")

    ret_jan = pd.Series(0.001, index=nyse_jan)
    ret_feb = pd.Series(1.045 ** (1.0 / len(nyse_feb)) - 1.0, index=nyse_feb)
    ret_mar = pd.Series(1.020 ** (1.0 / len(nyse_mar)) - 1.0, index=nyse_mar)
    ret_apr = pd.Series(0.002, index=nyse_apr)
    port_ret = pd.concat([ret_jan, ret_feb, ret_mar, ret_apr])

    cpi_csv = "\n".join(
        [
            "observation_date,CPIAUCSL",
            "2019-12-01,99.0",
            "2020-01-01,100.0",
            "2020-02-01,101.0",
            "2020-03-01,103.02",
            "2020-04-01,.",
        ]
    )
    cpi_df = parse_fred_cpi_csv(cpi_csv)
    assert list(cpi_df["month_period"]) == ["2019-12", "2020-01", "2020-02", "2020-03"]

    real_df = compute_ex_post_real_return_metrics(port_ret, cpi_df).set_index("metric")
    summary = real_df.attrs["common_months_summary"]
    assert summary["first_common_month"] == "2020-02"
    assert summary["last_common_month"] == "2020-03"
    assert summary["base_cpi_month"] == "2020-01"
    assert summary["n_common_complete_months"] == 2
    assert summary["partial_portfolio_months_excluded"] == ["2020-01"]
    assert summary["unreleased_or_missing_cpi_months_excluded"] == ["2020-04"]

    exp_nom_mult = 1.045 * 1.020
    exp_cpi_mult = 103.02 / 100.0
    exp_real_mult = exp_nom_mult / exp_cpi_mult
    exp_nom_ann = exp_nom_mult**6.0 - 1.0
    exp_cpi_ann = exp_cpi_mult**6.0 - 1.0
    exp_real_ann = exp_real_mult**6.0 - 1.0

    assert np.isclose(
        float(real_df.loc["ex_post_nominal_annual_return_common_months", "value"]),
        exp_nom_ann,
        atol=1e-13,
    )
    assert np.isclose(
        float(real_df.loc["ex_post_cpi_annual_inflation_common_months", "value"]),
        exp_cpi_ann,
        atol=1e-13,
    )
    assert np.isclose(
        float(real_df.loc["ex_post_real_annual_return_common_months", "value"]),
        exp_real_ann,
        atol=1e-13,
    )
    assert np.isclose(
        float(real_df.loc["ex_post_real_wealth_multiple_common_months", "value"]),
        exp_real_mult,
        atol=1e-13,
    )


def test_offline_development_period_kpis_rf_sensitivity_and_context_smoke_check(
    baseline_config: AppConfig,
) -> None:
    """Offline development-only (<= 2016-12-30) KPI, RF-sensitivity, CPI, and income verification."""
    bundle = load_data(baseline_config, offline=True)
    ctx = load_context_data(baseline_config, offline=True)

    assert bundle.manifest.dataset_id == "qe1_20050101_20261030_r3_6c4633a7ba"
    assert ctx.context_id == "qe1_context_20050101_20261030_a1b_2040bb6e15"
    assert len(ctx.manifest["file_sha256"]) == 7

    # Strictly restrict to development_end (2016-12-30); never compute selection or evaluation outcomes.
    dev_end = baseline_config.chronology.development_end
    assert dev_end == "2016-12-30"
    dev_returns = bundle.simple_returns.loc[:dev_end].copy()
    dev_rf = bundle.rf_daily.loc[:dev_end].copy()
    assert bundle.rf_accrual_sensitivity is not None
    dev_rf_accr = bundle.rf_accrual_sensitivity.loc[:dev_end].copy()

    core_specs = make_core_strategy_specs(baseline_config)
    paths = {
        name: build_portfolio_path(dev_returns, spec, baseline_config)
        for name, spec in core_specs.items()
    }

    dev_bundle = build_development_kpi_bundle(
        paths,
        dev_returns["SPY"],
        dev_rf,
        rf_accrual_sensitivity=dev_rf_accr,
        context_bundle=ctx,
    )

    mv_kpi = dev_bundle["kpis"]["min_variance"].set_index("metric")
    ew_kpi = dev_bundle["kpis"]["equal_weight"].set_index("metric")
    b60_kpi = dev_bundle["kpis"]["benchmark_60_40"].set_index("metric")

    assert (mv_kpi["status"] == "ok").all()
    assert (ew_kpi["status"] == "ok").all()
    assert b60_kpi.loc["tracking_error", "value"] == 0.0
    assert b60_kpi.loc["information_ratio", "status"] == "unavailable"
    assert b60_kpi.loc["information_ratio", "value"] is None

    # Verify exact development-period (2007-01-05..2016-12-30, n=2516) min_variance headline KPIs
    assert np.isclose(float(mv_kpi.loc["geometric_annual_return", "value"]), 0.06653371264164118, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["arithmetic_annual_return", "value"]), 0.06826591616989995, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["annualized_volatility", "value"]), 0.08769908081242896, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["sharpe_ratio", "value"]), 0.7027850546810748, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["downside_deviation", "value"]), 0.06126972633976861, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["sortino_ratio", "value"]), 1.0059791496617128, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["capm_beta", "value"]), 0.28928875338653603, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["jensen_alpha", "value"]), 0.03802772022813689, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["treynor_ratio", "value"]), 0.21306071004056845, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["tracking_error", "value"]), 0.08287337786245844, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["information_ratio", "value"]), 0.023188434146501537, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["max_drawdown", "value"]), -0.22175618468011338, atol=1e-12)
    assert np.isclose(float(mv_kpi.loc["calmar_ratio", "value"]), 0.30003092241876844, atol=1e-12)

    # Verify RF accrual sensitivity is small and finite
    mv_rf_sens = dev_bundle["rf_sensitivity"]["min_variance"].set_index("metric")
    assert (mv_rf_sens["status"] == "ok").all()
    assert abs(float(mv_rf_sens.loc["sharpe_ratio", "difference"])) < 0.005

    # Verify ex-post real returns (119 common completed months 2007-02..2016-12)
    mv_real = dev_bundle["ex_post_real_returns"]["min_variance"].set_index("metric")
    assert (mv_real["status"] == "ok").all()
    assert mv_real.attrs["common_months_summary"]["n_common_complete_months"] == 119
    assert np.isclose(
        float(mv_real.loc["ex_post_real_annual_return_common_months", "value"]),
        0.04663732670187959,
        atol=1e-12,
    )

    # Verify distribution income is reported alongside total return and does NOT alter net_returns
    mv_inc = dev_bundle["distribution_income"]["min_variance"].set_index("metric")
    assert (mv_inc["status"] == "ok").all()
    assert np.isclose(
        float(mv_inc.loc["annualized_ex_date_distribution_yield", "value"]),
        0.019038,
        atol=1e-6,
    )

    # Verify stationarity diagnostics on changing-weight strategy path (and synthetic fixed-exposure check)
    mv_stat = dev_bundle["stationarity"]["min_variance"]
    assert bool(mv_stat["reject_unit_root_5pct"].all())
    fixed_probe = run_portfolio_return_stationarity_diagnostics(
        paths["min_variance"].net_returns,
        series_label="min_variance",
        fixed_exposure_returns=dev_returns["SPY"].loc[paths["min_variance"].net_returns.index],
    )
    assert len(fixed_probe) == 4


def test_r1_positive_raw_returns_with_negative_rf_excess_returns_do_not_crash() -> None:
    """R1 regression: positive raw returns with some below-RF returns must not crash compute_kpis when zero-target Sortino is None."""
    dates = pd.bdate_range("2010-01-04", periods=4)
    p = pd.Series([0.0001, 0.0002, 0.0003, 0.0004], index=dates)
    b = pd.Series([0.00005, 0.0003, -0.0001, 0.0002], index=dates)
    m = pd.Series([0.001, -0.002, 0.002, -0.001], index=dates)
    rf = pd.Series(0.00025, index=dates)

    df = compute_kpis(p, b, m, rf).set_index("metric")
    assert df.attrs["diagnostics"]["downside_deviation_zero_target"] == 0.0
    assert df.attrs["diagnostics"]["sortino_zero_target"] is None

    # Primary RF-target downside deviation and Sortino are finite and available
    exp_dd_rf = np.sqrt(252.0 * ((-0.00015) ** 2 + (-0.00005) ** 2) / 4.0)
    assert df.loc["downside_deviation", "status"] == "ok"
    assert np.isclose(float(df.loc["downside_deviation", "value"]), exp_dd_rf, atol=1e-15)
    assert df.loc["sortino_ratio", "status"] == "ok"
    assert np.isclose(float(df.loc["sortino_ratio", "value"]), 0.0, atol=1e-14)
    assert "unavailable (all raw returns >= 0)" in str(df.loc["sortino_ratio", "note"])

    # Also verify positive mean excess return with all-positive raw returns
    p_pos_excess = pd.Series([0.0001, 0.0002, 0.0004, 0.0005], index=dates)
    df_pos = compute_kpis(p_pos_excess, b, m, rf).set_index("metric")
    exp_sortino_pos = (252.0 * 0.00005) / exp_dd_rf
    assert df_pos.loc["sortino_ratio", "status"] == "ok"
    assert np.isclose(float(df_pos.loc["sortino_ratio", "value"]), exp_sortino_pos, atol=1e-14)

    # Verify explicit input validation contract for +/-inf
    rf_inf = pd.Series([0.0001, np.inf, 0.0001, 0.0001], index=dates)
    with pytest.raises(ValueError, match="non-finite"):
        compute_kpis(p, b, m, rf_inf)


def test_r2_internal_cpi_gap_and_nyse_session_date_membership_validation() -> None:
    """R2 regression: internal missing CPI months never stitch disconnected factors, report missing prior CPI, and enforce exact NYSE date matching."""
    days = expected_nyse_sessions("2010-01-01", "2010-05-31")
    zero_returns = pd.Series(0.0, index=days)
    cpi = pd.Series(
        [100.0, 101.0, np.nan, 121.0, 122.0, 123.0],
        index=pd.period_range("2009-12", "2010-05", freq="M"),
    )

    # 1. Default policy ('endpoint_cpi_contiguous_nominal'): full 5-month contiguous nominal span + valid endpoint CPI 123/100
    real_df = compute_ex_post_real_return_metrics(zero_returns, cpi).set_index("metric")
    summary = real_df.attrs["common_months_summary"]
    assert summary["first_common_month"] == "2010-01"
    assert summary["last_common_month"] == "2010-05"
    assert summary["base_cpi_month"] == "2009-12"
    assert summary["n_common_complete_months"] == 5
    assert summary["calendar_months_in_span"] == 5
    assert summary["is_contiguous_calendar_span"] is True
    assert summary["has_internal_cpi_gaps"] is True
    assert np.isclose(float(summary["cpi_index_ratio"]), 123.0 / 100.0, atol=1e-14)
    assert np.isclose(float(summary["real_wealth_multiple"]), 100.0 / 123.0, atol=1e-14)
    assert summary["missing_current_cpi_months_excluded"] == ["2010-02"]
    assert summary["missing_prior_cpi_months_excluded"] == ["2010-03"]
    assert summary["unreleased_or_missing_cpi_months_excluded"] == ["2010-02", "2010-03"]
    assert (real_df["status"] == "warning").all()
    assert np.isclose(
        float(real_df.loc["ex_post_real_annual_return_common_months", "value"]),
        (100.0 / 123.0) ** (12.0 / 5.0) - 1.0,
        atol=1e-14,
    )
    assert (
        summary["scattered_single_months_diagnostic"]["classification"]
        == "scattered_noncontiguous_monthly_factors_not_an_endpoint_ratio"
    )

    # 2. Contiguous monthly-CPI-change block policy ('longest_contiguous_cpi_block'): selects 2010-04..2010-05 (base 2010-03)
    block_df = compute_ex_post_real_return_metrics(
        zero_returns,
        cpi,
        interval_policy="longest_contiguous_cpi_block",
    ).set_index("metric")
    block_sum = block_df.attrs["common_months_summary"]
    assert block_sum["first_common_month"] == "2010-04"
    assert block_sum["last_common_month"] == "2010-05"
    assert block_sum["base_cpi_month"] == "2010-03"
    assert block_sum["n_common_complete_months"] == 2
    assert block_sum["calendar_months_in_span"] == 2
    assert block_sum["has_internal_cpi_gaps"] is False
    assert np.isclose(float(block_sum["cpi_index_ratio"]), 123.0 / 121.0, atol=1e-14)
    assert block_sum["outside_selected_block_months_excluded"] == ["2010-01"]
    assert block_sum["unreleased_or_missing_cpi_months_excluded"] == ["2010-02", "2010-03"]
    assert (block_df["status"] == "ok").all()

    # 3. Missing valid NYSE session replaced by a Saturday with identical row count (19 rows) must be rejected
    jan_days = expected_nyse_sessions("2010-01-01", "2010-01-31")
    bad_days = jan_days.delete(1).append(pd.DatetimeIndex(["2010-01-09"])).sort_values()
    assert len(bad_days) == len(jan_days)
    bad_month_returns = pd.Series(0.0, index=bad_days)
    bad_real = compute_ex_post_real_return_metrics(bad_month_returns, cpi)
    bad_sum = bad_real.attrs["common_months_summary"]
    assert bad_sum["n_common_complete_months"] == 0
    assert bad_sum["partial_portfolio_months_excluded"] == ["2010-01"]
    assert bad_sum["excluded_months_by_reason"]["2010-01"]["reason"] == "non_nyse_or_mismatched_session_dates"
    assert bad_sum["excluded_months_by_reason"]["2010-01"]["missing_nyse_dates"] == ["2010-01-05"]
    assert bad_sum["excluded_months_by_reason"]["2010-01"]["unexpected_non_nyse_dates"] == ["2010-01-09"]
    assert (bad_real["status"] == "unavailable").all()


def test_r3_context_cache_relocation_tamper_rejection_and_config_compatibility(
    baseline_config: AppConfig,
    tmp_path: pytest.TempPathFactory,
) -> None:
    """R3 regression: context loader hashes and reads the same resolved files, rejects tampered copies, and checks config/provenance compatibility."""
    from dataclasses import replace
    import json
    from pathlib import Path
    import shutil

    repo_root = Path(__file__).resolve().parents[1]
    orig_ctx = load_context_data(baseline_config, offline=True, repo_root=repo_root)

    # 1. Valid untouched relocated cache succeeds and matches original bit-for-bit
    relocated = Path(tmp_path) / "context_relocated"
    shutil.copytree(repo_root / "data/reference/context", relocated)
    relocated_ctx = load_context_data(
        baseline_config,
        offline=True,
        repo_root=repo_root,
        context_dir=relocated,
    )
    pd.testing.assert_frame_equal(
        relocated_ctx.split_adjusted_closes,
        orig_ctx.split_adjusted_closes,
        check_exact=True,
    )

    # 2. Tampered relocated cache is rejected (never bypasses hash check via base_dir original)
    altered_path = relocated / "etf_split_adjusted_closes.parquet"
    altered_df = pd.read_parquet(altered_path)
    altered_df.iloc[0, 0] = float(altered_df.iloc[0, 0]) * 1.10
    altered_df.to_parquet(altered_path)
    with pytest.raises(DataUnavailableError, match="SHA-256 integrity mismatch"):
        load_context_data(
            baseline_config,
            offline=True,
            repo_root=repo_root,
            context_dir=relocated,
        )

    # 3. Default-path tamper rejection in an isolated temporary repo root
    fake_repo = Path(tmp_path) / "fake_repo"
    default_ctx_dir = fake_repo / "data/reference/context"
    shutil.copytree(repo_root / "data/reference/context", default_ctx_dir)
    tampered_default = default_ctx_dir / "etf_distributions.parquet"
    dist_df = pd.read_parquet(tampered_default)
    dist_df.iloc[0, 0] = float(dist_df.iloc[0, 0]) + 1.0
    dist_df.to_parquet(tampered_default)
    with pytest.raises(DataUnavailableError, match="SHA-256 integrity mismatch"):
        load_context_data(baseline_config, offline=True, repo_root=fake_repo)

    # 4. Config coverage compatibility: frozen-2016 config is rejected by default against 2026 context,
    #    or returns an explicitly bounded compatible view with truthful identity when slice_to_config=True
    older_cfg = replace(
        baseline_config,
        data=replace(baseline_config.data, frozen_end_date="2016-12-30"),
    )
    with pytest.raises(DataUnavailableError, match="does not match requested config NYSE coverage"):
        load_context_data(older_cfg, offline=True, repo_root=repo_root)

    bounded_ctx = load_context_data(
        older_cfg,
        offline=True,
        repo_root=repo_root,
        slice_to_config=True,
    )
    assert str(bounded_ctx.split_adjusted_closes.index[-1].date()) == "2016-12-30"
    assert bounded_ctx.context_id == f"{orig_ctx.context_id}__bounded_20050103_20161230"
    assert bounded_ctx.manifest["is_bounded_view"] is True
    assert bounded_ctx.manifest["source_context_id"] == orig_ctx.context_id
    assert str(bounded_ctx.cpi_monthly["month_period"].iloc[-1]) == "2016-12"

    # 5. Incompatible tickers or tampered parent_price_dataset_id is rejected
    bad_parent_dir = Path(tmp_path) / "context_bad_parent"
    shutil.copytree(repo_root / "data/reference/context", bad_parent_dir)
    m_path = bad_parent_dir / "context_manifest.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["parent_price_dataset_id"] = "qe1_nonexistent_parent_dataset"
    m_path.write_text(json.dumps(m_data, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(DataUnavailableError, match="unknown or missing parent_price_dataset_id"):
        load_context_data(
            baseline_config,
            offline=True,
            repo_root=repo_root,
            context_dir=bad_parent_dir,
        )

