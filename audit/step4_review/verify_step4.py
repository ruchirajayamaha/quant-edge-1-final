"""Independent Step 4 review: synthetic probes, development-only oracles and hashes.

This records demonstrated pre-fix problems. It is not a production regression
suite to preserve unchanged after fixes. No source data or runtime code is edited.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from quantedge.config import load_config
from quantedge.data import DataUnavailableError, load_context_data, load_data
from quantedge.kpis import compute_ex_post_real_return_metrics, compute_kpis
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs
from quantedge.returns import expected_nyse_sessions

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

cfg = load_config(ROOT / 'config.yaml')
out = {'scope': 'runtime read-only; synthetic repros; development-only strategy checks'}

dates = pd.bdate_range('2010-01-04', periods=4)
p = pd.Series([.0001, .0002, .0003, .0004], index=dates)
b = pd.Series([.00005, .0003, -.0001, .0002], index=dates)
m = pd.Series([.001, -.002, .002, -.001], index=dates)
rf = pd.Series(.00025, index=dates)
try:
    compute_kpis(p, b, m, rf)
    out['r1_positive_returns_below_rf'] = {'crashes': False}
except Exception as exc:
    out['r1_positive_returns_below_rf'] = {'crashes': True, 'type': type(exc).__name__, 'message': str(exc)}
assert out['r1_positive_returns_below_rf']['crashes']
assert out['r1_positive_returns_below_rf']['type'] == 'TypeError'

days = expected_nyse_sessions('2010-01-01', '2010-05-31')
zero_returns = pd.Series(0., index=days)
cpi = pd.Series([100., 101., np.nan, 121., 122., 123.],
                index=pd.period_range('2009-12', '2010-05', freq='M'))
real = compute_ex_post_real_return_metrics(zero_returns, cpi)
summary = real.attrs['common_months_summary']
out['r2_interior_cpi_gap'] = {
    'declared_start': summary['first_common_month'], 'declared_end': summary['last_common_month'],
    'months_used': summary['n_common_complete_months'], 'calendar_months_in_span': 5,
    'computed_cpi_multiplier': summary['cpi_index_ratio'],
    'declared_endpoint_cpi_multiplier': 123 / 100,
    'reported_excluded_cpi_months': summary['unreleased_or_missing_cpi_months_excluded'],
    'all_statuses': list(real['status']),
    'real_annual_return': float(real.set_index('metric').loc['ex_post_real_annual_return_common_months', 'value']),
}
assert summary['n_common_complete_months'] == 3
assert not math.isclose(summary['cpi_index_ratio'], 123 / 100)

jan_days = expected_nyse_sessions('2010-01-01', '2010-01-31')
bad_days = jan_days.delete(1).append(pd.DatetimeIndex(['2010-01-09'])).sort_values()
bad_month_returns = pd.Series(0., index=bad_days)
bad_real = compute_ex_post_real_return_metrics(bad_month_returns, cpi)
out['r2_month_coverage_count_only'] = {
    'missing_nyse_date': str(jan_days[1].date()), 'unexpected_saturday': '2010-01-09',
    'observed_rows': len(bad_days), 'expected_nyse_rows': len(jan_days),
    'falsely_counted_complete_months': bad_real.attrs['common_months_summary']['n_common_complete_months'],
}
assert out['r2_month_coverage_count_only']['falsely_counted_complete_months'] == 1

ctx = load_context_data(cfg, offline=True)
# Safe temporary workspace: verify path scope before TemporaryDirectory cleanup.
tmp_parent = (ROOT / 'tmp').resolve()
tmp_parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='step4_cache_probe_', dir=tmp_parent) as name:
    temporary = Path(name).resolve()
    assert temporary.is_relative_to(tmp_parent)
    copied = temporary / 'context'
    shutil.copytree(ROOT / 'data/reference/context', copied)
    altered_path = copied / 'etf_split_adjusted_closes.parquet'
    altered = pd.read_parquet(altered_path)
    original_first_price = float(altered.iloc[0, 0])
    altered.iloc[0, 0] = original_first_price * 1.10
    altered.to_parquet(altered_path)
    # The copied manifest still points to original repo-relative files, whose
    # hashes pass even though the actual payload being read was changed.
    try:
        loaded = load_context_data(cfg, offline=True, repo_root=ROOT, context_dir=copied)
        out['r3_custom_context_hash_bypass'] = {
            'tampered_copy_rejected': False, 'original_first_spy_price': original_first_price,
            'loaded_first_spy_price': float(loaded.split_adjusted_closes.iloc[0, 0]),
            'manifest_hash_unchanged': True,
        }
    except DataUnavailableError as exc:
        out['r3_custom_context_hash_bypass'] = {'tampered_copy_rejected': True, 'error': str(exc)}
assert out['r3_custom_context_hash_bypass']['tampered_copy_rejected'] is False
assert out['r3_custom_context_hash_bypass']['loaded_first_spy_price'] != original_first_price

older_cfg = replace(cfg, data=replace(cfg.data, frozen_end_date='2016-12-30'))
older_loaded = load_context_data(older_cfg, offline=True)
out['r3_cache_identity'] = {'requested_frozen_end': '2016-12-30',
                          'loaded_context_end': str(older_loaded.split_adjusted_closes.index[-1].date())}

# Independent actual headline calculations: Python statistics/math and statsmodels
# rather than the implementation's NumPy formulas and hand-coded OLS.
bundle = load_data(cfg, offline=True)
dev = bundle.simple_returns.loc[:cfg.chronology.development_end].copy()
paths = {name: build_portfolio_path(dev, spec, cfg)
         for name, spec in make_core_strategy_specs(cfg).items()}
path = paths['min_variance']
port = path.net_returns
bench = paths['benchmark_60_40'].net_returns
market = dev['SPY'].reindex(port.index)
rf_dev = bundle.rf_daily.reindex(port.index)
observed = compute_kpis(port, bench, market, rf_dev)
vals = observed.set_index('metric')['value'].to_dict()
pr = port.to_list()
ep = [float(a - c) for a, c in zip(port, rf_dev)]
em = [float(a - c) for a, c in zip(market, rf_dev)]
act = [float(a - c) for a, c in zip(port, bench)]
terminal = math.prod(1 + x for x in pr)
geo = terminal ** (252 / len(pr)) - 1
down = math.sqrt(252 * math.fsum(min(0, x) ** 2 for x in ep) / len(ep))
ols = sm.OLS(ep, sm.add_constant(em, has_constant='add')).fit()
wealth, peak, worst = 1., 1., 0.
for value in pr:
    wealth *= 1 + value
    peak = max(peak, wealth)
    worst = min(worst, wealth / peak - 1)
expected = {
    'geometric_annual_return': geo,
    'arithmetic_annual_return': 252 * statistics.mean(pr),
    'annualized_volatility': math.sqrt(252) * statistics.stdev(pr),
    'sharpe_ratio': math.sqrt(252) * statistics.mean(ep) / statistics.stdev(ep),
    'downside_deviation': down,
    'sortino_ratio': 252 * statistics.mean(ep) / down,
    'capm_beta': float(ols.params[1]), 'jensen_alpha': 252 * float(ols.params[0]),
    'treynor_ratio': 252 * statistics.mean(ep) / float(ols.params[1]),
    'tracking_error': math.sqrt(252) * statistics.stdev(act),
    'information_ratio': math.sqrt(252) * statistics.mean(act) / statistics.stdev(act),
    'max_drawdown': worst, 'calmar_ratio': geo / abs(worst),
}
diffs = {metric: abs(float(vals[metric]) - answer) for metric, answer in expected.items()}
assert max(diffs.values()) < 1e-10, diffs
out['independent_development_kpi_oracle'] = {
    'start': str(port.index[0].date()), 'end': str(port.index[-1].date()), 'n_obs': len(port),
    'metrics_checked': len(expected), 'max_absolute_difference': max(diffs.values()),
    'alpha_t_difference_vs_statsmodels': abs(float(observed.attrs['capm_regression']['alpha_t_stat']) - float(ols.tvalues[0])),
    'absolute_differences': diffs,
}

snapshot_checks = {}
for file in sorted((ROOT / 'data/processed').glob('*/manifest.json')):
    manifest = json.loads(file.read_text(encoding='utf-8-sig'))
    matches = [sha(ROOT / key) == expected for key, expected in manifest['file_sha256'].items()]
    assert all(matches)
    snapshot_checks[manifest['dataset_id']] = len(matches)
context_matches = [sha(ROOT / key) == expected for key, expected in ctx.manifest['file_sha256'].items()]
assert all(context_matches)
out['hashes'] = {'market_snapshots': sum(snapshot_checks.values()), 'context_files': len(context_matches),
                 'all_match': True}
out['context_numeric_checks'] = {
    'all_closes_finite_positive': bool(np.isfinite(ctx.split_adjusted_closes.to_numpy()).all()
                                      and (ctx.split_adjusted_closes.to_numpy() > 0).all()),
    'all_distributions_finite_nonnegative': bool(np.isfinite(ctx.distributions.to_numpy()).all()
                                               and (ctx.distributions.to_numpy() >= 0).all()),
}
for file in ['config.yaml', 'requirements.txt', 'src/quantedge/contracts.py', 'data/processed/active_snapshot.json']:
    original = subprocess.run(['git', 'show', f'HEAD:{file}'], cwd=ROOT, capture_output=True, check=True).stdout
    assert original.replace(b'\r\n', b'\n') == (ROOT / file).read_bytes().replace(b'\r\n', b'\n'), file
original_data = subprocess.run(['git', 'show', 'HEAD:src/quantedge/data.py'], cwd=ROOT,
                               capture_output=True, check=True).stdout.replace(b'\r\n', b'\n')
assert (ROOT / 'src/quantedge/data.py').read_bytes().replace(b'\r\n', b'\n').startswith(original_data.rstrip())
out['protected_files'] = 'config, dependencies, contracts, active pointer and pre-context data adapter unchanged'
out['reviewed_sha256'] = {name: sha(ROOT / name) for name in [
    'src/quantedge/kpis.py', 'src/quantedge/data.py', 'tests/test_a_kpis.py',
    'docs/sections/a_kpis_and_capm.md', 'data/reference/context/context_manifest.json']}
out['holdout_strategy_results'] = 'not computed; only development paths and synthetic probes'
(Path(__file__).parent / 'verification.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
for key in ['r1_positive_returns_below_rf', 'r2_interior_cpi_gap', 'r2_month_coverage_count_only', 'r3_custom_context_hash_bypass',
            'r3_cache_identity', 'independent_development_kpi_oracle', 'hashes']:
    print(key, json.dumps(out[key]))
