"""Build the static dataset: NASDAQ Trader universe + SEC revenue and SIC."""

from __future__ import annotations

import logging
import shutil
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from . import config
from .cache import read_json, write_json_atomic
from .gate import evaluate_gate
from .layer2 import write_layer2
from .output import SCHEMA_VERSION, company_json, screener_row, sort_screener_rows
from .revenue import EARNINGS_SPEC, analyze_company
from .sec.bulk import (
    download_companyfacts_zip,
    download_submissions_zip,
    extract_compact_facts,
    extract_compact_sic,
    zip_info,
)
from .sec.client import SecClient, load_overrides
from .sec.edgar import (
    facts_may_lag,
    latest_facts_period_end,
    newer_filings,
    supplement_earnings_facts,
    supplement_revenue_facts,
)
from .sec.sic import SicInfo
from .sec.store import FactsStore, PeriodicStore, SicStore, StatementStore
from .universe.fetch import load_universe
from .universe.nasdaq_trader import Listing

log = logging.getLogger(__name__)


class DatasetError(RuntimeError):
    pass


class IncompleteRun(DatasetError):
    """The run hit its time budget. State was saved; the live dataset was not replaced."""


def read_sample(name: str) -> tuple[list[str], dict]:
    path = config.SAMPLES_DIR / f"{name}.txt"
    if not path.exists():
        raise DatasetError(f"Sample list {path} not found")
    tickers: list[str] = []
    meta: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#:"):
            k, _, v = line[2:].partition("=")
            meta[k.strip()] = v.strip()
        elif line and not line.startswith("#"):
            tickers.append(line.split()[0].upper())
    return tickers, meta


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def build(
    universe: str,
    *,
    offline: bool = False,
    verify_quarters: bool = True,
    output_dir: Path | None = None,
    state_dir: Path | None = None,
    limit: int | None = None,
    time_budget_s: float | None = None,
    resume: bool = True,
    use_bulk: bool | None = None,
    write_live: bool = False,
) -> dict:
    output_dir = output_dir or config.OUTPUT_DIR
    state_dir = state_dir or config.STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    started = _now_iso()
    deadline = (time.monotonic() + time_budget_s) if time_budget_s is not None else None

    listings_all, exclusions, file_times = load_universe(offline=offline)
    by_symbol = {x.symbol: x for x in listings_all}

    if universe.startswith("sample:"):
        sample_name = universe.split(":", 1)[1]
        tickers, sample_meta = read_sample(sample_name)
        missing = [t for t in tickers if t not in by_symbol]
        if missing:
            excluded = {e.symbol: e.reason for e in exclusions}
            detail = ", ".join(f"{t} ({excluded.get(t, 'not listed')})" for t in missing)
            raise DatasetError(f"Sample tickers not eligible in the NASDAQ Trader universe: {detail}")
        listings: list[Listing] = [by_symbol[t] for t in tickers]
        dataset = {
            "mode": "sample",
            "id": sample_name,
            "name": sample_meta.get("name", sample_name),
            "description": sample_meta.get("description", ""),
        }
    elif universe == "full":
        listings = list(listings_all)
        dataset = {
            "mode": "full",
            "id": "us-listed",
            "name": "U.S. listed common stocks and ADRs",
            "description": (
                "Every eligible NASDAQ, NYSE and NYSE American listing from NASDAQ Trader. "
                "Listings without quarterly revenue stay in the table as N/A."
            ),
        }
    else:
        raise DatasetError(f"Unknown universe {universe!r}")

    if limit is not None:
        listings = listings[:limit]
        dataset = {
            **dataset,
            "mode": "partial",
            "id": f"{dataset.get('id')}-limit{limit}",
            "name": f"{dataset.get('name')} (first {limit} listings)",
            "description": f"Partial run of {limit} listings; cannot be published as the full universe.",
        }

    facts_store = FactsStore(state_dir / "facts")
    statement_store = StatementStore(state_dir / "statements")
    sic_store = SicStore(state_dir / "sic")
    periodic_store = PeriodicStore(state_dir / "periodic")
    sec = SecClient(
        offline=offline,
        facts_store=facts_store,
        statement_store=statement_store,
        sic_store=sic_store,
        periodic_store=periodic_store,
    )
    ticker_map = sec.ticker_map()
    overrides = load_overrides()

    cik_by_ticker: dict[str, str | None] = {}
    rec_by_ticker: dict[str, dict | None] = {}
    needed_ciks: list[str] = []
    for listing in listings:
        rec = SecClient.lookup_cik(ticker_map, listing.symbol)
        rec_by_ticker[listing.symbol] = rec
        cik = str(rec["cik"]).zfill(10) if rec else None
        cik_by_ticker[listing.symbol] = cik
        if cik:
            needed_ciks.append(cik)

    bulk_meta: dict | None = None
    should_bulk = use_bulk if use_bulk is not None else universe == "full"
    if should_bulk and needed_ciks:
        facts_zip = config.CACHE_DIR / "sec" / "bulk" / "companyfacts.zip"
        sic_zip = config.CACHE_DIR / "sec" / "bulk" / "submissions.zip"
        download_companyfacts_zip(sec.http, facts_zip, offline=offline)
        extract_compact_facts(facts_zip, needed_ciks, facts_store.directory)
        try:
            download_submissions_zip(sec.http, sic_zip, offline=offline)
            extract_compact_sic(
                sic_zip, needed_ciks, sic_store.directory, periodic_dir=periodic_store.directory
            )
        except FileNotFoundError:
            log.warning("submissions.zip unavailable; SIC will use the per-CIK API")
        bulk_meta = {
            "companyfacts": zip_info(facts_zip, config.SEC_COMPANYFACTS_ZIP_URL),
            "submissions": zip_info(sic_zip, config.SEC_SUBMISSIONS_ZIP_URL) if sic_zip.exists() else None,
        }

    progress_path = state_dir / "progress.json"
    progress = read_json(progress_path, default={}) or {}
    processed: dict[str, dict] = dict(progress.get("processed") or {}) if resume else {}

    companies: list[dict] = []
    issues_all: list[dict] = []
    pending: list[str] = []
    timed_out = False
    as_of = date.today()
    for listing in listings:
        if deadline is not None and time.monotonic() >= deadline:
            timed_out = True
            done = {c["ticker"] for c in companies}
            pending = [x.symbol for x in listings if x.symbol not in done]
            log.warning("Time budget reached after %d companies; %d pending", len(companies), len(pending))
            break
        cik = cik_by_ticker[listing.symbol]
        rec = rec_by_ticker[listing.symbol]
        c = rebuild_company(
            listing,
            cik,
            rec,
            sec,
            overrides,
            as_of=as_of,
            verify_quarters=verify_quarters,
            offline=offline,
        )
        companies.append(c)
        issues_all.extend(c.get("classificationIssues") or [])
        facts_hash = facts_store.hash_of(cik) if cik else None
        processed[listing.symbol] = {
            "cik": cik,
            "factsHash": facts_hash,
            "sic": ((c.get("sic") or {}).get("code")),
            "status": (c.get("revenue") or {}).get("status") or c["ttm"]["reason"],
            "doneAt": _now_iso(),
        }

    status = "complete" if not timed_out else "incomplete"
    run = {
        "status": status,
        "startedAt": started,
        "finishedAt": _now_iso(),
        "listingsTarget": len(listings),
        "listingsDone": len(companies),
        "pending": pending,
        "timeBudgetS": time_budget_s,
        "bulk": bulk_meta,
    }
    write_json_atomic(progress_path, {"processed": processed, "run": run, "dataset": dataset})

    rows = sort_screener_rows([screener_row(c) for c in companies])
    meta = make_meta(dataset, companies, listings_all, exclusions, file_times, started, run)

    if timed_out:
        staging = state_dir / "dataset-incomplete"
        write_dataset(staging, meta, rows, companies, issues_all)
        raise IncompleteRun(
            f"Time budget reached: processed {len(companies)} of {len(listings)} listings. "
            "State was saved; the live dataset was not replaced."
        )

    hold_live = dataset["mode"] != "sample" and output_dir.resolve() == config.OUTPUT_DIR.resolve()
    if hold_live and not (write_live and meta.get("gate", {}).get("ok")):
        staging = state_dir / f"dataset-{dataset['mode']}"
        write_dataset(staging, meta, rows, companies, issues_all)
        meta["run"]["publishedTo"] = str(staging)
        meta["run"]["heldBack"] = "awaiting_full_universe_validation"
        write_json_atomic(staging / "meta.json", meta)
        log.warning("%s dataset written to %s; live Pages payload unchanged.", dataset["mode"], staging)
        return meta

    write_dataset(output_dir, meta, rows, companies, issues_all)
    return meta


def rebuild_company(
    listing: Listing,
    cik: str | None,
    rec: dict | None,
    sec: SecClient,
    overrides: dict,
    *,
    as_of: date,
    verify_quarters: bool = True,
    offline: bool = False,
    refresh_filings: bool = False,
) -> dict:
    """One listing → company JSON using existing quarter, TTM, and EDGAR-supplement rules."""
    rev = None
    earn = None
    supp_dict = None
    earn_supp_dict = None
    sec_name = rec["name"] if rec else None
    sic: SicInfo | None = None
    if cik:
        sic = sec.sic(cik)
        rf = sec.revenue_facts(cik)
        if rf is not None:

            def fetch(accn: str, _cik: str = cik):
                return sec.income_statement(_cik, accn)

            periodic = sec.periodic_filings(cik, refresh=refresh_filings)
            latest_end = latest_facts_period_end(rf)
            if (
                not offline
                and not refresh_filings
                and facts_may_lag(latest_end, as_of)
                and not newer_filings(periodic, latest_end)
            ):
                periodic = sec.periodic_filings(cik, refresh=True)
                refreshed = True
            else:
                refreshed = refresh_filings
            rf, supp = supplement_revenue_facts(rf, periodic, fetch, as_of)
            supp.refreshed_submissions = refreshed
            rev = analyze_company(
                rf, fetch, override=overrides.get(cik, {}).get("concept"), verify_quarters=verify_quarters
            )
            if supp.status == "applied" and "supplemented_from_edgar_filing" not in rev.flags:
                rev.flags.append("supplemented_from_edgar_filing")
            supp_dict = supp.to_dict()
            ef = sec.earnings_facts(cik)
            if ef is not None:
                ef, e_supp = supplement_earnings_facts(ef, periodic, fetch, as_of)
                earn = analyze_company(ef, fetch, spec=EARNINGS_SPEC, verify_quarters=verify_quarters)
                if e_supp.status == "applied" and "supplemented_from_edgar_filing" not in earn.flags:
                    earn.flags.append("supplemented_from_edgar_filing")
                earn_supp_dict = e_supp.to_dict()
            log.info("%s: %s %s supplement=%s", listing.symbol, rev.status, rev.ttm, supp.status)
    issues = classification_issues(listing, cik, sic)
    c = company_json(listing, cik, sec_name, rev, sic, issues, earnings=earn)
    if rev is None:
        c["ttm"]["reason"] = "no_cik" if not cik else "no_company_facts"
    if supp_dict and c.get("revenue"):
        c["revenue"]["edgarSupplement"] = supp_dict
    if earn_supp_dict and c.get("earnings"):
        c["earnings"]["edgarSupplement"] = earn_supp_dict
    return c


def classification_issues(listing: Listing, cik: str | None, sic: SicInfo | None) -> list[dict]:
    out: list[dict] = []
    if not cik:
        out.append({"ticker": listing.symbol, "issue": "no_cik", "detail": "No SEC CIK matches this ticker."})
        return out
    if not sic or not sic.code:
        out.append(
            {"ticker": listing.symbol, "issue": "no_sic", "detail": "SEC submissions did not include an SIC code."}
        )
    return out


def _is_current_edgar_unresolved(c: dict) -> bool:
    """True when Company Facts look current but a newer official filing was not ingested.

    Foreign filers, issuers with no revenue concept, and stale snapshots (latest facts
    older than ~5 quarters) are not publication blockers. Those companies stay visible
    with N/A. The gate is for the INCY/SHEN case: a recent quarter is on EDGAR and we
    failed to read its income statement.
    """
    from datetime import date as date_cls

    supp = (c.get("revenue") or {}).get("edgarSupplement") or {}
    if supp.get("status") != "unresolved":
        return False
    if (c.get("ttm") or {}).get("reason") in {"foreign_filer", "no_revenue_concept"}:
        return False
    raw = supp.get("latestFactsEnd")
    if not raw:
        return False
    latest = date_cls.fromisoformat(raw)
    return (date.today() - latest).days <= 400


def make_meta(dataset, companies, listings_all, exclusions, file_times, started, run=None, baseline=None) -> dict:
    def count(pred) -> int:
        return sum(1 for c in companies if pred(c))

    def rev(c):
        return c.get("revenue") or {}

    checks = Counter(
        (q.get("check") or {}).get("status", "not_checked")
        for c in companies
        for q in rev(c).get("quarters", [])
        if not q.get("missing")
    )
    groups: dict[str, set[str]] = {}
    currencies: dict[str, int] = Counter()
    for c in companies:
        sic = c.get("sic") or {}
        g, lab = sic.get("majorGroup"), sic.get("label")
        if g:
            groups.setdefault(g, set())
            if lab:
                groups[g].add(lab)
        cur = (rev(c).get("currency") or (c.get("ttm") or {}).get("currency"))
        if cur:
            currencies[cur] += 1
        elif c["ttm"]["current"] is not None:
            currencies["unknown"] += 1

    filed = sorted(q["filed"] for c in companies for q in rev(c).get("quarters", []) if q.get("filed"))
    listings_n = len(companies)
    meta = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": _now_iso(),
        "buildStartedAt": started,
        "dataset": dataset,
        "run": run or {"status": "complete", "startedAt": started, "finishedAt": _now_iso()},
        "universe": {
            "source": "NASDAQ Trader symbol directory (nasdaqlisted.txt, otherlisted.txt)",
            "exchanges": ["NASDAQ", "NYSE", "NYSE American"],
            "eligibleListings": len(listings_all),
            "byExchange": dict(Counter(x.exchange for x in listings_all)),
            "bySecurityType": dict(Counter(x.security_type for x in listings_all)),
            "excludedByReason": dict(Counter(e.reason for e in exclusions)),
            "fileCreated": file_times,
        },
        "sources": {
            "nasdaqTrader": {
                "url": "https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs",
                "fileCreated": file_times,
            },
            "sec": {
                "url": "https://www.sec.gov/edgar",
                "companyFacts": "XBRL Company Facts (nightly companyfacts.zip)",
                "sic": "EDGAR submissions sic / sicDescription",
                "periodicFilings": (
                    "EDGAR submissions recent 10-Q/10-K. When Company Facts lag a newer filing, "
                    "Layer 1 uses that filing's official income-statement revenue."
                ),
                "latestFilingDate": filed[-1] if filed else None,
            },
        },
        "coverage": {
            "listings": listings_n,
            "companies": len({c["cik"] or c["ticker"] for c in companies}),
            "cikMatched": count(lambda c: c["cik"]),
            "sicAssigned": count(lambda c: (c.get("sic") or {}).get("code")),
            "includedWithoutRevenue": count(lambda c: c["ttm"]["current"] is None),
            "foreignFilers": count(lambda c: rev(c).get("status") == "foreign_filer"),
            "ambiguousConcept": count(lambda c: rev(c).get("status") == "ambiguous"),
            "eightQuarters": count(
                lambda c: len(rev(c).get("quarters", [])) >= 8
                and not any(q.get("missing") for q in rev(c)["quarters"][:8])
            ),
            "currentTtm": count(lambda c: c["ttm"]["current"] is not None),
            "growth": count(lambda c: c["ttm"]["growthPct"] is not None),
            "statementVerified": count(
                lambda c: ((rev(c).get("statementCheck") or {}).get("status") in ("verified", "verified_value"))
            ),
            "quarterChecks": dict(checks),
            "naReasons": dict(Counter(c["ttm"]["reason"] for c in companies if c["ttm"]["reason"])),
            "classificationIssues": sum(len(c["classificationIssues"]) for c in companies),
            "byCurrency": dict(currencies),
            "edgarSupplemented": count(
                lambda c: ((rev(c).get("edgarSupplement") or {}).get("status") == "applied")
            ),
            "edgarUnresolved": count(_is_current_edgar_unresolved),
            "edgarLaggingBeforeSupplement": count(
                lambda c: bool((rev(c).get("edgarSupplement") or {}).get("newerFilings"))
            ),
        },
        "sicMajorGroups": {s: sorted(i) for s, i in sorted(groups.items())},
        "currencies": sorted(c for c in currencies if c != "unknown"),
    }
    meta["gate"] = evaluate_gate(meta, baseline, publish=False).to_dict()
    return meta


def write_dataset(output_dir: Path, meta: dict, rows: list[dict], companies: list[dict], issues: list[dict]) -> None:
    """Write into a sibling temp directory, then swap it in, so readers never see a partial dataset."""
    tmp = output_dir.with_name(output_dir.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "companies").mkdir(parents=True)
    for c in companies:
        write_json_atomic(tmp / "companies" / f"{c['ticker']}.json", c)
    write_json_atomic(
        tmp / "screener.json",
        {"schemaVersion": SCHEMA_VERSION, "generatedAt": meta["generatedAt"], "rows": rows},
        compact=True,
    )
    write_json_atomic(tmp / "classification_issues.json", {"generatedAt": meta["generatedAt"], "issues": issues})
    write_json_atomic(tmp / "meta.json", meta)
    write_layer2(tmp)
    old = output_dir.with_name(output_dir.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if output_dir.exists():
        output_dir.rename(old)
    tmp.rename(output_dir)
    if old.exists():
        shutil.rmtree(old)
