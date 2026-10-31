"""Export completed Steps 1-4 as development-only figures/tables for review.

Run with the verified project Python. Rendering uses matplotlib installed in the
isolated, ignored tmp/figure_export_deps directory, or an existing installation.
It does not add dependencies to the application or evaluate holdout strategies.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
render_deps = ROOT / 'tmp/figure_export_deps'
if render_deps.exists():
    sys.path.insert(0, str(render_deps))

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, MaxNLocator
import numpy as np
import pandas as pd

from quantedge.config import load_config
from quantedge.data import load_data
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    out = ROOT / 'results/development_preview'
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(ROOT / 'config.yaml')
    verified_path = ROOT / 'audit/step4_review/CODEX_VERIFIED_STEP4_RESULTS.json'
    checkpoint = json.loads((ROOT / 'audit/step4_review/CODEX_CLOSURE_CHECKPOINT.json').read_text())
    for name in ['src/quantedge/portfolio.py', 'src/quantedge/kpis.py', 'src/quantedge/data.py']:
        assert sha(ROOT / name) == checkpoint['sha256'][name], f'Reviewed source changed: {name}'
    verified = json.loads(verified_path.read_text(encoding='utf-8'))
    assert verified['config_hash'] == cfg.config_hash
    data = load_data(cfg, offline=True)
    assert verified['dataset_id'] == data.manifest.dataset_id
    dev = data.simple_returns.loc[:cfg.chronology.development_end].copy()
    paths = {name: build_portfolio_path(dev, spec, cfg)
             for name, spec in make_core_strategy_specs(cfg).items()}
    keys = ['min_variance', 'equal_weight', 'benchmark_60_40']
    labels = {'min_variance': 'Constrained minimum variance', 'equal_weight': 'Equal weight reference',
              'benchmark_60_40': '60/40 SPY/AGG reference'}
    short = ['Min variance', 'Equal weight', '60/40']
    colors = {'min_variance': '#147D73', 'equal_weight': '#CF6A32', 'benchmark_60_40': '#314C78'}
    tables = verified['tables']
    kpi = {name: pd.DataFrame(tables['kpis'][name]).set_index('metric') for name in keys}
    unit = kpi[keys[0]]['unit']
    wide = pd.DataFrame({name: kpi[name]['value'] for name in keys})
    wide.insert(0, 'unit', unit)
    wide.to_csv(out / '01_kpi_comparison.csv', float_format='%.12g', na_rep='unavailable')
    for kind, filename in [('rf_sensitivity', '02_rf_sensitivity.csv'),
                           ('ex_post_real_returns', '03_real_returns.csv'),
                           ('distribution_income', '04_distribution_income.csv'),
                           ('stationarity', '05_stationarity.csv')]:
        frames = [pd.DataFrame(tables[kind][name]).assign(strategy=name) for name in keys]
        pd.concat(frames, ignore_index=True).to_csv(out / filename, index=False, float_format='%.12g')
    frame = pd.concat({name: pd.DataFrame({'gross_return': path.gross_returns,
                                          'net_return': path.net_returns, 'wealth': path.wealth,
                                          'drawdown': path.drawdown, 'turnover': path.turnover,
                                          'cost': path.costs}) for name, path in paths.items()}, axis=1)
    frame.columns = [f'{name}__{metric}' for name, metric in frame.columns]
    frame.to_csv(out / '06_portfolio_paths.csv', index_label='date', float_format='%.16g')
    mv = paths['min_variance']
    mv.weights_before.to_csv(out / '07_min_variance_holdings.csv', index_label='date', float_format='%.16g')
    compliance = [{'strategy': name, 'constraint_scope': path.metadata['constraint_enforcement_scope'],
                   'rebalance_targets_feasible': path.metadata['mandate_feasible_all_rebalances'],
                   'active_sessions': len(path.net_returns),
                   'pre_return_cap_breach_sessions': path.metadata['pre_return_holdings_compliance']['n_breach_sessions'],
                   'status': path.metadata['mandate_compliance_status']} for name, path in paths.items()]
    pd.DataFrame(compliance).to_csv(out / '08_constraint_scope.csv', index=False)
    verified_path_bytes = verified_path.read_bytes()
    (out / 'verified_step4_tables.json').write_bytes(verified_path_bytes)

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 12,
                         'axes.labelsize': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.edgecolor': '#AAB6C2', 'axes.labelcolor': '#24364A',
                         'text.color': '#182D43', 'xtick.color': '#46586A', 'ytick.color': '#46586A',
                         'grid.color': '#DCE3E8', 'grid.alpha': .65, 'figure.facecolor': 'white',
                         'savefig.facecolor': 'white', 'svg.fonttype': 'none'})
    period = f'{mv.net_returns.index[0]:%Y-%m-%d} to {mv.net_returns.index[-1]:%Y-%m-%d}'
    footnote = ('DEVELOPMENT SAMPLE | Provisional assumptions; committee decision pending.\n'
                'Net of 5 bps per traded leg. Reference portfolios are unconstrained comparisons.')
    figures = []
    rendering_versions = {name: importlib.metadata.version(name) for name in
                          ['matplotlib', 'contourpy', 'cycler', 'fonttools', 'kiwisolver', 'pyparsing']}
    (out / 'rendering-requirements.txt').write_text(
        '\n'.join(f'{name}=={version}' for name, version in rendering_versions.items()) + '\n',
        encoding='utf-8')
    (out / 'README.md').write_text(
        '# Verified development figures and tables\n\n'
        f'Active development period: {period}; {len(mv.net_returns):,} return sessions.\n\n'
        'Open index.html to browse all four figures and the KPI comparison. PNG files are '
        '300 dpi; SVG files are vector exports. CSV and JSON files contain actual computed '
        'values, with fractions/annual fractions explicitly labelled. Multiply fractions '
        'by 100 for percent display. Unavailable metrics are not zero.\n\n'
        'These outputs cover completed Steps 1-4 under provisional assumptions. They are '
        'development previews, not final evaluation results or a signed recommendation. '
        'Equal-weight and 60/40 are unconstrained references. Caps apply at rebalance '
        'targets; between-trade breaches are reported in 08_constraint_scope.csv.\n\n'
        'VaR/ES, validation, EVT and stress figures will be generated after the respective '
        'steps pass review. The final report/app must use one frozen result bundle.\n\n'
        'Reproduce from the repository root using the verified Python3.11 .venv:\n\n'
        '```powershell\n'
        '.\\.venv\\Scripts\\python.exe -m pip install --no-deps --target tmp\\figure_export_deps '
        '-r results\\development_preview\\rendering-requirements.txt\n'
        '.\\.venv\\Scripts\\python.exe scripts\\export_verified_development_preview.py\n'
        '```\n\n'
        'Rendering dependencies stay in the ignored tmp directory; the application '
        'requirements are unchanged. manifest.json records source and artifact hashes.\n',
        encoding='utf-8')

    def finish(fig, filename, title):
        fig.text(.07, .97, 'QUANT EDGE  /  VERIFIED DEVELOPMENT PREVIEW', fontsize=9,
                 color='#147D73', weight='bold', va='top')
        fig.text(.07, .925, title, fontsize=20, weight='bold', va='top')
        fig.text(.07, .877, period, fontsize=10, color='#5C6C7A', va='top')
        fig.text(.07, .035, footnote, fontsize=8, color='#5C6C7A', va='bottom', linespacing=1.5)
        fig.savefig(out / (filename + '.png'), dpi=300)
        fig.savefig(out / (filename + '.svg'))
        plt.close(fig)
        figures.append((filename, title))

    fig, axes = plt.subplots(2, 1, figsize=(11.7, 8.3), sharex=True,
                             gridspec_kw={'height_ratios': [1.6, 1]})
    fig.subplots_adjust(left=.085, right=.96, top=.80, bottom=.16, hspace=.16)
    for name, path in paths.items():
        anchor = pd.Timestamp(path.rebalances.iloc[0]['decision_date'])
        index = pd.DatetimeIndex([anchor]).append(path.wealth.index)
        axes[0].plot(index, np.r_[1., path.wealth.to_numpy()] * 10,
                     label=labels[name], color=colors[name], linewidth=1.8)
        axes[1].plot(index, np.r_[0., path.drawdown.to_numpy()] * 100,
                     color=colors[name], linewidth=1.3)
    axes[0].set_ylabel('Portfolio value (USD million)')
    axes[0].legend(loc='upper left', frameon=False, ncol=1, fontsize=9)
    axes[1].set_ylabel('Drawdown (%)')
    axes[1].xaxis.set_major_locator(mdates.YearLocator(2))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    axes[1].axhline(0, color='#8B9CA9', linewidth=.7)
    for ax in axes:
        ax.grid(axis='y')
        ax.set_axisbelow(True)
    finish(fig, 'figure_01_wealth_drawdown', 'Portfolio wealth and drawdown')

    asset_colors = ['#243E63', '#6B92AE', '#A9C7D7', '#147D73', '#D1A13A', '#CF6A32', '#8E6DA8']
    fig, (ax, bar) = plt.subplots(1, 2, figsize=(11.7, 7.6), gridspec_kw={'width_ratios': [2.5, 1]})
    fig.subplots_adjust(left=.075, right=.97, top=.78, bottom=.24, wspace=.28)
    ax.stackplot(mv.weights_before.index, mv.weights_before.to_numpy().T * 100,
                 labels=list(mv.weights_before.columns), colors=asset_colors, alpha=.95)
    ax.set_ylim(0, 100)
    ax.set_ylabel('Pre-return holdings (%)')
    ax.set_title('Holdings drift between monthly rebalances', loc='left', fontsize=11)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.legend(loc='upper left', bbox_to_anchor=(0, -.12), frameon=False, ncol=7, fontsize=8)
    last = mv.weights_before.iloc[-1] * 100
    bar.barh(list(last.index)[::-1], last.to_numpy()[::-1], color=asset_colors[::-1])
    bar.set_title('Holdings at development end', loc='left', fontsize=10)
    bar.set_xlabel('Weight (%)')
    bar.set_xlim(0, max(45, float(last.max()) * 1.25))
    for i, value in enumerate(last.to_numpy()[::-1]):
        bar.text(max(0, value) + .7, i, f'{value:.1f}%', va='center', fontsize=9)
    bar.grid(axis='x')
    bar.set_axisbelow(True)
    fig.text(.075, .115, 'Caps apply to rebalance targets; daily drift breaches are reported separately.',
             fontsize=8, color='#5C6C7A')
    finish(fig, 'figure_02_allocation', 'Constrained portfolio allocation')

    fig, axes = plt.subplots(2, 2, figsize=(11.7, 8.3))
    fig.subplots_adjust(left=.08, right=.96, top=.79, bottom=.16, hspace=.5, wspace=.28)
    specs = [('geometric_annual_return', 'Geometric annual return', 100, '%'),
             ('annualized_volatility', 'Annualised volatility', 100, '%'),
             ('sharpe_ratio', 'Sharpe ratio - daily RF excess', 1, ''),
             ('max_drawdown', 'Maximum drawdown - initial wealth included', 100, '%')]
    for ax, (metric, title, mult, suffix) in zip(axes.flat, specs):
        values = [float(kpi[name].loc[metric, 'value']) * mult for name in keys]
        ax.bar(short, values, color=[colors[name] for name in keys], width=.58)
        ax.set_title(title, loc='left', fontsize=10)
        ax.grid(axis='y')
        ax.set_axisbelow(True)
        lo, hi = min(0, min(values)), max(0, max(values))
        span = hi - lo if hi > lo else 1
        ax.set_ylim(lo - .23 * span, hi + .28 * span)
        for i, value in enumerate(values):
            ax.text(i, value + (.07 * span if value >= 0 else -.07 * span),
                    f'{value:.2f}{suffix}', ha='center', va='bottom' if value >= 0 else 'top', fontsize=10)
        ax.yaxis.set_major_locator(MaxNLocator(5))
    finish(fig, 'figure_03_kpis', 'Return, risk and performance comparisons')

    real = {name: pd.DataFrame(tables['ex_post_real_returns'][name]).set_index('metric') for name in keys}
    income = {name: pd.DataFrame(tables['distribution_income'][name]).set_index('metric') for name in keys}
    fig, axes = plt.subplots(1, 2, figsize=(11.7, 7.1))
    fig.subplots_adjust(left=.08, right=.96, top=.76, bottom=.23, wspace=.30)
    x = np.arange(3)
    for i, (metric, label, color) in enumerate([
            ('ex_post_nominal_annual_return_common_months', 'Nominal', '#314C78'),
            ('ex_post_real_annual_return_common_months', 'After CPI inflation', '#147D73')]):
        values = [float(real[name].loc[metric, 'value']) * 100 for name in keys]
        axes[0].bar(x + (i - .5) * .32, values, .30, label=label, color=color)
    axes[0].set_xticks(x, short)
    axes[0].set_ylabel('Annualised return (%)')
    axes[0].set_title('119 complete months: 2007-02 to 2016-12', loc='left', fontsize=10)
    axes[0].legend(frameon=False, loc='upper right', fontsize=9)
    axes[0].set_ylim(0, 8.5)
    yields = [float(income[name].loc['ending_trailing_12m_distribution_yield', 'value']) * 100 for name in keys]
    axes[1].bar(short, yields, color=[colors[name] for name in keys], width=.58)
    axes[1].set_ylabel('Trailing-365-day distribution yield (%)')
    axes[1].set_title('Development-end income context: 2016-12-30', loc='left', fontsize=10)
    axes[1].set_ylim(0, max(yields) * 1.4)
    for i, value in enumerate(yields):
        axes[1].text(i, value + .06, f'{value:.2f}%', ha='center', fontsize=10)
    for ax in axes:
        ax.grid(axis='y')
        ax.set_axisbelow(True)
    fig.text(.08, .13, 'CPI uses published endpoint levels ex post. Distribution income is already included in total returns.',
             fontsize=9, color='#5C6C7A')
    finish(fig, 'figure_04_income_real_returns', 'Purchasing power and distribution income')

    caption = ('Verified development sample only. Final selection/evaluation-period outputs and '
               'the committee recommendation remain pending. VaR/ES, backtest, EVT and stress '
               'figures will be generated after those modules pass review.')
    sections = ''.join(f'<section><h2>{html.escape(title)}</h2><a href="{name}.png"><img src="{name}.svg" '
                       f'alt="{html.escape(title)}"></a><p><a href="{name}.png">300-dpi PNG</a> '
                       f'&middot; <a href="{name}.svg">Vector SVG</a></p></section>' for name, title in figures)
    downloads = ''.join(f'<li><a href="{path.name}">{path.name}</a></li>' for path in sorted(out.glob('*.csv')))
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Quant Edge development outputs</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;background:#f1f5f8;color:#182d43;margin:0}}main{{max-width:1120px;margin:auto;padding:36px 24px}}h1{{font-size:34px;margin-bottom:12px}}section{{background:white;padding:24px;margin:24px 0;border:1px solid #dce3e8;border-radius:12px}}img{{width:100%;height:auto}}a{{color:#147d73}}.notice{{background:#e2eeec;padding:20px;border-left:5px solid #147d73}}table{{border-collapse:collapse;font-size:13px;width:100%}}td,th{{padding:8px;border-bottom:1px solid #dde4e9;text-align:right}}td:first-child,th:first-child{{text-align:left}}.scroll{{overflow:auto}}code{{font-size:12px;overflow-wrap:anywhere}}</style>
<main><p>QUANT EDGE / COMPLETED STEPS 1-4</p><h1>Verified development outputs</h1>
<div class="notice">{caption}<br><strong>Period:</strong> {period}; 2,516 active sessions; provisional constraints.</div>
{sections}<section><h2>KPI comparison - machine-readable values</h2><div class="scroll">{wide.to_html(na_rep='unavailable', float_format=lambda value: f'{value:.8f}', border=0)}</div></section>
<section><h2>Data tables</h2><ul>{downloads}</ul><a href="verified_step4_tables.json">Verified Step 4 JSON</a><p>Dataset: <code>{data.manifest.dataset_id}</code><br>Config: <code>{cfg.config_hash}</code></p></section></main></html>'''
    (out / 'index.html').write_text(page, encoding='utf-8')
    manifest = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': caption,
                'development_end': cfg.chronology.development_end, 'active_start': str(mv.net_returns.index[0].date()),
                'active_end': str(mv.net_returns.index[-1].date()), 'n_active_sessions': len(mv.net_returns),
                'dataset_id': data.manifest.dataset_id, 'config_hash': cfg.config_hash,
                'rendering_versions': rendering_versions,
                'reviewed_table_source_sha256': sha(verified_path),
                'source_sha256': {name: sha(ROOT / name) for name in ['src/quantedge/portfolio.py',
                                  'src/quantedge/kpis.py', 'scripts/export_verified_development_preview.py']},
                'artifacts_sha256': {path.name: sha(path) for path in sorted(out.iterdir())
                                     if path.is_file() and path.name != 'manifest.json'}}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Exported {len(figures)} figures (PNG + SVG), 8 CSV tables, JSON and index.html.')
    print(out)


if __name__ == '__main__':
    main()
