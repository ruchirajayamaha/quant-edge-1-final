# Step 4 / A1b-A2 review - 2026-10-31

**Disposition: mandatory KPI calculations on the current development sample are independently correct; fix R1-R3 before Step 5.** This is a bounded correction to valid-input handling, real-return sample semantics and context-cache verification. It does not require re-downloading market history, replacing the missing CPI observation, retuning portfolios or changing financial conventions.

Scope: actual `kpis.py`, appended A1b portion of `data.py`, snapshot manifest, CLI, tests and methodology, plus the supplied completion report. Audit artifacts only were created/updated; production code/config/data were not edited by this review. No selection/evaluation strategy outcomes were computed.

## R1 [P2] A valid positive-return sample crashes the entire KPI function

Location: `src/quantedge/kpis.py:430`.

With returns `[0.0001,0.0002,0.0003,0.0004]` and daily RF `0.00025`, no raw return is negative, while some returns fall below RF. Thus the primary RF-target downside deviation is positive and the primary Sortino is finite. But the optional zero-target Sortino is `None`, and constructing the primary note applies `:.4f` to it. `compute_kpis` raises `TypeError: unsupported format string passed to NoneType.__format__` instead of returning any of its metrics.

Fix only the optional-diagnostic rendering/guard, preserving valid primary RF-target formulas. Add a regression in which raw returns are all positive but excess returns include a shortfall. A missing optional zero-target ratio must not prevent the defined primary Sortino or the other metrics from being returned.

## R2 [P2] Real-return output stitches nonconsecutive CPI months and labels them as an endpoint period

Locations: `src/quantedge/kpis.py:953`, `:989`, and the period/endpoint notes near `:1040`.

The code checks whether each individual month has its preceding CPI value, but does not check that the retained months form a continuous block. A missing internal CPI month removes both that month's factor and the following month's factor. The surviving factors are compounded together with annualisation based on the retained count while notes refer to the first/last CPI endpoint ratio.

Repro: complete NYSE returns from January-May 2010, all zero; CPI December-May `[100,101,missing,121,122,123]`. The function combines January, April and May (3 of 5 months), gives CPI multiplier `1.026694214876033`, describes January-May/base December and returns all statuses `ok`. The stated endpoint ratio is actually `123/100 = 1.23`. March is also excluded because its prior CPI is absent, but the excluded-month list names February only.

This matters to the existing context: October 2025 CPI is actually absent. The supplied development results through 2016 are unaffected, but a later whole-history/evaluation real-return panel would hit this code path. The absence itself is legitimate: [BLS confirms it could not collect October 2025 CPI reference data](https://www.bls.gov/data/inflation_calculator.htm). Do not fabricate that month's inflation.

Use an explicit policy that produces honest interval returns. For example, return a clearly selected contiguous block with its actual anchor/end/duration; or compute full-interval purchasing-power growth from valid endpoint CPI and complete nominal wealth, while treating unavailable intermediate monthly real returns separately. If retaining a scattered-month diagnostic, label it as such and never call its product the full start/end wealth or CPI ratio. List every excluded month and reason, including missing prior CPI. Do not choose a block based on portfolio performance.

Also, completed NYSE coverage is currently tested by equal row counts (`:942`), not by matching actual session dates. A missing valid NYSE date replaced by a Saturday is incorrectly accepted as a complete month. Compare date membership/grid exactly when claiming full coverage. Add focused missing-internal-CPI and wrong-date/same-count tests. Keep existing valid contiguous development results stable where the policy still selects the same months.

## R3 [P2] The context loader can hash one file and return a different, altered file

Location: `src/quantedge/data.py:2339` versus reads at `:2351`.

For each manifest entry, the loader first verifies `base_dir / rel_path` if it exists. It then reads payloads from `context_dir / basename`. For a copied/custom context directory whose manifest still contains the original repository-relative paths, these are different files.

Repro: copy the context into an isolated temporary directory, keep its manifest unchanged and increase its first SPY close by 10%. Calling `load_context_data(..., offline=True, repo_root=ROOT, context_dir=copied)` accepts it and returns `132.33000335693362` instead of `120.30000305175781`, because the untouched original file passed the hash check. The temporary probe was isolated and removed; the real context remains unchanged.

Resolve each actual payload path once, verify its bytes and read exactly that file. Add a valid-relocated-cache test and a tampered-relocated-cache rejection test, alongside default-path tamper rejection.

The cache hit also bypasses requested config compatibility: a call with frozen end `2016-12-30` returns the context ending `2026-10-30`. Apply an explicit compatibility/coverage/parent policy before returning a hit; either reject incompatible input offline or return an explicitly bounded compatible view with truthful identity. Do not silently fetch or relabel a mismatched cache as matching. Hash integrity alone is not config/provenance compatibility.

## Independently verified strengths

- `.venv/Scripts/python.exe -m pytest -q`: **58 passed in 8.89s**, exit 0.
- The audit script's independent development oracle checked all **13 KPI values** using Python `statistics`/`math` and `statsmodels.OLS`, rather than the implementation's NumPy and hand-written OLS routes. Maximum absolute metric difference: **2.22e-16**; alpha t-statistic difference: **2.66e-15**.
- Actual development path: `2007-01-05..2016-12-30`, 2,516 active sessions. Headline CAGR, volatility, primary Sharpe/Sortino, beta/alpha, information ratio, initial-wealth drawdown and Calmar agree with the independent route.
- Existing snapshot hashes **46/46**, context hashes **7/7**: all match. Actual stored split-adjusted prices are finite/positive and distributions finite/nonnegative. R3 is a loader bug, not evidence that the current default snapshot is corrupted.
- Config, requirements, frozen contracts and active pointer match baseline Git content. The previous data adapter remains unchanged; the context adapter was appended.
- Distribution-income analysis uses preceding split-adjusted close denominators and is kept separate from adjusted-price total returns. GLD's lack of income is consistent with [the issuer's product disclosure](https://www.ssga.com/us/en/individual/etfs/spdr-gold-shares-gld).
- CPI is labelled latest-vintage, seasonally adjusted, ex post, and not an optimizer signal. The correct purchasing-power construction uses the relevant index ratios; see [BLS constant-dollar guidance](https://www.bls.gov/cpi/factsheets/purchasing-power-constant-dollars.htm).

## Nonblocking report consistency notes

The pasted report describes an older four-day test vector and a `1e-8` beta cutoff; the actual current hand-check uses constructed alpha `0.002`, beta `0.5`, and runtime `NEAR_ZERO_BETA_TOL=1e-4`. The actual code, tests and current methodology are the review authority. Refresh the completion summary from actual executed checks; do not reuse stale synthetic numbers in the memo. Likewise, the report promises unavailable RF metrics for infinite RF inputs, whereas the current input validator raises an error. State the actual input contract or explicitly implement/test any changed behaviour.

## Next action

Run `ANTIGRAVITY_STEP4_FIX_PROMPT.txt`, resolve R1-R3, run relevant regressions and the connected suite, then stop for the user's required review. No Step 5 or extra innovation work belongs in that correction. Keep human mandate decisions and validation pending until actually supplied/performed.
