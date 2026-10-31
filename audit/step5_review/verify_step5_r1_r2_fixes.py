"""Post-fix verification script for SOLO STEP 5 bounded R1/R2 corrections and visible exports.

Leaves audit/step5_review/verification.json and audit/step5_review/baseline_step5_results.json
untouched and writes audit/step5_review/verification_after_fixes.json.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

import numpy as np
import pandas as pd

from quantedge.config import load_config
from quantedge.contracts import CANONICAL_TICKERS
from quantedge.data import load_data
from quantedge.es import empirical_tail_weights, empirical_var_and_es
from quantedge.var import build_development_c1_risk_bundle, estimate_risk

ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_non_json_number(token: str) -> None:
    raise ValueError(f"Non-standard JSON numeric token: {token}")


def main() -> None:
    cfg = load_config(ROOT / "config.yaml")
    out: dict[str, object] = {
        "scope": "post-fix Step 5 (C1) R1/R2 + visible export verification; development-only risk results"
    }

    # 1. 450 Fraction rational-tail oracle checks
    rng = np.random.default_rng(50113)
    cases = 0
    maximum_tail_error = 0.0
    for i in range(450):
        n = int(rng.integers(1, 151))
        raw = [int(x) for x in rng.integers(-9, 13, n)]
        c = [0.5, 0.75, 0.8, 0.85, 0.9, 0.95, 0.99][i % 7]
        fraction_c = Fraction(str(c))
        descending = sorted(raw, reverse=True)
        mass = Fraction(n) * (1 - fraction_c)
        remain = mass
        weighted = Fraction(0)
        for loss in descending:
            take = min(Fraction(1), remain)
            weighted += take * loss
            remain -= take
            if remain == 0:
                break
        exact_es = float(weighted / mass)
        exact_var = sorted(raw)[math.ceil(Fraction(n) * fraction_c) - 1]
        losses = pd.Series(raw, index=[f"row_{j}" for j in range(n)], dtype=float)
        v, e, w, _ = empirical_var_and_es(losses, c)
        assert v == exact_var, (n, c, v, exact_var)
        maximum_tail_error = max(maximum_tail_error, abs(e - exact_es))
        assert abs(e - exact_es) < 1e-12
        assert abs(float(w.sum()) - 1.0) < 1e-12 and float(w.min()) >= 0
        shuffled = losses.sample(frac=1, random_state=i)
        shuffled_w = empirical_tail_weights(shuffled, c).reindex(losses.index)
        assert np.array_equal(w.to_numpy(), shuffled_w.to_numpy())
        cases += 1

    out["fraction_rational_tail_oracle"] = {
        "cases": cases,
        "max_es_absolute_error": maximum_tail_error,
        "exact_var_and_permutation_checks": True,
    }

    # 2. R2 strict RFC 8259 JSON parse & baseline comparison against baseline_step5_results.json
    saved_path = ROOT / "results/step5_development_c1_risk_tables.json"
    baseline_copy_path = Path(__file__).parent / "baseline_step5_results.json"
    assert _sha256(baseline_copy_path) == "5a98cca6bb1342e1cf15293ac64ea83066c8873f4421ea04057c08d6600aabb4"

    saved = json.loads(saved_path.read_text(encoding="utf-8"), parse_constant=_reject_non_json_number)
    json.dumps(saved, allow_nan=False)
    baseline = json.loads(baseline_copy_path.read_text(encoding="utf-8"))

    baseline_diffs: list[float] = []
    null_metadata_rows = 0
    mc_metadata_rows = 0
    for win, portfolios in saved["comparison_tables"].items():
        for name, rows in portfolios.items():
            base_rows = baseline["comparison_tables"][win][name]
            assert len(rows) == len(base_rows) == 9
            for row, base_row in zip(rows, base_rows):
                baseline_diffs.append(abs(float(row["var_loss"]) - float(base_row["var_loss"])))
                baseline_diffs.append(abs(float(row["es_loss"]) - float(base_row["es_loss"])))
                if row["model"] == "monte_carlo_normal":
                    assert row["seed"] == 202601 and row["monte_carlo_simulations"] == 25000
                    mc_metadata_rows += 1
                else:
                    assert row["seed"] is None and row["monte_carlo_simulations"] is None
                    null_metadata_rows += 1

    assert max(baseline_diffs) == 0.0
    out["strict_json_export_probe"] = {
        "strict_parse_succeeds": True,
        "allow_nan_false_roundtrip": True,
        "null_non_mc_metadata_rows": null_metadata_rows,
        "integer_mc_metadata_rows": mc_metadata_rows,
        "max_diff_vs_preserved_baseline_json": max(baseline_diffs),
        "preserved_baseline_sha256": _sha256(baseline_copy_path),
    }

    # 3. Independent 54-row development risk oracle
    bundle = load_data(cfg, offline=True)
    dev = bundle.simple_returns.loc[: cfg.chronology.development_end].copy()
    diffs: list[float] = []
    normal_diffs: list[float] = []
    for win, portfolios in saved["comparison_tables"].items():
        sample = dev.iloc[-1260:] if win == "recent_development_1260d" else dev
        for name, rows in portfolios.items():
            weights = pd.Series(saved["exposures"][name]["weights"], index=CANONICAL_TICKERS)
            losses = [
                float(-sum(float(r) * float(weights[t]) for r, t in zip(row, CANONICAL_TICKERS)))
                for row in sample.to_numpy()
            ]
            mean_loss = statistics.mean(losses)
            sigma = statistics.stdev(losses)
            for row in rows:
                c = row["confidence"]
                actual = estimate_risk(
                    sample,
                    weights,
                    model=row["model"],
                    confidence=c,
                    seed=saved["monte_carlo_seed"],
                )
                diffs.extend(
                    [
                        abs(float(actual.var_loss) - row["var_loss"]),
                        abs(float(actual.es_loss) - row["es_loss"]),
                    ]
                )
                if row["model"] == "parametric_normal":
                    z = statistics.NormalDist().inv_cdf(c)
                    v = mean_loss + sigma * z
                    e = mean_loss + sigma * math.exp(-z * z / 2) / math.sqrt(2 * math.pi) / (1 - c)
                    normal_diffs.extend([abs(v - row["var_loss"]), abs(e - row["es_loss"])])
                elif row["model"] == "historical":
                    descending = sorted(losses, reverse=True)
                    mass = Fraction(len(losses)) * (1 - Fraction(str(c)))
                    full = int(mass)
                    partial = float(mass - full)
                    es = (math.fsum(descending[:full]) + (partial * descending[full] if partial else 0.0)) / float(mass)
                    v = sorted(losses)[math.ceil(len(losses) * Fraction(str(c))) - 1]
                    normal_diffs.extend([abs(v - row["var_loss"]), abs(es - row["es_loss"])])
                assert row["n_obs"] == len(sample)
                assert math.isclose(row["var_usd"], row["var_loss"] * saved["nav_usd"], abs_tol=1e-8)
                assert math.isclose(row["es_usd"], row["es_loss"] * saved["nav_usd"], abs_tol=1e-8)

    assert max(diffs) == 0.0
    assert max(normal_diffs) < 1e-12
    out["development_risk_oracle"] = {
        "rows": sum(len(r) for p in saved["comparison_tables"].values() for r in p.values()),
        "saved_vs_current_max_error": max(diffs),
        "scalar_normal_empirical_oracle_max_error": max(normal_diffs),
        "usd_and_sample_checks": True,
    }

    # 4. R1 custom config probe (111 draws, seed 42, 20-day est window, 40-day recent window)
    toy = pd.DataFrame(
        rng.normal(0.0002, 0.01, (80, 7)),
        index=pd.bdate_range("2015-01-02", periods=80),
        columns=CANONICAL_TICKERS,
    )
    custom = replace(
        cfg,
        portfolio=replace(cfg.portfolio, estimation_window_days=20),
        risk=replace(cfg.risk, dashboard_risk_window_days=40, monte_carlo_simulations=111),
        seeds=replace(cfg.seeds, monte_carlo=42),
    )
    custom_bundle = build_development_c1_risk_bundle(toy, custom)
    counts = set()
    seeds_seen = set()
    hashes_seen = set()
    for portfolios in custom_bundle["comparison_tables"].values():
        for table in portfolios.values():
            hashes_seen.update(str(v) for v in table["config_hash"])
            mc_sub = table.loc[table.model == "monte_carlo_normal"]
            counts.update(int(v) for v in mc_sub["monte_carlo_simulations"])
            seeds_seen.update(int(v) for v in mc_sub["seed"])

    unc_c95 = custom_bundle["mc_uncertainty"]["recent_development_1260d"]["c_95"]
    mv_c95_row = custom_bundle["comparison_tables"]["recent_development_1260d"]["min_variance"].loc[
        lambda d: (d["model"] == "monte_carlo_normal") & np.isclose(d["confidence"], 0.95)
    ].iloc[0]
    assert sorted(counts) == [111]
    assert sorted(seeds_seen) == [42]
    assert sorted(hashes_seen) == [custom.config_hash]
    assert unc_c95["monte_carlo_simulations_per_rep"] == 111
    assert unc_c95["base_seed"] == 42
    assert unc_c95["config_hash"] == custom.config_hash
    assert math.isclose(unc_c95["primary_seed_var_loss"], float(mv_c95_row["var_loss"]), rel_tol=0.0, abs_tol=1e-15)
    assert math.isclose(unc_c95["primary_seed_es_loss"], float(mv_c95_row["es_loss"]), rel_tol=0.0, abs_tol=1e-15)

    out["config_count_probe"] = {
        "rejected_incompatible_config": False,
        "bundle_claimed_simulations": custom_bundle["monte_carlo_simulations"],
        "actual_comparison_simulations": sorted(counts),
        "uncertainty_simulations": unc_c95["monte_carlo_simulations_per_rep"],
        "bundle_claimed_seed": custom_bundle["monte_carlo_seed"],
        "actual_comparison_seeds": sorted(seeds_seen),
        "uncertainty_base_seed": unc_c95["base_seed"],
        "config_hash_consistent": sorted(hashes_seen) == [custom.config_hash],
        "primary_vs_uncertainty_seed0_var_diff": abs(unc_c95["primary_seed_var_loss"] - float(mv_c95_row["var_loss"])),
        "primary_vs_uncertainty_seed0_es_diff": abs(unc_c95["primary_seed_es_loss"] - float(mv_c95_row["es_loss"])),
    }

    # 5. Step 5 visible exports & Step 4 preview non-overwrite check
    step5_preview_dir = ROOT / "results/step5_c1_preview"
    step5_manifest = json.loads(
        (step5_preview_dir / "manifest.json").read_text(encoding="utf-8"),
        parse_constant=_reject_non_json_number,
    )
    for fname, expected_sha in step5_manifest["artifacts_sha256"].items():
        assert _sha256(step5_preview_dir / fname) == expected_sha

    step4_preview_dir = ROOT / "results/development_preview"
    step4_manifest = json.loads((step4_preview_dir / "manifest.json").read_text(encoding="utf-8"))
    for fname, expected_sha in step4_manifest["artifacts_sha256"].items():
        assert _sha256(step4_preview_dir / fname) == expected_sha

    out["visible_exports"] = {
        "step5_preview_dir": "results/step5_c1_preview",
        "step5_artifact_count": len(step5_manifest["artifacts_sha256"]),
        "step5_manifest_hashes_verified": True,
        "step4_preview_untouched": True,
        "step4_artifact_count": len(step4_manifest["artifacts_sha256"]),
    }

    # 6. 53/53 market + context hashes, Step 3/4 sources, and protected files
    hash_count = 0
    for path in list((ROOT / "data/processed").glob("*/manifest.json")) + [
        ROOT / "data/reference/context/context_manifest.json"
    ]:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        for name, expected in manifest["file_sha256"].items():
            assert _sha256(ROOT / name) == expected
            hash_count += 1
    assert hash_count == 53
    out["data_hashes"] = {"matching": hash_count, "expected": 53}

    checkpoint = json.loads((ROOT / "audit/step4_review/CODEX_CLOSURE_CHECKPOINT.json").read_text(encoding="utf-8"))
    for name in ("src/quantedge/portfolio.py", "src/quantedge/kpis.py", "src/quantedge/data.py"):
        assert _sha256(ROOT / name) == checkpoint["sha256"][name]
    out["accepted_step3_4_sources"] = "unchanged"

    for name in (
        "config.yaml",
        "requirements.txt",
        "src/quantedge/contracts.py",
        "data/processed/active_snapshot.json",
    ):
        original = subprocess.run(
            ["git", "show", f"HEAD:{name}"], cwd=ROOT, capture_output=True, check=True
        ).stdout
        assert original.replace(b"\r\n", b"\n") == (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
    out["protected_files"] = "unchanged"

    out["source_sha256"] = {
        name: _sha256(ROOT / name)
        for name in (
            "src/quantedge/var.py",
            "src/quantedge/es.py",
            "tests/test_c_var_es.py",
            "scripts/record_step5_c1_results.py",
            "scripts/export_step5_c1_preview.py",
            "results/step5_development_c1_risk_tables.json",
            "results/step5_c1_preview/manifest.json",
            "docs/sections/c_var_es_and_evt.md",
        )
    }

    target_json = Path(__file__).parent / "verification_after_fixes.json"
    target_json.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
