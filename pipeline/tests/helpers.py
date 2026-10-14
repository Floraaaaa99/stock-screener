"""Builders for hand-made SEC Company Facts structures used in unit tests.

These are test inputs only; they never reach the website.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from screener_pipeline.quarters import Quarter, build_timeline, dedupe_periods, derive_quarters, label_quarters
from screener_pipeline.sec.facts import Fact, FilingInfo, RevenueFacts, extract_revenue_facts

FIXTURES = Path(__file__).parent / "fixtures"


def fact(start: str, end: str, val: float, accn: str, fy: int, fp: str, form: str = "10-Q",
         filed: str | None = None) -> Fact:
    return Fact(
        start=date.fromisoformat(start),
        end=date.fromisoformat(end),
        val=float(val),
        accn=accn,
        fy=fy,
        fp=fp,
        form=form,
        filed=date.fromisoformat(filed or end),
    )


def raw(start: str, end: str, val: float, accn: str, fy: int, fp: str, form: str = "10-Q",
        filed: str | None = None) -> dict:
    return {"start": start, "end": end, "val": val, "accn": accn, "fy": fy, "fp": fp, "form": form,
            "filed": filed or end}


def companyfacts(concepts: dict[str, list[dict]], cik: int = 1234567, name: str = "Test Co") -> dict:
    return {
        "cik": cik,
        "entityName": name,
        "facts": {"us-gaap": {c: {"units": {"USD": facts}} for c, facts in concepts.items()}},
    }


def filings_for(facts: list[Fact]) -> dict[str, FilingInfo]:
    out: dict[str, FilingInfo] = {}
    for f in facts:
        cur = out.get(f.accn)
        if cur is None or f.end > cur.period_end:
            out[f.accn] = FilingInfo(f.accn, f.form, f.filed, f.fy, f.fp, f.end)
    return out


def quarters_from(facts: list[Fact], concept: str = "Revenues") -> dict[date, Quarter]:
    periods = dedupe_periods(facts)
    qs = derive_quarters(periods, concept)
    label_quarters(qs, filings_for(facts))
    return qs


def timeline_values(facts: list[Fact]) -> list[float | None]:
    return [getattr(s, "val", None) for s in build_timeline(quarters_from(facts))]


def load_fixture(ticker: str) -> RevenueFacts:
    return extract_revenue_facts(json.loads((FIXTURES / "companyfacts" / f"{ticker}.json").read_text()))


def calendar_year(fy: int, q1: float, q2: float, q3: float, q4: float, *, prefix: str = "A",
                  reported_q4: bool = False, ytd_only: bool = False) -> list[Fact]:
    """Facts as a calendar-year filer reports them: 10-Q 3M (+YTD) for Q1-Q3, and a 10-K FY total."""
    y = fy
    a1, a2, a3, ak = (f"{prefix}{y}-1", f"{prefix}{y}-2", f"{prefix}{y}-3", f"{prefix}{y}-K")
    out = [fact(f"{y}-01-01", f"{y}-03-31", q1, a1, y, "Q1", filed=f"{y}-05-01")]
    if not ytd_only:
        out.append(fact(f"{y}-04-01", f"{y}-06-30", q2, a2, y, "Q2", filed=f"{y}-08-01"))
        out.append(fact(f"{y}-07-01", f"{y}-09-30", q3, a3, y, "Q3", filed=f"{y}-11-01"))
    out.append(fact(f"{y}-01-01", f"{y}-06-30", q1 + q2, a2, y, "Q2", filed=f"{y}-08-01"))
    out.append(fact(f"{y}-01-01", f"{y}-09-30", q1 + q2 + q3, a3, y, "Q3", filed=f"{y}-11-01"))
    out.append(fact(f"{y}-01-01", f"{y}-12-31", q1 + q2 + q3 + q4, ak, y, "FY", form="10-K",
                    filed=f"{y + 1}-02-15"))
    if reported_q4:
        out.append(fact(f"{y}-10-01", f"{y}-12-31", q4, ak, y, "FY", form="10-K", filed=f"{y + 1}-02-15"))
    return out
