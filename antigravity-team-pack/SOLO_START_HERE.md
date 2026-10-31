# එක්කෙනෙක් Antigravity එකෙන් කරන පිළිවෙළ

**එක්කෙනෙක් code කරනවා නම් එක project folder එකක, එක Antigravity chat එකක පියවරෙන් පියවර කරගෙන යන්න.** කලින් දුන්න A/B/C/D කියන්නේ වැඩ කොටස්. එක්කෙනෙක් ඒ කොටස් ඔක්කොම මේ පහළ පිළිවෙළට කරනවා. Clones හතරක් හෝ agents හතරක් අවශ්‍ය නැහැ.

මුළු project එක එකවර හදන්න කියන්නේ නැතුව එක පියවරක් හදලා, අදාළ checks run කරලා, ඊළඟ එකට යන්න. මෙහි තවම project implementation එක කරලා නැහැ; මේක ඒ සඳහා guide එක සහ prompts.

## පිළිවෙළ

| පියවර | කරන දේ | ඉවර වුණාම තියෙන්න ඕන දේ |
|---|---|---|
| 1 | Project setup | Folders, config, dependencies සහ function interfaces |
| 2 | Data + data-quality checks | Download කරපු, සකස් කරපු prices/returns සහ quality report |
| 3 | Portfolio construction | ETF weights, benchmark සහ කාලයත් එක්ක portfolio return path |
| 4 | KPIs / CAPM | Return, Sharpe, drawdown ඇතුළු performance metrics |
| 5 | VaR + ES | Historical, parametric, Monte Carlo risk estimates |
| 6 | Backtesting | Model forecasts පරණ දවස්වල සැබෑ losses එක්ක පරීක්ෂා කළ results |
| 7 | EVT | Extreme losses සඳහා tail model සහ threshold diagnostics |
| 8 | Risk budgeting + stress | එක් ETF එකෙන් එන risk, weight alternatives සහ crisis losses |
| 9 | Streamlit app | ඉහත computed results පෙන්වන usable app එක |
| 10 | Docs + final audit | README, disclosure, memo/tear sheet drafts සහ final checks |

**Data-quality checks කියන්නේ step 2. Model validation/backtesting කියන්නේ step 6. ඒ දෙක වෙනස්.**

## දැන් මුලින්ම කරන්න ඕන දේ

1. Antigravity එකෙන් project folder එක open කරන්න. ඒක ඇතුළේ මේ `antigravity-team-pack/` folder එක තියෙන්න ඕන.
2. පහළ starter prompt එක එක chat එකකට paste කරන්න.
3. Step 1 ඉවර වුණාම continuation prompt එකෙන් step 2 කරන්න. එක වරකට එක step එකක්.

### මුලින් paste කරන prompt එක

```text
I am the single developer implementing this Quant Edge project.
Read antigravity-team-pack/SOLO_START_HERE.md and follow its solo workflow.
Read COMMON_CONTEXT.md and CONTRACTS.md from that same directory for the
project requirements and numerical interfaces.

SOLO OVERRIDE: I own all project modules. Ignore the four-person file-ownership,
separate-clone, parallel-branch and A/B/C/D handoff restrictions. Keep all the
data, numerical, no-look-ahead, testing and disclosure requirements unchanged.
Use one working checkout and one checkpoint file: handoff/SOLO.md.
The old initial prompt's instruction to restate the entire project and ask five
general questions is superseded by this bounded task.

Implement SOLO STEP 1 ONLY: project setup.
Use milestone D0 from 04_D_LEAD_APP.txt as the setup specification, subject
to the solo override. Do not implement data downloads or analytics yet.
Set up the folders, typed shared contracts, config, minimal installable package,
verified compatible dependencies and Windows run instructions.
Keep stubs explicitly unimplemented; never return fake portfolio results.
Do not overwrite the original PDFs or prompt files, publish, or deploy.

Run relevant setup/import/config checks that are possible. Record actual outcomes
and any environment limits. In handoff/SOLO.md record the completed work,
contract version, decisions still provisional, and STEP 2 as the next task.
Report briefly: files changed, checks actually run, real blockers, next step.
Do not start later steps in this request.
```

### එක් step එකක් ඉවර වුණාම paste කරන prompt එක

```text
Continue the existing solo Quant Edge project.
Read antigravity-team-pack/SOLO_START_HERE.md and handoff/SOLO.md.
Inspect the existing code and implement ONLY the next incomplete solo step.
Use the step-to-specification mapping below; read only the relevant milestone
and its named dependencies rather than replanning or regenerating the project.
The solo ownership override remains active.
Preserve completed work and the same data snapshot. Run relevant checks,
fix issues within this step, and update handoff/SOLO.md with actual results,
remaining limitations and the next step. Report a concise checkpoint.
Do not begin a later step in this request or claim human validation was done.
```

## Agent සඳහා step-to-specification mapping

The role prompt files are technical specifications, not separate people in this workflow. Read only the selected milestone and relevant interface definitions. The solo override takes precedence over their ownership/delegation instructions.

1. **Setup:** `04_D_LEAD_APP.txt` D0, without parallel branches/clones/owners. Keep one `handoff/SOLO.md`.
2. **Data:** `01_A_DATA_VALIDATION.txt` A1. Create one snapshot/manifest, session-aware simple/log returns, flags, ADF/quality outputs and offline states. Do not erase flagged observations or silently bridge missing sessions.
3. **Portfolio:** `02_B_PORTFOLIO_DECISIONS.txt` B1. Implement construction, feasibility, weight drift, costs and canonical benchmark paths. Metrics/model comparison calls depending on steps 4/5 are deferred to step 8, not duplicated or fabricated. Freeze selection/evaluation chronology before assessing performance.
4. **KPIs:** `01_A_DATA_VALIDATION.txt` A2, using the paths from step 3. Include stationarity diagnostics on actual modelled portfolio series as specified. Keep unavailable RF-dependent KPIs explicit.
5. **VaR/ES:** `03_C_RISK_EVT.txt` C1. Provide the shared moment and empirical-tail helpers. Compare the three required methods at95/99 with identical portfolio/sample conventions.
6. **Validation:** `01_A_DATA_VALIDATION.txt` A3. Use the existing weights/forecast APIs. Rolling selected-primary-model validation, no-look-ahead tests, Kupiec, Christoffersen and eligible Basel diagnostic. Distinguish unavailable selected-model backtests from primary historical validation. This step needs the selected VaR callback, not a completed EVT extension, so validate the basic model early.
7. **EVT:** `03_C_RISK_EVT.txt` C2/C3. Keep sufficient sample size, domain/support checks, threshold justification and uncertainty. Reuse conventional estimates on the same window for comparisons. Conditional EVT/GARCH remains deferred.
8. **Decision evidence:** `02_B_PORTFOLIO_DECISIONS.txt` B2/B3 plus deferred B1 comparisons, now using real functions/results from steps 4-7. Risk contributions, feasible position-sizing alternatives, historical crises and one hypothetical scenario. Complete return/risk trade-off tables. Team judgement and final recommendation remain pending until actually evaluated by humans.
9. **App:** `04_D_LEAD_APP.txt` D1/D2. Build the pipeline and six views using actual computed outputs. Cache expensive work; sidebar changes do not silently change the risk definition. Handle no cache, offline cache, unsupported methods/confidence and incomplete backtests honestly. No need for a synthetic UI-first implementation now that analytics exist.
10. **Docs/audit:** `04_D_LEAD_APP.txt` D3, then `05_INTEGRATE_AND_AUDIT.txt`. Replace cross-owner review requests with independent recomputations and actual human-review tasks. Check reproducibility, limitations and all deliverables. Report drafts/placeholders/unverified pagination as incomplete; do not manufacture reasoning or human sign-off. Add at most one optional extension only after the core and required outputs are complete.

At every step update documentation/disclosure incrementally, not just at step 10. Record snapshot/config/seed IDs, actual check commands/outcomes, unresolved assumptions and next task in `handoff/SOLO.md`. The public numerical/data interfaces remain the same as the four-person design; changes can be made consistently across callers by the single developer.

## Usage හෝ chat එක මාරු කරන්න වුණොත්

වැඩේ මුල ඉඳන් නැවත පටන් ගන්න එපා. Existing project folder එකෙන් අලුත් session එක open කරලා ඉහත continuation prompt එක දෙන්න. Checkpoint file එකෙන් නවත්තපු තැනින් ඉදිරියට යන්න. එකම files වෙනස් කරන sessions දෙකක් එකවර run කරන්න එපා.

Coding එක එක්කෙනෙක් කළත් අවසාන investment judgement, human checks සහ competition submission requirements වෙනස් වෙන්නේ නැහැ. Final recommendation එක AI එකෙන් තනිව තීරණය කරලා human-reviewed ලෙස දක්වන්න එපා.
