"""SEC EDGAR daily filing indexes (master.idx). Incremental updates only; not a full-universe rebuild."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .. import config
from .facts import DOMESTIC_FORMS

# https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/master.20261020.idx
SEC_DAILY_MASTER_URL = (
    "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/master.{yyyymmdd}.idx"
)

_ACCN_RE = re.compile(r"(\d{10}-\d{2}-\d{6})")
_SEPARATOR = "CIK|Company Name|Form Type|Date Filed|Filename"


@dataclass(frozen=True)
class DailyFiling:
    cik: str
    name: str
    form: str
    filed: date
    filename: str
    accn: str

    def to_dict(self) -> dict:
        return {
            "cik": self.cik,
            "name": self.name,
            "form": self.form,
            "filed": self.filed.isoformat(),
            "filename": self.filename,
            "accn": self.accn,
        }


def lookback_dates(as_of: date, days: int) -> list[date]:
    """Inclusive rolling window ending on as_of. Weekends/holidays are kept; missing indexes are skipped later."""
    if days < 1:
        raise ValueError("lookback days must be >= 1")
    return [as_of - timedelta(days=offset) for offset in range(days)]


def master_idx_url(day: date) -> str:
    quarter = (day.month - 1) // 3 + 1
    return SEC_DAILY_MASTER_URL.format(year=day.year, quarter=quarter, yyyymmdd=day.strftime("%Y%m%d"))


def accession_from_filename(filename: str) -> str | None:
    match = _ACCN_RE.search(filename.replace("_", "-"))
    return match.group(1) if match else None


def parse_master_idx(text: str, *, forms: set[str] | None = None) -> list[DailyFiling]:
    """Parse an EDGAR master.idx body. Unknown/malformed rows are skipped."""
    wanted = forms if forms is not None else set(DOMESTIC_FORMS)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start = 0
    for i, line in enumerate(lines):
        if line.startswith(_SEPARATOR) or line.startswith("CIK|"):
            start = i + 1
            if start < len(lines) and set(lines[start]) <= {"-", "="}:
                start += 1
            break
    out: list[DailyFiling] = []
    seen: set[str] = set()
    for line in lines[start:]:
        if not line.strip() or line.startswith("-"):
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        cik_raw, name, form, filed_raw, filename = (p.strip() for p in parts[:5])
        if form not in wanted:
            continue
        accn = accession_from_filename(filename)
        if not accn:
            continue
        try:
            cik = str(int(cik_raw)).zfill(10)
        except ValueError:
            continue
        filed = _parse_filed(filed_raw)
        if filed is None:
            continue
        key = accn
        if key in seen:
            continue
        seen.add(key)
        out.append(DailyFiling(cik=cik, name=name, form=form, filed=filed, filename=filename, accn=accn))
    return out


def _parse_filed(raw: str) -> date | None:
    compact = raw.replace("-", "").replace("/", "")
    if len(compact) == 8 and compact.isdigit():
        try:
            return date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))
        except ValueError:
            return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def fetch_master_idx(http, day: date, cache_dir: Path | None = None) -> str | None:
    """Download one day's master.idx. Missing days (weekends/holidays) return None."""
    url = master_idx_url(day)
    cache_dir = cache_dir or (config.CACHE_DIR / "sec" / "daily-index")
    path = cache_dir / f"master.{day.strftime('%Y%m%d')}.idx"
    missing = path.with_suffix(path.suffix + ".404")
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    if missing.exists():
        return None
    resp = http.get(url)
    if resp.status_code == 404:
        missing.parent.mkdir(parents=True, exist_ok=True)
        missing.write_text("", encoding="utf-8")
        return None
    resp.raise_for_status()
    text = resp.content.decode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def collect_period_filings(
    http,
    as_of: date,
    lookback_days: int,
    *,
    cache_dir: Path | None = None,
    forms: set[str] | None = None,
) -> tuple[list[DailyFiling], list[str], list[str]]:
    """Filings from the rolling lookback window. Returns (filings, index dates found, dates missing)."""
    found: list[DailyFiling] = []
    present: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for day in lookback_dates(as_of, lookback_days):
        text = fetch_master_idx(http, day, cache_dir=cache_dir)
        iso = day.isoformat()
        if text is None:
            missing.append(iso)
            continue
        present.append(iso)
        for row in parse_master_idx(text, forms=forms):
            if row.accn in seen:
                continue
            seen.add(row.accn)
            found.append(row)
    return found, present, missing
