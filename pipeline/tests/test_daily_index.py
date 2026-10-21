from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import requests

from screener_pipeline.sec.daily_index import (
    accession_from_filename,
    collect_period_filings,
    fetch_master_idx,
    fetch_master_idx_status,
    index_data_row_count,
    index_dates,
    index_is_complete,
    lookback_dates,
    master_idx_url,
    parse_master_idx,
    recent_business_days,
)
from screener_pipeline.sec.facts import DOMESTIC_FORMS

MASTER_IDX = """Description:           Daily Index of EDGAR Documents
Last Data Received:    Oct 20, 2026
Comments:              webmaster@sec.gov

CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
0000320193|Apple Inc.|10-Q|20261020|edgar/data/320193/0000320193-26-000111.txt
0000789019|MICROSOFT CORP|8-K|20261020|edgar/data/789019/0001193125-26-000001.txt
0001045810|NVIDIA CORP|10-Q/A|2026-10-20|edgar/data/1045810/0001045810-26-000222.txt
0000789019|MICROSOFT CORP|10-K|20261020|edgar/data/789019/0001193125-26-000099.txt
not-a-cik|Bad|10-Q|20261020|edgar/data/1/0000000001-26-000001.txt
"""

INCOMPLETE_IDX = """Description:           Daily Index of EDGAR Documents
Last Data Received:    Oct 20, 2026
"""

HEADER_ONLY_IDX = """Description:           Daily Index of EDGAR Documents
Last Data Received:    Oct 20, 2026
Comments:              webmaster@sec.gov

CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
"""

PARTIAL_IDX = """Description:           Daily Index of EDGAR Documents
Last Data Received:    Oct 20, 2026

CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
0000320193|Apple Inc.|10-Q|20261020|edgar/data/320193/0000320193-26-000111.txt
"""


class FakeResp:
    def __init__(self, status: int, text: str = ""):
        self.status_code = status
        self.content = text.encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code != 404:
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


def test_lookback_dates_are_inclusive():
    days = lookback_dates(date(2026, 10, 21), 3)
    assert days == [date(2026, 10, 21), date(2026, 10, 20), date(2026, 10, 19)]


def test_lookback_rejects_empty_window():
    with pytest.raises(ValueError):
        lookback_dates(date(2026, 10, 21), 0)


def test_master_idx_url_uses_calendar_quarter():
    assert master_idx_url(date(2026, 10, 20)).endswith("/2026/QTR4/master.20261020.idx")
    assert master_idx_url(date(2026, 1, 5)).endswith("/2026/QTR1/master.20260105.idx")
    assert master_idx_url(date(2026, 4, 1)).endswith("/2026/QTR2/master.20260401.idx")


def test_parse_master_idx_keeps_domestic_forms_and_skips_8k():
    rows = parse_master_idx(MASTER_IDX)
    forms = {r.form for r in rows}
    accns = {r.accn for r in rows}
    assert forms == {"10-Q", "10-Q/A", "10-K"}
    assert "0000320193-26-000111" in accns
    assert "0001045810-26-000222" in accns
    assert "0001193125-26-000099" in accns
    assert "0001193125-26-000001" not in accns
    apple = next(r for r in rows if r.cik == "0000320193")
    assert apple.filed == date(2026, 10, 20)


def test_accession_from_filename_accepts_underscore():
    assert accession_from_filename("edgar/data/320193/0000320193_26_000111.txt") == "0000320193-26-000111"


def test_index_is_complete_requires_header_and_rows():
    assert index_is_complete(MASTER_IDX)
    assert index_is_complete(PARTIAL_IDX)
    assert not index_is_complete(INCOMPLETE_IDX)
    assert not index_is_complete(HEADER_ONLY_IDX)
    assert not index_is_complete("")
    assert index_data_row_count(MASTER_IDX) >= 4
    assert index_data_row_count(HEADER_ONLY_IDX) == 0


def test_recent_business_days_skips_weekends():
    assert recent_business_days(date(2026, 10, 21), 3) == [
        date(2026, 10, 21),
        date(2026, 10, 20),
        date(2026, 10, 19),
    ]
    assert recent_business_days(date(2026, 10, 19), 3) == [
        date(2026, 10, 19),
        date(2026, 10, 16),
        date(2026, 10, 15),
    ]
    assert recent_business_days(date(2026, 10, 18), 3) == [
        date(2026, 10, 16),
        date(2026, 10, 15),
        date(2026, 10, 14),
    ]


def test_fetch_master_idx_does_not_cache_404(tmp_path: Path):
    day = date(2026, 10, 18)
    url = master_idx_url(day)
    http = FakeHttp({url: FakeResp(404)})
    assert fetch_master_idx(http, day, cache_dir=tmp_path) is None
    assert not (tmp_path / "master.20261018.idx").exists()
    assert not (tmp_path / "master.20261018.idx.404").exists()
    http2 = FakeHttp({url: FakeResp(404)})
    assert fetch_master_idx(http2, day, cache_dir=tmp_path) is None
    assert http2.urls == [url]


def test_fetch_master_idx_does_not_cache_incomplete(tmp_path: Path):
    day = date(2026, 10, 20)
    url = master_idx_url(day)
    http = FakeHttp({url: FakeResp(200, INCOMPLETE_IDX)})
    text, status = fetch_master_idx_status(http, day, cache_dir=tmp_path)
    assert text is None
    assert status == "incomplete"
    assert not (tmp_path / "master.20261020.idx").exists()


def test_fetch_master_idx_does_not_cache_header_only(tmp_path: Path):
    day = date(2026, 10, 20)
    url = master_idx_url(day)
    http = FakeHttp({url: FakeResp(200, HEADER_ONLY_IDX)})
    text, status = fetch_master_idx_status(http, day, cache_dir=tmp_path)
    assert text is None
    assert status == "incomplete"
    assert not (tmp_path / "master.20261020.idx").exists()


def test_header_only_cache_is_discarded_and_refetched(tmp_path: Path):
    day = date(2026, 10, 20)
    url = master_idx_url(day)
    cached = tmp_path / "master.20261020.idx"
    cached.write_text(HEADER_ONLY_IDX, encoding="utf-8")
    http = FakeHttp({url: FakeResp(200, MASTER_IDX)})
    text, status = fetch_master_idx_status(http, day, cache_dir=tmp_path)
    assert status == "ok"
    assert text is not None and "0000320193" in text
    assert http.urls == [url]
    assert index_is_complete(cached.read_text(encoding="utf-8"))


def test_fetch_master_idx_refetches_stale_incomplete_cache(tmp_path: Path):
    day = date(2026, 10, 20)
    url = master_idx_url(day)
    cached = tmp_path / "master.20261020.idx"
    cached.write_text(INCOMPLETE_IDX, encoding="utf-8")
    http = FakeHttp({url: FakeResp(200, MASTER_IDX)})
    text, status = fetch_master_idx_status(http, day, cache_dir=tmp_path)
    assert status == "ok"
    assert text is not None and "0000320193" in text
    assert http.urls == [url]


def test_fetch_master_idx_raises_on_5xx(tmp_path: Path):
    day = date(2026, 10, 20)
    url = master_idx_url(day)
    http = FakeHttp({url: FakeResp(503, "unavailable")})
    with pytest.raises(requests.HTTPError):
        fetch_master_idx(http, day, cache_dir=tmp_path)


def test_index_dates_extends_for_missed_sync():
    days = index_dates(date(2026, 10, 21), 10, since=date(2026, 9, 29))
    assert date(2026, 9, 29) in days
    assert date(2026, 10, 21) in days
    assert date(2026, 10, 1) in days
    assert len(days) == (date(2026, 10, 21) - date(2026, 9, 29)).days + 1


def test_recent_cached_index_is_refetched_and_can_grow(tmp_path: Path):
    as_of = date(2026, 10, 21)
    url = master_idx_url(as_of)
    cached = tmp_path / "master.20261021.idx"
    cached.write_text(PARTIAL_IDX, encoding="utf-8")
    http = FakeHttp({url: FakeResp(200, MASTER_IDX)})
    filings, found, unreconciled = collect_period_filings(
        http,
        as_of,
        1,
        cache_dir=tmp_path,
        revalidate_business_days=3,
    )
    assert http.urls == [url]
    assert as_of.isoformat() in found
    assert as_of.isoformat() in unreconciled
    assert {f.accn for f in filings} >= {"0000320193-26-000111", "0001193125-26-000099"}
    assert index_data_row_count(cached.read_text(encoding="utf-8")) >= 4


def test_older_complete_cache_is_reused(tmp_path: Path):
    as_of = date(2026, 10, 21)
    old = date(2026, 10, 12)
    path = tmp_path / "master.20261012.idx"
    path.write_text(MASTER_IDX, encoding="utf-8")
    http = FakeHttp({})
    filings, found, unreconciled = collect_period_filings(
        http,
        as_of,
        1,
        cache_dir=tmp_path,
        extra_dates=[old],
        revalidate_business_days=3,
    )
    assert http.urls == [master_idx_url(as_of)]
    assert old.isoformat() in found
    assert old.isoformat() not in unreconciled
    assert "0000320193-26-000111" in {f.accn for f in filings}


def test_collect_period_filings_keeps_recent_missing_unreconciled(tmp_path: Path):
    as_of = date(2026, 10, 20)
    present = master_idx_url(as_of)
    http = FakeHttp({present: FakeResp(200, MASTER_IDX)})
    filings, found, unreconciled = collect_period_filings(http, as_of, 3, cache_dir=tmp_path)
    assert as_of.isoformat() in found
    assert as_of.isoformat() in unreconciled
    assert date(2026, 10, 19).isoformat() in unreconciled
    assert date(2026, 10, 18).isoformat() not in unreconciled
    assert {f.accn for f in filings} >= {
        "0000320193-26-000111",
        "0001193125-26-000099",
        "0001193125-26-000001",
    }


def test_collect_period_filings_older_404_is_checked_empty(tmp_path: Path):
    as_of = date(2026, 10, 21)
    present = master_idx_url(as_of)
    http = FakeHttp({present: FakeResp(200, MASTER_IDX)})
    _filings, _found, unreconciled = collect_period_filings(
        http,
        as_of,
        10,
        cache_dir=tmp_path,
        revalidate_business_days=3,
    )
    assert date(2026, 10, 21).isoformat() in unreconciled
    assert date(2026, 10, 20).isoformat() in unreconciled
    assert date(2026, 10, 19).isoformat() in unreconciled
    assert date(2026, 10, 12).isoformat() not in unreconciled


def test_collect_period_filings_can_skip_8k_when_asked(tmp_path: Path):
    as_of = date(2026, 10, 20)
    http = FakeHttp({master_idx_url(as_of): FakeResp(200, MASTER_IDX)})
    filings, _found, _unreconciled = collect_period_filings(
        http,
        as_of,
        1,
        cache_dir=tmp_path,
        forms=set(DOMESTIC_FORMS),
    )
    assert "0001193125-26-000001" not in {f.accn for f in filings}


def test_collect_period_filings_retries_extra_unreconciled_dates(tmp_path: Path):
    as_of = date(2026, 10, 21)
    extra = date(2026, 10, 5)
    http = FakeHttp({master_idx_url(extra): FakeResp(200, MASTER_IDX)})
    filings, found, unreconciled = collect_period_filings(
        http,
        as_of,
        1,
        cache_dir=tmp_path,
        extra_dates=[extra],
        revalidate_business_days=3,
    )
    assert extra.isoformat() in found
    assert as_of.isoformat() in unreconciled
    assert "0000320193-26-000111" in {f.accn for f in filings}
