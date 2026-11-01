"""The six decision-room views. Numbers come from the reference or the analytical library."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from quantedge.final_engine import backtest_view, risk_view
from quantedge.kpis import compute_kpis
from quantedge.reference import load_backtest
from quantedge.risk_budget import risk_contributions
from quantedge.stress import run_stress_tests

import qe_theme as ui
from qe_theme import INK, RED, TEAL, pct, pill, pvalue, ratio, usd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = {
    "FINAL_SUBMISSION/01_Investment_Memo.pdf": "Investment memo",
    "FINAL_SUBMISSION/02_Executive_Tear_Sheet.pdf": "One-page tear sheet",
    "FINAL_SUBMISSION/supporting/Recommendation.pdf": "Plain-English recommendation",
}
ROUTES = {
    "Performance": "Performance evidence",
    "Tail risk": "Tail risk evidence",
    "Backtesting": "Model validation",
    "Risk budget & stress": "Crisis and risk budget",
    "Assumptions & Limitations": "Assumptions & limitations",
}
SCENARIOS = list(ui.SCENARIO_LABELS)
SAMPLES = {"full": "Full history", "development": "Development", "selection": "Selection", "evaluation": "Evaluation"}
CHART_CONFIG = {"displayModeBar": False}
HELD_FLOOR = 0.0005  # Optimiser residue below this rounds to 0.0% and is not a position.


@st.cache_data(show_spinner="Estimating risk...")
def selected_risk(_context, portfolio: str, confidence: float, window: int) -> pd.DataFrame:
    """Compare all methods on one exposure, sample, confidence and horizon."""
    cfg, data, ref, _ = _context
    weights = pd.DataFrame(ref["current_weights"]).set_index("ticker")[portfolio]
    return risk_view(data.simple_returns, weights, cfg, confidence, window)[0]


@st.cache_data(show_spinner=False)
def selected_stress(_context, portfolio: str) -> pd.DataFrame:
    """Replay one portfolio's prospective target through every scenario."""
    cfg, data, ref, _ = _context
    weights = pd.DataFrame(ref["current_weights"]).set_index("ticker")[portfolio]
    weights.name = portfolio
    scenarios = [*cfg.stress.historical_scenarios, cfg.stress.hypothetical_scenario]
    frame = run_stress_tests(data.simple_returns, weights, scenarios, nav=cfg.mandate.nav_usd)
    frame.attrs = {}  # Rich path attrs cannot be encoded for display.
    return frame


@st.cache_data(show_spinner=False)
def selected_kpis(_context, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Recompute KPIs for the chosen target dates with the shared library."""
    _, data, _, daily = _context
    chosen = daily[daily.date.between(start, end)]
    benchmark = chosen[chosen.portfolio_id == "benchmark_60_40"].set_index("date").net_return
    tables = []
    for portfolio, group in chosen.groupby("portfolio_id"):
        returns = group.set_index("date").net_return
        if len(returns) >= 2:
            table = compute_kpis(returns, benchmark, data.simple_returns.SPY, data.rf_daily)
            tables.append(table.assign(portfolio_id=portfolio))
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()


@st.cache_data(show_spinner=False)
def selected_backtest(model: str, confidence: float, start: pd.Timestamp, end: pd.Timestamp):
    """Select target dates from a persisted rolling run; forecast history stays intact."""
    rows = load_backtest(model, confidence)
    if rows.date.between(start, end).sum() == 0:
        return rows.iloc[0:0], pd.DataFrame(), {}
    chosen, summary, _ = backtest_view(rows, start, end)
    _, _, basel = backtest_view(load_backtest(model, 0.99), start, end)
    return chosen, summary, basel


def _kpi(ref: dict, period: str, portfolio: str, metric: str) -> float:
    return next(
        row["value"]
        for row in ref["period_kpis"]
        if row["period"] == period and row["portfolio_id"] == portfolio and row["metric"] == metric
    )


def _risk(ref: dict, window: str, model: str, confidence: float) -> dict:
    return next(
        row
        for row in ref["risk_table"]
        if row["window_id"] == window and row["model"] == model and row["confidence"] == confidence
    )


def _stress(ref: dict, portfolio: str, scenario: str) -> dict:
    return next(
        row for row in ref["stress_results"] if row["portfolio_id"] == portfolio and row["scenario_id"] == scenario
    )


def _coverage(ref: dict, period: str, model: str, confidence: float) -> dict:
    return next(
        row
        for row in ref["coverage_summary"]
        if row["period"] == period and row["model"] == model and row["confidence"] == confidence
    )


def _context_value(ref: dict, kind: str, metric: str) -> float:
    return next(row["value"] for row in ref["context"][kind]["min_variance"] if row["metric"] == metric)


def _budget_row(label: str, value: float, budget: float, nav: float, *, daily: bool = True) -> list[str]:
    """Build one comparison row. Loss values and budgets are positive fractions of NAV."""
    gap = value - budget
    tone, text = ("breach", "Above budget") if gap > 0 else ("within", "Within budget")
    excess = usd(gap * nav) if gap > 0 and daily else ("—" if gap <= 0 else pct(gap))
    return [label, pct(value), pct(budget), excess, pill(text, tone)]


def view_header(title: str, question: str, lead: str, conclusion: str, *, warn: bool = False) -> None:
    """Open a view with its question and its conclusion, before the detailed evidence."""
    st.markdown(f"## {title}")
    st.markdown(ui.question(question), unsafe_allow_html=True)
    st.markdown(ui.takeaway(lead, conclusion, warn=warn), unsafe_allow_html=True)


def show_chart(figure, key: str) -> None:
    st.plotly_chart(figure, width="stretch", key=key, config=CHART_CONFIG)


def show_table(*args, **kwargs) -> None:
    st.markdown(ui.html_table(*args, **kwargs), unsafe_allow_html=True)


def download_table(frame: pd.DataFrame, label: str, file_name: str) -> None:
    st.download_button(label, frame.to_csv(index=False), file_name=file_name, mime="text/csv", key=f"csv-{file_name}")


def go_to(view: str) -> None:
    st.session_state["view"] = view


def report_downloads(key_prefix: str) -> None:
    """Offer the current documents from their single published location."""
    columns = st.columns(len(REPORTS))
    for column, (name, label) in zip(columns, REPORTS.items()):
        path = ROOT / name
        with column:
            if path.exists():
                st.download_button(label, path.read_bytes(), file_name=path.name, mime="application/pdf",
                                   width="stretch", key=f"{key_prefix}-{path.name}")
            else:
                st.caption(f"{label} is unavailable: {name} is missing.")




def allocation_chart(weights: pd.Series, key: str, *, labels: dict[str, str] = ui.ASSET_LABELS) -> None:
    """Show held positions by readable name, largest first."""
    held = weights[weights >= HELD_FLOOR].sort_values(ascending=False)
    figure = go.Figure(
        go.Bar(
            x=held.values,
            y=[labels[ticker] for ticker in held.index],
            orientation="h",
            marker_color=TEAL,
            text=[pct(value, 1) for value in held.values],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x:.1%}<extra></extra>",
        )
    )
    figure.update_yaxes(autorange="reversed")
    ui.style_figure(figure, height=66 + 42 * len(held))
    figure.update_yaxes(zeroline=False, showgrid=False)
    figure.update_xaxes(tickformat=".0%", range=[0, max(0.5, float(held.max()) * 1.3)], nticks=4, title="Share of portfolio value")
    figure.update_layout(margin={"t": 8})
    show_chart(figure, key)


def path_chart(paths: pd.DataFrame, column: str):
    """Plot the three paths in a fixed order, with the candidate drawn heavier."""
    figure = px.line(paths, x="date", y=column, color="Portfolio", color_discrete_map=ui.PORTFOLIO_COLORS,
                     category_orders={"Portfolio": list(ui.PORTFOLIO_LABELS.values())})
    figure.update_traces(line={"width": 1.2})
    figure.update_traces(line={"width": 2.2}, selector={"name": ui.PORTFOLIO_LABELS["min_variance"]})
    return figure


def funding_chart(ref: dict, hurdle: float) -> None:
    rows = []
    for period, label in (("development", "Development<br>2007-2016"), ("selection", "Selection<br>2017-2020"),
                          ("evaluation", "Evaluation<br>2021-2026")):
        for portfolio in ui.PORTFOLIO_LABELS:
            rows.append(
                {
                    "Period": label,
                    "Portfolio": ui.PORTFOLIO_LABELS[portfolio],
                    "CAGR": _kpi(ref, period, portfolio, "geometric_annual_return"),
                }
            )
    figure = px.bar(pd.DataFrame(rows), x="Period", y="CAGR", color="Portfolio", barmode="group",
                    color_discrete_map=ui.PORTFOLIO_COLORS)
    figure.add_hline(y=hurdle, line_dash="dash", line_color=INK, line_width=1,
                     annotation_text=f"{pct(hurdle)} proposed hurdle", annotation_position="top left",
                     annotation_font_size=12)
    ui.style_figure(figure, height=320, percent_y=True, y_title="Net annual growth")
    figure.update_xaxes(tickangle=0)
    show_chart(figure, "decision-funding")


def decision_view(context) -> None:
    cfg, _, ref, _ = context
    proposal, limits, nav = ref["proposal"], ref["proposal"]["risk_limits"], cfg.mandate.nav_usd
    hurdle = proposal["required_nominal_return_fraction"]
    spending = proposal["spending_annual_fraction"]
    development = _kpi(ref, "development", "min_variance", "geometric_annual_return")
    selection = _kpi(ref, "selection", "min_variance", "geometric_annual_return")
    evaluation = _kpi(ref, "evaluation", "min_variance", "geometric_annual_return")
    var99 = _risk(ref, "recent", "historical", 0.99)
    full99 = _risk(ref, "full_history", "historical", 0.99)
    income = _context_value(ref, "distribution_income", "ending_trailing_12m_distribution_yield")
    gfc = _stress(ref, "min_variance", "gfc_2007_2009")
    reference_gfc = _stress(ref, "benchmark_60_40", "gfc_2007_2009")
    weights = pd.DataFrame(ref["current_weights"]).set_index("ticker")
    target = weights["min_variance"]
    es_excess = var99["es_usd"] - limits["max_daily_es_99_fraction"] * nav
    drift = ref["diagnostics"]["drift"]

    st.markdown(
        ui.masthead(
            "Serendib University Endowment · USD 10 million · proposed decision",
            "Conditional <em>ADJUST</em>: keep the rule, change the terms",
            "Keep the defensive candidate portfolio, led by US bonds and gold, but do not commit capital until "
            "the committee settles spending, loss budgets and holdings drift.",
        ),
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("### What do we recommend?")
        allocation_chart(target, "decision-allocation")
        st.caption(
            f"Prospective target for the next session, estimated at the {ui.short_date('2026-10-30')} close. These are not "
            "historical holdings, which drifted between monthly rebalances, and this is not a trade instruction."
        )
    with right:
        st.markdown("### Why this decision?")
        st.markdown(
            ui.fact_list(
                [
                    ("Why it is appropriate.", f"Bonds and gold are {pct(target['AGG'] + target['GLD'], 1)} of the target, and it "
                                               "lost less than 60/40 in all three historical crisis replays."),
                    ("Why not accept.", f"Cash income of {pct(income)} does not cover {pct(spending)} proposed spending, and "
                                        f"estimated tail losses sit {usd(es_excess)} above the proposed daily budget."),
                    ("Why not reject.", "It is the only tested allocation inside the proposed target caps, and its tail "
                                        "budget excesses are small and estimated with error."),
                ]
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            ui.takeaway(
                "Most important issue: spending.",
                f"On USD {nav / 1e6:.0f} million, income falls about {usd((spending - income) * nav)} a year short of proposed "
                "spending. That gap needs planned sales, possibly during a drawdown.",
                warn=True,
            ),
            unsafe_allow_html=True,
        )

    columns = st.columns(4)
    columns[0].metric("Proposed return hurdle", pct(hurdle), "Not a forecast", delta_color="off", delta_arrow="off")
    columns[0].caption(
        f"Proposed assumption, per year: {pct(spending)} spending, {pct(proposal['inflation_assumption_annual_fraction'])} "
        f"inflation, {pct(proposal['additional_fee_assumption_annual_fraction'])} fee."
    )
    columns[1].metric("Evaluation CAGR, 2021-2026", pct(evaluation), f"Development was {pct(development)}",
                      delta_color="off", delta_arrow="off")
    columns[1].caption("Historical, per year, 4 Jan 2021 to 30 Oct 2026. Net of 5 bp trading costs, before spending and the extra fee.")
    columns[2].metric("One-day ES at 99%, recent sample", usd(var99["es_usd"]), f"{usd(es_excess)} above budget",
                      delta_color="inverse", delta_arrow="off")
    columns[2].caption("Current estimate at today's target: average loss on the worst 1% of days. Last 1,260 sessions, before costs.")
    columns[3].metric("Ending cash yield", pct(income), f"Proposed spending is {pct(spending)}",
                      delta_color="off", delta_arrow="off")
    columns[3].caption("Historical path, trailing 12 months to 30 Oct 2026. Cash distributions only, per year.")

    left, right = st.columns([1, 1.45], gap="large")
    with left:
        st.markdown("### Read the reports")
        for name, label in REPORTS.items():
            path = ROOT / name
            if path.exists():
                st.download_button(label, path.read_bytes(), file_name=path.name, mime="application/pdf",
                                   width="stretch", key=f"decision-{path.name}")
            else:
                st.caption(f"{label} is unavailable: {name} is missing.")
    with right:
        st.markdown("### Explore the evidence")
        first, second = st.columns(2)
        for index, (view, label) in enumerate(ROUTES.items()):
            (first if index % 2 == 0 else second).button(label, width="stretch", key=f"route-{view}", on_click=go_to, args=(view,))

    st.markdown("### What could go wrong?")
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        rows = [
            _budget_row("One-day VaR 99%, recent 1,260 days", var99["var_loss"], limits["max_daily_var_99_fraction"], nav),
            _budget_row("One-day ES 99%, recent 1,260 days", var99["es_loss"], limits["max_daily_es_99_fraction"], nav),
            _budget_row("One-day ES 99%, full 5,491 days", full99["es_loss"], limits["max_daily_es_99_fraction"], nav),
            _budget_row("GFC replay, deepest fall", -gfc["max_drawdown"], limits["max_drawdown_fraction"], nav, daily=False),
            _budget_row("Worst crisis replay, endpoint", max(-_stress(ref, "min_variance", s)["total_return"] for s in SCENARIOS[:3]),
                        limits["max_historical_scenario_loss_fraction"], nav, daily=False),
        ]
        show_table(["Measure at today's target", "Estimate", "Budget", "Excess", "Status"], rows, numeric=(1, 2, 3), raw=(4,))
        st.caption(
            f"Budgets are team proposals, not client or organiser limits. Daily excess is on USD {nav:,.0f}. "
            "Small excesses are not precise cliffs, but limits are not raised to make the candidate pass."
        )
    with right:
        show_table(
            ["GFC replay", "Endpoint", "Deepest fall", "USD at endpoint"],
            [
                [ui.PORTFOLIO_SHORT["min_variance"], pct(gfc["total_return"]), pct(gfc["max_drawdown"]), usd(-gfc["usd_loss"])],
                [ui.PORTFOLIO_SHORT["benchmark_60_40"], pct(reference_gfc["total_return"]),
                 pct(reference_gfc["max_drawdown"]), usd(-reference_gfc["usd_loss"])],
            ],
            numeric=(1, 2, 3),
        )
        st.caption(
            "Today's target weights bought and held from 9 Oct 2007 to 9 Mar 2009: an ex-post exposure test, not "
            "the strategy's historical record. The endpoint hides the trough, so both are shown."
        )

    st.markdown("### How strong is the evidence?")
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        funding_chart(ref, hurdle)
        st.caption(
            f"The candidate cleared the proposed hurdle in two of three samples and missed it in development "
            f"({pct(development)} against {pct(hurdle)}); selection was {pct(selection)}. Historical, net of trading "
            "costs, before spending and the extra fee. Past growth is evidence of a trade-off, not a return promise."
        )
    with right:
        full = _coverage(ref, "full", "historical", 0.99)
        recent_block = _coverage(ref, "evaluation", "historical", 0.99)
        basel = ref["basel"]["historical"]
        zone_tone = {"green": "within", "yellow": "review", "red": "breach"}[basel["zone"]]
        show_table(
            ["99% VaR check", "Exceptions", "Result"],
            [
                ["Latest 250 sessions", f"{basel['n_exceedances']} against {ratio(basel['expected_exceedances'], 1)}",
                 pill(f"{basel['zone'].capitalize()}, educational", zone_tone)],
                ["Evaluation sample", f"{recent_block['n_exceedances']} against {ratio(recent_block['n_valid'] * 0.01, 1)}",
                 pill("Not rejected", "within")],
                ["Full history", f"{full['n_exceedances']} against {ratio(full['n_valid'] * 0.01, 1)}", pill("Rejected", "breach")],
            ],
            numeric=(1,),
            raw=(2,),
        )
        st.caption(
            "Exceptions are days when the loss passed the forecast made the day before. The model holds up recently but failed "
            "over the full history, when large losses came in clusters. Passing a test is not proof of safety."
        )

    st.markdown("### What should the committee do next?")
    st.markdown(
        ui.action_list(
            [
                ("Spending plan.", f"Cash yield of {pct(income)} does not fund {pct(spending)} spending; planned sales and "
                                   "liquidity need approval."),
                ("Loss budgets.", "Approve explicit limits, then test a feasible redistribution instead of raising them."),
                ("Drift policy.", f"Holdings passed a target cap on {drift['n_breach_sessions']:,} of {drift['n_active_sessions']:,} "
                                  "sessions. Monthly targets are controlled; daily holdings are not."),
            ]
        ),
        unsafe_allow_html=True,
    )
    st.caption("Competition proposal. Assumptions, limitations and review status are documented under Assumptions & Limitations.")
    with st.expander("All target weights and the hurdle arithmetic"):
        show_table(
            ["Fund", *[ui.PORTFOLIO_SHORT[p] for p in ui.PORTFOLIO_LABELS]],
            [[ui.ASSET_LABELS[ticker], *[pct(weights.at[ticker, p]) for p in ui.PORTFOLIO_LABELS]] for ticker in weights.index],
            numeric=(1, 2, 3),
            caption="Target for the next session, estimated at the frozen final close. Not a trade instruction.",
        )
        download_table(weights.reset_index(), "Download target weights (CSV)", "target_weights.csv")
        st.write(
            f"Planning bridge: 1 + R − spending − additional fee = (1 + inflation) × (1 + real growth). At zero real "
            f"growth, {pct(spending)} + {pct(proposal['additional_fee_assumption_annual_fraction'])} "
            f"+ {pct(proposal['inflation_assumption_annual_fraction'])} = {pct(hurdle)}, with deductions on beginning-year NAV. "
            "ETF expenses are already in the returns; the extra fee is a separate proposed mandate cost."
        )


def performance_view(context, portfolio: str, start: pd.Timestamp, end: pd.Timestamp) -> None:
    _, _, ref, daily = context
    chosen = daily[daily.date.between(start, end)]
    if chosen.empty:
        st.markdown("## Performance")
        st.info("No active portfolio sessions fall in this range. Paths start on 5 January 2007, after the 504-session warm-up.")
        return
    table = selected_kpis(context, start, end)
    pivot = table.pivot(index="metric", columns="portfolio_id", values="value") if not table.empty else pd.DataFrame()
    window = f"{ui.short_date(chosen.date.min())} to {ui.short_date(chosen.date.max())}"
    short = {"min_variance": "the candidate rule", "equal_weight": "the equal-weight reference",
             "benchmark_60_40": "the 60/40 reference"}[portfolio]
    if pivot.empty:
        view_header("Performance", "How has it performed?", "Too few sessions.",
                    f"{window} is too short for performance statistics.", warn=True)
    else:
        def value(metric: str, key: str = portfolio) -> str:
            return ui.kpi_value(metric, pivot.at[metric, key])

        conclusion = (f"From {window}, {short} grew {value('geometric_annual_return')} a year with a deepest fall of "
                      f"{value('max_drawdown')}.")
        if portfolio != "benchmark_60_40":
            conclusion += (f" 60/40 grew {value('geometric_annual_return', 'benchmark_60_40')} with a deepest fall of "
                           f"{value('max_drawdown', 'benchmark_60_40')}.")
        view_header("Performance", "How has it performed?", "Conclusion.",
                    conclusion + " Historical results, net of trading costs and before spending or the extra fee.")

    frames = []
    for name, group in chosen.groupby("portfolio_id"):
        returns = group.set_index("date").net_return
        wealth = (1 + returns).cumprod()
        frames.append(
            pd.DataFrame(
                {
                    "date": returns.index,
                    "Wealth": wealth.values,
                    "Drawdown": (wealth / wealth.cummax().clip(lower=1) - 1).values,
                    "Portfolio": ui.PORTFOLIO_LABELS[name],
                }
            )
        )
    paths = pd.concat(frames, ignore_index=True)
    weights = pd.DataFrame(ref["current_weights"]).set_index("ticker")[portfolio]
    left, right = st.columns([1, 1.9], gap="large")
    with left:
        st.markdown("### What does it hold today?")
        allocation_chart(weights, "performance-weights", labels=ui.ASSET_SHORT)
        st.caption(f"{ui.PORTFOLIO_LABELS[portfolio]}: prospective target at the frozen close, not historical holdings.")
    with right:
        st.markdown("### How did 1.00 grow?")
        show_chart(ui.style_figure(path_chart(paths, "Wealth"), height=280, y_title="Value of 1.00 invested"), "performance-wealth")
        st.markdown("### How deep were the falls?")
        figure = path_chart(paths, "Drawdown")
        figure.add_hline(y=-ref["proposal"]["risk_limits"]["max_drawdown_fraction"], line_dash="dash", line_color=RED, line_width=1,
                         annotation_text="Proposed 20% review line", annotation_position="bottom left", annotation_font_size=12)
        show_chart(ui.style_figure(figure, height=220, percent_y=True, y_title="Fall from high").update_layout(showlegend=False),
                   "performance-drawdown")
        st.caption(
            "The same three portfolios and colours as above. Each path starts at 1.00 before the first selected return, so a "
            "fall counts from the start value. These are the strategies' historical paths, with holdings drifting between rebalances."
        )

    if not pivot.empty:
        st.markdown("### Key statistics for the selected dates")
        rows = []
        for metric, meaning in ui.KEY_KPIS.items():
            if metric in pivot.index:
                rows.append([ui.KPI_LABELS[metric], *[ui.kpi_value(metric, pivot.at[metric, p]) if p in pivot.columns else ui.UNAVAILABLE
                                                      for p in ui.PORTFOLIO_LABELS], meaning])
        show_table(["Metric", *[ui.PORTFOLIO_SHORT[p] for p in ui.PORTFOLIO_LABELS], "What it tells you"], rows, numeric=(1, 2, 3))
        with st.expander("All performance statistics"):
            rows = [[label, *[ui.kpi_value(metric, pivot.at[metric, p]) if p in pivot.columns else ui.UNAVAILABLE
                              for p in ui.PORTFOLIO_LABELS]]
                    for metric, label in ui.KPI_LABELS.items() if metric in pivot.index]
            full = pd.DataFrame(rows, columns=["Metric", *[ui.PORTFOLIO_SHORT[p] for p in ui.PORTFOLIO_LABELS]])
            st.dataframe(full, hide_index=True, width="stretch")
            download_table(full, "Download statistics (CSV)", "performance_statistics.csv")
            st.caption(
                "CAPM uses SPY and the versioned DTB3 proxy. Tracking error and information ratio use the monthly 60/40 "
                "path, so they are unavailable for 60/40 against itself. Alpha is in-sample, not proof of persistent skill."
            )

    for kind, title, note in (
        ("distribution_income", "Income context",
         "Cash distributions are already inside adjusted total returns and are never added again. This is the historical "
         "path's yield, not an exact yield on today's target."),
        ("ex_post_real_returns", "Real-return context",
         "Endpoint CPI over common completed months, before spending. CPI is revised ex-post context, not a trading signal, "
         "and this interval is independent of the dates selected above."),
    ):
        with st.expander(f"{title}, full active history"):
            frame = pd.DataFrame(ref["context"][kind][portfolio])
            rows = [
                [row.metric.replace("_", " ").capitalize(), ratio(row.value) if row.unit == "multiple" else pct(row.value)]
                for row in frame.itertuples()
            ]
            show_table(["Measure", "Value"], rows, numeric=(1,))
            st.caption(note)


def tail_risk_view(context, portfolio: str, confidence: float, model: str) -> None:
    cfg, data, ref, _ = context
    nav = cfg.mandate.nav_usd
    st.markdown("## Tail risk")
    st.markdown(ui.question("What could go wrong on a bad day?"), unsafe_allow_html=True)
    window_label = st.radio("Estimation sample", ["Recent 1,260 sessions", "Full history"], horizontal=True)
    window = 1260 if window_label.startswith("Recent") else len(data.simple_returns)
    frame = selected_risk(context, portfolio, confidence, window)
    row = frame[frame.model == model]
    if row.empty:
        st.error("The selected method is not available.")
        return
    chosen = row.iloc[0]
    if pd.notna(chosen.es_loss):
        conclusion = (f"On the worst {1 - confidence:.0%} of days, {ui.MODEL_LABELS[model]} estimates an average one-day loss of "
                      f"{pct(chosen.es_loss)}, or {usd(chosen.es_loss * nav)} on USD {nav / 1e6:.0f} million.")
        normal = frame[frame.model == "parametric_normal"].iloc[0]
        if model != "parametric_normal" and pd.notna(normal.es_loss):
            conclusion += f" The Normal model gives {pct(normal.es_loss)} on the same days and sample."
        if confidence == 0.99:
            budget = ref["proposal"]["risk_limits"]["max_daily_es_99_fraction"]
            conclusion += f" The proposed budget is {pct(budget)}."
        st.markdown(ui.takeaway("Conclusion.", conclusion), unsafe_allow_html=True)
    else:
        st.markdown(ui.takeaway("Not available.", f"{ui.MODEL_LABELS[model]} cannot estimate this confidence level. "
                                                  "The other methods below still can.", warn=True), unsafe_allow_html=True)

    columns = st.columns(4)
    columns[0].metric(f"{confidence:.0%} one-day VaR", pct(chosen.var_loss))
    columns[1].metric(f"{confidence:.0%} one-day ES", pct(chosen.es_loss))
    columns[2].metric("ES in USD on $10M", usd(chosen.es_loss * nav if pd.notna(chosen.es_loss) else None))
    columns[3].metric("Estimation sessions", f"{window:,}")
    st.caption(
        f"VaR: the loss passed on about {1 - confidence:.0%} of days. ES: the average loss on those days. Current estimates at "
        "the prospective target, before costs, as a share of portfolio value. These are not realised returns."
    )
    if pd.notna(chosen.get("reason")) and chosen.get("reason"):
        message = f"{ui.MODEL_LABELS[model]}: {chosen.reason}"
        (st.warning if chosen.status == "unavailable" else st.info)(message)
    if window == 1260:
        st.caption("The recent sample starts on 25 October 2021, so it omits the GFC and COVID-19. Use Full history to include them.")

    rows = []
    focus = None
    for index, item in enumerate(frame.itertuples()):
        tone = {"ok": "within", "warning": "review", "unavailable": "info"}.get(item.status, "info")
        rows.append([ui.MODEL_LABELS.get(item.model, item.model), pct(item.var_loss), pct(item.es_loss),
                     usd(item.var_loss * nav if pd.notna(item.var_loss) else None),
                     usd(item.es_loss * nav if pd.notna(item.es_loss) else None), pill(item.status.capitalize(), tone)])
        if item.model == model:
            focus = index
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        st.markdown(f"### How much do the methods disagree at {confidence:.0%}?")
        show_table(["Method", "VaR", "ES", "VaR USD", "ES USD", "Status"], rows, numeric=(1, 2, 3, 4), raw=(5,), focus=focus)
    with right:
        finite = frame[frame.var_loss.notna()].copy()
        finite["Method"] = finite.model.map(ui.MODEL_SHORT)
        chart = finite.melt(id_vars="Method", value_vars=["var_loss", "es_loss"], var_name="Measure", value_name="Loss")
        chart["Measure"] = chart.Measure.map({"var_loss": "VaR", "es_loss": "ES"})
        figure = px.bar(chart, y="Method", x="Loss", color="Measure", barmode="group", orientation="h",
                        color_discrete_map={"VaR": ui.VAR_COLOR, "ES": ui.ES_COLOR})
        figure.update_yaxes(autorange="reversed")
        ui.style_figure(figure, height=320, x_title="One-day loss")
        figure.update_xaxes(tickformat=".1%", gridcolor=ui.RULE, showgrid=True)
        if confidence == 0.99:
            figure.add_vline(x=ref["proposal"]["risk_limits"]["max_daily_es_99_fraction"], line_dash="dash", line_color=RED, line_width=1,
                             annotation_text="Proposed ES budget", annotation_position="top", annotation_font_size=11)
        show_chart(figure, "tail-comparison")
    st.caption(
        "A gap between Normal and the empirical methods shows how much a thin-tailed assumption can understate the worst days. "
        "Normal Monte Carlo is a sampling approximation of the Normal model, not a fat-tail model. Pure POT is unavailable below "
        "its empirical tail boundary, and the hybrid uses the empirical body there and is labelled separately. Models that cannot "
        "produce a value stay unavailable rather than showing zero."
    )
    export = frame.drop(columns=[c for c in ("diagnostics",) if c in frame.columns]).copy()
    download_table(export, "Download method comparison (CSV)", f"tail_risk_{portfolio}_{confidence:.0%}_{window}.csv".replace("%", "pct"))
    with st.expander("EVT threshold diagnostics, primary portfolio"):
        diagnostics = pd.DataFrame(ref["evt_diagnostics"])
        rows = [
            ["Recent" if d.window_id == "recent" else "Full history", pct(d.candidate_quantile, 1), f"{d.n_exceedances:,}",
             ratio(d.xi, 3), ratio(d.beta * 100, 3), ratio(d.modified_scale * 100, 3), d.status.capitalize()]
            for d in diagnostics.itertuples()
        ]
        show_table(["Sample", "Threshold", "Excesses", "Shape ξ", "Scale β (%)", "Modified scale (%)", "Status"], rows,
                   numeric=(1, 2, 3, 4, 5))
        st.caption("Fitted at the current target. A positive fitted shape alone is not a formal rejection of the Gaussian model.")
    glossary()


def backtesting_view(context, confidence: float, start: pd.Timestamp, end: pd.Timestamp) -> None:
    _, _, ref, _ = context
    st.markdown("## Backtesting")
    st.markdown(ui.question("How strong is the evidence?"), unsafe_allow_html=True)
    model = st.radio("Rolling forecast model", list(ui.ROLLING_LABELS), horizontal=True,
                     format_func=lambda key: ui.ROLLING_LABELS[key])
    chosen, summary, basel = selected_backtest(model, confidence, start, end)
    if chosen.empty:
        st.info("No forecast targets fall in this range. Rolling targets run from 5 January 2007 to 30 October 2026.")
        return
    stats = summary.iloc[0]
    expected = (1 - confidence) * stats.n_valid
    frequency = "not rejected" if pd.notna(stats.p_uc) and stats.p_uc >= 0.05 else ("rejected" if pd.notna(stats.p_uc) else "unavailable")
    clustering = "not rejected" if pd.notna(stats.p_ind) and stats.p_ind >= 0.05 else ("rejected" if pd.notna(stats.p_ind) else "unavailable")
    st.markdown(
        ui.takeaway(
            "Conclusion.",
            f"Over the selected dates the {ui.ROLLING_LABELS[model]} {confidence:.0%} forecast was passed on "
            f"{int(stats.n_exceedances):,} of {int(stats.n_valid):,} days, against {expected:,.1f} expected. At the 5% level the "
            f"frequency test is {frequency} and the clustering test is {clustering}. Not being rejected is not proof of safety.",
            warn="rejected" in (frequency, clustering),
        ),
        unsafe_allow_html=True,
    )
    columns = st.columns(4)
    columns[0].metric("Exceptions / sessions", f"{int(stats.n_exceedances):,} / {int(stats.n_valid):,}",
                      f"Expected {expected:,.1f}", delta_color="off", delta_arrow="off")
    columns[1].metric("Kupiec p (frequency)", pvalue(stats.p_uc))
    columns[2].metric("Christoffersen p (clustering)", pvalue(stats.p_ind))
    columns[3].metric("Conditional coverage p", pvalue(stats.p_cc))
    st.caption("Small p-values reject the model at that test. A large p-value is not proof of future safety, and sparse samples have little power.")

    st.markdown("### Did losses stay inside the forecast?")
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=chosen.date, y=chosen.realized_loss, name="Realised gross loss", line={"color": ui.SLATE, "width": 0.8}))
    figure.add_trace(go.Scatter(x=chosen.date, y=chosen.forecast_var, name=f"{confidence:.0%} VaR forecast", line={"color": ui.VAR_COLOR, "width": 1.4}))
    breaches = chosen[chosen.exceedance.eq(True)]
    figure.add_trace(go.Scatter(x=breaches.date, y=breaches.realized_loss, name="Exception", mode="markers",
                                marker={"color": RED, "size": 5}))
    show_chart(ui.style_figure(figure, height=330, percent_y=True, y_title="One-day loss, share of value"), "backtest-chart")
    st.caption(
        "Each forecast uses the prior 500 sessions and the holdings known before that day, then meets the next realised loss. "
        "Red dots are exceptions. Clusters of dots mean large losses arrived together, which the forecast was slow to absorb. "
        "Only the primary rule has rolling results, for the Historical and Normal models."
    )

    st.markdown("### Educational Basel traffic light")
    if basel.get("status") == "ok":
        zone = basel["zone"]
        tone = {"green": "within", "yellow": "review", "red": "breach"}[zone]
        show_table(
            ["Scope", "Block", "Exceptions", "Expected", "Zone"],
            [["99% / 250 sessions", f"{ui.short_date(basel['block_start'])} to {ui.short_date(basel['block_end'])}",
              str(basel["n_exceedances"]), ratio(basel["expected_exceedances"], 1), pill(zone.capitalize(), tone)]],
            numeric=(2, 3),
            raw=(4,),
        )
    else:
        st.info(f"Unavailable for this range: {basel.get('reason') or 'it needs 250 valid sessions at 99%.'}")
    st.caption(
        "Always the final 250 valid 99% sessions in the selected range, whatever confidence is chosen above. It is a "
        "teaching diagnostic, not regulatory approval. A green recent light does not erase earlier failures: the full-history "
        "Historical 99% model still rejects both frequency and independence."
    )
    with st.expander(f"All frozen samples at {confidence:.0%}"):
        table = pd.DataFrame(
            [
                {
                    "Sample": SAMPLES[row["period"]],
                    "Model": ui.ROLLING_LABELS[row["model"]],
                    "Sessions": row["n_valid"],
                    "Exceptions": row["n_exceedances"],
                    "Expected": round(row["n_valid"] * (1 - confidence), 1),
                    "Kupiec p": pvalue(row["p_uc"]),
                    "Christoffersen p": pvalue(row["p_ind"]),
                    "Conditional coverage p": pvalue(row["p_cc"]),
                }
                for row in ref["coverage_summary"]
                if row["confidence"] == confidence and row["model"] in ui.ROLLING_LABELS and row["period"] in SAMPLES
            ]
        )
        st.dataframe(table, hide_index=True, width="stretch")
        download_table(table, "Download sample results (CSV)", f"coverage_{confidence:.0%}.csv".replace("%", "pct"))
    st.download_button("Download selected forecast rows (CSV)", chosen.to_csv(index=False), file_name="selected_backtest.csv", key="backtest-rows")


def risk_budget_view(context, portfolio: str, confidence: float) -> None:
    cfg, data, ref, _ = context
    weights = pd.DataFrame(ref["current_weights"]).set_index("ticker")[portfolio]
    st.markdown("## Risk budget and stress")
    st.markdown(ui.question("Where does risk come from in a crisis?"), unsafe_allow_html=True)
    method = st.selectbox("Risk decomposition", list(ui.EULER_LABELS), format_func=lambda key: ui.EULER_LABELS[key])
    frame = risk_contributions(data.simple_returns.iloc[-1260:], weights, confidence=confidence, method=method)
    stress = selected_stress(context, portfolio)
    reference = selected_stress(context, "benchmark_60_40")
    top = frame.loc[frame.pct_contribution.idxmax()]
    gfc = stress[stress.scenario_id == "gfc_2007_2009"].iloc[0]
    st.markdown(
        ui.takeaway(
            "Conclusion.",
            f"{ui.ASSET_SHORT[top.ticker]} is {pct(top.weight, 1)} of capital but {pct(top.pct_contribution, 1)} of "
            f"{ui.EULER_LABELS[method]} at {confidence:.0%}, so weight alone understates where risk sits. Replayed through the GFC, "
            f"today's target ends at {pct(gfc.total_return)} after a deepest fall of {pct(gfc.max_drawdown)}.",
        ),
        unsafe_allow_html=True,
    )
    share_label = f"Share of {ui.EULER_LABELS[method]}"
    held = frame[frame.weight >= HELD_FLOOR].copy()
    held["Fund"] = held.ticker.map(ui.ASSET_SHORT)
    chart = held.melt(id_vars="Fund", value_vars=["weight", "pct_contribution"], var_name="Measure", value_name="Share")
    chart["Measure"] = chart.Measure.map({"weight": "Target weight", "pct_contribution": share_label})
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.markdown(f"### Is risk spread like capital? ({confidence:.0%})")
        figure = px.bar(chart, x="Fund", y="Share", color="Measure", barmode="group",
                        color_discrete_map={"Target weight": ui.WEIGHT_COLOR, share_label: ui.RISK_SHARE_COLOR})
        show_chart(ui.style_figure(figure, height=320, percent_y=True, y_title="Share of total"), "risk-share")
        st.caption("Held funds only, at the prospective target on the recent 1,260 sessions. Where the amber bar is taller, a fund adds more risk than capital.")
    with right:
        st.markdown("### Marginal and component risk")
        rows = [[ui.ASSET_SHORT[row.ticker], pct(row.weight), pct(row.marginal_risk), pct(row.component_risk), pct(row.pct_contribution, 1)]
                for row in frame.itertuples()]
        show_table(["Fund", "Weight", "Marginal", "Component", "Share"], rows, numeric=(1, 2, 3, 4))
        st.caption(f"Components sum to total risk of {pct(frame.total_risk.iloc[0])} on the recent 1,260 sessions. Signed Euler shares: "
                   "a negative value is a local hedge in this sample, not guaranteed protection.")
        download_table(frame.drop(columns=[c for c in ("note",) if c in frame.columns]), "Download risk contributions (CSV)",
                       f"risk_contributions_{method}.csv")

    st.markdown("### How would today's target fare in a crisis?")
    bars = []
    pairs = [(portfolio, stress)] if portfolio == "benchmark_60_40" else [(portfolio, stress), ("benchmark_60_40", reference)]
    for key, source in pairs:
        for scenario in SCENARIOS:
            item = source[source.scenario_id == scenario].iloc[0]
            bars.append({"Scenario": ui.SCENARIO_LABELS[scenario], "Portfolio": ui.PORTFOLIO_LABELS[key], "Deepest fall": item.max_drawdown})
    figure = px.bar(pd.DataFrame(bars), x="Scenario", y="Deepest fall", color="Portfolio", barmode="group",
                    color_discrete_map=ui.PORTFOLIO_COLORS)
    figure.add_hline(y=-ref["proposal"]["risk_limits"]["max_drawdown_fraction"], line_dash="dash", line_color=RED, line_width=1,
                     annotation_text="Proposed 20% review line", annotation_position="bottom right", annotation_font_size=12)
    ui.style_figure(figure, height=320, percent_y=True, y_title="Deepest fall within scenario")
    figure.update_xaxes(tickangle=0)
    show_chart(figure, "stress-drawdown")
    rows = []
    for scenario in SCENARIOS:
        item = stress[stress.scenario_id == scenario].iloc[0]
        base = reference[reference.scenario_id == scenario].iloc[0]
        rows.append([ui.SCENARIO_LABELS[scenario], pct(item.total_return), pct(item.max_drawdown), pct(item.worst_day_return),
                     usd(-item.usd_loss), pct(base.total_return), pct(base.max_drawdown)])
    show_table(["Scenario", "Endpoint return", "Max drawdown", "Worst day", "USD at endpoint", "60/40 endpoint", "60/40 drawdown"],
               rows, numeric=(1, 2, 3, 4, 5, 6),
               caption=f"{ui.PORTFOLIO_LABELS[portfolio]}, prospective target, on USD {cfg.mandate.nav_usd:,.0f}.")
    st.caption(
        "Historical rows buy and hold the same target through actual return paths: ex-post exposure replays, not investable "
        "records. The hypothetical joint shock is one step with no assigned duration or probability, so it is not comparable with daily ES."
    )
    with st.expander("Feasibility against proposed limits"):
        rows = []
        for item in ref["allocation_comparisons"]:
            feasible = pill("Feasible", "within") if item["constraint_feasible"] else pill("Violates caps", "breach")
            limits = pill("Within limits", "within") if item["risk_limits_met"] else pill("Above limits", "breach")
            rows.append([ui.PORTFOLIO_LABELS[item["candidate_id"]], pct(item["var_loss"]), pct(item["es_loss"]), feasible, limits])
        show_table(["Candidate", "VaR 99%", "ES 99%", "Target caps", "Proposed tail limits"], rows, numeric=(1, 2), raw=(3, 4))
        st.caption("Historical simulation on the recent 1,260 sessions. References are not required to meet the candidate's caps.")
    with st.expander("Monitoring triggers"):
        rows = [[m["metric"], str(m["threshold"]), m["action"]] for m in ref["proposal"]["monitoring"]]
        show_table(["Metric", "Threshold", "Proposed response"], rows, numeric=(1,))


def glossary() -> None:
    with st.expander("Plain-English glossary"):
        for term, meaning in ui.GLOSSARY.items():
            st.markdown(f"**{term}.** {meaning}")


def assumptions_view(context) -> None:
    _, _, ref, _ = context
    view_header(
        "Assumptions & Limitations",
        "What does this not capture?",
        "In short.",
        "The mandate terms are proposals, the evidence is historical, and no model here guarantees protection. "
        "Read these limits alongside every number in this app.",
    )
    groups = {
        "The mandate is proposed, not supplied": [
            "The ten-year horizon, 4% spending, 2.5% inflation, 0.25% extra fee and every risk budget are team proposals. Neither the organiser nor a university gave them.",
            "The 6.75% hurdle is a planning sum, not a forecast. We state no probability of achieving it.",
        ],
        "History is not a promise": [
            "Past growth, alpha and crisis replays do not predict future results. Capital protection and sustainable spending are not guaranteed.",
            "Prior whole-history asset analysis and fixed-exposure stress work were seen before the rule was registered, so this is registered-rule evaluation, not a pristine blinded experiment.",
            "Recent risk estimates omit the GFC and COVID-19. Full-history estimates mix very different regimes.",
        ],
        "Models have boundaries": [
            "Normal models assume thin tails, and Monte Carlo here samples that same Normal model. It does not add fat tails.",
            "EVT assumes independent exceedances from a stable tail, which clustered markets violate. Pure POT is unavailable below its tail boundary, and a positive fitted shape alone does not reject normality.",
            "Rolling validation covers only the Historical and Normal models, on the primary rule. Rolling Monte Carlo and EVT results are not claimed.",
            "Backtests have low power with few expected exceptions. The Basel light is a teaching diagnostic, not approval.",
        ],
        "The portfolio is simplified": [
            "Monthly targets respect the caps, but holdings drift between rebalances. Daily compliance is not claimed.",
            "Costs are a flat 5 bp of traded weight at closing prices. Market impact, intraday slippage and taxes are not modelled.",
            "Liabilities, cash-flow timing, off-universe hedges and cash reserves are not modelled.",
            "Bonds can lose value when rates rise, gold pays no contractual income, and XLE's position is an optimiser outcome, not a macro forecast.",
        ],
        "The data has known limits": [
            "Prices come from one provider and were not independently checked for the whole history.",
            "Risk-free evidence is day-level. Exact historical release hours are unverified, some dates are inferred, and sparse early history uses a labelled calendar fallback. Dividing the DTB3 quote by 252 is a proxy, not a realised bill return.",
            "CPI is revised, used only as ex-post context. October 2025 CPI is absent and October 2026 was unreleased.",
            "Foreign-market ETFs close with US trading, so their daily correlations reflect non-synchronous underlying markets.",
        ],
    }
    left, right = st.columns(2, gap="large")
    for index, (title, items) in enumerate(groups.items()):
        with left if index % 2 == 0 else right:
            st.markdown(f"### {title}")
            for item in items:
                st.markdown(f"- {item}")

    st.markdown("### Review status")
    show_table(
        ["Item", "Status", "Meaning"],
        [
            ["AI-assisted verification", pill("Recorded", "within"), "Automated and AI checks are listed in audit/presentation_review/."],
            ["Independent human validation", pill("Pending", "review"), "A team member must recompute and record it. AI cannot complete this."],
            ["Team decision", pill("Pending", "review"), "The team must evaluate and own the recommendation."],
            ["University committee approval", pill("Not applicable yet", "info"), "This is a competition proposal. No real committee has approved it."],
        ],
        raw=(1,),
    )
    st.markdown("### Reports")
    report_downloads("evidence")
    st.markdown("### Evidence and audit detail")
    glossary()
    with st.expander("Result bundle and proposal provenance"):
        st.json(ref["metadata"])
        st.json(ref["proposal"])
    for name, label in (("AI_DISCLOSURE.md", "AI disclosure"), ("FINAL_SUBMISSION/COMPLIANCE_MATRIX.md", "Requirement trace"),
                        ("FINAL_SUBMISSION/supporting/Human_Review_Status.md", "Human review status")):
        path = ROOT / name
        if path.exists():
            with st.expander(label):
                st.markdown(path.read_text(encoding="utf-8"))
    st.download_button("Download source-of-truth JSON", (ROOT / "results/final/reference.json").read_bytes(),
                       file_name="reference.json", mime="application/json", key="evidence-json")
