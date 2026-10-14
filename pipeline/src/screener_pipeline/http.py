from __future__ import annotations

import logging
import random
import threading
import time

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class RateLimitedClient:
    """requests.Session wrapper with a minimum interval between requests and retry/backoff."""

    def __init__(self, user_agent: str, max_rps: float, retries: int = 4, timeout: float = 60.0):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.min_interval = 1.0 / max_rps
        self.retries = retries
        self.timeout = timeout
        self._last = 0.0
        self._lock = threading.Lock()

    def _wait_turn(self) -> None:
        with self._lock:
            delay = self._last + self.min_interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()

    def get(self, url: str) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait_turn()
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
            else:
                if resp.status_code not in RETRY_STATUS:
                    return resp
                last_exc = requests.HTTPError(f"HTTP {resp.status_code} for {url}", response=resp)
            if attempt < self.retries:
                backoff = (2**attempt) * 2 + random.uniform(0, 1)
                log.warning("GET %s failed (%s); retrying in %.1fs", url, last_exc, backoff)
                time.sleep(backoff)
        assert last_exc is not None
        raise last_exc
