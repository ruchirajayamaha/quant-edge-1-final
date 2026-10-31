# Requirement trace

Source: the official `Quant edge 1.0 Final Challenge 1.pdf`, 10 pages. "Met" means the artifact exists and was
checked by AI. It does not mean a human reviewed it, and **the package is not fully compliant while the 8.7
items below remain open.**

## Deliverables (section 7)

| Requirement | Evidence | Status |
|---|---|---|
| Public repository, documented and reproducible, with a README | https://github.com/ruchirajayamaha/quant-edge-1-final | Met; anonymous access checked |
| Streamlit app deployed, or runnable locally with one command | `python scripts/launch.py`; `03_Links_and_Run_Instructions.md` | Met by local launch; not deployed |
| 7-15 page report covering method, data, cleaning, results, assumptions, limitations | `01_Investment_Memo.pdf`, 11 pages including references | Met |
| One-page tear sheet: portfolio, risk metrics, recommendation | `02_Executive_Tear_Sheet.pdf` | Met |
| One-page plain-English accept / adjust / reject (section 8.6) | `supporting/Recommendation.pdf` | Met; conditional ADJUST |
| 10-12 minute pitch and deck, final five only | `submission/DEFENCE_NOTES.md` in the repository is an outline only | Conditional; no deck or rehearsal exists |

## Streamlit app (section 6)

| Requirement | Where in the app | Status |
|---|---|---|
| Sidebar: confidence 90/95/99, VaR method, backtest dates | Sidebar | Met |
| Weights, cumulative return, drawdown | Performance | Met |
| VaR, ES and EVT side by side at one confidence level | Tail risk | Met |
| Kupiec, Christoffersen and traffic light | Backtesting | Met; Basel zones are educational |
| Impact under each crisis scenario | Risk budget & stress | Met; current-target replays, not the strategy's history |
| Labelled "Assumptions & Limitations" page | Assumptions & Limitations | Met |

## Method (sections 3, 4, 8 and 9)

| Requirement | Evidence | Status |
|---|---|---|
| Horizon, return objective, risk constraints | Memo section 1; `submission/mandate_proposal.json` | Met; team proposals, not client facts |
| Suitability, trade-offs, assumptions | Memo opening and sections 4, 7, 8 | Met |
| Diversification benefits | Memo section 7 | Met; one sample |
| What can go wrong, how bad, how confident | Memo sections 5-8 | Met |
| Markowitz, CAPM and interpreted KPIs (8.1) | Memo sections 3-4, Tables 3-4 | Met |
| Historical, parametric and Monte Carlo VaR at 95 and 99, and why they differ (8.2) | Memo section 5, Table 5 | Met |
| ES with rationale (8.3) | Memo section 5 | Met |
| EVT with justified threshold (8.4) | Memo section 5, Table 6, Figures 5-6 | Met; failures stay unavailable |
| Out-of-sample Kupiec, Christoffersen, Basel (8.5) | Memo section 6, Tables 7-8 | Met for Historical and Normal; rolling MC and EVT not claimed |
| Risk budgeting with marginal contributions (8.6) | Memo section 7, Tables 9-10 | Met |
| GFC, COVID, 2022 and one hypothetical scenario (8.6) | Memo section 7, Table 11 | Met |
| Adjusted prices, calendars, log and simple returns, flags, ADF, reproducible cleaning (9.2) | Memo section 2; `docs/sections/a_data_quality.md` | Met |
| Approved data sources (9.1) | Memo section 9 | Met for Yahoo Finance and FRED. Archived Federal Reserve H.15 pages are disclosed and used only for release dates; **the team should confirm this is acceptable** |

## AI use (section 8.7)

| Requirement | Evidence | Status |
|---|---|---|
| Disclose tools, purposes and material components | `AI_DISCLOSURE.md` | Met |
| Independently review, test and validate AI output | `supporting/Human_Review_Status.md` | **Open: human review pending** |
| Understand and explain all submitted material | `handoff/human_review_pack/` in the repository | **Open: human task** |
| Recommendation developed and defended by the team | `supporting/Human_Review_Status.md` | **Open: the team must evaluate and own it** |

## Rubric: where to find the evidence

These are pointers, not scores. The judges decide.

| Criterion | Weight | Where to look |
|---|---|---|
| Investment decision-making | 30% | App Decision view; memo opening and sections 4, 7, 8; tear sheet; `supporting/Recommendation.pdf` |
| Technical rigor and correctness | 25% | Memo sections 5-7 and Tables 5-11; `supporting/Verification_Summary.md`; `docs/sections/` and `tests/` in the repository |
| Software and interface quality | 15% | The six app views; `03_Links_and_Run_Instructions.md`; the repository README and code |
| Innovation and ambition | 15% | Version-aware risk-free evidence; threshold diagnostics with pure POT and a separately labelled hybrid; matched recent and full tail samples; signed risk budget tied to funding. Justified extensions, not claims of novelty |
| Communication and defence | 15% | Memo, tear sheet and recommendation. The live defence is the team's own |

No paid service, every-model rolling backtest, or guaranteed return has been added as a requirement.
