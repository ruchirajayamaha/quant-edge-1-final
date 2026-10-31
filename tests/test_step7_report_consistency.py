"""Report/export regressions on persisted results; no refits or bootstrap reruns."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("step7_report", ROOT / "scripts/generate_step7_methodology.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def _data():
    return report.load_authority()


def _rows(section, next_heading):
    text = (ROOT / "docs/sections/c_var_es_and_evt.md").read_text(encoding="utf-8")
    chunk = text.split(section, 1)[1].split(next_heading, 1)[0]
    lines = [line for line in chunk.splitlines() if line.startswith("| ")]
    return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[2:]]


def _formatted(actual, value, multiplier, digits):
    if value is None:
        assert actual == "N/A"
    else:
        assert float(actual) == pytest.approx(value * multiplier, abs=0.500001 * 10**(-digits))


def test_all_generated_model_cells_have_correct_units_status_and_nulls():
    data = _data()
    rows = _rows("### 7.4 Matched model comparison", "### 7.5")
    assert len(rows) == 30
    by_key = {(r[0], r[1], float(r[2])): r for r in rows}
    nav = data["metadata"]["nav_usd"]
    for win, run in data["runs"].items():
        normals = {r["confidence"]: r for r in run["model_comparison"] if r["model"] == "parametric_normal"}
        for source in run["model_comparison"]:
            row = by_key[win, source["model"], source["confidence"]]
            v, e = source["var_loss"], source["es_loss"]
            for cell, value, factor, digits in ((3, v, 100, 4), (4, v, nav, 2), (5, e, 100, 4), (6, e, nav, 2)):
                _formatted(row[cell], value, factor, digits)
            n = normals[source["confidence"]]
            for cell, value in ((7, None if e is None else e-v),
                                (8, None if v is None else v-n["var_loss"]),
                                (9, None if e is None else e-n["es_loss"])):
                _formatted(row[cell], value, 10000, 4)
            assert row[10] == source["status"]
            assert row[11] == (source.get("region") or "N/A")
            assert row[12] == (source.get("reason") or "N/A")


def test_every_bootstrap_median_interval_count_and_unavailable_state_matches():
    data = _data()
    rows = _rows("### 7.5 Fixed-length", "### 7.6")
    assert len(rows) == 10
    by_key = {(r[0], float(r[1]), r[2]): r for r in rows}
    for win, run in data["runs"].items():
        boot = run["bootstrap"]
        total = boot["cache_key"]["n_replications"]
        required = boot["cache_key"]["min_successful_replications"]
        for source in boot["summary"]["by_confidence"].values():
            variants = [(source["method"], source)]
            if source["method"] != "body_tail_hybrid":
                variants.append(("body_tail_hybrid", source["body_tail_hybrid"]))
            for name, s in variants:
                row = by_key[win, source["confidence"], name]
                assert row[3] == f"{s['n_var_available']}/{total}"
                assert row[4] == f"{s['n_es_finite']}/{total}"
                assert int(row[5]) == required
                assert int(row[6]) == s["n_es_unavailable_infinite_xi_ge_1"]
                for metric, median_col, ci_col, status_col in (("var", 7, 8, 9), ("es", 10, 11, 12)):
                    ref = s[metric]
                    assert row[status_col] == ref["interval_status"]
                    _formatted(row[median_col], ref["median"], 100, 4)
                    if ref["n_finite"] < required:
                        assert row[ci_col] == "N/A" and ref["p025"] is None and ref["p975"] is None
                    else:
                        low, high = map(float, row[ci_col].strip("[]").split(","))
                        assert low == pytest.approx(ref["p025"] * 100, abs=0.000050001)
                        assert high == pytest.approx(ref["p975"] * 100, abs=0.000050001)


def test_threshold_cells_and_document_regeneration_are_consistent():
    data = _data()
    rows = _rows("### 7.3 Threshold diagnostics", "### 7.4")
    by_key = {(r[0], float(r[1])): r for r in rows}
    assert len(rows) == 16
    for win, run in data["runs"].items():
        for d in run["threshold_diagnostics_dense"]:
            row = by_key[win, d["candidate_quantile"]]
            assert int(row[3]) == d["n_exceedances"] and int(row[4]) == d["n_ties_at_threshold"]
            for col, name, factor in ((2, "threshold", 100), (5, "mean_excess", 100), (6, "xi", 1),
                                      (7, "xi_se_asymptotic_iid", 1), (8, "beta", 100), (9, "modified_scale", 100)):
                _formatted(row[col], d[name], factor, 4)
            assert row[10] == d["status"] and row[11] == (d.get("reason") or "N/A")
    text = (ROOT / "docs/sections/c_var_es_and_evt.md").read_text(encoding="utf-8")
    assert text[text.index(report.SECTION_MARKER):] == report.render_section(data)


def test_manifest_provenance_authority_and_protected_results():
    preview = ROOT / "results/step7_evt_preview"
    manifest = json.loads((preview / "manifest.json").read_text(encoding="utf-8"))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert manifest["numerical_authority_sha256"] == sha(ROOT / manifest["numerical_authority_json"])
    for name, digest in manifest["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    for name, digest in manifest["artifacts_sha256"].items():
        assert sha(preview / name) == digest, name
    baseline = json.loads((ROOT / "audit/step7_review/STEP7_FIX_BASELINE.json").read_text(encoding="utf-8"))
    for name, digest in baseline["protected_sha256"].items():
        assert sha(ROOT / name) == digest, name
    prefix = (ROOT / "docs/sections/c_var_es_and_evt.md").read_bytes().split(report.SECTION_MARKER.encode(), 1)[0]
    assert hashlib.sha256(prefix).hexdigest() == baseline["sections_1_6_sha256"]
