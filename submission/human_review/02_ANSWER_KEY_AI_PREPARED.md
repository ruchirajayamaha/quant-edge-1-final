# Expected answers: AI-PREPARED

**Reading this file is not performing a calculation.** These answers were computed by AI from the frozen
inputs. Use them only to compare with an answer you have already produced on your own.

| Item | Expected fraction | As percent | Compare with |
|---|---:|---:|---|
| A. One-day return, 29 Oct 2026 | -0.0023025187 | -0.230252% | results/final/daily_performance.csv |
| B. Evaluation maximum drawdown | -0.1678283922 | -16.782839% | period_kpis: max_drawdown |
| C. Recent Normal VaR 99% | 0.0129235514 | 1.292355% | risk_table: parametric_normal |
| D. Recent Historical ES 99% | 0.0203168865 | 2.031689% | risk_table: historical |
| E. GFC endpoint return, current target | -0.0892991335 | -8.929913% | stress_results: gfc_2007_2009 |
| F. Hurdle arithmetic | 0.0675 | 6.75% | submission/mandate_proposal.json |

Evaluation drawdown dates: peak 2021-11-12, trough 2022-10-20.
GFC endpoint on USD 10,000,000: $892,991.34 loss. This is not the replay's deeper
drawdown of about 23.87%, which comes from the daily path.

Small differences in the last digits are expected from rounding. Record any larger difference as a finding.
