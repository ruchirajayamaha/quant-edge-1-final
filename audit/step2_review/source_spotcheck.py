"""Read-only public-source comparison; writes audit evidence, never the snapshot."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
POINTER = json.loads((ROOT / 'data/processed/active_snapshot.json').read_text())
SNAPSHOT = ROOT / 'data/processed' / POINTER['dataset_id']
SAVED = pd.read_parquet(SNAPSHOT / 'prices.parquet')
yf.set_tz_cache_location(str(OUT / 'yfinance_cache'))

windows = [
    ('covid_all_seven', list(SAVED.columns), '2020-03-06', '2020-03-19'),
    ('recent_all_seven', list(SAVED.columns), '2026-10-19', '2026-10-31'),
    ('agg_gfc_extreme', ['AGG'], '2008-10-09', '2008-10-14'),
    ('gold_extreme', ['GLD'], '2026-01-29', '2026-02-03'),
]
results = {'dataset_id': POINTER['dataset_id'], 'yahoo_windows': [], 'fred': {}}
for name, tickers, start, end in windows:
    item = {'name': name, 'tickers': tickers, 'start': start, 'end_exclusive': end}
    try:
        frame = yf.download(tickers, start=start, end=end, auto_adjust=False,
                            actions=True, repair=False, keepna=True, progress=False,
                            threads=True, timeout=8)
        if frame.empty or 'Adj Close' not in frame.columns.get_level_values(0):
            raise ValueError('No usable fresh Adj Close response')
        adjusted = frame['Adj Close'].copy()
        adjusted.index = pd.DatetimeIndex(adjusted.index).tz_localize(None).normalize()
        adjusted = adjusted.reindex(columns=tickers)
        common = adjusted.index.intersection(SAVED.index)
        fresh = adjusted.loc[common, tickers]
        old = SAVED.loc[common, tickers]
        valid = fresh.notna() & old.notna()
        n_valid = int(valid.sum().sum())
        if not n_valid:
            raise ValueError('No finite common source cells')
        relative = ((fresh - old).abs() / old.abs()).where(valid)
        item.update(status='compared', n_cells_compared=n_valid,
                    n_expected_cells=int(len(common) * len(tickers)),
                    max_relative_difference=float(relative.max().max()),
                    all_compared_cells_within_1bp=bool((relative.fillna(0) <= 1e-4).all().all()),
                    adjustment_method='fresh unadjusted response Adj Close vs saved auto-adjusted Close')
        frame.to_parquet(OUT / f'source_{name}.parquet')
    except Exception as exc:
        item.update(status='unverified', error=f'{type(exc).__name__}: {exc}')
    results['yahoo_windows'].append(item)
    (OUT / 'source_spotcheck_result.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(item), flush=True)

url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3&cosd=2026-10-19&coed=2026-10-30'
try:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    table = pd.read_csv(io.StringIO(response.text))
    table.index = pd.to_datetime(table.iloc[:, 0])
    fresh = pd.to_numeric(table['DTB3'], errors='coerce')
    saved_rf = pd.read_parquet(ROOT / 'data/raw' / POINTER['dataset_id'] / 'fred_dtb3_raw.parquet')['rate_annual_pct']
    common = fresh.dropna().index.intersection(saved_rf.dropna().index)
    if not len(common):
        raise ValueError('No common finite FRED observations')
    results['fred'] = dict(status='compared', source=url, n_observations=len(common),
                           max_abs_annual_percent_difference=float(np.max(np.abs(fresh.loc[common] - saved_rf.loc[common]))))
    (OUT / 'source_fred_recent.csv').write_text(response.text)
except Exception as exc:
    results['fred'] = dict(status='unverified', source=url, error=f'{type(exc).__name__}: {exc}')
results['scope'] = 'Source consistency of samples, not independent-vendor verification or proof of every historical observation.'
(OUT / 'source_spotcheck_result.json').write_text(json.dumps(results, indent=2))
print(json.dumps({'fred': results['fred']}), flush=True)
