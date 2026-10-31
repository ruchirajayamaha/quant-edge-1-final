"""Render actual final tables, never substitute synthetic series."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tmp/figure_export_deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import pandas as pd
from quantedge.reference import load_reference

OUT=ROOT/'results/final/figures';OUT.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                     'figure.facecolor':'white','axes.labelcolor':'#163547','text.color':'#163547','axes.titleweight':'bold'})
COLORS=['#145c72','#db8b39','#7b8193'];LABELS={'min_variance':'Constrained min variance','equal_weight':'Equal weight reference','benchmark_60_40':'60/40 reference'}
def save(fig,name):
    fig.savefig(OUT/f'{name}.png',dpi=300,bbox_inches='tight');fig.savefig(OUT/f'{name}.svg',bbox_inches='tight');plt.close(fig)

def main():
    ref=load_reference();daily=pd.read_csv(ROOT/'results/final/daily_performance.csv',parse_dates=['date'])
    fig,ax=plt.subplots(2,1,figsize=(10,6),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    for (name,g),color in zip(daily.groupby('portfolio_id',sort=False),COLORS):
        ax[0].plot(g.date,g.wealth,label=LABELS[name],color=color,lw=1.5);ax[1].plot(g.date,g.drawdown,color=color,lw=1)
    ax[0].set(ylabel='Net wealth / initial NAV',title='Registered rule: growth with a lower loss envelope');ax[0].legend(frameon=False,ncol=3,fontsize=8)
    ax[1].set(ylabel='Drawdown');ax[1].yaxis.set_major_formatter(PercentFormatter(1));fig.tight_layout();save(fig,'01_wealth_drawdown')
    k=pd.DataFrame(ref['period_kpis']);fig,axes=plt.subplots(1,3,figsize=(10,3.4))
    for ax,metric,title in zip(axes,['geometric_annual_return','annualized_volatility','max_drawdown'],['Net CAGR','Annual volatility','Max drawdown']):
        pivot=k[(k.period!='full')&(k.metric==metric)].pivot(index='period',columns='portfolio_id',values='value').reindex(['development','selection','evaluation'])
        pivot=pivot.reindex(columns=list(LABELS));pivot.columns=[LABELS[x] for x in pivot.columns]
        pivot.plot.bar(ax=ax,color=COLORS,legend=False);ax.set(title=title,xlabel='');ax.tick_params(axis='x',rotation=20);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.axhline(0,color='#cad2d7',lw=.7)
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',ncol=3,frameon=False,fontsize=8);fig.tight_layout(rect=[0,.1,1,1]);save(fig,'02_period_scorecard')
    risk=pd.DataFrame(ref['risk_table']);fig,axes=plt.subplots(1,2,figsize=(10,3.8),sharey=True)
    for ax,wid in zip(axes,['recent','full_history']):
        d=risk[(risk.window_id==wid)&(risk.confidence==.99)&risk.model.isin(['historical','parametric_normal','monte_carlo_normal','evt_pot'])]
        x=range(len(d));ax.bar([i-.17 for i in x],d.var_loss,width=.34,label='VaR99',color=COLORS[0]);ax.bar([i+.17 for i in x],d.es_loss,width=.34,label='ES99',color=COLORS[1])
        ax.set_xticks(list(x),['Historical','Normal','MC Normal','POT-GPD'],rotation=15);ax.set_title('Recent 1,260 sessions' if wid=='recent' else 'Full 5,491 sessions')
        ax.axhline(.02,color='#b43e35',ls='--',lw=1,label='Proposed ES99 budget');ax.yaxis.set_major_formatter(PercentFormatter(1))
    axes[0].set_ylabel('One-day pre-cost loss / NAV');axes[1].legend(frameon=False,fontsize=8);fig.tight_layout();save(fig,'03_tail_model_comparison')
    rows=pd.read_csv(ROOT/'results/final/backtest_historical_0.99.csv',parse_dates=['date']);fig,ax=plt.subplots(figsize=(10,3.6))
    ax.plot(rows.date,rows.realized_loss,color='#9ba8b0',lw=.6,label='Realised gross loss');ax.plot(rows.date,rows.forecast_var,color=COLORS[0],lw=1,label='Prior500 HS VaR99')
    ex=rows[rows.exceedance.eq(True)];ax.scatter(ex.date,ex.realized_loss,s=10,color='#b43e35',label=f'Exceptions ({len(ex)})',zorder=3)
    ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_title('Coverage and clustering both matter');ax.legend(frameon=False,ncol=3,fontsize=8);fig.tight_layout();save(fig,'04_rolling_exceptions')
    stress=pd.DataFrame(ref['stress_results']);pivot=stress.pivot(index='scenario_id',columns='portfolio_id',values='total_return')
    pivot.index=['COVID','GFC','Hypothetical','2022 rates'] if list(pivot.index)==['covid_2020','gfc_2007_2009','hypothetical_stagflation_repricing','rate_shock_2022'] else pivot.index
    fig,ax=plt.subplots(figsize=(10,3.4));pivot.reindex(columns=['min_variance','benchmark_60_40']).rename(columns=LABELS).plot.bar(ax=ax,color=[COLORS[0],COLORS[2]],rot=0)
    ax.set(title='Same current exposure, different historical regimes',ylabel='Scenario total return',xlabel='');ax.yaxis.set_major_formatter(PercentFormatter(1));ax.legend(frameon=False);fig.tight_layout();save(fig,'05_stress_replay')
    rc=pd.DataFrame(ref['risk_contributions']['historical_es']);w=pd.DataFrame(ref['current_weights']).set_index('ticker').min_variance
    fig,axes=plt.subplots(1,2,figsize=(10,3.3));axes[0].bar(w.index,w.values,color=COLORS[0]);axes[0].set_title('Prospective target weights')
    axes[1].bar(rc.ticker,rc.pct_contribution,color=COLORS[1]);axes[1].set_title('Share of Historical ES99')
    for ax in axes:ax.yaxis.set_major_formatter(PercentFormatter(1))
    fig.tight_layout();save(fig,'06_weights_risk_budget')
    print('Exported 6 actual figures as PNG300dpi + SVG')

if __name__=='__main__':main()
