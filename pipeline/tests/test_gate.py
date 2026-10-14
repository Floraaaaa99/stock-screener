from __future__ import annotations

from screener_pipeline.gate import evaluate_gate


def _meta(*, mode="full", status="complete", listings=100, eligible=100, growth=80, mismatches=0, checks=200):
    return {
        "dataset": {"mode": mode},
        "run": {"status": status},
        "universe": {"eligibleListings": eligible},
        "coverage": {
            "listings": listings,
            "growth": growth,
            "currentTtm": growth,
            "quarterChecks": {"match": checks - mismatches, "mismatch": mismatches},
        },
    }


def test_complete_full_run_passes_non_publish_gate():
    r = evaluate_gate(_meta(), publish=False)
    assert r.ok
    assert r.reasons == []


def test_incomplete_and_partial_are_blocked():
    assert "incomplete_run" in evaluate_gate(_meta(status="incomplete")).reasons
    assert "partial_universe" in evaluate_gate(_meta(mode="partial")).reasons
    assert "missing_listings" in evaluate_gate(_meta(listings=99, eligible=100)).reasons


def test_publish_requires_full_universe():
    r = evaluate_gate(_meta(mode="sample"), publish=True)
    assert not r.ok
    assert "publish_requires_full_universe" in r.reasons
    assert evaluate_gate(_meta(), publish=True).ok


def test_quarter_mismatch_ratio_blocks():
    bad = evaluate_gate(_meta(mismatches=30, checks=200))  # 15%
    assert not bad.ok
    assert any(r.startswith("quarter_mismatch_ratio") for r in bad.reasons)
    ok = evaluate_gate(_meta(mismatches=10, checks=200))  # 5%
    assert ok.ok


def test_coverage_drop_thresholds():
    baseline = _meta(growth=80)
    assert evaluate_gate(_meta(growth=77), baseline).ok
    bad = evaluate_gate(_meta(growth=70), baseline)
    assert not bad.ok
    assert any(r.startswith("growth_coverage_drop") for r in bad.reasons)


def test_first_run_without_baseline_skips_drop_checks():
    assert evaluate_gate(_meta(growth=10), None).ok
