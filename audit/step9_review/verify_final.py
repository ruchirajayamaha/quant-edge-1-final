"""Independent scalar/array oracles over the persisted final reference."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm,chi2
from quantedge.config import load_config
from quantedge.data import load_data
from quantedge.reference import load_reference,load_backtest

ROOT=Path(__file__).resolve().parents[2]

def main():
    ref=load_reference();cfg=load_config();data=load_data(cfg,offline=True)
    base=json.loads((ROOT/'audit/step9_review/STEP9_BASELINE.json').read_text())
    for name,digest in base['protected_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    nhash=0
    for path in [*list((ROOT/'data/processed').glob('*/manifest.json')),ROOT/'data/reference/context/context_manifest.json']:
        for name,digest in json.loads(path.read_text(encoding='utf-8-sig'))['file_sha256'].items():
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
            nhash+=1
    daily=pd.read_csv(ROOT/'results/final/daily_performance.csv',parse_dates=['date'])
    r=daily[(daily.portfolio_id=='min_variance')&(daily.date>=pd.Timestamp('2021-01-04'))].net_return.to_numpy()
    wealth=np.cumprod(1+r);dd=min(wealth/np.maximum.accumulate(np.r_[1.,wealth])[1:]-1)
    cagr=np.expm1(np.log1p(r).sum()*252/len(r))
    def k(metric):return next(x['value'] for x in ref['period_kpis'] if x['period']=='evaluation' and x['portfolio_id']=='min_variance' and x['metric']==metric)
    w=pd.DataFrame(ref['current_weights']).set_index('ticker').min_variance.reindex(data.simple_returns.columns).to_numpy()
    loss=-(data.simple_returns.iloc[-1260:].to_numpy()@w)
    nv=loss.mean()+np.std(loss,ddof=1)*norm.ppf(.99)
    desc=np.sort(loss)[::-1];mass=.01*len(loss);n=int(mass);es=(sum(desc[:n])+(mass-n)*desc[n])/mass
    def q(model):return next(x for x in ref['risk_table'] if x['window_id']=='recent' and x['confidence']==.99 and x['model']==model)
    terminal=np.dot(np.prod(1+data.simple_returns.loc['2007-10-09':'2009-03-09'].to_numpy(),axis=0)-1,w)
    st=next(x for x in ref['stress_results'] if x['portfolio_id']=='min_variance' and x['scenario_id']=='gfc_2007_2009')
    actual={'evaluation_cagr':cagr,'evaluation_max_drawdown':dd,'recent_normal_var99':nv,'recent_historical_es99':es,'gfc_terminal_usd_loss':-terminal*1e7}
    expected={'evaluation_cagr':k('geometric_annual_return'),'evaluation_max_drawdown':k('max_drawdown'),'recent_normal_var99':q('parametric_normal')['var_loss'],'recent_historical_es99':q('historical')['es_loss'],'gfc_terminal_usd_loss':st['usd_loss']}
    errors={key:abs(actual[key]-expected[key]) for key in actual}
    for key,error in errors.items():assert error<(1e-7 if 'usd' in key else 1e-12),(key,error)
    euler=abs(sum(x['component_risk'] for x in ref['risk_contributions']['historical_es'])-es);assert euler<1e-12
    bt=[]
    for model in ('historical','parametric_normal'):
      for confidence in (.90,.95,.99):
        rows=load_backtest(model,confidence);assert (rows.train_end<rows.date).all()
        flags=rows.realized_loss.to_numpy()>rows.forecast_var.to_numpy();assert np.array_equal(flags,rows.exceedance.to_numpy())
        n=len(rows);x=sum(flags);p0=1-confidence;p1=x/n
        ll0=(n-x)*np.log1p(-p0)+x*np.log(p0)
        ll1=(n-x)*np.log1p(-p1)+x*np.log(p1)
        lr=-2*(ll0-ll1);record=next(z for z in ref['coverage_summary'] if z['period']=='full' and z['model']==model and z['confidence']==confidence)
        assert abs(lr-record['lr_uc'])<1e-9
        assert abs(float(chi2.sf(lr,1))-record['p_uc'])<1e-9
        bt.append({'model':model,'confidence':confidence,'sessions':n,'exceptions':int(x),'max_uc_lr_error':abs(lr-record['lr_uc'])})
    result={'bundle_id':ref['metadata']['bundle_id'],'source_data_hashes':nhash,'protected_files_unchanged':len(base['protected_sha256']),
      'independent_values':actual,'persisted_values':expected,'absolute_errors':errors,'euler_absolute_error':euler,
      'rolling_checks':bt,'human_validation':'PENDING','protocol_commit':'782ec20','all_checks_passed':True}
    (ROOT/'audit/step9_review/verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
