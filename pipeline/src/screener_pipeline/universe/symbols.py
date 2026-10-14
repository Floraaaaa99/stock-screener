from __future__ import annotations

import re


def canonical_symbol(symbol: str) -> str:
    """Canonical ticker form shared by all sources: upper case, share-class separator '-'.

    NASDAQ Trader (ACT/CQS) writes BRK.B, Yahoo and SEC write BRK-B.
    """
    s = symbol.strip().upper()
    return re.sub(r"[./]", "-", s)


def yahoo_symbol(canonical: str) -> str:
    return canonical


def sec_symbol_variants(canonical: str) -> list[str]:
    """Spellings SEC's company_tickers_exchange.json may use for the same listing."""
    variants = [canonical, canonical.replace("-", "."), canonical.replace("-", "")]
    seen: list[str] = []
    for v in variants:
        if v not in seen:
            seen.append(v)
    return seen
