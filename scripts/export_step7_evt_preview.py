"""Render persisted Step 7 EVT development artifacts and figures without re-estimating models.

Numerical authority: results/step7_evt_preview/step7_recorded_results.json.
Uses isolated plotting libraries in tmp/figure_export_deps; app dependencies are unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RENDER_DEPS = ROOT / "tmp/figure_export_deps"
if RENDER_DEPS.exists():
    sys.path.insert(0, str(RENDER_DEPS))

from generate_step7_methodology import bootstrap_table, risk_table, threshold_table, main as generate_methodology

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd


OUT = ROOT / "results/step7_evt_preview"
AUTHORITY = OUT / "step7_recorded_results.json"
FIG_DIR = OUT / "figures"
TABLES_DIR = OUT / "tables"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_non_json_number(token: str) -> None:
    raise ValueError(f"Non-standard JSON numeric token: {token}")


def _stamp_figure(fig, data):
    meta = data["metadata"]
    runs = data["runs"]
    rec = runs["recent_development_1260d"]
    full = runs["full_development_3020d"]
    weights = ", ".join(f"{t} {100*w:.2f}%" for t,w in meta["weights"].items() if w > 1e-8)
    footer = (
        f"DEVELOPMENT ONLY | min_variance fixed exposure: {weights} | 1-day pre-cost simple loss\n"
        f"Recent {rec['sample_start']} to {rec['sample_end']}; full {full['sample_start']} to {full['sample_end']} | NAV USD {meta['nav_usd']:,.0f}\n"
        "Unconditional research; human validation PENDING. Source/authority hashes: manifest.json."
    )
    fig.text(0.03, -0.075, footer, fontsize=8, color="#475569", va="top", linespacing=1.4)


def _render_figures(data: dict[str, Any]) -> dict[str, str]:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    runs = data["runs"]
    rec_run = runs["recent_development_1260d"]
    full_run = runs["full_development_3020d"]

    # Color palette matching QuantEdge theme
    c_recent = "#147D73"   # Teal
    c_full = "#182D43"     # Navy
    c_accent = "#CF6A32"   # Ochre / Terracotta
    c_gray = "#64748B"

    # -------------------------------------------------------------------------
    # FIGURE 1: Threshold Stability, MRL, and Modified Scale Diagnostics
    # -------------------------------------------------------------------------
    fig1, axes = plt.subplots(1, 3, figsize=(16, 5), dpi=300)
    fig1.patch.set_facecolor("#FFFFFF")

    # Panel A: Mean Residual Life (Mean Excess) vs Candidate Quantile
    ax = axes[0]
    ax.set_facecolor("#F8FAFC")
    ax.grid(True, linestyle="--", alpha=0.5, color="#CBD5E1")

    for run_data, label, col, marker in (
        (rec_run, "Recent 1,260d (2011-12-29 to 2016-12-30)", c_recent, "o"),
        (full_run, "Full 3,020d (2005-2016)", c_full, "s"),
    ):
        df_d = pd.DataFrame(run_data["threshold_diagnostics_dense"])
        df_valid = df_d[df_d["mean_excess"].notna()].copy()
        q = df_valid["candidate_quantile"].to_numpy(dtype=float)
        m = df_valid["mean_excess"].to_numpy(dtype=float)
        se = df_valid["mean_excess_se"].to_numpy(dtype=float)

        ax.plot(q, m * 100.0, color=col, marker=marker, linewidth=1.8, markersize=5, label=label)
        ax.fill_between(q, (m - 1.96 * se) * 100.0, (m + 1.96 * se) * 100.0, color=col, alpha=0.15)

    ax.axvline(0.95, color=c_accent, linestyle=":", linewidth=1.8, label="Provisional Policy (0.95)")
    ax.set_title("(a) Mean Residual Life (Mean Excess $\pm 1.96$ SE)", fontsize=11, fontweight="bold", color=c_full)
    ax.set_xlabel("Threshold Quantile $q$", fontsize=10)
    ax.set_ylabel("Mean Excess Loss (%)", fontsize=10)
    ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", fontsize=8.5)

    # Panel B: Fitted Shape Parameter xi(u) vs Candidate Quantile
    ax = axes[1]
    ax.set_facecolor("#F8FAFC")
    ax.grid(True, linestyle="--", alpha=0.5, color="#CBD5E1")

    for run_data, label, col, marker in (
        (rec_run, "Recent 1,260d", c_recent, "o"),
        (full_run, "Full 3,020d", c_full, "s"),
    ):
        df_d = pd.DataFrame(run_data["threshold_diagnostics_dense"])
        df_ok = df_d[df_d["xi"].notna()].copy()
        q = df_ok["candidate_quantile"].to_numpy(dtype=float)
        xi = df_ok["xi"].to_numpy(dtype=float)
        se = df_ok["xi_se_asymptotic_iid"].to_numpy(dtype=float)

        ax.plot(q, xi, color=col, marker=marker, linewidth=1.8, markersize=5, label=label)
        ax.fill_between(q, xi - 1.96 * se, xi + 1.96 * se, color=col, alpha=0.15)

    ax.axhline(0.0, color="#94A3B8", linestyle="--", linewidth=1.0, label=r"Exponential Tail ($\xi = 0$)")
    ax.axvline(0.95, color=c_accent, linestyle=":", linewidth=1.8, label="Provisional Policy (0.95)")
    ax.set_title(r"(b) GPD Shape Parameter $\hat{\xi}(u) \pm 1.96$ SE", fontsize=11, fontweight="bold", color=c_full)
    ax.set_xlabel("Threshold Quantile $q$", fontsize=10)
    ax.set_ylabel(r"Tail Index $\hat{\xi}$ (Heavy Tail > 0)", fontsize=10)
    ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", fontsize=8.5)

    # Panel C: Modified Scale beta(u) - xi * u
    ax = axes[2]
    ax.set_facecolor("#F8FAFC")
    ax.grid(True, linestyle="--", alpha=0.5, color="#CBD5E1")

    for run_data, label, col, marker in (
        (rec_run, "Recent 1,260d", c_recent, "o"),
        (full_run, "Full 3,020d", c_full, "s"),
    ):
        df_d = pd.DataFrame(run_data["threshold_diagnostics_dense"])
        df_ok = df_d[df_d["modified_scale"].notna()].copy()
        q = df_ok["candidate_quantile"].to_numpy(dtype=float)
        mod_b = df_ok["modified_scale"].to_numpy(dtype=float)

        ax.plot(q, mod_b * 100.0, color=col, marker=marker, linewidth=1.8, markersize=5, label=label)

    ax.axvline(0.95, color=c_accent, linestyle=":", linewidth=1.8, label="Provisional Policy (0.95)")
    ax.set_title(r"(c) Modified Scale $\hat{\beta}(u) - \hat{\xi} u$ Stability", fontsize=11, fontweight="bold", color=c_full)
    ax.set_xlabel("Threshold Quantile $q$", fontsize=10)
    ax.set_ylabel("Modified Scale (%)", fontsize=10)
    ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", fontsize=8.5)

    fig1.suptitle("QuantEdge 1.0 — Development Period Unconditional EVT Threshold Diagnostics (Through 2016-12-30)",
                  fontsize=13, fontweight="bold", color=c_full, y=1.02)
    fig1.tight_layout()
    _stamp_figure(fig1, data)

    fig1_png = FIG_DIR / "figure_01_threshold_stability_and_mrl.png"
    fig1_svg = FIG_DIR / "figure_01_threshold_stability_and_mrl.svg"
    fig1.savefig(fig1_png, dpi=300, bbox_inches="tight")
    fig1.savefig(fig1_svg, format="svg", bbox_inches="tight")
    plt.close(fig1)

    # -------------------------------------------------------------------------
    # FIGURE 2: Tail Excess QQ and Probability Plots (Primary q=0.95)
    # -------------------------------------------------------------------------
    fig2, axes = plt.subplots(1, 2, figsize=(13, 5.5), dpi=300)
    fig2.patch.set_facecolor("#FFFFFF")

    # QQ Plot (Panel A)
    ax = axes[0]
    ax.set_facecolor("#F8FAFC")
    ax.grid(True, linestyle="--", alpha=0.5, color="#CBD5E1")

    for run_data, label, col, marker in (
        (rec_run, f"Recent 1,260d (N_u={rec_run['primary_fit']['n_exceedances']})", c_recent, "o"),
        (full_run, f"Full 3,020d (N_u={full_run['primary_fit']['n_exceedances']})", c_full, "s"),
    ):
        qq_df = pd.DataFrame(run_data["qq_pp_data"])
        mod_q = qq_df["model_quantile_excess"].to_numpy(dtype=float) * 100.0
        emp_q = qq_df["empirical_excess"].to_numpy(dtype=float) * 100.0
        ax.scatter(mod_q, emp_q, color=col, marker=marker, s=28, alpha=0.8, edgecolors="none", label=label)

    max_val = max(ax.get_xlim()[1], ax.get_ylim()[1])
    ax.plot([0, max_val], [0, max_val], color=c_accent, linestyle="--", linewidth=1.5, label="Reference diagonal (45° line)")
    ax.set_title("(a) GPD Tail Excess Q-Q Plot ($q=0.95$ Threshold)", fontsize=11, fontweight="bold", color=c_full)
    ax.set_xlabel("Fitted GPD Excess Quantile (%)", fontsize=10)
    ax.set_ylabel("Empirical Excess Loss (%)", fontsize=10)
    ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", fontsize=8.5)

    # PP Plot (Panel B)
    ax = axes[1]
    ax.set_facecolor("#F8FAFC")
    ax.grid(True, linestyle="--", alpha=0.5, color="#CBD5E1")

    for run_data, label, col, marker in (
        (rec_run, "Recent 1,260d", c_recent, "o"),
        (full_run, "Full 3,020d", c_full, "s"),
    ):
        qq_df = pd.DataFrame(run_data["qq_pp_data"])
        p_emp = qq_df["plotting_position"].to_numpy(dtype=float)
        p_mod = qq_df["model_cdf_at_empirical"].to_numpy(dtype=float)
        ax.scatter(p_emp, p_mod, color=col, marker=marker, s=28, alpha=0.8, edgecolors="none", label=label)

    ax.plot([0, 1], [0, 1], color=c_accent, linestyle="--", linewidth=1.5, label="Reference Diagonal")
    ax.set_title("(b) GPD Tail Probability Plot (P-P)", fontsize=11, fontweight="bold", color=c_full)
    ax.set_xlabel(r"Empirical Plotting Position $(i - 0.5) / N_u$", fontsize=10)
    ax.set_ylabel(r"Fitted GPD Model CDF $F_{\hat{\theta}}(y_i)$", fontsize=10)
    ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", fontsize=8.5)

    fig2.suptitle("QuantEdge 1.0 — GPD Tail Descriptive Diagnostics (Primary $q=0.95$ Threshold)",
                  fontsize=13, fontweight="bold", color=c_full, y=1.02)
    fig2.tight_layout()
    _stamp_figure(fig2, data)

    fig2_png = FIG_DIR / "figure_02_gpd_tail_qq_pp_diagnostics.png"
    fig2_svg = FIG_DIR / "figure_02_gpd_tail_qq_pp_diagnostics.svg"
    fig2.savefig(fig2_png, dpi=300, bbox_inches="tight")
    fig2.savefig(fig2_svg, format="svg", bbox_inches="tight")
    plt.close(fig2)

    # -------------------------------------------------------------------------
    # FIGURE 3: Matched Risk Model & Bootstrap Uncertainty Comparison
    # -------------------------------------------------------------------------
    fig3, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=300)
    fig3.patch.set_facecolor("#FFFFFF")

    for idx, (win_id, title) in enumerate((
        ("recent_development_1260d", "Recent (1,260 sessions; 2011-12-29 to 2016-12-30)"),
        ("full_development_3020d", "Full Development (3,020 sessions, 2005-2016, incl. GFC)"),
    )):
        ax = axes[idx]
        ax.set_facecolor("#F8FAFC")
        ax.grid(True, linestyle="--", alpha=0.5, color="#CBD5E1", axis="y")

        r = runs[win_id]
        comp_df = pd.DataFrame(r["model_comparison"])
        # Focus on 95% and 99%
        models_order = ["historical", "parametric_normal", "monte_carlo_normal", "evt_pot", "evt_body_tail_hybrid"]
        model_display = {
            "historical": "Historical",
            "parametric_normal": "Normal",
            "monte_carlo_normal": "MC Normal",
            "evt_pot": "EVT POT",
            "evt_body_tail_hybrid": "EVT Hybrid",
        }

        # Plot 99% VaR and ES
        df99 = comp_df[comp_df["confidence"] == 0.99].copy()
        x = np.arange(len(models_order))
        w_bar = 0.35

        var_vals = [df99[df99["model"] == m]["var_pct"].iloc[0] if len(df99[df99["model"] == m]) > 0 else 0.0 for m in models_order]
        es_vals = [df99[df99["model"] == m]["es_pct"].iloc[0] if len(df99[df99["model"] == m]) > 0 else 0.0 for m in models_order]

        b1 = ax.bar(x - w_bar / 2, var_vals, width=w_bar, color="#0284C7", label="99% 1-Day VaR (%)", alpha=0.9)
        b2 = ax.bar(x + w_bar / 2, es_vals, width=w_bar, color="#E11D48", label="99% 1-Day ES (%)", alpha=0.9)

        # Add moving-block bootstrap 95% uncertainty interval on EVT POT
        boot_sum = r["bootstrap"]["summary"]["by_confidence"]["0.9900"]
        if boot_sum["var"]["interval_status"] == "ok":
            v_low = boot_sum["var"]["p025"] * 100.0
            v_high = boot_sum["var"]["p975"] * 100.0
            v_med = boot_sum["var"]["median"] * 100.0
            ax.errorbar([3 - w_bar / 2], [v_med], yerr=[[v_med - v_low], [v_high - v_med]],
                        fmt="none", ecolor="#0F172A", elinewidth=2.2, capsize=4.5, label="EVT Bootstrap 95% CI")
        if boot_sum["es"]["interval_status"] == "ok":
            e_low = boot_sum["es"]["p025"] * 100.0
            e_high = boot_sum["es"]["p975"] * 100.0
            e_med = boot_sum["es"]["median"] * 100.0
            ax.errorbar([3 + w_bar / 2], [e_med], yerr=[[e_med - e_low], [e_high - e_med]],
                        fmt="none", ecolor="#0F172A", elinewidth=2.2, capsize=4.5)

        ax.set_xticks(x)
        ax.set_xticklabels([model_display[m] for m in models_order], fontsize=9)
        ax.set_ylabel("1-Day Loss (%)", fontsize=10)
        ax.set_title(title, fontsize=11, fontweight="bold", color=c_full)
        if idx == 0:
            ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", fontsize=8.5)

    fig3.suptitle("QuantEdge 1.0 — 99% Risk Metric Comparison Across Methods and Windows",
                  fontsize=13, fontweight="bold", color=c_full, y=1.02)
    fig3.tight_layout()
    _stamp_figure(fig3, data)

    fig3_png = FIG_DIR / "figure_03_risk_model_and_uncertainty_comparison.png"
    fig3_svg = FIG_DIR / "figure_03_risk_model_and_uncertainty_comparison.svg"
    fig3.savefig(fig3_png, dpi=300, bbox_inches="tight")
    fig3.savefig(fig3_svg, format="svg", bbox_inches="tight")
    plt.close(fig3)

    return {
        "figure_01_threshold_stability_and_mrl.png": _sha256(fig1_png),
        "figure_01_threshold_stability_and_mrl.svg": _sha256(fig1_svg),
        "figure_02_gpd_tail_qq_pp_diagnostics.png": _sha256(fig2_png),
        "figure_02_gpd_tail_qq_pp_diagnostics.svg": _sha256(fig2_svg),
        "figure_03_risk_model_and_uncertainty_comparison.png": _sha256(fig3_png),
        "figure_03_risk_model_and_uncertainty_comparison.svg": _sha256(fig3_svg),
    }


def _format_markdown_tables(data):
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in [
        ("table_01_risk_model_comparison.md", risk_table(data)),
        ("table_02_threshold_diagnostics.md", threshold_table(data)),
        ("table_03_bootstrap_uncertainty.md", bootstrap_table(data)),
    ]:
        (TABLES_DIR / filename).write_text(content + "\n", encoding="utf-8")


def _write_manifest_and_docs(data: dict[str, Any], fig_hashes: dict[str, str]) -> None:
    # 2. README.md
    readme_text = f"""# QuantEdge 1.0 — Step 7 (C2/C3) EVT POT-GPD Tail Preview

**Scope:** DEVELOPMENT PERIOD ONLY (through `{data["metadata"]["development_end"]}`).
Unconditional Peaks-Over-Threshold Generalized Pareto Distribution (POT-GPD) tail risk modeling
and moving-block bootstrap uncertainty for the terminal-development `min_variance` portfolio exposure.

- **Dataset ID:** `{data["metadata"]["dataset_id"]}`
- **Config Hash:** `{data["metadata"]["config_hash"]}`
- **Portfolio NAV:** `USD {data["metadata"]["nav_usd"]:,.2f}`
- **Primary Threshold Policy:** Empirical `q = {data["metadata"]["threshold_policy"]["threshold_quantile"]}` loss quantile, `min_exceedances = {data["metadata"]["threshold_policy"]["min_exceedances"]}` (provisional; human approval PENDING).
- **Uncertainty Policy:** Moving-block bootstrap (`block_length = 10`, `n_replications = 100`, `seed = {data["metadata"]["bootstrap_policy"]["seed"]}`).
- **Authority File:** `step7_recorded_results.json`

## Deliverables
- `tables/table_01_risk_model_comparison.{{csv,md}}`: Matched 90%, 95%, 99% VaR and ES across Historical, Parametric Normal, Monte Carlo, and EVT (POT and Hybrid).
- `tables/table_02_threshold_diagnostics.{{csv,md}}`: Threshold grid diagnostics (MRL, xi, beta, modified scale beta - xi*u).
- `tables/table_03_bootstrap_uncertainty.{{csv,md}}`: 95% moving-block bootstrap confidence intervals.
- `tables/table_04_qq_pp_*.csv`: Empirical vs fitted GPD quantiles and probabilities.
- `figures/figure_01_threshold_stability_and_mrl.{{png,svg}}`: MRL and parameter stability plots.
- `figures/figure_02_gpd_tail_qq_pp_diagnostics.{{png,svg}}`: QQ and PP calibration plots.
- `figures/figure_03_risk_model_and_uncertainty_comparison.{{png,svg}}`: Visual risk and bootstrap error comparison.
"""
    (OUT / "README.md").write_text(readme_text, encoding="utf-8")

    # 3. index.html
    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>QuantEdge 1.0 — Step 7 EVT POT-GPD Preview</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 30px; line-height: 1.5; color: #182D43; background: #F8FAFC; }}
    h1, h2, h3 {{ color: #182D43; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; background: #E2E8F0; color: #334155; margin-right: 6px; }}
    .badge-dev {{ background: #FEF3C7; color: #92400E; }}
    .card {{ background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 20px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 13px; }}
    th, td {{ border: 1px solid #CBD5E1; padding: 8px 12px; text-align: left; }}
    th {{ background: #F1F5F9; font-weight: 600; }}
    tr:nth-child(even) {{ background: #F8FAFC; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #E2E8F0; border-radius: 6px; margin-top: 12px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; background: #F1F5F9; padding: 2px 4px; border-radius: 3px; }}
  </style>
</head>
<body>
  <h1>QuantEdge 1.0 — Step 7 EVT POT-GPD Tail Risk Preview</h1>
  <p>
    <span class="badge badge-dev">DEVELOPMENT ONLY (Through 2016-12-30)</span>
    <span class="badge">Dataset: {data["metadata"]["dataset_id"]}</span>
    <span class="badge">Config Hash: {data["metadata"]["config_hash"][:16]}...</span>
  </p>

  <div class="card">
    <h2>1. Threshold Stability & Mean Residual Life Diagnostics</h2>
    <p>Evaluation of candidate thresholds from 80% to 97.5%. The primary provisional policy is fixed at $q=0.95$ with minimum 50 strict exceedances.</p>
    <img src="figures/figure_01_threshold_stability_and_mrl.png" alt="Figure 1: Threshold Stability and MRL">
  </div>

  <div class="card">
    <h2>2. Descriptive Tail Fit Diagnostics (Q-Q & P-P Plots)</h2>
    <p>Descriptive excess quantile and probability plots for strict exceedances above the 95% loss threshold. No uncalibrated parametric GOF p-values are claimed.</p>
    <img src="figures/figure_02_gpd_tail_qq_pp_diagnostics.png" alt="Figure 2: Tail QQ/PP Diagnostics">
  </div>

  <div class="card">
    <h2>3. 99% Risk Comparison Across Methods with Bootstrap Uncertainty</h2>
    <p>1-day 99% VaR and Expected Shortfall across Historical, Parametric Normal, Monte Carlo Normal, and EVT (POT and Body/Tail Hybrid), with 95% moving-block bootstrap confidence intervals.</p>
    <img src="figures/figure_03_risk_model_and_uncertainty_comparison.png" alt="Figure 3: Risk Model and Uncertainty Comparison">
  </div>

  <div class="card">
    <h2>4. Exported Tables & Manifest</h2>
    <ul>
      <li><a href="tables/table_01_risk_model_comparison.csv">table_01_risk_model_comparison.csv</a></li>
      <li><a href="tables/table_02_threshold_diagnostics.csv">table_02_threshold_diagnostics.csv</a></li>
      <li><a href="tables/table_03_bootstrap_uncertainty.csv">table_03_bootstrap_uncertainty.csv</a></li>
      <li><a href="step7_recorded_results.json">step7_recorded_results.json (Strict Authority)</a></li>
      <li><a href="manifest.json">manifest.json</a></li>
    </ul>
  </div>
</body>
</html>
"""
    (OUT / "index.html").write_text(html_text, encoding="utf-8")

    source_names = [
        "config.yaml", "src/quantedge/contracts.py", "src/quantedge/evt.py",
        "src/quantedge/var.py", "src/quantedge/es.py",
        "scripts/record_step7_evt_results.py", "scripts/export_step7_evt_preview.py",
        "scripts/generate_step7_methodology.py", "docs/sections/c_var_es_and_evt.md",
    ]
    manifest_payload = {
        "dataset_id": data["metadata"]["dataset_id"],
        "config_hash": data["metadata"]["config_hash"],
        "development_end": data["metadata"]["development_end"],
        "portfolio_id": data["metadata"]["portfolio_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "numerical_authority_json": "results/step7_evt_preview/step7_recorded_results.json",
        "numerical_authority_sha256": _sha256(AUTHORITY),
        "source_sha256": {name: _sha256(ROOT / name) for name in source_names},
        "artifacts_sha256": {p.relative_to(OUT).as_posix(): _sha256(p)
                             for p in sorted(OUT.rglob("*"))
                             if p.is_file() and p.name != "manifest.json"},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest_payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    assert AUTHORITY.is_file(), f"Missing {AUTHORITY}; run record_step7_evt_results.py first."
    data = json.loads(AUTHORITY.read_text(encoding="utf-8"), parse_constant=_reject_non_json_number)

    generate_methodology()
    print("Rendering figures...", flush=True)
    fig_hashes = _render_figures(data)

    print("Formatting markdown tables...", flush=True)
    _format_markdown_tables(data)

    print("Writing manifest and documentation...", flush=True)
    _write_manifest_and_docs(data, fig_hashes)

    print("Step 7 preview export complete.", flush=True)


if __name__ == "__main__":
    main()
