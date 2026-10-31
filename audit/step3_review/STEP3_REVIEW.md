# Step 3 / B1 independent review

Review date: 2026-10-31. Scope: the supplied completion report, actual portfolio implementation, relevant contracts/config/tests and methodology. This review added audit artifacts only. No production implementation, configuration, dataset, active pointer or dependency was edited; no network market-data downloads or Git operations publishing changes were performed.

**Disposition: core implementation verified; address R1-R3 in one bounded correction before Step 4.** These are local input-validation, reporting and documentation corrections. They do not require new datasets, a new strategy, retuning constraints or another broad research pass.

## Findings

### R1 [P2] A fixed-weight override can silently bypass the named optimizer

Locations: `src/quantedge/portfolio.py:1010` and `:1089`.

`requires_estimation` becomes false whenever a fixed-weight dictionary is supplied, and the fixed-weight branch is taken before the objective branch. A `StrategySpec(objective='min_variance', fixed_weights=all_SPY)` therefore returns 100% SPY with `solver_status='analytic_reference'`, bypassing covariance estimation and the constrained solver. It is still advertised in metadata as minimum variance. Even an unsupported covariance-estimator string is ignored in this case. The same general branch can override an `equal_weight` objective.

The current `make_core_strategy_specs` does not trigger this bug, so the reported development smoke test is not invalidated. However, the public path API can silently misrepresent an allocation, including one breaching the provisional caps. Reject contradictory combinations before constructing a path; direct custom allocations to the explicit `fixed_weights` objective. Preserve the legitimate configured 60/40 reference path.

Acceptance: both feasible and infeasible fixed-weight overrides attached to `min_variance`/`equal_weight` fail clearly; the normal minimum-variance, equal-weight, 60/40 and explicitly fixed-weight paths still work. Add a focused regression.

### R2 [P2] Rebalance-target feasibility is presented as unqualified mandate compliance

Locations: `src/quantedge/portfolio.py:1192` and `:1243`.

`mandate_feasible_all_rebalances` correctly describes target allocations at trade dates. But `mandate_compliance_status='feasible_provisional_mandate'` is derived solely from those targets and does not describe holdings between trades. The distinction matters under the existing defaults, rather than just on hypothetical inputs:

| Development-only measurement | Result |
|---|---:|
| Active sessions, 2007-01-05 through 2016-12-30 | 2,516 |
| Feasible minimum-variance rebalance targets | 120 / 120 |
| Pre-return sessions exceeding a configured single-ETF or equity-group cap after drift | 1,439 |
| Maximum pre-return single-ETF holding | 45.1393% |
| Maximum pre-return equity-group holding | 37.2983% |

The caps supplied to the optimizer are 40% per ETF and 35% equities. Natural drift is intended and mathematically correct. These measurements **do not mean the optimizer failed** or establish that the human mandate requires continuous caps. They show that a policy treating caps as rebalance-target constraints is different from a policy enforcing them at all times. The latter has not been approved or implemented.

Declare the current scope as rebalance targets only. Add separate daily/pre-return compliance monitoring with dates/counts/maxima, and qualify any path-wide status/summary. Do not silently clip weights, introduce daily trading, change the return paths, relax limits or claim continuous compliance. Human choice of a continuous-limit policy remains pending.

Acceptance: a synthetic cap-feasible target that drifts beyond a cap remains target-feasible but has a separate observed-drift-breach status/count. A no-breach control remains clear. The existing development path arrays must remain unchanged by this reporting-only correction.

### R3 [P3] The written Frank-Wolfe certificate overstates the bound by a factor of two

Location: `docs/sections/b_portfolio_construction.md:41`.

The objective/gradient convention is `f(w)=w.T @ Sigma_scaled @ w`, `grad f=2*Sigma_scaled@w`. The general certificate is `0 <= f(w)-f* <= gap(w)`, not `2*(f(w)-f*) <= gap(w)`. For a counterexample, take `f(x)=x**2` on `[1,2]`, at `x=2`: optimum value 1, primal error 3, Frank-Wolfe gap 4. The written inequality would require 4 >= 6.

Correct the derivation and describe the numerical LP/solver certificate with its tolerances. The existing runtime criterion `gap <= 1e-7` need not change. The correct certificate is given in section 2, equation (2), of [Jaggi (2013), Revisiting Frank-Wolfe](https://proceedings.mlr.press/v28/jaggi13.pdf).

## Checks actually run

- `.venv/Scripts/python.exe -m pytest -q`: **49 passed in 6.97s**, independently rerun during this review.
- `.venv/Scripts/python.exe audit/step3_review/verify_step3.py`: passed the read-only audit assertions and reproduced R1/R2. Outputs are in `verification.json`.
- Independent units/price holdings ledger over 48 synthetic sessions, including monthly trades and the declared multiplicative-cost convention: maximum absolute wealth difference **4.44e-16**.
- Physically truncated-prefix check: earlier minimum-variance weights and wealth match **exactly**, supplementing the existing future-perturbation test.
- Development-only allocation monitoring: the measured values above; no selection/evaluation strategy paths or outcome comparisons computed.
- SHA-256 verification: **46/46** snapshot files match their manifests (v1 13, r2 15, r3 18).
- Config, requirements, contracts and active pointer match their Git baseline content; config hash remains `587ddbe363589fb6956c23c5fe8b2b544bac81d9224a0b4bb59f60f5fbc0a017`.
- The earlier 22-file runtime baseline differs only in the expected Step 3 implementation and setup-stub test. The new Step 3 test file is separately present and included in pytest.

## What is already satisfactory

Known-answer constrained optimization, bounds mapping, canonical order, optimizer output validation, reference labelling, prior-data training slices, monthly scheduling, drift, initial-entry turnover/cost, initial-wealth drawdown and focused future-invariance tests are implemented. The declared close-to-close execution approximation is disclosed; these tests are not proof of executable close-price trading or market-impact realism. The independent ledger verifies the declared transaction-cost convention, not an exact self-financing market-execution model.

Preserve this work. After R1-R3 and their relevant checks pass, proceed to Step 4 (bounded A1b context plus A2 KPIs). Economic inputs and human validation can remain visibly pending while engineering continues.
