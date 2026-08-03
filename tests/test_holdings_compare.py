"""Tests for holdings portfolio/BSE excess, industry EW, and Yahoo compare."""

from datetime import date
from decimal import Decimal

import httpx
from helpers import add_transaction
from pms_platform.analytics.holdings_compare import build_compare_series
from pms_platform.analytics.industry_peers import compute_industry_equal_weight
from pms_platform.analytics.open_holdings import analyze_open_holdings
from pms_platform.episodes.builder import build_episodes
from pms_platform.market_data.yahoo_finance import YahooFinanceClient
from pms_platform.models import BenchmarkTri, DailyPrice, Security
from pms_platform.models.enums import EventType


def _add_price(session, import_batch, security_id, trade_date, close):
    session.add(
        DailyPrice(
            security_id=security_id,
            identifier_type="SECURITY_ID",
            identifier=security_id,
            trade_date=trade_date,
            close=Decimal(close),
            adjusted_close=Decimal(close),
            adjustment_basis="SPLIT_ONLY",
            volume=None,
            currency="INR",
            source="fixture",
            source_file="fixture.csv",
            source_row=1,
            source_key=f"fixture|{security_id}|{trade_date}",
            import_batch_id=import_batch.import_batch_id,
        )
    )


def _seed_benchmark(session, import_batch, trade_date: date, level: str) -> None:
    session.add(
        BenchmarkTri(
            benchmark_code="BSE_SMALLCAP",
            trade_date=trade_date,
            tri_level=Decimal(level),
            source="fixture",
            source_file="fixture.csv",
            source_row=1,
            source_key=f"bench|{trade_date.isoformat()}",
            import_batch_id=import_batch.import_batch_id,
        )
    )


def test_open_holding_portfolio_and_bse_excess(
    session, import_batch, sample_security
) -> None:
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2020, 1, 2),
        EventType.BUY,
        10,
        1,
        Decimal("100"),
    )
    _add_price(session, import_batch, sample_security.security_id, date(2020, 1, 2), "100")
    _add_price(session, import_batch, sample_security.security_id, date(2020, 6, 30), "130")
    _seed_benchmark(session, import_batch, date(2020, 1, 2), "1000")
    _seed_benchmark(session, import_batch, date(2020, 6, 30), "1100")
    session.flush()
    build_episodes(session)
    session.flush()

    result = analyze_open_holdings(session, as_of_date=date(2020, 6, 30))
    row = result.holdings[0]
    assert row.stock_return_pct == Decimal("30")
    assert row.bse_return_pct == Decimal("10")
    assert row.excess_vs_bse_pp == Decimal("20")
    assert row.portfolio_return_pct == Decimal("30")  # single-name book
    assert row.excess_vs_portfolio_pp == Decimal("0")


def test_industry_equal_weight_excludes_self(
    session, import_batch, sample_security
) -> None:
    sample_security.industry = "Widgets"
    peer_a = Security(
        security_id="PEER_A",
        portfolio_name="Peer A",
        current_nse_symbol="PEERA",
        industry="Widgets",
        import_batch_id=import_batch.import_batch_id,
    )
    peer_b = Security(
        security_id="PEER_B",
        portfolio_name="Peer B",
        current_nse_symbol="PEERB",
        industry="Widgets",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add_all([peer_a, peer_b])
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2020, 1, 2),
        EventType.BUY,
        10,
        1,
        Decimal("100"),
    )
    for sid, start, end in (
        (sample_security.security_id, "100", "110"),
        ("PEER_A", "100", "120"),
        ("PEER_B", "100", "140"),
    ):
        _add_price(session, import_batch, sid, date(2020, 1, 2), start)
        _add_price(session, import_batch, sid, date(2020, 6, 30), end)
    session.flush()

    result = compute_industry_equal_weight(
        session,
        security_id=sample_security.security_id,
        start_date=date(2020, 1, 2),
        end_date=date(2020, 6, 30),
        fetch_yahoo=False,
    )
    assert result.peer_count == 2
    assert result.used_count == 2
    # mean of 20% and 40%
    assert result.total_return_pct == Decimal("30")
    assert sample_security.security_id not in {p.security_id for p in result.peers}


def test_yahoo_search_filters_indian_tickers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v1/finance/search" in str(request.url)
        return httpx.Response(
            200,
            json={
                "quotes": [
                    {"symbol": "HAVELLS.BO", "shortname": "Havells India", "exchange": "BSE"},
                    {"symbol": "AAPL", "shortname": "Apple", "exchange": "NMS"},
                    {"symbol": "RELIANCE.NS", "longname": "Reliance Industries"},
                ]
            },
        )

    client = YahooFinanceClient(
        base_url="http://test.local",
        transport=httpx.MockTransport(handler),
    )
    hits = client.search("havells")
    assert [h.yahoo_ticker for h in hits] == ["HAVELLS.BO", "RELIANCE.NS"]


def test_yahoo_period_return_uses_prior_close_when_start_is_non_trading() -> None:
    """Jan 31 2026 was Saturday — start price should come from prior Friday."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Fri 2026-01-30, Mon 2026-02-02, Fri 2026-07-31
        stamps = [1769731200, 1769990400, 1785456000]
        closes = [100.0, 110.0, 130.0]
        return httpx.Response(
            200,
            json={
                "chart": {
                    "result": [
                        {
                            "meta": {"symbol": "TEST.BO"},
                            "timestamp": stamps,
                            "indicators": {"quote": [{"close": closes}]},
                        }
                    ]
                }
            },
        )

    client = YahooFinanceClient(
        base_url="http://test.local",
        transport=httpx.MockTransport(handler),
    )
    detail = client.period_return_detail("TEST.BO", date(2026, 1, 31), date(2026, 7, 31))
    assert detail is not None
    assert detail.start_date == date(2026, 1, 30)
    assert detail.end_date == date(2026, 7, 31)
    assert detail.total_return_pct == Decimal("30")


def test_compare_series_shape(session, import_batch, sample_security) -> None:
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2020, 1, 2),
        EventType.BUY,
        10,
        1,
        Decimal("100"),
    )
    _add_price(session, import_batch, sample_security.security_id, date(2020, 1, 2), "100")
    _add_price(session, import_batch, sample_security.security_id, date(2020, 6, 30), "130")
    _seed_benchmark(session, import_batch, date(2020, 1, 2), "1000")
    _seed_benchmark(session, import_batch, date(2020, 6, 30), "1100")
    session.flush()
    build_episodes(session)
    session.flush()

    episode_id = analyze_open_holdings(session, as_of_date=date(2020, 6, 30)).holdings[0].episode_id
    series = build_compare_series(
        session,
        episode_id=episode_id,
        start_date=date(2020, 1, 2),
        end_date=date(2020, 6, 30),
    )
    assert series.security_id == sample_security.security_id
    assert len(series.points) >= 2
    assert series.points[0].stock == 100.0
    assert series.points[-1].stock is not None


def test_normalize_peer_tickers_dedupes_and_caps() -> None:
    from pms_platform.analytics.holdings_compare import _normalize_peer_tickers

    assert _normalize_peer_tickers(
        ["RKFORGE.BO", "rkforge.bo", "ITC.NS,RELIANCE.NS"],
        "HAVELLS.BO",
    ) == ["RKFORGE.BO", "ITC.NS", "RELIANCE.NS", "HAVELLS.BO"]
