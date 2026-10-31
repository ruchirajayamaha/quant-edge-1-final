# Presentation and LaTeX closure

Recorded 1 November 2026 by Claude Code (Claude Opus 5.5). This is AI-assisted numerical, editorial
and technical verification. **It is not independent human validation, which remains PENDING.**

## Decision state

Conditional ADJUST is unchanged. It is a team proposal under a competition brief. No real committee
has approved it, and the team has yet to evaluate and own it.

## What was checked

| Check | Result | Evidence |
|---|---|---|
| Baseline of analytics, config, data, final results, proposal and prior audit evidence | 768 files, 0 changed, 0 added | `PRESENTATION_BASELINE.json`, `scripts/freeze_presentation_baseline.py verify` |
| Independent recomputation from frozen inputs by a different route | 10 of 10 within stated tolerance; largest absolute difference 3.1e-09 on a USD figure | `verification.json` |
| Generated numeric macros against stored full-precision values | 142 checked, 0 failures | `verification.json` |
| Prompt regression checkpoints | All pass | `verification.json` |
| Key cells of 5 generated tables against the reference | 0 missing | `verification.json` |
| Compiled PDFs | Page limits met; dvipdfmx producer; Libertinus fonts; headlines found | `verification.json` |
| Full test suite | 144 passed; `pip check` clean | Run after the final code and report edits |
| App sweep: 6 views x 3 portfolios x 3 confidence levels x 5 risk methods, plus recent/full, rolling model, short and empty ranges | 287 runs, 0 exceptions or errors; all expected states seen | `app_exercise.json`, `exercise_app.py` |
| Controls | A 5 bp macro change and a changed table cell were both detected. The legacy script refuses to run without its flag | `app_exercise.json`, `tests/test_d_presentation.py` |
| Cloud entrypoint | `streamlit_app.py` runs the redesigned app under AppTest | `tests/test_d_presentation.py` |

The sweep first reported two states as false. That was a bug in the sweep's text helper, which skipped
info boxes. It was fixed and the sweep was rerun, and the recorded file is the rerun.

## Rendering review

All 16 final pages were rendered with pypdfium2 and read as images: memo 11, tear sheet 1,
recommendation 1, review pack 3. Reading them changed the documents:

- Prose: an overstated lede, an unsupported reference to 2022 and an overstated noise claim.
- Layout: review-form overflow, tear-sheet footer spacing, table header width.
- Figures: budget lines crossing data labels, a period label on a gridline, and a 6.7% label that sat
  beside the 6.75% hurdle although the value is 6.65%.

Memo page 10 ends with the References heading and one entry, and the rest follow on page 11. That is
natural pagination and was left as it is.

Dashboard views were also read in the built-in browser: all six at 1360 x 900 and the Decision view at
375 x 812, with no console errors. That pass fixed truncated metric labels, faint captions and a table
overflow at phone width.

## Limitations of this verification

- Macro and PDF headline checks are comprehensive for numbers carried by macros. Table checks cover
  key cells of 5 tables. App headlines are tested, but not every cell in the app was compared.
- Every number in the sources is generated, but the prose around them is AI-written and judgement-based.
- Citations were checked by search. The Kupiec journal pages were confirmed only from secondary
  sources, and Markowitz (1952) and Sharpe (1964) were not returned by search and rest on the
  standard bibliographic record.
- The build was run only with MiKTeX 25.12 on Windows. Another TeX distribution may paginate differently.
- The legacy ReportLab path was guarded and tested for refusal, and was not rerun.
- The cloud entrypoint was tested locally only. No Linux build was run and nothing was deployed, so no
  hosted URL exists or is claimed.
- The underlying research limitations stand: the candidate is above its proposed tail budgets, income
  does not cover spending, holdings drift past target caps, and the full-history model rejects.

## Still pending, and only a person can do it

- Recomputing and recording the worksheet in `handoff/human_review_pack/`.
- Answering the understanding questions, then completing and signing the review form.
- Evaluating and owning the recommendation, including disagreeing with it.
- Confirming team details, the deadline and the organiser's submission route.
- Practising the defence, and deciding whether to deploy a hosted app.

No message or upload was sent to competition organisers.
