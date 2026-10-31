# LaTeX report sources

These sources produce the submitted memo, tear sheet, recommendation and printable review pack.
`results/final/reference.json` and the frozen CSVs are the only numerical authority. Numbers in
the documents come from generated macros and tables, so do not type a result into the `.tex` files.

| Source | Output | Page rule |
|---|---|---|
| `main.tex` | `submission/investment_memo.pdf` | 7 to 15 pages |
| `tear_sheet.tex` | `submission/tear_sheet.pdf` | exactly 1 |
| `recommendation.tex` | `submission/recommendation.pdf` | exactly 1 |
| `human_review_pack.tex` | `submission/human_review/human_review_pack.pdf` | 2 to 5, outside the memo budget |

The first three are also copied to `output/pdf/`. Style is in `style/quantedge.sty`; references are
in `references.bib`. Everything under `generated/` is rebuilt from the frozen results, so edit the
generator and not the output.

## Toolchain used

- Engine: XeLaTeX, `MiKTeX-XeTeX 4.16 (MiKTeX 25.12)`, writing PDF through MiKTeX-dvipdfmx 20250413.
- Bibliography: BibTeX with `plainnat`, through `natbib`.
- Fonts: Libertinus Serif, Sans, Math and Mono (MiKTeX package `libertinus-fonts`), loaded by file.
- Python: `pip install -r requirements.txt -r requirements-render.txt`.

Run `xelatex --version` to record the exact version on another machine. Page breaks can shift with a
different TeX distribution, and the build fails if a page limit is broken.

## Build

Authoritative command, from the repository root:

```bash
python scripts/build_reports.py
```

It exports the figures, generates macros, tables and the review pack, runs XeLaTeX and BibTeX in
`tmp/report_build`, fails on an undefined reference, missing glyph, or overfull box above 2 pt, checks
page limits and only then publishes. Other forms:

```bash
python scripts/build_reports.py --no-publish
```

```bash
python scripts/build_reports.py --tex-only
```

The script finds TeX on `PATH`. Set `QE_TEX_BIN` to the folder holding `xelatex` if it is elsewhere.
On the development machine that folder is `D:\QuantEdgeTools\miktex\miktex\bin\x64`.

## After a build

```bash
python audit/presentation_review/verify_presentation.py
```

```bash
python scripts/render_pdf_pages.py submission/investment_memo.pdf tmp/pdf_review 1.6
```

Passing the build does not prove the pages read well. Look at every rendered page.

`scripts/build_submission_pdfs.py` is the superseded ReportLab builder. It refuses to run without
`--legacy-reportlab`, and it then writes only to `output/legacy_reportlab/`.

The dashboard needs none of this. It only serves the published PDFs.
