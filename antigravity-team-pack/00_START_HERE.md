CURRENT CHECKPOINT: Steps1-8 are implemented and technically checked. Step8 outputs: results/step8_risk_stress_preview/index.html; 127 tests pass. STOP before Step9 integration. Human validation/mandate choices remain PENDING. This checkpoint supersedes older next-task text below.

# Quant Edge: Antigravity 4 දෙනාගේ වැඩ බෙදීම

**එක්කෙනෙක් implement කරනවා නම් [SOLO_START_HERE.md](SOLO_START_HERE.md) භාවිත කරන්න.** එහි එක Antigravity chat එකක කරන පිළිවෙළ සහ starter/continuation prompts තියෙනවා. පහළ guide එක හතර දෙනාගේ workflow එකටයි.

**Current update (2026-10-31):** Steps 1-5 සහ corrections review කරලා ඉවරයි. දැන් [NEXT_TASK_STEP6.txt](NEXT_TASK_STEP6.txt) භාවිත කරලා rolling backtesting සහ coverage tests කරන්න; Step 7ට කලින් review සඳහා නවත්වන්න. Human choices/validation PENDING ලෙස තබන්න. පහළ four-person plan එක historical alternative එකක්; current solo guide සහ runtime/handoff එක ප්‍රමුඛයි.

මේක official challenge සහ upstream prompts මත පදනම් වූ implementation prompt pack එකක්. Current completed/pending work සඳහා handoff/SOLO.md බලන්න; මේ මුල් four-person plan එකෙන් project එක නැවත generate කරන්න එපා. Original source PDFs සහ upstream initial prompt preserved.

**Claude plan එකේ direction එක හරි. ඒක ඒ විදිහටම sessions 4කට දුන්නොත් duplicated work, merge conflicts සහ unnecessary extensions නිසා usage වැය වෙයි.** මෙහි core requirements තියාගෙන optional වැඩ පසුවට දාලා තියෙනවා.

## 1. හතර දෙනාට බෙදෙන වැඩ

| කෙනා / session | වගකීම | තමාට අයිති files | පසුව කරන වැඩ |
|---|---|---|---|
| A | Data, cleaning, returns, KPIs/CAPM | `data.py`, `returns.py`, `kpis.py`, `backtest.py` | B/C interfaces ලැබුණාම rolling backtest + Kupiec/Christoffersen/Basel |
| B | Portfolio සහ decision evidence | `portfolio.py`, `risk_budget.py`, `stress.py` | Walk-forward weights, contributions, crisis replay, return/risk trade-offs |
| C | Risk engine | `var.py`, `es.py`, `evt.py` | Historical/normal/Monte Carlo + unconditional POT-GPD EVT |
| D | Lead / integration / app | Scaffold, contracts, config, dependencies, `app/`, `pipeline.py`, exports, final docs | Streamlit, integration, memo/tear sheet assembly, final audit |

**Cට backtesting එකත් දෙන්නේ නැහැ:** EVT එකම සංකීර්ණ වැඩක්. A data deliver කරලා පසුව validation කරයි. B තමන්ගේ analytical sections ලියලා Dට දෙයි; D තනිවම මුළු report එක invent කරන්නේ නැහැ.

Workload එක ආසන්නව balance කරලා තියෙනවා. මේක measured token estimate එකක් හෝ සෑම account එකකටම 25% usage යන පොරොන්දුවක් නෙවෙයි. Dataset එක, model එක සහ debugging අනුව වෙනස් වෙනවා.

## 2. පටන් ගන්න පිළිවෙළ

1. Implementation repo එකේ මේ `antigravity-team-pack/` folder එක තියාගන්න. D මුලින් `04_D_LEAD_APP.txt` හි **D0** පමණක් කරයි: scaffold + config + contracts. Analytics නැහැ.
2. ඒ baseline commit එක A/B/C තමන්ගේ වෙන වෙනම clone/worktree වලට ගන්නවා. Branches: `work/a-data-validation`, `work/b-portfolio`, `work/c-risk`, `work/d-integration`.
3. හතර දෙනාම pack folder එකේ `COMMON_CONTEXT.md` සහ `CONTRACTS.md` context ලෙස දීලා **තමන්ට අදාළ role prompt එක පමණක්** දෙන්න. Agent එකට ඒ files folder එකෙන්ම කියවන්න කියන්නත් පුළුවන්.
4. A: A1 data. B: synthetic returns වල portfolio tests. C: synthetic losses වල risk tests. D: test fixtures වල UI shell. ඒවා parallel යන්න පුළුවන්.
5. A එක data snapshot එකක් + manifest එකක් දෙයි. හතර දෙනාම ඒ dataset ID එක භාවිත කරනවා; නැවත වෙන වෙනම downloads කරන්නේ නැහැ.
6. A2, B1/B2, C1/C2 handoffs D integrate කරයි. ඊට පසුව A3 rolling validation; D UI + real output exports.
7. `05_INTEGRATE_AND_AUDIT.txt` Dට දෙන්න. අවසානයේ team එක actual results බලලා reasoning/recommendation/human validation සම්පූර්ණ කරයි.

එකම physical folder එක sessions 4කින් edit කරන්න එපා. වෙන වෙනම branches තිබුණත් එකම checkout එකේ files shared වෙනවා. Separate clones/worktrees අවශ්‍යයි. Git hosting එකට මෙතැනින් publish කරලා නැහැ.

## 3. මුලින් කරන core / පසුව කරන extras

**Core එකෙන් අඩු නොකරන දේවල්:** Markowitz/CAPM + KPIs; VaR methods 3ම 95/99%; ES; justified EVT; selected primary VaR model එකේ out-of-sample validation; marginal/component VaR/ES; position-sizing alternatives; historical + hypothetical stress; required app panels; limitations; report; tear sheet; AI disclosure.

**Core pass වුණාට පස්සේ එක extension එකක් පමණක් තෝරන්න:** conditional EVT, GARCH-FHS, automatic threshold selection, regime overlay, formal ES backtest, reverse stress. Methods 4ක optimisers සහ daily rolling GARCH/EVT fits core එකට අවශ්‍ය නැහැ.

## 4. Usage අඩු කරන practical rules

- මුල් 13-page prompt pack එක sessions හැම එකටම නැවත නැවත paste කරන්න එපා. Common context + contracts + own role පමණක් දෙන්න.
- එක prompt එකකට එක milestone එකක්. අවසානයේ changed files, tests, blocker, next task විතරක් ඉල්ලන්න.
- දිග chat එක නැවත explain කරන්නේ නැතුව `handoff/A.md` වගේ checkpoint file එකෙන් resume කරන්න.
- D පමණක් shared files/dependencies/config වෙනස් කරයි. අනිත් අය dependency request එකක් handoff එකේ ලියයි.
- Data, simulation, optimisation, bootstrap සහ rolling forecasts cache කරලා UI reruns වලදී නැවත run නොකරන්න.
- Usage ඉවර වෙන්න ළඟ නම් `06_HANDOFF_TEMPLATE.md` අනුව checkpoint එකක් ලියවන්න. අලුත් session එකට same role ownership එක දෙන්න.
- Model plan/quota/reset times ගැන මෙහි උපකල්පන නැහැ; මේක duplicated development වැඩ අඩු කරන plan එකක්.

## 5. වැදගත් corrections

EVT sign/threshold rules, cash universe එකට පිටින් යාම, recommendation කලින් තෝරා තිබීම, වැරදි return-objective arithmetic, සහ 500-day EVT sample-size issue එක `REVIEW_AND_CORRECTIONS.md` එකේ දාලා තියෙනවා.

Official brief එකේ **team size 5** කියලා තියෙනවා. මෙහි 4 කියන්නේ development workstreams 4යි. Registered team එකත් 4 දෙනෙක් නම් organiserගේ team-size rule එක verify කරන්න. Fifth member කෙනෙක් ඉන්නවා නම් human checks, investment reasoning සහ viva preparation බාර දෙන්න.

**වේලාව:** මුල් pack එකේ 6 hours කියන්නේ suggestion එකක්. Supplied official brief එකේ submission deadline එකක් නැහැ. මේ pack එකෙන් hours 6කින් completion guarantee කරන්නේ නැහැ. අවසාන integration + human review සඳහා available time එකෙන් අවම වශයෙන් 20%ක් වෙන් කරගන්න.

**Submission:** Markdown skeleton එක final 7-15-page memo එකක් නෙවෙයි. Final report pagination සහ one-page tear sheet සැබෑ export එකේ check කරන්න. Team reasoning placeholders අවසාන submission එකට කලින් පුරවන්න.

## Files

- [Corrections and source references](REVIEW_AND_CORRECTIONS.md)
- [Common context](COMMON_CONTEXT.md)
- [Shared interfaces](CONTRACTS.md)
- [A prompt](01_A_DATA_VALIDATION.txt)
- [B prompt](02_B_PORTFOLIO_DECISIONS.txt)
- [C prompt](03_C_RISK_EVT.txt)
- [D prompt](04_D_LEAD_APP.txt)
- [Integration and audit prompt](05_INTEGRATE_AND_AUDIT.txt)
- [Handoff template](06_HANDOFF_TEMPLATE.md)

Role prompts English වලින් තියෙන්නේ agent එකට copy-paste කරන්න පහසු වෙන්න. Guide එක follow කරලා D0 ඉවර වුණාම ඉතිරි sessions parallel පටන් ගන්න.
