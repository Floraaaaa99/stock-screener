"""Mismatched or unverified TTM-window quarters never contribute to TTM figures."""

from datetime import date

from helpers import calendar_year, filings_for

from screener_pipeline.quarters import Quarter
from screener_pipeline.revenue import (
    QuarterCheck,
    analyze_company,
    ttm_window_block_reason,
)
from screener_pipeline.sec.facts import RevenueFacts, extract_revenue_facts


def _rf():
    facts = calendar_year(2024, 10, 20, 30, 40) + calendar_year(2025, 11, 21, 31, 41)
    return RevenueFacts(
        cik="0000000001",
        entity_name="Test",
        currency="USD",
        by_concept={"Revenues": facts},
        filings=filings_for(facts),
        forms_seen={"10-Q", "10-K"},
    )


def test_unverified_quarters_block_all_ttm_values_but_keep_the_company():
    rev = analyze_company(_rf(), lambda accn: None, verify_quarters=True)
    assert rev.status == "ok"
    assert [s.end for s in rev.slots if isinstance(s, Quarter)]
    assert rev.ttm.current is None
    assert rev.ttm.previous is None
    assert rev.ttm.growth_pct is None
    assert rev.ttm.reason == "unverified_quarters"
    assert "unverified_quarters" in rev.flags
    assert any(c.status == "unavailable" for c in rev.quarter_checks.values())


def test_verify_off_still_computes_ttm_from_facts():
    rev = analyze_company(_rf(), lambda accn: None, verify_quarters=False)
    assert rev.ttm.growth_pct is not None
    assert rev.ttm.reason is None


def test_mismatch_in_window_blocks_ttm():
    q = Quarter(
        date(2026, 4, 1), date(2026, 6, 30), 100, "reported", "3M reported", [], "Revenues"
    )
    checks = {q.end: QuarterCheck("mismatch", accn="x", form="10-Q")}
    assert ttm_window_block_reason([q] * 8, checks, "verified", verify_quarters=True) == "filing_mismatch"


def test_unavailable_in_window_blocks_ttm():
    q = Quarter(
        date(2026, 4, 1), date(2026, 6, 30), 100, "reported", "3M reported", [], "Revenues"
    )
    checks = {q.end: QuarterCheck("unavailable", accn="x", form="10-Q")}
    assert ttm_window_block_reason([q] * 8, checks, "verified", verify_quarters=True) == "unverified_quarters"


def test_matched_window_does_not_block():
    q = Quarter(
        date(2026, 4, 1), date(2026, 6, 30), 100, "reported", "3M reported", [], "Revenues"
    )
    checks = {q.end: QuarterCheck("match", accn="x", form="10-Q")}
    assert ttm_window_block_reason([q] * 8, checks, "verified", verify_quarters=True) is None


def test_f10_only_company_facts_are_foreign_filer():
    facts = {
        "cik": 1857047,
        "entityName": "MDA Space Ltd.",
        "facts": {
            "ffd": {
                "TtlOfferingAmt": {
                    "units": {
                        "USD": [
                            {
                                "end": "2026-07-07",
                                "val": 1,
                                "accn": "0001104659-26-081788",
                                "form": "F-10",
                                "filed": "2026-07-08",
                            }
                        ]
                    }
                }
            }
        },
    }
    rf = extract_revenue_facts(facts)
    assert rf.is_foreign_filer
    rev = analyze_company(rf, lambda _accn: None, verify_quarters=False)
    assert rev.status == "foreign_filer"
    assert rev.ttm.reason == "foreign_filer"
