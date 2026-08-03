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
    # 143/110 - 1 = 30%
    assert row.stock_return_pct == Decimal("30")
    # benchmark 1155/1050 - 1 = 10%
    assert row.benchmarks[0].total_return_pct == Decimal("10")
    assert row.benchmarks[0].excess_vs_stock_pp == Decimal("20")


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
