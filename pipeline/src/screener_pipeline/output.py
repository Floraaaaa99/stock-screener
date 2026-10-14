"""Serialize pipeline results into the static JSON files read by the website."""

from __future__ import annotations

from datetime import date

from .quarters import MissingQuarter, Quarter
from .revenue import CompanyRevenue, slot_role
from .sec.facts import filing_url

SCHEMA_VERSION = 1


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def quarter_json(slot, index: int, cik: str, rev: CompanyRevenue) -> dict:
    base = {
        "fiscalYear": slot.fiscal_year,
        "fiscalQuarter": slot.fiscal_quarter,
        "start": _iso(slot.start),
        "end": _iso(slot.end),
        "ttm": slot_role(index),
    }
    if isinstance(slot, MissingQuarter):
        return {**base, "missing": True, "value": None}
    q: Quarter = slot
    primary = q.sources[0]
    check = rev.quarter_checks.get(q.end)
    return {
        **base,
        "missing": False,
        "value": q.val,
        "concept": q.concept,
        "method": q.method,
        "formula": q.formula,
        "form": primary.form,
        "filed": _iso(primary.filed),
        "accn": primary.accn,
        "url": filing_url(cik, primary.accn),
        "restated": q.restated,
        "labelInferred": q.label_inferred,
        "flags": q.flags,
        "sources": [
            {
                "role": s.role,
                "sign": s.sign,
                "form": s.form,
                "filed": _iso(s.filed),
                "accn": s.accn,
                "start": _iso(s.start),
                "end": _iso(s.end),
                "value": s.val,
                "url": filing_url(cik, s.accn),
            }
            for s in q.sources
        ],
        "check": check.to_dict() if check else None,
    }


def company_json(listing, cik: str | None, sec_name: str | None, rev: CompanyRevenue | None,
                 yahoo: dict, issues: list[dict]) -> dict:
    revenue = None
    if rev is not None:
        sel = rev.selection
        revenue = {
            "status": rev.status,
            "currency": rev.currency,
            "concept": sel.concept if sel else None,
            "conceptStatus": sel.status if sel else None,
            "conceptNote": sel.note if sel else "",
            "candidates": sel.candidates if sel else [],
            "flags": rev.flags,
            "statementCheck": rev.statement_check,
            "quarters": [quarter_json(s, i, cik or "", rev) for i, s in enumerate(rev.slots)],
        }
    ttm = rev.ttm if rev else None
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ticker": listing.symbol,
        "name": listing.name,
        "exchange": listing.exchange,
        "securityType": listing.security_type,
        "cik": cik,
        "secName": sec_name,
        "market": {
            "sector": yahoo.get("sector"),
            "industry": yahoo.get("industry"),
            "marketCap": yahoo.get("marketCap"),
            "price": yahoo.get("price"),
            "currency": yahoo.get("currency"),
            "quoteType": yahoo.get("quoteType"),
            "profileAsOf": yahoo.get("profile_as_of"),
            "marketAsOf": yahoo.get("market_as_of"),
        },
        "ttm": {
            "current": ttm.current if ttm else None,
            "previous": ttm.previous if ttm else None,
            "growthPct": ttm.growth_pct if ttm else None,
            "reason": (ttm.reason if ttm else "no_cik"),
        },
        "revenue": revenue,
        "classificationIssues": issues,
    }


def screener_row(c: dict) -> dict:
    rev = c.get("revenue") or {}
    quarters = rev.get("quarters") or []
    latest = next((q for q in quarters if not q.get("missing")), None)
    return {
        "ticker": c["ticker"],
        "name": c["name"],
        "exchange": c["exchange"],
        "type": c["securityType"],
        "sector": c["market"]["sector"],
        "industry": c["market"]["industry"],
        "marketCap": c["market"]["marketCap"],
        "price": c["market"]["price"],
        "priceCurrency": c["market"]["currency"],
        "revenueCurrency": rev.get("currency"),
        "ttmCurrent": c["ttm"]["current"],
        "ttmPrevious": c["ttm"]["previous"],
        "ttmGrowth": c["ttm"]["growthPct"],
        "naReason": c["ttm"]["reason"],
        "latestQuarter": (
            f"FY{latest['fiscalYear']} Q{latest['fiscalQuarter']}" if latest and latest.get("fiscalYear") else None
        ),
        "latestQuarterEnd": latest["end"] if latest else None,
        "quartersAvailable": sum(1 for q in quarters if not q.get("missing")),
    }
