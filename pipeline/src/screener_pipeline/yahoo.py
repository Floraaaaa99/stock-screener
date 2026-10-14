"""Yahoo Finance profile and market data via yfinance, with a per-field timestamped cache.

Yahoo is an unofficial source: requests are throttled, retried with backoff, and on failure the last
known value is kept together with its as-of time. Values that were never fetched stay null (N/A).
Yahoo's financial fields (e.g. revenueGrowth) are deliberately not read.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import config
from .cache import read_json, write_json_atomic

log = logging.getLogger(__name__)

PROFILE_FIELDS = ("sector", "industry", "quoteType", "longName", "currency")
MARKET_FIELDS = ("marketCap", "price")


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _age_ok(as_of: str | None, ttl_h: float) -> bool:
    if not as_of:
        return False
    return _now() - datetime.fromisoformat(as_of) < timedelta(hours=ttl_h)


class YahooCache:
    def __init__(self, path: Path | None = None):
        self.path = path or (config.CACHE_DIR / "yahoo" / "yahoo_cache.json")
        self.data: dict[str, dict] = read_json(self.path, default={}) or {}

    def save(self) -> None:
        write_json_atomic(self.path, self.data)

    def get(self, ticker: str) -> dict:
        return self.data.setdefault(ticker, {})


def _fetch_info(ticker: str, retries: int = 4) -> dict:
    import yfinance as yf

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            info = yf.Ticker(ticker).info or {}
            if info.get("quoteType") is None and info.get("regularMarketPrice") is None and len(info) <= 2:
                raise LookupError(f"Yahoo returned no data for {ticker}")
            return info
        except Exception as exc:  # noqa: BLE001 - yfinance raises many exception types
            last = exc
            msg = str(exc)
            if "404" in msg or "not found" in msg.lower():
                raise LookupError(msg) from exc
            if attempt < retries:
                delay = (2**attempt) * 3 + random.uniform(0, 1.5)
                log.warning("Yahoo %s failed (%s); retry in %.1fs", ticker, exc, delay)
                time.sleep(delay)
    assert last is not None
    raise last


def refresh(tickers: list[str], cache: YahooCache, *, offline: bool = False,
            max_consecutive_errors: int = 20, checkpoint_every: int = 50) -> dict[str, str]:
    """Refresh stale entries. Returns {ticker: error} for tickers that failed this run."""
    errors: dict[str, str] = {}
    consecutive = 0
    done = 0
    for t in tickers:
        entry = cache.get(t)
        profile_fresh = _age_ok(entry.get("profile_as_of"), config.YAHOO_PROFILE_TTL_H)
        market_fresh = _age_ok(entry.get("market_as_of"), config.YAHOO_MARKET_TTL_H)
        if offline or (profile_fresh and market_fresh):
            continue
        time.sleep(config.YAHOO_MIN_INTERVAL_S + random.uniform(0, 0.5))
        try:
            info = _fetch_info(t)
        except Exception as exc:  # noqa: BLE001
            errors[t] = str(exc)[:200]
            entry["last_error"] = errors[t]
            entry["last_error_at"] = _now().isoformat()
            consecutive += 1
            if consecutive >= max_consecutive_errors:
                log.error("Stopping Yahoo refresh after %d consecutive errors", consecutive)
                break
            continue
        consecutive = 0
        stamp = _now().isoformat()
        entry.update({
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "quoteType": info.get("quoteType"),
            "longName": info.get("longName") or info.get("shortName"),
            "currency": info.get("currency"),
            "profile_as_of": stamp,
        })
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        entry.update({"marketCap": info.get("marketCap"), "price": price, "market_as_of": stamp})
        entry.pop("last_error", None)
        entry.pop("last_error_at", None)
        done += 1
        if done % checkpoint_every == 0:
            cache.save()
    cache.save()
    return errors
