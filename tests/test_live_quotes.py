"""Tests for Yahoo Finance client and live quote refresh."""

from datetime import date
from decimal import Decimal

import httpx
from helpers import add_transaction
from pms_platform.episodes.builder import build_episodes
from pms_platform.market_data.live_quotes import (
    bse_ticker_for_security,
    refresh_live_quotes,
)
from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.market_data.yahoo_finance import YahooFinanceClient
from pms_platform.models.enums import EventType


def test_bse_ticker_uses_nse_symbol(sample_security) -> None:
    sample_security.current_nse_symbol = "HAVELLS"
    assert bse_ticker_for_security(sample_security) == "HAVELLS.BO"


def test_client_parses_chart_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v8/finance/chart/HAVELLS.BO" in str(request.url)
        return httpx.Response(
            200,
            json={
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "currency": "INR",
                                "symbol": "HAVELLS.BO",
                                "regularMarketPrice": 1501.25,
                                "chartPreviousClose": 1490.0,
                                "regularMarketVolume": 12345,
                                "regularMarketTime": 1753975800,
                                "shortName": "Havells India Limited",
                            },
                            "indicators": {"quote": [{"close": [1501.25], "volume": [12345]}]},
                        }
                    ],
                    "error": None,
                }
            },
        )

    client = YahooFinanceClient(
        base_url="http://test.local",
        transport=httpx.MockTransport(handler),
    )
    quote = client.fetch_stock("HAVELLS.BO")
    assert quote is not None
    assert quote.last_price == Decimal("1501.25")
    assert quote.exchange == "BSE"
    assert quote.previous_close == Decimal("1490.0")
    assert quote.as_of_date == date(2025, 7, 31)


def test_refresh_live_quotes_upserts_daily_price(
    session, import_batch, sample_security
) -> None:
    sample_security.current_nse_symbol = "TESTCO"
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2024, 1, 2),
        EventType.BUY,
        10,
        1,
        Decimal("100"),
    )
    session.flush()
    build_episodes(session)
    session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "currency": "INR",
                                "symbol": "TESTCO.BO",
                                "regularMarketPrice": 123.45,
                                "chartPreviousClose": 120.0,
                                "regularMarketVolume": 1000,
                                "regularMarketTime": 1753975800,
                            },
                            "indicators": {"quote": [{"close": [123.45], "volume": [1000]}]},
                        }
                    ],
                    "error": None,
                }
            },
        )

    client = YahooFinanceClient(
        base_url="http://test.local",
        transport=httpx.MockTransport(handler),
    )
    result = refresh_live_quotes(session, client=client, prefer_bse=True)
    session.flush()

    assert result.fetched == 1
    assert result.upserted == 1
    observation = lookup_daily_price(
        session, sample_security.security_id, date(2025, 7, 31)
    )
    assert observation is not None
    assert observation.adjusted_close == Decimal("123.45")
    assert observation.lookup_mode == "EXACT"


def test_refresh_falls_back_to_nse_when_bse_missing(
    session, import_batch, sample_security
) -> None:
    sample_security.current_nse_symbol = "TESTCO"
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2024, 1, 2),
        EventType.BUY,
        10,
        1,
        Decimal("100"),
    )
    session.flush()
    build_episodes(session)
    session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("TESTCO.BO"):
            return httpx.Response(
                200,
                json={"chart": {"result": None, "error": {"code": "Not Found"}}},
            )
        if path.endswith("TESTCO.NS"):
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "meta": {
                                    "currency": "INR",
                                    "symbol": "TESTCO.NS",
                                    "regularMarketPrice": 99.5,
                                    "chartPreviousClose": 98.0,
                                    "regularMarketVolume": 500,
                                    "regularMarketTime": 1753975800,
                                },
                                "indicators": {
                                    "quote": [{"close": [99.5], "volume": [500]}]
                                },
                            }
                        ],
                        "error": None,
                    }
                },
            )
        return httpx.Response(404, json={"error": "unexpected"})

    client = YahooFinanceClient(
        base_url="http://test.local",
        transport=httpx.MockTransport(handler),
    )
    result = refresh_live_quotes(session, client=client, prefer_bse=True)
    session.flush()

    assert result.fetched == 1
    assert result.failed == 0
    assert any("TESTCO.NS" in note for note in result.notes)
    observation = lookup_daily_price(
        session, sample_security.security_id, date(2025, 7, 31)
    )
    assert observation is not None
    assert observation.adjusted_close == Decimal("99.5")
