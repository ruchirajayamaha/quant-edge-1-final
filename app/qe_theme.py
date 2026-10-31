"""Presentation tokens, formatters and small HTML components for the decision room.

No calculation happens here. Every value shown by these helpers is passed in by a view
that read it from the verified reference or the shared analytical library.
"""
from __future__ import annotations

from html import escape
import math

import pandas as pd

INK = "#16263d"
BODY = "#33404f"
MUTED = "#667080"
PAPER = "#fbf8f1"
SURFACE = "#fffdf9"
RULE = "#e3dccd"
TEAL = "#0f6b6b"
AMBER = "#a86a12"
RED = "#a8322a"
SLATE = "#8b93a0"
SAND = "#c9b48a"

SERIF = "'Iowan Old Style','Palatino Linotype','Book Antiqua',Palatino,Georgia,serif"
SANS = "'Segoe UI','Helvetica Neue',Arial,sans-serif"

PORTFOLIO_LABELS = {
    "min_variance": "Constrained minimum variance",
    "equal_weight": "Equal-weight reference",
    "benchmark_60_40": "60/40 reference",
}
PORTFOLIO_SHORT = {
    "min_variance": "Candidate rule",
    "equal_weight": "Equal weight",
    "benchmark_60_40": "60/40",
}
PORTFOLIO_COLORS = {
    PORTFOLIO_LABELS["min_variance"]: TEAL,
    PORTFOLIO_LABELS["equal_weight"]: SAND,
    PORTFOLIO_LABELS["benchmark_60_40"]: SLATE,
}
MODEL_LABELS = {
    "historical": "Historical simulation",
    "parametric_normal": "Normal (parametric)",
    "monte_carlo_normal": "Normal Monte Carlo",
    "evt_pot": "EVT: pure POT-GPD",
    "evt_body_tail_hybrid": "Empirical body / GPD tail hybrid",
}
ROLLING_LABELS = {"historical": "Historical", "parametric_normal": "Normal"}
SCENARIO_LABELS = {
    "gfc_2007_2009": "Global Financial Crisis",
    "covid_2020": "COVID-19 shock",
    "rate_shock_2022": "2022 rate shock",
    "hypothetical_stagflation_repricing": "Hypothetical stagflation",
}
EULER_LABELS = {
    "historical_es": "Historical ES",
    "normal_es": "Normal ES",
    "normal_var": "Normal VaR",
}
KPI_LABELS = {
    "geometric_annual_return": "Net annual growth (CAGR)",
    "arithmetic_annual_return": "Arithmetic annual return",
    "annualized_volatility": "Annual volatility",
    "downside_deviation": "Downside deviation",
    "max_drawdown": "Maximum drawdown",
    "sharpe_ratio": "Sharpe ratio",
    "sortino_ratio": "Sortino ratio",
    "calmar_ratio": "Calmar ratio",
    "capm_beta": "CAPM beta to SPY",
    "jensen_alpha": "Jensen alpha (annual)",
    "treynor_ratio": "Treynor ratio",
    "tracking_error": "Tracking error to 60/40",
    "information_ratio": "Information ratio to 60/40",
}
FRACTION_METRICS = {
    "geometric_annual_return",
    "arithmetic_annual_return",
    "annualized_volatility",
    "downside_deviation",
    "max_drawdown",
    "jensen_alpha",
    "tracking_error",
}
UNAVAILABLE = "Unavailable"


def _missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA


def pct(value: float | None, digits: int = 2) -> str:
    """Format a fraction as a percentage, keeping the sign of losses and gains."""
    return UNAVAILABLE if _missing(value) else f"{value:.{digits}%}"


def usd(value: float | None) -> str:
    """Format a dollar amount to the nearest dollar."""
    if _missing(value):
        return UNAVAILABLE
    return f"-${-value:,.0f}" if value < 0 else f"${value:,.0f}"


def ratio(value: float | None, digits: int = 2) -> str:
    """Format a unit-free statistic."""
    return UNAVAILABLE if _missing(value) else f"{value:.{digits}f}"


def pvalue(value: float | None) -> str:
    """Format a p-value without rounding a small value down to zero."""
    if _missing(value):
        return UNAVAILABLE
    if value == 0:
        return "< 1e-300"
    return f"{value:.1e}" if value < 0.001 else f"{value:.3f}"


def kpi_value(metric: str, value: float | None) -> str:
    """Format a KPI by its unit."""
    return pct(value) if metric in FRACTION_METRICS else ratio(value)


def css() -> str:
    """Return the page stylesheet. Fonts come from the viewer's system, so launch stays offline."""
    return f"""<style>
    .stApp {{background:{PAPER};color:{BODY};font-family:{SANS};}}
    .block-container {{padding-top:2.1rem;padding-bottom:3.5rem;max-width:1240px;}}
    h1,h2,h3,h4,.stMarkdown h2,.stMarkdown h3,[data-testid="stHeading"] *,[data-testid="stMarkdownContainer"] h2,[data-testid="stMarkdownContainer"] h3 {{font-family:{SERIF} !important;color:{INK};letter-spacing:-.005em;font-weight:600 !important;}}
    .stMarkdown h2 {{font-size:1.72rem !important;padding-top:.2rem !important;}}
    .stMarkdown h3 {{font-size:1.16rem !important;padding:.75rem 0 .3rem !important;border-top:1px solid {RULE};}}
    p,li {{line-height:1.58;}}
    [data-testid="stSidebar"] {{background:#f4efe3;border-right:1px solid {RULE};}}
    [data-testid="stSidebar"] h2 {{font-size:1.2rem !important;}}
    [data-testid="stMetric"] {{background:{SURFACE};border:1px solid {RULE};border-top:2px solid {INK};
        padding:13px 15px 11px;border-radius:2px;height:100%;}}
    [data-testid="stMetricLabel"] p {{color:{MUTED};font-size:.79rem;font-weight:600;line-height:1.3;}}
    [data-testid="stMetricValue"] {{font-family:{SERIF};color:{INK};font-size:1.72rem;font-variant-numeric:lining-nums;}}
    [data-testid="stMetricDelta"] {{font-size:.78rem;border-radius:8px;}}
    [data-testid="stMetricLabel"],[data-testid="stMetricLabel"] *,[data-testid="stMetricDelta"],[data-testid="stMetricDelta"] *
    {{white-space:normal !important;overflow:visible !important;text-overflow:clip !important;height:auto;}}
    [data-testid="stCaptionContainer"] {{opacity:1 !important;}}
    [data-testid="stCaptionContainer"] p {{color:{MUTED};font-size:.82rem;line-height:1.5;}}
    [data-testid="stExpander"] {{background:{SURFACE};border:1px solid {RULE};border-radius:2px;}}
    [data-testid="stDownloadButton"] button {{border-radius:2px;border:1px solid {INK};background:{SURFACE};color:{INK};}}
    .qe-kicker {{font-size:.74rem;letter-spacing:.11em;text-transform:uppercase;color:{MUTED};font-weight:600;}}
    .qe-title {{font-family:{SERIF};color:{INK};font-size:2.3rem;line-height:1.14;font-weight:600;margin:.25rem 0 .4rem;}}
    .qe-title em {{color:{TEAL};font-style:normal;}}
    .qe-lede {{font-size:1.04rem;line-height:1.58;color:{BODY};max-width:58rem;margin-bottom:.8rem;}}
    .qe-status {{display:flex;flex-wrap:wrap;gap:.45rem 1.5rem;border-top:1px solid {RULE};border-bottom:1px solid {RULE};
        padding:.5rem 0;margin:.2rem 0 1.15rem;font-size:.81rem;color:{BODY};}}
    .qe-status b {{color:{INK};font-weight:600;}}
    .qe-scroll {{overflow-x:auto;max-width:100%;}}
    .qe-table {{width:100%;border-collapse:collapse;font-size:.875rem;background:transparent;}}
    .qe-table caption {{caption-side:top;text-align:left;color:{MUTED};font-size:.79rem;padding-bottom:.35rem;}}
    .qe-table th {{text-align:left;color:{MUTED};font-weight:600;font-size:.75rem;letter-spacing:.02em;
        border-bottom:1.5px solid {INK};padding:.34rem .55rem .34rem 0;vertical-align:bottom;}}
    .qe-table td {{border-bottom:1px solid {RULE};padding:.42rem .55rem .42rem 0;vertical-align:top;color:{BODY};}}
    .qe-table,.qe-table th,.qe-table td {{border-left:none !important;border-right:none !important;border-top:none !important;}}
    .qe-table td.num,.qe-table th.num {{text-align:right;font-variant-numeric:tabular-nums lining-nums;white-space:nowrap;}}
    .qe-table td.lead {{color:{INK};font-weight:500;}}
    .qe-table tr.focus td {{background:#f1f4ee;}}
    .qe-pill {{display:inline-block;font-size:.73rem;font-weight:600;padding:.03rem .46rem;border-radius:2px;white-space:nowrap;}}
    .qe-pill.within {{color:{TEAL};background:#e6f0ee;}}
    .qe-pill.review {{color:{AMBER};background:#f7ecd8;}}
    .qe-pill.breach {{color:{RED};background:#f6e4e1;}}
    .qe-pill.info {{color:{MUTED};background:#eeeae0;}}
    .qe-note {{border-left:2px solid {INK};padding:.1rem 0 .1rem .8rem;margin:.55rem 0 .85rem;font-size:.92rem;}}
    .qe-actions {{margin:.2rem 0 .3rem;padding-left:0;list-style:none;counter-reset:qe;}}
    .qe-actions li {{counter-increment:qe;padding:.46rem 0 .46rem 1.9rem;position:relative;border-bottom:1px solid {RULE};font-size:.93rem;}}
    .qe-actions li:before {{content:counter(qe);position:absolute;left:0;top:.42rem;font-family:{SERIF};color:{TEAL};font-size:1.08rem;font-weight:600;}}
    .qe-actions b {{color:{INK};font-weight:600;}}
    </style>"""


def masthead(kicker: str, title_html: str, lede: str) -> str:
    """Return a restrained page masthead. ``title_html`` is trusted static markup."""
    return (
        f'<div class="qe-kicker">{escape(kicker)}</div><div class="qe-title">{title_html}</div>'
        f'<div class="qe-lede">{escape(lede)}</div>'
    )


def status_strip(items: list[tuple[str, str]]) -> str:
    """Return a one-line status area of labelled facts."""
    body = "".join(f"<span><b>{escape(k)}</b> {escape(v)}</span>" for k, v in items)
    return f'<div class="qe-status">{body}</div>'


def pill(text: str, tone: str) -> str:
    """Return a status label. ``tone`` is one of within, review, breach or info."""
    return f'<span class="qe-pill {tone}">{escape(text)}</span>'


def html_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    numeric: tuple[int, ...] = (),
    caption: str | None = None,
    focus: int | None = None,
    raw: tuple[int, ...] = (),
) -> str:
    """Return an editorial table. Cells are escaped unless their column is listed in ``raw``."""

    def cell(index: int, value: str) -> str:
        classes = "num" if index in numeric else ("lead" if index == 0 else "")
        content = value if index in raw else escape(str(value))
        return f'<td class="{classes}">{content}</td>'

    head = "".join(f'<th class="{"num" if i in numeric else ""}">{escape(h)}</th>' for i, h in enumerate(headers))
    body = "".join(
        f'<tr class="{"focus" if focus == r else ""}">' + "".join(cell(i, v) for i, v in enumerate(row)) + "</tr>"
        for r, row in enumerate(rows)
    )
    cap = f"<caption>{escape(caption)}</caption>" if caption else ""
    return f'<div class="qe-scroll"><table class="qe-table">{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def action_list(items: list[tuple[str, str]]) -> str:
    """Return a numbered list of bold-led actions."""
    body = "".join(f"<li><b>{escape(lead)}</b> {escape(text)}</li>" for lead, text in items)
    return f'<ol class="qe-actions">{body}</ol>'


def style_figure(figure, *, height: int = 330, percent_y: bool = False, y_title: str | None = None):
    """Apply the shared chart style so every chart has the same type, grid and legend."""
    figure.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": SANS, "color": BODY, "size": 12.5},
        margin={"l": 8, "r": 12, "t": 34, "b": 8},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0, "title": None, "font": {"size": 12}},
        hoverlabel={"font": {"family": SANS}},
        title=None,
    )
    figure.update_xaxes(showgrid=False, linecolor=INK, ticks="outside", tickcolor=RULE, title=None, automargin=True)
    figure.update_yaxes(gridcolor=RULE, zeroline=True, zerolinecolor=MUTED, zerolinewidth=1, title=y_title, automargin=True)
    if percent_y:
        figure.update_yaxes(tickformat=".1%")
    return figure
