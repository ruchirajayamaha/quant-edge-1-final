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
from qe_theme import INK, MUTED, RED, TEAL, pct, pill, pvalue, ratio, usd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = {
    "investment_memo.pdf": "Investment memo",
    "tear_sheet.pdf": "One-page tear sheet",
    "recommendation.pdf": "Plain-English recommendation",
}
SCENARIOS = list(ui.SCENARIO_LABELS)


@st.cache_data(show_spinner=False)
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


def _context_value(ref: dict, kind: str, metric: str) -> float:
    return next(row["value"] for row in ref["context"][kind]["min_variance"] if row["metric"] == metric)


def _budget_row(label: str, basis: str, value: float, budget: float, nav: float, *, daily: bool = True) -> list[str]:
    """Build one comparison row. Loss values and budgets are positive fractions of NAV."""
    gap = value - budget
    tone, text = ("breach", "Above budget") if gap > 0 else ("within", "Within budget")
    excess = usd(gap * nav) if gap > 0 and daily else ("—" if gap <= 0 else pct(gap))
    return [label, basis, pct(value), pct(budget), excess, pill(text, tone)]


def report_downloads(key_prefix: str) -> None:
    """Offer the current documents from their single published location."""
    columns = st.columns(len(REPORTS))
    for column, (name, label) in zip(columns, REPORTS.items()):
        path = ROOT / "submission" / name
        with column:
            if path.exists():
                st.download_button(label, path.read_bytes(), file_name=name, mime="application/pdf",
                                   width="stretch", key=f"{key_prefix}-{name}")
            else:
                st.caption(f"{label} is unavailable: {name} is missing from submission/.")


def decision_view(context) -> None:
    cfg, _, ref, _ = context
    proposal, limits, nav = ref["proposal"], ref["proposal"]["risk_limits"], cfg.mandate.nav_usd
    hurdle = proposal["required_nominal_return_fraction"]
    development = _kpi(ref, "development", "min_variance", "geometric_annual_return")
    selection = _kpi(ref, "selection", "min_variance", "geometric_annual_return")
    evaluation = _kpi(ref, "evaluation", "min_variance", "geometric_annual_return")
    var99 = _risk(ref, "recent", "historical", 0.99)
    full99 = _risk(ref, "full_history", "historical", 0.99)
    income = _context_value(ref, "distribution_income", "ending_trailing_12m_distribution_yield")
    gfc = _stress(ref, "min_variance", "gfc_2007_2009")
    reference_gfc = _stress(ref, "benchmark_60_40", "gfc_2007_2009")

    st.markdown(
        ui.masthead(
            "Investment committee brief · proposed decision",
            "Conditional <em>ADJUST</em>: keep the rule, change the terms",
            "Retain the constrained minimum-variance rule as a candidate, but do not commit capital yet. "
            "It missed the planning hurdle in one of three periods, its current tail risk sits marginally "
            "above the proposed budgets, and its cash income does not cover proposed spending.",
        ),
        unsafe_allow_html=True,
    )
    columns = st.columns(4)
    columns[0].metric("Proposed return hurdle", pct(hurdle), "Not a forecast", delta_color="off", delta_arrow="off")
    columns[1].metric("Evaluation CAGR, 2021-2026", pct(evaluation), f"Development was {pct(development)}",
                      delta_color="off", delta_arrow="off")
    columns[2].metric(
        "One-day ES at 99%, recent sample",
        usd(var99["es_usd"]),
        f"{usd(var99['es_usd'] - limits['max_daily_es_99_fraction'] * nav)} above budget",
        delta_color="inverse",
        delta_arrow="off",
    )
    columns[3].metric("Ending cash yield", pct(income), f"Proposed spending is {pct(proposal['spending_annual_fraction'])}",
                      delta_color="off", delta_arrow="off")

    left, right = st.columns([1.02, 1], gap="large")
    with left:
        st.markdown("### The funding trade-off")
        rows = []
        for period, label in (("development", "Development"), ("selection", "Selection"), ("evaluation", "Evaluation")):
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
        st.plotly_chart(ui.style_figure(figure, height=300, percent_y=True), width="stretch", key="decision-funding")
        st.caption(
            f"Net of 5 bp trading costs, before spending and the extra fee. The candidate cleared the hurdle in two of "
            f"three periods and missed it in development ({pct(development)} against {pct(hurdle)}); selection was "
            f"{pct(selection)}. Past growth is evidence of a trade-off, not a return promise."
        )
    with right:
        st.markdown("### Measured against the proposed budgets")
        rows = [
            _budget_row("VaR 99%, recent", "1 day, 1,260 sessions", var99["var_loss"], limits["max_daily_var_99_fraction"], nav),
            _budget_row("ES 99%, recent", "1 day, 1,260 sessions", var99["es_loss"], limits["max_daily_es_99_fraction"], nav),
            _budget_row("ES 99%, full history", "1 day, 5,491 sessions", full99["es_loss"], limits["max_daily_es_99_fraction"], nav),
            _budget_row("GFC drawdown", "Current-target replay", -gfc["max_drawdown"], limits["max_drawdown_fraction"], nav, daily=False),
            _budget_row("Worst crisis endpoint", "Current-target replay",
                        max(-_stress(ref, "min_variance", s)["total_return"] for s in SCENARIOS[:3]),
                        limits["max_historical_scenario_loss_fraction"], nav, daily=False),
        ]
        st.markdown(
            ui.html_table(["Measure", "Basis", "Estimate", "Budget", "Excess", "Status"], rows,
                          numeric=(2, 3, 4), raw=(5,)),
            unsafe_allow_html=True,
        )
        st.caption(
            f"Budgets are team proposals, not client or organiser limits. Daily excess is on USD {nav:,.0f}. "
            "Small excesses are not precise cliffs, but limits are not raised to make the candidate pass."
        )

    left, right = st.columns([1.02, 1], gap="large")
    with left:
        st.markdown("### A crisis in two numbers")
        st.markdown(
            ui.html_table(
                ["Global Financial Crisis replay", "Endpoint return", "Deepest drawdown", "USD at endpoint"],
                [
                    [ui.PORTFOLIO_SHORT["min_variance"], pct(gfc["total_return"]), pct(gfc["max_drawdown"]), usd(-gfc["usd_loss"])],
                    [ui.PORTFOLIO_SHORT["benchmark_60_40"], pct(reference_gfc["total_return"]),
                     pct(reference_gfc["max_drawdown"]), usd(-reference_gfc["usd_loss"])],
                ],
                numeric=(1, 2, 3),
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            "Today's target weights bought and held from 9 Oct 2007 to 9 Mar 2009: an ex-post exposure test, not "
            "the strategy's historical record. The endpoint hides the trough, so both are shown."
        )
    with right:
        st.markdown("### What needs adjusting")
        st.markdown(
            ui.action_list(
                [
                    ("Spending plan.", f"Cash yield of {pct(income)} does not fund {pct(proposal['spending_annual_fraction'])} spending; "
                                       "planned sales and liquidity need approval."),
                    ("Loss budgets.", "Approve explicit limits, then test a feasible redistribution instead of raising them."),
                    ("Drift policy.", f"Holdings passed a target cap on {ref['diagnostics']['drift']['n_breach_sessions']:,} of "
                                      f"{ref['diagnostics']['drift']['n_active_sessions']:,} sessions. Monthly targets are controlled; daily holdings are not."),
                    ("Human review.", "The team must validate and own this proposal before it is a recommendation."),
                ]
            ),
            unsafe_allow_html=True,
        )

    st.markdown("### Reports")
    report_downloads("decision")
    st.caption(
        "Proposed by the team under the competition brief. No university committee has approved it, and independent "
        "human validation is still pending."
    )
    with st.expander("Prospective target weights and mandate arithmetic"):
        weights = pd.DataFrame(ref["current_weights"]).set_index("ticker")
        st.markdown(
            ui.html_table(
                ["ETF", *[ui.PORTFOLIO_SHORT[p] for p in ui.PORTFOLIO_LABELS]],
                [[ticker, *[pct(weights.at[ticker, p]) for p in ui.PORTFOLIO_LABELS]] for ticker in weights.index],
                numeric=(1, 2, 3),
                caption="Target for the next session, estimated at the frozen final close. Not a trade instruction.",
            ),
            unsafe_allow_html=True,
        )
        st.write(
            f"Planning bridge: 1 + R − spending − additional fee = (1 + inflation) × (1 + real growth). At zero real "
            f"growth, {pct(proposal['spending_annual_fraction'])} + {pct(proposal['additional_fee_assumption_annual_fraction'])} "
            f"+ {pct(proposal['inflation_assumption_annual_fraction'])} = {pct(hurdle)}, with deductions on beginning-year NAV. "
            "ETF expenses are already in the returns; the extra fee is a separate proposed mandate cost."
        )


def performance_view(context, portfolio: str, start: pd.Timestamp, end: pd.Timestamp) -> None:
    _, _, ref, daily = context
    st.markdown("## Performance")
    st.write("Matched target dates for all three paths, net of trading costs and before spending or the extra fee.")
    chosen = daily[daily.date.between(start, end)]
    if chosen.empty:
        st.info("No active portfolio sessions fall in this range. Paths start on 5 January 2007, after the 504-session warm-up.")
        return

    weights = pd.DataFrame(ref["current_weights"]).set_index("ticker")[portfolio]
    left, right = st.columns([1, 2.1], gap="large")
    with left:
        st.markdown("### Portfolio weights")
        figure = go.Figure(go.Bar(x=weights.values, y=weights.index, orientation="h", marker_color=TEAL,
                                  text=[pct(v, 1) for v in weights.values], textposition="outside", cliponaxis=False))
        figure.update_yaxes(autorange="reversed")
        ui.style_figure(figure, height=330)
        figure.update_xaxes(tickformat=".0%", range=[0, max(0.5, float(weights.max()) * 1.25)])
        st.plotly_chart(figure, width="stretch", key="performance-weights")
        st.caption(f"{ui.PORTFOLIO_LABELS[portfolio]}: prospective target at the frozen close, not historical holdings.")
    with right:
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
        st.markdown("### Cumulative growth of 1.00")
        figure = px.line(paths, x="date", y="Wealth", color="Portfolio", color_discrete_map=ui.PORTFOLIO_COLORS)
        st.plotly_chart(ui.style_figure(figure, height=262), width="stretch", key="performance-wealth")
        st.markdown("### Drawdown from peak")
        figure = px.line(paths, x="date", y="Drawdown", color="Portfolio", color_discrete_map=ui.PORTFOLIO_COLORS)
        figure.update_layout(showlegend=False)
        st.plotly_chart(ui.style_figure(figure, height=196, percent_y=True).update_layout(showlegend=False),
                        width="stretch", key="performance-drawdown")
    st.caption("Each series starts at initial wealth 1.00 before the first selected return, so drawdown includes the starting value.")

    table = selected_kpis(context, start, end)
    if table.empty:
        st.info("At least two sessions are needed for performance statistics.")
    else:
        pivot = table.pivot(index="metric", columns="portfolio_id", values="value")
        rows = []
        for metric, label in ui.KPI_LABELS.items():
            if metric in pivot.index:
                values = [ui.kpi_value(metric, pivot.at[metric, p]) if p in pivot.columns else ui.UNAVAILABLE
                          for p in ui.PORTFOLIO_LABELS]
                rows.append([label, *values])
        st.markdown("### Interpreted statistics for the selected dates")
        st.markdown(
            ui.html_table(["Metric", *[ui.PORTFOLIO_SHORT[p] for p in ui.PORTFOLIO_LABELS]], rows, numeric=(1, 2, 3)),
            unsafe_allow_html=True,
        )
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
            st.markdown(ui.html_table(["Measure", "Value"], rows, numeric=(1,)), unsafe_allow_html=True)
            st.caption(note)


def tail_risk_view(context, portfolio: str, confidence: float, model: str) -> None:
    cfg, data, ref, _ = context
    st.markdown("## Tail risk")
    st.write("Every method below shares one confidence level, exposure, sample and one-day horizon.")
    window_label = st.radio("Estimation sample", ["Recent 1,260 sessions", "Full history"], horizontal=True)
    window = 1260 if window_label.startswith("Recent") else len(data.simple_returns)
    frame = selected_risk(context, portfolio, confidence, window)
    row = frame[frame.model == model]
    columns = st.columns(4)
    if row.empty:
        st.error("The selected method is not available.")
        return
    chosen = row.iloc[0]
    nav = cfg.mandate.nav_usd
    columns[0].metric(f"{confidence:.0%} one-day VaR", pct(chosen.var_loss))
    columns[1].metric(f"{confidence:.0%} one-day ES", pct(chosen.es_loss))
    columns[2].metric("ES in USD on $10M", usd(chosen.es_loss * nav if pd.notna(chosen.es_loss) else None))
    columns[3].metric("Estimation sessions", f"{window:,}")
    if pd.notna(chosen.get("reason")) and chosen.get("reason"):
        message = f"{ui.MODEL_LABELS[model]}: {chosen.reason}"
        (st.warning if chosen.status == "unavailable" else st.info)(message)

    rows = []
    focus = None
    for index, item in enumerate(frame.itertuples()):
        tone = {"ok": "within", "warning": "review", "unavailable": "info"}.get(item.status, "info")
        rows.append([ui.MODEL_LABELS.get(item.model, item.model), pct(item.var_loss), pct(item.es_loss),
                     usd(item.var_loss * nav if pd.notna(item.var_loss) else None),
                     usd(item.es_loss * nav if pd.notna(item.es_loss) else None), pill(item.status.capitalize(), tone)])
        if item.model == model:
            focus = index
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown(f"### VaR, ES and EVT at {confidence:.0%}")
        st.markdown(ui.html_table(["Method", "VaR", "ES", "VaR USD", "ES USD", "Status"], rows, numeric=(1, 2, 3, 4),
                                  raw=(5,), focus=focus), unsafe_allow_html=True)
    with right:
        finite = frame[frame.var_loss.notna()].copy()
        finite["Method"] = finite.model.map(ui.MODEL_LABELS)
        chart = finite.melt(id_vars="Method", value_vars=["var_loss", "es_loss"], var_name="Measure", value_name="Loss")
        chart["Measure"] = chart.Measure.map({"var_loss": "VaR", "es_loss": "ES"})
        figure = px.bar(chart, y="Method", x="Loss", color="Measure", barmode="group", orientation="h",
                        color_discrete_map={"VaR": TEAL, "ES": ui.SAND})
        figure.update_yaxes(autorange="reversed")
        ui.style_figure(figure, height=300)
        figure.update_xaxes(tickformat=".1%", gridcolor=ui.RULE)
        st.plotly_chart(figure, width="stretch", key="tail-comparison")
    st.caption(
        "One-day pre-cost simple losses at the prospective target, shown as positive fractions of NAV. Normal Monte Carlo "
        "is a sampling approximation of the Normal model, not a fat-tail model. Pure POT is unavailable below its "
        "empirical tail boundary; the hybrid uses the empirical body there and is labelled separately. Models that "
        "cannot produce a value stay unavailable rather than showing zero."
    )
    if window == 1260:
        st.caption("The recent sample starts on 25 October 2021, so it omits the GFC and COVID-19. Use Full history to include them.")
    with st.expander("EVT threshold diagnostics, primary portfolio"):
        diagnostics = pd.DataFrame(ref["evt_diagnostics"])
        rows = [
            ["Recent" if d.window_id == "recent" else "Full history", pct(d.candidate_quantile, 1), f"{d.n_exceedances:,}",
             ratio(d.xi, 3), ratio(d.beta * 100, 3), ratio(d.modified_scale * 100, 3), d.status.capitalize()]
            for d in diagnostics.itertuples()
        ]
        st.markdown(
            ui.html_table(["Sample", "Threshold", "Excesses", "Shape ξ", "Scale β (%)", "Modified scale (%)", "Status"],
                          rows, numeric=(1, 2, 3, 4, 5)),
            unsafe_allow_html=True,
        )
        st.caption("Fitted at the current target. A positive fitted shape alone is not a formal rejection of the Gaussian model.")


def backtesting_view(context, confidence: float, start: pd.Timestamp, end: pd.Timestamp) -> None:
    st.markdown("## Backtesting")
    st.write(
        "Forecast first, then observe the next loss. Each forecast uses the prior 500 sessions and the holdings known "
        "before that day. Only the primary rule has rolling results, for the Historical and Normal models below."
    )
    model = st.radio("Rolling forecast model", list(ui.ROLLING_LABELS), horizontal=True,
                     format_func=lambda key: ui.ROLLING_LABELS[key])
    chosen, summary, basel = selected_backtest(model, confidence, start, end)
    if chosen.empty:
        st.info("No forecast targets fall in this range. Rolling targets run from 5 January 2007 to 30 October 2026.")
        return
    stats = summary.iloc[0]
    columns = st.columns(4)
    columns[0].metric("Exceptions / sessions", f"{int(stats.n_exceedances):,} / {int(stats.n_valid):,}",
                      f"Expected {(1 - confidence) * stats.n_valid:,.1f}", delta_color="off", delta_arrow="off")
    columns[1].metric("Kupiec p (frequency)", pvalue(stats.p_uc))
    columns[2].metric("Christoffersen p (clustering)", pvalue(stats.p_ind))
    columns[3].metric("Conditional coverage p", pvalue(stats.p_cc))
    st.caption("Small p-values reject the model at that test. A large p-value is not proof of future safety, and sparse samples have little power.")

    figure = go.Figure()
    figure.add_trace(go.Scatter(x=chosen.date, y=chosen.realized_loss, name="Realised gross loss", line={"color": ui.SLATE, "width": 0.8}))
    figure.add_trace(go.Scatter(x=chosen.date, y=chosen.forecast_var, name=f"{confidence:.0%} VaR forecast", line={"color": TEAL, "width": 1.3}))
    breaches = chosen[chosen.exceedance.eq(True)]
    figure.add_trace(go.Scatter(x=breaches.date, y=breaches.realized_loss, name="Exception", mode="markers",
                                marker={"color": RED, "size": 5}))
    st.plotly_chart(ui.style_figure(figure, height=320, percent_y=True, y_title="One-day loss"), width="stretch", key="backtest-chart")

    st.markdown("### Educational Basel traffic light")
    if basel.get("status") == "ok":
        zone = basel["zone"]
        tone = {"green": "within", "yellow": "review", "red": "breach"}[zone]
        st.markdown(
            ui.html_table(
                ["Scope", "Block", "Exceptions", "Expected", "Zone"],
                [["99% / 250 sessions", f"{basel['block_start']} to {basel['block_end']}", str(basel["n_exceedances"]),
                  ratio(basel["expected_exceedances"], 1), pill(zone.capitalize(), tone)]],
                numeric=(2, 3), raw=(4,),
            ),
            unsafe_allow_html=True,
        )
    else:
        st.info(f"Unavailable for this range: {basel.get('reason') or 'it needs 250 valid sessions at 99%.'}")
    st.caption(
        "Always the final 250 valid 99% sessions in the selected range, whatever confidence is chosen above. It is a "
        "teaching diagnostic, not regulatory approval. A green recent light does not erase earlier failures: the full-history "
        "Historical 99% model still rejects both frequency and independence."
    )
    st.download_button("Download selected forecast rows (CSV)", chosen.to_csv(index=False), file_name="selected_backtest.csv", key="backtest-rows")


def risk_budget_view(context, portfolio: str, confidence: float) -> None:
    cfg, data, ref, _ = context
    st.markdown("## Risk budget and stress")
    st.write("Where tail risk comes from at the prospective target, and how that exposure behaves in actual crises.")
    weights = pd.DataFrame(ref["current_weights"]).set_index("ticker")[portfolio]
    method = st.selectbox("Risk decomposition", list(ui.EULER_LABELS), format_func=lambda key: ui.EULER_LABELS[key])
    frame = risk_contributions(data.simple_returns.iloc[-1260:], weights, confidence=confidence, method=method)
    chart = frame.melt(id_vars="ticker", value_vars=["weight", "pct_contribution"], var_name="Measure", value_name="Share")
    chart["Measure"] = chart.Measure.map({"weight": "Target weight", "pct_contribution": f"Share of {ui.EULER_LABELS[method]}"})
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.markdown(f"### Weight against share of risk, {confidence:.0%}")
        figure = px.bar(chart, x="ticker", y="Share", color="Measure", barmode="group",
                        color_discrete_map={"Target weight": ui.SLATE, f"Share of {ui.EULER_LABELS[method]}": TEAL})
        st.plotly_chart(ui.style_figure(figure, height=310, percent_y=True), width="stretch", key="risk-share")
    with right:
        st.markdown("### Marginal and component risk")
        rows = [[row.ticker, pct(row.weight), pct(row.marginal_risk), pct(row.component_risk), pct(row.pct_contribution, 1)]
                for row in frame.itertuples()]
        st.markdown(ui.html_table(["ETF", "Weight", "Marginal", "Component", "Share"], rows, numeric=(1, 2, 3, 4)), unsafe_allow_html=True)
        st.caption(f"Components sum to total risk of {pct(frame.total_risk.iloc[0])} on the recent 1,260 sessions. Signed Euler shares: "
                   "a negative value is a local hedge in this sample, not guaranteed protection.")

    st.markdown("### Crisis replay and hypothetical shock")
    stress = selected_stress(context, portfolio)
    reference = selected_stress(context, "benchmark_60_40")
    rows = []
    for scenario in SCENARIOS:
        item = stress[stress.scenario_id == scenario].iloc[0]
        base = reference[reference.scenario_id == scenario].iloc[0]
        rows.append([ui.SCENARIO_LABELS[scenario], pct(item.total_return), pct(item.max_drawdown), pct(item.worst_day_return),
                     usd(-item.usd_loss), pct(base.total_return), pct(base.max_drawdown)])
    st.markdown(
        ui.html_table(["Scenario", "Endpoint return", "Max drawdown", "Worst day", "USD at endpoint", "60/40 endpoint", "60/40 drawdown"],
                      rows, numeric=(1, 2, 3, 4, 5, 6),
                      caption=f"{ui.PORTFOLIO_LABELS[portfolio]}, prospective target, on USD {cfg.mandate.nav_usd:,.0f}."),
        unsafe_allow_html=True,
    )
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
        st.markdown(ui.html_table(["Candidate", "VaR 99%", "ES 99%", "Target caps", "Proposed tail limits"], rows, numeric=(1, 2), raw=(3, 4)),
                    unsafe_allow_html=True)
        st.caption("Historical simulation on the recent 1,260 sessions. References are not required to meet the candidate's caps.")
    with st.expander("Monitoring triggers"):
        rows = [[m["metric"], str(m["threshold"]), m["action"]] for m in ref["proposal"]["monitoring"]]
        st.markdown(ui.html_table(["Metric", "Threshold", "Proposed response"], rows, numeric=(1,)), unsafe_allow_html=True)


def assumptions_view(context) -> None:
    _, _, ref, _ = context
    st.markdown("## Assumptions & Limitations")
    st.write("What this analysis does not capture, in plain language.")
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
    st.markdown(
        ui.html_table(
            ["Item", "Status", "Meaning"],
            [
                ["AI-assisted verification", pill("Recorded", "within"), "Automated and AI checks are listed in audit/presentation_review/."],
                ["Independent human validation", pill("Pending", "review"), "A team member must recompute and record it. AI cannot complete this."],
                ["Team decision", pill("Pending", "review"), "The team must evaluate and own the recommendation."],
                ["University committee approval", pill("Not applicable yet", "info"), "This is a competition proposal. No real committee has approved it."],
            ],
            raw=(1,),
        ),
        unsafe_allow_html=True,
    )
    with st.expander("Result bundle and proposal provenance"):
        st.json(ref["metadata"])
        st.json(ref["proposal"])
    st.download_button("Download source-of-truth JSON", (ROOT / "results/final/reference.json").read_bytes(),
                       file_name="reference.json", mime="application/json", key="evidence-json")
    report_downloads("evidence")
    for name in ["AI_DISCLOSURE.md", "submission/COMPLIANCE_MATRIX.md", "submission/VALIDATION_CHECKLIST.md"]:
        path = ROOT / name
        if path.exists():
            with st.expander(path.name):
                st.markdown(path.read_text(encoding="utf-8"))
