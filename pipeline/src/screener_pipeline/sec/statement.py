"""Read the income statement exactly as presented in a filing (EDGAR's rendered R*.htm pages).

Used to confirm which XBRL concept a company presents as revenue on the face of its income statement,
and to validate pipeline values against the filing itself.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser

_INCOME_RX = re.compile(r"operations|income|earnings|loss", re.I)
_NOT_INCOME_RX = re.compile(
    r"parenthetical|balance|financial condition|cash flow|stockholders|shareholders|changes in|deficit", re.I
)
# "Statements of Comprehensive Income" alone is not the income statement; "Operations and
# Comprehensive Loss" is.
_COMPREHENSIVE_ONLY_RX = re.compile(r"statements?\s+of\s+comprehensive", re.I)
_TOTAL_REVENUE_RX = re.compile(
    r"^\s*(total\s+)?(net\s+)?(revenues?|sales|net sales|revenues?,\s*net|operating revenues?)"
    r"(\s*,\s*net)?(\s+and other income)?\s*$|^\s*total\s+(net\s+)?(revenues?|sales)\b",
    re.I,
)


def is_total_revenue_label(label: str) -> bool:
    return bool(_TOTAL_REVENUE_RX.search(label))


def income_statement_candidates(filing_summary_xml: str) -> list[tuple[str, str]]:
    """(html_file_name, short_name) of likely income statements, best first.

    Statements of operations rank first, combined "operations and comprehensive income" next, and a
    standalone "statement of comprehensive income" last (some companies present only that one).
    """
    root = ET.fromstring(filing_summary_xml)
    candidates: list[tuple[int, int, str, str]] = []
    for rep in root.iter("Report"):
        cat = (rep.findtext("MenuCategory") or "").strip()
        short = rep.findtext("ShortName") or ""
        html = rep.findtext("HtmlFileName")
        if cat != "Statements" or not html:
            continue
        if not _INCOME_RX.search(short) or _NOT_INCOME_RX.search(short):
            continue
        if _COMPREHENSIVE_ONLY_RX.search(short):
            rank = 2
        elif re.search(r"comprehensive", short, re.I):
            rank = 1
        else:
            rank = 0
        pos = int(rep.findtext("Position") or 999)
        candidates.append((rank, pos, html, short))
    candidates.sort()
    return [(c[2], c[3]) for c in candidates]


def has_revenue_line(st: Statement) -> bool:
    return any(
        re.search(r"revenue|sales", r.concept.split(":", 1)[-1], re.I) or re.search(r"revenue|sales", r.label, re.I)
        for r in st.rows
    )


@dataclass
class StatementColumn:
    months: int | None
    end: date | None


@dataclass
class StatementRow:
    concept: str
    label: str
    values: list[float | None]


@dataclass
class Statement:
    title: str
    scale: float
    columns: list[StatementColumn]
    rows: list[StatementRow] = field(default_factory=list)

    def value(self, row: StatementRow, months: int, end: date) -> float | None:
        for i, col in enumerate(self.columns):
            if col.months == months and col.end == end and i < len(row.values) and row.values[i] is not None:
                return row.values[i]
        return None


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict]] = []
        self._row: list[dict] | None = None
        self._cell: dict | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._depth += 1
        if self._depth != 1:
            return
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {
                "tag": tag,
                "class": a.get("class", ""),
                "colspan": int(a.get("colspan", "1") or 1),
                "text": "",
                "defref": None,
            }
        elif tag == "a" and self._cell is not None:
            m = re.search(r"defref_([A-Za-z0-9-]+)_([A-Za-z0-9_]+)", a.get("onclick", ""))
            if m:
                self._cell["defref"] = f"{m.group(1)}:{m.group(2)}"
        elif tag == "br" and self._cell is not None:
            self._cell["text"] += " "

    def handle_endtag(self, tag):
        if tag == "table":
            self._depth -= 1
            return
        if self._depth != 1:
            return
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._cell["text"] = re.sub(r"\s+", " ", self._cell["text"]).strip()
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data


def _parse_number(text: str) -> float | None:
    t = text.replace("$", "").replace(",", "").replace("\u00a0", " ").strip()
    if not t or not re.search(r"\d", t):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("() ")
    try:
        v = float(t.split()[0])
    except ValueError:
        return None
    return -v if neg else v


def _parse_date(text: str) -> date | None:
    t = text.replace(".", "").strip()
    t = re.sub(r"^Sept\b", "Sep", t)
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def _months(text: str) -> int | None:
    m = re.search(r"(\d+)\s+Months?\s+Ended", text, re.I)
    if m:
        return int(m.group(1))
    if re.search(r"\b(Year|Fiscal Year)s?\s+Ended\b", text, re.I):
        return 12
    return None


def parse_statement_html(html: str) -> Statement:
    p = _TableParser()
    p.feed(html)
    rows = p.rows
    if not rows:
        return Statement(title="", scale=1.0, columns=[])

    head_rows = [r for r in rows[:3] if r and all(c["tag"] == "th" for c in r)]
    title = head_rows[0][0]["text"] if head_rows else ""
    scale = 1.0
    m = re.search(r"\$\s*in\s+(Thousands|Millions|Billions)", title, re.I)
    if m:
        scale = {"thousands": 1e3, "millions": 1e6, "billions": 1e9}[m.group(1).lower()]

    # Columns are physical grid columns (colspans expanded); footnote cells occupy their own columns.
    columns: list[StatementColumn] = []
    if len(head_rows) >= 2:
        groups: list[int | None] = []
        for c in head_rows[0][1:]:
            groups.extend([_months(c["text"])] * c["colspan"])
        dates: list[date | None] = []
        for c in head_rows[1]:
            dates.extend([_parse_date(c["text"])] * c["colspan"])
        for i, d in enumerate(dates):
            columns.append(StatementColumn(groups[i] if i < len(groups) else None, d))
    elif head_rows:
        for c in head_rows[0][1:]:
            for _ in range(c["colspan"]):
                columns.append(StatementColumn(_months(c["text"]), _parse_date(c["text"])))

    # The title cell can span the label column plus a footnote column; data rows then carry that
    # footnote cell before the first value.
    lead = head_rows[0][0]["colspan"] if head_rows else 1
    st = Statement(title=title, scale=scale, columns=columns)
    for r in rows[len(head_rows):]:
        if not r or r[0]["tag"] != "td" or not r[0].get("defref"):
            continue
        values: list[float | None] = []
        for c in r[1:]:
            v = _parse_number(c["text"]) if c["tag"] == "td" and "fn" not in c["class"].split() else None
            values.append(v * scale if v is not None else None)
            values.extend([None] * (c["colspan"] - 1))
        st.rows.append(StatementRow(concept=r[0]["defref"], label=r[0]["text"], values=values[lead - 1:]))
    return st


@dataclass
class StatementEvidence:
    """Revenue-like rows on the face of one filing's income statement, for a given period."""

    accn: str
    form: str
    url: str
    title: str
    months: int
    end: date
    rows: list[tuple[str, str, float | None]]

    def concept_rows(self, concept: str) -> list[tuple[str, str, float | None]]:
        return [r for r in self.rows if r[0] == f"us-gaap:{concept}"]


def evidence_from_statement(
    st: Statement, accn: str, form: str, url: str, months: int, end: date
) -> StatementEvidence:
    rows: list[tuple[str, str, float | None]] = []
    for row in st.rows:
        name = row.concept.split(":", 1)[-1]
        if re.search(r"revenue|sales", name, re.I) or re.search(r"revenue|sales", row.label, re.I):
            rows.append((row.concept, row.label, st.value(row, months, end)))
    return StatementEvidence(accn, form, url, st.title, months, end, rows)
