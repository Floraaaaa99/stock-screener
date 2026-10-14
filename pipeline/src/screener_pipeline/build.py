"""Build the static dataset: universe -> SEC revenue -> Yahoo market data -> JSON files."""

from __future__ import annotations

import logging
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from . import config, yahoo
from .cache import write_json_atomic
from .output import SCHEMA_VERSION, company_json, screener_row
from .revenue import analyze_company
from .sec.client import SecClient, load_overrides
from .sec.facts import extract_revenue_facts
from .universe.fetch import load_universe
from .universe.nasdaq_trader import Listing

log = logging.getLogger(__name__)


class DatasetError(RuntimeError):
    pass


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


def build(universe: str, *, offline: bool = False, skip_yahoo: bool = False, verify_quarters: bool = True,
          output_dir: Path | None = None) -> dict:
    output_dir = output_dir or config.OUTPUT_DIR
    started = _now_iso()

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
            "expectedIndustry": sample_meta.get("industry"),
        }
    elif universe == "full":
        raise DatasetError(
            "The full-universe build is Stage 2 and is enabled after the sample is validated; "
            "use --universe sample:biotech20."
        )
    else:
        raise DatasetError(f"Unknown universe {universe!r}")

    sec = SecClient(offline=offline)
    ticker_map = sec.ticker_map()
    overrides = load_overrides()

    ycache = yahoo.YahooCache()
    yahoo_errors: dict[str, str] = {}
    if not skip_yahoo:
        yahoo_errors = yahoo.refresh([x.symbol for x in listings], ycache, offline=offline)

    companies: list[dict] = []
    issues_all: list[dict] = []
    for listing in listings:
        rec = SecClient.lookup_cik(ticker_map, listing.symbol)
        cik = str(rec["cik"]).zfill(10) if rec else None
        rev = None
        sec_name = rec["name"] if rec else None
        if cik:
            facts = sec.companyfacts(cik)
            if facts is not None:
                rf = extract_revenue_facts(facts)
                override = overrides.get(cik, {}).get("concept")

                def fetch(accn: str, _cik: str = cik):
                    return sec.income_statement(_cik, accn)

                rev = analyze_company(rf, fetch, override=override, verify_quarters=verify_quarters)
                log.info("%s: %s %s", listing.symbol, rev.status, rev.ttm)

        y = dict(ycache.get(listing.symbol))
        issues = classification_issues(listing, y, yahoo_errors.get(listing.symbol), dataset)
        issues_all.extend(issues)
        c = company_json(listing, cik, sec_name, rev, y, issues)
        if rev is None:
            c["ttm"]["reason"] = "no_cik" if not cik else "no_company_facts"
        companies.append(c)

    rows = sorted((screener_row(c) for c in companies),
                  key=lambda r: (r["marketCap"] is None, -(r["marketCap"] or 0)))
    meta = make_meta(dataset, companies, listings_all, exclusions, file_times, ycache, started)

    write_dataset(output_dir, meta, rows, companies, issues_all)
    return meta


def classification_issues(listing: Listing, y: dict, error: str | None, dataset: dict) -> list[dict]:
    out: list[dict] = []
    if not y.get("profile_as_of"):
        out.append({"ticker": listing.symbol, "issue": "yahoo_no_data", "detail": error or "never fetched"})
        return out
    qt = y.get("quoteType")
    if qt != "EQUITY":
        out.append({"ticker": listing.symbol, "issue": "yahoo_quote_type", "detail": f"quoteType={qt!r}"})
    if not y.get("sector") or not y.get("industry"):
        out.append({"ticker": listing.symbol, "issue": "yahoo_missing_classification",
                    "detail": f"sector={y.get('sector')!r} industry={y.get('industry')!r}"})
    expected = dataset.get("expectedIndustry")
    if expected and y.get("industry") and y.get("industry") != expected:
        out.append({"ticker": listing.symbol, "issue": "sample_industry_mismatch",
                    "detail": f"Yahoo industry is {y.get('industry')!r}, sample expects {expected!r}"})
    if error:
        out.append({"ticker": listing.symbol, "issue": "yahoo_stale", "detail": f"refresh failed: {error}"})
    return out


def make_meta(dataset, companies, listings_all, exclusions, file_times, ycache, started) -> dict:
    def count(pred) -> int:
        return sum(1 for c in companies if pred(c))

    def rev(c):
        return c.get("revenue") or {}

    checks = Counter(
        (q.get("check") or {}).get("status", "not_checked")
        for c in companies for q in rev(c).get("quarters", []) if not q.get("missing")
    )
    sectors: dict[str, set[str]] = {}
    for c in companies:
        s, i = c["market"]["sector"], c["market"]["industry"]
        if s:
            sectors.setdefault(s, set())
            if i:
                sectors[s].add(i)

    market_times = sorted(c["market"]["marketAsOf"] for c in companies if c["market"]["marketAsOf"])
    profile_times = sorted(c["market"]["profileAsOf"] for c in companies if c["market"]["profileAsOf"])
    filed = sorted(q["filed"] for c in companies for q in rev(c).get("quarters", []) if q.get("filed"))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": _now_iso(),
        "buildStartedAt": started,
        "dataset": dataset,
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
            "nasdaqTrader": {"url": "https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs",
                             "fileCreated": file_times},
            "yahoo": {"url": "https://finance.yahoo.com", "via": "yfinance",
                      "marketOldest": market_times[0] if market_times else None,
                      "marketNewest": market_times[-1] if market_times else None,
                      "profileOldest": profile_times[0] if profile_times else None},
            "sec": {"url": "https://www.sec.gov/edgar", "api": "XBRL Company Facts",
                    "latestFilingDate": filed[-1] if filed else None},
        },
        "coverage": {
            "listings": len(companies),
            "companies": len({c["cik"] or c["ticker"] for c in companies}),
            "yahooProfile": count(lambda c: c["market"]["sector"] and c["market"]["industry"]),
            "marketCap": count(lambda c: c["market"]["marketCap"] is not None),
            "price": count(lambda c: c["market"]["price"] is not None),
            "cikMatched": count(lambda c: c["cik"]),
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
        },
        "sectors": {s: sorted(i) for s, i in sorted(sectors.items())},
    }


def write_dataset(output_dir: Path, meta: dict, rows: list[dict], companies: list[dict], issues: list[dict]) -> None:
    """Write into a sibling temp directory, then swap it in, so readers never see a partial dataset."""
    tmp = output_dir.with_name(output_dir.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "companies").mkdir(parents=True)
    for c in companies:
        write_json_atomic(tmp / "companies" / f"{c['ticker']}.json", c)
    write_json_atomic(tmp / "screener.json", {"schemaVersion": SCHEMA_VERSION, "generatedAt": meta["generatedAt"],
                                              "rows": rows}, compact=True)
    write_json_atomic(tmp / "classification_issues.json", {"generatedAt": meta["generatedAt"], "issues": issues})
    write_json_atomic(tmp / "meta.json", meta)
    old = output_dir.with_name(output_dir.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if output_dir.exists():
        output_dir.rename(old)
    tmp.rename(output_dir)
    if old.exists():
        shutil.rmtree(old)
