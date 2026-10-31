"""Single analytical pipeline orchestrator for Streamlit views and document exports.

Public interface frozen in D0 for SOLO STEP 9 (D1/D2):
- ``run_pipeline(config=None, *, offline=False) -> PipelineResultBundle``

Note: ``pipeline.py`` never imports Streamlit; UI caching/rendering lives solely under ``app/``.
"""

from __future__ import annotations

from pathlib import Path

from quantedge.config import AppConfig
from quantedge.contracts import PipelineResultBundle


def run_pipeline(
    config: AppConfig | Path | str | None = None,
    *,
    offline: bool = False,
) -> PipelineResultBundle:
    """Execute or retrieve cached end-to-end analytics into a unified ``PipelineResultBundle``.

    Specification (SOLO STEP 9 / D1-D2):
    - Single orchestrator binding data snapshot, portfolio paths, KPIs, VaR/ES/EVT estimates,
      rolling validation, risk budgeting, and stress scenarios with shared ``dataset_id``,
      ``config_hash``, seeds, and ``code_version``.
    """
    from quantedge.final_engine import compute_bundle
    return compute_bundle(config, offline=offline)
