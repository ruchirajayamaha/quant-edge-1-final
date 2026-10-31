"""Build or verify the shared Quant Edge 1.0 market-data snapshot (SOLO STEP 2 / A1).

Usage (PowerShell, inside activated Python 3.11 .venv):
    python scripts/build_data_snapshot.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantedge.config import DEFAULT_CONFIG_PATH, load_config
from quantedge.data import derive_snapshot_from_existing, load_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or load Quant Edge 1.0 data snapshot.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml (default: repository root config.yaml).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Verify and load existing cached snapshot without network access.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force a fresh live download from Yahoo Finance and FRED.",
    )
    parser.add_argument(
        "--derive-from",
        type=str,
        default=None,
        help="Derive a hardened policy-revision snapshot offline from an existing verified dataset_id.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.derive_from:
        bundle = derive_snapshot_from_existing(cfg, source_dataset_id=args.derive_from)
    else:
        bundle = load_data(cfg, offline=args.offline, refresh=args.refresh)
    m = bundle.manifest

    summary = {
        "dataset_id": m.dataset_id,
        "policy_revision": m.policy_revision,
        "parent_dataset_id": m.parent_dataset_id,
        "schema_version": m.schema_version,
        "retrieved_at_utc": m.retrieved_at_utc,
        "requested_start": m.requested_start,
        "requested_end": m.requested_end,
        "actual_start": m.actual_start,
        "actual_end": m.actual_end,
        "tickers": list(m.tickers),
        "n_price_sessions": len(bundle.prices),
        "n_quarantined_unexpected_sessions": (
            len(bundle.quarantined_prices) if bundle.quarantined_prices is not None else 0
        ),
        "n_simple_return_sessions": len(bundle.simple_returns),
        "n_log_return_sessions": len(bundle.log_returns),
        "rf_alignment_policy": m.rf_convention.get("alignment_policy"),
        "n_rf_daily_valid": int(bundle.rf_daily.notna().sum()),
        "n_rf_daily_missing": int(bundle.rf_daily.isna().sum()),
        "n_days_forward_differs_from_ex_post": m.rf_convention.get(
            "n_days_forward_differs_from_ex_post"
        ),
        "n_quality_flags": len(bundle.quality_flags),
        "quality_flags_by_rule": (
            bundle.quality_flags["rule"].value_counts().to_dict()
            if not bundle.quality_flags.empty
            else {}
        ),
        "row_exclusions": m.row_exclusions,
        "offline_cache_used": m.offline_cache_used,
        "notes": list(m.notes),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
