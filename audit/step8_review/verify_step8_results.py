"""Independent array/scalar oracles for Step 8 contribution, sizing and stress outputs."""

import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from quantedge.config import load_config
from quantedge.data import load_data

ROOT=Path(__file__).resolve().parents[2]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def empirical(losses,c):
    ordered=sorted(float(v) for v in losses)
    n=len(ordered);mass=Fraction(n)*(1-Fraction(str(c)));whole=int(mass);fraction=float(mass-whole)
    v=ordered[math.ceil(Fraction(n)*Fraction(str(c)))-1]
    worst=ordered[::-1];e=(math.fsum(worst[:whole])+(fraction*worst[whole] if fraction else 0))/float(mass)
    return v,e


def main():
    cfg=load_config(ROOT/'config.yaml');bundle=load_data(cfg,offline=True)
    dev=bundle.simple_returns.loc[:cfg.chronology.development_end]
    outdir=ROOT/'results/step8_risk_stress_preview'
    result=json.loads((outdir/'step8_results.json').read_text(),parse_constant=lambda t:(_ for _ in()).throw(ValueError(t)))
    maxima={'contribution_total':0.,'contribution_marginal':0.,'allocation_risk':0.,'stress':0.}
    n_contrib=0;n_alloc=0;n_stress=0
    for win,run in result['windows'].items():
        sample=dev.iloc[-1260:] if 'recent' in win else dev
        a=sample.to_numpy();w=np.array([result['metadata']['weights'][t] for t in sample.columns]);loss=-a@w
        mean=a.mean(axis=0);cov=np.cov(a,rowvar=False,ddof=1);sigma=float(np.std(a@w,ddof=1))
        for method in ['normal_var','normal_es','historical_es']:
            for c in [.95,.99]:
                rows=[r for r in run['contributions'] if r['method']==method and r['confidence']==c]
                if method=='historical_es':
                    total=empirical(loss,c)[1]
                    # Scalar integration of each asset across portfolio-loss ranking.
                    mass=float(Fraction(len(a))*(1-Fraction(str(c))));remain=mass;marg=np.zeros(7)
                    order=np.argsort(-loss,kind='stable')
                    for index in order:
                        take=min(1.,remain);marg-=a[index]*(take/mass);remain-=take
                        if remain<1e-12:break
                else:
                    z=NormalDist().inv_cdf(c);factor=z if method=='normal_var' else math.exp(-z*z/2)/math.sqrt(2*math.pi)/(1-c)
                    total=-float(mean@w)+factor*sigma;marg=-mean+factor*(cov@w)/sigma
                maxima['contribution_total']=max(maxima['contribution_total'],abs(sum(r['component_risk'] for r in rows)-total))
                for i,row in enumerate(rows):
                    maxima['contribution_marginal']=max(maxima['contribution_marginal'],abs(row['marginal_risk']-marg[i]))
                    assert abs(row['component_risk']-w[i]*row['marginal_risk'])<1e-14
                    assert abs(row['total_risk']-total)<1e-13
                n_contrib+=len(rows)
        for row in run['allocations']:
            ww=np.array([row['weights'][t] for t in sample.columns]);v,e=empirical(-a@ww,.99)
            maxima['allocation_risk']=max(maxima['allocation_risk'],abs(v-row['var_loss']),abs(e-row['es_loss']))
            equity=float(ww[[0,1,2,5,6]].sum());defensive=float(ww[[3,4]].sum())
            feasible=bool(np.min(ww)>=-1e-7 and np.max(ww)<=.4+1e-7 and abs(ww.sum()-1)<1e-7 and equity<=.35+1e-7 and defensive>=.4-1e-7)
            assert row['constraint_feasible']==feasible
            assert row['risk_limits_met'] is None
            assert abs(row['expected_annual_return_proxy']-252*float(a.mean(axis=0)@ww))<1e-12
            n_alloc+=1
    scenarios={s['scenario_id']:s for s in result['scenarios']}
    for row in result['stress_results']:
        portfolio=row['portfolio_id'];wmap=result['metadata']['weights'] if portfolio=='terminal_development_min_variance' else result['metadata']['stress_benchmark_weights']
        w=np.array([wmap[t] for t in bundle.simple_returns.columns]);nav=result['metadata']['nav_usd'];holdings=nav*w.copy()
        initial=holdings.copy();peak=nav;prev=nav;maxdd=0.;worst=math.inf
        scenario=scenarios[row['scenario_id']]
        if scenario['scenario_type']=='historical':
            values=bundle.simple_returns.loc[scenario['start_date']:scenario['end_date']].to_numpy()
        else:
            values=np.array([[scenario['shocks'][t] for t in bundle.simple_returns.columns]])
        for returns in values:
            holdings*=1+returns;wealth=float(holdings.sum());daily=wealth/prev-1;peak=max(peak,wealth)
            maxdd=min(maxdd,wealth/peak-1);worst=min(worst,daily);prev=wealth
        total=float(holdings.sum()/nav-1)
        maxima['stress']=max(maxima['stress'],abs(total-row['total_return']),abs(maxdd-row['max_drawdown']),abs(worst-row['worst_day_return']),abs((nav-holdings.sum())/nav-row['usd_loss']/nav))
        attr=result['stress_attributions'][portfolio][row['scenario_id']]
        np.testing.assert_allclose([r['usd_pnl'] for r in attr],holdings-initial,rtol=1e-12,atol=1e-7)
        n_stress+=1
    assert all(v<1e-12 for v in maxima.values()),maxima
    baseline=json.loads((ROOT/'audit/step8_review/STEP8_BASELINE.json').read_text())
    for name,digest in baseline['protected_sha256'].items():assert sha(ROOT/name)==digest,name
    count=0
    for m in list((ROOT/'data/processed').glob('*/manifest.json'))+[ROOT/'data/reference/context/context_manifest.json']:
        for name,digest in json.loads(m.read_text(encoding='utf-8-sig'))['file_sha256'].items():assert sha(ROOT/name)==digest,name;count+=1
    manifest=json.loads((outdir/'manifest.json').read_text())
    for name,digest in manifest['source_sha256'].items():assert sha(ROOT/name)==digest,name
    for name,digest in manifest['artifacts_sha256'].items():assert sha(outdir/name)==digest,name
    assert count==53
    check={'status':'PASS','contribution_rows_checked':n_contrib,'allocation_rows_checked':n_alloc,'stress_rows_checked':n_stress,
           'max_absolute_errors':maxima,'protected_files_unchanged':len(baseline['protected_sha256']),
           'source_data_hashes_matching':count,'source_hashes_matching':len(manifest['source_sha256']),
           'artifact_hashes_matching':len(manifest['artifacts_sha256']),'authority_sha256':sha(outdir/'step8_results.json'),
           'scope':'Development contribution/sizing; explicitly authorized ex-post post2016 stress only, no strategy evaluation outcomes'}
    (ROOT/'audit/step8_review/verification.json').write_text(json.dumps(check,indent=2)+'\n');print(json.dumps(check,indent=2))


if __name__=='__main__':main()
