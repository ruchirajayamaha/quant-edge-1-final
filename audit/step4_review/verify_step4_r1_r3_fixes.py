"""Post-fix verification for SOLO STEP 4 bounded review corrections R1-R3.

Preserves original audit/step4_review/{STEP4_REVIEW.md,ANTIGRAVITY_STEP4_FIX_PROMPT.txt,
verify_step4.py,verification.json} untouched and writes verification_after_fixes.json.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quantedge.config import load_config
from quantedge.data import DataUnavailableError, load_context_data, load_data
from quantedge.kpis import (
    build_development_kpi_bundle,
    compute_ex_post_real_return_metrics,
    compute_kpis,
)
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs
from quantedge.returns import expected_nyse_sessions


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    cfg = load_config(ROOT / "config.yaml")
    out: dict[str, object] = {
        "scope": "post-fix R1-R3 verification; synthetic repros; development-only strategy checks; 46+7 hash checks",
    }

    # ------------------------------------------------------------------
    # R1: Positive raw returns with some negative RF-excess returns
    # ------------------------------------------------------------------
    dates = pd.bdate_range("2010-01-04", periods=4)
    p = pd.Series([0.0001, 0.0002, 0.0003, 0.0004], index=dates)
    b = pd.Series([0.00005, 0.0003, -0.0001, 0.0002], index=dates)
    m = pd.Series([0.001, -0.002, 0.002, -0.001], index=dates)
    rf = pd.Series(0.00025, index=dates)

    r1_df = compute_kpis(p, b, m, rf).set_index("metric")
    exp_dd_rf = math.sqrt(252.0 * ((-0.00015) ** 2 + (-0.00005) ** 2) / 4.0)
    assert r1_df.loc["downside_deviation", "status"] == "ok"
    assert r1_df.loc["sortino_ratio", "status"] == "ok"
    assert math.isclose(float(r1_df.loc["downside_deviation", "value"]), exp_dd_rf, abs_tol=1e-15)
    assert math.isclose(float(r1_df.loc["sortino_ratio", "value"]), 0.0, abs_tol=1e-14)
    assert r1_df.attrs["diagnostics"]["sortino_zero_target"] is None
    assert "unavailable (all raw returns >= 0)" in str(r1_df.loc["sortino_ratio", "note"])

    out["r1_positive_returns_below_rf"] = {
        "crashes": False,
        "downside_deviation_rf": float(r1_df.loc["downside_deviation", "value"]),
        "sortino_ratio_rf": float(r1_df.loc["sortino_ratio", "value"]),
        "sortino_status": str(r1_df.loc["sortino_ratio", "status"]),
        "sortino_zero_target": r1_df.attrs["diagnostics"]["sortino_zero_target"],
        "sortino_note": str(r1_df.loc["sortino_ratio", "note"]),
    }

    # ------------------------------------------------------------------
    # R2: Internal missing CPI months & exact NYSE session date matching
    # ------------------------------------------------------------------
    days = expected_nyse_sessions("2010-01-01", "2010-05-31")
    zero_returns = pd.Series(0.0, index=days)
    cpi = pd.Series(
        [100.0, 101.0, np.nan, 121.0, 122.0, 123.0],
        index=pd.period_range("2009-12", "2010-05", freq="M"),
    )
    real_default = compute_ex_post_real_return_metrics(zero_returns, cpi)
    summary_default = real_default.attrs["common_months_summary"]
    assert summary_default["n_common_complete_months"] == 5
    assert summary_default["calendar_months_in_span"] == 5
    assert math.isclose(float(summary_default["cpi_index_ratio"]), 123.0 / 100.0, rel_tol=1e-14)
    assert summary_default["missing_current_cpi_months_excluded"] == ["2010-02"]
    assert summary_default["missing_prior_cpi_months_excluded"] == ["2010-03"]
    assert summary_default["unreleased_or_missing_cpi_months_excluded"] == ["2010-02", "2010-03"]
    assert list(real_default["status"]) == ["warning", "warning", "warning", "warning"]

    real_block = compute_ex_post_real_return_metrics(
        zero_returns,
        cpi,
        interval_policy="longest_contiguous_cpi_block",
    )
    summary_block = real_block.attrs["common_months_summary"]
    assert summary_block["first_common_month"] == "2010-04"
    assert summary_block["last_common_month"] == "2010-05"
    assert summary_block["base_cpi_month"] == "2010-03"
    assert summary_block["n_common_complete_months"] == 2
    assert math.isclose(float(summary_block["cpi_index_ratio"]), 123.0 / 121.0, rel_tol=1e-14)
    assert summary_block["outside_selected_block_months_excluded"] == ["2010-01"]
    assert summary_block["unreleased_or_missing_cpi_months_excluded"] == ["2010-02", "2010-03"]

    out["r2_interior_cpi_gap"] = {
        "default_endpoint_cpi_policy": {
            "declared_start": summary_default["first_common_month"],
            "declared_end": summary_default["last_common_month"],
            "base_cpi_month": summary_default["base_cpi_month"],
            "months_used": summary_default["n_common_complete_months"],
            "calendar_months_in_span": summary_default["calendar_months_in_span"],
            "computed_cpi_multiplier": summary_default["cpi_index_ratio"],
            "declared_endpoint_cpi_multiplier": 123.0 / 100.0,
            "missing_current_cpi_months_excluded": summary_default["missing_current_cpi_months_excluded"],
            "missing_prior_cpi_months_excluded": summary_default["missing_prior_cpi_months_excluded"],
            "reported_excluded_cpi_months": summary_default["unreleased_or_missing_cpi_months_excluded"],
            "all_statuses": list(real_default["status"]),
            "real_annual_return": float(
                real_default.set_index("metric").loc["ex_post_real_annual_return_common_months", "value"]
            ),
            "scattered_diagnostic_classification": summary_default[
                "scattered_single_months_diagnostic"
            ]["classification"],
        },
        "longest_contiguous_cpi_block_policy": {
            "declared_start": summary_block["first_common_month"],
            "declared_end": summary_block["last_common_month"],
            "base_cpi_month": summary_block["base_cpi_month"],
            "months_used": summary_block["n_common_complete_months"],
            "computed_cpi_multiplier": summary_block["cpi_index_ratio"],
            "declared_endpoint_cpi_multiplier": 123.0 / 121.0,
            "outside_selected_block_months_excluded": summary_block[
                "outside_selected_block_months_excluded"
            ],
            "reported_excluded_cpi_months": summary_block[
                "unreleased_or_missing_cpi_months_excluded"
            ],
            "all_statuses": list(real_block["status"]),
        },
    }

    jan_days = expected_nyse_sessions("2010-01-01", "2010-01-31")
    bad_days = jan_days.delete(1).append(pd.DatetimeIndex(["2010-01-09"])).sort_values()
    bad_month_returns = pd.Series(0.0, index=bad_days)
    bad_real = compute_ex_post_real_return_metrics(bad_month_returns, cpi)
    bad_sum = bad_real.attrs["common_months_summary"]
    assert bad_sum["n_common_complete_months"] == 0
    assert bad_sum["partial_portfolio_months_excluded"] == ["2010-01"]
    assert (bad_real["status"] == "unavailable").all()
    out["r2_month_coverage_exact_dates"] = {
        "missing_nyse_date": str(jan_days[1].date()),
        "unexpected_saturday": "2010-01-09",
        "observed_rows": len(bad_days),
        "expected_nyse_rows": len(jan_days),
        "falsely_counted_complete_months": bad_sum["n_common_complete_months"],
        "excluded_reason": bad_sum["excluded_months_by_reason"]["2010-01"],
    }

    # ------------------------------------------------------------------
    # R3: Context cache file resolution, tamper rejection & compatibility
    # ------------------------------------------------------------------
    ctx = load_context_data(cfg, offline=True)
    tmp_parent = (ROOT / "tmp").resolve()
    tmp_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="step4_postfix_verify_", dir=tmp_parent) as name:
        temporary = Path(name).resolve()
        assert temporary.is_relative_to(tmp_parent)
        copied = temporary / "context"
        shutil.copytree(ROOT / "data/reference/context", copied)

        # 1. Untouched relocated cache succeeds
        relocated_ok = load_context_data(cfg, offline=True, repo_root=ROOT, context_dir=copied)
        pd.testing.assert_frame_equal(
            relocated_ok.split_adjusted_closes,
            ctx.split_adjusted_closes,
            check_exact=True,
        )

        # 2. Tampered relocated cache is rejected
        altered_path = copied / "etf_split_adjusted_closes.parquet"
        altered = pd.read_parquet(altered_path)
        original_first_price = float(altered.iloc[0, 0])
        altered.iloc[0, 0] = original_first_price * 1.10
        altered.to_parquet(altered_path)
        try:
            load_context_data(cfg, offline=True, repo_root=ROOT, context_dir=copied)
            tampered_rejected = False
            tampered_err = ""
        except DataUnavailableError as exc:
            tampered_rejected = True
            tampered_err = str(exc)
        assert tampered_rejected is True

    # Clean up empty tmp directory if empty
    if tmp_parent.exists() and not any(tmp_parent.iterdir()):
        tmp_parent.rmdir()

    older_cfg = replace(cfg, data=replace(cfg.data, frozen_end_date="2016-12-30"))
    try:
        load_context_data(older_cfg, offline=True)
        mismatched_end_rejected = False
        mismatch_error = ""
    except DataUnavailableError as exc:
        mismatched_end_rejected = True
        mismatch_error = str(exc)
    assert mismatched_end_rejected is True

    bounded_2016 = load_context_data(older_cfg, offline=True, slice_to_config=True)
    assert str(bounded_2016.split_adjusted_closes.index[-1].date()) == "2016-12-30"
    assert bounded_2016.manifest["is_bounded_view"] is True

    out["r3_custom_context_hash_and_identity"] = {
        "untouched_relocated_copy_accepted": True,
        "tampered_relocated_copy_rejected": tampered_rejected,
        "tampered_rejection_error": tampered_err,
        "mismatched_frozen_2016_rejected_by_default": mismatched_end_rejected,
        "mismatched_rejection_error": mismatch_error,
        "explicit_bounded_view_context_id": bounded_2016.context_id,
        "explicit_bounded_view_end": str(bounded_2016.split_adjusted_closes.index[-1].date()),
    }

    # ------------------------------------------------------------------
    # Independent development KPI oracle & before/after invariance
    # ------------------------------------------------------------------
    bundle = load_data(cfg, offline=True)
    dev = bundle.simple_returns.loc[: cfg.chronology.development_end].copy()
    paths = {
        name: build_portfolio_path(dev, spec, cfg)
        for name, spec in make_core_strategy_specs(cfg).items()
    }
    path = paths["min_variance"]
    port = path.net_returns
    bench = paths["benchmark_60_40"].net_returns
    market = dev["SPY"].reindex(port.index)
    rf_dev = bundle.rf_daily.reindex(port.index)
    observed = compute_kpis(port, bench, market, rf_dev)
    vals = observed.set_index("metric")["value"].to_dict()

    pr = port.to_list()
    ep = [float(a - c) for a, c in zip(port, rf_dev)]
    em = [float(a - c) for a, c in zip(market, rf_dev)]
    act = [float(a - c) for a, c in zip(port, bench)]
    terminal = math.prod(1.0 + x for x in pr)
    geo = terminal ** (252.0 / len(pr)) - 1.0
    down = math.sqrt(252.0 * math.fsum(min(0.0, x) ** 2 for x in ep) / len(ep))
    ols = sm.OLS(ep, sm.add_constant(em, has_constant="add")).fit()
    wealth, peak, worst = 1.0, 1.0, 0.0
    for value in pr:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1.0)
    expected = {
        "geometric_annual_return": geo,
        "arithmetic_annual_return": 252.0 * statistics.mean(pr),
        "annualized_volatility": math.sqrt(252.0) * statistics.stdev(pr),
        "sharpe_ratio": math.sqrt(252.0) * statistics.mean(ep) / statistics.stdev(ep),
        "downside_deviation": down,
        "sortino_ratio": 252.0 * statistics.mean(ep) / down,
        "capm_beta": float(ols.params[1]),
        "jensen_alpha": 252.0 * float(ols.params[0]),
        "treynor_ratio": 252.0 * statistics.mean(ep) / float(ols.params[1]),
        "tracking_error": math.sqrt(252.0) * statistics.stdev(act),
        "information_ratio": math.sqrt(252.0) * statistics.mean(act) / statistics.stdev(act),
        "max_drawdown": worst,
        "calmar_ratio": geo / abs(worst),
    }
    diffs = {metric: abs(float(vals[metric]) - answer) for metric, answer in expected.items()}
    assert max(diffs.values()) < 1e-10, diffs

    assert bundle.rf_accrual_sensitivity is not None
    dev_bundle = build_development_kpi_bundle(
        paths,
        dev["SPY"],
        bundle.rf_daily.loc[: cfg.chronology.development_end],
        rf_accrual_sensitivity=bundle.rf_accrual_sensitivity.loc[: cfg.chronology.development_end],
        context_bundle=ctx,
    )
    mv_real = dev_bundle["ex_post_real_returns"]["min_variance"].set_index("metric")
    assert (mv_real["status"] == "ok").all()
    assert mv_real.attrs["common_months_summary"]["n_common_complete_months"] == 119
    assert math.isclose(
        float(mv_real.loc["ex_post_real_annual_return_common_months", "value"]),
        0.04663732670187959,
        abs_tol=1e-15,
    )

    out["independent_development_kpi_oracle"] = {
        "start": str(port.index[0].date()),
        "end": str(port.index[-1].date()),
        "n_obs": len(port),
        "metrics_checked": len(expected),
        "max_absolute_difference": max(diffs.values()),
        "alpha_t_difference_vs_statsmodels": abs(
            float(observed.attrs["capm_regression"]["alpha_t_stat"]) - float(ols.tvalues[0])
        ),
        "development_119m_real_return_unchanged": True,
        "development_119m_real_annual_return": float(
            mv_real.loc["ex_post_real_annual_return_common_months", "value"]
        ),
    }

    # ------------------------------------------------------------------
    # 46 market snapshot hashes + 7 context hashes + protected files
    # ------------------------------------------------------------------
    snapshot_checks = {}
    for file in sorted((ROOT / "data/processed").glob("*/manifest.json")):
        manifest = json.loads(file.read_text(encoding="utf-8-sig"))
        matches = [
            sha(ROOT / key) == expected_h
            for key, expected_h in manifest["file_sha256"].items()
        ]
        assert all(matches)
        snapshot_checks[manifest["dataset_id"]] = len(matches)
    context_matches = [
        sha(ROOT / key) == expected_h for key, expected_h in ctx.manifest["file_sha256"].items()
    ]
    assert all(context_matches)
    out["hashes"] = {
        "market_snapshots": sum(snapshot_checks.values()),
        "context_files": len(context_matches),
        "all_match": True,
    }

    for file in [
        "config.yaml",
        "requirements.txt",
        "src/quantedge/contracts.py",
        "data/processed/active_snapshot.json",
    ]:
        original = subprocess.run(
            ["git", "show", f"HEAD:{file}"], cwd=ROOT, capture_output=True, check=True
        ).stdout
        assert original.replace(b"\r\n", b"\n") == (ROOT / file).read_bytes().replace(
            b"\r\n", b"\n"
        ), file
    original_data = subprocess.run(
        ["git", "show", "HEAD:src/quantedge/data.py"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.replace(b"\r\n", b"\n")
    assert (
        (ROOT / "src/quantedge/data.py")
        .read_bytes()
        .replace(b"\r\n", b"\n")
        .startswith(original_data.rstrip())
    )
    out["protected_files"] = (
        "config, dependencies, contracts, active pointer and pre-context data adapter unchanged"
    )
    out["post_fix_sha256"] = {
        name: sha(ROOT / name)
        for name in [
            "src/quantedge/kpis.py",
            "src/quantedge/data.py",
            "tests/test_a_kpis.py",
            "docs/sections/a_kpis_and_capm.md",
            "data/reference/context/context_manifest.json",
        ]
    }
    out["holdout_strategy_results"] = (
        "not computed; only development paths and synthetic probes"
    )

    out_path = Path(__file__).parent / "verification_after_fixes.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    for key in [
        "r1_positive_returns_below_rf",
        "r2_interior_cpi_gap",
        "r2_month_coverage_exact_dates",
        "r3_custom_context_hash_and_identity",
        "independent_development_kpi_oracle",
        "hashes",
    ]:
        print(key, json.dumps(out[key]))


if __name__ == "__main__":
    main()
