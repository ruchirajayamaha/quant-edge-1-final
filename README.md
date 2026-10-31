# Quant Edge 1.0 | Endowment Decision Room

An offline-reproducible Python and Streamlit decision tool for Serendib University's
USD10 million endowment. The eligible universe is **SPY, EFA, EEM, AGG, GLD, XLE, XLK**.

**Proposed decision: CONDITIONAL ADJUST.** The unchanged constrained minimum-variance
rule is a candidate, not an approved trade instruction. The proposed funding hurdle,
tail-loss budgets, concentration and monthly drift policy require human approval.
Independent human validation is **PENDING**; automated tests do not satisfy that requirement.

**Judges: start at [FINAL_SUBMISSION/00_START_HERE.md](FINAL_SUBMISSION/00_START_HERE.md).**
That folder is the one canonical submission, and
[QuantEdge_Final_Submission.zip](QuantEdge_Final_Submission.zip) is an archive of it.

[Investment memo](FINAL_SUBMISSION/01_Investment_Memo.pdf) ·
[One-page tear sheet](FINAL_SUBMISSION/02_Executive_Tear_Sheet.pdf) ·
[Plain-English recommendation](FINAL_SUBMISSION/supporting/Recommendation.pdf) ·
[Requirement trace](FINAL_SUBMISSION/COMPLIANCE_MATRIX.md) ·
[AI disclosure](AI_DISCLOSURE.md)

Repository visibility is **public**, verified by anonymous GitHub API and webpage
HTTP200 responses on31 October2026. Exact evidence: `audit/step9_review/publication.json`.

## Install and launch

Use **Python3.11**. Setup needs package installation; normal app launch needs no
market-data downloads, API key or paid service. Frozen inputs and results are included.
The official challenge permits a local one-command launch instead of hosted deployment.

Windows PowerShell:

```powershell
git clone https://github.com/ruchirajayamaha/quant-edge-1-final.git
cd quant-edge-1-final
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe scripts/launch.py
```

If Python3.11 is installed via `uv`, replace the venv command with
`uv venv --python 3.11 --seed .venv`. Global Python3.13 is not the verified environment.

macOS/Linux:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python scripts/launch.py
```

Equivalent direct command after activation: `streamlit run app/Home.py`.
Open the local URL printed by Streamlit, normally http://localhost:8501.
No public hosted-app URL is claimed. For headless verification:
`python scripts/launch.py --server.headless=true --server.port=8501`.

## What the app shows

The decision page connects funding needs to loss budgets. Other views cover
matched-period wealth/drawdown and CAPM KPIs; Historical, Normal, Monte Carlo Normal,
POT-GPD and separately labelled body/tail risk; rolling exceptions and coverage
tests; signed Euler risk contributions, feasible-allocation diagnostics and crisis
replays; assumptions, provenance and limitations.

Controls select portfolio, confidence90/95/99, risk methodology, estimation sample,
and performance/backtest target dates. Date selection preserves prior training
history. Current risk/stress exposures are prospective targets estimated at the
frozen final close, clearly distinguished from historical pre-return holdings.
Rolling validation is implemented for **Historical and Normal only**, using its
own selector. Risk-only MC/EVT estimates are not presented as backtested models.

## Frozen reference and headline evidence

- Dataset: `qe1_20050101_20261030_r3_6c4633a7ba`, schema1.1.0.
- Price bounds:3 Jan2005-30 Oct2026;5,491 one-session returns from4 Jan2005.
- Portfolio paths:5 Jan2007-30 Oct2026 after504-session warmup.
- Evaluation:4 Jan2021-30 Oct2026. Primary CAGR7.63%, annual volatility8.80%,
  maximum drawdown-16.78%, before spending and additional mandate fee, net of trading costs.
- Current recent HS99 VaR1.54%, ES2.03%; full-history HS99 ES2.50%.
- Final250 sessions:HS99 four exceptions (educational green), Normal99 nine (yellow).
  Longer-span calibration and clustering limitations remain material.

These are historical/fitted estimates, not forecasts or guaranteed loss bounds.
The proposed6.75% hurdle comprises4% spending,2.5% assumed inflation and a separate
0.25% additional fee under the explicit cash-flow convention. ETF fund expenses
are already embedded. The proposal is in `submission/mandate_proposal.json`, not
silently substituted for signed limits in the preserved config.

The rule and proposal were committed before post-2016 strategy outcomes in
`782ec20`. Earlier whole-history asset EDA, RF research and fixed-exposure stress
inspection were already available. We report registered-rule evaluation and do
not claim a pristine blind experiment or tune a winner on evaluation results.

## Reproduce and verify

```powershell
.\.venv\Scripts\python.exe scripts/build_final_results.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

The pipeline takes approximately one minute on the development machine; cache-free
runtime depends on hardware. All app/reference tables use the shared analytical
library. `results/final/reference.json` and its manifest bind dataset/config/source
identity; no executable pickle is loaded. Tampering or stale analytical code/config
is rejected. Reference hashes are checked on app load; sidebar changes cache only
affected risk computations. Original Steps3-8 outputs remain available unchanged.

The reports are compiled from LaTeX. That needs a TeX distribution and optional
Python packages, neither of which the app needs:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-render.txt
.\.venv\Scripts\python.exe scripts/build_reports.py
.\.venv\Scripts\python.exe audit/presentation_review/verify_presentation.py
```

`scripts/build_reports.py` is the one report entry point. It generates every number from
the frozen results, compiles with XeLaTeX and BibTeX, checks page limits and publishes
to `FINAL_SUBMISSION/`. Sources, toolchain and exact options are in
[report/latex/README.md](report/latex/README.md). Render and read every page after an edit.
The old ReportLab script only runs with `--legacy-reportlab`, and writes elsewhere.

## Method and limitations

Monthly minimum variance uses504 prior sessions and sample covariance (ddof1).
Long-only targets have ETF≤40%, equity≤35%, AGG+GLD≥40%; the first two imply
AGG and GLD each25%-40%. Targets are controlled; natural daily drift is not clipped.
Transaction cost is5bps times sum of absolute traded weights, with no factor-half.
Performance compounds simple returns; log returns support statistical diagnostics.
Dollar risk uses one-day simple loss before costs on USD10M.

Historical ES uses exact fractional/tied tail mass. Normal MC uses25,000 deterministic
scenarios and is not a fat-tail extension. POT requires50 strict excesses; pure tail
inference below the empirical boundary is unavailable. Hybrid body VaR is explicitly
empirical. Divergent ES, failed fits and sparse tests remain unavailable/warnings.
Kupiec uses all eligible observations; Christoffersen CC uses a transition-conditioned
likelihood and is withheld across disconnected runs. Basel is educational99%/250 days.

RF r3 uses eligible historical versions and day-level release evidence, not verified
intraday timestamps. Inferred dates, sparse-era fallbacks and two unresolved cases
remain. DTB3/252 is an approximate quote proxy, not realised bill return. Distribution
income is not added twice to adjusted returns. CPI is ex-post revised context with
missing/unreleased months; endpoint real-growth intervals are disclosed. Stress
replays use the current target ex-post, not the historical investable strategy.

## Submission and defence

Start with `FINAL_SUBMISSION/00_START_HERE.md`. The memo and1-page tear sheet are the
section7 documents, and the1-page recommendation answers section8.6. `submission/DEFENCE_NOTES.md`
supports human review and a conditional final-five10-12 minute pitch. A slide deck
is not claimed to have been submitted or rehearsed. Exact organiser deadline,
upload route and team member details must come from the team/organiser.

Before certification, complete `FINAL_SUBMISSION/supporting/Human_Review_Status.md` with real names,
dates and calculations, using `handoff/human_review_pack/`. AI generated/materially changed code, analysis and prose;
the team must independently evaluate and defend them under the official AI rules.

## Repository map

`src/quantedge/`: UI-independent analytics; `app/`: Streamlit; `report/latex/`: report
sources; `handoff/human_review_pack/`: blank human review pack; `data/`: verified
snapshots/evidence; `results/final/`: frozen integrated results; `tests/`: numerical,
causality and real-app checks; `audit/`: independent recomputations and review trail;
`docs/sections/`: detailed method; `scripts/`: reproducible builders;
`antigravity-team-pack/`: preserved historical workflow instructions. The current
README and final closure supersede stale milestone stop notes, without rewriting
their historical evidence. No secrets, virtual environment or temporary runtime
cache belongs in the published repository.
