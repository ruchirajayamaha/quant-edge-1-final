# Step 6 development backtest preview

Scope: DEVELOPMENT OOS RESEARCH; NOT FINAL HOLDOUT VALIDATION; actual sample 2007-01-05 through 2016-12-30.

All risk forecasts, realized gross losses and coverage statistics come from persisted `backtest_results.json`. This rendering script does not fit a risk model or recompute the likelihood tests. `annual_exception_display_summary.csv` only aggregates persisted valid exception indicators for the annual figure. No post-2016 strategy outcome is displayed. Human validation and mandate/protocol approval remain pending.

Dataset: `qe1_20050101_20261030_r3_6c4633a7ba`

Config: `587ddbe363589fb6956c23c5fe8b2b544bac81d9224a0b4bb59f60f5fbc0a017`

Window: 500 prior sessions; portfolio: min_variance; one-day gross market loss, excluding costs.

Re-render from repository root after generating the authoritative Step 6 results:

```powershell
.\.venv\Scripts\python.exe scripts\export_step6_backtest_preview.py
```

Rendering uses the isolated `tmp/figure_export_deps` environment listed in `rendering-requirements.txt`, not extra app dependencies. Figures are 300-dpi PNG and vector SVG; HTML works offline. Files from earlier steps are preserved.
