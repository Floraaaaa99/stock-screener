"""Official EDGAR filings win when Company Facts lag."""

from __future__ import annotations

import json
from datetime import date

from helpers import FIXTURES, calendar_year, fact, filings_for

from screener_pipeline.quarters import Quarter
from screener_pipeline.revenue import analyze_company
from screener_pipeline.sec.edgar import (
    PeriodicFiling,
    facts_may_lag,
    freshness_row,
    infer_fy_fp,
    latest_facts_period_end,
    parse_periodic_filings,
    period_start,
    pick_official_value,
    supplement_revenue_facts,
)
from screener_pipeline.sec.facts import FilingInfo, RevenueFacts, revenue_facts_from_compact
from screener_pipeline.sec.statement import parse_statement_html

INCY_Q2_ACCN = "0000879169-26-000056"
INCY_Q2_HTML = FIXTURES / "statements" / f"INCY-{INCY_Q2_ACCN}-R4.htm"
INCY_Q2_URL = (
    "https://www.sec.gov/Archives/edgar/data/879169/000087916926000056/R4.htm"
)
INCY_Q2_REVENUE = 1_674_039_000.0


Q2_HTML = """
<html><body><table class="report">
<tr>
<th class="tl" colspan="1"><div><strong>Statements of Operations - USD ($)<br> $ in Thousands</strong></div></th>
<th class="th">3 Months Ended</th>
<th class="th">6 Months Ended</th>
</tr>
<tr>
<th class="th"><div>Jun. 30, 2026</div></th>
<th class="th"><div>Jun. 30, 2026</div></th>
</tr>
<tr class="re">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_Revenues', window );">Total revenues</a></td>
<td class="nump">1,674,039</td>
<td class="nump">2,946,715</td>
</tr>
</table></body></html>
"""


def _rf_through_q1() -> RevenueFacts:
    facts = calendar_year(2025, 100, 110, 120, 130) + [
        fact("2026-01-01", "2026-03-31", 140, "A2026-1", 2026, "Q1", filed="2026-04-28"),
    ]
    return RevenueFacts(
        cik="0000879169",
        entity_name="INCYTE CORPORATION",
        currency="USD",
        by_concept={"RevenueFromContractWithCustomerExcludingAssessedTax": facts},
        filings=filings_for(facts),
        forms_seen={"10-Q", "10-K"},
    )


def _q2_filing() -> PeriodicFiling:
    return PeriodicFiling(INCY_Q2_ACCN, "10-Q", date(2026, 7, 28), date(2026, 6, 30))


def test_parse_submissions_keeps_latest_10q_per_period():
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "10-Q/A", "10-K"],
                "filingDate": ["2026-08-01", "2026-07-28", "2026-08-02", "2026-02-10"],
                "reportDate": ["2026-07-15", "2026-06-30", "2026-06-30", "2025-12-31"],
                "accessionNumber": ["a", "orig", "amend", "k"],
            }
        }
    }
    got = parse_periodic_filings(payload)
    by_end = {f.report_date: f for f in got}
    assert set(by_end) == {date(2026, 6, 30), date(2025, 12, 31)}
    assert by_end[date(2026, 6, 30)].accn == "amend"
    assert by_end[date(2026, 6, 30)].filed == date(2026, 8, 2)


def test_facts_may_lag_uses_next_quarter_window():
    assert facts_may_lag(date(2026, 3, 31), date(2026, 10, 14))
    assert not facts_may_lag(date(2026, 6, 30), date(2026, 10, 14))
    assert facts_may_lag(None, date(2026, 10, 14))


def test_period_start_is_first_day_of_the_reported_window():
    assert period_start(date(2026, 6, 30), 3) == date(2026, 4, 1)
    assert period_start(date(2026, 6, 30), 6) == date(2026, 1, 1)
    assert period_start(date(2025, 9, 30), 12) == date(2024, 10, 1)


def test_infer_fy_fp_steps_q1_to_q2():
    filings = {
        "q1": FilingInfo("q1", "10-Q", date(2026, 4, 28), 2026, "Q1", date(2026, 3, 31)),
    }
    assert infer_fy_fp(filings, "10-Q") == (2026, "Q2")


def test_no_newer_filing_leaves_facts_unchanged():
    rf = _rf_through_q1()
    out, result = supplement_revenue_facts(rf, [], lambda accn: None, date(2026, 10, 14))
    assert result.status == "current"
    assert out is rf
    assert latest_facts_period_end(out) == date(2026, 3, 31)


def test_missing_statement_is_unresolved_not_estimated():
    rf = _rf_through_q1()
    out, result = supplement_revenue_facts(rf, [_q2_filing()], lambda accn: None, date(2026, 10, 14))
    assert result.status == "unresolved"
    assert result.applied == []
    assert latest_facts_period_end(out) == date(2026, 3, 31)


def test_official_3m_from_10q_is_merged_and_verified():
    rf = _rf_through_q1()
    st = parse_statement_html(Q2_HTML)

    def fetch(accn):
        if accn != INCY_Q2_ACCN:
            return None
        return st, INCY_Q2_URL

    out, result = supplement_revenue_facts(rf, [_q2_filing()], fetch, date(2026, 10, 14))
    assert result.status == "applied"
    assert result.applied[0].value == INCY_Q2_REVENUE
    assert result.applied[0].months == 3
    assert result.applied[0].concept == "Revenues"
    assert latest_facts_period_end(out) == date(2026, 6, 30)

    rev = analyze_company(out, fetch)
    latest = rev.slots[0]
    assert isinstance(latest, Quarter)
    assert latest.end == date(2026, 6, 30)
    assert latest.val == INCY_Q2_REVENUE
    assert latest.method == "reported"
    assert latest.sources[0].accn == INCY_Q2_ACCN
    assert latest.fiscal_year == 2026
    assert latest.fiscal_quarter == 2
    check = rev.quarter_checks[date(2026, 6, 30)]
    assert check.status == "match"
    assert check.url == INCY_Q2_URL


def test_first_total_revenue_row_not_later_segment():
    html = Q2_HTML.replace(
        "</table>",
        """<tr class="re">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_Revenues', window );">Total revenues</a></td>
<td class="nump">11,200</td>
<td class="nump">28,200</td>
</tr></table>""",
    )
    st = parse_statement_html(html)
    picked = pick_official_value(st, 3, date(2026, 6, 30))
    assert picked is not None
    assert picked[2] == INCY_Q2_REVENUE


def test_incy_q2_from_official_10q_when_company_facts_stop_at_q1():
    compact = json.loads((FIXTURES / "companyfacts" / "INCY-compact.json").read_text())
    rf = revenue_facts_from_compact(compact)
    assert latest_facts_period_end(rf) == date(2026, 3, 31)
    html = INCY_Q2_HTML.read_text()
    st = parse_statement_html(html)

    def fetch(accn):
        if accn != INCY_Q2_ACCN:
            return None
        return st, INCY_Q2_URL

    out, result = supplement_revenue_facts(rf, [_q2_filing()], fetch, date(2026, 10, 14))
    assert result.status == "applied"
    assert result.applied[0].value == INCY_Q2_REVENUE
    rev = analyze_company(out, fetch, verify_quarters=True)
    latest = rev.slots[0]
    assert latest.end == date(2026, 6, 30)
    assert latest.val == INCY_Q2_REVENUE
    assert latest.formula == "3M reported"
    assert latest.sources[0].accn == INCY_Q2_ACCN
    assert latest.sources[0].form == "10-Q"
    assert rev.quarter_checks[date(2026, 6, 30)].status == "match"
    assert rev.statement_check["accn"] == INCY_Q2_ACCN
    assert rev.statement_check["url"] == INCY_Q2_URL
    q1 = next(s for s in rev.slots if s.end == date(2026, 3, 31))
    assert q1.val == 1_272_676_000


def test_freshness_row_flags_lagging_dataset():
    company = {
        "ticker": "INCY",
        "cik": "0000879169",
        "revenue": {
            "quarters": [
                {"fiscalYear": 2026, "fiscalQuarter": 1, "end": "2026-03-31", "missing": False},
            ]
        },
    }
    row = freshness_row(company, [_q2_filing()], date(2026, 10, 14))
    assert row["status"] == "lagging"
    assert row["newerFilings"][0]["accn"] == INCY_Q2_ACCN
    current = freshness_row(
        {
            **company,
            "revenue": {
                "quarters": [
                    {"fiscalYear": 2026, "fiscalQuarter": 2, "end": "2026-06-30", "missing": False},
                ]
            },
        },
        [_q2_filing()],
        date(2026, 10, 14),
    )
    assert current["status"] == "current"
    assert current["newerFilings"] == []
