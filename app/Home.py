"""Quant Edge 1.0 Streamlit entrypoint (SOLO STEP 1 / D0 baseline stub).

Launch after setup via:
    streamlit run app/Home.py

Full six-view dashboard integration is scheduled for SOLO STEP 9 (D1/D2) after
Steps 2-8 analytical modules and market-data snapshot are implemented. No fake or
synthetic portfolio metrics are rendered here.
"""

from __future__ import annotations

import streamlit as st

from quantedge import (
    CANONICAL_TICKERS,
    CONTRACT_SCHEMA_VERSION,
    MANDATE_NAV_USD,
    __version__,
    list_provisional_items,
    load_config,
)


def main() -> None:
    """Render honest Step 1 baseline status and provisional config diagnostics."""
    st.set_page_config(
        page_title="Quant Edge 1.0 — Endowment Risk & Allocation",
        layout="wide",
    )
    st.title("Quant Edge 1.0 — Conservative USD 10M University Endowment")
    st.info(
        "SOLO STEP 1 (D0 Project Setup) baseline is active. "
        "Data acquisition (Step 2), analytics (Steps 3–8), and the six interactive "
        "dashboard views (Step 9) are not yet executed. No synthetic or fabricated "
        "portfolio figures are displayed."
    )

    cfg = load_config()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Package Version", __version__)
    col2.metric("Contract Schema", CONTRACT_SCHEMA_VERSION)
    col3.metric("Mandate Scale (USD)", f"${MANDATE_NAV_USD:,.0f}")
    col4.metric("Universe Count", f"{len(CANONICAL_TICKERS)} ETFs")

    st.subheader("Canonical Allocation Universe")
    st.code(", ".join(CANONICAL_TICKERS), language="text")

    st.subheader("Configuration Provenance & Provisional Governance Items")
    st.caption(f"Deterministic Config SHA-256: `{cfg.config_hash}`")
    provisional_rows = [
        {
            "Field": item.field_path,
            "Status": item.status,
            "Governance Note": item.note,
        }
        for item in list_provisional_items(cfg)
    ]
    st.table(provisional_rows)


if __name__ == "__main__":
    main()
