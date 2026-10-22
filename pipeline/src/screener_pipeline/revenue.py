"""Company-level revenue analysis: concept selection, 12-quarter timeline, TTM, and filing checks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from .concepts import (
    ConceptSeries,
    Selection,
    prefer_attributable_net_income,
    select_concept,
    verify_against_statement,
)
from .quarters import (
    MissingQuarter,
    Quarter,
    Slot,
    annual_check,
    build_timeline,
    dedupe_periods,
    derive_quarters,
    label_quarters,
    values_agree,
)
from .sec.facts import (
    CURRENT_REPORT_FORMS,
    DOMESTIC_FORMS,
    EARNINGS_CONCEPTS,
    QUARTERLY_FORMS,
    REVENUE_CONCEPTS,
    FilingInfo,
    RevenueFacts,
)
from .sec.statement import (
    Statement,
    StatementEvidence,
    StatementRow,
    evidence_from_statement,
    is_net_income_label,
    is_total_revenue_label,
)
from .ttm import TTMResult, compute_ttm

StatementFetcher = Callable[[str], tuple[Statement, str] | None]


@dataclass(frozen=True)
class MetricSpec:
    key: str
    concepts: list[str]
    is_face_line: Callable[[str], bool]
    line_name: str
    none_reason: str
    no_quarterly_reason: str
    prefer_face: Callable | None = None


REVENUE_SPEC = MetricSpec(
    "revenue",
    REVENUE_CONCEPTS,
    is_total_revenue_label,
    "total revenue",
    "no_revenue_concept",
    "no_quarterly_revenue",
)
EARNINGS_SPEC = MetricSpec(
    "earnings",
    EARNINGS_CONCEPTS,
    is_net_income_label,
    "net income",
    "no_earnings_concept",
    "no_quarterly_earnings",
    prefer_attributable_net_income,
)

STALE_AFTER_DAYS = 270


@dataclass
class QuarterCheck:
    status: str
    accn: str | None = None
    form: str | None = None
    url: str | None = None
    statement_label: str | None = None
    statement_value: float | None = None
    expected_value: float | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "")}


@dataclass
class CompanyRevenue:
    status: str
    currency: str | None
    selection: Selection | None
    slots: list[Slot]
    ttm: TTMResult
    statement_check: dict | None = None
    quarter_checks: dict[date, QuarterCheck] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)


def original_filing(
    filings: dict[str, FilingInfo],
    period_end: date,
    *,
    forms: set[str] | None = None,
) -> FilingInfo | None:
    """The first non-amended filing whose current period ends on `period_end` (amendments as fallback)."""
    cands = [f for f in filings.values() if f.period_end == period_end]
    if forms is not None:
        cands = [f for f in cands if f.form in forms]
    cands.sort(key=lambda f: (f.form.endswith("/A"), f.filed))
    return cands[0] if cands else None


def _face_row(
    st: Statement,
    concept: str,
    months: int,
    end: date,
    target: float | None,
    is_face_line: Callable[[str], bool],
) -> StatementRow | None:
    same = [r for r in st.rows if r.concept == f"us-gaap:{concept}" and st.value(r, months, end) is not None]
    totals = [r for r in st.rows if is_face_line(r.label) and st.value(r, months, end) is not None]
    for pool in (same, totals):
        if target is not None:
            for r in pool:
                if values_agree(st.value(r, months, end), target):
                    return r
        if pool:
            return pool[0]
    return None


def _months(start: date, end: date) -> int:
    return round(((end - start).days + 1) / 30.44)


def verify_quarter(
    q: Quarter,
    fetch: StatementFetcher,
    *,
    is_face_line: Callable[[str], bool] = is_total_revenue_label,
    line_name: str = "revenue",
) -> QuarterCheck:
    """Check every fact a quarter is built from against the income statement of the filing it is cited from.

    A reported quarter is compared with the filing's 3-month column; a derived quarter (e.g. FY − 9M)
    is recomputed from the statement columns of its source filings. A reported quarter that only appears
    in the notes (e.g. Q4 in a 10-K) is verified through an agreeing alternative derivation.
    """
    check = _verify_sources(q, fetch, is_face_line, line_name)
    if check.status != "unavailable":
        return check
    for alt in q.alternates:
        if not values_agree(alt.val, q.val):
            continue
        alt_check = _verify_sources(alt, fetch, is_face_line, line_name)
        if alt_check.status == "match":
            alt_check.detail = (
                f"The reported 3-month figure is not on the face of {check.form} {check.accn}; "
                f"verified as {alt.formula}: {alt_check.detail}"
            )
            return alt_check
    return check


def _verify_sources(
    q: Quarter,
    fetch: StatementFetcher,
    is_face_line: Callable[[str], bool] = is_total_revenue_label,
    line_name: str = "revenue",
) -> QuarterCheck:
    face_values: list[float] = []
    parts: list[str] = []
    first_url = first_label = None
    for s in q.sources:
        got = fetch(s.accn)
        if got is None:
            return QuarterCheck(
                "unavailable", s.accn, s.form, detail=f"Income statement of {s.form} {s.accn} could not be read."
            )
        st, url = got
        months = _months(s.start, s.end)
        row = _face_row(st, q.concept, months, s.end, s.val, is_face_line)
        face = st.value(row, months, s.end) if row else None
        if face is None:
            return QuarterCheck(
                "unavailable",
                s.accn,
                s.form,
                url,
                detail=f"No {months}-month {line_name} column ending {s.end} on {s.form} {s.accn}.",
            )
        if not values_agree(face, s.val):
            return QuarterCheck(
                "mismatch",
                s.accn,
                s.form,
                url,
                row.label,
                face,
                s.val,
                detail=f"{months}-month value on {s.form} {s.accn} is {face:,.0f}; Company Facts has {s.val:,.0f}.",
            )
        if first_url is None:
            first_url, first_label = url, row.label
        face_values.append(s.sign * face)
        parts.append(f"{'+' if s.sign > 0 else '−'} {months}M {face:,.0f} ({s.form} {s.accn})")

    expected = sum(face_values)
    status = "match" if values_agree(expected, q.val) else "mismatch"
    primary = q.sources[0]
    detail = " ".join(parts).lstrip("+ ") if q.method == "derived" else ""
    return QuarterCheck(status, primary.accn, primary.form, first_url, first_label, face_values[0], expected, detail)


def _eight_k_sources(q: Quarter) -> bool:
    return bool(q.sources) and all(s.form in CURRENT_REPORT_FORMS for s in q.sources)


def _latest_evidence(rf: RevenueFacts, fetch: StatementFetcher) -> StatementEvidence | None:
    domestic = [f for f in rf.filings.values() if f.form in DOMESTIC_FORMS]
    if not domestic:
        return None
    latest_end = max(f.period_end for f in domestic)
    f = original_filing(rf.filings, latest_end, forms=DOMESTIC_FORMS)
    if f is None:
        return None
    got = fetch(f.accn)
    if got is None:
        return None
    st, url = got
    months = 3 if f.form in QUARTERLY_FORMS else 12
    return evidence_from_statement(st, f.accn, f.form, url, months, f.period_end)


def analyze_company(
    rf: RevenueFacts,
    fetch: StatementFetcher,
    *,
    override: str | None = None,
    verify_quarters: bool = True,
    today: date | None = None,
    spec: MetricSpec = REVENUE_SPEC,
) -> CompanyRevenue:
    if not rf.by_concept:
        if rf.is_foreign_filer:
            return CompanyRevenue("foreign_filer", rf.currency, None, [], TTMResult(None, None, None, "foreign_filer"))
        return CompanyRevenue("no_revenue_facts", rf.currency, None, [], TTMResult(None, None, None, spec.none_reason))

    series: dict[str, ConceptSeries] = {}
    for concept, facts in rf.by_concept.items():
        periods = dedupe_periods(facts)
        quarters = derive_quarters(periods, concept)
        label_quarters(quarters, rf.filings)
        series[concept] = ConceptSeries(concept, periods, quarters)

    evidence = _latest_evidence(rf, fetch)
    sel = select_concept(
        list(series.values()),
        evidence,
        override,
        is_face_line=spec.is_face_line,
        concepts=spec.concepts,
        line_name=spec.line_name,
        prefer_face=spec.prefer_face,
    )
    flags = list(sel.flags)

    if sel.status == "ambiguous":
        return CompanyRevenue(
            "ambiguous", rf.currency, sel, [], TTMResult(None, None, None, "ambiguous_concept"), flags=flags
        )
    if sel.concept is None:
        return CompanyRevenue(
            "no_revenue_facts", rf.currency, sel, [], TTMResult(None, None, None, spec.no_quarterly_reason), flags=flags
        )

    slots = build_timeline(sel.quarters, sel.anchor_end)
    check_status, ours, theirs = verify_against_statement(sel, series, evidence, is_face_line=spec.is_face_line)
    statement_check = {
        "status": check_status,
        "accn": evidence.accn if evidence else None,
        "form": evidence.form if evidence else None,
        "url": evidence.url if evidence else None,
        "period_end": evidence.end.isoformat() if evidence else None,
        "months": evidence.months if evidence else None,
        "pipeline_value": ours,
        "statement_value": theirs,
    }

    window_start = slots[-1].start if slots else None
    bad_years = [
        d
        for d in annual_check(series[sel.concept].quarters, series[sel.concept].periods)
        if window_start and d >= window_start
    ]
    if bad_years:
        flags.append("annual_sum_mismatch")

    checks: dict[date, QuarterCheck] = {}
    if verify_quarters:
        for s in slots:
            if not isinstance(s, Quarter):
                continue
            if _eight_k_sources(s):
                primary = s.sources[0]
                checks[s.end] = QuarterCheck(
                    "awaiting_10q",
                    primary.accn,
                    primary.form,
                    detail="8-K earnings release; no face income statement to verify.",
                )
                continue
            checks[s.end] = verify_quarter(s, fetch, is_face_line=spec.is_face_line, line_name=spec.line_name)

    for s in slots:
        if isinstance(s, Quarter):
            for fl in s.flags:
                if fl not in flags:
                    flags.append(fl)

    today = today or date.today()
    if slots and (today - slots[0].end).days > STALE_AFTER_DAYS:
        flags.append("stale_filings")

    blocking = ttm_window_block_reason(slots, checks, check_status, verify_quarters=verify_quarters)
    ttm = compute_ttm(slots, blocking)
    if blocking:
        flags.append(blocking)

    return CompanyRevenue("ok", rf.currency, sel, slots, ttm, statement_check, checks, flags)


VERIFIED_CHECK = "match"
PROVISIONAL_CHECK = "awaiting_10q"


def ttm_window_block_reason(
    slots: list[Slot],
    checks: dict[date, QuarterCheck],
    statement_status: str | None,
    *,
    verify_quarters: bool,
) -> str | None:
    """Mismatched or unverified TTM-window quarters never contribute to TTM figures.

    The dataset-level 10% mismatch gate is a publish brake only. Per company, any of the 8
    TTM-window quarters that is a mismatch or not verified against its filing blocks Current
    TTM, Previous TTM, and growth. The company stays in the table with N/A and this reason.
    """
    if statement_status == "mismatch":
        return "statement_mismatch"
    if not verify_quarters:
        return None
    for s in slots[:8]:
        if not isinstance(s, Quarter):
            continue
        check = checks.get(s.end)
        if check is None:
            return "unverified_quarters"
        if check.status == "mismatch":
            return "filing_mismatch"
        if check.status not in {VERIFIED_CHECK, PROVISIONAL_CHECK}:
            return "unverified_quarters"
    return None


def slot_role(index: int) -> str | None:
    if index < 4:
        return "current"
    if index < 8:
        return "previous"
    return None


__all__ = [
    "CompanyRevenue",
    "EARNINGS_SPEC",
    "MissingQuarter",
    "Quarter",
    "REVENUE_SPEC",
    "analyze_company",
    "slot_role",
    "ttm_window_block_reason",
    "verify_quarter",
]
