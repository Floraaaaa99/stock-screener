"""Discover Item 2.02 8-K earnings exhibits from the SEC filing document list.

Does not parse financial tables. Unrelated 8-Ks and investor decks are rejected.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .. import config
from .facts import filing_url

log = logging.getLogger(__name__)

ITEM_202_RE = re.compile(r"item\s*2\s*\.\s*02\b", re.I)
ITEM_202_TITLE_RE = re.compile(
    r"item\s*2\s*\.\s*02.{0,80}results of operations|results of operations and financial condition",
    re.I,
)
EXHIBIT_TYPE_RE = re.compile(r"^ex-?99(?:\.?\d+)?(?:[a-z])?$", re.I)
EX_99_1_RE = re.compile(r"^ex-?99(?:\.?0?1)$", re.I)
REJECT_DESC_RE = re.compile(
    r"\b(presentation|transcript|webcast|investor\s+deck|slide\s+deck|slides?|script)\b",
    re.I,
)
EARNINGS_DESC_RE = re.compile(
    r"earnings|results of operations|financial (results|statements|condition)|press release",
    re.I,
)
EARNINGS_BODY_RE = re.compile(
    r"three months ended|statements? of (income|operations|earnings)|condensed consolidated",
    re.I,
)
PRIMARY_FORM_RE = re.compile(r"^8-k(/a)?$", re.I)
SKIP_INDEX_NAMES = re.compile(
    r"(index|filingSummary|xsl|xml|xsd|gif|jpg|jpeg|png|css|\.js$)",
    re.I,
)

FetchText = Callable[[str, str, str], str | None]


@dataclass(frozen=True)
class FilingDocument:
    name: str
    doc_type: str
    description: str
    url: str


@dataclass
class EarningsExhibit:
    item_202: bool
    exhibit: FilingDocument | None
    documents: list[FilingDocument] = field(default_factory=list)
    primary: FilingDocument | None = None
    reason: str | None = None
    filing_url: str = ""

    @property
    def is_earnings(self) -> bool:
        return self.item_202 and self.exhibit is not None


def archives_base(cik: str, accn: str) -> str:
    return config.SEC_ARCHIVES_URL.format(cik=int(cik), accn_nodash=accn.replace("-", ""))


def filing_index_url(cik: str, accn: str) -> str:
    return f"{archives_base(cik, accn)}{accn}-index.htm"


def filing_index_json_url(cik: str, accn: str) -> str:
    return f"{archives_base(cik, accn)}index.json"


def document_url(cik: str, accn: str, name: str) -> str:
    return archives_base(cik, accn) + name.lstrip("/")


class _LinkTableParser(HTMLParser):
    """Collect rows from the EDGAR filing index table (Seq / Description / Document / Type)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._href: str | None = None
        self._in_table = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == "table":
            self._depth += 1
            self._in_table = True
        if not self._in_table:
            return
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._href = None
        elif tag == "a" and self._cell is not None:
            self._href = attrs_d.get("href")

    def handle_endtag(self, tag):
        if tag == "table":
            self._depth -= 1
            if self._depth <= 0:
                self._in_table = False
                self._depth = 0
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            text = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            if self._href and not text:
                text = self._href.rsplit("/", 1)[-1]
            if self._href:
                self._row.append(f"{text}\x1f{self._href}")
            else:
                self._row.append(text)
            self._cell = None
            self._href = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _cell_parts(cell: str) -> tuple[str, str | None]:
    if "\x1f" in cell:
        text, href = cell.split("\x1f", 1)
        name = href.rsplit("/", 1)[-1].split("?")[0]
        return text.strip(), name
    return cell.strip(), None


def parse_index_htm(html: str, cik: str, accn: str) -> list[FilingDocument]:
    parser = _LinkTableParser()
    parser.feed(html)
    docs: list[FilingDocument] = []
    seen: set[str] = set()
    header_idx = None
    for i, row in enumerate(parser.rows):
        joined = " ".join(_cell_parts(c)[0] for c in row).lower()
        if "document" in joined and ("type" in joined or "description" in joined):
            header_idx = i
            break
    body = parser.rows[header_idx + 1 :] if header_idx is not None else parser.rows
    for row in body:
        texts: list[str] = []
        href_name: str | None = None
        for cell in row:
            text, name = _cell_parts(cell)
            texts.append(text)
            if name and not SKIP_INDEX_NAMES.search(name):
                href_name = name
        if not href_name:
            continue
        doc_type = ""
        description = ""
        for text in texts:
            compact = text.replace(" ", "")
            if PRIMARY_FORM_RE.match(text) or EXHIBIT_TYPE_RE.match(compact) or EXHIBIT_TYPE_RE.match(text):
                doc_type = compact if EXHIBIT_TYPE_RE.match(compact) else text
            elif text.lower() not in {href_name.lower(), "edgar"} and not re.fullmatch(r"\d+", text):
                if not description or len(text) > len(description):
                    description = text
        if not doc_type:
            if PRIMARY_FORM_RE.match(href_name.replace(".", "")):
                doc_type = "8-K"
            elif EXHIBIT_TYPE_RE.match(href_name.replace("_", "-").split(".")[0]):
                doc_type = href_name.split(".")[0]
        key = href_name.lower()
        if key in seen:
            continue
        seen.add(key)
        docs.append(
            FilingDocument(
                name=href_name,
                doc_type=doc_type or href_name,
                description=description,
                url=document_url(cik, accn, href_name),
            )
        )
    return docs


def parse_index_json(payload: dict | str, cik: str, accn: str) -> list[FilingDocument]:
    data = json.loads(payload) if isinstance(payload, str) else payload
    items = ((data or {}).get("directory") or {}).get("item") or []
    docs: list[FilingDocument] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or SKIP_INDEX_NAMES.search(name):
            continue
        docs.append(
            FilingDocument(
                name=name,
                doc_type=name,
                description="",
                url=document_url(cik, accn, name),
            )
        )
    return docs


def has_item_202(text: str | None) -> bool:
    if not text:
        return False
    if ITEM_202_TITLE_RE.search(text):
        return True
    return bool(ITEM_202_RE.search(text))


def _is_exhibit(doc: FilingDocument) -> bool:
    compact = doc.doc_type.replace(" ", "")
    return bool(EXHIBIT_TYPE_RE.match(compact) or EXHIBIT_TYPE_RE.match(doc.name.split(".")[0].replace("_", "-")))


def _is_primary(doc: FilingDocument) -> bool:
    if PRIMARY_FORM_RE.match(doc.doc_type.strip()):
        return True
    name = doc.name.lower()
    return bool(re.search(r"(^|[^a-z])8-?k", name)) and "ex-" not in name and "ex99" not in name


def _is_rejected_exhibit(doc: FilingDocument) -> bool:
    return bool(REJECT_DESC_RE.search(doc.description) or REJECT_DESC_RE.search(doc.name))


def _exhibit_rank(doc: FilingDocument, peek: str | None) -> tuple:
    desc = f"{doc.description} {doc.name}"
    earnings_desc = bool(EARNINGS_DESC_RE.search(desc))
    peek_hit = bool(peek and EARNINGS_BODY_RE.search(peek))
    type_key = doc.doc_type.replace(" ", "")
    name_key = doc.name.split(".")[0].replace("_", "-")
    is_991 = bool(EX_99_1_RE.match(type_key) or EX_99_1_RE.match(name_key))
    return (earnings_desc, peek_hit, is_991)


def select_earnings_exhibit(
    documents: list[FilingDocument],
    *,
    peek_text: dict[str, str] | None = None,
) -> FilingDocument | None:
    """Pick the earnings-release exhibit. Investor presentations are never selected."""
    exhibits = [d for d in documents if _is_exhibit(d) and not _is_rejected_exhibit(d)]
    if not exhibits:
        return None
    ranked = sorted(
        exhibits,
        key=lambda d: _exhibit_rank(d, (peek_text or {}).get(d.name)),
        reverse=True,
    )
    best = ranked[0]
    score = _exhibit_rank(best, (peek_text or {}).get(best.name))
    if not any(score[:2]) and len(exhibits) > 1 and not score[2]:
        return None
    if not any(score[:2]) and not score[2]:
        # A lone EX-99.2 with no earnings description is not assumed to be financials.
        return None
    return best


def discover_earnings_exhibit(
    cik: str,
    accn: str,
    fetch: FetchText,
    *,
    form: str = "8-K",
) -> EarningsExhibit:
    """Inspect the SEC document list and Item 2.02; locate the earnings exhibit if present."""
    filing = filing_url(cik, accn)
    index_html = fetch(cik, accn, f"{accn}-index.htm")
    documents: list[FilingDocument] = []
    if index_html:
        documents = parse_index_htm(index_html, cik, accn)
    index_json = None
    if not documents:
        index_json = fetch(cik, accn, "index.json")
        if index_json:
            documents = parse_index_json(index_json, cik, accn)

    primary = next((d for d in documents if _is_primary(d)), None)
    if primary is None:
        for guess in (f"{accn}.txt", "d8k.htm", "8k.htm", f"{form.lower().replace('/', '')}.htm"):
            text = fetch(cik, accn, guess)
            if text:
                primary = FilingDocument(guess, form, "Current report", document_url(cik, accn, guess))
                documents.append(primary)
                break

    if not documents and primary is None and not index_html and not index_json:
        return EarningsExhibit(
            item_202=False,
            exhibit=None,
            documents=[],
            primary=None,
            reason="index_unavailable",
            filing_url=filing,
        )

    primary_text = fetch(cik, accn, primary.name) if primary else None
    item_202 = has_item_202(primary_text) or has_item_202(index_html)
    if not item_202:
        return EarningsExhibit(
            item_202=False,
            exhibit=None,
            documents=documents,
            primary=primary,
            reason="not_item_202",
            filing_url=filing,
        )

    peek: dict[str, str] = {}
    for doc in documents:
        if _is_exhibit(doc) and not _is_rejected_exhibit(doc):
            body = fetch(cik, accn, doc.name)
            if body:
                peek[doc.name] = body[:12000]
    exhibit = select_earnings_exhibit(documents, peek_text=peek)
    if exhibit is None:
        return EarningsExhibit(
            item_202=True,
            exhibit=None,
            documents=documents,
            primary=primary,
            reason="no_earnings_exhibit",
            filing_url=filing,
        )
    return EarningsExhibit(
        item_202=True,
        exhibit=exhibit,
        documents=documents,
        primary=primary,
        reason=None,
        filing_url=filing,
    )
