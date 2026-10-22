"""Run 8-K earnings extract on the existing daily SEC update.

New 8-Ks come from this run's discovery. Failed or pending extracts are
retried. A small one-shot list can target already-recorded accessions
without scanning unrelated historical 8-Ks. Failed extracts do not rewrite
verified JSON.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from . import config
from .eight_k_extract import extract_earnings_release
from .sec.daily_index import DailyFiling
from .sec.eight_k import discover_earnings_exhibit
from .sec.facts import CURRENT_REPORT_FORMS, filing_url

log = logging.getLogger(__name__)

TERMINAL_STATUSES = {"extracted", "not_earnings", "superseded"}
RETRYABLE_STATUSES = {"pending", "failed"}


def prune_extractions(extractions: dict, as_of: date, keep_days: int) -> dict:
    cutoff = as_of - timedelta(days=keep_days)
    kept: dict[str, dict] = {}
    for accn, row in extractions.items():
        if not isinstance(row, dict):
            continue
        raw = row.get("filed")
        try:
            filed = date.fromisoformat(str(raw)) if raw else None
        except ValueError:
            filed = None
        if filed is None or filed >= cutoff:
            kept[accn] = row
    return kept


def _row_to_filing(accn: str, row: dict) -> DailyFiling | None:
    try:
        filed = date.fromisoformat(str(row.get("filed")))
    except (TypeError, ValueError):
        return None
    accepted = None
    raw_acc = row.get("accepted")
    if raw_acc:
        try:
            accepted = datetime.fromisoformat(str(raw_acc).replace("Z", "+00:00"))
        except ValueError:
            accepted = None
    cik = str(row.get("cik") or "").zfill(10)
    if not cik.isdigit():
        return None
    return DailyFiling(
        cik=cik,
        name=str(row.get("name") or ""),
        form=str(row.get("form") or "8-K"),
        filed=filed,
        filename=str(row.get("filename") or f"edgar/data/{int(cik)}/{accn}.txt"),
        accn=accn,
        accepted=accepted,
        source=str(row.get("source") or "retry"),
    )


def should_process_extraction(row: dict | None, *, max_attempts: int) -> bool:
    if row is None:
        return True
    status = row.get("status")
    if status in TERMINAL_STATUSES:
        return False
    if status == "failed" and int(row.get("attempts") or 0) >= max_attempts:
        return False
    return True


def collect_earnings_jobs(
    recorded_current: list[DailyFiling],
    processed: dict,
    extractions: dict,
    *,
    as_of: date,
    by_cik: dict[str, list[str]],
    one_shot_accns: tuple[str, ...] | None = None,
    max_attempts: int | None = None,
) -> list[DailyFiling]:
    _ = as_of
    max_attempts = config.EIGHT_K_MAX_ATTEMPTS if max_attempts is None else max_attempts
    one_shot_accns = config.EIGHT_K_ONE_SHOT_ACCNS if one_shot_accns is None else one_shot_accns
    jobs: list[DailyFiling] = []
    seen: set[str] = set()

    def add(filing: DailyFiling) -> None:
        if filing.accn in seen:
            return
        if filing.form not in CURRENT_REPORT_FORMS:
            return
        if filing.cik not in by_cik:
            return
        if not should_process_extraction(extractions.get(filing.accn), max_attempts=max_attempts):
            return
        jobs.append(filing)
        seen.add(filing.accn)

    for filing in recorded_current:
        add(filing)
    for accn, row in extractions.items():
        if not should_process_extraction(row if isinstance(row, dict) else None, max_attempts=max_attempts):
            continue
        filing = _row_to_filing(accn, row if isinstance(row, dict) else {})
        if filing is None and isinstance(processed.get(accn), dict):
            filing = _row_to_filing(accn, processed[accn])
        if filing is None:
            continue
        add(filing)
    for accn in one_shot_accns:
        row = processed.get(accn)
        if not isinstance(row, dict) or row.get("status") != "recorded_8k":
            continue
        filing = _row_to_filing(accn, {**row, "source": "one_shot"})
        if filing is None:
            continue
        add(filing)
    return jobs


def _injected_fetch(documents: dict[str, dict[str, str]]) -> Callable[[str, str, str], str | None]:
    def fetch(_cik: str, accn: str, name: str) -> str | None:
        bucket = documents.get(accn) or {}
        if name in bucket:
            return bucket[name]
        # Allow lookup by basename aliases used in tests.
        for key, value in bucket.items():
            if key.rsplit("/", 1)[-1] == name:
                return value
        return None

    return fetch


def _client_fetch(sec) -> Callable[[str, str, str], str | None]:
    def fetch(cik: str, accn: str, name: str) -> str | None:
        try:
            return sec.filing_document(cik, accn, name)
        except FileNotFoundError:
            return None
        except Exception as exc:  # noqa: BLE001 — extraction is best-effort
            log.warning("8-K document fetch failed for %s %s: %s", accn, name, exc)
            return None

    return fetch


def process_earnings_filing(
    filing: DailyFiling,
    fetch: Callable[[str, str, str], str | None],
    previous: dict | None,
) -> dict:
    attempts = int((previous or {}).get("attempts") or 0) + 1
    now_fields = {
        "cik": filing.cik,
        "form": filing.form,
        "filed": filing.filed.isoformat(),
        "accepted": filing.accepted.isoformat() if filing.accepted else None,
        "attempts": attempts,
        "filingUrl": filing_url(filing.cik, filing.accn),
    }
    try:
        discovered = discover_earnings_exhibit(filing.cik, filing.accn, fetch, form=filing.form)
    except Exception as exc:  # noqa: BLE001
        log.warning("8-K discovery failed for %s: %s", filing.accn, exc)
        return {
            **now_fields,
            "status": "failed",
            "reason": "discovery_error",
            "lastError": str(exc)[:240],
        }
    if discovered.reason == "index_unavailable":
        return {
            **now_fields,
            "status": "failed",
            "reason": "index_unavailable",
            "item202": None,
            "lastError": "SEC filing index was not available",
        }
    if not discovered.item_202:
        return {
            **now_fields,
            "status": "not_earnings",
            "reason": discovered.reason or "not_item_202",
            "item202": False,
        }
    if discovered.exhibit is None:
        return {
            **now_fields,
            "status": "failed",
            "reason": discovered.reason or "no_earnings_exhibit",
            "item202": True,
            "lastError": discovered.reason,
        }
    html = fetch(filing.cik, filing.accn, discovered.exhibit.name)
    extracted = extract_earnings_release(
        html or "",
        item_202=True,
        exhibit_name=discovered.exhibit.name,
        exhibit_url=discovered.exhibit.url,
        filing_url=discovered.filing_url,
    )
    payload = {
        **now_fields,
        "status": extracted.status,
        "reason": extracted.reason,
        "item202": True,
        "exhibitName": extracted.exhibit_name,
        "exhibitUrl": extracted.exhibit_url,
        "fiscalYear": extracted.fiscal_year,
        "fiscalQuarter": extracted.fiscal_quarter,
        "periodEnd": extracted.period_end.isoformat() if extracted.period_end else None,
        "metrics": extracted.to_state_metrics(),
        "evidence": extracted.evidence[:40],
    }
    if extracted.status == "extracted":
        payload["extractedAt"] = (previous or {}).get("extractedAt")
    return payload


def run_earnings_extractions(
    jobs: list[DailyFiling],
    extractions: dict,
    *,
    sec=None,
    eight_k_documents: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict]:
    fetch = _injected_fetch(eight_k_documents) if eight_k_documents is not None else _client_fetch(sec)
    updated = dict(extractions)
    for filing in jobs:
        previous = updated.get(filing.accn) if isinstance(updated.get(filing.accn), dict) else None
        result = process_earnings_filing(filing, fetch, previous)
        updated[filing.accn] = result
        log.info(
            "8-K extract %s %s status=%s reason=%s",
            filing.cik,
            filing.accn,
            result.get("status"),
            result.get("reason"),
        )
    return updated


def extraction_rows_by_cik(extractions: dict) -> dict[str, list[dict[str, Any]]]:
    from .eight_k_layer3 import extraction_from_state

    grouped: dict[str, list[dict[str, Any]]] = {}
    for accn, row in extractions.items():
        extract = extraction_from_state(row)
        if extract is None:
            continue
        cik = str(row.get("cik") or "").zfill(10)
        grouped.setdefault(cik, []).append(
            {
                "accn": accn,
                "form": row.get("form") or "8-K",
                "filed": row.get("filed"),
                "extract": extract,
            }
        )
    for _cik, rows in grouped.items():
        rows.sort(key=lambda r: (str(r.get("filed") or ""), r["accn"]))
    return grouped


def mark_superseded(extractions: dict, accns: set[str]) -> dict:
    out = dict(extractions)
    for accn in accns:
        row = out.get(accn)
        if not isinstance(row, dict) or row.get("status") != "extracted":
            continue
        next_row = dict(row)
        next_row["status"] = "superseded"
        next_row["supersededReason"] = "company_facts_period_covered"
        out[accn] = next_row
    return out
