# Worked calculation worksheet

Prepared by AI as a review aid. It is not a completed review, and using it does not validate anything until a named person does the work and records their own findings.

Work each item yourself with a calculator, a spreadsheet or code you wrote. Check inputs against the
named original file, not just this sheet. Leave the answer key closed until you have an answer.

## A. One-day portfolio return, 29 October 2026

Original files: `results/final/weights_before_min_variance.csv` and the active `simple_returns.parquet`.
Task: multiply each weight by its return and add them up.

| ETF | Pre-return weight | Asset simple return |
|---|---:|---:|
| SPY | 0.2072522004 | -0.0038197255 |
| EFA | 0.0000000000 | 0.0064621737 |
| EEM | 0.0000000000 | -0.0125944463 |
| AGG | 0.3988026610 | 0.0027114625 |
| GLD | 0.2401612921 | -0.0132258904 |
| XLE | 0.1537838464 | 0.0037984244 |
| XLK | 0.0000000000 | -0.0118324320 |

Your answer: ____________________

## B. Evaluation maximum drawdown

Original file: `results/final/daily_performance.csv`, `min_variance`, from 4 January 2021.
Task: compound `net_return` from wealth 1 and include that starting value in the running peak. Find the
deepest fall from peak. Then confirm your peak and trough dates.

Your answer: ____________________  Peak date: ____________  Trough date: ____________

## C. Recent Normal VaR at 99%

Inputs: the last 1,260 rows of returns and `current_weights.min_variance` in `results/final/reference.json`.
These target weights differ from the historical holdings in item A.

| Input | Value |
|---|---:|
| Sample mean loss | -0.00041620720369139 |
| Sample standard deviation, ddof = 1 | 0.00573420629040984 |
| Standard Normal 99% quantile | 2.3263478740408408 |

Task: mean loss + quantile × standard deviation.

Your answer: ____________________

## D. Recent Historical ES at 99%

The worst 1% of 1,260 sessions is 12.6 sessions of probability mass. It is not 13 equally weighted days.
The worst 13 losses, largest first:

```text
0.030862960694864747
0.028527213355473074
0.024811953728094204
0.020923104255072020
0.020264968671476060
0.019071441706077743
0.019039837128778044
0.018237884073075833
0.018052241272015521
0.016010965832909375
0.015517799357651846
0.015435410391321087
0.015394981955742935
```

Task: (sum of the first 12 + 0.6 × the 13th) ÷ 12.6.

Your answer: ____________________

## E. GFC endpoint return at the current target

Dates: 9 October 2007 to 9 March 2009, buy and hold. Task: multiply each target weight by its cumulative
return and add them up. Then give the USD result on $10,000,000.

| ETF | Current target | Cumulative return |
|---|---:|---:|
| SPY | 0.2039227295 | -0.5476743002 |
| EFA | 0.0000000000 | -0.5978555404 |
| EEM | 0.0000000000 | -0.5850587914 |
| AGG | 0.4000000000 | 0.0716563681 |
| GLD | 0.2500000000 | 0.2487246825 |
| XLE | 0.1460772705 | -0.4686534254 |
| XLK | 0.0000000000 | -0.5103941499 |

Your answer: ____________________  USD: ____________________

## F. Return hurdle

Convention: 1 + R − spending − additional fee = (1 + inflation) × (1 + real growth).
Inputs: spending 4%, fee 0.25%, inflation 2.5%, real growth 0%.

Your answer: ____________________
