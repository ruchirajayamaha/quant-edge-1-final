"""Correct a supplied review draft and add only the user-requested typed identity.

AI reference calculations do not certify a human review. No credential, review
date, committee approval or certificate-based digital signature is invented.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import numpy as np
import pandas as pd
from quantedge.config import load_config
from quantedge.data import load_data
from quantedge.reference import load_reference
from build_reports import BUILD, compile_document, page_count, tex_environment

ROOT=Path(__file__).resolve().parents[1]
DOCUMENT='review_nisal_induwara'
OUTPUT=ROOT/'FINAL_SUBMISSION/supporting/Human_Review_Nisal_Induwara_DRAFT.pdf'

def main():
    ref=load_reference();data=load_data(load_config(),offline=True)
    daily=pd.read_csv(ROOT/'results/final/daily_performance.csv',parse_dates=['date'])
    returns=data.simple_returns
    held=pd.read_csv(ROOT/'results/final/weights_before_min_variance.csv',index_col='date',parse_dates=True)
    day=pd.Timestamp('2026-10-29')
    one_day=float(np.dot(held.loc[day].reindex(returns.columns),returns.loc[day]))
    series=daily[(daily.portfolio_id=='min_variance')&(daily.date>='2021-01-04')].set_index('date').net_return
    wealth=(1+series).cumprod();drawdown=wealth/wealth.cummax().clip(lower=1)-1
    trough=drawdown.idxmin();peak=wealth.loc[:trough].idxmax()
    weights=pd.DataFrame(ref['current_weights']).set_index('ticker').min_variance.reindex(returns.columns)
    losses=-(returns.iloc[-1260:].to_numpy()@weights.to_numpy())
    normal=float(losses.mean()+2.3263478740408408*losses.std(ddof=1))
    worst=np.sort(losses)[::-1][:13]
    es=float((sum(worst[:12])+.6*worst[12])/12.6)
    crisis=(1+returns.loc['2007-10-09':'2009-03-09']).prod()-1
    stress=float(np.dot(weights,crisis))
    values={'OneDay':f'{one_day:.10f}','OneDayPct':f'{one_day:.6%}',
      'Drawdown':f'{drawdown.loc[trough]:.10f}','DrawdownPct':f'{drawdown.loc[trough]:.6%}',
      'PeakDate':str(peak.date()),'TroughDate':str(trough.date()),
      'PeakWealth':f'{wealth.loc[peak]:.10f}','TroughWealth':f'{wealth.loc[trough]:.10f}',
      'NormalVar':f'{normal:.10f}','NormalVarPct':f'{normal:.6%}',
      'HistoricalEs':f'{es:.10f}','HistoricalEsPct':f'{es:.6%}',
      'Gfc':f'{stress:.10f}','GfcPct':f'{stress:.6%}',
      'GfcLossUsd':f'{-stress*1e7:,.2f}','GfcEndUsd':f'{(1+stress)*1e7:,.2f}',
      'WorstTwelveSum':f'{worst[:12].sum():.12f}','ThirteenthLoss':f'{worst[12]:.12f}'}
    for key,want in [('NormalVar',normal),('HistoricalEs',es)]:
        model='parametric_normal' if key=='NormalVar' else 'historical'
        row=next(x for x in ref['risk_table'] if x['window_id']=='recent' and x['model']==model and x['confidence']==.99)
        assert abs(want-row['var_loss' if key=='NormalVar' else 'es_loss'])<1e-12
    commands=''.join('\\newcommand{\\nr'+k+'}{'+v.replace('%',r'\%')+'}\n' for k,v in values.items())
    (ROOT/'report/latex/generated/named_review_values.tex').write_text(commands,encoding='utf-8')
    BUILD.mkdir(parents=True,exist_ok=True)
    env=tex_environment()
    # Windows resolves the executable against the calling process's PATH.
    os.environ['PATH']=env['PATH']
    built=compile_document(DOCUMENT,env)
    pages=page_count(built)
    if pages!=3:raise ValueError(f'Expected three readable review pages; got {pages}')
    OUTPUT.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(built,OUTPUT)
    record={'reviewer_name_supplied_by_user':'Nisal Induwara',
      'signature':'Typed name requested by user; not a certificate-based digital signature',
      'status':'DRAFT_AWAITING_REVIEWER_CONFIRMATION','human_validation':'PENDING',
      'pages':pages,
      'review_date':None,'professional_credential':None,'reviewer_role':None,
      'bundle_id':ref['metadata']['bundle_id'],'numerical_reference_values':values,
      'output':OUTPUT.relative_to(ROOT).as_posix(),
      'output_sha256':hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
      'corrections':['Removed mismatched Alex Thorne/CFA/Digital ID identity claims',
        'Corrected drawdown and peak/trough dates against frozen returns',
        'Removed unsupported completed/verified/signed-off status',
        'Clarified proposed budgets, breaches and non-forecast hurdle; left reviewer findings/decision/date blank']}
    out=ROOT/'audit/presentation_review/named_review_draft.json'
    out.write_text(json.dumps(record,indent=2)+'\n')
    print('NAMED_REVIEW_DRAFT',OUTPUT,flush=True)

if __name__=='__main__':main()
