"""Merge extracted 8-K earnings figures into the shared Company Facts payload.

Layers 1, 2, and 3 all read this same quarterly dataset. Missing 8-K metrics stay
absent — they are never invented or written as zero. Derived Non-GAAP figures
(company-reported FCF) are not injected as US-GAAP facts.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

from .eight_k_extract import EightKExtraction, ExtractedMetric
from .sec.facts import CURRENT_REPORT_FORMS

# Map extracted 8-K keys onto the same us-gaap concepts Layer 1 / Layer 3 already read.
DURATION_CONCEPTS = {
    "revenue": ("Revenues", "USD"),
    "costOfRevenue": ("CostOfRevenue", "USD"),
    "grossProfit": ("GrossProfit", "USD"),
    "operatingIncome": ("OperatingIncomeLoss", "USD"),
    "netIncome": ("NetIncomeLoss", "USD"),
    "operatingCashFlow": ("NetCashProvidedByUsedInOperatingActivities", "USD"),
    "capitalExpenditures": ("PaymentsToAcquirePropertyPlantAndEquipment", "USD"),
}
INSTANT_CONCEPTS = {
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "USD"),
    "inventory": ("InventoryNet", "USD"),
    "totalDebt": ("LongTermDebt", "USD"),
}

# Not US-GAAP Company Facts: derived FCF, Non-GAAP FCF, EPS (Layer 3 overlay), unused stocks.
SKIP_KEYS = {
    "freeCashFlow",
    "companyReportedFreeCashFlow",
    "dilutedEps",
    "totalAssets",
    "totalLiabilities",
}


def _parse_filed(raw: object) -> date | None:
    if raw in (None, ""):
        return None
    text = str(raw)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _quarter_start(end: date) -> date:
    month = end.month - 2
    year = end.year
    if month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _fp(fiscal_quarter: int | None) -> str | None:
    if fiscal_quarter == 1:
        return "Q1"
    if fiscal_quarter == 2:
        return "Q2"
    if fiscal_quarter == 3:
        return "Q3"
    if fiscal_quarter == 4:
        return "FY"
    return None


def _gaap_root(payload: dict) -> dict:
    facts = payload.setdefault("facts", {})
    gaap = facts.setdefault("us-gaap", {})
    return gaap


def _append_fact(gaap: dict, concept: str, unit: str, row: dict) -> None:
    bucket = gaap.setdefault(concept, {}).setdefault("units", {}).setdefault(unit, [])
    for existing in bucket:
        if (
            existing.get("accn") == row.get("accn")
            and existing.get("end") == row.get("end")
            and existing.get("start") == row.get("start")
            and existing.get("form") == row.get("form")
        ):
            return
    bucket.append(row)


def _metric_row(
    metric: ExtractedMetric,
    *,
    accn: str,
    form: str,
    filed: date,
    instant: bool,
) -> dict | None:
    if metric.value is None:
        return None
    end = metric.period_end
    if end is None:
        return None
    fy = metric.fiscal_year
    fp = _fp(metric.fiscal_quarter)
    row: dict[str, Any] = {
        "end": end.isoformat(),
        "val": float(metric.value),
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed.isoformat(),
    }
    if instant:
        return row
    start = metric.period_start or _quarter_start(end)
    row["start"] = start.isoformat()
    return row


def merge_extraction_into_companyfacts(
    companyfacts: dict,
    extract: EightKExtraction,
    *,
    accn: str,
    form: str,
    filed: str | None,
) -> dict:
    """Return a copy of `companyfacts` with available 8-K figures appended.

    Existing 10-Q/10-K facts are preserved. Unavailable 8-K metrics are omitted.
    """
    if extract.status != "extracted" or not extract.metrics:
        return companyfacts
    if form not in CURRENT_REPORT_FORMS:
        form = "8-K"
    filed_d = _parse_filed(filed) or extract.period_end
    if filed_d is None:
        return companyfacts

    payload = copy.deepcopy(companyfacts)
    gaap = _gaap_root(payload)
    for key, metric in extract.metrics.items():
        if key in SKIP_KEYS:
            continue
        if not isinstance(metric, ExtractedMetric) or metric.value is None:
            continue
        if metric.gaap is False:
            continue
        if key in DURATION_CONCEPTS:
            concept, unit = DURATION_CONCEPTS[key]
            row = _metric_row(metric, accn=accn, form=form, filed=filed_d, instant=False)
            if row is None:
                continue
            _append_fact(gaap, concept, unit, row)
        elif key in INSTANT_CONCEPTS:
            concept, unit = INSTANT_CONCEPTS[key]
            row = _metric_row(metric, accn=accn, form=form, filed=filed_d, instant=True)
            if row is None:
                continue
            _append_fact(gaap, concept, unit, row)
    return payload


def merge_extractions_into_companyfacts(companyfacts: dict, rows: list[dict[str, Any]]) -> dict:
    """Apply extracted (not yet superseded) 8-K rows in filing order."""
    payload = companyfacts
    for row in rows:
        if row.get("status") == "superseded":
            continue
        extract = row.get("extract")
        if not isinstance(extract, EightKExtraction):
            continue
        payload = merge_extraction_into_companyfacts(
            payload,
            extract,
            accn=str(row.get("accn") or ""),
            form=str(row.get("form") or "8-K"),
            filed=row.get("filed"),
        )
    return payload
