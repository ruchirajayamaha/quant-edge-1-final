"""Unit, causality, likelihood-oracle, Basel boundary, and development smoke tests for SOLO STEP 6 (A3)."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from scipy.stats import chi2 as scipy_chi2

from quantedge import (
    BACKTEST_COLUMNS,
    CANONICAL_TICKERS,
    COVERAGE_TEST_COLUMNS,
    RiskEstimate,
    load_config,
)
from quantedge.backtest import (
    basel_traffic_light,
    coverage_tests,
    rolling_backtest,
)
from quantedge.data import load_data
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs
from quantedge.returns import expected_nyse_sessions
from quantedge.var import get_risk_forecaster

ROOT = Path(__file__).resolve().parents[1]


def _make_nyse_returns_and_weights(
    n_sessions: int = 16,
    *,
    start_date: str = "2016-01-04",
    weight_start_offset: int = 4,
    seed: int = 202606,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create synthetic 7-ETF simple returns and pre-return weights on consecutive NYSE sessions."""
    nyse = expected_nyse_sessions(start_date, "2018-12-31")[:n_sessions]
    rng = np.random.default_rng(seed)
    rets = rng.normal(loc=0.0004, scale=0.011, size=(n_sessions, len(CANONICAL_TICKERS)))
    returns_df = pd.DataFrame(rets, index=nyse, columns=list(CANONICAL_TICKERS))

    n_targets = n_sessions - weight_start_offset
    raw_w = rng.uniform(0.05, 0.35, size=(n_targets, len(CANONICAL_TICKERS)))
    raw_w = raw_w / raw_w.sum(axis=1, keepdims=True)
    weights_df = pd.DataFrame(
        raw_w,
        index=nyse[weight_start_offset:],
        columns=list(CANONICAL_TICKERS),
    )
    return returns_df, weights_df


def test_spy_callback_verifies_exact_previous_window_date_t_exclusion_and_weights() -> None:
    """Spy callback verifies exact preceding window, strict train_end < t, warmup preservation, and non-mutation."""
    returns_df, weights_df = _make_nyse_returns_and_weights(n_sessions=14, weight_start_offset=4)
    orig_returns = returns_df.copy(deep=True)
    orig_weights = weights_df.copy(deep=True)

    calls: list[dict[str, Any]] = []

    class SpyForecaster:
        model = "spy_historical"

        def __call__(
            self,
            train_asset_returns: pd.DataFrame,
            weights: pd.Series,
            *,
            confidence: float,
            seed: int | None = None,
        ) -> RiskEstimate:
            calls.append(
                {
                    "train_index": train_asset_returns.index.copy(),
                    "train_values": train_asset_returns.to_numpy(dtype=float, copy=True),
                    "weights_index": tuple(weights.index),
                    "weights_values": weights.to_numpy(dtype=float, copy=True),
                    "target_date": pd.Timestamp(weights.name),
                    "confidence": confidence,
                    "seed": seed,
                }
            )
            losses = -(train_asset_returns.to_numpy(dtype=float) @ weights.to_numpy(dtype=float))
            var_val = float(np.max(losses))
            es_val = float(var_val + 0.001)
            # Mutate callback arguments in-place to prove rolling_backtest isolates inputs
            train_asset_returns.iloc[:, :] = 999.0
            weights.iloc[:] = -999.0
            return RiskEstimate(
                model="spy_historical",
                confidence=confidence,
                horizon_days=1,
                var_loss=var_val,
                es_loss=es_val,
                n_obs=len(train_asset_returns),
                sample_start=train_asset_returns.index[0].strftime("%Y-%m-%d"),
                sample_end=train_asset_returns.index[-1].strftime("%Y-%m-%d"),
                status="ok",
            )

    window = 4
    bt = rolling_backtest(
        returns_df,
        weights_df,
        SpyForecaster(),
        confidence=0.95,
        window=window,
        seed=202603,
    )

    # Full prior warmup (rows 0..3 of returns_df) was preserved, so all 10 target rows are valid
    assert len(bt) == 10
    assert len(calls) == 10
    assert (bt["status"] == "ok").all()
    assert tuple(bt.columns) == BACKTEST_COLUMNS

    for idx, call_info in enumerate(calls):
        target_ts = weights_df.index[idx]
        expected_slice = returns_df.iloc[idx : idx + window]
        assert call_info["target_date"] == target_ts
        assert call_info["train_index"].equals(expected_slice.index)
        assert call_info["train_index"][-1] < target_ts
        assert target_ts not in call_info["train_index"]
        assert call_info["weights_index"] == CANONICAL_TICKERS
        assert np.allclose(call_info["weights_values"], weights_df.iloc[idx].to_numpy(dtype=float), atol=0.0)
        assert np.allclose(call_info["train_values"], expected_slice.to_numpy(dtype=float), atol=0.0)
        assert call_info["seed"] == 202603

        expected_realized_loss = float(
            -(returns_df.loc[target_ts].to_numpy(dtype=float) @ weights_df.loc[target_ts].to_numpy(dtype=float))
        )
        assert math.isclose(float(bt.loc[idx, "realized_loss"]), expected_realized_loss, rel_tol=0.0, abs_tol=1e-16)
        assert pd.Timestamp(bt.loc[idx, "train_start"]) == expected_slice.index[0]
        assert pd.Timestamp(bt.loc[idx, "train_end"]) == expected_slice.index[-1]
        assert pd.Timestamp(bt.loc[idx, "train_end"]) < pd.Timestamp(bt.loc[idx, "date"])

    # Verify caller DataFrames were not mutated
    pd.testing.assert_frame_equal(returns_df, orig_returns, check_exact=True)
    pd.testing.assert_frame_equal(weights_df, orig_weights, check_exact=True)


def test_future_perturbation_and_appended_data_invariance_plus_origin_seed_policy() -> None:
    """Perturbing returns on or after t_star never alters forecasts on or before t_star; appending rows preserves prefix."""
    returns_df, weights_df = _make_nyse_returns_and_weights(n_sessions=20, weight_start_offset=5, seed=77)
    forecaster = get_risk_forecaster("historical")

    bt_base = rolling_backtest(
        returns_df,
        weights_df,
        forecaster,
        confidence=0.95,
        window=5,
        seed=202603,
    )

    # Perturb returns at target index 6 (session 11) and all later dates
    perturbed_returns = returns_df.copy(deep=True)
    t_star = weights_df.index[6]
    perturbed_returns.loc[perturbed_returns.index >= t_star] = -0.15

    bt_perturbed = rolling_backtest(
        perturbed_returns,
        weights_df,
        forecaster,
        confidence=0.95,
        window=5,
        seed=202603,
    )

    # Forecasts up to and including t_star (rows 0..6) must be bit-for-bit identical
    for idx in range(7):
        assert bt_base.loc[idx, "date"] == bt_perturbed.loc[idx, "date"]
        assert float(bt_base.loc[idx, "forecast_var"]) == float(bt_perturbed.loc[idx, "forecast_var"])
        assert float(bt_base.loc[idx, "forecast_es"]) == float(bt_perturbed.loc[idx, "forecast_es"])

    # Realizations before t_star (rows 0..5) are unchanged, while realization at t_star (row 6) changes
    for idx in range(6):
        assert float(bt_base.loc[idx, "realized_loss"]) == float(bt_perturbed.loc[idx, "realized_loss"])
        assert bt_base.loc[idx, "exceedance"] == bt_perturbed.loc[idx, "exceedance"]
    assert float(bt_perturbed.loc[6, "realized_loss"]) != float(bt_base.loc[6, "realized_loss"])
    assert bt_perturbed.loc[6, "exceedance"] is True

    # Appending future data leaves earlier rows and origin seeds completely unchanged
    bt_prefix = rolling_backtest(
        returns_df.iloc[:15],
        weights_df.iloc[:10],
        get_risk_forecaster("parametric_normal"),
        confidence=0.99,
        window=5,
        seed=999,
    )
    bt_extended = rolling_backtest(
        returns_df,
        weights_df,
        get_risk_forecaster("parametric_normal"),
        confidence=0.99,
        window=5,
        seed=999,
    )
    pd.testing.assert_frame_equal(
        bt_prefix.reset_index(drop=True),
        bt_extended.iloc[:10].reset_index(drop=True),
        check_exact=True,
    )


def test_hand_calculated_gross_pnl_equality_boundary_negative_var_and_warning_vs_unavailable() -> None:
    """Verify exact gross P&L, equality is non-exceedance, negative VaR sign preservation, and warning vs unavailable."""
    nyse = expected_nyse_sessions("2016-02-01", "2016-02-20")[:6]
    daily_r = [-0.010, 0.005, -0.020, 0.010, 0.008, -0.030]
    returns_df = pd.DataFrame(
        np.tile(np.array(daily_r, dtype=float)[:, None], (1, len(CANONICAL_TICKERS))),
        index=nyse,
        columns=list(CANONICAL_TICKERS),
    )
    eq_w = np.full((4, len(CANONICAL_TICKERS)), 1.0 / len(CANONICAL_TICKERS), dtype=float)
    weights_df = pd.DataFrame(eq_w, index=nyse[2:], columns=list(CANONICAL_TICKERS))

    def custom_forecaster(
        train_asset_returns: pd.DataFrame,
        weights: pd.Series,
        *,
        confidence: float,
        seed: int | None = None,
    ) -> RiskEstimate:
        t_end = train_asset_returns.index[-1]
        s_start = train_asset_returns.index[0].strftime("%Y-%m-%d")
        s_end = t_end.strftime("%Y-%m-%d")
        if t_end == nyse[1]:
            return RiskEstimate(
                model="custom_model",
                confidence=confidence,
                horizon_days=1,
                var_loss=0.020,
                es_loss=0.025,
                n_obs=2,
                sample_start=s_start,
                sample_end=s_end,
                status="ok",
            )
        if t_end == nyse[2]:
            return RiskEstimate(
                model="custom_model",
                confidence=confidence,
                horizon_days=1,
                var_loss=-0.015,
                es_loss=-0.012,
                n_obs=2,
                sample_start=s_start,
                sample_end=s_end,
                status="ok",
            )
        if t_end == nyse[3]:
            return RiskEstimate(
                model="custom_model",
                confidence=confidence,
                horizon_days=1,
                var_loss=0.010,
                es_loss=None,
                n_obs=2,
                sample_start=s_start,
                sample_end=s_end,
                status="warning",
                reason="GPD shape xi >= 1: finite VaR, infinite ES",
            )
        return RiskEstimate(
            model="custom_model",
            confidence=confidence,
            horizon_days=1,
            var_loss=None,
            es_loss=None,
            n_obs=2,
            sample_start=s_start,
            sample_end=s_end,
            status="unavailable",
            reason="POT threshold had fewer than 50 exceedances",
        )

    bt = rolling_backtest(returns_df, weights_df, custom_forecaster, confidence=0.99, window=2)
    assert len(bt) == 4

    # Row 0: realized_loss == forecast_var == 0.020 -> exceedance is False
    assert math.isclose(float(bt.loc[0, "realized_loss"]), 0.020, abs_tol=1e-16)
    assert math.isclose(float(bt.loc[0, "forecast_var"]), 0.020, abs_tol=1e-16)
    assert bt.loc[0, "exceedance"] is False
    assert bt.loc[0, "status"] == "ok"
    assert bt.loc[0, "reason"] is None

    # Row 1: negative forecast_var = -0.015 preserved, realized_loss = -0.010 > -0.015 -> exceedance is True
    assert math.isclose(float(bt.loc[1, "forecast_var"]), -0.015, abs_tol=1e-16)
    assert math.isclose(float(bt.loc[1, "realized_loss"]), -0.010, abs_tol=1e-16)
    assert bt.loc[1, "exceedance"] is True
    assert bt.loc[1, "status"] == "ok"

    # Row 2: eligible warning forecast (var_loss=0.010, es_loss=None, realized_loss=-0.008) -> exceedance is False
    assert math.isclose(float(bt.loc[2, "forecast_var"]), 0.010, abs_tol=1e-16)
    assert bt.loc[2, "forecast_es"] is None
    assert bt.loc[2, "exceedance"] is False
    assert bt.loc[2, "status"] == "warning"
    assert "xi >= 1" in str(bt.loc[2, "reason"])

    # Row 3: unavailable forecast -> forecast_var is None, exceedance is None (never False)
    assert bt.loc[3, "forecast_var"] is None
    assert bt.loc[3, "forecast_es"] is None
    assert math.isclose(float(bt.loc[3, "realized_loss"]), 0.030, abs_tol=1e-16)
    assert bt.loc[3, "exceedance"] is None
    assert bt.loc[3, "status"] == "unavailable"
    assert "fewer than 50 exceedances" in str(bt.loc[3, "reason"])

    cov = coverage_tests(bt)
    assert int(cov.loc[0, "n_valid"]) == 3
    assert int(cov.loc[0, "n_skipped"]) == 1
    assert int(cov.loc[0, "n_exceedances"]) == 1


def test_missing_weights_short_history_nyse_gaps_and_canonical_validation() -> None:
    """Test short history, invalid/missing weights, genuine NYSE gaps vs holidays, and canonical validation."""
    # Include Thanksgiving 2015-11-26 (an NYSE holiday) to prove holidays are NOT mistaken for gaps
    returns_df, _ = _make_nyse_returns_and_weights(
        n_sessions=10,
        start_date="2015-11-20",
        weight_start_offset=0,
        seed=42,
    )
    assert pd.Timestamp("2015-11-26") not in returns_df.index

    eq_w = np.full((10, len(CANONICAL_TICKERS)), 1.0 / len(CANONICAL_TICKERS), dtype=float)
    weights_df = pd.DataFrame(eq_w, index=returns_df.index.copy(), columns=list(CANONICAL_TICKERS))
    # Corrupt weights on row 4 (NaN), row 5 (sum != 1.0), and drop row 7 from weights_df
    weights_df.iloc[4, 0] = float("nan")
    weights_df.iloc[5, :] = 0.25
    omitted_weight_ts = weights_df.index[7]
    weights_with_omitted = weights_df.drop(index=[omitted_weight_ts])

    bt = rolling_backtest(
        returns_df,
        weights_with_omitted,
        get_risk_forecaster("historical"),
        confidence=0.90,
        window=3,
    )
    # Output still contains all 10 expected NYSE sessions between first and last weights date
    assert len(bt) == 10
    for idx in (0, 1, 2):
        assert bt.loc[idx, "status"] == "unavailable"
        assert bt.loc[idx, "exceedance"] is None
        assert "insufficient_training_history" in str(bt.loc[idx, "reason"])

    assert bt.loc[3, "status"] == "ok"
    assert bt.loc[4, "status"] == "unavailable" and "missing_or_non_finite_weights" in str(bt.loc[4, "reason"])
    assert bt.loc[5, "status"] == "unavailable" and "invalid_weights_before" in str(bt.loc[5, "reason"])
    assert bt.loc[6, "status"] == "ok"
    assert bt.loc[7, "status"] == "unavailable" and "missing_weights_before_session" in str(bt.loc[7, "reason"])
    for idx in (8, 9):
        assert bt.loc[idx, "status"] == "ok"
        assert isinstance(bt.loc[idx, "exceedance"], bool)

    # Now drop a genuine open NYSE session (returns_df.index[6]) from returns_df
    dropped_ts = returns_df.index[6]
    gapped_returns = returns_df.drop(index=[dropped_ts])
    bt_gapped = rolling_backtest(
        gapped_returns,
        weights_df.iloc[6:],
        get_risk_forecaster("historical"),
        confidence=0.90,
        window=3,
    )
    assert bt_gapped.loc[0, "status"] == "unavailable"
    assert bt_gapped.loc[0, "realized_loss"] is None
    assert bt_gapped.loc[0, "exceedance"] is None
    assert "missing_target_asset_returns" in str(bt_gapped.loc[0, "reason"])

    assert bt_gapped.loc[1, "status"] == "unavailable"
    assert bt_gapped.loc[1, "realized_loss"] is None
    assert bt_gapped.loc[1, "exceedance"] is None
    assert "missing_nyse_session_before_target" in str(bt_gapped.loc[1, "reason"])

    assert bt_gapped.loc[2, "status"] == "unavailable"
    assert "missing_nyse_session_in_training_window" in str(bt_gapped.loc[2, "reason"])
    assert bt_gapped.loc[3, "status"] == "unavailable"
    assert "missing_nyse_session_in_training_window" in str(bt_gapped.loc[3, "reason"])

    # Verify canonical column order and parameter validation
    scrambled = returns_df[["AGG", "SPY", "EFA", "EEM", "GLD", "XLE", "XLK"]]
    with pytest.raises(ValueError, match="canonical order"):
        rolling_backtest(scrambled, weights_df, get_risk_forecaster("historical"), confidence=0.95, window=3)
    with pytest.raises(ValueError, match="canonical order"):
        rolling_backtest(
            returns_df,
            weights_df[["AGG", "SPY", "EFA", "EEM", "GLD", "XLE", "XLK"]],
            get_risk_forecaster("historical"),
            confidence=0.95,
            window=3,
        )
    with pytest.raises(ValueError, match="confidence"):
        rolling_backtest(returns_df, weights_df, get_risk_forecaster("historical"), confidence=1.0, window=3)
    with pytest.raises(ValueError, match="window"):
        rolling_backtest(returns_df, weights_df, get_risk_forecaster("historical"), confidence=0.95, window=1)


def test_coverage_tests_independent_scalar_likelihood_oracle_and_clustered_vs_dispersed() -> None:
    """Verify Kupiec POF, Christoffersen independence, and conditional coverage against an independent scalar oracle."""
    n_obs = 250
    nyse = expected_nyse_sessions("2015-01-02", "2016-06-30")[:n_obs]
    conf = 0.95
    alpha = 0.05

    # Sequence 1: 12 dispersed exceptions (every 20th session: indices 10, 30, ..., 230) -> n11 = 0
    dispersed_exc = [False] * n_obs
    for idx in range(10, 240, 20):
        dispersed_exc[idx] = True
    assert sum(dispersed_exc) == 12

    # Sequence 2: 12 exceptions with a cluster of 10 consecutive exceptions (indices 20..29) + 2 isolated (100, 150) -> n11 = 9
    clustered_exc = [False] * n_obs
    for idx in list(range(20, 30)) + [100, 150]:
        clustered_exc[idx] = True
    assert sum(clustered_exc) == 12

    def _build_bt_from_exc(model_name: str, exc_flags: list[bool]) -> pd.DataFrame:
        rows = []
        for d_ts, is_e in zip(nyse, exc_flags):
            rows.append(
                {
                    "date": d_ts,
                    "model": model_name,
                    "confidence": conf,
                    "forecast_var": 0.010,
                    "forecast_es": 0.014,
                    "realized_loss": 0.015 if is_e else 0.002,
                    "exceedance": bool(is_e),
                    "train_start": pd.Timestamp("2013-01-02"),
                    "train_end": pd.Timestamp("2014-12-31"),
                    "status": "ok",
                    "reason": None,
                }
            )
        return pd.DataFrame(rows, columns=list(BACKTEST_COLUMNS))

    df_disp = _build_bt_from_exc("dispersed_model", dispersed_exc)
    df_clus = _build_bt_from_exc("clustered_model", clustered_exc)
    combined = pd.concat([df_disp, df_clus], ignore_index=True)

    cov = coverage_tests(combined)
    assert tuple(cov.columns) == COVERAGE_TEST_COLUMNS
    assert len(cov) == 2

    def _scalar_oracle(exc_seq: list[bool], p_exp: float) -> tuple[float, float, float, float, float, float]:
        n = len(exc_seq)
        x = sum(1 for e in exc_seq if e)
        p_hat = x / n
        ll0_u = (n - x) * math.log(1.0 - p_exp) + x * math.log(p_exp)
        ll1_u = (n - x) * math.log(1.0 - p_hat) + x * math.log(p_hat)
        lr_u = 2.0 * (ll1_u - ll0_u)
        p_u = float(scipy_chi2.sf(lr_u, df=1))

        n00 = sum(1 for a, b in zip(exc_seq[:-1], exc_seq[1:]) if not a and not b)
        n01 = sum(1 for a, b in zip(exc_seq[:-1], exc_seq[1:]) if not a and b)
        n10 = sum(1 for a, b in zip(exc_seq[:-1], exc_seq[1:]) if a and not b)
        n11 = sum(1 for a, b in zip(exc_seq[:-1], exc_seq[1:]) if a and b)
        pi01 = n01 / (n00 + n01)
        pi11 = n11 / (n10 + n11)
        pi_all = (n01 + n11) / (n00 + n01 + n10 + n11)

        def _term(cnt: int, prob: float) -> float:
            return 0.0 if cnt == 0 else cnt * math.log(prob)

        ll0_i = _term(n00 + n10, 1.0 - pi_all) + _term(n01 + n11, pi_all)
        ll1_i = _term(n00, 1.0 - pi01) + _term(n01, pi01) + _term(n10, 1.0 - pi11) + _term(n11, pi11)
        lr_i = 2.0 * (ll1_i - ll0_i)
        p_i = float(scipy_chi2.sf(lr_i, df=1))
        ll0_cc = _term(n00 + n10, 1.0 - p_exp) + _term(n01 + n11, p_exp)
        lr_c = 2.0 * (ll1_i - ll0_cc)
        p_c = float(scipy_chi2.sf(lr_c, df=2))
        return lr_u, p_u, lr_i, p_i, lr_c, p_c

    u1, pu1, i1, pi1, c1, pc1 = _scalar_oracle(dispersed_exc, alpha)
    u2, pu2, i2, pi2, c2, pc2 = _scalar_oracle(clustered_exc, alpha)

    # Note: coverage_tests sorts by (model, confidence): row 0 is clustered_model, row 1 is dispersed_model
    row_clus = cov.loc[cov["model"] == "clustered_model"].iloc[0]
    row_disp = cov.loc[cov["model"] == "dispersed_model"].iloc[0]

    assert math.isclose(u1, u2, abs_tol=1e-15)
    assert math.isclose(float(row_disp["lr_uc"]), u1, abs_tol=1e-14)
    assert math.isclose(float(row_clus["lr_uc"]), u2, abs_tol=1e-14)
    assert math.isclose(float(row_disp["p_uc"]), pu1, abs_tol=1e-14)

    assert math.isclose(float(row_disp["lr_ind"]), i1, abs_tol=1e-13)
    assert math.isclose(float(row_disp["p_ind"]), pi1, abs_tol=1e-13)
    assert math.isclose(float(row_disp["lr_cc"]), c1, abs_tol=1e-13)
    assert math.isclose(float(row_disp["p_cc"]), pc1, abs_tol=1e-13)
    assert float(row_disp["p_ind"]) > 0.20

    assert math.isclose(float(row_clus["lr_ind"]), i2, abs_tol=1e-13)
    assert math.isclose(float(row_clus["p_ind"]), pi2, abs_tol=1e-13)
    assert math.isclose(float(row_clus["lr_cc"]), c2, abs_tol=1e-13)
    assert math.isclose(float(row_clus["p_cc"]), pc2, abs_tol=1e-13)
    assert float(row_clus["p_ind"]) < 1e-6
    assert float(row_clus["p_cc"]) < 1e-5


def test_persisted_step6_preview_artifacts_and_strict_json_integrity() -> None:
    """Verify persisted results/step6_backtest_preview/ artifacts, strict JSON, and 53/53 snapshot hashes."""
    preview_dir = ROOT / "results/step6_backtest_preview"
    authority_path = preview_dir / "backtest_results.json"
    manifest_path = preview_dir / "manifest.json"
    baseline_path = ROOT / "audit/step6_review/STEP6_BASELINE.json"

    assert authority_path.is_file()
    assert manifest_path.is_file()
    assert baseline_path.is_file()

    def _reject_nan_inf(token: str) -> Any:
        raise ValueError(f"Non-standard JSON token encountered: {token}")

    authority = json.loads(authority_path.read_text(encoding="utf-8"), parse_constant=_reject_nan_inf)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"), parse_constant=_reject_nan_inf)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"), parse_constant=_reject_nan_inf)

    # Verify strict JSON roundtrip with allow_nan=False
    json.dumps(authority, allow_nan=False)
    json.dumps(manifest, allow_nan=False)

    # Verify all 50 protected Step 3-5 / config / contract files in STEP6_BASELINE.json
    for rel_path, expected_sha in baseline["sha256"].items():
        actual_sha = hashlib.sha256((ROOT / rel_path).read_bytes()).hexdigest()
        assert actual_sha == expected_sha, f"Protected file modified: {rel_path}"

    # Verify all 53 source-data hashes (v1=13, r2=15, r3=18, context=7)
    data_hash_count = 0
    for m_path in list((ROOT / "data/processed").glob("*/manifest.json")) + [
        ROOT / "data/reference/context/context_manifest.json"
    ]:
        m_json = json.loads(m_path.read_text(encoding="utf-8-sig"))
        for f_rel, f_sha in m_json["file_sha256"].items():
            assert hashlib.sha256((ROOT / f_rel).read_bytes()).hexdigest() == f_sha, f_rel
            data_hash_count += 1
    assert data_hash_count == 53

    # Verify manifest artifact SHA-256 hashes
    for art_name, expected_sha in manifest["artifacts_sha256"].items():
        art_file = preview_dir / art_name
        assert art_file.is_file(), f"Missing preview artifact: {art_name}"
        assert hashlib.sha256(art_file.read_bytes()).hexdigest() == expected_sha, f"Hash mismatch for {art_name}"

    # Verify PNG magic bytes and SVG root tags on both Step 6 figures
    for stem in ("figure_01_rolling_var_exceptions", "figure_02_annual_exception_calibration"):
        png_bytes = (preview_dir / f"{stem}.png").read_bytes()
        svg_text = (preview_dir / f"{stem}.svg").read_text(encoding="utf-8")
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert "<svg" in svg_text and "</svg>" in svg_text

    # Verify development-only bounds and 4 primary runs (historical & parametric_normal x 0.95 & 0.99)
    assert authority["metadata"]["development_end"] == "2016-12-30"
    assert authority["metadata"]["sample_start"] == "2007-01-05"
    assert authority["metadata"]["sample_end"] == "2016-12-30"
    assert authority["metadata"]["n_target_sessions"] == 2516
    assert authority["metadata"]["holdout_outcomes_inspected"] is False
    assert len(authority["runs"]) == 4

    # Also verify 90% confidence works on the real development min_variance path
    cfg = load_config(ROOT / "config.yaml")
    data = load_data(cfg, offline=True)
    dev_returns = data.simple_returns.loc[: cfg.chronology.development_end]
    mv_path = build_portfolio_path(dev_returns, make_core_strategy_specs(cfg)["min_variance"], cfg)
    bt_90 = rolling_backtest(
        dev_returns.iloc[:520],
        mv_path.weights_before.iloc[:16],
        get_risk_forecaster("historical"),
        confidence=0.90,
        window=500,
    )
    assert len(bt_90) == 16
    assert (bt_90["status"] == "ok").all()
    assert basel_traffic_light(bt_90)["status"] == "not_applicable"
