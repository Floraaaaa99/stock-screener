"""Derive standalone fiscal quarters from SEC revenue facts for a single XBRL concept.

Rules:
- Facts for the same (start, end) period are de-duplicated; the most recently filed value wins
  (restatements), and the earliest filing that reported that final value is cited.
- A ~3-month fact is a reported quarter.
- Missing quarters are derived from year-to-date facts: Q2 = 6M - Q1, Q3 = 9M - 6M, Q4 = FY - 9M,
  falling back to FY - (Q1 + Q2 + Q3) when no 9-month fact exists. Reported values take precedence.
- Fiscal year/quarter labels come from the filing in which the quarter is the current period.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .sec.facts import ANNUAL_FORMS, DOMESTIC_FORMS, Fact, FilingInfo

QUARTER_DAYS = (80, 100)
CHAIN_TOLERANCE_DAYS = 7
MAX_SLOTS = 12


def values_agree(a: float, b: float) -> bool:
    return abs(a - b) <= max(1000.0, 0.001 * max(abs(a), abs(b)))


def is_quarter_length(days: int) -> bool:
    return QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    val: float
    accn: str
    form: str
    filed: date
    restated: bool
    original_val: float
    original_accn: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def months(self) -> int:
        return round(self.days / 30.44)


@dataclass(frozen=True)
class Source:
    accn: str
    form: str
    filed: date
    start: date
    end: date
    val: float
    role: str
    sign: int = 1


def _negate(sources: list[Source]) -> list[Source]:
    return [Source(s.accn, s.form, s.filed, s.start, s.end, s.val, s.role, -s.sign) for s in sources]


@dataclass
class Quarter:
    start: date
    end: date
    val: float
    method: str
    formula: str
    sources: list[Source]
    concept: str
    restated: bool = False
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    label_inferred: bool = False
    flags: list[str] = field(default_factory=list)
    alternates: list[Quarter] = field(default_factory=list)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass
class MissingQuarter:
    start: date
    end: date
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None


Slot = Quarter | MissingQuarter


def _trailing_zeros(v: float) -> int:
    n = int(round(abs(v)))
    if n == 0:
        return 0
    tz = 0
    while n % 10 == 0:
        n //= 10
        tz += 1
    return tz


def filing_precision(facts: list[Fact]) -> dict[str, int]:
    """Reporting precision per filing, as a power of ten (3 = thousands, 6 = millions).

    Inferred from the fewest trailing zeros among the filing's non-zero values, so a single round
    number cannot make a filing look coarser than it is.
    """
    prec: dict[str, int] = {}
    for f in facts:
        if f.val == 0:
            continue
        tz = _trailing_zeros(f.val)
        prec[f.accn] = min(prec.get(f.accn, tz), tz)
    return prec


def same_up_to_rounding(precise: float, precise_prec: int, coarse: float, coarse_prec: int) -> bool:
    """True when `coarse` is `precise` re-reported in coarser units (e.g. 166,496,000 -> 167,000,000).

    One full unit of the coarse precision is allowed because companies adjust rounded figures so
    that quarters foot to year-to-date totals.
    """
    if coarse_prec <= precise_prec or coarse_prec < 3:
        return False
    return abs(precise - coarse) <= 10**coarse_prec


def dedupe_periods(facts: list[Fact]) -> dict[tuple[date, date], Period]:
    """One value per (start, end). The latest filing wins (restatements), except when the later value
    is only the earlier one rounded to coarser units, in which case the more precise value is kept.

    Verified 10-Q/10-K facts always supersede 8-K earnings figures for the same period.
    """
    prec = filing_precision(facts)
    groups: dict[tuple[date, date], list[Fact]] = {}
    for f in facts:
        groups.setdefault((f.start, f.end), []).append(f)
    out: dict[tuple[date, date], Period] = {}
    for key, fs in groups.items():
        verified = [f for f in fs if f.form in DOMESTIC_FORMS]
        pool = verified or fs
        pool.sort(key=lambda f: (f.filed, f.accn))
        final = pool[-1]
        final_val, final_prec = final.val, prec.get(final.accn, 0)
        for f in reversed(pool[:-1]):
            f_prec = prec.get(f.accn, 0)
            if same_up_to_rounding(f.val, f_prec, final_val, final_prec):
                final_val, final_prec = f.val, f_prec
        cited = next(f for f in pool if abs(f.val - final_val) < 0.5)
        original = pool[0]
        restated = abs(original.val - final_val) >= 0.5 and not same_up_to_rounding(
            original.val, prec.get(original.accn, 0), final_val, final_prec
        )
        out[key] = Period(
            start=key[0],
            end=key[1],
            val=final_val,
            accn=cited.accn,
            form=cited.form,
            filed=cited.filed,
            restated=restated,
            original_val=original.val,
            original_accn=original.accn,
        )
    return out


def _ytd_label(p: Period) -> str:
    m = p.months
    if m >= 11 and p.form in ANNUAL_FORMS:
        return "FY"
    return f"{m}M YTD" if m > 3 else "3M"


def _source(p: Period, role: str, sign: int = 1) -> Source:
    return Source(p.accn, p.form, p.filed, p.start, p.end, p.val, role, sign)


def derive_quarters(periods: dict[tuple[date, date], Period], concept: str) -> dict[date, Quarter]:
    """Return standalone quarters keyed by period end date."""
    quarters: dict[date, Quarter] = {}
    alternates: dict[date, list[Quarter]] = {}

    for p in periods.values():
        if is_quarter_length(p.days):
            q = Quarter(
                p.start, p.end, p.val, "reported", "3M reported", [_source(p, "quarter")], concept, restated=p.restated
            )
            existing = quarters.get(p.end)
            if existing is None or p.days > existing.days:
                quarters[p.end] = q

    ytd = sorted((p for p in periods.values() if p.days > QUARTER_DAYS[1]), key=lambda p: (p.end, p.days))

    def offer(q: Quarter) -> bool:
        cur = quarters.get(q.end)
        if cur is None:
            quarters[q.end] = q
            return True
        alternates.setdefault(q.end, []).append(q)
        return False

    for _ in range(4):
        changed = False
        for p in ytd:
            head = _subtract_tail(p, quarters, concept)
            if head and not any(abs((e - head.end).days) <= CHAIN_TOLERANCE_DAYS for e in quarters):
                changed |= offer(head)
            if p.end in quarters and quarters[p.end].method == "reported":
                cand = _subtract_ytd(p, periods, concept)
                if cand:
                    alternates.setdefault(p.end, []).append(cand)
                continue
            if p.end in quarters:
                continue
            cand = _subtract_ytd(p, periods, concept) or _subtract_chain(p, quarters, concept)
            if cand:
                changed |= offer(cand)
        if not changed:
            break

    for end, alts in alternates.items():
        q = quarters[end]
        q.alternates = alts
        for alt in alts:
            if not values_agree(alt.val, q.val) and "derivation_mismatch" not in q.flags:
                q.flags.append("derivation_mismatch")

    for q in quarters.values():
        if q.val < 0 and "negative_value" not in q.flags:
            q.flags.append("negative_value")
    return quarters


def _subtract_ytd(p: Period, periods: dict[tuple[date, date], Period], concept: str) -> Quarter | None:
    best: Period | None = None
    for b in periods.values():
        if b.start != p.start or b.end >= p.end:
            continue
        if not is_quarter_length((p.end - b.end).days):
            continue
        if best is None or b.end > best.end:
            best = b
    if best is None:
        return None
    formula = f"{_ytd_label(p)} − {_ytd_label(best)}"
    return Quarter(
        start=best.end + timedelta(days=1),
        end=p.end,
        val=p.val - best.val,
        method="derived",
        formula=formula,
        sources=[_source(p, "ytd_total"), _source(best, "ytd_prior", -1)],
        concept=concept,
        restated=p.restated or best.restated,
    )


def _subtract_chain(p: Period, quarters: dict[date, Quarter], concept: str) -> Quarter | None:
    """FY − (Q1 + Q2 + Q3) when the prior quarters are known but no 9-month YTD fact exists."""
    by_start = sorted(quarters.values(), key=lambda q: q.start)
    chain: list[Quarter] = []
    cursor = p.start
    for _ in range(3):
        nxt = next((q for q in by_start if abs((q.start - cursor).days) <= 3 and q.end < p.end), None)
        if nxt is None:
            break
        chain.append(nxt)
        cursor = nxt.end + timedelta(days=1)
        if is_quarter_length((p.end - nxt.end).days):
            break
    if not chain or not is_quarter_length((p.end - chain[-1].end).days):
        return None
    labels = " + ".join(f"Q{i + 1}" for i in range(len(chain)))
    return Quarter(
        start=chain[-1].end + timedelta(days=1),
        end=p.end,
        val=p.val - sum(q.val for q in chain),
        method="derived",
        formula=f"{_ytd_label(p)} − ({labels})",
        sources=[_source(p, "ytd_total")] + [s for q in chain for s in _negate(q.sources)],
        concept=concept,
        restated=p.restated or any(q.restated for q in chain),
    )


def _subtract_tail(p: Period, quarters: dict[date, Quarter], concept: str) -> Quarter | None:
    """Earliest quarter of a YTD period from its later reported quarters, e.g. Q1 = 6M YTD − Q2.

    Covers filings missing from Company Facts whose figures survive as YTD totals in later filings.
    """
    chain: list[Quarter] = []
    cursor_end = p.end
    for _ in range(3):
        q = quarters.get(cursor_end)
        if q is None or q.method != "reported":
            return None
        chain.append(q)
        head_end = q.start - timedelta(days=1)
        head_days = (head_end - p.start).days + 1
        if is_quarter_length(head_days):
            labels = " − ".join(f"Q{len(chain) - i + 1}" for i in range(len(chain)))
            return Quarter(
                start=p.start,
                end=head_end,
                val=p.val - sum(c.val for c in chain),
                method="derived",
                formula=f"{_ytd_label(p)} − {labels}",
                sources=[_source(p, "ytd_total")] + [s for c in chain for s in _negate(c.sources)],
                concept=concept,
                restated=p.restated or any(c.restated for c in chain),
            )
        if head_days < QUARTER_DAYS[0]:
            return None
        cursor_end = head_end
    return None


def label_quarters(quarters: dict[date, Quarter], filings: dict[str, FilingInfo]) -> None:
    """Assign fiscal year/quarter from the filing whose current period ends on the quarter end."""
    by_end: dict[date, list[FilingInfo]] = {}
    for f in filings.values():
        by_end.setdefault(f.period_end, []).append(f)
    for q in quarters.values():
        cands = sorted(by_end.get(q.end, []), key=lambda f: f.filed)
        for f in cands:
            fq = {"Q1": 1, "Q2": 2, "Q3": 3, "FY": 4}.get(f.fp or "")
            if f.fy and fq:
                q.fiscal_year, q.fiscal_quarter = f.fy, fq
                break

    ordered = sorted(quarters.values(), key=lambda q: q.end)
    for _ in range(2):
        for i, q in enumerate(ordered):
            if q.fiscal_quarter is not None:
                continue
            prev = ordered[i - 1] if i > 0 else None
            nxt = ordered[i + 1] if i + 1 < len(ordered) else None
            if prev and prev.fiscal_quarter and _adjacent(prev, q):
                q.fiscal_quarter = prev.fiscal_quarter % 4 + 1
                q.fiscal_year = prev.fiscal_year + (1 if prev.fiscal_quarter == 4 else 0)
                q.label_inferred = True
            elif nxt and nxt.fiscal_quarter and _adjacent(q, nxt):
                q.fiscal_quarter = (nxt.fiscal_quarter - 2) % 4 + 1
                q.fiscal_year = nxt.fiscal_year - (1 if nxt.fiscal_quarter == 1 else 0)
                q.label_inferred = True


def _adjacent(older: Quarter | MissingQuarter, newer: Quarter | MissingQuarter) -> bool:
    return abs((newer.start - older.end).days - 1) <= CHAIN_TOLERANCE_DAYS


def build_timeline(
    quarters: dict[date, Quarter], anchor_end: date | None = None, max_slots: int = MAX_SLOTS
) -> list[Slot]:
    """Latest `max_slots` consecutive quarter slots, newest first; gaps become MissingQuarter slots.

    Trailing missing slots (before the company's first available quarter) are not emitted.
    """
    if not quarters:
        return []
    ordered = sorted(quarters.values(), key=lambda q: q.end, reverse=True)
    if anchor_end is None:
        anchor_end = ordered[0].end

    def find(end: date) -> Quarter | None:
        best = None
        for q in ordered:
            diff = abs((q.end - end).days)
            if diff <= CHAIN_TOLERANCE_DAYS and (best is None or diff < abs((best.end - end).days)):
                best = q
        return best

    slots: list[Slot] = []
    expected_end = anchor_end
    oldest = ordered[-1].end
    while len(slots) < max_slots and expected_end >= oldest - timedelta(days=CHAIN_TOLERANCE_DAYS):
        q = find(expected_end)
        if q is not None:
            slots.append(q)
            expected_end = q.start - timedelta(days=1)
        else:
            start = _approx_quarter_start(expected_end)
            slots.append(MissingQuarter(start=start, end=expected_end))
            expected_end = start - timedelta(days=1)
    while slots and isinstance(slots[-1], MissingQuarter):
        slots.pop()
    _label_missing(slots)
    return slots


def _approx_quarter_start(end: date) -> date:
    month = end.month - 3
    year = end.year
    if month <= 0:
        month += 12
        year -= 1
    day = min(end.day, 28)
    return date(year, month, day) + timedelta(days=1)


def _label_missing(slots: list[Slot]) -> None:
    for i, s in enumerate(slots):
        if not isinstance(s, MissingQuarter):
            continue
        newer = slots[i - 1] if i > 0 else None
        if newer is not None and newer.fiscal_quarter:
            s.fiscal_quarter = (newer.fiscal_quarter - 2) % 4 + 1
            s.fiscal_year = newer.fiscal_year - (1 if newer.fiscal_quarter == 1 else 0)


def annual_check(quarters: dict[date, Quarter], periods: dict[tuple[date, date], Period]) -> list[date]:
    """End dates of fiscal years whose four reported quarters do not sum to the reported annual value."""
    bad: list[date] = []
    for p in periods.values():
        if not (350 <= p.days <= 380 and p.form in ANNUAL_FORMS):
            continue
        qs = [q for q in quarters.values() if p.start <= q.start and q.end <= p.end]
        if len(qs) == 4 and all(q.method == "reported" for q in qs):
            if not values_agree(sum(q.val for q in qs), p.val):
                bad.append(p.end)
    return bad
