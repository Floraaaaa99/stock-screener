"""Deterministic GAAP extraction from 8-K earnings-release HTML tables.

Never invents values, never substitutes non-GAAP, and never treats missing as zero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser

from .sec.statement import is_net_income_label, is_total_revenue_label

AWAITING_10Q_LABEL = "8-K Earnings Release — Awaiting 10-Q Verification"
VERIFIED_10Q_LABEL = "10-Q/10-K Verified"
SOURCE_TYPE_8K = "8k_earnings_release"
SOURCE_TYPE_FACTS = "company_facts"

SCALE_WORDS = {"thousand": 1e3, "thousands": 1e3, "million": 1e6, "millions": 1e6, "billion": 1e9, "billions": 1e9}
MISSING_TOKENS = {"", "—", "–", "-", "n/a", "na", "nm", "*", "**", "— —"}

NON_GAAP_RE = re.compile(r"\bnon[\s-]*gaap\b|\badjusted\b|\bnon[\s-]*ifrs\b", re.I)
GAAP_RE = re.compile(r"\bgaap\b|condensed consolidated|consolidated statements?", re.I)
PERCENT_RE = re.compile(r"%|percent", re.I)
YTD_RE = re.compile(r"\b(six|nine|six\-month|nine\-month)\s+months?\s+ended\b", re.I)
QUARTER_RE = re.compile(r"\bthree\s+months?\s+ended\b|\bquarter\s+ended\b|\bthree\-month", re.I)
ANNUAL_RE = re.compile(r"\b(year|twelve\s+months?|fiscal\s+year)s?\s+ended\b", re.I)
QUARTER_NAME_RE = re.compile(
    r"\b(?:first|1st|q\s*1)\s+quarter\b|\bq1\b|"
    r"\b(?:second|2nd|q\s*2)\s+quarter\b|\bq2\b|"
    r"\b(?:third|3rd|q\s*3)\s+quarter\b|\bq3\b|"
    r"\b(?:fourth|4th|q\s*4)\s+quarter\b|\bq4\b",
    re.I,
)
FY_RE = re.compile(r"\bf(?:iscal\s+)?y(?:ear)?\s*['’]?\s*(\d{2,4})\b", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")
DATE_RE = re.compile(
    r"\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+\d{1,2},?\s+20\d{2})\b",
    re.I,
)

IS_HINT_RE = re.compile(r"statements? of (income|operations|earnings)|income statement", re.I)
BS_HINT_RE = re.compile(r"balance sheet|statements? of financial (position|condition)", re.I)
CF_HINT_RE = re.compile(r"statements? of cash flows?|cash flow statement", re.I)
PRESENTATION_HINT_RE = re.compile(r"\b(slide|webcast|investor presentation|non-gaap reconciliation)\b", re.I)

EPS_RE = re.compile(
    r"^(diluted\s+)?(net\s+)?(income|earnings|loss).{0,40}per\s+(common\s+)?(share|unit).{0,20}diluted"
    r"|^diluted\s+(net\s+)?(income|earnings|loss)\s+per\s+(share|unit)"
    r"|earnings per share[^\n]{0,20}diluted",
    re.I,
)
BASIC_EPS_RE = re.compile(r"\bbasic\b", re.I)
COGS_RE = re.compile(r"^(total\s+)?cost of (revenue|sales|goods sold)\b", re.I)
GP_RE = re.compile(r"^(total\s+)?gross (profit|margin|income)\b", re.I)
OPINC_RE = re.compile(
    r"^(income|loss|profit) from operations\b|^operating (income|loss|profit)\b"
    r"|^\s*income \(loss\) from operations",
    re.I,
)
CASH_RE = re.compile(r"^cash and cash equivalents\b|^cash, cash equivalents\b", re.I)
CASH_PLUS_RE = re.compile(r"restricted|marketable|short-term investments|securities", re.I)
ASSETS_RE = re.compile(r"^total assets\b", re.I)
LIAB_RE = re.compile(r"^total liabilities\b", re.I)
DEBT_RE = re.compile(r"^total debt\b|^total borrowings\b", re.I)
ST_DEBT_RE = re.compile(
    r"current (portion of )?(long-term )?(debt|borrowings)|short-term (debt|borrowings)",
    re.I,
)
LT_DEBT_RE = re.compile(r"^long-term (debt|borrowings)\b|^long term (debt|borrowings)\b", re.I)
INV_RE = re.compile(r"^inventor(y|ies)\b", re.I)
OCF_RE = re.compile(
    r"net cash (provided by|from|used in) operating activities|^cash from operations\b",
    re.I,
)
CAPEX_RE = re.compile(
    r"purchases? of (property|ppe|property and equipment)|capital expenditures?"
    r"|payments? for (property and equipment|ppe)",
    re.I,
)
FCF_RE = re.compile(r"^free cash flow\b", re.I)
ADJ_EBITDA_RE = re.compile(r"adjusted ebitda|non-gaap net income|adjusted net income", re.I)

LOSS_LABEL_RE = re.compile(r"\bloss\b", re.I)
INCOME_OR_LOSS_RE = re.compile(r"income\s*\(\s*loss\s*\)|profit\s*\(\s*loss\s*\)|loss\s*\(\s*income\s*\)", re.I)


@dataclass
class ExtractedMetric:
    key: str
    value: float
    unit: str
    scale: float
    label: str
    period_kind: str
    fiscal_year: int | None
    fiscal_quarter: int | None
    period_end: date | None
    period_start: date | None
    gaap: bool
    method: str = "reported"
    formula: str | None = None


@dataclass
class EightKExtraction:
    status: str
    reason: str | None
    item_202: bool
    exhibit_name: str | None
    exhibit_url: str | None
    filing_url: str | None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    period_end: date | None = None
    period_start: date | None = None
    currency: str | None = "USD"
    metrics: dict[str, ExtractedMetric] = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)

    def to_state_metrics(self) -> dict:
        out = {}
        for key, metric in self.metrics.items():
            out[key] = {
                "value": metric.value,
                "unit": metric.unit,
                "scale": metric.scale,
                "label": metric.label,
                "periodKind": metric.period_kind,
                "fiscalYear": metric.fiscal_year,
                "fiscalQuarter": metric.fiscal_quarter,
                "periodEnd": metric.period_end.isoformat() if metric.period_end else None,
                "periodStart": metric.period_start.isoformat() if metric.period_start else None,
                "gaap": metric.gaap,
                "method": metric.method,
                "formula": metric.formula,
            }
        return out


class _GridParser(HTMLParser):
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
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = {
                "tag": tag,
                "text": "",
                "colspan": int(a.get("colspan", "1") or 1),
            }
        elif tag == "br" and self._cell is not None:
            self._cell["text"] += " "

    def handle_endtag(self, tag):
        if tag == "table":
            self._depth -= 1
            return
        if self._depth != 1:
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._cell["text"] = re.sub(r"\s+", " ", self._cell["text"]).strip()
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(c["text"] for c in self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data


def _expand_row(row: list[dict]) -> list[str]:
    cells: list[str] = []
    for cell in row:
        cells.extend([cell["text"]] * max(1, cell["colspan"]))
    return cells


def iter_tables(html: str) -> list[tuple[str, list[list[str]]]]:
    tables: list[tuple[str, list[list[str]]]] = []
    for match in re.finditer(r"<table\b.*?</table>", html, re.I | re.S):
        before = html[max(0, match.start() - 1800) : match.start()]
        context = re.sub(r"<[^>]+>", " ", before)
        context = re.sub(r"\s+", " ", context).strip()
        parser = _GridParser()
        try:
            parser.feed(match.group(0))
        except Exception:  # noqa: BLE001 — skip malformed tables
            continue
        grid = [_expand_row(r) for r in parser.rows]
        if grid:
            tables.append((context, grid))
    return tables


def parse_number(text: str) -> float | None:
    raw = (text or "").replace("\u00a0", " ").replace("$", "").strip()
    raw = raw.replace(",", "")
    if PERCENT_RE.search(raw):
        return None
    compact = raw.lower().strip(" .")
    if compact in MISSING_TOKENS:
        return None
    if not re.search(r"\d", raw):
        return None
    neg = bool(re.search(r"^\(.*\)$", raw.strip())) or raw.strip().startswith("−") or raw.strip().startswith("-")
    cleaned = raw.strip().strip("()").replace("−", "-").strip()
    cleaned = re.sub(r"[*†‡§]+$", "", cleaned).strip()
    if re.search(r"\d.+\d", cleaned) and not re.fullmatch(r"-?\d+(\.\d+)?", cleaned.replace(" ", "")):
        parts = re.findall(r"-?\d+(?:\.\d+)?", cleaned)
        if len(parts) != 1:
            return None
        cleaned = parts[0]
    try:
        value = float(cleaned.split()[0])
    except (ValueError, IndexError):
        return None
    return -abs(value) if neg else value


def parse_scale(text: str) -> float:
    blob = text.lower()
    match = re.search(r"\b(in|\$ in)\s+(thousands?|millions?|billions?)\b", blob)
    if match:
        return SCALE_WORDS[match.group(2)]
    match = re.search(r"\((thousands?|millions?|billions?)\)", blob)
    if match:
        return SCALE_WORDS[match.group(1)]
    return 1.0


def parse_date_text(text: str) -> date | None:
    raw = re.sub(r"^Sept\b", "Sep", (text or "").replace(".", ""), flags=re.I).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def fiscal_quarter_from_end(end: date | None) -> int | None:
    if end is None:
        return None
    return (end.month - 1) // 3 + 1


def quarter_from_name(text: str) -> int | None:
    blob = text.lower()
    mapping = (
        (r"first|1st|q\s*1\b|\bq1\b", 1),
        (r"second|2nd|q\s*2\b|\bq2\b", 2),
        (r"third|3rd|q\s*3\b|\bq3\b", 3),
        (r"fourth|4th|q\s*4\b|\bq4\b", 4),
    )
    for pattern, number in mapping:
        if re.search(pattern, blob):
            return number
    return None


def period_kind(text: str) -> str | None:
    if YTD_RE.search(text):
        return "ytd"
    if QUARTER_RE.search(text) or quarter_from_name(text):
        return "quarterly"
    if ANNUAL_RE.search(text):
        return "annual"
    return None


@dataclass
class ColumnMeta:
    kind: str | None
    end: date | None
    year: int | None
    gaap: bool
    text: str


def _classify_columns(grid: list[list[str]], context: str) -> list[ColumnMeta]:
    width = max(len(r) for r in grid)
    header_rows = []
    for row in grid[:4]:
        data_values = []
        for cell in row[1:]:
            if re.fullmatch(r"20\d{2}", (cell or "").strip()):
                continue
            number = parse_number(cell)
            if number is not None:
                data_values.append(number)
        if data_values:
            break
        header_rows.append(row)
    if not header_rows:
        header_rows = grid[:1]
    combined = [""] * width
    for row in header_rows:
        for i in range(width):
            cell = row[i] if i < len(row) else ""
            combined[i] = (combined[i] + " " + cell).strip()
    context_kind = period_kind(context)
    context_q = quarter_from_name(context)
    context_end = None
    dates = [parse_date_text(m.group(1)) for m in DATE_RE.finditer(context)]
    dates = [d for d in dates if d]
    if dates:
        context_end = dates[0]
    cols: list[ColumnMeta] = []
    for i, text in enumerate(combined):
        kind = period_kind(text) or (context_kind if i else None)
        end = parse_date_text(text)
        if end is None:
            found = [parse_date_text(m.group(1)) for m in DATE_RE.finditer(text)]
            found = [d for d in found if d]
            end = found[-1] if found else None
        year = None
        years = YEAR_RE.findall(text)
        if years:
            year = int(years[-1])
        elif end:
            year = end.year
        if end is None and year and context_end and context_end.year != year:
            try:
                end = context_end.replace(year=year)
            except ValueError:
                end = context_end
        elif end is None:
            end = context_end
        gaap = not bool(NON_GAAP_RE.search(text))
        if i == 0:
            cols.append(ColumnMeta(None, None, None, True, text))
        else:
            if kind is None and context_q and (not text or YEAR_RE.search(text)):
                kind = "quarterly"
            cols.append(ColumnMeta(kind, end, year, gaap, text))
    return cols


def _norm_label(label: str) -> str:
    text = re.sub(r"\s+", " ", (label or "").replace("\n", " ")).strip()
    return re.sub(r"[:.]+$", "", text)


def _is_non_gaap_label(label: str) -> bool:
    return bool(NON_GAAP_RE.search(label) or ADJ_EBITDA_RE.search(label))


def _match_metric(label: str, statement: str) -> str | None:
    text = _norm_label(label)
    if not text or _is_non_gaap_label(text):
        return None
    if statement == "is":
        if EPS_RE.search(text) and not BASIC_EPS_RE.search(text.split("per")[0] if False else text):
            if "diluted" in text.lower() or EPS_RE.search(text):
                if "basic" in text.lower() and "diluted" not in text.lower():
                    return None
                return "dilutedEps"
        if is_total_revenue_label(text) or re.match(r"^(total\s+)?(net\s+)?revenues?\s*$", text, re.I):
            return "revenue"
        if COGS_RE.search(text):
            return "costOfRevenue"
        if GP_RE.search(text) and "%" not in text:
            return "grossProfit"
        if OPINC_RE.search(text):
            return "operatingIncome"
        if is_net_income_label(text):
            return "netIncome"
    elif statement == "bs":
        if CASH_RE.search(text) and not CASH_PLUS_RE.search(text):
            return "cash"
        if ASSETS_RE.search(text):
            return "totalAssets"
        if LIAB_RE.search(text) and "equity" not in text.lower():
            return "totalLiabilities"
        if DEBT_RE.search(text):
            return "totalDebt"
        if ST_DEBT_RE.search(text):
            return "shortTermDebt"
        if LT_DEBT_RE.search(text) and "current" not in text.lower():
            return "longTermDebt"
        if INV_RE.search(text) and "turnover" not in text.lower():
            return "inventory"
    elif statement == "cf":
        if OCF_RE.search(text):
            return "operatingCashFlow"
        if CAPEX_RE.search(text) and "proceeds" not in text.lower():
            return "capitalExpenditures"
        if FCF_RE.search(text) and not NON_GAAP_RE.search(text):
            # Explicit FCF is often non-GAAP; only keep when the table itself is GAAP-labeled.
            return "freeCashFlow"
    return None


def _apply_loss_sign(key: str, label: str, value: float) -> float | None:
    if key not in {"operatingIncome", "netIncome", "grossProfit"}:
        return value
    if INCOME_OR_LOSS_RE.search(label):
        return value
    if LOSS_LABEL_RE.search(label) and value > 0:
        return -value
    return value


def _statement_type(context: str, labels: list[str]) -> str | None:
    near = context[-500:]
    blob = near.lower()
    if PRESENTATION_HINT_RE.search(blob) and not IS_HINT_RE.search(blob) and not CF_HINT_RE.search(blob):
        return None
    if NON_GAAP_RE.search(blob) and not GAAP_RE.search(blob):
        return None
    if CF_HINT_RE.search(near):
        return "cf"
    if BS_HINT_RE.search(near):
        return "bs"
    if IS_HINT_RE.search(near):
        return "is"
    joined = " | ".join(labels).lower()
    if "total assets" in joined and ("total liabilities" in joined or "stockholders" in joined):
        return "bs"
    if "operating activities" in joined or "investing activities" in joined:
        return "cf"
    if any("revenue" in x or "net sales" in x for x in labels) and any(
        "net income" in x or "net loss" in x or "operating" in x for x in labels
    ):
        return "is"
    return None


def _pick_quarterly_column(cols: list[ColumnMeta]) -> int | None:
    candidates: list[tuple[tuple, int]] = []
    for i, col in enumerate(cols):
        if i == 0 or not col.gaap:
            continue
        if col.kind not in {None, "quarterly"}:
            continue
        if col.kind is None and col.end is None and col.year is None:
            continue
        end = col.end or date.min
        candidates.append(((end, col.year or 0, -i), i))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    best_end = candidates[0][0][0]
    # Ambiguous: two current-period GAAP quarterly columns.
    same = [c for c in candidates if c[0][0] == best_end]
    if len({c[1] for c in same}) > 1 and best_end != date.min:
        # Same date repeated (common: current / prior year split across header years).
        # Prefer the leftmost current-year column.
        return min(c[1] for c in same)
    return candidates[0][1]


def _period_from_column(col: ColumnMeta, context: str) -> tuple[int | None, int | None, date | None]:
    end = col.end
    fy = col.year
    if fy is None and end:
        fy = end.year
    context_fy = FY_RE.search(context)
    if context_fy and fy is None:
        year = int(context_fy.group(1))
        fy = year + 2000 if year < 100 else year
    fq = quarter_from_name(context) or quarter_from_name(col.text) or fiscal_quarter_from_end(end)
    return fy, fq, end


def extract_metrics_from_html(html: str, *, exhibit_name: str = "") -> tuple[dict[str, ExtractedMetric], list[dict]]:
    if PRESENTATION_HINT_RE.search(html[:2000]) and "statements of income" not in html.lower():
        if re.search(r"investor presentation", html[:2000], re.I):
            return {}, [{"reason": "rejected_presentation", "exhibit": exhibit_name}]
    metrics: dict[str, ExtractedMetric] = {}
    evidence: list[dict] = []
    annual: dict[str, ExtractedMetric] = {}
    ytd9: dict[str, ExtractedMetric] = {}

    for context, grid in iter_tables(html):
        labels = [_norm_label(row[0]) if row else "" for row in grid]
        statement = _statement_type(context, labels)
        if statement is None:
            evidence.append({"skipped": "unclassified_or_nongaap_table", "context": context[:160]})
            continue
        if NON_GAAP_RE.search(context) and not GAAP_RE.search(context):
            evidence.append({"skipped": "non_gaap_table", "context": context[:160]})
            continue
        cols = _classify_columns(grid, context)
        scale = parse_scale(context + " " + " ".join(cols[i].text for i in range(min(3, len(cols)))))
        q_idx = _pick_quarterly_column(cols) if statement != "bs" else None
        bs_idx = None
        if statement == "bs":
            dated = [(c.end or date.min, -i, i) for i, c in enumerate(cols) if i and c.gaap and (c.end or c.year)]
            if dated:
                dated.sort(reverse=True)
                bs_idx = dated[0][2]
        target_idx = q_idx if statement != "bs" else bs_idx
        if target_idx is None:
            # Keep annual / 9M columns for optional Q4 derivation.
            for i, col in enumerate(cols[1:], start=1):
                if not col.gaap:
                    continue
                if col.kind == "annual":
                    target_kind = "annual"
                elif col.kind == "ytd" and col.end:
                    target_kind = "ytd"
                else:
                    continue
                fy, fq, end = _period_from_column(col, context)
                for row in grid:
                    if not row:
                        continue
                    key = _match_metric(row[0], statement)
                    if not key or key == "dilutedEps":
                        continue
                    if target_idx_value := (row[i] if i < len(row) else ""):
                        number = parse_number(target_idx_value)
                        if number is None:
                            continue
                        number = _apply_loss_sign(key, row[0], number)
                        if number is None:
                            continue
                        unit_scale = 1.0 if key == "dilutedEps" else scale
                        metric = ExtractedMetric(
                            key=key,
                            value=number * unit_scale,
                            unit="USD" if key != "dilutedEps" else "USD/shares",
                            scale=unit_scale,
                            label=_norm_label(row[0]),
                            period_kind=target_kind,
                            fiscal_year=fy,
                            fiscal_quarter=4 if target_kind == "annual" else fq,
                            period_end=end,
                            period_start=None,
                            gaap=True,
                        )
                        bucket = annual if target_kind == "annual" else ytd9
                        if key not in bucket:
                            bucket[key] = metric
            evidence.append({"skipped": "no_quarterly_column", "context": context[:160], "statement": statement})
            continue

        col = cols[target_idx]
        fy, fq, end = _period_from_column(col, context)
        if statement != "bs" and (fy is None or fq is None):
            evidence.append({"skipped": "ambiguous_period", "context": context[:160]})
            continue
        kind = "quarterly" if statement != "bs" else "instant"
        table_gaap = True
        for row in grid:
            if not row:
                continue
            label = row[0]
            key = _match_metric(label, statement)
            if not key:
                continue
            if target_idx >= len(row):
                continue
            number = parse_number(row[target_idx])
            if number is None:
                continue
            signed = _apply_loss_sign(key, label, number)
            if signed is None:
                continue
            unit_scale = 1.0 if key == "dilutedEps" else scale
            if key == "capitalExpenditures":
                signed = -abs(signed) if signed != 0 else signed
                # Store CapEx as a positive cash outflow magnitude to match Layer 3.
                signed = abs(signed)
            metric = ExtractedMetric(
                key=key,
                value=signed * unit_scale if key != "dilutedEps" else signed,
                unit="USD" if key != "dilutedEps" else "USD/shares",
                scale=unit_scale,
                label=_norm_label(label),
                period_kind=kind,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end=end,
                period_start=None,
                gaap=table_gaap,
            )
            if key in metrics:
                continue
            metrics[key] = metric
            evidence.append(
                {
                    "key": key,
                    "label": metric.label,
                    "value": metric.value,
                    "column": col.text,
                    "statement": statement,
                }
            )

    if "totalDebt" not in metrics:
        st = metrics.get("shortTermDebt")
        lt = metrics.get("longTermDebt")
        if st and lt and st.period_end == lt.period_end:
            metrics["totalDebt"] = ExtractedMetric(
                key="totalDebt",
                value=st.value + lt.value,
                unit="USD",
                scale=st.scale,
                label="short-term debt + long-term debt",
                period_kind="instant",
                fiscal_year=st.fiscal_year,
                fiscal_quarter=st.fiscal_quarter,
                period_end=st.period_end,
                period_start=None,
                gaap=True,
                method="derived",
                formula="short_term_debt + long_term_debt",
            )

    if "freeCashFlow" not in metrics:
        ocf = metrics.get("operatingCashFlow")
        capex = metrics.get("capitalExpenditures")
        if ocf and capex and ocf.period_end == capex.period_end and ocf.period_kind == capex.period_kind:
            metrics["freeCashFlow"] = ExtractedMetric(
                key="freeCashFlow",
                value=ocf.value - capex.value,
                unit="USD",
                scale=ocf.scale,
                label="operating cash flow − capital expenditures",
                period_kind=ocf.period_kind,
                fiscal_year=ocf.fiscal_year,
                fiscal_quarter=ocf.fiscal_quarter,
                period_end=ocf.period_end,
                period_start=None,
                gaap=True,
                method="derived",
                formula="OCF − CapEx",
            )

    # Existing verified rule: Q4 = FY − 9M when both appear in the same exhibit.
    for key, fy_metric in annual.items():
        nine = ytd9.get(key)
        if key in metrics or nine is None:
            continue
        if fy_metric.fiscal_year != nine.fiscal_year:
            continue
        if nine.period_kind != "ytd":
            continue
        metrics[key] = ExtractedMetric(
            key=key,
            value=fy_metric.value - nine.value,
            unit=fy_metric.unit,
            scale=fy_metric.scale,
            label=fy_metric.label,
            period_kind="quarterly",
            fiscal_year=fy_metric.fiscal_year,
            fiscal_quarter=4,
            period_end=fy_metric.period_end,
            period_start=None,
            gaap=True,
            method="derived",
            formula="FY − 9M",
        )
        evidence.append({"key": key, "method": "FY − 9M", "value": metrics[key].value})

    for drop in ("shortTermDebt", "longTermDebt"):
        metrics.pop(drop, None)
    return metrics, evidence


def extract_earnings_release(
    html: str,
    *,
    item_202: bool,
    exhibit_name: str | None,
    exhibit_url: str | None,
    filing_url: str | None,
) -> EightKExtraction:
    if not item_202:
        return EightKExtraction(
            status="not_earnings",
            reason="not_item_202",
            item_202=False,
            exhibit_name=exhibit_name,
            exhibit_url=exhibit_url,
            filing_url=filing_url,
        )
    if not html or not html.strip():
        return EightKExtraction(
            status="failed",
            reason="empty_exhibit",
            item_202=True,
            exhibit_name=exhibit_name,
            exhibit_url=exhibit_url,
            filing_url=filing_url,
        )
    metrics, evidence = extract_metrics_from_html(html, exhibit_name=exhibit_name or "")
    quarterly = {k: m for k, m in metrics.items() if m.period_kind in {"quarterly", "instant"}}
    if not quarterly:
        return EightKExtraction(
            status="failed",
            reason="no_gaap_quarterly_metrics",
            item_202=True,
            exhibit_name=exhibit_name,
            exhibit_url=exhibit_url,
            filing_url=filing_url,
            evidence=evidence,
        )
    sample = next(
        (m for m in quarterly.values() if m.fiscal_year and m.fiscal_quarter),
        next(iter(quarterly.values())),
    )
    return EightKExtraction(
        status="extracted",
        reason=None,
        item_202=True,
        exhibit_name=exhibit_name,
        exhibit_url=exhibit_url,
        filing_url=filing_url,
        fiscal_year=sample.fiscal_year,
        fiscal_quarter=sample.fiscal_quarter,
        period_end=sample.period_end,
        period_start=sample.period_start,
        metrics=quarterly,
        evidence=evidence,
    )
