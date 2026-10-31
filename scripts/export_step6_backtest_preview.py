"""Render persisted Step 6 development backtests without re-estimating any risk model.

Numerical authority: results/step6_backtest_preview/backtest_results.json.
Uses isolated plotting libraries in tmp/figure_export_deps; app dependencies are unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RENDER_DEPS = ROOT / "tmp/figure_export_deps"
if RENDER_DEPS.exists():
    sys.path.insert(0, str(RENDER_DEPS))

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd


OUT = ROOT / "results/step6_backtest_preview"
AUTHORITY = OUT / "backtest_results.json"
MODELS = ("historical", "parametric_normal")
CONFIDENCES = (0.95, 0.99)
LABELS = {"historical": "Historical", "parametric_normal": "Normal"}
COLORS = {"historical": "#147D73", "parametric_normal": "#CF6A32"}
INK = "#182D43"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_non_json_number(token: str) -> None:
    raise ValueError(f"Non-standard JSON numeric token: {token}")


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _run_frame(run: dict[str, object], development_end: pd.Timestamp) -> pd.DataFrame:
    frame = pd.DataFrame(run["rows"]).copy()
    required = {"date", "model", "confidence", "forecast_var", "realized_loss", "exceedance", "status"}
    if frame.empty or not required.issubset(frame.columns):
        raise ValueError("Each persisted run must contain actual backtest rows with the frozen schema.")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame["date"].dt.tz is not None:
        raise ValueError("Preview expects timezone-naive NYSE session dates.")
    if frame["date"].duplicated().any() or not frame["date"].is_monotonic_increasing:
        raise ValueError("Persisted backtest dates must be unique and ascending within each run.")
    if frame["date"].max() > development_end:
        raise ValueError("This preview must not expose selection/evaluation outcomes.")
    if not frame["model"].eq(run["model"]).all():
        raise ValueError("Run model metadata differs from its row model labels.")
    if not np.allclose(frame["confidence"].astype(float), float(run["confidence"]), rtol=0.0, atol=1e-12):
        raise ValueError("Run confidence differs from its row confidence labels.")
    frame["eligible"] = (
        frame["status"].isin(("ok", "warning"))
        & frame["forecast_var"].map(_finite)
        & frame["realized_loss"].map(_finite)
        & frame["exceedance"].map(lambda value: isinstance(value, (bool, np.bool_)))
    )
    return frame


def _decorate(fig: plt.Figure, title: str, metadata: dict[str, object]) -> None:
    fig.text(0.07, 0.975, "QUANT EDGE  /  STEP 6  /  DEVELOPMENT OOS RESEARCH", fontsize=9,
             color="#147D73", weight="bold", va="top")
    fig.text(0.07, 0.94, title, fontsize=18, color=INK, weight="bold", va="top")
    fig.text(
        0.07, 0.887,
        f"{metadata['sample_start']} to {metadata['sample_end']}  |  "
        f"{metadata['portfolio_id']}  |  Previous {metadata['window']} sessions  |  "
        "1-day gross market loss; weights known before each session",
        fontsize=9, color="#526574", va="top",
    )
    fig.text(
        0.07, 0.034,
        "Development research only; no post-2016 strategy results. Human validation and mandate approval pending.\n"
        "Risk forecasts exclude transaction costs. Persisted backtest rows are the numerical authority; provenance is in manifest.json.",
        fontsize=8, color="#526574", va="bottom", linespacing=1.45,
    )


def _save_figure(fig: plt.Figure, stem: str) -> None:
    # Fixed canvas dimensions and reserved header/footer space avoid cropping labels.
    fig.savefig(OUT / f"{stem}.png", dpi=300, facecolor="white")
    fig.savefig(OUT / f"{stem}.svg", facecolor="white")
    plt.close(fig)


def _fmt(value: object, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "unavailable"
    if isinstance(value, (int, np.integer)):
        return str(value)
    if isinstance(value, (float, np.floating)):
        return f"{value:.{digits}f}"
    return str(value)


def main() -> None:
    saved = json.loads(AUTHORITY.read_text(encoding="utf-8"), parse_constant=_reject_non_json_number)
    json.dumps(saved, allow_nan=False)
    metadata = saved["metadata"]
    for key in ("scope", "dataset_id", "config_hash", "development_end", "portfolio_id",
                "window", "sample_start", "sample_end", "runtime_seconds"):
        if key not in metadata:
            raise ValueError(f"Missing authority provenance: {key}")
    development_end = pd.Timestamp(metadata["development_end"])
    if development_end > pd.Timestamp("2016-12-30"):
        raise ValueError("Step 6 development preview is bounded at 2016-12-30.")

    frames: dict[tuple[str, float], pd.DataFrame] = {}
    for run in saved["runs"]:
        key = (run["model"], round(float(run["confidence"]), 10))
        if key in frames:
            raise ValueError(f"Duplicate persisted run: {key}")
        frames[key] = _run_frame(run, development_end)
    for model in MODELS:
        for confidence in CONFIDENCES:
            if (model, confidence) not in frames:
                raise ValueError(f"Required actual persisted comparison missing: {model}, {confidence}")

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#AAB6C2", "axes.labelcolor": INK,
        "text.color": INK, "xtick.color": "#46586A", "ytick.color": "#46586A",
        "grid.color": "#DCE3E8", "grid.alpha": 0.65, "svg.fonttype": "none",
    })

    # Actual observed market losses and forecasts: NaN only inside plotting arrays means a gap.
    # The persisted JSON remains strict and keeps an explicit skipped-row status/reason.
    fig, axes = plt.subplots(2, 1, figsize=(13.5, 8.8), sharex=True)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.785, bottom=0.145, hspace=0.28)
    for ax, confidence in zip(axes, CONFIDENCES):
        base = frames[("historical", confidence)]
        base_loss = pd.to_numeric(base["realized_loss"], errors="coerce")
        ax.plot(base["date"], base_loss * 100, color="#94A6B5", lw=0.55, alpha=0.85, zorder=1)
        panel_stats: list[str] = []
        for model in MODELS:
            frame = frames[(model, confidence)]
            same = base[["date", "realized_loss"]].merge(
                frame[["date", "realized_loss"]], on="date", suffixes=("_base", "_model"), how="outer"
            )
            if len(same) != len(base) or len(same) != len(frame):
                raise ValueError("Model comparison must use matched target dates.")
            finite_both = same["realized_loss_base"].notna() & same["realized_loss_model"].notna()
            if not np.allclose(same.loc[finite_both, "realized_loss_base"].astype(float),
                               same.loc[finite_both, "realized_loss_model"].astype(float),
                               rtol=0.0, atol=1e-12):
                raise ValueError("Model comparison does not share the same realized gross loss.")
            forecasts = pd.to_numeric(frame["forecast_var"], errors="coerce").where(frame["eligible"])
            ax.plot(frame["date"], forecasts * 100, color=COLORS[model], lw=1.0, zorder=3)
            exceptions = frame["eligible"] & frame["exceedance"].eq(True)
            ax.scatter(frame.loc[exceptions, "date"],
                       pd.to_numeric(frame.loc[exceptions, "realized_loss"]) * 100,
                       marker="o" if model == "historical" else "x", s=13,
                       facecolors="none" if model == "historical" else COLORS[model],
                       edgecolors=COLORS[model] if model == "historical" else None,
                       color=COLORS[model], linewidths=0.8, zorder=4)
            n_valid = int(frame["eligible"].sum())
            n_skipped = len(frame) - n_valid
            panel_stats.append(f"{LABELS[model]}: {int(exceptions.sum())}/{n_valid} exceptions; {n_skipped} skipped")
            skipped_dates = frame.loc[~frame["eligible"], "date"]
            if len(skipped_dates):
                ax.plot(skipped_dates, np.zeros(len(skipped_dates)), "|", color="#9E2A2B", ms=7, zorder=5)
        ax.set_title(f"{confidence:.0%} VaR   |   " + "   ·   ".join(panel_stats), loc="left", fontsize=10)
        ax.set_ylabel("Loss / VaR (% of NAV)")
        ax.axhline(0, color="#C4CDD4", lw=0.6)
        ax.grid(axis="y")
        ax.set_axisbelow(True)
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.margins(x=0.005)
    axes[-1].set_xlabel("Realization session")
    handles = [
        Line2D([0], [0], color="#94A6B5", lw=1, label="Realized gross market loss"),
        Line2D([0], [0], color=COLORS["historical"], lw=1.5, label="Historical VaR (○ exceptions)"),
        Line2D([0], [0], color=COLORS["parametric_normal"], lw=1.5, label="Normal VaR (× exceptions)"),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.065, 0.855),
               ncol=3, frameon=False, fontsize=9)
    _decorate(fig, "Rolling VaR forecasts and actual daily losses", metadata)
    _save_figure(fig, "figure_01_rolling_var_exceptions")

    # Annual counts are a transparent aggregation of persisted eligible exception indicators.
    # This is a display calculation, not a fresh risk estimator or likelihood implementation.
    annual_rows: list[dict[str, object]] = []
    fig, axes = plt.subplots(2, 1, figsize=(13.5, 8.8), sharex=True)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.785, bottom=0.145, hspace=0.31)
    years = sorted({int(year) for frame in frames.values() for year in frame["date"].dt.year})
    x = np.arange(len(years), dtype=float)
    width = 0.34
    for ax, confidence in zip(axes, CONFIDENCES):
        for model_index, model in enumerate(MODELS):
            frame = frames[(model, confidence)]
            observed: list[int] = []
            expected: list[float] = []
            for year in years:
                sub = frame.loc[frame["date"].dt.year.eq(year)]
                n_valid = int(sub["eligible"].sum())
                exceptions = int((sub["eligible"] & sub["exceedance"].eq(True)).sum())
                n_expected = n_valid * (1 - confidence)
                observed.append(exceptions)
                expected.append(n_expected)
                annual_rows.append({
                    "model": model, "confidence": confidence, "year": year,
                    "n_valid": n_valid, "n_skipped": len(sub) - n_valid,
                    "n_exceedances": exceptions, "expected_exceptions": n_expected,
                })
            offset_x = x + (model_index - 0.5) * width
            bars = ax.bar(offset_x, observed, width=width * 0.94, color=COLORS[model], alpha=0.95)
            ax.scatter(offset_x, expected, marker="D", color="#344D61", s=20, zorder=4)
            y_scale = 34.0 if confidence == 0.95 else 20.0
            for rect, obs_val, exp_val in zip(bars, observed, expected):
                label_y = (
                    max(float(obs_val), float(exp_val)) + 0.042 * y_scale
                    if -0.03 * y_scale <= (float(exp_val) - float(obs_val)) <= 0.11 * y_scale
                    else float(obs_val) + 0.022 * y_scale
                )
                ax.text(
                    rect.get_x() + rect.get_width() / 2.0,
                    label_y,
                    str(obs_val),
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color=INK,
                )
        ax.set_title(f"{confidence:.0%} VaR — yearly observed versus expected exceptions", loc="left", fontsize=10.5)
        ax.set_ylabel("Exceptions (count)")
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
        ax.set_ylim(0, max(ax.get_ylim()[1] * 1.16, 3))
        ax.grid(axis="y")
        ax.set_axisbelow(True)
    axes[-1].set_xticks(x, [str(year) for year in years])
    axes[-1].set_xlabel("Realization year")
    fig.legend(handles=[
        Patch(color=COLORS["historical"], label="Observed: Historical"),
        Patch(color=COLORS["parametric_normal"], label="Observed: Normal"),
        Line2D([0], [0], color="#344D61", marker="D", ls="none", ms=5,
               label="Expected: valid pairs × (1 − confidence)"),
    ], loc="upper left", bbox_to_anchor=(0.065, 0.855), ncol=3, frameon=False, fontsize=9)
    _decorate(fig, "Exception calibration by year", metadata)
    _save_figure(fig, "figure_02_annual_exception_calibration")
    pd.DataFrame(annual_rows).to_csv(OUT / "annual_exception_display_summary.csv", index=False,
                                   float_format="%.12g")

    rendering_versions = {name: importlib.metadata.version(name) for name in
                          ("matplotlib", "contourpy", "cycler", "fonttools", "kiwisolver", "pyparsing")}
    (OUT / "rendering-requirements.txt").write_text(
        "\n".join(f"{name}=={version}" for name, version in rendering_versions.items()) + "\n", encoding="utf-8"
    )
    figures = [
        ("figure_01_rolling_var_exceptions", "Rolling forecasts, actual loss and exceptions"),
        ("figure_02_annual_exception_calibration", "Observed and expected annual exceptions"),
    ]
    cov_rows = [run["coverage"] for run in saved["runs"]]
    coverage_df = pd.DataFrame(cov_rows)
    display_columns = [name for name in ("model", "confidence", "n_valid", "n_skipped", "n_exceedances",
                       "expected_rate", "observed_rate", "p_uc", "p_ind", "p_cc", "status") if name in coverage_df]
    cov_html = coverage_df[display_columns].to_html(index=False, border=0, na_rep="unavailable",
                                                  float_format=lambda v: f"{v:.4f}")
    basel_rows: list[dict[str, object]] = []
    for run in saved["runs"]:
        if run.get("basel") is not None:
            basel_rows.append({"model": run["model"], **run["basel"]})
    basel_html = pd.DataFrame(basel_rows).to_html(index=False, border=0, na_rep="unavailable") if basel_rows else "<p>Not available.</p>"
    figure_html = "".join(
        f'<section><h2>{html.escape(title)}</h2><img src="{stem}.svg" alt="{html.escape(title)}">'
        f'<p><a href="{stem}.png">300-dpi PNG</a> · <a href="{stem}.svg">Vector SVG</a></p></section>'
        for stem, title in figures
    )
    table_links = "".join(f'<li><a href="{html.escape(p.name)}">{html.escape(p.name)}</a></li>'
                          for p in sorted(OUT.glob("*.csv")))
    index = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>Quant Edge Step 6 development backtests</title>
<style>body{{font:15px/1.55 system-ui,sans-serif;background:#f1f5f8;color:#182d43;margin:0}}main{{max-width:1180px;margin:auto;padding:30px 24px}}h1{{font-size:30px}}section{{background:white;padding:22px;margin:22px 0;border:1px solid #dce3e8;border-radius:12px}}img{{width:100%;height:auto}}a{{color:#147d73}}.notice{{background:#e2eeec;padding:18px;border-left:5px solid #147d73}}.scroll{{overflow:auto}}table{{border-collapse:collapse;font-size:12px}}td,th{{padding:8px;border-bottom:1px solid #dde4e9;text-align:right}}td:first-child,th:first-child{{text-align:left}}code{{font-size:12px;overflow-wrap:anywhere}}</style>
<main><p>QUANT EDGE / SOLO STEP 6</p><h1>Development rolling validation</h1>
<div class="notice"><strong>DEVELOPMENT OOS RESEARCH — through {html.escape(str(metadata['development_end']))}.</strong>
These changing-exposure forecasts use only prior observations. This sample overlaps development and is not final holdout evidence. Human validation and mandate approval remain pending.
<br>Primary: Historical VaR; comparison: Normal. Window: {metadata['window']} sessions; portfolio: {html.escape(str(metadata['portfolio_id']))}; one-day gross market loss, before transaction costs.
<br>Dataset <code>{html.escape(str(metadata['dataset_id']))}</code><br>Config <code>{html.escape(str(metadata['config_hash']))}</code>
<br>Actual backtest runtime: {_fmt(metadata['runtime_seconds'], 2)} seconds. Code version: <code>{html.escape(str(metadata.get('code_version', 'not_supplied')))}</code>.</div>
{figure_html}
<section><h2>Coverage tests</h2><p>Asymptotic p-values require care with sparse exceptions. Non-rejection is not proof of safe losses or model adequacy. Test-specific availability and transition counts are retained in the authority JSON.</p><div class="scroll">{cov_html}</div></section>
<section><h2>Latest 99% / 250-session Basel diagnostic</h2><p>Educational diagnostic only; not bank regulatory approval. A block with missing or unusable pairs cannot receive a traffic-light zone.</p><div class="scroll">{basel_html}</div></section>
<section><h2>Actual machine-readable outputs</h2><ul>{table_links}</ul><p><a href="backtest_results.json">Strict JSON authority</a> · <a href="manifest.json">SHA-256 manifest</a> · <a href="README.md">Reproduction notes</a></p></section></main></html>"""
    (OUT / "index.html").write_text(index, encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Step 6 development backtest preview\n\n"
        f"Scope: {metadata['scope']}; actual sample {metadata['sample_start']} through {metadata['sample_end']}.\n\n"
        "All risk forecasts, realized gross losses and coverage statistics come from persisted "
        "`backtest_results.json`. This rendering script does not fit a risk model or recompute "
        "the likelihood tests. `annual_exception_display_summary.csv` only aggregates persisted "
        "valid exception indicators for the annual figure. No post-2016 strategy outcome is displayed. "
        "Human validation and mandate/protocol approval remain pending.\n\n"
        f"Dataset: `{metadata['dataset_id']}`\n\nConfig: `{metadata['config_hash']}`\n\n"
        f"Window: {metadata['window']} prior sessions; portfolio: {metadata['portfolio_id']}; "
        "one-day gross market loss, excluding costs.\n\n"
        "Re-render from repository root after generating the authoritative Step 6 results:\n\n"
        "```powershell\n.\\.venv\\Scripts\\python.exe scripts\\export_step6_backtest_preview.py\n```\n\n"
        "Rendering uses the isolated `tmp/figure_export_deps` environment listed in "
        "`rendering-requirements.txt`, not extra app dependencies. Figures are 300-dpi PNG and "
        "vector SVG; HTML works offline. Files from earlier steps are preserved.\n",
        encoding="utf-8",
    )
    source_paths = [
        "config.yaml", "src/quantedge/contracts.py", "src/quantedge/returns.py",
        "src/quantedge/backtest.py", "src/quantedge/_backtest_diagnostics.py",
        "src/quantedge/portfolio.py", "src/quantedge/var.py", "src/quantedge/es.py",
        "scripts/record_step6_backtest_results.py", "scripts/export_step6_backtest_preview.py",
    ]
    # Root may choose a shorter recorder filename; hash any actual Step 6 recorder as well.
    source_paths.extend(p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "scripts").glob("record_step6*.py")))
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
        "numerical_authority_json": AUTHORITY.relative_to(ROOT).as_posix(),
        "numerical_authority_sha256": _sha256(AUTHORITY),
        "rendering_versions": rendering_versions,
        "source_sha256": {name: _sha256(ROOT / name) for name in dict.fromkeys(source_paths) if (ROOT / name).is_file()},
        "artifacts_sha256": {p.name: _sha256(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "manifest.json"},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for name, expected in manifest["artifacts_sha256"].items():
        assert _sha256(OUT / name) == expected, name
    print(f"Rendered {len(figures)} actual Step 6 figures (PNG/SVG), annual display table, HTML and verified manifest: {OUT}")


if __name__ == "__main__":
    main()
