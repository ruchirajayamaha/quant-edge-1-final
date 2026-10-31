"""Offline endowment decision room. All numbers use the shared analytical engine."""
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from quantedge.config import load_config
from quantedge.data import load_data
from quantedge.reference import load_reference

import qe_theme as ui
import qe_views as views

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ["Decision", "Performance", "Tail risk", "Backtesting", "Risk budget & stress", "Assumptions & Limitations"]


@st.cache_resource(show_spinner=False)
def source_data():
    """Load the frozen snapshot and verified reference once per server."""
    cfg = load_config()
    daily = pd.read_csv(ROOT / "results/final/daily_performance.csv", parse_dates=["date"])
    return cfg, load_data(cfg, offline=True), load_reference(), daily


def main() -> None:
    st.set_page_config(page_title="Quant Edge | Endowment Decision Room", layout="wide")
    st.markdown(ui.css(), unsafe_allow_html=True)
    try:
        context = source_data()
    except (OSError, ValueError) as exc:
        st.error(f"Verified reference unavailable: {exc}")
        st.code("python scripts/build_final_results.py")
        st.stop()
    _, _, ref, daily = context

    st.sidebar.markdown("## Decision room")
    st.sidebar.caption("Serendib University Endowment · USD 10 million")
    view = st.sidebar.radio("View", VIEWS)
    portfolio = st.sidebar.selectbox("Portfolio", list(ui.PORTFOLIO_LABELS), format_func=lambda key: ui.PORTFOLIO_LABELS[key])
    confidence = st.sidebar.select_slider("Confidence", options=[0.90, 0.95, 0.99], value=0.99, format_func=lambda x: f"{x:.0%}")
    model = st.sidebar.selectbox("Risk method", list(ui.MODEL_LABELS), format_func=lambda key: ui.MODEL_LABELS[key])
    limits = (daily.date.min().date(), daily.date.max().date())
    dates = st.sidebar.date_input(
        "Performance and backtest target dates",
        value=(pd.Timestamp("2021-01-04").date(), limits[1]),
        min_value=limits[0],
        max_value=limits[1],
    )
    st.sidebar.caption(
        "Dates select performance and backtest targets; earlier training history stays intact. Current risk and stress "
        "use the prospective target at the frozen final close, not historical holdings."
    )
    with st.sidebar.expander("Data provenance"):
        st.caption(
            f"Bundle {ref['metadata']['bundle_id']}, "
            f"dataset {ref['metadata']['dataset_id']}. Data frozen at 30 October 2026. Offline; no market downloads."
        )
    if len(dates) != 2:
        st.info("Select both a start and an end date.")
        st.stop()
    start, end = map(pd.Timestamp, dates)

    st.markdown(
        ui.status_strip(
            [
                ("Status", "Conditional ADJUST, team proposal"),
                ("Data", "frozen 30 Oct 2026"),
            ]
        ),
        unsafe_allow_html=True,
    )
    if portfolio != "min_variance" and view != "Decision":
        st.info(f"{ui.PORTFOLIO_LABELS[portfolio]} is a comparison. It does not have to satisfy the candidate's target caps.")

    if view == "Decision":
        views.decision_view(context)
    elif view == "Performance":
        views.performance_view(context, portfolio, start, end)
    elif view == "Tail risk":
        views.tail_risk_view(context, portfolio, confidence, model)
    elif view == "Backtesting":
        views.backtesting_view(context, confidence, start, end)
    elif view == "Risk budget & stress":
        views.risk_budget_view(context, portfolio, confidence)
    else:
        views.assumptions_view(context)


if __name__ == "__main__":
    main()
