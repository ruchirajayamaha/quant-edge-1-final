"""Likelihood-based VaR diagnostics for frozen one-day backtest rows.

Kupiec UC uses all eligible observations. Christoffersen IND and CC use the
first-state-conditioned transition likelihood; consequently CC is IND plus the
UC statistic on transition destinations, not UC on all N observations. CC is
withheld for disconnected valid runs. This module performs no forecasting.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2

from quantedge.contracts import BACKTEST_COLUMNS, COVERAGE_TEST_COLUMNS
from quantedge.returns import expected_nyse_sessions


def _finite(value: Any) -> bool:
    return not isinstance(value, (bool, np.bool_)) and isinstance(value, (int, float, np.integer, np.floating)) and math.isfinite(float(value))


def _frame(rows: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(rows, pd.DataFrame):
        raise TypeError("backtest_rows must be a DataFrame")
    missing = set(BACKTEST_COLUMNS) - set(rows.columns)
    if missing:
        raise ValueError(f"backtest rows missing columns: {sorted(missing)}")
    if rows.columns.duplicated().any():
        raise ValueError("backtest columns must be unique")
    for portfolio_column in ("portfolio_id", "strategy_id"):
        if portfolio_column in rows and rows[portfolio_column].nunique(dropna=False) > 1:
            raise ValueError("Call diagnostics separately for each portfolio/strategy")
    frame = rows.copy(deep=True)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    dates = pd.DatetimeIndex(frame["date"])
    if dates.hasnans or dates.tz is not None or not dates.equals(dates.normalize()):
        raise ValueError("backtest dates must be finite timezone-naive session dates")
    if frame["model"].isna().any() or any(not isinstance(v, str) or not v for v in frame["model"]):
        raise ValueError("backtest model names must be nonempty strings")
    if any(not _finite(v) or not 0 < float(v) < 1 for v in frame["confidence"]):
        raise ValueError("backtest confidence must be finite and in (0,1)")
    if frame.duplicated(["model", "confidence", "date"]).any():
        raise ValueError("duplicate target date within a model/confidence group")
    return frame.sort_values(["model", "confidence", "date"], kind="stable").reset_index(drop=True)


def _eligible(group: pd.DataFrame) -> tuple[np.ndarray, list[str | None], pd.DatetimeIndex]:
    dates = pd.DatetimeIndex(group["date"])
    calendar = expected_nyse_sessions(dates.min(), dates.max()) if len(dates) else pd.DatetimeIndex([])
    sessions = set(calendar)
    eligible: list[bool] = []
    reasons: list[str | None] = []
    for row in group.to_dict(orient="records"):
        reason = None
        if row["date"] not in sessions:
            reason = "not_an_expected_nyse_session"
        elif not isinstance(row["status"], str) or row["status"] not in ("ok", "warning"):
            reason = row["reason"] if isinstance(row["reason"], str) and row["reason"] else "forecast_unavailable"
        elif not _finite(row["forecast_var"]) or not _finite(row["realized_loss"]):
            reason = "nonfinite_var_or_realized_loss"
        elif not isinstance(row["exceedance"], (bool, np.bool_)):
            reason = "missing_or_nonboolean_exceedance"
        elif bool(row["exceedance"]) != (float(row["realized_loss"]) > float(row["forecast_var"])):
            reason = "exceedance_disagrees_with_strict_loss_comparison"
        else:
            try:
                start, end = pd.Timestamp(row["train_start"]), pd.Timestamp(row["train_end"])
                if pd.isna(start) or pd.isna(end) or start > end or not end < row["date"]:
                    reason = "invalid_or_nonpast_training_bounds"
            except (TypeError, ValueError):
                reason = "invalid_or_nonpast_training_bounds"
        eligible.append(reason is None)
        reasons.append(reason)
    return np.asarray(eligible, dtype=bool), reasons, calendar


def _log_bernoulli(n0: int, n1: int, probability: float) -> float:
    """Count-weighted log likelihood with zero-count terms defined as zero."""
    if not 0 <= probability <= 1:
        raise ValueError("Bernoulli probability outside [0,1]")
    if n1 and probability == 0 or n0 and probability == 1:
        return -math.inf
    return (n1 * math.log(probability) if n1 else 0.0) + (n0 * math.log(1.0 - probability) if n0 else 0.0)


def _lr(null_log: float, alternative_log: float) -> float:
    value = 2.0 * (alternative_log - null_log)
    if value < -1e-10 or not math.isfinite(value):
        raise ValueError("invalid likelihood-ratio statistic")
    return max(value, 0.0)


def coverage_tests(backtest_rows: pd.DataFrame) -> pd.DataFrame:
    """Return all-N UC plus conditional-transition IND/CC, with explicit availability."""
    frame = _frame(backtest_rows)
    summaries: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for (model, confidence), group in frame.groupby(["model", "confidence"], sort=True):
        group = group.reset_index(drop=True)
        eligible, reasons, calendar = _eligible(group)
        dates = pd.DatetimeIndex(group["date"])
        ranks = {date: i for i, date in enumerate(calendar)}
        n_valid = int(eligible.sum())
        n_skipped = int(len(group) - n_valid)
        exceptions = [bool(x) for x in group.loc[eligible, "exceedance"]]
        n_exceptions = sum(exceptions)
        q = round(1.0 - float(confidence), 12)
        counts = [0, 0, 0, 0]
        valid_runs = 0
        prior_date: pd.Timestamp | None = None
        prior_exception: bool | None = None
        for row, valid in zip(group.to_dict(orient="records"), eligible):
            if not valid:
                prior_date = None
                prior_exception = None
                continue
            date = row["date"]
            exception = bool(row["exceedance"])
            if prior_date is not None and ranks[date] == ranks[prior_date] + 1:
                counts[2 * int(prior_exception) + int(exception)] += 1
            else:
                valid_runs += 1
            prior_date, prior_exception = date, exception
        n00, n01, n10, n11 = counts
        n_transitions = sum(counts)
        skipped_reasons: dict[str, int] = {}
        for reason in reasons:
            if reason:
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        diag: dict[str, Any] = {
            "model": str(model), "confidence": float(confidence),
            "n00": n00, "n01": n01, "n10": n10, "n11": n11,
            "n_transitions": n_transitions, "valid_runs": valid_runs,
            "uc_status": "unavailable", "uc_reason": "no_eligible_pairs",
            "ind_status": "unavailable", "ind_reason": "too_few_transitions",
            "cc_status": "unavailable", "cc_reason": "independence_unavailable",
            "lr_uc_transition": None, "p_uc_transition": None,
            "skipped_reason_counts": skipped_reasons,
            "transition_likelihood": "condition_on_first_observation_of_each_run",
        }
        values: dict[str, Any] = {name: None for name in COVERAGE_TEST_COLUMNS}
        values.update(model=str(model), confidence=float(confidence), n_valid=n_valid,
                      n_skipped=n_skipped, n_exceedances=n_exceptions, expected_rate=q,
                      observed_rate=n_exceptions / n_valid if n_valid else None)
        notes = ["Chi-square p-values are asymptotic; non-rejection is not proof of safety."]
        if n_valid:
            null = _log_bernoulli(n_valid - n_exceptions, n_exceptions, q)
            alternative = _log_bernoulli(n_valid - n_exceptions, n_exceptions, n_exceptions / n_valid)
            values["lr_uc"] = _lr(null, alternative)
            values["p_uc"] = float(chi2.sf(values["lr_uc"], 1))
            diag.update(uc_status="ok", uc_reason=None)
            if n_valid * q < 5 or n_exceptions < 5:
                notes.append("Sparse exceptions/expected count: asymptotic calibration and power are limited.")
        if n_transitions >= 2:
            if n00 + n01 == 0 or n10 + n11 == 0:
                diag["ind_reason"] = "unvisited_origin_state_transition_probability_unidentified"
            elif n01 + n11 == 0 or n00 + n10 == 0:
                diag["ind_reason"] = "boundary_pooled_transition_probability"
            else:
                pooled = (n01 + n11) / n_transitions
                iid_ll = _log_bernoulli(n00 + n10, n01 + n11, pooled)
                markov_ll = _log_bernoulli(n00, n01, n01 / (n00 + n01)) + _log_bernoulli(n10, n11, n11 / (n10 + n11))
                values["lr_ind"] = _lr(iid_ll, markov_ll)
                values["p_ind"] = float(chi2.sf(values["lr_ind"], 1))
                diag.update(ind_status="ok", ind_reason=None)
                null_transition_ll = _log_bernoulli(n00 + n10, n01 + n11, q)
                diag["lr_uc_transition"] = _lr(null_transition_ll, iid_ll)
                diag["p_uc_transition"] = float(chi2.sf(diag["lr_uc_transition"], 1))
                if min(counts) < 5:
                    notes.append("Sparse transition cells/boundary fitted probabilities limit chi-square approximations.")
                if valid_runs == 1:
                    values["lr_cc"] = _lr(null_transition_ll, markov_ll)
                    values["p_cc"] = float(chi2.sf(values["lr_cc"], 2))
                    diag.update(cc_status="ok", cc_reason=None)
                else:
                    diag["cc_reason"] = "disconnected_valid_runs_conditional_coverage_withheld"
        for test in ("ind", "cc"):
            if diag[f"{test}_status"] == "unavailable":
                notes.append(f"{test.upper()} unavailable: {diag[f'{test}_reason']}.")
        notes.append("CC uses transition-conditioned UC + IND; all-N UC is reported separately.")
        values["status"] = "unavailable" if not n_valid else ("warning" if n_skipped or any(diag[f"{test}_status"] != "ok" for test in ("ind", "cc")) or n_valid * q < 5 or min(counts) < 5 else "ok")
        values["note"] = " ".join(notes)
        summaries.append(values)
        diagnostics.append(diag)
    result = pd.DataFrame(summaries, columns=COVERAGE_TEST_COLUMNS, dtype=object)
    result.attrs.update(diagnostics=diagnostics, likelihood_convention="UC: all eligible N; IND/CC: conditional on first state; CC unavailable across disconnected valid runs")
    return result


def basel_traffic_light(backtest_rows_99: pd.DataFrame) -> dict[str, Any]:
    """Educational 99% diagnostic at the latest supplied date, without gap filling."""
    frame = _frame(backtest_rows_99)
    result: dict[str, Any] = {
        "status": "unavailable", "reason": None, "zone": None,
        "model": None, "confidence": 0.99, "window_sessions": 250,
        "n_valid": 0, "n_exceedances": None, "expected_exceedances": 2.5,
        "block_start": None, "block_end": None,
        "educational_only": True,
        "note": "Educational 250-session 99% one-day diagnostic; not regulatory approval.",
    }
    if backtest_rows_99.attrs.get("horizon_days", 1) != 1 or (
        "horizon_days" in frame.columns and not frame["horizon_days"].eq(1).all()
    ):
        result.update(status="not_applicable", reason="requires_one_day_forecast_realization_pairs")
        return result
    if frame.empty:
        result["reason"] = "insufficient_history_empty_input"
        return result
    if frame["model"].nunique() != 1 or frame["confidence"].nunique() != 1:
        result.update(status="not_applicable", reason="mixed_models_or_confidences")
        return result
    result["model"] = str(frame.iloc[0]["model"])
    if not math.isclose(float(frame.iloc[0]["confidence"]), 0.99, rel_tol=0, abs_tol=1e-12):
        result.update(status="not_applicable", reason="requires_99_percent_confidence")
        return result
    end = pd.Timestamp(frame["date"].max())
    result["block_end"] = end.strftime("%Y-%m-%d")
    calendar = expected_nyse_sessions(end - pd.Timedelta(days=600), end)
    if end not in calendar or len(calendar) < 250:
        result.update(status="not_applicable", reason="endpoint_is_not_an_expected_nyse_session")
        return result
    block = calendar[-250:]
    result["block_start"] = block[0].strftime("%Y-%m-%d")
    eligible, reasons, _ = _eligible(frame)
    frame = frame.assign(_eligible=eligible, _invalid_reason=reasons).set_index("date")
    existing = frame.reindex(block)
    n_valid = int(existing["_eligible"].eq(True).sum())
    result["n_valid"] = n_valid
    result["n_missing_sessions"] = int((~block.isin(frame.index)).sum())
    result["n_invalid_pairs"] = int(250 - n_valid - result["n_missing_sessions"])
    if len(frame) < 250 or frame.index.min() > block[0]:
        result["reason"] = "insufficient_history_for_latest_250_sessions"
        return result
    if n_valid != 250:
        result["reason"] = "latest_250_sessions_include_missing_or_invalid_pairs_no_backward_fallback"
        return result
    count = int(existing["exceedance"].astype(bool).sum())
    result.update(status="ok", reason=None, n_exceedances=count,
                  zone="green" if count <= 4 else "yellow" if count <= 9 else "red")
    return result
