"""Extract revenue facts from an SEC Company Facts payload."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Total-revenue concepts in priority order. Priority is only a tie-breaker between concepts that
# report the same values; it never decides between concepts that disagree (see concepts.py).
REVENUE_CONCEPTS: list[str] = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
]

QUARTERLY_FORMS = {"10-Q", "10-Q/A", "10-QT", "10-QT/A"}
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "10-KT/A"}
DOMESTIC_FORMS = QUARTERLY_FORMS | ANNUAL_FORMS
FOREIGN_FORMS = {"20-F", "20-F/A", "40-F", "40-F/A", "6-K", "6-K/A"}


@dataclass(frozen=True)
class Fact:
    start: date
    end: date
    val: float
    accn: str
    fy: int | None
    fp: str | None
    form: str
    filed: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _d(s: str) -> date:
    return date.fromisoformat(s)


def parse_fact(raw: dict) -> Fact | None:
    if "start" not in raw or "end" not in raw or raw.get("val") is None:
        return None
    return Fact(
        start=_d(raw["start"]),
        end=_d(raw["end"]),
        val=float(raw["val"]),
        accn=raw["accn"],
        fy=raw.get("fy"),
        fp=raw.get("fp"),
        form=raw.get("form", ""),
        filed=_d(raw["filed"]),
    )


@dataclass(frozen=True)
class FilingInfo:
    accn: str
    form: str
    filed: date
    fy: int | None
    fp: str | None
    period_end: date


@dataclass
class RevenueFacts:
    cik: str
    entity_name: str
    currency: str | None
    by_concept: dict[str, list[Fact]]
    filings: dict[str, FilingInfo]
    forms_seen: set[str]

    @property
    def is_foreign_filer(self) -> bool:
        has_domestic = bool(self.forms_seen & DOMESTIC_FORMS)
        return not has_domestic and bool(self.forms_seen & FOREIGN_FORMS)


def _forms_in(facts_root: dict) -> set[str]:
    forms: set[str] = set()
    for taxonomy in facts_root.values():
        for concept in taxonomy.values():
            for unit_facts in concept.get("units", {}).values():
                for f in unit_facts:
                    forms.add(f.get("form", ""))
    return forms


def _pick_unit(units: dict[str, list]) -> str | None:
    if "USD" in units:
        return "USD"
    monetary = [u for u in units if "/" not in u and u.isalpha() and len(u) == 3]
    return monetary[0] if len(monetary) == 1 else None


def extract_revenue_facts(companyfacts: dict) -> RevenueFacts:
    """Revenue duration facts from 10-Q/10-K filings, grouped by concept, plus per-filing metadata.

    A filing's period end is the latest end date among its revenue facts. Company Facts tags every
    fact with the fiscal year/period of the *filing*, so comparative prior-year figures carry the
    filing's fy/fp; quarters are therefore labelled from the filing in which they are the current period.
    """
    cik = str(companyfacts.get("cik", "")).zfill(10)
    root = companyfacts.get("facts", {})
    gaap = root.get("us-gaap", {})
    forms_seen = _forms_in(root)

    currencies = {
        _pick_unit(gaap[c].get("units", {})) for c in REVENUE_CONCEPTS if c in gaap
    } - {None}
    currency = "USD" if "USD" in currencies else (next(iter(currencies)) if len(currencies) == 1 else None)

    by_concept: dict[str, list[Fact]] = {}
    filings: dict[str, FilingInfo] = {}
    if currency:
        for concept in REVENUE_CONCEPTS:
            raw_list = gaap.get(concept, {}).get("units", {}).get(currency, [])
            facts = [
                f
                for f in (parse_fact(r) for r in raw_list)
                if f is not None and f.form in DOMESTIC_FORMS
            ]
            if facts:
                by_concept[concept] = facts
            for f in facts:
                info = filings.get(f.accn)
                if info is None or f.end > info.period_end:
                    filings[f.accn] = FilingInfo(f.accn, f.form, f.filed, f.fy, f.fp, f.end)

    return RevenueFacts(
        cik=cik,
        entity_name=companyfacts.get("entityName", ""),
        currency=currency,
        by_concept=by_concept,
        filings=filings,
        forms_seen=forms_seen,
    )


def filing_url(cik: str, accn: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.htm"
