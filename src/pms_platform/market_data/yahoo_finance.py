"""Free live quotes via Yahoo Finance chart API (NSE .NS / BSE .BO).

No API key. Quotes can be delayed a few minutes — suitable for research MTM.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from pms_platform.config import settings

DEFAULT_TIMEOUT_SECONDS = 30.0
SOURCE_NAME = "YAHOO_FINANCE"
_MAX_WORKERS = 8


@dataclass(frozen=True)
class LiveQuote:
    """Normalized live quote."""

    symbol: str
    exchange: str
    ticker: str
    last_price: Decimal
    previous_close: Decimal | None
    change: Decimal | None
    percent_change: Decimal | None
    volume: int | None
    company_name: str | None
    as_of_date: date
    raw_timestamp: str | None


def _to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _as_of_from_meta(meta: dict[str, Any]) -> date:
    epoch = meta.get("regularMarketTime")
    if epoch is not None:
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc).date()
        except (TypeError, ValueError, OSError, OverflowError):
            pass
    return date.today()


def _quote_from_chart(ticker: str, payload: dict[str, Any]) -> LiveQuote | None:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        return None
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        return None
    result = results[0]
    if not isinstance(result, dict):
        return None
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return None

    last_price = _to_decimal(meta.get("regularMarketPrice"))
    if last_price is None or last_price <= 0:
        # Fall back to latest daily close in the chart series.
        indicators = result.get("indicators")
        if isinstance(indicators, dict):
            quotes = indicators.get("quote")
            if isinstance(quotes, list) and quotes and isinstance(quotes[0], dict):
                closes = quotes[0].get("close")
                if isinstance(closes, list):
                    for value in reversed(closes):
                        last_price = _to_decimal(value)
                        if last_price is not None and last_price > 0:
                            break
    if last_price is None or last_price <= 0:
        return None

    previous_close = _to_decimal(
        meta.get("chartPreviousClose") or meta.get("previousClose")
    )
    change = None
    percent_change = None
    if previous_close is not None and previous_close != 0:
        change = last_price - previous_close
        percent_change = (change / previous_close) * Decimal("100")

    volume = _to_int(meta.get("regularMarketVolume"))
    if volume is None:
        indicators = result.get("indicators")
        if isinstance(indicators, dict):
            quotes = indicators.get("quote")
            if isinstance(quotes, list) and quotes and isinstance(quotes[0], dict):
                volumes = quotes[0].get("volume")
                if isinstance(volumes, list):
                    for value in reversed(volumes):
                        volume = _to_int(value)
                        if volume is not None:
                            break

    ticker_resolved = str(meta.get("symbol") or ticker).upper()
    symbol = ticker_resolved.split(".")[0]
    exchange = "BSE" if ticker_resolved.endswith(".BO") else "NSE"
    as_of = _as_of_from_meta(meta)
    market_time = meta.get("regularMarketTime")
    raw_ts = None
    if market_time is not None:
        try:
            raw_ts = datetime.fromtimestamp(int(market_time), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            raw_ts = str(market_time)

    return LiveQuote(
        symbol=symbol,
        exchange=exchange,
        ticker=ticker_resolved,
        last_price=last_price,
        previous_close=previous_close,
        change=change,
        percent_change=percent_change,
        volume=volume,
        company_name=str(meta.get("shortName") or meta.get("longName") or "") or None,
        as_of_date=as_of,
        raw_timestamp=raw_ts,
    )


@dataclass(frozen=True)
class YahooSearchHit:
    symbol: str
    name: str
    exchange: str
    yahoo_ticker: str


@dataclass(frozen=True)
class YahooPeriodReturn:
    ticker: str
    start_date: date
    end_date: date
    start_price: Decimal
    end_price: Decimal
    total_return_pct: Decimal


class YahooFinanceClient:
    """HTTP client for Yahoo Finance chart quotes."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.yahoo_finance_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self._transport,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; pms-decision-platform/0.1)",
            },
        )

    def fetch_stock(self, ticker: str) -> LiveQuote | None:
        """Fetch one stock via /v8/finance/chart/{ticker}."""
        path = f"/v8/finance/chart/{ticker}"
        with self._client() as client:
            response = client.get(path, params={"interval": "1d", "range": "1d"})
            response.raise_for_status()
            payload = response.json()
        return _quote_from_chart(ticker, payload)

    def fetch_stocks(self, tickers: list[str]) -> dict[str, LiveQuote]:
        """Fetch many tickers concurrently.

        Keys are only the requested ticker and Yahoo's resolved ticker for that
        request — never cross-map .BO ↔ .NS (callers choose exchange fallback).
        """
        if not tickers:
            return {}
        unique = list(dict.fromkeys(tickers))
        results: dict[str, LiveQuote] = {}

        def _one(symbol: str) -> tuple[str, LiveQuote | None]:
            try:
                return symbol, self.fetch_stock(symbol)
            except (httpx.HTTPError, ValueError, TypeError):
                return symbol, None

        workers = min(_MAX_WORKERS, len(unique))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one, ticker) for ticker in unique]
            for future in as_completed(futures):
                requested, quote = future.result()
                if quote is None:
                    continue
                results[requested] = quote
                results[quote.ticker] = quote
        return results

    def search(self, query: str, *, limit: int = 12) -> list[YahooSearchHit]:
        """Search Yahoo for Indian equities (.BO / .NS)."""
        q = query.strip()
        if not q:
            return []
        with self._client() as client:
            response = client.get(
                "/v1/finance/search",
                params={"q": q, "quotesCount": limit, "newsCount": 0},
            )
            response.raise_for_status()
            payload = response.json()
        quotes = payload.get("quotes") if isinstance(payload, dict) else None
        if not isinstance(quotes, list):
            return []
        hits: list[YahooSearchHit] = []
        for item in quotes:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            if not (symbol.endswith(".BO") or symbol.endswith(".NS")):
                continue
            exchange = "BSE" if symbol.endswith(".BO") else "NSE"
            name = str(
                item.get("shortname")
                or item.get("longname")
                or item.get("name")
                or symbol
            )
            hits.append(
                YahooSearchHit(
                    symbol=symbol.split(".")[0],
                    name=name,
                    exchange=exchange,
                    yahoo_ticker=symbol,
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def fetch_chart_history(
        self, ticker: str, start: date, end: date
    ) -> list[tuple[date, Decimal]]:
        """Daily closes between start and end (inclusive), via chart period1/period2."""
        period1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
        # Yahoo period2 is exclusive-ish; add a day buffer.
        end_plus = end.toordinal() + 1
        end_dt = date.fromordinal(end_plus)
        period2 = int(
            datetime(end_dt.year, end_dt.month, end_dt.day, tzinfo=timezone.utc).timestamp()
        )
        path = f"/v8/finance/chart/{ticker}"
        with self._client() as client:
            response = client.get(
                path,
                params={"interval": "1d", "period1": period1, "period2": period2},
            )
            response.raise_for_status()
            payload = response.json()
        chart = payload.get("chart") if isinstance(payload, dict) else None
        if not isinstance(chart, dict):
            return []
        results = chart.get("result")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            return []
        result = results[0]
        timestamps = result.get("timestamp")
        indicators = result.get("indicators")
        if not isinstance(timestamps, list) or not isinstance(indicators, dict):
            return []
        quotes = indicators.get("quote")
        if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
            return []
        closes = quotes[0].get("close")
        if not isinstance(closes, list):
            return []
        points: list[tuple[date, Decimal]] = []
        for ts, close in zip(timestamps, closes, strict=False):
            price = _to_decimal(close)
            if price is None or price <= 0:
                continue
            try:
                day = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
            except (TypeError, ValueError, OSError, OverflowError):
                continue
            if start <= day <= end:
                points.append((day, price))
        return points

    def period_return(
        self, ticker: str, start: date, end: date
    ) -> Decimal | None:
        """Total return from close on/before start to close on/before end."""
        detail = self.period_return_detail(ticker, start, end)
        return detail.total_return_pct if detail is not None else None

    def period_return_detail(
        self, ticker: str, start: date, end: date
    ) -> YahooPeriodReturn | None:
        # Always look back so we can take the last close on/before start
        # (weekends/holidays). Widening only when history is empty misses
        # the case where bars start after `start`.
        widened_start = date.fromordinal(max(start.toordinal() - 14, 1))
        history = self.fetch_chart_history(ticker, widened_start, end)
        if not history:
            return None
        start_pt = None
        end_pt = None
        for day, price in history:
            if day <= start:
                start_pt = (day, price)
            if day <= end:
                end_pt = (day, price)
        # If start was before the first available bar, use first close on/after start.
        if start_pt is None:
            for day, price in history:
                if day >= start:
                    start_pt = (day, price)
                    break
        if start_pt is None or end_pt is None or start_pt[1] <= 0:
            return None
        total = ((end_pt[1] / start_pt[1]) - Decimal("1")) * Decimal("100")
        return YahooPeriodReturn(
            ticker=ticker.upper(),
            start_date=start_pt[0],
            end_date=end_pt[0],
            start_price=start_pt[1],
            end_price=end_pt[1],
            total_return_pct=total,
        )


# Back-compat alias used by older imports/tests during transition.
IndianStockMarketClient = YahooFinanceClient
