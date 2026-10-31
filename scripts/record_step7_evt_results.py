"""Record Step 7 (C2/C3) EVT tail results and diagnostics on development data.

Numerical authority for Step 7:
- Window: recent (1,260 sessions) and full (3,020 sessions) through 2016-12-30.
- Exposure: terminal-development min_variance weights.
- Models: Historical, Parametric Normal, Monte Carlo Normal, EVT POT, EVT Body/Tail Hybrid.
- Threshold policy: provisional q=0.95, min_exceedances=50.
- Moving-block bootstrap: block length 10, 100 repetitions, seed 202602.
Output: results/step7_evt_preview/step7_recorded_results.json and CSV tables.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np
import pandas as pd

from quantedge.config import load_config
from quantedge.data import load_data
from quantedge.contracts import CANONICAL_TICKERS, MANDATORY_COMPARISON_CONFIDENCES, SUPPORTED_CONFIDENCE_LEVELS
from quantedge import evt
from quantedge.var import estimate_risk, resolve_risk_runtime_settings


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "results/step7_evt_preview"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ValueError(f"Non-finite float cannot be exported to strict JSON: {value}")
    return value


def _verify_preservation() -> dict[str, int]:
    baseline_path = ROOT / "audit/step7_review/STEP7_BASELINE.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    for name, expected in baseline["protected_sha256"].items():
        actual = _sha(ROOT / name)
        assert actual == expected, f"Protected file changed: {name} (expected {expected}, got {actual})"
    count = 0
    for path in list((ROOT / "data/processed").glob("*/manifest.json")) + [
        ROOT / "data/reference/context/context_manifest.json"
    ]:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        for name, expected in manifest["file_sha256"].items():
            actual = _sha(ROOT / name)
            assert actual == expected, f"Data hash mismatch: {name}"
            count += 1
    assert count == 53
    return {
        "protected_files_unchanged": len(baseline["protected_sha256"]),
        "source_data_hashes_matching": count,
    }


def main() -> None:
    start_time = time.perf_counter()
    integrity = _verify_preservation()

    cfg = load_config(ROOT / "config.yaml")
    data = load_data(cfg, offline=True)
    dev_returns = data.simple_returns.loc[: cfg.chronology.development_end].copy()
    assert dev_returns.index.max() <= pd.Timestamp("2016-12-30")

    step5_tables_path = ROOT / "results/step5_development_c1_risk_tables.json"
    step5_data = json.loads(step5_tables_path.read_text(encoding="utf-8"))
    mv_weights_dict = step5_data["exposures"]["min_variance"]["weights"]
    weights = pd.Series(mv_weights_dict, dtype=float)[list(CANONICAL_TICKERS)]

    recent_win_days = int(cfg.risk.dashboard_risk_window_days)  # 1260
    windows = {
        "recent_development_1260d": dev_returns.iloc[-recent_win_days:].copy(),
        "full_development_3020d": dev_returns.copy(),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tables_dir = OUT_DIR / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    c2_runs: dict[str, Any] = {}
    dense_grid = (0.80, 0.825, 0.85, 0.875, 0.90, 0.925, 0.95, 0.975)
    confidences = (0.90, 0.95, 0.99)

    for win_id, win_returns in windows.items():
        win_start = time.perf_counter()
        losses = evt.portfolio_losses(win_returns, weights)
        n_obs = len(losses)
        sample_start = str(win_returns.index[0].date())
        sample_end = str(win_returns.index[-1].date())

        # 1. Threshold diagnostics: D0 candidate grid + dense grid
        diag_d0 = evt.evt_threshold_diagnostics(losses, candidate_quantiles=(0.90, 0.925, 0.95, 0.975), min_exceedances=50)
        diag_dense = evt.evt_threshold_diagnostics(losses, candidate_quantiles=dense_grid, min_exceedances=50)

        # 2. Primary GPD fit at q=0.95, min_exceedances=50
        fit_primary = evt.fit_gpd_tail(losses, threshold_quantile=0.95, min_exceedances=50)
        qq_pp = evt.gpd_qq_pp_table(fit_primary) if fit_primary.is_usable else pd.DataFrame()

        # 3. Model comparisons across confidences (0.90, 0.95, 0.99)
        model_rows: list[dict[str, Any]] = []
        for c in confidences:
            # Step 5 C1 models
            est_hist = estimate_risk(win_returns, weights, model="historical", confidence=c)
            est_norm = estimate_risk(win_returns, weights, model="parametric_normal", confidence=c)
            est_mc = estimate_risk(win_returns, weights, model="monte_carlo_normal", confidence=c, seed=cfg.seeds.monte_carlo)

            # Step 7 C2 models
            est_pot = evt.estimate_evt_pot(win_returns, weights, confidence=c, threshold_quantile=0.95, min_exceedances=50)
            est_hyb = evt.estimate_evt_body_tail(win_returns, weights, confidence=c, threshold_quantile=0.95, min_exceedances=50)

            for est, is_hyb in ((est_hist, False), (est_norm, False), (est_mc, False), (est_pot, False), (est_hyb, True)):
                v = est.var_loss
                e = est.es_loss
                model_rows.append({
                    "window_id": win_id,
                    "portfolio_id": "min_variance",
                    "model": est.model,
                    "confidence": est.confidence,
                    "alpha": float(1.0 - est.confidence),
                    "is_mandatory": bool(est.confidence in (0.95, 0.99)),
                    "var_loss": v,
                    "es_loss": e,
                    "var_pct": float(v * 100.0) if v is not None else None,
                    "es_pct": float(e * 100.0) if e is not None else None,
                    "var_usd": float(v * cfg.mandate.nav_usd) if v is not None else None,
                    "es_usd": float(e * cfg.mandate.nav_usd) if e is not None else None,
                    "es_minus_var": float(e - v) if (v is not None and e is not None) else None,
                    "diff_vs_normal_var_bps": float((v - est_norm.var_loss) * 10000.0) if (v is not None and est_norm.var_loss is not None) else None,
                    "diff_vs_normal_es_bps": float((e - est_norm.es_loss) * 10000.0) if (e is not None and est_norm.es_loss is not None) else None,
                    "status": est.status,
                    "region": est.diagnostics.get("region"),
                    "var_label": est.diagnostics.get("var_label", est.model.upper()),
                    "reason": est.reason,
                })

        # 4. Moving-block bootstrap uncertainty
        boot_res = evt.bootstrap_evt_tail_uncertainty(
            losses,
            confidences=confidences,
            threshold_quantile=0.95,
            min_exceedances=50,
            block_length=10,
            n_replications=100,
            seed=cfg.seeds.evt_bootstrap,
            dataset_id=data.manifest.dataset_id,
            exposure_id="min_variance_terminal_dev",
            config_hash=cfg.config_hash,
            policy_id="provisional_q95_min50_block10_rep100",
        )

        win_elapsed = time.perf_counter() - win_start
        c2_runs[win_id] = {
            "window_id": win_id,
            "n_obs": n_obs,
            "sample_start": sample_start,
            "sample_end": sample_end,
            "runtime_seconds": win_elapsed,
            "threshold_diagnostics_d0": _jsonable(diag_d0.to_dict(orient="records")),
            "threshold_diagnostics_dense": _jsonable(diag_dense.to_dict(orient="records")),
            "primary_fit": fit_primary.to_record(),
            "qq_pp_data": _jsonable(qq_pp.to_dict(orient="records")),
            "model_comparison": _jsonable(model_rows),
            "bootstrap": _jsonable(boot_res),
        }

    # Build CSV tables
    # Table 1: Model Risk Comparison
    comp_records = []
    for win_id, r in c2_runs.items():
        comp_records.extend(r["model_comparison"])
    comp_df = pd.DataFrame(comp_records)
    comp_df.to_csv(tables_dir / "table_01_risk_model_comparison.csv", index=False, float_format="%.17g")

    # Table 2: Primary GPD Threshold Diagnostics
    diag_records = []
    for win_id, r in c2_runs.items():
        for d in r["threshold_diagnostics_dense"]:
            diag_records.append({"window_id": win_id, **d})
    diag_df = pd.DataFrame(diag_records)
    diag_df.to_csv(tables_dir / "table_02_threshold_diagnostics.csv", index=False, float_format="%.17g")

    # Table 3: Moving-block Bootstrap Tail Risk Uncertainty Summary
    boot_records = []
    for win_id, r in c2_runs.items():
        b_sum = r["bootstrap"]["summary"]
        for c_str, c_data in b_sum["by_confidence"].items():
            boot_records.append({
                "window_id": win_id,
                "confidence": c_data["confidence"],
                "method": c_data["method"],
                "n_var_available": c_data["n_var_available"],
                "n_es_finite": c_data["n_es_finite"],
                "n_es_unavailable_xi_ge_1": c_data["n_es_unavailable_infinite_xi_ge_1"],
                "var_p025": c_data["var"]["p025"],
                "var_median": c_data["var"]["median"],
                "var_p975": c_data["var"]["p975"],
                "var_interval_status": c_data["var"]["interval_status"],
                "es_p025": c_data["es"]["p025"],
                "es_median": c_data["es"]["median"],
                "es_p975": c_data["es"]["p975"],
                "es_interval_status": c_data["es"]["interval_status"],
                "hybrid_var_p025": c_data["body_tail_hybrid"]["var"]["p025"],
                "hybrid_var_median": c_data["body_tail_hybrid"]["var"]["median"],
                "hybrid_var_p975": c_data["body_tail_hybrid"]["var"]["p975"],
                "hybrid_es_p025": c_data["body_tail_hybrid"]["es"]["p025"],
                "hybrid_es_median": c_data["body_tail_hybrid"]["es"]["median"],
                "hybrid_es_p975": c_data["body_tail_hybrid"]["es"]["p975"],
            })
    boot_df = pd.DataFrame(boot_records)
    boot_df.to_csv(tables_dir / "table_03_bootstrap_uncertainty.csv", index=False, float_format="%.17g")

    # Table 4: QQ/PP data
    for win_id, r in c2_runs.items():
        qq_df = pd.DataFrame(r["qq_pp_data"])
        qq_df.to_csv(tables_dir / f"table_04_qq_pp_{win_id}.csv", index=False, float_format="%.17g")

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    sources = [
        "src/quantedge/evt.py",
        "src/quantedge/var.py",
        "src/quantedge/es.py",
        "scripts/record_step7_evt_results.py",
    ]

    total_elapsed = time.perf_counter() - start_time
    payload = {
        "metadata": {
            "scope": "DEVELOPMENT ONLY; UNCONDITIONAL EVT POT-GPD RESEARCH; NOT FINAL HOLDOUT VALIDATION",
            "computed_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_id": data.manifest.dataset_id,
            "config_hash": cfg.config_hash,
            "code_version": f"{head}-working-tree",
            "source_sha256": {n: _sha(ROOT / n) for n in sources},
            "development_end": cfg.chronology.development_end,
            "portfolio_id": "min_variance",
            "weights": {t: float(weights.loc[t]) for t in CANONICAL_TICKERS},
            "threshold_policy": {
                "threshold_quantile": float(cfg.risk.evt_threshold_quantile),
                "min_exceedances": int(cfg.risk.evt_min_exceedances),
                "threshold_convention": "u = L_(ceil(n q)) step-CDF order statistic; strict exceedances L > u",
                "status": "PROVISIONAL_INHERITED; human committee approval PENDING",
            },
            "bootstrap_policy": {
                "block_length": 10,
                "n_replications": 100,
                "seed": int(cfg.seeds.evt_bootstrap),
                "min_successful_replications": 80,
            },
            "nav_usd": float(cfg.mandate.nav_usd),
            "runtime_seconds": total_elapsed,
            "integrity": integrity,
        },
        "runs": c2_runs,
    }

    text = json.dumps(_jsonable(payload), indent=2, allow_nan=False) + "\n"
    # Strict JSON validation
    json.loads(text, parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))
    (OUT_DIR / "step7_recorded_results.json").write_text(text, encoding="utf-8")
    _verify_preservation()
    print(f"Step 7 EVT results recorded successfully in {total_elapsed:.3f}s.", flush=True)


if __name__ == "__main__":
    main()
