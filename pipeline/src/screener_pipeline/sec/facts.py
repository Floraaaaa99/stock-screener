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

# Bottom-line earnings. Priority is only a tie-breaker when values agree.
EARNINGS_CONCEPTS: list[str] = [
    "NetIncomeLoss",
    "ProfitLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "NetIncomeLossAttributableToParent",
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


def extract_duration_facts(companyfacts: dict, concepts: list[str]) -> RevenueFacts:
    """Duration facts from 10-Q/10-K filings for the given us-gaap concepts."""
    cik = str(companyfacts.get("cik", "")).zfill(10)
    root = companyfacts.get("facts", {})
    gaap = root.get("us-gaap", {})
    forms_seen = _forms_in(root)

    currencies = {_pick_unit(gaap[c].get("units", {})) for c in concepts if c in gaap} - {None}
    currency = "USD" if "USD" in currencies else (next(iter(currencies)) if len(currencies) == 1 else None)

    by_concept: dict[str, list[Fact]] = {}
    filings: dict[str, FilingInfo] = {}
    if currency:
        for concept in concepts:
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


def extract_revenue_facts(companyfacts: dict) -> RevenueFacts:
    """Revenue duration facts from 10-Q/10-K filings, grouped by concept, plus per-filing metadata.

    A filing's period end is the latest end date among its revenue facts. Company Facts tags every
    fact with the fiscal year/period of the *filing*, so comparative prior-year figures carry the
    filing's fy/fp; quarters are therefore labelled from the filing in which they are the current period.
    """
    return extract_duration_facts(companyfacts, REVENUE_CONCEPTS)


def extract_earnings_facts(companyfacts: dict) -> RevenueFacts:
    return extract_duration_facts(companyfacts, EARNINGS_CONCEPTS)


def _compact_facts_list(facts: list[Fact]) -> list[dict]:
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


def compact_by_concept(rf: RevenueFacts) -> dict[str, list[dict]]:
    return {concept: _compact_facts_list(facts) for concept, facts in rf.by_concept.items()}


def compact_revenue_facts(rf: RevenueFacts, earnings: RevenueFacts | None = None) -> dict:
    """JSON-ready extracted facts only — not the full Company Facts payload."""
    payload = {
        "cik": rf.cik,
        "entityName": rf.entity_name,
        "currency": rf.currency,
        "formsSeen": sorted(rf.forms_seen),
        "byConcept": compact_by_concept(rf),
        "filings": {
            accn: {
                "accn": info.accn,
                "form": info.form,
                "filed": info.filed.isoformat(),
                "fy": info.fy,
                "fp": info.fp,
                "period_end": info.period_end.isoformat(),
            }
            for accn, info in rf.filings.items()
        },
    }
    if earnings is not None:
        payload["earningsByConcept"] = compact_by_concept(earnings)
        payload["earningsCurrency"] = earnings.currency
        payload["earningsFilings"] = {
            accn: {
                "accn": info.accn,
                "form": info.form,
                "filed": info.filed.isoformat(),
                "fy": info.fy,
                "fp": info.fp,
                "period_end": info.period_end.isoformat(),
            }
            for accn, info in earnings.filings.items()
        }
        payload["earningsFormsSeen"] = sorted(earnings.forms_seen)
    return payload


def duration_facts_from_compact(
    data: dict,
    *,
    concept_key: str = "byConcept",
    currency_key: str = "currency",
    filings_key: str = "filings",
    forms_key: str = "formsSeen",
) -> RevenueFacts:
    by_concept: dict[str, list[Fact]] = {}
    for concept, rows in (data.get(concept_key) or {}).items():
        facts = [parse_fact(r) for r in rows]
        by_concept[concept] = [f for f in facts if f is not None]
    filings = {
        accn: FilingInfo(
            accn=info["accn"],
            form=info["form"],
            filed=_d(info["filed"]),
            fy=info.get("fy"),
            fp=info.get("fp"),
            period_end=_d(info["period_end"]),
        )
        for accn, info in (data.get(filings_key) or {}).items()
    }
    return RevenueFacts(
        cik=str(data.get("cik", "")).zfill(10),
        entity_name=data.get("entityName", ""),
        currency=data.get(currency_key),
        by_concept=by_concept,
        filings=filings,
        forms_seen=set(data.get(forms_key) or []),
    )


def revenue_facts_from_compact(data: dict) -> RevenueFacts:
    return duration_facts_from_compact(data)


def earnings_facts_from_compact(data: dict) -> RevenueFacts | None:
    if not data.get("earningsByConcept"):
        return None
    return duration_facts_from_compact(
        data,
        concept_key="earningsByConcept",
        currency_key="earningsCurrency",
        filings_key="earningsFilings",
        forms_key="earningsFormsSeen",
    )


def filing_url(cik: str, accn: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.htm"
