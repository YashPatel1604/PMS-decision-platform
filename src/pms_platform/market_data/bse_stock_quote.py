"""BSE valuation quote fetcher — StockTrading + ComHeader + scrip header."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from pms_platform.market_data.bse_http import bse_headers

_STOCK_TRADING_URL = "https://api.bseindia.com/BseIndiaAPI/api/StockTrading/w"
_COM_HEADER_URL = "https://api.bseindia.com/BseIndiaAPI/api/ComHeader/w"
_SCRIP_HEADER_URL = "https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w"
_CACHE_TTL_SEC = 6 * 60 * 60
_cache: dict[str, tuple[float, "BseStockQuote | None"]] = {}


class BseStockQuoteFetchError(Exception):
    """Raised when valuation APIs return an unusable response."""


@dataclass(frozen=True)
class BseStockQuote:
    """Valuation snapshot assembled from BSE quote endpoints."""

    bse_code: str
    last_price: Decimal | None
    market_cap_cr: Decimal | None
    pe_ratio: Decimal | None
    industry_pe: Decimal | None
    book_value_per_share: Decimal | None
    price_to_book: Decimal | None
    eps: Decimal | None
    dividend_yield: Decimal | None
    week_52_high: Decimal | None
    week_52_low: Decimal | None
    face_value: Decimal | None
    return_1d_pct: Decimal | None
    as_of_date: date


def _to_dec(raw: object) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("%", "")
    if not text or text.lower() in {"nan", "none", "null", "-", "—", "--", "na", "n/a"}:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _get_json(client: httpx.Client, url: str, params: dict[str, Any], timeout: float) -> Any | None:
    try:
        resp = client.get(url, params=params, timeout=timeout)
        if resp.status_code != 200 or len(resp.content) < 3:
            return None
        if "html" in resp.headers.get("content-type", "").lower():
            return None
        return resp.json()
    except Exception:
        return None


def _parse_combined(
    bse_code: str,
    *,
    trading: Any,
    header: Any,
    scrip: Any,
) -> BseStockQuote:
    trading = trading if isinstance(trading, dict) else {}
    header = header if isinstance(header, dict) else {}
    scrip = scrip if isinstance(scrip, dict) else {}

    curr = scrip.get("CurrRate") if isinstance(scrip.get("CurrRate"), dict) else {}
    hdr = scrip.get("Header") if isinstance(scrip.get("Header"), dict) else {}

    last_price = _to_dec(curr.get("LTP") or hdr.get("LTP") or trading.get("WAP"))
    market_cap_cr = _to_dec(trading.get("MktCapFull"))
    pe_ratio = _to_dec(header.get("PE"))
    industry_pe = _to_dec(header.get("IndPE") or header.get("IndustryPE"))
    price_to_book = _to_dec(header.get("PB"))
    eps = _to_dec(header.get("EPS"))
    dividend_yield = _to_dec(header.get("DivYield") or header.get("DivYld"))
    face_value = _to_dec(header.get("FaceVal") or header.get("FaceValue"))
    week_52_high = _to_dec(trading.get("High52") or header.get("High52"))
    week_52_low = _to_dec(trading.get("Low52") or header.get("Low52"))
    return_1d_pct = _to_dec(curr.get("PcChg"))

    book_value: Decimal | None = None
    if last_price and price_to_book and price_to_book != 0:
        book_value = (last_price / price_to_book).quantize(Decimal("0.0001"))

    return BseStockQuote(
        bse_code=bse_code,
        last_price=last_price,
        market_cap_cr=market_cap_cr,
        pe_ratio=pe_ratio,
        industry_pe=industry_pe,
        book_value_per_share=book_value,
        price_to_book=price_to_book,
        eps=eps,
        dividend_yield=dividend_yield,
        week_52_high=week_52_high,
        week_52_low=week_52_low,
        face_value=face_value,
        return_1d_pct=return_1d_pct,
        as_of_date=date.today(),
    )


def fetch_bse_stock_quote(
    bse_code: str,
    *,
    timeout: float = 15.0,
    client: httpx.Client | None = None,
    force: bool = False,
) -> BseStockQuote | None:
    """Fetch valuation quote for one BSE scrip; returns None on failure."""
    now = time.time()
    cached = _cache.get(bse_code)
    if not force and cached is not None and now - cached[0] < _CACHE_TTL_SEC:
        return cached[1]

    def _do_fetch(c: httpx.Client) -> BseStockQuote | None:
        try:
            c.get("https://www.bseindia.com/")
        except Exception:
            pass
        trading = _get_json(
            c,
            _STOCK_TRADING_URL,
            {"flag": "", "quotetype": "EQ", "scripcode": bse_code},
            timeout,
        )
        header = _get_json(
            c,
            _COM_HEADER_URL,
            {"scripcode": bse_code, "scripname": ""},
            timeout,
        )
        scrip = _get_json(
            c,
            _SCRIP_HEADER_URL,
            {"scripcode": bse_code},
            timeout,
        )
        if trading is None and header is None and scrip is None:
            return None
        quote = _parse_combined(bse_code, trading=trading, header=header, scrip=scrip)
        if (
            quote.market_cap_cr is None
            and quote.pe_ratio is None
            and quote.last_price is None
        ):
            return None
        return quote

    if client is not None:
        quote = _do_fetch(client)
    else:
        with httpx.Client(headers=bse_headers(), follow_redirects=True) as c:
            quote = _do_fetch(c)

    _cache[bse_code] = (now, quote)
    return quote


def fetch_bse_stock_quotes_batch(
    bse_codes: list[str],
    *,
    timeout: float = 15.0,
    delay_sec: float = 0.25,
) -> dict[str, BseStockQuote | None]:
    """Fetch valuation quotes for multiple BSE scrips with rate limiting."""
    results: dict[str, BseStockQuote | None] = {}
    with httpx.Client(headers=bse_headers(), follow_redirects=True) as client:
        try:
            client.get("https://www.bseindia.com/")
        except Exception:
            pass
        for i, code in enumerate(bse_codes):
            if i > 0:
                time.sleep(delay_sec)
            results[code] = fetch_bse_stock_quote(code, timeout=timeout, client=client)
    return results
