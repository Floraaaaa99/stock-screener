"""Use official EDGAR 10-Q/10-K income statements when Company Facts lag the latest filing.

Company Facts (nightly companyfacts.zip or a cached per-CIK snapshot) is a convenience index.
The source of truth for a quarter is the issuer's filed 10-Q/10-K. When EDGAR submissions list a
newer periodic report than the latest Company Facts period, this module reads that filing's
rendered income statement and adds the officially reported revenue fact. No estimates.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta

from .facts import ANNUAL_FORMS, DOMESTIC_FORMS, QUARTERLY_FORMS, REVENUE_CONCEPTS, Fact, FilingInfo, RevenueFacts
from .statement import Statement, is_total_revenue_label

# Slower 10-Q window (accelerated filers). Used only to decide whether submissions should be
# re-fetched because Company Facts look stale — not to invent a quarter.
TEN_Q_FILED_BY_DAYS = 45


@dataclass(frozen=True)
class PeriodicFiling:
    accn: str
    form: str
    filed: date
    report_date: date | None

    def to_dict(self) -> dict:
        return {
            "accn": self.accn,
            "form": self.form,
            "filed": self.filed.isoformat(),
            "reportDate": self.report_date.isoformat() if self.report_date else None,
        }


@dataclass
class AppliedFact:
    accn: str
    form: str
    end: date
    start: date
    months: int
    value: float
    concept: str
    label: str
    url: str

    def to_dict(self) -> dict:
        return {
            "accn": self.accn,
            "form": self.form,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "months": self.months,
            "value": self.value,
            "concept": self.concept,
            "label": self.label,
            "url": self.url,
        }


@dataclass
class SupplementResult:
    status: str
    latest_facts_end: date | None
    newer: list[PeriodicFiling] = field(default_factory=list)
    applied: list[AppliedFact] = field(default_factory=list)
    unresolved: list[dict] = field(default_factory=list)
    refreshed_submissions: bool = False

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "latestFactsEnd": self.latest_facts_end.isoformat() if self.latest_facts_end else None,
            "window": "official_filings",
            "newerFilings": [f.to_dict() for f in self.newer],
            "applied": [a.to_dict() for a in self.applied],
            "unresolved": self.unresolved,
            "refreshedSubmissions": self.refreshed_submissions,
        }


def parse_periodic_filings(payload: dict) -> list[PeriodicFiling]:
    """10-Q/10-K rows from an EDGAR submissions JSON (recent list)."""
    recent = (payload.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    filed_dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    accns = recent.get("accessionNumber") or []
    out: list[PeriodicFiling] = []
    for i, form in enumerate(forms):
        if form not in DOMESTIC_FORMS:
            continue
        if i >= len(accns) or i >= len(filed_dates) or not accns[i] or not filed_dates[i]:
            continue
        try:
            filed = date.fromisoformat(filed_dates[i])
        except ValueError:
            continue
        report: date | None = None
        if i < len(report_dates) and report_dates[i]:
            try:
                report = date.fromisoformat(report_dates[i])
            except ValueError:
                report = None
        out.append(PeriodicFiling(accns[i], form, filed, report))
    return _dedupe_periodic(out)


def _dedupe_periodic(filings: list[PeriodicFiling]) -> list[PeriodicFiling]:
    """One row per report date: the latest filed accession wins (covers 10-Q/A)."""
    by_end: dict[date | str, PeriodicFiling] = {}
    for f in filings:
        key: date | str = f.report_date or f.accn
        cur = by_end.get(key)
        if cur is None or f.filed > cur.filed or (f.filed == cur.filed and f.form.endswith("/A")):
            by_end[key] = f
    return sorted(by_end.values(), key=lambda f: (f.report_date or date.min, f.filed))


def latest_facts_period_end(rf: RevenueFacts) -> date | None:
    if not rf.filings:
        return None
    return max(info.period_end for info in rf.filings.values())


# Fiscal year-ends that land a few days after the calendar quarter are the same period.
FISCAL_END_SLACK_DAYS = 10


def newer_filings(filings: list[PeriodicFiling], latest_end: date | None) -> list[PeriodicFiling]:
    """The single latest official 10-Q/10-K that Company Facts does not already cover.

    Trying every historical filing after a stale Company Facts snapshot would fetch years
    of 10-Qs for REITs, banks, and pre-revenue biotechs, then treat a missing revenue
    line as an unresolved lag. Only the newest dated report can change Layer 1's latest
    quarter. Report dates within FISCAL_END_SLACK_DAYS of the facts period are the same
    fiscal quarter (e.g. 2026-07-03 vs 2026-06-30).
    """
    dated = [f for f in filings if f.report_date]
    if not dated:
        return []
    if latest_end is None:
        cutoff = None
        candidates = dated
    else:
        cutoff = latest_end + timedelta(days=FISCAL_END_SLACK_DAYS)
        candidates = [f for f in dated if f.report_date > cutoff]
    if not candidates:
        return []
    return [max(candidates, key=lambda f: (f.report_date, f.filed))]


def add_months(d: date, months: int) -> date:
    month0 = d.month - 1 + months
    year = d.year + month0 // 12
    month = month0 % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def facts_may_lag(latest_end: date | None, as_of: date, *, lag_days: int = TEN_Q_FILED_BY_DAYS) -> bool:
    """True when the next fiscal quarter is past its typical 10-Q filing window at as-of."""
    if latest_end is None:
        return True
    return as_of > add_months(latest_end, 3) + timedelta(days=lag_days)


def period_start(end: date, months: int) -> date:
    y, m = end.year, end.month - (months - 1)
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def pick_official_value(st: Statement, months: int, end: date) -> tuple[str, str, float] | None:
    """First total-revenue line (else first known revenue concept) for that statement column.

    Later rows with the same label are segment breakdowns, not a second guess at the total.
    """
    totals: list[tuple[str, str, float]] = []
    concepts: list[tuple[str, str, float]] = []
    for row in st.rows:
        val = st.value(row, months, end)
        if val is None:
            continue
        short = row.concept.split(":", 1)[-1]
        if is_total_revenue_label(row.label):
            totals.append((short, row.label, val))
        elif short in REVENUE_CONCEPTS:
            concepts.append((short, row.label, val))
    if totals:
        return totals[0]
    if concepts:
        return concepts[0]
    return None


def _step_fp(fy: int, fp: str) -> tuple[int, str]:
    if fp == "Q1":
        return fy, "Q2"
    if fp == "Q2":
        return fy, "Q3"
    if fp == "Q3":
        return fy, "FY"
    return fy + 1, "Q1"


def infer_fy_fp(filings: dict[str, FilingInfo], form: str) -> tuple[int | None, str | None]:
    labeled = [f for f in filings.values() if f.fy and f.fp]
    if not labeled:
        return None, "FY" if form in ANNUAL_FORMS else None
    last = max(labeled, key=lambda f: f.period_end)
    fy, fp = _step_fp(int(last.fy), last.fp or "FY")
    if form in ANNUAL_FORMS:
        while fp != "FY":
            fy, fp = _step_fp(fy, fp)
    elif fp == "FY":
        fy, fp = _step_fp(fy, fp)
    return fy, fp


def _months_to_try(form: str) -> list[int]:
    if form in QUARTERLY_FORMS:
        return [3, 6, 9]
    return [3, 12, 9, 6]


def supplement_revenue_facts(
    rf: RevenueFacts,
    filings: list[PeriodicFiling],
    fetch,
    as_of: date | None = None,
) -> tuple[RevenueFacts, SupplementResult]:
    """Add officially reported facts from EDGAR filings newer than Company Facts.

    `fetch(accn)` returns `(Statement, url)` or None. Existing standalone-quarter derivation and
    statement checks run on the merged facts afterward.
    """
    del as_of  # reserved; detection uses filing report dates, not the calendar heuristic
    latest = latest_facts_period_end(rf)
    newer = newer_filings(filings, latest)
    result = SupplementResult(status="current", latest_facts_end=latest, newer=newer)
    if not newer:
        return rf, result

    by_concept = {k: list(v) for k, v in rf.by_concept.items()}
    filing_map = dict(rf.filings)
    forms_seen = set(rf.forms_seen)

    for pf in newer:
        if pf.report_date is None:
            result.unresolved.append({"accn": pf.accn, "form": pf.form, "reason": "no_report_date"})
            continue
        existing = filing_map.get(pf.accn)
        if existing is not None and existing.period_end == pf.report_date:
            continue
        got = fetch(pf.accn)
        if got is None:
            result.unresolved.append(
                {
                    "accn": pf.accn,
                    "form": pf.form,
                    "reportDate": pf.report_date.isoformat(),
                    "reason": "income_statement_unavailable",
                }
            )
            continue
        st, url = got
        picked = None
        used_months = None
        for months in _months_to_try(pf.form):
            picked = pick_official_value(st, months, pf.report_date)
            if picked is not None:
                used_months = months
                break
        if picked is None or used_months is None:
            result.unresolved.append(
                {
                    "accn": pf.accn,
                    "form": pf.form,
                    "reportDate": pf.report_date.isoformat(),
                    "reason": "no_official_revenue_column",
                }
            )
            continue
        concept, label, val = picked
        start = period_start(pf.report_date, used_months)
        fy, fp = infer_fy_fp(filing_map, pf.form)
        fact = Fact(start, pf.report_date, val, pf.accn, fy, fp, pf.form, pf.filed)
        by_concept.setdefault(concept, []).append(fact)
        filing_map[pf.accn] = FilingInfo(pf.accn, pf.form, pf.filed, fy, fp, pf.report_date)
        forms_seen.add(pf.form)
        result.applied.append(
            AppliedFact(pf.accn, pf.form, pf.report_date, start, used_months, val, concept, label, url)
        )

    if result.applied:
        result.status = "applied"
        rf = RevenueFacts(rf.cik, rf.entity_name, rf.currency, by_concept, filing_map, forms_seen)
    elif result.unresolved:
        # A newer 10-Q with no total-revenue line (pre-revenue biotech, SPAC, bank) is
        # not a failed ingest. unresolved_edgar_lag is only for a statement we could
        # not obtain, or a report date we could not read.
        fetch_failures = {"income_statement_unavailable", "no_report_date"}
        if any(u.get("reason") in fetch_failures for u in result.unresolved):
            result.status = "unresolved"
        else:
            result.status = "current"
    return rf, result


def dataset_latest_end(company: dict) -> date | None:
    quarters = ((company.get("revenue") or {}).get("quarters")) or []
    ends = [date.fromisoformat(q["end"]) for q in quarters if q.get("end") and not q.get("missing")]
    return max(ends) if ends else None


def freshness_row(company: dict, filings: list[PeriodicFiling], as_of: date) -> dict:
    latest = dataset_latest_end(company)
    newer = newer_filings(filings, latest)
    status = "lagging" if newer else ("current" if not facts_may_lag(latest, as_of) else "expected_current")
    return {
        "ticker": company.get("ticker"),
        "cik": company.get("cik"),
        "latestQuarterEnd": latest.isoformat() if latest else None,
        "latestQuarter": next(
            (
                f"FY{q.get('fiscalYear')} Q{q.get('fiscalQuarter')}"
                for q in (company.get("revenue") or {}).get("quarters") or []
                if not q.get("missing") and q.get("fiscalYear")
            ),
            None,
        ),
        "status": status,
        "asOf": as_of.isoformat(),
        "newerFilings": [f.to_dict() for f in newer],
    }
