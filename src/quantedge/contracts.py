"""Shared typed contracts, constants, and callback protocols for Quant Edge 1.0.

Frozen in SOLO STEP 1 (milestone D0). All analytical modules in ``src/quantedge``
and orchestration in ``pipeline.py`` consume these shared interfaces without
importing Streamlit.

Conventions:
- Asset prices and returns share sorted, unique trading-session ``DatetimeIndex`` values.
- Returns, weights, and risk quantities are fractions (not percentages).
- Portfolio return at session ``t`` uses weights known strictly BEFORE session ``t``
  (``weights_before.loc[t]``), drifting between documented rebalance boundaries.
- Loss is negative simple portfolio return: ``L_t = -R_{p,t}``. Positive risk values
  represent losses before transaction costs; nonpositive loss quantiles are preserved
  rather than masked with ``abs()``.
- Unavailable metrics are ``None`` (never ``0.0``, ``NaN``, or ``inf``) and carry an
  explicit ``status`` and ``reason``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Literal, Protocol, runtime_checkable

import pandas as pd

CONTRACT_SCHEMA_VERSION: str = "1.1.0"

CANONICAL_TICKERS: tuple[str, ...] = ("SPY", "EFA", "EEM", "AGG", "GLD", "XLE", "XLK")
EQUITY_TICKERS: tuple[str, ...] = ("SPY", "EFA", "EEM", "XLE", "XLK")
DEFENSIVE_TICKERS: tuple[str, ...] = ("AGG", "GLD")
MARKET_PROXY_TICKER: str = "SPY"

MANDATE_NAV_USD: float = 10_000_000.0

SUPPORTED_CONFIDENCE_LEVELS: tuple[float, ...] = (0.90, 0.95, 0.99)
MANDATORY_COMPARISON_CONFIDENCES: tuple[float, ...] = (0.95, 0.99)
CORE_RISK_MODELS: tuple[str, ...] = (
    "historical",
    "parametric_normal",
    "monte_carlo_normal",
    "evt_pot",
)

EstimateStatus = Literal["ok", "warning", "unavailable"]
RiskModelName = Literal["historical", "parametric_normal", "monte_carlo_normal", "evt_pot"]
ScenarioType = Literal["historical", "hypothetical"]

QUALITY_FLAG_COLUMNS: tuple[str, ...] = ("date", "ticker", "rule", "value", "action")
KPI_COLUMNS: tuple[str, ...] = ("metric", "value", "unit", "status", "note")
BACKTEST_COLUMNS: tuple[str, ...] = (
    "date",
    "model",
    "confidence",
    "forecast_var",
    "forecast_es",
    "realized_loss",
    "exceedance",
    "train_start",
    "train_end",
    "status",
    "reason",
)
COVERAGE_TEST_COLUMNS: tuple[str, ...] = (
    "model",
    "confidence",
    "n_valid",
    "n_skipped",
    "n_exceedances",
    "expected_rate",
    "observed_rate",
    "lr_uc",
    "p_uc",
    "lr_ind",
    "p_ind",
    "lr_cc",
    "p_cc",
    "status",
    "note",
)
RISK_CONTRIBUTION_COLUMNS: tuple[str, ...] = (
    "ticker",
    "weight",
    "marginal_risk",
    "component_risk",
    "pct_contribution",
    "total_risk",
    "method",
    "confidence",
    "status",
    "note",
)
STRESS_SCENARIO_COLUMNS: tuple[str, ...] = (
    "scenario_id",
    "scenario_type",
    "portfolio_id",
    "start_date",
    "end_date",
    "total_return",
    "max_drawdown",
    "worst_day_return",
    "usd_loss",
    "status",
    "note",
)


@dataclass(frozen=True)
class DataManifest:
    """Reproducibility manifest for a single shared market-data snapshot."""

    dataset_id: str
    schema_version: str
    requested_start: str
    requested_end: str | None
    actual_start: str
    actual_end: str
    retrieved_at_utc: str
    tickers: tuple[str, ...]
    source_urls: dict[str, str]
    price_adjustment: str
    row_exclusions: dict[str, Any]
    file_sha256: dict[str, str]
    rf_convention: dict[str, Any]
    session_calendar_note: str = ""
    offline_cache_used: bool = False
    notes: tuple[str, ...] = ()
    policy_revision: str = "r2_hardened"
    parent_dataset_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize manifest metadata to a JSON-compatible dictionary."""
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        """Allow read-only dictionary-style lookup on manifest fields."""
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        """Return attribute value if present, else ``default``."""
        return getattr(self, key, default)


@dataclass(frozen=True)
class DataBundle:
    """Canonical market-data bundle shared across all analytical modules.

    Attributes:
        prices: Adjusted close ``DataFrame`` on the documented shared US trading-session
            grid with ascending unique ``DatetimeIndex`` and exact columns
            ``SPY, EFA, EEM, AGG, GLD, XLE, XLK``. Missing observations remain un-filled.
        simple_returns: Complete one-session ``P_t / P_{t-1} - 1`` ``DataFrame`` computed
            on the uncollapsed session grid without implicit forward fill or artificial
            first-day zero; incomplete rows are excluded/counted only after return calculation.
        log_returns: Log returns ``log1p(simple_returns)`` aligned identically to
            ``simple_returns``.
        rf_daily: Fractional approximate trading-day risk-free proxy aligned to return
            dates from past available ``DTB3`` quotes only (never backfilled).
        quality_flags: Tidy ``DataFrame`` with columns ``date, ticker, rule, value, action``.
            Flagging does not automatically drop observations.
        manifest: Snapshot provenance, hashes, bounds, exclusion counts, and RF conventions.
        raw_rf_quotes: Optional raw annual-percent ``DTB3`` observation table preserved
            with original observation dates.
        excluded_return_rows: Optional table recording session gaps / excluded return dates
            so continuity-sensitive diagnostics (e.g., 250-day Basel window) detect breaks.
        rf_provenance: Optional per-return table of the decision cutoff, selected observation,
            value, version, and availability evidence under versioned RF policies.
        rf_accrual_sensitivity: Optional labelled 91-day bill accrual conversion sensitivity on
            the same selected quotes. It is not the primary RF and not a realized return.
    """

    prices: pd.DataFrame
    simple_returns: pd.DataFrame
    log_returns: pd.DataFrame
    rf_daily: pd.Series
    quality_flags: pd.DataFrame
    manifest: DataManifest
    raw_rf_quotes: pd.DataFrame | None = None
    excluded_return_rows: pd.DataFrame | None = None
    ex_post_rf_daily: pd.Series | None = None
    quarantined_prices: pd.DataFrame | None = None
    rf_provenance: pd.DataFrame | None = None
    rf_accrual_sensitivity: pd.Series | None = None


@dataclass(frozen=True)
class PortfolioConstraints:
    """Mandate and optimization constraints for the 7-ETF allocation universe."""

    long_only: bool = True
    fully_invested: bool = True
    min_weight_per_etf: float = 0.0
    max_weight_per_etf: float | None = 0.40
    max_equity_weight: float | None = 0.35
    min_defensive_weight: float | None = 0.40
    provisional: bool = True
    notes: str = ""


@dataclass(frozen=True)
class StrategySpec:
    """Specification for constructing and rebalancing a portfolio path."""

    strategy_id: str
    objective: str
    rebalance_frequency: str = "M"
    estimation_window_days: int | None = 504
    covariance_estimator: str = "sample_ddof1"
    constraints: PortfolioConstraints | None = None
    fixed_weights: dict[str, float] | None = None
    target_annual_return: float | None = None
    provisional: bool = True


@dataclass(frozen=True)
class PortfolioPath:
    """Time-series portfolio trajectory with strict pre-return weight timing.

    Attributes:
        weights_before: ``DataFrame`` (date x canonical ticker) of holdings weights
            known strictly before each session's close-to-close return.
        gross_returns: Daily simple portfolio return ``Series`` before transaction costs.
        net_returns: Daily simple portfolio return ``Series`` after rebalance costs.
        turnover: Daily weight turnover fraction ``Series``.
        costs: Daily transaction cost fraction of NAV ``Series``.
        wealth: Cumulative net wealth ``Series`` anchored from initial wealth ``1.0``.
        drawdown: Fractional drawdown ``Series`` derived from net wealth including
            initial wealth ``1.0``.
        rebalances: Table recording decision dates, effective dates, execution timing,
            training bounds, target weights, solver status, and constraint feasibility.
        metadata: Strategy ID, parameters, train/selection/evaluation boundaries, and
            rebalance/cost conventions.
    """

    weights_before: pd.DataFrame
    gross_returns: pd.Series
    net_returns: pd.Series
    turnover: pd.Series
    costs: pd.Series
    wealth: pd.Series
    drawdown: pd.Series
    rebalances: pd.DataFrame
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RiskEstimate:
    """One-horizon simple-return loss risk estimate (VaR and ES).

    Values are fractional one-day simple-return losses before transaction costs:
    ``USD loss = loss_fraction * portfolio_NAV``. Unavailable quantities must be
    ``None`` (never ``0.0``, ``NaN``, or ``inf``).
    """

    model: str
    confidence: float
    horizon_days: int
    var_loss: float | None
    es_loss: float | None
    n_obs: int
    sample_start: str | pd.Timestamp | None
    sample_end: str | pd.Timestamp | None
    status: EstimateStatus
    reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in ("ok", "warning", "unavailable"):
            raise ValueError(f"Invalid RiskEstimate status: {self.status!r}")
        if not (0.0 < self.confidence < 1.0):
            raise ValueError(f"confidence must lie strictly in (0, 1); got {self.confidence!r}")
        if self.horizon_days < 1:
            raise ValueError(f"horizon_days must be >= 1; got {self.horizon_days!r}")
        if self.n_obs < 0:
            raise ValueError(f"n_obs must be >= 0; got {self.n_obs!r}")
        if self.var_loss is not None and not math.isfinite(self.var_loss):
            raise ValueError(
                "var_loss must be finite or None; diagnose nonfinite quantities explicitly."
            )
        if self.es_loss is not None and not math.isfinite(self.es_loss):
            raise ValueError(
                "es_loss must be finite or None; diagnose nonfinite ES (e.g. xi >= 1) via None + status/reason."
            )
        if self.status == "unavailable":
            if self.var_loss is not None or self.es_loss is not None:
                raise ValueError(
                    "When status='unavailable', both var_loss and es_loss must be None."
                )
            if not self.reason:
                raise ValueError("When status='unavailable', an explicit reason is required.")
        if self.status == "ok" and (self.var_loss is None or self.es_loss is None):
            raise ValueError(
                "When status='ok', both var_loss and es_loss must be finite floats "
                "(use status='warning' if only var_loss is finite and es_loss is unavailable)."
            )


@runtime_checkable
class RiskForecastFn(Protocol):
    """Generic callback signature for point-in-time or rolling VaR/ES forecasting."""

    def __call__(
        self,
        train_asset_returns: pd.DataFrame,
        weights: pd.Series,
        *,
        confidence: float,
        seed: int | None = None,
    ) -> RiskEstimate:
        """Forecast one-day simple-return VaR/ES from historical asset returns and fixed weights."""


@dataclass(frozen=True)
class StressScenarioSpec:
    """Historical replay window or explicit 7-ETF hypothetical one-step shock vector."""

    scenario_id: str
    label: str
    scenario_type: ScenarioType
    start_date: str | None = None
    end_date: str | None = None
    shocks: dict[str, float] | None = None
    provisional: bool = False
    rationale: str = ""


@dataclass(frozen=True)
class ResultBundleMetadata:
    """Provenance metadata attached to every orchestrated result bundle."""

    bundle_id: str
    schema_version: str
    code_version: str
    dataset_id: str | None
    config_hash: str
    computed_at_utc: str
    forecast_convention: str
    cost_convention: str
    provisional_fields: tuple[str, ...]


@dataclass(frozen=True)
class PipelineResultBundle:
    """Single source-of-truth result bundle shared by the Streamlit app and exported reports."""

    metadata: ResultBundleMetadata
    data_bundle: DataBundle | None = None
    portfolio_paths: dict[str, PortfolioPath] = field(default_factory=dict)
    kpis: dict[str, pd.DataFrame] = field(default_factory=dict)
    risk_estimates: list[RiskEstimate] = field(default_factory=list)
    evt_diagnostics: pd.DataFrame | None = None
    backtest_rows: dict[str, pd.DataFrame] = field(default_factory=dict)
    coverage_summary: pd.DataFrame | None = None
    basel_diagnostic_99: dict[str, Any] | None = None
    risk_contributions: dict[str, pd.DataFrame] = field(default_factory=dict)
    allocation_comparisons: pd.DataFrame | None = None
    stress_results: pd.DataFrame | None = None
