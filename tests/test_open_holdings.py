"""Open holdings analytics tests."""

from datetime import date
from decimal import Decimal

from helpers import add_transaction
from pms_platform.analytics.open_holdings import analyze_open_holdings
from pms_platform.episodes.builder import build_episodes
from pms_platform.models import BenchmarkTri, DailyPrice
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


def test_open_holding_return_and_benchmark_excess(
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
    assert result.open_count == 1
    row = result.holdings[0]
    assert row.quantity == 10
    assert row.stock_return_pct == Decimal("30")
    assert row.as_of_price == Decimal("130")
    assert row.benchmarks[0].code == "BSE_SMALLCAP"
    assert row.benchmarks[0].total_return_pct == Decimal("10")
    assert row.benchmarks[0].excess_vs_stock_pp == Decimal("20")
    assert row.data_quality_status == "OK"
    assert row.period_start_date == date(2020, 1, 2)
    assert row.from_price == Decimal("100")
    assert row.period_days == (date(2020, 6, 30) - date(2020, 1, 2)).days


def test_open_holding_from_date_window(
    session, import_batch, sample_security, monkeypatch
) -> None:
    monkeypatch.setattr(
        "pms_platform.analytics.open_holdings.lookup_research_portfolio_value",
        lambda _as_of: None,
    )
    monkeypatch.setattr(
        "pms_platform.analytics.open_holdings.load_client_portfolio_book",
        lambda: None,
    )
    monkeypatch.setattr(
        "pms_platform.episodes.model_reconcile.load_client_portfolio_book",
        lambda: None,
    )
    monkeypatch.setattr(
        "pms_platform.analytics.open_holdings.latest_research_book_date",
        lambda: None,
    )
    monkeypatch.setattr(
        "pms_platform.analytics.open_holdings.latest_bhav_trade_date",
        lambda _session: None,
    )
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
    _add_price(session, import_batch, sample_security.security_id, date(2020, 3, 31), "110")
    _add_price(session, import_batch, sample_security.security_id, date(2020, 6, 30), "143")
    _seed_benchmark(session, import_batch, date(2020, 1, 2), "1000")
    _seed_benchmark(session, import_batch, date(2020, 3, 31), "1050")
    _seed_benchmark(session, import_batch, date(2020, 6, 30), "1155")
    session.flush()
    build_episodes(session)
    session.flush()

    result = analyze_open_holdings(
        session,
        as_of_date=date(2020, 6, 30),
        from_date=date(2020, 3, 31),
    )
    row = result.holdings[0]
    assert result.from_date == date(2020, 3, 31)
    assert result.equity_market_value_from == Decimal("1100")
    assert result.equity_market_value == Decimal("1430")
    assert result.portfolio_value_source == "RECONSTRUCTED"
    assert row.period_start_date == date(2020, 3, 31)
    assert row.from_price == Decimal("110")
    assert row.first_buy_price == Decimal("100")
    # Period window: current / period-start mark = 143/110 - 1 = 30%
    assert row.stock_return_pct == Decimal("30")
    assert row.as_of_price == Decimal("143")
    # benchmark 1155/1050 - 1 = 10%
    assert row.benchmarks[0].total_return_pct == Decimal("10")
    assert row.benchmarks[0].excess_vs_stock_pp == Decimal("20")


def test_open_holding_from_date_uses_adjusted_start_not_adj_times_factor(
    session, import_batch, sample_security, monkeypatch
) -> None:
    """Period start price is adjusted close (same series as as-of adj), not adj×CA."""
    for target in (
        "pms_platform.analytics.open_holdings.lookup_research_portfolio_value",
        "pms_platform.analytics.open_holdings.load_client_portfolio_book",
        "pms_platform.episodes.model_reconcile.load_client_portfolio_book",
        "pms_platform.analytics.open_holdings.latest_research_book_date",
        "pms_platform.analytics.open_holdings.latest_bhav_trade_date",
    ):
        monkeypatch.setattr(target, lambda *_a, **_k: None)

    sid = sample_security.security_id
    add_transaction(
        session, import_batch, sid, date(2020, 1, 2), EventType.BUY, 10, 1, Decimal("100")
    )
    session.add(
        DailyPrice(
            security_id=sid,
            identifier_type="SECURITY_ID",
            identifier=sid,
            trade_date=date(2020, 3, 31),
            close=Decimal("200"),
            adjusted_close=Decimal("100"),
            adjustment_basis="SPLIT_ONLY",
            volume=None,
            currency="INR",
            source="fixture",
            source_file="fixture.csv",
            source_row=1,
            source_key=f"fixture|{sid}|2020-03-31",
            import_batch_id=import_batch.import_batch_id,
        )
    )
    session.add(
        DailyPrice(
            security_id=sid,
            identifier_type="SECURITY_ID",
            identifier=sid,
            trade_date=date(2020, 6, 30),
            close=Decimal("260"),
            adjusted_close=Decimal("130"),
            adjustment_basis="SPLIT_ONLY",
            volume=None,
            currency="INR",
            source="fixture",
            source_file="fixture.csv",
            source_row=2,
            source_key=f"fixture|{sid}|2020-06-30",
            import_batch_id=import_batch.import_batch_id,
        )
    )
    add_transaction(
        session, import_batch, sid, date(2020, 5, 1), EventType.SPLIT, 10, 2
    )
    session.flush()
    build_episodes(session)
    session.flush()

    row = analyze_open_holdings(
        session,
        as_of_date=date(2020, 6, 30),
        from_date=date(2020, 3, 31),
    ).holdings[0]
    assert row.from_price == Decimal("100")
    assert row.stock_return_pct == Decimal("30")


def test_open_holding_missing_price_is_insufficient(
    session, import_batch, sample_security
) -> None:
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2020, 1, 2),
        EventType.BUY,
        5,
        1,
        Decimal("50"),
    )
    session.flush()
    build_episodes(session)
    session.flush()

    result = analyze_open_holdings(session, as_of_date=date(2020, 6, 30))
    assert result.open_count == 1
    assert result.holdings[0].data_quality_status == "INSUFFICIENT"
    assert result.holdings[0].stock_return_pct is None
    assert result.holdings[0].benchmarks[0].data_status == "INSUFFICIENT"


def test_open_holding_uses_bhav_when_newer_than_book(
    session, import_batch, sample_security, monkeypatch
) -> None:
    from pms_platform.models.nse_bhav import NseBhavBar

    monkeypatch.setattr(
        "pms_platform.analytics.open_holdings.latest_research_book_date",
        lambda: date(2020, 6, 30),
    )
    monkeypatch.setattr(
        "pms_platform.analytics.open_holdings.lookup_research_portfolio_value",
        lambda _as_of: None,
    )
    monkeypatch.setattr(
        "pms_platform.analytics.open_holdings.load_client_portfolio_book",
        lambda: None,
    )
    monkeypatch.setattr(
        "pms_platform.episodes.model_reconcile.load_client_portfolio_book",
        lambda: None,
    )
    sample_security.current_nse_symbol = "TESTCO"
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
    session.add(
        NseBhavBar(
            trade_date=date(2020, 7, 15),
            symbol="TESTCO",
            series="EQ",
            isin=None,
            instrument_name="Test",
            open=Decimal("140"),
            high=Decimal("150"),
            low=Decimal("135"),
            close=Decimal("145"),
            prev_close=Decimal("130"),
            volume=1000,
            turnover=Decimal("145000"),
            source_key="test|TESTCO|EQ|2020-07-15",
        )
    )
    session.flush()
    build_episodes(session)
    session.flush()

    # Request past book date — ceiling should lift to bhav day.
    result = analyze_open_holdings(session, as_of_date=date(2020, 7, 15))
    assert result.as_of_date == date(2020, 7, 15)
    row = result.holdings[0]
    assert row.as_of_price == Decimal("145")
    assert row.market_value == Decimal("1450")
    assert result.portfolio_value_source == "BHAV_REVALUED"


def test_open_holding_stock_return_uses_first_buy_not_avg(
    session, import_batch, sample_security, monkeypatch
) -> None:
    """Adds raise avg buy; Stock % stays first-buy → current."""
    for target in (
        "pms_platform.analytics.open_holdings.lookup_research_portfolio_value",
        "pms_platform.analytics.open_holdings.load_client_portfolio_book",
        "pms_platform.episodes.model_reconcile.load_client_portfolio_book",
        "pms_platform.analytics.open_holdings.latest_research_book_date",
        "pms_platform.analytics.open_holdings.latest_bhav_trade_date",
    ):
        monkeypatch.setattr(target, lambda *_a, **_k: None)

    sid = sample_security.security_id
    add_transaction(
        session, import_batch, sid, date(2020, 1, 2), EventType.BUY, 10, 1, Decimal("100")
    )
    add_transaction(
        session, import_batch, sid, date(2020, 3, 2), EventType.BUY, 10, 2, Decimal("200")
    )
    _add_price(session, import_batch, sid, date(2020, 1, 2), "100")
    _add_price(session, import_batch, sid, date(2020, 6, 30), "150")
    session.flush()
    build_episodes(session)
    session.flush()

    row = analyze_open_holdings(session, as_of_date=date(2020, 6, 30)).holdings[0]
    assert row.first_buy_price == Decimal("100")
    assert row.average_buy_price == Decimal("150")
    # 150/100 - 1 = 50% (avg buy → current would be 0%)
    assert row.stock_return_pct == Decimal("50")


def test_average_buy_price_in_current_share_units(
    session, import_batch, sample_security
) -> None:
    """Pre-split lots are diluted into today's share units; post-split lots stay as-is."""
    from types import SimpleNamespace

    from pms_platform.analytics.open_holdings import _average_buy_price

    sid = sample_security.security_id
    add_transaction(
        session, import_batch, sid, date(2025, 1, 2), EventType.BUY, 100, 1, Decimal("1000")
    )
    add_transaction(
        session, import_batch, sid, date(2025, 6, 5), EventType.SPLIT, 900, 2
    )
    session.flush()

    events = [
        SimpleNamespace(
            decision_type="INITIATE",
            price=Decimal("1000"),
            quantity_change=100,
            event_date=date(2025, 1, 2),
        ),
        SimpleNamespace(
            decision_type="ADD",
            price=Decimal("200"),
            quantity_change=50,
            event_date=date(2025, 7, 1),
        ),
    ]
    # (1000*100 + 200*50) / (100*10 + 50*1) = 110000/1050
    assert _average_buy_price(session, sid, events) == Decimal("110000") / Decimal("1050")
