"""Independent Step 3 review probes; no runtime edits, downloads or holdout outcomes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from quantedge.config import load_config
from quantedge.contracts import CANONICAL_TICKERS, StrategySpec
from quantedge.data import load_data
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


cfg = load_config(ROOT / 'config.yaml')
out = {'scope': 'read-only runtime review; synthetic probes and development-only path checks'}

# A conflicting specification should not silently substitute an arbitrary fixed
# portfolio for a strategy advertised as minimum variance.
toy = pd.DataFrame(0.0, index=pd.bdate_range('2010-01-04', periods=4), columns=CANONICAL_TICKERS)
all_spy = dict.fromkeys(CANONICAL_TICKERS, 0.0)
all_spy['SPY'] = 1.0
conflict = StrategySpec(strategy_id='conflicting_minvar_probe', objective='min_variance',
                        estimation_window_days=2, covariance_estimator='unsupported_probe',
                        fixed_weights=all_spy)
path = build_portfolio_path(toy, conflict, cfg)
out['conflicting_specification'] = {
    'accepted': True, 'advertised_objective': path.metadata['objective'],
    'actual_solver': path.rebalances.iloc[0]['solver_status'],
    'spy_weight': float(path.weights_before.iloc[0]['SPY']),
    'constraint_feasible': bool(path.rebalances.iloc[0]['mandate_feasible']),
}
assert out['conflicting_specification']['spy_weight'] == 1.0
assert out['conflicting_specification']['constraint_feasible'] is False

# Rebalance-target compliance and holdings compliance are distinct.
drift = toy.iloc[:3].copy()
drift.iloc[0, drift.columns.get_loc('SPY')] = 0.20
fixed = StrategySpec(strategy_id='drift_scope_probe', objective='fixed_weights',
                     estimation_window_days=None, fixed_weights=cfg.portfolio.illustrative_weights)
drift_path = build_portfolio_path(drift, fixed, cfg)
equities = ['SPY', 'EFA', 'EEM', 'XLE', 'XLK']
out['compliance_scope'] = {
    'reported_status': drift_path.metadata['mandate_compliance_status'],
    'all_rebalance_targets_feasible': drift_path.metadata['mandate_feasible_all_rebalances'],
    'next_session_equity_weight': float(drift_path.weights_before.iloc[1][equities].sum()),
    'equity_cap': cfg.portfolio.constraints.max_equity_weight,
}
assert out['compliance_scope']['next_session_equity_weight'] > out['compliance_scope']['equity_cap']

# Independent units/holdings ledger for the declared multiplicative-cost convention.
rng = np.random.default_rng(3301)
synthetic = pd.DataFrame(rng.normal(0, .01, (48, 7)),
                         index=pd.bdate_range('2010-01-15', periods=48), columns=CANONICAL_TICKERS)
reference = StrategySpec(strategy_id='ledger', objective='benchmark_60_40', estimation_window_days=None)
ledger_path = build_portfolio_path(synthetic, reference, cfg)
prices = np.ones(7)
units = np.zeros(7)
wealth = 1.0
target = np.array([.6, 0, 0, .4, 0, 0, 0])
ledger_wealth = []
for i, (day, row) in enumerate(synthetic.iterrows()):
    boundary = i == 0 or day.month != synthetic.index[i - 1].month
    if boundary:
        current = units * prices
        pre_weights = current / wealth
        turnover = float(np.abs(target - pre_weights).sum())
        wealth *= 1 - cfg.portfolio.transaction_cost_bps_one_way / 10000 * turnover
        units = target * wealth / prices
    prices *= 1 + row.to_numpy()
    wealth = float(units @ prices)
    ledger_wealth.append(wealth)
ledger_error = float(np.max(np.abs(np.array(ledger_wealth) - ledger_path.wealth.to_numpy())))
assert ledger_error < 1e-12
out['independent_units_ledger'] = {'sessions': 48, 'max_absolute_wealth_difference': ledger_error}

# Prefix invariance uses a physically truncated frame, not just changed future rows.
random_spec = make_core_strategy_specs(cfg, estimation_window_days=20)['min_variance']
full = build_portfolio_path(synthetic, random_spec, cfg)
prefix = build_portfolio_path(synthetic.iloc[:37].copy(), random_spec, cfg)
pd.testing.assert_frame_equal(full.weights_before.loc[prefix.weights_before.index], prefix.weights_before,
                              check_exact=True)
pd.testing.assert_series_equal(full.wealth.loc[prefix.wealth.index], prefix.wealth, check_exact=True)
out['truncated_prefix_invariance'] = 'passed, exact weights and wealth'

# Same already-authorized development slice as the supplied smoke test.
bundle = load_data(cfg, offline=True)
dev = bundle.simple_returns.loc[:cfg.chronology.development_end].copy()
dev_path = build_portfolio_path(dev, make_core_strategy_specs(cfg)['min_variance'], cfg)
wb = dev_path.weights_before
breaches = (wb.max(axis=1) > .4 + 1e-7) | (wb[equities].sum(axis=1) > .35 + 1e-7)
out['development_weight_monitoring'] = {
    'active_start': str(wb.index[0].date()), 'active_end': str(wb.index[-1].date()),
    'n_active': len(wb), 'feasible_rebalance_targets': int(dev_path.rebalances['mandate_feasible'].sum()),
    'n_rebalances': len(dev_path.rebalances),
    'pre_return_sessions_with_drifted_cap_breach': int(breaches.sum()),
    'max_single_weight': float(wb.max().max()),
    'max_equity_group_weight': float(wb[equities].sum(axis=1).max()),
}

# Correct mathematical certificate is gap >= f(w)-f*, without a universal factor 2.
out['documentation_counterexample'] = {'f': 'x**2 on [1,2]', 'x': 2, 'x_star': 1,
                                      'fw_gap': 4, 'primal_error': 3, 'twice_primal_error': 6}

checks = {}
for manifest_file in sorted((ROOT / 'data/processed').glob('*/manifest.json')):
    manifest = json.loads(manifest_file.read_text(encoding='utf-8-sig'))
    matches = [sha(ROOT / file) == expected for file, expected in manifest['file_sha256'].items()]
    assert all(matches)
    checks[manifest['dataset_id']] = len(matches)
out['snapshot_hashes'] = {'verified': sum(checks.values()), 'by_dataset': checks}
baseline = json.loads((ROOT / 'tmp/prompt_update_baseline.json').read_text(encoding='utf-8-sig'))
changed = [file for file, expected in baseline.items() if sha(ROOT / file) != expected]
assert set(changed) == {'src\\quantedge\\portfolio.py', 'tests\\test_d_setup.py'}
out['baseline_runtime_changes'] = changed
for file in ['config.yaml', 'requirements.txt', 'src/quantedge/contracts.py', 'data/processed/active_snapshot.json']:
    original = subprocess.run(['git', 'show', f'HEAD:{file}'], cwd=ROOT, capture_output=True, check=True).stdout
    # Git autocrlf changes line endings of text files; content comparisons normalize them.
    assert original.replace(b'\r\n', b'\n') == (ROOT / file).read_bytes().replace(b'\r\n', b'\n'), file
out['config_hash'] = cfg.config_hash
out['reviewed_source_sha256'] = {
    file: sha(ROOT / file) for file in ['src/quantedge/portfolio.py', 'tests/test_b_portfolio.py',
                                      'tests/test_d_setup.py', 'docs/sections/b_portfolio_construction.md']
}
out['protected_git_content'] = 'config, requirements, contracts and active pointer unchanged'
out['holdout_strategy_outcomes'] = 'not computed; source load only, paths restricted to development'
(Path(__file__).parent / 'verification.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
print(json.dumps(out, indent=2))
