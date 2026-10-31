# Step9 technical closure

Integrated the registered portfolio rule, current risk, rolling coverage, Euler
allocation, stress and context through one shared analytical engine. Streamlit
loads the same non-executable, hash-verified reference used by the exports and
memo. Final bundle identity includes dataset, preserved config, analytical source
and the separate team-proposed mandate. The base Git revision and exact source
digest are distinguished; no self-referential final-commit hash is fabricated.

## Actual completed verification

- Preserved all53 source-data file hashes and102 protected previous source/output
  files. Earlier ETF data, contracts, config and development results are unchanged.
- Full connected suite:132 passed in26.39s before the final Decision headline
  refinement. Final integration/UI suite after that refinement:5 passed in7.12s.
- Independent5-value verification in `verification.json`: evaluation CAGR and
  max drawdown, Normal VaR99, exact fractional-tail Historical ES99 and GFC dollar
  terminal loss. Maximum fractional-metric error below5.2e-15; dollar error below
  5.9e-10. Signed Euler components agree within3.5e-18.
-29,922 actual rolling forecast rows checked (six runs ×4,987 targets); prior
  training ends before each realised session. Independent Kupiec likelihood errors
  below4.6e-13. Different models retain their own rows, not relabelled outputs.
- Six real-data app views; confidence90/95/99 crossed with all five risk methods;
  equal-weight reference; short-date Basel failure. AppTest required an unsandboxed
  local socket pair; the sandbox stalled asyncio before the app started, rather
  than revealing a financial-model failure. The actual tests then ran successfully.
- `pip check`: no broken requirements.
- Final release suite after mandate/source identity and RF-sensitivity integration:
 132 passed in21.57s. The fresh checkout initially exposed a missing ignored `tmp/`
 directory in test setup; the integration test now creates its own workspace temp
 directory rather than depending on a directory from prior development runs.
- Memo12 pages, tear sheet1 page, separate plain-English recommendation1 page;
  PDFs rendered via Poppler, all pages visually inspected. No clipping/overflow.
- Publication token/private-key pattern scan found no matches; no unignored file
  above50MB. The scan is an evidence-based check, not a guarantee of all possible
  secret patterns. No credentials were printed or written to repository files.

## Corrections found and applied during integration

- Supplied the required config argument to the offline UI data loader.
- Cleared rich stress DataFrame attrs for Arrow UI display; the analytical engine
  retains its original daily-path/attribution contract.
- Kept pure-POT and body/tail hybrid method identifiers distinct.
- Corrected the short-range diagnostic test:90/95 Basel is not applicable;
  a99% range shorter than250 sessions is unavailable.
- Made the persisted identity detect stale proposed mandates as well as source and
  config changes. Full RF accrual KPI sensitivity is retained as a labelled table.
- Current risk uses prospective final-close target weights; historical strategy
  returns use their actual pre-return drifting weights. Controls state this scope.

## Decision and limitations

Conditional ADJUST, under explicitly team-proposed10-year/4% spending/2.5% inflation/
0.25% additional-fee assumptions. These are not supplied client facts. No post-hoc
strategy switch followed the evaluation. Protocol/proposal commit782ec20 came
before post-2016 strategy outcomes; prior asset EDA, RF and fixed-exposure stress
inspection are disclosed. Current recent HS99 tail budgets are marginally exceeded;
full-history tails, GFC drawdown, monthly drift and dependence remain material.

Independent human validation, the team's substantive recommendation evaluation,
team/member details and the organiser's exact deadline/submission route remain
OPEN. No human sign-off or organiser upload is claimed. Final-five pitch/deck is
conditional; defence notes are preparation, not a completed rehearsal/deck.

## Clean-install and publication evidence

Fresh-checkout/new-environment and remote publication results are recorded in
`clean_install.json` and `publication.json` only after those actions complete.
The repository is not claimed public until independently verified there.
