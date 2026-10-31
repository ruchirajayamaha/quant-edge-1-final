"""Final real-snapshot verification and actual interactive control smoke checks."""
from pathlib import Path
import hashlib
import json
import tempfile
import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm
from quantedge.data import load_data
from quantedge.config import load_config
from quantedge.reference import load_reference,load_backtest
from quantedge.final_engine import backtest_view

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def final():return load_reference(),load_data(load_config(),offline=True)

def test_final_independent_headline_oracles(final):
    ref,data=final
    daily=pd.read_csv(ROOT/'results/final/daily_performance.csv',parse_dates=['date'])
    group=daily[(daily.portfolio_id=='min_variance')&(daily.date>=pd.Timestamp('2021-01-04'))]
    returns=group.net_return.to_numpy();wealth=np.cumprod(1+returns)
    cagr=np.exp(np.log1p(returns).sum()*252/len(returns))-1
    dd=(wealth/np.maximum.accumulate(np.r_[1.,wealth])[1:]-1).min()
    def k(metric):return next(x['value'] for x in ref['period_kpis'] if x['period']=='evaluation' and x['portfolio_id']=='min_variance' and x['metric']==metric)
    assert abs(cagr-k('geometric_annual_return'))<1e-12
    assert abs(dd-k('max_drawdown'))<1e-12
    weights=pd.DataFrame(ref['current_weights']).set_index('ticker').min_variance.reindex(data.simple_returns.columns)
    sample=data.simple_returns.iloc[-1260:];loss=-(sample.to_numpy()@weights.to_numpy())
    normal_var=loss.mean()+np.std(loss,ddof=1)*norm.ppf(.99)
    def risk(model):return next(x for x in ref['risk_table'] if x['window_id']=='recent' and x['confidence']==.99 and x['model']==model)
    assert abs(normal_var-risk('parametric_normal')['var_loss'])<1e-12
    descending=np.sort(loss)[::-1];mass=len(loss)*.01;whole=int(np.floor(mass));fraction=mass-whole
    es=(sum(descending[:whole])+fraction*descending[whole])/mass
    assert abs(es-risk('historical')['es_loss'])<1e-12
    assert abs(sum(x['component_risk'] for x in ref['risk_contributions']['historical_es'])-es)<1e-12
    crisis=data.simple_returns.loc['2007-10-09':'2009-03-09']
    terminal=np.dot(np.prod(1+crisis.to_numpy(),axis=0)-1,weights.to_numpy())
    stress=next(x for x in ref['stress_results'] if x['portfolio_id']=='min_variance' and x['scenario_id']=='gfc_2007_2009')
    assert abs(-terminal*1e7-stress['usd_loss'])<1e-7

def test_final_rolling_targets_and_actual_model_outputs(final):
    ref,_=final
    for model in ('historical','parametric_normal'):
      for confidence in (.90,.95,.99):
        rows=load_backtest(model,confidence)
        assert rows.status.eq('ok').all()
        assert (rows.train_end<rows.date).all()
        chosen,summary,basel=backtest_view(rows,'2021-01-04','2026-10-30')
        actual=next(x for x in ref['coverage_summary'] if x['period']=='evaluation' and x['model']==model and x['confidence']==confidence)
        assert len(chosen)==1464
        assert int(summary.iloc[0].n_exceedances)==actual['n_exceedances']
        if confidence==.99:assert basel['n_valid']==250
        short,_,bb=backtest_view(rows,'2026-10-01','2026-10-30')
        assert len(short)<250 and bb['status']==('unavailable' if confidence==.99 else 'not_applicable')
    assert not np.array_equal(load_backtest('historical',.99).forecast_var,load_backtest('parametric_normal',.99).forecast_var)

def test_final_evt_failures_proposed_limits_and_unchanged_sources(final):
    ref,_=final
    for row in ref['risk_table']:
        if row['model']=='evt_pot' and row['confidence']==.90:assert row['status']=='unavailable' and row['var_loss'] is None
    p=ref['proposal'];assert p['required_nominal_return_fraction']==pytest.approx(p['spending_annual_fraction']+p['inflation_assumption_annual_fraction']+p['additional_fee_assumption_annual_fraction'])
    candidate=ref['allocation_comparisons'][0];assert candidate['constraint_feasible'] and not candidate['risk_limits_met']
    baseline=json.loads((ROOT/'audit/step9_review/STEP9_BASELINE.json').read_text())
    for name,digest in baseline['protected_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name

def test_reference_tamper_and_stale_config_rejected(tmp_path):
    import shutil
    (tmp_path/'results/final').mkdir(parents=True)
    shutil.copy(ROOT/'config.yaml',tmp_path/'config.yaml')
    shutil.copy(ROOT/'results/final/reference.json',tmp_path/'results/final/reference.json')
    digest=hashlib.sha256((tmp_path/'results/final/reference.json').read_bytes()).hexdigest()
    manifest=tmp_path/'results/final/manifest.json';manifest.write_text(json.dumps({'file_sha256':{'reference.json':digest}}))
    assert load_reference(tmp_path)['metadata']['dataset_id']
    with (tmp_path/'results/final/reference.json').open('a') as f:f.write(' ')
    with pytest.raises(ValueError,match='hash mismatch'):load_reference(tmp_path)

def test_app_real_pages_controls_and_edge_ranges():
    tempfile.tempdir=str(ROOT/'tmp')
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(ROOT/'app/Home.py'),default_timeout=45).run()
    assert not app.exception and not app.error
    assert app.metric[1].value=='7.63%'
    for view in ['Performance','Tail risk','Backtesting','Risk budget & stress','Assumptions & evidence']:
        app.sidebar.radio[0].set_value(view).run(timeout=45)
        assert not app.exception and not app.error,view
    app.sidebar.radio[0].set_value('Tail risk').run(timeout=45)
    for c in (.90,.95,.99):
        app.sidebar.select_slider[0].set_value(c).run(timeout=45)
        for method in ['historical','parametric_normal','monte_carlo_normal','evt_pot','evt_body_tail_hybrid']:
            app.sidebar.selectbox[1].set_value(method).run(timeout=45)
            assert not app.exception and not app.error,(c,method)
    app.sidebar.selectbox[0].set_value('equal_weight').run(timeout=45);assert not app.exception
    app.sidebar.radio[0].set_value('Backtesting').run(timeout=45)
    app.sidebar.date_input[0].set_value((pd.Timestamp('2026-10-01').date(),pd.Timestamp('2026-10-30').date())).run(timeout=45)
    assert not app.exception
