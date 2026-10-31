"""Read-only independent Step 5 review; synthetic probes and development-only data."""
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

import numpy as np
import pandas as pd

from quantedge.config import load_config
from quantedge.contracts import CANONICAL_TICKERS
from quantedge.data import load_data
from quantedge.es import empirical_tail_weights, empirical_var_and_es
from quantedge.var import build_development_c1_risk_bundle, estimate_risk

ROOT = Path(__file__).resolve().parents[2]
cfg = load_config(ROOT / 'config.yaml')
out = {'scope': 'read-only runtime; synthetic checks and development-only risk results'}
rng = np.random.default_rng(50113)
cases = 0
maximum_tail_error = 0.
for i in range(450):
    n = int(rng.integers(1, 151))
    raw = [int(x) for x in rng.integers(-9, 13, n)]
    c = [0.5, .75, .8, .85, .9, .95, .99][i % 7]
    fraction_c = Fraction(str(c))
    descending = sorted(raw, reverse=True)
    mass = Fraction(n) * (1 - fraction_c)
    remain = mass
    weighted = Fraction(0)
    for loss in descending:
        take = min(Fraction(1), remain)
        weighted += take * loss
        remain -= take
        if remain == 0:
            break
    exact_es = float(weighted / mass)
    exact_var = sorted(raw)[math.ceil(Fraction(n) * fraction_c) - 1]
    losses = pd.Series(raw, index=[f'row_{j}' for j in range(n)], dtype=float)
    v, e, w, _ = empirical_var_and_es(losses, c)
    assert v == exact_var, (n, c, v, exact_var)
    maximum_tail_error = max(maximum_tail_error, abs(e - exact_es))
    assert abs(e - exact_es) < 1e-12
    assert abs(float(w.sum()) - 1.) < 1e-12 and float(w.min()) >= 0
    shuffled = losses.sample(frac=1, random_state=i)
    shuffled_w = empirical_tail_weights(shuffled, c).reindex(losses.index)
    assert np.array_equal(w.to_numpy(), shuffled_w.to_numpy())
    cases += 1
out['fraction_rational_tail_oracle'] = {'cases': cases, 'max_es_absolute_error': maximum_tail_error,
                                      'exact_var_and_permutation_checks': True}

saved_path = ROOT / 'results/step5_development_c1_risk_tables.json'
saved = json.loads(saved_path.read_text())
def reject_non_json_number(token):
    raise ValueError(f'Non-standard JSON numeric token: {token}')
try:
    json.loads(saved_path.read_text(), parse_constant=reject_non_json_number)
    out['strict_json_export_probe'] = {'strict_parse_succeeds': True}
except ValueError as exc:
    out['strict_json_export_probe'] = {'strict_parse_succeeds': False, 'error': str(exc)}
    (Path(__file__).parent / 'baseline_step5_results.json').write_bytes(saved_path.read_bytes())
bundle = load_data(cfg, offline=True)
dev = bundle.simple_returns.loc[:cfg.chronology.development_end].copy()
diffs = []
normal_diffs = []
mc_standardised_errors = []
for win, portfolios in saved['comparison_tables'].items():
    sample = dev.iloc[-1260:] if win == 'recent_development_1260d' else dev
    for name, rows in portfolios.items():
        weights = pd.Series(saved['exposures'][name]['weights'], index=CANONICAL_TICKERS)
        losses = [float(-sum(float(r) * float(weights[t]) for r, t in zip(row, CANONICAL_TICKERS)))
                  for row in sample.to_numpy()]
        mean_loss = statistics.mean(losses)
        sigma = statistics.stdev(losses)
        for row in rows:
            c = row['confidence']
            actual = estimate_risk(sample, weights, model=row['model'], confidence=c, seed=saved['monte_carlo_seed'])
            diffs.extend([abs(float(actual.var_loss) - row['var_loss']), abs(float(actual.es_loss) - row['es_loss'])])
            if row['model'] == 'parametric_normal':
                z = statistics.NormalDist().inv_cdf(c)
                v = mean_loss + sigma * z
                e = mean_loss + sigma * math.exp(-z*z/2) / math.sqrt(2*math.pi) / (1-c)
                normal_diffs.extend([abs(v-row['var_loss']), abs(e-row['es_loss'])])
            elif row['model'] == 'historical':
                # Independent scalar sorting and partial-last-observation integration.
                descending = sorted(losses, reverse=True)
                mass = Fraction(len(losses)) * (1-Fraction(str(c)))
                full = int(mass)
                partial = float(mass-full)
                es = (math.fsum(descending[:full]) + (partial*descending[full] if partial else 0)) / float(mass)
                v = sorted(losses)[math.ceil(len(losses)*Fraction(str(c))) - 1]
                normal_diffs.extend([abs(v-row['var_loss']), abs(es-row['es_loss'])])
            assert row['n_obs'] == len(sample)
            assert math.isclose(row['var_usd'], row['var_loss']*saved['nav_usd'], abs_tol=1e-8)
            assert math.isclose(row['es_usd'], row['es_loss']*saved['nav_usd'], abs_tol=1e-8)
    for c, stats in saved['mc_uncertainty'][win].items():
        for metric in ['var', 'es']:
            key = f'empirical_{metric}_se'
            if key in stats and stats[key] > 0:
                mc_standardised_errors.append(abs(stats[f'primary_seed_{metric}_diff_vs_analytic'])/stats[key])
assert max(diffs) < 1e-14
assert max(normal_diffs) < 1e-12
out['development_risk_oracle'] = {'rows': sum(len(r) for p in saved['comparison_tables'].values() for r in p.values()),
    'saved_vs_current_max_error': max(diffs), 'scalar_normal_empirical_oracle_max_error': max(normal_diffs),
    'usd_and_sample_checks': True}

# A different supplied AppConfig must not silently mix its recorded MC count
# with a baseline-global count inside the actual comparison estimates.
toy = pd.DataFrame(rng.normal(.0002, .01, (80, 7)),
                   index=pd.bdate_range('2015-01-02', periods=80), columns=CANONICAL_TICKERS)
custom = replace(cfg, portfolio=replace(cfg.portfolio, estimation_window_days=20),
                 risk=replace(cfg.risk, dashboard_risk_window_days=40, monte_carlo_simulations=111),
                 seeds=replace(cfg.seeds, monte_carlo=42))
try:
    custom_bundle = build_development_c1_risk_bundle(toy, custom)
    counts = set()
    for portfolios in custom_bundle['comparison_tables'].values():
        for table in portfolios.values():
            counts.update(int(v) for v in table.loc[table.model == 'monte_carlo_normal', 'monte_carlo_simulations'])
    out['config_count_probe'] = {'rejected_incompatible_config': False,
        'bundle_claimed_simulations': custom_bundle['monte_carlo_simulations'],
        'actual_comparison_simulations': sorted(counts),
        'uncertainty_simulations': custom_bundle['mc_uncertainty']['recent_development_1260d']['c_95']['monte_carlo_simulations_per_rep']}
except (ValueError, RuntimeError) as exc:
    out['config_count_probe'] = {'rejected_incompatible_config': True, 'error': str(exc)}

hash_count = 0
for path in list((ROOT/'data/processed').glob('*/manifest.json')) + [ROOT/'data/reference/context/context_manifest.json']:
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    for name, expected in manifest['file_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected
        hash_count += 1
out['data_hashes'] = {'matching': hash_count, 'expected': 53}
checkpoint = json.loads((ROOT/'audit/step4_review/CODEX_CLOSURE_CHECKPOINT.json').read_text())
for name in ['src/quantedge/portfolio.py', 'src/quantedge/kpis.py', 'src/quantedge/data.py']:
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == checkpoint['sha256'][name]
out['accepted_step3_4_sources'] = 'unchanged'
for name in ['config.yaml','requirements.txt','src/quantedge/contracts.py','data/processed/active_snapshot.json']:
    original = subprocess.run(['git','show',f'HEAD:{name}'],cwd=ROOT,capture_output=True,check=True).stdout
    assert original.replace(b'\r\n',b'\n') == (ROOT/name).read_bytes().replace(b'\r\n',b'\n')
out['protected_files'] = 'unchanged'
out['source_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                       ['src/quantedge/var.py','src/quantedge/es.py','tests/test_c_var_es.py',
                        'results/step5_development_c1_risk_tables.json']}
(Path(__file__).parent/'verification.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2))
