"""GAAP net-income concept scope: consolidated vs attributable to parent/common."""

from datetime import date

from helpers import calendar_year, fact, filings_for, quarters_from

from screener_pipeline.concepts import ConceptSeries, prefer_attributable_net_income, select_concept
from screener_pipeline.quarters import Quarter, dedupe_periods
from screener_pipeline.revenue import EARNINGS_SPEC, analyze_company
from screener_pipeline.sec.facts import RevenueFacts
from screener_pipeline.sec.statement import (
    Statement,
    StatementColumn,
    StatementRow,
    evidence_from_statement,
)

M = 1_000_000


def earnings_series(concept, facts):
    return ConceptSeries(concept, dedupe_periods(facts), quarters_from(facts, concept))


def pltr_like_statement():
    """Palantir Q2 2026 10-Q face: consolidated NI and attributable-to-common both reported."""
    return Statement(
        title="Condensed Consolidated Statements of Operations",
        scale=1000.0,
        columns=[StatementColumn(3, date(2026, 6, 30))],
        rows=[
            StatementRow("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "Revenue", [1_935_464_000.0]),
            StatementRow("us-gaap:ProfitLoss", "Net income", [1_065_962_000.0]),
            StatementRow(
                "us-gaap:NetIncomeLossAttributableToNoncontrollingInterest",
                "Less: Net income attributable to noncontrolling interests",
                [4_072_000.0],
            ),
            StatementRow(
                "us-gaap:NetIncomeLoss",
                "Net income attributable to common stockholders",
                [1_061_890_000.0],
            ),
        ],
    )


def pltr_like_facts():
    """Eight standalone quarters; ProfitLoss is ~NCI higher than NetIncomeLoss."""
    common = [
        fact("2024-07-01", "2024-09-30", 143_503_000, "p-old", 2024, "Q3", filed="2024-11-04"),
        fact("2024-10-01", "2024-12-31", 79_009_000, "p-k", 2024, "FY", form="10-K", filed="2025-02-18"),
        fact("2025-01-01", "2025-03-31", 214_031_000, "p-q1", 2025, "Q1", filed="2025-05-05"),
        fact("2025-04-01", "2025-06-30", 326_727_000, "p-q2", 2025, "Q2", filed="2025-08-04"),
        fact("2025-07-01", "2025-09-30", 475_599_000, "p-q3", 2025, "Q3", filed="2025-11-03"),
        fact("2025-10-01", "2025-12-31", 608_676_000, "p-k2", 2025, "FY", form="10-K", filed="2026-02-17"),
        fact("2026-01-01", "2026-03-31", 870_527_000, "p-26q1", 2026, "Q1", filed="2026-05-05"),
        fact("2026-04-01", "2026-06-30", 1_061_890_000, "p-26q2", 2026, "Q2", filed="2026-08-04"),
    ]
    nci = [4_000_000, 3_000_000, 3_686_000, 1_845_000, 1_149_000, 2_931_000, 5_875_000, 4_072_000]
    consol = [
        fact(
            f.start.isoformat(),
            f.end.isoformat(),
            f.val + extra,
            f.accn,
            f.fy,
            f.fp,
            form=f.form,
            filed=f.filed.isoformat(),
        )
        for f, extra in zip(common, nci, strict=True)
    ]
    # FY totals so Q4 can be derived if a 3M Q4 fact were missing (kept as reported 3M here).
    common.append(fact("2025-01-01", "2025-12-31", 1_625_033_000, "p-k2", 2025, "FY", form="10-K", filed="2026-02-17"))
    common.append(fact("2025-01-01", "2025-09-30", 1_016_357_000, "p-q3", 2025, "Q3", filed="2025-11-03"))
    return RevenueFacts(
        cik="0001321655",
        entity_name="Palantir Technologies Inc.",
        currency="USD",
        by_concept={"NetIncomeLoss": common, "ProfitLoss": consol},
        filings=filings_for(common),
        forms_seen={"10-Q", "10-K"},
    )


def test_evidence_includes_net_income_rows():
    ev = evidence_from_statement(pltr_like_statement(), "acc", "10-Q", "http://x", 3, date(2026, 6, 30))
    labels = {r[1] for r in ev.rows}
    assert "Revenue" in labels
    assert "Net income" in labels
    assert "Net income attributable to common stockholders" in labels
    assert ev.concept_rows("NetIncomeLoss")[0][2] == 1_061_890_000.0
    assert ev.concept_rows("ProfitLoss")[0][2] == 1_065_962_000.0


def test_prefer_attributable_over_consolidated():
    nil = earnings_series("NetIncomeLoss", calendar_year(2025, 10 * M, 20 * M, 30 * M, 40 * M))
    pl = earnings_series("ProfitLoss", calendar_year(2025, 11 * M, 21 * M, 31 * M, 41 * M, prefix="B"))
    picked = prefer_attributable_net_income(
        [
            (pl, ("us-gaap:ProfitLoss", "Net income", 41 * M)),
            (nil, ("us-gaap:NetIncomeLoss", "Net income attributable to common stockholders", 40 * M)),
        ]
    )
    assert picked is not None
    assert picked.concept == "NetIncomeLoss"


def test_statement_resolves_pltr_like_disagreement_to_common():
    nil = earnings_series(
        "NetIncomeLoss",
        calendar_year(2024, 100 * M, 110 * M, 120 * M, 130 * M)
        + calendar_year(2025, 140 * M, 150 * M, 160 * M, 170 * M),
    )
    pl = earnings_series(
        "ProfitLoss",
        calendar_year(2024, 101 * M, 111 * M, 121 * M, 131 * M, prefix="B")
        + calendar_year(2025, 141 * M, 151 * M, 161 * M, 171 * M, prefix="B"),
    )
    ev = evidence_from_statement(pltr_like_statement(), "acc", "10-Q", "http://x", 3, date(2026, 6, 30))
    # Evidence period is 2026-06-30; calendar_year latest is 2025-12-31. Build ev for 2025-12-31.
    ev = type(ev)(ev.accn, ev.form, ev.url, ev.title, 3, date(2025, 12, 31), ev.rows)
    sel = select_concept(
        [nil, pl],
        ev,
        is_face_line=EARNINGS_SPEC.is_face_line,
        concepts=EARNINGS_SPEC.concepts,
        line_name=EARNINGS_SPEC.line_name,
        prefer_face=EARNINGS_SPEC.prefer_face,
    )
    assert sel.status == "statement_verified"
    assert sel.concept == "NetIncomeLoss"
    assert sel.quarters  # series kept; not wiped as ambiguous


def test_analyze_pltr_like_uses_attributable_common_and_keeps_q4():
    rf = pltr_like_facts()
    st = pltr_like_statement()

    def fetch(accn):
        if accn == "p-26q2":
            return st, "https://www.sec.gov/Archives/edgar/data/1321655/000132165526000041/R4.htm"
        return None

    earn = analyze_company(rf, fetch, spec=EARNINGS_SPEC, verify_quarters=True)
    assert earn.status != "ambiguous"
    assert earn.selection.concept == "NetIncomeLoss"
    by_end = {s.end: s for s in earn.slots if isinstance(s, Quarter)}
    assert by_end[date(2025, 9, 30)].val == 475_599_000
    assert by_end[date(2025, 12, 31)].val == 608_676_000
    assert by_end[date(2026, 3, 31)].val == 870_527_000
    assert by_end[date(2026, 6, 30)].val == 1_061_890_000
    assert by_end[date(2025, 12, 31)].formula in {"3M reported", "FY − 9M YTD"}
    assert earn.statement_check["status"] in {"verified", "verified_value"}


def test_q4_derived_from_verified_annual_and_nine_month():
    q1 = fact("2025-01-01", "2025-03-31", 214_031_000, "q1", 2025, "Q1", filed="2025-05-05")
    q2 = fact("2025-04-01", "2025-06-30", 326_727_000, "q2", 2025, "Q2", filed="2025-08-04")
    q3 = fact("2025-07-01", "2025-09-30", 475_599_000, "q3", 2025, "Q3", filed="2025-11-03")
    ytd9 = fact("2025-01-01", "2025-09-30", 1_016_357_000, "q3", 2025, "Q3", filed="2025-11-03")
    fy = fact("2025-01-01", "2025-12-31", 1_625_033_000, "k", 2025, "FY", form="10-K", filed="2026-02-17")
    # Prior year so the 12-quarter window has history
    prior = calendar_year(2024, 80_000_000, 90_000_000, 100_000_000, 110_000_000, prefix="O")
    latest = [
        fact("2026-01-01", "2026-03-31", 870_527_000, "nq1", 2026, "Q1", filed="2026-05-05"),
        fact("2026-04-01", "2026-06-30", 1_061_890_000, "nq2", 2026, "Q2", filed="2026-08-04"),
    ]
    rf = RevenueFacts(
        cik="1",
        entity_name="T",
        currency="USD",
        by_concept={"NetIncomeLoss": prior + [q1, q2, q3, ytd9, fy, *latest]},
        filings=filings_for(prior + [q1, q2, q3, fy, *latest]),
        forms_seen={"10-Q", "10-K"},
    )
    earn = analyze_company(rf, lambda _a: None, spec=EARNINGS_SPEC, verify_quarters=False)
    by_end = {s.end: s for s in earn.slots if isinstance(s, Quarter)}
    q4 = by_end[date(2025, 12, 31)]
    assert q4.val == 608_676_000
    assert q4.formula == "FY − 9M YTD"


def test_available_to_common_wins_over_consolidated_face_line():
    nil = earnings_series(
        "NetIncomeLoss",
        calendar_year(2024, 100 * M, 110 * M, 120 * M, 130 * M)
        + calendar_year(2025, 140 * M, 150 * M, 160 * M, 170 * M),
    )
    pl = earnings_series(
        "ProfitLoss",
        calendar_year(2024, 101 * M, 111 * M, 121 * M, 131 * M, prefix="B")
        + calendar_year(2025, 141 * M, 151 * M, 161 * M, 171 * M, prefix="B"),
    )
    st = Statement(
        title="Ops",
        scale=1,
        columns=[StatementColumn(3, date(2025, 12, 31))],
        rows=[
            StatementRow("us-gaap:ProfitLoss", "Net Loss", [171 * M]),
            StatementRow("us-gaap:NetIncomeLoss", "Net Loss Available to Common Shareholders", [170 * M]),
        ],
    )
    ev = evidence_from_statement(st, "acc", "10-K", "http://x", 3, date(2025, 12, 31))
    sel = select_concept(
        [nil, pl],
        ev,
        is_face_line=EARNINGS_SPEC.is_face_line,
        concepts=EARNINGS_SPEC.concepts,
        line_name=EARNINGS_SPEC.line_name,
        prefer_face=EARNINGS_SPEC.prefer_face,
    )
    assert sel.concept == "NetIncomeLoss"


def test_face_line_may_be_a_third_candidate_not_in_the_first_conflict():
    nil = earnings_series(
        "NetIncomeLoss",
        calendar_year(2024, 100 * M, 110 * M, 120 * M, 130 * M)
        + calendar_year(2025, 140 * M, 150 * M, 160 * M, 170 * M),
    )
    pl = earnings_series(
        "ProfitLoss",
        calendar_year(2024, 101 * M, 111 * M, 121 * M, 131 * M, prefix="B")
        + calendar_year(2025, 141 * M, 151 * M, 161 * M, 171 * M, prefix="B"),
    )
    common = earnings_series(
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        calendar_year(2024, 90 * M, 100 * M, 110 * M, 120 * M, prefix="C")
        + calendar_year(2025, 130 * M, 140 * M, 150 * M, 160 * M, prefix="C"),
    )
    st = Statement(
        title="Ops",
        scale=1,
        columns=[StatementColumn(3, date(2025, 12, 31))],
        rows=[StatementRow("us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic", "NET INCOME", [160 * M])],
    )
    ev = evidence_from_statement(st, "acc", "10-K", "http://x", 3, date(2025, 12, 31))
    sel = select_concept(
        [nil, pl, common],
        ev,
        is_face_line=EARNINGS_SPEC.is_face_line,
        concepts=EARNINGS_SPEC.concepts,
        line_name=EARNINGS_SPEC.line_name,
        prefer_face=EARNINGS_SPEC.prefer_face,
    )
    assert sel.concept == "NetIncomeLossAvailableToCommonStockholdersBasic"


def test_only_consolidated_face_line_is_used_when_that_is_all_the_statement_shows():
    nil = earnings_series(
        "NetIncomeLoss",
        calendar_year(2024, 100 * M, 110 * M, 120 * M, 130 * M)
        + calendar_year(2025, 140 * M, 150 * M, 160 * M, 170 * M),
    )
    pl = earnings_series(
        "ProfitLoss",
        calendar_year(2024, 101 * M, 111 * M, 121 * M, 131 * M, prefix="B")
        + calendar_year(2025, 141 * M, 151 * M, 161 * M, 171 * M, prefix="B"),
    )
    st = Statement(
        title="Ops",
        scale=1,
        columns=[StatementColumn(3, date(2025, 12, 31))],
        rows=[StatementRow("us-gaap:ProfitLoss", "Net income", [171 * M])],
    )
    ev = evidence_from_statement(st, "acc", "10-K", "http://x", 3, date(2025, 12, 31))
    sel = select_concept(
        [nil, pl],
        ev,
        is_face_line=EARNINGS_SPEC.is_face_line,
        concepts=EARNINGS_SPEC.concepts,
        line_name=EARNINGS_SPEC.line_name,
        prefer_face=EARNINGS_SPEC.prefer_face,
    )
    assert sel.concept == "ProfitLoss"


def test_revenue_disagreement_is_unchanged_without_a_total_line():
    a = earnings_series("Revenues", calendar_year(2025, 10 * M, 11 * M, 12 * M, 13 * M, prefix="A"))
    b = earnings_series(
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        calendar_year(2025, 20 * M, 21 * M, 22 * M, 23 * M, prefix="B"),
    )
    sel = select_concept([a, b])
    assert sel.status == "ambiguous"
    assert sel.concept is None
