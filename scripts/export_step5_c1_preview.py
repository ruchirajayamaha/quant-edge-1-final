"""Export SOLO STEP 5 (C1) development-only risk tables and PNG/SVG figures for review.

Consumes the saved, strictly RFC-8259-validated ``results/step5_development_c1_risk_tables.json``
artifact as the sole numerical authority for all VaR, ES, and Monte Carlo uncertainty numbers.
Uses the isolated ``tmp/figure_export_deps`` Matplotlib installation without modifying application
dependencies or touching ``results/development_preview/`` (Step 4 preview).
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
sys.path.insert(0, str(ROOT / "src"))
render_deps = ROOT / "tmp/figure_export_deps"
if render_deps.exists():
    sys.path.insert(0, str(render_deps))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from quantedge.config import load_config
from quantedge.contracts import CANONICAL_TICKERS
from quantedge.data import load_data


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_non_json_number(token: str) -> None:
    raise ValueError(f"Non-standard JSON numeric token encountered: {token}")


def main() -> None:
    out_dir = ROOT / "results/step5_c1_preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_config(ROOT / "config.yaml")
    checkpoint = json.loads((ROOT / "audit/step4_review/CODEX_CLOSURE_CHECKPOINT.json").read_text(encoding="utf-8"))
    for rel_name in ("src/quantedge/portfolio.py", "src/quantedge/kpis.py", "src/quantedge/data.py"):
        assert _sha256(ROOT / rel_name) == checkpoint["sha256"][rel_name], f"Accepted Step 3/4 source changed: {rel_name}"

    saved_json_path = ROOT / "results/step5_development_c1_risk_tables.json"
    raw_json_text = saved_json_path.read_text(encoding="utf-8")
    saved = json.loads(raw_json_text, parse_constant=_reject_non_json_number)

    assert saved["config_hash"] == cfg.config_hash
    assert saved["development_end"] == cfg.chronology.development_end
    assert saved["monte_carlo_seed"] == cfg.seeds.monte_carlo
    assert saved["monte_carlo_simulations"] == cfg.risk.monte_carlo_simulations

    data = load_data(cfg, offline=True)
    assert saved["dataset_id"] == data.manifest.dataset_id
    dev_returns = data.simple_returns.loc[: cfg.chronology.development_end].copy()
    assert len(dev_returns) == 3020
    assert str(dev_returns.index[0].date()) == "2005-01-04"
    assert str(dev_returns.index[-1].date()) == "2016-12-30"

    # ------------------------------------------------------------------
    # 1. Export machine-readable CSV tables & copy validated JSON
    # ------------------------------------------------------------------
    (out_dir / "step5_development_c1_risk_tables.json").write_bytes(saved_json_path.read_bytes())

    all_comp_rows: list[dict[str, object]] = []
    for win_id in ("recent_development_1260d", "full_development_3020d"):
        for port_id in ("min_variance", "equal_weight", "benchmark_60_40"):
            all_comp_rows.extend(saved["comparison_tables"][win_id][port_id])
    comp_df = pd.DataFrame(all_comp_rows)
    comp_df.to_csv(
        out_dir / "01_c1_risk_comparison_all_confidences.csv",
        index=False,
        float_format="%.12g",
        na_rep="not_applicable",
    )

    mand_rows: list[dict[str, object]] = []
    for win_id in ("recent_development_1260d", "full_development_3020d"):
        for port_id in ("min_variance", "equal_weight", "benchmark_60_40"):
            mand_rows.extend(saved["mandatory_95_99_tables"][win_id][port_id])
    mand_df = pd.DataFrame(mand_rows)
    mand_df.to_csv(
        out_dir / "02_c1_mandatory_95_99_comparison.csv",
        index=False,
        float_format="%.12g",
        na_rep="not_applicable",
    )

    exp_rows: list[dict[str, object]] = []
    mv_meta = saved["exposures"]["min_variance"]
    for ticker in CANONICAL_TICKERS:
        exp_rows.append(
            {
                "ticker": ticker,
                "min_variance_terminal_504d_weight": mv_meta["weights"][ticker],
                "min_variance_last_scheduled_rebalance_2016_12_01_weight": mv_meta[
                    "last_scheduled_rebalance_2016_12_01_weights"
                ][ticker],
                "equal_weight_reference": saved["exposures"]["equal_weight"]["weights"][ticker],
                "benchmark_60_40_reference": saved["exposures"]["benchmark_60_40"]["weights"][ticker],
                "min_variance_estimation_start": mv_meta["estimation_start"],
                "min_variance_estimation_end": mv_meta["estimation_end"],
                "min_variance_n_estimation_sessions": mv_meta["n_estimation_sessions"],
            }
        )
    pd.DataFrame(exp_rows).to_csv(
        out_dir / "03_c1_fixed_exposures.csv",
        index=False,
        float_format="%.12g",
    )

    diag_rows: list[dict[str, object]] = []
    for win_id in ("recent_development_1260d", "full_development_3020d"):
        for port_id in ("min_variance", "equal_weight", "benchmark_60_40"):
            d = saved["fixed_exposure_diagnostics"][win_id][port_id]
            m = d["loss_moments"]
            st_rows = {r["series"]: r for r in d["stationarity_table"]}
            s_simple = st_rows[f"{port_id}_{win_id}_fixed_exposure_simple_return"]
            s_log = st_rows[f"{port_id}_{win_id}_fixed_exposure_log1p_return"]
            cw_rows = {r["series"]: r for r in saved["changing_weight_strategy_stationarity"][port_id]}
            cw_simple = cw_rows[f"{port_id}_simple_return"]
            cw_log = cw_rows[f"{port_id}_log1p_return"]
            diag_rows.append(
                {
                    "window_id": win_id,
                    "portfolio_id": port_id,
                    "n_obs": d["n_obs"],
                    "sample_start": d["sample_start"],
                    "sample_end": d["sample_end"],
                    "sample_loss_mean": m["sample_loss_mean"],
                    "sample_return_mean": m["sample_return_mean"],
                    "sample_loss_std_ddof1": m["sample_loss_std_ddof1"],
                    "sample_loss_skewness": m["sample_loss_skewness"],
                    "sample_loss_excess_kurtosis": m["sample_loss_excess_kurtosis"],
                    "sample_min_loss": m["sample_min_loss"],
                    "sample_max_loss": m["sample_max_loss"],
                    "fixed_exposure_simple_adf_stat": s_simple["adf_stat"],
                    "fixed_exposure_simple_p_value": s_simple["p_value"],
                    "fixed_exposure_simple_used_lag": s_simple["used_lag"],
                    "fixed_exposure_log1p_adf_stat": s_log["adf_stat"],
                    "fixed_exposure_log1p_p_value": s_log["p_value"],
                    "fixed_exposure_log1p_used_lag": s_log["used_lag"],
                    "changing_weight_net_2516d_simple_adf_stat": cw_simple["adf_stat"],
                    "changing_weight_net_2516d_simple_p_value": cw_simple["p_value"],
                    "changing_weight_net_2516d_log1p_adf_stat": cw_log["adf_stat"],
                    "changing_weight_net_2516d_log1p_p_value": cw_log["p_value"],
                }
            )
    pd.DataFrame(diag_rows).to_csv(
        out_dir / "04_c1_loss_moments_and_stationarity.csv",
        index=False,
        float_format="%.12g",
    )

    unc_rows: list[dict[str, object]] = []
    for win_id in ("recent_development_1260d", "full_development_3020d"):
        for c_key in ("c_90", "c_95", "c_99"):
            u = dict(saved["mc_uncertainty"][win_id][c_key])
            u["window_id"] = win_id
            u["portfolio_id"] = "min_variance"
            unc_rows.append(u)
    pd.DataFrame(unc_rows).to_csv(
        out_dir / "05_c1_mc_uncertainty_64seeds.csv",
        index=False,
        float_format="%.12g",
    )

    # Daily fixed-exposure 1-day pre-cost simple losses L_t = -(R_t @ w) through 2016-12-30
    loss_cols: dict[str, np.ndarray] = {}
    ret_mat = dev_returns.loc[:, list(CANONICAL_TICKERS)].to_numpy(dtype=np.float64)
    for port_id in ("min_variance", "equal_weight", "benchmark_60_40"):
        w_vec = np.array(
            [float(saved["exposures"][port_id]["weights"][t]) for t in CANONICAL_TICKERS],
            dtype=np.float64,
        )
        port_ret = ret_mat @ w_vec
        loss_cols[f"{port_id}_simple_return"] = port_ret
        loss_cols[f"{port_id}_loss"] = -port_ret
    daily_loss_df = pd.DataFrame(loss_cols, index=dev_returns.index)
    daily_loss_df["in_recent_1260d_window"] = False
    daily_loss_df.iloc[-1260:, daily_loss_df.columns.get_loc("in_recent_1260d_window")] = True
    daily_loss_df.to_csv(
        out_dir / "06_c1_fixed_exposure_daily_losses.csv",
        index_label="date",
        float_format="%.16g",
    )

    # ------------------------------------------------------------------
    # 2. Configure Matplotlib styling (matching Step 4 preview quality)
    # ------------------------------------------------------------------
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.labelsize": 9.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#AAB6C2",
            "axes.labelcolor": "#24364A",
            "text.color": "#182D43",
            "xtick.color": "#46586A",
            "ytick.color": "#46586A",
            "grid.color": "#DCE3E8",
            "grid.alpha": 0.65,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "svg.fonttype": "none",
        }
    )

    rendering_versions = {
        name: importlib.metadata.version(name)
        for name in ["matplotlib", "contourpy", "cycler", "fonttools", "kiwisolver", "pyparsing"]
    }
    (out_dir / "rendering-requirements.txt").write_text(
        "\n".join(f"{name}=={version}" for name, version in rendering_versions.items()) + "\n",
        encoding="utf-8",
    )

    subtitle_meta = (
        f"DEVELOPMENT ONLY (through {saved['development_end']})  |  1-day pre-cost simple loss L_t = -(R_t @ w)  |  "
        f"Notional USD {saved['nav_usd']:,.0f}  |  MC seed={saved['monte_carlo_seed']}, M={saved['monte_carlo_simulations']:,}\n"
        f"Dataset: {saved['dataset_id']}  |  Config SHA-256: {saved['config_hash']}"
    )
    footnote = (
        "DEVELOPMENT SAMPLE ONLY (<= 2016-12-30) | Provisional mandate constraints; committee decision pending. "
        "Selection (2017-2020) and evaluation (2021-2026) periods remain uninspected.\n"
        "All values are read directly from results/step5_development_c1_risk_tables.json. "
        "Positive numbers represent 1-day fractional/USD portfolio losses before transaction costs."
    )

    figures: list[tuple[str, str]] = []

    def _finish_figure(fig: plt.Figure, filename: str, title: str) -> None:
        fig.text(
            0.065,
            0.975,
            "QUANT EDGE  /  SOLO STEP 5 (C1)  /  DEVELOPMENT ONLY PREVIEW",
            fontsize=9,
            color="#147D73",
            weight="bold",
            va="top",
        )
        fig.text(0.065, 0.942, title, fontsize=18.0, weight="bold", va="top")
        fig.text(
            0.065,
            0.900,
            subtitle_meta,
            fontsize=8.3,
            color="#5C6C7A",
            va="top",
            linespacing=1.35,
        )
        fig.text(
            0.065,
            0.022,
            footnote,
            fontsize=7.8,
            color="#5C6C7A",
            va="bottom",
            linespacing=1.4,
        )
        fig.savefig(out_dir / f"{filename}.png", dpi=300)
        fig.savefig(out_dir / f"{filename}.svg")
        plt.close(fig)
        figures.append((filename, title))

    model_colors = {
        "historical": "#147D73",
        "parametric_normal": "#314C78",
        "monte_carlo_normal": "#CF6A32",
    }
    model_labels = {
        "historical": "Historical (empirical step-CDF / tail integral)",
        "parametric_normal": "Parametric Normal (closed-form ddof=1)",
        "monte_carlo_normal": f"Monte Carlo Normal (PCG64 seed={saved['monte_carlo_seed']}, M={saved['monte_carlo_simulations']:,})",
    }

    # ------------------------------------------------------------------
    # Figure 1: Same-Exposure 95% and 99% VaR & ES Comparison (Historical / Normal / MC)
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9.5))
    fig.subplots_adjust(left=0.065, right=0.975, top=0.785, bottom=0.125, hspace=0.44, wspace=0.20)

    win_specs = [
        (
            "recent_development_1260d",
            "Recent Dev Window: 2011-12-29 to 2016-12-30 (N = 1,260; post-GFC)",
        ),
        (
            "full_development_3020d",
            "Full Dev Window: 2005-01-04 to 2016-12-30 (N = 3,020; GFC included)",
        ),
    ]

    # Top row: Primary min_variance exposure across 95% VaR, 95% ES, 99% VaR, 99% ES
    metric_groups = [
        (0.95, "var_pct", "var_usd", "95% VaR"),
        (0.95, "es_pct", "es_usd", "95% ES"),
        (0.99, "var_pct", "var_usd", "99% VaR"),
        (0.99, "es_pct", "es_usd", "99% ES"),
    ]
    x_pos = np.arange(len(metric_groups)) * 1.15
    bar_w = 0.30

    for col_idx, (win_id, win_title) in enumerate(win_specs):
        ax = axes[0, col_idx]
        mv_rows = {
            (round(float(r["confidence"]), 2), r["model"]): r
            for r in saved["mandatory_95_99_tables"][win_id]["min_variance"]
        }
        max_v = 0.0
        for m_idx, m_name in enumerate(("historical", "parametric_normal", "monte_carlo_normal")):
            pct_vals = [float(mv_rows[(conf, m_name)][pct_k]) for conf, pct_k, _, _ in metric_groups]
            usd_vals = [float(mv_rows[(conf, m_name)][usd_k]) for conf, _, usd_k, _ in metric_groups]
            max_v = max(max_v, max(pct_vals))
            offset = (m_idx - 1) * bar_w
            bars = ax.bar(
                x_pos + offset,
                pct_vals,
                width=bar_w * 0.90,
                color=model_colors[m_name],
                label=model_labels[m_name],
            )
            for b_rect, p_val, u_val in zip(bars, pct_vals, usd_vals):
                ax.text(
                    b_rect.get_x() + b_rect.get_width() / 2.0,
                    p_val + max_v * 0.02 + (max_v * 0.055 if m_idx == 2 else 0.0),
                    f"{p_val:.2f}%\n(${u_val / 1000.0:.0f}k)",
                    ha="center",
                    va="bottom",
                    fontsize=6.9,
                    linespacing=1.05,
                )
        ax.set_xticks(x_pos, [label for _, _, _, label in metric_groups])
        ax.set_ylabel("1-day pre-cost loss (% of NAV)")
        ax.set_title(
            f"Primary min_variance (SPY 33.9%, AGG 40.0%, GLD 26.1%)\n{win_title}",
            loc="left",
            fontsize=9.6,
        )
        ax.set_ylim(0.0, max_v * 1.38)
        ax.grid(axis="y")
        ax.set_axisbelow(True)

    axes[0, 0].legend(
        loc="upper left",
        bbox_to_anchor=(0.0, 1.25),
        ncol=3,
        frameon=False,
        fontsize=8.5,
    )

    # Bottom row: 99% VaR and 99% ES across all 3 exposures (min_variance, equal_weight, benchmark_60_40)
    port_groups = [
        ("min_variance", "var_pct", "Min-Var\n99% VaR"),
        ("min_variance", "es_pct", "Min-Var\n99% ES"),
        ("equal_weight", "var_pct", "Equal-Wt\n99% VaR"),
        ("equal_weight", "es_pct", "Equal-Wt\n99% ES"),
        ("benchmark_60_40", "var_pct", "60/40\n99% VaR"),
        ("benchmark_60_40", "es_pct", "60/40\n99% ES"),
    ]
    x_port = np.arange(len(port_groups)) * 1.18
    bar_w_port = 0.30

    for col_idx, (win_id, win_title) in enumerate(win_specs):
        ax = axes[1, col_idx]
        max_v = 0.0
        for m_idx, m_name in enumerate(("historical", "parametric_normal", "monte_carlo_normal")):
            vals: list[float] = []
            for p_id, metric_key, _ in port_groups:
                row_99 = next(
                    r
                    for r in saved["mandatory_95_99_tables"][win_id][p_id]
                    if abs(float(r["confidence"]) - 0.99) <= 1e-9 and r["model"] == m_name
                )
                vals.append(float(row_99[metric_key]))
            max_v = max(max_v, max(vals))
            offset = (m_idx - 1) * bar_w_port
            bars = ax.bar(
                x_port + offset,
                vals,
                width=bar_w_port * 0.90,
                color=model_colors[m_name],
            )
            for b_rect, p_val in zip(bars, vals):
                ax.text(
                    b_rect.get_x() + b_rect.get_width() / 2.0,
                    p_val + max_v * 0.018 + (max_v * 0.055 if m_idx == 2 else 0.0),
                    f"{p_val:.2f}%",
                    ha="center",
                    va="bottom",
                    fontsize=6.8,
                )
        ax.set_xticks(x_port, [label for _, _, label in port_groups])
        ax.set_ylabel("1-day 99% loss (% of NAV)")
        ax.set_title(
            f"Cross-exposure 99% VaR & ES comparison (same dates & horizon)\n{win_title}",
            loc="left",
            fontsize=9.6,
        )
        ax.set_ylim(0.0, max_v * 1.32)
        ax.grid(axis="y")
        ax.set_axisbelow(True)

    _finish_figure(
        fig,
        "figure_01_c1_var_es_95_99_comparison",
        "Same-exposure 95% and 99% VaR and ES model comparison",
    )

    # ------------------------------------------------------------------
    # Figure 2: Fixed-Exposure 1-Day Loss Distribution with Selected Risk Markers
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(2, 1, figsize=(13.5, 9.5))
    fig.subplots_adjust(left=0.065, right=0.975, top=0.795, bottom=0.125, hspace=0.38)

    mv_losses_full_pct = daily_loss_df["min_variance_loss"].to_numpy(dtype=np.float64) * 100.0
    mv_losses_recent_pct = mv_losses_full_pct[-1260:]

    dist_panels = [
        (
            axes[0],
            "recent_development_1260d",
            mv_losses_recent_pct,
            "Panel A — Recent Development Window (2011-12-29 to 2016-12-30, N = 1,260 sessions; GFC precedes window)",
        ),
        (
            axes[1],
            "full_development_3020d",
            mv_losses_full_pct,
            "Panel B — Full Development Window (2005-01-04 to 2016-12-30, N = 3,020 sessions; includes 2007-2009 GFC)",
        ),
    ]

    for ax, win_id, losses_pct, panel_title in dist_panels:
        rows_map = {
            (round(float(r["confidence"]), 2), r["model"]): r
            for r in saved["mandatory_95_99_tables"][win_id]["min_variance"]
        }
        moments = saved["fixed_exposure_diagnostics"][win_id]["min_variance"]["loss_moments"]
        mu_loss_pct = float(moments["sample_loss_mean"]) * 100.0
        sd_loss_pct = float(moments["sample_loss_std_ddof1"]) * 100.0

        bins = np.linspace(float(np.min(losses_pct)) - 0.1, float(np.max(losses_pct)) + 0.1, 75)
        ax.hist(
            losses_pct,
            bins=bins,
            density=True,
            color="#CBD7E2",
            edgecolor="white",
            linewidth=0.4,
            alpha=0.88,
            label="Empirical 1-day loss histogram (L_t = -R_{p,t})",
        )

        x_grid = np.linspace(float(np.min(losses_pct)) - 0.15, float(np.max(losses_pct)) + 0.15, 600)
        gauss_pdf = (
            1.0
            / (sd_loss_pct * math.sqrt(2.0 * math.pi))
            * np.exp(-0.5 * ((x_grid - mu_loss_pct) / sd_loss_pct) ** 2)
        )
        ax.plot(
            x_grid,
            gauss_pdf,
            color="#314C78",
            linewidth=1.7,
            linestyle="-",
            label=f"Fitted Gaussian density (mean={mu_loss_pct:+.3f}%, sd={sd_loss_pct:.3f}%)",
        )

        marker_specs = [
            (0.95, "historical", "var_pct", "#147D73", "--", 1.5, "95% Hist VaR"),
            (0.95, "parametric_normal", "var_pct", "#314C78", "--", 1.4, "95% Normal VaR"),
            (0.99, "historical", "var_pct", "#147D73", "-", 2.0, "99% Hist VaR"),
            (0.99, "parametric_normal", "var_pct", "#314C78", "-", 1.8, "99% Normal VaR"),
            (0.99, "monte_carlo_normal", "var_pct", "#CF6A32", ":", 1.8, "99% MC VaR"),
            (0.99, "historical", "es_pct", "#9E2A2B", "-", 2.2, "99% Hist ES"),
            (0.99, "parametric_normal", "es_pct", "#6A4C93", "-.", 1.8, "99% Normal ES"),
            (0.99, "monte_carlo_normal", "es_pct", "#CF6A32", "-.", 1.7, "99% MC ES"),
        ]
        for conf, m_name, col_key, color, ls, lw, lbl in marker_specs:
            val_pct = float(rows_map[(conf, m_name)][col_key])
            ax.axvline(
                val_pct,
                color=color,
                linestyle=ls,
                linewidth=lw,
                label=f"{lbl}: {val_pct:.2f}%",
            )

        # Summary callout box with exact 95% and 99% VaR / ES numbers from saved JSON
        h95 = rows_map[(0.95, "historical")]
        n95 = rows_map[(0.95, "parametric_normal")]
        m95 = rows_map[(0.95, "monte_carlo_normal")]
        h99 = rows_map[(0.99, "historical")]
        n99 = rows_map[(0.99, "parametric_normal")]
        m99 = rows_map[(0.99, "monte_carlo_normal")]
        summary_box = (
            f"Saved Risk Markers (Notional USD 10M):\n"
            f"95% VaR: Hist {h95['var_pct']:.2f}% (${h95['var_usd']:,.0f}) | "
            f"Norm {n95['var_pct']:.2f}% (${n95['var_usd']:,.0f}) | "
            f"MC {m95['var_pct']:.2f}% (${m95['var_usd']:,.0f})\n"
            f"95% ES : Hist {h95['es_pct']:.2f}% (${h95['es_usd']:,.0f}) | "
            f"Norm {n95['es_pct']:.2f}% (${n95['es_usd']:,.0f}) | "
            f"MC {m95['es_pct']:.2f}% (${m95['es_usd']:,.0f})\n"
            f"99% VaR: Hist {h99['var_pct']:.2f}% (${h99['var_usd']:,.0f}) | "
            f"Norm {n99['var_pct']:.2f}% (${n99['var_usd']:,.0f}) | "
            f"MC {m99['var_pct']:.2f}% (${m99['var_usd']:,.0f})\n"
            f"99% ES : Hist {h99['es_pct']:.2f}% (${h99['es_usd']:,.0f}) | "
            f"Norm {n99['es_pct']:.2f}% (${n99['es_usd']:,.0f}) | "
            f"MC {m99['es_pct']:.2f}% (${m99['es_usd']:,.0f})\n"
            f"Moments: skew={moments['sample_loss_skewness']:+.2f}, "
            f"ex.kurt={moments['sample_loss_excess_kurtosis']:+.2f}, "
            f"max loss={float(moments['sample_max_loss']) * 100.0:.2f}%"
        )
        ax.text(
            0.015,
            0.95,
            summary_box,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=7.7,
            family="monospace",
            bbox={"boxstyle": "round,pad=0.45", "facecolor": "#F7FAFC", "edgecolor": "#CBD7E2"},
        )

        ax.set_title(panel_title, loc="left", fontsize=10.2)
        ax.set_xlabel("1-day fixed-exposure pre-cost portfolio loss L_t = -R_{p,t} (% of NAV; positive = loss)")
        ax.set_ylabel("Density")
        ax.legend(loc="upper right", ncol=2, frameon=True, facecolor="white", framealpha=0.92, fontsize=7.6)
        ax.grid(axis="x")
        ax.set_axisbelow(True)

    _finish_figure(
        fig,
        "figure_02_c1_fixed_exposure_loss_distribution",
        "Fixed-exposure 1-day loss distribution and VaR / ES tail markers",
    )

    # ------------------------------------------------------------------
    # Figure 3: Monte Carlo Normal Convergence & 64-Seed Sampling Uncertainty
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 7.2), sharey=False)
    fig.subplots_adjust(left=0.07, right=0.975, top=0.76, bottom=0.17, wspace=0.22)

    for col_idx, (win_id, win_title) in enumerate(win_specs):
        ax = axes[col_idx]
        u_map = saved["mc_uncertainty"][win_id]
        labels_x = ["90% VaR", "90% ES", "95% VaR", "95% ES", "99% VaR", "99% ES"]
        analytic_bps: list[float] = []
        primary_diff_bps: list[float] = []
        mean_diff_bps: list[float] = []
        se_bps: list[float] = []
        lo95_diff_bps: list[float] = []
        hi95_diff_bps: list[float] = []

        for c_key in ("c_90", "c_95", "c_99"):
            u = u_map[c_key]
            for metric_prefix in ("var", "es"):
                a_val = float(u[f"analytic_normal_{metric_prefix}_loss"])
                p_val = float(u[f"primary_seed_{metric_prefix}_loss"])
                m_val = float(u[f"empirical_{metric_prefix}_mean_across_seeds"])
                s_bps = float(u[f"empirical_{metric_prefix}_se_bps"])
                p025 = float(u[f"empirical_{metric_prefix}_p025"])
                p975 = float(u[f"empirical_{metric_prefix}_p975"])

                analytic_bps.append(a_val * 10_000.0)
                primary_diff_bps.append((p_val - a_val) * 10_000.0)
                mean_diff_bps.append((m_val - a_val) * 10_000.0)
                se_bps.append(s_bps)
                lo95_diff_bps.append((p025 - a_val) * 10_000.0)
                hi95_diff_bps.append((p975 - a_val) * 10_000.0)

        x_idx = np.arange(len(labels_x))
        ax.axhline(0.0, color="#314C78", linewidth=1.3, linestyle="--", label="Closed-form Parametric Normal baseline (0 bps diff)")

        # 95% empirical seed interval [p025, p975] across 64 seeds
        ax.vlines(
            x_idx,
            lo95_diff_bps,
            hi95_diff_bps,
            color="#8B9CA9",
            linewidth=2.2,
            label="95% empirical interval across 64 seeds [p025, p975]",
        )
        # +/- 1 empirical SE across 64 seeds
        ax.errorbar(
            x_idx,
            mean_diff_bps,
            yerr=se_bps,
            fmt="o",
            color="#147D73",
            capsize=4,
            markersize=5.5,
            label="64-seed MC mean +/- 1 empirical SE",
        )
        # Primary seed 202601
        ax.scatter(
            x_idx,
            primary_diff_bps,
            color="#CF6A32",
            s=52,
            zorder=5,
            marker="D",
            label=f"Primary seed {saved['monte_carlo_seed']} (M={saved['monte_carlo_simulations']:,})",
        )

        for i, (p_diff, s_val) in enumerate(zip(primary_diff_bps, se_bps)):
            ax.text(
                i,
                hi95_diff_bps[i] + 0.16,
                f"{p_diff:+.2f} bps\n(1-SE: {s_val:.2f})",
                ha="center",
                va="bottom",
                fontsize=7.1,
            )

        ax.set_xlim(-0.55, len(labels_x) - 0.45)
        ax.set_xticks(x_idx, labels_x)
        ax.set_ylabel("Monte Carlo minus Parametric Normal (bps of NAV; 1 bp = USD 1,000)")
        ax.set_title(f"min_variance MC sampling error vs. closed-form Normal\n{win_title}", loc="left", fontsize=9.6)
        y_min = min(lo95_diff_bps) - 0.85
        y_max = max(hi95_diff_bps) + 1.15
        ax.set_ylim(y_min, y_max)
        ax.yaxis.set_major_locator(MaxNLocator(6))
        ax.grid(axis="y")
        ax.set_axisbelow(True)

    axes[0].legend(loc="lower left", frameon=True, facecolor="white", framealpha=0.92, fontsize=8.0)

    _finish_figure(
        fig,
        "figure_03_c1_mc_sampling_uncertainty",
        "Monte Carlo Normal convergence and 64-seed sampling uncertainty",
    )

    # ------------------------------------------------------------------
    # 3. Write README.md, index.html, and manifest.json with SHA-256 hashes
    # ------------------------------------------------------------------
    (out_dir / "README.md").write_text(
        "# Verified Step 5 (C1) development risk figures and tables\n\n"
        f"- **Scope:** `{saved['scope']}` (development sample through `{saved['development_end']}`)\n"
        f"- **Active market dataset:** `{saved['dataset_id']}`\n"
        f"- **Configuration SHA-256:** `{saved['config_hash']}`\n"
        f"- **Mandate scale:** `USD {saved['nav_usd']:,.2f}`\n"
        f"- **Monte Carlo authority:** `seed = {saved['monte_carlo_seed']}`, `M = {saved['monte_carlo_simulations']:,}` draws\n\n"
        "All CSV tables and 300-dpi PNG / vector SVG figures in this directory are generated directly "
        "from `results/step5_development_c1_risk_tables.json` without implementing a second risk engine "
        "and without overwriting `results/development_preview/` (Step 4 preview). "
        "No post-2016 selection or evaluation strategy outcomes are computed or displayed.\n\n"
        "Reproduce from the repository root using the verified Python 3.11 `.venv`:\n\n"
        "```powershell\n"
        ".\\.venv\\Scripts\\python.exe scripts\\record_step5_c1_results.py\n"
        ".\\.venv\\Scripts\\python.exe scripts\\export_step5_c1_preview.py\n"
        "```\n",
        encoding="utf-8",
    )

    fig_sections = "".join(
        f'<section><h2>{html.escape(title)}</h2>'
        f'<a href="{fname}.png"><img src="{fname}.svg" alt="{html.escape(title)}"></a>'
        f'<p><a href="{fname}.png">300-dpi PNG</a> &middot; <a href="{fname}.svg">Vector SVG</a></p></section>'
        for fname, title in figures
    )
    csv_links = "".join(
        f'<li><a href="{p.name}">{p.name}</a></li>' for p in sorted(out_dir.glob("*.csv"))
    )
    html_table = mand_df[
        [
            "window_id",
            "portfolio_id",
            "model",
            "confidence",
            "n_obs",
            "sample_start",
            "sample_end",
            "var_loss",
            "var_pct",
            "var_usd",
            "es_loss",
            "es_pct",
            "es_usd",
            "diff_vs_parametric_normal_var_bps",
            "diff_vs_parametric_normal_es_bps",
            "status",
        ]
    ].to_html(index=False, na_rep="not_applicable", float_format=lambda v: f"{v:.6f}", border=0)

    index_html = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Quant Edge Step 5 (C1) development risk outputs</title>
<style>body{{font:15px/1.55 system-ui,sans-serif;background:#f1f5f8;color:#182d43;margin:0}}main{{max-width:1180px;margin:auto;padding:32px 24px}}h1{{font-size:30px;margin-bottom:10px}}section{{background:white;padding:22px;margin:22px 0;border:1px solid #dce3e8;border-radius:12px}}img{{width:100%;height:auto}}a{{color:#147d73}}.notice{{background:#e2eeec;padding:18px;border-left:5px solid #147d73}}table{{border-collapse:collapse;font-size:12.5px;width:100%}}td,th{{padding:7px;border-bottom:1px solid #dde4e9;text-align:right}}td:first-child,th:first-child,td:nth-child(2),th:nth-child(2),td:nth-child(3),th:nth-child(3){{text-align:left}}.scroll{{overflow:auto}}code{{font-size:12px;overflow-wrap:anywhere}}</style>
<main><p>QUANT EDGE / COMPLETED SOLO STEP 5 (C1)</p><h1>Verified development VaR and ES outputs (through 2016-12-30)</h1>
<div class="notice"><strong>DEVELOPMENT ONLY:</strong> All figures and tables are restricted to the development sample ending <code>{saved['development_end']}</code>. Selection (<code>2017-2020</code>) and evaluation (<code>2021-2026</code>) periods remain untouched. EVT POT-GPD (Step 7), rolling backtests (Step 6), and stress/risk-budgeting (Step 8) are not yet executed.<br><strong>Provenance:</strong> Dataset <code>{saved['dataset_id']}</code> | Config <code>{saved['config_hash']}</code> | MC seed <code>{saved['monte_carlo_seed']}</code> (<code>M = {saved['monte_carlo_simulations']:,}</code>) | Notional <code>USD {saved['nav_usd']:,.0f}</code>.</div>
{fig_sections}
<section><h2>Mandatory 95% and 99% VaR / ES comparison table</h2><div class="scroll">{html_table}</div></section>
<section><h2>Machine-readable CSV and JSON exports</h2><ul>{csv_links}</ul><p><a href="step5_development_c1_risk_tables.json">step5_development_c1_risk_tables.json (RFC 8259 strict JSON)</a></p></section>
</main></html>"""
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": saved["scope"],
        "development_end": saved["development_end"],
        "dataset_id": saved["dataset_id"],
        "config_hash": saved["config_hash"],
        "monte_carlo_seed": saved["monte_carlo_seed"],
        "monte_carlo_simulations": saved["monte_carlo_simulations"],
        "nav_usd": saved["nav_usd"],
        "rendering_versions": rendering_versions,
        "numerical_authority_json": "results/step5_development_c1_risk_tables.json",
        "numerical_authority_sha256": _sha256(saved_json_path),
        "source_sha256": {
            rel: _sha256(ROOT / rel)
            for rel in (
                "src/quantedge/es.py",
                "src/quantedge/var.py",
                "scripts/record_step5_c1_results.py",
                "scripts/export_step5_c1_preview.py",
            )
        },
        "artifacts_sha256": {
            p.name: _sha256(p)
            for p in sorted(out_dir.iterdir())
            if p.is_file() and p.name != "manifest.json"
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(figures)} figures (PNG + SVG), 6 CSV tables, JSON, index.html, and manifest.json to {out_dir}")


if __name__ == "__main__":
    main()
