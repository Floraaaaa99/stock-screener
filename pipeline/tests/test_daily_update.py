from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests
from helpers import calendar_year, companyfacts, raw

from screener_pipeline.cache import write_json_atomic, write_json_if_changed
from screener_pipeline.cli import main
from screener_pipeline.daily_update import DailyUpdateError, discovery_since, pacific_today, run_daily_update
from screener_pipeline.sec.daily_index import DailyFiling, collect_period_filings
from screener_pipeline.sec.facts import Fact


def _raw_facts(facts: list[Fact]) -> list[dict]:
    return [
        {
            "start": f.start.isoformat(),
            "end": f.end.isoformat(),
            "val": f.val,
            "accn": f.accn,
            "fy": f.fy,
            "fp": f.fp,
            "form": f.form,
            "filed": f.filed.isoformat(),
        }
        for f in facts
    ]


def _revenue_payload(cik: int, name: str, extra_q: Fact | None = None) -> dict:
    facts = calendar_year(2024, 10, 11, 12, 13, prefix="B") + calendar_year(2025, 14, 15, 16, 17, prefix="A")
    if extra_q:
        facts.append(extra_q)
    return companyfacts({"Revenues": _raw_facts(facts)}, cik=cik, name=name)


def _company(
    ticker: str,
    cik: str,
    *,
    current: float | None = 62.0,
    previous: float | None = 46.0,
    growth: float | None = 34.78,
    missing: bool = False,
) -> dict:
    return {
        "schemaVersion": 2,
        "ticker": ticker,
        "name": ticker,
        "exchange": "NASDAQ",
        "securityType": "common",
        "cik": cik,
        "secName": ticker,
        "sic": {
            "code": "7372",
            "description": "Software",
            "majorGroup": "Business Services",
            "label": "7372 — Software",
        },
        "ttm": {
            "current": current,
            "previous": previous,
            "growthPct": growth,
            "reason": None if growth is not None else "insufficient_quarters",
            "currency": "USD",
        },
        "revenue": {
            "status": "ok" if not missing else "insufficient_quarters",
            "currency": "USD",
            "concept": "Revenues",
            "quarters": [
                {
                    "fiscalYear": 2026,
                    "fiscalQuarter": 1,
                    "start": "2026-01-01",
                    "end": "2026-03-31",
                    "ttm": "current",
                    "missing": missing,
                    "value": None if missing else current,
                }
            ],
        },
        "earnings": {"status": "ok", "currency": "USD", "quarters": []},
        "classificationIssues": [],
    }


def _meta(*, mode: str = "sample", listings: int = 1, eligible: int = 100, growth: int = 1) -> dict:
    return {
        "schemaVersion": 2,
        "generatedAt": "2026-10-01T00:00:00+00:00",
        "dataset": {"mode": mode, "id": "test", "name": "Test", "description": ""},
        "run": {"status": "complete", "listingsTarget": listings, "listingsDone": listings, "pending": []},
        "universe": {
            "source": "test",
            "exchanges": ["NASDAQ"],
            "eligibleListings": eligible,
            "byExchange": {"NASDAQ": eligible},
            "bySecurityType": {"common": eligible},
            "excludedByReason": {},
            "fileCreated": {},
        },
        "sources": {
            "nasdaqTrader": {"url": "https://example.test", "fileCreated": {}},
            "sec": {"url": "https://www.sec.gov/edgar", "latestFilingDate": "2026-08-01"},
        },
        "coverage": {
            "listings": listings,
            "growth": growth,
            "currentTtm": growth,
            "quarterChecks": {"match": 8, "mismatch": 0},
        },
        "gate": {"ok": True, "reasons": []},
    }


def _dataset(tmp_path: Path, companies: list[dict], *, extra_layer3: dict | None = None) -> Path:
    data = tmp_path / "data"
    (data / "companies").mkdir(parents=True)
    rows = []
    by_ticker = {}
    for company in companies:
        write_json_atomic(data / "companies" / f"{company['ticker']}.json", company)
        rows.append(
            {
                "ticker": company["ticker"],
                "name": company["name"],
                "exchange": company["exchange"],
                "type": company["securityType"],
                "sicCode": (company.get("sic") or {}).get("code"),
                "ttmCurrent": company["ttm"]["current"],
                "ttmPrevious": company["ttm"]["previous"],
                "ttmGrowth": company["ttm"]["growthPct"],
                "naReason": company["ttm"]["reason"],
                "revenueCurrency": "USD",
            }
        )
        if company.get("cik"):
            by_ticker[company["ticker"]] = company["cik"]
    write_json_atomic(
        data / "screener.json",
        {"schemaVersion": 2, "generatedAt": "2026-10-01T00:00:00+00:00", "rows": rows},
        compact=True,
    )
    write_json_atomic(data / "issuers.json", {"schemaVersion": 1, "byTicker": by_ticker})
    growth_n = sum(1 for c in companies if c["ttm"]["growthPct"] is not None)
    write_json_atomic(data / "meta.json", _meta(listings=len(companies), growth=growth_n))
    write_json_atomic(
        data / "layer2.json",
        {
            "schemaVersion": 1,
            "generatedAt": "2026-10-01T00:00:00+00:00",
            "rows": [],
            "counts": {"listings": len(companies)},
        },
    )
    write_json_atomic(data / "classification_issues.json", {"generatedAt": "2026-10-01T00:00:00+00:00", "issues": []})
    cik_dir = data / "layer3" / "cik"
    cik_dir.mkdir(parents=True)
    for company in companies:
        cik = company.get("cik")
        if not cik:
            continue
        write_json_atomic(
            cik_dir / f"{cik}.json",
            {
                "cik": cik,
                "tickers": [company["ticker"]],
                "displayTicker": company["ticker"],
                "extractionStatus": "extracted",
                "metrics": {"ocf": {"ttm": 1, "quarters": []}},
            },
            compact=True,
        )
    if extra_layer3:
        write_json_atomic(cik_dir / extra_layer3["filename"], extra_layer3["payload"], compact=True)
    write_json_atomic(
        data / "layer3.json",
        {
            "schemaVersion": 3,
            "extractionVersion": 4,
            "generatedAt": "2026-10-01T00:00:00+00:00",
            "payload": "index",
            "rows": [],
            "counts": {"issuers": len(list(cik_dir.glob("*.json")))},
        },
        compact=True,
    )
    return data


def _filing(
    cik: str,
    accn: str,
    form: str = "10-Q",
    *,
    filed: date | None = None,
    accepted: datetime | None = None,
    source: str = "daily-index",
) -> DailyFiling:
    return DailyFiling(
        cik=cik,
        name="Test",
        form=form,
        filed=filed or date(2026, 10, 20),
        filename=f"edgar/data/{int(cik)}/{accn}.txt",
        accn=accn,
        accepted=accepted,
        source=source,
    )


def test_write_json_if_changed_skips_identical_payload(tmp_path: Path):
    path = tmp_path / "x.json"
    payload = {"a": 1, "missing": None}
    assert write_json_if_changed(path, payload) is True
    mtime = path.stat().st_mtime_ns
    assert write_json_if_changed(path, {"missing": None, "a": 1}) is False
    assert path.stat().st_mtime_ns == mtime
    assert write_json_if_changed(path, {"a": 2, "missing": None}) is True


def test_processed_accession_is_not_applied_again(tmp_path: Path):
    company = _company("AAA", "0000000001")
    data = _dataset(tmp_path, [company])
    accn = "0000000001-26-000010"
    write_json_atomic(
        data / "daily-update.json",
        {
            "processedAccessions": {
                accn: {"cik": "0000000001", "form": "10-Q", "filed": "2026-10-20", "status": "applied"}
            }
        },
    )
    before = (data / "companies" / "AAA.json").read_bytes()
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[_filing("0000000001", accn)],
        companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report["filingsNew"] == 0
    assert report["companiesUpdated"] == []
    assert report["published"] is False
    assert report["unchanged"] is True
    assert (data / "companies" / "AAA.json").read_bytes() == before
    assert "dailyUpdate" not in (data / "meta.json").read_text()


def test_unknown_cik_does_not_expand_universe(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[_filing("0000999999", "0000999999-26-000001")],
        companyfacts_by_cik={},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report["outOfUniverse"] == 1
    assert report["companiesUpdated"] == []
    assert report["published"] is False
    assert report["stateUpdated"] is True
    assert "dailyUpdate" not in (data / "meta.json").read_text()
    state = (data / "daily-update.json").read_text()
    assert "0000999999-26-000001" in state
    assert "out_of_universe" in state
    assert (data / "companies" / "BBB.json").exists() is False


def test_missing_quarter_stays_null_not_zero(tmp_path: Path):
    company = _company("AAA", "0000000001", current=None, previous=None, growth=None, missing=True)
    data = _dataset(tmp_path, [company])
    sparse = companyfacts(
        {
            "Revenues": [
                raw("2025-01-01", "2025-03-31", 10, "A-1", 2025, "Q1"),
                raw("2025-04-01", "2025-06-30", 11, "A-2", 2025, "Q2"),
            ]
        },
        cik=1,
        name="AAA",
    )
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[_filing("0000000001", "0000000001-26-000011")],
        companyfacts_by_cik={"0000000001": sparse},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert report["published"] is True
    payload = json.loads((data / "companies" / "AAA.json").read_text())
    assert payload["ttm"]["current"] is None
    assert payload["ttm"]["previous"] is None
    assert payload["ttm"]["growthPct"] is None
    for quarter in payload["revenue"]["quarters"]:
        if quarter.get("missing"):
            assert quarter["value"] is None
        else:
            assert quarter["value"] in (10, 11)


def test_gate_failure_keeps_previous_dataset(tmp_path: Path):
    company = _company("AAA", "0000000001")
    data = _dataset(tmp_path, [company])
    before = (data / "companies" / "AAA.json").read_bytes()
    generated_before = (data / "meta.json").read_text()
    empty = companyfacts({"Revenues": []}, cik=1, name="AAA")
    try:
        run_daily_update(
            data,
            as_of=date(2026, 10, 21),
            indexes=[_filing("0000000001", "0000000001-26-000012")],
            companyfacts_by_cik={"0000000001": empty},
            state_dir=tmp_path / "state",
            verify_quarters=False,
            offline=True,
            update_layer3=False,
        )
        raised = False
    except DailyUpdateError as exc:
        raised = True
        assert "gate" in str(exc).lower() or "Validation" in str(exc)
    assert raised
    assert (data / "companies" / "AAA.json").read_bytes() == before
    assert (data / "meta.json").read_text() == generated_before
    assert not (data.with_name(data.name + ".daily-staging")).exists()
    state = data / "daily-update.json"
    if state.exists():
        assert "0000000001-26-000012" not in state.read_text()


def test_layer3_extra_issuer_file_is_preserved(tmp_path: Path):
    extra = {
        "filename": "0000888888.json",
        "payload": {
            "cik": "0000888888",
            "tickers": ["KEEP"],
            "extractionStatus": "extracted",
            "metrics": {"ocf": {"ttm": 9}},
        },
    }
    data = _dataset(tmp_path, [_company("AAA", "0000000001")], extra_layer3=extra)
    from test_layer3_extract import _instant, _ytd_year

    facts = _revenue_payload(1, "AAA")
    facts["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"] = {
        "units": {"USD": _ytd_year(2025, 10, 10, 10, 10, prefix="O") + _ytd_year(2024, 9, 9, 9, 9, prefix="P")}
    }
    facts["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"] = {
        "units": {"USD": _ytd_year(2025, 2, 2, 2, 2, prefix="C") + _ytd_year(2024, 1, 1, 1, 1, prefix="D")}
    }
    facts["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"] = {
        "units": {"USD": [_instant("2025-12-31", 50, "a", 2025, "FY", form="10-K")]}
    }
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[_filing("0000000001", "0000000001-26-000013")],
        companyfacts_by_cik={"0000000001": facts},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report["published"] is True
    kept = data / "layer3" / "cik" / "0000888888.json"
    assert kept.exists()
    assert "KEEP" in kept.read_text()


def test_dry_run_does_not_write(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    before_meta = (data / "meta.json").read_text()
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[_filing("0000000001", "0000000001-26-000014")],
        companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        dry_run=True,
        update_layer3=False,
    )
    assert report["published"] is False
    assert report["heldBack"] == "dry_run"
    assert (data / "meta.json").read_text() == before_meta
    assert not (data / "daily-update.json").exists()


def test_no_new_filings_advances_checkpoint_without_publishing(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    before_meta = (data / "meta.json").read_bytes()
    before_company = (data / "companies" / "AAA.json").read_bytes()
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[],
        latest_filings=[],
        companyfacts_by_cik={},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report["published"] is False
    assert report["unchanged"] is True
    assert report["stateUpdated"] is True
    assert report["checkpointAdvanced"] is True
    assert report["generatedAt"] == "2026-10-01T00:00:00+00:00"
    assert (data / "meta.json").read_bytes() == before_meta
    assert (data / "companies" / "AAA.json").read_bytes() == before_company
    state = json.loads((data / "daily-update.json").read_text())
    assert state["lastSuccessfulSyncAt"]
    assert state.get("lastFinancialUpdateAt") is None


def test_cli_daily_update_help():
    with pytest.raises(SystemExit) as ei:
        main(["daily-update", "--help"])
    assert ei.value.code == 0


def test_pacific_today_uses_los_angeles_not_utc():
    # 6:00 PM PDT on 2026-10-21 is 01:00 UTC on 2026-10-22.
    assert pacific_today(datetime(2026, 10, 22, 1, 0, tzinfo=UTC)) == date(2026, 10, 21)
    assert pacific_today(datetime(2026, 10, 21, 23, 0, tzinfo=UTC)) == date(2026, 10, 21)
    assert pacific_today(datetime(2026, 10, 22, 8, 0, tzinfo=UTC)) == date(2026, 10, 22)


def test_run_daily_update_defaults_as_of_to_pacific_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("screener_pipeline.daily_update.pacific_today", lambda: date(2026, 10, 21))
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    report = run_daily_update(
        data,
        indexes=[],
        latest_filings=[],
        companyfacts_by_cik={},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report["asOf"] == "2026-10-21"


def test_discovery_since_uses_lookback_or_missed_period_plus_overlap():
    as_of = date(2026, 10, 21)
    assert discovery_since(as_of, None, 10, 48) == date(2026, 10, 12)
    assert discovery_since(as_of, datetime(2026, 10, 20, 1, tzinfo=UTC), 10, 48) == date(2026, 10, 12)
    assert discovery_since(as_of, datetime(2026, 10, 1, 1, tzinfo=UTC), 10, 48) == date(2026, 9, 29)


def test_same_day_latest_filing_is_applied_when_index_missing(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    accn = "0000000001-26-000021"
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        latest_filings=[
            _filing(
                "0000000001",
                accn,
                filed=date(2026, 10, 21),
                accepted=datetime(2026, 10, 21, 18, 5, tzinfo=UTC),
                source="latest",
            )
        ],
        indexes=[],
        companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert report["filingsNew"] == 1
    assert report["published"] is True
    assert "AAA" in report["companiesUpdated"]
    state = json.loads((data / "daily-update.json").read_text())
    assert state["processedAccessions"][accn]["status"] == "applied"


def test_delayed_filing_inside_overlap_is_still_new(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    write_json_atomic(
        data / "daily-update.json",
        {"lastSuccessfulSyncAt": "2026-10-20T01:00:00+00:00", "processedAccessions": {}},
    )
    accn = "0000000001-26-000022"
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        latest_filings=[
            _filing(
                "0000000001",
                accn,
                filed=date(2026, 10, 18),
                accepted=datetime(2026, 10, 18, 22, 0, tzinfo=UTC),
                source="latest",
            )
        ],
        indexes=[],
        companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert report["syncFrom"] == "2026-10-12"
    assert report["filingsNew"] == 1
    assert report["published"] is True


def test_duplicate_accession_from_both_sources_is_applied_once(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    filing = _filing("0000000001", "0000000001-26-000023")
    latest = _filing(
        "0000000001",
        "0000000001-26-000023",
        accepted=datetime(2026, 10, 20, 16, 0, tzinfo=UTC),
        source="latest",
    )
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        latest_filings=[latest],
        indexes=[filing],
        companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert report["filingsSeen"] == 1
    assert report["filingsNew"] == 1
    assert report["published"] is True
    state = json.loads((data / "daily-update.json").read_text())
    assert list(state["processedAccessions"]) == ["0000000001-26-000023"]


def test_eight_k_is_recorded_not_rebuilt(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    before_company = (data / "companies" / "AAA.json").read_bytes()
    before_meta = (data / "meta.json").read_text()
    accn = "0000000001-26-000024"
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        latest_filings=[_filing("0000000001", accn, form="8-K", source="latest")],
        indexes=[_filing("0000000001", accn, form="8-K")],
        companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report["published"] is False
    assert report["unchanged"] is True
    assert report["filingsRecorded8k"] == 1
    assert report["companiesUpdated"] == []
    assert report["generatedAt"] == "2026-10-01T00:00:00+00:00"
    assert (data / "companies" / "AAA.json").read_bytes() == before_company
    assert (data / "meta.json").read_text() == before_meta
    state = json.loads((data / "daily-update.json").read_text())
    assert state["processedAccessions"][accn]["status"] == "recorded_8k"
    assert state["lastSuccessfulSyncAt"]
    assert state.get("lastFinancialUpdateAt") is None


def test_recent_unreconciled_dates_are_kept(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    write_json_atomic(
        data / "daily-update.json",
        {
            "lastSuccessfulSyncAt": "2026-10-20T01:00:00+00:00",
            "unreconciledDates": ["2026-10-20", "2026-10-10"],
            "processedAccessions": {},
        },
    )
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[],
        latest_filings=[],
        companyfacts_by_cik={},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert "2026-10-20" in report["unresolvedDates"]
    assert "2026-10-10" not in report["unresolvedDates"]
    state = json.loads((data / "daily-update.json").read_text())
    assert state["unreconciledDates"] == ["2026-10-20"]
    assert state["lastSuccessfulSyncAt"] != "2026-10-20T01:00:00+00:00"


def test_missed_run_recovers_older_filing(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    write_json_atomic(
        data / "daily-update.json",
        {"lastSuccessfulSyncAt": "2026-10-10T01:00:00+00:00", "processedAccessions": {}},
    )
    accn = "0000000001-26-000025"
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[_filing("0000000001", accn, filed=date(2026, 10, 12))],
        latest_filings=[],
        companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert report["syncFrom"] == "2026-10-08"
    assert report["filingsNew"] == 1
    assert report["published"] is True
    assert report["lastFinancialUpdateAt"]


def test_discovery_http_error_does_not_advance_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    write_json_atomic(
        data / "daily-update.json",
        {"lastSuccessfulSyncAt": "2026-10-20T01:00:00+00:00", "processedAccessions": {}},
    )
    before_company = (data / "companies" / "AAA.json").read_bytes()
    before_state = (data / "daily-update.json").read_text()

    def boom(*_args, **_kwargs):
        raise requests.HTTPError("HTTP 503")

    monkeypatch.setenv("SEC_USER_AGENT", "stock-screener tester@example.com")
    monkeypatch.setattr("screener_pipeline.daily_update.fetch_latest_filings", boom)
    with pytest.raises(DailyUpdateError, match="SEC discovery"):
        run_daily_update(
            data,
            as_of=date(2026, 10, 21),
            state_dir=tmp_path / "state",
            verify_quarters=False,
            offline=False,
            update_layer3=False,
        )
    assert (data / "companies" / "AAA.json").read_bytes() == before_company
    assert (data / "daily-update.json").read_text() == before_state


def test_weekend_master_idx_is_not_requested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    write_json_atomic(
        data / "daily-update.json",
        {"lastSuccessfulSyncAt": "2026-10-20T01:00:00+00:00", "processedAccessions": {}},
    )
    before_company = (data / "companies" / "AAA.json").read_bytes()

    class _Resp:
        def __init__(self, status: int):
            self.status_code = status
            self.content = b""

        def raise_for_status(self):
            if self.status_code >= 400 and self.status_code != 404:
                raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    class _Http:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str) -> _Resp:
            self.urls.append(url)
            return _Resp(404)

    http = _Http()

    def wrapped(_http, *args, **kwargs):
        return collect_period_filings(http, *args, **kwargs)

    monkeypatch.setenv("SEC_USER_AGENT", "stock-screener tester@example.com")
    monkeypatch.setattr(
        "screener_pipeline.daily_update.fetch_latest_filings",
        lambda *_args, **_kwargs: ([], {"pages": 1, "hits": 0}),
    )
    monkeypatch.setattr("screener_pipeline.daily_update.collect_period_filings", wrapped)

    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        verify_quarters=False,
        offline=False,
        update_layer3=False,
    )
    assert report["ok"] is True
    assert report["published"] is False
    assert "2026-10-18" not in report["unresolvedDates"]
    assert "2026-10-17" not in report["unresolvedDates"]
    assert all("master.20261018.idx" not in url and "master.20261017.idx" not in url for url in http.urls)
    assert (data / "companies" / "AAA.json").read_bytes() == before_company


def test_company_facts_http_error_does_not_advance_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    write_json_atomic(
        data / "daily-update.json",
        {"lastSuccessfulSyncAt": "2026-10-20T01:00:00+00:00", "processedAccessions": {}},
    )
    before_company = (data / "companies" / "AAA.json").read_bytes()

    def boom(*_args, **_kwargs):
        raise requests.HTTPError("HTTP 502")

    monkeypatch.setattr("screener_pipeline.daily_update._fetch_companyfacts", boom)
    with pytest.raises(DailyUpdateError, match="Company Facts"):
        run_daily_update(
            data,
            as_of=date(2026, 10, 21),
            indexes=[_filing("0000000001", "0000000001-26-000026")],
            latest_filings=[],
            state_dir=tmp_path / "state",
            verify_quarters=False,
            offline=True,
            update_layer3=False,
        )
    assert (data / "companies" / "AAA.json").read_bytes() == before_company
    state = json.loads((data / "daily-update.json").read_text())
    assert state["lastSuccessfulSyncAt"] == "2026-10-20T01:00:00+00:00"
    assert "0000000001-26-000026" not in state.get("processedAccessions", {})


def test_facts_lag_does_not_mark_accession_or_advance(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    facts = _revenue_payload(1, "AAA")
    first = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[_filing("0000000001", "0000000001-26-000010")],
        latest_filings=[],
        companyfacts_by_cik={"0000000001": facts},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert first["published"] is True
    after_first = (data / "companies" / "AAA.json").read_bytes()
    sync_at = json.loads((data / "daily-update.json").read_text())["lastSuccessfulSyncAt"]
    try:
        run_daily_update(
            data,
            as_of=date(2026, 10, 21),
            indexes=[_filing("0000000001", "0000000001-26-000027")],
            latest_filings=[],
            companyfacts_by_cik={"0000000001": facts},
            state_dir=tmp_path / "state",
            verify_quarters=False,
            offline=True,
            update_layer3=False,
        )
        raised = False
    except DailyUpdateError as exc:
        raised = True
        assert "lagging" in str(exc) or "Company Facts" in str(exc)
    assert raised
    assert (data / "companies" / "AAA.json").read_bytes() == after_first
    state = json.loads((data / "daily-update.json").read_text())
    assert state["lastSuccessfulSyncAt"] == sync_at
    assert "0000000001-26-000010" in state["processedAccessions"]
    assert "0000000001-26-000027" not in state["processedAccessions"]


def _annual_facts(
    cik: int,
    name: str,
    *,
    accn: str,
    form: str = "10-K",
    filed: str = "2026-02-15",
    q4: float = 17,
    extra: list[Fact] | None = None,
) -> dict:
    facts = calendar_year(2024, 10, 11, 12, 13, prefix="B") + calendar_year(2025, 14, 15, 16, q4, prefix="A")
    tagged: list[Fact] = []
    for item in facts:
        if item.form == "10-K" and item.fy == 2025:
            tagged.append(
                Fact(
                    start=item.start,
                    end=item.end,
                    val=item.val,
                    accn=accn,
                    fy=item.fy,
                    fp=item.fp,
                    form=form,
                    filed=date.fromisoformat(filed),
                )
            )
        else:
            tagged.append(item)
    tagged.extend(extra or [])
    return companyfacts({"Revenues": _raw_facts(tagged)}, cik=cik, name=name)


def test_ten_k_then_amendment_is_a_new_accession(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    original = "0000000001-26-000100"
    amendment = "0000000001-26-000200"
    first = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[_filing("0000000001", original, form="10-K")],
        latest_filings=[],
        companyfacts_by_cik={"0000000001": _annual_facts(1, "AAA", accn=original)},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert first["published"] is True
    assert first["filingsNew"] == 1
    assert "AAA" in first["companiesUpdated"]
    state = json.loads((data / "daily-update.json").read_text())
    assert state["processedAccessions"][original]["status"] == "applied"
    before = json.loads((data / "companies" / "AAA.json").read_text())

    restated = _annual_facts(
        1,
        "AAA",
        accn=original,
        extra=[
            Fact(
                start=date(2025, 1, 1),
                end=date(2025, 12, 31),
                val=14 + 15 + 16 + 25,
                accn=amendment,
                fy=2025,
                fp="FY",
                form="10-K/A",
                filed=date(2026, 10, 28),
            )
        ],
    )
    second = run_daily_update(
        data,
        as_of=date(2026, 10, 28),
        indexes=[_filing("0000000001", amendment, form="10-K/A", filed=date(2026, 10, 28))],
        latest_filings=[],
        companyfacts_by_cik={"0000000001": restated},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert second["filingsNew"] == 1
    assert second["published"] is True
    assert "AAA" in second["companiesUpdated"]
    after = json.loads((data / "companies" / "AAA.json").read_text())
    assert after["ttm"]["current"] != before["ttm"]["current"]
    state = json.loads((data / "daily-update.json").read_text())
    assert state["processedAccessions"][original]["status"] == "applied"
    assert state["processedAccessions"][amendment]["status"] == "applied"
    assert state["processedAccessions"][amendment]["form"] == "10-K/A"


def test_two_new_accessions_same_company_are_applied_together(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    k_accn = "0000000001-26-000100"
    a_accn = "0000000001-26-000200"
    facts = _annual_facts(
        1,
        "AAA",
        accn=k_accn,
        extra=[
            Fact(
                start=date(2025, 1, 1),
                end=date(2025, 12, 31),
                val=14 + 15 + 16 + 17,
                accn=a_accn,
                fy=2025,
                fp="FY",
                form="10-K/A",
                filed=date(2026, 10, 21),
            )
        ],
    )
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[
            _filing("0000000001", k_accn, form="10-K"),
            _filing("0000000001", a_accn, form="10-K/A"),
        ],
        latest_filings=[],
        companyfacts_by_cik={"0000000001": facts},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert report["filingsNew"] == 2
    assert report["published"] is True
    assert report["companiesUpdated"] == ["AAA"]
    state = json.loads((data / "daily-update.json").read_text())
    assert state["processedAccessions"][k_accn]["status"] == "applied"
    assert state["processedAccessions"][a_accn]["status"] == "applied"


def test_unready_amendment_is_not_marked_when_original_is_applied(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    k_accn = "0000000001-26-000100"
    a_accn = "0000000001-26-000200"
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[
            _filing("0000000001", k_accn, form="10-K"),
            _filing("0000000001", a_accn, form="10-K/A"),
        ],
        latest_filings=[],
        companyfacts_by_cik={"0000000001": _annual_facts(1, "AAA", accn=k_accn)},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=False,
    )
    assert report["published"] is True
    assert "AAA" in report["companiesUpdated"]
    assert report["checkpointAdvanced"] is False
    state = json.loads((data / "daily-update.json").read_text())
    assert state["processedAccessions"][k_accn]["status"] == "applied"
    assert a_accn not in state["processedAccessions"]
    reasons = {row["accn"]: row.get("reason") for row in report["skippedFilings"]}
    assert reasons.get(a_accn) == "company_facts_lag"


def test_production_does_not_apply_accession_missing_from_company_facts(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    accn = "0000000001-26-000300"
    before = (data / "companies" / "AAA.json").read_bytes()
    try:
        run_daily_update(
            data,
            as_of=date(2026, 10, 21),
            indexes=[_filing("0000000001", accn, form="10-K")],
            latest_filings=[],
            companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
            state_dir=tmp_path / "state",
            verify_quarters=False,
            offline=False,
            update_layer3=False,
        )
        raised = False
    except DailyUpdateError as exc:
        raised = True
        assert "lagging" in str(exc) or "Company Facts" in str(exc)
    assert raised
    assert (data / "companies" / "AAA.json").read_bytes() == before
    state = data / "daily-update.json"
    if state.exists():
        assert accn not in json.loads(state.read_text()).get("processedAccessions", {})


def test_recorded_eight_k_is_backfilled_without_touching_layer1(tmp_path: Path):
    from fixtures.eight_k import GAAP_EARNINGS_EXHIBIT, META_ACCN, META_CIK, META_Q3_2026_EXHIBIT, earnings_documents

    company = _company("META", META_CIK)
    data = _dataset(tmp_path, [company])
    before_company = (data / "companies" / "META.json").read_bytes()
    before_l3 = (data / "layer3" / "cik" / f"{META_CIK}.json").read_bytes()
    write_json_atomic(
        data / "daily-update.json",
        {
            "schemaVersion": 2,
            "processedAccessions": {
                META_ACCN: {
                    "cik": META_CIK,
                    "form": "8-K",
                    "filed": "2026-10-21",
                    "status": "recorded_8k",
                }
            },
        },
    )
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 22),
        latest_filings=[],
        indexes=[],
        companyfacts_by_cik={},
        eight_k_documents={META_ACCN: earnings_documents(META_ACCN, exhibit=META_Q3_2026_EXHIBIT)},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report["eightKBackfill"] == 1
    assert report["companiesUpdated"] == []
    assert (data / "companies" / "META.json").read_bytes() == before_company
    state = json.loads((data / "daily-update.json").read_text())
    ext = state["earningsExtractions"][META_ACCN]
    assert ext["status"] == "extracted"
    assert ext["fiscalYear"] == 2026
    assert ext["fiscalQuarter"] == 3
    assert META_CIK in report["layer3Updated"]
    issuer = json.loads((data / "layer3" / "cik" / f"{META_CIK}.json").read_text())
    assert issuer["provisionalEarnings"]["status"] == "awaiting_10q"
    assert issuer["metrics"]["revenue"]["quarters"][0]["sourceType"] == "8k_earnings_release"
    assert issuer["metrics"]["revenue"]["quarters"][0]["value"] == 56_100_000_000
    assert before_l3 != (data / "layer3" / "cik" / f"{META_CIK}.json").read_bytes()
    # Successful extract is not reprocessed.
    report2 = run_daily_update(
        data,
        as_of=date(2026, 10, 22),
        latest_filings=[],
        indexes=[],
        companyfacts_by_cik={},
        eight_k_documents={META_ACCN: earnings_documents(META_ACCN, exhibit=GAAP_EARNINGS_EXHIBIT)},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report2["eightKBackfill"] == 0
    assert json.loads((data / "daily-update.json").read_text())["earningsExtractions"][META_ACCN]["attempts"] == 1


def test_failed_eight_k_extract_does_not_corrupt_verified_json(tmp_path: Path):
    from fixtures.eight_k import ITEM_202_NO_TABLES, earnings_documents

    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    before_company = (data / "companies" / "AAA.json").read_bytes()
    before_l3 = (data / "layer3" / "cik" / "0000000001.json").read_bytes()
    accn = "0000000001-26-000024"
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        latest_filings=[_filing("0000000001", accn, form="8-K", source="latest")],
        indexes=[_filing("0000000001", accn, form="8-K")],
        companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
        eight_k_documents={accn: earnings_documents(accn, exhibit=ITEM_202_NO_TABLES)},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report["published"] is False
    assert report["companiesUpdated"] == []
    assert (data / "companies" / "AAA.json").read_bytes() == before_company
    assert (data / "layer3" / "cik" / "0000000001.json").read_bytes() == before_l3
    state = json.loads((data / "daily-update.json").read_text())
    assert state["processedAccessions"][accn]["status"] == "recorded_8k"
    assert state["earningsExtractions"][accn]["status"] == "failed"
    assert state["earningsExtractions"][accn]["attempts"] == 1


def test_ten_q_facts_supersede_provisional_eight_k(tmp_path: Path):
    from fixtures.eight_k import GAAP_EARNINGS_EXHIBIT, earnings_documents

    from screener_pipeline.sec.facts import Fact

    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    eight_k = "0000000001-26-000024"
    ten_q = "0000000001-26-000099"
    run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        latest_filings=[_filing("0000000001", eight_k, form="8-K", source="latest")],
        indexes=[_filing("0000000001", eight_k, form="8-K")],
        companyfacts_by_cik={"0000000001": _revenue_payload(1, "AAA")},
        eight_k_documents={eight_k: earnings_documents(eight_k, exhibit=GAAP_EARNINGS_EXHIBIT)},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=True,
    )
    issuer = json.loads((data / "layer3" / "cik" / "0000000001.json").read_text())
    assert issuer["provisionalEarnings"]["status"] == "awaiting_10q"
    extra = [
        Fact(date(2026, 1, 1), date(2026, 3, 31), 18.0, "0000000001-26-000091", 2026, "Q1", "10-Q", date(2026, 5, 1)),
        Fact(date(2026, 4, 1), date(2026, 6, 30), 19.0, "0000000001-26-000092", 2026, "Q2", "10-Q", date(2026, 8, 1)),
        Fact(date(2026, 7, 1), date(2026, 9, 30), 51_240_000_000, ten_q, 2026, "Q3", "10-Q", date(2026, 10, 30)),
    ]
    facts = _revenue_payload(1, "AAA")
    facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"].extend(_raw_facts(extra))
    run_daily_update(
        data,
        as_of=date(2026, 10, 31),
        latest_filings=[],
        indexes=[_filing("0000000001", ten_q, form="10-Q", filed=date(2026, 10, 30))],
        companyfacts_by_cik={"0000000001": facts},
        eight_k_documents={eight_k: earnings_documents(eight_k, exhibit=GAAP_EARNINGS_EXHIBIT)},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
        update_layer3=True,
    )
    state = json.loads((data / "daily-update.json").read_text())
    assert state["processedAccessions"][ten_q]["status"] == "applied"
    assert state["earningsExtractions"][eight_k]["status"] == "superseded"
    issuer = json.loads((data / "layer3" / "cik" / "0000000001.json").read_text())
    assert issuer["earningsReleaseAudit"]
    assert issuer["earningsReleaseAudit"][0]["accn"] == eight_k
