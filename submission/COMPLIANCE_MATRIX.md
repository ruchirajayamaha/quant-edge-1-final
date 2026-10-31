# Official requirement trace

Source: official `Quant edge 1.0 Final Challenge 1.pdf` (10 pages), sections8-10.
Status refers to actual artifacts, not a guarantee of compliance before human review.

| Official requirement | Actual evidence | Status / limit |
|---|---|---|
| USD10M conservative endowment; seven prescribed ETFs | config.yaml; memo pages1-3; app Decision | Implemented; team-proposed mandate pending approval |
| Explain horizon, return objective and risk limits | mandate_proposal.json; memo pages1-2; recommendation.pdf | Proposed with explicit arithmetic; not invented client facts |
| Adjusted prices, trading-calendar alignment, log/statistical work and simple-return explanation | data manifests; data.py/returns.py; memo page2 | Implemented and tested |
| Flag suspected errors and document cleaning; stationarity check | quality_flags.parquet; ADF tables; memo page2 | Retained flags, no silent outlier deletion; stationarity is not iid |
| Markowitz allocation and allocation weights | portfolio.py; current_weights in reference.json; memo pages2-3; app | Implemented; target caps and drift distinguished |
| Performance / CAPM KPIs and interpreted decision relevance | final period_kpis.csv; app Performance; memo pages3-4 | Implemented with units / denominator availability |
| Historical, parametric and Monte Carlo VaR95/99; Expected Shortfall | final risk_table.csv; app Tail risk; memo pages4-5 | Same exposure/sample/horizon; primary risk before costs |
| Justified EVT method and diagnostics | evt.py; final evt_diagnostics.csv; earlier Step7 QQ/PP/bootstrap; memo pages5-7 | Failure states retained; earlier intervals not relabelled current |
| OOS backtesting of chosen VaR; Kupiec / Christoffersen | final backtest CSVs and coverage_summary; app; memo pages7-8 | Primary Historical, fixed Normal comparison; MC/EVT rolling not claimed |
| Basel traffic-light evidence | final reference.json basel; app Backtesting; memo page8 | Educational99%/250 valid sessions; green is not approval |
| Marginal / component risk and position sizing | risk_budget.py; reference risk_contributions / allocation_comparisons; memo pages8-9 | Signed Euler; explicit feasibility and proposed-limit breaches |
| GFC, COVID,2022 and hypothetical scenario | final stress_results.csv; app; memo page9 | Same current-target ex-post replays; duration/probability caveats |
| Streamlit sidebar confidence, methodology and date range | app/Home.py, app/qe_views.py; real AppTest controls | Implemented; target dates preserve training; separate rolling selector |
| Weights, wealth/drawdown, comparative risk, backtests, stress, assumptions/limitations views | six app views; frozen result bundle | Implemented; actual real-data UI checks recorded in closure |
| Public or judge-accessible repository | GitHub repository linked in README; publication.json | Public; anonymous API and webpage HTTP200 verified31 Oct2026 |
| Hosted app OR one-command local launch | scripts/launch.py; README clean setup | Local option selected; hosted deployment is not mandatory |
| Investment memo7-15 pages | investment_memo.pdf; report/latex/main.tex |11 pages; compiled with XeLaTeX; every page rendered and inspected |
| Tear sheet1 page | tear_sheet.pdf; report/latex/tear_sheet.tex |1 page; rendered and visually inspected |
| Section8.6 plain-English ACCEPT/ADJUST/REJECT recommendation | recommendation.pdf; report/latex/recommendation.tex |1 page; conditional ADJUST; human substantiation PENDING |
| AI tools, material contribution and independent human validation | AI_DISCLOSURE.md; VALIDATION_CHECKLIST.md; human_review/ | AI disclosure present; real human validation remains PENDING |
| Team understands / defends all material; responsibility for accuracy | DEFENCE_NOTES.md; checklist | Human task remains OPEN; no fabricated names or rehearsal |
|10-12 minute pitch/deck if final-five selected | DEFENCE_NOTES.md timing / prompts | Conditional follow-up; no completed deck/rehearsal claim |

## Rubric visibility

These are pointers to evidence. They are not scores, and the judges decide.

| Weight | Where judges can assess it |
|---|---|
| Investment decision-making30% | App Decision view; memo page1, section4 and section8; tear sheet; recommendation.pdf |
| Technical rigor25% | Memo sections5-7; memo Tables5-11; presentation_verification.json; tests; docs/sections/ in the repository |
| Software/interface15% | Six real-data views, usable controls, one-command offline launch, verified frozen bundle and clean-install evidence; the app needs no TeX |
| Innovation/ambition15% | Version-aware RF evidence; empirical-body/GPD-tail distinction; matched recent/full tail sensitivity; signed risk budget linked to funding/governance. These are justified extensions, not a claim of unprecedented novelty. |
| Communication/defence15% |11-page memo, one-page outputs, plain-English limitations and defence questions; actual team defence remains the team's responsibility |

No official requirement for a paid service, hosted deployment, every-model rolling
backtest or guaranteed return / competition rank has been invented.
