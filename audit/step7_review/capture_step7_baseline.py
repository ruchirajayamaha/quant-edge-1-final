"""Capture the pre-Step-7 protected-file baseline BEFORE any Step 7 code edit or EVT fit.

Writes audit/step7_review/STEP7_BASELINE.json. Run once; refuses to overwrite.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "audit/step7_review/STEP7_BASELINE.json"

# Files Step 7 is permitted to edit (minimal var.py EVT dispatch, evt.py implementation,
# deferred-stub tests, and documentation/handoff files). Their pre-Step-7 hashes are recorded
# for transparency only; they are NOT asserted unchanged.
EXPECTED_TO_CHANGE = (
    "src/quantedge/evt.py",
    "src/quantedge/var.py",
    "tests/test_c_var_es.py",
    "tests/test_d_setup.py",
    "docs/sections/c_var_es_and_evt.md",
    "audit/decision_register/REGISTER.md",
    "handoff/SOLO.md",
    "CHANGELOG.md",
    "AI_DISCLOSURE.md",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} already exists; baseline is captured once before Step 7 edits.")
    step6 = json.loads((ROOT / "audit/step6_review/STEP6_BASELINE.json").read_text(encoding="utf-8"))
    protected = sorted(name for name in step6["sha256"] if name not in EXPECTED_TO_CHANGE)
    extra = [
        "src/quantedge/backtest.py",
        "src/quantedge/_backtest_diagnostics.py",
        "src/quantedge/config.py",
        "docs/sections/a_backtesting.md",
        "scripts/record_step5_c1_results.py",
        "scripts/export_step5_c1_preview.py",
        "scripts/record_step6_backtest_results.py",
        "scripts/export_step6_backtest_preview.py",
        "audit/step6_review/verification.json",
        "audit/step6_review/verify_step6_results.py",
        "audit/step6_review/STEP6_BASELINE.json",
        "audit/step6_review/STEP6_CLOSURE.md",
    ]
    extra += sorted(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "results/step6_backtest_preview").iterdir()
        if p.is_file()
    )
    protected = sorted(set(protected) | set(extra))
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Pre-Step-7 baseline captured before any evt.py/var.py edit and before any EVT fit",
        "protected_sha256": {name: _sha(ROOT / name) for name in protected},
        "pre_step7_sha256_of_files_expected_to_change": {
            name: _sha(ROOT / name) for name in EXPECTED_TO_CHANGE if (ROOT / name).exists()
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Protected files: {len(payload['protected_sha256'])}; expected-to-change recorded: "
          f"{len(payload['pre_step7_sha256_of_files_expected_to_change'])}")


if __name__ == "__main__":
    main()
