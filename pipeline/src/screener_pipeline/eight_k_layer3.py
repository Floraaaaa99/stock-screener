"""Attach provisional 8-K earnings figures to Layer 3 issuer files.

Layer 1 / Layer 2 company JSON is never modified. Verified 10-Q/10-K quarters
remain in place; an 8-K quarter is shown only when Company Facts does not yet
cover that fiscal slot.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .cache import read_json, write_json_if_changed
from .eight_k_extract import (
    AWAITING_10Q_LABEL,
    SOURCE_TYPE_8K,
    SOURCE_TYPE_FACTS,
    VERIFIED_10Q_LABEL,
    EightKExtraction,
)
from .layer3_build import issuer_dir_for
from .sec.facts import filing_url

FLOW_KEYS = {
    "revenue": "revenue",
    "costOfRevenue": "costOfRevenue",
    "grossProfit": "grossProfit",
    "operatingIncome": "operatingIncome",
    "netIncome": "netIncome",
    "operatingCashFlow": "ocf",
    "capitalExpenditures": "capex",
    "freeCashFlow": "fcf",
}
STOCK_KEYS = {
    "cash": "cash",
    "inventory": "inventory",
    "totalDebt": "totalDebt",
    "totalAssets": "totalAssets",
    "totalLiabilities": "totalLiabilities",
}
EPS_KEY = "dilutedEps"
ALL_LAYER3_KEYS = {**FLOW_KEYS, **STOCK_KEYS, EPS_KEY: EPS_KEY}


def _period_key(fy: object, fq: object) -> str | None:
    if fy in (None, "") or fq in (None, ""):
        return None
    return f"{int(fy)}Q{int(fq)}"


def _quarter_is_verified(row: dict) -> bool:
    if row.get("value") is None:
        return False
    if row.get("sourceType") == SOURCE_TYPE_8K:
        return False
    form = str(row.get("form") or "")
    if form.startswith("10-") or form in {"10-Q", "10-K", "10-Q/A", "10-K/A", "10-QT", "10-KT"}:
        return True
    if row.get("sourceType") in {SOURCE_TYPE_FACTS, None, ""} and row.get("accn"):
        return True
    return False


def verified_quarter(metric: dict | None, fy: int | None, fq: int | None) -> dict | None:
    if not metric or fy is None or fq is None:
        return None
    want = _period_key(fy, fq)
    for row in metric.get("quarters") or []:
        if _period_key(row.get("fiscalYear"), row.get("fiscalQuarter")) != want:
            continue
        if _quarter_is_verified(row):
            return row
    for row in metric.get("history") or []:
        if _period_key(row.get("fiscalYear"), row.get("fiscalQuarter")) != want:
            continue
        if _quarter_is_verified(row):
            return row
    return None


def _overlay_quarter(extract: EightKExtraction, raw_key: str, filed: str | None, form: str) -> dict:
    item = extract.metrics[raw_key]
    return {
        "fiscalYear": item.fiscal_year,
        "fiscalQuarter": item.fiscal_quarter,
        "start": item.period_start.isoformat() if item.period_start else None,
        "end": item.period_end.isoformat() if item.period_end else None,
        "value": item.value,
        "rawValue": item.value,
        "reason": None,
        "method": item.method,
        "formula": item.formula,
        "concept": item.label,
        "accn": None,
        "form": form,
        "filed": filed,
        "url": extract.filing_url,
        "exhibitUrl": extract.exhibit_url,
        "sourceType": SOURCE_TYPE_8K,
        "unit": item.unit,
        "calculationMethod": item.method,
        "verification": "awaiting_10q",
        "verificationNote": AWAITING_10Q_LABEL,
    }


def _comparable_ttm(quarters: list[dict]) -> float | None:
    """Sum the newest four standalone quarters when every slot has a value."""
    labeled = [
        q
        for q in quarters
        if q.get("fiscalYear") is not None and q.get("fiscalQuarter") is not None and q.get("value") is not None
    ]
    by_key: dict[str, dict] = {}
    for q in labeled:
        by_key[_period_key(q["fiscalYear"], q["fiscalQuarter"]) or ""] = q
    if len(by_key) < 4:
        return None
    ordered = sorted(by_key.values(), key=lambda q: (int(q["fiscalYear"]), int(q["fiscalQuarter"])), reverse=True)
    newest = ordered[0]
    fy, fq = int(newest["fiscalYear"]), int(newest["fiscalQuarter"])
    window = []
    for _ in range(4):
        key = _period_key(fy, fq)
        row = by_key.get(key or "")
        if row is None or row.get("value") is None:
            return None
        window.append(row)
        if fq == 1:
            fy -= 1
            fq = 4
        else:
            fq -= 1
    return sum(float(q["value"]) for q in window)


def _insert_flow_quarter(metric: dict, quarter: dict) -> dict:
    updated = dict(metric)
    quarters = [dict(q) for q in (metric.get("quarters") or [])]
    want = _period_key(quarter.get("fiscalYear"), quarter.get("fiscalQuarter"))
    replaced = False
    next_rows = []
    for row in quarters:
        if _period_key(row.get("fiscalYear"), row.get("fiscalQuarter")) == want:
            if _quarter_is_verified(row):
                next_rows.append(row)
                replaced = True
                continue
            next_rows.append(quarter)
            replaced = True
        else:
            next_rows.append(row)
    if not replaced:
        next_rows.insert(0, quarter)
    updated["quarters"] = next_rows
    original_ttm = metric.get("ttm")
    provisional = _comparable_ttm(next_rows)
    if provisional is not None and any(q.get("sourceType") == SOURCE_TYPE_8K for q in next_rows[:4]):
        updated["verifiedTtm"] = original_ttm
        updated["ttm"] = provisional
        updated["ttmSourceType"] = SOURCE_TYPE_8K
        updated["verification"] = "awaiting_10q"
        updated["verificationNote"] = AWAITING_10Q_LABEL
        status = updated.get("status")
        if status in {None, "missing"}:
            updated["status"] = "extracted"
            updated["reason"] = None
    return updated


def _insert_stock_point(metric: dict, quarter: dict) -> dict:
    updated = dict(metric)
    history = [dict(h) for h in (metric.get("history") or [])]
    want = _period_key(quarter.get("fiscalYear"), quarter.get("fiscalQuarter"))
    replaced = False
    next_rows = []
    for row in history:
        if _period_key(row.get("fiscalYear"), row.get("fiscalQuarter")) == want:
            if _quarter_is_verified(row):
                next_rows.append(row)
                replaced = True
                continue
            next_rows.append({**quarter, "status": "extracted"})
            replaced = True
        else:
            next_rows.append(row)
    if not replaced:
        next_rows.insert(0, {**quarter, "status": "extracted"})
    updated["history"] = next_rows
    latest = next_rows[0] if next_rows else quarter
    if latest.get("sourceType") == SOURCE_TYPE_8K:
        updated["value"] = latest.get("value")
        updated["end"] = latest.get("end")
        updated["accn"] = latest.get("accn")
        updated["form"] = latest.get("form")
        updated["filed"] = latest.get("filed")
        updated["url"] = latest.get("url")
        updated["exhibitUrl"] = latest.get("exhibitUrl")
        updated["sourceType"] = SOURCE_TYPE_8K
        updated["verification"] = "awaiting_10q"
        updated["verificationNote"] = AWAITING_10Q_LABEL
        updated["status"] = "extracted"
        updated["reason"] = None
    return updated


def _diff_metrics(extract: EightKExtraction, payload: dict) -> dict[str, dict]:
    diffs: dict[str, dict] = {}
    metrics = payload.get("metrics") or {}
    for raw_key, layer_key in ALL_LAYER3_KEYS.items():
        item = extract.metrics.get(raw_key)
        if item is None:
            continue
        verified = verified_quarter(metrics.get(layer_key), item.fiscal_year, item.fiscal_quarter)
        eight_k_val = item.value
        verified_val = verified.get("value") if verified else None
        delta = None
        if verified_val is not None:
            delta = float(verified_val) - float(eight_k_val)
        diffs[raw_key] = {
            "eightK": eight_k_val,
            "verified": verified_val,
            "difference": delta,
            "unit": item.unit,
        }
    return diffs


def slim_provisional(extract: EightKExtraction, *, accn: str, form: str, filed: str | None, status: str) -> dict:
    return {
        "status": status,
        "label": AWAITING_10Q_LABEL if status == "awaiting_10q" else VERIFIED_10Q_LABEL,
        "form": form,
        "filed": filed,
        "accn": accn,
        "exhibitUrl": extract.exhibit_url,
        "filingUrl": extract.filing_url,
        "fiscalYear": extract.fiscal_year,
        "fiscalQuarter": extract.fiscal_quarter,
        "periodEnd": extract.period_end.isoformat() if extract.period_end else None,
        "sourceType": SOURCE_TYPE_8K,
        "metricsPresent": sorted(extract.metrics),
    }


def attach_provisional(
    payload: dict,
    extract: EightKExtraction,
    *,
    accn: str,
    form: str,
    filed: str | None,
) -> tuple[dict, str]:
    """Overlay 8-K values or mark them superseded when 10-Q facts already cover the period.

    Returns (payload, action) where action is attached | superseded | unchanged.
    """
    if extract.status != "extracted" or not extract.metrics:
        return payload, "unchanged"
    metrics = dict(payload.get("metrics") or {})
    if not metrics:
        return payload, "unchanged"

    covered = False
    for raw_key, layer_key in FLOW_KEYS.items():
        item = extract.metrics.get(raw_key)
        if item is None:
            continue
        if verified_quarter(metrics.get(layer_key), item.fiscal_year, item.fiscal_quarter):
            covered = True
            break
    if not covered:
        for raw_key, layer_key in STOCK_KEYS.items():
            item = extract.metrics.get(raw_key)
            if item is None:
                continue
            if verified_quarter(metrics.get(layer_key), item.fiscal_year, item.fiscal_quarter):
                covered = True
                break

    audit = list(payload.get("earningsReleaseAudit") or [])
    if covered:
        diffs = _diff_metrics(extract, payload)
        audit_row = {
            "accn": accn,
            "form": form,
            "filed": filed,
            "exhibitUrl": extract.exhibit_url,
            "filingUrl": extract.filing_url,
            "fiscalYear": extract.fiscal_year,
            "fiscalQuarter": extract.fiscal_quarter,
            "periodEnd": extract.period_end.isoformat() if extract.period_end else None,
            "status": "superseded",
            "label": VERIFIED_10Q_LABEL,
            "differences": diffs,
            "metrics": extract.to_state_metrics(),
        }
        if not any(row.get("accn") == accn and row.get("status") == "superseded" for row in audit):
            audit.append(audit_row)
        next_payload = dict(payload)
        next_payload["earningsReleaseAudit"] = audit
        existing = payload.get("provisionalEarnings") or {}
        if existing.get("accn") == accn or existing.get("status") == "awaiting_10q":
            next_payload["provisionalEarnings"] = slim_provisional(
                extract, accn=accn, form=form, filed=filed, status="superseded"
            )
        return next_payload, "superseded"

    for raw_key, layer_key in FLOW_KEYS.items():
        if raw_key not in extract.metrics:
            continue
        current = metrics.get(layer_key) or {
            "status": "missing",
            "reason": "no_concept",
            "ttm": None,
            "quarters": [],
            "verification": "awaiting_10q",
        }
        quarter = _overlay_quarter(extract, raw_key, filed, form)
        quarter["accn"] = accn
        if not quarter.get("url"):
            quarter["url"] = filing_url(str(payload.get("cik") or ""), accn)
        metrics[layer_key] = _insert_flow_quarter(current, quarter)

    for raw_key, layer_key in STOCK_KEYS.items():
        if raw_key not in extract.metrics:
            continue
        current = metrics.get(layer_key) or {
            "status": "missing",
            "reason": "no_concept",
            "value": None,
            "history": [],
            "verification": "not_checked",
        }
        quarter = _overlay_quarter(extract, raw_key, filed, form)
        quarter["accn"] = accn
        metrics[layer_key] = _insert_stock_point(current, quarter)

    if EPS_KEY in extract.metrics:
        quarter = _overlay_quarter(extract, EPS_KEY, filed, form)
        quarter["accn"] = accn
        current = metrics.get(EPS_KEY) or {
            "status": "extracted",
            "reason": None,
            "ttm": None,
            "quarters": [],
            "verification": "awaiting_10q",
        }
        metrics[EPS_KEY] = _insert_flow_quarter(current, quarter)

    next_payload = dict(payload)
    next_payload["metrics"] = metrics
    next_payload["provisionalEarnings"] = slim_provisional(
        extract, accn=accn, form=form, filed=filed, status="awaiting_10q"
    )
    flags = list(next_payload.get("flags") or [])
    if "eight_k_awaiting_10q" not in flags:
        flags.append("eight_k_awaiting_10q")
    next_payload["flags"] = flags
    if extract.period_end:
        current_as_of = next_payload.get("dataAsOf")
        end = extract.period_end.isoformat()
        if not current_as_of or end > str(current_as_of):
            next_payload["dataAsOf"] = end
    return next_payload, "attached"


def apply_extractions_to_issuer(
    path: Path,
    rows: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Apply extracted/supersede actions to one issuer file. Never writes on failure."""
    if not path.exists():
        return False, ["issuer_missing"]
    original = read_json(path)
    if not isinstance(original, dict):
        return False, ["issuer_invalid"]
    payload = original
    actions: list[str] = []
    try:
        for row in rows:
            extract: EightKExtraction = row["extract"]
            payload, action = attach_provisional(
                payload,
                extract,
                accn=row["accn"],
                form=row["form"],
                filed=row.get("filed"),
            )
            actions.append(action)
    except Exception:  # noqa: BLE001 — keep verified JSON
        return False, ["attach_failed"]
    if payload is original or actions == ["unchanged"] * len(actions):
        return False, actions
    changed = write_json_if_changed(path, payload, compact=True)
    return changed, actions


def apply_extractions_to_dataset(
    data_dir: Path,
    by_cik: dict[str, list[dict[str, Any]]],
    *,
    dest: Path | None = None,
) -> tuple[list[str], set[str]]:
    """Write overlays into layer3/cik/*.json. Failed attach skips that file."""
    root = Path(dest or data_dir)
    cik_dir = issuer_dir_for(root / "layer3.json") if (root / "layer3.json").exists() else root / "layer3" / "cik"
    updated: list[str] = []
    superseded: set[str] = set()
    for cik, rows in by_cik.items():
        path = cik_dir / f"{str(cik).zfill(10)}.json"
        changed, actions = apply_extractions_to_issuer(path, rows)
        for row, action in zip(rows, actions, strict=False):
            if action == "superseded":
                superseded.add(row["accn"])
        if changed:
            updated.append(str(cik).zfill(10))
    return updated, superseded


def extraction_from_state(row: dict) -> EightKExtraction | None:
    if not isinstance(row, dict) or row.get("status") not in {"extracted", "superseded"}:
        return None
    from .eight_k_extract import ExtractedMetric

    metrics = {}
    for key, raw in (row.get("metrics") or {}).items():
        if not isinstance(raw, dict) or raw.get("value") is None:
            continue
        end = raw.get("periodEnd")
        start = raw.get("periodStart")
        metrics[key] = ExtractedMetric(
            key=key,
            value=float(raw["value"]),
            unit=raw.get("unit") or "USD",
            scale=float(raw.get("scale") or 1),
            label=raw.get("label") or key,
            period_kind=raw.get("periodKind") or "quarterly",
            fiscal_year=raw.get("fiscalYear"),
            fiscal_quarter=raw.get("fiscalQuarter"),
            period_end=date.fromisoformat(end) if end else None,
            period_start=date.fromisoformat(start) if start else None,
            gaap=bool(raw.get("gaap", True)),
            method=raw.get("method") or "reported",
            formula=raw.get("formula"),
        )
    if not metrics:
        return None
    period_end = row.get("periodEnd")
    return EightKExtraction(
        status="extracted",
        reason=None,
        item_202=True,
        exhibit_name=row.get("exhibitName"),
        exhibit_url=row.get("exhibitUrl"),
        filing_url=row.get("filingUrl"),
        fiscal_year=row.get("fiscalYear"),
        fiscal_quarter=row.get("fiscalQuarter"),
        period_end=date.fromisoformat(period_end) if period_end else None,
        metrics=metrics,
    )
