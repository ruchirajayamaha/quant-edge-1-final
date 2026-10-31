"""AI-assisted verification of the presentation upgrade. This is not human validation.

Recomputes representative values from frozen inputs by routes that avoid the production helpers,
compares every generated macro and key table with the verified reference, checks the compiled PDFs,
and writes audit/presentation_review/verification.json.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from statistics import NormalDist
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp/report_deps"))
OUT = Path(__file__).with_name("verification.json")
GENERATED = ROOT / "report/latex/generated"
REF = json.loads((ROOT / "results/final/reference.json").read_text(encoding="utf-8"))
DATASET = REF["metadata"]["dataset_id"]
MINUS = "\N{MINUS SIGN}"


def kpi(period: str, metric: str, portfolio: str = "min_variance") -> float:
    return next(x["value"] for x in REF["period_kpis"]
                if x["period"] == period and x["portfolio_id"] == portfolio and x["metric"] == metric)


def risk(window: str, model: str, confidence: float) -> dict:
    return next(x for x in REF["risk_table"] if x["window_id"] == window and x["model"] == model and x["confidence"] == confidence)


def independent_recomputation() -> list[dict]:
    """Plain-Python routes from original frozen files; no quantedge helper is called."""
    returns = pd.read_parquet(ROOT / f"data/processed/{DATASET}/simple_returns.parquet")
    tickers = list(returns.columns)
    rows = {str(day.date()): dict(zip(tickers, values)) for day, values in zip(returns.index, returns.to_numpy().tolist())}
    target = {x["ticker"]: x["min_variance"] for x in REF["current_weights"]}
    held = pd.read_csv(ROOT / "results/final/weights_before_min_variance.csv").set_index("date")
    daily = pd.read_csv(ROOT / "results/final/daily_performance.csv")
    results = []

    def record(name: str, inputs: str, method: str, computed: float, reference: float, tolerance: float) -> None:
        results.append({"check": name, "inputs": inputs, "method": method, "computed": computed, "reference": reference,
                        "absolute_difference": abs(computed - reference), "tolerance": tolerance,
                        "passed": abs(computed - reference) <= tolerance})

    day = "2026-10-29"
    value = sum(float(held.at[day, t]) * rows[day][t] for t in tickers)
    stored = daily[(daily.portfolio_id == "min_variance") & (daily.date == day)].net_return.iloc[0]
    record("One-day portfolio return", f"weights_before row {day}; simple_returns row {day}", "Explicit sum of weight times return in a Python loop", value, float(stored), 1e-12)

    path = daily[(daily.portfolio_id == "min_variance") & (daily.date >= "2021-01-04")].net_return.tolist()
    log_sum, wealth, peak, worst = 0.0, 1.0, 1.0, 0.0
    for item in path:
        log_sum += math.log1p(item)
        wealth *= 1 + item
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1)
    record("Evaluation CAGR", "daily_performance net_return from 2021-01-04", "Sum of log1p, annualised at 252, in a Python loop",
           math.expm1(log_sum * 252 / len(path)), kpi("evaluation", "geometric_annual_return"), 1e-11)
    record("Evaluation maximum drawdown", "daily_performance net_return from 2021-01-04", "Running peak from starting wealth 1 in a Python loop",
           worst, kpi("evaluation", "max_drawdown"), 1e-11)

    days = list(rows)[-1260:]
    losses = [-sum(target[t] * rows[d][t] for t in tickers) for d in days]
    mean = sum(losses) / len(losses)
    variance = sum((x - mean) ** 2 for x in losses) / (len(losses) - 1)
    record("Recent Normal VaR 99%", "last 1,260 simple_returns; reference target weights", "statistics.NormalDist quantile; hand variance, ddof 1",
           mean + NormalDist().inv_cdf(0.99) * math.sqrt(variance), risk("recent", "parametric_normal", 0.99)["var_loss"], 1e-12)
    ordered = sorted(losses, reverse=True)
    record("Recent Historical ES 99%", "same 1,260 losses", "Exact tail mass 12.6: first 12 plus 0.6 of the 13th",
           (sum(ordered[:12]) + 0.6 * ordered[12]) / 12.6, risk("recent", "historical", 0.99)["es_loss"], 1e-12)

    gfc = [d for d in rows if "2007-10-09" <= d <= "2009-03-09"]
    holdings = {t: target[t] * 10_000_000 for t in tickers}
    nav_path = [sum(holdings.values())]
    for d in gfc:
        holdings = {t: holdings[t] * (1 + rows[d][t]) for t in tickers}
        nav_path.append(sum(holdings.values()))
    reference = next(x for x in REF["stress_results"] if x["portfolio_id"] == "min_variance" and x["scenario_id"] == "gfc_2007_2009")
    record("GFC endpoint USD loss", "simple_returns 2007-10-09 to 2009-03-09; reference target weights", "Dollar holdings compounded session by session",
           10_000_000 - nav_path[-1], reference["usd_loss"], 1e-6)
    high, deepest = nav_path[0], 0.0
    for nav in nav_path:
        high = max(high, nav)
        deepest = min(deepest, nav / high - 1)
    record("GFC within-scenario drawdown", "same dollar path", "Running peak on the dollar path", deepest, reference["max_drawdown"], 1e-11)

    proposal = REF["proposal"]
    record("Return hurdle", "mandate_proposal.json", "(1+i)(1+g)-1+s+f", (1 + proposal["inflation_assumption_annual_fraction"]) * (1 + proposal["desired_real_growth_annual_fraction"]) - 1
           + proposal["spending_annual_fraction"] + proposal["additional_fee_assumption_annual_fraction"], proposal["required_nominal_return_fraction"], 1e-12)

    def plain_es(losses: list[float]) -> float:
        """Average the worst 1% of probability mass, including the fractional session."""
        ordered, mass, total = sorted(losses, reverse=True), 0.01 * len(losses), 0.0
        for index, loss in enumerate(ordered):
            take = min(1.0, mass - index)
            if take <= 0:
                break
            total += take * loss
        return total / mass

    last_rows = [rows[key] for key in sorted(rows)[-1260:]]
    own_es = sum(target[t] * plain_es([-row[t] for row in last_rows]) for t in tickers)
    manifest = json.loads((GENERATED / "metrics_manifest.json").read_text(encoding="utf-8"))
    record("Weighted own ES for diversification", "simple_returns last 1,260 sessions; reference target weights",
           "Sorted losses per ETF, fractional 12.6-session tail, weighted sum", own_es, manifest["qeDivWeighted"]["value"], 1e-12)

    exceptions = pd.read_csv(ROOT / "results/final/backtest_historical_0.99.csv")
    last = exceptions.tail(250)
    record("Final 250 Historical 99% exceptions", "backtest_historical_0.99.csv", "Count realized_loss > forecast_var directly",
           float((last.realized_loss > last.forecast_var).sum()), float(REF["basel"]["historical"]["n_exceedances"]), 0)
    record("Chronology: training ends before target", "backtest_historical_0.99.csv", "Maximum of train_end minus date, in days",
           float((pd.to_datetime(exceptions.train_end) >= pd.to_datetime(exceptions.date)).sum()), 0.0, 0)
    return results


def parse_macro(tex: str) -> float:
    text = tex.replace(r"\%", "").replace(r"\$", "").replace(",", "").replace(MINUS, "-").strip()
    match = re.fullmatch(r"\$(-?[\d.]+)\\times10\^\{(-?\d+)\}\$", text)
    return float(match.group(1)) * 10 ** int(match.group(2)) if match else float(text)


def macros_match_reference() -> dict:
    """Every numeric macro must equal its stored value to the printed precision."""
    manifest = json.loads((GENERATED / "metrics_manifest.json").read_text(encoding="utf-8"))
    failures, checked = [], 0
    for name, entry in manifest.items():
        kind, value, tex = entry["kind"], entry["value"], entry["tex"]
        if kind == "text":
            continue
        checked += 1
        shown = parse_macro(tex)
        if kind.startswith("percent"):
            allowed = 0.5 * 10 ** (-int(kind[-1])) + 1e-9
            ok = abs(shown - value * 100) <= allowed
        elif kind == "usd":
            ok = abs(shown - value) <= 0.5 + 1e-6
        elif kind == "count":
            ok = shown == value
        elif kind.startswith("number"):
            ok = abs(shown - value) <= 0.5 * 10 ** (-int(kind[-1])) + 1e-9
        else:  # pvalue: compare on a two-significant-figure basis
            ok = (abs(shown - value) <= 0.0005 + 1e-9) if value >= 0.001 else (abs(shown / value - 1) <= 0.05)
        if not ok:
            failures.append(name)

    expected = {
        "qeEvalCagr": kpi("evaluation", "geometric_annual_return"), "qeEvalVol": kpi("evaluation", "annualized_volatility"),
        "qeEvalDrawdown": kpi("evaluation", "max_drawdown"), "qeDevCagr": kpi("development", "geometric_annual_return"),
        "qeVar": risk("recent", "historical", 0.99)["var_loss"], "qeEs": risk("recent", "historical", 0.99)["es_loss"],
        "qeFullEs": risk("full_history", "historical", 0.99)["es_loss"],
    }
    regression = {
        "qeEvalCagr": 0.076336, "qeEvalVol": 0.088026, "qeEvalDrawdown": -0.167828, "qeDevCagr": 0.066534,
        "qeVar": 0.01539498, "qeEs": 0.02031689, "qeFullEs": 0.02501847,
    }
    regression_ok = {k: abs(expected[k] - v) < 1e-6 and abs(manifest[k]["value"] - expected[k]) < 1e-15 for k, v in regression.items()}
    return {"numeric_macros_checked": checked, "failures": failures, "prompt_regression_checkpoints": regression_ok}


def tables_match_reference() -> dict:
    """Rebuild expected cells separately and require each to appear in its generated table."""
    missing: dict[str, list[str]] = {}

    def check(table: str, cells: list[str]) -> None:
        text = (GENERATED / "tables" / f"{table}.tex").read_text(encoding="utf-8")
        tokens = re.findall(r"-?[\d,]*\.?\d+", text)
        absent = [c for c in cells if c not in tokens]
        if absent:
            missing[table] = absent

    check("risk", [f"{x * 100:.2f}" for row in REF["risk_table"] if row["confidence"] in (0.95, 0.99)
                   for x in (row["var_loss"], row["es_loss"]) if x is not None])
    check("stress", [f"{row['total_return'] * 100:.2f}" for row in REF["stress_results"]] + [f"{row['max_drawdown'] * 100:.2f}" for row in REF["stress_results"]])
    check("periods", [f"{kpi(p, m, q) * 100:.2f}" for p in ("development", "selection", "evaluation")
                      for q in ("min_variance", "equal_weight", "benchmark_60_40") for m in ("geometric_annual_return", "annualized_volatility", "max_drawdown")])
    check("backtest", [f"{row['n_exceedances']}" for row in REF["coverage_summary"] if row["confidence"] == 0.99])
    check("contributions", [f"{x['component_risk'] * 100:.2f}" for x in REF["risk_contributions"]["historical_es"] if x["weight"] > 1e-6])
    return {"tables_checked": 5, "missing_cells": missing}


def pdf_checks() -> dict:
    from pypdf import PdfReader

    limits = {"investment_memo.pdf": (7, 15), "tear_sheet.pdf": (1, 1), "recommendation.pdf": (1, 1)}
    paths = {"investment_memo.pdf": "01_Investment_Memo.pdf", "tear_sheet.pdf": "02_Executive_Tear_Sheet.pdf",
             "recommendation.pdf": "supporting/Recommendation.pdf"}
    headline = {
        "investment_memo.pdf": ["7.63%", "6.65%", "6.75%", "1.54%", "2.03%", "2.50%", "$3,950", "$3,169", "−8.93%", "−23.87%", "2,771", "45.14%", "2.19%"],
        "tear_sheet.pdf": ["7.63", "6.65", "$153,950", "$203,169", "$250,185", "−8.93%", "−23.87%", "2,771", "45.14%", "2.19%"],
        "recommendation.pdf": ["7.63%", "6.65%", "6.75%", "$153,950", "$203,169", "−8.93%", "−23.87%", "2,771", "2.19%"],
    }
    result = {}
    for name, (low, high) in limits.items():
        reader = PdfReader(ROOT / "FINAL_SUBMISSION" / paths[name])
        text = "".join(page.extract_text() for page in reader.pages)
        compact = re.sub(r"\s+", "", text)
        producer = str((reader.metadata or {}).get("/Producer", ""))
        fonts = set()
        for page in reader.pages:
            for font in (page.get("/Resources", {}).get("/Font", {}) or {}).values():
                fonts.add(str(font.get_object().get("/BaseFont", "")))
        result[name] = {
            "pages": len(reader.pages), "within_limit": low <= len(reader.pages) <= high, "producer": producer,
            "compiled_by_tex": "dvipdfmx" in producer.lower(), "reportlab": "reportlab" in producer.lower(),
            "missing_headlines": [h for h in headline[name] if h.replace(" ", "") not in compact],
            "contains_pending_status": "pending" in text.lower(), "font_families": sorted({f.split("+")[-1].split("-")[0] for f in fonts}),
        }
    return result


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    frozen = subprocess.run([sys.executable, str(ROOT / "scripts/freeze_presentation_baseline.py"), "verify"], capture_output=True, text=True)
    output = {
        "scope": "AI-assisted numerical, editorial and technical verification. Not independent human validation.",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bundle_id": REF["metadata"]["bundle_id"],
        "dataset_id": DATASET,
        "baseline_verify_exit_code": frozen.returncode,
        "baseline_verify_output": frozen.stdout.strip().splitlines(),
        "independent_recomputation": independent_recomputation(),
        "macros": macros_match_reference(),
        "tables": tables_match_reference(),
        "pdfs": pdf_checks(),
        "human_validation": "PENDING",
    }
    OUT.write_text(json.dumps(output, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    passed = sum(item["passed"] for item in output["independent_recomputation"])
    print(f"Recomputed {passed}/{len(output['independent_recomputation'])}; macros {output['macros']['numeric_macros_checked']} "
          f"failures {output['macros']['failures']}; regression {all(output['macros']['prompt_regression_checkpoints'].values())}; "
          f"tables missing {output['tables']['missing_cells']}; baseline exit {frozen.returncode}")
    for name, item in output["pdfs"].items():
        print(name, item["pages"], item["producer"][:44], "TeX" if item["compiled_by_tex"] else "NOT TEX", item["missing_headlines"], item["font_families"][:4])


if __name__ == "__main__":
    main()
