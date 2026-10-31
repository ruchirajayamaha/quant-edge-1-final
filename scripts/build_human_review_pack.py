"""Build the human-review pack from frozen inputs. Nothing here records a completed review.

Writes handoff/human_review_pack/*.md and report/latex/generated/review_*.tex. The worksheet has
blank answer columns; the AI-prepared answer key is a separate file.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "handoff/human_review_pack"
LATEX = ROOT / "report/latex/generated"
NOTICE = ("Prepared by AI as a review aid. It is not a completed review, and using it does not validate anything "
          "until a named person does the work and records their own findings.")


def main() -> None:
    PACK.mkdir(parents=True, exist_ok=True)
    ref = json.loads((ROOT / "results/final/reference.json").read_text(encoding="utf-8"))
    dataset = ref["metadata"]["dataset_id"]
    returns = pd.read_parquet(ROOT / f"data/processed/{dataset}/simple_returns.parquet")
    weights_before = pd.read_csv(ROOT / "results/final/weights_before_min_variance.csv", parse_dates=["date"]).set_index("date")
    daily = pd.read_csv(ROOT / "results/final/daily_performance.csv", parse_dates=["date"])
    target = pd.DataFrame(ref["current_weights"]).set_index("ticker")["min_variance"].reindex(returns.columns)

    day = pd.Timestamp("2026-10-29")
    held, day_returns = weights_before.loc[day, returns.columns], returns.loc[day]
    day_result = float(held @ day_returns)

    path = daily[(daily.portfolio_id == "min_variance") & (daily.date >= "2021-01-04")].set_index("date").net_return
    wealth = (1 + path).cumprod()
    peak = wealth.cummax().clip(lower=1)
    trough_day = (wealth / peak - 1).idxmin()
    peak_day = wealth.loc[:trough_day].idxmax()

    sample = returns.iloc[-1260:]
    losses = -(sample.to_numpy() @ target.to_numpy())
    mean_loss, std_loss, z = losses.mean(), losses.std(ddof=1), 2.3263478740408408
    worst = np.sort(losses)[::-1][:13]

    crisis = returns.loc["2007-10-09":"2009-03-09"]
    cumulative = (1 + crisis).prod() - 1

    def rows(frame_rows: list[list[str]]) -> str:
        return "\n".join("| " + " | ".join(r) + " |" for r in frame_rows)

    answers = [
        ("A. One-day return, 29 Oct 2026", f"{day_result:.10f}", f"{day_result:.6%}", "results/final/daily_performance.csv"),
        ("B. Evaluation maximum drawdown", f"{wealth[trough_day] / wealth[peak_day] - 1:.10f}", f"{wealth[trough_day] / wealth[peak_day] - 1:.6%}", "period_kpis: max_drawdown"),
        ("C. Recent Normal VaR 99%", f"{mean_loss + z * std_loss:.10f}", f"{mean_loss + z * std_loss:.6%}", "risk_table: parametric_normal"),
        ("D. Recent Historical ES 99%", f"{(worst[:12].sum() + 0.6 * worst[12]) / 12.6:.10f}", f"{(worst[:12].sum() + 0.6 * worst[12]) / 12.6:.6%}", "risk_table: historical"),
        ("E. GFC endpoint return, current target", f"{float(target @ cumulative):.10f}", f"{float(target @ cumulative):.6%}", "stress_results: gfc_2007_2009"),
        ("F. Hurdle arithmetic", "0.0675", "6.75%", "submission/mandate_proposal.json"),
    ]

    worksheet = f"""# Worked calculation worksheet

{NOTICE}

Work each item yourself with a calculator, a spreadsheet or code you wrote. Check inputs against the
named original file, not just this sheet. Leave the answer key closed until you have an answer.

## A. One-day portfolio return, 29 October 2026

Original files: `results/final/weights_before_min_variance.csv` and the active `simple_returns.parquet`.
Task: multiply each weight by its return and add them up.

| ETF | Pre-return weight | Asset simple return |
|---|---:|---:|
{rows([[t, f"{held[t]:.10f}", f"{day_returns[t]:.10f}"] for t in returns.columns])}

Your answer: ____________________

## B. Evaluation maximum drawdown

Original file: `results/final/daily_performance.csv`, `min_variance`, from 4 January 2021.
Task: compound `net_return` from wealth 1 and include that starting value in the running peak. Find the
deepest fall from peak. Then confirm your peak and trough dates.

Your answer: ____________________  Peak date: ____________  Trough date: ____________

## C. Recent Normal VaR at 99%

Inputs: the last 1,260 rows of returns and `current_weights.min_variance` in `results/final/reference.json`.
These target weights differ from the historical holdings in item A.

| Input | Value |
|---|---:|
| Sample mean loss | {mean_loss:.17f} |
| Sample standard deviation, ddof = 1 | {std_loss:.17f} |
| Standard Normal 99% quantile | {z:.16f} |

Task: mean loss + quantile × standard deviation.

Your answer: ____________________

## D. Recent Historical ES at 99%

The worst 1% of 1,260 sessions is 12.6 sessions of probability mass. It is not 13 equally weighted days.
The worst 13 losses, largest first:

```text
{chr(10).join(f"{x:.18f}" for x in worst)}
```

Task: (sum of the first 12 + 0.6 × the 13th) ÷ 12.6.

Your answer: ____________________

## E. GFC endpoint return at the current target

Dates: 9 October 2007 to 9 March 2009, buy and hold. Task: multiply each target weight by its cumulative
return and add them up. Then give the USD result on $10,000,000.

| ETF | Current target | Cumulative return |
|---|---:|---:|
{rows([[t, f"{target[t]:.10f}", f"{cumulative[t]:.10f}"] for t in returns.columns])}

Your answer: ____________________  USD: ____________________

## F. Return hurdle

Convention: 1 + R − spending − additional fee = (1 + inflation) × (1 + real growth).
Inputs: spending 4%, fee 0.25%, inflation 2.5%, real growth 0%.

Your answer: ____________________
"""
    (PACK / "01_CALCULATION_WORKSHEET.md").write_text(worksheet, encoding="utf-8")

    key = f"""# Expected answers: AI-PREPARED

**Reading this file is not performing a calculation.** These answers were computed by AI from the frozen
inputs. Use them only to compare with an answer you have already produced on your own.

| Item | Expected fraction | As percent | Compare with |
|---|---:|---:|---|
{rows([list(row) for row in answers])}

Evaluation drawdown dates: peak {peak_day.date()}, trough {trough_day.date()}.
GFC endpoint on USD 10,000,000: ${-float(target @ cumulative) * 1e7:,.2f} loss. This is not the replay's deeper
drawdown of about 23.87%, which comes from the daily path.

Small differences in the last digits are expected from rounding. Record any larger difference as a finding.
"""
    (PACK / "02_ANSWER_KEY_AI_PREPARED.md").write_text(key, encoding="utf-8")

    questions = """# Can you explain it?

Answer aloud or in writing, in your own words, without notes. These test understanding. A wrong or
uncertain answer is a useful finding, so record it.

## The decision

1. Why is the proposal ADJUST, and not ACCEPT or REJECT?
2. Which three things must the committee settle before capital is committed?
3. Which assumptions did the team choose, and which came from the official brief?
4. Why does showing only the evaluation period flatter the rule?
5. Why is the 6.75% hurdle not a forecast? What would you do if the committee used 5% spending?
6. Why does a 2.19% cash yield not simply add to a 7.63% return?
7. What is the difference between this team's assessment and approval by a real investment committee?

## The measurement

8. What does a one-day ES of 2.03% mean, and what does it not mean?
9. Why are the excesses of about $3,950 and $3,169 not precise breaches?
10. Why does Normal Monte Carlo agree with parametric Normal, and why is that not a fat-tail test?
11. Why is pure POT unavailable at 90%? How is the hybrid different?
12. Why does a positive fitted shape not by itself reject the Gaussian?
13. Why can the GFC endpoint be −8.93% when the drawdown is −23.87%?

## The validation

14. What do Kupiec and Christoffersen each test?
15. Why does a green Basel light not erase the full-history rejection?
16. Why were two selection-period Basel blocks red, and what does that teach?
17. How can every monthly target respect a cap while holdings passed it on 2,771 sessions?
18. Why is a current-target crisis replay not an investable historical record?
19. What had the team already seen before the rule was registered?

## The limits

20. Name three things the analysis does not capture, and how each could change the decision.
21. Which risk-free dates are inferred or unresolved, and does that matter here?
22. What did AI do in this project, and what did a person check?
"""
    (PACK / "03_UNDERSTANDING_QUESTIONS.md").write_text(questions, encoding="utf-8")

    form = """# Human review form

Complete one form per reviewer. Leave a field blank if the work was not done. Do not fill this in for
someone else. Do not copy from the answer key. Status stays PENDING until a real person records real work.

| Field | Entry |
|---|---|
| Reviewer's real name | |
| Date and time | |
| Role in the team | |

## Calculations

| Item | File and dates checked | Method used | Your result | Reference | Difference | Finding |
|---|---|---|---|---|---|---|
| A. One-day return | | | | | | |
| B. Evaluation drawdown | | | | | | |
| C. Normal VaR 99% | | | | | | |
| D. Historical ES 99% | | | | | | |
| E. GFC endpoint | | | | | | |
| F. Hurdle | | | | | | |

## Review

| Topic | What you checked | Finding |
|---|---|---|
| Mandate assumptions and budgets | | |
| Model assumptions and unavailable outputs | | |
| App launched and controls used | | |
| Memo, tear sheet and recommendation read | | |
| Understanding questions answered | | |

## Decision on the team's proposal

This records the team's own assessment of its competition proposal. It is not approval by a university
investment committee.

- [ ] Agree with the proposal
- [ ] Agree with changes (describe below)
- [ ] Disagree (describe below)

Reasons and required changes:



Signature: ______________________________  Date: ______________
"""
    (PACK / "04_REVIEW_FORM.md").write_text(form, encoding="utf-8")

    readme = f"""# Human review pack

{NOTICE}

Status: **PENDING**. Nothing in this folder records a completed review.

1. Launch the app and read the recommendation and memo.
2. Work through `01_CALCULATION_WORKSHEET.md` on your own.
3. Only then compare with `02_ANSWER_KEY_AI_PREPARED.md`.
4. Discuss `03_UNDERSTANDING_QUESTIONS.md` without notes.
5. Complete `04_REVIEW_FORM.md` with your real name, date, method and findings.
6. Update `submission/VALIDATION_CHECKLIST.md` and `AI_DISCLOSURE.md` with only what was actually done.

A general instruction to an AI to "do the review" is delegation, not an independent human review. If a
person supplies a real review later, record only the actions and findings they state.
A printable version is in `submission/human_review/human_review_pack.pdf`.
"""
    (PACK / "README.md").write_text(readme, encoding="utf-8")

    def tex_rows(items: list[list[str]]) -> str:
        return "\n".join(" & ".join(r) + r" \\" for r in items)

    (LATEX / "review_inputs.tex").write_text(
        "\n".join(
            [
                r"\newcommand{\qeReviewTableA}{" + tex_rows([[t, f"{held[t]:.10f}", f"{day_returns[t]:.10f}".replace("-", "\N{MINUS SIGN}")] for t in returns.columns]) + "}",
                r"\newcommand{\qeReviewTableE}{" + tex_rows([[t, f"{target[t]:.10f}", f"{cumulative[t]:.10f}".replace("-", "\N{MINUS SIGN}")] for t in returns.columns]) + "}",
                rf"\newcommand{{\qeReviewMean}}{{{mean_loss:.17f}}}".replace("-", "\N{MINUS SIGN}"),
                rf"\newcommand{{\qeReviewStd}}{{{std_loss:.17f}}}",
                r"\newcommand{\qeReviewWorst}{" + r", ".join(f"{x:.10f}" for x in worst) + "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("Human review pack written; status remains PENDING")


if __name__ == "__main__":
    main()
