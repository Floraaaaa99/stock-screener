"""8-K figures merge into the shared Company Facts dataset used by all layers."""

from __future__ import annotations

from datetime import date

from fixtures.eight_k import GAAP_EARNINGS_EXHIBIT, MISSING_CF_EXHIBIT
from helpers import companyfacts

from screener_pipeline.eight_k_extract import EightKExtraction, ExtractedMetric, extract_earnings_release
from screener_pipeline.eight_k_facts import merge_extraction_into_companyfacts
from screener_pipeline.sec.facts import extract_duration_facts, extract_instant_facts, extract_revenue_facts


def _metric(**kwargs) -> ExtractedMetric:
    defaults = dict(
        key="revenue",
        value=10.0,
        unit="USD",
        scale=1.0,
        label="Revenue",
        period_kind="quarterly",
        fiscal_year=2026,
        fiscal_quarter=3,
        period_end=date(2026, 9, 30),
        period_start=date(2026, 7, 1),
        gaap=True,
    )
    defaults.update(kwargs)
    return ExtractedMetric(**defaults)


def _extract(metrics: dict[str, ExtractedMetric]) -> EightKExtraction:
    return EightKExtraction(
        status="extracted",
        reason=None,
        item_202=True,
        exhibit_name="ex991.htm",
        exhibit_url="https://www.sec.gov/ex991.htm",
        filing_url="https://www.sec.gov/index.htm",
        fiscal_year=2026,
        fiscal_quarter=3,
        period_end=date(2026, 9, 30),
        metrics=metrics,
    )


def test_merge_writes_available_metrics_and_skips_missing_and_nongaap():
    extract = _extract(
        {
            "revenue": _metric(key="revenue", value=51_242_000_000),
            "netIncome": _metric(key="netIncome", value=18_300_000_000, label="Net income"),
            "freeCashFlow": _metric(
                key="freeCashFlow",
                value=16_700_000_000,
                gaap=False,
                method="derived",
                formula="OCF − CapEx",
            ),
            "companyReportedFreeCashFlow": _metric(
                key="companyReportedFreeCashFlow",
                value=-2_120_000_000,
                gaap=False,
            ),
        }
    )
    merged = merge_extraction_into_companyfacts(
        companyfacts({"Revenues": []}, cik=1, name="AAA"),
        extract,
        accn="0000000001-26-000024",
        form="8-K",
        filed="2026-10-21",
    )
    gaap = merged["facts"]["us-gaap"]
    rev = gaap["Revenues"]["units"]["USD"]
    assert rev[0]["val"] == 51_242_000_000
    assert rev[0]["form"] == "8-K"
    assert rev[0]["start"] == "2026-07-01"
    assert gaap["NetIncomeLoss"]["units"]["USD"][0]["val"] == 18_300_000_000
    assert "InventoryNet" not in gaap
    assert "GrossProfit" not in gaap
    assert all("FreeCashFlow" not in name for name in gaap)


def test_missing_cash_flow_exhibit_does_not_write_zero_ocf():
    extracted = extract_earnings_release(
        MISSING_CF_EXHIBIT,
        item_202=True,
        exhibit_name="ex991.htm",
        exhibit_url="https://www.sec.gov/ex991.htm",
        filing_url="https://www.sec.gov/index.htm",
    )
    merged = merge_extraction_into_companyfacts(
        companyfacts({"Revenues": []}, cik=1, name="AAA"),
        extracted,
        accn="0000000001-26-000024",
        form="8-K",
        filed="2026-10-21",
    )
    gaap = merged["facts"]["us-gaap"]
    assert gaap["Revenues"]["units"]["USD"][0]["val"] == 10_000_000
    assert "NetCashProvidedByUsedInOperatingActivities" not in gaap
    assert "PaymentsToAcquirePropertyPlantAndEquipment" not in gaap
    rf = extract_duration_facts(merged, ["NetCashProvidedByUsedInOperatingActivities"])
    assert rf.by_concept == {}


def test_gaap_exhibit_is_readable_as_shared_duration_and_instant_facts():
    extracted = extract_earnings_release(
        GAAP_EARNINGS_EXHIBIT,
        item_202=True,
        exhibit_name="ex991.htm",
        exhibit_url="https://www.sec.gov/ex991.htm",
        filing_url="https://www.sec.gov/index.htm",
    )
    merged = merge_extraction_into_companyfacts(
        companyfacts({"Revenues": []}, cik=1, name="AAA"),
        extracted,
        accn="0000000001-26-000024",
        form="8-K",
        filed="2026-10-21",
    )
    rf = extract_revenue_facts(merged)
    assert rf.by_concept["Revenues"][0].val == 51_242_000_000
    assert rf.by_concept["Revenues"][0].form == "8-K"
    cash = extract_instant_facts(merged, ["CashAndCashEquivalentsAtCarryingValue"])
    assert cash["CashAndCashEquivalentsAtCarryingValue"][0].val == 44_400_000_000
    assert "start" not in merged["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"]["units"]["USD"][0]
