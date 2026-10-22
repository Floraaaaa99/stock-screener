from __future__ import annotations

from fixtures.eight_k import (
    GAAP_EARNINGS_EXHIBIT,
    MISSING_CF_EXHIBIT,
    UNITS_SIGNS_EXHIBIT,
    YTD_ONLY_EXHIBIT,
)

from screener_pipeline.eight_k_extract import extract_earnings_release, parse_number


def _extract(html: str):
    return extract_earnings_release(
        html,
        item_202=True,
        exhibit_name="ex991.htm",
        exhibit_url="https://www.sec.gov/ex991.htm",
        filing_url="https://www.sec.gov/index.htm",
    )


def test_quarterly_gaap_not_ytd_or_nongaap():
    result = _extract(GAAP_EARNINGS_EXHIBIT)
    assert result.status == "extracted"
    assert result.fiscal_year == 2026
    assert result.fiscal_quarter == 3
    m = result.metrics
    assert m["revenue"].value == 51_242_000_000
    assert m["costOfRevenue"].value == 9_100_000_000
    assert m["grossProfit"].value == 42_142_000_000
    assert m["operatingIncome"].value == 20_500_000_000
    assert m["netIncome"].value == 18_300_000_000
    assert m["dilutedEps"].value == 7.25
    assert m["dilutedEps"].unit == "USD/shares"
    assert m["operatingCashFlow"].value == 25_100_000_000
    assert m["capitalExpenditures"].value == 8_400_000_000
    assert m["freeCashFlow"].value == 16_700_000_000
    assert m["freeCashFlow"].formula == "OCF − CapEx"
    assert m["cash"].value == 44_400_000_000
    assert m["inventory"].value == 1_200_000_000
    assert m["totalAssets"].value == 280_000_000_000
    assert m["totalLiabilities"].value == 90_000_000_000
    assert m["totalDebt"].value == 30_000_000_000
    # Adjusted net income / EBITDA must never replace GAAP.
    assert m["netIncome"].value != 21_000_000_000
    assert all(item.gaap for item in m.values())
    assert all(item.period_kind in {"quarterly", "instant"} for item in m.values())


def test_ytd_only_is_not_treated_as_quarterly():
    result = _extract(YTD_ONLY_EXHIBIT)
    assert result.status == "failed"
    assert result.reason == "no_gaap_quarterly_metrics"
    assert result.metrics == {}


def test_missing_cash_flow_stays_missing():
    result = _extract(MISSING_CF_EXHIBIT)
    assert result.status == "extracted"
    assert result.metrics["revenue"].value == 10_000_000
    assert result.metrics["netIncome"].value == 2_000_000
    assert "operatingCashFlow" not in result.metrics
    assert "capitalExpenditures" not in result.metrics
    assert "cash" not in result.metrics


def test_thousands_and_parentheses():
    result = _extract(UNITS_SIGNS_EXHIBIT)
    assert result.status == "extracted"
    assert result.metrics["revenue"].value == 1_234_500
    assert result.metrics["operatingIncome"].value == -88_000
    assert result.metrics["netIncome"].value == -101_500


def test_parse_number_rejects_percent_and_blank():
    assert parse_number("(1,234)") == -1234
    assert parse_number("—") is None
    assert parse_number("12%") is None
    assert parse_number("n/a") is None
    assert parse_number("0") == 0.0
