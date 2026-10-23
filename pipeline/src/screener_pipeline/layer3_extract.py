"""Extract and derive Layer 3 financial metrics from SEC Company Facts.

Reuses quarter derivation (including YTD → standalone Q and Q4 = FY − 9M) and TTM windowing.
Missing or unverified values stay null with a reason. Never mapped to zero.
Does not compute the 100-point score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .concepts import ConceptSeries, select_concept
from .layer3_concepts import (
    ACQUISITION_CF_CONCEPTS,
    AMORTIZATION_ADDON_CONCEPTS,
    AP_CONCEPTS,
    AR_CONCEPTS,
    ASSET_SALE_CONCEPTS,
    CAPEX_CONCEPTS,
    CAPEX_MAY_BE_NET,
    CASH_CONCEPTS,
    CF_CASH_CHANGE_EXCLUDING_FX_CONCEPTS,
    CF_CASH_CHANGE_INCLUDING_FX_CONCEPTS,
    COST_OF_REVENUE_CONCEPTS,
    CURRENT_ASSET_CONCEPTS,
    CURRENT_LIABILITY_CONCEPTS,
    DA_CONCEPTS,
    DEBT_FINANCING_NET_CONCEPTS,
    DEBT_ISSUANCE_COSTS_NOTE,
    DEBT_ISSUANCE_GROSS_CONCEPTS,
    DEBT_ISSUANCE_NET_OF_COSTS,
    DEBT_REPAYMENT_GROSS_CONCEPTS,
    DEPRECIATION_ONLY_CONCEPTS,
    DIVIDEND_PAID_CONCEPTS,
    EQUITY_ISSUANCE_CONCEPTS,
    FINANCING_CF_CONCEPTS,
    FLOW_ALIGN_DAYS,
    FLOW_CONCEPTS,
    FX_ON_CASH_CONCEPTS,
    GROSS_PROFIT_CONCEPTS,
    HISTORY_SLOTS,
    INTEREST_CONCEPTS,
    INVENTORY_CONCEPTS,
    INVENTORY_NARROW_SCOPE,
    INVESTING_CF_CONCEPTS,
    LAYER3_EXTRACTION_VERSION,
    LAYER3_SCHEMA_VERSION,
    LT_DEBT_CONCEPTS,
    LT_DEBT_INCLUDES_LEASES,
    NET_DEBT_FINANCING_NOTE,
    OCF_CONCEPTS,
    OPERATING_INCOME_CONCEPTS,
    SHARE_REPURCHASE_CONCEPTS,
    ST_DEBT_PART_CONCEPTS,
    ST_DEBT_TOTAL_CONCEPTS,
    STOCK_ALIGN_DAYS,
    STOCK_CONCEPTS,
    TOTAL_DEBT_FALLBACK_CONCEPTS,
    TOTAL_DEBT_INCLUDES_LEASES,
    cash_change_includes_fx,
    cf_cash_family,
    gaap_concepts_present,
    is_financial_sic,
    normalize_cik,
)
from .layer3_derived import (
    add_flows,
    apply_ttm_yoy,
    average_balance,
    cash_conversion_cycle,
    cash_conversion_metric,
    cash_flow_identity,
    current_ratio_metric,
    days_outstanding,
    flag_extreme_ratio,
    identity_holds,
    margin_metric,
    operating_working_capital,
    stock_yoy,
    subtract_flows,
    suppress_incompatible_derived,
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
    source_type_for_form,
)
from .ttm import TTMResult

NULL = None


def _layer3_currency(companyfacts: dict) -> str | None:
    """Issuer research currency from OCF / revenue / cash, not the full concept bag.

    A secondary tag that happens to include USD (e.g. NetIncomeLoss CAD+USD) must
    not drop CAD-only operating and cash-flow series.
    """
    gaap = (companyfacts.get("facts") or {}).get("us-gaap") or {}
    for concept in (*OCF_CONCEPTS, *REVENUE_CONCEPTS, *CASH_CONCEPTS):
        units = (gaap.get(concept) or {}).get("units") or {}
        if not units:
            continue
        if "USD" in units:
            return "USD"
        monetary = [u for u in units if "/" not in u and u.isalpha() and len(u) == 3]
        if len(monetary) == 1:
            return monetary[0]
    return None


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


def _concept_series(rf: RevenueFacts, concept: str) -> ConceptSeries | None:
    facts = rf.by_concept.get(concept) or []
    if not facts:
        return None
    periods = dedupe_periods(facts)
    quarters = derive_quarters(periods, concept)
    label_quarters(quarters, rf.filings)
    if not quarters:
        return None
    return ConceptSeries(concept, periods, quarters)


def _missing_flow(reason: str, *, concept: str | None = None) -> dict:
    return apply_ttm_yoy({
        "status": "missing",
        "reason": reason,
        "concept": concept,
        "ttm": None,
        "previousTtm": None,
        "quarters": [],
        "calculationMethod": "extracted",
        "verification": "not_checked",
    })


def _flow_from_slots(
    rf: RevenueFacts,
    slots: list[Slot],
    *,
    concept: str,
    cik: str = "",
    as_of: date | None = None,
    require_align: bool = False,
) -> dict:
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
    ttm = compute_flow_ttm(slots)
    return apply_ttm_yoy({
        "status": "extracted" if ttm.current is not None else "missing",
        "reason": ttm.reason,
        "concept": concept,
        "unit": rf.currency,
        "ttm": ttm.current,
        "previousTtm": ttm.previous,
        "quarters": _quarter_payloads(slots, cik=cik),
        "calculationMethod": "extracted",
        "verification": "company_facts_only",
        "verificationNote": COMPANY_FACTS_ONLY_NOTE,
    })


def _revenue_metric(
    rf: RevenueFacts,
    candidates: list[str],
    *,
    cik: str = "",
    as_of: date | None = None,
    require_align: bool = False,
    override: str | None = None,
) -> dict:
    """Layer 1 `select_concept` on revenue, including equivalent `concept_merged` history.

    Does not pick a single XBRL tag by list order. Overlapping equivalent tags may
    fill gaps; disagreeing or non-overlapping tags are not merged.
    """
    series: list[ConceptSeries] = []
    for concept in candidates:
        item = _concept_series(rf, concept)
        if item is not None:
            series.append(item)
    if not series:
        return _missing_flow("no_concept")
    sel = select_concept(
        series,
        None,
        override,
        concepts=candidates,
        line_name="total revenue",
    )
    if sel.status == "ambiguous" or sel.concept is None or not sel.quarters:
        reason = "ambiguous_concept" if sel.status == "ambiguous" else "no_concept"
        return _missing_flow(reason, concept=sel.concept)
    slots = build_timeline(sel.quarters, sel.anchor_end)
    return _flow_from_slots(
        rf, slots, concept=sel.concept, cik=cik, as_of=as_of, require_align=require_align,
    )


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
                "sourceType": source_type_for_form(s.sources[0].form) if s.sources else None,
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
    magnitude: bool = False,
    cik: str = "",
    as_of: date | None = None,
    require_align: bool = False,
    financing_basis: str | None = None,
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
        return _annotate_cash_flow(
            apply_ttm_yoy({
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
            }),
            concept=concept,
            financing_basis=financing_basis,
        )
    if capex or magnitude:
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
        if capex and concept in CAPEX_MAY_BE_NET:
            payload["scopeNote"] = (
                "Last-resort tag; US-GAAP name is net of asset-sale proceeds. "
                "Used only when no gross PPE CapEx tag is aligned."
            )
        return _annotate_cash_flow(payload, concept=concept, financing_basis=financing_basis)
    ttm = compute_flow_ttm(slots)
    quarters = _quarter_payloads(slots, cik=cik)
    return _annotate_cash_flow(
        apply_ttm_yoy({
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
        }),
        concept=concept,
        financing_basis=financing_basis,
    )


def _annotate_cash_flow(payload: dict, *, concept: str | None, financing_basis: str | None) -> dict:
    """Gross vs net debt labels. A net tag is never retitled as issuance or repayment."""
    if financing_basis:
        payload["financingBasis"] = financing_basis
    if financing_basis == "net":
        payload["scopeNote"] = NET_DEBT_FINANCING_NOTE
    elif financing_basis == "gross" and concept in DEBT_ISSUANCE_NET_OF_COSTS:
        payload["scopeNote"] = DEBT_ISSUANCE_COSTS_NOTE
    return payload


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
        "sourceType": source_type_for_form(latest.form),
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
        "sourceType": found.get("sourceType") or source_type_for_form(found.get("form")),
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


def _usable_aligned_ttm(metric: dict | None) -> bool:
    """True when the series has a current TTM on the analysis window.

    A tag that only has older quarters (HEI GrossProfit through FY2020) is not
    current and must not block Revenue − COGS / Revenue − GP derivation.
    """
    if not metric:
        return False
    return metric.get("status") == "extracted" and metric.get("ttm") is not None


def _stale_window_note(metric: dict) -> str:
    newest = metric.get("newestEnd")
    aligned = metric.get("alignedTo")
    if newest and aligned:
        return f" (newestEnd {newest}, alignedTo {aligned})"
    if newest:
        return f" (newestEnd {newest})"
    return ""


def _select_gross_and_cogs(
    rf: RevenueFacts,
    revenue: dict,
    cik: str,
    as_of: date | None,
) -> tuple[dict, dict]:
    """Pick GP and COGS that share revenue's scope. Never take the first non-empty tag.

    Only aligned TTM series count as reported-current. A stale tag does not
    override a same-period derivation, and two aligned series that do not foot
    are both kept (never overwritten).
    """
    gps = _candidate_flows(rf, GROSS_PROFIT_CONCEPTS, cik, as_of)
    costs = _candidate_flows(rf, COST_OF_REVENUE_CONCEPTS, cik, as_of)
    aligned_gps = [m for m in gps if _usable_aligned_ttm(m)]
    aligned_costs = [m for m in costs if _usable_aligned_ttm(m)]
    rev_ttm = revenue.get("ttm")

    for gp in aligned_gps:
        for cogs in aligned_costs:
            if identity_holds(gp.get("ttm"), cogs.get("ttm"), rev_ttm):
                gp = {**gp, "identity": "gross_plus_cogs_equals_revenue"}
                cogs = {**cogs, "identity": "gross_plus_cogs_equals_revenue"}
                return apply_ttm_yoy(gp), apply_ttm_yoy(cogs)

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

    if rev_ttm is not None and aligned_gps and not aligned_costs:
        gp = aligned_gps[0]
        implied = subtract_flows(
            revenue, gp, "Revenue − Gross Profit",
            missing_left="missing_revenue", missing_right="missing_gross_profit",
        )
        implied["concept"] = None
        implied["derivedFrom"] = "revenue_minus_gross_profit"
        if costs:
            implied["scopeNote"] = (
                "Reported Cost of Revenue is not aligned to the current TTM window"
                f"{_stale_window_note(costs[0])}. Derived as Revenue − Gross Profit "
                "from the aligned pair. The unaligned tagged series was not used."
            )
        return apply_ttm_yoy(gp), implied
    if rev_ttm is not None and aligned_costs and not aligned_gps:
        cogs = aligned_costs[0]
        implied = subtract_flows(
            revenue, cogs, "Revenue − Cost of Revenue",
            missing_left="missing_revenue", missing_right="missing_cost_of_revenue",
        )
        implied["concept"] = None
        implied["derivedFrom"] = "revenue_minus_cost_of_revenue"
        if gps:
            implied["scopeNote"] = (
                "Reported Gross Profit is not aligned to the current TTM window"
                f"{_stale_window_note(gps[0])}. Derived as Revenue − Cost of Revenue "
                "from the aligned pair. The unaligned tagged series was not used as current GP."
            )
        return implied, apply_ttm_yoy(cogs)

    if aligned_gps and aligned_costs:
        gp = apply_ttm_yoy({
            **aligned_gps[0],
            "identity": "concept_scope_mismatch" if rev_ttm is not None else "unverified_without_revenue",
            "scopeNote": (
                "Reported Gross Profit and Cost of Revenue do not foot to selected "
                "Revenue. Both Company Facts series are kept. COGS was not replaced "
                "with Revenue − Gross Profit."
            ),
        })
        cogs = apply_ttm_yoy({
            **aligned_costs[0],
            "identity": "concept_scope_mismatch" if rev_ttm is not None else "unverified_without_revenue",
            "scopeNote": (
                "Reported Cost of Revenue conflicts with Gross Profit + Revenue. "
                "The tagged series is preserved; it is not overwritten with a derived value."
            ),
        })
        return gp, cogs
    return apply_ttm_yoy(gps[0] if gps else empty), apply_ttm_yoy(costs[0] if costs else empty)


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
    disclosures: dict | None = None

    def to_dict(self) -> dict:
        payload = {
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
        if self.disclosures:
            if "cashFlow" in self.disclosures or "groups" not in self.disclosures:
                payload["disclosures"] = self.disclosures
            else:
                payload["disclosures"] = {"cashFlow": self.disclosures}
        return payload


def analyze_layer3_facts(
    companyfacts: dict,
    *,
    sic_code: str | None = None,
    foreign: bool | None = None,
    preferred_revenue_concept: str | None = None,
    preferred_earnings_concept: str | None = None,
    canonical_cik: str | None = None,
    disclosures: dict | None = None,
) -> Layer3Analysis:
    """Analyze one issuer's Company Facts payload. Does not score.

    Issuer identity is ``canonical_cik`` when provided (the issuers.json /
    filename CIK). A missing or zero Company Facts CIK is never used as identity.
    """
    currency = _layer3_currency(companyfacts)
    flows = extract_named_duration_facts(companyfacts, FLOW_CONCEPTS, currency=currency)
    instants = extract_instant_facts(companyfacts, STOCK_CONCEPTS, currency=currency)
    facts_cik = normalize_cik(flows.cik) or normalize_cik(companyfacts.get("cik"))
    canonical = normalize_cik(canonical_cik)
    cik = canonical or facts_cik or str(canonical_cik or "").zfill(10)
    flags: list[str] = []
    if canonical and facts_cik and facts_cik != canonical:
        flags.append("company_facts_cik_mismatch")
    elif canonical and facts_cik is None and companyfacts.get("cik") not in (None, ""):
        flags.append("company_facts_cik_unusable")
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
    if preferred_revenue_concept and preferred_revenue_concept not in rev_concepts:
        rev_concepts = [preferred_revenue_concept, *rev_concepts]
    earn_concepts = list(EARNINGS_CONCEPTS)
    if preferred_earnings_concept:
        earn_concepts = [preferred_earnings_concept] + [c for c in earn_concepts if c != preferred_earnings_concept]
    revenue = _revenue_metric(
        flows,
        rev_concepts,
        cik=cik,
        as_of=as_of,
        require_align=align,
        override=preferred_revenue_concept,
    )
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
    flow_kw = {"cik": cik, "as_of": as_of, "require_align": align}
    investing_cf = _flow_metric(flows, INVESTING_CF_CONCEPTS, **flow_kw)
    financing_cf = _flow_metric(flows, FINANCING_CF_CONCEPTS, **flow_kw)
    debt_issuance = _flow_metric(
        flows, DEBT_ISSUANCE_GROSS_CONCEPTS, financing_basis="gross", **flow_kw
    )
    debt_repayment = _flow_metric(
        flows, DEBT_REPAYMENT_GROSS_CONCEPTS, magnitude=True, financing_basis="gross", **flow_kw
    )
    net_debt_financing = _flow_metric(
        flows, DEBT_FINANCING_NET_CONCEPTS, financing_basis="net", **flow_kw
    )
    equity_issuance = _flow_metric(flows, EQUITY_ISSUANCE_CONCEPTS, **flow_kw)
    asset_sales = _flow_metric(flows, ASSET_SALE_CONCEPTS, **flow_kw)
    share_repurchases = _flow_metric(flows, SHARE_REPURCHASE_CONCEPTS, magnitude=True, **flow_kw)
    dividends_paid = _flow_metric(flows, DIVIDEND_PAID_CONCEPTS, magnitude=True, **flow_kw)
    acquisitions = _flow_metric(flows, ACQUISITION_CF_CONCEPTS, magnitude=True, **flow_kw)
    fx_on_cash = _flow_metric(flows, FX_ON_CASH_CONCEPTS, **flow_kw)
    cash_change_excl = _flow_metric(flows, CF_CASH_CHANGE_EXCLUDING_FX_CONCEPTS, **flow_kw)
    cash_change_incl = _flow_metric(flows, CF_CASH_CHANGE_INCLUDING_FX_CONCEPTS, **flow_kw)
    cash_change = cash_change_excl if cash_change_excl.get("ttm") is not None else cash_change_incl
    cash_cf_identity = cash_flow_identity(
        ocf=ocf,
        investing=investing_cf,
        financing=financing_cf,
        fx=fx_on_cash,
        cash_change=cash_change,
        includes_fx=cash_change_includes_fx(cash_change.get("concept")),
        cash_family=cf_cash_family(cash_change.get("concept")),
        f3_cash_concept=stocks["cash"].get("concept"),
        align_days=FLOW_ALIGN_DAYS,
    )
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
        "investingCf": investing_cf,
        "financingCf": financing_cf,
        "debtIssuance": debt_issuance,
        "debtRepayment": debt_repayment,
        "netDebtFinancing": net_debt_financing,
        "equityIssuance": equity_issuance,
        "assetSales": asset_sales,
        "shareRepurchases": share_repurchases,
        "dividendsPaid": dividends_paid,
        "acquisitions": acquisitions,
        "fxOnCash": fx_on_cash,
        "cashChangeCf": cash_change,
        "cashCfIdentity": cash_cf_identity,
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
        "currentRatio": flag_extreme_ratio(
            current_ratio_metric(current_assets, current_liabilities), "currentRatio"
        ),
        "operatingWorkingCapital": operating_working_capital(ar, inventory, ap),
        "arYoy": stock_yoy(ar.get("history")),
        "inventoryYoy": (
            {"status": "not_applicable", "reason": "no_inventory_concept", "value": None,
             "calculationMethod": "derived", "verification": "not_checked"}
            if inventory.get("status") == "not_applicable"
            else stock_yoy(inventory.get("history"))
        ),
        "apYoy": stock_yoy(ap.get("history")),
        "dso": flag_extreme_ratio(dso, "dso"),
        "dio": flag_extreme_ratio(dio, "dio"),
        "dpo": flag_extreme_ratio(dpo, "dpo"),
        "cashConversionCycle": flag_extreme_ratio(
            cash_conversion_cycle(dso, dio, dpo), "cashConversionCycle"
        ),
        "noInterestBurden": no_interest_burden,
        "growthSource": "not_yet_verified",
    }

    if (
        gross_profit.get("identity") == "concept_scope_mismatch"
        or cost_of_revenue.get("identity") == "concept_scope_mismatch"
    ):
        flags.append("concept_scope_mismatch")
        metrics["grossMargin"] = suppress_incompatible_derived(metrics["grossMargin"])
        if metrics["dio"].get("status") != "not_applicable":
            metrics["dio"] = suppress_incompatible_derived(metrics["dio"])
        metrics["dpo"] = suppress_incompatible_derived(metrics["dpo"])
        metrics["cashConversionCycle"] = suppress_incompatible_derived(
            metrics["cashConversionCycle"]
        )

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
        disclosures=disclosures,
    )
