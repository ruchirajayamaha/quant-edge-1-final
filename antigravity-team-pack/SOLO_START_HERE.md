CURRENT CHECKPOINT: Steps1-8 are implemented and technically checked. Step8 outputs: results/step8_risk_stress_preview/index.html; 127 tests pass. STOP before Step9 integration. Human validation/mandate choices remain PENDING. This checkpoint supersedes older next-task text below.

# එක්කෙනෙක් Antigravity එකෙන් කරන current workflow එක

**Setup, market-data work සහ RF-only r3 upgrade එක ඉවරයි. ඒවා නැවත පටන් ගන්න එපා.** Current active baseline: `qe1_20050101_20261030_r3_6c4633a7ba`, runtime schema `1.1.0`. Live `handoff/SOLO.md` සහ runtime contracts බලන්න; පරණ design file එකකින් working code downgrade කරන්න එපා.

එක developer කෙනෙක්, එක checkout එකක් සහ `handoff/SOLO.md` checkpoint එකක් භාවිත කරන්න. A/B/C/D files කියන්නේ වැඩ කොටස්වල specifications. Solo mode එකේ වෙන වෙනම clone/owner restrictions අදාළ නැහැ.

## දැන් ඉන්න තැන සහ ඊළඟ වැඩේ

Steps 1-5 සහ corrections review කරලා ඉවරයි. දැන් **Step 6 / A3 rolling backtesting සහ coverage tests පටන්ගන්න.** `audit/decision_register/REGISTER.md` inherited settings provisional ලෙස තබාගෙන code/tests කරන්න; human inputs සහ independent validation තවම PENDING.

[Step 6 prompt එක](NEXT_TASK_STEP6.txt) agent එකට දෙන්න. Real-data checks development period එකට සීමා කරන්න. Step 6 ඉවර වුණාම report එක දීලා Step 7ට කලින් Codex review සඳහා නවත්වන්න. Accepted results සඳහා Step 4/5 audit closures සහ actual artifacts භාවිත කරන්න; chat එකක වෙනස් numbers තිබුණොත් ඒවාට code retune කරන්න එපා.

## පිළිවෙළ

| පියවර | වැඩේ | දැන් තත්ත්වය / prerequisite |
|---|---|---|
| 1 | Project setup | Complete; නැවත නොකරන්න |
| 2 | ETF data, cleaning, r3 RF evidence | Complete; snapshot preserve කරන්න |
| B0 | Decision register / team defence roles | Factual draft exists; human choices continue alongside implementation |
| 3 | Portfolio rules and return paths | Complete and reviewed; B1 |
| A1b | Bounded income/inflation context | Complete; original context preserved |
| 4 | KPIs, CAPM, income/real-growth interpretation | Complete; R1-R3 closed by review |
| 5 | Historical/normal/MC VaR and ES | Start now; C1, then stop for review |
| 6 | Registered primary-model backtesting | A3; past-only callback and weights |
| 7 | EVT and empirical-body/GPD-tail support | C2/C3; threshold safeguards තියාගන්න |
| 8 | Risk budgeting, sizing, stress and decision evidence | B2/B3; human-owned outcome |
| 8b | Mandate Feasibility Frontier | Preferred post-core B4; candidate-table fallback |
| 8c | EWMA-FHS challenger | Optional C4 after core; drop/defer if not defensible |
| 9 | Streamlit / shared result bundle | D1/D2; Recommendation-first; all required panels |
| 10 | Memo, tear sheet and final audit | D3 + final audit; actual page/render/install checks |
| Human work | Checks, reasoning and viva practice | Throughout; actual humans only |

## Step specifications and safeguards

- **B0/B1:** `02_B_PORTFOLIO_DECISIONS.txt`. Register constraints/rules before selecting/evaluating performance. Log existing full-history asset-data exposure honestly. Test rules, not hindsight weights. Use current sample covariance primary; shrinkage is optional.
- **A1b/A2:** `01_A_DATA_VALIDATION.txt`. Separate context snapshot; income share/price basis and no dividend double counting; CPI is ex-post monthly context unless a proper publication-aware decision policy is separately defined. Derive objectives from a declared cash-flow convention.
- **C1/A3:** `03_C_RISK_EVT.txt`, then A3. Respect single config draw count, simulation uncertainty, actual sample dates, and the registered primary model. Target HS/normal/MC rolling coverage, but only expose supported backtest choices; genuine failures remain visible.
- **C2/C3:** Recent current-risk view plus full-history crisis sensitivity, with identical methods per window. Recent data includes 2022 but not GFC/COVID. Do not force a low EVT threshold to populate 90%; use a labelled body/tail construction with valid ES integration and boundary tests.
- **B2/B3:** Contributions, feasible changes, historical paths and a justified seven-ETF hypothetical. Humans define ACCEPT/ADJUST/REJECT relative to proposed assumptions and monitoring actions. Scenario constraints are not automatically reverse stress.
- **B4/C4:** Optional standard-method integrations, not novel inventions or official requirements. Cache and measure real runtime. Bootstrap output is not a guaranteed probability of funding the endowment.
- **D1-D3:** `04_D_LEAD_APP.txt`. A first screen with decision/downside/confidence evidence; frozen reference bundle; same computed values in app and documents. Pending human decisions remain pending.
- **Final:** `05_INTEGRATE_AND_AUDIT.txt`. Corrected rule matrix, fresh clone/new venv, offline bundle, representative controls/error cases, page checks, actual judge access and human validation. One-page recommendation/tear-sheet reuse is a stated interpretation, not a confirmed organiser waiver.

## එක milestone එකක් ඉවර වුණාම

```text
Continue the existing solo Quant Edge project.
Read antigravity-team-pack/SOLO_START_HERE.md, COMMON_CONTEXT.md,
CONTRACTS.md and handoff/SOLO.md.
Implement ONLY the next registered, incomplete milestone.
Preserve r3 and completed work. Inspect existing code before editing.
Do not invent human choices or call exploratory work preregistered evaluation.
Run relevant checks and update the handoff with actual outcomes and limitations.
Do not start another milestone in this request.
```

Inputs නැත්නම් ඒ dependency එක record කරලා independent code/tests/docs කරන්න. Session/usage මාරු වුණාම current checkout සහ handoff එකෙන් resume කරන්න; project එක නැවත generate කරන්න එපා. Current rule interpretations and review dispositions are in `audit/final_strategy_review/PROMPT_INTEGRATION_DECISIONS.md`.
