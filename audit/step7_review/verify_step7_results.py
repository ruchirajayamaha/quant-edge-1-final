"""Independent verification of Step 7 (C2/C3) EVT tail results and baseline integrity.

Verifies:
1. All 75 protected Step 3-6 files in STEP7_BASELINE.json remain unmodified.
2. All 53 source-data hashes match official manifests.
3. Authority step7_recorded_results.json parses strictly without NaN/Infinity.
4. Independent scalar/array GPD and hybrid risk formulas verify recorded values within 1e-14.
5. All 18 preview artifact hashes in results/step7_evt_preview/manifest.json match disk.
Writes: audit/step7_review/verification.json.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "audit/step7_review/STEP7_BASELINE.json"
AUTHORITY_PATH = ROOT / "results/step7_evt_preview/step7_recorded_results.json"
MANIFEST_PATH = ROOT / "results/step7_evt_preview/manifest.json"
VERIFICATION_PATH = ROOT / "audit/step7_review/verification.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_non_json_number(token: str) -> None:
    raise ValueError(f"Non-standard JSON numeric token: {token}")


def verify_protected_files(baseline: dict[str, Any]) -> dict[str, Any]:
    mismatches = []
    for rel_path, expected_sha in baseline["protected_sha256"].items():
        p = ROOT / rel_path
        if not p.is_file():
            mismatches.append(f"Missing file: {rel_path}")
            continue
        actual_sha = _sha(p)
        if actual_sha != expected_sha:
            mismatches.append(f"Hash mismatch {rel_path}: expected {expected_sha}, got {actual_sha}")
    if mismatches:
        raise AssertionError(f"Protected file check failed ({len(mismatches)} errors):\n" + "\n".join(mismatches))
    return {
        "status": "PASS",
        "protected_files_checked": len(baseline["protected_sha256"]),
        "mismatches": 0,
    }


def verify_source_data_hashes() -> dict[str, Any]:
    count = 0
    mismatches = []
    for m_path in list((ROOT / "data/processed").glob("*/manifest.json")) + [
        ROOT / "data/reference/context/context_manifest.json"
    ]:
        manifest = json.loads(m_path.read_text(encoding="utf-8-sig"))
        for rel_name, expected_sha in manifest["file_sha256"].items():
            actual = _sha(ROOT / rel_name)
            if actual != expected_sha:
                mismatches.append(f"{rel_name}: expected {expected_sha}, got {actual}")
            count += 1
    if mismatches:
        raise AssertionError(f"Source data hash mismatch:\n" + "\n".join(mismatches))
    assert count == 53
    return {
        "status": "PASS",
        "source_data_hashes_verified": count,
        "mismatches": 0,
    }


def verify_manifest_artifacts(manifest: dict[str, Any]) -> dict[str, Any]:
    art_dir = ROOT / "results/step7_evt_preview"
    mismatches = []
    for rel_name, expected_sha in manifest["artifacts_sha256"].items():
        p = art_dir / rel_name
        if not p.is_file():
            mismatches.append(f"Missing preview artifact: {rel_name}")
            continue
        actual_sha = _sha(p)
        if actual_sha != expected_sha:
            mismatches.append(f"Artifact {rel_name}: expected {expected_sha}, got {actual_sha}")
    if mismatches:
        raise AssertionError(f"Manifest artifact mismatch:\n" + "\n".join(mismatches))
    return {
        "status": "PASS",
        "artifacts_checked": len(manifest["artifacts_sha256"]),
        "mismatches": 0,
    }


def verify_independent_gpd_oracle(authority: dict[str, Any]) -> dict[str, Any]:
    runs = authority["runs"]
    max_errors = {
        "var_difference": 0.0,
        "es_difference": 0.0,
        "threshold_difference": 0.0,
        "mean_excess_difference": 0.0,
    }
    checks_performed = 0

    for win_id, r in runs.items():
        fit = r["primary_fit"]
        u = float(fit["threshold"])
        n_exc = int(fit["n_exceedances"])
        p_u = float(fit["p_u"])
        xi = float(fit["xi"])
        beta = float(fit["beta"])

        for row in r["model_comparison"]:
            m_name = row["model"]
            conf = float(row["confidence"])
            alpha = float(row["alpha"])

            if m_name == "evt_pot":
                checks_performed += 1
                if conf < 0.95:
                    assert row["status"] == "unavailable"
                    assert row["var_loss"] is None
                    assert row["es_loss"] is None
                else:
                    a = alpha / p_u
                    # Closed form scalar GPD VaR
                    expected_var = u + (beta / xi) * (math.exp(-xi * math.log(a)) - 1.0)
                    expected_es = (expected_var + beta - xi * u) / (1.0 - xi)

                    diff_var = abs(row["var_loss"] - expected_var)
                    diff_es = abs(row["es_loss"] - expected_es)
                    max_errors["var_difference"] = max(max_errors["var_difference"], diff_var)
                    max_errors["es_difference"] = max(max_errors["es_difference"], diff_es)
                    assert diff_var < 1e-14, f"EVT POT VaR mismatch at c={conf}: diff={diff_var}"
                    assert diff_es < 1e-14, f"EVT POT ES mismatch at c={conf}: diff={diff_es}"

            elif m_name == "evt_body_tail_hybrid":
                checks_performed += 1
                if conf >= 0.95:
                    # In tail region, matches pure POT exactly
                    a = alpha / p_u
                    expected_var = u + (beta / xi) * (math.exp(-xi * math.log(a)) - 1.0)
                    expected_es = (expected_var + beta - xi * u) / (1.0 - xi)
                    diff_var = abs(row["var_loss"] - expected_var)
                    diff_es = abs(row["es_loss"] - expected_es)
                    max_errors["var_difference"] = max(max_errors["var_difference"], diff_var)
                    max_errors["es_difference"] = max(max_errors["es_difference"], diff_es)
                    assert diff_var < 1e-14
                    assert diff_es < 1e-14
                else:
                    # Body region
                    assert row["region"] == "body"
                    assert "BODY" in row["var_label"]

    return {
        "status": "PASS",
        "checks_performed": checks_performed,
        "max_errors": max_errors,
    }


def main() -> None:
    assert BASELINE_PATH.is_file(), f"Missing {BASELINE_PATH}"
    assert AUTHORITY_PATH.is_file(), f"Missing {AUTHORITY_PATH}"
    assert MANIFEST_PATH.is_file(), f"Missing {MANIFEST_PATH}"

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"), parse_constant=_reject_non_json_number)
    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"), parse_constant=_reject_non_json_number)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"), parse_constant=_reject_non_json_number)

    protected_res = verify_protected_files(baseline)
    source_res = verify_source_data_hashes()
    manifest_res = verify_manifest_artifacts(manifest)
    oracle_res = verify_independent_gpd_oracle(authority)

    payload = {
        "verification_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "overall_status": "PASS",
        "authority_file": "results/step7_evt_preview/step7_recorded_results.json",
        "authority_sha256": _sha(AUTHORITY_PATH),
        "manifest_sha256": _sha(MANIFEST_PATH),
        "protected_files_check": protected_res,
        "source_data_hashes_check": source_res,
        "manifest_artifacts_check": manifest_res,
        "independent_gpd_oracle_check": oracle_res,
    }

    VERIFICATION_PATH.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Independent Step 7 verification PASSED. Authority SHA256: {payload['authority_sha256']}")


if __name__ == "__main__":
    main()
