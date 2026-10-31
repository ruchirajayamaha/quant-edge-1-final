# Links and run instructions

## Links

- Repository: https://github.com/ruchirajayamaha/quant-edge-1-final
- This folder: https://github.com/ruchirajayamaha/quant-edge-1-final/tree/main/FINAL_SUBMISSION
- Public app: not yet deployed. Status and steps are in `DEPLOY_STREAMLIT.md` in the repository.

## Set up once

Use Python 3.11. Setup installs packages. After that, the app needs no download, API key or paid service.

Windows PowerShell:

```powershell
git clone https://github.com/ruchirajayamaha/quant-edge-1-final.git
cd quant-edge-1-final
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

macOS or Linux:

```bash
git clone https://github.com/ruchirajayamaha/quant-edge-1-final.git
cd quant-edge-1-final
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps -e .
```

The install was tested on Windows with Python 3.11.16. macOS and Linux have not been run.

## Run it locally

Windows:

```powershell
.\.venv\Scripts\python.exe scripts/launch.py
```

macOS or Linux:

```bash
.venv/bin/python scripts/launch.py
```

Open the local address Streamlit prints, normally http://localhost:8501. That address works only on your
own computer. It is not a public link.

## What to try

Use the sidebar to pick a view, portfolio, confidence level (90, 95 or 99%), risk method and date range.

- **Tail risk:** choose 90% to see pure POT shown as unavailable, then switch between recent and full history.
- **Backtesting:** compare Historical and Normal. Choose October 2026 only to see the Basel result unavailable.
- **Risk budget & stress:** these use today's prospective target. They are not the historical strategy record.

## Check and rebuild

```bash
python -m pytest -q
```

Reports need a TeX distribution and `requirements-render.txt`, which the app does not need:

```bash
python scripts/build_reports.py
```

Then refresh this folder, its checksums and the ZIP:

```bash
python scripts/package_submission.py
```

Report sources and toolchain notes are in `latex_source/README.md`.

## Verify this package

On macOS or Linux, from inside this folder:

```bash
sha256sum -c SHA256SUMS.txt
```
