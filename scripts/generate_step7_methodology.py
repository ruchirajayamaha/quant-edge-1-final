"""Generate Step 7 methodology from persisted results, without fitting or resampling."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "results/step7_evt_preview/step7_recorded_results.json"
DOC = ROOT / "docs/sections/c_var_es_and_evt.md"
SECTION_MARKER = "## 7. SOLO STEP 7"


def load_authority():
    return json.loads(AUTHORITY.read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def number(value, digits=4, multiplier=1):
    return "N/A" if value is None else f"{value * multiplier:.{digits}f}"


def table(headers, rows):
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(str(v).replace("|", "/") for v in row) + " |" for row in rows),
    ])


def risk_table(data):
    rows = []
    for win, run in data["runs"].items():
        normal = {r["confidence"]: r for r in run["model_comparison"] if r["model"] == "parametric_normal"}
        for r in run["model_comparison"]:
            v, e = r["var_loss"], r["es_loss"]
            n = normal[r["confidence"]]
            rows.append([
                win, r["model"], number(r["confidence"], 2), number(v, 4, 100),
                number(v, 2, data["metadata"]["nav_usd"]), number(e, 4, 100),
                number(e, 2, data["metadata"]["nav_usd"]),
                number(None if v is None or e is None else e-v, 4, 10000),
                number(None if v is None else v-n["var_loss"], 4, 10000),
                number(None if e is None else e-n["es_loss"], 4, 10000),
                r["status"], r.get("region") or "N/A", r.get("reason") or "N/A",
            ])
    return table(["Window", "Model", "Confidence", "VaR (%)", "VaR (USD)", "ES (%)", "ES (USD)",
                  "ES minus VaR (bps)", "VaR minus Normal (bps)", "ES minus Normal (bps)",
                  "Status", "Region", "Reason"], rows)


def threshold_table(data):
    rows = []
    for win, run in data["runs"].items():
        for d in run["threshold_diagnostics_dense"]:
            rows.append([win, number(d["candidate_quantile"], 3), number(d["threshold"], 4, 100),
                         d["n_exceedances"], d["n_ties_at_threshold"], number(d["mean_excess"], 4, 100),
                         number(d["xi"], 4), number(d["xi_se_asymptotic_iid"], 4),
                         number(d["beta"], 4, 100), number(d["modified_scale"], 4, 100),
                         d["status"], d.get("reason") or "N/A"])
    return table(["Window", "q", "u (%)", "Strict exceedances", "Ties at u", "Mean excess (%)",
                  "xi", "xi SE (iid asymptotic)", "beta (%)", "beta minus xi*u (%)", "Status", "Reason"], rows)


def bootstrap_records(data):
    """Separate pure-POT/hybrid availability and intervals; never copy one into the other."""
    rows = []
    for win, run in data["runs"].items():
        boot = run["bootstrap"]
        for c in boot["summary"]["by_confidence"].values():
            entries = [(c["method"], c)]
            if c["method"] != "body_tail_hybrid":
                entries.append(("body_tail_hybrid", c["body_tail_hybrid"]))
            for method, item in entries:
                rows.append({"window": win, "confidence": c["confidence"], "method": method,
                             "replications": boot["cache_key"]["n_replications"],
                             "required": boot["cache_key"]["min_successful_replications"],
                             "n_var": item["n_var_available"], "n_es": item["n_es_finite"],
                             "n_infinite_es": item["n_es_unavailable_infinite_xi_ge_1"],
                             "var": item["var"], "es": item["es"]})
    return rows


def interval(summary):
    if summary["interval_status"] != "ok":
        return "N/A"
    return f"[{summary['p025'] * 100:.4f}, {summary['p975'] * 100:.4f}]"


def bootstrap_table(data):
    return table(
        ["Window", "Confidence", "Method", "VaR finite/total", "ES finite/total", "Required", "Infinite ES",
         "VaR median (%)", "VaR interval (%)", "VaR interval status", "ES median (%)", "ES interval (%)", "ES interval status"],
        [[r["window"], number(r["confidence"], 2), r["method"], f"{r['n_var']}/{r['replications']}",
          f"{r['n_es']}/{r['replications']}", r["required"], r["n_infinite_es"],
          number(r["var"]["median"], 4, 100), interval(r["var"]), r["var"]["interval_status"],
          number(r["es"]["median"], 4, 100), interval(r["es"]), r["es"]["interval_status"]]
         for r in bootstrap_records(data)])


def render_section(data):
    meta = data["metadata"]
    policy = meta["bootstrap_policy"]
    fit_rows = []
    for win, r in data["runs"].items():
        f = r["primary_fit"]
        ci = r["bootstrap"]["summary"]["xi"]
        fit_rows.append([win, r["sample_start"], r["sample_end"], r["n_obs"],
                         f["n_exceedances"], number(f["xi"], 6), number(ci["p025"], 6),
                         number(ci["p975"], 6), ci["interval_status"]])
    weights = ", ".join(f"{t} {v * 100:.4f}%" for t, v in meta["weights"].items())
    return f'''## 7. SOLO STEP 7 (C2/C3) — Unconditional EVT and tail uncertainty

<!-- Generated by scripts/generate_step7_methodology.py from the saved authority. -->

**DEVELOPMENT ONLY through {meta['development_end']}; fixed terminal-development exposure;
one-day pre-cost simple-return losses. Human validation and mandate/protocol approval PENDING.**

Authority: `results/step7_evt_preview/step7_recorded_results.json`.
Dataset: `{meta['dataset_id']}`. Config: `{meta['config_hash']}`.
NAV: USD {meta['nav_usd']:,.2f}. Exposure: {weights}.

### 7.1 Construction and limitations

Loss is `L = -(asset_returns @ weights)`. The threshold is the empirical step-CDF
quantile under the recorded fixed quantile policy; excesses are strictly `L > u`.
GPD location is fixed at zero. Scale must be positive and observed excesses must
satisfy fitted support. Failed convergence, inadequate excess counts and invalid
support remain explicit unavailable results. Nelder-Mead uses maxiter=20,000 and
maxfun=40,000, plus a local likelihood perturbation check. The reported parameter
SEs use analytic iid asymptotic formulas, not an observed-Hessian covariance.

For `p_u = N_u/n` and `a = (1-c)/p_u <= 1`, pure-POT VaR is
`u + beta*expm1(-xi*log(a))/xi`, with limit `u-beta*log(a)` at xi=0.
The actual threshold boundary is `1-p_u`; below it pure POT is unavailable.
For xi<1, `ES = (VaR + beta - xi*u)/(1-xi)`; at xi>=1, ES is unavailable
with a warning even if VaR is finite. Negative-xi tails have finite upper support.

The hybrid has the empirical step CDF for x<=u and `1-p_u*S_GPD(x-u)` for x>u.
Its empirical body has atoms and is not smooth or globally continuous. The tail's
right limit matches F(u); generally there is a left jump at u. Body-region VaR is
labelled BODY, not EVT extrapolation. Hybrid ES uses exact discrete body-quantile
integration, including fractional probability mass, plus analytic tail integration.

QQ/PP plots are descriptive diagnostics; they do not prove fit quality. Positive
xi point estimates are consistent with heavy tails under this fitted model, but
do not by themselves establish a formal rejection of Gaussianity. The recorded
moving-block xi intervals below both include zero. Threshold sensitivity, sparse
excesses, unconditional modelling and dependence limit interpretation; apparent
stability is not proof that the provisional threshold is uniquely correct.

The inherited threshold policy was recorded before development fitting, but it
remains unsigned and is not completed human preregistration. Step 6 found exception
clustering; the green final 250-session Basel blocks do not establish overall model
adequacy. These EVT results are not rolling EVT validation or final holdout results.

### 7.2 Samples and shape uncertainty

{table(['Window', 'Start', 'End', 'Observations', 'Primary excesses', 'xi', 'xi interval low', 'xi interval high', 'Interval status'], fit_rows)}

### 7.3 Threshold diagnostics

{threshold_table(data)}

### 7.4 Matched model comparison

All methods within each window use identical observations, exposure and horizon.
Conversions: loss fraction times 100 gives percent, times NAV gives USD, and
times 10,000 gives basis points. N/A remains unavailable, not zero.

{risk_table(data)}

### 7.5 Fixed-length moving-block bootstrap uncertainty

The saved policy uses block length {policy['block_length']}, {policy['n_replications']}
replications, seed {policy['seed']} and minimum {policy['min_successful_replications']}
finite replicates per reported interval. Blocks have fixed length with uniform
non-circular starting positions, concatenated and truncated to sample length.
This is a moving-block bootstrap, not the distinct stationary bootstrap. Each
resample re-estimates u under the fixed quantile policy and refits independently.
Caching is process-local; results and replicates are persisted in the authority.

Intervals are percentile summaries conditional on the threshold policy and block
dependence assumption; they omit threshold-selection uncertainty and regime shifts.
Ties can place 95% below a resample's pure-tail boundary. The pure-POT intervals
below remain N/A when too few replicates are available; hybrid intervals are
reported separately and must not be substituted under a pure-POT label.

{bootstrap_table(data)}

### 7.6 Verification and handoff

The numerical implementation was independently checked, including exact body-mass
integration, saved C1 equivalence and bootstrap-summary recomputation. Generated
document cells and conversions are checked against the authority by regression
tests. Passing software tests is not independent human economic validation.
Actual source/artifact hashes are in the preview manifest. No post-development
strategy outcomes are used. Stop before Step 8 for review.
'''


def main():
    data = load_authority()
    current = DOC.read_bytes()
    marker = SECTION_MARKER.encode()
    if marker not in current:
        raise ValueError("Section 7 marker absent; refusing to replace earlier methodology")
    prefix = current.split(marker, 1)[0]
    DOC.write_bytes(prefix + render_section(data).encode("utf-8"))
    print("Generated Section 7 from saved JSON; preceding bytes preserved.")


if __name__ == "__main__":
    main()
