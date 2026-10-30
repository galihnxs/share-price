"""HTTP sessions for SEC (rate-limited, User-Agent from .env) and Yahoo (cookie + crumb)."""
from __future__ import annotations

import threading
import time

import requests

from common.config import sec_user_agent, settings
from common.log import get_logger

log = get_logger("http")
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
)


class _RateLimiter:
    def __init__(self, per_second: float):
        self.gap = 1.0 / per_second
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            if now < self.next:
                time.sleep(self.next - now)
            self.next = max(now, self.next) + self.gap


class SEC:
    """data.sec.gov and www.sec.gov, max ~8 requests/second (settings.sec.max_requests_per_second)."""

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": sec_user_agent(), "Accept-Encoding": "gzip, deflate"})
        self.rl = _RateLimiter(settings()["sec"]["max_requests_per_second"])

    def get(self, url: str, tries: int = 4) -> requests.Response:
        for a in range(tries):
            self.rl.wait()
            try:
                r = self.s.get(url, timeout=60)
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"{r.status_code}")
                r.raise_for_status()
                return r
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                if a == tries - 1 or (isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code == 404):
                    raise
                time.sleep(2 * (a + 1))
        raise RuntimeError("unreachable")

    def json(self, url: str) -> dict:
        return self.get(url).json()

    def text(self, url: str) -> str:
        return self.get(url).text


class Yahoo:
    """query1.finance.yahoo.com with the same cookie + crumb handshake a browser does."""

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": BROWSER_UA, "Accept": "*/*"})
        self.crumb = ""
        self.refresh()

    def refresh(self) -> None:
        self.s.get("https://fc.yahoo.com", timeout=30, allow_redirects=True)  # 404 is normal; it sets the A3 cookie
        r = self.s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=30)
        r.raise_for_status()
        self.crumb = r.text.strip()
        if not self.crumb or "<" in self.crumb:
            raise RuntimeError(f"Yahoo crumb handshake failed: {r.text[:80]!r}")

    def json(self, path: str, params: dict | None = None, tries: int = 3) -> dict:
        url = "https://query1.finance.yahoo.com" + path
        for a in range(tries):
            r = self.s.get(url, params={**(params or {}), "crumb": self.crumb}, timeout=30)
            if r.status_code == 401:
                self.refresh()
                continue
            if r.status_code == 429:
                time.sleep(5 * (a + 1))
                continue
            if r.status_code == 404:
                return {}
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"Yahoo {path}: gave up after {tries} tries")
