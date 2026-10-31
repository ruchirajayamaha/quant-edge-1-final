# Verified Step 5 (C1) development risk figures and tables

- **Scope:** `development_only_through_2016_12_30` (development sample through `2016-12-30`)
- **Active market dataset:** `qe1_20050101_20261030_r3_6c4633a7ba`
- **Configuration SHA-256:** `587ddbe363589fb6956c23c5fe8b2b544bac81d9224a0b4bb59f60f5fbc0a017`
- **Mandate scale:** `USD 10,000,000.00`
- **Monte Carlo authority:** `seed = 202601`, `M = 25,000` draws

All CSV tables and 300-dpi PNG / vector SVG figures in this directory are generated directly from `results/step5_development_c1_risk_tables.json` without implementing a second risk engine and without overwriting `results/development_preview/` (Step 4 preview). No post-2016 selection or evaluation strategy outcomes are computed or displayed.

Reproduce from the repository root using the verified Python 3.11 `.venv`:

```powershell
.\.venv\Scripts\python.exe scripts\record_step5_c1_results.py
.\.venv\Scripts\python.exe scripts\export_step5_c1_preview.py
```
