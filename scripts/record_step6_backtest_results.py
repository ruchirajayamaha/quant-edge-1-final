"""Persist bounded Step 6 development rolling results; no holdout outcomes or tuning."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

import numpy as np
import pandas as pd

from quantedge.backtest import basel_traffic_light, coverage_tests, rolling_backtest
from quantedge.config import load_config
from quantedge.data import load_data
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs
from quantedge.var import get_risk_forecaster


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/step6_backtest_preview"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value):
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
            return None  # Only legitimate missing cells; finite core metrics checked below.
        if not math.isfinite(value):
            raise ValueError("Infinite result cannot be exported")
    return value


def _verify_preservation() -> dict:
    baseline = json.loads((ROOT / "audit/step6_review/STEP6_BASELINE.json").read_text(encoding="utf-8"))
    for name, expected in baseline["sha256"].items():
        assert _sha(ROOT / name) == expected, f"Protected file changed: {name}"
    count = 0
    for path in list((ROOT / "data/processed").glob("*/manifest.json")) + [
        ROOT / "data/reference/context/context_manifest.json"
    ]:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        for name, expected in manifest["file_sha256"].items():
            assert _sha(ROOT / name) == expected, name
            count += 1
    assert count == 53
    return {"protected_files_unchanged": len(baseline["sha256"]), "source_data_hashes_matching": count}


def main() -> None:
    start = time.perf_counter()
    integrity = _verify_preservation()
    cfg = load_config(ROOT / "config.yaml")
    assert cfg.risk.primary_backtest_model == "historical"
    assert cfg.risk.backtest_window_days == 500
    register = (ROOT / "audit/decision_register/REGISTER.md").read_text(encoding="utf-8")
    assert "Step 6 development engineering protocol" in register
    data = load_data(cfg, offline=True)
    dev = data.simple_returns.loc[: cfg.chronology.development_end].copy()
    assert dev.index.max() <= pd.Timestamp("2016-12-30")
    spec = make_core_strategy_specs(cfg)["min_variance"]
    path = build_portfolio_path(dev, spec, cfg)
    np.testing.assert_allclose(
        (dev.loc[path.weights_before.index].to_numpy() * path.weights_before.to_numpy()).sum(axis=1),
        path.gross_returns.to_numpy(), rtol=0, atol=1e-15,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    path.weights_before.to_csv(OUT / "04_pre_return_weights.csv", index_label="date", float_format="%.17g")
    runs = []
    csv_frames = []
    coverage_frames = []
    for model in ("historical", "parametric_normal"):
        for conf in (0.95, 0.99):
            run_start = time.perf_counter()
            rows = rolling_backtest(
                dev, path.weights_before, get_risk_forecaster(model),
                confidence=conf, window=cfg.risk.backtest_window_days, seed=cfg.seeds.backtest,
            )
            eligible = rows.status.isin(["ok", "warning"]) & rows.exceedance.notna()
            assert np.isfinite(rows.loc[eligible, ["forecast_var", "realized_loss"]].to_numpy(dtype=float)).all()
            assert (rows.loc[eligible, "train_end"] < rows.loc[eligible, "date"]).all()
            assert rows.date.max() <= pd.Timestamp(cfg.chronology.development_end)
            summary = coverage_tests(rows)
            assert len(summary) == 1
            basel = basel_traffic_light(rows) if conf == 0.99 else None
            elapsed = time.perf_counter() - run_start
            records = _jsonable(rows.to_dict(orient="records"))
            coverage_record = _jsonable(summary.iloc[0].to_dict())
            diagnostics = _jsonable(summary.attrs)
            runs.append({
                "model": model, "confidence": conf, "rows": records,
                "coverage": coverage_record, "diagnostics": diagnostics, "basel": _jsonable(basel),
                "runtime_seconds": elapsed, "backtest_metadata": _jsonable(rows.attrs),
            })
            csv_frames.append(rows.assign(portfolio_id="min_variance"))
            coverage_frames.append(summary.assign(portfolio_id="min_variance", runtime_seconds=elapsed))
            print(f"{model} c={conf}: {int(eligible.sum())}/{len(rows)} eligible; {coverage_record['n_exceedances']} exceptions; {elapsed:.3f}s", flush=True)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    sources = ["src/quantedge/backtest.py", "src/quantedge/_backtest_diagnostics.py",
               "src/quantedge/var.py", "src/quantedge/es.py", "src/quantedge/portfolio.py",
               "scripts/record_step6_backtest_results.py"]
    metadata = {
        "scope": "DEVELOPMENT OOS RESEARCH; NOT FINAL HOLDOUT VALIDATION",
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": data.manifest.dataset_id, "config_hash": cfg.config_hash,
        "code_version": f"{head}-working-tree", "source_sha256": {n: _sha(ROOT / n) for n in sources},
        "development_end": cfg.chronology.development_end, "portfolio_id": "min_variance",
        "window": cfg.risk.backtest_window_days, "nav_usd": cfg.mandate.nav_usd,
        "seed": cfg.seeds.backtest, "sample_start": path.weights_before.index.min().strftime("%Y-%m-%d"),
        "sample_end": path.weights_before.index.max().strftime("%Y-%m-%d"),
        "n_target_sessions": len(path.weights_before), "primary_model": "historical",
        "comparison_model": "parametric_normal", "confidences": [0.95, 0.99],
        "runtime_seconds": time.perf_counter() - start,
        "loss_convention": "1-day gross market loss = -(weights_before[t] @ asset_returns[t]); before costs",
        "exposure_convention": "known pre-return weights; natural drift and accepted monthly rebalance targets",
        "approval": "PROVISIONAL; independent human validation and committee decision PENDING",
        "holdout_outcomes_inspected": False, "integrity": integrity,
    }
    payload = _jsonable({"metadata": metadata, "runs": runs})
    text = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    json.loads(text, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    (OUT / "backtest_results.json").write_text(text, encoding="utf-8")
    pd.concat(csv_frames, ignore_index=True).to_csv(OUT / "01_daily_backtest_rows.csv", index=False, float_format="%.17g")
    pd.concat(coverage_frames, ignore_index=True).to_csv(OUT / "02_coverage_summary.csv", index=False, float_format="%.17g")
    diagnostic_payload = [{k: r[k] for k in ("model", "confidence", "diagnostics", "basel")} for r in runs]
    (OUT / "03_transition_and_basel_diagnostics.json").write_text(json.dumps(diagnostic_payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    _verify_preservation()
    print(f"Saved {len(runs)} runs / {sum(len(r['rows']) for r in runs)} rows; total {metadata['runtime_seconds']:.3f}s", flush=True)


if __name__ == "__main__":
    main()
