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


def _two_year_income() -> dict[str, list[dict]]:
    return {
        "Revenues": _ytd_year(2025, 100, 110, 120, 130, prefix="R") + _ytd_year(2024, 80, 85, 90, 95, prefix="S"),
        "GrossProfit": _ytd_year(2025, 40, 44, 48, 52, prefix="G") + _ytd_year(2024, 30, 32, 34, 36, prefix="H"),
        "CostOfRevenue": _ytd_year(2025, 60, 66, 72, 78, prefix="K") + _ytd_year(2024, 50, 53, 56, 59, prefix="L"),
        "NetIncomeLoss": _ytd_year(2025, 12, 13, 14, 15, prefix="N") + _ytd_year(2024, 8, 9, 10, 11, prefix="M"),
        "NetCashProvidedByUsedInOperatingActivities": (
            _ytd_year(2025, 20, 22, 24, 26, prefix="O") + _ytd_year(2024, 16, 17, 18, 19, prefix="P")
        ),
        "PaymentsToAcquirePropertyPlantAndEquipment": (
            _ytd_year(2025, 2, 2, 2, 2, prefix="C") + _ytd_year(2024, 1, 1, 1, 1, prefix="D")
        ),
        "OperatingIncomeLoss": (
            _ytd_year(2025, 18, 19, 20, 21, prefix="I") + _ytd_year(2024, 14, 15, 16, 17, prefix="J")
        ),
        "DepreciationAndAmortization": (
            _ytd_year(2025, 3, 3, 3, 3, prefix="A") + _ytd_year(2024, 2, 2, 2, 2, prefix="B")
        ),
    }


def _eight_instants(tag: str, values: list[float]) -> list[dict]:
    """Eight quarter-ends matching calendar-year _ytd_year slots, newest last in list."""
    ends = [
        ("2024-03-31", 2024, "Q1", "10-Q"),
        ("2024-06-30", 2024, "Q2", "10-Q"),
        ("2024-09-30", 2024, "Q3", "10-Q"),
        ("2024-12-31", 2024, "FY", "10-K"),
        ("2025-03-31", 2025, "Q1", "10-Q"),
        ("2025-06-30", 2025, "Q2", "10-Q"),
        ("2025-09-30", 2025, "Q3", "10-Q"),
        ("2025-12-31", 2025, "FY", "10-K"),
    ]
    return [
        _instant(end, val, f"{tag}-{end}", fy, fp, form=form)
        for (end, fy, fp, form), val in zip(ends, values, strict=True)
    ]


def test_gross_profit_and_cogs_keep_revenue_identity():
    facts = companyfacts(_two_year_income())
    analysis = analyze_layer3_facts(facts)
    gp = analysis.metrics["grossProfit"]
    cogs = analysis.metrics["costOfRevenue"]
    rev = analysis.metrics["revenue"]
    assert rev["ttm"] == 460
    assert gp["ttm"] == 184
    assert cogs["ttm"] == 276
    assert gp["ttm"] + cogs["ttm"] == rev["ttm"]
    assert gp["verification"] == "company_facts_only"
    assert gp["verification"] != "statement_verified"
    assert analysis.metrics["grossMargin"]["ttm"] == 184 / 460
    assert analysis.schema_version == 3
    assert analysis.extraction_version == 4
    assert analysis.data_as_of == "2025-12-31"


def test_mismatched_cogs_tag_is_not_first_nonempty():
    concepts = _two_year_income()
    # A broader/wrong cost tag that does not foot to revenue.
    concepts["CostOfGoodsAndServicesSold"] = (
        _ytd_year(2025, 90, 90, 90, 90, prefix="X") + _ytd_year(2024, 90, 90, 90, 90, prefix="Y")
    )
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["costOfRevenue"]["concept"] == "CostOfRevenue"
    assert analysis.metrics["costOfRevenue"]["ttm"] == 276


def test_conflicting_reported_cogs_is_not_replaced_with_revenue_minus_gp():
    """When both GP and COGS are tagged but do not foot, keep both series."""
    concepts = _two_year_income()
    concepts["CostOfRevenue"] = (
        _ytd_year(2025, 5000, 5000, 5000, 5000, prefix="K") + _ytd_year(2024, 4000, 4000, 4000, 4000, prefix="L")
    )
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    gp = analysis.metrics["grossProfit"]
    cogs = analysis.metrics["costOfRevenue"]
    rev = analysis.metrics["revenue"]
    assert gp["ttm"] == 184
    assert cogs["ttm"] == 20000
    assert cogs["ttm"] != rev["ttm"] - gp["ttm"]
    assert cogs["calculationMethod"] == "extracted"
    assert cogs["concept"] == "CostOfRevenue"
    assert cogs["identity"] == "concept_scope_mismatch"
    assert "not overwritten" in (cogs.get("scopeNote") or "")
    assert gp["identity"] == "concept_scope_mismatch"
    assert gp["concept"] == "GrossProfit"


def test_missing_cogs_is_derived_from_revenue_minus_gp():
    concepts = _two_year_income()
    del concepts["CostOfRevenue"]
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    cogs = analysis.metrics["costOfRevenue"]
    assert cogs["calculationMethod"] == "derived"
    assert cogs["ttm"] == 460 - 184
    assert cogs["derivedFrom"] == "revenue_minus_gross_profit"
    assert cogs["verification"] != "statement_verified"


def test_missing_gross_profit_is_derived_from_revenue_minus_cogs():
    concepts = _two_year_income()
    del concepts["GrossProfit"]
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    gp = analysis.metrics["grossProfit"]
    assert gp["calculationMethod"] == "derived"
    assert gp["ttm"] == 460 - 276
    assert gp["derivedFrom"] == "revenue_minus_cost_of_revenue"
    assert gp["verification"] != "statement_verified"
    assert any(q.get("value") == 40 for q in gp["quarters"])


def test_stale_gross_profit_is_derived_from_aligned_revenue_minus_cogs():
    """HEI-like: GrossProfit last tagged years ago; current Revenue and COGS remain."""
    concepts = _two_year_income()
    concepts["GrossProfit"] = (
        _ytd_year(2020, 40, 44, 48, 52, prefix="G") + _ytd_year(2019, 30, 32, 34, 36, prefix="H")
    )
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    gp = analysis.metrics["grossProfit"]
    cogs = analysis.metrics["costOfRevenue"]
    rev = analysis.metrics["revenue"]
    assert cogs["calculationMethod"] == "extracted"
    assert cogs["ttm"] == 276
    assert gp["calculationMethod"] == "derived"
    assert gp["derivedFrom"] == "revenue_minus_cost_of_revenue"
    assert gp["ttm"] == rev["ttm"] - cogs["ttm"]
    assert gp["ttm"] == 184
    assert gp["concept"] is None
    assert gp["verification"] != "statement_verified"
    assert "not aligned" in (gp.get("scopeNote") or "")
    assert gp.get("newestEnd") != "2025-12-31"
    assert analysis.metrics["grossMargin"]["ttm"] == 184 / 460
    assert any(q.get("end") == "2025-12-31" and q.get("value") == 52 for q in gp["quarters"])


def test_stale_cogs_is_derived_from_aligned_revenue_minus_gp():
    concepts = _two_year_income()
    concepts["CostOfRevenue"] = (
        _ytd_year(2020, 60, 66, 72, 78, prefix="K") + _ytd_year(2019, 50, 53, 56, 59, prefix="L")
    )
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    cogs = analysis.metrics["costOfRevenue"]
    gp = analysis.metrics["grossProfit"]
    assert gp["calculationMethod"] == "extracted"
    assert gp["ttm"] == 184
    assert cogs["calculationMethod"] == "derived"
    assert cogs["derivedFrom"] == "revenue_minus_gross_profit"
    assert cogs["ttm"] == 460 - 184
    assert cogs["concept"] is None
    assert "not aligned" in (cogs.get("scopeNote") or "")


def test_stale_gp_and_stale_cogs_are_not_derived_across_periods():
    concepts = _two_year_income()
    concepts["GrossProfit"] = _ytd_year(2020, 40, 44, 48, 52, prefix="G")
    concepts["CostOfRevenue"] = _ytd_year(2018, 10, 10, 10, 10, prefix="K")
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    gp = analysis.metrics["grossProfit"]
    cogs = analysis.metrics["costOfRevenue"]
    assert gp["ttm"] is None
    assert cogs["ttm"] is None
    assert gp["calculationMethod"] != "derived"
    assert cogs["calculationMethod"] != "derived"
    assert analysis.metrics["grossMargin"]["ttm"] is None


def test_fcf_and_ebitda_have_eight_derived_quarters():
    facts = companyfacts(_two_year_income())
    analysis = analyze_layer3_facts(facts)
    fcf = analysis.metrics["fcf"]
    ebitda = analysis.metrics["ebitda"]
    assert fcf["ttm"] == 92 - 8
    assert len(fcf["quarters"]) == 8
    assert fcf["quarters"][0]["value"] == 26 - 2
    assert fcf["calculationMethod"] == "derived"
    assert ebitda["ttm"] == 78 + 12
    assert len(ebitda["quarters"]) == 8
    assert ebitda["quarters"][0]["method"] == "derived"
    assert analysis.metrics["ocf"]["ttmYoy"] == (92 / 70 - 1) * 100


def test_balance_sheet_history_aligns_and_does_not_fill_stale_gaps():
    concepts = _two_year_income()
    concepts["CashAndCashEquivalentsAtCarryingValue"] = _eight_instants("cash", [10, 11, 12, 13, 14, 15, 16, 20])
    concepts["AccountsReceivableNetCurrent"] = _eight_instants("ar", [30, 31, 32, 33, 34, 35, 36, 40])
    concepts["InventoryNet"] = _eight_instants("inv", [8, 8, 8, 9, 9, 9, 9, 10])
    concepts["AccountsPayableCurrent"] = _eight_instants("ap", [6, 6, 7, 7, 7, 8, 8, 9])
    concepts["AssetsCurrent"] = _eight_instants("ca", [50, 52, 54, 56, 58, 60, 62, 70])
    concepts["LiabilitiesCurrent"] = _eight_instants("cl", [20, 20, 21, 21, 22, 22, 23, 25])
    concepts["DebtCurrent"] = [_instant("2025-12-31", 4, "st", 2025, "FY", form="10-K")]
    concepts["LongTermDebtNoncurrent"] = [
        _instant("2025-12-31", 12, "lt", 2025, "FY", form="10-K"),
        _instant("2011-04-30", 999, "old", 2011, "Q2"),
    ]
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    cash = analysis.metrics["cash"]
    assert cash["value"] == 20
    assert len(cash["history"]) == 8
    assert [h["value"] for h in cash["history"]] == [20, 16, 15, 14, 13, 12, 11, 10]
    assert cash["history"][0]["end"] == "2025-12-31"
    assert analysis.metrics["longTermDebt"]["value"] == 12
    stale_slots = [h for h in analysis.metrics["longTermDebt"]["history"] if h["end"] != "2025-12-31"]
    assert all(h["value"] is None for h in stale_slots)
    assert analysis.metrics["currentRatio"]["value"] == 70 / 25
    owc = analysis.metrics["operatingWorkingCapital"]
    assert owc["value"] == 40 + 10 - 9
    assert owc["formula"] == "AR + Inventory − AP"
    assert analysis.metrics["arYoy"]["value"] == (40 / 33 - 1) * 100
    assert analysis.metrics["dso"]["status"] == "extracted"
    assert analysis.metrics["dso"]["value"] == ((33 + 40) / 2) / 460 * analysis.metrics["dso"]["daysInWindow"]
    assert analysis.metrics["cashConversionCycle"]["status"] == "extracted"
    assert analysis.metrics["cash"]["verification"] == "company_facts_only"


def test_software_without_inventory_is_not_applicable_not_zero():
    concepts = _two_year_income()
    concepts["CashAndCashEquivalentsAtCarryingValue"] = [_instant("2025-12-31", 50, "c", 2025, "FY", form="10-K")]
    concepts["AccountsReceivableNetCurrent"] = _eight_instants("ar", [10, 11, 12, 13, 14, 15, 16, 20])
    concepts["AccountsPayableCurrent"] = _eight_instants("ap", [4, 4, 4, 5, 5, 5, 5, 6])
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["inventory"]["status"] == "not_applicable"
    assert analysis.metrics["inventory"]["value"] is None
    assert analysis.metrics["dio"]["status"] == "not_applicable"
    assert analysis.metrics["inventoryYoy"]["status"] == "not_applicable"
    owc = analysis.metrics["operatingWorkingCapital"]
    assert owc["value"] == 20 - 6
    assert "inventory not applicable" in owc["formula"]
    ccc = analysis.metrics["cashConversionCycle"]
    assert ccc["status"] == "extracted"
    assert "DIO not applicable" in ccc["formula"]


def test_working_capital_ratios_do_not_treat_missing_as_zero():
    concepts = _two_year_income()
    concepts["AccountsReceivableNetCurrent"] = [_instant("2025-12-31", 40, "ar", 2025, "FY", form="10-K")]
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    assert analysis.metrics["dso"]["ttm"] is None if False else analysis.metrics["dso"]["value"] is None
    assert analysis.metrics["dso"]["reason"] == "insufficient_stock_history"
    assert analysis.metrics["operatingWorkingCapital"]["value"] is None
    assert analysis.metrics["operatingWorkingCapital"]["reason"] == "missing_accounts_payable"
    assert analysis.metrics["currentRatio"]["value"] is None
    assert analysis.metrics["cashConversionCycle"]["value"] is None


def test_non_december_fiscal_year_spine_is_preserved():
    """HEI-like October year-end: Q4 = FY − 9M still holds."""
    def _oct_ytd(fy: int, q1: float, q2: float, q3: float, q4: float, prefix: str) -> list[dict]:
        y0 = fy - 1
        return [
            raw(f"{y0}-11-01", f"{fy}-01-31", q1, f"{prefix}{fy}-1", fy, "Q1", filed=f"{fy}-03-01"),
            raw(f"{y0}-11-01", f"{fy}-04-30", q1 + q2, f"{prefix}{fy}-2", fy, "Q2", filed=f"{fy}-06-01"),
            raw(f"{y0}-11-01", f"{fy}-07-31", q1 + q2 + q3, f"{prefix}{fy}-3", fy, "Q3", filed=f"{fy}-09-01"),
            raw(f"{y0}-11-01", f"{fy}-10-31", q1 + q2 + q3 + q4, f"{prefix}{fy}-K", fy, "FY",
                form="10-K", filed=f"{fy}-12-15"),
        ]

    facts = companyfacts(
        {
            "NetCashProvidedByUsedInOperatingActivities": _oct_ytd(2025, 10, 20, 30, 40, "O")
            + _oct_ytd(2024, 5, 6, 7, 8, "P"),
            "CashAndCashEquivalentsAtCarryingValue": [
                _instant("2025-07-31", 9, "q3", 2025, "Q3"),
                _instant("2025-10-31", 11, "fy", 2025, "FY", form="10-K", filed="2025-12-15"),
            ],
        }
    )
    analysis = analyze_layer3_facts(facts)
    by_end = {q["end"]: q for q in analysis.metrics["ocf"]["quarters"]}
    assert by_end["2025-10-31"]["value"] == 40
    assert by_end["2025-10-31"]["formula"] == "FY − 9M YTD"
    assert analysis.metrics["cash"]["end"] == "2025-10-31"
    assert analysis.metrics["cash"]["value"] == 11
    assert analysis.data_as_of == "2025-10-31"


def test_fifty_two_week_balance_sheet_matches_calendar_slot():
    """NVDA-like 52/53-week instants (07-26) must align to a 07-31 fiscal slot."""
    concepts = _two_year_income()
    cash_ends = [
        ("2024-03-26", 2024, "Q1", "10-Q"),
        ("2024-06-25", 2024, "Q2", "10-Q"),
        ("2024-09-24", 2024, "Q3", "10-Q"),
        ("2024-12-26", 2024, "FY", "10-K"),
        ("2025-03-25", 2025, "Q1", "10-Q"),
        ("2025-06-24", 2025, "Q2", "10-Q"),
        ("2025-09-25", 2025, "Q3", "10-Q"),
        ("2025-12-26", 2025, "FY", "10-K"),
    ]
    ar_vals = [30, 31, 32, 33, 34, 35, 36, 40]
    concepts["CashAndCashEquivalentsAtCarryingValue"] = [
        _instant(end, val, f"cash-{end}", fy, fp, form=form)
        for (end, fy, fp, form), val in zip(cash_ends, [10, 11, 12, 13, 14, 15, 16, 20], strict=True)
    ]
    concepts["AccountsReceivableNetCurrent"] = [
        _instant(end, val, f"ar-{end}", fy, fp, form=form)
        for (end, fy, fp, form), val in zip(cash_ends, ar_vals, strict=True)
    ]
    facts = companyfacts(concepts)
    analysis = analyze_layer3_facts(facts)
    cash = analysis.metrics["cash"]
    assert cash["value"] == 20
    assert cash["end"] == "2025-12-26"
    assert [h["value"] for h in cash["history"]] == [20, 16, 15, 14, 13, 12, 11, 10]
    assert cash["history"][0]["end"] == "2025-12-26"
    dso = analysis.metrics["dso"]
    assert dso["status"] == "extracted"
    assert dso["value"] is not None
    assert dso["inputs"]["begin"] == 33
    assert dso["inputs"]["close"] == 40


def test_derived_never_labeled_statement_verified():
    facts = companyfacts(_two_year_income())
    analysis = analyze_layer3_facts(facts)
    dumped = analysis.to_dict()
    assert dumped["scoring"] is None
    blob = str(dumped)
    assert "statement_verified" not in blob
    assert analysis.metrics["fcf"]["calculationMethod"] == "derived"
    assert analysis.metrics["grossMargin"]["verification"] == "not_checked"
