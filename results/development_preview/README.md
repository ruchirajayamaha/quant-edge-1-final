# Verified development figures and tables

Active development period: 2007-01-05 to 2016-12-30; 2,516 return sessions.

Open index.html to browse all four figures and the KPI comparison. PNG files are 300 dpi; SVG files are vector exports. CSV and JSON files contain actual computed values, with fractions/annual fractions explicitly labelled. Multiply fractions by 100 for percent display. Unavailable metrics are not zero.

These outputs cover completed Steps 1-4 under provisional assumptions. They are development previews, not final evaluation results or a signed recommendation. Equal-weight and 60/40 are unconstrained references. Caps apply at rebalance targets; between-trade breaches are reported in 08_constraint_scope.csv.

VaR/ES, validation, EVT and stress figures will be generated after the respective steps pass review. The final report/app must use one frozen result bundle.

Reproduce from the repository root using the verified Python3.11 .venv:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-deps --target tmp\figure_export_deps -r results\development_preview\rendering-requirements.txt
.\.venv\Scripts\python.exe scripts\export_verified_development_preview.py
```

Rendering dependencies stay in the ignored tmp directory; the application requirements are unchanged. manifest.json records source and artifact hashes.
