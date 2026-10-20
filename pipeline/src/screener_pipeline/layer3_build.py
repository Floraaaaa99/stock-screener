"""Build a slim Layer 3 index plus one CIK-keyed metrics file per issuer.

GitHub Pages cannot call the SEC from the browser. Metrics are precomputed at build
time for every issuer in issuers.json / screener.json. The website downloads
``layer3/cik/{cik}.json`` only for issuers on the user's manually curated list.

``layer3.json`` is an index: identity, the four status dimensions, and counts.
It does not embed quarter-level cash-flow or balance-sheet series.

This writer never recalculates Layer 1 TTM revenue or Layer 2 buckets. Those values
are copied as references when present. The 100-point score is not computed.
"""

from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from . import config
from .cache import read_json, write_json_atomic
from .layer3_concepts import (
    LAYER3_EXTRACTION_VERSION,
    LAYER3_ISSUER_FILE_TEMPLATE,
    LAYER3_SCHEMA_VERSION,
    ZERO_CIK,
    is_financial_sic,
    normalize_cik,
)
from .layer3_extract import analyze_layer3_facts

COVERAGE_KEYS = (
    "revenue",
    "netIncome",
    "grossProfit",
    "costOfRevenue",
    "operatingIncome",
    "ocf",
    "capex",
    "fcf",
    "interestExpense",
    "depreciationAmortization",
    "ebitda",
    "grossMargin",
    "operatingMargin",
    "netMargin",
    "fcfMargin",
    "cashConversion",
    "cash",
    "shortTermDebt",
    "longTermDebt",
    "totalDebt",
    "netDebt",
    "accountsReceivable",
    "inventory",
    "accountsPayable",
    "currentAssets",
    "currentLiabilities",
    "currentRatio",
    "operatingWorkingCapital",
    "dso",
    "dio",
    "dpo",
    "cashConversionCycle",
)


def _empty_counts() -> dict:
    return {
        "issuers": 0,
        "extraction": {"extracted": 0, "pendingAnalysis": 0, "insufficientFacts": 0},
        "verification": {"companyFactsOnly": 0, "notChecked": 0},
        "model": {"applicable": 0, "notApplicable": 0},
        "scoring": {"notImplemented": 0},
        "inputs": {"ready": 0, "pendingDataVerification": 0, "pendingAnalysis": 0},
        "metrics": {
            key: {"extracted": 0, "missing": 0, "notApplicable": 0}
            for key in COVERAGE_KEYS
        },
    }


def _count_row(counts: dict, payload: dict) -> None:
    counts["issuers"] += 1
    ext_map = {
        "extracted": "extracted",
        "pending_analysis": "pendingAnalysis",
        "insufficient_facts": "insufficientFacts",
    }
    inp_map = {
        "ready": "ready",
        "pending_data_verification": "pendingDataVerification",
        "pending_analysis": "pendingAnalysis",
    }
    ext = payload.get("extractionStatus") or "pending_analysis"
    counts["extraction"][ext_map.get(ext, "pendingAnalysis")] += 1
    ver = payload.get("verificationStatus") or "not_checked"
    counts["verification"]["companyFactsOnly" if ver == "company_facts_only" else "notChecked"] += 1
    counts["model"]["notApplicable" if payload.get("modelApplicability") == "not_applicable" else "applicable"] += 1
    counts["scoring"]["notImplemented"] += 1
    inp = payload.get("inputCompleteness") or "pending_analysis"
    counts["inputs"][inp_map.get(inp, "pendingAnalysis")] += 1
    metrics = payload.get("metrics") or {}
    for key in COVERAGE_KEYS:
        item = metrics.get(key) if isinstance(metrics, dict) else None
        if not isinstance(item, dict):
            counts["metrics"][key]["missing"] += 1
            continue
        status = item.get("status")
        has_value = item.get("ttm") is not None or item.get("value") is not None
        if status == "not_applicable":
            counts["metrics"][key]["notApplicable"] += 1
        elif status == "extracted" or has_value:
            counts["metrics"][key]["extracted"] += 1
        else:
            counts["metrics"][key]["missing"] += 1


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _reused_layer1(row: dict | None, company: dict | None) -> dict:
    ttm = (company or {}).get("ttm") or {}
    earnings = (company or {}).get("earnings") or {}
    return {
        "revenueTtm": row.get("ttmCurrent") if row else ttm.get("current"),
        "revenuePriorTtm": row.get("ttmPrevious") if row else ttm.get("previous"),
        "revenueTtmGrowth": row.get("ttmGrowth") if row else ttm.get("growthPct"),
        "revenueReason": row.get("naReason") if row else ttm.get("reason"),
        "revenueCurrency": (row or {}).get("revenueCurrency") or ttm.get("currency"),
        "earningsConcept": earnings.get("concept"),
        "earningsStatus": earnings.get("status"),
        "source": "layer1_copy",
    }


def _strip_sources(value):
    if isinstance(value, list):
        return [_strip_sources(v) for v in value]
    if isinstance(value, dict):
        return {k: _strip_sources(v) for k, v in value.items() if k != "sources"}
    return value


def public_metrics(metrics: dict | None) -> dict | None:
    """Drop bulky source-leg arrays from the static website payload. Provenance remains
    on each quarter (concept, method, formula, accn, form, filed, url)."""
    if metrics is None:
        return None
    return _strip_sources(metrics)


def issuer_file_relpath(cik: str) -> str:
    return LAYER3_ISSUER_FILE_TEMPLATE.format(cik=str(cik).zfill(10))


def issuer_dir_for(dest: Path) -> Path:
    return Path(dest).parent / "layer3" / "cik"


class Layer3BuildError(RuntimeError):
    """Safe-build failure. Existing live issuer files must be left untouched."""


def live_layer3_dest() -> Path:
    return config.REPO_ROOT / "web" / "public" / "data" / "layer3.json"


def is_live_layer3_dest(dest: Path) -> bool:
    return Path(dest).resolve() == live_layer3_dest().resolve()


def reset_issuer_dir(directory: Path) -> Path:
    """Clear a directory of issuer JSON. Only for empty staging trees, never live data."""
    directory = Path(directory)
    if directory.resolve() == issuer_dir_for(live_layer3_dest()).resolve():
        raise Layer3BuildError("refusing to reset the live Layer 3 issuer directory")
    if directory.exists():
        for path in directory.glob("*.json"):
            path.unlink()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _is_keepable_extract(payload: dict | None) -> bool:
    if not payload:
        return False
    if payload.get("extractionStatus") != "extracted":
        return False
    return payload.get("metrics") is not None


def _load_issuer(directory: Path, cik: str) -> dict | None:
    path = Path(directory) / f"{str(cik).zfill(10)}.json"
    return read_json(path) if path.exists() else None


def _scan_issuer_dir(directory: Path) -> dict[str, dict]:
    """Index issuer files by filename stem (canonical CIK), not payload.cik."""
    out: dict[str, dict] = {}
    directory = Path(directory)
    if not directory.exists():
        return out
    for path in directory.glob("*.json"):
        payload = read_json(path) or {}
        out[path.stem.zfill(10) if path.stem.isdigit() else path.stem] = payload
    return out


def _issuer_identity_errors(directory: Path) -> list[str]:
    """Filename, payload CIK, duplicates, and zero-CIK checks for one tree."""
    errors: list[str] = []
    seen: dict[str, str] = {}
    directory = Path(directory)
    if not directory.exists():
        return ["issuer directory does not exist"]
    for path in sorted(directory.glob("*.json")):
        payload = read_json(path) or {}
        raw = payload.get("cik")
        cik = normalize_cik(raw)
        if cik is None:
            errors.append(f"{path.name} has zero or invalid cik {raw!r}")
            continue
        if path.stem != cik:
            errors.append(f"{path.name} payload cik {cik} does not match filename")
        if cik in seen:
            errors.append(f"duplicate payload cik {cik} in {seen[cik]} and {path.name}")
        else:
            seen[cik] = path.name
    return errors


def _normalize_ciks(ciks: list[str] | None) -> set[str] | None:
    if ciks is None:
        return None
    return {str(c).zfill(10) for c in ciks if str(c).strip()}


def _has_facts_source(
    companyfacts_by_cik: dict[str, dict] | None,
    facts_dir: Path | None,
    facts_zip: Path | None,
) -> bool:
    if companyfacts_by_cik:
        return True
    if facts_dir is not None and Path(facts_dir).exists():
        return True
    return facts_zip is not None and Path(facts_zip).exists()


def validate_layer3_publish(live_dir: Path, staging_dir: Path) -> list[str]:
    """Reject an unsafe publish: identity errors, extracted→pending, unexpected deletes."""
    errors: list[str] = []
    live_dir = Path(live_dir)
    staging_dir = Path(staging_dir)
    staged_files = list(staging_dir.glob("*.json")) if staging_dir.exists() else []
    if not staged_files:
        return ["staging issuer directory is empty"]
    errors.extend(_issuer_identity_errors(staging_dir))
    errors.extend(_issuer_identity_errors(live_dir))

    live = {p.name: read_json(p) or {} for p in live_dir.glob("*.json")} if live_dir.exists() else {}
    staged = {p.name: read_json(p) or {} for p in staged_files}
    staged_by_ticker: dict[str, list[str]] = defaultdict(list)
    for name, payload in staged.items():
        ticker = payload.get("displayTicker")
        if ticker:
            staged_by_ticker[str(ticker)].append(name)

    for name, payload in sorted(live.items()):
        next_payload = staged.get(name)
        if next_payload is None:
            ticker = payload.get("displayTicker")
            remap = staged_by_ticker.get(str(ticker) or "")
            if remap:
                errors.append(
                    f"{name} would be deleted; ticker {ticker} remapped to {', '.join(remap)}"
                )
            elif _is_keepable_extract(payload):
                errors.append(f"{name} extracted on live is missing from staging")
            else:
                errors.append(f"{name} would be deleted from live")
        elif (
            _is_keepable_extract(payload)
            and next_payload.get("extractionStatus") == "pending_analysis"
        ):
            errors.append(f"{name} would replace extracted with pending_analysis")
    return errors


def _copy_json_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in Path(src).glob("*.json"):
        write_json_atomic(dest / path.name, read_json(path) or {}, compact=True)


def _sync_json_tree(src: Path, dest: Path) -> None:
    """Copy src over dest, then remove dest files that are not in src."""
    _copy_json_tree(src, dest)
    keep = {path.name for path in Path(src).glob("*.json")}
    for path in dest.glob("*.json"):
        if path.name not in keep:
            path.unlink()


def publish_layer3(
    live_dest: Path,
    staging_dest: Path,
    *,
    rollback_dir: Path | None = None,
    write_live: bool = True,
) -> dict:
    """Swap a validated staging tree into live dest. Restore rollback on failure."""
    live_dest = Path(live_dest)
    staging_dest = Path(staging_dest)
    if is_live_layer3_dest(live_dest) and not write_live:
        raise Layer3BuildError("refusing to publish over live Layer 3 without write_live=True")
    live_cik = issuer_dir_for(live_dest)
    staging_cik = issuer_dir_for(staging_dest)
    errors = validate_layer3_publish(live_cik, staging_cik)
    if errors:
        raise Layer3BuildError("publish blocked: " + "; ".join(errors[:8]))

    stamp = _now_iso().replace(":", "")
    rollback_dir = Path(rollback_dir) if rollback_dir else live_dest.parent / f"layer3.rollback-{stamp}"
    rollback_index = rollback_dir / "layer3.json"
    rollback_cik = rollback_dir / "cik"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    published = False
    try:
        if live_dest.exists():
            write_json_atomic(rollback_index, read_json(live_dest) or {})
        if live_cik.exists():
            _copy_json_tree(live_cik, rollback_cik)
        _sync_json_tree(staging_cik, live_cik)
        staging_index = read_json(staging_dest) or {}
        write_json_atomic(live_dest, staging_index, compact=True)
        published = True
    except Exception:
        if rollback_cik.exists():
            _sync_json_tree(rollback_cik, live_cik)
        if rollback_index.exists():
            write_json_atomic(live_dest, read_json(rollback_index) or {}, compact=True)
        raise
    return {
        "published": published,
        "rollbackDir": str(rollback_dir),
        "liveDest": str(live_dest),
        "stagingDest": str(staging_dest),
    }


def index_row(payload: dict) -> dict:
    """Universe index row: statuses and identity only. No quarter-level metrics."""
    row = {k: v for k, v in payload.items() if k != "metrics"}
    row["metrics"] = None
    row["issuerFile"] = issuer_file_relpath(payload["cik"])
    return row


def load_companyfacts_file(path: Path) -> dict:
    return json.loads(path.read_text())


def companyfacts_from_dir(directory: Path, cik: str) -> dict | None:
    directory = Path(directory)
    for name in (f"{cik}.json", f"CIK{cik}.json"):
        path = directory / name
        if path.exists():
            return load_companyfacts_file(path)
    return None


class CompanyFactsZip:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._zf = zipfile.ZipFile(self.path)

    def get(self, cik: str) -> dict | None:
        name = f"CIK{str(cik).zfill(10)}.json"
        try:
            return json.loads(self._zf.read(name))
        except KeyError:
            return None

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> CompanyFactsZip:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _pending_payload(base: dict, sic_code: str | None) -> dict:
    return {
        **base,
        "extractionStatus": "pending_analysis",
        "verificationStatus": "not_checked",
        "modelApplicability": "not_applicable" if is_financial_sic(sic_code) else "applicable",
        "scoringStatus": "not_implemented",
        "inputCompleteness": "pending_analysis",
        "flags": ["financial_institution"] if is_financial_sic(sic_code) else [],
        "metrics": None,
        "scoring": None,
        "reason": (
            "financial_institution_review_required"
            if is_financial_sic(sic_code)
            else "layer3_concepts_not_in_compact_facts"
        ),
    }


def _analyze_payload(
    base: dict,
    facts: dict,
    *,
    sic_code: str | None,
    reused: dict,
    tickers: list[str],
    primary: str,
    row: dict | None,
    company: dict | None,
) -> dict:
    canonical = str(base["cik"]).zfill(10)
    analysis = analyze_layer3_facts(
        facts,
        sic_code=sic_code,
        preferred_earnings_concept=reused.get("earningsConcept"),
        canonical_cik=canonical,
    )
    payload = {**base, **analysis.to_dict()}
    payload["cik"] = canonical
    payload["metrics"] = public_metrics(payload.get("metrics"))
    payload["tickers"] = tickers
    payload["displayTicker"] = primary
    payload["name"] = (row or company or {}).get("name") or payload.get("name") or canonical
    payload["scoring"] = None
    facts_cik = normalize_cik((facts or {}).get("cik"))
    raw_facts_cik = (facts or {}).get("cik")
    if facts_cik and facts_cik != canonical:
        payload["companyFactsCik"] = facts_cik
    elif facts_cik is None and raw_facts_cik not in (None, ""):
        payload["companyFactsCik"] = ZERO_CIK
    return payload


def _write_index(dest: Path, counts: dict) -> dict:
    out = {
        "schemaVersion": LAYER3_SCHEMA_VERSION,
        "extractionVersion": LAYER3_EXTRACTION_VERSION,
        "generatedAt": _now_iso(),
        "payload": "index",
        "issuerFileTemplate": LAYER3_ISSUER_FILE_TEMPLATE,
        "cutoffNote": "Facts available in the dataset snapshot only; no look-ahead beyond that extract.",
        "verificationNote": (
            "Cash-flow, balance-sheet, and newly added income-statement research "
            "figures are independently recalculated from SEC Company Facts XBRL. "
            "They are not face-checked against rendered 10-Q/10-K cash-flow or "
            "balance-sheet statements. Layer 1 income-statement matches remain a "
            "separate, statement-verified concept. calculationMethod=derived is a "
            "formula, not a statement verification."
        ),
        "scoring": None,
        "counts": counts,
        "rows": [],
    }
    write_json_atomic(dest, out, compact=True)
    return out


def write_layer3(
    data_dir: Path,
    dest: Path | None = None,
    *,
    companyfacts_by_cik: dict[str, dict] | None = None,
    facts_dir: Path | None = None,
    facts_zip: Path | None = None,
    limit: int | None = None,
    ciks: list[str] | None = None,
    read_company_json: bool = False,
    mode: str = "incremental",
    staging_dir: Path | None = None,
    publish: bool = False,
    write_live: bool = False,
) -> dict:
    """Extract Layer 3 issuer files.

    ``incremental`` (default): update only selected CIKs in place. Never deletes
    the issuer directory. Never overwrites an extracted file with pending_analysis.

    ``full``: write a complete tree into ``staging_dir`` (or ``<dest>.staging``).
    Publish to ``dest`` only when ``publish=True`` and validation passes.
    """
    if mode not in {"incremental", "full"}:
        raise Layer3BuildError(f"unknown layer3 mode {mode!r}")
    if publish and mode != "full":
        raise Layer3BuildError("publish=True requires mode='full'")
    data_dir = Path(data_dir)
    dest = Path(dest) if dest else data_dir / "layer3.json"
    live_cik_dir = issuer_dir_for(dest)
    wanted = _normalize_ciks(ciks)
    facts_zip = Path(facts_zip) if facts_zip else None
    facts_dir = Path(facts_dir) if facts_dir else None
    if not _has_facts_source(companyfacts_by_cik, facts_dir, facts_zip):
        raise Layer3BuildError(
            "No Company Facts source (zip, facts dir, or inline payload). "
            "Existing issuer JSON was not modified."
        )
    if is_live_layer3_dest(dest) and not write_live:
        if mode == "incremental" or publish:
            raise Layer3BuildError(
                "Refusing to write over live web/public/data/layer3.json without "
                "write_live=True / --write-live. Use a sidecar --output or staging."
            )

    screener = read_json(data_dir / "screener.json")
    issuers = read_json(data_dir / "issuers.json", default={"byTicker": {}}) or {"byTicker": {}}
    companies_dir = data_dir / "companies"
    by_ticker = {r["ticker"]: r for r in (screener or {}).get("rows", [])}
    by_cik: dict[str, list[str]] = defaultdict(list)
    for ticker, cik in (issuers.get("byTicker") or {}).items():
        if cik:
            by_cik[str(cik).zfill(10)].append(ticker)
    if not by_cik:
        for ticker, _row in by_ticker.items():
            path = companies_dir / f"{ticker}.json"
            if not path.exists():
                continue
            company = read_json(path)
            cik = company.get("cik")
            if cik:
                by_cik[str(cik).zfill(10)].append(ticker)

    selected = sorted(by_cik)
    if wanted is not None:
        missing = wanted - set(by_cik)
        selected = [c for c in selected if c in wanted]
        if missing:
            raise Layer3BuildError(
                "Unknown CIKs (not in issuers.json / screener): " + ", ".join(sorted(missing)[:12])
            )
    if limit is not None:
        selected = selected[:limit]

    write_dir = live_cik_dir
    write_dest = dest
    staging_dest = None
    if mode == "full":
        staging_root = Path(staging_dir) if staging_dir else dest.parent / (dest.name + ".staging")
        staging_dest = staging_root / "layer3.json" if staging_root.suffix != ".json" else staging_root
        if staging_dest.suffix != ".json":
            staging_dest = staging_root / "layer3.json"
        write_dest = staging_dest
        write_dir = issuer_dir_for(write_dest)
        reset_issuer_dir(write_dir)
    else:
        write_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    preserved: list[str] = []
    updated: list[str] = []
    inline = companyfacts_by_cik or {}
    zf = CompanyFactsZip(facts_zip) if facts_zip else None
    try:
        for cik in selected:
            tickers = sorted(set(by_cik[cik]))
            primary = next((t for t in tickers if t in by_ticker), tickers[0])
            row = by_ticker.get(primary)
            company = None
            if read_company_json and (companies_dir / f"{primary}.json").exists():
                company = read_json(companies_dir / f"{primary}.json", default=None)
            sic = ((company or {}).get("sic") or {})
            sic_code = sic.get("code") or (row or {}).get("sicCode")
            reused = _reused_layer1(row, company)
            base = {
                "cik": cik,
                "tickers": tickers,
                "displayTicker": primary,
                "name": (row or company or {}).get("name") or primary,
                "exchange": (row or company or {}).get("exchange"),
                "sicCode": sic_code,
                "sicIndustry": sic.get("label") or (row or {}).get("sicIndustry"),
                "sicMajorGroup": sic.get("majorGroup") or (row or {}).get("sicMajorGroup"),
                "layer1": reused,
                "growthSource": "not_yet_verified",
                "schemaVersion": LAYER3_SCHEMA_VERSION,
                "extractionVersion": LAYER3_EXTRACTION_VERSION,
                "dataAsOf": None,
                "scoring": None,
            }
            facts = None
            if cik in inline:
                facts = inline[cik]
            elif facts_dir is not None:
                facts = companyfacts_from_dir(facts_dir, cik)
            elif zf is not None:
                facts = zf.get(cik)

            existing_live = _load_issuer(live_cik_dir, cik)
            if facts is not None:
                payload = _analyze_payload(
                    base, facts, sic_code=sic_code, reused=reused,
                    tickers=tickers, primary=primary, row=row, company=company,
                )
            else:
                payload = _pending_payload(base, sic_code)
                if mode == "incremental" and _is_keepable_extract(existing_live):
                    payload = existing_live
                    preserved.append(cik)
                    rows.append(payload)
                    continue
            if (
                mode == "incremental"
                and _is_keepable_extract(existing_live)
                and payload.get("extractionStatus") == "pending_analysis"
            ):
                preserved.append(cik)
                rows.append(existing_live)
                continue
            write_json_atomic(write_dir / f"{cik}.json", payload, compact=True)
            updated.append(cik)
            rows.append(payload)
    finally:
        if zf is not None:
            zf.close()

    if mode == "full":
        on_disk = _scan_issuer_dir(write_dir)
        counts = _empty_counts()
        index_rows = []
        for _cik, payload in sorted(on_disk.items()):
            _count_row(counts, payload)
            index_rows.append(index_row(payload))
        out = _write_index(write_dest, counts)
        publish_info = None
        if publish:
            publish_info = publish_layer3(dest, write_dest, write_live=write_live)
        return {
            **out,
            "rows": rows,
            "indexRows": index_rows,
            "mode": "full",
            "updated": updated,
            "preserved": preserved,
            "stagingDest": str(write_dest),
            "published": bool(publish_info),
            "publish": publish_info,
        }

    # Incremental: merge updated rows with untouched files so the index stays complete.
    on_disk = _scan_issuer_dir(write_dir)
    for payload in rows:
        on_disk[str(payload["cik"]).zfill(10)] = payload
    counts = _empty_counts()
    index_rows = []
    merged_rows = []
    for _cik, payload in sorted(on_disk.items()):
        _count_row(counts, payload)
        index_rows.append(index_row(payload))
        merged_rows.append(payload)
    out = _write_index(dest, counts)
    return {
        **out,
        "rows": merged_rows,
        "indexRows": index_rows,
        "mode": "incremental",
        "updated": updated,
        "preserved": preserved,
        "published": False,
    }


def default_facts_zip() -> Path | None:
    path = config.CACHE_DIR / "sec" / "bulk" / "companyfacts.zip"
    return path if path.exists() else None


COMPARE_FLOW_KEYS = (
    "ocf",
    "capex",
    "fcf",
    "operatingIncome",
    "interestExpense",
    "depreciationAmortization",
    "ebitda",
    "revenue",
    "netIncome",
    "grossProfit",
    "costOfRevenue",
)
COMPARE_STOCK_KEYS = (
    "cash",
    "shortTermDebt",
    "longTermDebt",
    "totalDebt",
    "netDebt",
    "accountsReceivable",
    "inventory",
    "accountsPayable",
    "currentAssets",
    "currentLiabilities",
)
COMPARE_NEW_KEYS = (
    "grossMargin",
    "operatingMargin",
    "netMargin",
    "fcfMargin",
    "cashConversion",
    "currentRatio",
    "operatingWorkingCapital",
    "dso",
    "dio",
    "dpo",
    "cashConversionCycle",
    "arYoy",
    "inventoryYoy",
    "apYoy",
)


def compare_layer3_issuers(previous: dict, current: dict) -> dict:
    """Diff two issuer payloads (v3 vs v4). Does not write files."""
    prev_m = previous.get("metrics") or {}
    cur_m = current.get("metrics") or {}

    def _metric_view(metrics: dict, key: str) -> dict:
        item = metrics.get(key) if isinstance(metrics, dict) else None
        if not isinstance(item, dict):
            return {"present": False}
        hist = item.get("history") or []
        qs = item.get("quarters") or []
        return {
            "present": True,
            "status": item.get("status"),
            "ttm": item.get("ttm"),
            "previousTtm": item.get("previousTtm"),
            "ttmYoy": item.get("ttmYoy"),
            "value": item.get("value"),
            "end": item.get("end"),
            "concept": item.get("concept"),
            "calculationMethod": item.get("calculationMethod"),
            "verification": item.get("verification"),
            "reason": item.get("reason"),
            "identity": item.get("identity"),
            "quarterCount": len(qs),
            "historyCount": len(hist),
            "historyValues": sum(1 for row in hist if row.get("value") is not None),
        }

    flows = {}
    for key in COMPARE_FLOW_KEYS:
        before, after = _metric_view(prev_m, key), _metric_view(cur_m, key)
        flows[key] = {
            "previous": before,
            "current": after,
            "ttmUnchanged": before.get("ttm") == after.get("ttm") if before.get("present") else None,
        }
    stocks = {}
    for key in COMPARE_STOCK_KEYS:
        before, after = _metric_view(prev_m, key), _metric_view(cur_m, key)
        stocks[key] = {
            "previous": before,
            "current": after,
            "valueUnchanged": before.get("value") == after.get("value") if before.get("present") else None,
        }
    added = {key: _metric_view(cur_m, key) for key in COMPARE_NEW_KEYS}
    return {
        "cik": current.get("cik") or previous.get("cik"),
        "previousExtractionVersion": previous.get("extractionVersion"),
        "currentExtractionVersion": current.get("extractionVersion"),
        "previousSchemaVersion": previous.get("schemaVersion"),
        "currentSchemaVersion": current.get("schemaVersion"),
        "extractionStatus": {
            "previous": previous.get("extractionStatus"),
            "current": current.get("extractionStatus"),
        },
        "verificationStatus": {
            "previous": previous.get("verificationStatus"),
            "current": current.get("verificationStatus"),
        },
        "flows": flows,
        "stocks": stocks,
        "added": added,
        "replacedExtractedWithPending": (
            previous.get("extractionStatus") == "extracted"
            and current.get("extractionStatus") == "pending_analysis"
        ),
    }
