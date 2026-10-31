"""Replot the report figures from persisted results as vector PDF and 300 dpi PNG.

Reads only results/final and the saved development-only Step 7 tables. No model is
re-estimated and no series is synthesised. Requires requirements-render.txt.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tmp/figure_export_deps"))

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

OUT = ROOT / "report/latex/generated/figures"
FINAL = ROOT / "results/final"
INK, BODY, MUTED, RULE = "#16263d", "#33404f", "#667080", "#ddd5c5"
TEAL, SAND, SLATE, RED, AMBER = "#0f6b6b", "#c9b48a", "#8b93a0", "#a8322a", "#a86a12"
NAMES = {"min_variance": "Candidate rule", "equal_weight": "Equal weight", "benchmark_60_40": "60/40"}
COLORS = {"min_variance": TEAL, "equal_weight": SAND, "benchmark_60_40": SLATE}
FULL_WIDTH, PERCENT = 6.3, FuncFormatter(lambda v, _: f"{v:.0%}")
PERCENT_1 = FuncFormatter(lambda v, _: f"{v:.1%}")


def configure_fonts() -> None:
    """Match the report's sans font when TeX can locate it; otherwise use matplotlib's default."""
    family = "DejaVu Sans"
    kpsewhich = shutil.which("kpsewhich")
    if kpsewhich:
        for name in ("LibertinusSans-Regular.otf", "LibertinusSans-Bold.otf", "LibertinusSans-Italic.otf"):
            found = subprocess.run([kpsewhich, name], capture_output=True, text=True).stdout.strip()
            if found:
                font_manager.fontManager.addfont(found)
                family = "Libertinus Sans"
    plt.rcParams.update(
        {
            "font.family": family,
            "font.size": 9,
            "axes.titlesize": 9.5,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 8.8,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.5,
            "legend.frameon": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": INK,
            "axes.linewidth": 0.6,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "axes.axisbelow": True,
            "grid.color": RULE,
            "grid.linewidth": 0.5,
            "text.color": INK,
            "axes.labelcolor": BODY,
            "xtick.color": BODY,
            "ytick.color": BODY,
            "xtick.major.width": 0.5,
            "ytick.major.width": 0,
            "figure.dpi": 150,
            "pdf.fonttype": 3,
            "svg.fonttype": "none",
        }
    )


def save(figure: plt.Figure, name: str) -> None:
    figure.savefig(OUT / f"{name}.pdf", bbox_inches="tight", pad_inches=0.02)
    figure.savefig(OUT / f"{name}.png", dpi=300, bbox_inches="tight", pad_inches=0.02)
    plt.close(figure)


def kpi(ref: dict, period: str, portfolio: str, metric: str) -> float:
    return next(
        x["value"] for x in ref["period_kpis"]
        if x["period"] == period and x["portfolio_id"] == portfolio and x["metric"] == metric
    )


def wealth_drawdown() -> None:
    daily = pd.read_csv(FINAL / "daily_performance.csv", parse_dates=["date"])
    figure, axes = plt.subplots(2, 1, figsize=(FULL_WIDTH, 3.45), sharex=True, gridspec_kw={"height_ratios": [1.7, 1], "hspace": 0.1})
    for portfolio in NAMES:
        group = daily[daily.portfolio_id == portfolio]
        width = 1.25 if portfolio == "min_variance" else 0.85
        axes[0].plot(group.date, group.wealth, color=COLORS[portfolio], lw=width, label=NAMES[portfolio])
        axes[1].plot(group.date, group.drawdown, color=COLORS[portfolio], lw=width)
    for start, end in (("2017-01-03", "2020-12-31"),):
        for axis in axes:
            axis.axvspan(pd.Timestamp(start), pd.Timestamp(end), color="#f1ecdf", lw=0, zorder=0)
    axes[0].text(pd.Timestamp("2011-12-30"), 0.47, "Development", color=MUTED, ha="center", fontsize=8.3)
    axes[0].text(pd.Timestamp("2019-01-01"), 0.47, "Selection", color=MUTED, ha="center", fontsize=8.3)
    axes[0].text(pd.Timestamp("2024-01-01"), 0.47, "Evaluation", color=MUTED, ha="center", fontsize=8.3)
    axes[0].set_ylabel("Net wealth (start = 1)")
    axes[0].set_ylim(bottom=0.35)
    axes[0].legend(ncol=3, loc="upper left", borderaxespad=0.1)
    axes[1].set_ylabel("Drawdown")
    axes[1].yaxis.set_major_formatter(PERCENT)
    axes[1].axhline(-0.20, color=RED, lw=0.7, ls=(0, (4, 3)))
    axes[1].text(pd.Timestamp("2013-07-01"), -0.21, "Proposed 20% review line", color=RED, ha="center", va="top", fontsize=8)
    save(figure, "wealth_drawdown")


def funding(ref: dict) -> None:
    periods = [("development", "Development\n2007-2016"), ("selection", "Selection\n2017-2020"), ("evaluation", "Evaluation\n2021-2026")]
    hurdle = ref["proposal"]["required_nominal_return_fraction"]
    figure, axis = plt.subplots(figsize=(FULL_WIDTH * 0.62, 2.15))
    x = np.arange(3)
    for offset, portfolio in zip((-0.27, 0, 0.27), NAMES):
        values = [kpi(ref, p, portfolio, "geometric_annual_return") for p, _ in periods]
        bars = axis.bar(x + offset, values, 0.26, color=COLORS[portfolio], label=NAMES[portfolio])
        for bar, value in zip(bars, values):
            above_line = value + 0.0165 if abs(value - hurdle) < 0.012 else value + 0.002
            axis.text(bar.get_x() + bar.get_width() / 2, above_line if value < hurdle + 0.012 else value + 0.002, f"{value:.2%}",
                      ha="center", fontsize=6.3, color=BODY)
    axis.axhline(hurdle, color=INK, lw=0.8, ls=(0, (4, 3)))
    axis.text(2.5, hurdle, f" {hurdle:.2%}\n hurdle", ha="left", va="center", fontsize=8, color=INK, clip_on=False)
    axis.set_xticks(x, [label for _, label in periods])
    axis.set_xlim(-0.5, 2.5)
    axis.set_yticks([0, 0.05, 0.10, 0.15])
    axis.yaxis.set_major_formatter(PERCENT)
    axis.set_ylim(0, 0.185)
    axis.set_ylabel("Net CAGR")
    axis.legend(ncol=3, loc="upper left", borderaxespad=0.1, columnspacing=1.1, handlelength=1.2)
    save(figure, "funding")


def weights_risk(ref: dict) -> None:
    contributions = pd.DataFrame(ref["risk_contributions"]["historical_es"]).set_index("ticker")
    figure, axis = plt.subplots(figsize=(FULL_WIDTH * 0.62, 1.95))
    x = np.arange(len(contributions))
    axis.bar(x - 0.19, contributions.weight, 0.36, color=SLATE, label="Target weight")
    axis.bar(x + 0.19, contributions.pct_contribution, 0.36, color=TEAL, label="Share of Historical ES 99%")
    for i, (w, s) in enumerate(zip(contributions.weight, contributions.pct_contribution)):
        if w > 0.0005:
            axis.text(i - 0.19, w + 0.008, f"{w:.0%}", ha="center", fontsize=7.4, color=BODY)
            axis.text(i + 0.19, s + 0.008, f"{s:.0%}", ha="center", fontsize=7.4, color=BODY)
    axis.set_xticks(x, contributions.index)
    axis.yaxis.set_major_formatter(PERCENT)
    axis.set_ylim(0, 0.5)
    axis.legend(ncol=2, loc="upper right", borderaxespad=0)
    save(figure, "weights_risk")


def target_path() -> None:
    rows = pd.read_csv(FINAL / "rebalances_min_variance.csv", parse_dates=["effective_date"])
    tickers = ["AGG", "GLD", "SPY", "XLE", "XLK", "EFA", "EEM"]
    colors = [TEAL, SAND, INK, AMBER, SLATE, "#b9bfc8", "#dcd6c8"]
    figure, axis = plt.subplots(figsize=(FULL_WIDTH * 0.62, 1.8))
    axis.stackplot(rows.effective_date, *[rows[t].clip(lower=0) for t in tickers], colors=colors, labels=tickers, lw=0)
    axis.set_ylim(0, 1)
    axis.margins(x=0)
    axis.grid(False)
    axis.yaxis.set_major_formatter(PERCENT)
    axis.set_ylabel("Monthly target")
    axis.legend(ncol=1, loc="center left", bbox_to_anchor=(1.0, 0.5), handlelength=1, labelspacing=0.3)
    save(figure, "target_path")


def tail_models(ref: dict) -> None:
    risk = pd.DataFrame(ref["risk_table"])
    models = [("historical", "Historical"), ("parametric_normal", "Normal"), ("monte_carlo_normal", "Normal MC"), ("evt_pot", "POT-GPD")]
    limits = ref["proposal"]["risk_limits"]
    figure, axes = plt.subplots(1, 2, figsize=(FULL_WIDTH, 2.25), sharey=True, gridspec_kw={"wspace": 0.06})
    for axis, (window, title) in zip(axes, (("recent", "Recent 1,260 sessions"), ("full_history", "Full 5,491 sessions"))):
        frame = risk[(risk.window_id == window) & (risk.confidence == 0.99)].set_index("model")
        x = np.arange(len(models))
        var, es = [frame.at[m, "var_loss"] for m, _ in models], [frame.at[m, "es_loss"] for m, _ in models]
        axis.bar(x - 0.19, var, 0.36, color=SLATE, label="VaR 99%")
        axis.bar(x + 0.19, es, 0.36, color=TEAL, label="ES 99%")
        for i, (v, e) in enumerate(zip(var, es)):
            for x_at, value in ((i - 0.19, v), (i + 0.19, e)):
                axis.text(x_at, value + 0.0004, f"{value:.2%}", ha="center", fontsize=6.4, color=BODY, zorder=6,
                          bbox=dict(facecolor="white", edgecolor="none", pad=0.6))
        axis.axhline(limits["max_daily_es_99_fraction"], color=RED, lw=0.8, ls=(0, (4, 3)), label="ES budget 2.0%")
        axis.axhline(limits["max_daily_var_99_fraction"], color=AMBER, lw=0.8, ls=(0, (1, 2)), label="VaR budget 1.5%")
        axis.set_xticks(x, [label for _, label in models])
        axis.set_title(title)
    axes[0].yaxis.set_major_formatter(PERCENT_1)
    axes[0].set_ylabel("One-day loss / NAV")
    axes[0].set_ylim(0, 0.03)
    handles, labels = axes[1].get_legend_handles_labels()
    figure.legend(handles, labels, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.09), columnspacing=1.4, handlelength=1.6)
    save(figure, "tail_models")


def evt_stability(ref: dict) -> None:
    frame = pd.DataFrame(ref["evt_diagnostics"])
    figure, axes = plt.subplots(1, 2, figsize=(FULL_WIDTH, 1.75), gridspec_kw={"wspace": 0.28})
    for window, label, color in (("recent", "Recent 1,260", TEAL), ("full_history", "Full 5,491", INK)):
        rows = frame[(frame.window_id == window) & frame.xi.notna()]
        axes[0].errorbar(rows.candidate_quantile, rows.xi, yerr=1.96 * rows.xi_se_asymptotic_iid, color=color, marker="o", ms=3.5,
                         lw=0.9, elinewidth=0.7, capsize=2, label=label)
        axes[1].plot(rows.candidate_quantile, rows.modified_scale * 100, color=color, marker="o", ms=3.5, lw=0.9)
    axes[0].axhline(0, color=MUTED, lw=0.6)
    axes[0].set_title("Fitted shape ξ, with iid asymptotic ±1.96 SE")
    axes[0].legend(loc="upper left", ncol=2, borderaxespad=0.1)
    axes[0].set_ylim(-0.25, 0.88)
    axes[1].set_title("Modified scale β − ξu (% of NAV)")
    for axis in axes:
        axis.xaxis.set_major_formatter(PERCENT_1)
        axis.set_xticks([0.90, 0.925, 0.95, 0.975])
        axis.set_xlabel("Threshold quantile")
    save(figure, "evt_stability")


def development_qq() -> None:
    frame = pd.read_csv(ROOT / "results/step7_evt_preview/tables/table_04_qq_pp_full_development_3020d.csv")
    figure, axes = plt.subplots(1, 1, figsize=(FULL_WIDTH * 0.42, 1.9))
    x, y = frame["model_quantile_excess"] * 100, frame["empirical_excess"] * 100
    top = float(max(x.max(), y.max())) * 1.05
    axes.plot([0, top], [0, top], color=MUTED, lw=0.7)
    axes.scatter(x, y, s=4, color=TEAL, lw=0)
    axes.set_xlabel("Fitted GPD excess quantile (%)")
    axes.set_ylabel("Empirical excess (%)")
    axes.grid(False)
    save(figure, "development_qq")


def exceptions() -> None:
    rows = pd.read_csv(FINAL / "backtest_historical_0.99.csv", parse_dates=["date"])
    figure, axes = plt.subplots(2, 1, figsize=(FULL_WIDTH, 2.95), sharex=True, gridspec_kw={"height_ratios": [1.8, 1], "hspace": 0.12})
    axes[0].plot(rows.date, rows.realized_loss.clip(lower=0), color=SLATE, lw=0.35, label="Realised gross loss")
    axes[0].plot(rows.date, rows.forecast_var, color=TEAL, lw=0.9, label="Prior-500 Historical VaR 99%")
    hits = rows[rows.exceedance.eq(True)]
    axes[0].scatter(hits.date, hits.realized_loss, s=7, color=RED, lw=0, zorder=3, label=f"Exceptions ({len(hits)})")
    axes[0].yaxis.set_major_formatter(PERCENT)
    axes[0].set_ylabel("One-day loss")
    axes[0].legend(ncol=3, loc="lower right", bbox_to_anchor=(1, 1), borderaxespad=0.1)
    count = rows.exceedance.astype(float).rolling(250).sum()
    axes[1].plot(rows.date, count, color=INK, lw=0.9)
    axes[1].axhline(2.5, color=MUTED, lw=0.7, ls=(0, (1, 2)))
    axes[1].axhspan(4.5, 9.5, color="#f7ecd8", lw=0, zorder=0)
    axes[1].axhspan(9.5, max(count.max() + 1, 12), color="#f6e4e1", lw=0, zorder=0)
    axes[1].set_ylabel("Exceptions in\nlast 250 sessions")
    axes[1].set_ylim(0, max(count.max() + 1, 12))
    save(figure, "exceptions")


def stress(ref: dict) -> None:
    frame = pd.DataFrame(ref["stress_results"])
    scenarios = [("gfc_2007_2009", "GFC"), ("covid_2020", "COVID-19"), ("rate_shock_2022", "2022 rates"),
                 ("hypothetical_stagflation_repricing", "Hypothetical")]
    figure, axis = plt.subplots(figsize=(FULL_WIDTH, 1.95))
    x = np.arange(len(scenarios))
    for offset, portfolio, shade in ((-0.2, "min_variance", TEAL), (0.2, "benchmark_60_40", SLATE)):
        rows = frame[frame.portfolio_id == portfolio].set_index("scenario_id")
        ends = [rows.at[s, "total_return"] for s, _ in scenarios]
        troughs = [rows.at[s, "max_drawdown"] for s, _ in scenarios]
        axis.bar(x + offset, troughs, 0.36, color=shade, alpha=0.28, lw=0)
        axis.bar(x + offset, ends, 0.36, color=shade, label=NAMES[portfolio])
        for i, (e, t) in enumerate(zip(ends, troughs)):
            axis.text(i + offset, t - 0.008, f"{t:.1%}".replace("-", "\N{MINUS SIGN}"), ha="center", va="top", fontsize=7, color=BODY, zorder=6, bbox=dict(facecolor="white", edgecolor="none", pad=0.5))
    axis.axhline(-0.20, color=RED, lw=0.8, ls=(0, (4, 3)))
    axis.axhline(0, color=INK, lw=0.6)
    axis.set_xticks(x, [label for _, label in scenarios])
    axis.tick_params(axis="x", length=0)
    axis.xaxis.tick_top()
    axis.spines["bottom"].set_visible(False)
    axis.yaxis.set_major_formatter(PERCENT)
    axis.set_ylim(-0.37, 0)
    axis.set_ylabel("Return / NAV")
    axis.legend(ncol=2, loc="lower right", borderaxespad=0, title="Solid: endpoint.  Pale: deepest drawdown", title_fontsize=8,
                frameon=True, facecolor="white", edgecolor="none", framealpha=1)
    save(figure, "stress")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    configure_fonts()
    ref = json.loads((FINAL / "reference.json").read_text(encoding="utf-8"))
    wealth_drawdown()
    funding(ref)
    weights_risk(ref)
    target_path()
    tail_models(ref)
    evt_stability(ref)
    development_qq()
    exceptions()
    stress(ref)
    print(f"Exported {len(list(OUT.glob('*.pdf')))} vector figures using {plt.rcParams['font.family']}")


if __name__ == "__main__":
    main()
