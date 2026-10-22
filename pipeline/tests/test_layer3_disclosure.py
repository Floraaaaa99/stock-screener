"""v1 SEC cash-flow face disclosure. Research metrics stay one-tag and unchanged."""

from __future__ import annotations

from datetime import date

from helpers import FIXTURES
from test_layer3_capital_allocation import _cf_core

from screener_pipeline.layer3_disclosure import build_cash_flow_disclosure, line_identity, note_source_links
from screener_pipeline.layer3_extract import analyze_layer3_facts
from screener_pipeline.sec.statement import (
    Statement,
    StatementColumn,
    StatementRow,
    has_cash_flow_line,
    parse_statement_html,
)

MOG_Q3 = FIXTURES / "statements" / "MOG-0001628280-26-051294-R6.htm"
MOG_Q2 = FIXTURES / "statements" / "MOG-0001628280-26-027064-R6.htm"
MOG_SUMMARY = FIXTURES / "statements" / "MOG-0001628280-26-051294-FilingSummary.xml"


def _mog_disclosure():
    q3 = parse_statement_html(MOG_Q3.read_text())
    q2 = parse_statement_html(MOG_Q2.read_text())
    notes = note_source_links(MOG_SUMMARY.read_text(), "0000067887", "0001628280-26-051294")
    return build_cash_flow_disclosure(
        q3,
        cik="0000067887",
        accn="0001628280-26-051294",
        form="10-Q",
        filed="2026-07-31",
        html_name="R6.htm",
        prior_statement=q2,
        prior_accn="0001628280-26-027064",
        note_links=notes,
    )


def _lines(disc: dict, group: str) -> list[dict]:
    for g in disc["groups"]:
        if g["id"] == group:
            return g["lines"]
    return []


def _line(disc: dict, concept: str) -> dict:
    for g in disc["groups"]:
        for line in g["lines"]:
            if line["concept"] == concept:
                return line
    raise AssertionError(f"missing {concept}")


def test_mog_face_keeps_revolver_notes_and_custom_sect_lines():
    q3 = parse_statement_html(MOG_Q3.read_text())
    assert has_cash_flow_line(q3)
    disc = _mog_disclosure()
    assert disc["source"] == "sec_cash_flow_face"
    assert disc["period"]["months"] == 9
    assert disc["period"]["end"] == "2026-06-27"
    assert disc["notesParsed"] is False
    assert disc["filing"]["accn"] == "0001628280-26-051294"
    assert disc["filing"]["statementUrl"].endswith("/R6.htm")

    revolver_in = _line(disc, "us-gaap:ProceedsFromLongTermLinesOfCredit")
    assert revolver_in["label"] == "Proceeds from revolving lines of credit"
    assert revolver_in["identity"] == "debtFinancing"
    assert revolver_in["asReported"]["kind"] == "asReported"
    assert revolver_in["asReported"]["value"] == 1_348_400_000
    assert revolver_in["standaloneQuarter"]["kind"] == "calculated"
    assert revolver_in["standaloneQuarter"]["value"] == 479_000_000
    assert revolver_in["standaloneQuarter"]["formula"] == "9M YTD − 6M YTD"

    revolver_out = _line(disc, "us-gaap:RepaymentsOfLongTermLinesOfCredit")
    assert revolver_out["asReported"]["value"] == -1_375_400_000
    assert revolver_out["standaloneQuarter"]["value"] == -311_000_000

    notes_in = _line(disc, "us-gaap:ProceedsFromIssuanceOfSeniorLongTermDebt")
    assert notes_in["label"] == "Proceeds from senior notes, net of issuance costs"
    assert notes_in["asReported"]["value"] == 491_443_000
    assert notes_in["standaloneQuarter"]["kind"] == "calculated"
    assert notes_in["standaloneQuarter"]["value"] == -778_000

    notes_out = _line(disc, "us-gaap:RepaymentsOfSeniorDebt")
    assert notes_out["label"] == "Payments on senior notes"
    # R6.htm shows 500,000 without parentheses (terseLabel, not negated).
    assert notes_out["asReported"]["value"] == 500_000_000
    assert notes_out["standaloneQuarter"]["kind"] == "unavailable"
    assert notes_out["standaloneQuarter"]["reason"] == "missing_prior_ytd"
    assert notes_out["standaloneQuarter"]["value"] is None

    secured = _line(disc, "us-gaap:ProceedsFromIssuanceOfSecuredDebt")
    assert secured["label"] == "Proceeds from long-term debt"
    assert secured["asReported"]["value"] == 0

    sect = _line(disc, "mog:PurchaseOfStockHeldByStockEmployeeCompensationTrust")
    assert sect["label"] == "Purchase of stock held by SECT"
    assert sect["identity"] is None
    assert sect["asReported"]["value"] == -51_319_000
    assert sect["standaloneQuarter"]["kind"] == "calculated"
    assert sect["standaloneQuarter"]["value"] == -16_849_000

    financing = next(g for g in disc["groups"] if g["id"] == "financing")
    assert financing["reportedTotal"]["value"] == -148_305_000
    assert financing["reportedTotal"]["concept"] == "us-gaap:NetCashProvidedByUsedInFinancingActivities"
    child_sum = sum(
        line["asReported"]["value"]
        for line in financing["lines"]
        if line["role"] == "line" and line["asReported"]["value"] is not None
    )
    assert financing["reportedTotal"]["value"] == -148_305_000
    assert child_sum != financing["reportedTotal"]["value"]


def test_mog_capex_is_face_total_without_invented_breakdown():
    disc = _mog_disclosure()
    capex = _line(disc, "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")
    assert capex["label"] == "Purchase of property, plant and equipment"
    assert capex["identity"] == "capex"
    assert capex["asReported"]["value"] == -93_692_000
    assert disc["capex"]["breakdown"] == "not_specified"
    assert disc["capex"]["note"] == "Breakdown not specified."
    assert disc["acquisitions"]["disclosedOnFace"] is False


def test_mog_note_links_are_urls_only():
    disc = _mog_disclosure()
    assert disc["noteLinks"]
    assert all(link["parsed"] is False for link in disc["noteLinks"])
    titles = {link["title"] for link in disc["noteLinks"]}
    assert any("Indebtedness" in t for t in titles)
    assert any("Acquisitions" in t for t in titles)
    assert any("Property" in t for t in titles)


def test_three_month_face_column_is_as_reported_standalone():
    st = Statement(
        title="Statements of Cash Flows",
        scale=1,
        columns=[StatementColumn(months=3, end=date(2026, 3, 31))],
        rows=[
            StatementRow(
                concept="us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
                label="Purchases of property and equipment",
                values=[-1_000_000],
            )
        ],
    )
    disc = build_cash_flow_disclosure(st, cik="0000320193", accn="0000320193-26-000050", html_name="R6.htm")
    capex = _line(disc, "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")
    assert capex["asReported"]["kind"] == "asReported"
    assert capex["asReported"]["value"] == -1_000_000
    assert capex["standaloneQuarter"]["kind"] == "asReported"
    assert capex["standaloneQuarter"]["value"] == -1_000_000
    assert capex["standaloneQuarter"]["formula"] == "3M reported"


def test_missing_prior_ytd_is_not_zero_for_new_face_line():
    q3 = parse_statement_html(MOG_Q3.read_text())
    disc = build_cash_flow_disclosure(
        q3,
        cik="0000067887",
        accn="0001628280-26-051294",
        html_name="R6.htm",
        prior_statement=None,
    )
    notes_out = _line(disc, "us-gaap:RepaymentsOfSeniorDebt")
    assert notes_out["asReported"]["value"] == 500_000_000
    assert notes_out["standaloneQuarter"]["value"] is None
    assert notes_out["standaloneQuarter"]["kind"] == "unavailable"
    assert notes_out["standaloneQuarter"]["reason"] == "missing_prior_ytd"


def test_custom_tag_is_not_forced_into_a_standard_identity():
    assert (
        line_identity(
            "mog:PurchaseOfStockHeldByStockEmployeeCompensationTrust",
            "Purchase of stock held by SECT",
        )
        is None
    )
    assert (
        line_identity(
            "us-gaap:PaymentsForRepurchaseOfCommonStock",
            "Purchase of outstanding shares for treasury",
        )
        == "shareRepurchases"
    )


def test_disclosure_is_additive_and_does_not_change_research_metrics():
    facts = _cf_core()
    disc = _mog_disclosure()
    plain = analyze_layer3_facts(facts)
    with_face = analyze_layer3_facts(facts, disclosures=disc)
    assert plain.disclosures is None
    assert "disclosures" not in plain.to_dict()
    assert with_face.disclosures is disc
    assert with_face.to_dict()["disclosures"]["cashFlow"]["source"] == "sec_cash_flow_face"
    for key in (
        "ocf",
        "capex",
        "fcf",
        "debtIssuance",
        "debtRepayment",
        "netDebtFinancing",
        "shareRepurchases",
        "dividendsPaid",
        "acquisitions",
        "investingCf",
        "financingCf",
        "cash",
        "cashCfIdentity",
    ):
        assert with_face.metrics[key] == plain.metrics[key], key


def test_real_research_metrics_unchanged_when_disclosure_attached():
    """META / MSFT / AAPL one-tag pins stay valid when a disclosure tree is attached."""
    import zipfile

    import pytest
    from test_layer3_capital_allocation import REAL_CONCEPTS, _slim_from_zip

    from screener_pipeline.layer3_build import default_facts_zip

    zpath = default_facts_zip()
    if zpath is None:
        pytest.skip("companyfacts.zip not in cache")
    disc = _mog_disclosure()
    with zipfile.ZipFile(zpath) as zf:
        meta = analyze_layer3_facts(_slim_from_zip(zf, "0001326801", REAL_CONCEPTS), sic_code="7370", disclosures=disc)
        msft = analyze_layer3_facts(_slim_from_zip(zf, "0000789019", REAL_CONCEPTS), sic_code="7372", disclosures=disc)
        aapl = analyze_layer3_facts(_slim_from_zip(zf, "0000320193", REAL_CONCEPTS), sic_code="3571", disclosures=disc)
    assert meta.metrics["debtIssuance"]["concept"] == "ProceedsFromIssuanceOfLongTermDebt"
    assert meta.metrics["shareRepurchases"]["concept"] == "PaymentsForRepurchaseOfCommonStock"
    assert msft.metrics["shareRepurchases"]["ttm"] is not None
    assert msft.metrics["dividendsPaid"]["ttm"] is not None
    assert aapl.metrics["debtIssuance"]["concept"] == "ProceedsFromIssuanceOfLongTermDebt"
    assert aapl.metrics["debtRepayment"]["concept"] == "RepaymentsOfLongTermDebt"
    assert aapl.metrics["netDebtFinancing"]["concept"].startswith("ProceedsFromRepayments")
    assert meta.metrics["fcf"]["formula"].startswith("OCF − CapEx")
    assert msft.metrics["cashCfIdentity"]["usedF3Cash"] is False
    assert aapl.metrics["cashCfIdentity"]["usedF3Cash"] is False
