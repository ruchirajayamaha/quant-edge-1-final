# Human review: follow this guide and record what you actually checked

Use the printable pack in `handoff/human_review_pack/` or
`submission/human_review/human_review_pack.pdf` for the worksheet and form.

This is an AI-prepared guide, not a completed human validation record. Reading the
expected answers or rerunning the same AI script does not, by itself, independently
validate the work. Check the original inputs, calculate using your own calculator,
spreadsheet or independently written method, and explain the interpretation.
Ask a teammate who understands the calculation to review material you cannot yet defend.

## 1. Open the app

In PowerShell:

```powershell
cd "C:\Users\ruchira\Desktop\qunt"
.\.venv\Scripts\python.exe scripts/launch.py
```

Open the local URL printed by Streamlit. That is a local server, not public hosting.

Visit Decision, Performance, Tail risk, Backtesting, Risk budget & stress, and
Assumptions & Limitations. Write down any error, inconsistent label or unexplained number.

Try these specific controls:

- Performance: select4 Jan2021-30 Oct2026. Primary CAGR should show about7.63%,
  annual volatility8.80%, maximum drawdown-16.78%. These are different quantities.
- Tail risk: select the primary portfolio,99%, recent1,260 sessions. Historical
  VaR is about1.54%, ES2.03%; Normal and MC Normal are their own estimates.
- Switch to90% and pure POT. It should be unavailable below the tail threshold,
  with an explanation. The separately labelled hybrid is a different construction.
- Backtesting: compare Historical and Normal. The latest250-session99% results
  are4 green versus9 yellow. Explain why green does not mean guaranteed safety.
- Select1-30 Oct2026 for Backtesting. Its99% Basel result should be unavailable
  because that selected range contains fewer than250 sessions.
- Switch to a reference portfolio. References need not satisfy the candidate caps.

## 2. Read and challenge the decision

Read submission/recommendation.pdf, then the memo. In your own words, answer:

1. Why is the proposed decision ADJUST rather than an unconditional ACCEPT?
2. Why are historical growth and cash distribution income different?
3. What would you do if the2% daily ES99 review budget were exceeded?
4. What risks remain even if one recent backtest does not reject the model?

Review the proposed10-year horizon,4% spending,2.5% inflation and0.25% additional
fee. These are proposed research assumptions, not facts supplied by the client.
Decide whether your team can justify them. Disagreement is a valid finding to
record; it is not a failed human review to identify something that needs changing.

Under the stated beginning-NAV deduction convention, check the arithmetic:

`4.00% + 2.50% + 0.25% = 6.75% nominal planning hurdle`.

Explain why this is not a promised future return and why fund expenses are not
charged again. Do not approve assumptions merely because the AI chose them.

## 3. Independently check representative calculations

All numbers below are fractions unless labelled otherwise. Work the arithmetic
before looking at the expected result. Use the original CSV/snapshot and its date
labels to check the input, not just this guide's transcription.

### A. One-day primary portfolio return:29 October2026

Original holdings: results/final/weights_before_min_variance.csv, row2026-10-29.
Original asset returns: the active r3 simple_returns.parquet, row2026-10-29.
Reference result: results/final/daily_performance.csv, min_variance on that date.

| ETF | Pre-return weight | Asset simple return |
|---|---:|---:|
| SPY |0.2072522004|-0.0038197255|
| EFA | approximately0 |0.0064621737|
| EEM |0|-0.0125944463|
| AGG |0.3988026610|0.0027114625|
| GLD |0.2401612921|-0.0132258904|
| XLE |0.1537838464|0.0037984244|
| XLK | approximately0 |-0.0118324320|

Multiply each weight by its return and sum the products. That date has zero
rebalance cost, so gross and net agree. Tiny numerical residual weights are shown
as approximately0; rounding means a hand result need not match every last digit.

Expected: approximately `-0.002302518676 = -0.2302518676%`.
On a hypothetical USD10M beginning-day NAV that is approximately USD23,025.19 loss.
The actual compounded strategy NAV is a different dollar base.

### B. Evaluation drawdown

From the evaluation-period cumulative net returns, normalised to initial wealth1:

- Prior peak,12 Nov2021: `1.0216333523816952`.
- Trough,20 Oct2022: `0.8501742694342942`.

Compute `trough / prior_peak - 1`. Expected: approximately `-16.78283922%`.
Verify the peak is the highest prior wealth and no other evaluation date has a
deeper drawdown. Include initial wealth1 in the running-peak calculation.

### C. Recent Normal99% one-day VaR

Use the recent1,260 asset-return rows and prospective target weights in
results/final/reference.json -> current_weights. These weights differ from the
historical pre-return weights used in exampleA.

Compute each fixed-exposure loss as `-sum(weight * asset_return)`.

- Sample mean loss: `-0.00041620720369139403`.
- Sample standard deviation,ddof1: `0.005734206290409836`.
- Standard Normal99% quantile: `2.3263478740408408`.

Calculate `mean_loss + quantile * sample_standard_deviation`.
Expected: `0.012923551409315144`, approximately1.29235514%.
It is a fitted one-day quantile, not the maximum possible loss.

### D. Recent Historical99% ES

Use those same1,260 fixed-exposure losses. Sort descending. The worst1% has
probability mass equivalent to12.6 observations, not13 equally weighted observations.

Worst13 loss fractions, descending:

```text
0.030862960694864747
0.028527213355473077
0.024811953728094204
0.020923104255072017
0.020264968671476060
0.019071441706077740
0.019039837128778048
0.018237884073075833
0.018052241272015520
0.016010965832909375
0.015517799357651846
0.015435410391321087
0.015394981955742935
```

Calculate `(sum(first12) +0.6 * thirteenth) /12.6`.
Expected: `0.020316886479385343`, approximately2.03168865% or USD203,168.86
on USD10M NAV. Compare with reference.json and explain the proposed2% budget breach.
This is an estimated tail-average loss, not a claim that tomorrow loses that amount.

### E. GFC buy-and-hold stress terminal loss

Use the prospective target weights, not historical strategy weights. Compound
each asset's simple returns over9 Oct2007-9 Mar2009, then multiply its cumulative
return by its initial weight and sum.

| ETF | Current prospective target | Asset cumulative GFC return |
|---|---:|---:|
| SPY |0.2039227295|-0.5476743002|
| EFA |0|-0.5978555404|
| EEM | approximately0 |-0.5850587914|
| AGG |0.4000000000|0.0716563681|
| GLD |0.2500000000|0.2487246825|
| XLE |0.1460772705|-0.4686534254|
| XLK | approximately0 |-0.5103941499|

Expected terminal portfolio return: approximately-8.92991335%.
Expected terminal USD loss: approximately USD892,991.34 on initial USD10M.
This endpoint loss is different from the replay's approximately23.87% drawdown.
Explain why a path can recover before its endpoint and still have a deep trough.

## 4. Record the real review

Use submission/VALIDATION_CHECKLIST.md. For each item you actually reviewed, record:

```text
Reviewer: [your real name]
Date/time: [when you actually reviewed, Asia/Colombo]
Item / original file / dates checked:
Independent method: [calculator, spreadsheet, independently written calculation]
My calculated result:
Reference result:
Difference and explanation:
My interpretation / concern:
Status: REVIEWED / NEEDS CORRECTION / NOT YET REVIEWED
```

Do not copy another person's name or claim calculations you did not perform.
Mark only the completed checklist rows. Remaining rows stay pending.
Confirm actual team/member details and organiser deadline/upload route from their
instructions. No organiser submission or human sign-off has been performed by AI.

## 5. Final discussion

Use submission/DEFENCE_NOTES.md to question one another. If someone cannot explain
a material method, investigate it rather than memorising the expected answer.
The team should independently evaluate the recommendation and record agreement,
disagreement or required changes with reasons. Only then update the human-validation
record and AI disclosure to reflect what really happened.
