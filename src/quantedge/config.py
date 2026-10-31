"""Typed configuration loader, validator, and deterministic hasher for Quant Edge 1.0.

Loads ``config.yaml`` offline without market/network access, validates structural and
mandate invariants, computes a reproducible SHA-256 ``config_hash``, and surfaces all
provisional governance fields that still require human team review and sign-off.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml

from quantedge.contracts import (
    CANONICAL_TICKERS,
    CONTRACT_SCHEMA_VERSION,
    CORE_RISK_MODELS,
    DEFENSIVE_TICKERS,
    EQUITY_TICKERS,
    MANDATORY_COMPARISON_CONFIDENCES,
    MARKET_PROXY_TICKER,
    PortfolioConstraints,
    SUPPORTED_CONFIDENCE_LEVELS,
    StressScenarioSpec,
)

DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().parents[2] / "config.yaml"


@dataclass(frozen=True)
class ProvisionalItem:
    """Explicit record of a governance or modelling choice awaiting human sign-off."""

    field_path: str
    status: str
    note: str


@dataclass(frozen=True)
class MandateConfig:
    """Endowment mandate scale, canonical universe, and provisional governance targets."""

    nav_usd: float
    canonical_tickers: tuple[str, ...]
    equity_tickers: tuple[str, ...]
    defensive_tickers: tuple[str, ...]
    market_proxy_ticker: str
    benchmark_60_40_weights: dict[str, float]
    investment_horizon_value: str
    investment_horizon_status: str
    investment_horizon_note: str
    return_target: dict[str, Any]
    final_recommendation: dict[str, Any]


@dataclass(frozen=True)
class DataConfig:
    """Market and risk-free data acquisition, adjustment, and caching settings."""

    requested_start: str
    end_date_policy: str
    frozen_end_date: str | None
    price_source: str
    price_adjustment: str
    no_implicit_forward_fill: bool
    fred_rf_series: str
    fred_csv_url: str
    rf_quote_basis: str
    rf_conversion_formula: str
    rf_trading_days_per_year: int
    rf_availability_lag_sessions: int
    rf_no_backfill: bool
    raw_dir: str
    processed_dir: str
    results_dir: str


@dataclass(frozen=True)
class ChronologyConfig:
    """Frozen development / selection / out-of-sample evaluation split and execution rule."""

    status: str
    development_start: str
    development_end: str
    selection_start: str
    selection_end: str
    evaluation_start: str
    evaluation_end: str | None
    execution_assumption: str


@dataclass(frozen=True)
class PortfolioConfig:
    """Rebalancing, cost, illustrative allocation, and provisional constraint settings."""

    rebalance_frequency: str
    estimation_window_days: int
    transaction_cost_bps_one_way: float
    annualization_days: int
    covariance_estimator_default: str
    illustrative_label: str
    illustrative_provisional: bool
    illustrative_note: str
    illustrative_weights: dict[str, float]
    constraints_status: str
    constraints: PortfolioConstraints
    risk_limits: dict[str, Any]


@dataclass(frozen=True)
class RiskConfig:
    """VaR, ES, EVT, and rolling validation parameters."""

    confidence_levels: tuple[float, ...]
    mandatory_comparison_confidences: tuple[float, ...]
    horizon_days: int
    loss_convention: str
    primary_backtest_model: str
    supported_models: tuple[str, ...]
    dashboard_risk_window_days: int
    backtest_window_days: int
    basel_diagnostic_window_days: int
    basel_diagnostic_confidence: float
    normal_ddof: int
    monte_carlo_simulations: int
    evt_threshold_quantile: float
    evt_min_exceedances: int


@dataclass(frozen=True)
class SeedsConfig:
    """Deterministic integer seeds for reproducible simulation and bootstrap checks."""

    global_seed: int
    monte_carlo: int
    evt_bootstrap: int
    backtest: int


@dataclass(frozen=True)
class StressConfig:
    """Historical replay crisis windows and explicit 7-ETF hypothetical scenario."""

    historical_scenarios: tuple[StressScenarioSpec, ...]
    hypothetical_scenario: StressScenarioSpec
    hypothetical_status: str


@dataclass(frozen=True)
class AppConfig:
    """Top-level validated configuration object for Quant Edge 1.0."""

    schema_version: str
    project_name: str
    mandate: MandateConfig
    data: DataConfig
    chronology: ChronologyConfig
    portfolio: PortfolioConfig
    risk: RiskConfig
    seeds: SeedsConfig
    stress: StressConfig

    def to_dict(self) -> dict[str, Any]:
        """Convert validated configuration to a plain JSON-serializable dictionary."""
        return asdict(self)

    @property
    def config_hash(self) -> str:
        """Deterministic SHA-256 hex digest of the validated configuration."""
        return compute_config_hash(self)


def compute_config_hash(config: AppConfig | dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hex digest over canonicalized config values."""
    payload = config.to_dict() if isinstance(config, AppConfig) else config
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def list_provisional_items(config: AppConfig) -> list[ProvisionalItem]:
    """Return all configuration items still marked provisional or pending human decision."""
    items: list[ProvisionalItem] = []

    if "PROVISIONAL" in config.mandate.investment_horizon_status.upper():
        items.append(
            ProvisionalItem(
                field_path="mandate.investment_horizon",
                status=config.mandate.investment_horizon_status,
                note=config.mandate.investment_horizon_note,
            )
        )

    rt_status = str(config.mandate.return_target.get("status", ""))
    if "PROVISIONAL" in rt_status.upper() or "PENDING" in rt_status.upper():
        items.append(
            ProvisionalItem(
                field_path="mandate.return_target",
                status=rt_status,
                note=str(config.mandate.return_target.get("note", "")),
            )
        )

    rec_status = str(config.mandate.final_recommendation.get("status", ""))
    if "PENDING" in rec_status.upper() or "PROVISIONAL" in rec_status.upper():
        items.append(
            ProvisionalItem(
                field_path="mandate.final_recommendation",
                status=rec_status,
                note=str(config.mandate.final_recommendation.get("note", "")),
            )
        )

    if "PROVISIONAL" in config.chronology.status.upper():
        items.append(
            ProvisionalItem(
                field_path="chronology",
                status=config.chronology.status,
                note=config.chronology.execution_assumption,
            )
        )

    if config.portfolio.illustrative_provisional:
        items.append(
            ProvisionalItem(
                field_path="portfolio.illustrative_weights",
                status=config.portfolio.illustrative_label,
                note=config.portfolio.illustrative_note,
            )
        )

    if config.portfolio.constraints.provisional or "PROVISIONAL" in config.portfolio.constraints_status.upper():
        items.append(
            ProvisionalItem(
                field_path="portfolio.constraints",
                status=config.portfolio.constraints_status,
                note=config.portfolio.constraints.notes,
            )
        )

    rl_status = str(config.portfolio.risk_limits.get("status", ""))
    if "PROVISIONAL" in rl_status.upper() or "PENDING" in rl_status.upper():
        items.append(
            ProvisionalItem(
                field_path="portfolio.risk_limits",
                status=rl_status,
                note=str(config.portfolio.risk_limits.get("note", "")),
            )
        )

    if config.stress.hypothetical_scenario.provisional or "PROVISIONAL" in config.stress.hypothetical_status.upper():
        items.append(
            ProvisionalItem(
                field_path="stress.hypothetical_scenario",
                status=config.stress.hypothetical_status,
                note=config.stress.hypothetical_scenario.rationale,
            )
        )

    return items


def _validate_raw_config(raw: dict[str, Any]) -> AppConfig:
    """Parse and validate a raw YAML dictionary into an immutable ``AppConfig``."""
    schema_version = str(raw.get("schema_version", ""))
    if schema_version != CONTRACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported config schema_version {schema_version!r}; "
            f"expected {CONTRACT_SCHEMA_VERSION!r}."
        )

    project_name = str(raw.get("project_name", "")).strip()
    if not project_name:
        raise ValueError("project_name must be a non-empty string.")

    # Mandate validation
    mandate_raw = raw["mandate"]
    nav_usd = float(mandate_raw["nav_usd"])
    if not math.isfinite(nav_usd) or nav_usd <= 0.0:
        raise ValueError(f"mandate.nav_usd must be finite and > 0; got {nav_usd!r}")

    canonical_tickers = tuple(str(t) for t in mandate_raw["canonical_tickers"])
    if canonical_tickers != CANONICAL_TICKERS:
        raise ValueError(
            f"mandate.canonical_tickers must match exact canonical order {CANONICAL_TICKERS}; "
            f"got {canonical_tickers}."
        )

    equity_tickers = tuple(str(t) for t in mandate_raw["equity_tickers"])
    defensive_tickers = tuple(str(t) for t in mandate_raw["defensive_tickers"])
    if equity_tickers != EQUITY_TICKERS or defensive_tickers != DEFENSIVE_TICKERS:
        raise ValueError(
            "mandate.equity_tickers and mandate.defensive_tickers must match canonical partitions."
        )

    market_proxy = str(mandate_raw["market_proxy_ticker"])
    if market_proxy != MARKET_PROXY_TICKER:
        raise ValueError(f"mandate.market_proxy_ticker must be {MARKET_PROXY_TICKER!r}.")

    bench_weights = {str(k): float(v) for k, v in mandate_raw["benchmark_60_40_weights"].items()}
    if set(bench_weights.keys()) != {"SPY", "AGG"} or abs(sum(bench_weights.values()) - 1.0) > 1e-9:
        raise ValueError("benchmark_60_40_weights must allocate across SPY and AGG summing to 1.0.")

    inv_horizon = mandate_raw["investment_horizon"]
    final_rec = dict(mandate_raw["final_recommendation"])
    if final_rec.get("decision") is not None:
        raise ValueError(
            "mandate.final_recommendation.decision must remain None during baseline setup; "
            "do not hardcode a predetermined investment conclusion."
        )

    mandate_cfg = MandateConfig(
        nav_usd=nav_usd,
        canonical_tickers=canonical_tickers,
        equity_tickers=equity_tickers,
        defensive_tickers=defensive_tickers,
        market_proxy_ticker=market_proxy,
        benchmark_60_40_weights=bench_weights,
        investment_horizon_value=str(inv_horizon["value"]),
        investment_horizon_status=str(inv_horizon["status"]),
        investment_horizon_note=str(inv_horizon.get("note", "")),
        return_target=dict(mandate_raw["return_target"]),
        final_recommendation=final_rec,
    )

    # Data validation
    data_raw = raw["data"]
    if not bool(data_raw["no_implicit_forward_fill"]):
        raise ValueError("data.no_implicit_forward_fill must be True per project conventions.")
    if not bool(data_raw["rf_no_backfill"]):
        raise ValueError("data.rf_no_backfill must be True per project conventions.")
    rf_days = int(data_raw["rf_trading_days_per_year"])
    rf_lag = int(data_raw["rf_availability_lag_sessions"])
    if rf_days <= 0 or rf_lag < 0:
        raise ValueError("rf_trading_days_per_year must be > 0 and rf_availability_lag_sessions >= 0.")

    frozen_end = data_raw.get("frozen_end_date")
    data_cfg = DataConfig(
        requested_start=str(data_raw["requested_start"]),
        end_date_policy=str(data_raw["end_date_policy"]),
        frozen_end_date=str(frozen_end) if frozen_end is not None else None,
        price_source=str(data_raw["price_source"]),
        price_adjustment=str(data_raw["price_adjustment"]),
        no_implicit_forward_fill=bool(data_raw["no_implicit_forward_fill"]),
        fred_rf_series=str(data_raw["fred_rf_series"]),
        fred_csv_url=str(data_raw["fred_csv_url"]),
        rf_quote_basis=str(data_raw["rf_quote_basis"]),
        rf_conversion_formula=str(data_raw["rf_conversion_formula"]),
        rf_trading_days_per_year=rf_days,
        rf_availability_lag_sessions=rf_lag,
        rf_no_backfill=bool(data_raw["rf_no_backfill"]),
        raw_dir=str(data_raw["raw_dir"]),
        processed_dir=str(data_raw["processed_dir"]),
        results_dir=str(data_raw["results_dir"]),
    )

    # Chronology validation
    chron_raw = raw["chronology"]
    dev_start = str(chron_raw["development_start"])
    dev_end = str(chron_raw["development_end"])
    sel_start = str(chron_raw["selection_start"])
    sel_end = str(chron_raw["selection_end"])
    eval_start = str(chron_raw["evaluation_start"])
    eval_end = chron_raw.get("evaluation_end")
    if not (dev_start < dev_end < sel_start < sel_end < eval_start):
        raise ValueError(
            "Chronology dates must satisfy "
            "development_start < development_end < selection_start < selection_end < evaluation_start."
        )
    if eval_end is not None and not (eval_start < str(eval_end)):
        raise ValueError("evaluation_end, when set, must be strictly after evaluation_start.")

    chronology_cfg = ChronologyConfig(
        status=str(chron_raw["status"]),
        development_start=dev_start,
        development_end=dev_end,
        selection_start=sel_start,
        selection_end=sel_end,
        evaluation_start=eval_start,
        evaluation_end=str(eval_end) if eval_end is not None else None,
        execution_assumption=str(chron_raw["execution_assumption"]),
    )

    # Portfolio validation
    port_raw = raw["portfolio"]
    illus_raw = port_raw["illustrative_weights"]
    raw_illus_weights = {str(k): float(v) for k, v in illus_raw["weights"].items()}
    if set(raw_illus_weights.keys()) != set(CANONICAL_TICKERS):
        raise ValueError(
            f"portfolio.illustrative_weights must cover all seven canonical tickers "
            f"{CANONICAL_TICKERS}; got {tuple(raw_illus_weights.keys())}."
        )
    illus_weights = {ticker: raw_illus_weights[ticker] for ticker in CANONICAL_TICKERS}
    if abs(sum(illus_weights.values()) - 1.0) > 1e-9:
        raise ValueError(
            f"portfolio.illustrative_weights must sum to 1.0; got {sum(illus_weights.values()):.12f}."
        )
    if not bool(illus_raw["provisional"]):
        raise ValueError(
            "portfolio.illustrative_weights must be marked provisional=True so it cannot "
            "masquerade as a signed investment recommendation."
        )

    c_raw = port_raw["constraints"]
    c_status = str(c_raw["status"])
    constraints = PortfolioConstraints(
        long_only=bool(c_raw["long_only"]),
        fully_invested=bool(c_raw["fully_invested"]),
        min_weight_per_etf=float(c_raw["min_weight_per_etf"]),
        max_weight_per_etf=(
            float(c_raw["max_weight_per_etf"]) if c_raw.get("max_weight_per_etf") is not None else None
        ),
        max_equity_weight=(
            float(c_raw["max_equity_weight"]) if c_raw.get("max_equity_weight") is not None else None
        ),
        min_defensive_weight=(
            float(c_raw["min_defensive_weight"])
            if c_raw.get("min_defensive_weight") is not None
            else None
        ),
        provisional="PROVISIONAL" in c_status.upper(),
        notes=str(c_raw.get("note", "")),
    )

    portfolio_cfg = PortfolioConfig(
        rebalance_frequency=str(port_raw["rebalance_frequency"]),
        estimation_window_days=int(port_raw["estimation_window_days"]),
        transaction_cost_bps_one_way=float(port_raw["transaction_cost_bps_one_way"]),
        annualization_days=int(port_raw["annualization_days"]),
        covariance_estimator_default=str(port_raw["covariance_estimator_default"]),
        illustrative_label=str(illus_raw["label"]),
        illustrative_provisional=bool(illus_raw["provisional"]),
        illustrative_note=str(illus_raw.get("note", "")),
        illustrative_weights=illus_weights,
        constraints_status=c_status,
        constraints=constraints,
        risk_limits=dict(port_raw["risk_limits"]),
    )

    # Risk validation
    risk_raw = raw["risk"]
    conf_levels = tuple(float(c) for c in risk_raw["confidence_levels"])
    if conf_levels != SUPPORTED_CONFIDENCE_LEVELS:
        raise ValueError(
            f"risk.confidence_levels must equal {SUPPORTED_CONFIDENCE_LEVELS}; got {conf_levels}."
        )
    mandatory_conf = tuple(float(c) for c in risk_raw["mandatory_comparison_confidences"])
    if mandatory_conf != MANDATORY_COMPARISON_CONFIDENCES:
        raise ValueError(
            f"risk.mandatory_comparison_confidences must equal {MANDATORY_COMPARISON_CONFIDENCES}; "
            f"got {mandatory_conf}."
        )
    supported_models = tuple(str(m) for m in risk_raw["supported_models"])
    if supported_models != CORE_RISK_MODELS:
        raise ValueError(
            f"risk.supported_models must equal {CORE_RISK_MODELS}; got {supported_models}."
        )
    primary_model = str(risk_raw["primary_backtest_model"])
    if primary_model not in supported_models:
        raise ValueError(f"primary_backtest_model {primary_model!r} must be in supported_models.")
    normal_ddof = int(risk_raw["normal_ddof"])
    if normal_ddof != 1:
        raise ValueError("risk.normal_ddof is frozen to 1 in D0 contracts.")

    risk_cfg = RiskConfig(
        confidence_levels=conf_levels,
        mandatory_comparison_confidences=mandatory_conf,
        horizon_days=int(risk_raw["horizon_days"]),
        loss_convention=str(risk_raw["loss_convention"]),
        primary_backtest_model=primary_model,
        supported_models=supported_models,
        dashboard_risk_window_days=int(risk_raw["dashboard_risk_window_days"]),
        backtest_window_days=int(risk_raw["backtest_window_days"]),
        basel_diagnostic_window_days=int(risk_raw["basel_diagnostic_window_days"]),
        basel_diagnostic_confidence=float(risk_raw["basel_diagnostic_confidence"]),
        normal_ddof=normal_ddof,
        monte_carlo_simulations=int(risk_raw["monte_carlo_simulations"]),
        evt_threshold_quantile=float(risk_raw["evt_threshold_quantile"]),
        evt_min_exceedances=int(risk_raw["evt_min_exceedances"]),
    )

    # Seeds validation
    seeds_raw = raw["seeds"]
    seeds_cfg = SeedsConfig(
        global_seed=int(seeds_raw["global_seed"]),
        monte_carlo=int(seeds_raw["monte_carlo"]),
        evt_bootstrap=int(seeds_raw["evt_bootstrap"]),
        backtest=int(seeds_raw["backtest"]),
    )

    # Stress validation
    stress_raw = raw["stress"]
    hist_specs: list[StressScenarioSpec] = []
    for item in stress_raw["historical_scenarios"]:
        start_d = str(item["start_date"])
        end_d = str(item["end_date"])
        if not (start_d < end_d):
            raise ValueError(
                f"Historical scenario {item['scenario_id']!r} requires start_date < end_date."
            )
        hist_specs.append(
            StressScenarioSpec(
                scenario_id=str(item["scenario_id"]),
                label=str(item["label"]),
                scenario_type="historical",
                start_date=start_d,
                end_date=end_d,
                provisional=bool(item.get("provisional", False)),
            )
        )

    hyp_raw = stress_raw["hypothetical_scenario"]
    raw_hyp_shocks = {str(k): float(v) for k, v in hyp_raw["shocks"].items()}
    if set(raw_hyp_shocks.keys()) != set(CANONICAL_TICKERS):
        raise ValueError(
            f"Hypothetical stress scenario shocks must explicitly name all seven canonical tickers "
            f"{CANONICAL_TICKERS}; got {tuple(raw_hyp_shocks.keys())}."
        )
    hyp_shocks = {ticker: raw_hyp_shocks[ticker] for ticker in CANONICAL_TICKERS}
    hyp_status = str(hyp_raw["status"])
    hyp_spec = StressScenarioSpec(
        scenario_id=str(hyp_raw["scenario_id"]),
        label=str(hyp_raw["label"]),
        scenario_type="hypothetical",
        shocks=hyp_shocks,
        provisional="PROVISIONAL" in hyp_status.upper(),
        rationale=str(hyp_raw.get("rationale", "")),
    )

    stress_cfg = StressConfig(
        historical_scenarios=tuple(hist_specs),
        hypothetical_scenario=hyp_spec,
        hypothetical_status=hyp_status,
    )

    return AppConfig(
        schema_version=schema_version,
        project_name=project_name,
        mandate=mandate_cfg,
        data=data_cfg,
        chronology=chronology_cfg,
        portfolio=portfolio_cfg,
        risk=risk_cfg,
        seeds=seeds_cfg,
        stress=stress_cfg,
    )


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load and validate ``config.yaml`` from ``path`` (defaults to repository root ``config.yaml``)."""
    resolved = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not resolved.exists():
        raise FileNotFoundError(f"Configuration file not found: {resolved}")
    with resolved.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"Configuration root in {resolved} must be a YAML mapping.")
    return _validate_raw_config(raw)
