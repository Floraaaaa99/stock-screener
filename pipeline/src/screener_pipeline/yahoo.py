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


def implied_market_cap(price: float | None, shares: float | None) -> float | None:
    if price is None or shares is None:
        return None
    if not (price > 0 and shares > 0):
        return None
    return price * shares


def batch_row_error(info_market_cap: float | None, implied: float | None) -> float | None:
    """Relative error of implied cap vs Yahoo's .info marketCap; None if either side is missing."""
    if info_market_cap is None or implied is None or info_market_cap <= 0:
        return None
    return abs(implied - info_market_cap) / info_market_cap


def summarize_batch_comparison(rows: list[dict], max_rel_error: float | None = None) -> dict:
    """Decide whether batched prices may be adopted. Default is no."""
    limit = config.YAHOO_BATCH_MAX_REL_ERROR if max_rel_error is None else max_rel_error
    errors = [r["relError"] for r in rows if r.get("relError") is not None]
    comparable = len(errors)
    within = sum(1 for e in errors if e <= limit)
    adopt = comparable >= 10 and within / comparable >= 0.95
    return {
        "compared": comparable,
        "withinTolerance": within,
        "tolerance": limit,
        "maxRelError": max(errors) if errors else None,
        "medianRelError": sorted(errors)[len(errors) // 2] if errors else None,
        "adopt": adopt,
        "reason": (
            "Batched prices match Yahoo marketCap closely enough to adopt."
            if adopt
            else "Keep per-ticker .info; batched prices are not accurate enough or the sample is too small."
        ),
    }


def refresh_market_batch(tickers: list[str], cache: YahooCache, *, batch_size: int | None = None) -> dict[str, str]:
    """Experimental: fill price from yf.download in batches. Does not overwrite sector/industry.

    Market cap is left unchanged unless sharesOutstanding is already in the cache from a prior .info
    fetch, in which case it is recomputed as price × shares. This path is not used by the default
    build; call it only after summarize_batch_comparison(...).adopt is true.
    """
    import yfinance as yf

    errors: dict[str, str] = {}
    size = batch_size or config.YAHOO_BATCH_SIZE
    stamp = _now().isoformat()
    for i in range(0, len(tickers), size):
        chunk = tickers[i : i + size]
        try:
            data = yf.download(
                chunk,
                period="1d",
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
            )
        except Exception as exc:  # noqa: BLE001
            for t in chunk:
                errors[t] = str(exc)[:200]
            continue
        for t in chunk:
            price = _batch_last_close(data, t, len(chunk) == 1)
            if price is None:
                errors[t] = "no close in batch download"
                continue
            entry = cache.get(t)
            entry["price"] = float(price)
            entry["market_as_of"] = stamp
            shares = entry.get("sharesOutstanding")
            implied = implied_market_cap(float(price), shares)
            if implied is not None:
                entry["marketCap"] = implied
    cache.save()
    return errors


def _batch_last_close(data, ticker: str, single: bool) -> float | None:
    try:
        if single:
            closes = data["Close"]
        else:
            closes = data[ticker]["Close"]
        val = closes.dropna().iloc[-1]
        return float(val)
    except Exception:  # noqa: BLE001
        return None


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
        entry.update({
            "marketCap": info.get("marketCap"),
            "price": price,
            "sharesOutstanding": info.get("sharesOutstanding"),
            "market_as_of": stamp,
        })
        entry.pop("last_error", None)
        entry.pop("last_error_at", None)
        done += 1
        if done % checkpoint_every == 0:
            cache.save()
    cache.save()
    return errors
