# Step 6 technical review — 2026-10-31

**Core Step 6 implementation and development results are cleared for progression to Step 7.** This is not approval of model adequacy or a final investment recommendation.

- Independently reran the connected suite: **96 passed in 18.74s**; `pip check` reports no broken requirements.
- Reran the independent scalar/array verifier: **10,064 daily rows** checked, 4 coverage summaries, all 53 market/context hashes and 50 protected files unchanged. Largest VaR/ES differences are 1.22e-17 / 3.13e-17; LR/p-value differences are below 1.14e-13 / 3.78e-15.
- Strict authoritative JSON parses. All **13 preview artifact hashes** and recorded source hashes match. Both actual PNG figures were visually inspected. Files and plots in the live preview, not filenames/hashes quoted in chat, are authoritative.
- Actual production seed policy reuses the same base seed at each origin; the pasted completion report's `seed + fold_idx` claim is stale. The actual `_backtest_diagnostics.py` exports `coverage_tests` and `basel_traffic_light`; several helper names and parquet/subdirectory paths claimed in the pasted report do not exist in the current checkout. These are reporting discrepancies, not discrepancies in the verified numerical tables. Use `results/step6_backtest_preview/index.html` and `manifest.json` for deliverable paths. Current plots contain two panels, rather than the three-panel plot claimed in chat.

## Interpretation to carry into the final report

There are 2,516 eligible sessions per model/confidence, 2007-01-05 through 2016-12-30, and no skipped targets. Historical 95/99 exceptions are 127/32; Normal 95/99 exceptions are 127/53. At 5%, independence is rejected in all four comparisons. Historical 99% UC is not rejected (p=0.1885), but conditional coverage is rejected (p=0.0113); sparse tail transition counts limit asymptotic interpretation. Normal 99% UC is rejected (p=1.18e-6), consistent with too many tail losses in this development sample.

The endpoint-fixed Basel block is 2016-01-06 through 2016-12-30: Historical has 2 exceptions and Normal has 3, both green. This shorter educational diagnostic does not override the full-sample coverage/clustering findings. Status `ok` in a summary row means a statistic was computed, not that the model passed a statistical hypothesis test. ES forecasts are saved, but these exception tests validate VaR, not ES calibration.

No retuning is justified merely to manufacture favourable coverage. Proceed with the planned EVT tail analysis, disclose limitations and preserve the inherited primary backtest protocol. Human validation and final protocol/mandate approval remain pending. No selection/evaluation strategy outcomes or Step 7 calculations were performed by this review.
