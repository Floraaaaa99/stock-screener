"""Choose a consistent, comparable revenue concept for a company's latest 12 quarters.

A concept is never chosen because its values are larger. The rules, in order:
1. A documented override (pipeline/config/concept_overrides.json), validated against filings.
2. If every candidate concept that has quarters in the 12-quarter window reports the same values where
   they overlap, the concepts are equivalent: the best-covered current one is used, and gaps may be
   filled from equivalent concepts (verified by at least one overlapping quarter).
3. If candidates disagree, the face of the latest filing's income statement decides: the candidate
   presented as (total) revenue there is used.
4. Otherwise the company is flagged "ambiguous" and no TTM figures are produced.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from .quarters import CHAIN_TOLERANCE_DAYS, Period, Quarter, values_agree
from .sec.facts import REVENUE_CONCEPTS
from .sec.statement import StatementEvidence, is_total_revenue_label

FaceLine = Callable[[str], bool]

WINDOW_DAYS = 12 * 92


@dataclass
class ConceptSeries:
    concept: str
    periods: dict[tuple[date, date], Period]
    quarters: dict[date, Quarter]

    @property
    def latest_end(self) -> date | None:
        return max(self.quarters) if self.quarters else None


@dataclass
class Selection:
    status: str
    concept: str | None
    quarters: dict[date, Quarter]
    anchor_end: date | None
    flags: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    note: str = ""


def _match(quarters: dict[date, Quarter], end: date) -> Quarter | None:
    for e, q in quarters.items():
        if abs((e - end).days) <= CHAIN_TOLERANCE_DAYS:
            return q
    return None


def compare(a: ConceptSeries, b: ConceptSeries, window_start: date) -> tuple[int, int]:
    """(overlapping quarters, disagreeing quarters) within the window."""
    overlaps = disagreements = 0
    for end, qa in a.quarters.items():
        if end < window_start:
            continue
        qb = _match(b.quarters, end)
        if qb is None:
            continue
        overlaps += 1
        if not values_agree(qa.val, qb.val):
            disagreements += 1
    return overlaps, disagreements


def _coverage(s: ConceptSeries, window_start: date) -> int:
    return sum(1 for e in s.quarters if e >= window_start)


def _priority(concept: str, concepts: list[str]) -> int:
    return concepts.index(concept) if concept in concepts else len(concepts)


def _resolve_by_statement(
    group: list[ConceptSeries],
    evidence: StatementEvidence | None,
    is_face_line: FaceLine,
) -> ConceptSeries | None:
    if evidence is None:
        return None
    present = [(s, row) for s in group for row in evidence.concept_rows(s.concept)]
    if not present:
        return None
    if len(present) == 1:
        s, row = present[0]
        other_totals = [
            r for r in evidence.rows if is_face_line(r[1]) and r[0] != f"us-gaap:{s.concept}"
        ]
        if is_face_line(row[1]) or not other_totals:
            return s
        return None
    totals = {s.concept: s for s, row in present if is_face_line(row[1])}
    if len(totals) == 1:
        return next(iter(totals.values()))
    return None


def select_concept(
    series: list[ConceptSeries],
    evidence: StatementEvidence | None = None,
    override: str | None = None,
    *,
    is_face_line: FaceLine = is_total_revenue_label,
    concepts: list[str] | None = None,
    line_name: str = "total revenue",
) -> Selection:
    rank = concepts or REVENUE_CONCEPTS
    usable = [s for s in series if s.quarters]
    if not usable:
        return Selection("none", None, {}, None, note=f"No quarterly {line_name} facts in 10-Q/10-K filings.")

    latest = max(s.latest_end for s in usable if s.latest_end)
    window_start = latest - timedelta(days=WINDOW_DAYS)
    current = [s for s in usable if s.latest_end and abs((s.latest_end - latest).days) <= CHAIN_TOLERANCE_DAYS]
    relevant = [s for s in usable if _coverage(s, window_start) > 0]
    current.sort(key=lambda s: (-_coverage(s, window_start), _priority(s.concept, rank)))

    def summary(chosen: ConceptSeries | None, reference: ConceptSeries | None = None) -> list[dict]:
        """Candidate overview; overlaps are measured against the chosen (or reference) concept."""
        ref = chosen or reference
        out = []
        for s in sorted(relevant, key=lambda s: _priority(s.concept, rank)):
            lq = s.quarters[s.latest_end] if s.latest_end else None
            ov, dis = compare(s, ref, window_start) if ref and s is not ref else (0, 0)
            on_statement = None
            if evidence is not None:
                rows = evidence.concept_rows(s.concept)
                on_statement = rows[0][1] if rows else None
            out.append({
                "concept": s.concept,
                "latestEnd": s.latest_end.isoformat() if s.latest_end else None,
                "latestValue": lq.val if lq else None,
                "quartersInWindow": _coverage(s, window_start),
                "selected": s is chosen,
                "comparedWith": ref.concept if ref and s is not ref else None,
                "overlaps": ov,
                "disagreements": dis,
                "statementLabel": on_statement,
            })
        return out

    chosen: ConceptSeries | None = None
    status = ""
    flags: list[str] = []
    note = ""

    by_name = {s.concept: s for s in usable}
    if override and override in by_name:
        chosen, status = by_name[override], "override"
        note = "Concept set by a documented override validated against SEC filings."
    else:
        primary = current[0]
        conflicts = [s for s in relevant if s is not primary and compare(primary, s, window_start)[1] > 0]
        if not conflicts:
            chosen = primary
            status = "single" if len(relevant) == 1 else "equivalent"
        else:
            group = [primary] + [s for s in conflicts if s in current]
            resolved = _resolve_by_statement(group, evidence, is_face_line)
            if resolved is not None:
                chosen, status = resolved, "statement_verified"
                note = (
                    f"Candidate concepts disagree; {resolved.concept} is the {line_name} line presented on the "
                    f"income statement of filing {evidence.accn}."
                )
            else:
                names = ", ".join(
                    sorted({primary.concept, *(s.concept for s in conflicts)}, key=lambda c: _priority(c, rank))
                )
                return Selection(
                    "ambiguous",
                    None,
                    {},
                    latest,
                    flags=["ambiguous_concept"],
                    candidates=summary(None, primary),
                    note=f"Concepts disagree ({names}) and the income statement does not resolve which "
                    f"is {line_name}.",
                )

    merged: dict[date, Quarter] = dict(chosen.quarters)
    for s in sorted(relevant, key=lambda s: _priority(s.concept, rank)):
        if s is chosen:
            continue
        overlaps, disagreements = compare(s, chosen, window_start)
        if disagreements:
            if "other_concept_disagrees" not in flags:
                flags.append("other_concept_disagrees")
            continue
        if overlaps == 0:
            if "concept_change_unverified" not in flags:
                flags.append("concept_change_unverified")
            continue
        for end, q in s.quarters.items():
            if end >= window_start and _match(merged, end) is None:
                merged[end] = q
                if "concept_merged" not in flags:
                    flags.append("concept_merged")

    return Selection(status, chosen.concept, merged, latest, flags=flags, candidates=summary(chosen), note=note)


def verify_against_statement(
    selection: Selection,
    series: dict[str, ConceptSeries],
    evidence: StatementEvidence | None,
    *,
    is_face_line: FaceLine = is_total_revenue_label,
) -> tuple[str, float | None, float | None]:
    """Compare the pipeline value for the evidence period with the face of the income statement.

    Returns (status, pipeline_value, statement_value). Status is one of: verified (same concept and
    value), verified_value (same value on a revenue line with another tag), mismatch, not_presented,
    unavailable.
    """
    if evidence is None or selection.concept is None:
        return "unavailable", None, None
    ours: float | None = None
    if evidence.months == 3:
        q = _match(selection.quarters, evidence.end)
        ours = q.val if q else None
    else:
        s = series.get(selection.concept)
        for p in (s.periods.values() if s else []):
            if p.end == evidence.end and 350 <= p.days <= 380:
                ours = p.val
    if ours is None:
        return "unavailable", None, None

    same = [r for r in evidence.concept_rows(selection.concept) if r[2] is not None]
    for r in same:
        if values_agree(r[2], ours):
            return "verified", ours, r[2]
    totals = [r for r in evidence.rows if r[2] is not None and is_face_line(r[1])]
    for r in totals:
        if values_agree(r[2], ours):
            return "verified_value", ours, r[2]
    if same or totals:
        ref = (same or totals)[0][2]
        return "mismatch", ours, ref
    return "not_presented", ours, None
