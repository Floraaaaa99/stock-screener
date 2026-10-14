from __future__ import annotations

from pathlib import Path

import requests

from .. import config
from ..cache import is_fresh, write_text_atomic
from .nasdaq_trader import Exclusion, Listing, build_universe


def _get(url: str, path: Path, offline: bool) -> str:
    if path.exists() and (offline or is_fresh(path, config.NASDAQ_TTL_H)):
        return path.read_text(encoding="utf-8")
    if offline:
        raise FileNotFoundError(f"offline mode and no cached copy of {url}")
    resp = requests.get(url, timeout=60, headers={"User-Agent": "stock-screener (personal research)"})
    resp.raise_for_status()
    write_text_atomic(path, resp.text)
    return resp.text


def load_universe(offline: bool = False) -> tuple[list[Listing], list[Exclusion], dict[str, str | None]]:
    d = config.CACHE_DIR / "nasdaq"
    nasdaq = _get(config.NASDAQ_LISTED_URL, d / "nasdaqlisted.txt", offline)
    other = _get(config.OTHER_LISTED_URL, d / "otherlisted.txt", offline)
    return build_universe(nasdaq, other)
