# Defence rehearsal notes

Use the actual app and memo. These notes are AI-assisted preparation, not evidence
that any team member has rehearsed or understood the material.

## Suggested10-12 minute final-five pitch (conditional requirement)

1.0 min: conservative endowment, spending/real-capital problem, conditional ADJUST.
1.0 min: proposed mandate and explicit6.75% planning bridge; not a return forecast.
1.0 min: data alignment, retained flags, log/simple distinction, day-level RF limits.
1.5 min:504-session monthly min-variance rule, imposed caps and monthly drift.
1.0 min: matched development/selection/evaluation trade-offs; no post-hoc winner.
1.5 min: same-exposure VaR/ES models, Normal under-tail risk, POT domain and hybrid.
1.0 min:500-session forecasts, exception frequency and clustering; green is not approval.
1.0 min: GFC/COVID/2022/hypothetical; terminal loss versus trough; energy/gold components.
1.0 min: concrete spending/liquidity/risk-budget actions, limitations and human responsibility.
Keep remaining time for transitions; practise against an actual timer if selected.

## Questions each member should answer in their own words

- Why use log returns for statistical diagnostics but simple returns for portfolio P&L?
- Why are dividends not added again? Why does ending cash yield differ from total return?
- What does a 1-day ES of2.03% mean, and what does it not mean?
- Why does Normal Monte Carlo not automatically cure the thin-tail assumption?
- What happens at ξ=0, ξ≥1, negative ξ support, or fewer than50 exceedances?
- Why is pure full-history POT95 unavailable while the hybrid is labelled separately?
- How do fractional ES tail weights handle ties and a non-integer tail count?
- Where is the optimiser's training end relative to the realised return?
- How can every monthly target meet a cap but daily holdings violate it?
- Why can a small XLE weight carry a large ES contribution?
- Why can GFC terminal loss be small while scenario drawdown exceeds20%?
- How do all-N Kupiec and transition-conditioned Christoffersen likelihoods differ?
- Why do four last250 HS99 exceptions not erase earlier clustering failures?
- Why isn't evaluation CAGR a forward return promise or proof of sustainable4% spending?
- What prior full-history evidence was viewed before the registered strategy evaluation?
- Which exact human reviews did the team actually perform, and which remain open?

## Demo path

Launch `python scripts/launch.py`. Start Decision, then Performance/evaluation,
Tail risk/recent vs full/99%, Backtesting/HS vs Normal, Risk budget & stress,
and Assumptions & Limitations. Show a90% pure-POT unavailable result and a short
backtest range with unavailable Basel rather than pretending every control passes.
Avoid claiming hosted deployment, unseen human approval or guaranteed competition rank.
