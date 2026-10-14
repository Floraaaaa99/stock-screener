"""Regression tests on trimmed real SEC Company Facts.

Expected values were verified against the income statements of the cited 10-Q/10-K filings
(see docs/validation/biotech20.md).
"""

from datetime import date

import pytest
from helpers import FIXTURES, load_fixture

from screener_pipeline.quarters import Quarter, dedupe_periods, derive_quarters
from screener_pipeline.revenue import analyze_company
from screener_pipeline.sec.statement import parse_statement_html

M = 1_000_000


def no_statements(_accn):
    return None


def srpt_statements(accn):
    if accn != "0001193125-26-335003":
        return None
    html = (FIXTURES / "statements" / f"SRPT-{accn}-R4.htm").read_text()
    return parse_statement_html(html), "https://www.sec.gov/Archives/edgar/data/873303/000119312526335003/R4.htm"


def values(rev):
    return [s.val for s in rev.slots if isinstance(s, Quarter)]


def test_vertex_twelve_quarters_and_ttm():
    rev = analyze_company(load_fixture("VRTX"), no_statements, verify_quarters=False)
    assert rev.selection.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert values(rev) == [
        3333.9 * M, 2986.9 * M, 3190.0 * M, 3076.4 * M, 2964.7 * M, 2770.2 * M,
        2912.0 * M, 2771.9 * M, 2645.6 * M, 2690.6 * M, 2517.7 * M, 2483.5 * M,
    ]
    labels = [(s.fiscal_year, s.fiscal_quarter) for s in rev.slots]
    assert labels[:3] == [(2026, 2), (2026, 1), (2025, 4)]
    assert rev.slots[2].formula == "FY − 9M YTD"
    assert rev.ttm.current == pytest.approx(12_587.2 * M)
    assert rev.ttm.previous == pytest.approx(11_418.8 * M)
    assert rev.ttm.growth_pct == pytest.approx(10.2322, abs=1e-3)
    # FY2025 quarters add up to the 10-K annual revenue of $12,001.3M.
    assert sum(values(rev)[2:6]) == pytest.approx(12_001.3 * M)


def test_alnylam_q1_derived_when_its_10q_is_missing_from_company_facts():
    rev = analyze_company(load_fixture("ALNY"), no_statements, verify_quarters=False)
    q1 = rev.slots[1]
    assert q1.end == date(2026, 3, 31)
    assert q1.val == 1_167_175_000
    assert q1.formula == "6M YTD − Q2"
    assert q1.label_inferred
    assert rev.ttm.current == 4_804_182_000
    assert rev.ttm.previous == 2_461_963_000


def test_ultragenyx_keeps_precise_values_when_later_filings_round_to_millions():
    rev = analyze_company(load_fixture("RARE"), no_statements, verify_quarters=False)
    by_end = {s.end: s for s in rev.slots}
    assert by_end[date(2025, 6, 30)].val == 166_496_000
    assert not by_end[date(2025, 6, 30)].restated
    assert by_end[date(2026, 6, 30)].val == 214 * M
    assert by_end[date(2024, 12, 31)].val == 164_877_000
    assert rev.ttm.current == 717_212_000
    assert rev.ttm.previous == 610_159_000


def test_intellia_negative_quarter_is_kept_and_flagged():
    rf = load_fixture("NTLA")
    concept = "RevenueFromContractWithCustomerExcludingAssessedTax"
    qs = derive_quarters(dedupe_periods(rf.by_concept[concept]), concept)
    q = qs[date(2023, 12, 31)]
    assert q.val == -1_917_000
    assert q.formula == "FY − 9M YTD"
    assert "negative_value" in q.flags


def test_intellia_stale_disagreeing_concept_needs_statement_resolution():
    rev = analyze_company(load_fixture("NTLA"), no_statements, verify_quarters=False)
    assert rev.status == "ambiguous"
    assert rev.ttm.reason == "ambiguous_concept"


def test_sarepta_is_ambiguous_without_statement_and_resolved_by_it():
    unresolved = analyze_company(load_fixture("SRPT"), no_statements, verify_quarters=False)
    assert unresolved.status == "ambiguous"
    assert unresolved.ttm.reason == "ambiguous_concept"
    assert unresolved.ttm.current is None

    resolved = analyze_company(load_fixture("SRPT"), srpt_statements, verify_quarters=False)
    assert resolved.selection.status == "statement_verified"
    assert resolved.selection.concept == "Revenues"
    assert resolved.statement_check["status"] == "verified"
    assert values(resolved)[0] == 401_251_000
    assert resolved.ttm.current == 1_974_344_000
    assert resolved.ttm.previous == 2_481_531_000
