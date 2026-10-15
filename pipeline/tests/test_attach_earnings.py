from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from helpers import FIXTURES
from test_layer2 import company as layer1_company

from screener_pipeline.attach_earnings import attach_earnings
from screener_pipeline.cache import write_json_atomic
from screener_pipeline.layer2 import BUCKET_PASSED, analyze_company
from screener_pipeline.sec.facts import compact_revenue_facts, extract_earnings_facts, extract_revenue_facts
from screener_pipeline.sec.statement import (
    parse_income_statement_from_dir,
    statement_has_net_income,
    statement_to_compact,
)


def _ni_companyfacts(cik: str = "0000000123") -> dict:
    units = []
    y, m = 2024, 3
    val = 10.0
    accn_i = 1
    for _ in range(12):
        start_m = m - 2
        start_y = y
        if start_m <= 0:
            start_m += 12
            start_y -= 1
        start = date(start_y, start_m, 1)
        end = date(y, m, 28)
        fp = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}[m]
        units.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "val": val,
                "accn": f"0000000000-26-{accn_i:06d}",
                "fy": y,
                "fp": fp,
                "form": "10-Q",
                "filed": date(y, min(m + 1, 12), 15).isoformat(),
            }
        )
        val += 1
        accn_i += 1
        m += 3
        if m > 12:
            m = 3
            y += 1
    return {
        "cik": int(cik),
        "entityName": "Earn Co",
        "facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": units}}}},
    }


def test_attach_earnings_leaves_ttm_and_bucket_alone(tmp_path: Path):
    cik = "0000000123"
    ticker = "TST"
    row = layer1_company([12, 11, 11, 11, 10, 10, 10, 10], ttm_growth=20.0, ticker=ticker)
    row["cik"] = cik
    data_dir = tmp_path / "data"
    companies = data_dir / "companies"
    companies.mkdir(parents=True)
    write_json_atomic(companies / f"{ticker}.json", row)
    write_json_atomic(data_dir / "meta.json", {"generatedAt": "2026-10-15T00:00:00+00:00", "schemaVersion": 2})
    write_json_atomic(data_dir / "screener.json", {"rows": [{"ticker": ticker}]})

    state = tmp_path / "state"
    facts = state / "facts"
    facts.mkdir(parents=True)
    raw = _ni_companyfacts(cik)
    compact = compact_revenue_facts(extract_revenue_facts(raw), extract_earnings_facts(raw))
    write_json_atomic(facts / f"{cik}.json", compact)

    report = attach_earnings(
        data_dir,
        state_dir=state,
        merge_facts=False,
        verify_quarters=False,
    )
    assert report["attached"] == 1
    updated = json.loads((companies / f"{ticker}.json").read_text())
    assert updated["ttm"] == row["ttm"]
    assert updated["revenue"] == row["revenue"]
    assert updated["earnings"]["concept"] == "NetIncomeLoss"
    assert any(not q.get("missing") for q in updated["earnings"]["quarters"])

    l2 = analyze_company(updated)
    assert l2["bucket"] == BUCKET_PASSED
    assert l2["earningsConcept"] == "NetIncomeLoss"
    assert len(l2["earningsYoy"]) == 4


def test_parse_cached_filing_keeps_net_income(tmp_path: Path):
    html = (FIXTURES / "statements" / "SRPT-0001193125-26-335003-R4.htm").read_text()
    summary = (FIXTURES / "statements" / "SRPT-0001193125-26-335003-FilingSummary.xml").read_text()
    fdir = tmp_path / "0001193125-26-335003"
    fdir.mkdir()
    (fdir / "FilingSummary.xml").write_text(summary)
    (fdir / "R4.htm").write_text(html)
    parsed = parse_income_statement_from_dir(fdir)
    assert parsed is not None
    st, name = parsed
    assert name == "R4.htm"
    compact = statement_to_compact(st, "https://example.test/R4.htm")
    assert statement_has_net_income(st)
    assert any(
        "netincome" in r["concept"].lower() or "profitloss" in r["concept"].lower()
        or "net income" in r["label"].lower()
        or "net loss" in r["label"].lower()
        for r in compact["rows"]
    )
