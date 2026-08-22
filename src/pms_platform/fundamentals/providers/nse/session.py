"""Reusable HTTP session for NSE website JSON endpoints."""

from __future__ import annotations

import random
import time
from typing import Any

import httpx

_NSE_HOME = "https://www.nseindia.com/"
_NSE_REPORTS = "https://www.nseindia.com/all-reports"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _NSE_HOME,
}


class NSESessionError(RuntimeError):
    """NSE request failed after retries."""


class NSESession:
    """Bounded-retries client for NSE public website routes."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        base_backoff: float = 0.75,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._client = httpx.Client(
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=timeout,
        )
        self._warmed = False

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NSESession:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def warm_up(self) -> None:
        if self._warmed:
            return
        for url in (_NSE_HOME, _NSE_REPORTS):
            try:
                self._client.get(url, timeout=self._timeout)
            except httpx.HTTPError:
                pass
        self._warmed = True

    def get_json(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        """GET ``path`` (absolute or relative to nseindia.com) and parse JSON."""
        self.warm_up()
        url = path if path.startswith("http") else f"https://www.nseindia.com{path}"
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                last_exc = exc
                self._sleep_backoff(attempt, retry_after=None)
                continue
            if response.status_code in {401, 403, 429} or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")
                self._sleep_backoff(attempt, retry_after=retry_after)
                last_exc = NSESessionError(f"HTTP {response.status_code} for {url}")
                continue
            if response.status_code != 200:
                raise NSESessionError(f"HTTP {response.status_code} for {url}")
            return response.json()
        raise NSESessionError(str(last_exc or "NSE request failed"))

    def get_text(self, url: str) -> str:
        """Download document text (XBRL/XML/HTML archives)."""
        self.warm_up()
        headers = {**_DEFAULT_HEADERS, "Referer": _NSE_HOME}
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                last_exc = exc
                self._sleep_backoff(attempt, retry_after=None)
                continue
            if response.status_code != 200:
                self._sleep_backoff(attempt, retry_after=response.headers.get("Retry-After"))
                last_exc = NSESessionError(f"HTTP {response.status_code} for {url}")
                continue
            return response.text
        raise NSESessionError(str(last_exc or "NSE document fetch failed"))

    def _sleep_backoff(self, attempt: int, *, retry_after: str | None) -> None:
        if retry_after and retry_after.isdigit():
            time.sleep(min(int(retry_after), 30))
            return
        delay = self._base_backoff * (2**attempt) + random.uniform(0, 0.25)
        time.sleep(delay)
