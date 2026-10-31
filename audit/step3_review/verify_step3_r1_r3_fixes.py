"""Post-fix verification for SOLO STEP 3 bounded review corrections (R1-R3).

Preserves the original `verify_step3.py` and `verification.json` untouched as
historical audit evidence while verifying:
- R1: rejection of conflicting `objective` / `fixed_weights` combinations (both
  feasible and cap-violating overrides) and non-bypassable `covariance_estimator`
  validation.
- R2: explicit `rebalance_targets_only` constraint enforcement scope separated
  from daily pre-return drifted holdings compliance diagnostics (`120/120`
  feasible rebalance targets vs. `1,439/2,516` drifted pre-return sessions on
  the development-only `min_variance` path), with synthetic breach and no-breach
  controls.
- R3: corrected `0 <= f(w*) - f_opt <= FW_gap(w*)` Frank-Wolfe convex duality-gap
  certificate in `docs/sections/b_portfolio_construction.md`.
- Bit-for-bit (`0`-ULP SHA-256) invariance of all 21 core development-period
  (`2005-01-04..2016-12-30`) portfolio path arrays before vs. after R1-R3 fixes.
- Unchanged protected files (`config.yaml`, `requirements.txt`,
  `src/quantedge/contracts.py`, `data/processed/active_snapshot.json`) and
  `46/46` snapshot SHA-256 hashes across `v1`, `r2`, and `r3`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quantedge.config import load_config
from quantedge.contracts import CANONICAL_TICKERS, StrategySpec
from quantedge.data import load_data
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs


PRE_FIX_DEV_ARRAY_SHA256: dict[str, dict[str, str]] = {
    "min_variance": {
        "weights_before": "1362e3ce3cb636bb50149a03c8bdafc8d249df3f56f8a37497a989a8e348cdbb",
        "gross_returns": "284ab78bccf6a1ad5b111157056aee9a2613c33370824013e8cc243b48da30e9",
        "net_returns": "1fb28442c39d073a78ab101db35f63f61a7054ce07ee5de4a60a3ad18d727987",
        "turnover": "6164bd1c53bb72b4899de0d58c17e163a002de89f4fb2248876c83718727811e",
        "costs": "3dddc50f7ba58b9afba154b320af43a9b5c1415000e1927fb8c86a583eb1a192",
        "wealth": "a210f36945a935c53eb1572e0bbc28dc25268dc2501e47dba707c37a7b009870",
        "drawdown": "4bc4e8f183f55cb215288da8763b1076edd868d28ef89436509a36d143647f43",
    },
    "equal_weight": {
        "weights_before": "6543ba09d9b30e3a613bb99bc3ca764385f91d56c754ff02f06bd4ff361b6d73",
        "gross_returns": "f4aa591b4ecc2ea3179a08abf41b3902dd53f10e8d3ca7ad254418fafa161878",
        "net_returns": "b0f10c75a22d49c816cf57ee2a746262c676955ec47f2f5bcfa43e00668c997d",
        "turnover": "d68ffc964725f159dca92f71797cd0581671d10c0532e0b774bae4af72736a87",
        "costs": "ba3d6455befd13b159b93ff474f8adc2588c99c4ca5fe393379828768c190e77",
        "wealth": "325e5340a77cf765151a02edcfd9039670f0df74e94d6713605ec9f00bb177a6",
        "drawdown": "a4aa0845f8cad6768400d9cb0ed61c2856fa70501a77ce4828d15bccaaca988b",
    },
    "benchmark_60_40": {
        "weights_before": "d7155044641abe588cffb871c91edf46121ef96efb0d28e9ad1733362289fa41",
        "gross_returns": "82f7b7cdacf5a0d14049e09078c7402429f4d21c2a61f50cdec70d717bcd5ce7",
        "net_returns": "610cc5efcfc52ee248709fa7d38f38b71553ab29fb82c02557f171820d976c2c",
        "turnover": "1acc3bf663f5e8f89c505d39d77574b0ce3345c7ecfa6676a30bd034a2be9c03",
        "costs": "01b41bb1aed1bd139e5bfd2ec77a29b43be4edea8bf0048352e169b9121f569d",
        "wealth": "c5c05200de2c8c898c9a0cd2dafb9c85d84e7f020f2a1d47349228e7fe3af2d3",
        "drawdown": "a17396712c42c2460514ba6baf52eb8485dce643fba95cb32187b4518ece8c32",
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expect_value_error(fn) -> str:
    try:
        fn()
    except ValueError as exc:
        return str(exc)
    raise AssertionError("Expected ValueError was not raised.")


def main() -> None:
    cfg = load_config(ROOT / "config.yaml")
    out: dict[str, Any] = {
        "scope": "post-fix Step 3 verification (R1-R3); synthetic probes and development-only (<= 2016-12-30) path checks",
    }

    # 1. R1: Conflicting objective / fixed_weights combinations must be rejected upfront.
    toy = pd.DataFrame(0.0, index=pd.bdate_range("2010-01-04", periods=4), columns=CANONICAL_TICKERS)
    all_spy = dict.fromkeys(CANONICAL_TICKERS, 0.0)
    all_spy["SPY"] = 1.0
    feasible_override = dict(cfg.portfolio.illustrative_weights)

    r1_cases = {
        "audit_probe_minvar_unsupported_cov_cap_violating": StrategySpec(
            strategy_id="conflicting_minvar_probe",
            objective="min_variance",
            estimation_window_days=2,
            covariance_estimator="unsupported_probe",
            fixed_weights=all_spy,
        ),
        "minvar_with_feasible_override": StrategySpec(
            strategy_id="minvar_feasible_override",
            objective="min_variance",
            estimation_window_days=2,
            covariance_estimator="sample_ddof1",
            fixed_weights=feasible_override,
        ),
        "minvar_with_cap_violating_override": StrategySpec(
            strategy_id="minvar_cap_violating_override",
            objective="min_variance",
            estimation_window_days=2,
            covariance_estimator="sample_ddof1",
            fixed_weights=all_spy,
        ),
        "minvar_unsupported_covariance_without_override": StrategySpec(
            strategy_id="minvar_bad_cov",
            objective="min_variance",
            estimation_window_days=2,
            covariance_estimator="unsupported_probe",
            fixed_weights=None,
        ),
        "equal_weight_with_feasible_override": StrategySpec(
            strategy_id="ew_feasible_override",
            objective="equal_weight",
            estimation_window_days=None,
            fixed_weights=feasible_override,
        ),
        "equal_weight_with_cap_violating_override": StrategySpec(
            strategy_id="ew_cap_violating_override",
            objective="equal_weight",
            estimation_window_days=None,
            fixed_weights=all_spy,
        ),
        "benchmark_60_40_with_non_60_40_override": StrategySpec(
            strategy_id="b6040_mismatch_override",
            objective="benchmark_60_40",
            estimation_window_days=None,
            fixed_weights=feasible_override,
        ),
        "fixed_weights_missing_dictionary": StrategySpec(
            strategy_id="fixed_missing_dict",
            objective="fixed_weights",
            estimation_window_days=None,
            fixed_weights=None,
        ),
    }
    r1_results: dict[str, dict[str, Any]] = {}
    for case_name, bad_spec in r1_cases.items():
        msg = expect_value_error(lambda spec=bad_spec: build_portfolio_path(toy, spec, cfg))
        r1_results[case_name] = {"rejected": True, "error": msg}

    # Explicit fixed_weights and matching 60/40 remain supported
    valid_fixed = build_portfolio_path(
        toy,
        StrategySpec(
            strategy_id="valid_fixed",
            objective="fixed_weights",
            estimation_window_days=None,
            fixed_weights=feasible_override,
        ),
        cfg,
    )
    valid_6040 = build_portfolio_path(
        toy,
        StrategySpec(
            strategy_id="valid_6040_explicit",
            objective="benchmark_60_40",
            estimation_window_days=None,
            fixed_weights=dict(cfg.mandate.benchmark_60_40_weights),
        ),
        cfg,
    )
    assert np.isclose(
        float(valid_fixed.weights_before.iloc[0]["AGG"]),
        float(feasible_override["AGG"]),
        atol=1e-14,
    )
    assert np.isclose(float(valid_6040.weights_before.iloc[0]["SPY"]), 0.60, atol=1e-14)
    out["r1_conflicting_specification_checks"] = {
        "all_conflicting_cases_rejected": True,
        "cases": r1_results,
        "explicit_fixed_weights_supported": True,
        "matching_benchmark_60_40_supported": True,
    }

    # 2. R2: Rebalance-target compliance vs. drifted pre-return holdings compliance (synthetic + control).
    drift = toy.iloc[:3].copy()
    drift.iloc[0, drift.columns.get_loc("SPY")] = 0.20
    fixed = StrategySpec(
        strategy_id="drift_scope_probe",
        objective="fixed_weights",
        estimation_window_days=None,
        fixed_weights=cfg.portfolio.illustrative_weights,
    )
    drift_path = build_portfolio_path(drift, fixed, cfg)
    equities = ["SPY", "EFA", "EEM", "XLE", "XLK"]
    assert drift_path.metadata["constraint_enforcement_scope"] == "rebalance_targets_only"
    assert drift_path.metadata["mandate_feasible_all_rebalances"] is True
    assert drift_path.metadata["mandate_feasible_all_pre_return_sessions"] is False
    assert (
        drift_path.metadata["mandate_compliance_status"]
        == "rebalance_targets_feasible_with_post_trade_drift_cap_breaches_provisional"
    )
    assert float(drift_path.weights_before.iloc[1][equities].sum()) > cfg.portfolio.constraints.max_equity_weight
    assert float(drift_path.turnover.iloc[1]) == 0.0

    interior_weights = {
        "SPY": 0.10,
        "EFA": 0.05,
        "EEM": 0.05,
        "AGG": 0.35,
        "GLD": 0.35,
        "XLE": 0.05,
        "XLK": 0.05,
    }
    calm = pd.DataFrame(0.001, index=drift.index, columns=CANONICAL_TICKERS)
    calm["AGG"] = -0.001
    ctrl_path = build_portfolio_path(
        calm,
        StrategySpec(
            strategy_id="no_breach_control",
            objective="fixed_weights",
            estimation_window_days=None,
            fixed_weights=interior_weights,
        ),
        cfg,
    )
    assert ctrl_path.metadata["mandate_feasible_all_rebalances"] is True
    assert ctrl_path.metadata["mandate_feasible_all_pre_return_sessions"] is True
    assert (
        ctrl_path.metadata["mandate_compliance_status"]
        == "rebalance_targets_and_pre_return_holdings_within_provisional_caps"
    )
    out["r2_synthetic_compliance_scope"] = {
        "drift_breach_probe": {
            "constraint_enforcement_scope": drift_path.metadata["constraint_enforcement_scope"],
            "mandate_feasible_all_rebalances": drift_path.metadata["mandate_feasible_all_rebalances"],
            "rebalance_target_compliance_status": drift_path.metadata["rebalance_target_compliance_status"],
            "mandate_feasible_all_pre_return_sessions": drift_path.metadata["mandate_feasible_all_pre_return_sessions"],
            "mandate_compliance_status": drift_path.metadata["mandate_compliance_status"],
            "next_session_equity_weight": float(drift_path.weights_before.iloc[1][equities].sum()),
            "equity_cap": cfg.portfolio.constraints.max_equity_weight,
            "breach_dates": list(drift_path.metadata["pre_return_holdings_compliance"]["breach_dates"]),
            "violated_constraints": list(drift_path.metadata["pre_return_holdings_compliance"]["violated_constraints"]),
        },
        "no_breach_control": {
            "mandate_feasible_all_rebalances": ctrl_path.metadata["mandate_feasible_all_rebalances"],
            "mandate_feasible_all_pre_return_sessions": ctrl_path.metadata["mandate_feasible_all_pre_return_sessions"],
            "mandate_compliance_status": ctrl_path.metadata["mandate_compliance_status"],
            "n_breach_sessions": ctrl_path.metadata["pre_return_holdings_compliance"]["n_breach_sessions"],
        },
    }

    # 3. Independent 48-session units/holdings ledger & physically truncated prefix exact invariance.
    rng = np.random.default_rng(3301)
    synthetic = pd.DataFrame(
        rng.normal(0.0, 0.01, (48, 7)),
        index=pd.bdate_range("2010-01-15", periods=48),
        columns=CANONICAL_TICKERS,
    )
    reference = StrategySpec(strategy_id="ledger", objective="benchmark_60_40", estimation_window_days=None)
    ledger_path = build_portfolio_path(synthetic, reference, cfg)
    prices = np.ones(7)
    units = np.zeros(7)
    wealth = 1.0
    target = np.array([0.6, 0.0, 0.0, 0.4, 0.0, 0.0, 0.0])
    ledger_wealth = []
    for i, (day, row) in enumerate(synthetic.iterrows()):
        boundary = i == 0 or day.month != synthetic.index[i - 1].month
        if boundary:
            current = units * prices
            pre_weights = current / wealth
            turnover = float(np.abs(target - pre_weights).sum())
            wealth *= 1.0 - cfg.portfolio.transaction_cost_bps_one_way / 10000.0 * turnover
            units = target * wealth / prices
        prices *= 1.0 + row.to_numpy()
        wealth = float(units @ prices)
        ledger_wealth.append(wealth)
    ledger_error = float(np.max(np.abs(np.array(ledger_wealth) - ledger_path.wealth.to_numpy())))
    assert ledger_error < 1e-12
    out["independent_units_ledger"] = {"sessions": 48, "max_absolute_wealth_difference": ledger_error}

    random_spec = make_core_strategy_specs(cfg, estimation_window_days=20)["min_variance"]
    full = build_portfolio_path(synthetic, random_spec, cfg)
    prefix = build_portfolio_path(synthetic.iloc[:37].copy(), random_spec, cfg)
    pd.testing.assert_frame_equal(
        full.weights_before.loc[prefix.weights_before.index],
        prefix.weights_before,
        check_exact=True,
    )
    pd.testing.assert_series_equal(
        full.wealth.loc[prefix.wealth.index],
        prefix.wealth,
        check_exact=True,
    )
    out["truncated_prefix_invariance"] = "passed, exact weights and wealth"

    # 4. Development-only (<= 2016-12-30) path invariance & target-vs-drift monitoring.
    bundle = load_data(cfg, offline=True)
    dev = bundle.simple_returns.loc[: cfg.chronology.development_end].copy()
    core_specs = make_core_strategy_specs(cfg)
    dev_paths = {name: build_portfolio_path(dev, spec, cfg) for name, spec in core_specs.items()}

    verified_arrays = 0
    post_fix_sha256: dict[str, dict[str, str]] = {}
    for strat_name, p in dev_paths.items():
        post_fix_sha256[strat_name] = {}
        for field_name, exp_hash in PRE_FIX_DEV_ARRAY_SHA256[strat_name].items():
            actual_hash = hashlib.sha256(getattr(p, field_name).to_numpy(dtype="float64").tobytes()).hexdigest()
            assert actual_hash == exp_hash, f"Array changed for {strat_name}.{field_name}"
            post_fix_sha256[strat_name][field_name] = actual_hash
            verified_arrays += 1

    dev_minvar = dev_paths["min_variance"]
    dev_diag = dev_minvar.metadata["pre_return_holdings_compliance"]
    assert dev_minvar.metadata["mandate_feasible_all_rebalances"] is True
    assert dev_minvar.metadata["mandate_feasible_all_pre_return_sessions"] is False
    assert dev_diag["n_active_sessions"] == 2516
    assert dev_diag["n_breach_sessions"] == 1439
    assert dev_diag["n_compliant_sessions"] == 1077

    out["development_path_array_invariance"] = {
        "strategies_checked": list(core_specs.keys()),
        "arrays_verified_bit_identical": verified_arrays,
        "sha256_by_strategy": post_fix_sha256,
    }
    out["development_min_variance_target_vs_drift"] = {
        "active_start": dev_minvar.metadata["active_start"],
        "active_end": dev_minvar.metadata["active_end"],
        "constraint_enforcement_scope": dev_minvar.metadata["constraint_enforcement_scope"],
        "n_rebalances": dev_minvar.metadata["n_rebalances"],
        "feasible_rebalance_targets": int(dev_minvar.rebalances["mandate_feasible"].sum()),
        "mandate_feasible_all_rebalances": dev_minvar.metadata["mandate_feasible_all_rebalances"],
        "rebalance_target_compliance_status": dev_minvar.metadata["rebalance_target_compliance_status"],
        "n_active_sessions": dev_diag["n_active_sessions"],
        "n_compliant_pre_return_sessions": dev_diag["n_compliant_sessions"],
        "n_breach_pre_return_sessions": dev_diag["n_breach_sessions"],
        "breach_session_fraction": dev_diag["breach_session_fraction"],
        "mandate_feasible_all_pre_return_sessions": dev_minvar.metadata["mandate_feasible_all_pre_return_sessions"],
        "mandate_compliance_status": dev_minvar.metadata["mandate_compliance_status"],
        "first_breach_date": dev_diag["first_breach_date"],
        "last_breach_date": dev_diag["last_breach_date"],
        "first_5_breach_dates": list(dev_diag["breach_dates"][:5]),
        "last_5_breach_dates": list(dev_diag["breach_dates"][-5:]),
        "violated_constraints": list(dev_diag["violated_constraints"]),
        "breach_counts_by_constraint": dev_diag["breach_counts_by_constraint"],
        "breach_counts_by_ticker_upper_cap": dev_diag["breach_counts_by_ticker_upper_cap"],
        "max_exposures": dev_diag["max_exposures"],
    }

    # 5. R3: Frank-Wolfe convex duality-gap inequality check.
    doc_text = (ROOT / "docs/sections/b_portfolio_construction.md").read_text(encoding="utf-8")
    assert r"0 \le f(w^*) - \min_{v \in \mathcal{P}} f(v) \le \max_{v \in \mathcal{P}}" in doc_text
    assert r"2\big(f(w^*)" not in doc_text
    x_eval, x_star = 2.0, 1.0
    fw_gap = float((2.0 * x_eval) * (x_eval - x_star))
    primal_err = float(x_eval**2 - x_star**2)
    assert 0.0 <= primal_err <= fw_gap
    assert 2.0 * primal_err > fw_gap
    out["r3_documentation_certificate"] = {
        "corrected_inequality_present": True,
        "erroneous_factor_two_removed": True,
        "counterexample_x2_on_1_2_at_2": {
            "primal_error": primal_err,
            "fw_gap": fw_gap,
            "twice_primal_error": 2.0 * primal_err,
            "primal_error_le_fw_gap": primal_err <= fw_gap,
        },
    }

    # 6. Snapshot hashes, baseline runtime diff, and protected git content checks.
    checks: dict[str, int] = {}
    for manifest_file in sorted((ROOT / "data/processed").glob("*/manifest.json")):
        manifest = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
        matches = [sha(ROOT / file) == expected for file, expected in manifest["file_sha256"].items()]
        assert all(matches)
        checks[manifest["dataset_id"]] = len(matches)
    assert sum(checks.values()) == 46
    out["snapshot_hashes"] = {"verified": sum(checks.values()), "by_dataset": checks}

    baseline_path = ROOT / "tmp/prompt_update_baseline.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
        changed = [file for file, expected in baseline.items() if sha(ROOT / file) != expected]
        assert set(changed) == {"src\\quantedge\\portfolio.py", "tests\\test_d_setup.py"}
        out["baseline_runtime_changes"] = changed

    for file in [
        "config.yaml",
        "requirements.txt",
        "src/quantedge/contracts.py",
        "data/processed/active_snapshot.json",
    ]:
        original = subprocess.run(
            ["git", "show", f"HEAD:{file}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        assert original.replace(b"\r\n", b"\n") == (ROOT / file).read_bytes().replace(b"\r\n", b"\n"), file

    assert cfg.config_hash == "587ddbe363589fb6956c23c5fe8b2b544bac81d9224a0b4bb59f60f5fbc0a017"
    out["config_hash"] = cfg.config_hash
    out["preserved_original_audit_files_sha256"] = {
        file: sha(ROOT / file)
        for file in [
            "audit/step3_review/STEP3_REVIEW.md",
            "audit/step3_review/ANTIGRAVITY_STEP3_FIX_PROMPT.txt",
            "audit/step3_review/verify_step3.py",
            "audit/step3_review/verification.json",
        ]
    }
    out["post_fix_source_sha256"] = {
        file: sha(ROOT / file)
        for file in [
            "src/quantedge/portfolio.py",
            "tests/test_b_portfolio.py",
            "tests/test_d_setup.py",
            "docs/sections/b_portfolio_construction.md",
        ]
    }
    out["protected_git_content"] = "config, requirements, contracts and active pointer unchanged"
    out["holdout_strategy_outcomes"] = "not computed; source load only, paths restricted to development (<= 2016-12-30)"

    out_path = Path(__file__).parent / "verification_after_fixes.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
