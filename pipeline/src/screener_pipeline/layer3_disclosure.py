"""SEC cash-flow face disclosure tree. Additive to one-concept research metrics.

The face statement is the source of line names, order, and as-reported amounts.
A standalone quarter is calculated only when a comparable shorter YTD exists in
another filing of the same fiscal year. Missing prior YTD is never treated as zero.
Section totals are preserved and are never replaced by a sum of children.
"""

from __future__ import annotations

import re
from datetime import date

from .layer3_concepts import (
    ACQUISITION_CF_CONCEPTS,
    CAPEX_CONCEPTS,
    DEBT_FINANCING_NET_CONCEPTS,
    DEBT_ISSUANCE_GROSS_CONCEPTS,
    DEBT_REPAYMENT_GROSS_CONCEPTS,
    DIVIDEND_PAID_CONCEPTS,
    SHARE_REPURCHASE_CONCEPTS,
)
from .sec.facts import filing_url
from .sec.statement import Statement, StatementColumn, StatementRow

STANDARD_NS = {"us-gaap", "ifrs-full"}

OPERATING_TOTALS = {
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
}
INVESTING_TOTALS = {
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
}
FINANCING_TOTALS = {
    "NetCashProvidedByUsedInFinancingActivities",
    "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
}
SECTION_TOTALS = {
    **{n: "operating" for n in OPERATING_TOTALS},
    **{n: "investing" for n in INVESTING_TOTALS},
    **{n: "financing" for n in FINANCING_TOTALS},
}

GROUP_LABELS = {
    "operating": "Operating",
    "investing": "Investing",
    "financing": "Financing",
    "other": "Other",
    "supplemental": "Supplemental",
}

IDENTITY_LABELS = {
    "capex": "CapEx",
    "debtFinancing": "Debt financing",
    "shareRepurchases": "Share repurchases",
    "dividends": "Dividends",
    "acquisitions": "Acquisitions",
}

_NOTE_HINTS = (
    (re.compile(r"indebt|credit facility|long-term debt|long term debt", re.I), "debtFinancing"),
    (re.compile(r"acquisit", re.I), "acquisitions"),
    (re.compile(r"property,\s*plant|property plant|capital expenditure", re.I), "capex"),
    (re.compile(r"repurchase|treasury stock", re.I), "shareRepurchases"),
    (re.compile(r"\bdividends?\b", re.I), "dividends"),
)

_QUARTER_GAP = (60, 120)


def _local(concept: str) -> str:
    return (concept or "").split(":", 1)[-1]


def _ns(concept: str) -> str:
    return (concept or "").split(":", 1)[0] if ":" in (concept or "") else ""


def line_identity(concept: str, label: str = "") -> str | None:
    """Optional family badge. Custom namespaces stay unclassified."""
    if _ns(concept) and _ns(concept) not in STANDARD_NS:
        return None
    name = _local(concept)
    if name in CAPEX_CONCEPTS:
        return "capex"
    if name in ACQUISITION_CF_CONCEPTS:
        return "acquisitions"
    if name in SHARE_REPURCHASE_CONCEPTS:
        return "shareRepurchases"
    if name in DIVIDEND_PAID_CONCEPTS:
        return "dividends"
    if (
        name in DEBT_ISSUANCE_GROSS_CONCEPTS
        or name in DEBT_REPAYMENT_GROSS_CONCEPTS
        or name in DEBT_FINANCING_NET_CONCEPTS
    ):
        return "debtFinancing"
    # Standard siblings used on faces but omitted from the one-tag research lists.
    if name in {
        "ProceedsFromLongTermLinesOfCredit",
        "ProceedsFromIssuanceOfSecuredDebt",
        "ProceedsFromIssuanceOfSeniorLongTermDebt",
        "ProceedsFromIssuanceOfSubordinatedLongTermDebt",
        "RepaymentsOfLongTermLinesOfCredit",
        "RepaymentsOfSeniorDebt",
        "RepaymentsOfSecuredDebt",
        "RepaymentsOfSubordinatedDebt",
    }:
        return "debtFinancing"
    _ = label
    return None


def _current_column(columns: list[StatementColumn]) -> tuple[int | None, StatementColumn | None]:
    dated = [(i, c) for i, c in enumerate(columns) if c.end]
    if not dated:
        return (0, columns[0]) if columns else (None, None)
    return max(dated, key=lambda item: (item[1].end or date.min, item[1].months or 0))


def _prior_year_column(
    columns: list[StatementColumn], current: StatementColumn
) -> tuple[int | None, StatementColumn | None]:
    if current.end is None or current.months is None:
        return None, None
    best: tuple[int, StatementColumn] | None = None
    for i, col in enumerate(columns):
        if col.end is None or col.months != current.months or col.end >= current.end:
            continue
        delta = (current.end - col.end).days
        if 300 <= delta <= 430:
            if best is None or col.end > best[1].end:
                best = (i, col)
    return best if best else (None, None)


def _row_value(row: StatementRow, index: int | None) -> float | None:
    if index is None or index < 0 or index >= len(row.values):
        return None
    return row.values[index]


def _find_row(st: Statement, concept: str) -> StatementRow | None:
    for row in st.rows:
        if row.concept == concept:
            return row
    return None


def _prior_ytd_stub(
    concept: str,
    current: StatementColumn,
    prior: Statement | None,
) -> tuple[float, StatementColumn] | None:
    """Comparable shorter YTD from another same-year filing. Absence is not zero."""
    if prior is None or current.end is None or current.months is None:
        return None
    prior_idx, prior_col = _current_column(prior.columns)
    if prior_col is None or prior_col.end is None or prior_col.months is None:
        return None
    if prior_col.months >= current.months or prior_col.end >= current.end:
        return None
    gap = (current.end - prior_col.end).days
    if gap < _QUARTER_GAP[0] or gap > _QUARTER_GAP[1]:
        return None
    if current.months - prior_col.months not in (2, 3, 4):
        return None
    row = _find_row(prior, concept)
    if row is None:
        return None
    val = _row_value(row, prior_idx)
    if val is None:
        return None
    return val, prior_col


def _same_end_quarter_column(
    columns: list[StatementColumn], current: StatementColumn
) -> tuple[int | None, StatementColumn | None]:
    """A 3-month column on the same face for the same period end is as-reported quarterly."""
    if current.end is None:
        return None, None
    for i, col in enumerate(columns):
        if col.end == current.end and col.months == 3 and (current.months or 0) > 3:
            return i, col
    return None, None


def _group_for_concept(name: str, current: str) -> str:
    if "SupplementalCashFlow" in name:
        return "supplemental"
    if name.endswith("OperatingActivitiesAbstract") or name in OPERATING_TOTALS:
        return "operating"
    if name.endswith("InvestingActivitiesAbstract") or name in INVESTING_TOTALS:
        return "investing"
    if name.endswith("FinancingActivitiesAbstract") or name in FINANCING_TOTALS:
        return "financing"
    if name.startswith("EffectOfExchangeRate") or "PeriodIncreaseDecrease" in name:
        return "other"
    if name in {
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndCashEquivalentsAtCarryingValue",
    }:
        return "other"
    return current


def _role(name: str, values: list[float | None], group: str) -> str:
    if name.endswith("Abstract") or "Abstract" in name:
        return "header"
    if name in SECTION_TOTALS:
        return "total"
    if group == "supplemental" and all(v is None for v in values):
        return "header"
    if all(v is None for v in values):
        return "header"
    return "line"


def statement_document_url(cik: str, accn: str, html_name: str) -> str:
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    if not digits or not accn or not html_name:
        return ""
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(digits)}/"
        f"{accn.replace('-', '')}/{html_name}"
    )


def note_source_links(filing_summary_xml: str, cik: str, accn: str) -> list[dict]:
    """URLs to relevant note R pages. Notes are not parsed."""
    if not (filing_summary_xml or "").strip():
        return []
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(filing_summary_xml)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for rep in root.iter("Report"):
        cat = (rep.findtext("MenuCategory") or "").strip()
        if cat not in {"Notes", "Tables"}:
            continue
        short = (rep.findtext("ShortName") or "").strip()
        html = (rep.findtext("HtmlFileName") or "").strip()
        if not html or html in seen:
            continue
        hint = None
        for rx, ident in _NOTE_HINTS:
            if rx.search(short):
                hint = ident
                break
        if hint is None:
            continue
        seen.add(html)
        out.append(
            {
                "title": short,
                "identity": hint,
                "url": statement_document_url(cik, accn, html),
                "parsed": False,
            }
        )
    return out


def build_cash_flow_disclosure(
    statement: Statement,
    *,
    cik: str,
    accn: str,
    form: str | None = None,
    filed: str | None = None,
    statement_url: str = "",
    html_name: str = "",
    prior_statement: Statement | None = None,
    prior_accn: str | None = None,
    note_links: list[dict] | None = None,
    currency: str | None = "USD",
) -> dict:
    """Turn one face cash-flow statement into the disclosure tree."""
    cur_idx, current = _current_column(statement.columns)
    py_idx, prior_year = _prior_year_column(statement.columns, current) if current else (None, None)
    q_idx, q_col = _same_end_quarter_column(statement.columns, current) if current else (None, None)

    groups: dict[str, dict] = {}
    group_id = "operating"
    capex_lines = 0

    for order, row in enumerate(statement.rows):
        name = _local(row.concept)
        group_id = _group_for_concept(name, group_id)
        role = _role(name, row.values, group_id)
        reported = _row_value(row, cur_idx) if role != "header" else None
        prior_year_val = _row_value(row, py_idx) if role != "header" and py_idx is not None else None
        identity = line_identity(row.concept, row.label) if role == "line" else None
        if identity == "capex":
            capex_lines += 1

        standalone: dict
        if role != "line":
            standalone = {
                "kind": "unavailable",
                "reason": None,
                "value": None,
                "formula": None,
            }
        elif current is not None and current.months == 3 and reported is not None:
            standalone = {
                "kind": "asReported",
                "reason": None,
                "value": reported,
                "formula": "3M reported",
                "months": 3,
                "end": current.end.isoformat() if current.end else None,
            }
        elif q_col is not None and _row_value(row, q_idx) is not None:
            standalone = {
                "kind": "asReported",
                "reason": None,
                "value": _row_value(row, q_idx),
                "formula": "3M reported",
                "months": 3,
                "end": q_col.end.isoformat() if q_col.end else None,
            }
        else:
            stub = _prior_ytd_stub(row.concept, current, prior_statement) if current else None
            if stub is not None and reported is not None and current is not None:
                prior_val, prior_col = stub
                standalone = {
                    "kind": "calculated",
                    "reason": None,
                    "value": reported - prior_val,
                    "formula": f"{current.months}M YTD − {prior_col.months}M YTD",
                    "months": (current.months or 0) - (prior_col.months or 0),
                    "end": current.end.isoformat() if current.end else None,
                    "priorAccn": prior_accn,
                    "priorEnd": prior_col.end.isoformat() if prior_col.end else None,
                    "priorValue": prior_val,
                }
            elif reported is None:
                standalone = {
                    "kind": "unavailable",
                    "reason": "no_reported_amount",
                    "value": None,
                    "formula": None,
                }
            else:
                standalone = {
                    "kind": "unavailable",
                    "reason": "missing_prior_ytd",
                    "value": None,
                    "formula": None,
                }

        line = {
            "order": order,
            "label": row.label,
            "concept": row.concept,
            "role": role,
            "identity": identity,
            "group": group_id,
            "asReported": {
                "kind": "asReported" if reported is not None else "unavailable",
                "value": reported,
                "months": current.months if current else None,
                "end": current.end.isoformat() if current and current.end else None,
            },
            "priorYear": {
                "kind": "asReported" if prior_year_val is not None else "unavailable",
                "value": prior_year_val,
                "months": prior_year.months if prior_year else None,
                "end": prior_year.end.isoformat() if prior_year and prior_year.end else None,
            },
            "standaloneQuarter": standalone,
        }
        bucket = groups.setdefault(
            group_id,
            {
                "id": group_id,
                "label": GROUP_LABELS.get(group_id, group_id.title()),
                "lines": [],
                "reportedTotal": None,
            },
        )
        bucket["lines"].append(line)
        if role == "total" and reported is not None:
            bucket["reportedTotal"] = {
                "kind": "asReported",
                "value": reported,
                "concept": row.concept,
                "label": row.label,
            }

    capex_breakdown = "not_specified" if capex_lines <= 1 else "multiple_face_lines"
    acquisition_lines = [
        line
        for g in groups.values()
        for line in g["lines"]
        if line.get("identity") == "acquisitions" and line.get("role") == "line"
    ]

    return {
        "source": "sec_cash_flow_face",
        "currency": currency,
        "filing": {
            "cik": str(cik).zfill(10),
            "accn": accn,
            "form": form,
            "filed": filed,
            "indexUrl": filing_url(cik, accn),
            "statementUrl": statement_url or statement_document_url(cik, accn, html_name),
            "title": statement.title,
        },
        "period": {
            "kind": "asReported",
            "months": current.months if current else None,
            "end": current.end.isoformat() if current and current.end else None,
        },
        "groups": [
            groups[key]
            for key in ("operating", "investing", "financing", "other", "supplemental")
            if key in groups
        ],
        "identities": IDENTITY_LABELS,
        "capex": {
            "breakdown": capex_breakdown,
            "note": (
                "Breakdown not specified."
                if capex_breakdown == "not_specified"
                else "More than one CapEx line appears on the cash-flow face."
            ),
        },
        "acquisitions": {
            "disclosedOnFace": bool(acquisition_lines),
            "note": None if acquisition_lines else "No acquisition cash-flow line was disclosed on this statement.",
        },
        "noteLinks": note_links or [],
        "notesParsed": False,
    }
