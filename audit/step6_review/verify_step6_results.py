"""Independent scalar/array oracle and preservation checks for persisted Step 6 results."""

from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from quantedge.config import load_config
from quantedge.data import load_data
from quantedge.portfolio import build_portfolio_path, make_core_strategy_specs
from quantedge.returns import expected_nyse_sessions


ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def logterm(count, probability):
    return 0.0 if count == 0 else count * math.log(probability)


def main():
    base = json.loads((ROOT / "audit/step6_review/STEP6_BASELINE.json").read_text(encoding="utf-8"))
    for name, expected in base["sha256"].items():
        assert sha(ROOT / name) == expected, name
    count = 0
    for p in list((ROOT / "data/processed").glob("*/manifest.json")) + [ROOT / "data/reference/context/context_manifest.json"]:
        for name, expected in json.loads(p.read_text(encoding="utf-8-sig"))["file_sha256"].items():
            assert sha(ROOT / name) == expected, name
            count += 1
    assert count == 53
    outdir = ROOT / "results/step6_backtest_preview"
    payload = json.loads((outdir / "backtest_results.json").read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    cfg = load_config(ROOT / "config.yaml")
    data = load_data(cfg, offline=True)
    dev = data.simple_returns.loc[: cfg.chronology.development_end]
    path = build_portfolio_path(dev, make_core_strategy_specs(cfg)["min_variance"], cfg)
    assert len(payload["runs"]) == 4
    assert payload["metadata"]["n_target_sessions"] == len(path.weights_before)
    maxima = {"var": 0.0, "es": 0.0, "gross_loss": 0.0, "coverage_lr": 0.0, "coverage_p": 0.0}
    rows_checked = 0
    summaries = []
    for run in payload["runs"]:
        conf = run["confidence"]
        prob = float(1 - Fraction(str(conf)))
        hits = []
        for row in run["rows"]:
            date = pd.Timestamp(row["date"])
            assert date <= pd.Timestamp("2016-12-30")
            assert row["status"] in ("ok", "warning"), row
            position = dev.index.get_loc(date)
            train = dev.iloc[position - 500:position]
            assert len(train) == 500 and train.index[-1] < date
            assert train.index.equals(expected_nyse_sessions(train.index.min(), train.index.max()))
            assert pd.Timestamp(row["train_start"]) == train.index[0]
            assert pd.Timestamp(row["train_end"]) == train.index[-1]
            w = path.weights_before.loc[date].to_numpy()
            losses = -(train.to_numpy() @ w)
            realized = -float(dev.loc[date].to_numpy() @ w)
            if run["model"] == "historical":
                ordered = np.sort(losses)
                rank = math.ceil(len(ordered) * Fraction(str(conf)))
                v = float(ordered[rank - 1])
                tail_count = int(len(ordered) * (1 - Fraction(str(conf))))
                e = float(math.fsum(ordered[-tail_count:]) / tail_count)
            else:
                mu_loss = float(losses.mean())
                sigma = float(losses.std(ddof=1))
                z = NormalDist().inv_cdf(conf)
                v = mu_loss + sigma * z
                e = mu_loss + sigma * math.exp(-z * z / 2) / math.sqrt(2 * math.pi) / prob
            maxima["var"] = max(maxima["var"], abs(v - row["forecast_var"]))
            maxima["es"] = max(maxima["es"], abs(e - row["forecast_es"]))
            maxima["gross_loss"] = max(maxima["gross_loss"], abs(realized - row["realized_loss"]))
            assert bool(row["exceedance"]) == (realized > row["forecast_var"])
            hits.append(int(row["exceedance"]))
            rows_checked += 1
        assert [r["date"] for r in run["rows"]] == [d.strftime("%Y-%m-%d") for d in path.weights_before.index]
        n = len(hits)
        x = sum(hits)
        p = x / n
        ll_null = logterm(x, prob) + logterm(n - x, 1 - prob)
        ll_mle = logterm(x, p) + logterm(n - x, 1 - p)
        lr_uc = 2 * (ll_mle - ll_null)
        trans = {"n00": 0, "n01": 0, "n10": 0, "n11": 0}
        for a, b in zip(hits[:-1], hits[1:]):
            trans[f"n{a}{b}"] += 1
        a, b, c, d = (trans[k] for k in ("n00", "n01", "n10", "n11"))
        pp = (b + d) / (n - 1)
        l_iid = logterm(a + c, 1 - pp) + logterm(b + d, pp)
        l_markov = logterm(a, a / (a + b)) + logterm(b, b / (a + b)) + logterm(c, c / (c + d)) + logterm(d, d / (c + d))
        lr_ind = 2 * (l_markov - l_iid)
        s = run["coverage"]
        assert s["n_valid"] == n and s["n_skipped"] == 0 and s["n_exceedances"] == x
        for key, oracle in (("lr_uc", lr_uc), ("lr_ind", lr_ind)):
            maxima["coverage_lr"] = max(maxima["coverage_lr"], abs(s[key] - oracle))
            maxima["coverage_p"] = max(maxima["coverage_p"], abs(s['p_' + key[3:]] - math.erfc(math.sqrt(max(oracle, 0) / 2))))
        # Conditional likelihood test on transition destinations, conditioned on first hit.
        l_cc_null = logterm(a + c, 1 - prob) + logterm(b + d, prob)
        cc_conditioned = 2 * (l_markov - l_cc_null)
        cc = float(s["lr_cc"])
        assert abs(cc - cc_conditioned) < 1e-9
        assert abs(s["p_cc"] - math.exp(-cc / 2)) < 1e-12
        if conf == 0.99:
            expected = sum(hits[-250:])
            zone = "green" if expected <= 4 else "yellow" if expected <= 9 else "red"
            basel = run["basel"]
            # Accept documented key names; verify the actual count and zone unambiguously.
            assert basel.get("zone") == zone, basel
            actual_count = basel.get("n_exceedances", basel.get("exceptions"))
            assert actual_count == expected, basel
        summaries.append({"model": run["model"], "confidence": conf, "n": n, "exceptions": x, "transitions": trans, "lr_uc": lr_uc, "lr_ind": lr_ind, "lr_cc_recorded": cc})
    assert maxima["var"] < 1e-12 and maxima["es"] < 1e-12
    assert maxima["gross_loss"] < 1e-15 and maxima["coverage_lr"] < 1e-9 and maxima["coverage_p"] < 1e-12
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "rows_checked": rows_checked,
              "max_absolute_errors": maxima, "source_data_hashes": count,
              "protected_files_unchanged": len(base["sha256"]), "summaries": summaries,
              "holdout_outcomes_inspected": False, "authority_sha256": sha(outdir / "backtest_results.json")}
    (ROOT / "audit/step6_review/verification.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
