"""LEGACY ReportLab documents, superseded by the LaTeX build in scripts/build_reports.py.

The submitted PDFs are compiled from report/latex/. This script is kept only to reproduce the earlier
accepted documents. It needs --legacy-reportlab and writes to output/legacy_reportlab/, so it cannot
replace a submitted PDF. Those earlier PDFs are archived in audit/presentation_review/.
"""
import sys

if '--legacy-reportlab' not in sys.argv:
    raise SystemExit('Superseded: run python scripts/build_reports.py. '
                     'Use --legacy-reportlab to reproduce the old ReportLab PDFs in output/legacy_reportlab/.')

import json
import math
import re
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/legacy_reportlab';OUT.mkdir(parents=True,exist_ok=True)
FIG=ROOT/'results/final/figures'
R=json.loads((ROOT/'results/final/reference.json').read_text())
font_dirs=[Path('C:/Windows/Fonts'),Path('/usr/share/fonts/truetype/dejavu')]
try:
    import matplotlib
    font_dirs.append(Path(matplotlib.get_data_path())/'fonts/ttf')
except ImportError:pass
font_dir=next((d for d in font_dirs if (d/'DejaVuSans.ttf').exists()),None)
if font_dir is None:raise RuntimeError('Install DejaVu Sans fonts or the optional matplotlib rendering package')
pdfmetrics.registerFont(TTFont('DejaVu',str(font_dir/'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DejaVuBold',str(font_dir/'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('DejaVu',normal='DejaVu',bold='DejaVuBold',italic='DejaVu',boldItalic='DejaVuBold')
BLUE=colors.HexColor('#163547');TEAL=colors.HexColor('#145c72');GOLD=colors.HexColor('#db8b39');LIGHT=colors.HexColor('#edf3f5')
S=getSampleStyleSheet()
S.add(ParagraphStyle(name='BodyX',fontName='DejaVu',fontSize=9.1,leading=14,spaceAfter=8,textColor=BLUE))
S.add(ParagraphStyle(name='SmallX',parent=S['BodyX'],fontSize=7.7,leading=11,spaceAfter=5))
S.add(ParagraphStyle(name='TitleX',parent=S['BodyX'],fontName='DejaVuBold',fontSize=25,leading=30,spaceAfter=15))
S.add(ParagraphStyle(name='HeadX',parent=S['BodyX'],fontName='DejaVuBold',fontSize=17,leading=22,spaceAfter=14))
S.add(ParagraphStyle(name='SubX',parent=S['BodyX'],fontName='DejaVuBold',fontSize=11,leading=16,spaceAfter=8))
S.add(ParagraphStyle(name='CellX',parent=S['BodyX'],fontSize=7.5,leading=10,spaceAfter=0))
S.add(ParagraphStyle(name='BadgeX',parent=S['BodyX'],fontName='DejaVuBold',fontSize=12,leading=18,textColor=TEAL,spaceAfter=12))

def p(text,style='BodyX'):
    # Keep prose spacing readable without changing link targets or hash strings.
    parts=re.split(r'(<[^>]*>)',text)
    for i in range(0,len(parts),2):
        parts[i]=re.sub(r'(?<=[,;])(?=\S)',' ',parts[i])
        parts[i]=re.sub(r'\b(during|through|above|below|versus|for|separate|horizon|spending|inflation|fee|of|after|before|additional|Historical)(?=\d)',r'\1 ',parts[i])
    return Paragraph(''.join(parts),S[style])
def percent(x,d=2):return 'N/A' if x is None else f'{x:.{d}%}'
def num(x,d=3):
    if x is None:return 'N/A'
    return f'{x:.1e}' if 0<abs(x)<.5*10**(-d) else f'{x:.{d}f}'
def dollars(x):return 'N/A' if x is None else f'${x:,.0f}'
def metric(period,portfolio,metric):
    return next(x['value'] for x in R['period_kpis'] if x['period']==period and x['portfolio_id']==portfolio and x['metric']==metric)
def risk(window,confidence,model):return next(x for x in R['risk_table'] if x['window_id']==window and x['confidence']==confidence and x['model']==model)
def context(kind,metric):return next(x['value'] for x in R['context'][kind]['min_variance'] if x['metric']==metric)
def table(rows,widths=None):
    t=Table([[p(escape(str(c)),'CellX') for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),LIGHT),('LINEBELOW',(0,0),(-1,0),1,TEAL),
       ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
       ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
       ('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#dce3e8'))]))
    return t
def image(name,h=190):
    from PIL import Image as PILImage
    path=FIG/(name+'.png');w,hh=PILImage.open(path).size
    width=min(503,h*w/hh);return Image(str(path),width=width,height=width*hh/w,hAlign='CENTER')
def footer(canvas,doc):
    canvas.setStrokeColor(TEAL);canvas.setLineWidth(.7);canvas.line(46,43,A4[0]-46,43)
    canvas.setFont('DejaVu',7);canvas.setFillColor(BLUE)
    canvas.drawString(46,30,'QUANT EDGE 1.0  |  Research as of 30 Oct 2026  |  Human validation PENDING')
    canvas.drawRightString(A4[0]-46,30,str(doc.page))
    canvas.setFont('DejaVuBold',7);canvas.drawString(46,A4[1]-31,'SERENDIB UNIVERSITY ENDOWMENT  /  INVESTMENT COMMITTEE RESEARCH')
def document(name,story,expected):
    path=OUT/name
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=46,leftMargin=46,topMargin=57,bottomMargin=56,
        title='Quant Edge - '+name.replace('_',' ').replace('.pdf',''),author='Quant Edge research submission',pageCompression=1)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    n=len(PdfReader(path).pages)
    if n!=expected:raise AssertionError(f'{name}: expected{expected} pages, got{n}')
    print(name,n,'pages')

def memo():
    story=[]
    def page(title,items):
        if story:story.append(PageBreak())
        story.extend([p(title,'HeadX'),*items])
    hs=risk('recent',.99,'historical');full=risk('full_history',.99,'historical')
    evc=metric('evaluation','min_variance','geometric_annual_return');evdd=metric('evaluation','min_variance','max_drawdown')
    page('01 / Preserve capital. Fund the mission.',[
      p('CONDITIONAL ADJUST','BadgeX'),p('USD 10 million endowment<br/>Investment committee memo','TitleX'),
      p('Retain the constrained minimum-variance rule as a candidate, but adjust the spending / liquidity plan and obtain approval of explicit loss budgets before implementation. Lower observed volatility does not eliminate concentrated exposures, tail risk or funding uncertainty.'),
      table([['Evaluation: 4 Jan 2021 - 30 Oct 2026','Observed result'],['Net annual growth',percent(evc)],['Annual volatility',percent(metric('evaluation','min_variance','annualized_volatility'))],['Maximum drawdown',percent(evdd)],['Current HS99 one-day ES',percent(hs['es_loss'])+' / '+dollars(hs['es_usd'])],['Full-history exposure HS99 ES',percent(full['es_loss'])+' / '+dollars(full['es_usd'])]],[325,178]),
      Spacer(1,14),p('The decision in three points','SubX'),
      p('<b>Funding:</b> the proposed 6.75% nominal hurdle is below the observed evaluation CAGR, but that historical margin is not a reliable forecast or a sequence-safe spending guarantee.'),
      p('<b>Loss budget:</b> current HS VaR99 and ES99 marginally exceed the proposed 1.5% and 2% limits; full-history tails and crisis drawdowns are materially worse. Limits must not be relaxed merely to manufacture acceptance.'),
      p('<b>Governance:</b> approve the mandate assumptions, the treatment of monthly weight drift and the response to clustered exceptions. Independent human review remains pending; automated checks are not a sign-off.'),
      p('All figures are derived from the frozen r3 dataset and the unchanged registered portfolio rule. No strategy switch or threshold retuning follows from evaluation results. Bundle '+R['metadata']['bundle_id']+'.','SmallX')])
    page('02 / A mandate that can be evaluated',[
      p('The official challenge specifies the USD 10M conservative endowment and seven-ETF universe; it leaves teams to set the horizon, objective and numerical risk budgets. The following are team-proposed planning assumptions, not facts supplied by the organiser or client.'),
      table([['Planning choice','Team proposal'],['Horizon / review','10 years; quarterly review; monthly scheduled rebalance'],['Spending / inflation','4.00% of beginning-year NAV / 2.50% annual assumption'],['Additional mandate fee','0.25%; distinct from embedded ETF fund expenses'],['Desired real growth','0%; preserve purchasing power after spending'],['Cash-flow convention','End-year spending / fee deductions measured against beginning-year NAV']],[160,343]),
      Spacer(1,12),p('Return bridge','SubX'),p('<b>1 + R - spending - fee = (1 + inflation) × (1 + real growth)</b><br/>At zero real growth: R = 4.00% + 0.25% + 2.50% = <b>6.75%</b>. This is a planning hurdle. No probability of achieving it is asserted. Daily return paths include trading costs, but do not deduct endowment spending or this additional fee.'),
      table([['Proposed review budget','Fraction of NAV','USD at $10M'],['Daily Historical VaR95','1.00%','$100,000'],['Daily Historical VaR99','1.50%','$150,000'],['Daily Historical ES99','2.00%','$200,000'],['Annual volatility','10.00%','Not a one-day loss limit'],['Drawdown / scenario terminal loss','20.00% each','$2,000,000']],[220,110,173]),
      Spacer(1,12),p('Decision rule','SubX'),p('Conditional ADJUST applies while tail budgets, income / spending feasibility, concentration or human governance remain unresolved. A review threshold is not a guarantee that losses stop there. Cash reserves, off-universe hedges and automatic daily clipping are not silently introduced.')])
    page('03 / Data quality is part of the result',[
      table([['Input','Frozen scope / treatment'],['ETF market history','SPY, EFA, EEM, AGG, GLD, XLE, XLK; Yahoo Finance via yfinance'],['Prices / returns','5,492 NYSE prices, 3 Jan 2005 - 30 Oct 2026; 5,491 one-session returns from 4 Jan 2005'],['Adjusted price basis','Dividend/split-adjusted Close, auto_adjust=True; no extra dividend return added'],['Risk-free proxy','FRED DTB3; versioned r3 values and day-level availability; primary (quote/100)/252'],['Income / inflation','Separate split-adjusted dividends / non-dividend-adjusted prices; FRED CPIAUCSL context'],['Reproducibility','SHA-256 verified snapshots and manifests; offline load; raw inputs retained']],[145,358]),
      Spacer(1,12),p('Alignment and outliers','SubX'),p('All seven ETFs match the expected NYSE session grid without missing price cells. The first price is an anchor, not a zero return. Missing adjacent intervals are invalidated rather than bridged or forward-filled. The original quality audit retained all 307 flags: 188 large negatives, 101 robust-MAD jumps and 18 heuristic structural-break candidates. Overlapping flags are not separate deleted observations.'),
      p('Statistical conventions','SubX'),p('Log returns support asset statistics, ADF checks and correlation diagnostics. Simple returns are used for self-financing portfolio P&amp;L, compounding, dollar losses and tail models because these require exact arithmetic aggregation. Asset and strategy ADF tests reject a unit-root null; this does not establish independent observations or constant volatility.'),
      p('Availability caveats','SubX'),p('DTB3 is a discount-basis annual quote [1], not a realised trading return. r3 uses eligible observation versions as well as availability dates; older revisions cannot displace newer eligible observations. Exact intraday release hours remain unverified. There are inferred later vintages, a sparse-era calendar fallback and two unresolved observations. /252 stays primary; 91-day accrual is a sensitivity. CPI is revised ex-post context and never a trading signal.'),
      p('Dataset '+R['metadata']['dataset_id']+'<br/>Config SHA-256 '+R['metadata']['config_hash'],'SmallX')])
    page('04 / Construction: constraints have consequences',[
      p('The unchanged rule minimises sample portfolio variance using the previous 504 sessions, sample covariance (ddof=1), long-only full investment and monthly targets. Weights used for session t are known before that session’s return. Five basis points are charged per sum of absolute traded weights; net wealth compounds the cost-adjusted returns.'),
      table([['Target constraint','Consequence'],['Each ETF ≤40%','No single target dominates beyond 40%'],['Equity group ≤35%','At least 65% jointly in AGG and GLD'],['AGG / GLD implied bounds','Each 25%-40% at target; not a promise of positive returns'],['Defensive group ≥40%','Redundant with the stricter equity cap, retained transparently'],['Constraint scope','Rebalance targets only; natural drift is monitored, not clipped']],[170,333]),
      Spacer(1,8),image('06_weights_risk_budget',175),
      p('Prospective target estimated through the frozen final close. It is not the last session’s pre-return holdings or an instruction already executed. The current XLE position is an optimiser outcome, not an explicit macro forecast. Rebalancing and solver records are exported.'),
      p('Protocol integrity','SubX'),p('Commit 782ec20 records the rule and proposed mandate before post-2016 strategy outcomes. Development ends in 2016; selection covers 2017-2020; evaluation begins in 2021. No selection-period winner is chosen. Prior whole-history asset EDA, RF research and fixed-exposure stress inspection were already available, so this is registered-rule evaluation rather than a pristine blinded experiment. Equal weight and 60/40 are references and may violate the candidate’s mandate constraints.')])
    rows=[['Period / portfolio','CAGR','Volatility','Max DD','Sharpe']]
    for period in ['development','selection','evaluation']:
      for key,label in [('min_variance','Min variance'),('equal_weight','Equal weight'),('benchmark_60_40','60/40')]:
        rows.append([period.title()+' / '+label,percent(metric(period,key,'geometric_annual_return')),percent(metric(period,key,'annualized_volatility')),percent(metric(period,key,'max_drawdown')),num(metric(period,key,'sharpe_ratio'))])
    page('05 / Results: preserve the comparison, not the story',[
      image('01_wealth_drawdown',220),table(rows,[175,80,80,85,83]),Spacer(1,8),
      p('Active paths begin 5 Jan 2007 after 504-session warmup and end 30 Oct 2026. All three use the same monthly execution / cost conventions. The constrained rule reduces volatility and drawdown relative to 60/40 over these samples, but earns less than equal weight in evaluation. We retain this trade-off rather than selecting the highest realised return after observing it. Drawdown includes initial wealth 1.0.','SmallX')])
    kp=[['Full active history metric','Min variance','60/40 reference']]
    ratio={'sharpe_ratio','sortino_ratio','capm_beta','treynor_ratio','information_ratio','calmar_ratio'}
    for m in ['geometric_annual_return','arithmetic_annual_return','annualized_volatility','sharpe_ratio','downside_deviation','sortino_ratio','capm_beta','jensen_alpha','treynor_ratio','tracking_error','information_ratio','max_drawdown','calmar_ratio']:
      fn=num if m in ratio else percent
      kp.append([m.replace('_',' ').title(),fn(metric('full','min_variance',m)),fn(metric('full','benchmark_60_40',m))])
    income=context('distribution_income','ending_trailing_12m_distribution_yield')
    real=context('ex_post_real_returns','ex_post_real_annual_return_common_months')
    page('06 / Return is not the same as spendable income',[
      table(kp,[245,129,129]),Spacer(1,10),p('CAPM / KPI interpretation','SubX'),p('CAPM beta and Jensen alpha use SPY excess returns against day-aligned r3 RF. Tracking error and information ratio use net monthly-rebalanced 60/40. Alpha is an in-sample regression statistic, not proof of persistent skill. Ratios with zero / unidentified denominators remain unavailable. Sortino uses the RF daily target and all observations.'),
      p('Income and purchasing power','SubX'),p('The primary path’s ending trailing-12-month cash distribution yield is '+percent(income)+', below proposed 4% spending. A pure distribution-funded policy would therefore require an adjustment; total-return spending requires asset sales and a liquidity plan. Distributions are already embedded in adjusted returns and are never added twice.'),
      p('Endpoint-CPI real annual growth is '+percent(real)+' before endowment spending over 236 contiguous completed months, Feb 2007-Sep 2026. Missing October 2025 / following monthly changes do not invalidate endpoint growth, but prevent a complete intermediate monthly inflation series. October 2026 CPI was unreleased. The nominal and real intervals differ; do not subtract figures from unmatched windows. Historical purchasing-power gains do not guarantee future funding.')])
    tr=[['Sample / model','Confidence','VaR','ES','ES USD']]
    for wid,cs in [('recent',(.95,.99)),('full_history',(.99,))]:
      for c in cs:
        for model,label in [('historical','Historical'),('parametric_normal','Normal'),('monte_carlo_normal','MC Normal'),('evt_pot','POT-GPD')]:
          x=risk(wid,c,model);tr.append([('Recent' if wid=='recent' else 'Full')+' / '+label,percent(c,0),percent(x['var_loss']),percent(x['es_loss']),dollars(x['es_usd'])])
    page('07 / Tail loss: Normal is a useful reference, not protection',[
      image('03_tail_model_comparison',190),table(tr,[170,65,80,80,108]),Spacer(1,8),
      p('All estimates use one-day pre-cost simple losses at the same prospective target weights and matched sample / confidence. Historical VaR uses an empirical quantile; ES allocates exactly the requested tail probability, including fractional / tied boundary mass. Normal VaR/ES retain the estimated mean and sample volatility. Monte Carlo uses 25,000 seeded Normal scenarios and differs through sampling, not a richer tail model.','SmallX'),
      p('Current recent HS99 VaR exceeds its proposed limit by '+dollars((hs['var_loss']-.015)*1e7)+' and ES99 by '+dollars((hs['es_loss']-.02)*1e7)+'. These small exceedances are not statistically precise cliffs. Full-history ES99 is much higher; recent 1,260 sessions omit GFC and COVID.','SmallX')])
    er=[['Sample / threshold','Excesses','Shape ξ','Scale β','Status']]
    for d in R['evt_diagnostics']:
      er.append([('Recent' if d['window_id']=='recent' else 'Full')+' / '+percent(d['candidate_quantile'],1),d['n_exceedances'],num(d['xi']),num(d['beta'],5),d['status']])
    page('08 / EVT: show where extrapolation begins',[
      p('Peaks over threshold fits a Generalised Pareto distribution to strict loss excesses with location fixed at zero. The predeclared 95% threshold balances tail relevance against sample size; the threshold is not lowered to rescue a failed fit. Minimum strict excess count is 50. The empirical boundary is 1 - Nᵤ/N, which can differ from the requested quantile because of ties.'),
      table(er,[190,65,75,85,88]),Spacer(1,10),p('Diagnostics and limits','SubX'),p('Mean residual life, shape and modified scale β - ξu are exported for the 90%, 92.5%, 95% and 97.5% candidates. Recent 97.5% has only 31 strict excesses, so its fit is unavailable. The recent 95% fit has ξ='+num(next(d['xi'] for d in R['evt_diagnostics'] if d['window_id']=='recent' and d['candidate_quantile']==.95))+'. Positive shape by itself does not reject a Gaussian model or prove a stable tail law. Fits and asymptotic standard errors do not remove volatility dependence.'),
      p('For confidence c in the fitted tail, VaR = u + β/ξ × [(pᵤ/(1-c))^ξ - 1], with the exponential limit at ξ = 0. ES = (VaR + β - ξu)/(1-ξ) when ξ &lt; 1. ξ ≥ 1 makes the first moment unavailable. Negative ξ requires respecting the finite upper support. These implementation checks follow the GPD support convention [2].'),
      p('Pure POT at 90% is unavailable rather than pretending that body quantiles are tail extrapolations. An explicitly separate empirical-body / GPD-tail hybrid supports body VaR and integrates its ES over the empirical body plus fitted tail. At full-history 95%, the actual boundary exceeds 95% slightly, so pure POT is unavailable there too; hybrid 95% remains labelled separately.'),
      p('Development-only uncertainty evidence','SubX'),p('Step7 includes fixed-seed moving-block bootstrap tail sensitivity and QQ/PP diagnostics. Some pure-POT 95% bootstrap intervals failed the minimum successful-replication rule and remain unavailable; hybrid intervals are separate. Those earlier development-exposure intervals are not relabelled as uncertainty bands for this new current target. No rolling EVT calibration is claimed.')])
    bt=[['Scope / model / c','N / exceptions','UC p','IND p','CC p']]
    for period in ('full','evaluation'):
      for model,label in [('historical','HS'),('parametric_normal','Normal')]:
       for c in (.95,.99):
        x=next(x for x in R['coverage_summary'] if x['period']==period and x['model']==model and x['confidence']==c)
        bt.append([period.title()+f' / {label} {c:.0%}',str(x['n_valid'])+' / '+str(x['n_exceedances']),num(x['p_uc'],4),num(x['p_ind'],4),num(x['p_cc'],4)])
    page('09 / Backtesting: count and sequence both matter',[
      image('04_rolling_exceptions',175),table(bt,[180,100,74,74,75]),Spacer(1,8),
      p('Each forecast uses 500 sessions strictly before target t and the actual pre-return portfolio weights. Realised gross loss is -(w_before[t] dot r[t]). An exception requires loss &gt; VaR (equality is not an exception). Date controls select targets without deleting warmup. HS is primary; Normal is the fixed comparison. No rolling MC or EVT results are asserted.'),
      p('Kupiec tests unconditional exception frequency on all valid N. Christoffersen IND tests first-order clustering. CC combines IND with transition-conditioned UC; each contiguous run’s first state is conditioned out. Disconnected valid runs withhold CC. Asymptotic p-values, sparse cells and low power limit conclusions; non-rejection is not safety.'),
      p('The final 250 sessions (3 Nov 2025-30 Oct 2026) contain <b>4 HS99 exceptions: green</b>, versus <b>9 Normal99 exceptions: yellow</b>. This educational Basel-style diagnostic [3] is not regulatory approval. It does not erase full-history HS99 frequency / independence rejection, nor Normal99 evaluation rejection. Evaluation HS99 is less concerning at these tests, while HS95 evaluation independence still rejects.')])
    st=[['Portfolio / scenario','Total return','Max drawdown','Terminal USD loss']]
    names={'gfc_2007_2009':'GFC','covid_2020':'COVID','rate_shock_2022':'2022 rates','hypothetical_stagflation_repricing':'Hypothetical'}
    for x in R['stress_results']:
      st.append([('Min variance' if x['portfolio_id']=='min_variance' else '60/40')+' / '+names[x['scenario_id']],percent(x['total_return']),percent(x['max_drawdown']),dollars(x['usd_loss'])])
    page('10 / Stress: a terminal recovery can hide a deep trough',[
      image('05_stress_replay',180),table(st,[180,90,105,128]),Spacer(1,9),
      p('Historical windows are GFC 9 Oct 2007-9 Mar 2009, COVID 19 Feb-23 Mar 2020 and rates / inflation 3 Jan-14 Oct 2022. Each replay buys and holds today’s same initial target weights through the asset history. It is an ex-post exposure diagnostic, not the historical monthly strategy. Per-asset P&amp;L and daily paths are available in the stress engine.'),
      p('The candidate’s GFC terminal loss is modest relative to its within-window drawdown. Drawdown includes starting NAV; it cannot be replaced by endpoint return. Current-target GFC drawdown breaches the proposed 20% review threshold even when terminal loss does not.'),
      p('The hypothetical joint repricing shocks are SPY/EFA/EEM -25%, AGG -12%, GLD +10%, XLE +20% and XLK -30%. Its duration and probability are unassigned. Positive gold / energy shocks are assumptions, not guaranteed hedges. Never compare this one-step repricing with daily ES as if they share a horizon.')])
    rc=[['ETF','Current target','ES99 share']]
    for x in R['risk_contributions']['historical_es']:
      rc.append([x['ticker'],percent(x['weight']),percent(x['pct_contribution'])])
    page('11 / From risk decomposition to a review action',[
      table(rc,[130,170,203]),Spacer(1,10),p('Euler decomposition','SubX'),p('Normal marginal VaR / ES include the mean term; Historical ES uses the same exact fractional tail mass as portfolio ES. Components sum to total risk, including signed hedging contributions. Percentages are unavailable when total risk is non-positive; they are not forced to sum meaningfully around zero.'),
      p('The 14.61% XLE target contributes about '+percent(next(x['pct_contribution'] for x in R['risk_contributions']['historical_es'] if x['ticker']=='XLE'))+' of recent HS99 ES. Gold also has a substantial tail component despite its defensive label. A small nominal weight is not the same as a small risk budget. Allocations at the same exposure and sample are compared with constraint violations and proposed loss-limit status, not a backfit winner.'),
      p('Drift is a policy issue','SubX'),p('Across the full active path, '+str(R['diagnostics']['drift']['n_breach_sessions'])+' of 4,987 pre-return sessions drift beyond at least one target cap. Maximum single-ETF exposure is '+percent(R['diagnostics']['drift']['max_exposures']['max_single_etf_weight'])+'. Targets remain controlled; continuous compliance is not claimed. The committee must approve whether natural drift is acceptable or a new policy is required, then validate any changed policy separately.'),
      table([['Trigger','Proposed response'],['HS99 ES >2% or VaR99 >1.5%','Review feasible redistribution and the risk budget; do not raise limits simply to pass'],['Drawdown >20% / crisis shortfall','Review spending, liquidity needs and ability to tolerate the loss path'],['Quarterly clustering test p<0.05','Investigate model dependence; consider a separately validated conditional-volatility extension'],['Target-cap drift / missing sessions','Escalate governance / data review; no silent clipping, filling or stale forecast substitution']],[190,313])])
    page('12 / Reproduce, challenge and defend',[
      p('What remains conditional','SubX'),p('Human mandate approval and independent validation remain PENDING. Assumptions about spending, additional fees, future inflation, loss tolerance and continuous constraint enforcement are proposed. Sample means, geometric growth, regression alpha and stress history are not forecasts. No liability cash-flow optimisation or guaranteed capital protection is claimed.'),
      p('The historical rule uses estimated covariance and approximate closing-price execution. Costs are a fixed turnover model; liquidity, market impact, tax, borrowing and intraday slippage are not fully modelled. References differ in mandate feasibility. Recent / full-window risk sensitivity is disclosed instead of hiding favourable sample choices.'),
      p('Reproducibility','SubX'),p('The repository includes the verified frozen inputs, exact pinned Python3.11 dependencies, pipeline, tests, actual CSV / JSON / PNG / SVG results and Streamlit app. Run <b>python scripts/launch.py</b> after installation. It opens the local dashboard without market-data downloads. Rebuild with scripts/build_final_results.py; figures and PDFs consume that persisted reference. Source versions and config hashes are embedded in results.'),
      p('AI disclosure and required human review','SubX'),p('Google Antigravity, Claude Code and OpenAI Codex materially assisted research, implementation, testing, analysis and report drafting; actual known tools and purposes are recorded in AI_DISCLOSURE.md. Automated tests do not substitute for the challenge’s independent team review. The team must evaluate the recommendation, verify representative calculations, understand the code and sign the validation checklist before certifying this as its own decision.'),
      p('Sources and primary references','SubX'),p('[1] Federal Reserve Board, DTB3 discount-basis Treasury quote, via FRED: <link href="https://fred.stlouisfed.org/series/DTB3" color="#145c72">fred.stlouisfed.org/series/DTB3</link>. Versioned evidence: ALFRED / archived H.15, paths and source URLs in data/reference/rf_evidence and audit/rf_research.'),
      p('[2] SciPy official GPD distribution / support documentation: <link href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.genpareto.html" color="#145c72">docs.scipy.org / scipy.stats.genpareto</link>. Installed package versions are pinned in requirements.txt.'),
      p('[3] Basel Committee (1996), supervisory backtesting framework: <link href="https://www.bis.org/publ/bcbs22.pdf" color="#145c72">bis.org/publ/bcbs22.pdf</link>. Educational traffic lights are distinguished from model approval.'),
      p('Market / context: Yahoo Finance via yfinance; FRED CPIAUCSL (<link href="https://fred.stlouisfed.org/series/CPIAUCSL" color="#145c72">series link</link>). Official competition requirements: Quant edge 1.0 Final Challenge 1.pdf, sections8-10. Full methodology, quality reports and evidence are in docs/sections and audit/. No proprietary data source is used.'),
      p('Decision: <b>CONDITIONAL ADJUST</b>. Preserve the rule as a candidate; resolve the funding, tail budget and governance questions before investing.','BadgeX')])
    document('investment_memo.pdf',story,12)

def tear():
    hs=risk('recent',.99,'historical')
    rows=[['Evaluation 2021-2026','Min variance','60/40 reference'],['CAGR',percent(metric('evaluation','min_variance','geometric_annual_return')),percent(metric('evaluation','benchmark_60_40','geometric_annual_return'))],['Annual volatility',percent(metric('evaluation','min_variance','annualized_volatility')),percent(metric('evaluation','benchmark_60_40','annualized_volatility'))],['Max drawdown',percent(metric('evaluation','min_variance','max_drawdown')),percent(metric('evaluation','benchmark_60_40','max_drawdown'))],['Sharpe',num(metric('evaluation','min_variance','sharpe_ratio')),num(metric('evaluation','benchmark_60_40','sharpe_ratio'))]]
    story=[p('Endowment decision / at a glance','HeadX'),p('CONDITIONAL ADJUST','BadgeX'),p('Retain the constrained rule as a candidate; resolve tail budgets, funding and human mandate approval before implementation.'),table(rows,[220,140,143]),Spacer(1,9),image('06_weights_risk_budget',160),
      table([['Risk / funding lens','Evidence'],['Proposed nominal hurdle','6.75% = spending4% + inflation2.5% + additional fee0.25%'],['Current recent HS99 VaR / ES',percent(hs['var_loss'])+' / '+percent(hs['es_loss'])],['Full-history current-target HS99 ES',percent(risk('full_history',.99,'historical')['es_loss'])],['Latest250 Basel99','HS:4 green; Normal:9 yellow; educational only'],['Cash income context','Ending path TTM distribution yield '+percent(context('distribution_income','ending_trailing_12m_distribution_yield'))+'; not sufficient alone for4% spending']],[195,308]),Spacer(1,9),
      p('Rule:504 prior sessions, monthly minimum variance, long-only; target ETF≤40%, equity≤35%, AGG+GLD≥40%. Drift is monitored, not clipped. Trading cost5bps per sum-absolute-trade-weight. Risk is one-day gross; performance is net of trading costs, before spending / additional fee.','SmallX'),
      p('Frozen r3 data through30 Oct2026; current weights are a prospective target, not already executed. References need not meet mandate caps. Registered rule unchanged after evaluation. Day-level RF and ex-post CPI limitations remain. AI materially assisted this work; independent human validation PENDING. Source-of-truth bundle '+R['metadata']['bundle_id']+'.','SmallX')]
    document('tear_sheet.pdf',story,1)

def recommendation():
    story=[p('Investment recommendation / section 8.6','HeadX'),p('CONDITIONAL ADJUST','BadgeX'),
      p('<b>Our proposed decision is to adjust the mandate implementation before committing capital.</b> Keep the seven-ETF universe and the constrained minimum-variance rule as a candidate. Do not treat lower historical volatility as a promise that this endowment can meet spending needs without painful losses.'),
      p('We propose a ten-year horizon,4% annual spending,2.5% inflation and a separate0.25% additional fee, with no desired real growth. Under the stated beginning-NAV deduction convention this implies a6.75% nominal planning hurdle. These are our planning assumptions, not numerical limits supplied by the organiser or the university.'),
      p('The unchanged rule earned '+percent(metric('evaluation','min_variance','geometric_annual_return'))+' a year during2021-2026, with '+percent(metric('evaluation','min_variance','annualized_volatility'))+' volatility and '+percent(metric('evaluation','min_variance','max_drawdown'))+' maximum drawdown. This is useful evidence of a return / loss trade-off, not a forecast. The cash distribution yield at the end of the historical strategy path was '+percent(context('distribution_income','ending_trailing_12m_distribution_yield'))+', so4% spending cannot be assumed to come entirely from distributions. A total-return spending policy would need planned sales and liquidity.'),
      p('The candidate does not cleanly pass our proposed tail budgets. At the current prospective target, recent Historical99% daily VaR is '+percent(risk('recent',.99,'historical')['var_loss'])+' versus a1.5% budget, and ES is '+percent(risk('recent',.99,'historical')['es_loss'])+' versus2%. Full-history ES rises to '+percent(risk('full_history',.99,'historical')['es_loss'])+'. The current-target GFC replay also shows a drawdown beyond20%, even though its terminal loss is smaller. Limits must not be raised simply to make the candidate pass.'),
      p('Before implementation, the committee should approve spending and loss tolerances, assess a feasible redistribution within the allowed universe, and decide whether monthly target caps may drift between rebalances. Current energy and gold exposures carry substantial tail risk. Any modified rule must be evaluated separately; we have not switched strategies after seeing the evaluation results.'),
      p('Review the portfolio quarterly and rebalance on the scheduled monthly rule. Escalate daily ES99 above2%, drawdown above20%, target-cap drift, missing data and clustered exceptions. The latest HS99 educational Basel light is green with four exceptions, but longer-history clustering concerns remain. A green light is not model approval.'),
      p('<b>This is an AI-assisted draft recommendation awaiting independent human evaluation and committee approval.</b> The team must verify the supporting evidence and be able to explain and defend it. We do not claim exact intraday point-in-time data, guaranteed capital protection or assured spending sustainability. The full memo, tests and evidence state the remaining limitations.')]
    document('recommendation.pdf',story,1)

if __name__=='__main__':memo();tear();recommendation()
