"""Redesigned decision room, LaTeX deliverables and the presentation build guards."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
(ROOT / "tmp").mkdir(exist_ok=True)

import qe_theme as ui


def _app():
    tempfile.tempdir = str(ROOT / "tmp")
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(str(ROOT / "app/Home.py"), default_timeout=60).run()


def _text(app) -> str:
    parts = [m.value for m in app.markdown] + [c.value for c in app.caption] + [w.value for w in app.warning] + [i.value for i in app.info]
    return " ".join(parts)


def test_formatters_keep_signs_units_and_unavailable_states():
    assert ui.usd(-892991.3) == "-$892,991"
    assert ui.usd(203168.86) == "$203,169"
    assert ui.pct(None) == ui.UNAVAILABLE and ui.usd(float("nan")) == ui.UNAVAILABLE
    assert ui.pct(-0.0893, 2) == "-8.93%"
    assert ui.pvalue(1.7e-05) == "1.7e-05" and ui.pvalue(0.394) == "0.394"
    assert ui.pvalue(None) == ui.UNAVAILABLE


def test_decision_screen_shows_decision_budgets_crisis_and_honest_status():
    app = _app()
    assert not app.exception and not app.error
    metrics = {m.label: m for m in app.metric}
    assert metrics["Proposed return hurdle"].value == "6.75%"
    assert metrics["Evaluation CAGR, 2021-2026"].value == "7.63%"
    assert "6.65%" in metrics["Evaluation CAGR, 2021-2026"].delta
    assert metrics["One-day ES at 99%, recent sample"].value == "$203,169"
    assert metrics["One-day ES at 99%, recent sample"].delta == "$3,169 above budget"
    assert metrics["Ending cash yield"].value == "2.19%"
    text = _text(app)
    for expected in ("Conditional", "$3,950", "Above budget", "-23.87%", "-8.93%", "-$892,991", "2,771", "pending"):
        assert expected in text, expected
    assert "approved by" not in text.lower().replace("no university committee has approved it", "")
    assert {button.label for button in app.get("download_button")} >= {"Investment memo", "One-page tear sheet", "Plain-English recommendation"}


def test_limitations_page_uses_the_official_label_and_keeps_review_status():
    app = _app()
    app.sidebar.radio[0].set_value("Assumptions & Limitations").run(timeout=60)
    assert not app.exception and not app.error
    text = _text(app)
    assert "## Assumptions & Limitations" in text
    assert "Independent human validation" in text and "Pending" in text
    assert "No real committee has approved it" in text


def test_tail_view_keeps_failures_explicit_and_samples_labelled():
    app = _app()
    app.sidebar.radio[0].set_value("Tail risk").run(timeout=60)
    app.sidebar.select_slider[0].set_value(0.90).run(timeout=60)
    app.sidebar.selectbox[1].set_value("evt_pot").run(timeout=60)
    assert not app.exception and not app.error
    assert any("EVT: pure POT-GPD" in w.value for w in app.warning)
    assert next(m for m in app.metric if m.label == "90% one-day VaR").value == ui.UNAVAILABLE
    assert "Unavailable" in _text(app)

    app.sidebar.select_slider[0].set_value(0.99).run(timeout=60)
    app.sidebar.selectbox[1].set_value("historical").run(timeout=60)
    recent = next(m for m in app.metric if m.label == "99% one-day ES").value
    assert recent == "2.03%" and "omits the GFC and COVID-19" in _text(app)
    app.radio[0].set_value("Full history").run(timeout=60)
    assert not app.exception
    assert next(m for m in app.metric if m.label == "99% one-day ES").value == "2.50%"
    assert next(m for m in app.metric if m.label == "Estimation sessions").value == "5,491"


def test_normal_monte_carlo_is_described_as_sampling_not_fat_tailed():
    app = _app()
    app.sidebar.radio[0].set_value("Tail risk").run(timeout=60)
    assert "not a fat-tail model" in _text(app)


def test_backtest_view_separates_rolling_model_basel_and_short_ranges():
    app = _app()
    app.sidebar.radio[0].set_value("Backtesting").run(timeout=60)
    assert not app.exception and not app.error
    assert next(m for m in app.metric if m.label == "Exceptions / sessions").value == "18 / 1,464"
    assert "Green" in _text(app)

    # A different selected confidence must not change the 99%/250 Basel diagnostic.
    app.sidebar.select_slider[0].set_value(0.95).run(timeout=60)
    assert not app.exception and "Green" in _text(app) and "99% / 250 sessions" in _text(app)

    app.sidebar.select_slider[0].set_value(0.99).run(timeout=60)
    app.radio[0].set_value("parametric_normal").run(timeout=60)
    assert not app.exception and "Yellow" in _text(app)

    short = (pd.Timestamp("2026-10-01").date(), pd.Timestamp("2026-10-30").date())
    app.sidebar.date_input[0].set_value(short).run(timeout=60)
    assert not app.exception and "Unavailable for this range" in _text(app)

    weekend = (pd.Timestamp("2021-01-09").date(), pd.Timestamp("2021-01-10").date())
    app.sidebar.date_input[0].set_value(weekend).run(timeout=60)
    assert not app.exception and "No forecast targets fall in this range" in _text(app)


def test_performance_and_stress_handle_references_and_empty_ranges():
    app = _app()
    app.sidebar.selectbox[0].set_value("benchmark_60_40").run(timeout=60)
    app.sidebar.radio[0].set_value("Risk budget & stress").run(timeout=60)
    assert not app.exception and not app.error
    assert "does not have to satisfy" in _text(app)
    for method in ("normal_es", "normal_var", "historical_es"):
        app.selectbox[0].set_value(method).run(timeout=60)
        assert not app.exception and not app.error, method
    app.sidebar.radio[0].set_value("Performance").run(timeout=60)
    assert not app.exception and not app.error
    weekend = (pd.Timestamp("2021-01-09").date(), pd.Timestamp("2021-01-10").date())
    app.sidebar.date_input[0].set_value(weekend).run(timeout=60)
    assert not app.exception and "No active portfolio sessions" in _text(app)


def test_cloud_entrypoint_runs_the_redesigned_app():
    tempfile.tempdir = str(ROOT / "tmp")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60).run()
    assert not app.exception and not app.error
    assert next(m for m in app.metric if m.label == "Evaluation CAGR, 2021-2026").value == "7.63%"


def test_macros_reproduce_the_reference():
    ref = json.loads((ROOT / "results/final/reference.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "report/latex/generated/metrics_manifest.json").read_text(encoding="utf-8"))
    assert manifest["qeBundle"]["value"] == ref["metadata"]["bundle_id"]
    kpi = next(x["value"] for x in ref["period_kpis"] if x["period"] == "evaluation"
               and x["portfolio_id"] == "min_variance" and x["metric"] == "geometric_annual_return")
    assert manifest["qeEvalCagr"]["value"] == kpi
    assert manifest["qeEvalCagr"]["tex"] == r"7.63\%"
    assert manifest["qeHsFullInd"]["tex"].startswith("$1.7\\times10^{")
    assert manifest["qeGfcDrawdown"]["tex"] == "\N{MINUS SIGN}23.87\\%"


def test_published_pdfs_are_tex_compiled_and_within_page_limits():
    pypdf = pytest.importorskip("pypdf")
    for name, low, high in (("investment_memo.pdf", 7, 15), ("tear_sheet.pdf", 1, 1), ("recommendation.pdf", 1, 1)):
        reader = pypdf.PdfReader(ROOT / "submission" / name)
        assert low <= len(reader.pages) <= high, name
        producer = str(reader.metadata.get("/Producer", "")).lower()
        assert "dvipdfmx" in producer and "reportlab" not in producer, name
        assert (ROOT / "submission" / name).read_bytes() == (ROOT / "output/pdf" / name).read_bytes(), name


def test_human_review_pack_is_blank_and_status_is_pending():
    form = (ROOT / "handoff/human_review_pack/04_REVIEW_FORM.md").read_text(encoding="utf-8")
    assert "- [ ] Agree with the proposal" in form and "[x]" not in form.lower()
    assert "| Reviewer's real name | |" in form
    worksheet = (ROOT / "handoff/human_review_pack/01_CALCULATION_WORKSHEET.md").read_text(encoding="utf-8")
    assert "Your answer: ____________________" in worksheet and "-0.0023025" not in worksheet
    key = (ROOT / "handoff/human_review_pack/02_ANSWER_KEY_AI_PREPARED.md").read_text(encoding="utf-8")
    assert "AI-PREPARED" in key and "not performing a calculation" in key


def test_legacy_reportlab_script_cannot_overwrite_latex_deliverables():
    before = (ROOT / "submission/investment_memo.pdf").read_bytes()
    result = subprocess.run([sys.executable, str(ROOT / "scripts/build_submission_pdfs.py")], capture_output=True, text=True)
    assert result.returncode != 0 and "build_reports.py" in result.stderr
    assert (ROOT / "submission/investment_memo.pdf").read_bytes() == before
    source = (ROOT / "scripts/build_submission_pdfs.py").read_text(encoding="utf-8")
    assert "ROOT/'submission'" not in source and "output/legacy_reportlab" in source
