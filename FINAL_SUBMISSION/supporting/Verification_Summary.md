# Verification summary

AI-assisted technical verification by Claude Code (Claude Opus 5.5), 1 November 2026. **This is not independent
human validation, which remains PENDING.** Result bundle `1c7bd6007fe22b014b25`, dataset
`qe1_20050101_20261030_r3_6c4633a7ba`, evidence frozen at 30 October 2026.

## Results

| Check | Method | Result |
|---|---|---|
| Full test suite | `python -m pytest -q` | 147 passed; `pip check` clean |
| Clean clone | New Python 3.11 environment from `requirements.txt`, no editable install, no TeX or Matplotlib | 146 passed, 1 skipped (that test needs optional `pypdf`) |
| Independent recomputation | 11 checks from frozen inputs in plain Python, not through the production helpers | 11 of 11 within tolerance; largest difference 3.1e-09 on a USD amount |
| Report numbers | Each of 148 generated macros compared with its stored full-precision value | 0 failures; all regression checkpoints hold |
| Report tables | Key cells of 5 generated tables compared with the reference | 0 missing |
| App sweep | 6 views x 3 portfolios x 3 confidence levels x 5 risk methods, plus samples, rolling models, short and empty ranges | 287 runs, 0 exceptions or errors; unavailable states shown as expected |
| Controls | Deliberately changed a macro by 5 bp and altered a table cell in scratch copies | Both caught |
| Source and result invariance | SHA-256 against the frozen baseline | 768 files: analytics 18, config 3, data 64, results 21, proposal 1, prior audit evidence 661. 0 changed, 0 added |
| Checksums and ZIP | `SHA256SUMS.txt` and archive contents compared file by file | All match |
| LaTeX source | The packaged `latex_source/` compiled on its own | Memo 11 pages, tear sheet 1, recommendation 1 |

Headline values are unchanged: evaluation CAGR 7.63%, development CAGR 6.65% against a 6.75% hurdle, recent 99%
VaR $153,950 and ES $203,169, full-history ES $250,185, GFC replay endpoint -8.93% and drawdown -23.87%.

The discrepancy found was a defect in the checking script, not the results: two sweep states first read false
because the script skipped info boxes. It was fixed and rerun.

## PDFs and visual review

| Document | Pages | Requirement |
|---|---|---|
| `01_Investment_Memo.pdf` | 11, including references | 7 to 15 |
| `02_Executive_Tear_Sheet.pdf` | 1 | Exactly 1 |
| `supporting/Recommendation.pdf` | 1 | One page, section 8.6 |

All were compiled with MiKTeX-XeTeX 4.16 (MiKTeX 25.12), rendered with pypdfium2, and read as page images,
including the 3-page review pack. Fixes from that reading covered overstated wording, chart labels crossed by
budget lines, a 6.7% label beside the 6.75% hurdle, and a form overflow.

Re-reading the brief added two things to the memo: a diversification paragraph and the calendar statement. The
diversification figure compares the portfolio's 99% ES of 2.03% with 3.30% for the funds held separately at
target weights. That is arithmetic on frozen inputs. No model, parameter or result changed.

## Public app

**Live at https://quant-edge-1-final.streamlit.app/** on Streamlit Community Cloud, from `main` with `streamlit_app.py`. App code revision
`5304403`; later commits change documents and tests only. Bundle `1c7bd6007fe22b014b25`. The build log shows
Python 3.11.18 and all pinned packages installed with no errors, and the frozen results passed their hash
check on Linux.

Tested in a browser that was not signed in to Streamlit, after the interface rendered:

| Check | Result |
|---|---|
| Access | No login screen; the app rendered with viewer controls only |
| Six views | All opened with charts and tables, 0 exceptions, 0 error messages |
| Headlines | 7.63%, $203,169, 2.19%, recent VaR 1.54% and ES 2.03%, full-history ES 2.50%, 18 of 1,464 exceptions |
| Confidence | 99 and 90 checked on the final code; 90% VaR 0.65%, ES 1.03% |
| Risk method | Pure POT shows Unavailable at 90% with its explanation, and 1.68% VaR at 99% on full history |
| Sample window | Recent 1,260 and full 5,491 sessions |
| Portfolio | 60/40 shows its reference notice and its own results |
| Rolling model | Historical 18 and Normal 27 exceptions; final-250 Basel green and yellow |
| Short range | October 2026 only: 22 sessions and Basel unavailable, with no exception |
| PDF downloads | Memo, tear sheet and recommendation served byte-identical to the packaged files (SHA-256 and size) |
| Widths | Desktop 1360 and phone 375, with no horizontal page scroll |

Portfolio and pure POT at 99% were last clicked before two display-only commits. Those commits changed styling
and the file watcher, not calculations. 95% was covered by the automated sweep, not clicked on the live app.

The logs showed one real error. When an update arrived with a session open, Cloud logged an `ImportError` and
`AttributeError` as `quantedge` was reloaded. The app kept working for new sessions. The file watcher was turned
off, and the next update with sessions open logged no traceback. As a result, new Python code needs a manual
reboot. The log's remaining warning is that `requirements.txt` and `pyproject.toml` both exist, and it used
`requirements.txt` as intended.

Community Cloud may put an idle app to sleep, so a visitor can see a wake-up button first. Availability depends
on that free service, and the local launch is the fallback.

## Limits and unresolved items

- **Human validation under brief section 8.7 is open.** It is a mandatory requirement, so the package is
  technically complete but not fully compliant.
- Archived Federal Reserve H.15 pages support release dates and are disclosed, but are not named in section 9.1.
  The team should confirm that is acceptable.
- Macro checks are comprehensive; table checks cover key cells; not every app cell was compared.
- Citations were checked by search. Kupiec's journal pages came from secondary sources, and Markowitz (1952) and
  Sharpe (1964) rest on the standard bibliographic record.
- The research limits stand: the candidate is above its proposed tail budgets, cash income does not cover
  spending, holdings drift past target caps, and the full-history 99% Historical model is rejected.
