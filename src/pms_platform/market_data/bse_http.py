"""Shared BSE HTTP headers / client defaults."""

from __future__ import annotations

import httpx

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def bse_headers(*, referer: str = "https://www.bseindia.com/") -> dict[str, str]:
    """Browser-like headers BSE JSON endpoints expect."""
    return {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
        "Origin": "https://www.bseindia.com",
        "Accept-Language": "en-US,en;q=0.9",
    }


def bse_client(*, timeout: float = 30.0, referer: str = "https://www.bseindia.com/") -> httpx.Client:
    """httpx client with BSE headers and redirects on."""
    return httpx.Client(headers=bse_headers(referer=referer), timeout=timeout, follow_redirects=True)
