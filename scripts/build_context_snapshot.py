"""Build and verify the bounded A1b income/inflation context snapshot in data/reference/context/.

Usage (from repository root):
    .\\.venv\\Scripts\\python.exe scripts/build_context_snapshot.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantedge.config import DEFAULT_CONFIG_PATH, load_config
from quantedge.data import build_context_snapshot, load_context_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build bounded A1b income/inflation context snapshot.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--refresh", action="store_true", help="Re-download context inputs even if cached.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    bundle = build_context_snapshot(cfg, repo_root=ROOT, refresh=args.refresh)
    reloaded = load_context_data(cfg, offline=True, repo_root=ROOT)
    assert reloaded.context_id == bundle.context_id
    print(
        json.dumps(
            {
                "context_id": reloaded.context_id,
                "coverage": reloaded.manifest["coverage"],
                "positive_distribution_event_counts": reloaded.manifest["share_basis_verification"][
                    "positive_distribution_event_counts"
                ],
                "max_ex_div_factor_abs_diff_by_ticker": reloaded.manifest["share_basis_verification"][
                    "max_ex_div_factor_abs_diff_by_ticker"
                ],
                "file_sha256": reloaded.manifest["file_sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
