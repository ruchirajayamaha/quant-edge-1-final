"""Verified, non-executable persisted interface produced by the common pipeline."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from quantedge.config import load_config

ROOT=Path(__file__).resolve().parents[2]

def load_reference(root=None):
    root=Path(root) if root else ROOT
    folder=root/'results/final'
    manifest=json.loads((folder/'manifest.json').read_text())
    for name,digest in manifest['file_sha256'].items():
        path=(folder/name).resolve()
        if path.parent!=folder.resolve():raise ValueError('Invalid reference path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError(f'Reference hash mismatch: {name}')
    result=json.loads((folder/'reference.json').read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
    if result['metadata']['config_hash']!=load_config(root/'config.yaml').config_hash:raise ValueError('Reference configuration is stale; rebuild final results')
    source=root/'src/quantedge'
    if source.exists():
        digest=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(source.glob('*.py')))).hexdigest()
        if result['diagnostics']['source_sha256']!=digest:raise ValueError('Reference analytical source is stale; rebuild final results')
    proposal=root/'submission/mandate_proposal.json'
    if proposal.exists() and hashlib.sha256(proposal.read_bytes()).hexdigest()!=result['diagnostics']['mandate_proposal_sha256']:
        raise ValueError('Reference mandate proposal is stale; rebuild final results')
    return result

def load_backtest(model,confidence,root=None):
    folder=(Path(root) if root else ROOT)/'results/final'
    if model not in ('historical','parametric_normal') or confidence not in (.90,.95,.99):raise ValueError('Unsupported rolling specification')
    return pd.read_csv(folder/f'backtest_{model}_{confidence:.2f}.csv',parse_dates=['date','train_start','train_end'])
