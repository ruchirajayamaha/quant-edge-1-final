"""Record or verify SHA-256 baselines for everything the presentation upgrade must not change.

Usage:
    python scripts/freeze_presentation_baseline.py record
    python scripts/freeze_presentation_baseline.py verify
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "audit" / "presentation_review" / "PRESENTATION_BASELINE.json"
SCOPES = {
    "analytical_source": ["src/quantedge/*.py"],
    "configuration": ["config.yaml", "requirements.txt", "pyproject.toml"],
    "data_snapshots": ["data/**/*"],
    "final_results": ["results/final/*.json", "results/final/*.csv"],
    "proposal": ["submission/mandate_proposal.json"],
    "prior_audit_evidence": [
        "audit/step2_review/**/*",
        "audit/step3_review/**/*",
        "audit/step4_review/**/*",
        "audit/step5_review/**/*",
        "audit/step6_review/**/*",
        "audit/step7_review/**/*",
        "audit/step8_review/**/*",
        "audit/step9_review/**/*",
        "audit/rf_research/**/*",
        "audit/decision_register/**/*",
        "audit/final_strategy_review/**/*",
    ],
}


def snapshot() -> dict[str, dict[str, str]]:
    """Hash every in-scope file, excluding bytecode and local caches."""
    result: dict[str, dict[str, str]] = {}
    for scope, patterns in SCOPES.items():
        files: dict[str, str] = {}
        for pattern in patterns:
            for path in sorted(ROOT.glob(pattern)):
                if not path.is_file() or "__pycache__" in path.parts or "yfinance_cache" in path.parts:
                    continue
                if any(part.startswith("pytest_") for part in path.parts):
                    continue
                rel = path.relative_to(ROOT).as_posix()
                files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        result[scope] = files
    return result


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "verify"
    current = snapshot()
    if action == "record":
        if BASELINE.exists():
            raise SystemExit(f"Refusing to overwrite existing baseline {BASELINE}.")
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print({scope: len(files) for scope, files in current.items()})
        return
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    problems = 0
    for scope, files in baseline.items():
        changed = [name for name, digest in files.items() if current[scope].get(name) != digest]
        added = sorted(set(current[scope]) - set(files))
        problems += len(changed) + len(added)
        print(f"{scope}: {len(files)} baselined, {len(changed)} changed, {len(added)} added")
        for name in [*changed, *added][:20]:
            print(f"  {name}")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
