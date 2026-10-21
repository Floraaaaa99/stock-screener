from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import requests

from screener_pipeline.sec.daily_index import (
    accession_from_filename,
    collect_period_filings,
    fetch_master_idx,
    lookback_dates,
    master_idx_url,
    parse_master_idx,
)

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


def test_fetch_master_idx_caches_404(tmp_path: Path):
    day = date(2026, 10, 18)
    url = master_idx_url(day)
    http = FakeHttp({url: FakeResp(404)})
    assert fetch_master_idx(http, day, cache_dir=tmp_path) is None
    marker = tmp_path / "master.20261018.idx.404"
    assert marker.exists()
    http2 = FakeHttp({})
    assert fetch_master_idx(http2, day, cache_dir=tmp_path) is None
    assert http2.urls == []


def test_collect_period_filings_skips_missing_days(tmp_path: Path):
    as_of = date(2026, 10, 20)
    present = master_idx_url(as_of)
    http = FakeHttp({present: FakeResp(200, MASTER_IDX)})
    filings, found, missing = collect_period_filings(http, as_of, 3, cache_dir=tmp_path)
    assert as_of.isoformat() in found
    assert date(2026, 10, 19).isoformat() in missing
    assert {f.accn for f in filings} >= {"0000320193-26-000111", "0001193125-26-000099"}
