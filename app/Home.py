"""Offline endowment decision room. All numbers use the shared analytical engine."""
from pathlib import Path
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from quantedge.config import load_config
from quantedge.data import load_data
from quantedge.reference import load_reference,load_backtest
from quantedge.final_engine import backtest_view,risk_view
from quantedge.kpis import compute_kpis
from quantedge.risk_budget import risk_contributions
from quantedge.stress import run_stress_tests

ROOT=Path(__file__).resolve().parents[1]
LABELS={'min_variance':'Constrained minimum variance','equal_weight':'Equal weight reference','benchmark_60_40':'60/40 reference'}
COLORS=['#145c72','#db8b39','#7b8193']

@st.cache_data(show_spinner=False)
def source_data():
    cfg=load_config()
    return cfg,load_data(cfg,offline=True),load_reference(),pd.read_csv(ROOT/'results/final/daily_performance.csv',parse_dates=['date'])

@st.cache_data(show_spinner=False)
def selected_risk(portfolio,confidence,window):
    cfg,data,ref,_=source_data()
    w=pd.DataFrame(ref['current_weights']).set_index('ticker')[portfolio]
    return risk_view(data.simple_returns,w,cfg,confidence,window)[0]

@st.cache_data(show_spinner=False)
def selected_stress(portfolio):
    cfg,data,ref,_=source_data();w=pd.DataFrame(ref['current_weights']).set_index('ticker')[portfolio];w.name=portfolio
    frame=run_stress_tests(data.simple_returns,w,[*cfg.stress.historical_scenarios,cfg.stress.hypothetical_scenario],nav=cfg.mandate.nav_usd)
    # attrs contain rich DataFrame paths, which Arrow cannot encode as metadata.
    frame.attrs={}
    return frame

def pct(value):return 'Unavailable' if value is None or pd.isna(value) else f'{value:.2%}'

def main():
    st.set_page_config(page_title='Quant Edge | Endowment Decision Room',page_icon='◈',layout='wide')
    st.markdown('''<style>.stApp {background:#f6f7f8} h1,h2,h3 {color:#163547}
    [data-testid="stMetric"] {background:white;border:1px solid #dce3e8;padding:16px;border-radius:8px}
    [data-testid="stSidebar"] {background:#eef2f4} .block-container{padding-top:2rem;max-width:1500px}
    </style>''',unsafe_allow_html=True)
    try:cfg,data,ref,daily=source_data()
    except (OSError,ValueError) as exc:
        st.error(f'Verified reference unavailable: {exc}');st.code('python scripts/build_final_results.py');st.stop()
    st.caption('QUANT EDGE 1.0  /  SERENDIB UNIVERSITY ENDOWMENT')
    st.title('Preserve capital. Fund the mission.')
    st.caption('USD 10 million · seven eligible ETFs · frozen as of 30 October 2026 · offline reproducible')
    st.sidebar.title('Decision room')
    view=st.sidebar.radio('View',['Decision','Performance','Tail risk','Backtesting','Risk budget & stress','Assumptions & evidence'])
    portfolio=st.sidebar.selectbox('Portfolio',list(LABELS),format_func=lambda x:LABELS[x])
    conf=st.sidebar.select_slider('Confidence',options=[.90,.95,.99],value=.99,format_func=lambda x:f'{x:.0%}')
    model=st.sidebar.selectbox('Risk methodology',['historical','parametric_normal','monte_carlo_normal','evt_pot','evt_body_tail_hybrid'])
    limits=(daily.date.min().date(),daily.date.max().date())
    dates=st.sidebar.date_input('Performance / backtest target range',value=(pd.Timestamp('2021-01-04').date(),limits[1]),min_value=limits[0],max_value=limits[1])
    if len(dates)!=2:st.info('Select a start and end date.');st.stop()
    start,end=map(pd.Timestamp,dates)
    if start>end:st.error('Start must precede end.');st.stop()
    st.sidebar.caption('Risk and stress use prospective weights estimated at the frozen final close. Date range selects performance and backtest targets; prior training stays intact.')
    st.sidebar.caption(f"Bundle {ref['metadata']['bundle_id']} · Human validation PENDING")
    if portfolio!='min_variance':st.info('Reference portfolio: not required to satisfy the constrained mandate caps.')
    st.warning('Conditional ADJUST · Team-proposed mandate; independent human validation and committee approval remain pending.')
    if view=='Decision':
        st.subheader('A funding decision, supported by risk evidence')
        st.write('Retain the constrained rule as a candidate. Adjust the spending / liquidity plan and approve explicit loss budgets before investing. Historical returns are evidence, not a return promise.')
        k=pd.DataFrame(ref['period_kpis']);p=k[(k.portfolio_id=='min_variance')&(k.period=='evaluation')].set_index('metric')
        c=st.columns(4)
        c[0].metric('Proposed annual hurdle','6.75%');c[1].metric('Evaluation CAGR',pct(p.loc['geometric_annual_return','value']))
        hs=next(x for x in ref['risk_table'] if x['window_id']=='recent' and x['model']=='historical' and x['confidence']==.99)
        c[2].metric('Current HS99 daily ES',f"${hs['es_usd']:,.0f}",delta=f"${hs['es_usd']-200000:,.0f} above proposed budget",delta_color='inverse')
        c[3].metric('Planning horizon','10 years')
        st.write('Planning bridge: 4.00% spending + 2.50% inflation + 0.25% additional fee = 6.75% nominal return hurdle (zero real growth; deductions on beginning-year NAV). Fund expenses are already reflected in ETF returns.')
        st.caption('Decision candidate is the registered constrained minimum-variance rule. Reference controls apply to the analytical views.')
        full=next(x for x in ref['risk_table'] if x['window_id']=='full_history' and x['model']=='historical' and x['confidence']==.99)
        gfc=next(x for x in ref['stress_results'] if x['portfolio_id']=='min_variance' and x['scenario_id']=='gfc_2007_2009')
        st.write(f"Full-history current-target daily ES99: ${full['es_usd']:,.0f}. Current-target GFC replay drawdown: {gfc['max_drawdown']:.2%}. Daily tails and multi-session drawdowns have different horizons.")
        st.subheader('Prospective next-session target — not a trade instruction')
        w=pd.DataFrame(ref['current_weights']).set_index('ticker')
        st.bar_chart(w[['min_variance']]);st.dataframe(w.style.format('{:.2%}'),width='stretch')
        st.write('Bond and gold minimum allocations are implied by the existing caps. Gold has no contractual yield; bonds can lose value when rates rise. All weights face monthly target controls, with drift monitored between rebalances.')
        for name in ['investment_memo.pdf','tear_sheet.pdf','recommendation.pdf']:
            path=ROOT/'submission'/name
            if path.exists():st.download_button('Download '+name,path.read_bytes(),file_name=name,mime='application/pdf')
    elif view=='Performance':
        st.subheader('Matched-period performance · net of trading costs')
        selected=daily[daily.date.between(start,end)]
        if selected.empty:st.info('No active portfolio sessions in selected range.');st.stop()
        wealth=[];tables=[];bench=selected[selected.portfolio_id=='benchmark_60_40'].set_index('date').net_return
        for name,group in selected.groupby('portfolio_id'):
            r=group.set_index('date').net_return;v=(1+r).cumprod();dd=v/v.cummax().clip(lower=1)-1
            wealth.append(pd.DataFrame({'date':r.index,'Wealth':v,'Drawdown':dd,'Portfolio':LABELS[name]}))
            tables.append(compute_kpis(r,bench,data.simple_returns.SPY,data.rf_daily).assign(portfolio=LABELS[name]))
        chart=pd.concat(wealth)
        st.plotly_chart(px.line(chart,x='date',y='Wealth',color='Portfolio',color_discrete_sequence=COLORS),width='stretch')
        st.plotly_chart(px.line(chart,x='date',y='Drawdown',color='Portfolio',color_discrete_sequence=COLORS),width='stretch')
        table=pd.concat(tables);st.dataframe(table.pivot(index='metric',columns='portfolio',values='value'),width='stretch')
        st.caption('Series start at initial wealth 1 before first selected return. Fractional metrics are not percentage points. CAPM uses SPY; tracking error and information ratio use monthly 60/40. No cash spending or extra mandate fee is deducted from these return paths.')
        for kind in ('distribution_income','ex_post_real_returns'):
            with st.expander(kind.replace('_',' ').title()+' · full active history'):
                st.dataframe(pd.DataFrame(ref['context'][kind][portfolio]),width='stretch')
        st.caption('Distributions are descriptive cash-income context and are not added again to adjusted total returns. Real returns use endpoint CPI over a contiguous usable interval, not the selected nominal date range.')
    elif view=='Tail risk':
        st.subheader('Same confidence. Same exposure. Different tail assumptions.')
        window=st.radio('Estimation sample',['Recent 1,260 sessions','Full history'],horizontal=True)
        n=1260 if window.startswith('Recent') else len(data.simple_returns)
        frame=selected_risk(portfolio,conf,n)
        row=frame[frame.model==model]
        if row.empty:st.error('Selected method unavailable.')
        else:
            r=row.iloc[0];cols=st.columns(3)
            cols[0].metric(f'{conf:.0%} one-day VaR',pct(r.var_loss));cols[1].metric(f'{conf:.0%} one-day ES',pct(r.es_loss));cols[2].metric('Estimation sessions',str(n))
        st.dataframe(frame.reindex(columns=['model','confidence','var_loss','es_loss','var_usd','es_usd','status','reason']),width='stretch')
        finite=frame[frame.var_loss.notna()].melt(id_vars='model',value_vars=['var_loss','es_loss'],var_name='Measure',value_name='Loss fraction')
        st.plotly_chart(px.bar(finite,x='model',y='Loss fraction',color='Measure',barmode='group',color_discrete_sequence=COLORS),width='stretch')
        st.caption('1-day pre-cost loss. MC is a Normal sampling approximation, not a separate fat-tail model. Pure POT below its empirical threshold boundary is unavailable; hybrid body VaR is empirical, not EVT extrapolation. ES can be unavailable when fitted ξ ≥ 1.')
        st.caption('Recent sample omits GFC and COVID; full-history sensitivity includes them. No probability or exact future loss guarantee follows from either window.')
        with st.expander('Primary portfolio EVT threshold diagnostics'):
            st.dataframe(pd.DataFrame(ref['evt_diagnostics']),width='stretch')
    elif view=='Backtesting':
        st.subheader('Forecast first. Observe the next loss.')
        st.caption('Registered primary portfolio only. Sidebar risk-method selector does not imply rolling MC or EVT validation.')
        bm=st.radio('Rolling forecast model',['historical','parametric_normal'],horizontal=True)
        rows=load_backtest(bm,conf);chosen,summary,_=backtest_view(rows,start,end)
        st.dataframe(summary,width='stretch')
        figure=go.Figure()
        figure.add_trace(go.Scatter(x=chosen.date,y=chosen.realized_loss,name='Realised gross loss',line_color='#7b8193'))
        figure.add_trace(go.Scatter(x=chosen.date,y=chosen.forecast_var,name=f'{conf:.0%} prior500 VaR',line_color='#145c72'))
        ex=chosen[chosen.exceedance.eq(True)]
        figure.add_trace(go.Scatter(x=ex.date,y=ex.realized_loss,name='Exception',mode='markers',marker={'color':'#b43e35','size':6}))
        st.plotly_chart(figure,width='stretch')
        _,_,basel=backtest_view(load_backtest(bm,.99),start,end)
        st.write('Educational Basel 99% · final 250 sessions within selected target range')
        st.json(basel)
        st.caption('All-N Kupiec UC; Christoffersen IND and CC use transition-conditioned likelihood, dropping each run’s first state. Sparse samples and asymptotic tests have limited power. Green traffic light is not model approval; independence failures remain material.')
        st.download_button('Download selected actual forecast rows',chosen.to_csv(index=False),file_name='selected_backtest.csv')
    elif view=='Risk budget & stress':
        st.subheader('Where the risk comes from — and where losses can cluster')
        w=pd.DataFrame(ref['current_weights']).set_index('ticker')[portfolio]
        method=st.selectbox('Euler decomposition',['historical_es','normal_es','normal_var'])
        frame=risk_contributions(data.simple_returns.iloc[-1260:],w,confidence=conf,method=method)
        st.dataframe(frame,width='stretch')
        st.plotly_chart(px.bar(frame,x='ticker',y='component_risk',color_discrete_sequence=COLORS),width='stretch')
        stress=selected_stress(portfolio);st.dataframe(stress,width='stretch')
        st.plotly_chart(px.bar(stress,x='scenario_id',y='total_return',color_discrete_sequence=COLORS),width='stretch')
        st.caption('Historical buy-and-hold replays at the same prospective target; ex-post, not an investable historical strategy. Scenario return and within-scenario drawdown differ. Hypothetical joint shock has no assigned duration/probability and is not daily ES.')
        with st.expander('Feasibility / risk-limit comparison · proposed budgets'):
            st.dataframe(pd.DataFrame(ref['allocation_comparisons']),width='stretch')
        st.write('Monitoring: ES99 >2%, drawdown >20%, constraint drift, missing data and clustered exceptions trigger review. Do not raise limits simply to make an allocation pass. Negative components represent local hedging contributions, not guaranteed protection.')
    else:
        st.subheader('Every claim has a boundary')
        st.write('All assumptions and caveats are also included in the investment memo. The rule and mandate proposal were recorded before post-2016 strategy outcomes in protocol commit 782ec20. Earlier full-history asset EDA and fixed-exposure crisis replays were already viewed; this is registered-rule evaluation, not a pristine blinded experiment.')
        st.write('RF: versioned DTB3 evidence is day-level; exact historical release hours are unverified. Some availability dates are inferred, sparse-era calendar fallbacks and two unresolved observations remain. /252 is a quote proxy, not an exact realised bill return; 91-day accrual is a sensitivity.')
        st.write('CPI is revised ex-post context, not a trading signal. October 2025 CPI is absent and October 2026 was unreleased. No distributions are double-counted. No return guarantee, liability optimisation, intraday execution model or out-of-universe hedge is claimed.')
        st.write('AI materially generated code, analysis and prose. Automated tests are not independent human validation. The team must understand and validate the submission before certifying it.')
        st.json(ref['metadata']);st.json(ref['proposal'])
        st.download_button('Download source-of-truth JSON',(ROOT/'results/final/reference.json').read_bytes(),file_name='reference.json',mime='application/json')
        for name in ['AI_DISCLOSURE.md','submission/COMPLIANCE_MATRIX.md','submission/VALIDATION_CHECKLIST.md']:
            path=ROOT/name
            if path.exists():
                with st.expander(path.name):st.markdown(path.read_text(encoding='utf-8'))

if __name__=='__main__':main()
