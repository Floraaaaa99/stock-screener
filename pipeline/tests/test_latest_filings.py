from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import requests

from screener_pipeline.sec.latest_filings import (
    SEC_CURRENT_PAGE_SIZE,
    current_atom_url,
    dateb_from_accepted,
    fetch_latest_filings,
    parse_current_atom,
    start_from_url,
)

ATOM_ENTRY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Latest Filings from EDGAR</title>
  <entry>
    <title>{form} - {name} ({cik}) (Filer)</title>
    <link href="https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{accn}-index.htm"/>
    <summary type="html">&lt;b&gt;Filed:&lt;/b&gt; {filed} &lt;b&gt;AccNo:&lt;/b&gt; {accn}</summary>
    <updated>{updated}</updated>
    <category term="{form}" />
  </entry>
</feed>
"""

EMPTY_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Latest Filings from EDGAR</title>
</feed>
"""


def _atom(*, form: str, name: str, cik: str, accn: str, filed: str, updated: str) -> str:
    return ATOM_ENTRY.format(
        form=form,
        name=name,
        cik=cik,
        cik_int=int(cik),
        accn=accn,
        accn_nodash=accn.replace("-", ""),
        filed=filed,
        updated=updated,
    )


class FakeResp:
    def __init__(self, status: int, text: str = ""):
        self.status_code = status
        self.content = text.encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeHttp:
    def __init__(self, by_url: dict[str, FakeResp]):
        self.by_url = by_url
        self.urls: list[str] = []

    def get(self, url: str) -> FakeResp:
        self.urls.append(url)
        if url not in self.by_url:
            return FakeResp(404)
        return self.by_url[url]


def test_getcurrent_is_documented_as_same_day_not_historical():
    from screener_pipeline.sec import latest_filings as mod

    assert "not a historical archive" in (mod.__doc__ or "")
    assert "getcurrent" in (mod.__doc__ or "")


def test_dateb_from_accepted_is_compact_local_stamp():
    stamp = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    assert dateb_from_accepted(stamp) == "20261021120000"


def test_current_atom_url_caps_count_at_sec_page_size():
    url = current_atom_url("10-Q", start=40, count=100)
    assert "count=40" in url
    assert "start=40" in url
    assert "action=getcurrent" in url
    assert "type=10-Q" in url
    assert start_from_url(url) == 40


def test_parse_current_atom_reads_acceptance_and_accession():
    xml = _atom(
        form="10-Q",
        name="Apple Inc",
        cik="0000320193",
        accn="0000320193-26-000111",
        filed="2026-10-20",
        updated="2026-10-20T16:15:00-04:00",
    )
    rows = parse_current_atom(xml)
    assert len(rows) == 1
    row = rows[0]
    assert row.cik == "0000320193"
    assert row.form == "10-Q"
    assert row.accn == "0000320193-26-000111"
    assert row.filed == date(2026, 10, 20)
    assert row.accepted is not None
    assert row.accepted.hour == 16
    assert row.accepted.minute == 15
    assert row.source == "latest"


def test_parse_current_atom_skips_unwanted_forms_and_bad_xml():
    xml = _atom(
        form="4",
        name="Insider",
        cik="0000000001",
        accn="0000000001-26-000001",
        filed="2026-10-20",
        updated="2026-10-20T12:00:00-04:00",
    )
    assert parse_current_atom(xml) == []
    assert parse_current_atom("not-xml") == []
    assert parse_current_atom("") == []


def test_parse_8k_is_kept():
    xml = _atom(
        form="8-K",
        name="Example Corp",
        cik="0000789019",
        accn="0001193125-26-000001",
        filed="2026-10-21",
        updated="2026-10-21T09:01:00-04:00",
    )
    rows = parse_current_atom(xml)
    assert [r.form for r in rows] == ["8-K"]


def test_fetch_latest_filings_pages_until_empty():
    page0 = current_atom_url("10-Q", start=0, count=SEC_CURRENT_PAGE_SIZE)
    short = FakeHttp(
        {
            page0: FakeResp(
                200,
                _atom(
                    form="10-Q",
                    name="Apple Inc",
                    cik="0000320193",
                    accn="0000320193-26-000111",
                    filed="2026-10-21",
                    updated="2026-10-21T10:00:00-04:00",
                ),
            ),
        }
    )
    rows, stats = fetch_latest_filings(short, forms=("10-Q",), page_size=40, max_pages=5)
    assert [r.accn for r in rows] == ["0000320193-26-000111"]
    assert stats["pages"] == 1
    assert stats["hits"] == 1
    assert page0 in short.urls

    page_size1 = current_atom_url("10-Q", start=0, count=1)
    page_size1_next = current_atom_url("10-Q", start=1, count=1)
    paged = FakeHttp(
        {
            page_size1: FakeResp(
                200,
                _atom(
                    form="10-Q",
                    name="Apple Inc",
                    cik="0000320193",
                    accn="0000320193-26-000111",
                    filed="2026-10-21",
                    updated="2026-10-21T10:00:00-04:00",
                ),
            ),
            page_size1_next: FakeResp(200, EMPTY_FEED),
        }
    )
    rows2, stats2 = fetch_latest_filings(paged, forms=("10-Q",), page_size=1, max_pages=5)
    assert [r.accn for r in rows2] == ["0000320193-26-000111"]
    assert stats2["pages"] == 2
    assert page_size1_next in paged.urls


def test_fetch_latest_filings_falls_back_to_dateb_when_start_repeats():
    first = _atom(
        form="8-K",
        name="Example Corp",
        cik="0000789019",
        accn="0001193125-26-000010",
        filed="2026-10-21",
        updated="2026-10-21T12:00:00-04:00",
    )
    older = _atom(
        form="8-K",
        name="Other Corp",
        cik="0000000002",
        accn="0000000002-26-000002",
        filed="2026-10-21",
        updated="2026-10-21T09:00:00-04:00",
    )
    start0 = current_atom_url("8-K", start=0, count=1)
    start1 = current_atom_url("8-K", start=1, count=1)
    dateb_url = current_atom_url("8-K", start=0, count=1, dateb="20261021120000")
    dateb_next = current_atom_url("8-K", start=0, count=1, dateb="20261021090000")
    http = FakeHttp(
        {
            start0: FakeResp(200, first),
            start1: FakeResp(200, first),
            dateb_url: FakeResp(200, older),
            dateb_next: FakeResp(200, EMPTY_FEED),
        }
    )
    rows, stats = fetch_latest_filings(http, forms=("8-K",), page_size=1, max_pages=5)
    assert {r.accn for r in rows} == {"0001193125-26-000010", "0000000002-26-000002"}
    assert stats["pages"] >= 2
    assert any("dateb=20261021120000" in url for url in http.urls)


def test_fetch_latest_filings_raises_on_5xx():
    url = current_atom_url("10-K", start=0, count=40)
    http = FakeHttp({url: FakeResp(503, "unavailable")})
    with pytest.raises(requests.HTTPError):
        fetch_latest_filings(http, forms=("10-K",), max_pages=2)
