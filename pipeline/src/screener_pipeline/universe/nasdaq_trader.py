"""Parse and classify the NASDAQ Trader symbol directory (the authoritative stock universe)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .symbols import canonical_symbol

EXCHANGES = {"Q": "NASDAQ", "N": "NYSE", "A": "NYSE American"}
NASDAQ_TIERS = {"Q": "Global Select", "G": "Global Market", "S": "Capital Market"}
IN_SCOPE_OTHER_EXCHANGES = {"N", "A"}

# Each rule: (reason, compiled regex on the security name). The first match excludes the listing.
_NAME_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("warrant", re.compile(r"\bwarrants?\b|\(ADW\)", re.I)),
    ("right", re.compile(r"\brights?\b", re.I)),
    (
        "unit",
        re.compile(r"\bunits?,?\s+each\b|\s-\s*units?\.?\s*$|^units?\b|\b(equity|corporate)\s+units?\b", re.I),
    ),
    ("preferred", re.compile(r"\bpreferred\b|\bpreference\s+shares?\b|\bpfd\b", re.I)),
    # "Depositary Shares" without "American" are fractional interests in preferred stock.
    ("preferred", re.compile(r"^(?!.*\bamerican\b)(?!.*\bADSs?\b).*\bdepositary\s+shares?\b", re.I)),
    ("structured_product", re.compile(r"\bSTRATS\b|\btrust\s+certificates?\b|\bcapital\s+securities\b", re.I)),
    (
        "debt",
        re.compile(
            r"\bnotes?\b|\bdebentures?\b|\bbonds?\b|\bsenior\b.*\bdue\b|\bdue\s+(19|20)\d\d\b|"
            r"\bbaby\s+bonds?\b|\bsubordinated\b",
            re.I,
        ),
    ),
    ("etn", re.compile(r"\betns?\b|exchange[- ]traded\s+notes?", re.I)),
    (
        "fund",
        re.compile(
            r"\bfund\b|\bclosed[- ]end\b|\betf\b|\bindex\s+shares\b|\bmunicipals?\b|"
            r"\bincome\s+(securities\s+)?trust\b",
            re.I,
        ),
    ),
    ("when_issued", re.compile(r"\bwhen[- ]issued\b", re.I)),
]

# Symbol-suffix rules for otherlisted.txt ACT symbols: units (.U), warrants (.W/.WS), rights (.R),
# preferred ($), when-issued (#).
_ACT_SUFFIX_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("preferred", re.compile(r"\$")),
    ("unit", re.compile(r"\.U$")),
    ("warrant", re.compile(r"\.W[S]?[A-Z]?$")),
    ("right", re.compile(r"\.R[T]?$")),
    ("when_issued", re.compile(r"#")),
]

_ADR = re.compile(r"\bamerican\s+depositary\b|\bADRs?\b|\bADSs?\b|\bdepositary\s+(shares|receipts)\b", re.I)


@dataclass(frozen=True)
class Listing:
    symbol: str
    raw_symbol: str
    name: str
    exchange: str
    exchange_code: str
    security_type: str
    nasdaq_tier: str | None
    financial_status: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Exclusion:
    symbol: str
    raw_symbol: str
    name: str
    exchange_code: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _rows(text: str) -> tuple[list[dict[str, str]], str | None]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = lines[0].split("|")
    rows: list[dict[str, str]] = []
    created: str | None = None
    for ln in lines[1:]:
        if ln.startswith("File Creation Time"):
            created = ln.split(":", 1)[1].split("|")[0].strip()
            continue
        parts = ln.split("|")
        rows.append({h: (parts[i].strip() if i < len(parts) else "") for i, h in enumerate(header)})
    return rows, created


def clean_name(name: str) -> str:
    """Drop NASDAQ's ' - Common Stock' style suffixes for display."""
    n = re.sub(r"\s+", " ", name).strip()
    n = re.sub(
        r"\s*-?\s*(Class [A-Z] )?(New )?(Common Stock|Common Shares|Ordinary Shares|Capital Stock|"
        r"American Depositary Shares.*|Common Units.*|Shares of Beneficial Interest.*)\s*$",
        "",
        n,
        flags=re.I,
    )
    return n.rstrip(" -,") or name.strip()


def classify_name(name: str) -> str | None:
    """Return an exclusion reason for a security name, or None if it is common equity / ADR."""
    lowered = name.lower()
    for reason, rx in _NAME_RULES:
        if rx.search(name):
            if reason == "right" and "common" in lowered and "rights" not in lowered:
                continue
            return reason
    return None


def security_type(name: str) -> str:
    return "adr" if _ADR.search(name) else "common"


def parse_nasdaq_listed(text: str) -> tuple[list[Listing], list[Exclusion], str | None]:
    rows, created = _rows(text)
    listings: list[Listing] = []
    exclusions: list[Exclusion] = []
    for r in rows:
        raw = r["Symbol"]
        name = r["Security Name"]
        sym = canonical_symbol(raw)
        reason = None
        if r.get("Test Issue") == "Y":
            reason = "test_issue"
        elif r.get("ETF") == "Y":
            reason = "etf"
        elif r.get("NextShares") == "Y":
            reason = "nextshares"
        else:
            reason = classify_name(name)
        if reason:
            exclusions.append(Exclusion(sym, raw, name, "Q", reason))
            continue
        listings.append(
            Listing(
                symbol=sym,
                raw_symbol=raw,
                name=clean_name(name),
                exchange=EXCHANGES["Q"],
                exchange_code="Q",
                security_type=security_type(name),
                nasdaq_tier=NASDAQ_TIERS.get(r.get("Market Category", "")),
                financial_status=r.get("Financial Status") or None,
            )
        )
    return listings, exclusions, created


def parse_other_listed(text: str) -> tuple[list[Listing], list[Exclusion], str | None]:
    rows, created = _rows(text)
    listings: list[Listing] = []
    exclusions: list[Exclusion] = []
    for r in rows:
        raw = r["ACT Symbol"]
        name = r["Security Name"]
        exch = r.get("Exchange", "")
        sym = canonical_symbol(raw)
        reason = None
        if r.get("Test Issue") == "Y":
            reason = "test_issue"
        elif exch not in IN_SCOPE_OTHER_EXCHANGES:
            reason = "exchange_out_of_scope"
        elif r.get("ETF") == "Y":
            reason = "etf"
        else:
            for rsn, rx in _ACT_SUFFIX_RULES:
                if rx.search(raw):
                    reason = rsn
                    break
            if reason is None:
                reason = classify_name(name)
        if reason:
            exclusions.append(Exclusion(sym, raw, name, exch, reason))
            continue
        listings.append(
            Listing(
                symbol=sym,
                raw_symbol=raw,
                name=clean_name(name),
                exchange=EXCHANGES[exch],
                exchange_code=exch,
                security_type=security_type(name),
                nasdaq_tier=None,
                financial_status=None,
            )
        )
    return listings, exclusions, created


def build_universe(
    nasdaq_text: str, other_text: str
) -> tuple[list[Listing], list[Exclusion], dict[str, str | None]]:
    """Combine both files; de-duplicate canonical symbols (first file wins, duplicates recorded)."""
    n_list, n_exc, n_created = parse_nasdaq_listed(nasdaq_text)
    o_list, o_exc, o_created = parse_other_listed(other_text)
    seen: dict[str, Listing] = {}
    exclusions = n_exc + o_exc
    for listing in n_list + o_list:
        if listing.symbol in seen:
            exclusions.append(
                Exclusion(listing.symbol, listing.raw_symbol, listing.name, listing.exchange_code, "duplicate")
            )
            continue
        seen[listing.symbol] = listing
    listings = sorted(seen.values(), key=lambda x: x.symbol)
    return listings, exclusions, {"nasdaqlisted": n_created, "otherlisted": o_created}
