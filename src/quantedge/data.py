"""Market-data snapshot acquisition, caching, and quality-flagging adapter (SOLO STEP 2 / A1).

Public interface frozen in D0:
- ``load_data(config, *, offline=False) -> DataBundle``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantedge.config import AppConfig
from quantedge.contracts import DataBundle


def load_data(
    config: AppConfig | dict[str, Any] | Path | str,
    *,
    offline: bool = False,
) -> DataBundle:
    """Load or build the shared market-data snapshot and quality flags.

    Specification (implemented in SOLO STEP 2 / milestone A1):
    - Fetch adjusted close prices for ``SPY, EFA, EEM, AGG, GLD, XLE, XLK`` via
      ``yfinance`` (``auto_adjust=True``) from ``2005-01-01`` and FRED ``DTB3``.
    - Persist raw observations, actual bounds, SHA-256 checksums, and manifest.
    - Never forward-fill ETF prices by default or backfill missing initial RF quotes.
    - When ``offline=True`` or network retrieval fails, return a matching cached
      snapshot with explicit cache metadata, or fail clearly when no valid cache exists.
    """
    raise NotImplementedError(
        "load_data is a D0 interface stub scheduled for implementation in SOLO STEP 2 (A1)."
    )
