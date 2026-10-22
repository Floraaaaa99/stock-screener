from __future__ import annotations

from datetime import date

from fixtures.eight_k import (
    GAAP_EARNINGS_EXHIBIT,
    INVESTOR_DECK,
    ITEM_202_BODY,
    ITEM_202_NO_TABLES,
    ITEM_801_BODY,
    META_ACCN,
    META_CIK,
    META_Q3_2026_REAL_EXHIBIT,
    earnings_documents,
    item202_presentation_only,
    unrelated_documents,
)

from screener_pipeline.eight_k_extract import extract_earnings_release
from screener_pipeline.eight_k_update import collect_earnings_jobs, process_earnings_filing
from screener_pipeline.sec.daily_index import DailyFiling
from screener_pipeline.sec.eight_k import (
    discover_earnings_exhibit,
    has_item_202,
    parse_index_htm,
    select_earnings_exhibit,
)


def _fetch(docs: dict[str, str]):
    def fetch(_cik: str, _accn: str, name: str) -> str | None:
        return docs.get(name)
    return fetch


def _filing(cik: str, accn: str, form: str = "8-K") -> DailyFiling:
    return DailyFiling(cik, "Test", form, date(2026, 10, 21), f"{accn}.txt", accn)


def test_item_202_detected_and_unrelated_rejected():
    assert has_item_202(ITEM_202_BODY) is True
    assert has_item_202(ITEM_801_BODY) is False
    accn = "0000000001-26-000100"
    found = discover_earnings_exhibit("0000000001", accn, _fetch(earnings_documents(accn)))
    assert found.is_earnings is True
    assert found.exhibit is not None
    assert found.exhibit.name == "ex991.htm"
    unrelated = discover_earnings_exhibit("0000000001", accn, _fetch(unrelated_documents(accn)))
    assert unrelated.item_202 is False
    assert unrelated.exhibit is None
    assert unrelated.reason == "not_item_202"


def test_presentation_exhibit_is_not_selected():
    accn = "0000000001-26-000101"
    docs = parse_index_htm(
        item202_presentation_only(accn)[f"{accn}-index.htm"],
        "0000000001",
        accn,
    )
    assert select_earnings_exhibit(docs, peek_text={"ex991.htm": INVESTOR_DECK}) is None
    discovered = discover_earnings_exhibit("0000000001", accn, _fetch(item202_presentation_only(accn)))
    assert discovered.item_202 is True
    assert discovered.exhibit is None


def test_prefers_ex_99_1_over_investor_deck():
    accn = "0000000001-26-000102"
    docs = earnings_documents(
        accn,
        extra_exhibits=[("EX-99.2", "Investor Presentation", "ex992.htm", INVESTOR_DECK)],
    )
    found = discover_earnings_exhibit("0000000001", accn, _fetch(docs))
    assert found.exhibit is not None
    assert found.exhibit.name == "ex991.htm"


def test_eight_k_amendment_uses_same_item_202_path():
    accn = "0000000001-26-000103"
    docs = earnings_documents(accn, form="8-K/A")
    found = discover_earnings_exhibit("0000000001", accn, _fetch(docs), form="8-K/A")
    assert found.item_202 is True
    assert found.exhibit is not None
    result = process_earnings_filing(_filing("0000000001", accn, "8-K/A"), _fetch(docs), None)
    assert result["status"] == "extracted"
    assert result["form"] == "8-K/A"


def test_item_202_without_tables_is_failed_not_invented():
    accn = "0000000001-26-000104"
    docs = earnings_documents(accn, exhibit=ITEM_202_NO_TABLES)
    result = process_earnings_filing(_filing("0000000001", accn), _fetch(docs), None)
    assert result["status"] == "failed"
    assert result["metrics"] == {}


def test_meta_q3_2026_accession_extracts_when_exhibit_present():
    docs = earnings_documents(META_ACCN, exhibit=META_Q3_2026_REAL_EXHIBIT)
    result = process_earnings_filing(_filing(META_CIK, META_ACCN), _fetch(docs), None)
    assert result["status"] == "extracted"
    assert result["fiscalYear"] == 2026
    assert result["fiscalQuarter"] == 3
    assert result["metrics"]["revenue"]["value"] == 64_601_000_000
    assert result["metrics"]["netIncome"]["value"] == 9_860_000_000
    assert result["metrics"]["operatingIncome"]["value"] == 12_988_000_000
    assert result["metrics"]["dilutedEps"]["value"] == 3.83
    assert result["metrics"]["operatingCashFlow"]["value"] == 32_786_000_000
    assert result["metrics"]["capitalExpenditures"]["value"] == 33_942_000_000
    assert result["metrics"]["freeCashFlow"]["value"] == -1_156_000_000
    assert result["metrics"]["freeCashFlow"]["gaap"] is False
    assert result["metrics"]["companyReportedFreeCashFlow"]["value"] == -2_120_000_000
    extracted = extract_earnings_release(
        GAAP_EARNINGS_EXHIBIT,
        item_202=True,
        exhibit_name="ex991.htm",
        exhibit_url="https://example.test/ex991.htm",
        filing_url="https://example.test/index.htm",
    )
    assert extracted.status == "extracted"


def test_collect_earnings_jobs_does_not_scan_unrelated_recorded_8ks():
    processed = {
        META_ACCN: {
            "cik": META_CIK,
            "form": "8-K",
            "filed": "2026-10-21",
            "status": "recorded_8k",
        },
        "0000000001-26-000111": {
            "cik": "0000000001",
            "form": "8-K",
            "filed": "2026-10-10",
            "status": "recorded_8k",
        },
    }
    by_cik = {META_CIK: ["META"], "0000000001": ["AAA"]}
    jobs = collect_earnings_jobs(
        [],
        processed,
        {},
        as_of=date(2026, 10, 22),
        by_cik=by_cik,
    )
    assert [job.accn for job in jobs] == [META_ACCN]
    jobs = collect_earnings_jobs(
        [],
        processed,
        {
            "0000000001-26-000111": {
                "cik": "0000000001",
                "form": "8-K",
                "filed": "2026-10-10",
                "status": "failed",
                "attempts": 1,
            }
        },
        as_of=date(2026, 10, 22),
        by_cik=by_cik,
    )
    assert {job.accn for job in jobs} == {META_ACCN, "0000000001-26-000111"}
