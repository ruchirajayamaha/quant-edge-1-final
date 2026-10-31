"""Record Step 8 contributions/sizing and explicitly ex-post scenario replays."""

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

import numpy as np
import pandas as pd

from quantedge.config import load_config
from quantedge.contracts import CANONICAL_TICKERS
from quantedge.data import load_data
from quantedge.risk_budget import risk_contributions, compare_feasible_allocations
from quantedge.stress import run_stress_tests
from quantedge.var import get_risk_forecaster

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/step8_risk_stress_preview'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [clean(v) for v in value]
    if isinstance(value,np.generic):
        return clean(value.item())
    if isinstance(value,float):
        if math.isnan(value):return None
        if not math.isfinite(value):raise ValueError('Infinite result cannot be serialized')
    return value


def verify_inputs():
    base=json.loads((ROOT/'audit/step8_review/STEP8_BASELINE.json').read_text())
    for name,digest in base['protected_sha256'].items():assert sha(ROOT/name)==digest,name
    count=0
    for path in list((ROOT/'data/processed').glob('*/manifest.json'))+[ROOT/'data/reference/context/context_manifest.json']:
        for name,digest in json.loads(path.read_text(encoding='utf-8-sig'))['file_sha256'].items():
            assert sha(ROOT/name)==digest,name
            count+=1
    assert count==53
    return {'protected_files_unchanged':len(base['protected_sha256']),'source_data_hashes':count}


def main():
    started=time.perf_counter();integrity=verify_inputs()
    cfg=load_config(ROOT/'config.yaml');data=load_data(cfg,offline=True)
    assert 'Step 8 bounded engineering protocol' in (ROOT/'audit/decision_register/REGISTER.md').read_text(encoding='utf-8')
    prior=json.loads((ROOT/'results/step5_development_c1_risk_tables.json').read_text())
    dev=data.simple_returns.loc[:cfg.chronology.development_end].copy()
    baseline=pd.Series(prior['exposures']['min_variance']['weights']).reindex(CANONICAL_TICKERS)
    baseline.name='terminal_development_min_variance'
    benchmark=pd.Series(cfg.mandate.benchmark_60_40_weights).reindex(CANONICAL_TICKERS,fill_value=0.)
    benchmark.name='benchmark_60_40_reference'
    candidates={'baseline_min_variance':baseline}
    for label,spy,agg,gld in [('defensive_20_40_40',.2,.4,.4),('equity_cap_35_40_25',.35,.4,.25),
                              ('balanced_30_35_35',.3,.35,.35),('gold_tilt_25_35_40',.25,.35,.4)]:
        candidates[label]=pd.Series([spy,0,0,agg,gld,0,0],index=CANONICAL_TICKERS)
    candidates['equal_weight_reference']=pd.Series(1/7,index=CANONICAL_TICKERS)
    candidates['benchmark_60_40_reference']=benchmark
    windows={'recent_development_1260d':dev.iloc[-1260:], 'full_development_3020d':dev}
    runs={};contribution_csv=[];sizing_csv=[]
    for name,sample in windows.items():
        c_rows=[]
        for conf in (.95,.99):
            for method in ('normal_var','normal_es','historical_es'):
                frame=risk_contributions(sample,baseline,confidence=conf,method=method)
                assert frame.status.isin(['ok','warning']).all()
                c_rows.extend(frame.to_dict(orient='records'))
                contribution_csv.append(frame.assign(window_id=name))
        comparison=compare_feasible_allocations(sample,candidates,
            {'constraints':cfg.portfolio.constraints,'baseline_id':'baseline_min_variance','confidence':.99,
             'max_var_loss':cfg.portfolio.risk_limits.get('max_daily_var_99_fraction'),
             'max_es_loss':cfg.portfolio.risk_limits.get('max_daily_es_99_fraction'),
             'annualization_days':cfg.portfolio.annualization_days,'seed':cfg.seeds.backtest},
            get_risk_forecaster('historical'))
        assert comparison.iloc[:5].constraint_feasible.eq(True).all()
        assert comparison.status.isin(['ok','warning']).all()
        sizing_csv.append(comparison.assign(window_id=name))
        runs[name]={'sample_start':str(sample.index[0].date()),'sample_end':str(sample.index[-1].date()),
                    'n_obs':len(sample),'contributions':c_rows,'allocations':comparison.to_dict(orient='records'),
                    'allocation_metadata':comparison.attrs}
    scenarios=[*cfg.stress.historical_scenarios,cfg.stress.hypothetical_scenario]
    stress_rows=[];stress_paths={};attributions={}
    # Explicitly authorized ex-post post-development scenarios at the already frozen exposure.
    # This does not calculate or select a post-2016 investable strategy.
    for weights in (baseline,benchmark):
        frame=run_stress_tests(data.simple_returns,weights,scenarios,nav=cfg.mandate.nav_usd)
        assert frame.status.isin(['ok','warning']).all(),frame.to_dict('records')
        stress_rows.extend(frame.to_dict(orient='records'))
        stress_paths[weights.name]={k:clean(v.to_dict('records')) for k,v in frame.attrs['daily_paths'].items()}
        attributions[weights.name]={k:clean(v.to_dict('records')) for k,v in frame.attrs['attributions'].items()}
    # Daily development scale context only; the hypothetical repricing horizon is unspecified.
    scale=[]
    shocks=cfg.stress.hypothetical_scenario.shocks
    for t in CANONICAL_TICKERS:
        scale.append({'ticker':t,'hypothetical_shock':shocks[t], 'development_worst_daily_return':float(dev[t].min()),
                      'development_best_daily_return':float(dev[t].max()),
                      'interpretation':'Daily extrema are scale context only; hypothetical joint repricing duration/probability unassigned.'})
    monitoring=[{'metric':'daily_HS_ES99','threshold':None,'status':'PENDING_HUMAN_RISK_LIMIT',
                 'action':'Review approved risk budget and feasible redistribution after human-defined threshold breach; no automatic relaxation.'},
                {'metric':'drawdown_and_crisis_loss','threshold':None,'status':'PENDING_HUMAN_LOSS_TOLERANCE',
                 'action':'Review liquidity/spending plan and allowed allocation changes against approved horizon-specific loss tolerance.'},
                {'metric':'pre_return_holdings_drift','threshold':'configured provisional target caps; continuous enforcement policy PENDING',
                 'status':'PROPOSED_MONITOR_ONLY','action':'Flag drift beyond target caps; seek approved rebalance policy, do not silently clip daily weights.'},
                {'metric':'missing_sessions_or_forecast_failures','threshold':'any','status':'SOFTWARE_QUALITY_TRIGGER',
                 'action':'Mark dependent analytics unavailable and investigate before relying on the output.'}]
    sources=['src/quantedge/risk_budget.py','src/quantedge/stress.py','scripts/record_step8_results.py']
    payload={'metadata':{'scope':'DEVELOPMENT sizing/risk contributions + EX-POST historical stress at frozen development exposure; not final recommendation',
             'dataset_id':data.manifest.dataset_id,'config_hash':cfg.config_hash,
             'code_version':subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()+'-working-tree',
             'source_sha256':{n:sha(ROOT/n) for n in sources},'computed_at_utc':datetime.now(timezone.utc).isoformat(),
             'runtime_seconds':time.perf_counter()-started,'nav_usd':cfg.mandate.nav_usd,
             'weights':baseline.to_dict(),'stress_benchmark_weights':benchmark.to_dict(),
             'development_end':cfg.chronology.development_end,'integrity':integrity,
             'selection_evaluation_strategy_outcomes_inspected':False,'post_2016_fixed_weight_scenario_replays':True,
             'human_validation':'PENDING','mandate_risk_limits':cfg.portfolio.risk_limits},
             'windows':runs,'stress_results':stress_rows,'stress_daily_paths':stress_paths,'stress_attributions':attributions,
             'scenarios':[vars(s) for s in scenarios], 'hypothetical_scale_context':scale,'monitoring':monitoring,
             'decision':'PENDING_HUMAN_DECISION; no candidate selected, no ACCEPT/ADJUST/REJECT claim'}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'step8_results.json').write_text(json.dumps(clean(payload),indent=2,allow_nan=False)+'\n',encoding='utf-8')
    pd.concat(contribution_csv,ignore_index=True).to_csv(OUT/'01_risk_contributions.csv',index=False,float_format='%.17g')
    flat=[]
    for frame in sizing_csv:
        for row in frame.to_dict('records'):
            for t in CANONICAL_TICKERS:row['weight_'+t]=row['weights'][t]
            for key in ('weights','baseline_weights','weight_change','constraint_violations'):
                row[key]=json.dumps(clean(row[key]),allow_nan=False)
            flat.append(row)
    pd.DataFrame(flat).to_csv(OUT/'02_allocation_comparisons.csv',index=False,float_format='%.17g')
    pd.DataFrame(stress_rows).to_csv(OUT/'03_stress_comparison.csv',index=False,float_format='%.17g')
    attrs=[]
    for portfolio,ss in attributions.items():
        for scenario,rows in ss.items():attrs.extend([{**row,'portfolio_id':portfolio,'scenario_id':scenario} for row in rows])
    pd.DataFrame(attrs).to_csv(OUT/'04_stress_asset_attribution.csv',index=False,float_format='%.17g')
    pd.DataFrame(scale).to_csv(OUT/'05_hypothetical_scale_context.csv',index=False,float_format='%.17g')
    verify_inputs()
    print('Saved Step8: 84 contribution rows,14 allocation comparisons,8 stress rows. Runtime',payload['metadata']['runtime_seconds'])


if __name__=='__main__':main()
