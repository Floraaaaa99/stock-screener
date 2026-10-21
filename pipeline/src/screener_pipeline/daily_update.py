"""Incremental daily refresh from SEC EDGAR master.idx.

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

import requests

from . import config
from .build import DatasetError, make_meta, rebuild_company
from .cache import read_json, write_json_if_changed
from .gate import evaluate_gate
from .layer2 import write_layer2
from .layer3_build import write_layer3
from .output import SCHEMA_VERSION, screener_row, sort_screener_rows
from .sec.client import SecClient, load_overrides
from .sec.daily_index import DailyFiling, collect_period_filings
from .sec.store import FactsStore, PeriodicStore, SicStore, StatementStore
from .universe.nasdaq_trader import Listing

log = logging.getLogger(__name__)

STATE_FILENAME = "daily-update.json"
STATE_SCHEMA_VERSION = 1
EXCHANGE_CODES = {"NASDAQ": "Q", "NYSE": "N", "NYSE American": "A"}


class DailyUpdateError(DatasetError):
    """Validation or dataset error. The previous live payload must stay in place."""


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


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
    return {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "lastSuccessfulAt": data.get("lastSuccessfulAt"),
        "asOf": data.get("asOf"),
        "lookbackDays": data.get("lookbackDays"),
        "processedAccessions": processed,
    }


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


def _fetch_companyfacts(sec: SecClient, cik: str, injected: dict[str, dict] | None) -> dict | None:
    if injected and cik in injected:
        return injected[cik]
    try:
        return sec.companyfacts(cik, force=not sec.offline)
    except FileNotFoundError:
        if sec.offline:
            return None
        raise


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
    companyfacts_by_cik: dict[str, dict] | None = None,
    state_dir: Path | None = None,
    cache_dir: Path | None = None,
) -> dict:
    """Apply new 10-Q/10-K accessions to the existing dataset.

    Universe membership is unchanged. CIKs not already in the dataset are skipped.
    On validation or HTTP failure the live directory is left untouched.
    """
    data_dir = Path(data_dir or config.OUTPUT_DIR)
    as_of = as_of or date.today()
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
    state_path = data_dir / STATE_FILENAME
    state = load_state(state_path)
    processed = dict(state["processedAccessions"])

    present: list[str] = []
    missing: list[str] = []
    if indexes is None:
        facts_store = FactsStore(state_dir / "facts")
        sec_probe = SecClient(
            cache_dir=cache_dir,
            offline=offline,
            facts_store=facts_store,
            statement_store=StatementStore(state_dir / "statements"),
            sic_store=SicStore(state_dir / "sic"),
            periodic_store=PeriodicStore(state_dir / "periodic"),
        )
        try:
            found, present, missing = collect_period_filings(
                sec_probe.http,
                as_of,
                lookback_days,
                cache_dir=(cache_dir or config.CACHE_DIR) / "sec" / "daily-index",
            )
        except requests.HTTPError as exc:
            raise DailyUpdateError(f"SEC daily index request failed; live dataset unchanged: {exc}") from exc
        filings = found
        sec = sec_probe
    else:
        filings = list(indexes)
        present = sorted({f.filed.isoformat() for f in filings})
        sec = SecClient(
            cache_dir=cache_dir,
            offline=offline or companyfacts_by_cik is not None,
            facts_store=FactsStore(state_dir / "facts"),
            statement_store=StatementStore(state_dir / "statements"),
            sic_store=SicStore(state_dir / "sic"),
            periodic_store=PeriodicStore(state_dir / "periodic"),
        )

    new_filings = [f for f in filings if f.accn not in processed]
    grouped: dict[str, list[DailyFiling]] = defaultdict(list)
    out_of_universe: list[dict] = []
    in_universe: dict[str, list[DailyFiling]] = {}
    for row in new_filings:
        grouped[row.cik].append(row)
    for cik, rows in grouped.items():
        if cik in by_cik:
            in_universe[cik] = rows
        else:
            out_of_universe.extend(r.to_dict() for r in rows)

    report: dict[str, Any] = {
        "ok": True,
        "published": False,
        "heldBack": None,
        "asOf": as_of.isoformat(),
        "lookbackDays": lookback_days,
        "generatedAt": None,
        "indexesFound": present,
        "indexesMissing": missing,
        "filingsSeen": len(filings),
        "filingsNew": len(new_filings),
        "outOfUniverse": len(out_of_universe),
        "companiesUpdated": [],
        "companiesSkipped": [],
        "filesRewritten": [],
        "layer3Updated": [],
        "gate": None,
        "dryRun": dry_run,
    }

    generated_at = _now_iso()
    daily_meta = {
        "lastSuccessfulAt": generated_at,
        "asOf": as_of.isoformat(),
        "lookbackDays": lookback_days,
        "companiesUpdated": 0,
        "filingsProcessed": 0,
        "outOfUniverse": len(out_of_universe),
    }

    if not in_universe:
        report["generatedAt"] = generated_at
        if publish_to_dest:
            _record_success(
                data_dir,
                processed,
                out_of_universe,
                [],
                generated_at,
                as_of,
                lookback_days,
                heartbeat_only=True,
                daily_meta=daily_meta,
            )
            report["published"] = True
            report["filesRewritten"] = [STATE_FILENAME, "meta.json"]
        elif is_live and not write_live:
            report["heldBack"] = "write_live_required"
        return report

    staging = data_dir.with_name(data_dir.name + ".daily-staging")
    try:
        copy_dataset(data_dir, staging)
        overrides = load_overrides()
        raw_facts: dict[str, dict] = {}
        updated_tickers: list[str] = []
        skipped_ciks: list[str] = []
        rebuilt_accessions: list[DailyFiling] = []

        for cik, rows in sorted(in_universe.items()):
            try:
                raw = _fetch_companyfacts(sec, cik, companyfacts_by_cik)
            except requests.HTTPError as exc:
                raise DailyUpdateError(
                    f"SEC Company Facts request failed for {cik}; live dataset unchanged: {exc}"
                ) from exc
            if raw is None:
                log.warning("No Company Facts for %s; skipping this CIK and retrying in the lookback window", cik)
                skipped_ciks.append(cik)
                continue
            sec.facts_store.put_raw(raw)
            raw_facts[cik] = raw
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
            rebuilt_accessions.extend(rows)

        if skipped_ciks and not rebuilt_accessions:
            raise DailyUpdateError(
                "Every affected CIK was missing Company Facts; live dataset unchanged"
            )

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
                "companiesUpdated": len(set(updated_tickers)),
                "filingsProcessed": len(rebuilt_accessions),
            },
        }
        meta = rebuild_aggregates(
            staging,
            list(companies_staging.values()),
            generated_at=generated_at,
            run=run,
            baseline=baseline,
        )
        layer3_updated: list[str] = []
        if update_layer3 and raw_facts and (staging / "layer3.json").exists():
            payload = write_layer3(
                staging,
                staging / "layer3.json",
                companyfacts_by_cik=raw_facts,
                ciks=list(raw_facts),
                mode="incremental",
                write_live=False,
            )
            layer3_updated = list(payload.get("updated") or [])
            bump_generated_at(staging / "layer3.json", generated_at)

        publish = publish_to_dest and (baseline.get("dataset") or {}).get("mode") == "full"
        gate = evaluate_gate(meta, baseline, publish=publish)
        meta["gate"] = gate.to_dict()
        write_json_if_changed(staging / "meta.json", meta)
        report["gate"] = gate.to_dict()
        report["companiesUpdated"] = updated_tickers
        report["companiesSkipped"] = skipped_ciks
        report["layer3Updated"] = layer3_updated
        report["generatedAt"] = generated_at

        if not gate.ok:
            raise DailyUpdateError("Validation gate failed; live dataset unchanged: " + ", ".join(gate.reasons))

        processed_rows = list(rebuilt_accessions)
        if publish_to_dest:
            _write_state(
                staging / STATE_FILENAME,
                processed,
                out_of_universe,
                processed_rows,
                generated_at,
                as_of,
                lookback_days,
            )
            sync_stats = sync_changed_files(staging, data_dir)
            report["filesRewritten"] = sync_stats["copied"]
            report["published"] = True
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
    processed: dict,
    out_of_universe: list[dict],
    rebuilt: list[DailyFiling],
    generated_at: str,
    as_of: date,
    lookback_days: int,
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
    payload = {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "lastSuccessfulAt": generated_at,
        "asOf": as_of.isoformat(),
        "lookbackDays": lookback_days,
        "processedAccessions": prune_processed(processed, as_of, config.DAILY_ACCESSION_KEEP_DAYS),
    }
    write_json_if_changed(path, payload)


def _record_success(
    data_dir: Path,
    processed: dict,
    out_of_universe: list[dict],
    rebuilt: list[DailyFiling],
    generated_at: str,
    as_of: date,
    lookback_days: int,
    *,
    heartbeat_only: bool,
    daily_meta: dict,
) -> None:
    _write_state(
        data_dir / STATE_FILENAME,
        processed,
        out_of_universe,
        rebuilt,
        generated_at,
        as_of,
        lookback_days,
    )
    meta = read_json(data_dir / "meta.json") or {}
    meta["generatedAt"] = generated_at
    meta["dailyUpdate"] = {**daily_meta, "heartbeat": heartbeat_only}
    if isinstance(meta.get("run"), dict):
        meta["run"] = {
            **meta["run"],
            "kind": "daily-incremental",
            "finishedAt": generated_at,
            "status": "complete",
        }
    write_json_if_changed(data_dir / "meta.json", meta)
