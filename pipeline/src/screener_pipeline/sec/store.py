"""On-disk caches for compact revenue facts and parsed income statements."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .. import config
from ..cache import canonical_hash, read_json, write_json_atomic
from .edgar import PeriodicFiling
from .facts import RevenueFacts, compact_revenue_facts, extract_revenue_facts, revenue_facts_from_compact
from .sic import SicInfo, sic_from_submissions
from .statement import Statement, statement_from_compact, statement_to_compact


class FactsStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (config.STATE_DIR / "facts")
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, cik: str) -> Path:
        return self.directory / f"{str(cik).zfill(10)}.json"

    def get(self, cik: str) -> RevenueFacts | None:
        data = read_json(self.path(cik))
        return revenue_facts_from_compact(data) if data else None

    def put(self, rf: RevenueFacts) -> str:
        compact = compact_revenue_facts(rf)
        write_json_atomic(self.path(rf.cik), compact)
        return canonical_hash(compact)

    def put_raw(self, companyfacts: dict) -> tuple[RevenueFacts, str]:
        rf = extract_revenue_facts(companyfacts)
        return rf, self.put(rf)

    def hash_of(self, cik: str) -> str | None:
        data = read_json(self.path(cik))
        return canonical_hash(data) if data else None


class StatementStore:
    """Cached rendered income statements, keyed by accession number. Filings are immutable."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or (config.STATE_DIR / "statements")
        self.directory.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, tuple[Statement, str] | None] = {}

    def path(self, accn: str) -> Path:
        return self.directory / f"{accn}.json"

    def get(self, accn: str) -> tuple[Statement, str] | None | bool:
        """Cached result, False if known-missing, None if not yet fetched."""
        if accn in self._mem:
            return self._mem[accn] if self._mem[accn] is not None else False
        data = read_json(self.path(accn))
        if data is None:
            return None
        if data.get("missing"):
            self._mem[accn] = None
            return False
        st, url = statement_from_compact(data)
        self._mem[accn] = (st, url)
        return st, url

    def put(self, accn: str, result: tuple[Statement, str] | None) -> None:
        self._mem[accn] = result
        if result is None:
            write_json_atomic(self.path(accn), {"missing": True, "accn": accn})
            return
        st, url = result
        payload = statement_to_compact(st, url)
        payload["accn"] = accn
        write_json_atomic(self.path(accn), payload)


class SicStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (config.STATE_DIR / "sic")
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, cik: str) -> Path:
        return self.directory / f"{str(cik).zfill(10)}.json"

    def get(self, cik: str) -> SicInfo | None:
        data = read_json(self.path(cik))
        if not data:
            return None
        return SicInfo(data.get("code"), data.get("description"), data.get("majorGroup"), data.get("label"))

    def put(self, cik: str, info: SicInfo) -> None:
        payload = info.to_dict()
        payload["cik"] = str(cik).zfill(10)
        write_json_atomic(self.path(cik), payload)

    def put_payload(self, cik: str, payload: dict) -> SicInfo:
        info = sic_from_submissions(payload)
        self.put(cik, info)
        return info


class PeriodicStore:
    """Recent 10-Q/10-K accessions from EDGAR submissions, keyed by CIK."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or (config.STATE_DIR / "periodic")
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, cik: str) -> Path:
        return self.directory / f"{str(cik).zfill(10)}.json"

    def get(self, cik: str) -> list[PeriodicFiling] | None:
        data = read_json(self.path(cik))
        if not data:
            return None
        out: list[PeriodicFiling] = []
        for row in data.get("filings") or []:
            try:
                filed = date.fromisoformat(row["filed"])
                report = date.fromisoformat(row["reportDate"]) if row.get("reportDate") else None
            except (KeyError, TypeError, ValueError):
                continue
            out.append(PeriodicFiling(row["accn"], row.get("form", ""), filed, report))
        return out

    def put(self, cik: str, filings: list[PeriodicFiling], *, source: str) -> None:
        write_json_atomic(
            self.path(cik),
            {
                "cik": str(cik).zfill(10),
                "source": source,
                "filings": [f.to_dict() for f in filings],
            },
        )
