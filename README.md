# Quant Edge 1.0 — Endowment Allocation & Tail-Risk Analytics

Quantitative portfolio construction, tail-risk modelling (VaR, Expected Shortfall, POT-GPD Extreme Value Theory), out-of-sample rolling validation, stress testing, and Streamlit decision support for a conservative **USD 10,000,000** university endowment.

- **Authoritative specification:** `Quant edge 1.0 Final Challenge 1.pdf`
- **Canonical 7-ETF allocation universe:** `SPY, EFA, EEM, AGG, GLD, XLE, XLK`
- **Contract / config schema version:** `1.1.0`
- **Current workflow status:** **SOLO STEP 1 (D0 Project Setup) and SOLO STEP 2 (A1 Data Snapshot, Quality Diagnostics & Bounded `r2` Hardening Pass) complete.** Active verified snapshot: `qe1_20050101_20261030_r2_cd2904443b` (derived from preserved audited snapshot `qe1_20050101_20261030_afb9ce5694`). Analytics (Steps 3–8), full six-view Streamlit dashboard (Step 9), and final report audit (Step 10) are not yet executed; remaining Step 3–9 analytical functions explicitly raise `NotImplementedError` rather than returning fabricated numbers.

---

## Repository Structure

```text
.
├── antigravity-team-pack/   # Workflow specifications, contracts, and review notes (preserved)
├── app/
│   └── Home.py              # Streamlit entrypoint (D0 baseline status; full 6-view UI in Step 9)
├── config.yaml              # Canonical universe, conventions, seeds, and provisional governance fields
├── data/
│   ├── raw/                 # Raw market/FRED snapshots and provenance manifests (Step 2)
│   └── processed/           # Session-aligned prices, simple/log returns, and quality flags (Step 2)
├── docs/
│   └── sections/            # Incremental methodology, limitations, and report sections
├── handoff/
│   └── SOLO.md              # Single-developer checkpoint and audit log across Steps 1–10
├── results/                 # Versioned, config-hashed pipeline result bundles
├── scripts/                 # CLI helpers for reproducible snapshot/pipeline runs
├── src/
│   └── quantedge/           # Installable analytical library (never imports Streamlit)
│       ├── __init__.py
│       ├── contracts.py     # Frozen dataclasses, constants, column schemas, RiskForecastFn
│       ├── config.py        # Offline YAML validator, provisional-item inspector, SHA-256 hasher
│       ├── data.py          # Market-data snapshot, boundary/quarantine guards & SHA-256 cache loader (Step 2)
│       ├── returns.py       # NYSE/Fed calendars, session returns, cutoff-valid RF & ADF diagnostics (Step 2)
│       ├── portfolio.py     # Weight optimization & drifting return-path stubs (Step 3)
│       ├── kpis.py          # Performance KPIs & CAPM regression stub (Step 4)
│       ├── var.py           # Normal moments (ddof=1), VaR estimator & callback registry stubs (Step 5)
│       ├── es.py            # Shared empirical ES tail-weight helper stub (Step 5)
│       ├── backtest.py      # Out-of-sample rolling backtest, Kupiec/Christoffersen & Basel stubs (Step 6)
│       ├── evt.py           # Unconditional POT-GPD EVT & threshold diagnostic stubs (Step 7)
│       ├── risk_budget.py   # Euler VaR/ES contributions & feasible sizing stubs (Step 8)
│       ├── stress.py        # Historical crisis replays & 7-ETF hypothetical scenario stub (Step 8)
│       └── pipeline.py      # Single analytical orchestrator stub (Step 9)
├── tests/
│   ├── conftest.py          # Shared offline fixtures
│   └── test_d_setup.py      # Step 1 import, boundary, config, contract, and stub checks
├── AI_DISCLOSURE.md         # Incremental AI assistance log and PENDING human-validation tracker
├── CHANGELOG.md             # Incremental milestone changelog
├── pyproject.toml           # PEP 621 installable src-layout package metadata
└── requirements.txt         # Verified pinned Python 3.11+ dependencies
```

---

## Windows PowerShell Setup & Launch

Setup and data acquisition (Step 2) are explicit prerequisites prior to launching the interactive dashboard.

### 1. Create and activate a Python 3.11 virtual environment

Using `uv` (recommended on Windows when `py -3.11` is not pre-installed globally):

```powershell
uv venv --python 3.11 .venv
.\.venv\Scripts\Activate.ps1
```

Or using standard `py` / `python` (Python 3.11+):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install pinned dependencies and editable `quantedge` package

With `pip` inside the activated `.venv`:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --no-build-isolation --no-deps -e .
```

Or equivalently with `uv`:

```powershell
uv pip install -r requirements.txt
uv pip install --no-build-isolation --no-deps -e .
```

### 3. Run offline baseline verification checks

```powershell
pytest -q
```

### 4. Launch the Streamlit application

Once setup (and, starting from Step 2/9, data snapshot creation) is complete, launch with the single command:

```powershell
streamlit run app/Home.py
```

---

## Core Conventions & Governance Status

- **Units & sign orientation:** Returns, weights, and risk estimates are expressed as fractions (not percentages). Loss is negative simple portfolio return (`L_t = -R_{p,t}`), so positive VaR/ES values represent losses before transaction costs (`USD loss = loss_fraction * 10,000,000`).
- **No look-ahead:** Portfolio return on session `t` uses weights known strictly before session `t` (`weights_before.loc[t]`), drifting between scheduled rebalances. Rolling risk forecasts for session `t` inspect strictly prior sessions (`train_end < t`).
- **Provisional governance items:** Investment horizon, return target, portfolio constraints, risk limits, illustrative weights, hypothetical stress rationale, and final investment recommendation remain explicitly marked `PROVISIONAL_*` / `PENDING_HUMAN_DECISION` in `config.yaml` until evaluated and signed off by the human team.
