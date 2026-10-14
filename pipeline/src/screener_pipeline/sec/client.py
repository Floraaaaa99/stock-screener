from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import config
from ..cache import is_fresh, read_json, write_text_atomic
from ..http import RateLimitedClient
from ..universe.symbols import sec_symbol_variants
from .statement import Statement, has_revenue_line, income_statement_candidates, parse_statement_html

log = logging.getLogger(__name__)


class SecClient:
    def __init__(self, cache_dir: Path | None = None, offline: bool = False):
        self.cache_dir = (cache_dir or config.CACHE_DIR) / "sec"
        self.offline = offline
        self._http: RateLimitedClient | None = None
        self._statements: dict[str, tuple[Statement, str] | None] = {}

    @property
    def http(self) -> RateLimitedClient:
        if self._http is None:
            self._http = RateLimitedClient(config.sec_user_agent(), config.SEC_MAX_RPS)
        return self._http

    def _cached_text(self, url: str, path: Path, ttl_h: float | None) -> str | None:
        """Return cached text if fresh (ttl None = immutable), else download. 404 -> None (cached)."""
        missing_marker = path.with_suffix(path.suffix + ".404")
        if path.exists() and (ttl_h is None or is_fresh(path, ttl_h) or self.offline):
            return path.read_text(encoding="utf-8")
        if missing_marker.exists() and (ttl_h is None or is_fresh(missing_marker, ttl_h) or self.offline):
            return None
        if self.offline:
            raise FileNotFoundError(f"offline mode and no cache for {url}")
        resp = self.http.get(url)
        if resp.status_code == 404:
            write_text_atomic(missing_marker, "")
            return None
        resp.raise_for_status()
        text = resp.content.decode("utf-8", errors="replace")
        write_text_atomic(path, text)
        return text

    def ticker_map(self) -> dict[str, dict]:
        text = self._cached_text(config.SEC_TICKERS_URL, self.cache_dir / "company_tickers_exchange.json",
                                 config.SEC_FACTS_TTL_H)
        data = json.loads(text or "{}")
        fields = data.get("fields", [])
        out: dict[str, dict] = {}
        for row in data.get("data", []):
            rec = dict(zip(fields, row, strict=False))
            out.setdefault(str(rec["ticker"]).upper(), rec)
        return out

    @staticmethod
    def lookup_cik(ticker_map: dict[str, dict], canonical: str) -> dict | None:
        for v in sec_symbol_variants(canonical):
            if v in ticker_map:
                return ticker_map[v]
        return None

    def companyfacts(self, cik: str) -> dict | None:
        cik10 = str(cik).zfill(10)
        text = self._cached_text(
            config.SEC_COMPANYFACTS_URL.format(cik=cik10),
            self.cache_dir / "companyfacts" / f"CIK{cik10}.json",
            config.SEC_FACTS_TTL_H,
        )
        return json.loads(text) if text else None

    def income_statement(self, cik: str, accn: str) -> tuple[Statement, str] | None:
        """The income statement as rendered by EDGAR for one filing, and its URL (cached forever)."""
        base = config.SEC_ARCHIVES_URL.format(cik=int(cik), accn_nodash=accn.replace("-", ""))
        fdir = self.cache_dir / "filings" / accn
        key = accn
        if key in self._statements:
            return self._statements[key]
        result: tuple[Statement, str] | None = None
        try:
            summary = self._cached_text(base + "FilingSummary.xml", fdir / "FilingSummary.xml", None)
            for html_name, _ in income_statement_candidates(summary) if summary else []:
                html = self._cached_text(base + html_name, fdir / html_name, None)
                if not html:
                    continue
                st = parse_statement_html(html)
                if has_revenue_line(st):
                    result = (st, base + html_name)
                    break
                if result is None:
                    result = (st, base + html_name)
        except Exception as exc:  # noqa: BLE001 - statements are best-effort; absence is reported, not fatal
            log.warning("income statement unavailable for %s %s: %s", cik, accn, exc)
            result = None
        self._statements[key] = result
        return result


def load_overrides() -> dict[str, dict]:
    data = read_json(config.OVERRIDES_FILE, default={}) or {}
    return {str(k).zfill(10): v for k, v in data.get("overrides", {}).items()}
