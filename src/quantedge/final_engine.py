"""Shared final analysis; no UI imports, model selection, or outcome-driven tuning."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any
import numpy as np
import pandas as pd
from quantedge.config import AppConfig, load_config, list_provisional_items
from quantedge.contracts import PipelineResultBundle, ResultBundleMetadata, RiskEstimate
from quantedge.data import load_data, load_context_data
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs, construct_weights, summarize_pre_return_holdings_compliance
from quantedge.kpis import compute_kpis, build_development_kpi_bundle
from quantedge.var import compare_risk_models_table, get_risk_forecaster
from quantedge.evt import estimate_evt_pot, estimate_evt_body_tail, evt_threshold_diagnostics
from quantedge.backtest import rolling_backtest, coverage_tests, basel_traffic_light
from quantedge.risk_budget import risk_contributions, compare_feasible_allocations
from quantedge.stress import run_stress_tests

ROOT=Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class IntegratedResultBundle(PipelineResultBundle):
    """Additive payload preserves the frozen base contract."""
    risk_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    period_kpis: pd.DataFrame = field(default_factory=pd.DataFrame)
    current_weights: pd.DataFrame = field(default_factory=pd.DataFrame)
    context: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    proposal: dict[str, Any] = field(default_factory=dict)

def json_safe(value):
    if value is None or value is pd.NA or value is pd.NaT:return None
    if isinstance(value,(pd.Timestamp,datetime)):return value.isoformat()
    if isinstance(value,(np.ndarray,pd.Index)):return [json_safe(v) for v in value.tolist()]
    if isinstance(value,dict):return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [json_safe(v) for v in value]
    if isinstance(value,np.generic):return json_safe(value.item())
    if isinstance(value,float):
        if math.isnan(value):return None
        if not math.isfinite(value):raise ValueError('Infinite analytical result')
    return value

def period_performance(paths,data,start=None,end=None):
    output=[]
    for name,path in paths.items():
        r=path.net_returns.loc[start:end]
        if len(r)<2:continue
        table=compute_kpis(r,paths['benchmark_60_40'].net_returns.loc[start:end],data.simple_returns.SPY,data.rf_daily)
        output.append(table.assign(portfolio_id=name,start=str(r.index.min().date()),end=str(r.index.max().date()),n_sessions=len(r)))
    return pd.concat(output,ignore_index=True) if output else pd.DataFrame()

def backtest_view(rows,start=None,end=None):
    """Select target dates, never truncate the forecast training history."""
    result=rows.copy()
    if start is not None:result=result.loc[result.date>=pd.Timestamp(start)]
    if end is not None:result=result.loc[result.date<=pd.Timestamp(end)]
    result=result.copy().reset_index(drop=True);result.attrs=dict(rows.attrs)
    return result,coverage_tests(result),basel_traffic_light(result)

def risk_view(returns,weights,cfg,confidence,window=None):
    sample=returns.iloc[-window:] if window else returns
    table=compare_risk_models_table(sample,weights,confidences=(confidence,),
        models=('historical','parametric_normal','monte_carlo_normal'),seed=cfg.seeds.monte_carlo,config=cfg)
    records=table.to_dict('records')
    estimates=[RiskEstimate(model=row['model'],confidence=confidence,horizon_days=1,
        var_loss=row['var_loss'],es_loss=row['es_loss'],n_obs=len(sample),
        sample_start=sample.index[0],sample_end=sample.index[-1],status=row['status'],
        reason=None if pd.isna(row.get('reason')) else row['reason'],
        diagnostics={'config_hash':cfg.config_hash,'seed':row.get('seed'),
                     'monte_carlo_simulations':row.get('monte_carlo_simulations')}) for row in records]
    for fn in (estimate_evt_pot,estimate_evt_body_tail):
        e=fn(sample,weights,confidence=confidence,threshold_quantile=cfg.risk.evt_threshold_quantile,
             min_exceedances=cfg.risk.evt_min_exceedances,seed=cfg.seeds.evt_bootstrap)
        estimates.append(e);row=asdict(e)
        row.update(var_usd=None if e.var_loss is None else e.var_loss*cfg.mandate.nav_usd,
                   es_usd=None if e.es_loss is None else e.es_loss*cfg.mandate.nav_usd,config_hash=cfg.config_hash)
        records.append(row)
    return pd.DataFrame(records),estimates

def compute_bundle(config=None,*,offline=False):
    cfg=config if isinstance(config,AppConfig) else load_config(config or ROOT/'config.yaml')
    data=load_data(cfg,offline=offline);context=load_context_data(cfg,offline=offline);r=data.simple_returns
    specs=make_core_strategy_specs(cfg)
    paths={name:build_portfolio_path(r,spec,cfg) for name,spec in specs.items()}
    context_tables=build_development_kpi_bundle(paths,r.SPY,data.rf_daily,
        rf_accrual_sensitivity=data.rf_accrual_sensitivity,context_bundle=context)
    periods={'development':(None,cfg.chronology.development_end),
      'selection':(cfg.chronology.selection_start,cfg.chronology.selection_end),
      'evaluation':(cfg.chronology.evaluation_start,cfg.chronology.evaluation_end),'full':(None,None)}
    period_tables=[period_performance(paths,data,lo,hi).assign(period=key) for key,(lo,hi) in periods.items()]
    sample=r.iloc[-cfg.portfolio.estimation_window_days:]
    current={}
    for name,spec in specs.items():
        current[name]=construct_weights(sample,spec.constraints or cfg.portfolio.constraints,objective=spec.objective) if spec.fixed_weights is None else pd.Series(spec.fixed_weights).reindex(r.columns,fill_value=0.)
    weights=pd.DataFrame(current);risks=[];estimates=[];diagnostics=[]
    for wid,n in [('recent',cfg.risk.dashboard_risk_window_days),('full_history',len(r))]:
        for c in (.90,.95,.99):
            table,ee=risk_view(r,weights.min_variance,cfg,c,n)
            risks.append(table.assign(window_id=wid,portfolio_id='min_variance'));estimates.extend(ee)
        diagnostics.append(evt_threshold_diagnostics(-(r.iloc[-n:]@weights.min_variance)).assign(window_id=wid))
    bt={};coverage=[];basel={};pdg=[]
    for model in ('historical','parametric_normal'):
        for c in (.90,.95,.99):
            key=f'{model}_{c:.2f}'
            rows=rolling_backtest(r,paths['min_variance'].weights_before,get_risk_forecaster(model),
                confidence=c,window=cfg.risk.backtest_window_days,seed=cfg.seeds.backtest)
            bt[key]=rows;coverage.append(coverage_tests(rows).assign(period='full',portfolio_id='min_variance'))
            if c==.99:basel[model]=basel_traffic_light(rows)
            for period,(lo,hi) in periods.items():
                if period=='full':continue
                rr,ss,bb=backtest_view(rows,lo,hi)
                coverage.append(ss.assign(period=period,portfolio_id='min_variance'))
                pdg.append({'period':period,'model':model,'confidence':c,'diagnostics':ss.attrs,'basel':bb if c==.99 else None})
            print(f'Backtest {key}: {len(rows)} targets',flush=True)
    primary=weights.min_variance.copy();primary.name='min_variance_next_session_target'
    recent=r.iloc[-cfg.risk.dashboard_risk_window_days:]
    rc={m:risk_contributions(recent,primary,confidence=.99,method=m) for m in ('normal_var','normal_es','historical_es')}
    proposal_path=ROOT/'submission/mandate_proposal.json'
    proposal_hash=hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    proposal=json.loads(proposal_path.read_text(encoding='utf-8'));limits=proposal['risk_limits']
    allocations=compare_feasible_allocations(recent,{name:weights[name] for name in weights},
       {'constraints':cfg.portfolio.constraints,'baseline_id':'min_variance','confidence':.99,
        'max_var_loss':limits['max_daily_var_99_fraction'],'max_es_loss':limits['max_daily_es_99_fraction']},get_risk_forecaster('historical'))
    stress=[];scenarios=[*cfg.stress.historical_scenarios,cfg.stress.hypothetical_scenario]
    for name in ('min_variance','benchmark_60_40'):
        w=weights[name].copy();w.name=name
        stress.append(run_stress_tests(r,w,scenarios,nav=cfg.mandate.nav_usd).assign(portfolio_id=name))
    code=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip() or 'source-export'
    sh=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'src/quantedge').glob('*.py')))).hexdigest()
    identity=f'{data.manifest.dataset_id}:{cfg.config_hash}:{sh}:{proposal_hash}'
    meta=ResultBundleMetadata(bundle_id=hashlib.sha256(identity.encode()).hexdigest()[:20],schema_version=cfg.schema_version,
       code_version='base-commit:'+code+';source-sha256:'+sh,dataset_id=data.manifest.dataset_id,config_hash=cfg.config_hash,
       computed_at_utc=datetime.now(timezone.utc).isoformat(),forecast_convention='Prior500 sessions; pre-return weights; gross one-day loss',
       cost_convention='Net performance includes5bps per sum-absolute-trade-weight; risk before costs',
       provisional_fields=tuple(x.field_path for x in list_provisional_items(cfg)))
    return IntegratedResultBundle(metadata=meta,data_bundle=data,portfolio_paths=paths,kpis=context_tables['kpis'],
       risk_estimates=estimates,evt_diagnostics=pd.concat(diagnostics,ignore_index=True),backtest_rows=bt,
       coverage_summary=pd.concat(coverage,ignore_index=True),basel_diagnostic_99=basel,risk_contributions=rc,
       allocation_comparisons=allocations,stress_results=pd.concat(stress,ignore_index=True),risk_table=pd.concat(risks,ignore_index=True),
       period_kpis=pd.concat(period_tables,ignore_index=True),current_weights=weights,context=context_tables,
       diagnostics={'period_backtests':pdg,'drift':summarize_pre_return_holdings_compliance(paths['min_variance'].weights_before,cfg.portfolio.constraints),
          'current_exposure_convention':'Prospective target estimated through frozen final close; not assumed already traded',
          'human_validation':'PENDING','protocol_commit':'782ec20','source_sha256':sh,
          'mandate_proposal_sha256':proposal_hash},proposal=proposal)
