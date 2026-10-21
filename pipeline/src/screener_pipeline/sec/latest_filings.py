"""SEC Latest Filings (browse-edgar getcurrent).

The public Latest Filings page lists filings for the **current official filing
date** only, including after-hours submissions from the previous filing day.
It is not a historical archive: walking `start` / `dateb` pages retrieves more
of *today's* list, not prior calendar days. A missed run cannot be recovered
from getcurrent alone.

Complete daily coverage is `master.idx` under /Archives/edgar/daily-index
(indexes update nightly starting about 10:00 p.m. ET). Callers must merge both
sources and keep `lastSuccessfulSyncAt` for lookback.

browse-edgar caps `count` at 40. Paginate with `start`, and if a page repeats
the same accessions, walk backward with `dateb=YYYYMMDDHHmmss` from the oldest
acceptance timestamp on that page.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .daily_index import DailyFiling, accession_from_filename
from .facts import LATEST_DISCOVERY_FORMS

# https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&output=atom
SEC_CURRENT_ATOM_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_CURRENT_PAGE_SIZE = 40
_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
_TITLE_RE = re.compile(r"^(?P<form>\S+)\s+-\s+(?P<name>.+?)\s+\((?P<cik>\d+)\)")
_ACCNO_RE = re.compile(r"AccNo:\s*(?:</b>)?\s*(\d{10}-\d{2}-\d{6})", re.I)
_FILED_RE = re.compile(r"Filed:\s*(?:</b>)?\s*(\d{4}-\d{2}-\d{2})", re.I)


def current_atom_url(
    form: str,
    *,
    start: int = 0,
    count: int = SEC_CURRENT_PAGE_SIZE,
    dateb: str | None = None,
) -> str:
    query = {
        "action": "getcurrent",
        "type": form,
        "owner": "include",
        "count": str(min(count, SEC_CURRENT_PAGE_SIZE)),
        "output": "atom",
    }
    if start:
        query["start"] = str(start)
    if dateb:
        query["dateb"] = dateb
    return f"{SEC_CURRENT_ATOM_URL}?{urlencode(query)}"


def dateb_from_accepted(accepted: datetime) -> str:
    return accepted.strftime("%Y%m%d%H%M%S")


def parse_current_atom(text: str, *, source: str = "latest") -> list[DailyFiling]:
    """Parse one getcurrent Atom page. Malformed entries are skipped."""
    if not text or not text.strip():
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    entries = list(root.findall("a:entry", _ATOM_NS)) or list(root.findall("entry"))
    out: list[DailyFiling] = []
    seen: set[str] = set()
    for entry in entries:
        filing = _entry_to_filing(entry, source=source)
        if filing is None or filing.accn in seen:
            continue
        seen.add(filing.accn)
        out.append(filing)
    return out


def _find(entry: ET.Element, name: str) -> ET.Element | None:
    found = entry.find(f"a:{name}", _ATOM_NS)
    if found is not None:
        return found
    return entry.find(name)


def _text(entry: ET.Element, name: str) -> str:
    found = _find(entry, name)
    return (found.text or "") if found is not None else ""


def _entry_to_filing(entry: ET.Element, *, source: str) -> DailyFiling | None:
    title = _text(entry, "title")
    summary = _text(entry, "summary")
    updated = _text(entry, "updated")
    category = _find(entry, "category")
    link = _find(entry, "link")
    href = (link.get("href") if link is not None else "") or ""

    form = (category.get("term") if category is not None else "") or ""
    match = _TITLE_RE.match(title.strip())
    if match:
        form = form or match.group("form")
        name = match.group("name").strip()
        try:
            cik = str(int(match.group("cik"))).zfill(10)
        except ValueError:
            return None
    else:
        return None
    if form not in LATEST_DISCOVERY_FORMS:
        return None
    accn = accession_from_filename(href)
    if not accn:
        found = _ACCNO_RE.search(summary)
        accn = found.group(1) if found else None
    if not accn:
        return None
    filed = _parse_filed(summary, updated)
    if filed is None:
        return None
    accepted = _parse_accepted(updated)
    filename = href.split("sec.gov/", 1)[-1] if "sec.gov/" in href else href
    return DailyFiling(
        cik=cik,
        name=name,
        form=form,
        filed=filed,
        filename=filename,
        accn=accn,
        accepted=accepted,
        source=source,
    )


def _parse_filed(summary: str, updated: str) -> date | None:
    match = _FILED_RE.search(summary)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass
    accepted = _parse_accepted(updated)
    return accepted.date() if accepted else None


def _parse_accepted(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _oldest_accepted(rows: list[DailyFiling]) -> datetime | None:
    stamps = [row.accepted for row in rows if row.accepted is not None]
    return min(stamps) if stamps else None


def fetch_latest_filings(
    http,
    *,
    forms: tuple[str, ...] | list[str] | None = None,
    page_size: int = SEC_CURRENT_PAGE_SIZE,
    max_pages: int = 50,
) -> tuple[list[DailyFiling], dict]:
    """Page through getcurrent for each form type until a page is empty.

    Does not provide historical coverage. Callers must also read master.idx.
    """
    wanted = tuple(forms) if forms is not None else tuple(sorted(LATEST_DISCOVERY_FORMS))
    found: list[DailyFiling] = []
    seen: set[str] = set()
    pages = 0
    count = min(page_size, SEC_CURRENT_PAGE_SIZE)
    for form in wanted:
        start = 0
        dateb: str | None = None
        for _page in range(max_pages):
            url = current_atom_url(form, start=start, count=count, dateb=dateb)
            resp = http.get(url)
            resp.raise_for_status()
            text = resp.content.decode("utf-8", errors="replace")
            rows = parse_current_atom(text)
            pages += 1
            if not rows:
                break
            new_rows = [row for row in rows if row.accn not in seen]
            if not new_rows:
                oldest = _oldest_accepted(rows)
                if dateb is None and oldest is not None:
                    dateb = dateb_from_accepted(oldest)
                    start = 0
                    continue
                break
            for row in new_rows:
                seen.add(row.accn)
                found.append(row)
            if len(rows) < count:
                break
            if dateb is None:
                start += count
            else:
                oldest = _oldest_accepted(rows)
                if oldest is None:
                    break
                nxt = dateb_from_accepted(oldest)
                if nxt == dateb:
                    break
                dateb = nxt
    return found, {"pages": pages, "forms": list(wanted), "hits": len(found)}


def start_from_url(url: str) -> int:
    values = parse_qs(urlparse(url).query).get("start") or ["0"]
    try:
        return int(values[0])
    except ValueError:
        return 0


def with_start(url: str, start: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["start"] = [str(start)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
