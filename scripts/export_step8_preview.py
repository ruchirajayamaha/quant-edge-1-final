"""Render saved Step 8 results and methodology; no financial engine in presentation."""

from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tmp/figure_export_deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT=ROOT/'results/step8_risk_stress_preview'
AUTHORITY=OUT/'step8_results.json'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def md(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |',
                      *['| '+' | '.join(str(v).replace('|','/') for v in row)+' |' for row in rows]])


def f(x,scale=1,digits=4):return 'N/A' if x is None else f'{x*scale:.{digits}f}'


def methodology(data):
    parts=['# Step 8 — Risk contributions, feasible sizing and stress evidence',
           '**DEVELOPMENT RESEARCH / EX-POST SCENARIOS; human mandate decisions and independent validation PENDING.**',
           'Generated from `results/step8_risk_stress_preview/step8_results.json`. The initial portfolio is the frozen terminal-development exposure, not a newly selected current recommendation. No post-2016 strategy performance was computed. COVID/2022 are explicitly ex-post fixed-allocation stress replays.',
           '## Risk allocation convention',
           'For Normal loss risk `rho(w)=-mu@w+k*sqrt(w@Sigma@w)`, the marginal is `-mu+k*(Sigma@w)/sigma`; k is the Normal quantile for VaR or Normal density divided by tail mass for ES. Component risk is weight times marginal risk. Shared moments use ddof=1, and the mean term is retained. Historical ES marginal risk is the shared exact-tail-weight average of negative asset returns; boundary ties give a subgradient. Components sum to the un-clipped signed total. Negative hedges remain negative; percentages are fractions of total risk and are unavailable for nonpositive/near-zero totals. At zero portfolio volatility with risky individual assets, the gradient is undefined rather than fabricated.',
           '## Practical sizing convention',
           'Five candidate targets were recorded before outcomes, with two labelled unconstrained references. No cash is introduced, constraints are not relaxed, and no candidate is automatically selected. Expected-return proxy is 252 times the same-window arithmetic sample mean, not a forward expected return, geometric/net/real spending result or promise. Risk is Historical 99% one-day pre-cost VaR/ES. The return-risk ratio is explicitly annual arithmetic return-proxy sacrifice divided by daily ES reduction; it is a scale comparison mixing stated horizons, not a Sharpe ratio. Ratios are N/A when risk does not fall. Null human risk limits remain PENDING, not automatically met.',
           '## Stress conventions and rationale',
           'Historical replay starts at wealth 1, includes the first stored close-to-close return, compounds each asset separately and lets holdings drift. No daily rebalancing or transaction costs are imposed. Drawdown includes initial wealth; asset P&L sums to total P&L. Exact NYSE-session coverage is required. Signed USD loss is negative for a scenario gain. These are ex-post scenario replays and do not imply those weights were held during the crisis.',
           'GFC represents joint equity/liquidity stress; COVID represents a rapid liquidity shock; 2022 represents equity/duration repricing. Dates are configured team assumptions. The provisional hypothetical vector combines equity and duration losses with gold/energy gains: SPY/EFA/EEM -25%, AGG -12%, GLD +10%, XLE +20%, XLK -30%. Energy and technology differ deliberately from broad equities. Joint signs/magnitudes are assumptions, not a fitted joint distribution. Duration/probability is unspecified. Daily development extrema provide scale context only and do not calibrate a multi-day repricing scenario. A deterministic scenario loss is not ES.',
           '## Computed results']
    for win,run in data['windows'].items():
        parts += [f"### {win}: {run['sample_start']} to {run['sample_end']}, N={run['n_obs']}",
                  'Baseline 99% Euler allocations (component units: bps of NAV; percentages can be negative or exceed 100% for hedges):']
        contrib=[r for r in run['contributions'] if r['confidence']==.99]
        parts.append(md(['Method','Ticker','Weight (%)','Marginal (fraction)','Component (bps)','Share (%)','Total (bps)','Status'],
            [[r['method'],r['ticker'],f(r['weight'],100),f(r['marginal_risk'],1,8),f(r['component_risk'],10000),f(r['pct_contribution'],100),f(r['total_risk'],10000),r['status']] for r in contrib]))
        parts += ['Candidate table; positive risk reduction is relative to the baseline:',
                  md(['Candidate','Constraint feasible','HS VaR99 (%)','HS ES99 (%)','Annual return proxy (%)','ES reduction (bps)','Annual proxy sacrifice (pp)','Risk-limit status'],
                    [[r['candidate_id'],r['constraint_feasible'],f(r['var_loss'],100),f(r['es_loss'],100),f(r['expected_annual_return_proxy'],100),f(r['reduction_es_loss'],10000),f(r['annual_return_proxy_sacrificed'],100),r['risk_limits_status']] for r in run['allocations']])]
    parts += ['## Historical and hypothetical comparison',md(['Portfolio','Scenario','Start','End','Total return (%)','Max drawdown (%)','Worst day/step (%)','USD loss','Status'],
        [[r['portfolio_id'],r['scenario_id'],r['start_date'] or 'one step',r['end_date'] or 'unspecified horizon',f(r['total_return'],100),f(r['max_drawdown'],100),f(r['worst_day_return'],100),f(r['usd_loss'],1,2),r['status']] for r in data['stress_results']]),
        'For the hypothetical row, max drawdown means only initial-to-final one-step decline and worst day/step is the stipulated step; no within-step path or daily horizon is inferred.',
        '## Decision and monitoring evidence',
        'The default equity cap forces at least 65% AGG+GLD and, with 40% per fund, at least 25% in each. This narrow feasible set does not prove capital safety. Income/spending, inflation, fee and real-growth choices remain pending; do not infer ACCEPT/ADJUST/REJECT from this sizing table alone. Candidate comparisons use the existing windows without selecting friendlier constraints or tuning on evaluation outcomes.',
        md(['Metric','Threshold','Status','Action'],[[r['metric'],r['threshold'] if r['threshold'] is not None else 'PENDING',r['status'],r['action']] for r in data['monitoring']]),
        'Monitoring policy is proposed evidence for the team. Missing human thresholds must be completed before a final approved mandate claim; software data-quality triggers are separate from economic risk limits.',
        '## Hand-check and limitations',
        'With SPY/AGG 50/50 and daily returns (-20%,+10%), then (+10%,-10%), wealth is 0.95 then 0.935: asset-wise compounding gives 0.5*0.8*1.1+0.5*1.1*0.9. Resetting weights daily would instead give 0.95. This catches accidental constant-weight rebalancing. One-step shocks SPY -25%, AGG +10% give portfolio -7.5%, USD loss 7.5 on NAV100, with signed component P&L adding exactly.',
        'Normal moments/ES and historical tails are conditional on sample/exposure conventions. Step 6 dependence and Step 7 EVT uncertainty remain relevant. Historical stress has no calibrated future probability, trading/market impact model or guarantee. Target feasibility is distinct from continuously enforced holdings caps. The final app/report must ultimately share a frozen pipeline result bundle, not compute alternative values independently.',
        'Step 8 only; Step 9 integration, final selection/evaluation protocol, human decisions, app and submission work remain.']
    return '\n\n'.join(parts)+'\n'


def main():
    data=json.loads(AUTHORITY.read_text(),parse_constant=lambda t:(_ for _ in ()).throw(ValueError(t)))
    meta=data['metadata'];plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','svg.fonttype':'none'})
    figures=[]
    def save(fig,name,title,subtitle):
        fig.suptitle(title,fontsize=15,fontweight='bold',y=.98)
        fig.text(.06,.91,subtitle,fontsize=8.5,color='#526475')
        fig.text(.06,.02,'DEVELOPMENT RESEARCH / EX-POST SCENARIOS | one-day pre-cost risk; frozen development exposure | human approval PENDING\n'
                 'Risk limits are unsigned; no recommendation selected. Computed JSON and source hashes: manifest.json.',fontsize=8,color='#526475')
        fig.savefig(OUT/(name+'.png'),dpi=300);fig.savefig(OUT/(name+'.svg'));plt.close(fig)
        figures.append((name,title))
    names=list(data['windows']);colors=['#147D73','#314C78','#CF6A32']
    fig,axes=plt.subplots(1,2,figsize=(13.5,6.8));fig.subplots_adjust(left=.075,right=.98,bottom=.20,top=.80,wspace=.25)
    for ax,win in zip(axes,names):
        run=data['windows'][win];x=np.arange(7)
        for j,method in enumerate(['normal_var','normal_es','historical_es']):
            rows=[r for r in run['contributions'] if r['confidence']==.99 and r['method']==method]
            ax.bar(x+(j-1)*.24,[r['component_risk']*10000 for r in rows],.24,label=method,color=colors[j])
        ax.axhline(0,color='#64748B',lw=.8);ax.set_xticks(x,['SPY','EFA','EEM','AGG','GLD','XLE','XLK']);ax.set_ylabel('Signed component risk (bps of NAV)')
        ax.set_title(('Recent' if 'recent' in win else 'Full development')+f" (N={run['n_obs']})",fontsize=11)
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axes[0].legend(fontsize=8)
    save(fig,'figure_01_risk_components','99% Euler risk contributions by asset','Recent 2011-12-29 to 2016-12-30; full 2005-01-04 to 2016-12-30 | negative hedge contributions retained')
    fig,ax=plt.subplots(figsize=(13.5,6.8));fig.subplots_adjust(left=.075,right=.98,bottom=.24,top=.80)
    scenario_ids=[s['scenario_id'] for s in data['scenarios']];portfolios=list(data['stress_attributions'])
    for j,portfolio in enumerate(portfolios):
        vals=[next(r for r in data['stress_results'] if r['scenario_id']==s and r['portfolio_id']==portfolio) for s in scenario_ids]
        xpos=np.arange(4)+(j-.5)*.34
        bars=ax.bar(xpos,[-100*r['total_return'] for r in vals],.34,color=colors[j],label='Frozen development min-variance' if j==0 else '60/40 reference')
        for bar,row in zip(bars,vals):
            val=-100*row['total_return'];ax.annotate(f"{val:.1f}%\n${row['usd_loss']/1000:,.0f}k",(bar.get_x()+bar.get_width()/2,val),xytext=(0,5 if val>=0 else -5),textcoords='offset points',ha='center',va='bottom' if val>=0 else 'top',fontsize=8)
    ax.set_xticks(np.arange(4),['GFC\n2007-10-09 – 2009-03-09','COVID\n2020-02-19 – 2020-03-23','Rate shock\n2022-01-03 – 2022-10-14','Hypothetical repricing\nOne step; duration unspecified'])
    ax.set_ylabel('Signed scenario loss (% of initial NAV)');ax.axhline(0,color='#64748B',lw=.8);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.legend(loc='upper right',fontsize=8);ax.margins(y=.25)
    save(fig,'figure_02_stress_comparison','Historical crisis replays and an illustrative joint shock','Buy-and-hold historical drift; no costs | initial NAV USD 10,000,000 | deterministic scenarios are not ES')
    fig,axes=plt.subplots(1,2,figsize=(13.5,7.5));fig.subplots_adjust(left=.20,right=.98,bottom=.20,top=.80,wspace=.32)
    labels=['Baseline min-var','Defensive 20/40/40','Equity cap 35/40/25','Balanced 30/35/35','Gold tilt 25/35/40']
    for ax,win in zip(axes,names):
        rows=data['windows'][win]['allocations'][:5]
        values=np.array([[r['weights']['SPY']*100,r['weights']['AGG']*100,r['weights']['GLD']*100,r['es_loss']*100,r['expected_annual_return_proxy']*100] for r in rows])
        # A table preserves independent column units; color is used only for emphasis.
        ax.axis('off');table=ax.table(cellText=[[f'{v:.2f}' for v in row] for row in values],rowLabels=labels,
            colLabels=['SPY %','AGG %','GLD %','ES99 %/day','Return proxy\n%/year'],loc='center',cellLoc='center')
        table.auto_set_font_size(False);table.set_fontsize(8);table.scale(1,2)
        for (row,col),cell in table.get_celld().items():
            cell.set_edgecolor('#CBD5E1')
            if row==0:cell.set_facecolor('#DCECE8')
        ax.set_title('Recent development' if 'recent' in win else 'Full development sensitivity',fontsize=11)
    save(fig,'figure_03_feasible_sizing','Five predeclared feasible allocation targets','ES: Historical 99%, one-day pre-cost | return proxy: same-window arithmetic sample mean × 252, not forward return')
    doc=methodology(data);(ROOT/'docs/sections/b_risk_budget_and_stress.md').write_text(doc,encoding='utf-8')
    (OUT/'README.md').write_text('# Step 8 risk/stress preview\n\n'+meta['scope']+'\n\nAuthority: step8_results.json. Figures and tables are derived from it. No portfolio winner or signed risk limit is inferred.\n\nReproduce: `.venv/Scripts/python.exe scripts/record_step8_results.py`, then `.venv/Scripts/python.exe scripts/export_step8_preview.py`.\n',encoding='utf-8')
    links=''.join(f'<h2>{html.escape(title)}</h2><img src="{name}.png" alt="{html.escape(title)}">' for name,title in figures)
    files=''.join(f'<li><a href="{p.name}">{p.name}</a></li>' for p in sorted(OUT.iterdir()) if p.suffix in ['.csv','.json'])
    (OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Step 8 risk and stress</title><style>body{font:16px system-ui;margin:32px;color:#182D43;max-width:1300px}img{width:100%}p{line-height:1.6}</style><h1>Step 8 — Risk contributions and stress evidence</h1><p>DEVELOPMENT RESEARCH / EX-POST SCENARIOS. Human validation and economic limits PENDING. Post-2016 scenarios use the frozen development exposure; these are not historical strategy results. </p>'+links+'<h2>Computed tables and provenance</h2><ul>'+files+'</ul>',encoding='utf-8')
    sources=['config.yaml','src/quantedge/contracts.py','src/quantedge/risk_budget.py','src/quantedge/stress.py','src/quantedge/var.py','src/quantedge/es.py','src/quantedge/portfolio.py','src/quantedge/returns.py','scripts/record_step8_results.py','scripts/export_step8_preview.py','docs/sections/b_risk_budget_and_stress.md']
    manifest={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'dataset_id':meta['dataset_id'],'config_hash':meta['config_hash'],
              'numerical_authority_json':'results/step8_risk_stress_preview/step8_results.json','numerical_authority_sha256':sha(AUTHORITY),
              'source_sha256':{n:sha(ROOT/n) for n in sources},'artifacts_sha256':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='manifest.json'}}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('Exported 3 PNG/SVG figures, HTML, methodology and final source/artifact manifest.')


if __name__=='__main__':main()
