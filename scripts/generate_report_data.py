"""Format verified results as LaTeX macros and tables. No analytics happen here.

Inputs: results/final/reference.json, data/reference/rf_evidence/evidence_coverage.json,
the active snapshot's quality flags, and the saved Step 7 authority.
Outputs: report/latex/generated/metrics.tex, tables/*.tex and metrics_manifest.json.
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report/latex/generated"
TABLES = OUT / "tables"
NA = r"\textit{n/a}"
MINUS = "\N{MINUS SIGN}"
PORTFOLIOS = {"min_variance": "Candidate rule", "equal_weight": "Equal weight", "benchmark_60_40": "60/40"}
MODELS = {
    "historical": "Historical",
    "parametric_normal": "Normal",
    "monte_carlo_normal": "Normal Monte Carlo",
    "evt_pot": "Pure POT-GPD",
    "evt_body_tail_hybrid": "Body/tail hybrid",
}
SCENARIOS = {
    "gfc_2007_2009": "Global Financial Crisis",
    "covid_2020": "COVID-19 shock",
    "rate_shock_2022": "2022 rate shock",
    "hypothetical_stagflation_repricing": "Hypothetical stagflation",
}
KPIS = [
    ("geometric_annual_return", "Net CAGR", "pct"),
    ("annualized_volatility", "Annual volatility", "pct"),
    ("downside_deviation", "Downside deviation", "pct"),
    ("max_drawdown", "Maximum drawdown", "pct"),
    ("sharpe_ratio", "Sharpe ratio", "ratio"),
    ("sortino_ratio", "Sortino ratio", "ratio"),
    ("calmar_ratio", "Calmar ratio", "ratio"),
    ("capm_beta", "CAPM beta to SPY", "ratio"),
    ("jensen_alpha", "Jensen alpha, annual", "pct"),
    ("treynor_ratio", "Treynor ratio", "ratio"),
    ("tracking_error", "Tracking error to 60/40", "pct"),
    ("information_ratio", "Information ratio to 60/40", "ratio"),
]


def tex_escape(text: object) -> str:
    """Escape LaTeX special characters in plain text."""
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in str(text))


def signed(text: str) -> str:
    return text.replace("-", MINUS)


def pct(value: float | None, digits: int = 2) -> str:
    return NA if value is None else signed(f"{value * 100:.{digits}f}") + r"\%"


def pct_cell(value: float | None, digits: int = 2) -> str:
    """Percent value for a decimal-aligned table column whose header carries the unit."""
    return "{" + NA + "}" if value is None else f"{value * 100:.{digits}f}"


def usd(value: float | None) -> str:
    if value is None:
        return NA
    return (MINUS if value < 0 else "") + r"\$" + f"{abs(value):,.0f}"


def number(value: float | None, digits: int = 2) -> str:
    return NA if value is None else signed(f"{value:.{digits}f}")


def pvalue(value: float | None) -> str:
    """Scientific notation for tiny p-values, never rounded down to zero."""
    if value is None:
        return NA
    if value == 0:
        return r"$<10^{-300}$"
    if value >= 0.001:
        return f"{value:.3f}"
    mantissa, exponent = f"{value:.1e}".split("e")
    return rf"${mantissa}\times10^{{{int(exponent)}}}$"


def long_date(text: str) -> str:
    day = date.fromisoformat(text[:10])
    return f"{day.day} {day.strftime('%B %Y')}"


def short_date(text: str) -> str:
    day = date.fromisoformat(text[:10])
    return f"{day.day} {day.strftime('%b %Y')}"


class Metrics:
    """Collect macros together with the raw value each one must reproduce."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.manifest: dict[str, dict] = {}

    def add(self, name: str, tex: str, value: float | str | None, source: str, kind: str) -> None:
        if not re.fullmatch(r"qe[A-Za-z]+", name):
            raise ValueError(f"Invalid macro name: {name}")
        if name in self.manifest:
            raise ValueError(f"Duplicate macro: {name}")
        self.lines.append(rf"\newcommand{{\{name}}}{{{tex}}}")
        self.manifest[name] = {"tex": tex, "value": value, "source": source, "kind": kind}

    def percent(self, name: str, value: float, source: str, digits: int = 2) -> None:
        self.add(name, pct(value, digits), value, source, f"percent{digits}")

    def dollars(self, name: str, value: float, source: str) -> None:
        self.add(name, usd(value), value, source, "usd")

    def plain(self, name: str, value: float, source: str, digits: int = 2) -> None:
        self.add(name, number(value, digits), value, source, f"number{digits}")

    def count(self, name: str, value: int, source: str) -> None:
        self.add(name, f"{value:,}", value, source, "count")

    def text(self, name: str, value: str, source: str) -> None:
        self.add(name, tex_escape(value), value, source, "text")


def table(path: str, columns: str, header: list[str], rows: list[list[str]], *, midrules: tuple[int, ...] = (), lead: str = "") -> None:
    """Write one booktabs tabular. Rows hold already-formatted LaTeX cells."""
    lines = [rf"\begin{{tabular}}{{{columns}}}", r"\toprule"]
    if lead:
        lines.append(lead)
    lines += [" & ".join(header) + r" \\", r"\midrule"]
    for index, row in enumerate(rows):
        if index in midrules:
            lines.append(r"\midrule")
        lines.append(" & ".join(row) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", ""]
    (TABLES / f"{path}.tex").write_text("\n".join(lines), encoding="utf-8")


def head(text: str) -> str:
    return "{" + text + "}"


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    ref = json.loads((ROOT / "results/final/reference.json").read_text(encoding="utf-8"))
    coverage = json.loads((ROOT / "data/reference/rf_evidence/evidence_coverage.json").read_text(encoding="utf-8"))
    dataset = ref["metadata"]["dataset_id"]
    flags = pd.read_parquet(ROOT / f"data/processed/{dataset}/quality_flags.parquet")
    manifest = json.loads((ROOT / f"data/processed/{dataset}/manifest.json").read_text(encoding="utf-8"))
    proposal, limits = ref["proposal"], ref["proposal"]["risk_limits"]
    nav = 10_000_000.0

    def kpi(period: str, portfolio: str, metric: str) -> float | None:
        return next(x["value"] for x in ref["period_kpis"]
                    if x["period"] == period and x["portfolio_id"] == portfolio and x["metric"] == metric)

    def risk(window: str, model: str, confidence: float) -> dict:
        return next(x for x in ref["risk_table"]
                    if x["window_id"] == window and x["model"] == model and x["confidence"] == confidence)

    def stress(portfolio: str, scenario: str) -> dict:
        return next(x for x in ref["stress_results"] if x["portfolio_id"] == portfolio and x["scenario_id"] == scenario)

    def cover(period: str, model: str, confidence: float) -> dict:
        return next(x for x in ref["coverage_summary"]
                    if x["period"] == period and x["model"] == model and x["confidence"] == confidence)

    def context(kind: str, metric: str) -> float:
        return next(x["value"] for x in ref["context"][kind]["min_variance"] if x["metric"] == metric)

    m = Metrics()
    m.text("qeBundle", ref["metadata"]["bundle_id"], "metadata.bundle_id")
    m.text("qeDataset", dataset, "metadata.dataset_id")
    m.text("qeConfigHash", ref["metadata"]["config_hash"], "metadata.config_hash")
    m.text("qeProtocolCommit", ref["diagnostics"]["protocol_commit"], "diagnostics.protocol_commit")

    # Mandate
    m.percent("qeHurdle", proposal["required_nominal_return_fraction"], "proposal.required_nominal_return_fraction")
    m.percent("qeSpending", proposal["spending_annual_fraction"], "proposal.spending_annual_fraction")
    m.percent("qeInflation", proposal["inflation_assumption_annual_fraction"], "proposal.inflation_assumption_annual_fraction")
    m.percent("qeFee", proposal["additional_fee_assumption_annual_fraction"], "proposal.additional_fee_assumption_annual_fraction")
    m.percent("qeRealGrowth", proposal["desired_real_growth_annual_fraction"], "proposal.desired_real_growth_annual_fraction")
    m.count("qeHorizon", proposal["investment_horizon_years"], "proposal.investment_horizon_years")
    m.percent("qeBudgetVarNinetyFive", limits["max_daily_var_95_fraction"], "risk_limits.max_daily_var_95_fraction")
    m.percent("qeBudgetVar", limits["max_daily_var_99_fraction"], "risk_limits.max_daily_var_99_fraction")
    m.percent("qeBudgetEs", limits["max_daily_es_99_fraction"], "risk_limits.max_daily_es_99_fraction")
    m.percent("qeBudgetVol", limits["max_annual_volatility_fraction"], "risk_limits.max_annual_volatility_fraction")
    m.percent("qeBudgetDrawdown", limits["max_drawdown_fraction"], "risk_limits.max_drawdown_fraction")
    m.percent("qeBudgetScenario", limits["max_historical_scenario_loss_fraction"], "risk_limits.max_historical_scenario_loss_fraction")
    m.dollars("qeBudgetVarUsd", limits["max_daily_var_99_fraction"] * nav, "risk_limits.max_daily_var_99_fraction*NAV")
    m.dollars("qeBudgetEsUsd", limits["max_daily_es_99_fraction"] * nav, "risk_limits.max_daily_es_99_fraction*NAV")
    m.dollars("qeBudgetDrawdownUsd", limits["max_drawdown_fraction"] * nav, "risk_limits.max_drawdown_fraction*NAV")

    # Performance
    for label, period in (("Dev", "development"), ("Sel", "selection"), ("Eval", "evaluation"), ("Full", "full")):
        source = f"period_kpis[{period},min_variance]"
        m.percent(f"qe{label}Cagr", kpi(period, "min_variance", "geometric_annual_return"), source)
        m.percent(f"qe{label}Vol", kpi(period, "min_variance", "annualized_volatility"), source)
        m.percent(f"qe{label}Drawdown", kpi(period, "min_variance", "max_drawdown"), source)
        m.plain(f"qe{label}Sharpe", kpi(period, "min_variance", "sharpe_ratio"), source)
    m.percent("qeEvalCagrSixty", kpi("evaluation", "benchmark_60_40", "geometric_annual_return"), "period_kpis[evaluation,benchmark_60_40]")
    m.percent("qeEvalVolSixty", kpi("evaluation", "benchmark_60_40", "annualized_volatility"), "period_kpis[evaluation,benchmark_60_40]")
    m.percent("qeEvalDrawdownSixty", kpi("evaluation", "benchmark_60_40", "max_drawdown"), "period_kpis[evaluation,benchmark_60_40]")
    m.plain("qeEvalSharpeSixty", kpi("evaluation", "benchmark_60_40", "sharpe_ratio"), "period_kpis[evaluation,benchmark_60_40]")
    m.percent("qeEvalCagrEqual", kpi("evaluation", "equal_weight", "geometric_annual_return"), "period_kpis[evaluation,equal_weight]")
    m.plain("qeFullBeta", kpi("full", "min_variance", "capm_beta"), "period_kpis[full,min_variance]")
    m.percent("qeFullAlpha", kpi("full", "min_variance", "jensen_alpha"), "period_kpis[full,min_variance]")
    m.percent("qeEvalAlpha", kpi("evaluation", "min_variance", "jensen_alpha"), "period_kpis[evaluation,min_variance]")
    m.percent("qeHurdleGapDev", kpi("development", "min_variance", "geometric_annual_return") - proposal["required_nominal_return_fraction"],
              "development CAGR minus hurdle")

    # Income and inflation
    m.percent("qeIncomeYield", context("distribution_income", "ending_trailing_12m_distribution_yield"), "context.distribution_income")
    m.percent("qeIncomeMean", context("distribution_income", "mean_trailing_12m_distribution_yield"), "context.distribution_income")
    m.percent("qeRealReturn", context("ex_post_real_returns", "ex_post_real_annual_return_common_months"), "context.ex_post_real_returns")
    m.percent("qeCpiInflation", context("ex_post_real_returns", "ex_post_cpi_annual_inflation_common_months"), "context.ex_post_real_returns")
    sensitivity = {x["metric"]: x for x in ref["context"]["rf_sensitivity"]["min_variance"]}
    m.plain("qeSharpeAccrual", sensitivity["sharpe_ratio"]["accrual_91d_value"], "context.rf_sensitivity.sharpe_ratio", 3)
    m.plain("qeSharpePrimary", sensitivity["sharpe_ratio"]["primary_r3_value"], "context.rf_sensitivity.sharpe_ratio", 3)

    # Tail risk
    hs99, hs95 = risk("recent", "historical", 0.99), risk("recent", "historical", 0.95)
    full99 = risk("full_history", "historical", 0.99)
    normal99, mc99 = risk("recent", "parametric_normal", 0.99), risk("recent", "monte_carlo_normal", 0.99)
    pot99, fullpot = risk("recent", "evt_pot", 0.99), risk("full_history", "evt_pot", 0.99)
    m.percent("qeVar", hs99["var_loss"], "risk_table[recent,historical,0.99].var_loss")
    m.percent("qeEs", hs99["es_loss"], "risk_table[recent,historical,0.99].es_loss")
    m.dollars("qeVarUsd", hs99["var_usd"], "risk_table[recent,historical,0.99].var_usd")
    m.dollars("qeEsUsd", hs99["es_usd"], "risk_table[recent,historical,0.99].es_usd")
    m.dollars("qeVarExcess", hs99["var_usd"] - limits["max_daily_var_99_fraction"] * nav, "VaR USD minus budget USD")
    m.dollars("qeEsExcess", hs99["es_usd"] - limits["max_daily_es_99_fraction"] * nav, "ES USD minus budget USD")
    m.percent("qeVarNinetyFive", hs95["var_loss"], "risk_table[recent,historical,0.95].var_loss")
    m.percent("qeNormalVarNinetyFive", risk("recent", "parametric_normal", 0.95)["var_loss"], "risk_table[recent,parametric_normal,0.95].var_loss")
    m.percent("qeFullVar", full99["var_loss"], "risk_table[full_history,historical,0.99].var_loss")
    m.percent("qeFullEs", full99["es_loss"], "risk_table[full_history,historical,0.99].es_loss")
    m.dollars("qeFullEsUsd", full99["es_usd"], "risk_table[full_history,historical,0.99].es_usd")
    m.percent("qeNormalVar", normal99["var_loss"], "risk_table[recent,parametric_normal,0.99].var_loss")
    m.percent("qeNormalEs", normal99["es_loss"], "risk_table[recent,parametric_normal,0.99].es_loss")
    m.percent("qeMcVar", mc99["var_loss"], "risk_table[recent,monte_carlo_normal,0.99].var_loss")
    m.percent("qePotEs", pot99["es_loss"], "risk_table[recent,evt_pot,0.99].es_loss")
    m.percent("qePotVar", pot99["var_loss"], "risk_table[recent,evt_pot,0.99].var_loss")
    m.percent("qeFullPotEs", fullpot["es_loss"], "risk_table[full_history,evt_pot,0.99].es_loss")
    m.count("qeMcDraws", int(mc99["monte_carlo_simulations"]), "risk_table monte_carlo_simulations")

    # Backtests
    hs_full, hs_eval = cover("full", "historical", 0.99), cover("evaluation", "historical", 0.99)
    nm_eval = cover("evaluation", "parametric_normal", 0.99)
    m.count("qeHsFullExceptions", hs_full["n_exceedances"], "coverage[full,historical,0.99]")
    m.count("qeFullSessions", hs_full["n_valid"], "coverage[full,historical,0.99]")
    m.add("qeHsFullUc", pvalue(hs_full["p_uc"]), hs_full["p_uc"], "coverage[full,historical,0.99].p_uc", "pvalue")
    m.add("qeHsFullInd", pvalue(hs_full["p_ind"]), hs_full["p_ind"], "coverage[full,historical,0.99].p_ind", "pvalue")
    m.add("qeHsEvalUc", pvalue(hs_eval["p_uc"]), hs_eval["p_uc"], "coverage[evaluation,historical,0.99].p_uc", "pvalue")
    m.add("qeHsEvalInd", pvalue(hs_eval["p_ind"]), hs_eval["p_ind"], "coverage[evaluation,historical,0.99].p_ind", "pvalue")
    m.count("qeHsEvalExceptions", hs_eval["n_exceedances"], "coverage[evaluation,historical,0.99]")
    m.count("qeNormalEvalExceptions", nm_eval["n_exceedances"], "coverage[evaluation,parametric_normal,0.99]")
    m.add("qeNormalEvalUc", pvalue(nm_eval["p_uc"]), nm_eval["p_uc"], "coverage[evaluation,parametric_normal,0.99].p_uc", "pvalue")
    m.count("qeEvalSessions", hs_eval["n_valid"], "coverage[evaluation,historical,0.99]")
    hs_basel, nm_basel = ref["basel"]["historical"], ref["basel"]["parametric_normal"]
    m.count("qeBaselHs", hs_basel["n_exceedances"], "basel.historical")
    m.count("qeBaselNormal", nm_basel["n_exceedances"], "basel.parametric_normal")
    m.text("qeBaselHsZone", hs_basel["zone"], "basel.historical.zone")
    m.text("qeBaselNormalZone", nm_basel["zone"], "basel.parametric_normal.zone")
    m.text("qeBaselStart", short_date(hs_basel["block_start"]), "basel.historical.block_start")
    m.text("qeBaselEnd", short_date(hs_basel["block_end"]), "basel.historical.block_end")
    m.add("qeBaselExpected", number(hs_basel["expected_exceedances"], 1), hs_basel["expected_exceedances"], "basel.historical", "number1")

    # Risk contributions, drift and stress
    es_share = {x["ticker"]: x for x in ref["risk_contributions"]["historical_es"]}
    for ticker, label in (("SPY", "Spy"), ("AGG", "Agg"), ("GLD", "Gld"), ("XLE", "Xle")):
        m.percent(f"qeWeight{label}", es_share[ticker]["weight"], f"current_weights.{ticker}", 1)
        m.percent(f"qeShare{label}", es_share[ticker]["pct_contribution"], f"risk_contributions.historical_es.{ticker}", 1)
    drift = ref["diagnostics"]["drift"]
    m.count("qeDriftSessions", drift["n_breach_sessions"], "diagnostics.drift.n_breach_sessions")
    m.count("qeActiveSessions", drift["n_active_sessions"], "diagnostics.drift.n_active_sessions")
    m.percent("qeDriftMax", drift["max_exposures"]["max_single_etf_weight"], "diagnostics.drift.max_exposures", 2)
    m.text("qeDriftTicker", drift["max_exposures"]["max_single_etf_ticker"], "diagnostics.drift.max_exposures")
    m.text("qeDriftDate", short_date(drift["max_exposures"]["max_single_etf_date"]), "diagnostics.drift.max_exposures")
    m.percent("qeDriftEquity", drift["max_exposures"]["max_equity_group_weight"], "diagnostics.drift.max_exposures", 2)
    for label, scenario in (("Gfc", "gfc_2007_2009"), ("Covid", "covid_2020"), ("Rates", "rate_shock_2022"), ("Hypo", "hypothetical_stagflation_repricing")):
        row, reference = stress("min_variance", scenario), stress("benchmark_60_40", scenario)
        m.percent(f"qe{label}Return", row["total_return"], f"stress[{scenario}].total_return")
        m.percent(f"qe{label}Drawdown", row["max_drawdown"], f"stress[{scenario}].max_drawdown")
        m.dollars(f"qe{label}Usd", row["usd_loss"], f"stress[{scenario}].usd_loss")
        m.percent(f"qe{label}ReturnSixty", reference["total_return"], f"stress[{scenario},60/40].total_return")
        m.percent(f"qe{label}DrawdownSixty", reference["max_drawdown"], f"stress[{scenario},60/40].max_drawdown")

    # Data facts
    counts = flags["rule"].value_counts()
    m.count("qeFlags", len(flags), "quality_flags rows")
    m.count("qeFlagNegative", int(counts["large_negative_return"]), "quality_flags")
    m.count("qeFlagJump", int(counts["robust_mad_jump"]), "quality_flags")
    m.count("qeFlagBreak", int(counts["candidate_structural_break"]), "quality_flags")
    m.count("qePriceSessions", manifest["row_exclusions"]["n_price_grid_sessions"], "manifest.row_exclusions")
    m.count("qeReturnSessions", manifest["row_exclusions"]["n_complete_return_rows"], "manifest.row_exclusions")
    m.count("qeMissingCells", manifest["row_exclusions"]["n_missing_price_cells"], "manifest.row_exclusions")
    m.count("qeVintages", coverage["published_vintages"], "evidence_coverage.published_vintages")
    m.count("qeRfObservations", coverage["observations"], "evidence_coverage.observations")
    m.count("qeRfSupported", coverage["initial_by_tier"]["vintage_supported"], "evidence_coverage.initial_by_tier")
    m.count("qeRfInferred", coverage["initial_by_tier"]["inferred"], "evidence_coverage.initial_by_tier")
    m.count("qeRfFallback", coverage["initial_by_tier"]["calendar_fallback"], "evidence_coverage.initial_by_tier")
    m.count("qeRfDocumented", coverage["initial_by_tier"]["documented"], "evidence_coverage.initial_by_tier")
    m.count("qeRfUnresolved", coverage["initial_by_tier"]["unresolved"], "evidence_coverage.initial_by_tier")

    # Derived presentation values and EVT evidence
    m.add("qeHurdleGapDevAbs", number(proposal["required_nominal_return_fraction"] * 100 - kpi("development", "min_variance", "geometric_annual_return") * 100, 2),
          proposal["required_nominal_return_fraction"] * 100 - kpi("development", "min_variance", "geometric_annual_return") * 100, "hurdle minus development CAGR, pct points", "number2")
    income_gap = proposal["spending_annual_fraction"] - context("distribution_income", "ending_trailing_12m_distribution_yield")
    m.dollars("qeIncomeGapUsd", income_gap * nav, "(spending minus ending yield) * NAV; illustrative")
    evt = {(d["window_id"], d["candidate_quantile"]): d for d in ref["evt_diagnostics"]}
    m.add("qeEvtRecentXi", number(evt[("recent", 0.95)]["xi"], 3), evt[("recent", 0.95)]["xi"], "evt_diagnostics[recent,0.95].xi", "number3")
    m.add("qeEvtFullXi", number(evt[("full_history", 0.95)]["xi"], 3), evt[("full_history", 0.95)]["xi"], "evt_diagnostics[full,0.95].xi", "number3")
    m.count("qeEvtRecentN", evt[("recent", 0.95)]["n_exceedances"], "evt_diagnostics[recent,0.95]")
    m.count("qeEvtFullN", evt[("full_history", 0.95)]["n_exceedances"], "evt_diagnostics[full,0.95]")
    m.count("qeEvtSparseN", evt[("recent", 0.975)]["n_exceedances"], "evt_diagnostics[recent,0.975]")
    boot = pd.read_csv(ROOT / "results/step7_evt_preview/tables/table_03_bootstrap_uncertainty.csv")
    full_dev = boot[(boot.window_id == "full_development_3020d") & (boot.confidence.round(2) == 0.99) & (boot.method == "pure_pot")].iloc[0]
    sparse_dev = boot[(boot.window_id == "full_development_3020d") & (boot.confidence.round(2) == 0.95) & (boot.method == "pure_pot")].iloc[0]
    m.percent("qeDevBootVarLow", float(full_dev.var_p025), "step7 table_03 full_development 0.99 pure_pot var_p025")
    m.percent("qeDevBootVarHigh", float(full_dev.var_p975), "step7 table_03 full_development 0.99 pure_pot var_p975")
    m.percent("qeDevBootEsLow", float(full_dev.es_p025), "step7 table_03 full_development 0.99 pure_pot es_p025")
    m.percent("qeDevBootEsHigh", float(full_dev.es_p975), "step7 table_03 full_development 0.99 pure_pot es_p975")
    m.count("qeDevBootFinite", int(sparse_dev.n_var_available), "step7 table_03 full_development 0.95 pure_pot")
    period_basel = {(x["period"], x["model"]): x["basel"] for x in ref["diagnostics"]["period_backtests"] if x["confidence"] == 0.99}
    m.count("qeBaselSelHs", period_basel[("selection", "historical")]["n_exceedances"], "period_backtests[selection,historical].basel")
    m.count("qeBaselSelNormal", period_basel[("selection", "parametric_normal")]["n_exceedances"], "period_backtests[selection,parametric_normal].basel")
    hs_selection = cover("selection", "historical", 0.99)
    m.add("qeHsSelInd", pvalue(hs_selection["p_ind"]), hs_selection["p_ind"], "coverage[selection,historical,0.99].p_ind", "pvalue")
    m.add("qeHsFullExpected", number(hs_full["n_valid"] * 0.01, 1), hs_full["n_valid"] * 0.01, "n_valid * 0.01", "number1")
    m.add("qeHsEvalExpected", number(hs_eval["n_valid"] * 0.01, 1), hs_eval["n_valid"] * 0.01, "n_valid * 0.01", "number1")
    equal_row = next(x for x in ref["allocation_comparisons"] if x["candidate_id"] == "equal_weight")
    sixty_row = next(x for x in ref["allocation_comparisons"] if x["candidate_id"] == "benchmark_60_40")
    m.percent("qeAllocEqualEs", equal_row["es_loss"], "allocation_comparisons[equal_weight].es_loss")
    m.percent("qeAllocSixtyEs", sixty_row["es_loss"], "allocation_comparisons[benchmark_60_40].es_loss")

    # Tables
    budget_rows = []

    def budget(label: str, basis: str, value: float, cap: float, *, excess_usd: bool = True) -> None:
        gap = value - cap
        excess = (usd(gap * nav) if excess_usd else pct(gap)) if gap > 0 else "---"
        status = r"\qeabove" if gap > 0 else r"\qewithin"
        budget_rows.append([label, basis, pct_cell(value), pct_cell(cap), excess, status])

    budget("VaR 95\\%, recent", "1 day; 1,260 sessions", hs95["var_loss"], limits["max_daily_var_95_fraction"])
    budget("VaR 99\\%, recent", "1 day; 1,260 sessions", hs99["var_loss"], limits["max_daily_var_99_fraction"])
    budget("ES 99\\%, recent", "1 day; 1,260 sessions", hs99["es_loss"], limits["max_daily_es_99_fraction"])
    budget("VaR 99\\%, full history", "1 day; 5,491 sessions", full99["var_loss"], limits["max_daily_var_99_fraction"])
    budget("ES 99\\%, full history", "1 day; 5,491 sessions", full99["es_loss"], limits["max_daily_es_99_fraction"])
    budget("Annual volatility", "Evaluation path", kpi("evaluation", "min_variance", "annualized_volatility"), limits["max_annual_volatility_fraction"], excess_usd=False)
    budget("Maximum drawdown", "Evaluation path", -kpi("evaluation", "min_variance", "max_drawdown"), limits["max_drawdown_fraction"], excess_usd=False)
    budget("Maximum drawdown", "Development path", -kpi("development", "min_variance", "max_drawdown"), limits["max_drawdown_fraction"], excess_usd=False)
    budget("Crisis drawdown", "GFC, current target", -stress("min_variance", "gfc_2007_2009")["max_drawdown"], limits["max_drawdown_fraction"], excess_usd=False)
    budget("Crisis endpoint loss", "COVID-19, current target", -stress("min_variance", "covid_2020")["total_return"], limits["max_historical_scenario_loss_fraction"], excess_usd=False)
    table("budgets", "@{}llS[table-format=2.2]S[table-format=2.2]rl@{}",
          ["Measure", "Basis", head("Estimate (\\%)"), head("Budget (\\%)"), "Excess", "Status"], budget_rows)

    rows = []
    for period, label in (("development", "Development"), ("selection", "Selection"), ("evaluation", "Evaluation")):
        sample = next(x for x in ref["period_kpis"] if x["period"] == period)
        for portfolio, name in PORTFOLIOS.items():
            rows.append([label if portfolio == "min_variance" else "", name,
                         pct_cell(kpi(period, portfolio, "geometric_annual_return")),
                         pct_cell(kpi(period, portfolio, "annualized_volatility")),
                         pct_cell(kpi(period, portfolio, "max_drawdown")),
                         f"{kpi(period, portfolio, 'sharpe_ratio'):.2f}",
                         f"{sample['n_sessions']:,}" if portfolio == "min_variance" else ""])
    table("periods", "@{}llS[table-format=2.2]S[table-format=2.2]S[table-format=-2.2]S[table-format=1.2]r@{}",
          ["Period", "Portfolio", head("CAGR (\\%)"), head("Vol.\\ (\\%)"), head("Max DD (\\%)"), head("Sharpe"), "Sessions"], rows, midrules=(3, 6))

    rows = []
    for metric, label, kind in KPIS:
        values = [kpi("full", p, metric) for p in PORTFOLIOS]
        rows.append([label, *[("{" + NA + "}" if v is None else (f"{v * 100:.2f}" if kind == "pct" else f"{v:.2f}")) for v in values]])
        rows[-1][0] += r" (\%)" if kind == "pct" else ""
    table("kpis", "@{}lS[table-format=-2.2]S[table-format=-2.2]S[table-format=-2.2]@{}",
          ["Full active history", *[head(n) for n in PORTFOLIOS.values()]], rows)

    rows = []
    for model, label in MODELS.items():
        row = [label]
        for window in ("recent", "full_history"):
            for confidence in (0.95, 0.99):
                item = risk(window, model, confidence)
                row += [pct_cell(item["var_loss"]), pct_cell(item["es_loss"])]
        rows.append(row)
    lead = (r" & \multicolumn{4}{c}{Recent 1,260 sessions} & \multicolumn{4}{c@{}}{Full 5,491 sessions} \\"
            r" \cmidrule(lr){2-5}\cmidrule(l){6-9}"
            r" & \multicolumn{2}{c}{95\%} & \multicolumn{2}{c}{99\%} & \multicolumn{2}{c}{95\%} & \multicolumn{2}{c@{}}{99\%} \\")
    table("risk", "@{}l" + "S[table-format=1.2]" * 8 + "@{}",
          ["\\% of NAV", *[head(x) for x in ("VaR", "ES") * 4]], rows, lead=lead)

    rows = []
    for d in ref["evt_diagnostics"]:
        rows.append(["Recent" if d["window_id"] == "recent" else "Full history", f"{d['candidate_quantile'] * 100:.1f}",
                     f"{d['n_exceedances']:,}", number(d["xi"], 3), number(None if d["beta"] is None else d["beta"] * 100, 3),
                     number(None if d["modified_scale"] is None else d["modified_scale"] * 100, 3),
                     "Fitted" if d["status"] == "ok" else "Below 50 excesses"])
    table("evt", "@{}lrrrrrl@{}", ["Sample", "Quantile (\\%)", "Excesses", r"Shape $\xi$", r"Scale $\beta$ (\%)", "Modified scale (\\%)", "Status"], rows, midrules=(4,))

    rows = []
    for period, label in (("full", "Full active"), ("development", "Development"), ("selection", "Selection"), ("evaluation", "Evaluation")):
        for model, name in (("historical", "Historical"), ("parametric_normal", "Normal")):
            item = cover(period, model, 0.99)
            rows.append([label if model == "historical" else "", name, f"{item['n_valid']:,}", str(item["n_exceedances"]),
                         f"{item['n_valid'] * 0.01:.1f}", pvalue(item["p_uc"]), pvalue(item["p_ind"]), pvalue(item["p_cc"])])
    table("backtest", "@{}llrrrrrr@{}", ["99\\% VaR", "Model", "Sessions", "Exceptions", "Expected", "Kupiec $p$", "Indep.\\ $p$", "Cond.\\ $p$"], rows, midrules=(2, 4, 6))

    rows = []
    for period, label in (("development", "Development"), ("selection", "Selection"), ("evaluation", "Evaluation")):
        for model, name in (("historical", "Historical"), ("parametric_normal", "Normal")):
            basel = next(x for x in ref["diagnostics"]["period_backtests"]
                         if x["period"] == period and x["model"] == model and x["confidence"] == 0.99)["basel"]
            rows.append([label if model == "historical" else "", name, f"{short_date(basel['block_start'])} -- {short_date(basel['block_end'])}",
                         str(basel["n_exceedances"]), rf"\qezone{{{basel['zone']}}}"])
    table("basel", "@{}lllrl@{}", ["Period", "Model", "Final 250-session block", "Exceptions", "Zone"], rows, midrules=(2, 4))

    normal = {x["ticker"]: x for x in ref["risk_contributions"]["normal_es"]}
    rows = [[t, pct_cell(x["weight"], 1), pct_cell(x["marginal_risk"]), pct_cell(x["component_risk"]), pct_cell(x["pct_contribution"], 1),
             pct_cell(normal[t]["pct_contribution"], 1)] for t, x in es_share.items() if x["weight"] > 1e-6]
    total = next(iter(es_share.values()))["total_risk"]
    rows.append([r"\textit{Total}", "100.0", "", pct_cell(total), "100.0", "100.0"])
    table("contributions", "@{}lS[table-format=3.1]S[table-format=1.2]S[table-format=1.2]S[table-format=3.1]S[table-format=3.1]@{}",
          ["ETF", head("Weight (\\%)"), head("Marginal (\\%)"), head("Component (\\%)"), head("Hist.\\ share (\\%)"), head("Normal share (\\%)")], rows, midrules=(len(rows) - 1,))

    rows = []
    for item in ref["allocation_comparisons"]:
        rows.append([PORTFOLIOS[item["candidate_id"]], pct_cell(item["var_loss"]), pct_cell(item["es_loss"]),
                     r"\qewithin" if item["constraint_feasible"] else r"\qeabove", r"\qewithin" if item["risk_limits_met"] else r"\qeabove"])
    table("allocations", "@{}lS[table-format=1.2]S[table-format=1.2]ll@{}",
          ["Allocation", head("VaR 99 (\\%)"), head("ES 99 (\\%)"), "Target caps", "Tail budgets"], rows)

    rows = []
    for scenario, label in SCENARIOS.items():
        a, b = stress("min_variance", scenario), stress("benchmark_60_40", scenario)
        rows.append([label, pct_cell(a["total_return"]), pct_cell(a["max_drawdown"]), usd(a["usd_loss"]), pct_cell(b["total_return"]), pct_cell(b["max_drawdown"])])
    lead = r" & \multicolumn{3}{c}{Candidate target} & \multicolumn{2}{c@{}}{60/40} \\ \cmidrule(lr){2-4}\cmidrule(l){5-6}"
    table("stress", "@{}lS[table-format=-2.2]S[table-format=-2.2]rS[table-format=-2.2]S[table-format=-2.2]@{}",
          ["Scenario", head("Endpoint (\\%)"), head("Drawdown (\\%)"), "Endpoint loss", head("Endpoint (\\%)"), head("Drawdown (\\%)")], rows, lead=lead)

    # Tear sheet tables
    weights = pd.DataFrame(ref["current_weights"]).set_index("ticker")
    table("tear_weights", "@{}lS[table-format=2.1]S[table-format=2.1]@{}", ["ETF", head("Target (\\%)"), head("ES share (\\%)")],
          [[t, pct_cell(weights.at[t, "min_variance"], 1), pct_cell(es_share[t]["pct_contribution"], 1)]
           for t in weights.index if weights.at[t, "min_variance"] > 1e-6])
    rows = []
    for metric, label, digits in (("geometric_annual_return", "Net CAGR", "pct"), ("annualized_volatility", "Volatility", "pct"),
                                  ("max_drawdown", "Max drawdown", "pct"), ("sharpe_ratio", "Sharpe", "ratio")):
        rows.append([label + (r" (\%)" if digits == "pct" else ""),
                     *[(f"{kpi(p, q, metric) * 100:.2f}" if digits == "pct" else f"{kpi(p, q, metric):.2f}")
                       for p, q in (("development", "min_variance"), ("selection", "min_variance"), ("evaluation", "min_variance"), ("evaluation", "benchmark_60_40"))]])
    table("tear_performance", "@{}lS[table-format=-2.2]S[table-format=-2.2]S[table-format=-2.2]S[table-format=-2.2]@{}",
          ["", head("2007--16"), head("2017--20"), head("2021--26"), head("60/40")], rows)

    trigger_labels = {
        "HS99 ES": ("Historical ES 99\\%, one day", pct),
        "drawdown": ("Drawdown from peak", pct),
        "max_equity_weight": ("Total equity weight", pct),
        "quarterly model independence test": ("Quarterly independence test", lambda v: f"$p<{v}$"),
    }
    rows = [[trigger_labels[x["metric"]][0], trigger_labels[x["metric"]][1](x["threshold"]),
             tex_escape(x["action"]).replace("below0.05", "below 0.05")] for x in proposal["monitoring"]]
    table("monitoring", r"@{}p{0.27\textwidth}rp{0.56\textwidth}@{}", ["Metric", "Threshold", "Proposed response"], rows)

    header = ["% Generated by scripts/generate_report_data.py from the verified reference. Do not edit.", ""]
    (OUT / "metrics.tex").write_text("\n".join([*header, *m.lines, ""]), encoding="utf-8")
    (OUT / "metrics_manifest.json").write_text(json.dumps(m.manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(m.manifest)} macros, {len(list(TABLES.glob('*.tex')))} tables")


if __name__ == "__main__":
    main()
