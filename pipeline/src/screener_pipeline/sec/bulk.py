"""Download and stream SEC's nightly companyfacts.zip into compact per-CIK revenue facts."""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path

from .. import config
from ..cache import canonical_hash, is_fresh, read_json, sha256_file, write_json_atomic
from ..http import RateLimitedClient
from .facts import compact_revenue_facts, extract_revenue_facts

log = logging.getLogger(__name__)


def zip_member(cik: str) -> str:
    return f"CIK{str(cik).zfill(10)}.json"


def download_companyfacts_zip(http: RateLimitedClient, dest: Path, *, offline: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (offline or is_fresh(dest, config.SEC_BULK_TTL_H)):
        return dest
    if offline:
        raise FileNotFoundError(f"offline mode and no cached copy of {config.SEC_COMPANYFACTS_ZIP_URL}")
    log.info("Downloading companyfacts.zip to %s", dest)
    http.download(config.SEC_COMPANYFACTS_ZIP_URL, dest)
    return dest


def extract_compact_facts(
    zip_path: Path,
    ciks: list[str],
    facts_dir: Path,
    *,
    force: bool = False,
) -> dict[str, str]:
    """Write compact revenue facts for each CIK present in the zip. Returns {cik: sha256}."""
    facts_dir.mkdir(parents=True, exist_ok=True)
    wanted = {str(c).zfill(10) for c in ciks}
    hashes: dict[str, str] = {}
    found: set[str] = set()
    with zipfile.ZipFile(zip_path) as zf:
        available = set(zf.namelist())
        for cik in sorted(wanted):
            name = zip_member(cik)
            out = facts_dir / f"{cik}.json"
            if out.exists() and not force:
                hashes[cik] = canonical_hash(read_json(out))
                found.add(cik)
                continue
            if name not in available:
                continue
            with zf.open(name) as fh:
                payload = json.load(fh)
            compact = compact_revenue_facts(extract_revenue_facts(payload))
            write_json_atomic(out, compact)
            hashes[cik] = canonical_hash(compact)
            found.add(cik)
    missing = wanted - found
    if missing:
        log.info(
            "companyfacts.zip missing %d of %d requested CIKs; API fallback will be used",
            len(missing),
            len(wanted),
        )
    return hashes


def zip_info(zip_path: Path) -> dict:
    return {
        "path": str(zip_path),
        "bytes": zip_path.stat().st_size if zip_path.exists() else 0,
        "sha256": sha256_file(zip_path) if zip_path.exists() else None,
        "url": config.SEC_COMPANYFACTS_ZIP_URL,
    }
