"""Incremental daily refresh from SEC Latest Filings plus EDGAR master.idx.

Does not expand the universe, download companyfacts.zip, or replace a live
dataset that fails validation. Missing financial values stay missing.
"""

from __future__ import annotations

import logging
import shutil
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from . import config
from .build import DatasetError, make_meta, rebuild_company
from .cache import read_json, write_json_if_changed
from .gate import evaluate_gate
from .layer2 import write_layer2
from .layer3_build import write_layer3
from .output import SCHEMA_VERSION, screener_row, sort_screener_rows
from .sec.client import SecClient, load_overrides
from .sec.daily_index import DailyFiling, collect_period_filings, recent_business_days
from .sec.facts import CURRENT_REPORT_FORMS, DOMESTIC_FORMS, INDEX_RECONCILE_FORMS
from .sec.latest_filings import fetch_latest_filings
from .sec.store import FactsStore, PeriodicStore, SicStore, StatementStore
from .universe.nasdaq_trader import Listing

log = logging.getLogger(__name__)

STATE_FILENAME = "daily-update.json"
STATE_SCHEMA_VERSION = 2
EXCHANGE_CODES = {"NASDAQ": "Q", "NYSE": "N", "NYSE American": "A"}


class DailyUpdateError(DatasetError):
    """Validation or dataset error. The previous live payload must stay in place."""


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def pacific_today(now: datetime | None = None) -> date:
    """Calendar date in America/Los_Angeles. Does not use the runner's UTC date."""
    tz = ZoneInfo(config.DAILY_AS_OF_TZ)
    current = datetime.now(tz) if now is None else now
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(tz).date()


def listing_from_company(company: dict) -> Listing:
    exchange = company.get("exchange") or "NASDAQ"
    return Listing(
        symbol=company["ticker"],
        raw_symbol=company["ticker"],
        name=company.get("name") or company["ticker"],
        exchange=exchange,
        exchange_code=EXCHANGE_CODES.get(exchange, "Q"),
        security_type=company.get("securityType") or "common",
        nasdaq_tier=None,
        financial_status=None,
    )


def load_companies(data_dir: Path) -> dict[str, dict]:
    companies_dir = data_dir / "companies"
    out: dict[str, dict] = {}
    if not companies_dir.is_dir():
        return out
    for path in sorted(companies_dir.glob("*.json")):
        company = read_json(path)
        if not isinstance(company, dict):
            continue
        ticker = company.get("ticker") or path.stem
        out[ticker] = company
    return out


def cik_to_tickers(data_dir: Path, companies: dict[str, dict] | None = None) -> dict[str, list[str]]:
    """Map issuer CIK → listing tickers from issuers.json and company JSON. Does not remap CIKs."""
    mapping: dict[str, list[str]] = defaultdict(list)
    issuers = read_json(data_dir / "issuers.json", default={"byTicker": {}}) or {}
    for ticker, cik in (issuers.get("byTicker") or {}).items():
        if not cik or not ticker:
            continue
        key = str(cik).zfill(10)
        if ticker not in mapping[key]:
            mapping[key].append(ticker)
    for ticker, company in (companies or load_companies(data_dir)).items():
        cik = company.get("cik")
        if not cik:
            continue
        key = str(cik).zfill(10)
        if ticker not in mapping[key]:
            mapping[key].append(ticker)
    return dict(mapping)


def load_state(path: Path) -> dict:
    data = read_json(path, default={}) or {}
    processed = data.get("processedAccessions")
    if not isinstance(processed, dict):
        processed = {}
    unresolved = data.get("unreconciledDates") or data.get("unresolvedDates") or []
    if not isinstance(unresolved, list):
        unresolved = []
    return {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "lastSuccessfulSyncAt": data.get("lastSuccessfulSyncAt") or data.get("lastSuccessfulAt"),
        "lastFinancialUpdateAt": data.get("lastFinancialUpdateAt"),
        "asOf": data.get("asOf"),
        "lookbackDays": data.get("lookbackDays"),
        "unreconciledDates": [str(x) for x in unresolved],
        "processedAccessions": processed,
    }


def parse_sync_at(raw: object) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(text[:10]), datetime.min.time(), tzinfo=UTC)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def discovery_since(as_of: date, last_sync: datetime | None, lookback_days: int, overlap_hours: int) -> date:
    """Start of the index window: lookback, or the missed period plus overlap — whichever is earlier."""
    floor = as_of - timedelta(days=lookback_days - 1)
    if last_sync is None:
        return floor
    recovered = (last_sync.astimezone(UTC) - timedelta(hours=overlap_hours)).date()
    return min(floor, recovered)


def prune_processed(processed: dict, as_of: date, keep_days: int) -> dict:
    cutoff = as_of - timedelta(days=keep_days)
    kept: dict[str, dict] = {}
    for accn, row in processed.items():
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


def copy_dataset(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("*.tmp", ".*.tmp", "__pycache__"))


def iter_files(root: Path) -> list[Path]:
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())


def files_identical(left: Path, right: Path) -> bool:
    if not left.exists() or not right.exists():
        return False
    if left.stat().st_size != right.stat().st_size:
        return False
    return left.read_bytes() == right.read_bytes()


def sync_changed_files(src: Path, dest: Path) -> dict:
    """Copy files from src when bytes differ. Never deletes extra files in dest."""
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    skipped = 0
    for rel in iter_files(src):
        source = src / rel
        target = dest / rel
        if files_identical(source, target):
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(rel.as_posix())
    dest_only = 0
    src_set = {p.as_posix() for p in iter_files(src)}
    for rel in iter_files(dest):
        if rel.as_posix() not in src_set:
            dest_only += 1
    return {"copied": copied, "skipped": skipped, "destOnlyPreserved": dest_only}


def rebuild_aggregates(
    data_dir: Path,
    companies: list[dict],
    *,
    generated_at: str,
    run: dict,
    baseline: dict | None,
) -> dict:
    old = read_json(data_dir / "meta.json") or {}
    rows = sort_screener_rows([screener_row(c) for c in companies])
    issues = [issue for c in companies for issue in (c.get("classificationIssues") or [])]
    started = run.get("startedAt") or generated_at
    file_times = (old.get("universe") or {}).get("fileCreated") or {}
    meta = make_meta(old.get("dataset") or {}, companies, [], [], file_times, started, run, baseline)
    meta["generatedAt"] = generated_at
    meta["buildStartedAt"] = old.get("buildStartedAt") or started
    if old.get("universe"):
        meta["universe"] = old["universe"]
    sources = old.get("sources") or {}
    if sources.get("nasdaqTrader"):
        meta["sources"]["nasdaqTrader"] = sources["nasdaqTrader"]
    if sources.get("sec"):
        sec_src = dict(sources["sec"])
        sec_src["latestFilingDate"] = (meta.get("sources") or {}).get("sec", {}).get("latestFilingDate")
        meta["sources"]["sec"] = sec_src
    if run.get("dailyUpdate"):
        meta["dailyUpdate"] = run["dailyUpdate"]
    write_json_if_changed(
        data_dir / "screener.json",
        {"schemaVersion": SCHEMA_VERSION, "generatedAt": generated_at, "rows": rows},
        compact=True,
    )
    write_json_if_changed(
        data_dir / "classification_issues.json",
        {"generatedAt": generated_at, "issues": issues},
    )
    write_json_if_changed(data_dir / "meta.json", meta)
    write_layer2(data_dir)
    return read_json(data_dir / "meta.json") or meta


def bump_generated_at(path: Path, generated_at: str) -> bool:
    data = read_json(path)
    if not isinstance(data, dict):
        return False
    data["generatedAt"] = generated_at
    compact = path.name in {"screener.json", "layer3.json"}
    return write_json_if_changed(path, data, compact=compact)


def _assert_no_zero_filled_missing(company: dict) -> None:
    """Safety net: a missing quarter must stay null, never 0."""
    for metric in ("revenue", "earnings"):
        payload = company.get(metric) or {}
        for quarter in payload.get("quarters") or []:
            if quarter.get("missing") and quarter.get("value") not in (None,):
                raise DailyUpdateError(
                    f"{company.get('ticker')}: missing {metric} quarter {quarter.get('end')} "
                    f"has value {quarter.get('value')!r}; missing must stay null"
                )


def accessions_in_companyfacts(raw: dict) -> set[str]:
    found: set[str] = set()
    for taxonomy in (raw.get("facts") or {}).values():
        if not isinstance(taxonomy, dict):
            continue
        for concept in taxonomy.values():
            if not isinstance(concept, dict):
                continue
            for unit_facts in (concept.get("units") or {}).values():
                if not isinstance(unit_facts, list):
                    continue
                for fact in unit_facts:
                    if isinstance(fact, dict) and fact.get("accn"):
                        found.add(str(fact["accn"]))
    return found


def _facts_cover_accessions(sec: SecClient, cik: str, accns: list[str]) -> bool:
    if not accns:
        return False
    have: set[str] = set()
    cached = sec.facts_store.get(cik)
    if cached is not None:
        have.update(cached.filings)
    earnings = sec.facts_store.get_earnings(cik)
    if earnings is not None:
        have.update(earnings.filings)
    return all(accn in have for accn in accns)


def _fetch_companyfacts(
    sec: SecClient,
    cik: str,
    injected: dict[str, dict] | None,
    *,
    accns: list[str],
) -> dict | None:
    if injected and cik in injected:
        return injected[cik]
    force = not sec.offline and not _facts_cover_accessions(sec, cik, accns)
    try:
        return sec.companyfacts(cik, force=force)
    except FileNotFoundError:
        if sec.offline:
            return None
        raise


def merge_filings(*groups: list[DailyFiling]) -> list[DailyFiling]:
    seen: set[str] = set()
    out: list[DailyFiling] = []
    for group in groups:
        for row in group:
            if row.accn in seen:
                continue
            seen.add(row.accn)
            out.append(row)
    return out


def is_periodic(form: str) -> bool:
    return form in DOMESTIC_FORMS


def is_current_report(form: str) -> bool:
    return form in CURRENT_REPORT_FORMS


def parse_rebuild_tickers(raw: str | list[str] | None) -> list[str]:
    """Normalize a manual rebuild list. Empty input means incremental discovery only."""
    if not raw:
        return []
    parts = raw.replace(",", " ").split() if isinstance(raw, str) else [str(item) for item in raw]
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        ticker = part.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append(ticker)
    return out


def resolve_rebuild_tickers(
    tickers: list[str],
    companies: dict[str, dict],
    by_cik: dict[str, list[str]],
) -> tuple[dict[str, list[str]], list[str]]:
    """Map in-universe tickers to CIKs. Unknown symbols are not added to the dataset."""
    ticker_to_cik: dict[str, str] = {}
    for cik, symbols in by_cik.items():
        for symbol in symbols:
            ticker_to_cik[str(symbol).upper()] = str(cik).zfill(10)
    for symbol, company in companies.items():
        cik = company.get("cik")
        if cik:
            ticker_to_cik.setdefault(str(symbol).upper(), str(cik).zfill(10))
    resolved: dict[str, list[str]] = {}
    unknown: list[str] = []
    for ticker in tickers:
        cik = ticker_to_cik.get(ticker)
        if not cik:
            unknown.append(ticker)
            continue
        actual = next((symbol for symbol in by_cik.get(cik, []) if str(symbol).upper() == ticker), ticker)
        resolved.setdefault(cik, [])
        if actual not in resolved[cik]:
            resolved[cik].append(actual)
    return resolved, unknown


def run_daily_update(
    data_dir: Path | None = None,
    *,
    lookback_days: int | None = None,
    as_of: date | None = None,
    dry_run: bool = False,
    offline: bool = False,
    verify_quarters: bool = True,
    update_layer3: bool = True,
    write: bool = True,
    write_live: bool = False,
    indexes: list[DailyFiling] | None = None,
    latest_filings: list[DailyFiling] | None = None,
    companyfacts_by_cik: dict[str, dict] | None = None,
    state_dir: Path | None = None,
    cache_dir: Path | None = None,
    rebuild_tickers: str | list[str] | None = None,
) -> dict:
    """Apply new 10-Q/10-K accessions to the existing dataset.

    Universe membership is unchanged. CIKs not already in the dataset are skipped.
    On validation or HTTP failure the live directory is left untouched.
    """
    data_dir = Path(data_dir or config.OUTPUT_DIR)
    as_of = as_of or pacific_today()
    lookback_days = config.DAILY_LOOKBACK_DAYS if lookback_days is None else lookback_days
    state_dir = Path(state_dir or config.STATE_DIR)
    started = _now_iso()
    is_live = data_dir.resolve() == config.OUTPUT_DIR.resolve()
    publish_to_dest = write and not dry_run and (write_live or not is_live)

    if not (data_dir / "meta.json").exists() or not (data_dir / "companies").is_dir():
        raise DailyUpdateError(f"No dataset to update in {data_dir}")

    baseline = read_json(data_dir / "meta.json") or {}
    companies_live = load_companies(data_dir)
    by_cik = cik_to_tickers(data_dir, companies_live)
    wanted_tickers = parse_rebuild_tickers(rebuild_tickers)
    force_by_cik, unknown_tickers = resolve_rebuild_tickers(wanted_tickers, companies_live, by_cik)
    state_path = data_dir / STATE_FILENAME
    state = load_state(state_path)
    processed = dict(state["processedAccessions"])
    last_sync = parse_sync_at(state.get("lastSuccessfulSyncAt"))
    overlap_hours = config.DAILY_OVERLAP_HOURS
    since = discovery_since(as_of, last_sync, lookback_days, overlap_hours)
    extra_dates = []
    for raw in state.get("unreconciledDates") or []:
        try:
            extra_dates.append(date.fromisoformat(str(raw)))
        except ValueError:
            continue

    present: list[str] = []
    unreconciled: list[str] = []
    latest_stats: dict = {}
    injected = indexes is not None or latest_filings is not None
    sec = SecClient(
        cache_dir=cache_dir,
        offline=offline or (injected and companyfacts_by_cik is not None),
        facts_store=FactsStore(state_dir / "facts"),
        statement_store=StatementStore(state_dir / "statements"),
        sic_store=SicStore(state_dir / "sic"),
        periodic_store=PeriodicStore(state_dir / "periodic"),
    )
    if not injected:
        try:
            latest_rows, latest_stats = fetch_latest_filings(sec.http)
            index_rows, present, unreconciled = collect_period_filings(
                sec.http,
                as_of,
                lookback_days,
                cache_dir=(cache_dir or config.CACHE_DIR) / "sec" / "daily-index",
                forms=set(INDEX_RECONCILE_FORMS),
                since=since,
                extra_dates=extra_dates,
                revalidate_business_days=config.DAILY_INDEX_REVALIDATE_BUSINESS_DAYS,
            )
        except requests.HTTPError as exc:
            raise DailyUpdateError(f"SEC discovery request failed; live dataset unchanged: {exc}") from exc
        filings = merge_filings(latest_rows, index_rows)
    else:
        filings = merge_filings(latest_filings or [], indexes or [])
        present = sorted({f.filed.isoformat() for f in (indexes or [])})
        recent = set(recent_business_days(as_of, config.DAILY_INDEX_REVALIDATE_BUSINESS_DAYS))
        unreconciled = [d.isoformat() for d in extra_dates if d in recent]
        latest_stats = {"pages": 0, "hits": len(latest_filings or []), "injected": True}

    new_filings = [f for f in filings if f.accn not in processed]
    grouped: dict[str, list[DailyFiling]] = defaultdict(list)
    out_of_universe: list[dict] = []
    recorded_current: list[DailyFiling] = []
    in_universe: dict[str, list[DailyFiling]] = {}
    skipped_filings: list[dict] = []
    for row in new_filings:
        grouped[row.cik].append(row)
    for cik, rows in grouped.items():
        if cik not in by_cik:
            out_of_universe.extend(r.to_dict() for r in rows)
            continue
        periodic = [r for r in rows if is_periodic(r.form)]
        current = [r for r in rows if is_current_report(r.form)]
        other = [r for r in rows if not is_periodic(r.form) and not is_current_report(r.form)]
        if periodic:
            in_universe[cik] = periodic
        recorded_current.extend(current)
        skipped_filings.extend(r.to_dict() | {"reason": "unsupported_form"} for r in other)

    report: dict[str, Any] = {
        "ok": True,
        "published": False,
        "heldBack": None,
        "asOf": as_of.isoformat(),
        "lookbackDays": lookback_days,
        "syncFrom": since.isoformat(),
        "lastSuccessfulSyncAt": state.get("lastSuccessfulSyncAt"),
        "lastFinancialUpdateAt": state.get("lastFinancialUpdateAt") or baseline.get("generatedAt"),
        "generatedAt": baseline.get("generatedAt"),
        "indexesFound": present,
        "unresolvedDates": unreconciled,
        "latestFilings": latest_stats,
        "filingsSeen": len(filings),
        "filingsNew": len(new_filings),
        "filingsRecorded8k": 0,
        "outOfUniverse": len(out_of_universe),
        "companiesUpdated": [],
        "companiesSkipped": [],
        "skippedFilings": skipped_filings,
        "filesRewritten": [],
        "layer3Updated": [],
        "errors": [f"unknown_ticker:{ticker}" for ticker in unknown_tickers],
        "gate": None,
        "dryRun": dry_run,
        "unchanged": False,
        "stateUpdated": False,
        "checkpointAdvanced": False,
        "rebuildTickers": wanted_tickers,
        "rebuildUnknown": unknown_tickers,
    }

    generated_at = _now_iso()
    daily_meta = {
        "lastSuccessfulSyncAt": state.get("lastSuccessfulSyncAt"),
        "lastFinancialUpdateAt": state.get("lastFinancialUpdateAt") or baseline.get("generatedAt"),
        "asOf": as_of.isoformat(),
        "lookbackDays": lookback_days,
        "companiesUpdated": 0,
        "filingsProcessed": 0,
        "outOfUniverse": len(out_of_universe),
    }

    processing_complete = True
    if not in_universe and not force_by_cik:
        report["unchanged"] = True
        report["filingsRecorded8k"] = len(recorded_current)
        if publish_to_dest:
            _write_state(
                data_dir / STATE_FILENAME,
                state,
                processed,
                out_of_universe,
                [],
                recorded_current,
                generated_at,
                as_of,
                lookback_days,
                unreconciled=unreconciled,
                advance_sync=processing_complete,
                financial_at=state.get("lastFinancialUpdateAt"),
            )
            report["stateUpdated"] = True
            report["checkpointAdvanced"] = processing_complete
            report["lastSuccessfulSyncAt"] = generated_at if processing_complete else state.get("lastSuccessfulSyncAt")
            report["filesRewritten"] = [STATE_FILENAME]
        elif is_live and not write_live:
            report["heldBack"] = "write_live_required"
        log.info(
            "daily-update: seen=%s new=%s 8k=%s out=%s unresolved=%s companies=0",
            len(filings),
            len(new_filings),
            len(recorded_current),
            len(out_of_universe),
            unreconciled,
        )
        return report

    staging = data_dir.with_name(data_dir.name + ".daily-staging")
    try:
        copy_dataset(data_dir, staging)
        overrides = load_overrides()
        raw_facts: dict[str, dict] = {}
        updated_tickers: list[str] = []
        skipped_ciks: list[str] = []
        rebuilt_accessions: list[DailyFiling] = []
        facts_lag = False

        for cik in sorted(set(in_universe) | set(force_by_cik)):
            rows = list(in_universe.get(cik, []))
            accns = [r.accn for r in rows]
            try:
                raw = _fetch_companyfacts(sec, cik, companyfacts_by_cik, accns=accns)
            except requests.HTTPError as exc:
                raise DailyUpdateError(
                    f"SEC Company Facts request failed for {cik}; live dataset unchanged: {exc}"
                ) from exc
            if raw is None:
                log.warning("No Company Facts for %s; skipping this CIK and retrying in the lookback window", cik)
                skipped_ciks.append(cik)
                skipped_filings.extend(r.to_dict() | {"reason": "company_facts_unavailable"} for r in rows)
                continue
            covered = accessions_in_companyfacts(raw)
            sec.facts_store.put_raw(raw)
            raw_facts[cik] = raw
            changed_here = False
            for ticker in by_cik[cik]:
                previous = companies_live.get(ticker) or read_json(staging / "companies" / f"{ticker}.json")
                if not previous:
                    log.warning("Ticker %s mapped to %s but has no company JSON; skipping", ticker, cik)
                    continue
                listing = listing_from_company(previous)
                rec = {"cik": int(cik), "name": previous.get("secName") or previous.get("name")}
                rebuilt = rebuild_company(
                    listing,
                    cik,
                    rec,
                    sec,
                    overrides,
                    as_of=as_of,
                    verify_quarters=verify_quarters,
                    offline=offline or companyfacts_by_cik is not None,
                    refresh_filings=True,
                )
                _assert_no_zero_filled_missing(rebuilt)
                dest = staging / "companies" / f"{ticker}.json"
                if write_json_if_changed(dest, rebuilt):
                    updated_tickers.append(ticker)
                    changed_here = True
            applied_here: list[DailyFiling] = []
            any_covered = any(row.accn in covered for row in rows)
            for row in rows:
                if row.accn in covered:
                    applied_here.append(row)
                    continue
                if offline and changed_here and not any_covered:
                    # Offline tests use synthetic accession numbers. Production
                    # never applies an accession that is absent from Company Facts.
                    applied_here.append(row)
                    continue
                facts_lag = True
                skipped_filings.append(row.to_dict() | {"reason": "company_facts_lag"})
                log.warning("Company Facts for %s do not yet include %s; will retry", cik, row.accn)
            rebuilt_accessions.extend(applied_here)
            if rows and not applied_here:
                skipped_ciks.append(cik)

        if skipped_ciks and not rebuilt_accessions:
            raise DailyUpdateError(
                "Every affected CIK was missing Company Facts or still lagging; live dataset unchanged"
            )
        processing_complete = not skipped_ciks and not facts_lag
        report["filingsRecorded8k"] = len(recorded_current)
        report["skippedFilings"] = skipped_filings
        report["errors"] = [
            *report["errors"],
            *[f"company_facts_unavailable:{cik}" for cik in skipped_ciks],
        ]
        if facts_lag:
            report["errors"] = [*report["errors"], "company_facts_lag"]

        layer3_updated: list[str] = []
        if update_layer3 and raw_facts and (staging / "layer3.json").exists():
            index_backup = (staging / "layer3.json").read_bytes()
            payload = write_layer3(
                staging,
                staging / "layer3.json",
                companyfacts_by_cik=raw_facts,
                ciks=list(raw_facts),
                mode="incremental",
                write_live=False,
            )
            for cik in payload.get("updated") or []:
                rel = Path("layer3") / "cik" / f"{str(cik).zfill(10)}.json"
                if not files_identical(staging / rel, data_dir / rel):
                    layer3_updated.append(cik)
            if not layer3_updated:
                (staging / "layer3.json").write_bytes(index_backup)

        report["companiesUpdated"] = updated_tickers
        report["companiesSkipped"] = skipped_ciks
        report["layer3Updated"] = layer3_updated
        report["generatedAt"] = generated_at

        if not updated_tickers and not layer3_updated:
            report["unchanged"] = True
            report["generatedAt"] = baseline.get("generatedAt")
            if publish_to_dest:
                _write_state(
                    data_dir / STATE_FILENAME,
                    state,
                    processed,
                    out_of_universe,
                    rebuilt_accessions,
                    recorded_current,
                    generated_at,
                    as_of,
                    lookback_days,
                    unreconciled=unreconciled,
                    advance_sync=processing_complete,
                    financial_at=state.get("lastFinancialUpdateAt"),
                )
                report["stateUpdated"] = True
                report["checkpointAdvanced"] = processing_complete
                report["filesRewritten"] = [STATE_FILENAME]
            elif is_live and not write_live:
                report["heldBack"] = "write_live_required"
            else:
                report["heldBack"] = "dry_run"
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            return report

        companies_staging = load_companies(staging)
        run = {
            "status": "complete",
            "kind": "daily-incremental",
            "startedAt": started,
            "finishedAt": generated_at,
            "listingsTarget": (baseline.get("run") or {}).get("listingsTarget") or len(companies_staging),
            "listingsDone": len(companies_staging),
            "pending": [],
            "companiesUpdated": updated_tickers,
            "dailyUpdate": {
                **daily_meta,
                "lastSuccessfulSyncAt": generated_at if processing_complete else state.get("lastSuccessfulSyncAt"),
                "lastFinancialUpdateAt": generated_at,
                "companiesUpdated": len(set(updated_tickers)),
                "filingsProcessed": len(rebuilt_accessions),
            },
        }
        if updated_tickers:
            meta = rebuild_aggregates(
                staging,
                list(companies_staging.values()),
                generated_at=generated_at,
                run=run,
                baseline=baseline,
            )
        else:
            meta = read_json(staging / "meta.json") or {}
            meta["generatedAt"] = generated_at
            meta["dailyUpdate"] = run["dailyUpdate"]
            write_json_if_changed(staging / "meta.json", meta)
        if layer3_updated:
            bump_generated_at(staging / "layer3.json", generated_at)

        publish = publish_to_dest and (baseline.get("dataset") or {}).get("mode") == "full"
        gate = evaluate_gate(meta, baseline, publish=publish)
        meta["gate"] = gate.to_dict()
        write_json_if_changed(staging / "meta.json", meta)
        report["gate"] = gate.to_dict()

        if not gate.ok:
            raise DailyUpdateError("Validation gate failed; live dataset unchanged: " + ", ".join(gate.reasons))

        processed_rows = list(rebuilt_accessions)
        if publish_to_dest:
            _write_state(
                staging / STATE_FILENAME,
                state,
                processed,
                out_of_universe,
                processed_rows,
                recorded_current,
                generated_at,
                as_of,
                lookback_days,
                unreconciled=unreconciled,
                advance_sync=processing_complete,
                financial_at=generated_at,
            )
            sync_stats = sync_changed_files(staging, data_dir)
            report["filesRewritten"] = sync_stats["copied"]
            report["published"] = True
            report["checkpointAdvanced"] = processing_complete
            report["lastSuccessfulSyncAt"] = generated_at if processing_complete else state.get("lastSuccessfulSyncAt")
            report["lastFinancialUpdateAt"] = generated_at
            report["generatedAt"] = generated_at
        else:
            report["heldBack"] = "write_live_required" if is_live and not write_live else "dry_run"
            report["filesRewritten"] = [
                p.as_posix()
                for p in iter_files(staging)
                if not files_identical(staging / p, data_dir / p)
            ]
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    else:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return report


def _write_state(
    path: Path,
    previous: dict,
    processed: dict,
    out_of_universe: list[dict],
    rebuilt: list[DailyFiling],
    recorded_current: list[DailyFiling],
    generated_at: str,
    as_of: date,
    lookback_days: int,
    *,
    unreconciled: list[str],
    advance_sync: bool,
    financial_at: str | None,
) -> None:
    now = generated_at
    for row in out_of_universe:
        processed[row["accn"]] = {
            "cik": row["cik"],
            "form": row["form"],
            "filed": row["filed"],
            "processedAt": now,
            "status": "out_of_universe",
        }
    for filing in rebuilt:
        processed[filing.accn] = {
            "cik": filing.cik,
            "form": filing.form,
            "filed": filing.filed.isoformat(),
            "processedAt": now,
            "status": "applied",
        }
    for filing in recorded_current:
        processed[filing.accn] = {
            "cik": filing.cik,
            "form": filing.form,
            "filed": filing.filed.isoformat(),
            "accepted": filing.accepted.isoformat() if filing.accepted else None,
            "processedAt": now,
            "status": "recorded_8k",
        }
    payload = {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "lastSuccessfulSyncAt": generated_at if advance_sync else previous.get("lastSuccessfulSyncAt"),
        "lastFinancialUpdateAt": financial_at or previous.get("lastFinancialUpdateAt"),
        "asOf": as_of.isoformat(),
        "lookbackDays": lookback_days,
        "unreconciledDates": sorted(unreconciled),
        "processedAccessions": prune_processed(processed, as_of, config.DAILY_ACCESSION_KEEP_DAYS),
    }
    write_json_if_changed(path, payload)
