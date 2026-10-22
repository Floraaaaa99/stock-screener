from __future__ import annotations

from datetime import date
from pathlib import Path

from fixtures.eight_k import GAAP_EARNINGS_EXHIBIT

from screener_pipeline.cache import read_json, write_json_atomic
from screener_pipeline.eight_k_extract import AWAITING_10Q_LABEL, SOURCE_TYPE_8K, extract_earnings_release
from screener_pipeline.eight_k_layer3 import attach_provisional


def _extract():
    return extract_earnings_release(
        GAAP_EARNINGS_EXHIBIT,
        item_202=True,
        exhibit_name="ex991.htm",
        exhibit_url="https://www.sec.gov/ex991.htm",
        filing_url="https://www.sec.gov/index.htm",
    )


def _issuer(*, include_verified_q3: bool = False) -> dict:
    q2 = {
        "fiscalYear": 2026,
        "fiscalQuarter": 2,
        "start": "2026-04-01",
        "end": "2026-06-30",
        "value": 48_000_000_000,
        "method": "reported",
        "formula": None,
        "form": "10-Q",
        "accn": "0000000001-26-000010",
        "sourceType": "company_facts",
    }
    q3 = {
        "fiscalYear": 2026,
        "fiscalQuarter": 3,
        "start": "2026-07-01",
        "end": "2026-09-30",
        "value": 51_240_000_000,
        "method": "reported",
        "formula": None,
        "form": "10-Q",
        "accn": "0000000001-26-000099",
        "sourceType": "company_facts",
    }
    quarters = [q3, q2] if include_verified_q3 else [q2]
    return {
        "cik": "0000000001",
        "displayTicker": "AAA",
        "extractionStatus": "extracted",
        "flags": [],
        "metrics": {
            "revenue": {
                "status": "extracted",
                "ttm": 190_000_000_000,
                "quarters": quarters,
                "verification": "company_facts_only",
            },
            "netIncome": {
                "status": "extracted",
                "ttm": 60_000_000_000,
                "quarters": [],
                "verification": "company_facts_only",
            },
            "ocf": {
                "status": "missing",
                "ttm": None,
                "quarters": [],
                "reason": "no_concept",
                "verification": "not_checked",
            },
            "capex": {
                "status": "missing",
                "ttm": None,
                "quarters": [],
                "reason": "no_concept",
                "verification": "not_checked",
            },
            "cash": {
                "status": "extracted",
                "value": 38_000_000_000,
                "history": [],
                "verification": "company_facts_only",
            },
        },
    }


def test_overlay_shows_available_metrics_and_leaves_others():
    payload, action = attach_provisional(
        _issuer(),
        _extract(),
        accn="0000000001-26-000024",
        form="8-K",
        filed="2026-10-21",
    )
    assert action == "attached"
    assert payload["provisionalEarnings"]["label"] == AWAITING_10Q_LABEL
    rev_q = payload["metrics"]["revenue"]["quarters"][0]
    assert rev_q["sourceType"] == SOURCE_TYPE_8K
    assert rev_q["value"] == 51_242_000_000
    assert rev_q["verification"] == "awaiting_10q"
    assert payload["metrics"]["revenue"]["quarters"][1]["value"] == 48_000_000_000
    assert payload["metrics"]["netIncome"]["quarters"][0]["value"] == 18_300_000_000
    assert payload["metrics"]["ocf"]["quarters"][0]["value"] == 25_100_000_000
    # No inventory metric existed; overlay adds it when extracted.
    assert payload["metrics"]["inventory"]["value"] == 1_200_000_000


def test_ten_q_supersedes_eight_k_and_keeps_audit():
    payload, action = attach_provisional(
        _issuer(include_verified_q3=True),
        _extract(),
        accn="0000000001-26-000024",
        form="8-K",
        filed="2026-10-21",
    )
    assert action == "superseded"
    assert payload["metrics"]["revenue"]["quarters"][0]["sourceType"] == "company_facts"
    assert payload["metrics"]["revenue"]["quarters"][0]["value"] == 51_240_000_000
    audit = payload["earningsReleaseAudit"]
    assert audit[0]["status"] == "superseded"
    assert audit[0]["differences"]["revenue"]["eightK"] == 51_242_000_000
    assert audit[0]["differences"]["revenue"]["verified"] == 51_240_000_000
    assert audit[0]["differences"]["revenue"]["difference"] == -2_000_000


def test_failed_extract_does_not_rewrite_issuer(tmp_path: Path):
    path = tmp_path / "0000000001.json"
    original = _issuer()
    write_json_atomic(path, original, compact=True)
    before = path.read_bytes()
    from screener_pipeline.eight_k_extract import EightKExtraction
    from screener_pipeline.eight_k_layer3 import apply_extractions_to_issuer

    failed = EightKExtraction(
        status="failed",
        reason="no_gaap_quarterly_metrics",
        item_202=True,
        exhibit_name="ex991.htm",
        exhibit_url=None,
        filing_url=None,
    )
    changed, actions = apply_extractions_to_issuer(
        path,
        [{"extract": failed, "accn": "x", "form": "8-K", "filed": "2026-10-21"}],
    )
    assert changed is False
    assert path.read_bytes() == before
    assert read_json(path)["metrics"]["revenue"]["ttm"] == 190_000_000_000
    assert date(2026, 9, 30).isoformat() == "2026-09-30"
    assert actions == ["unchanged"]
