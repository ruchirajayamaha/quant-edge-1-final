"""Rebuild the auditable final reference without any network or UI dependency."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import pandas as pd
from quantedge.pipeline import run_pipeline
from quantedge.final_engine import json_safe

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/final'

def records(frame,index=False):
    return json_safe((frame.reset_index() if index else frame).to_dict('records'))

def main():
    bundle=run_pipeline(offline=True);OUT.mkdir(parents=True,exist_ok=True)
    payload={'metadata':asdict(bundle.metadata),'proposal':bundle.proposal,
       'period_kpis':records(bundle.period_kpis),'current_weights':records(bundle.current_weights.rename_axis('ticker'),True),
       'risk_table':records(bundle.risk_table),'evt_diagnostics':records(bundle.evt_diagnostics),
       'coverage_summary':records(bundle.coverage_summary),'basel':bundle.basel_diagnostic_99,
       'risk_contributions':{k:records(v) for k,v in bundle.risk_contributions.items()},
       'allocation_comparisons':records(bundle.allocation_comparisons),'stress_results':records(bundle.stress_results),
       'context':{kind:{k:records(v) for k,v in tables.items()} for kind,tables in bundle.context.items()},
       'diagnostics':bundle.diagnostics}
    performance=[]
    for name,path in bundle.portfolio_paths.items():
        frame=pd.DataFrame({'net_return':path.net_returns,'gross_return':path.gross_returns,'wealth':path.wealth,
                            'drawdown':path.drawdown,'turnover':path.turnover,'cost':path.costs})
        performance.append(frame.assign(portfolio_id=name).rename_axis('date').reset_index())
        path.weights_before.to_csv(OUT/f'weights_before_{name}.csv',index_label='date',float_format='%.17g')
        path.rebalances.to_csv(OUT/f'rebalances_{name}.csv',index=False)
    daily=pd.concat(performance,ignore_index=True)
    daily.to_csv(OUT/'daily_performance.csv',index=False,float_format='%.17g')
    for name,frame in [('period_kpis',bundle.period_kpis),('risk_table',bundle.risk_table),
                       ('coverage_summary',bundle.coverage_summary),('stress_results',bundle.stress_results),
                       ('evt_diagnostics',bundle.evt_diagnostics),('allocation_comparisons',bundle.allocation_comparisons)]:
        frame.to_csv(OUT/f'{name}.csv',index=False,float_format='%.17g')
    for key,rows in bundle.backtest_rows.items():
        rows.to_csv(OUT/f'backtest_{key}.csv',index=False,float_format='%.17g')
        payload.setdefault('backtest_metadata',{})[key]=rows.attrs
    (OUT/'reference.json').write_text(json.dumps(json_safe(payload),indent=2,allow_nan=False)+'\n',encoding='utf-8')
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json'}
    (OUT/'manifest.json').write_text(json.dumps({'bundle_id':bundle.metadata.bundle_id,'file_sha256':manifest},indent=2)+'\n')
    print('FINAL_REFERENCE_READY',bundle.metadata.bundle_id,flush=True)

if __name__=='__main__':main()
