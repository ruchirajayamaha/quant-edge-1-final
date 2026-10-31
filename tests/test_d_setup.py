"""Offline smoke, contract, and configuration checks for SOLO STEP 1 (D0 setup)."""

from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

import pandas as pd
import pytest
import yaml

import quantedge
from quantedge import (
    AppConfig,
    CANONICAL_TICKERS,
    CONTRACT_SCHEMA_VERSION,
    MANDATE_NAV_USD,
    PortfolioConstraints,
    RiskEstimate,
    RiskForecastFn,
    StrategySpec,
    compute_config_hash,
    list_provisional_items,
    load_config,
)
from quantedge import (
    backtest,
    config,
    contracts,
    data,
    es,
    evt,
    kpis,
    pipeline,
    portfolio,
    returns,
    risk_budget,
    stress,
    var,
)


def test_canonical_constants_and_schema_version() -> None:
    """Canonical 7-ETF order, USD 10M NAV, and schema version 1.0.0 are frozen."""
    assert CONTRACT_SCHEMA_VERSION == "1.0.0"
    assert CANONICAL_TICKERS == ("SPY", "EFA", "EEM", "AGG", "GLD", "XLE", "XLK")
    assert MANDATE_NAV_USD == 10_000_000.0


def test_library_modules_never_import_streamlit(repo_root: Path) -> None:
    """No module under src/quantedge may import streamlit (architecture boundary)."""
    pkg_dir = repo_root / "src" / "quantedge"
    py_files = sorted(pkg_dir.glob("*.py"))
    assert len(py_files) == 14

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name.split(".")[0] for alias in node.names]
                assert "streamlit" not in imported, f"Forbidden streamlit import in {py_file}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_mod = node.module.split(".")[0]
                assert root_mod != "streamlit", f"Forbidden streamlit import in {py_file}"


def test_config_loads_offline_and_hashes_deterministically(
    repo_root: Path,
    baseline_config: AppConfig,
) -> None:
    """config.yaml loads without network access and yields a stable 64-hex SHA-256 hash."""
    reloaded = load_config(repo_root / "config.yaml")
    assert baseline_config == reloaded
    assert len(baseline_config.config_hash) == 64
    assert baseline_config.config_hash == compute_config_hash(reloaded)
    assert baseline_config.mandate.canonical_tickers == CANONICAL_TICKERS
    assert baseline_config.mandate.nav_usd == 10_000_000.0
    assert baseline_config.data.requested_start == "2005-01-01"
    assert baseline_config.data.no_implicit_forward_fill is True
    assert baseline_config.data.rf_no_backfill is True
    assert baseline_config.risk.confidence_levels == (0.90, 0.95, 0.99)
    assert baseline_config.risk.primary_backtest_model == "historical"
    assert baseline_config.risk.dashboard_risk_window_days == 1260
    assert baseline_config.risk.backtest_window_days == 500
    assert baseline_config.risk.normal_ddof == 1
    assert baseline_config.mandate.final_recommendation["decision"] is None


def test_provisional_governance_items_are_explicit(baseline_config: AppConfig) -> None:
    """All human-team governance decisions remain visibly provisional in D0."""
    items = list_provisional_items(baseline_config)
    paths = {item.field_path for item in items}
    expected_paths = {
        "mandate.investment_horizon",
        "mandate.return_target",
        "mandate.final_recommendation",
        "chronology",
        "portfolio.illustrative_weights",
        "portfolio.constraints",
        "portfolio.risk_limits",
        "stress.hypothetical_scenario",
    }
    assert expected_paths.issubset(paths)


def test_config_rejects_invalid_invariants(repo_root: Path, tmp_path: Path) -> None:
    """Malformed ticker order, predetermined decisions, or missing shock tickers fail fast."""
    raw = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))

    # 1. Wrong canonical ticker order
    bad_tickers = copy.deepcopy(raw)
    bad_tickers["mandate"]["canonical_tickers"] = ["AGG", "SPY", "EFA", "EEM", "GLD", "XLE", "XLK"]
    p1 = tmp_path / "bad_tickers.yaml"
    p1.write_text(yaml.safe_dump(bad_tickers), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical order"):
        load_config(p1)

    # 2. Predetermined investment decision
    bad_rec = copy.deepcopy(raw)
    bad_rec["mandate"]["final_recommendation"]["decision"] = "accept_with_es_adjustment"
    p2 = tmp_path / "bad_rec.yaml"
    p2.write_text(yaml.safe_dump(bad_rec), encoding="utf-8")
    with pytest.raises(ValueError, match="predetermined"):
        load_config(p2)

    # 3. Hypothetical shock missing a ticker
    bad_shock = copy.deepcopy(raw)
    del bad_shock["stress"]["hypothetical_scenario"]["shocks"]["XLK"]
    p3 = tmp_path / "bad_shock.yaml"
    p3.write_text(yaml.safe_dump(bad_shock), encoding="utf-8")
    with pytest.raises(ValueError, match="seven canonical tickers"):
        load_config(p3)


def test_risk_estimate_contract_invariants() -> None:
    """RiskEstimate enforces finite numbers, explicit unavailable None metrics, and xi>=1 warning mode."""
    valid_ok = RiskEstimate(
        model="historical",
        confidence=0.99,
        horizon_days=1,
        var_loss=0.021,
        es_loss=0.028,
        n_obs=1260,
        sample_start="2019-01-02",
        sample_end="2023-12-29",
        status="ok",
    )
    assert valid_ok.var_loss == 0.021

    # EVT xi >= 1 case: finite VaR, divergent ES -> es_loss=None with status='warning'
    evt_xi_ge_1 = RiskEstimate(
        model="evt_pot",
        confidence=0.99,
        horizon_days=1,
        var_loss=0.024,
        es_loss=None,
        n_obs=1260,
        sample_start="2019-01-02",
        sample_end="2023-12-29",
        status="warning",
        reason="GPD shape xi >= 1: first moment diverges; ES is undefined/infinite.",
    )
    assert evt_xi_ge_1.es_loss is None

    # Unavailable must carry None for both metrics and a non-empty reason
    unavail = RiskEstimate(
        model="evt_pot",
        confidence=0.90,
        horizon_days=1,
        var_loss=None,
        es_loss=None,
        n_obs=1260,
        sample_start="2019-01-02",
        sample_end="2023-12-29",
        status="unavailable",
        reason="Requested confidence 0.90 is below POT threshold quantile 0.95.",
    )
    assert unavail.var_loss is None and unavail.es_loss is None

    # Fabricated zero on unavailable status must fail
    with pytest.raises(ValueError, match="must be None"):
        RiskEstimate(
            model="evt_pot",
            confidence=0.90,
            horizon_days=1,
            var_loss=0.0,
            es_loss=0.0,
            n_obs=1260,
            sample_start=None,
            sample_end=None,
            status="unavailable",
            reason="Below threshold",
        )

    # Nonfinite inf ES must fail
    with pytest.raises(ValueError, match="finite or None"):
        RiskEstimate(
            model="evt_pot",
            confidence=0.99,
            horizon_days=1,
            var_loss=0.024,
            es_loss=float("inf"),
            n_obs=1260,
            sample_start=None,
            sample_end=None,
            status="warning",
            reason="xi >= 1",
        )


def test_frozen_shared_helper_and_callback_signatures() -> None:
    """Shared D0 helper signatures match CONTRACTS.md specifications."""
    nm_sig = inspect.signature(var.normal_moments)
    assert list(nm_sig.parameters.keys()) == ["asset_returns"]

    tw_sig = inspect.signature(es.empirical_tail_weights)
    assert list(tw_sig.parameters.keys()) == ["losses", "confidence"]

    er_sig = inspect.signature(var.estimate_risk)
    assert list(er_sig.parameters.keys()) == [
        "train_asset_returns",
        "weights",
        "model",
        "confidence",
        "seed",
    ]
    assert isinstance(
        lambda train_asset_returns, weights, *, confidence, seed=None: None,
        RiskForecastFn,
    )


def test_all_analytics_stubs_explicitly_raise_not_implemented(
    baseline_config: AppConfig,
    synthetic_asset_returns: pd.DataFrame,
    equal_canonical_weights: pd.Series,
) -> None:
    """Every analytics entrypoint raises NotImplementedError in Step 1 rather than returning fake output."""
    s = synthetic_asset_returns["SPY"]
    weights_df = pd.DataFrame(
        [equal_canonical_weights.values] * len(synthetic_asset_returns),
        index=synthetic_asset_returns.index,
        columns=CANONICAL_TICKERS,
    )
    dummy_cb = lambda train_asset_returns, weights, *, confidence, seed=None: None  # noqa: E731

    stub_calls = [
        lambda: data.load_data(baseline_config, offline=True),
        lambda: returns.compute_session_returns(synthetic_asset_returns),
        lambda: returns.align_risk_free_rate(s, synthetic_asset_returns.index),
        lambda: returns.run_stationarity_diagnostics({"SPY": s}),
        lambda: kpis.compute_kpis(s, s, s, s),
        lambda: portfolio.build_portfolio_path(
            synthetic_asset_returns,
            StrategySpec(strategy_id="min_var", objective="min_variance"),
            baseline_config,
        ),
        lambda: portfolio.construct_weights(
            synthetic_asset_returns,
            PortfolioConstraints(),
            "min_variance",
        ),
        lambda: var.normal_moments(synthetic_asset_returns),
        lambda: var.estimate_risk(
            synthetic_asset_returns,
            equal_canonical_weights,
            model="historical",
            confidence=0.99,
            seed=202601,
        ),
        lambda: var.get_risk_forecaster("historical"),
        lambda: es.empirical_tail_weights(-s, 0.99),
        lambda: evt.estimate_evt_pot(
            synthetic_asset_returns,
            equal_canonical_weights,
            confidence=0.99,
        ),
        lambda: evt.evt_threshold_diagnostics(-s),
        lambda: backtest.rolling_backtest(
            synthetic_asset_returns,
            weights_df,
            dummy_cb,
            confidence=0.99,
            window=3,
        ),
        lambda: backtest.coverage_tests(pd.DataFrame()),
        lambda: backtest.basel_traffic_light(pd.DataFrame()),
        lambda: risk_budget.risk_contributions(
            synthetic_asset_returns,
            equal_canonical_weights,
            confidence=0.99,
            method="historical_es",
        ),
        lambda: risk_budget.compare_feasible_allocations(
            synthetic_asset_returns,
            {"eq": equal_canonical_weights},
            {},
            dummy_cb,
        ),
        lambda: stress.run_stress_tests(
            synthetic_asset_returns,
            equal_canonical_weights,
            baseline_config.stress.historical_scenarios,
        ),
        lambda: pipeline.run_pipeline(baseline_config, offline=True),
    ]

    for call in stub_calls:
        with pytest.raises(NotImplementedError):
            call()

    assert quantedge.__version__ == "0.1.0"
    assert hasattr(contracts, "DataBundle")
    assert hasattr(config, "load_config")
