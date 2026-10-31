"""AI-run sweep of the real app, plus controls showing the presentation checks can fail.

Runs every view against every portfolio, confidence and risk method on the frozen results, then the
sample, rolling-model, short-range and empty-range states. Writes app_exercise.json. This is software
evidence only and is not independent human validation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import itertools
import json
from pathlib import Path
import shutil
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("app_exercise.json")
SCRATCH = ROOT / "tmp/presentation_controls"
sys.path.insert(0, str(ROOT / "app"))

import qe_theme as ui

VIEWS = ["Decision", "Performance", "Tail risk", "Backtesting", "Risk budget & stress", "Assumptions & Limitations"]


def text(app) -> str:
    return " ".join([m.value for m in app.markdown] + [c.value for c in app.caption] + [w.value for w in app.warning]
                    + [i.value for i in app.info])


def new_app():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(str(ROOT / "app/Home.py"), default_timeout=90).run()


def sweep() -> dict:
    app = new_app()
    runs, failures = 0, []

    def check(label: str) -> None:
        nonlocal runs
        runs += 1
        if app.exception or app.error:
            failures.append({"state": label, "messages": [e.value for e in list(app.exception) + list(app.error)]})

    check("initial")
    for view, portfolio, confidence, model in itertools.product(VIEWS, ui.PORTFOLIO_LABELS, (0.90, 0.95, 0.99), ui.MODEL_LABELS):
        app.sidebar.radio[0].set_value(view)
        app.sidebar.selectbox[0].set_value(portfolio)
        app.sidebar.select_slider[0].set_value(confidence)
        app.sidebar.selectbox[1].set_value(model)
        app.run(timeout=90)
        check(f"{view} | {portfolio} | {confidence} | {model}")

    states = {}
    app.sidebar.selectbox[0].set_value("min_variance")
    app.sidebar.selectbox[1].set_value("historical")
    app.sidebar.select_slider[0].set_value(0.99)
    app.sidebar.radio[0].set_value("Tail risk").run(timeout=90)
    check("Tail risk recent")
    states["recent_es_99"] = next(m for m in app.metric if m.label == "99% one-day ES").value
    app.radio[0].set_value("Full history").run(timeout=90)
    check("Tail risk full")
    states["full_es_99"] = next(m for m in app.metric if m.label == "99% one-day ES").value

    app.sidebar.select_slider[0].set_value(0.90)
    app.sidebar.radio[0].set_value("Tail risk").run(timeout=90)
    states["pot_90_unavailable"] = "Unavailable" in text(app)
    app.sidebar.select_slider[0].set_value(0.99)

    app.sidebar.radio[0].set_value("Backtesting").run(timeout=90)
    check("Backtesting Historical")
    states["historical_basel_final_250"] = "Green" in text(app)
    app.radio[0].set_value("parametric_normal").run(timeout=90)
    check("Backtesting Normal")
    states["normal_basel_final_250"] = "Yellow" in text(app)

    ranges = {"short": ("2026-10-01", "2026-10-30"), "empty": ("2021-01-09", "2021-01-10")}
    for name, (start, end) in ranges.items():
        app.sidebar.date_input[0].set_value((pd.Timestamp(start).date(), pd.Timestamp(end).date()))
        for view in VIEWS:
            app.sidebar.radio[0].set_value(view).run(timeout=90)
            check(f"{name} range | {view}")
    app.sidebar.radio[0].set_value("Backtesting")
    app.sidebar.date_input[0].set_value((pd.Timestamp("2026-10-01").date(), pd.Timestamp("2026-10-30").date())).run(timeout=90)
    states["short_range_basel_unavailable"] = "Unavailable for this range" in text(app)
    app.sidebar.date_input[0].set_value((pd.Timestamp("2021-01-09").date(), pd.Timestamp("2021-01-10").date())).run(timeout=90)
    states["empty_range_message"] = "No forecast targets fall in this range" in text(app)
    return {"app_runs": runs, "failures": failures, "states": states}


def controls() -> dict:
    """Corrupt scratch copies of generated numbers: each check must then report a failure."""
    spec = importlib.util.spec_from_file_location("verify_presentation", ROOT / "audit/presentation_review/verify_presentation.py")
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    shutil.copytree(ROOT / "report/latex/generated", SCRATCH)
    verify.GENERATED = SCRATCH

    clean_macros = verify.macros_match_reference()
    clean_tables = verify.tables_match_reference()

    path = SCRATCH / "metrics_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["qeEvalCagr"]["value"] += 0.0005
    path.write_text(json.dumps(manifest), encoding="utf-8")
    bad_macros = verify.macros_match_reference()

    table = SCRATCH / "tables/risk.tex"
    table.write_text(table.read_text(encoding="utf-8").replace("2.03", "1.93"), encoding="utf-8")
    bad_tables = verify.tables_match_reference()
    shutil.rmtree(SCRATCH)

    return {
        "clean_macro_failures": len(clean_macros["failures"]),
        "clean_table_missing": sum(len(v) for v in clean_tables["missing_cells"].values()),
        "macro_change_of_5bp_detected": bool(bad_macros["failures"]) or not all(bad_macros["prompt_regression_checkpoints"].values()),
        "table_cell_change_detected": bool(bad_tables["missing_cells"]),
    }


def main() -> None:
    tempfile.tempdir = str(ROOT / "tmp")
    swept = sweep()
    control = controls()
    OUT.write_text(json.dumps({
        "scope": "AI-run software evidence. Not independent human validation.",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sweep": swept,
        "controls": control,
    }, indent=1) + "\n", encoding="utf-8")
    print(swept["app_runs"], "app runs;", len(swept["failures"]), "failures")
    print(swept["states"])
    print(control)
    for item in swept["failures"][:8]:
        print(item)


if __name__ == "__main__":
    main()
