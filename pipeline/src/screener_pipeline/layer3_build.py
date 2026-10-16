"""Build static layer3.json from Layer 1 identity plus optional Company Facts.

GitHub Pages cannot call the SEC from the browser. Metrics are precomputed at build
time for every issuer in issuers.json / screener.json. The website only *displays*
metrics for companies the user added to the Layer 3 list.

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
from .layer3_concepts import LAYER3_EXTRACTION_VERSION, LAYER3_SCHEMA_VERSION, is_financial_sic
from .layer3_extract import analyze_layer3_facts


def _empty_counts() -> dict:
    return {
        "issuers": 0,
        "extraction": {"extracted": 0, "pendingAnalysis": 0, "insufficientFacts": 0},
        "verification": {"companyFactsOnly": 0, "notChecked": 0},
        "model": {"applicable": 0, "notApplicable": 0},
        "scoring": {"notImplemented": 0},
        "inputs": {"ready": 0, "pendingDataVerification": 0, "pendingAnalysis": 0},
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


def write_layer3(
    data_dir: Path,
    dest: Path | None = None,
    *,
    companyfacts_by_cik: dict[str, dict] | None = None,
    facts_dir: Path | None = None,
    facts_zip: Path | None = None,
    limit: int | None = None,
    read_company_json: bool = False,
) -> dict:
    data_dir = Path(data_dir)
    dest = Path(dest) if dest else data_dir / "layer3.json"
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

    rows = []
    counts = _empty_counts()
    inline = companyfacts_by_cik or {}
    zf = CompanyFactsZip(facts_zip) if facts_zip else None
    try:
        for cik, tickers in sorted(by_cik.items()):
            if limit is not None and counts["issuers"] >= limit:
                break
            tickers = sorted(set(tickers))
            primary = next((t for t in tickers if t in by_ticker), tickers[0])
            row = by_ticker.get(primary)
            company = None
            if read_company_json and (companies_dir / f"{primary}.json").exists():
                company = read_json(companies_dir / f"{primary}.json", default=None)
            sic = ((company or {}).get("sic") or {})
            sic_code = sic.get("code") or (row or {}).get("sicCode")
            reused = _reused_layer1(row, company)
            payload = {
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
                "extractionVersion": LAYER3_EXTRACTION_VERSION,
                "scoring": None,
            }
            facts = None
            if cik in inline:
                facts = inline[cik]
            elif facts_dir is not None:
                facts = companyfacts_from_dir(facts_dir, cik)
            elif zf is not None:
                facts = zf.get(cik)

            if facts is not None:
                analysis = analyze_layer3_facts(facts, sic_code=sic_code)
                payload.update(analysis.to_dict())
                payload["metrics"] = public_metrics(payload.get("metrics"))
                payload["tickers"] = tickers
                payload["displayTicker"] = primary
                payload["name"] = (row or company or {}).get("name") or payload.get("name") or analysis.cik
                payload["scoring"] = None
            else:
                payload["extractionStatus"] = "pending_analysis"
                payload["verificationStatus"] = "not_checked"
                payload["modelApplicability"] = "not_applicable" if is_financial_sic(sic_code) else "applicable"
                payload["scoringStatus"] = "not_implemented"
                payload["inputCompleteness"] = "pending_analysis"
                payload["flags"] = ["financial_institution"] if is_financial_sic(sic_code) else []
                payload["metrics"] = None
                payload["reason"] = (
                    "financial_institution_review_required"
                    if is_financial_sic(sic_code)
                    else "layer3_concepts_not_in_compact_facts"
                )
            _count_row(counts, payload)
            rows.append(payload)
    finally:
        if zf is not None:
            zf.close()

    out = {
        "schemaVersion": LAYER3_SCHEMA_VERSION,
        "extractionVersion": LAYER3_EXTRACTION_VERSION,
        "generatedAt": _now_iso(),
        "cutoffNote": "Facts available in the dataset snapshot only; no look-ahead beyond that extract.",
        "verificationNote": (
            "Cash-flow and balance-sheet figures are taken from SEC Company Facts. "
            "The current statement cache is income-statement only, so those lines are "
            "not face-checked against the rendered 10-Q/10-K in Phase 2."
        ),
        "scoring": None,
        "counts": counts,
        "rows": rows,
    }
    write_json_atomic(dest, out, compact=True)
    return out


def default_facts_zip() -> Path | None:
    path = config.CACHE_DIR / "sec" / "bulk" / "companyfacts.zip"
    return path if path.exists() else None
