"""Extract and derive Layer 3 financial metrics from SEC Company Facts.

Reuses quarter derivation (including YTD → standalone Q and Q4 = FY − 9M) and TTM windowing.
Missing or unverified values stay null with a reason. Never mapped to zero.
Does not compute the 100-point score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .layer3_concepts import (
    AMORTIZATION_ADDON_CONCEPTS,
    AP_CONCEPTS,
    AR_CONCEPTS,
    CAPEX_CONCEPTS,
    CAPEX_MAY_BE_NET,
    CASH_CONCEPTS,
    COST_OF_REVENUE_CONCEPTS,
    CURRENT_ASSET_CONCEPTS,
    CURRENT_LIABILITY_CONCEPTS,
    DA_CONCEPTS,
    DEPRECIATION_ONLY_CONCEPTS,
    FLOW_ALIGN_DAYS,
    FLOW_CONCEPTS,
    GROSS_PROFIT_CONCEPTS,
    HISTORY_SLOTS,
    INTEREST_CONCEPTS,
    INVENTORY_CONCEPTS,
    INVENTORY_NARROW_SCOPE,
    LAYER3_EXTRACTION_VERSION,
    LAYER3_SCHEMA_VERSION,
    LT_DEBT_CONCEPTS,
    LT_DEBT_INCLUDES_LEASES,
    OCF_CONCEPTS,
    OPERATING_INCOME_CONCEPTS,
    ST_DEBT_PART_CONCEPTS,
    ST_DEBT_TOTAL_CONCEPTS,
    STOCK_ALIGN_DAYS,
    STOCK_CONCEPTS,
    TOTAL_DEBT_FALLBACK_CONCEPTS,
    TOTAL_DEBT_INCLUDES_LEASES,
    gaap_concepts_present,
    is_financial_sic,
)
from .layer3_derived import (
    add_flows,
    apply_ttm_yoy,
    average_balance,
    cash_conversion_cycle,
    cash_conversion_metric,
    current_ratio_metric,
    days_outstanding,
    identity_holds,
    margin_metric,
    operating_working_capital,
    stock_yoy,
    subtract_flows,
    ttm_window,
)
from .quarters import MissingQuarter, Quarter, Slot, build_timeline, dedupe_periods, derive_quarters, label_quarters
from .sec.facts import (
    EARNINGS_CONCEPTS,
    REVENUE_CONCEPTS,
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


def _newest_quarter_end(slots: list[Slot]) -> date | None:
    for s in slots:
        if isinstance(s, Quarter):
            return s.end
    return None


def _aligned(end: date | None, as_of: date | None, days: int) -> bool:
    if end is None or as_of is None:
        return as_of is None
    return abs((end - as_of).days) <= days


def _pick_flow_concept(rf: RevenueFacts, candidates: list[str], as_of: date | None = None) -> str | None:
    """Prefer a concept whose newest standalone quarter sits on the OCF window."""
    best: tuple[tuple, str] | None = None
    for idx, concept in enumerate(candidates):
        if not rf.by_concept.get(concept):
            continue
        newest = _newest_quarter_end(_slots_for_concept(rf, concept))
        aligned = _aligned(newest, as_of, FLOW_ALIGN_DAYS) if as_of else True
        score = (aligned, newest or date.min, -idx)
        if best is None or score > best[0]:
            best = (score, concept)
    return best[1] if best else None


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
    for s in slots[:HISTORY_SLOTS]:
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


COMPANY_FACTS_ONLY_NOTE = (
    "Taken from SEC Company Facts XBRL. Not checked against the rendered 10-Q/10-K "
    "cash-flow or balance-sheet statement."
)


def _flow_metric(
    rf: RevenueFacts,
    candidates: list[str],
    *,
    capex: bool = False,
    cik: str = "",
    as_of: date | None = None,
    require_align: bool = False,
) -> dict:
    concept = _pick_flow_concept(rf, candidates, as_of if require_align else None)
    if concept is None:
        return apply_ttm_yoy({
            "status": "missing",
            "reason": "no_concept",
            "concept": None,
            "ttm": None,
            "previousTtm": None,
            "quarters": [],
            "calculationMethod": "extracted",
            "verification": "not_checked",
        })
    slots = _slots_for_concept(rf, concept)
    newest = _newest_quarter_end(slots)
    if require_align and as_of is not None and not _aligned(newest, as_of, FLOW_ALIGN_DAYS):
        return apply_ttm_yoy({
            "status": "missing",
            "reason": "ttm_window_not_aligned",
            "concept": concept,
            "ttm": None,
            "previousTtm": None,
            "quarters": _quarter_payloads(slots, cik=cik),
            "calculationMethod": "extracted",
            "verification": "not_checked",
            "verificationNote": COMPANY_FACTS_ONLY_NOTE,
            "newestEnd": newest.isoformat() if newest else None,
            "alignedTo": as_of.isoformat(),
        })
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
        payload = apply_ttm_yoy({
            "status": "extracted" if ttm.current is not None else "missing",
            "reason": ttm.reason,
            "concept": concept,
            "unit": rf.currency,
            "signPolicy": "positive_cash_outflow_magnitude",
            "ttm": ttm.current,
            "previousTtm": ttm.previous,
            "quarters": quarters,
            "calculationMethod": "extracted",
            "verification": "company_facts_only",
            "verificationNote": COMPANY_FACTS_ONLY_NOTE,
        })
        if concept in CAPEX_MAY_BE_NET:
            payload["scopeNote"] = (
                "Last-resort tag; US-GAAP name is net of asset-sale proceeds. "
                "Used only when no gross PPE CapEx tag is aligned."
            )
        return payload
    ttm = compute_flow_ttm(slots)
    quarters = _quarter_payloads(slots, cik=cik)
    return apply_ttm_yoy({
        "status": "extracted" if ttm.current is not None else "missing",
        "reason": ttm.reason,
        "concept": concept,
        "unit": rf.currency,
        "ttm": ttm.current,
        "previousTtm": ttm.previous,
        "quarters": quarters,
        "calculationMethod": "extracted",
        "verification": "company_facts_only",
        "verificationNote": COMPANY_FACTS_ONLY_NOTE,
    })


def _latest_instant(facts: list[InstantFact], as_of: date | None) -> InstantFact | None:
    """Latest instant on the analysis date. Stale prior-year balances are not used."""
    usable = [f for f in facts if as_of is None or _aligned(f.end, as_of, STOCK_ALIGN_DAYS)]
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
        "calculationMethod": "extracted",
        "verification": "company_facts_only",
        "verificationNote": COMPANY_FACTS_ONLY_NOTE,
    }


def _missing_stock(reason: str) -> dict:
    return {
        "status": "missing",
        "reason": reason,
        "concept": None,
        "value": None,
        "end": None,
        "calculationMethod": "extracted",
        "verification": "not_checked",
        "history": [],
    }


def _not_applicable_stock(reason: str) -> dict:
    return {
        "status": "not_applicable",
        "reason": reason,
        "concept": None,
        "value": None,
        "end": None,
        "calculationMethod": "extracted",
        "verification": "not_checked",
        "history": [],
    }


def _has_any(instants: dict[str, list[InstantFact]], concepts: list[str]) -> bool:
    return any(instants.get(c) for c in concepts)


def _first_aligned_stock(
    instants: dict[str, list[InstantFact]],
    concepts: list[str],
    as_of: date | None,
    cik: str,
    currency: str | None,
) -> dict:
    for concept in concepts:
        found = _stock_from_concept(instants, concept, as_of, cik, currency)
        if found:
            return found
    return _missing_stock("stock_not_as_of_latest_quarter" if _has_any(instants, concepts) else "no_concept")


def _stock_metrics(instants: dict[str, list[InstantFact]], as_of: date | None, cik: str, currency: str | None) -> dict:
    cash = _first_aligned_stock(instants, CASH_CONCEPTS, as_of, cik, currency)
    if cash["status"] == "extracted":
        cash["aggregation"] = "latest_quarter_end"

    st = _first_aligned_stock(instants, ST_DEBT_TOTAL_CONCEPTS, as_of, cik, currency)
    if st["status"] == "extracted":
        st["aggregation"] = "single_current_debt_total"
    else:
        parts = []
        st_parts_used: list[str] = []
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
                    "calculationMethod": "extracted",
                    "verification": "company_facts_only",
                    "verificationNote": COMPANY_FACTS_ONLY_NOTE,
                    "url": parts[0].get("url"),
                }
        elif st["reason"] != "stock_not_as_of_latest_quarter":
            reason = "stock_not_as_of_latest_quarter" if _has_any(instants, ST_DEBT_PART_CONCEPTS) else "no_concept"
            st = _missing_stock(reason)

    lt = _first_aligned_stock(instants, LT_DEBT_CONCEPTS, as_of, cik, currency)
    if lt["status"] == "extracted":
        lt["aggregation"] = "single_long_term_debt_concept"
        if lt.get("concept") in LT_DEBT_INCLUDES_LEASES:
            lt["includesLeaseObligations"] = True
            lt["scopeNote"] = "This tag includes capital / finance lease obligations with borrowings."

    total_debt = None
    total_reason = None
    total_formula = "short_term_debt + long_term_debt"
    total_concept = None
    total_end = st.get("end") or lt.get("end")
    if st["value"] is not None and lt["value"] is not None:
        if st.get("end") != lt.get("end"):
            total_reason = "debt_period_mismatch"
        else:
            total_debt = st["value"] + lt["value"]
    else:
        fallback = _first_aligned_stock(instants, TOTAL_DEBT_FALLBACK_CONCEPTS, as_of, cik, currency)
        known_part = st["value"] if st["value"] is not None else lt["value"]
        fallback_is_total = (
            fallback["status"] == "extracted"
            and (known_part is None or fallback["value"] + 1 >= known_part)
        )
        if fallback_is_total:
            # Fallback tags are totals. Never add them on top of the current portion.
            total_debt = fallback["value"]
            total_concept = fallback["concept"]
            total_end = fallback.get("end")
            total_formula = "single_total_debt_concept"
            if total_concept in TOTAL_DEBT_INCLUDES_LEASES:
                fallback["includesLeaseObligations"] = True
        elif st["value"] is None and lt["value"] is None:
            total_reason = fallback["reason"]
        elif st["value"] is None:
            total_reason = "missing_short_term_debt"
        else:
            total_reason = "missing_long_term_debt"

    net_debt = None
    net_reason = None
    if total_debt is None:
        net_reason = total_reason
    elif cash["value"] is None:
        net_reason = "missing_cash"
    else:
        net_debt = total_debt - cash["value"]

    total_payload = {
        "status": "extracted" if total_debt is not None else "missing",
        "reason": total_reason,
        "value": total_debt,
        "formula": total_formula,
        "concept": total_concept,
        "end": total_end,
        "calculationMethod": "derived" if total_debt is not None else "extracted",
        "verification": "derived" if total_debt is not None else "not_checked",
    }
    if total_concept in TOTAL_DEBT_INCLUDES_LEASES:
        total_payload["includesLeaseObligations"] = True

    return {
        "cash": cash,
        "shortTermDebt": st,
        "longTermDebt": lt,
        "totalDebt": total_payload,
        "netDebt": {
            "status": "extracted" if net_debt is not None else "missing",
            "reason": net_reason,
            "value": net_debt,
            "formula": "total_debt − cash",
            "end": cash.get("end") or total_end,
            "calculationMethod": "derived" if net_debt is not None else "extracted",
            "verification": "derived" if net_debt is not None else "not_checked",
        },
    }


def _fiscal_spine(flow: dict) -> list[dict]:
    """Eight fiscal slots from a duration metric. Missing values still keep the period."""
    out = []
    for q in (flow.get("quarters") or [])[:HISTORY_SLOTS]:
        if q.get("end"):
            out.append({
                "fiscalYear": q.get("fiscalYear"),
                "fiscalQuarter": q.get("fiscalQuarter"),
                "start": q.get("start"),
                "end": q.get("end"),
            })
    return out


def _history_row(slot: dict, found: dict) -> dict:
    return {
        "fiscalYear": slot.get("fiscalYear"),
        "fiscalQuarter": slot.get("fiscalQuarter"),
        "end": found.get("end") or slot.get("end"),
        "value": found.get("value"),
        "status": found.get("status"),
        "reason": found.get("reason"),
        "concept": found.get("concept"),
        "accn": found.get("accn"),
        "form": found.get("form"),
        "filed": found.get("filed"),
        "url": found.get("url"),
        "calculationMethod": found.get("calculationMethod"),
        "verification": found.get("verification"),
    }


def _simple_stock_with_history(
    instants: dict[str, list[InstantFact]],
    concepts: list[str],
    spine: list[dict],
    as_of: date | None,
    cik: str,
    currency: str | None,
    *,
    present: bool = True,
    na_reason: str = "not_applicable",
    scope_note_for: set[str] | None = None,
) -> dict:
    if not present:
        payload = _not_applicable_stock(na_reason)
        payload["history"] = [
            {**slot, "value": None, "status": "not_applicable", "reason": na_reason, "verification": "not_checked"}
            for slot in spine
        ]
        return payload
    latest = _first_aligned_stock(instants, concepts, as_of, cik, currency)
    if latest.get("concept") and scope_note_for and latest["concept"] in scope_note_for:
        latest["scopeNote"] = "Narrower inventory tag; not a total inventory line."
    latest["history"] = [
        _history_row(
            slot,
            _first_aligned_stock(
                instants, concepts, date.fromisoformat(slot["end"]), cik, currency
            ),
        )
        for slot in spine
    ]
    return latest


def _debt_history(
    instants: dict[str, list[InstantFact]],
    spine: list[dict],
    cik: str,
    currency: str | None,
) -> dict[str, list]:
    hist: dict[str, list] = {k: [] for k in ("cash", "shortTermDebt", "longTermDebt", "totalDebt", "netDebt")}
    for slot in spine:
        as_of = date.fromisoformat(slot["end"])
        snap = _stock_metrics(instants, as_of, cik, currency)
        for key in hist:
            hist[key].append(_history_row(slot, snap[key]))
    return hist


def _candidate_flows(rf: RevenueFacts, concepts: list[str], cik: str, as_of: date | None) -> list[dict]:
    out = []
    for concept in concepts:
        if not rf.by_concept.get(concept):
            continue
        metric = _flow_metric(rf, [concept], cik=cik, as_of=as_of, require_align=bool(as_of))
        if metric.get("status") == "extracted" or any(q.get("value") is not None for q in metric.get("quarters") or []):
            out.append(metric)
    return out


def _select_gross_and_cogs(
    rf: RevenueFacts,
    revenue: dict,
    cik: str,
    as_of: date | None,
) -> tuple[dict, dict]:
    """Pick GP and COGS that share revenue's scope. Never take the first non-empty tag."""
    gps = _candidate_flows(rf, GROSS_PROFIT_CONCEPTS, cik, as_of)
    costs = _candidate_flows(rf, COST_OF_REVENUE_CONCEPTS, cik, as_of)
    rev_ttm = revenue.get("ttm")

    for gp in gps:
        for cogs in costs:
            if identity_holds(gp.get("ttm"), cogs.get("ttm"), rev_ttm):
                gp = {**gp, "identity": "gross_plus_cogs_equals_revenue"}
                cogs = {**cogs, "identity": "gross_plus_cogs_equals_revenue"}
                return apply_ttm_yoy(gp), apply_ttm_yoy(cogs)

    if rev_ttm is not None:
        for gp in gps:
            if gp.get("ttm") is None:
                continue
            implied = subtract_flows(
                revenue, gp, "Revenue − Gross Profit",
                missing_left="missing_revenue", missing_right="missing_gross_profit",
            )
            implied["concept"] = None
            for cogs in costs:
                if identity_holds(gp.get("ttm"), cogs.get("ttm"), rev_ttm):
                    return apply_ttm_yoy(gp), apply_ttm_yoy(cogs)
            return apply_ttm_yoy(gp), implied
        for cogs in costs:
            if cogs.get("ttm") is None:
                continue
            implied = subtract_flows(
                revenue, cogs, "Revenue − Cost of Revenue",
                missing_left="missing_revenue", missing_right="missing_cost_of_revenue",
            )
            implied["concept"] = None
            return implied, apply_ttm_yoy(cogs)

    empty = apply_ttm_yoy({
        "status": "missing",
        "reason": "no_concept",
        "concept": None,
        "ttm": None,
        "previousTtm": None,
        "quarters": [],
        "calculationMethod": "extracted",
        "verification": "not_checked",
    })
    gp = gps[0] if gps else empty
    cogs = costs[0] if costs else empty
    if (
        gp.get("ttm") is not None
        and cogs.get("ttm") is not None
        and rev_ttm is not None
        and not identity_holds(gp.get("ttm"), cogs.get("ttm"), rev_ttm)
    ):
        cogs = apply_ttm_yoy({
            **cogs,
            "status": "missing",
            "reason": "concept_scope_mismatch",
            "ttm": None,
            "previousTtm": None,
            "ttmYoy": None,
        })
    return apply_ttm_yoy(gp), apply_ttm_yoy(cogs)


@dataclass
class Layer3Analysis:
    cik: str
    extraction_status: str
    verification_status: str
    model_applicability: str
    scoring_status: str
    input_completeness: str
    currency: str | None
    metrics: dict
    flags: list[str] = field(default_factory=list)
    extraction_version: int = LAYER3_EXTRACTION_VERSION
    schema_version: int = LAYER3_SCHEMA_VERSION
    data_as_of: str | None = None

    def to_dict(self) -> dict:
        return {
            "cik": self.cik,
            "schemaVersion": self.schema_version,
            "extractionVersion": self.extraction_version,
            "dataAsOf": self.data_as_of,
            "extractionStatus": self.extraction_status,
            "verificationStatus": self.verification_status,
            "modelApplicability": self.model_applicability,
            "scoringStatus": self.scoring_status,
            "inputCompleteness": self.input_completeness,
            "currency": self.currency,
            "flags": self.flags,
            "metrics": self.metrics,
            "scoring": None,
        }


def analyze_layer3_facts(
    companyfacts: dict,
    *,
    sic_code: str | None = None,
    foreign: bool | None = None,
    preferred_revenue_concept: str | None = None,
    preferred_earnings_concept: str | None = None,
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
    as_of = None
    for q in ocf.get("quarters") or []:
        if q.get("end") and q.get("value") is not None:
            as_of = date.fromisoformat(q["end"])
            break
    align = bool(as_of)
    capex = _flow_metric(flows, CAPEX_CONCEPTS, capex=True, cik=cik, as_of=as_of, require_align=align)
    opinc = _flow_metric(flows, OPERATING_INCOME_CONCEPTS, cik=cik, as_of=as_of, require_align=align)
    interest = _flow_metric(flows, INTEREST_CONCEPTS, cik=cik, as_of=as_of, require_align=align)
    da = _flow_metric(flows, DA_CONCEPTS, cik=cik, as_of=as_of, require_align=align)
    da_incomplete = False
    if da.get("concept") in DEPRECIATION_ONLY_CONCEPTS:
        amort = _flow_metric(flows, AMORTIZATION_ADDON_CONCEPTS, cik=cik, as_of=as_of, require_align=align)
        if amort.get("ttm") is not None and da.get("ttm") is not None:
            prior = None
            if da.get("previousTtm") is not None and amort.get("previousTtm") is not None:
                prior = da["previousTtm"] + amort["previousTtm"]
            da = apply_ttm_yoy({
                **da,
                "ttm": da["ttm"] + amort["ttm"],
                "previousTtm": prior,
                "concept": f"{da['concept']}+{amort['concept']}",
                "aggregation": "sum_depreciation_and_amortization",
                "reason": None if prior is not None else da.get("reason") or amort.get("reason"),
            })
        elif amort.get("reason") != "no_concept":
            # Amortization exists but is unaligned or gapped. Do not treat it as zero.
            da_incomplete = True

    rev_concepts = list(REVENUE_CONCEPTS)
    if preferred_revenue_concept:
        rev_concepts = [preferred_revenue_concept] + [c for c in rev_concepts if c != preferred_revenue_concept]
    earn_concepts = list(EARNINGS_CONCEPTS)
    if preferred_earnings_concept:
        earn_concepts = [preferred_earnings_concept] + [c for c in earn_concepts if c != preferred_earnings_concept]
    revenue = _flow_metric(flows, rev_concepts, cik=cik, as_of=as_of, require_align=align)
    net_income = _flow_metric(flows, earn_concepts, cik=cik, as_of=as_of, require_align=align)
    gross_profit, cost_of_revenue = _select_gross_and_cogs(flows, revenue, cik, as_of)

    fcf = subtract_flows(
        ocf, capex, "OCF − CapEx (CapEx as positive cash outflow)",
        missing_left="missing_ocf", missing_right="missing_capex",
    )
    if da_incomplete:
        ebitda = {
            "status": "missing",
            "reason": "depreciation_excludes_amortization",
            "ttm": None,
            "previousTtm": None,
            "quarters": [],
            "formula": "operating_income + depreciation_and_amortization",
            "definition": "Operating income used as an EBIT proxy only when that concept is selected.",
            "calculationMethod": "derived",
            "verification": "not_checked",
            "verificationNote": "Derived from Company Facts operating income and D&A. Not statement-checked.",
        }
    else:
        ebitda = add_flows(
            opinc, da, "operating_income + depreciation_and_amortization",
            missing_left="missing_operating_income",
            missing_right="missing_depreciation_amortization",
        )
        ebitda["definition"] = "Operating income used as an EBIT proxy only when that concept is selected."
    # Keep the previous verification token so existing UI copy still reads "Derived".
    if fcf.get("ttm") is not None:
        fcf["verification"] = "derived"
    if ebitda.get("ttm") is not None:
        ebitda["verification"] = "derived"

    stocks = _stock_metrics(instants, as_of, cik, flows.currency)
    spine = _fiscal_spine(ocf) or _fiscal_spine(revenue)
    debt_hist = _debt_history(instants, spine, cik, flows.currency) if spine else {}
    for key, rows in debt_hist.items():
        stocks[key]["history"] = rows

    inv_present = bool(gaap_concepts_present(companyfacts, INVENTORY_CONCEPTS))
    ar = _simple_stock_with_history(instants, AR_CONCEPTS, spine, as_of, cik, flows.currency)
    inventory = _simple_stock_with_history(
        instants, INVENTORY_CONCEPTS, spine, as_of, cik, flows.currency,
        present=inv_present, na_reason="no_inventory_concept",
        scope_note_for=INVENTORY_NARROW_SCOPE,
    )
    ap = _simple_stock_with_history(instants, AP_CONCEPTS, spine, as_of, cik, flows.currency)
    current_assets = _simple_stock_with_history(
        instants, CURRENT_ASSET_CONCEPTS, spine, as_of, cik, flows.currency
    )
    current_liabilities = _simple_stock_with_history(
        instants, CURRENT_LIABILITY_CONCEPTS, spine, as_of, cik, flows.currency
    )

    _ttm_start, ttm_end, ttm_days = ttm_window(revenue if revenue.get("ttm") is not None else ocf)
    begin_end = None
    if spine and len(spine) >= 5:
        begin_end = spine[4].get("end")
    close_end = spine[0].get("end") if spine else (ttm_end.isoformat() if ttm_end else None)
    avg_ar, ar_reason, ar_inputs = average_balance(ar.get("history"), begin_end, close_end)
    avg_inv, inv_reason, inv_inputs = average_balance(inventory.get("history"), begin_end, close_end)
    avg_ap, ap_reason, ap_inputs = average_balance(ap.get("history"), begin_end, close_end)
    dso = days_outstanding(
        average=avg_ar, flow_ttm=revenue.get("ttm"), days=ttm_days,
        formula="Average AR / TTM Revenue × days_in_window",
        avg_reason=ar_reason, flow_reason="missing_revenue",
    )
    dso["inputs"] = ar_inputs
    if inventory.get("status") == "not_applicable":
        dio = {
            "status": "not_applicable",
            "reason": "no_inventory_concept",
            "value": None,
            "formula": "Average Inventory / TTM Cost of Revenue × days_in_window",
            "calculationMethod": "derived",
            "verification": "not_checked",
        }
    else:
        dio = days_outstanding(
            average=avg_inv, flow_ttm=cost_of_revenue.get("ttm"), days=ttm_days,
            formula="Average Inventory / TTM Cost of Revenue × days_in_window",
            avg_reason=inv_reason, flow_reason="missing_cost_of_revenue",
        )
        dio["inputs"] = inv_inputs
    dpo = days_outstanding(
        average=avg_ap, flow_ttm=cost_of_revenue.get("ttm"), days=ttm_days,
        formula="Average AP / TTM Cost of Revenue × days_in_window",
        avg_reason=ap_reason, flow_reason="missing_cost_of_revenue",
    )
    dpo["inputs"] = ap_inputs

    no_interest_burden = (
        interest.get("ttm") == 0
        and stocks["totalDebt"]["value"] == 0
        and interest.get("status") == "extracted"
        and stocks["totalDebt"]["status"] == "extracted"
    )

    metrics = {
        "revenue": revenue,
        "netIncome": net_income,
        "grossProfit": gross_profit,
        "costOfRevenue": cost_of_revenue,
        "operatingIncome": opinc,
        "ocf": ocf,
        "capex": capex,
        "interestExpense": interest,
        "depreciationAmortization": da,
        "fcf": fcf,
        "ebitda": ebitda,
        "grossMargin": margin_metric(gross_profit, revenue, "Gross Profit / Revenue"),
        "operatingMargin": margin_metric(opinc, revenue, "Operating Income / Revenue"),
        "netMargin": margin_metric(net_income, revenue, "Net Income / Revenue"),
        "fcfMargin": margin_metric(fcf, revenue, "FCF / Revenue"),
        "cashConversion": cash_conversion_metric(ocf, net_income),
        **stocks,
        "accountsReceivable": ar,
        "inventory": inventory,
        "accountsPayable": ap,
        "currentAssets": current_assets,
        "currentLiabilities": current_liabilities,
        "currentRatio": current_ratio_metric(current_assets, current_liabilities),
        "operatingWorkingCapital": operating_working_capital(ar, inventory, ap),
        "arYoy": stock_yoy(ar.get("history")),
        "inventoryYoy": (
            {"status": "not_applicable", "reason": "no_inventory_concept", "value": None,
             "calculationMethod": "derived", "verification": "not_checked"}
            if inventory.get("status") == "not_applicable"
            else stock_yoy(inventory.get("history"))
        ),
        "apYoy": stock_yoy(ap.get("history")),
        "dso": dso,
        "dio": dio,
        "dpo": dpo,
        "cashConversionCycle": cash_conversion_cycle(dso, dio, dpo),
        "noInterestBurden": no_interest_burden,
        "growthSource": "not_yet_verified",
    }

    extracted_any = any(
        (isinstance(metrics[k], dict) and (
            metrics[k].get("status") == "extracted" or metrics[k].get("ttm") is not None
        ))
        for k in ("ocf", "capex", "operatingIncome", "cash", "revenue")
    )
    if "foreign_filer" in flags and not extracted_any:
        flags.append("no_fabricated_foreign_quarters")
        extraction_status = "insufficient_facts"
    elif extracted_any:
        extraction_status = "extracted"
    else:
        extraction_status = "insufficient_facts"

    verification_status = "company_facts_only" if extracted_any else "not_checked"
    model_applicability = "not_applicable" if "financial_institution" in flags else "applicable"
    if ocf.get("ttm") is not None and capex.get("ttm") is not None and stocks["cash"]["value"] is not None:
        input_completeness = "ready"
    else:
        input_completeness = "pending_data_verification"

    data_as_of = None
    for q in (ocf.get("quarters") or revenue.get("quarters") or []):
        if q.get("end") and q.get("value") is not None:
            data_as_of = q["end"]
            break

    return Layer3Analysis(
        cik=cik,
        extraction_status=extraction_status,
        verification_status=verification_status,
        model_applicability=model_applicability,
        scoring_status="not_implemented",
        input_completeness=input_completeness,
        currency=flows.currency,
        metrics=metrics,
        flags=flags,
        data_as_of=data_as_of,
    )
