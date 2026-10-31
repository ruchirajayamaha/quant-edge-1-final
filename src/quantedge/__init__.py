"""Quant Edge 1.0 analytical library package.

Exposes shared typed contracts, constants, and configuration helpers frozen in
SOLO STEP 1 (milestone D0). No module in ``quantedge`` imports Streamlit.
"""

from __future__ import annotations

from quantedge.config import (
    AppConfig,
    DEFAULT_CONFIG_PATH,
    ProvisionalItem,
    compute_config_hash,
    list_provisional_items,
    load_config,
)
from quantedge.contracts import (
    BACKTEST_COLUMNS,
    CANONICAL_TICKERS,
    CONTRACT_SCHEMA_VERSION,
    CORE_RISK_MODELS,
    COVERAGE_TEST_COLUMNS,
    DEFENSIVE_TICKERS,
    EQUITY_TICKERS,
    KPI_COLUMNS,
    MANDATE_NAV_USD,
    MANDATORY_COMPARISON_CONFIDENCES,
    MARKET_PROXY_TICKER,
    QUALITY_FLAG_COLUMNS,
    RISK_CONTRIBUTION_COLUMNS,
    STRESS_SCENARIO_COLUMNS,
    SUPPORTED_CONFIDENCE_LEVELS,
    DataBundle,
    DataManifest,
    PipelineResultBundle,
    PortfolioConstraints,
    PortfolioPath,
    ResultBundleMetadata,
    RiskEstimate,
    RiskForecastFn,
    StrategySpec,
    StressScenarioSpec,
)

__version__: str = "0.1.0"

__all__ = [
    "__version__",
    "AppConfig",
    "BACKTEST_COLUMNS",
    "CANONICAL_TICKERS",
    "CONTRACT_SCHEMA_VERSION",
    "CORE_RISK_MODELS",
    "COVERAGE_TEST_COLUMNS",
    "DEFAULT_CONFIG_PATH",
    "DEFENSIVE_TICKERS",
    "DataBundle",
    "DataManifest",
    "EQUITY_TICKERS",
    "KPI_COLUMNS",
    "MANDATE_NAV_USD",
    "MANDATORY_COMPARISON_CONFIDENCES",
    "MARKET_PROXY_TICKER",
    "PipelineResultBundle",
    "PortfolioConstraints",
    "PortfolioPath",
    "ProvisionalItem",
    "QUALITY_FLAG_COLUMNS",
    "RISK_CONTRIBUTION_COLUMNS",
    "ResultBundleMetadata",
    "RiskEstimate",
    "RiskForecastFn",
    "STRESS_SCENARIO_COLUMNS",
    "SUPPORTED_CONFIDENCE_LEVELS",
    "StrategySpec",
    "StressScenarioSpec",
    "compute_config_hash",
    "list_provisional_items",
    "load_config",
]
