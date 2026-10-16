"""Extract and derive Layer 3 financial metrics from SEC Company Facts.

Reuses quarter derivation (including YTD → standalone Q and Q4 = FY − 9M) and TTM windowing.
Missing or unverified values stay null with a reason. Never mapped to zero.
Does not compute the 100-point score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .layer3_concepts import (
    CAPEX_CONCEPTS,
    CASH_CONCEPTS,
    DA_CONCEPTS,
    FLOW_CONCEPTS,
    INTEREST_CONCEPTS,
    LAYER3_EXTRACTION_VERSION,
    LT_DEBT_CONCEPTS,
    OCF_CONCEPTS,
    OPERATING_INCOME_CONCEPTS,
    ST_DEBT_PART_CONCEPTS,
    ST_DEBT_TOTAL_CONCEPTS,
    STOCK_CONCEPTS,
    is_financial_sic,
)
from .quarters import MissingQuarter, Quarter, Slot, build_timeline, dedupe_periods, derive_quarters, label_quarters
from .sec.facts import (
    InstantFact,
    RevenueFacts,
    extract_instant_facts,
    extract_named_duration_facts,
    filing_url,
)
from .ttm import TTMResult

NULL = None


def compute_flow_ttm(slots: list[Slot]) -> TTMResult:
    """Current and prior four-quarter sums. Negative TTM is allowed. Missing is never zero."""
    if len(slots) < 4 or any(isinstance(s, MissingQuarter) for s in slots[:4]):
        gapped = any(isinstance(s, MissingQuarter) for s in slots[:4])
        reason = "gap_in_quarters" if gapped else "insufficient_quarters"
        return TTMResult(None, None, None, reason)
    current = sum(s.val for s in slots[:4] if isinstance(s, Quarter))
    if len(slots) < 8 or any(isinstance(s, MissingQuarter) for s in slots[4:8]):
        gapped = any(isinstance(s, MissingQuarter) for s in slots[4:8])
        reason = "gap_in_quarters" if gapped else "insufficient_quarters"
        return TTMResult(current, None, None, reason)
    previous = sum(s.val for s in slots[4:8] if isinstance(s, Quarter))
    return TTMResult(current, previous, None, None)


def _pick_flow_concept(rf: RevenueFacts, candidates: list[str]) -> str | None:
    for concept in candidates:
        if rf.by_concept.get(concept):
            return concept
    return None


def _slots_for_concept(rf: RevenueFacts, concept: str) -> list[Slot]:
    facts = rf.by_concept.get(concept) or []
    if not facts:
        return []
    periods = dedupe_periods(facts)
    quarters = derive_quarters(periods, concept)
    label_quarters(quarters, rf.filings)
    return build_timeline(quarters)


def _quarter_payloads(slots: list[Slot], *, magnitude: bool = False, cik: str = "") -> list[dict]:
    out: list[dict] = []
    for s in slots[:8]:
        if isinstance(s, MissingQuarter):
            out.append(
                {
                    "fiscalYear": s.fiscal_year,
                    "fiscalQuarter": s.fiscal_quarter,
                    "start": s.start.isoformat(),
                    "end": s.end.isoformat(),
                    "value": None,
                    "reason": "missing_quarter",
                    "method": None,
                    "formula": None,
                }
            )
            continue
        val = abs(s.val) if magnitude else s.val
        accn = s.sources[0].accn if s.sources else None
        url = filing_url(cik, accn) if cik and accn else None
        out.append(
            {
                "fiscalYear": s.fiscal_year,
                "fiscalQuarter": s.fiscal_quarter,
                "start": s.start.isoformat(),
                "end": s.end.isoformat(),
                "value": val,
                "rawValue": s.val,
                "method": s.method,
                "formula": s.formula,
                "concept": s.concept,
                "restated": s.restated,
                "accn": accn,
                "form": s.sources[0].form if s.sources else None,
                "filed": s.sources[0].filed.isoformat() if s.sources else None,
                "url": url,
                "sources": [
                    {
                        "role": src.role,
                        "sign": src.sign,
                        "accn": src.accn,
                        "form": src.form,
                        "filed": src.filed.isoformat(),
                        "start": src.start.isoformat(),
                        "end": src.end.isoformat(),
                        "value": src.val,
                    }
                    for src in s.sources
                ],
            }
        )
    return out


def _flow_metric(rf: RevenueFacts, candidates: list[str], *, capex: bool = False, cik: str = "") -> dict:
    concept = _pick_flow_concept(rf, candidates)
    if concept is None:
        return {
            "status": "missing",
            "reason": "no_concept",
            "concept": None,
            "ttm": None,
            "previousTtm": None,
            "quarters": [],
            "verification": "not_checked",
        }
    slots = _slots_for_concept(rf, concept)
    if capex:
        mag_slots: list[Slot] = []
        for s in slots:
            if isinstance(s, Quarter):
                mag_slots.append(
                    Quarter(
                        s.start,
                        s.end,
                        abs(s.val),
                        s.method,
                        s.formula,
                        s.sources,
                        s.concept,
                        restated=s.restated,
                        fiscal_year=s.fiscal_year,
                        fiscal_quarter=s.fiscal_quarter,
                        label_inferred=s.label_inferred,
                        flags=list(s.flags),
                    )
                )
            else:
                mag_slots.append(s)
        ttm = compute_flow_ttm(mag_slots)
        quarters = _quarter_payloads(slots, magnitude=True, cik=cik)
        return {
            "status": "extracted" if ttm.current is not None else "missing",
            "reason": ttm.reason,
            "concept": concept,
            "unit": rf.currency,
            "signPolicy": "positive_cash_outflow_magnitude",
            "ttm": ttm.current,
            "previousTtm": ttm.previous,
            "quarters": quarters,
            "verification": "company_facts_only",
            "verificationNote": "Cash-flow face statements are not in the current income-statement cache.",
        }
    ttm = compute_flow_ttm(slots)
    quarters = _quarter_payloads(slots, cik=cik)
    return {
        "status": "extracted" if ttm.current is not None else "missing",
        "reason": ttm.reason,
        "concept": concept,
        "unit": rf.currency,
        "ttm": ttm.current,
        "previousTtm": ttm.previous,
        "quarters": quarters,
        "verification": "company_facts_only",
        "verificationNote": "Cash-flow / income-statement face check for this metric is not cached in Phase 2.",
    }


def _latest_instant(facts: list[InstantFact], as_of: date | None) -> InstantFact | None:
    usable = [f for f in facts if as_of is None or f.end <= as_of]
    if not usable:
        return None
    usable.sort(key=lambda f: (f.end, f.filed, f.accn))
    return usable[-1]


def _stock_from_concept(
    instants: dict[str, list[InstantFact]],
    concept: str,
    as_of: date | None,
    cik: str,
    currency: str | None,
) -> dict | None:
    latest = _latest_instant(instants.get(concept) or [], as_of)
    if latest is None:
        return None
    return {
        "status": "extracted",
        "reason": None,
        "concept": concept,
        "value": latest.val,
        "end": latest.end.isoformat(),
        "accn": latest.accn,
        "form": latest.form,
        "filed": latest.filed.isoformat(),
        "url": filing_url(cik, latest.accn),
        "unit": currency,
        "aggregation": "latest_quarter_end",
        "verification": "company_facts_only",
    }


def _missing_stock(reason: str) -> dict:
    return {
        "status": "missing",
        "reason": reason,
        "concept": None,
        "value": None,
        "end": None,
        "verification": "not_checked",
    }


def _stock_metrics(instants: dict[str, list[InstantFact]], as_of: date | None, cik: str, currency: str | None) -> dict:
    cash = None
    for concept in CASH_CONCEPTS:
        cash = _stock_from_concept(instants, concept, as_of, cik, currency)
        if cash:
            break
    if cash is None:
        cash = _missing_stock("no_concept")

    st = None
    st_parts_used: list[str] = []
    for concept in ST_DEBT_TOTAL_CONCEPTS:
        st = _stock_from_concept(instants, concept, as_of, cik, currency)
        if st:
            st["aggregation"] = "single_current_debt_total"
            break
    if st is None:
        parts = []
        for concept in ST_DEBT_PART_CONCEPTS:
            part = _stock_from_concept(instants, concept, as_of, cik, currency)
            if part:
                parts.append(part)
                st_parts_used.append(concept)
        if parts:
            ends = {p["end"] for p in parts}
            if len(ends) > 1:
                st = {
                    "status": "missing",
                    "reason": "debt_period_mismatch",
                    "concept": None,
                    "value": None,
                    "components": parts,
                    "verification": "not_checked",
                }
            else:
                st = {
                    "status": "extracted",
                    "reason": None,
                    "concept": "+".join(st_parts_used),
                    "value": sum(p["value"] for p in parts),
                    "end": parts[0]["end"],
                    "components": parts,
                    "aggregation": "sum_disjoint_current_components",
                    "unit": currency,
                    "verification": "company_facts_only",
                    "url": parts[0].get("url"),
                }
        else:
            st = _missing_stock("no_concept")

    lt = None
    for concept in LT_DEBT_CONCEPTS:
        lt = _stock_from_concept(instants, concept, as_of, cik, currency)
        if lt:
            lt["aggregation"] = "single_long_term_debt_concept"
            break
    if lt is None:
        lt = _missing_stock("no_concept")

    total_debt = None
    total_reason = None
    if st["value"] is None and lt["value"] is None:
        total_reason = "no_concept"
    elif st["value"] is None:
        total_reason = "missing_short_term_debt"
    elif lt["value"] is None:
        total_reason = "missing_long_term_debt"
    else:
        total_debt = st["value"] + lt["value"]

    net_debt = None
    net_reason = None
    if total_debt is None:
        net_reason = total_reason
    elif cash["value"] is None:
        net_reason = "missing_cash"
    else:
        net_debt = total_debt - cash["value"]

    return {
        "cash": cash,
        "shortTermDebt": st,
        "longTermDebt": lt,
        "totalDebt": {
            "status": "extracted" if total_debt is not None else "missing",
            "reason": total_reason,
            "value": total_debt,
            "formula": "short_term_debt + long_term_debt",
            "end": st.get("end") or lt.get("end"),
            "verification": "derived" if total_debt is not None else "not_checked",
        },
        "netDebt": {
            "status": "extracted" if net_debt is not None else "missing",
            "reason": net_reason,
            "value": net_debt,
            "formula": "total_debt − cash",
            "end": cash.get("end") or st.get("end"),
            "verification": "derived" if net_debt is not None else "not_checked",
        },
    }


@dataclass
class Layer3Analysis:
    cik: str
    status: str
    currency: str | None
    metrics: dict
    flags: list[str] = field(default_factory=list)
    extraction_version: int = LAYER3_EXTRACTION_VERSION

    def to_dict(self) -> dict:
        return {
            "cik": self.cik,
            "status": self.status,
            "currency": self.currency,
            "extractionVersion": self.extraction_version,
            "flags": self.flags,
            "metrics": self.metrics,
        }


def analyze_layer3_facts(
    companyfacts: dict,
    *,
    sic_code: str | None = None,
    foreign: bool | None = None,
) -> Layer3Analysis:
    """Analyze one issuer's Company Facts payload. Does not score."""
    flows = extract_named_duration_facts(companyfacts, FLOW_CONCEPTS)
    instants = extract_instant_facts(companyfacts, STOCK_CONCEPTS)
    cik = flows.cik or str(companyfacts.get("cik", "")).zfill(10)
    flags: list[str] = []
    if foreign or flows.is_foreign_filer:
        flags.append("foreign_filer")
    if is_financial_sic(sic_code):
        flags.append("financial_institution")

    ocf = _flow_metric(flows, OCF_CONCEPTS, cik=cik)
    capex = _flow_metric(flows, CAPEX_CONCEPTS, capex=True, cik=cik)
    opinc = _flow_metric(flows, OPERATING_INCOME_CONCEPTS, cik=cik)
    interest = _flow_metric(flows, INTEREST_CONCEPTS, cik=cik)
    da = _flow_metric(flows, DA_CONCEPTS, cik=cik)

    fcf_ttm = fcf_prior = None
    fcf_reason = None
    if ocf.get("ttm") is None:
        fcf_reason = "missing_ocf"
    elif capex.get("ttm") is None:
        fcf_reason = "missing_capex"
    else:
        fcf_ttm = ocf["ttm"] - capex["ttm"]
        if ocf.get("previousTtm") is not None and capex.get("previousTtm") is not None:
            fcf_prior = ocf["previousTtm"] - capex["previousTtm"]
        else:
            fcf_reason = ocf.get("reason") or capex.get("reason") or "insufficient_quarters"

    ebitda = None
    ebitda_reason = None
    if opinc.get("ttm") is None:
        ebitda_reason = "missing_operating_income"
    elif da.get("ttm") is None:
        ebitda_reason = "missing_depreciation_amortization"
    else:
        ebitda = opinc["ttm"] + da["ttm"]

    as_of = None
    for q in ocf.get("quarters") or []:
        if q.get("end") and q.get("value") is not None:
            as_of = date.fromisoformat(q["end"])
            break
    stocks = _stock_metrics(instants, as_of, cik, flows.currency)

    no_interest_burden = (
        interest.get("ttm") == 0
        and stocks["totalDebt"]["value"] == 0
        and interest.get("status") == "extracted"
        and stocks["totalDebt"]["status"] == "extracted"
    )

    metrics = {
        "ocf": ocf,
        "capex": capex,
        "fcf": {
            "status": "extracted" if fcf_ttm is not None else "missing",
            "reason": None if fcf_ttm is not None else fcf_reason,
            "ttm": fcf_ttm,
            "previousTtm": fcf_prior,
            "formula": "OCF − CapEx (CapEx as positive cash outflow)",
            "verification": "derived" if fcf_ttm is not None else "not_checked",
        },
        "operatingIncome": opinc,
        "interestExpense": interest,
        "depreciationAmortization": da,
        "ebitda": {
            "status": "extracted" if ebitda is not None else "missing",
            "reason": None if ebitda is not None else ebitda_reason,
            "ttm": ebitda,
            "formula": "operating_income + depreciation_and_amortization",
            "definition": "Operating income used as an EBIT proxy only when that concept is selected.",
            "verification": "derived" if ebitda is not None else "not_checked",
        },
        **stocks,
        "noInterestBurden": no_interest_burden,
        "growthSource": "not_yet_verified",
    }

    extracted_any = any(
        metrics[k].get("status") == "extracted" or metrics[k].get("ttm") is not None
        for k in ("ocf", "capex", "operatingIncome", "cash")
    )
    if "financial_institution" in flags:
        status = "model_not_applicable"
    elif "foreign_filer" in flags and not extracted_any:
        status = "insufficient_verified_data"
        flags.append("no_fabricated_foreign_quarters")
    elif extracted_any and (ocf.get("ttm") is None or capex.get("ttm") is None or stocks["cash"]["value"] is None):
        status = "pending_data_verification"
    elif extracted_any:
        status = "extracted"
    else:
        status = "pending_data_verification"

    return Layer3Analysis(cik=cik, status=status, currency=flows.currency, metrics=metrics, flags=flags)
