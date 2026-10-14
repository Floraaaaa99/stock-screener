from __future__ import annotations

from screener_pipeline.gate import evaluate_gate


def _meta(*, mode="full", status="complete", listings=100, eligible=100, growth=80, yahoo=90):
    return {
        "dataset": {"mode": mode},
        "run": {"status": status},
        "universe": {"eligibleListings": eligible},
        "coverage": {"listings": listings, "growth": growth, "yahooProfile": yahoo},
    }


def test_complete_full_run_passes_non_publish_gate():
    r = evaluate_gate(_meta(), publish=False)
    assert r.ok
    assert r.reasons == []


def test_incomplete_and_partial_are_blocked():
    assert not evaluate_gate(_meta(status="incomplete")).ok
    assert "incomplete_run" in evaluate_gate(_meta(status="incomplete")).reasons
    assert "partial_universe" in evaluate_gate(_meta(mode="partial")).reasons
    assert "missing_listings" in evaluate_gate(_meta(listings=99, eligible=100)).reasons


def test_publish_full_is_blocked_by_yahoo_terms():
    r = evaluate_gate(_meta(), publish=True)
    assert not r.ok
    assert "yahoo_terms_block_public_full_dataset" in r.reasons


def test_coverage_drop_thresholds():
    baseline = _meta(growth=80, yahoo=90)
    ok = evaluate_gate(_meta(growth=77, yahoo=82), baseline)  # -3pt growth, -8pt yahoo
    assert ok.ok
    bad_growth = evaluate_gate(_meta(growth=70, yahoo=90), baseline)  # -10pt
    assert not bad_growth.ok
    assert any(r.startswith("growth_coverage_drop") for r in bad_growth.reasons)
    bad_yahoo = evaluate_gate(_meta(growth=80, yahoo=70), baseline)  # -20pt
    assert not bad_yahoo.ok
    assert any(r.startswith("yahoo_profile_coverage_drop") for r in bad_yahoo.reasons)


def test_first_run_without_baseline_skips_drop_checks():
    assert evaluate_gate(_meta(growth=10, yahoo=10), None).ok
