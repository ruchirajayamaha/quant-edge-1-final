"""Record actual Step 4 values and refresh documentation tables without runtime edits."""
import json
from pathlib import Path
import re

from quantedge.config import load_config
from quantedge.data import load_context_data, load_data
from quantedge.kpis import build_development_kpi_bundle
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs

root = Path(__file__).resolve().parents[2]
cfg = load_config(root / 'config.yaml')
data = load_data(cfg, offline=True)
context = load_context_data(cfg, offline=True)
dev = data.simple_returns.loc[:cfg.chronology.development_end].copy()
paths = {key: build_portfolio_path(dev, spec, cfg) for key, spec in make_core_strategy_specs(cfg).items()}
bundle = build_development_kpi_bundle(paths, dev['SPY'], data.rf_daily,
                                    rf_accrual_sensitivity=data.rf_accrual_sensitivity,
                                    context_bundle=context)
record = {'scope': 'development only, through 2016-12-30; actual computed values',
          'dataset_id': data.manifest.dataset_id, 'context_id': context.context_id,
          'config_hash': cfg.config_hash,
          'tables': {kind: {name: table.to_dict(orient='records') for name, table in values.items()}
                     for kind, values in bundle.items()}}
out = root / 'audit/step4_review/CODEX_VERIFIED_STEP4_RESULTS.json'
out.write_text(json.dumps(record, indent=2, default=str) + '\n', encoding='utf-8')

names = ['min_variance', 'equal_weight', 'benchmark_60_40']
sensitivity = {name: bundle['rf_sensitivity'][name].set_index('metric') for name in names}
rows = ['| Metric | `min_variance` Primary `/252` | `min_variance` 91d Accrual | Difference (`Accrual - Primary`) | `equal_weight` Difference | `benchmark_60_40` Difference |',
        '|---|---:|---:|---:|---:|---:|']
for metric, row in sensitivity['min_variance'].iterrows():
    rows.append(f"| `{metric}` | `{float(row['primary_r3_value']):.9f}` | `{float(row['accrual_91d_value']):.9f}` | `{float(row['difference']):+.9f}` | `{float(sensitivity['equal_weight'].loc[metric, 'difference']):+.9f}` | `{float(sensitivity['benchmark_60_40'].loc[metric, 'difference']):+.9f}` |")
doc_path = root / 'docs/sections/a_kpis_and_capm.md'
doc = doc_path.read_text(encoding='utf-8-sig')
start = doc.index('| Metric | `min_variance` Primary `/252`')
end = doc.index('### Table 5C', start)
doc = doc[:start] + '\n'.join(rows) + '\n\n' + doc[end:]

adf_cells = []
for name in names:
    table = bundle['stationarity'][name]
    simple = table.loc[table['series'] == f'{name}_simple_return'].iloc[0]
    log = table.loc[table['series'] == f'{name}_log1p_return'].iloc[0]
    adf_cells.append(f"`{float(simple['adf_stat']):.4f}` / `{float(log['adf_stat']):.4f}`")
adf_line = '| Strategy return ADF $t$-stat (`simple` / `log1p`) | ' + ' | '.join(adf_cells) + ' | Statistics only; refer to the verified JSON for p-values/lags. Unit-root rejection does not imply i.i.d. or constant volatility. |'
doc, n = re.subn(r'^\| Strategy return ADF .*$', lambda _: adf_line, doc, flags=re.MULTILINE)
assert n == 1
notice = ('\nVerified numerical source: `audit/step4_review/CODEX_VERIFIED_STEP4_RESULTS.json`. '
          'Table 5B and the ADF row were refreshed by Codex from actual development computations; '
          'use the saved tables rather than copied chat figures.\n')
if 'Verified numerical source: `audit/step4_review/CODEX_VERIFIED_STEP4_RESULTS.json`' not in doc:
    doc += notice
doc_path.write_text(doc, encoding='utf-8')
print('Recorded actual development tables; refreshed RF sensitivity and ADF documentation.')
print('Min-variance annual Jensen alpha sensitivity:', sensitivity['min_variance'].loc['jensen_alpha', 'difference'])
print(out.relative_to(root).as_posix())
