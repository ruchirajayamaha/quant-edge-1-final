# Official requirement trace

Source: official `Quant edge 1.0 Final Challenge 1.pdf` (10 pages), sections8-10.
Status refers to actual artifacts, not a guarantee of compliance before human review.

| Official requirement | Actual evidence | Status / limit |
|---|---|---|
| USD10M conservative endowment; seven prescribed ETFs | config.yaml; memo pages1-4; app Decision | Implemented; team-proposed mandate pending approval |
| Explain horizon, return objective and risk limits | mandate_proposal.json; memo page2; recommendation.pdf | Proposed with explicit arithmetic; not invented client facts |
| Adjusted prices, trading-calendar alignment, log/statistical work and simple-return explanation | data manifests; data.py/returns.py; memo page3 | Implemented and tested |
| Flag suspected errors and document cleaning; stationarity check | quality_flags.parquet; ADF tables; memo page3 | Retained flags, no silent outlier deletion; stationarity is not iid |
| Markowitz allocation and allocation weights | portfolio.py; current_weights in reference.json; app | Implemented; target caps and drift distinguished |
| Performance / CAPM KPIs and interpreted decision relevance | final period_kpis.csv; app Performance; memo pages5-6 | Implemented with units / denominator availability |
| Historical, parametric and Monte Carlo VaR95/99; Expected Shortfall | final risk_table.csv; app Tail risk; memo page7 | Same exposure/sample/horizon; primary risk before costs |
| Justified EVT method and diagnostics | evt.py; final evt_diagnostics.csv; earlier Step7 QQ/PP/bootstrap; memo page8 | Failure states retained; earlier intervals not relabelled current |
| OOS backtesting of chosen VaR; Kupiec / Christoffersen | final backtest CSVs and coverage_summary; app; memo page9 | Primary Historical, fixed Normal comparison; MC/EVT rolling not claimed |
| Basel traffic-light evidence | final reference.json basel; app Backtesting | Educational99%/250 valid sessions; green is not approval |
| Marginal / component risk and position sizing | risk_budget.py; reference risk_contributions / allocation_comparisons; memo page11 | Signed Euler; explicit feasibility and proposed-limit breaches |
| GFC, COVID,2022 and hypothetical scenario | final stress_results.csv; app; memo page10 | Same current-target ex-post replays; duration/probability caveats |
| Streamlit sidebar confidence, methodology and date range | app/Home.py; real AppTest controls | Implemented; target dates preserve training; separate rolling selector |
| Weights, wealth/drawdown, comparative risk, backtests, stress, assumptions/limitations views | six app views; frozen result bundle | Implemented; actual real-data UI checks recorded in closure |
| Public or judge-accessible repository | GitHub repository linked in README | Publication verified separately; no invented access claim |
| Hosted app OR one-command local launch | scripts/launch.py; README clean setup | Local option selected; hosted deployment is not mandatory |
| Investment memo7-15 pages | investment_memo.pdf |12 pages; rendered and visually inspected |
| Tear sheet1 page | tear_sheet.pdf |1 page; rendered and visually inspected |
| Section8.6 plain-English ACCEPT/ADJUST/REJECT recommendation | recommendation.pdf |1 page; conditional ADJUST; human substantiation PENDING |
| AI tools, material contribution and independent human validation | AI_DISCLOSURE.md; VALIDATION_CHECKLIST.md | AI disclosure present; real human validation remains PENDING |
| Team understands / defends all material; responsibility for accuracy | DEFENCE_NOTES.md; checklist | Human task remains OPEN; no fabricated names or rehearsal |
|10-12 minute pitch/deck if final-five selected | DEFENCE_NOTES.md timing / prompts | Conditional follow-up; no completed deck/rehearsal claim |

## Rubric visibility

| Weight | Where judges can assess it |
|---|---|
| Investment decision-making30% | Decision page; memo1-2,6,10-11; conditional recommendation, funding/risk bridge and action triggers |
| Technical rigor25% | Same-sample model tables, exact ES mass, EVT domain failures, coverage likelihoods, independent scalar checks and test suite |
| Software/interface15% | Six real-data views, usable controls, one-command offline launch, verified frozen bundle and clean-install evidence |
| Innovation/ambition15% | Version-aware RF evidence; empirical-body/GPD-tail distinction; matched recent/full tail sensitivity; signed risk budget linked to funding/governance. These are justified extensions, not a claim of unprecedented novelty. |
| Communication/defence15% |12-page memo, one-page outputs, plain-English limitations and defence questions; actual team defence remains the team's responsibility |

No official requirement for a paid service, hosted deployment, every-model rolling
backtest or guaranteed return / competition rank has been invented.
