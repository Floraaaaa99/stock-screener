from datetime import date

from helpers import companyfacts, raw

from screener_pipeline.layer3_concepts import is_financial_sic
from screener_pipeline.layer3_extract import analyze_layer3_facts, compute_flow_ttm
from screener_pipeline.quarters import MissingQuarter, Quarter
from screener_pipeline.sec.facts import parse_instant_fact


def _q(start, end, val, method="reported"):
    return Quarter(date.fromisoformat(start), date.fromisoformat(end), val, method, method, [], "X")


def _miss(start, end):
    return MissingQuarter(date.fromisoformat(start), date.fromisoformat(end))


def _ytd_year(fy: int, q1: float, q2: float, q3: float, q4: float, *, prefix: str) -> list[dict]:
    """Calendar-year cash-flow facts as typically filed: Q1 3M, Q2/Q3 YTD, 10-K FY."""
    y = fy
    a1, a2, a3, ak = f"{prefix}{y}-1", f"{prefix}{y}-2", f"{prefix}{y}-3", f"{prefix}{y}-K"
    return [
        raw(f"{y}-01-01", f"{y}-03-31", q1, a1, y, "Q1", filed=f"{y}-05-01"),
        raw(f"{y}-01-01", f"{y}-06-30", q1 + q2, a2, y, "Q2", filed=f"{y}-08-01"),
        raw(f"{y}-01-01", f"{y}-09-30", q1 + q2 + q3, a3, y, "Q3", filed=f"{y}-11-01"),
        raw(f"{y}-01-01", f"{y}-12-31", q1 + q2 + q3 + q4, ak, y, "FY", form="10-K", filed=f"{y + 1}-02-15"),
    ]


def _instant(end: str, val: float, accn: str, fy: int, fp: str, form: str = "10-Q", filed: str | None = None) -> dict:
    return {"end": end, "val": val, "accn": accn, "fy": fy, "fp": fp, "form": form, "filed": filed or end}


def test_flow_ttm_allows_negative_and_never_maps_missing_to_zero():
    current = compute_flow_ttm([_q("2025-10-01", "2025-12-31", -10), _q("2025-07-01", "2025-09-30", 4),
                                _q("2025-04-01", "2025-06-30", 3), _q("2025-01-01", "2025-03-31", 2),
                                _q("2024-10-01", "2024-12-31", -8), _q("2024-07-01", "2024-09-30", 1),
                                _q("2024-04-01", "2024-06-30", 1), _q("2024-01-01", "2024-03-31", 1)])
    assert current.current == -1
    assert current.previous == -5
    assert current.reason is None
    gapped = compute_flow_ttm([_q("2025-10-01", "2025-12-31", 10), _miss("2025-07-01", "2025-09-30"),
                               _q("2025-04-01", "2025-06-30", 3), _q("2025-01-01", "2025-03-31", 2)])
    assert gapped.current is None and gapped.previous is None
    assert gapped.reason == "gap_in_quarters"


def test_ytd_ocf_derives_standalone_quarters_and_ttm():
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 10, 20, 30, 40, prefix="O") + _ytd_year(2024, 5, 6, 7, 8, prefix="P")
            ),
            "PaymentsToAcquirePropertyPlantAndEquipment": (
                _ytd_year(2025, 1, 2, 3, 4, prefix="C") + _ytd_year(2024, 1, 1, 1, 1, prefix="D")
            ),
        },
        cik=875320,
        name="Vertex",
    )
    analysis = analyze_layer3_facts(facts, sic_code="2834")
    ocf = analysis.metrics["ocf"]
    by_end = {q["end"]: q for q in ocf["quarters"]}
    assert by_end["2025-06-30"]["value"] == 20
    assert by_end["2025-06-30"]["formula"] == "6M YTD − 3M"
    assert by_end["2025-09-30"]["formula"] == "9M YTD − 6M YTD"
    assert by_end["2025-12-31"]["value"] == 40
    assert by_end["2025-12-31"]["formula"] == "FY − 9M YTD"
    assert ocf["ttm"] == 100
    assert ocf["previousTtm"] == 26
    assert ocf["concept"] == "NetCashProvidedByUsedInOperatingActivities"
    assert ocf["verification"] == "company_facts_only"
    capex = analysis.metrics["capex"]
    assert capex["ttm"] == 10
    assert capex["previousTtm"] == 4
    assert capex["signPolicy"] == "positive_cash_outflow_magnitude"
    fcf = analysis.metrics["fcf"]
    assert fcf["ttm"] == 90
    assert fcf["previousTtm"] == 22
    assert fcf["formula"].startswith("OCF − CapEx")
    assert analysis.extraction_status == "extracted"
    assert analysis.verification_status == "company_facts_only"
    assert analysis.scoring_status == "not_implemented"
    assert analysis.input_completeness == "pending_data_verification"  # cash missing
    assert analysis.metrics["fcf"]["ttm"] != 0 or fcf["ttm"] == 90


def test_negative_capex_tag_becomes_positive_outflow_magnitude():
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 50, 50, 50, 50, prefix="O") + _ytd_year(2024, 40, 40, 40, 40, prefix="P")
            ),
            "PaymentsToAcquirePropertyPlantAndEquipment": (
                _ytd_year(2025, -8, -8, -8, -8, prefix="C") + _ytd_year(2024, -5, -5, -5, -5, prefix="D")
            ),
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["capex"]["ttm"] == 32
    assert analysis.metrics["fcf"]["ttm"] == 200 - 32


def test_missing_capex_leaves_fcf_null_not_zero():
    facts = companyfacts(
        {"NetCashProvidedByUsedInOperatingActivities": _ytd_year(2025, 10, 10, 10, 10, prefix="O")
         + _ytd_year(2024, 10, 10, 10, 10, prefix="P")}
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["ocf"]["ttm"] == 40
    assert analysis.metrics["capex"]["ttm"] is None
    assert analysis.metrics["fcf"]["ttm"] is None
    assert analysis.metrics["fcf"]["reason"] == "missing_capex"
    assert analysis.metrics["fcf"]["status"] == "missing"


def test_ebitda_only_when_operating_income_and_da_exist():
    base_ocf = _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 10, 10, 10, 10, prefix="P")
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": base_ocf,
            "OperatingIncomeLoss": _ytd_year(2025, 8, 8, 8, 8, prefix="I") + _ytd_year(2024, 7, 7, 7, 7, prefix="J"),
        }
    )
    missing_da = analyze_layer3_facts(facts)
    assert missing_da.metrics["ebitda"]["ttm"] is None
    assert missing_da.metrics["ebitda"]["reason"] == "missing_depreciation_amortization"
    facts["facts"]["us-gaap"]["DepreciationAndAmortization"] = {
        "units": {"USD": _ytd_year(2025, 2, 2, 2, 2, prefix="A") + _ytd_year(2024, 1, 1, 1, 1, prefix="B")}
    }
    ok = analyze_layer3_facts(facts)
    assert ok.metrics["ebitda"]["ttm"] == 32 + 8
    assert ok.metrics["ebitda"]["formula"] == "operating_income + depreciation_and_amortization"


def test_stocks_use_latest_quarter_end_and_do_not_sum():
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 10, 10, 10, 10, prefix="P")
            ),
            "PaymentsToAcquirePropertyPlantAndEquipment": (
                _ytd_year(2025, 1, 1, 1, 1, prefix="C") + _ytd_year(2024, 1, 1, 1, 1, prefix="D")
            ),
            "CashAndCashEquivalentsAtCarryingValue": [
                _instant("2024-12-31", 100, "old", 2024, "FY", form="10-K", filed="2025-02-15"),
                _instant("2025-12-31", 250, "new", 2025, "FY", form="10-K", filed="2026-02-15"),
            ],
            "DebtCurrent": [_instant("2025-12-31", 40, "new", 2025, "FY", form="10-K", filed="2026-02-15")],
            "LongTermDebtNoncurrent": [_instant("2025-12-31", 60, "new", 2025, "FY", form="10-K", filed="2026-02-15")],
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["cash"]["value"] == 250
    assert analysis.metrics["cash"]["aggregation"] == "latest_quarter_end"
    assert analysis.metrics["totalDebt"]["value"] == 100
    assert analysis.metrics["netDebt"]["value"] == -150
    assert analysis.extraction_status == "extracted"
    assert analysis.input_completeness == "ready"
    assert analysis.verification_status == "company_facts_only"
    assert analysis.scoring_status == "not_implemented"


def test_debt_components_sum_only_when_same_period_and_no_total():
    mismatch = companyfacts(
        {
            "LongTermDebtCurrent": [_instant("2025-12-31", 10, "a", 2025, "FY", form="10-K")],
            "ShortTermBorrowings": [_instant("2025-09-30", 5, "b", 2025, "Q3")],
            "LongTermDebtNoncurrent": [_instant("2025-12-31", 20, "a", 2025, "FY", form="10-K")],
        }
    )
    bad = analyze_layer3_facts(mismatch)
    assert bad.metrics["shortTermDebt"]["status"] == "missing"
    assert bad.metrics["shortTermDebt"]["reason"] == "debt_period_mismatch"
    assert bad.metrics["totalDebt"]["value"] is None
    assert bad.metrics["netDebt"]["value"] is None

    aligned = companyfacts(
        {
            "LongTermDebtCurrent": [_instant("2025-12-31", 10, "a", 2025, "FY", form="10-K")],
            "ShortTermBorrowings": [_instant("2025-12-31", 5, "a", 2025, "FY", form="10-K")],
            "LongTermDebtNoncurrent": [_instant("2025-12-31", 20, "a", 2025, "FY", form="10-K")],
        }
    )
    ok = analyze_layer3_facts(aligned)
    assert ok.metrics["shortTermDebt"]["value"] == 15
    assert ok.metrics["shortTermDebt"]["aggregation"] == "sum_disjoint_current_components"
    assert ok.metrics["totalDebt"]["value"] == 35


def test_long_term_debt_does_not_add_overlapping_concepts():
    facts = companyfacts(
        {
            "LongTermDebtNoncurrent": [_instant("2025-12-31", 80, "a", 2025, "FY", form="10-K")],
            "LongTermDebt": [_instant("2025-12-31", 80, "a", 2025, "FY", form="10-K")],
            "DebtCurrent": [_instant("2025-12-31", 0, "a", 2025, "FY", form="10-K")],
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["longTermDebt"]["concept"] == "LongTermDebtNoncurrent"
    assert analysis.metrics["longTermDebt"]["value"] == 80


def test_no_interest_burden_requires_extracted_zeros_not_missing():
    empty = analyze_layer3_facts(companyfacts({}))
    assert empty.metrics["noInterestBurden"] is False
    facts = companyfacts(
        {
            "InterestExpense": _ytd_year(2025, 0, 0, 0, 0, prefix="I") + _ytd_year(2024, 0, 0, 0, 0, prefix="J"),
            "DebtCurrent": [_instant("2025-12-31", 0, "a", 2025, "FY", form="10-K")],
            "LongTermDebtNoncurrent": [_instant("2025-12-31", 0, "a", 2025, "FY", form="10-K")],
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["interestExpense"]["ttm"] == 0
    assert analysis.metrics["totalDebt"]["value"] == 0
    assert analysis.metrics["noInterestBurden"] is True


def test_financial_sic_is_model_not_applicable_but_metrics_are_still_extracted():
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 10, 10, 10, 10, prefix="P")
            ),
            "CashAndCashEquivalentsAtCarryingValue": [_instant("2025-12-31", 1, "a", 2025, "FY", form="10-K")],
        }
    )
    analysis = analyze_layer3_facts(facts, sic_code="6021")
    assert is_financial_sic("6021")
    assert analysis.model_applicability == "not_applicable"
    assert analysis.extraction_status == "extracted"
    assert analysis.scoring_status == "not_implemented"
    assert "financial_institution" in analysis.flags
    assert analysis.metrics["ocf"]["ttm"] == 40
    assert analysis.to_dict()["scoring"] is None


def test_foreign_filer_does_not_fabricate_quarters():
    facts = {
        "cik": 1835632,
        "entityName": "Foreign Co",
        "facts": {
            "us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            raw("2025-01-01", "2025-12-31", 100, "f", 2025, "FY", form="20-F", filed="2026-03-01"),
                        ]
                    }
                }
            }
        },
    }
    analysis = analyze_layer3_facts(facts, foreign=True)
    assert analysis.extraction_status == "insufficient_facts"
    assert analysis.verification_status == "not_checked"
    assert "no_fabricated_foreign_quarters" in analysis.flags
    assert analysis.metrics["ocf"]["ttm"] is None


def test_instant_parser_rejects_duration_facts():
    assert parse_instant_fact({"end": "2025-12-31", "start": "2025-01-01", "val": 1, "accn": "a",
                               "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2026-02-01"}) is None
    inst = parse_instant_fact({"end": "2025-12-31", "val": 0, "accn": "a", "fy": 2025, "fp": "FY",
                               "form": "10-K", "filed": "2026-02-01"})
    assert inst is not None and inst.val == 0


def test_scoring_is_not_emitted():
    analysis = analyze_layer3_facts(companyfacts({}))
    dumped = analysis.to_dict()
    assert dumped["scoring"] is None
    assert dumped["scoringStatus"] == "not_implemented"
    assert dumped["verificationStatus"] == "not_checked"
    assert dumped["metrics"]["growthSource"] == "not_yet_verified"


def test_stale_long_term_debt_is_not_treated_as_current():
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 10, 10, 10, 10, prefix="P")
            ),
            "PaymentsToAcquirePropertyPlantAndEquipment": (
                _ytd_year(2025, 1, 1, 1, 1, prefix="C") + _ytd_year(2024, 1, 1, 1, 1, prefix="D")
            ),
            "CashAndCashEquivalentsAtCarryingValue": [_instant("2025-12-31", 50, "new", 2025, "FY", form="10-K")],
            "DebtCurrent": [_instant("2025-12-31", 3, "new", 2025, "FY", form="10-K")],
            "LongTermDebtNoncurrent": [_instant("2011-04-30", 7, "old", 2011, "Q2")],
            "LongTermDebtAndCapitalLeaseObligations": [_instant("2025-12-31", 2500, "new", 2025, "FY", form="10-K")],
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["longTermDebt"]["value"] == 2500
    assert analysis.metrics["longTermDebt"]["concept"] == "LongTermDebtAndCapitalLeaseObligations"
    assert analysis.metrics["longTermDebt"]["includesLeaseObligations"] is True
    assert analysis.metrics["totalDebt"]["value"] == 2503
    assert analysis.metrics["netDebt"]["value"] == 2503 - 50


def test_interest_skips_stale_concept_for_aligned_window():
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 10, 10, 10, 10, prefix="P")
            ),
            "InterestExpense": _ytd_year(2019, 0, 0, 0, 0, prefix="I") + _ytd_year(2018, 0, 0, 0, 0, prefix="J"),
            "InterestExpenseDebt": _ytd_year(2025, 2, 2, 2, 2, prefix="K") + _ytd_year(2024, 1, 1, 1, 1, prefix="L"),
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["interestExpense"]["concept"] == "InterestExpenseDebt"
    assert analysis.metrics["interestExpense"]["ttm"] == 8


def test_unqualified_long_term_debt_is_not_added_to_current_portion():
    """LongTermDebt is often a total. Do not add it on top of LongTermDebtCurrent."""
    facts = companyfacts(
        {
            "LongTermDebtCurrent": [_instant("2025-12-31", 139, "a", 2025, "FY", form="10-K")],
            "LongTermDebt": [_instant("2025-12-31", 32760, "a", 2025, "FY", form="10-K")],
            "LongTermDebtAndCapitalLeaseObligations": [_instant("2025-12-31", 32621, "a", 2025, "FY", form="10-K")],
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["shortTermDebt"]["value"] == 139
    assert analysis.metrics["longTermDebt"]["value"] == 32621
    assert analysis.metrics["totalDebt"]["value"] == 32760


def test_notes_payable_is_a_total_fallback_not_added_to_current_portion():
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 10, 10, 10, 10, prefix="P")
            ),
            "PaymentsToAcquirePropertyPlantAndEquipment": (
                _ytd_year(2025, 1, 1, 1, 1, prefix="C") + _ytd_year(2024, 1, 1, 1, 1, prefix="D")
            ),
            "CashAndCashEquivalentsAtCarryingValue": [_instant("2025-12-31", 50, "a", 2025, "FY", form="10-K")],
            "LongTermDebtCurrent": [_instant("2025-12-31", 5.61, "a", 2025, "FY", form="10-K")],
            "NotesPayable": [_instant("2025-12-31", 756.937, "a", 2025, "FY", form="10-K")],
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["shortTermDebt"]["value"] == 5.61
    assert analysis.metrics["longTermDebt"]["value"] is None
    assert analysis.metrics["totalDebt"]["value"] == 756.937
    assert analysis.metrics["totalDebt"]["concept"] == "NotesPayable"
    assert analysis.metrics["totalDebt"]["formula"] == "single_total_debt_concept"
    assert analysis.metrics["netDebt"]["value"] == 756.937 - 50


def test_last_resort_net_capex_tag_used_only_when_gross_ppe_missing():
    ocf = _ytd_year(2025, 50, 50, 50, 50, prefix="O") + _ytd_year(2024, 40, 40, 40, 40, prefix="P")
    net = _ytd_year(2025, 4, 4, 4, 4, prefix="N") + _ytd_year(2024, 3, 3, 3, 3, prefix="M")
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": ocf,
            "PaymentsForProceedsFromProductiveAssets": net,
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["capex"]["concept"] == "PaymentsForProceedsFromProductiveAssets"
    assert analysis.metrics["capex"]["ttm"] == 16
    assert analysis.metrics["fcf"]["ttm"] == 200 - 16
    assert "net of asset-sale proceeds" in (analysis.metrics["capex"].get("scopeNote") or "")

    facts["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"] = {
        "units": {"USD": _ytd_year(2025, 5, 5, 5, 5, prefix="C") + _ytd_year(2024, 2, 2, 2, 2, prefix="D")}
    }
    prefer = analyze_layer3_facts(facts)
    assert prefer.metrics["capex"]["concept"] == "PaymentsToAcquirePropertyPlantAndEquipment"
    assert prefer.metrics["capex"]["ttm"] == 20


def test_depreciation_only_does_not_treat_unaligned_amortization_as_zero():
    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": (
                _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 10, 10, 10, 10, prefix="P")
            ),
            "OperatingIncomeLoss": _ytd_year(2025, 8, 8, 8, 8, prefix="I") + _ytd_year(2024, 7, 7, 7, 7, prefix="J"),
            "Depreciation": _ytd_year(2025, 2, 2, 2, 2, prefix="D") + _ytd_year(2024, 1, 1, 1, 1, prefix="E"),
            "AmortizationOfIntangibleAssets": _ytd_year(2020, 3, 3, 3, 3, prefix="A")
            + _ytd_year(2019, 3, 3, 3, 3, prefix="B"),
        }
    )
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["depreciationAmortization"]["concept"] == "Depreciation"
    assert analysis.metrics["depreciationAmortization"]["ttm"] == 8
    assert analysis.metrics["ebitda"]["ttm"] is None
    assert analysis.metrics["ebitda"]["reason"] == "depreciation_excludes_amortization"

    facts["facts"]["us-gaap"]["AmortizationOfIntangibleAssets"] = {
        "units": {"USD": _ytd_year(2025, 3, 3, 3, 3, prefix="A") + _ytd_year(2024, 2, 2, 2, 2, prefix="B")}
    }
    summed = analyze_layer3_facts(facts)
    assert summed.metrics["depreciationAmortization"]["ttm"] == 8 + 12
    assert summed.metrics["depreciationAmortization"]["aggregation"] == "sum_depreciation_and_amortization"
    assert summed.metrics["ebitda"]["ttm"] == 32 + 20
