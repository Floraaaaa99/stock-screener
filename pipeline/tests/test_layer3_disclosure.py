"""v1 SEC cash-flow face disclosure. Research metrics stay one-tag and unchanged."""

from __future__ import annotations

from datetime import date

from helpers import FIXTURES
from test_layer3_capital_allocation import _cf_core

from screener_pipeline.layer3_disclosure import (
    build_cash_flow_disclosure,
    line_identity,
    note_source_links,
    parse_concept_auth_refs,
    presentation_amount,
    resolve_cash_flow_disclosure,
)
from screener_pipeline.layer3_extract import analyze_layer3_facts
from screener_pipeline.sec.edgar import PeriodicFiling, latest_official_periodic
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
META_Q3 = FIXTURES / "statements" / "META-0001628280-26-066773-R8.htm"
META_Q2 = FIXTURES / "statements" / "META-0001628280-26-050705-R8.htm"
MSFT_FY = FIXTURES / "statements" / "MSFT-0001193125-26-323660-R6.htm"
MSFT_Q3 = FIXTURES / "statements" / "MSFT-0001193125-26-191507-R6.htm"
AAPL_Q3 = FIXTURES / "statements" / "AAPL-0000320193-26-000020-R7.htm"
AAPL_Q2 = FIXTURES / "statements" / "AAPL-0000320193-26-000013-R7.htm"


def _mog_disclosure():
    q3_html = MOG_Q3.read_text()
    q3 = parse_statement_html(q3_html)
    q2 = parse_statement_html(MOG_Q2.read_text())
    notes = note_source_links(MOG_SUMMARY.read_text(), "0000067887", "0001628280-26-051294")
    return build_cash_flow_disclosure(
        q3,
        cik="0000067887",
        accn="0001628280-26-051294",
        form="10-Q",
        filed="2026-07-31",
        html_name="R6.htm",
        statement_html=q3_html,
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
    assert notes_out["asReported"]["value"] == -500_000_000
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
    # Official ($500M) senior-notes outflow makes the face lines reconcile to the reported total.
    # The total is still the SEC section amount, not a recomputed child sum.
    assert child_sum == financing["reportedTotal"]["value"]


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
    q3_html = MOG_Q3.read_text()
    q3 = parse_statement_html(q3_html)
    disc = build_cash_flow_disclosure(
        q3,
        cik="0000067887",
        accn="0001628280-26-051294",
        html_name="R6.htm",
        statement_html=q3_html,
        prior_statement=None,
    )
    notes_out = _line(disc, "us-gaap:RepaymentsOfSeniorDebt")
    assert notes_out["asReported"]["value"] == -500_000_000
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


def test_apple_style_continuing_operations_headers_keep_financing_together():
    st = Statement(
        title="Statements of Cash Flows",
        scale=1,
        columns=[StatementColumn(months=9, end=date(2026, 6, 27))],
        rows=[
            StatementRow(
                "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                "Beginning cash",
                [10.0],
            ),
            StatementRow(
                "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperationsAbstract",
                "Operating activities:",
                [None],
            ),
            StatementRow("us-gaap:NetIncomeLoss", "Net income", [5.0]),
            StatementRow("us-gaap:NetCashProvidedByUsedInOperatingActivities", "Cash from operations", [8.0]),
            StatementRow(
                "us-gaap:NetCashProvidedByUsedInInvestingActivitiesContinuingOperationsAbstract",
                "Investing activities:",
                [None],
            ),
            StatementRow("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "CapEx", [-2.0]),
            StatementRow("us-gaap:NetCashProvidedByUsedInInvestingActivities", "Cash from investing", [-2.0]),
            StatementRow(
                "us-gaap:NetCashProvidedByUsedInFinancingActivitiesContinuingOperationsAbstract",
                "Financing activities:",
                [None],
            ),
            StatementRow("us-gaap:PaymentsForRepurchaseOfCommonStock", "Repurchases", [-3.0]),
            StatementRow("us-gaap:NetCashProvidedByUsedInFinancingActivities", "Cash from financing", [-3.0]),
        ],
    )
    disc = build_cash_flow_disclosure(st, cik="0000320193", accn="0000320193-26-000020", html_name="R7.htm")
    assert _line(disc, "us-gaap:NetIncomeLoss")["group"] == "operating"
    assert _line(disc, "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")["group"] == "investing"
    assert _line(disc, "us-gaap:PaymentsForRepurchaseOfCommonStock")["group"] == "financing"
    assert _line(disc, "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")["group"] == "other"
    by_order = {line["order"]: line["concept"] for g in disc["groups"] for line in g["lines"]}
    assert [by_order[i] for i in range(len(st.rows))] == [r.concept for r in st.rows]


def test_meta_msft_aapl_faces_keep_original_labels_custom_tags_and_groups():
    meta_html = META_Q3.read_text()
    meta = build_cash_flow_disclosure(
        parse_statement_html(meta_html),
        cik="0001326801",
        accn="0001628280-26-066773",
        form="10-Q",
        html_name="R8.htm",
        statement_html=meta_html,
        prior_statement=parse_statement_html(META_Q2.read_text()),
    )
    assert has_cash_flow_line(parse_statement_html(META_Q3.read_text()))
    assert meta["period"] == {"kind": "asReported", "months": 9, "end": "2026-09-30"}
    assert _line(meta, "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")["label"] == (
        "Purchases of property and equipment"
    )
    assert _line(meta, "us-gaap:PaymentsForRepurchaseOfCommonStock")["group"] == "financing"
    custom = _line(meta, "meta:PaymentsToAcquireBusinessesNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets")
    assert custom["identity"] is None
    assert custom["group"] == "investing"
    assert custom["label"] == "Acquisitions of businesses and intangible assets"
    assert _line(meta, "meta:UnrealizedGainLossOnMarketableAndNonmarketableEquityInvestments")["identity"] is None
    meta_other = next(g for g in meta["groups"] if g["id"] == "other")
    meta_begin = next(line for line in meta_other["lines"] if "beginning of the period" in line["label"].lower())
    meta_end = next(line for line in meta_other["lines"] if "end of the period" in line["label"].lower())
    assert meta_begin["asReported"]["value"] == 39_100_000_000
    assert meta_end["asReported"]["value"] == 24_354_000_000
    assert meta_begin["standaloneQuarter"]["reason"] == "instant_balance"
    assert meta_end["standaloneQuarter"]["reason"] == "instant_balance"
    assert meta_begin["standaloneQuarter"]["value"] is None
    restricted_current = _line(meta, "us-gaap:RestrictedCashAndCashEquivalentsAtCarryingValue")
    restricted_noncurrent = _line(meta, "us-gaap:RestrictedCashAndCashEquivalentsNoncurrent")
    assert restricted_current["asReported"]["value"] == 597_000_000
    assert restricted_noncurrent["asReported"]["value"] == 12_535_000_000
    assert restricted_current["standaloneQuarter"]["reason"] == "instant_balance"
    assert restricted_noncurrent["standaloneQuarter"]["reason"] == "instant_balance"

    msft_html = MSFT_FY.read_text()
    msft = build_cash_flow_disclosure(
        parse_statement_html(msft_html),
        cik="0000789019",
        accn="0001193125-26-323660",
        form="10-K",
        html_name="R6.htm",
        statement_html=msft_html,
        prior_statement=parse_statement_html(MSFT_Q3.read_text()),
    )
    assert msft["period"] == {"kind": "asReported", "months": 12, "end": "2026-06-30"}
    assert _line(msft, "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")["label"] == (
        "Additions to property and equipment"
    )
    assert _line(msft, "us-gaap:PaymentsForRepurchaseOfCommonStock")["group"] == "financing"
    assert _line(msft, "msft:AcquisitionsNetOfCashAcquiredAndPurchasesOfIntangibleAndOtherAssets")["identity"] is None
    assert _line(msft, "msft:DepreciationAmortizationAndOther")["identity"] is None
    msft_other = next(g for g in msft["groups"] if g["id"] == "other")
    msft_begin = next(line for line in msft_other["lines"] if "beginning of period" in line["label"].lower())
    msft_end = next(line for line in msft_other["lines"] if "end of period" in line["label"].lower())
    assert msft_begin["asReported"]["value"] == 30_242_000_000
    assert msft_end["asReported"]["value"] == 20_935_000_000
    assert msft_begin["standaloneQuarter"]["reason"] == "instant_balance"
    assert msft_end["standaloneQuarter"]["reason"] == "instant_balance"
    assert msft_begin["standaloneQuarter"]["value"] is None

    aapl_html = AAPL_Q3.read_text()
    aapl = build_cash_flow_disclosure(
        parse_statement_html(aapl_html),
        cik="0000320193",
        accn="0000320193-26-000020",
        form="10-Q",
        html_name="R7.htm",
        statement_html=aapl_html,
        prior_statement=parse_statement_html(AAPL_Q2.read_text()),
    )
    assert aapl["period"] == {"kind": "asReported", "months": 9, "end": "2026-06-27"}
    assert _line(aapl, "us-gaap:NetIncomeLoss")["group"] == "operating"
    assert _line(aapl, "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")["group"] == "investing"
    assert _line(aapl, "us-gaap:PaymentsForRepurchaseOfCommonStock")["group"] == "financing"
    assert _line(aapl, "us-gaap:PaymentsOfDividends")["group"] == "financing"
    cash = _line(aapl, "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")
    assert cash["group"] == "other"
    aapl_rows = parse_statement_html(AAPL_Q3.read_text()).rows
    by_order = {line["order"]: line["concept"] for g in aapl["groups"] for line in g["lines"]}
    assert [by_order[i] for i in range(len(aapl_rows))] == [r.concept for r in aapl_rows]
    other = next(g for g in aapl["groups"] if g["id"] == "other")
    begin = next(line for line in other["lines"] if "beginning" in line["label"].lower())
    end = next(line for line in other["lines"] if "ending" in line["label"].lower())
    assert begin["asReported"]["value"] == 35_934_000_000
    assert end["asReported"]["value"] == 39_544_000_000
    assert begin["standaloneQuarter"] == {
        "kind": "unavailable",
        "reason": "instant_balance",
        "value": None,
        "formula": None,
    }
    assert end["standaloneQuarter"]["reason"] == "instant_balance"
    assert end["standaloneQuarter"]["value"] is None


def test_mog_senior_notes_sign_matches_sec_10q_outflow_not_r_page_text():
    raw = parse_statement_html(MOG_Q3.read_text())
    raw_notes = next(r for r in raw.rows if r.concept == "us-gaap:RepaymentsOfSeniorDebt")
    assert raw_notes.values[0] == 500_000_000
    disc = _mog_disclosure()
    notes = _line(disc, "us-gaap:RepaymentsOfSeniorDebt")
    assert notes["asReported"]["value"] == -500_000_000
    meta = parse_concept_auth_refs(MOG_Q3.read_text())["us-gaap:RepaymentsOfSeniorDebt"]
    assert meta["periodType"] == "duration"
    assert meta["balanceType"] == "credit"
    assert "cash outflow" in (meta["definition"] or "").lower()
    assert presentation_amount("us-gaap:RepaymentsOfSeniorDebt", 500_000_000, meta=meta) == -500_000_000


def test_sign_normalization_does_not_use_concept_prefixes_or_touch_nets():
    disc = _mog_disclosure()
    assert _line(disc, "us-gaap:ProceedsFromIssuanceOfSeniorLongTermDebt")["asReported"]["value"] == 491_443_000
    assert _line(disc, "us-gaap:ProceedsFromLongTermLinesOfCredit")["asReported"]["value"] == 1_348_400_000
    assert _line(disc, "mog:PurchaseOfStockHeldByStockEmployeeCompensationTrust")["asReported"]["value"] == (
        -51_319_000
    )
    meta_html = META_Q3.read_text()
    meta = build_cash_flow_disclosure(
        parse_statement_html(meta_html),
        cik="0001326801",
        accn="0001628280-26-066773",
        statement_html=meta_html,
    )
    assert _line(meta, "us-gaap:PaymentsForProceedsFromOtherInvestingActivities")["asReported"]["value"] == (
        1_079_000_000
    )
    assert _line(meta, "meta:AcquisitionOfBusinessAndIntangibleAssets")["asReported"]["value"] == 1_593_000_000
    unknown = presentation_amount("us-gaap:PaymentsForSomethingUnlisted", 10.0)
    assert unknown == 10.0
    already_neg = presentation_amount("us-gaap:RepaymentsOfSeniorDebt", -15_716_000)
    assert already_neg == -15_716_000


def _sign_normalized_face_lines(html: str) -> list[tuple[str, str, float, float]]:
    """Raw R-page values that disclosure presentation flips."""
    raw = parse_statement_html(html)
    meta = parse_concept_auth_refs(html)
    flipped = []
    for row in raw.rows:
        if not row.values or row.values[0] is None:
            continue
        presented = presentation_amount(
            row.concept, row.values[0], label=row.label, meta=meta.get(row.concept)
        )
        if presented != row.values[0]:
            flipped.append((row.concept, row.label, row.values[0], presented))
    return flipped


def test_sign_normalized_values_match_official_sec_cash_flow_face():
    """Only verified unsigned outflows are flipped, and only to the official face sign."""
    mog_flips = _sign_normalized_face_lines(MOG_Q3.read_text())
    assert mog_flips == [
        ("us-gaap:RepaymentsOfSeniorDebt", "Payments on senior notes", 500_000_000.0, -500_000_000.0)
    ]
    # Official Moog FY2026 Q3 10-Q cash-flow face shows the senior-notes repayment in parentheses.
    official_mog_10q_senior_notes = -500_000_000
    assert mog_flips[0][3] == official_mog_10q_senior_notes

    assert _sign_normalized_face_lines(META_Q3.read_text()) == []
    assert _sign_normalized_face_lines(MSFT_FY.read_text()) == []
    assert _sign_normalized_face_lines(AAPL_Q3.read_text()) == []

    disc = _mog_disclosure()
    assert _line(disc, "us-gaap:RepaymentsOfLongTermLinesOfCredit")["asReported"]["value"] == -1_375_400_000
    assert _line(disc, "us-gaap:FinanceLeasePrincipalPayments")["asReported"]["value"] == -15_716_000
    assert _line(disc, "us-gaap:PaymentsOfDividends")["asReported"]["value"] == -28_209_000
    assert _line(disc, "us-gaap:PaymentsForRepurchaseOfCommonStock")["asReported"]["value"] == -62_673_000
    assert _line(disc, "us-gaap:NetCashProvidedByUsedInFinancingActivities")["asReported"]["value"] == (
        -148_305_000
    )
    assert _line(disc, "us-gaap:NetCashProvidedByUsedInOperatingActivities")["asReported"]["value"] == (
        244_921_000
    )


def test_instant_balances_keep_face_amounts_and_skip_ytd_subtraction():
    disc = _mog_disclosure()
    other = next(g for g in disc["groups"] if g["id"] == "other")
    begin = next(line for line in other["lines"] if "beginning of period" in line["label"].lower())
    end = next(line for line in other["lines"] if "end of period" in line["label"].lower())
    change = _line(
        disc,
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
    )
    fx = _line(
        disc,
        "us-gaap:EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    )
    assert begin["asReported"]["value"] == 62_213_000
    assert end["asReported"]["value"] == 67_752_000
    assert begin["standaloneQuarter"]["kind"] == "unavailable"
    assert begin["standaloneQuarter"]["reason"] == "instant_balance"
    assert begin["standaloneQuarter"]["value"] is None
    assert end["standaloneQuarter"]["reason"] == "instant_balance"
    assert end["standaloneQuarter"]["value"] is None
    assert change["asReported"]["value"] == 5_539_000
    assert change["standaloneQuarter"]["kind"] == "calculated"
    assert change["standaloneQuarter"]["value"] == 5_539_000 - 246_019_000
    assert fx["standaloneQuarter"]["kind"] == "calculated"
    assert fx["standaloneQuarter"]["value"] == 454_000 - 21_000

    cash_meta = parse_concept_auth_refs(MOG_Q3.read_text())[
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
    ]
    assert cash_meta["periodType"] == "instant"

    st = Statement(
        title="CF",
        scale=1,
        columns=[StatementColumn(months=9, end=date(2026, 6, 27))],
        rows=[
            StatementRow(
                "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                "Cash at beginning of period",
                [10.0],
            )
        ],
    )
    prior = Statement(
        title="CF",
        scale=1,
        columns=[StatementColumn(months=6, end=date(2026, 3, 28))],
        rows=[
            StatementRow(
                "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                "Cash at beginning of period",
                [10.0],
            )
        ],
    )
    synthetic = build_cash_flow_disclosure(
        st,
        cik="1",
        accn="a",
        prior_statement=prior,
        concept_meta={
            "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {
                "periodType": "instant",
                "balanceType": "debit",
                "definition": "Amount of cash",
            }
        },
    )
    line = _line(synthetic, "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")
    assert line["asReported"]["value"] == 10.0
    assert line["standaloneQuarter"]["reason"] == "instant_balance"
    assert line["standaloneQuarter"]["value"] is None


def test_latest_official_periodic_is_not_the_metric_accession():
    older = PeriodicFiling("0000000001-26-000050", "10-Q", date(2026, 5, 1), date(2026, 3, 31))
    newer = PeriodicFiling("0000000001-26-000090", "10-Q", date(2026, 8, 1), date(2026, 6, 30))
    assert latest_official_periodic([older, newer]).accn == "0000000001-26-000090"
    assert latest_official_periodic([older, newer]).accn != "0000000001-26-000050"


class _FakeSec:
    def __init__(self, statements, summaries=None, fail=None):
        self.statements = statements
        self.summaries = summaries or {}
        self.fail = set(fail or [])
        self.cf_gets: list[str] = []

    def cash_flow_statement(self, cik, accn):
        self.cf_gets.append(accn)
        if accn in self.fail:
            return None
        st = self.statements.get(accn)
        if st is None:
            return None
        return st, f"https://www.sec.gov/Archives/edgar/data/1/{accn.replace('-', '')}/R6.htm"

    def filing_summary(self, cik, accn):
        return self.summaries.get(accn)


def test_resolve_uses_official_filing_not_metric_accn_and_marks_stale():
    latest = PeriodicFiling("0000000001-26-000090", "10-Q", date(2026, 8, 1), date(2026, 6, 30))
    st = Statement(
        title="CF",
        scale=1,
        columns=[StatementColumn(months=3, end=date(2026, 6, 30))],
        rows=[StatementRow("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "PPE", [-4.0])],
    )
    sec = _FakeSec({"0000000001-26-000090": st})
    resolved = resolve_cash_flow_disclosure(
        cik="0000000001",
        sec=sec,
        official_filings=[latest],
        existing={
            "cashFlow": {
                "source": "sec_cash_flow_face",
                "filing": {"accn": "0000000001-26-000050"},
                "groups": [{"id": "old", "lines": []}],
            }
        },
    )
    assert resolved["cashFlow"]["status"] == "current"
    assert resolved["cashFlow"]["filing"]["accn"] == "0000000001-26-000090"
    assert sec.cf_gets == ["0000000001-26-000090"]

    failed = resolve_cash_flow_disclosure(
        cik="0000000001",
        sec=_FakeSec({}, fail={"0000000001-26-000090"}),
        official_filings=[latest],
        existing={
            "cashFlow": {
                "source": "sec_cash_flow_face",
                "filing": {"accn": "0000000001-26-000050", "filed": "2026-05-01"},
                "groups": [{"id": "financing", "lines": [{"concept": "keep"}]}],
            }
        },
    )
    assert failed["cashFlow"]["status"] == "stale"
    assert failed["cashFlow"]["filing"]["accn"] == "0000000001-26-000050"
    assert failed["cashFlow"]["targetAccn"] == "0000000001-26-000090"
    assert failed["cashFlow"]["groups"][0]["lines"][0]["concept"] == "keep"

    missing = resolve_cash_flow_disclosure(
        cik="0000000001",
        sec=_FakeSec({}, fail={"0000000001-26-000090"}),
        official_filings=[latest],
    )
    assert missing["cashFlow"]["status"] == "unavailable"
    assert missing["cashFlow"]["groups"] == []
    assert missing["cashFlow"]["targetAccn"] == "0000000001-26-000090"
