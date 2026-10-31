# Commit map after the history rewrite

On 1 November 2026, at the owner's request, one planning PDF was removed from all Git history. The commit that had
deleted it became empty and was dropped, taking the history from 27 commits to 26. Every commit hash changed.

Files recorded before this date cite the old hashes, including `results/final/reference.json` and
`src/quantedge/final_engine.py`. Those files are hash-bound and were not edited. Use this table to read them. The
registered rule and proposed mandate were in `782ec20`, now `16181c0`.

## Evidence

- Method: `git filter-branch --index-filter` removing one path, with `--prune-empty`, in a separate clone.
- The rewritten tip had the same tree hash as the previous tip: `5e70420d29bf247b53e57ed85d617929fa5f03d1`.
- All 26 commits kept their author, author date and subject, and differed from their originals only by that PDF.
- The PDF's blob and any commit touching its path were absent from the rewritten history.

## Limits

This is AI-run technical evidence, not human validation. A rewritten commit's date is preserved metadata, so it
cannot by itself prove when the original commit was made. Earlier commits may stay reachable on GitHub by direct
link until GitHub removes them, and existing clones or forks keep the old history.

## Map

| Before | After | Subject |
|---|---|---|
| `8e21caf` | `3afe914` | chore(d0): initialize SOLO STEP 1 project setup, frozen contracts, and Python 3.11 baseline |
| `3f54021` | `3b0ba2c` | docs(handoff): record SOLO STEP 1 checkpoint in handoff/SOLO.md |
| `8882ed1` | `e05da7e` | feat(a1): implement SOLO STEP 2 data snapshot, returns, quality flags, and ADF diagnostics |
| `777b06d` | `4dac454` | docs(handoff): record SOLO STEP 2 checkpoint and snapshot qe1_20050101_20261030_afb9ce5694 |
| `99e0193` | `77998cf` | Complete bounded SOLO STEP 2 data-hardening pass (r2_hardened) |
| `43d26e1` | `079f337` | Record Step 2 r2_hardened commit hash in handoff/SOLO.md |
| `aacad93` | `f861147` | Add versioned RF evidence snapshot r3 and research review artifacts |
| `5751819` | `d1602d2` | Document private GitHub checkpoint and next review milestone |
| `d7ccafe` | `851b040` | Keep repository publication entry in the AI disclosure table |
| `782ec20` | `16181c0` | Record Step 9 fixed-rule evaluation protocol and proposed mandate assumptions |
| `e22ab38` | `4d73398` | Complete registered analytics, verified decision room and final research exports |
| `7f11b5f` | `49a2c5d` | Polish PDF typography and create test scratch directory in fresh checkouts |
| `c41b0eb` | `2598486` | Package final submission and record public access and clean-install evidence |
| `d5b37de` | `632534d` | Add Claude Code LaTeX and dashboard redesign handoff with honest review workflow |
| `27090c9` | `98d80d3` | Add tested Streamlit Community Cloud entrypoint and deployment instructions |
| `6608f99` | `f62fe8c` | Redesign the decision room and compile the reports from LaTeX |
| `95ac36f` | `ad14489` | Record clean-install evidence and rebuild the submission package |
| `5141b52` | `be450ea` | Assemble the canonical final submission folder |
| `42a0209` | `3c2ab2a` | Record final verification and rebuild the submission archive |
| `c965873` | `4710526` | Keep metric values and table status pills readable at narrow widths |
| `80de385` | `ab068d4` | Disable the hosted file watcher that raced module imports during updates |
| `5304403` | `a7d8b96` | Keep metric values on one line and scale them to the available width |
| `6cab076` | `fb25503` | Publish the verified public app link and rebuild the submission archive |
| `86ca30b` | `a87dc76` | Consolidate review disclosure on Assumptions page and simplify primary app screens |
| `b073558` | `8b9c74f` | Match the review-status test to the app and record final live checks |
| `5fa1353` | `138842c` | Publish corrected Nisal Induwara review draft with typed name and app evidence link |
