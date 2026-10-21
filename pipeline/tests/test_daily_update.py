from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from helpers import calendar_year, companyfacts, raw

from screener_pipeline.cache import write_json_atomic, write_json_if_changed
from screener_pipeline.cli import main
from screener_pipeline.daily_update import DailyUpdateError, run_daily_update
from screener_pipeline.sec.daily_index import DailyFiling
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


def _filing(cik: str, accn: str, form: str = "10-Q") -> DailyFiling:
    return DailyFiling(
        cik=cik,
        name="Test",
        form=form,
        filed=date(2026, 10, 20),
        filename=f"edgar/data/{int(cik)}/{accn}.txt",
        accn=accn,
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


def test_no_new_filings_does_not_rewrite_or_publish(tmp_path: Path):
    data = _dataset(tmp_path, [_company("AAA", "0000000001")])
    before_meta = (data / "meta.json").read_bytes()
    before_company = (data / "companies" / "AAA.json").read_bytes()
    report = run_daily_update(
        data,
        as_of=date(2026, 10, 21),
        indexes=[],
        companyfacts_by_cik={},
        state_dir=tmp_path / "state",
        verify_quarters=False,
        offline=True,
    )
    assert report["published"] is False
    assert report["unchanged"] is True
    assert report["stateUpdated"] is False
    assert (data / "meta.json").read_bytes() == before_meta
    assert (data / "companies" / "AAA.json").read_bytes() == before_company
    assert not (data / "daily-update.json").exists()


def test_cli_daily_update_help():
    with pytest.raises(SystemExit) as ei:
        main(["daily-update", "--help"])
    assert ei.value.code == 0
