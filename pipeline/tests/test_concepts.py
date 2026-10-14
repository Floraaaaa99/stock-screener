from datetime import date

from helpers import calendar_year, fact, quarters_from

from screener_pipeline.concepts import ConceptSeries, select_concept, verify_against_statement
from screener_pipeline.quarters import dedupe_periods
from screener_pipeline.sec.statement import StatementEvidence


def series(concept, facts):
    return ConceptSeries(concept, dedupe_periods(facts), quarters_from(facts, concept))


M = 1_000_000


def two_years(scale=1.0, prefix="A"):
    """Two fiscal years of quarterly revenue, in millions of dollars."""
    s = scale * M
    return calendar_year(2024, 100 * s, 110 * s, 120 * s, 130 * s, prefix=prefix) + calendar_year(
        2025, 140 * s, 150 * s, 160 * s, 170 * s, prefix=prefix
    )


def evidence(rows, months=3, end=date(2025, 12, 31)):
    """Statement rows with values given in millions."""
    scaled = [(c, label, v * M if v is not None else None) for c, label, v in rows]
    return StatementEvidence("acc", "10-K", "http://x", "Statement", months, end, scaled)


def test_single_concept_is_selected():
    sel = select_concept([series("Revenues", two_years())])
    assert sel.status == "single"
    assert sel.concept == "Revenues"


def test_equivalent_concepts_use_best_coverage_and_priority():
    a = series("Revenues", two_years())
    b = series("RevenueFromContractWithCustomerExcludingAssessedTax", two_years(prefix="B"))
    sel = select_concept([b, a])
    assert sel.status == "equivalent"
    assert sel.concept == "Revenues"


def test_disagreeing_concepts_are_ambiguous_and_larger_value_is_not_chosen():
    total = series("Revenues", two_years(scale=1.5))
    product = series("RevenueFromContractWithCustomerExcludingAssessedTax", two_years(prefix="B"))
    sel = select_concept([total, product])
    assert sel.status == "ambiguous"
    assert sel.concept is None
    assert "ambiguous_concept" in sel.flags
    assert {c["concept"] for c in sel.candidates} == {total.concept, product.concept}


def test_income_statement_total_line_resolves_disagreement():
    total = series("Revenues", two_years(scale=1.5))
    product = series("RevenueFromContractWithCustomerExcludingAssessedTax", two_years(prefix="B"))
    ev = evidence([
        ("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "Net product revenues", 170.0),
        ("us-gaap:Revenues", "Total revenues", 255.0),
    ])
    sel = select_concept([total, product], ev)
    assert sel.status == "statement_verified"
    assert sel.concept == "Revenues"
    assert "other_concept_disagrees" in sel.flags


def test_statement_resolution_picks_the_smaller_concept_when_it_is_the_total_line():
    big = series("Revenues", two_years(scale=1.5))
    total = series("RevenueFromContractWithCustomerExcludingAssessedTax", two_years(prefix="B"))
    ev = evidence([("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "Total revenues", 170.0)])
    sel = select_concept([big, total], ev)
    assert sel.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_component_line_with_separate_custom_total_is_not_accepted():
    a = series("Revenues", two_years(scale=1.5))
    b = series("RevenueFromContractWithCustomerExcludingAssessedTax", two_years(prefix="B"))
    ev = evidence([
        ("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "Product revenue, net", 170.0),
        ("abc:TotalRevenuesAndOtherIncome", "Total revenues", 300.0),
    ])
    assert select_concept([a, b], ev).status == "ambiguous"


def test_override_wins():
    a = series("Revenues", two_years(scale=1.5))
    b = series("RevenueFromContractWithCustomerExcludingAssessedTax", two_years(prefix="B"))
    sel = select_concept([a, b], override="RevenueFromContractWithCustomerExcludingAssessedTax")
    assert sel.status == "override"
    assert sel.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_concept_switch_is_merged_when_overlap_verifies_it():
    old = calendar_year(2024, 100, 110, 120, 130, prefix="O")
    new = [f for f in calendar_year(2025, 140, 150, 160, 170, prefix="N")]
    # The 2025 filings re-tag 2024 comparatives with the new concept (same values).
    new += [fact("2024-10-01", "2024-12-31", 130, "N2025-K", 2025, "FY", form="10-K", filed="2026-02-15")]
    sel = select_concept([series("SalesRevenueNet", old),
                          series("RevenueFromContractWithCustomerExcludingAssessedTax", new)])
    assert sel.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert "concept_merged" in sel.flags
    assert len(sel.quarters) == 8


def test_concept_switch_without_overlap_is_not_merged():
    old = calendar_year(2024, 100, 110, 120, 130, prefix="O")
    new = calendar_year(2025, 140, 150, 160, 170, prefix="N")
    sel = select_concept([series("SalesRevenueNet", old),
                          series("RevenueFromContractWithCustomerExcludingAssessedTax", new)])
    assert "concept_change_unverified" in sel.flags
    assert len(sel.quarters) == 4


def test_verify_against_statement_statuses():
    s = series("Revenues", two_years())
    sel = select_concept([s])
    by_name = {"Revenues": s}
    ok = evidence([("us-gaap:Revenues", "Total revenues", 170.0)])
    assert verify_against_statement(sel, by_name, ok)[0] == "verified"
    other_tag = evidence([("abc:Total", "Total revenues", 170.0)])
    assert verify_against_statement(sel, by_name, other_tag)[0] == "verified_value"
    wrong = evidence([("us-gaap:Revenues", "Total revenues", 171.0)])
    assert verify_against_statement(sel, by_name, wrong)[0] == "mismatch"
    annual = evidence([("us-gaap:Revenues", "Total revenues", 620.0)], months=12)
    assert verify_against_statement(sel, by_name, annual)[0] == "verified"
    assert verify_against_statement(sel, by_name, None)[0] == "unavailable"
