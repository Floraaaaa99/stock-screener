"""Mismatched or unverified TTM-window quarters never contribute to TTM figures."""

from datetime import date

from helpers import calendar_year, filings_for

from screener_pipeline.quarters import Quarter
from screener_pipeline.revenue import (
    QuarterCheck,
    analyze_company,
    ttm_window_block_reason,
)
from screener_pipeline.sec.facts import Fact, RevenueFacts


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
    q = Quarter(date(2026, 4, 1), date(2026, 6, 30), 100, "reported", "3M reported", [], "Revenues")
    checks = {q.end: QuarterCheck("mismatch", accn="x", form="10-Q")}
    assert ttm_window_block_reason([q] * 8, checks, "verified", verify_quarters=True) == "filing_mismatch"


def test_unavailable_in_window_blocks_ttm():
    q = Quarter(date(2026, 4, 1), date(2026, 6, 30), 100, "reported", "3M reported", [], "Revenues")
    checks = {q.end: QuarterCheck("unavailable", accn="x", form="10-Q")}
    assert ttm_window_block_reason([q] * 8, checks, "verified", verify_quarters=True) == "unverified_quarters"


def test_matched_window_does_not_block():
    q = Quarter(date(2026, 4, 1), date(2026, 6, 30), 100, "reported", "3M reported", [], "Revenues")
    checks = {q.end: QuarterCheck("match", accn="x", form="10-Q")}
    assert ttm_window_block_reason([q] * 8, checks, "verified", verify_quarters=True) is None


def test_eight_k_awaiting_10q_does_not_block_ttm():
    from screener_pipeline.quarters import Source

    src = Source(
        accn="8k",
        form="8-K",
        filed=date(2026, 10, 21),
        start=date(2026, 7, 1),
        end=date(2026, 9, 30),
        val=100,
        role="reported",
    )
    q = Quarter(date(2026, 7, 1), date(2026, 9, 30), 100, "reported", "3M reported", [src], "Revenues")
    checks = {q.end: QuarterCheck("awaiting_10q", accn="8k", form="8-K")}
    assert ttm_window_block_reason([q] * 8, checks, "verified", verify_quarters=True) is None


def test_analyze_company_skips_face_statement_for_eight_k():
    def eight_k_year(fy: int, q1: float, q2: float, q3: float, q4: float) -> list[Fact]:
        return [
            Fact(date(fy, 1, 1), date(fy, 3, 31), q1, f"{fy}q1", fy, "Q1", "8-K", date(fy, 4, 21)),
            Fact(date(fy, 4, 1), date(fy, 6, 30), q2, f"{fy}q2", fy, "Q2", "8-K", date(fy, 7, 21)),
            Fact(date(fy, 7, 1), date(fy, 9, 30), q3, f"{fy}q3", fy, "Q3", "8-K", date(fy, 10, 21)),
            Fact(date(fy, 10, 1), date(fy, 12, 31), q4, f"{fy}q4", fy, "FY", "8-K", date(fy + 1, 1, 21)),
        ]

    facts = eight_k_year(2024, 10, 20, 30, 40) + eight_k_year(2025, 11, 21, 31, 41)
    rf = RevenueFacts(
        cik="0000000001",
        entity_name="Test",
        currency="USD",
        by_concept={"Revenues": facts},
        filings=filings_for(facts),
        forms_seen={"8-K"},
    )
    rev = analyze_company(rf, lambda accn: None, verify_quarters=True)
    assert rev.ttm.current == 11 + 21 + 31 + 41
    assert rev.ttm.reason is None
    assert all(c.status == "awaiting_10q" for c in rev.quarter_checks.values())
