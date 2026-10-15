"""Attach net-income detail to an existing Layer 1 dataset without rewriting revenue or TTM."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from . import config
from .cache import read_json, write_json_atomic
from .layer2 import write_layer2
from .output import metric_json
from .revenue import EARNINGS_SPEC, analyze_company
from .sec.bulk import extract_compact_facts
from .sec.client import SecClient
from .sec.edgar import supplement_earnings_facts
from .sec.statement import parse_income_statement_from_dir, statement_has_net_income
from .sec.store import FactsStore, PeriodicStore, SicStore, StatementStore

log = logging.getLogger(__name__)


def _as_of(meta: dict) -> date:
    raw = meta.get("generatedAt")
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return date.today()


def _fetch_with_net_income(sec: SecClient, cik: str):
    filings_root = sec.cache_dir / "filings"

    def fetch(accn: str):
        cached = sec.statement_store.get(accn)
        if cached is False:
            return None
        if cached is not None:
            st, url = cached
            if statement_has_net_income(st):
                return cached
            parsed = parse_income_statement_from_dir(filings_root / accn)
            if parsed is None:
                return cached
            st, html_name = parsed
            if url and "/" in url:
                url = url.rsplit("/", 1)[0] + "/" + html_name
            else:
                url = html_name
            sec.statement_store.put(accn, (st, url))
            return st, url
        return sec.income_statement(cik, accn)

    return fetch


def attach_earnings(
    data_dir: Path,
    *,
    state_dir: Path | None = None,
    facts_zip: Path | None = None,
    merge_facts: bool = True,
    verify_quarters: bool = True,
    rebuild_layer2: bool = True,
) -> dict:
    """Write `earnings` onto each company JSON. Revenue, TTM, and Layer 2 buckets stay as they are."""
    data_dir = Path(data_dir)
    state_dir = Path(state_dir) if state_dir else config.STATE_DIR
    companies_dir = data_dir / "companies"
    if not companies_dir.is_dir():
        raise FileNotFoundError(f"No companies directory in {data_dir}")

    facts_store = FactsStore(state_dir / "facts")
    statement_store = StatementStore(state_dir / "statements")
    sic_store = SicStore(state_dir / "sic")
    periodic_store = PeriodicStore(state_dir / "periodic")
    sec = SecClient(
        offline=True,
        facts_store=facts_store,
        statement_store=statement_store,
        sic_store=sic_store,
        periodic_store=periodic_store,
    )

    paths = sorted(companies_dir.glob("*.json"))
    ciks = []
    for path in paths:
        company = read_json(path) or {}
        if company.get("cik"):
            ciks.append(str(company["cik"]).zfill(10))

    merged = False
    if merge_facts:
        zip_path = facts_zip or (config.CACHE_DIR / "sec" / "bulk" / "companyfacts.zip")
        if zip_path.exists() and ciks:
            extract_compact_facts(zip_path, ciks, facts_store.directory)
            merged = True
            log.info("Merged earnings into compact facts for %d CIKs", len(ciks))

    meta = read_json(data_dir / "meta.json") or {}
    as_of = _as_of(meta)
    attached = 0
    skipped = 0
    for i, path in enumerate(paths, 1):
        company = read_json(path) or {}
        ttm = company.get("ttm")
        revenue = company.get("revenue")
        cik = company.get("cik")
        earn_payload = None
        earn_supp = None
        if cik:
            ef = sec.earnings_facts(cik)
            if ef is not None:
                fetch = _fetch_with_net_income(sec, cik)
                periodic = sec.periodic_filings(cik)
                ef, e_supp = supplement_earnings_facts(ef, periodic, fetch, as_of)
                earn = analyze_company(ef, fetch, spec=EARNINGS_SPEC, verify_quarters=verify_quarters)
                if e_supp.status == "applied" and "supplemented_from_edgar_filing" not in earn.flags:
                    earn.flags.append("supplemented_from_edgar_filing")
                earn_payload = metric_json(earn, cik)
                earn_supp = e_supp.to_dict()
                if earn_supp:
                    earn_payload["edgarSupplement"] = earn_supp
        if company.get("earnings") != earn_payload:
            company["earnings"] = earn_payload
            if company.get("ttm") != ttm or company.get("revenue") != revenue:
                raise RuntimeError(f"{path.name}: attach_earnings must not rewrite revenue or TTM")
            write_json_atomic(path, company)
            attached += 1
        else:
            skipped += 1
        if i % 250 == 0 or i == len(paths):
            log.info("attach-earnings %d/%d attached=%d", i, len(paths), attached)

    layer2 = write_layer2(data_dir) if rebuild_layer2 else None
    return {
        "companies": len(paths),
        "factsMerged": merged,
        "attached": attached,
        "unchanged": skipped,
        "layer2Counts": None if layer2 is None else layer2.get("counts"),
    }
