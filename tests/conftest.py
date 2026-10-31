"""Shared pytest fixtures for Quant Edge 1.0 offline unit and integration tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantedge import AppConfig, CANONICAL_TICKERS, load_config


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the absolute path to the project repository root."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def baseline_config(repo_root: Path) -> AppConfig:
    """Load the baseline ``config.yaml`` once per test session."""
    return load_config(repo_root / "config.yaml")


@pytest.fixture()
def synthetic_asset_returns() -> pd.DataFrame:
    """Small deterministic synthetic return frame for offline interface/stub checks only."""
    dates = pd.bdate_range("2024-01-02", periods=5)
    data = {
        ticker: [0.001 * (idx + 1) * (-1 if t_idx % 2 else 1) for idx in range(5)]
        for t_idx, ticker in enumerate(CANONICAL_TICKERS)
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture()
def equal_canonical_weights() -> pd.Series:
    """Equal-weight canonical ticker Series summing to 1.0 for stub call verification."""
    w = 1.0 / len(CANONICAL_TICKERS)
    return pd.Series({ticker: w for ticker in CANONICAL_TICKERS}, dtype=float)
