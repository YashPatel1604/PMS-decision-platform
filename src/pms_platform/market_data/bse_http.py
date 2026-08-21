"""Shared BSE HTTP headers / client defaults."""

from __future__ import annotations

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
