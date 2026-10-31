"""Independent likelihood and continuity boundary checks for Step 6 diagnostics."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import chi2

from quantedge._backtest_diagnostics import basel_traffic_light, coverage_tests
from quantedge.contracts import BACKTEST_COLUMNS, COVERAGE_TEST_COLUMNS
from quantedge.returns import expected_nyse_sessions


def rows(bits: list[int], *, confidence: float = 0.95, model: str = "historical") -> pd.DataFrame:
    dates = expected_nyse_sessions("2014-01-02", "2016-12-30")[:len(bits)]
    result = pd.DataFrame([
        dict(date=d, model=model, confidence=confidence, forecast_var=0.01,
             forecast_es=0.03, realized_loss=0.02 if bit else 0.0,
             exceedance=bool(bit), train_start=d-pd.Timedelta(days=100),
             train_end=d-pd.Timedelta(days=1), status="ok", reason=None)
        for d, bit in zip(dates, bits)
    ], columns=BACKTEST_COLUMNS)
    result["exceedance"] = result["exceedance"].astype("boolean")
    return result


def scalar_log_probability(sequence: list[int], p: float) -> float:
    return math.fsum(math.log(p if bit else 1-p) for bit in sequence)


def test_hand_likelihood_oracle_and_conditioned_cc() -> None:
    bits = [0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0]
    result = coverage_tests(rows(bits))
    actual = result.iloc[0]
    counts = {(0, 0): 3, (0, 1): 3, (1, 0): 3, (1, 1): 2}
    # Count table is hand-enumerated; compute each observed transition probability.
    q = 0.05
    uc = 2*(scalar_log_probability(bits, sum(bits)/len(bits)) - scalar_log_probability(bits, q))
    p01 = counts[0, 1] / (counts[0, 0]+counts[0, 1])
    p11 = counts[1, 1] / (counts[1, 0]+counts[1, 1])
    markov = math.fsum(math.log((p11 if previous else p01) if current else (1-p11 if previous else 1-p01)) for previous, current in zip(bits[:-1], bits[1:]))
    iid = scalar_log_probability(bits[1:], sum(bits[1:])/len(bits[1:]))
    null = scalar_log_probability(bits[1:], q)
    ind = 2*(markov-iid)
    cc = 2*(markov-null)
    assert tuple(result.columns) == COVERAGE_TEST_COLUMNS
    assert actual.lr_uc == pytest.approx(uc)
    assert actual.lr_ind == pytest.approx(ind)
    assert actual.lr_cc == pytest.approx(cc)
    assert actual.p_uc == pytest.approx(chi2.sf(uc, 1))
    assert actual.p_ind == pytest.approx(chi2.sf(ind, 1))
    assert actual.p_cc == pytest.approx(chi2.sf(cc, 2))
    diag = result.attrs["diagnostics"][0]
    assert [diag[k] for k in ("n00", "n01", "n10", "n11")] == [3, 3, 3, 2]
    assert actual.lr_cc == pytest.approx(actual.lr_ind + diag["lr_uc_transition"])
    assert actual.lr_cc != pytest.approx(actual.lr_ind + actual.lr_uc)


def test_clustered_vs_dispersed_same_total_exceptions() -> None:
    clustered = [0]*80+[1]*20+[0]*100
    dispersed = [1 if i % 10 == 5 else 0 for i in range(200)]
    first, second = coverage_tests(rows(clustered)).iloc[0], coverage_tests(rows(dispersed)).iloc[0]
    assert first.n_exceedances == second.n_exceedances == 20
    assert first.lr_uc == second.lr_uc
    assert first.lr_ind > second.lr_ind


@pytest.mark.parametrize("bit", [0, 1])
def test_no_or_all_exceptions_uc_finite_ind_unidentifiable(bit: int) -> None:
    result = coverage_tests(rows([bit]*30))
    value = result.iloc[0]
    assert math.isfinite(value.lr_uc) and math.isfinite(value.p_uc)
    assert value.lr_ind is None and value.p_ind is None
    assert value.lr_cc is None and value.p_cc is None
    assert "unidentified" in result.attrs["diagnostics"][0]["ind_reason"]


def test_tiny_empty_and_warning_forecast_samples() -> None:
    empty = coverage_tests(rows([]))
    assert empty.empty and tuple(empty.columns) == COVERAGE_TEST_COLUMNS
    single = coverage_tests(rows([1])).iloc[0]
    assert single.n_valid == 1 and single.lr_uc is not None and single.lr_ind is None
    warning_rows = rows([0, 1, 0, 1, 0, 0])
    warning_rows.loc[0, ["status", "reason", "forecast_es"]] = ["warning", "ES is not defined", None]
    warning = coverage_tests(warning_rows).iloc[0]
    assert warning.n_valid == 6


@pytest.mark.parametrize("drop_row", [False, True])
def test_transition_counts_never_bridge_invalid_or_missing_sessions(drop_row: bool) -> None:
    frame = rows([0, 0, 1, 0, 1, 1])
    if drop_row:
        frame = frame.drop(index=2)
    else:
        frame.loc[2, ["status", "reason", "forecast_var", "exceedance"]] = ["unavailable", "fit_failure", None, None]
    result = coverage_tests(frame)
    diag = result.attrs["diagnostics"][0]
    assert [diag[k] for k in ("n00", "n01", "n10", "n11")] == [1, 1, 0, 1]
    assert diag["n_transitions"] == 3 and diag["valid_runs"] == 2
    assert result.iloc[0].n_skipped == (0 if drop_row else 1)
    assert result.iloc[0].lr_cc is None
    assert result.iloc[0].lr_ind is not None


def test_calendar_holidays_do_not_break_consecutive_sessions() -> None:
    frame = rows([0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0])
    assert any((frame.date.diff().dt.days.fillna(1)) > 1)
    diag = coverage_tests(frame).attrs["diagnostics"][0]
    assert diag["n_transitions"] == len(frame)-1 and diag["valid_runs"] == 1


def test_invalid_pairs_not_silently_nonexceptions_and_inputs_unchanged() -> None:
    frame = rows([0, 1, 0, 1, 0, 0])
    frame.loc[0, "exceedance"] = True
    frame.loc[1, "train_end"] = frame.loc[1, "date"]
    frame.loc[2, "forecast_var"] = math.inf
    saved = frame.copy(deep=True)
    result = coverage_tests(frame)
    pd.testing.assert_frame_equal(frame, saved)
    assert result.iloc[0].n_valid == 3 and result.iloc[0].n_skipped == 3
    assert sum(result.attrs["diagnostics"][0]["skipped_reason_counts"].values()) == 3


def test_grouping_rejects_portfolio_mixing_and_duplicate_dates() -> None:
    first = rows([0, 1, 0, 0])
    second = rows([0, 1, 0, 0], confidence=0.99, model="parametric_normal")
    result = coverage_tests(pd.concat([first, second]))
    assert len(result) == 2 and result.n_valid.tolist() == [4, 4]
    with pytest.raises(ValueError, match="duplicate"):
        coverage_tests(pd.concat([first, first]))
    mixed = first.assign(portfolio_id=["a", "a", "b", "b"])
    with pytest.raises(ValueError, match="separately"):
        coverage_tests(mixed)


@pytest.mark.parametrize("count,zone", [(4,"green"), (5,"yellow"), (9,"yellow"), (10,"red")])
def test_basel_boundaries_exactly_250(count: int, zone: str) -> None:
    frame = rows([1]*count+[0]*(250-count), confidence=0.99)
    result = basel_traffic_light(frame)
    assert result["zone"] == zone and result["n_exceedances"] == count
    assert result["status"] == "ok" and result["n_valid"] == 250
    assert result["expected_exceedances"] == 2.5
    assert result["block_start"] == frame.iloc[0].date.strftime("%Y-%m-%d")
    assert result["block_end"] == frame.iloc[-1].date.strftime("%Y-%m-%d")


def test_basel_requires_250_and_99_percent_and_single_group() -> None:
    assert basel_traffic_light(rows([], confidence=0.99))["status"] == "unavailable"
    assert basel_traffic_light(rows([0]*249, confidence=0.99))["zone"] is None
    assert basel_traffic_light(rows([0]*250))["status"] == "not_applicable"
    mixed = pd.concat([rows([0]*250, confidence=0.99), rows([0], confidence=0.99, model="parametric_normal")])
    assert basel_traffic_light(mixed)["status"] == "not_applicable"
    multiday = rows([0]*250, confidence=0.99)
    multiday.attrs["horizon_days"] = 10
    assert basel_traffic_light(multiday)["status"] == "not_applicable"
    assert "one_day" in basel_traffic_light(multiday)["reason"]


@pytest.mark.parametrize("mode", ["drop_interior", "invalid_interior", "invalid_endpoint"])
def test_basel_latest_block_gaps_never_fall_back(mode: str) -> None:
    frame = rows([0]*300, confidence=0.99)
    old_end = frame.iloc[-1].date.strftime("%Y-%m-%d")
    if mode == "drop_interior":
        frame = frame.drop(index=280)
    else:
        position = 299 if mode == "invalid_endpoint" else 280
        frame.loc[position, ["status", "reason", "forecast_var", "exceedance"]] = ["unavailable", "no_forecast", None, None]
    result = basel_traffic_light(frame)
    assert result["status"] == "unavailable" and result["zone"] is None
    assert result["block_end"] == old_end and result["n_valid"] == 249
    assert "no_backward_fallback" in result["reason"]


def test_basel_latest_block_ignores_invalid_older_rows() -> None:
    frame = rows([0]*300, confidence=0.99)
    frame.loc[0, ["status", "reason", "forecast_var", "exceedance"]] = ["unavailable", "old_fit_failure", None, None]
    assert basel_traffic_light(frame)["status"] == "ok"
