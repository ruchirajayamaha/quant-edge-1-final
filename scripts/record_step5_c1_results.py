"""Compute and record Step 5 (C1) development risk tables and generate c_var_es_and_evt.md."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quantedge.config import load_config
from quantedge.data import load_data
from quantedge.var import build_development_c1_risk_bundle, serialize_c1_risk_bundle


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_non_json_number(token: str) -> None:
    raise ValueError(f"Non-standard JSON numeric token encountered: {token}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "config.yaml")
    data = load_data(cfg, offline=True)
    dev_returns = data.simple_returns.loc[: cfg.chronology.development_end].copy()

    bundle = build_development_c1_risk_bundle(dev_returns, cfg)
    serializable = serialize_c1_risk_bundle(bundle, dataset_id=data.manifest.dataset_id)

    results_dir = root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "step5_development_c1_risk_tables.json"
    json_text = json.dumps(serializable, indent=2, allow_nan=False) + "\n"
    # Verify strict RFC 8259 parsing before writing
    json.loads(json_text, parse_constant=_reject_non_json_number)
    json_path.write_text(json_text, encoding="utf-8")

    # Format Markdown tables directly from the computed bundle
    mv_w = bundle["exposures"]["min_variance"]["weights"]
    mv_rebal_w = bundle["exposures"]["min_variance"]["last_scheduled_rebalance_2016_12_01_weights"]
    eq_w = bundle["exposures"]["equal_weight"]["weights"]
    bm_w = bundle["exposures"]["benchmark_60_40"]["weights"]

    def _fmt_comp_table(win_id: str, port_id: str) -> str:
        df = bundle["comparison_tables"][win_id][port_id]
        lines = [
            "| Model | Confidence | `VaR` (Fraction) | `VaR` (`%`) | `VaR` (`USD` on `10M`) | `ES` (Fraction) | `ES` (`%`) | `ES` (`USD` on `10M`) | `VaR - Normal` (`bps`) | `ES - Normal` (`bps`) | Status |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for r in df.to_dict(orient="records"):
            lines.append(
                f"| `{r['model']}` | `{r['confidence']:.2f}` | `{r['var_loss']:.9f}` | "
                f"`{r['var_pct']:.4f}%` | `{r['var_usd']:,.2f}` | `{r['es_loss']:.9f}` | "
                f"`{r['es_pct']:.4f}%` | `{r['es_usd']:,.2f}` | "
                f"`{r['diff_vs_parametric_normal_var_bps']:+.4f}` | "
                f"`{r['diff_vs_parametric_normal_es_bps']:+.4f}` | `{r['status']}` |"
            )
        return "\n".join(lines)

    def _fmt_mc_uncertainty_table(win_id: str) -> str:
        u_map = bundle["mc_uncertainty"][win_id]
        lines = [
            "| Confidence | Analytic `VaR` | Primary Seed `202601` `VaR` | `MC - Analytic` `VaR` (`bps`) | Empirical `VaR` SE (`bps`, `64` seeds) | Asymptotic `VaR` SE (`bps`) | Analytic `ES` | Primary Seed `202601` `ES` | `MC - Analytic` `ES` (`bps`) | Empirical `ES` SE (`bps`, `64` seeds) | `95%` Seed Interval `VaR` | `95%` Seed Interval `ES` |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ]
        for key in ("c_90", "c_95", "c_99"):
            u = u_map[key]
            lines.append(
                f"| `{u['confidence']:.2f}` | `{u['analytic_normal_var_loss']:.9f}` | "
                f"`{u['primary_seed_var_loss']:.9f}` | "
                f"`{u['primary_seed_var_diff_vs_analytic'] * 10000.0:+.4f}` | "
                f"`{u['empirical_var_se_bps']:.4f}` | `{u['asymptotic_var_se'] * 10000.0:.4f}` | "
                f"`{u['analytic_normal_es_loss']:.9f}` | `{u['primary_seed_es_loss']:.9f}` | "
                f"`{u['primary_seed_es_diff_vs_analytic'] * 10000.0:+.4f}` | "
                f"`{u['empirical_es_se_bps']:.4f}` | "
                f"`[{u['empirical_var_p025']:.6f}, {u['empirical_var_p975']:.6f}]` | "
                f"`[{u['empirical_es_p025']:.6f}, {u['empirical_es_p975']:.6f}]` |"
            )
        return "\n".join(lines)

    def _fmt_moments_and_adf_table() -> str:
        lines = [
            "| Window (`n_obs`, Bounds) | Portfolio Exposure | Mean Loss | Loss Std (`ddof=1`) | Loss Skewness | Loss Excess Kurtosis | Max 1-Day Loss | Min 1-Day Loss (Max Gain) | Fixed-Exposure Simple ADF (`lags`) | Fixed-Exposure `log1p` ADF (`lags`) | Changing-Weight Net Strategy Simple / `log1p` ADF (`2,516d`) |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
        ]
        for win_id in ("recent_development_1260d", "full_development_3020d"):
            for port_id in ("min_variance", "equal_weight", "benchmark_60_40"):
                diag = bundle["fixed_exposure_diagnostics"][win_id][port_id]
                m = diag["loss_moments"]
                st = diag["stationarity_table"]
                s_simple = st.iloc[0]
                s_log = st.iloc[1]
                cw = bundle["changing_weight_strategy_stationarity"][port_id]
                cw_s = cw.loc[cw["series"] == f"{port_id}_simple_return"].iloc[0]
                cw_l = cw.loc[cw["series"] == f"{port_id}_log1p_return"].iloc[0]
                lines.append(
                    f"| `{win_id}` (`{diag['n_obs']}`, `{diag['sample_start']}..{diag['sample_end']}`) | "
                    f"`{port_id}` | `{m['sample_loss_mean']:+.9f}` | `{m['sample_loss_std_ddof1']:.9f}` | "
                    f"`{m['sample_loss_skewness']:+.6f}` | `{m['sample_loss_excess_kurtosis']:+.6f}` | "
                    f"`{m['sample_max_loss']:.6f}` | `{m['sample_min_loss']:+.6f}` | "
                    f"`{float(s_simple['adf_stat']):.4f}` (`p={float(s_simple['p_value']):.2e}`, `lag={int(s_simple['used_lag'])}`) | "
                    f"`{float(s_log['adf_stat']):.4f}` (`p={float(s_log['p_value']):.2e}`, `lag={int(s_log['used_lag'])}`) | "
                    f"`{float(cw_s['adf_stat']):.4f}` / `{float(cw_l['adf_stat']):.4f}` (`lag={int(cw_s['used_lag'])}`) |"
                )
        return "\n".join(lines)

    weight_rows = [
        "| Canonical Ticker | `min_variance` (`2015-01-02..2016-12-30`, `504d` Target) | `min_variance` (`2016-12-01` Last Scheduled Rebalance) | `equal_weight` Reference | `benchmark_60_40` Reference |",
        "|---|---:|---:|---:|---:|",
    ]
    for t in ("SPY", "EFA", "EEM", "AGG", "GLD", "XLE", "XLK"):
        weight_rows.append(
            f"| `{t}` | `{mv_w[t]:.9f}` | `{mv_rebal_w[t]:.9f}` | `{eq_w[t]:.9f}` | `{bm_w[t]:.9f}` |"
        )
    weight_table_md = "\n".join(weight_rows)

    doc_content = f"""# Section C — Value-at-Risk (VaR) and Expected Shortfall (ES) Methodology & Development Diagnostics (`SOLO STEP 5 / C1`)

- **Active market snapshot (`r3_release_evidence`):** `{data.manifest.dataset_id}` (`schema_version = "1.1.0"`)
- **Configuration SHA-256 (`config_hash`):** `{bundle["config_hash"]}`
- **Mandate scale (`nav_usd`):** `USD 10,000,000.00`
- **Monte Carlo authority (`config.yaml`):** `monte_carlo_simulations = {bundle["monte_carlo_simulations"]}`, `seeds.monte_carlo = {bundle["monte_carlo_seed"]}`
- **Holdout discipline:** All real-data risk tables in this section are restricted to the **development period through `{bundle["development_end"]}`**. Selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy outcomes remain uncomputed and uninspected. Unconditional POT-GPD Extreme Value Theory (`C2/C3`) is scheduled for **SOLO STEP 7**.
- **Saved numerical source of truth:** `results/step5_development_c1_risk_tables.json` (strictly RFC 8259 compliant via `allow_nan=False`, with `null` for non-applicable `seed` and `monte_carlo_simulations` metadata on non-Monte-Carlo rows)
- **Exported CSV tables & PNG/SVG figures:** `results/step5_c1_preview/` (`01_c1_risk_comparison_all_confidences.csv` through `06_c1_fixed_exposure_daily_losses.csv`, `figure_01_c1_var_es_95_99_comparison.{{png,svg}}`, `figure_02_c1_fixed_exposure_loss_distribution.{{png,svg}}`, `figure_03_c1_mc_sampling_uncertainty.{{png,svg}}`, `index.html`, and `manifest.json`)

---

## 1. Mathematical Specifications & Shared Conventions (`src/quantedge/var.py`, `src/quantedge/es.py`)

### 1.1 Fixed-Exposure One-Day Simple-Return Loss Convention & Aggregation Exception
For a fixed portfolio weight vector $w = (w_{{\\text{{SPY}}}}, w_{{\\text{{EFA}}}}, w_{{\\text{{EEM}}}}, w_{{\\text{{AGG}}}}, w_{{\\text{{GLD}}}}, w_{{\\text{{XLE}}}}, w_{{\\text{{XLK}}}})^\\top$ ($\\sum_{{i=1}}^7 w_i = 1$) and historical simple asset return matrix $R \\in \\mathbb{{R}}^{{n \\times 7}}$, the one-day fixed-exposure portfolio simple return and pre-transaction-cost loss on session $t$ are:
$$R_{{p,t}} = \\sum_{{i=1}}^7 w_i R_{{i,t}} = (R w)_t, \\qquad L_t = -R_{{p,t}}.$$

- **Sign orientation:** Positive values of $L_t$, $\\text{{VaR}}_c$, and $\\text{{ES}}_c$ represent one-day fractional losses before transaction costs ($\\text{{USD loss}} = \\text{{loss fraction}} \\times 10{{,}}000{{,}}000$). Nonpositive loss quantiles ($\\text{{VaR}}_c \\le 0$ or $\\text{{ES}}_c \\le 0$, corresponding to tail outcomes that are still net gains) are preserved with their exact sign and are **never** masked with `abs()` or floored at `0.0`.
- **Simple-return modelling exception:** Cross-sectional portfolio value changes aggregate linearly in simple returns ($R_{{p,t}} = \\sum_i w_i R_{{i,t}}$), whereas log returns are time-additive but not linearly additive across assets ($\\log(1 + \\sum_i w_i R_{{i,t}}) \\ne \\sum_i w_i \\log(1 + R_{{i,t}})$). All committee risk models therefore operate on one-day simple portfolio losses $L_t = -R_{{p,t}}$, while log returns $\\log(1 + R_{{p,t}})$ are also inspected in ADF stationarity diagnostics.

### 1.2 Historical Simulation VaR and Exact Empirical Tail-Integral ES (`empirical_tail_weights`)
Given $n \\ge 2$ finite historical loss observations $L_1, \\dots, L_n$ (each carrying empirical probability mass $1/n$), let $L_{{(1)}} \\le L_{{(2)}} \\le \\dots \\le L_{{(n)}}$ denote the ascending order statistics and $L_{{[1]}} \\ge L_{{[2]}} \\ge \\dots \\ge L_{{[n]}}$ denote the descending (worst-first) order statistics ($L_{{[j]}} = L_{{(n - j + 1)}}$):

1. **Historical VaR (`method="inverted_cdf"`, Hyndman-Fan Type 1):**
   $$\\text{{VaR}}_c^{{\\text{{hist}}}} = F_n^{{-1}}(c) = \\inf\\{{x \\in \\mathbb{{R}} : F_n(x) \\ge c\\}} = L_{{(\\lceil n c \\rceil)}}.$$
2. **Historical ES (`empirical_tail_weights`):**
   Expected Shortfall integrates the empirical quantile function over the worst $\\alpha = 1 - c$ probability mass:
   $$\\text{{ES}}_c^{{\\text{{hist}}}} = \\frac{{1}}{{\\alpha}} \\int_c^1 F_n^{{-1}}(u)\\,du = \\sum_{{i=1}}^n w_{{\\text{{tail}},i}}\\,L_i, \\qquad \\sum_{{i=1}}^n w_{{\\text{{tail}},i}} = 1.$$
   Let $m = n \\alpha = n(1 - c)$ be the exact number of worst observations required to cover probability mass $\\alpha$, and let $k_{{\\text{{slots}}}} = \\lceil m \\rceil \\in \\{{1, \\dots, n\\}}$. The order-statistic boundary loss is $u_* = L_{{[k_{{\\text{{slots}}}}]}}$:
   - Every observation strictly exceeding the boundary ($L_i > u_*$, count $k_{{\\text{{strict}}}} < m$) receives full normalized mass:
     $$w_{{\\text{{tail}},i}} = \\frac{{1/n}}{{\\alpha}} = \\frac{{1}}{{m}}.$$
   - All observations tied at the boundary ($L_i = u_*$, count $k_{{\\text{{tie}}}} \\ge 1$) split the remaining required tail mass $\\alpha - k_{{\\text{{strict}}}}/n = (m - k_{{\\text{{strict}}}})/n$ equally:
     $$w_{{\\text{{tail}},i}} = \\frac{{\\alpha - k_{{\\text{{strict}}}}/n}}{{\\alpha \\cdot k_{{\\text{{tie}}}}}} = \\frac{{m - k_{{\\text{{strict}}}}}}{{m \\cdot k_{{\\text{{tie}}}}}}.$$
   - All observations strictly below $u_*$ ($L_i < u_*$) receive $w_{{\\text{{tail}},i}} = 0$.
   - Because $u_*$ is an actual sample order statistic rather than a linearly interpolated value between adjacent order statistics, $0 \\le k_{{\\text{{strict}}}} < m \\le k_{{\\text{{strict}}}} + k_{{\\text{{tie}}}}$ holds for every sample size $n$ and confidence $c \\in (0, 1)$, guaranteeing $\\text{{ES}}_c^{{\\text{{hist}}}} \\ge \\text{{VaR}}_c^{{\\text{{hist}}}}$, confidence monotonicity, and exact cross-asset Euler ES additivity ($\\sum_{{j=1}}^7 w_j (w_{{\\text{{tail}}}}^\\top (-R_{{\\cdot,j}})) = \\text{{ES}}_c^{{\\text{{hist}}}}$).

### 1.3 Shared Normal Moments (`normal_moments`) and Parametric Normal VaR & ES
`normal_moments(asset_returns)` computes the canonical 7-ETF arithmetic sample mean vector $\\hat{{\\mu}} \\in \\mathbb{{R}}^7$ and unbiased sample covariance matrix $\\hat{{\\Sigma}} \\in \\mathbb{{R}}^{{7 \\times 7}}$ with `ddof = 1`:
$$\\hat{{\\mu}} = \\frac{{1}}{{n}}\\sum_{{t=1}}^n R_t, \\qquad \\hat{{\\Sigma}} = \\frac{{1}}{{n - 1}}\\sum_{{t=1}}^n (R_t - \\hat{{\\mu}})(R_t - \\hat{{\\mu}})^\\top.$$
For fixed portfolio weights $w$, the portfolio daily simple-return mean and variance are $\\mu_p = w^\\top \\hat{{\\mu}}$ and $\\sigma_p^2 = w^\\top \\hat{{\\Sigma}} w$ ($\\sigma_p = \\sqrt{{\\max(0, \\sigma_p^2)}}$). With standard normal quantile $z_c = \\Phi^{{-1}}(c)$ and standard normal density $\\phi(z_c) = \\frac{{1}}{{\\sqrt{{2\\pi}}}}e^{{-z_c^2/2}}$:
$$\\text{{VaR}}_c^{{\\text{{norm}}}} = -\\mu_p + \\sigma_p z_c, \\qquad \\text{{ES}}_c^{{\\text{{norm}}}} = -\\mu_p + \\sigma_p \\frac{{\\phi(z_c)}}{{1 - c}}.$$
- **Degenerate zero volatility ($\\sigma_p = 0$):** Handled without division by zero or `NaN`; all three C1 models return finite deterministic loss $\\text{{VaR}}_c = \\text{{ES}}_c = -\\mu_p$ with `status = "warning"` and `diagnostics["zero_portfolio_volatility"] = True`.
- **Unbounded Gaussian simple-return approximation:** The normal model $R_t \\sim \\mathcal{{N}}(\\hat{{\\mu}}, \\hat{{\\Sigma}})$ is an unbounded continuous approximation on $(-\\infty, +\\infty)$ even though theoretical long-only simple returns cannot fall below $-100\\%$ ($L_t \\le 1.0$). Draws and quantiles are never artificially truncated at $-1.0$.

### 1.4 Seeded Multivariate Normal Monte Carlo (`monte_carlo_normal`) & Uncertainty Quantification
Using the **exact same** fitted asset moments $(\\hat{{\\mu}}, \\hat{{\\Sigma}}) = \\text{{normal\\_moments}}(\\text{{train\\_asset\\_returns}})$, `monte_carlo_normal` eigendecomposes $\\hat{{\\Sigma}} = V \\,\\text{{diag}}(\\max(\\lambda, 0))\\, V^\\top$, initializes NumPy's PCG64 generator `np.random.default_rng(seed)` (defaulting to `config.seeds.monte_carlo = 202601`), draws $M = 25{{,}}000$ (`config.risk.monte_carlo_simulations`) 7-ETF return vectors $R_{{\\text{{sim}}}} \\sim \\mathcal{{N}}_7(\\hat{{\\mu}}, \\hat{{\\Sigma}})$, projects one-day portfolio losses $L_{{\\text{{sim}}}} = -(R_{{\\text{{sim}}}} w) \\in \\mathbb{{R}}^M$, and applies `empirical_var_and_es` to $L_{{\\text{{sim}}}}$. Simulated asset return draws are cached in memory by `(moments_digest, seed, n_simulations)` so multi-confidence and multi-portfolio calls on the same window do not re-simulate.

---

## 2. Development-Period Fixed Exposures & Window Policy (`<= 2016-12-30`)

### 2.1 Evaluated Fixed Portfolio Exposures
{weight_table_md}

### 2.2 Development Diagnostic Windows & Truthful Crisis Coverage
- **`recent_development_1260d` (`2011-12-29` to `2016-12-30`, $N = 1{{,}}260$ trading sessions):**
  Trailing `1,260`-session (`dashboard_risk_window_days`) window at the end of the development period.
  - **Crisis coverage:** `included_scenarios = ()`. The 2007–2009 Global Financial Crisis (`2007-10-09..2009-03-09`) precedes `2011-12-29` (`pre_window_omitted`), and both `covid_2020` (`2020-02-19..2020-03-23`) and `rate_shock_2022` (`2022-01-03..2022-10-14`) lie in the post-2016 holdout period (`post_window_not_in_sample`).
- **`full_development_3020d` (`2005-01-04` to `2016-12-30`, $N = 3{{,}}020$ trading sessions):**
  Complete development-period simple-return sample.
  - **Crisis coverage:** `included_scenarios = ("gfc_2007_2009",)`. Fully includes the 2007–2009 Global Financial Crisis (`2007-10-09..2009-03-09`) and excludes post-2016 `covid_2020` and `rate_shock_2022` (`post_window_not_in_sample`).

---

## 3. Matched Development Risk Comparison Tables (`90%`, `95%`, `99%`; Mandatory `95%` & `99%` Highlighted)

### 3.1 Recent Development Window (`recent_development_1260d`: `2011-12-29..2016-12-30`, $N = 1{{,}}260$)

#### A. Constrained Minimum Variance (`min_variance`)
{_fmt_comp_table("recent_development_1260d", "min_variance")}

#### B. Equal-Weight Reference (`equal_weight`)
{_fmt_comp_table("recent_development_1260d", "equal_weight")}

#### C. 60/40 Benchmark Reference (`benchmark_60_40`)
{_fmt_comp_table("recent_development_1260d", "benchmark_60_40")}

### 3.2 Full Development Window (`full_development_3020d`: `2005-01-04..2016-12-30`, $N = 3{{,}}020$, GFC-Inclusive)

#### A. Constrained Minimum Variance (`min_variance`)
{_fmt_comp_table("full_development_3020d", "min_variance")}

#### B. Equal-Weight Reference (`equal_weight`)
{_fmt_comp_table("full_development_3020d", "equal_weight")}

#### C. 60/40 Benchmark Reference (`benchmark_60_40`)
{_fmt_comp_table("full_development_3020d", "benchmark_60_40")}

---

## 4. Monte Carlo Sampling Uncertainty (`M = 25,000` Draws, `64` Independent Seeds `202601..202664`)

### 4.1 Recent Development Window (`recent_development_1260d`, `min_variance`)
{_fmt_mc_uncertainty_table("recent_development_1260d")}

### 4.2 Full Development Window (`full_development_3020d`, `min_variance`)
{_fmt_mc_uncertainty_table("full_development_3020d")}

- **Precision & tolerance interpretation:** At $M = 25{{,}}000$ multivariate normal draws, empirical 1-SE simulation noise across 64 independent seeds on `min_variance` is `0.34–0.91 bps` (`USD 339–908`) on `recent_development_1260d` and `0.61–1.68 bps` (`USD 606–1,680`) on `full_development_3020d`. Primary seed `202601` agrees with closed-form `parametric_normal` within `0.09–1.41 bps` across all confidence levels (`< 1.2 SE`).

---

## 5. Fixed-Exposure Risk Series vs. Changing-Weight Strategy Series Diagnostics

{_fmt_moments_and_adf_table()}

### Empirical Interpretation of Historical vs. Gaussian Risk Differences
1. **Leptokurtic Shoulder vs. Extreme-Tail Crossing:**
   - On `full_development_3020d` (`2005-01-04..2016-12-30`), mixing the 2007–2009 GFC with calmer years produces extreme loss excess kurtosis (`+14.33` on `min_variance`, `+14.63` on `equal_weight`, `+22.04` on `benchmark_60_40`). Because a leptokurtic distribution concentrates probability mass both in the narrow central peak and in the far tails while depleting the intermediate shoulders, **90% and 95% Historical VaR lie below Parametric Normal VaR** on `full_development_3020d` (by `-14.11 bps` and `-5.76 bps` on `min_variance`), whereas **95% Historical ES already exceeds Parametric Normal ES by `+16.49 bps`** (`1.2704%` vs. `1.1055%`) because ES integrates across the heavy tail beyond the 95% quantile.
   - At **99% confidence**, we are past the distribution's shoulder into the fat tail across all portfolios and both windows: on `min_variance`, 99% Historical VaR exceeds Parametric Normal VaR by `+14.07 bps` (`1.0414%` vs. `0.9006%`) in `recent_development_1260d` and by `+23.20 bps` (`1.4824%` vs. `1.2504%`) in `full_development_3020d`, while **99% Historical ES exceeds Parametric Normal ES by `+46.74 bps` (`1.5018%` vs. `1.0344%`, `1.45x`) in `recent_development_1260d` and by `+72.27 bps` (`2.1595%` vs. `1.4368%`, `1.50x`) in `full_development_3020d`**.
2. **Distinction Between Fixed-Exposure Risk Series and Changing-Weight Net Strategy Series:**
   - Point-in-time risk estimation (`estimate_risk`) evaluates the historical distribution of the **current fixed weight vector** $w$ (`R_{{p,t}} = (R w)_t$, pre-cost, $N = 1{{,}}260$ or $N = 3{{,}}020$), whereas Step 4's performance KPIs evaluate the **changing-weight, monthly-rebalanced, post-cost** strategy trajectory (`path.net_returns`, $N = 2{{,}}516$ active sessions `2007-01-05..2016-12-30`). Both series strongly reject a unit root in ADF diagnostics, though ADF unit-root rejection does not imply independent and identically distributed (`i.i.d.`) losses or constant conditional volatility.

---

## 6. Bounded Step 5 Review Corrections (`R1–R2`) & Visible Output Exports

1. **`R1` — Coherent Configuration Propagation Across Primary Estimates, Bundle Metadata & MC Uncertainty:**
   - While preserving the frozen `D0` public signature `estimate_risk(train_asset_returns, weights, *, model, confidence, seed=None) -> RiskEstimate`, internal helper `_estimate_risk_with_settings` and table/uncertainty builders (`compare_risk_models_table`, `quantify_monte_carlo_uncertainty`, `build_development_c1_risk_bundle`) route a single resolved `AppConfig` (`resolve_risk_runtime_settings(config, seed=..., n_simulations=...)`).
   - Any caller-supplied `AppConfig` (e.g., custom `monte_carlo_simulations`, `seeds.monte_carlo`, `nav_usd`, `estimation_window_days`, or `dashboard_risk_window_days`) is applied consistently across the primary `monte_carlo_normal` comparison estimates, bundle metadata, and `mc_uncertainty` replications, and `displayed_precision_note` dynamically reports the actual resolved draw count and empirical standard errors.
2. **`R2` — Strict RFC 8259 JSON Serialization (`allow_nan=False`):**
   - Non-applicable metadata columns (`seed` and `monte_carlo_simulations` on `'historical'` and `'parametric_normal'` rows, and `reason` on `status='ok'` rows) are preserved as `None` (serialized as JSON `null`, never bare `NaN`) via `comparison_table_to_records` and `serialize_c1_risk_bundle`, while invalid non-finite core risk values on `status='ok'` rows raise `ValueError` rather than being masked as `0.0`.
   - `results/step5_development_c1_risk_tables.json` is serialized with `json.dumps(..., allow_nan=False)` and verified with `json.loads(..., parse_constant=...)`, with `0.0` (0-ULP) change across all `54` baseline risk rows relative to `audit/step5_review/baseline_step5_results.json`.
3. **Exported Development-Only Tables & Figures (`results/step5_c1_preview/`):**
   - `01_c1_risk_comparison_all_confidences.csv` (`54` rows) & `02_c1_mandatory_95_99_comparison.csv` (`36` rows)
   - `03_c1_fixed_exposures.csv`, `04_c1_loss_moments_and_stationarity.csv`, `05_c1_mc_uncertainty_64seeds.csv`, & `06_c1_fixed_exposure_daily_losses.csv` (`3,020` sessions)
   - `figure_01_c1_var_es_95_99_comparison.png` (`300 dpi`) & `.svg`
   - `figure_02_c1_fixed_exposure_loss_distribution.png` (`300 dpi`) & `.svg`
   - `figure_03_c1_mc_sampling_uncertainty.png` (`300 dpi`) & `.svg`
"""

    doc_path = root / "docs" / "sections" / "c_var_es_and_evt.md"
    doc_path.write_text(doc_content, encoding="utf-8")
    print("Wrote JSON:", json_path.relative_to(root).as_posix(), _sha256(json_path))
    print("Wrote Doc:", doc_path.relative_to(root).as_posix(), _sha256(doc_path))


if __name__ == "__main__":
    main()
