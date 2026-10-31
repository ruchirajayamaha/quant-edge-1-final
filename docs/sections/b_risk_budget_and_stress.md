# Step 8 — Risk contributions, feasible sizing and stress evidence

**DEVELOPMENT RESEARCH / EX-POST SCENARIOS; human mandate decisions and independent validation PENDING.**

Generated from `results/step8_risk_stress_preview/step8_results.json`. The initial portfolio is the frozen terminal-development exposure, not a newly selected current recommendation. No post-2016 strategy performance was computed. COVID/2022 are explicitly ex-post fixed-allocation stress replays.

## Risk allocation convention

For Normal loss risk `rho(w)=-mu@w+k*sqrt(w@Sigma@w)`, the marginal is `-mu+k*(Sigma@w)/sigma`; k is the Normal quantile for VaR or Normal density divided by tail mass for ES. Component risk is weight times marginal risk. Shared moments use ddof=1, and the mean term is retained. Historical ES marginal risk is the shared exact-tail-weight average of negative asset returns; boundary ties give a subgradient. Components sum to the un-clipped signed total. Negative hedges remain negative; percentages are fractions of total risk and are unavailable for nonpositive/near-zero totals. At zero portfolio volatility with risky individual assets, the gradient is undefined rather than fabricated.

## Practical sizing convention

Five candidate targets were recorded before outcomes, with two labelled unconstrained references. No cash is introduced, constraints are not relaxed, and no candidate is automatically selected. Expected-return proxy is 252 times the same-window arithmetic sample mean, not a forward expected return, geometric/net/real spending result or promise. Risk is Historical 99% one-day pre-cost VaR/ES. The return-risk ratio is explicitly annual arithmetic return-proxy sacrifice divided by daily ES reduction; it is a scale comparison mixing stated horizons, not a Sharpe ratio. Ratios are N/A when risk does not fall. Null human risk limits remain PENDING, not automatically met.

## Stress conventions and rationale

Historical replay starts at wealth 1, includes the first stored close-to-close return, compounds each asset separately and lets holdings drift. No daily rebalancing or transaction costs are imposed. Drawdown includes initial wealth; asset P&L sums to total P&L. Exact NYSE-session coverage is required. Signed USD loss is negative for a scenario gain. These are ex-post scenario replays and do not imply those weights were held during the crisis.

GFC represents joint equity/liquidity stress; COVID represents a rapid liquidity shock; 2022 represents equity/duration repricing. Dates are configured team assumptions. The provisional hypothetical vector combines equity and duration losses with gold/energy gains: SPY/EFA/EEM -25%, AGG -12%, GLD +10%, XLE +20%, XLK -30%. Energy and technology differ deliberately from broad equities. Joint signs/magnitudes are assumptions, not a fitted joint distribution. Duration/probability is unspecified. Daily development extrema provide scale context only and do not calibrate a multi-day repricing scenario. A deterministic scenario loss is not ES.

## Computed results

### recent_development_1260d: 2011-12-29 to 2016-12-30, N=1260

Baseline 99% Euler allocations (component units: bps of NAV; percentages can be negative or exceed 100% for hedges):

| Method | Ticker | Weight (%) | Marginal (fraction) | Component (bps) | Share (%) | Total (bps) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| normal_var | SPY | 33.9337 | 0.01133897 | 38.4773 | 42.7226 | 90.0632 | ok |
| normal_var | EFA | 0.0000 | 0.01367306 | 0.0000 | 0.0000 | 90.0632 | ok |
| normal_var | EEM | 0.0000 | 0.01748096 | 0.0000 | 0.0000 | 90.0632 | ok |
| normal_var | AGG | 40.0000 | 0.00115009 | 4.6004 | 5.1079 | 90.0632 | ok |
| normal_var | GLD | 26.0663 | 0.01802539 | 46.9855 | 52.1695 | 90.0632 | ok |
| normal_var | XLE | 0.0000 | 0.01629712 | 0.0000 | 0.0000 | 90.0632 | ok |
| normal_var | XLK | 0.0000 | 0.01159543 | 0.0000 | 0.0000 | 90.0632 | ok |
| normal_es | SPY | 33.9337 | 0.01307467 | 44.3672 | 42.8913 | 103.4412 | ok |
| normal_es | EFA | 0.0000 | 0.01571015 | 0.0000 | 0.0000 | 103.4412 | ok |
| normal_es | EEM | 0.0000 | 0.02004254 | 0.0000 | 0.0000 | 103.4412 | ok |
| normal_es | AGG | 40.0000 | 0.00133004 | 5.3201 | 5.1432 | 103.4412 | ok |
| normal_es | GLD | 26.0663 | 0.02062197 | 53.7538 | 51.9656 | 103.4412 | ok |
| normal_es | XLE | 0.0000 | 0.01870721 | 0.0000 | 0.0000 | 103.4412 | ok |
| normal_es | XLK | 0.0000 | 0.01337581 | 0.0000 | 0.0000 | 103.4412 | ok |
| historical_es | SPY | 33.9337 | 0.01763278 | 59.8346 | 39.8424 | 150.1782 | ok |
| historical_es | EFA | 0.0000 | 0.01792856 | 0.0000 | 0.0000 | 150.1782 | ok |
| historical_es | EEM | 0.0000 | 0.02319995 | 0.0000 | 0.0000 | 150.1782 | ok |
| historical_es | AGG | 40.0000 | 0.00160242 | 6.4097 | 4.2680 | 150.1782 | ok |
| historical_es | GLD | 26.0663 | 0.03220022 | 83.9340 | 55.8896 | 150.1782 | ok |
| historical_es | XLE | 0.0000 | 0.02671195 | 0.0000 | 0.0000 | 150.1782 | ok |
| historical_es | XLK | 0.0000 | 0.01616625 | 0.0000 | 0.0000 | 150.1782 | ok |

Candidate table; positive risk reduction is relative to the baseline:

| Candidate | Constraint feasible | HS VaR99 (%) | HS ES99 (%) | Annual return proxy (%) | ES reduction (bps) | Annual proxy sacrifice (pp) | Risk-limit status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_min_variance | True | 1.0414 | 1.5018 | 4.4801 | 0.0000 | 0.0000 | not_supplied_pending_human_input |
| defensive_20_40_40 | True | 1.2377 | 1.8123 | 1.7542 | -31.0528 | 2.7259 | not_supplied_pending_human_input |
| equity_cap_35_40_25 | True | 1.0368 | 1.4865 | 4.6887 | 1.5316 | -0.2086 | not_supplied_pending_human_input |
| balanced_30_35_35 | True | 1.1919 | 1.7347 | 3.3516 | -23.2881 | 1.1285 | not_supplied_pending_human_input |
| gold_tilt_25_35_40 | True | 1.2857 | 1.8497 | 2.3735 | -34.7902 | 2.1067 | not_supplied_pending_human_input |
| equal_weight_reference | False | 1.6679 | 2.3479 | 6.3143 | -84.6129 | -1.8342 | not_supplied_pending_human_input |
| benchmark_60_40_reference | False | 1.2699 | 1.6150 | 9.5796 | -11.3204 | -5.0995 | not_supplied_pending_human_input |

### full_development_3020d: 2005-01-04 to 2016-12-30, N=3020

Baseline 99% Euler allocations (component units: bps of NAV; percentages can be negative or exceed 100% for hedges):

| Method | Ticker | Weight (%) | Marginal (fraction) | Component (bps) | Share (%) | Total (bps) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| normal_var | SPY | 33.9337 | 0.02117788 | 71.8644 | 57.4710 | 125.0447 | ok |
| normal_var | EFA | 0.0000 | 0.02604652 | 0.0000 | 0.0000 | 125.0447 | ok |
| normal_var | EEM | 0.0000 | 0.03409138 | 0.0000 | 0.0000 | 125.0447 | ok |
| normal_var | AGG | 40.0000 | 0.00144637 | 5.7855 | 4.6267 | 125.0447 | ok |
| normal_var | GLD | 26.0663 | 0.01818240 | 47.3948 | 37.9023 | 125.0447 | ok |
| normal_var | XLE | 0.0000 | 0.03050943 | 0.0000 | 0.0000 | 125.0447 | ok |
| normal_var | XLK | 0.0000 | 0.01935631 | 0.0000 | 0.0000 | 125.0447 | ok |
| normal_es | SPY | 33.9337 | 0.02431535 | 82.5110 | 57.4278 | 143.6778 | ok |
| normal_es | EFA | 0.0000 | 0.02987701 | 0.0000 | 0.0000 | 143.6778 | ok |
| normal_es | EEM | 0.0000 | 0.03911938 | 0.0000 | 0.0000 | 143.6778 | ok |
| normal_es | AGG | 40.0000 | 0.00168041 | 6.7217 | 4.6783 | 143.6778 | ok |
| normal_es | GLD | 26.0663 | 0.02088720 | 54.4452 | 37.8939 | 143.6778 | ok |
| normal_es | XLE | 0.0000 | 0.03502636 | 0.0000 | 0.0000 | 143.6778 | ok |
| normal_es | XLK | 0.0000 | 0.02223625 | 0.0000 | 0.0000 | 143.6778 | ok |
| historical_es | SPY | 33.9337 | 0.04231770 | 143.5997 | 66.4970 | 215.9490 | ok |
| historical_es | EFA | 0.0000 | 0.04880317 | 0.0000 | 0.0000 | 215.9490 | ok |
| historical_es | EEM | 0.0000 | 0.06478077 | 0.0000 | 0.0000 | 215.9490 | ok |
| historical_es | AGG | 40.0000 | 0.00071325 | 2.8530 | 1.3212 | 215.9490 | ok |
| historical_es | GLD | 26.0663 | 0.02666138 | 69.4963 | 32.1818 | 215.9490 | ok |
| historical_es | XLE | 0.0000 | 0.06474514 | 0.0000 | 0.0000 | 215.9490 | ok |
| historical_es | XLK | 0.0000 | 0.03616148 | 0.0000 | 0.0000 | 215.9490 | ok |

Candidate table; positive risk reduction is relative to the baseline:

| Candidate | Constraint feasible | HS VaR99 (%) | HS ES99 (%) | Annual return proxy (%) | ES reduction (bps) | Annual proxy sacrifice (pp) | Risk-limit status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_min_variance | True | 1.4824 | 2.1595 | 7.2421 | 0.0000 | 0.0000 | not_supplied_pending_human_input |
| defensive_20_40_40 | True | 1.5497 | 2.2388 | 7.3304 | -7.9358 | -0.0883 | not_supplied_pending_human_input |
| equity_cap_35_40_25 | True | 1.5078 | 2.1766 | 7.2354 | -1.7077 | 0.0068 | not_supplied_pending_human_input |
| balanced_30_35_35 | True | 1.6021 | 2.2975 | 7.5517 | -13.8059 | -0.3096 | not_supplied_pending_human_input |
| gold_tilt_25_35_40 | True | 1.6373 | 2.3457 | 7.5834 | -18.6220 | -0.3413 | not_supplied_pending_human_input |
| equal_weight_reference | False | 3.1316 | 4.4105 | 8.9950 | -225.0961 | -1.7528 | not_supplied_pending_human_input |
| benchmark_60_40_reference | False | 2.2845 | 3.1735 | 7.0769 | -101.4007 | 0.1652 | not_supplied_pending_human_input |

## Historical and hypothetical comparison

| Portfolio | Scenario | Start | End | Total return (%) | Max drawdown (%) | Worst day/step (%) | USD loss | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| terminal_development_min_variance | gfc_2007_2009 | 2007-10-09 | 2009-03-09 | -9.2350 | -20.7586 | -6.0784 | 923504.55 | ok |
| terminal_development_min_variance | covid_2020 | 2020-02-19 | 2020-03-23 | -12.6783 | -14.6021 | -5.6277 | 1267826.02 | ok |
| terminal_development_min_variance | rate_shock_2022 | 2022-01-03 | 2022-10-14 | -17.1045 | -17.1045 | -2.6017 | 1710453.23 | ok |
| terminal_development_min_variance | hypothetical_stagflation_repricing | one step | unspecified horizon | -10.6768 | -10.6768 | -10.6768 | 1067680.25 | warning |
| benchmark_60_40_reference | gfc_2007_2009 | 2007-10-09 | 2009-03-09 | -29.9942 | -30.3292 | -4.7510 | 2999420.33 | ok |
| benchmark_60_40_reference | covid_2020 | 2020-02-19 | 2020-03-23 | -20.5882 | -20.8071 | -7.0564 | 2058821.91 | ok |
| benchmark_60_40_reference | rate_shock_2022 | 2022-01-03 | 2022-10-14 | -20.5751 | -20.6337 | -2.8904 | 2057506.37 | ok |
| benchmark_60_40_reference | hypothetical_stagflation_repricing | one step | unspecified horizon | -19.8000 | -19.8000 | -19.8000 | 1980000.00 | warning |

For the hypothetical row, max drawdown means only initial-to-final one-step decline and worst day/step is the stipulated step; no within-step path or daily horizon is inferred.

## Decision and monitoring evidence

The default equity cap forces at least 65% AGG+GLD and, with 40% per fund, at least 25% in each. This narrow feasible set does not prove capital safety. Income/spending, inflation, fee and real-growth choices remain pending; do not infer ACCEPT/ADJUST/REJECT from this sizing table alone. Candidate comparisons use the existing windows without selecting friendlier constraints or tuning on evaluation outcomes.

| Metric | Threshold | Status | Action |
| --- | --- | --- | --- |
| daily_HS_ES99 | PENDING | PENDING_HUMAN_RISK_LIMIT | Review approved risk budget and feasible redistribution after human-defined threshold breach; no automatic relaxation. |
| drawdown_and_crisis_loss | PENDING | PENDING_HUMAN_LOSS_TOLERANCE | Review liquidity/spending plan and allowed allocation changes against approved horizon-specific loss tolerance. |
| pre_return_holdings_drift | configured provisional target caps; continuous enforcement policy PENDING | PROPOSED_MONITOR_ONLY | Flag drift beyond target caps; seek approved rebalance policy, do not silently clip daily weights. |
| missing_sessions_or_forecast_failures | any | SOFTWARE_QUALITY_TRIGGER | Mark dependent analytics unavailable and investigate before relying on the output. |

Monitoring policy is proposed evidence for the team. Missing human thresholds must be completed before a final approved mandate claim; software data-quality triggers are separate from economic risk limits.

## Hand-check and limitations

With SPY/AGG 50/50 and daily returns (-20%,+10%), then (+10%,-10%), wealth is 0.95 then 0.935: asset-wise compounding gives 0.5*0.8*1.1+0.5*1.1*0.9. Resetting weights daily would instead give 0.95. This catches accidental constant-weight rebalancing. One-step shocks SPY -25%, AGG +10% give portfolio -7.5%, USD loss 7.5 on NAV100, with signed component P&L adding exactly.

Normal moments/ES and historical tails are conditional on sample/exposure conventions. Step 6 dependence and Step 7 EVT uncertainty remain relevant. Historical stress has no calibrated future probability, trading/market impact model or guarantee. Target feasibility is distinct from continuously enforced holdings caps. The final app/report must ultimately share a frozen pipeline result bundle, not compute alternative values independently.

Step 8 only; Step 9 integration, final selection/evaluation protocol, human decisions, app and submission work remain.
