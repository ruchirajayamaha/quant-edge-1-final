# Section C — Value-at-Risk (VaR) and Expected Shortfall (ES) Methodology & Development Diagnostics (`SOLO STEP 5 / C1`)

- **Active market snapshot (`r3_release_evidence`):** `qe1_20050101_20261030_r3_6c4633a7ba` (`schema_version = "1.1.0"`)
- **Configuration SHA-256 (`config_hash`):** `587ddbe363589fb6956c23c5fe8b2b544bac81d9224a0b4bb59f60f5fbc0a017`
- **Mandate scale (`nav_usd`):** `USD 10,000,000.00`
- **Monte Carlo authority (`config.yaml`):** `monte_carlo_simulations = 25000`, `seeds.monte_carlo = 202601`
- **Holdout discipline:** All real-data risk tables in this section are restricted to the **development period through `2016-12-30`**. Selection (`2017-01-03..2020-12-31`) and final evaluation (`2021-01-04..2026-10-30`) strategy outcomes remain uncomputed and uninspected. Unconditional POT-GPD Extreme Value Theory (`C2/C3`) is scheduled for **SOLO STEP 7**.
- **Saved numerical source of truth:** `results/step5_development_c1_risk_tables.json` (strictly RFC 8259 compliant via `allow_nan=False`, with `null` for non-applicable `seed` and `monte_carlo_simulations` metadata on non-Monte-Carlo rows)
- **Exported CSV tables & PNG/SVG figures:** `results/step5_c1_preview/` (`01_c1_risk_comparison_all_confidences.csv` through `06_c1_fixed_exposure_daily_losses.csv`, `figure_01_c1_var_es_95_99_comparison.{png,svg}`, `figure_02_c1_fixed_exposure_loss_distribution.{png,svg}`, `figure_03_c1_mc_sampling_uncertainty.{png,svg}`, `index.html`, and `manifest.json`)

---

## 1. Mathematical Specifications & Shared Conventions (`src/quantedge/var.py`, `src/quantedge/es.py`)

### 1.1 Fixed-Exposure One-Day Simple-Return Loss Convention & Aggregation Exception
For a fixed portfolio weight vector $w = (w_{\text{SPY}}, w_{\text{EFA}}, w_{\text{EEM}}, w_{\text{AGG}}, w_{\text{GLD}}, w_{\text{XLE}}, w_{\text{XLK}})^\top$ ($\sum_{i=1}^7 w_i = 1$) and historical simple asset return matrix $R \in \mathbb{R}^{n \times 7}$, the one-day fixed-exposure portfolio simple return and pre-transaction-cost loss on session $t$ are:
$$R_{p,t} = \sum_{i=1}^7 w_i R_{i,t} = (R w)_t, \qquad L_t = -R_{p,t}.$$

- **Sign orientation:** Positive values of $L_t$, $\text{VaR}_c$, and $\text{ES}_c$ represent one-day fractional losses before transaction costs ($\text{USD loss} = \text{loss fraction} \times 10{,}000{,}000$). Nonpositive loss quantiles ($\text{VaR}_c \le 0$ or $\text{ES}_c \le 0$, corresponding to tail outcomes that are still net gains) are preserved with their exact sign and are **never** masked with `abs()` or floored at `0.0`.
- **Simple-return modelling exception:** Cross-sectional portfolio value changes aggregate linearly in simple returns ($R_{p,t} = \sum_i w_i R_{i,t}$), whereas log returns are time-additive but not linearly additive across assets ($\log(1 + \sum_i w_i R_{i,t}) \ne \sum_i w_i \log(1 + R_{i,t})$). All committee risk models therefore operate on one-day simple portfolio losses $L_t = -R_{p,t}$, while log returns $\log(1 + R_{p,t})$ are also inspected in ADF stationarity diagnostics.

### 1.2 Historical Simulation VaR and Exact Empirical Tail-Integral ES (`empirical_tail_weights`)
Given $n \ge 2$ finite historical loss observations $L_1, \dots, L_n$ (each carrying empirical probability mass $1/n$), let $L_{(1)} \le L_{(2)} \le \dots \le L_{(n)}$ denote the ascending order statistics and $L_{[1]} \ge L_{[2]} \ge \dots \ge L_{[n]}$ denote the descending (worst-first) order statistics ($L_{[j]} = L_{(n - j + 1)}$):

1. **Historical VaR (`method="inverted_cdf"`, Hyndman-Fan Type 1):**
   $$\text{VaR}_c^{\text{hist}} = F_n^{-1}(c) = \inf\{x \in \mathbb{R} : F_n(x) \ge c\} = L_{(\lceil n c \rceil)}.$$
2. **Historical ES (`empirical_tail_weights`):**
   Expected Shortfall integrates the empirical quantile function over the worst $\alpha = 1 - c$ probability mass:
   $$\text{ES}_c^{\text{hist}} = \frac{1}{\alpha} \int_c^1 F_n^{-1}(u)\,du = \sum_{i=1}^n w_{\text{tail},i}\,L_i, \qquad \sum_{i=1}^n w_{\text{tail},i} = 1.$$
   Let $m = n \alpha = n(1 - c)$ be the exact number of worst observations required to cover probability mass $\alpha$, and let $k_{\text{slots}} = \lceil m \rceil \in \{1, \dots, n\}$. The order-statistic boundary loss is $u_* = L_{[k_{\text{slots}}]}$:
   - Every observation strictly exceeding the boundary ($L_i > u_*$, count $k_{\text{strict}} < m$) receives full normalized mass:
     $$w_{\text{tail},i} = \frac{1/n}{\alpha} = \frac{1}{m}.$$
   - All observations tied at the boundary ($L_i = u_*$, count $k_{\text{tie}} \ge 1$) split the remaining required tail mass $\alpha - k_{\text{strict}}/n = (m - k_{\text{strict}})/n$ equally:
     $$w_{\text{tail},i} = \frac{\alpha - k_{\text{strict}}/n}{\alpha \cdot k_{\text{tie}}} = \frac{m - k_{\text{strict}}}{m \cdot k_{\text{tie}}}.$$
   - All observations strictly below $u_*$ ($L_i < u_*$) receive $w_{\text{tail},i} = 0$.
   - Because $u_*$ is an actual sample order statistic rather than a linearly interpolated value between adjacent order statistics, $0 \le k_{\text{strict}} < m \le k_{\text{strict}} + k_{\text{tie}}$ holds for every sample size $n$ and confidence $c \in (0, 1)$, guaranteeing $\text{ES}_c^{\text{hist}} \ge \text{VaR}_c^{\text{hist}}$, confidence monotonicity, and exact cross-asset Euler ES additivity ($\sum_{j=1}^7 w_j (w_{\text{tail}}^\top (-R_{\cdot,j})) = \text{ES}_c^{\text{hist}}$).

### 1.3 Shared Normal Moments (`normal_moments`) and Parametric Normal VaR & ES
`normal_moments(asset_returns)` computes the canonical 7-ETF arithmetic sample mean vector $\hat{\mu} \in \mathbb{R}^7$ and unbiased sample covariance matrix $\hat{\Sigma} \in \mathbb{R}^{7 \times 7}$ with `ddof = 1`:
$$\hat{\mu} = \frac{1}{n}\sum_{t=1}^n R_t, \qquad \hat{\Sigma} = \frac{1}{n - 1}\sum_{t=1}^n (R_t - \hat{\mu})(R_t - \hat{\mu})^\top.$$
For fixed portfolio weights $w$, the portfolio daily simple-return mean and variance are $\mu_p = w^\top \hat{\mu}$ and $\sigma_p^2 = w^\top \hat{\Sigma} w$ ($\sigma_p = \sqrt{\max(0, \sigma_p^2)}$). With standard normal quantile $z_c = \Phi^{-1}(c)$ and standard normal density $\phi(z_c) = \frac{1}{\sqrt{2\pi}}e^{-z_c^2/2}$:
$$\text{VaR}_c^{\text{norm}} = -\mu_p + \sigma_p z_c, \qquad \text{ES}_c^{\text{norm}} = -\mu_p + \sigma_p \frac{\phi(z_c)}{1 - c}.$$
- **Degenerate zero volatility ($\sigma_p = 0$):** Handled without division by zero or `NaN`; all three C1 models return finite deterministic loss $\text{VaR}_c = \text{ES}_c = -\mu_p$ with `status = "warning"` and `diagnostics["zero_portfolio_volatility"] = True`.
- **Unbounded Gaussian simple-return approximation:** The normal model $R_t \sim \mathcal{N}(\hat{\mu}, \hat{\Sigma})$ is an unbounded continuous approximation on $(-\infty, +\infty)$ even though theoretical long-only simple returns cannot fall below $-100\%$ ($L_t \le 1.0$). Draws and quantiles are never artificially truncated at $-1.0$.

### 1.4 Seeded Multivariate Normal Monte Carlo (`monte_carlo_normal`) & Uncertainty Quantification
Using the **exact same** fitted asset moments $(\hat{\mu}, \hat{\Sigma}) = \text{normal\_moments}(\text{train\_asset\_returns})$, `monte_carlo_normal` eigendecomposes $\hat{\Sigma} = V \,\text{diag}(\max(\lambda, 0))\, V^\top$, initializes NumPy's PCG64 generator `np.random.default_rng(seed)` (defaulting to `config.seeds.monte_carlo = 202601`), draws $M = 25{,}000$ (`config.risk.monte_carlo_simulations`) 7-ETF return vectors $R_{\text{sim}} \sim \mathcal{N}_7(\hat{\mu}, \hat{\Sigma})$, projects one-day portfolio losses $L_{\text{sim}} = -(R_{\text{sim}} w) \in \mathbb{R}^M$, and applies `empirical_var_and_es` to $L_{\text{sim}}$. Simulated asset return draws are cached in memory by `(moments_digest, seed, n_simulations)` so multi-confidence and multi-portfolio calls on the same window do not re-simulate.

---

## 2. Development-Period Fixed Exposures & Window Policy (`<= 2016-12-30`)

### 2.1 Evaluated Fixed Portfolio Exposures
| Canonical Ticker | `min_variance` (`2015-01-02..2016-12-30`, `504d` Target) | `min_variance` (`2016-12-01` Last Scheduled Rebalance) | `equal_weight` Reference | `benchmark_60_40` Reference |
|---|---:|---:|---:|---:|
| `SPY` | `0.339337214` | `0.340517839` | `0.142857143` | `0.600000000` |
| `EFA` | `0.000000000` | `0.000000000` | `0.142857143` | `0.000000000` |
| `EEM` | `0.000000000` | `0.000000000` | `0.142857143` | `0.000000000` |
| `AGG` | `0.400000000` | `0.400000000` | `0.142857143` | `0.400000000` |
| `GLD` | `0.260662786` | `0.259482161` | `0.142857143` | `0.000000000` |
| `XLE` | `0.000000000` | `0.000000000` | `0.142857143` | `0.000000000` |
| `XLK` | `0.000000000` | `0.000000000` | `0.142857143` | `0.000000000` |

### 2.2 Development Diagnostic Windows & Truthful Crisis Coverage
- **`recent_development_1260d` (`2011-12-29` to `2016-12-30`, $N = 1{,}260$ trading sessions):**
  Trailing `1,260`-session (`dashboard_risk_window_days`) window at the end of the development period.
  - **Crisis coverage:** `included_scenarios = ()`. The 2007–2009 Global Financial Crisis (`2007-10-09..2009-03-09`) precedes `2011-12-29` (`pre_window_omitted`), and both `covid_2020` (`2020-02-19..2020-03-23`) and `rate_shock_2022` (`2022-01-03..2022-10-14`) lie in the post-2016 holdout period (`post_window_not_in_sample`).
- **`full_development_3020d` (`2005-01-04` to `2016-12-30`, $N = 3{,}020$ trading sessions):**
  Complete development-period simple-return sample.
  - **Crisis coverage:** `included_scenarios = ("gfc_2007_2009",)`. Fully includes the 2007–2009 Global Financial Crisis (`2007-10-09..2009-03-09`) and excludes post-2016 `covid_2020` and `rate_shock_2022` (`post_window_not_in_sample`).

---

## 3. Matched Development Risk Comparison Tables (`90%`, `95%`, `99%`; Mandatory `95%` & `99%` Highlighted)

### 3.1 Recent Development Window (`recent_development_1260d`: `2011-12-29..2016-12-30`, $N = 1{,}260$)

#### A. Constrained Minimum Variance (`min_variance`)
| Model | Confidence | `VaR` (Fraction) | `VaR` (`%`) | `VaR` (`USD` on `10M`) | `ES` (Fraction) | `ES` (`%`) | `ES` (`USD` on `10M`) | `VaR - Normal` (`bps`) | `ES - Normal` (`bps`) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `historical` | `0.90` | `0.004291090` | `0.4291%` | `42,910.90` | `0.007012616` | `0.7013%` | `70,126.16` | `-5.9052` | `+2.6197` | `ok` |
| `parametric_normal` | `0.90` | `0.004881606` | `0.4882%` | `48,816.06` | `0.006750650` | `0.6751%` | `67,506.50` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.90` | `0.004872799` | `0.4873%` | `48,727.99` | `0.006780878` | `0.6781%` | `67,808.78` | `-0.0881` | `+0.3023` | `ok` |
| `historical` | `0.95` | `0.005927267` | `0.5927%` | `59,272.67` | `0.009061438` | `0.9061%` | `90,614.38` | `-3.8861` | `+10.9591` | `ok` |
| `parametric_normal` | `0.95` | `0.006315873` | `0.6316%` | `63,158.73` | `0.007965523` | `0.7966%` | `79,655.23` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.95` | `0.006338450` | `0.6338%` | `63,384.50` | `0.008024991` | `0.8025%` | `80,249.91` | `+0.2258` | `+0.5947` | `ok` |
| `historical` | `0.99` | `0.010413756` | `1.0414%` | `104,137.56` | `0.015017825` | `1.5018%` | `150,178.25` | `+14.0744` | `+46.7371` | `ok` |
| `parametric_normal` | `0.99` | `0.009006318` | `0.9006%` | `90,063.18` | `0.010344116` | `1.0344%` | `103,441.16` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.99` | `0.009073747` | `0.9074%` | `90,737.47` | `0.010481552` | `1.0482%` | `104,815.52` | `+0.6743` | `+1.3744` | `ok` |

#### B. Equal-Weight Reference (`equal_weight`)
| Model | Confidence | `VaR` (Fraction) | `VaR` (`%`) | `VaR` (`USD` on `10M`) | `ES` (Fraction) | `ES` (`%`) | `ES` (`USD` on `10M`) | `VaR - Normal` (`bps`) | `ES - Normal` (`bps`) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `historical` | `0.90` | `0.008106335` | `0.8106%` | `81,063.35` | `0.012545350` | `1.2545%` | `125,453.50` | `-5.0759` | `+6.5669` | `ok` |
| `parametric_normal` | `0.90` | `0.008613928` | `0.8614%` | `86,139.28` | `0.011888656` | `1.1889%` | `118,886.56` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.90` | `0.008768118` | `0.8768%` | `87,681.18` | `0.011961482` | `1.1961%` | `119,614.82` | `+1.5419` | `+0.7283` | `ok` |
| `historical` | `0.95` | `0.011885007` | `1.1885%` | `118,850.07` | `0.015497148` | `1.5497%` | `154,971.48` | `+7.5812` | `+14.7993` | `ok` |
| `parametric_normal` | `0.95` | `0.011126889` | `1.1127%` | `111,268.89` | `0.014017221` | `1.4017%` | `140,172.21` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.95` | `0.011133374` | `1.1133%` | `111,333.74` | `0.014057581` | `1.4058%` | `140,575.81` | `+0.0649` | `+0.4036` | `ok` |
| `historical` | `0.99` | `0.016679095` | `1.6679%` | `166,790.95` | `0.023479110` | `2.3479%` | `234,791.10` | `+8.3831` | `+52.9439` | `ok` |
| `parametric_normal` | `0.99` | `0.015840786` | `1.5841%` | `158,407.86` | `0.018184725` | `1.8185%` | `181,847.25` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.99` | `0.015883049` | `1.5883%` | `158,830.49` | `0.018393287` | `1.8393%` | `183,932.87` | `+0.4226` | `+2.0856` | `ok` |

#### C. 60/40 Benchmark Reference (`benchmark_60_40`)
| Model | Confidence | `VaR` (Fraction) | `VaR` (`%`) | `VaR` (`USD` on `10M`) | `ES` (Fraction) | `ES` (`%`) | `ES` (`USD` on `10M`) | `VaR - Normal` (`bps`) | `ES - Normal` (`bps`) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `historical` | `0.90` | `0.005103760` | `0.5104%` | `51,037.60` | `0.008538959` | `0.8539%` | `85,389.59` | `-5.8935` | `+6.0226` | `ok` |
| `parametric_normal` | `0.90` | `0.005693112` | `0.5693%` | `56,931.12` | `0.007936698` | `0.7937%` | `79,366.98` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.90` | `0.005704352` | `0.5704%` | `57,043.52` | `0.007985412` | `0.7985%` | `79,854.12` | `+0.1124` | `+0.4871` | `ok` |
| `historical` | `0.95` | `0.007609444` | `0.7609%` | `76,094.44` | `0.010928667` | `1.0929%` | `109,286.67` | `+1.9465` | `+15.3364` | `ok` |
| `parametric_normal` | `0.95` | `0.007414795` | `0.7415%` | `74,147.95` | `0.009395024` | `0.9395%` | `93,950.24` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.95` | `0.007463655` | `0.7464%` | `74,636.55` | `0.009467962` | `0.9468%` | `94,679.62` | `+0.4886` | `+0.7294` | `ok` |
| `historical` | `0.99` | `0.012699096` | `1.2699%` | `126,990.96` | `0.016149868` | `1.6150%` | `161,498.68` | `+20.5471` | `+38.9960` | `ok` |
| `parametric_normal` | `0.99` | `0.010644387` | `1.0644%` | `106,443.87` | `0.012250269` | `1.2250%` | `122,502.69` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.99` | `0.010728503` | `1.0729%` | `107,285.03` | `0.012308387` | `1.2308%` | `123,083.87` | `+0.8412` | `+0.5812` | `ok` |

### 3.2 Full Development Window (`full_development_3020d`: `2005-01-04..2016-12-30`, $N = 3{,}020$, GFC-Inclusive)

#### A. Constrained Minimum Variance (`min_variance`)
| Model | Confidence | `VaR` (Fraction) | `VaR` (`%`) | `VaR` (`USD` on `10M`) | `ES` (Fraction) | `ES` (`%`) | `ES` (`USD` on `10M`) | `VaR - Normal` (`bps`) | `ES - Normal` (`bps`) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `historical` | `0.90` | `0.005348825` | `0.5349%` | `53,488.25` | `0.009688480` | `0.9688%` | `96,884.80` | `-14.1064` | `+3.2577` | `ok` |
| `parametric_normal` | `0.90` | `0.006759460` | `0.6759%` | `67,594.60` | `0.009362712` | `0.9363%` | `93,627.12` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.90` | `0.006850521` | `0.6851%` | `68,505.21` | `0.009431339` | `0.9431%` | `94,313.39` | `+0.9106` | `+0.6863` | `ok` |
| `historical` | `0.95` | `0.008180685` | `0.8181%` | `81,806.85` | `0.012703771` | `1.2704%` | `127,037.71` | `-5.7646` | `+16.4895` | `ok` |
| `parametric_normal` | `0.95` | `0.008757144` | `0.8757%` | `87,571.44` | `0.011054819` | `1.1055%` | `110,548.19` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.95` | `0.008785925` | `0.8786%` | `87,859.25` | `0.011126869` | `1.1127%` | `111,268.69` | `+0.2878` | `+0.7205` | `ok` |
| `historical` | `0.99` | `0.014824403` | `1.4824%` | `148,244.03` | `0.021594902` | `2.1595%` | `215,949.02` | `+23.1994` | `+72.2712` | `ok` |
| `parametric_normal` | `0.99` | `0.012504465` | `1.2504%` | `125,044.65` | `0.014367784` | `1.4368%` | `143,677.84` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.99` | `0.012645838` | `1.2646%` | `126,458.38` | `0.014420321` | `1.4420%` | `144,203.21` | `+1.4137` | `+0.5254` | `ok` |

#### B. Equal-Weight Reference (`equal_weight`)
| Model | Confidence | `VaR` (Fraction) | `VaR` (`%`) | `VaR` (`USD` on `10M`) | `ES` (Fraction) | `ES` (`%`) | `ES` (`USD` on `10M`) | `VaR - Normal` (`bps`) | `ES - Normal` (`bps`) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `historical` | `0.90` | `0.010819975` | `1.0820%` | `108,199.75` | `0.019246348` | `1.9246%` | `192,463.48` | `-26.4874` | `+6.7015` | `ok` |
| `parametric_normal` | `0.90` | `0.013468715` | `1.3469%` | `134,687.15` | `0.018576200` | `1.8576%` | `185,762.00` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.90` | `0.013725671` | `1.3726%` | `137,256.71` | `0.018709444` | `1.8709%` | `187,094.44` | `+2.5696` | `+1.3324` | `ok` |
| `historical` | `0.95` | `0.015407194` | `1.5407%` | `154,071.94` | `0.025522828` | `2.5523%` | `255,228.28` | `-19.8090` | `+36.2678` | `ok` |
| `parametric_normal` | `0.95` | `0.017388097` | `1.7388%` | `173,880.97` | `0.021896053` | `2.1896%` | `218,960.53` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.95` | `0.017383623` | `1.7384%` | `173,836.23` | `0.021949505` | `2.1950%` | `219,495.05` | `-0.0447` | `+0.5345` | `ok` |
| `historical` | `0.99` | `0.031316366` | `3.1316%` | `313,163.66` | `0.044104512` | `4.4105%` | `441,045.12` | `+65.7616` | `+157.0854` | `ok` |
| `parametric_normal` | `0.99` | `0.024740206` | `2.4740%` | `247,402.06` | `0.028395970` | `2.8396%` | `283,959.70` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.99` | `0.024718080` | `2.4718%` | `247,180.80` | `0.028753029` | `2.8753%` | `287,530.29` | `-0.2213` | `+3.5706` | `ok` |

#### C. 60/40 Benchmark Reference (`benchmark_60_40`)
| Model | Confidence | `VaR` (Fraction) | `VaR` (`%`) | `VaR` (`USD` on `10M`) | `ES` (Fraction) | `ES` (`%`) | `ES` (`USD` on `10M`) | `VaR - Normal` (`bps`) | `ES - Normal` (`bps`) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `historical` | `0.90` | `0.006714328` | `0.6714%` | `67,143.28` | `0.012962864` | `1.2963%` | `129,628.64` | `-23.9630` | `+3.8284` | `ok` |
| `parametric_normal` | `0.90` | `0.009110623` | `0.9111%` | `91,106.23` | `0.012580022` | `1.2580%` | `125,800.22` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.90` | `0.009259791` | `0.9260%` | `92,597.91` | `0.012695112` | `1.2695%` | `126,951.12` | `+1.4917` | `+1.1509` | `ok` |
| `historical` | `0.95` | `0.010216340` | `1.0216%` | `102,163.40` | `0.017572230` | `1.7572%` | `175,722.30` | `-15.5663` | `+27.3711` | `ok` |
| `parametric_normal` | `0.95` | `0.011772970` | `1.1773%` | `117,729.70` | `0.014835122` | `1.4835%` | `148,351.22` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.95` | `0.011902139` | `1.1902%` | `119,021.39` | `0.014916251` | `1.4916%` | `149,162.51` | `+1.2917` | `+0.8113` | `ok` |
| `historical` | `0.99` | `0.022845104` | `2.2845%` | `228,451.04` | `0.031734974` | `3.1735%` | `317,349.74` | `+60.7801` | `+124.8461` | `ok` |
| `parametric_normal` | `0.99` | `0.016767090` | `1.6767%` | `167,670.90` | `0.019250367` | `1.9250%` | `192,503.67` | `+0.0000` | `+0.0000` | `ok` |
| `monte_carlo_normal` | `0.99` | `0.016840832` | `1.6841%` | `168,408.32` | `0.019369468` | `1.9369%` | `193,694.68` | `+0.7374` | `+1.1910` | `ok` |

---

## 4. Monte Carlo Sampling Uncertainty (`M = 25,000` Draws, `64` Independent Seeds `202601..202664`)

### 4.1 Recent Development Window (`recent_development_1260d`, `min_variance`)
| Confidence | Analytic `VaR` | Primary Seed `202601` `VaR` | `MC - Analytic` `VaR` (`bps`) | Empirical `VaR` SE (`bps`, `64` seeds) | Asymptotic `VaR` SE (`bps`) | Analytic `ES` | Primary Seed `202601` `ES` | `MC - Analytic` `ES` (`bps`) | Empirical `ES` SE (`bps`, `64` seeds) | `95%` Seed Interval `VaR` | `95%` Seed Interval `ES` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `0.90` | `0.004881606` | `0.004872799` | `-0.0881` | `0.3388` | `0.4268` | `0.006750650` | `0.006780878` | `+0.3023` | `0.4027` | `[0.004823, 0.004951]` | `[0.006678, 0.006826]` |
| `0.95` | `0.006315873` | `0.006338450` | `+0.2258` | `0.4857` | `0.5276` | `0.007965523` | `0.008024991` | `+0.5947` | `0.5773` | `[0.006224, 0.006406]` | `[0.007851, 0.008076]` |
| `0.99` | `0.009006318` | `0.009073747` | `+0.6743` | `0.9079` | `0.9321` | `0.010344116` | `0.010481552` | `+1.3744` | `1.2140` | `[0.008816, 0.009145]` | `[0.010095, 0.010547]` |

### 4.2 Full Development Window (`full_development_3020d`, `min_variance`)
| Confidence | Analytic `VaR` | Primary Seed `202601` `VaR` | `MC - Analytic` `VaR` (`bps`) | Empirical `VaR` SE (`bps`, `64` seeds) | Asymptotic `VaR` SE (`bps`) | Analytic `ES` | Primary Seed `202601` `ES` | `MC - Analytic` `ES` (`bps`) | Empirical `ES` SE (`bps`, `64` seeds) | `95%` Seed Interval `VaR` | `95%` Seed Interval `ES` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `0.90` | `0.006759460` | `0.006850521` | `+0.9106` | `0.6057` | `0.5945` | `0.009362712` | `0.009431339` | `+0.6863` | `0.7477` | `[0.006649, 0.006860]` | `[0.009206, 0.009475]` |
| `0.95` | `0.008757144` | `0.008785925` | `+0.2878` | `0.7654` | `0.7349` | `0.011054819` | `0.011126869` | `+0.7205` | `0.9907` | `[0.008591, 0.008893]` | `[0.010843, 0.011190]` |
| `0.99` | `0.012504465` | `0.012645838` | `+1.4137` | `1.5763` | `1.2983` | `0.014367784` | `0.014420321` | `+0.5254` | `1.6796` | `[0.012225, 0.012737]` | `[0.013982, 0.014669]` |

- **Precision & tolerance interpretation:** At $M = 25{,}000$ multivariate normal draws, empirical 1-SE simulation noise across 64 independent seeds on `min_variance` is `0.34–0.91 bps` (`USD 339–908`) on `recent_development_1260d` and `0.61–1.68 bps` (`USD 606–1,680`) on `full_development_3020d`. Primary seed `202601` agrees with closed-form `parametric_normal` within `0.09–1.41 bps` across all confidence levels (`< 1.2 SE`).

---

## 5. Fixed-Exposure Risk Series vs. Changing-Weight Strategy Series Diagnostics

| Window (`n_obs`, Bounds) | Portfolio Exposure | Mean Loss | Loss Std (`ddof=1`) | Loss Skewness | Loss Excess Kurtosis | Max 1-Day Loss | Min 1-Day Loss (Max Gain) | Fixed-Exposure Simple ADF (`lags`) | Fixed-Exposure `log1p` ADF (`lags`) | Changing-Weight Net Strategy Simple / `log1p` ADF (`2,516d`) |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| `recent_development_1260d` (`1260`, `2011-12-29..2016-12-30`) | `min_variance` | `-0.000177782` | `0.003947862` | `+0.560997` | `+5.293518` | `0.030572` | `-0.018640` | `-36.2154` (`p=0.00e+00`, `lag=0`) | `-36.1958` (`p=0.00e+00`, `lag=0`) | `-11.6047` / `-11.5646` (`lag=18`) |
| `recent_development_1260d` (`1260`, `2011-12-29..2016-12-30`) | `equal_weight` | `-0.000250567` | `0.006917002` | `+0.191886` | `+1.634860` | `0.031316` | `-0.027056` | `-19.6163` (`p=0.00e+00`, `lag=3`) | `-19.6037` (`p=0.00e+00`, `lag=3`) | `-11.2221` / `-11.0411` (`lag=19`) |
| `recent_development_1260d` (`1260`, `2011-12-29..2016-12-30`) | `benchmark_60_40` | `-0.000380142` | `0.004738985` | `+0.264056` | `+1.999695` | `0.025410` | `-0.021173` | `-19.6039` (`p=0.00e+00`, `lag=3`) | `-19.5841` (`p=0.00e+00`, `lag=3`) | `-11.2606` / `-11.0908` (`lag=20`) |
| `full_development_3020d` (`3020`, `2005-01-04..2016-12-30`) | `min_variance` | `-0.000287387` | `0.005498684` | `-0.132766` | `+14.330162` | `0.054957` | `-0.060894` | `-12.5557` (`p=2.16e-23`, `lag=21`) | `-12.4917` (`p=2.94e-23`, `lag=21`) | `-11.6047` / `-11.5646` (`lag=18`) |
| `full_development_3020d` (`3020`, `2005-01-04..2016-12-30`) | `equal_weight` | `-0.000356943` | `0.010788218` | `-0.419485` | `+14.633428` | `0.079559` | `-0.119630` | `-12.3711` (`p=5.28e-23`, `lag=19`) | `-12.1709` (`p=1.42e-22`, `lag=19`) | `-11.2221` / `-11.0411` (`lag=19`) |
| `full_development_3020d` (`3020`, `2005-01-04..2016-12-30`) | `benchmark_60_40` | `-0.000280831` | `0.007328191` | `-0.621123` | `+22.038695` | `0.052668` | `-0.102594` | `-12.4078` (`p=4.41e-23`, `lag=20`) | `-12.2156` (`p=1.14e-22`, `lag=20`) | `-11.2606` / `-11.0908` (`lag=20`) |

### Empirical Interpretation of Historical vs. Gaussian Risk Differences
1. **Leptokurtic Shoulder vs. Extreme-Tail Crossing:**
   - On `full_development_3020d` (`2005-01-04..2016-12-30`), mixing the 2007–2009 GFC with calmer years produces extreme loss excess kurtosis (`+14.33` on `min_variance`, `+14.63` on `equal_weight`, `+22.04` on `benchmark_60_40`). Because a leptokurtic distribution concentrates probability mass both in the narrow central peak and in the far tails while depleting the intermediate shoulders, **90% and 95% Historical VaR lie below Parametric Normal VaR** on `full_development_3020d` (by `-14.11 bps` and `-5.76 bps` on `min_variance`), whereas **95% Historical ES already exceeds Parametric Normal ES by `+16.49 bps`** (`1.2704%` vs. `1.1055%`) because ES integrates across the heavy tail beyond the 95% quantile.
   - At **99% confidence**, we are past the distribution's shoulder into the fat tail across all portfolios and both windows: on `min_variance`, 99% Historical VaR exceeds Parametric Normal VaR by `+14.07 bps` (`1.0414%` vs. `0.9006%`) in `recent_development_1260d` and by `+23.20 bps` (`1.4824%` vs. `1.2504%`) in `full_development_3020d`, while **99% Historical ES exceeds Parametric Normal ES by `+46.74 bps` (`1.5018%` vs. `1.0344%`, `1.45x`) in `recent_development_1260d` and by `+72.27 bps` (`2.1595%` vs. `1.4368%`, `1.50x`) in `full_development_3020d`**.
2. **Distinction Between Fixed-Exposure Risk Series and Changing-Weight Net Strategy Series:**
   - Point-in-time risk estimation (`estimate_risk`) evaluates the historical distribution of the **current fixed weight vector** $w$ (`R_{p,t} = (R w)_t$, pre-cost, $N = 1{,}260$ or $N = 3{,}020$), whereas Step 4's performance KPIs evaluate the **changing-weight, monthly-rebalanced, post-cost** strategy trajectory (`path.net_returns`, $N = 2{,}516$ active sessions `2007-01-05..2016-12-30`). Both series strongly reject a unit root in ADF diagnostics, though ADF unit-root rejection does not imply independent and identically distributed (`i.i.d.`) losses or constant conditional volatility.

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


---

## 7. SOLO STEP 7 (C2/C3) — Unconditional EVT and tail uncertainty

<!-- Generated by scripts/generate_step7_methodology.py from the saved authority. -->

**DEVELOPMENT ONLY through 2016-12-30; fixed terminal-development exposure;
one-day pre-cost simple-return losses. Human validation and mandate/protocol approval PENDING.**

Authority: `results/step7_evt_preview/step7_recorded_results.json`.
Dataset: `qe1_20050101_20261030_r3_6c4633a7ba`. Config: `587ddbe363589fb6956c23c5fe8b2b544bac81d9224a0b4bb59f60f5fbc0a017`.
NAV: USD 10,000,000.00. Exposure: SPY 33.9337%, EFA 0.0000%, EEM 0.0000%, AGG 40.0000%, GLD 26.0663%, XLE 0.0000%, XLK 0.0000%.

### 7.1 Construction and limitations

Loss is `L = -(asset_returns @ weights)`. The threshold is the empirical step-CDF
quantile under the recorded fixed quantile policy; excesses are strictly `L > u`.
GPD location is fixed at zero. Scale must be positive and observed excesses must
satisfy fitted support. Failed convergence, inadequate excess counts and invalid
support remain explicit unavailable results. Nelder-Mead uses maxiter=20,000 and
maxfun=40,000, plus a local likelihood perturbation check. The reported parameter
SEs use analytic iid asymptotic formulas, not an observed-Hessian covariance.

For `p_u = N_u/n` and `a = (1-c)/p_u <= 1`, pure-POT VaR is
`u + beta*expm1(-xi*log(a))/xi`, with limit `u-beta*log(a)` at xi=0.
The actual threshold boundary is `1-p_u`; below it pure POT is unavailable.
For xi<1, `ES = (VaR + beta - xi*u)/(1-xi)`; at xi>=1, ES is unavailable
with a warning even if VaR is finite. Negative-xi tails have finite upper support.

The hybrid has the empirical step CDF for x<=u and `1-p_u*S_GPD(x-u)` for x>u.
Its empirical body has atoms and is not smooth or globally continuous. The tail's
right limit matches F(u); generally there is a left jump at u. Body-region VaR is
labelled BODY, not EVT extrapolation. Hybrid ES uses exact discrete body-quantile
integration, including fractional probability mass, plus analytic tail integration.

QQ/PP plots are descriptive diagnostics; they do not prove fit quality. Positive
xi point estimates are consistent with heavy tails under this fitted model, but
do not by themselves establish a formal rejection of Gaussianity. The recorded
moving-block xi intervals below both include zero. Threshold sensitivity, sparse
excesses, unconditional modelling and dependence limit interpretation; apparent
stability is not proof that the provisional threshold is uniquely correct.

The inherited threshold policy was recorded before development fitting, but it
remains unsigned and is not completed human preregistration. Step 6 found exception
clustering; the green final 250-session Basel blocks do not establish overall model
adequacy. These EVT results are not rolling EVT validation or final holdout results.

### 7.2 Samples and shape uncertainty

| Window | Start | End | Observations | Primary excesses | xi | xi interval low | xi interval high | Interval status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recent_development_1260d | 2011-12-29 | 2016-12-30 | 1260 | 63 | 0.225755 | -0.123433 | 0.493897 | ok |
| full_development_3020d | 2005-01-04 | 2016-12-30 | 3020 | 151 | 0.260679 | -0.007762 | 0.432967 | ok |

### 7.3 Threshold diagnostics

| Window | q | u (%) | Strict exceedances | Ties at u | Mean excess (%) | xi | xi SE (iid asymptotic) | beta (%) | beta minus xi*u (%) | Status | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recent_development_1260d | 0.800 | 0.2603 | 252 | 1 | 0.2537 | 0.1686 | 0.0736 | 0.2105 | 0.1666 | ok | N/A |
| recent_development_1260d | 0.825 | 0.2864 | 220 | 1 | 0.2626 | 0.1533 | 0.0778 | 0.2218 | 0.1779 | ok | N/A |
| recent_development_1260d | 0.850 | 0.3199 | 189 | 1 | 0.2692 | 0.1534 | 0.0839 | 0.2273 | 0.1782 | ok | N/A |
| recent_development_1260d | 0.875 | 0.3569 | 157 | 1 | 0.2826 | 0.1342 | 0.0905 | 0.2439 | 0.1960 | ok | N/A |
| recent_development_1260d | 0.900 | 0.4291 | 126 | 1 | 0.2722 | 0.2236 | 0.1090 | 0.2113 | 0.1154 | ok | N/A |
| recent_development_1260d | 0.925 | 0.4834 | 94 | 1 | 0.3006 | 0.1758 | 0.1213 | 0.2470 | 0.1620 | ok | N/A |
| recent_development_1260d | 0.950 | 0.5927 | 63 | 1 | 0.3134 | 0.2258 | 0.1544 | 0.2423 | 0.1085 | ok | N/A |
| recent_development_1260d | 0.975 | 0.7965 | 31 | 1 | 0.3438 | N/A | N/A | N/A | N/A | unavailable | insufficient strict exceedances: N_u=31 < min_exceedances=50 at threshold quantile 0.975 (threshold and minimum are never lowered silently) |
| full_development_3020d | 0.800 | 0.2925 | 604 | 1 | 0.3900 | 0.1451 | 0.0466 | 0.3331 | 0.2907 | ok | N/A |
| full_development_3020d | 0.825 | 0.3328 | 528 | 1 | 0.4031 | 0.1274 | 0.0491 | 0.3512 | 0.3088 | ok | N/A |
| full_development_3020d | 0.850 | 0.3846 | 453 | 1 | 0.4142 | 0.1178 | 0.0525 | 0.3647 | 0.3194 | ok | N/A |
| full_development_3020d | 0.875 | 0.4596 | 377 | 1 | 0.4150 | 0.1436 | 0.0589 | 0.3547 | 0.2887 | ok | N/A |
| full_development_3020d | 0.900 | 0.5349 | 302 | 1 | 0.4340 | 0.1278 | 0.0649 | 0.3775 | 0.3092 | ok | N/A |
| full_development_3020d | 0.925 | 0.6610 | 226 | 1 | 0.4330 | 0.1842 | 0.0788 | 0.3526 | 0.2309 | ok | N/A |
| full_development_3020d | 0.950 | 0.8181 | 151 | 1 | 0.4523 | 0.2607 | 0.1026 | 0.3368 | 0.1235 | ok | N/A |
| full_development_3020d | 0.975 | 1.0863 | 75 | 1 | 0.5352 | 0.2248 | 0.1414 | 0.4159 | 0.1717 | ok | N/A |

### 7.4 Matched model comparison

All methods within each window use identical observations, exposure and horizon.
Conversions: loss fraction times 100 gives percent, times NAV gives USD, and
times 10,000 gives basis points. N/A remains unavailable, not zero.

| Window | Model | Confidence | VaR (%) | VaR (USD) | ES (%) | ES (USD) | ES minus VaR (bps) | VaR minus Normal (bps) | ES minus Normal (bps) | Status | Region | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recent_development_1260d | historical | 0.90 | 0.4291 | 42910.90 | 0.7013 | 70126.16 | 27.2153 | -5.9052 | 2.6197 | ok | N/A | N/A |
| recent_development_1260d | parametric_normal | 0.90 | 0.4882 | 48816.06 | 0.6751 | 67506.50 | 18.6904 | 0.0000 | 0.0000 | ok | N/A | N/A |
| recent_development_1260d | monte_carlo_normal | 0.90 | 0.4873 | 48727.99 | 0.6781 | 67808.78 | 19.0808 | -0.0881 | 0.3023 | ok | N/A | N/A |
| recent_development_1260d | evt_pot | 0.90 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | unavailable | N/A | confidence 0.9 < threshold_quantile 0.95: pure POT tail inference is unavailable in the loss body; the empirical-body/GPD-tail hybrid must be requested explicitly (estimate_evt_body_tail). |
| recent_development_1260d | evt_body_tail_hybrid | 0.90 | 0.4291 | 42910.90 | 0.7010 | 70101.98 | 27.1911 | -5.9052 | 2.5955 | ok | body | VaR lies in the empirical BODY (below 1 - p_u); it is not EVT extrapolation |
| recent_development_1260d | historical | 0.95 | 0.5927 | 59272.67 | 0.9061 | 90614.38 | 31.3417 | -3.8861 | 10.9591 | ok | N/A | N/A |
| recent_development_1260d | parametric_normal | 0.95 | 0.6316 | 63158.73 | 0.7966 | 79655.23 | 16.4965 | 0.0000 | 0.0000 | ok | N/A | N/A |
| recent_development_1260d | monte_carlo_normal | 0.95 | 0.6338 | 63384.50 | 0.8025 | 80249.91 | 16.8654 | 0.2258 | 0.5947 | ok | N/A | N/A |
| recent_development_1260d | evt_pot | 0.95 | 0.5927 | 59272.67 | 0.9057 | 90566.01 | 31.2933 | -3.8861 | 10.9108 | ok | threshold_boundary | N/A |
| recent_development_1260d | evt_body_tail_hybrid | 0.95 | 0.5927 | 59272.67 | 0.9057 | 90566.01 | 31.2933 | -3.8861 | 10.9108 | ok | threshold_boundary | N/A |
| recent_development_1260d | historical | 0.99 | 1.0414 | 104137.56 | 1.5018 | 150178.25 | 46.0407 | 14.0744 | 46.7371 | ok | N/A | N/A |
| recent_development_1260d | parametric_normal | 0.99 | 0.9006 | 90063.18 | 1.0344 | 103441.16 | 13.3780 | 0.0000 | 0.0000 | ok | N/A | N/A |
| recent_development_1260d | monte_carlo_normal | 0.99 | 0.9074 | 90737.47 | 1.0482 | 104815.52 | 14.0780 | 0.6743 | 1.3744 | ok | N/A | N/A |
| recent_development_1260d | evt_pot | 0.99 | 1.0629 | 106293.35 | 1.5130 | 151297.01 | 45.0037 | 16.2302 | 47.8559 | ok | tail | N/A |
| recent_development_1260d | evt_body_tail_hybrid | 0.99 | 1.0629 | 106293.35 | 1.5130 | 151297.01 | 45.0037 | 16.2302 | 47.8559 | ok | tail | N/A |
| full_development_3020d | historical | 0.90 | 0.5349 | 53488.25 | 0.9688 | 96884.80 | 43.3965 | -14.1064 | 3.2577 | ok | N/A | N/A |
| full_development_3020d | parametric_normal | 0.90 | 0.6759 | 67594.60 | 0.9363 | 93627.12 | 26.0325 | 0.0000 | 0.0000 | ok | N/A | N/A |
| full_development_3020d | monte_carlo_normal | 0.90 | 0.6851 | 68505.21 | 0.9431 | 94313.39 | 25.8082 | 0.9106 | 0.6863 | ok | N/A | N/A |
| full_development_3020d | evt_pot | 0.90 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | unavailable | N/A | confidence 0.9 < threshold_quantile 0.95: pure POT tail inference is unavailable in the loss body; the empirical-body/GPD-tail hybrid must be requested explicitly (estimate_evt_body_tail). |
| full_development_3020d | evt_body_tail_hybrid | 0.90 | 0.5349 | 53488.25 | 0.9704 | 97044.84 | 43.5566 | -14.1064 | 3.4177 | ok | body | VaR lies in the empirical BODY (below 1 - p_u); it is not EVT extrapolation |
| full_development_3020d | historical | 0.95 | 0.8181 | 81806.85 | 1.2704 | 127037.71 | 45.2309 | -5.7646 | 16.4895 | ok | N/A | N/A |
| full_development_3020d | parametric_normal | 0.95 | 0.8757 | 87571.44 | 1.1055 | 110548.19 | 22.9768 | 0.0000 | 0.0000 | ok | N/A | N/A |
| full_development_3020d | monte_carlo_normal | 0.95 | 0.8786 | 87859.25 | 1.1127 | 111268.69 | 23.4094 | 0.2878 | 0.7205 | ok | N/A | N/A |
| full_development_3020d | evt_pot | 0.95 | 0.8181 | 81806.85 | 1.2736 | 127357.79 | 45.5509 | -5.7646 | 16.8096 | ok | threshold_boundary | N/A |
| full_development_3020d | evt_body_tail_hybrid | 0.95 | 0.8181 | 81806.85 | 1.2736 | 127357.79 | 45.5509 | -5.7646 | 16.8096 | ok | threshold_boundary | N/A |
| full_development_3020d | historical | 0.99 | 1.4824 | 148244.03 | 2.1595 | 215949.02 | 67.7050 | 23.1994 | 72.2712 | ok | N/A | N/A |
| full_development_3020d | parametric_normal | 0.99 | 1.2504 | 125044.65 | 1.4368 | 143677.84 | 18.6332 | 0.0000 | 0.0000 | ok | N/A | N/A |
| full_development_3020d | monte_carlo_normal | 0.99 | 1.2646 | 126458.38 | 1.4420 | 144203.21 | 17.7448 | 1.4137 | 0.5254 | ok | N/A | N/A |
| full_development_3020d | evt_pot | 0.99 | 1.4915 | 149149.25 | 2.1844 | 218444.60 | 69.2953 | 24.1046 | 74.7668 | ok | tail | N/A |
| full_development_3020d | evt_body_tail_hybrid | 0.99 | 1.4915 | 149149.25 | 2.1844 | 218444.60 | 69.2953 | 24.1046 | 74.7668 | ok | tail | N/A |

### 7.5 Fixed-length moving-block bootstrap uncertainty

The saved policy uses block length 10, 100
replications, seed 202602 and minimum 80
finite replicates per reported interval. Blocks have fixed length with uniform
non-circular starting positions, concatenated and truncated to sample length.
This is a moving-block bootstrap, not the distinct stationary bootstrap. Each
resample re-estimates u under the fixed quantile policy and refits independently.
Caching is process-local; results and replicates are persisted in the authority.

Intervals are percentile summaries conditional on the threshold policy and block
dependence assumption; they omit threshold-selection uncertainty and regime shifts.
Ties can place 95% below a resample's pure-tail boundary. The pure-POT intervals
below remain N/A when too few replicates are available; hybrid intervals are
reported separately and must not be substituted under a pure-POT label.

| Window | Confidence | Method | VaR finite/total | ES finite/total | Required | Infinite ES | VaR median (%) | VaR interval (%) | VaR interval status | ES median (%) | ES interval (%) | ES interval status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recent_development_1260d | 0.90 | body_tail_hybrid | 100/100 | 100/100 | 80 | 0 | 0.4302 | [0.3602, 0.4717] | ok | 0.6972 | [0.6085, 0.7970] | ok |
| recent_development_1260d | 0.95 | pure_pot | 58/100 | 58/100 | 80 | 0 | N/A | N/A | unavailable: 58 finite replicates < required 80 | N/A | N/A | unavailable: 58 finite replicates < required 80 |
| recent_development_1260d | 0.95 | body_tail_hybrid | 100/100 | 100/100 | 80 | 0 | 0.5927 | [0.5167, 0.6489] | ok | 0.8967 | [0.7599, 1.0497] | ok |
| recent_development_1260d | 0.99 | pure_pot | 100/100 | 100/100 | 80 | 0 | 1.0641 | [0.8826, 1.2399] | ok | 1.4964 | [1.1015, 1.9822] | ok |
| recent_development_1260d | 0.99 | body_tail_hybrid | 100/100 | 100/100 | 80 | 0 | 1.0641 | [0.8826, 1.2399] | ok | 1.4964 | [1.1015, 1.9822] | ok |
| full_development_3020d | 0.90 | body_tail_hybrid | 100/100 | 100/100 | 80 | 0 | 0.5331 | [0.4882, 0.5980] | ok | 0.9771 | [0.8753, 1.0782] | ok |
| full_development_3020d | 0.95 | pure_pot | 62/100 | 62/100 | 80 | 0 | N/A | N/A | unavailable: 62 finite replicates < required 80 | N/A | N/A | unavailable: 62 finite replicates < required 80 |
| full_development_3020d | 0.95 | body_tail_hybrid | 100/100 | 100/100 | 80 | 0 | 0.8201 | [0.7446, 0.8854] | ok | 1.2863 | [1.1299, 1.4516] | ok |
| full_development_3020d | 0.99 | pure_pot | 100/100 | 100/100 | 80 | 0 | 1.5051 | [1.3126, 1.7450] | ok | 2.2066 | [1.7483, 2.7006] | ok |
| full_development_3020d | 0.99 | body_tail_hybrid | 100/100 | 100/100 | 80 | 0 | 1.5051 | [1.3126, 1.7450] | ok | 2.2066 | [1.7483, 2.7006] | ok |

### 7.6 Verification and handoff

The numerical implementation was independently checked, including exact body-mass
integration, saved C1 equivalence and bootstrap-summary recomputation. Generated
document cells and conversions are checked against the authority by regression
tests. Passing software tests is not independent human economic validation.
Actual source/artifact hashes are in the preview manifest. No post-development
strategy outcomes are used. Stop before Step 8 for review.
