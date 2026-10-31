 (C2/C3) — Unconditional Peaks-Over-Threshold (POT-GPD) EVT & Tail Uncertainty

- **Scope & Holdout Discipline:** Real-data fits are strictly restricted to the **development period through `2016-12-30`**. No selection (`2017-01-03..2020-12-31`) or evaluation (`2021-01-04..2026-10-30`) strategy outcomes were inspected or computed. EVT uses the exact same `min_variance` terminal exposure and identical recent (1,260 sessions) and full (3,020 sessions) windows as C1. Neither window includes COVID-19 (2020) or the 2022 rate shock.
- **Primary Threshold Policy (Inherited, Not Tuned):** $q = 0.95$ loss quantile under the empirical step-CDF order statistic convention ($u = L_{(\lceil n \cdot 0.95 \rceil)}$), strict exceedances $L > u$, minimum $N_u \ge 50$ (`config.risk.evt_threshold_quantile`, `evt_min_exceedances`). If $N_u < 50$, the fit is marked `unavailable`; the threshold or minimum is never lowered silently.
- **Authority Artifacts:** `results/step7_evt_preview/step7_recorded_results.json` (strict RFC 8259, `allow_nan=False`), `table_01_risk_model_comparison.{csv,md}`, `table_02_threshold_diagnostics.{csv,md}`, `table_03_bootstrap_uncertainty.{csv,md}`, `figure_01_threshold_stability_and_mrl.{png,svg}`, `figure_02_gpd_tail_qq_pp_diagnostics.{png,svg}`, `figure_03_risk_model_and_uncertainty_comparison.{png,svg}`, `manifest.json`, and `index.html`.

### 7.1 Mathematical Formulation (`src/quantedge/evt.py`)

#### 7.1.1 Generalized Pareto Distribution (GPD)
For fixed-exposure 1-day portfolio losses $L_t = -(R_{p,t}) = -(R_t w)$, let $u$ denote the threshold and $y_j = L_j - u > 0$ denote strict excesses ($j = 1, \dots, N_u$). Under the Pickands-Balkema-de Haan theorem, the excess distribution converges asymptotically to the Generalized Pareto Distribution with location fixed at $0$, scale $\beta > 0$, and shape $\xi \in (-\infty, +\infty)$:
$$G_{\xi, \beta}(y) = 1 - \left(1 + \frac{\xi y}{\beta}\right)^{-1/\xi}, \qquad y \ge 0 \quad (\text{for } \xi \ge 0), \quad 0 \le y \le -\frac{\beta}{\xi} \quad (\text{for } \xi < 0).$$

#### 7.1.2 Pure POT VaR and ES Formulas
With empirical exceedance fraction $p_u = N_u / n$ and normalized tail ratio $a = \frac{1 - c}{p_u}$:
1. **POT VaR (Quantile):**
   $$\text{VaR}_c^{\text{POT}} = u + \frac{\beta}{\xi} \left(a^{-\xi} - 1\right) = u + \beta \frac{e^{-\xi \ln a} - 1}{\xi}.$$
   For $\xi \to 0$ (exponential tail limit):
   $$\lim_{\xi \to 0} \text{VaR}_c^{\text{POT}} = u - \beta \ln a.$$
   At the empirical threshold boundary ($c = 1 - p_u \implies a = 1$):
   $$\text{VaR}_{1 - p_u}^{\text{POT}} = u.$$
2. **POT Expected Shortfall (Tail Mean):**
   For $\xi < 1$ (finite first moment):
   $$\text{ES}_c^{\text{POT}} = \frac{\text{VaR}_c^{\text{POT}} + \beta - \xi u}{1 - \xi}.$$
   For $\xi \ge 1$ (divergent mean / infinite tail expectation): $\text{ES}_c = \text{None}$ with `status = "warning"` and diagnostic reason explicitly disclosing that the GPD first moment does not exist.

#### 7.1.3 Empirical-Body / GPD-Tail Hybrid Distribution
Pure POT is undefined for $c < 1 - p_u$ ($a > 1$). To evaluate committee confidence levels like $90\%$ without extrapolating GPD into the central body, `estimate_evt_body_tail` couples the empirical step CDF below $u$ (mass $1 - p_u$) with the fitted GPD tail above $u$ (mass $p_u$):
- **CDF:** $F(x) = F_n(x)$ for $x \le u$; $F(x) = 1 - p_u (1 - G_{\xi, \beta}(x - u))$ for $x > u$ (strictly continuous at $x = u$ because $F_n(u) = 1 - p_u$).
- **Quantile:** For $c < 1 - p_u$, $\text{VaR}_c = L_{(\lceil n c \rceil)}$ (labelled `BODY_EMPIRICAL_QUANTILE_NOT_EVT_EXTRAPOLATION`). For $c \ge 1 - p_u$, $\text{VaR}_c = \text{VaR}_c^{\text{POT}}$.
- **Expected Shortfall:** Decomposed into empirical body integral and upper GPD tail integral:
  $$\text{ES}_c^{\text{hybrid}} = \frac{1}{1 - c} \left[\int_c^{1 - p_u} F_n^{-1}(p)\,dp + p_u \left(u + \frac{\beta}{1 - \xi}\right)\right].$$

### 7.2 Development-Period Fitted Parameters & Threshold Diagnostics (`min_variance`)

| Window | Observations ($n$) | Threshold Quantile $q$ | Threshold $u$ (%) | Strict Exceedances $N_u$ | Exceedance Rate $p_u$ | Mean Excess (%) | Shape $\hat{\xi} \pm \text{SE}$ | Scale $\hat{\beta}$ (%) | Modified Scale $\hat{\beta} - \hat{\xi} u$ (%) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **Recent 1,260d** | `1,260` | `0.900` | `0.4291%` | `126` | `10.00%` | `0.2722%` | `0.2236 ± 0.1089` | `0.2113%` | `0.1154%` | `ok` |
| **Recent 1,260d** | `1,260` | `0.925` | `0.4834%` | `94` | `7.46%` | `0.3006%` | `0.1758 ± 0.1213` | `0.2470%` | `0.1620%` | `ok` |
| **Recent 1,260d** (Primary) | `1,260` | **`0.950`** | **`0.5927%`** | **`63`** | **`5.00%`** | **`0.3134%`** | **`0.2258 ± 0.1544`** | **`0.2423%`** | **`0.1085%`** | `ok` |
| **Recent 1,260d** | `1,260` | `0.975` | `0.7965%` | `31` | `2.46%` | `0.3438%` | `N/A` ($N_u < 50$) | `N/A` | `N/A` | `unavailable` |
| **Full 3,020d** | `3,020` | `0.900` | `0.5349%` | `302` | `10.00%` | `0.4340%` | `0.1278 ± 0.0649` | `0.3775%` | `0.3092%` | `ok` |
| **Full 3,020d** | `3,020` | `0.925` | `0.6610%` | `226` | `7.48%` | `0.4330%` | `0.1842 ± 0.0788` | `0.3526%` | `0.2309%` | `ok` |
| **Full 3,020d** (Primary) | `3,020` | **`0.950`** | **`0.8181%`** | **`151`** | **`5.00%`** | **`0.4523%`** | **`0.2607 ± 0.1026`** | **`0.3368%`** | **`0.1235%`** | `ok` |
| **Full 3,020d** | `3,020` | `0.975` | `1.0863%` | `75` | `2.48%` | `0.5352%` | `0.2248 ± 0.1414` | `0.4159%` | `0.1717%` | `ok` |

- **Empirical Diagnostics Interpretation:**
  1. **Strict Exceedances & Threshold Sample Size:** At $q = 0.95$, Recent 1,260d yields $N_u = 63$ strict exceedances (above the mandated $50$ minimum), while Full 3,020d yields $N_u = 151$. Moving to $q = 0.975$ on the 1,260-day window produces only $N_u = 31 < 50$, correctly diagnosed as `unavailable`.
  2. **Positive Tail Index $\hat{\xi} > 0$:** Both windows exhibit heavy-tailed Fréchet behavior ($\hat{\xi} = 0.2258 \pm 0.1544$ recent, $0.2607 \pm 0.1026$ full). Asymptotically, $\xi > 0$ indicates polynomial tail decay ($P(L > x) \sim x^{-1/\xi}$ with tail index $\alpha_{\text{tail}} \approx 1/0.26 \approx 3.84$).
  3. **Modified Scale Stability:** The modified scale parameter $\hat{\beta} - \hat{\xi} u$ remains reasonably stable across $q \in [0.90, 0.95]$ (`0.11%` to `0.16%` recent; `0.12%` to `0.31%` full), supporting $q = 0.95$ as a justifiable provisional threshold.

### 7.3 Multi-Model Risk Comparison Table (`min_variance`, Development Split)

| Window | Model | Confidence | VaR (%) | VaR (USD 10M) | ES (%) | ES (USD 10M) | ES - VaR (bps) | Diff vs Normal VaR (bps) | Diff vs Normal ES (bps) | Status | Region |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Recent 1,260d | `historical` | `0.90` | `0.4291%` | `$42,910.90` | `0.6976%` | `$69,760.36` | `+26.85` | `-5.91` | `+2.25` | `ok` | - |
| Recent 1,260d | `parametric_normal` | `0.90` | `0.4882%` | `$48,816.06` | `0.6751%` | `$67,506.50` | `+18.69` | `0.00` | `0.00` | `ok` | - |
| Recent 1,260d | `monte_carlo_normal` | `0.90` | `0.4873%` | `$48,727.99` | `0.6781%` | `$67,808.78` | `+19.08` | `-0.88` | `+3.02` | `ok` | - |
| Recent 1,260d | `evt_pot` | `0.90` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `unavailable` | - |
| Recent 1,260d | `evt_body_tail_hybrid` | `0.90` | `0.4291%` | `$42,910.90` | `0.7010%` | `$70,101.98` | `+27.19` | `-5.91` | `+25.95` | `ok` | `body` |
| Recent 1,260d | `historical` | `0.95` | `0.5927%` | `$59,272.67` | `0.8797%` | `$87,973.91` | `+28.70` | `-3.89` | `+8.32` | `ok` | - |
| Recent 1,260d | `parametric_normal` | `0.95` | `0.6316%` | `$63,158.73` | `0.7966%` | `$79,655.23` | `+16.50` | `0.00` | `0.00` | `ok` | - |
| Recent 1,260d | `monte_carlo_normal` | `0.95` | `0.6338%` | `$63,384.50` | `0.8025%` | `$80,249.91` | `+16.87` | `+2.26` | `+5.95` | `ok` | - |
| Recent 1,260d | `evt_pot` | `0.95` | `0.5927%` | `$59,272.67` | `0.9057%` | `$90,566.01` | `+31.29` | `-3.89` | `+109.11` | `ok` | `threshold_boundary` |
| Recent 1,260d | `evt_body_tail_hybrid` | `0.95` | `0.5927%` | `$59,272.67` | `0.9057%` | `$90,566.01` | `+31.29` | `-3.89` | `+109.11` | `ok` | `threshold_boundary` |
| Recent 1,260d | `historical` | `0.99` | `1.0414%` | `$104,142.42` | `1.5018%` | `$150,182.84` | `+46.04` | `+14.08` | `+46.74` | `ok` | - |
| Recent 1,260d | `parametric_normal` | `0.99` | `0.9006%` | `$90,063.18` | `1.0344%` | `$103,441.16` | `+13.38` | `0.00` | `0.00` | `ok` | - |
| Recent 1,260d | `monte_carlo_normal` | `0.99` | `0.9074%` | `$90,737.47` | `1.0482%` | `$104,815.52` | `+14.08` | `+6.74` | `+13.74` | `ok` | - |
| Recent 1,260d | `evt_pot` | `0.99` | `1.0629%` | `$106,293.35` | `1.5130%` | `$151,297.01` | `+45.00` | `+16.23` | `+478.56` | `ok` | `tail` |
| Recent 1,260d | `evt_body_tail_hybrid` | `0.99` | `1.0629%` | `$106,293.35` | `1.5130%` | `$151,297.01` | `+45.00` | `+16.23` | `+478.56` | `ok` | `tail` |
| Full 3,020d | `historical` | `0.90` | `0.5349%` | `$53,488.25` | `1.0435%` | `$104,351.48` | `+50.86` | `-14.11` | `+10.72` | `ok` | - |
| Full 3,020d | `parametric_normal` | `0.90` | `0.6759%` | `$67,594.60` | `0.9363%` | `$93,627.12` | `+26.03` | `0.00` | `0.00` | `ok` | - |
| Full 3,020d | `monte_carlo_normal` | `0.90` | `0.6851%` | `$68,505.21` | `0.9431%` | `$94,313.39` | `+25.81` | `+9.11` | `+6.86` | `ok` | - |
| Full 3,020d | `evt_pot` | `0.90` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `unavailable` | - |
| Full 3,020d | `evt_body_tail_hybrid` | `0.90` | `0.5349%` | `$53,488.25` | `0.9704%` | `$97,044.84` | `+43.56` | `-14.11` | `+34.18` | `ok` | `body` |
| Full 3,020d | `historical` | `0.95` | `0.8181%` | `$81,806.85` | `1.2704%` | `$127,038.54` | `+45.23` | `-5.76` | `+16.49` | `ok` | - |
| Full 3,020d | `parametric_normal` | `0.95` | `0.8757%` | `$87,571.44` | `1.1055%` | `$110,548.19` | `+22.98` | `0.00` | `0.00` | `ok` | - |
| Full 3,020d | `monte_carlo_normal` | `0.95` | `0.8786%` | `$87,859.25` | `1.1127%` | `$111,268.69` | `+23.41` | `+2.88` | `+7.20` | `ok` | - |
| Full 3,020d | `evt_pot` | `0.95` | `0.8181%` | `$81,806.85` | `1.2736%` | `$127,357.79` | `+45.55` | `-5.76` | `+168.10` | `ok` | `threshold_boundary` |
| Full 3,020d | `evt_body_tail_hybrid` | `0.95` | `0.8181%` | `$81,806.85` | `1.2736%` | `$127,357.79` | `+45.55` | `-5.76` | `+168.10` | `ok` | `threshold_boundary` |
| Full 3,020d | `historical` | `0.99` | `1.4824%` | `$148,243.68` | `2.1595%` | `$215,946.90` | `+67.70` | `+23.20` | `+72.27` | `ok` | - |
| Full 3,020d | `parametric_normal` | `0.99` | `1.2504%` | `$125,044.65` | `1.4368%` | `$143,677.84` | `+18.63` | `0.00` | `0.00` | `ok` | - |
| Full 3,020d | `monte_carlo_normal` | `0.99` | `1.2646%` | `$126,458.38` | `1.4420%` | `$144,203.21` | `+17.74` | `+14.14` | `+5.25` | `ok` | - |
| Full 3,020d | `evt_pot` | `0.99` | `1.4915%` | `$149,149.25` | `2.1844%` | `$218,444.60` | `+69.29` | `+24.10` | `+747.67` | `ok` | `tail` |
| Full 3,020d | `evt_body_tail_hybrid` | `0.99` | `1.4915%` | `$149,149.25` | `2.1844%` | `$218,444.60` | `+69.29` | `+24.10` | `+747.67` | `ok` | `tail` |

### 7.4 Moving-Block Bootstrap Uncertainty (10-Session Blocks, 100 Replications, Seed 202602)

| Window | Confidence | Model / Method | Available Replicates | VaR Median (%) | VaR 95% Bootstrap CI (%) | ES Median (%) | ES 95% Bootstrap CI (%) | Status |
|---|---:|---|---:|---:|---|---:|---|---|
| **Recent 1,260d** | `0.90` | `body_tail_hybrid` | `100 / 100` | `0.4302%` | `[0.3602%, 0.4717%]` | `0.6972%` | `[0.6085%, 0.7970%]` | `ok` |
| **Recent 1,260d** | `0.95` | `pure_pot` | `58 / 100` | `N/A` | `unavailable: 58 < 80` | `N/A` | `unavailable: 58 < 80` | `unavailable` |
| **Recent 1,260d** | `0.95` | `body_tail_hybrid` | `100 / 100` | `0.5919%` | `[0.4834%, 0.6690%]` | `0.8995%` | `[0.7226%, 1.1578%]` | `ok` |
| **Recent 1,260d** | `0.99` | `pure_pot` | `100 / 100` | `1.0641%` | `[0.8826%, 1.2399%]` | `1.4964%` | `[1.1015%, 1.9822%]` | `ok` |
| **Full 3,020d** | `0.90` | `body_tail_hybrid` | `100 / 100` | `0.5331%` | `[0.4882%, 0.5980%]` | `0.9771%` | `[0.8753%, 1.0782%]` | `ok` |
| **Full 3,020d** | `0.95` | `pure_pot` | `62 / 100` | `N/A` | `unavailable: 62 < 80` | `N/A` | `unavailable: 62 < 80` | `unavailable` |
| **Full 3,020d** | `0.95` | `body_tail_hybrid` | `100 / 100` | `0.8174%` | `[0.7247%, 0.9048%]` | `1.2845%` | `[1.1292%, 1.5126%]` | `ok` |
| **Full 3,020d** | `0.99` | `pure_pot` | `100 / 100` | `1.5051%` | `[1.3126%, 1.7450%]` | `2.2066%` | `[1.7483%, 2.7006%]` | `ok` |

- **Uncertainty & Bootstrap Findings:**
  1. **Threshold Boundary Sensitivity in Resamples:** At exactly $c = 0.95$, in resamples with duplicated boundary values, the empirical tail probability $p_u = N_u / n$ can slightly fall below $1 - q$ (e.g., $N_u = 62 / 1260 = 0.0492 < 0.05$), placing $c = 0.95$ strictly in the body ($a > 1$). Pure POT correctly refuses to extrapolate and returns `unavailable`, yielding only $58 / 100$ (recent) and $62 / 100$ (full) finite pure POT replicates (correctly triggering the $\ge 80$ failure guard). In contrast, the explicitly labelled hybrid evaluates across $100 / 100$ replicates (`[0.4834%, 0.6690%]` VaR recent, `[0.7247%, 0.9048%]` full).
  2. **Tail Thickness & ES Spread:** At 99% confidence, EVT POT Expected Shortfall has a 95% confidence interval of `[1.1015%, 1.9822%]` (median `1.4964%`) on Recent 1,260d and `[1.7483%, 2.7006%]` (median `2.2066%`) on Full 3,020d. The upper bound on full development ($2.70\%$, or $\$270{,}000$ on $\$10\text{M}$) reflects the severe fat-tail risk observed during the 2008 financial crisis.
  3. **Conditional Uncertainty Warning:** These bootstrap intervals are conditional on the fixed $q = 0.95$ threshold policy and the 10-session block dependence assumption. They do not account for regime shifts beyond development data or structural breaks.
