"""Episode analytics tests."""

from datetime import date
from decimal import Decimal
from sqlalchemy import select

from helpers import add_transaction
from pms_platform.analytics.episode_performance import analyze_closed_episodes
from pms_platform.episodes.builder import build_episodes
from pms_platform.models import BenchmarkTri, EpisodePerformance
from pms_platform.models.enums import EventType


def _seed_benchmark(session, import_batch, trade_date: date, level: str) -> None:
    session.add(
        BenchmarkTri(
            benchmark_code="BSE_SMALLCAP",
            trade_date=trade_date,
            tri_level=Decimal(level),
            source="fixture",
            source_file="fixture.csv",
            source_row=1,
            source_key=f"fixture|{trade_date.isoformat()}",
            import_batch_id=import_batch.import_batch_id,
        )
    )


def test_analyze_closed_episode_with_benchmark_comparison(
    session, import_batch, sample_security
) -> None:
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2019, 1, 2),
        EventType.BUY,
        100,
        1,
        Decimal("100"),
    )
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2019, 6, 30),
        EventType.SELL,
        -100,
        2,
        Decimal("150"),
    )
    _seed_benchmark(session, import_batch, date(2019, 1, 2), "10000")
    _seed_benchmark(session, import_batch, date(2019, 6, 30), "11000")
    session.flush()

    episodes, _ = build_episodes(session)
    session.flush()

    summary = analyze_closed_episodes(session)
    performance = session.scalar(
        select(EpisodePerformance).where(EpisodePerformance.episode_id == episodes[0].episode_id)
    )

    assert summary.analyzed == 1
    assert performance is not None
    assert performance.total_invested == Decimal("10000")
    assert performance.total_sale_proceeds == Decimal("15000")
    assert performance.total_profit_loss == Decimal("5000")
    assert performance.stock_xirr is not None
    assert performance.smallcap_return_pct == Decimal("10")
    assert performance.excess_vs_smallcap is not None
    assert performance.data_quality_status == "OK"


def test_split_events_do_not_create_cash_flows(session, import_batch, sample_security) -> None:
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2019, 1, 2),
        EventType.BUY,
        100,
        1,
        Decimal("10"),
    )
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2019, 3, 1),
        EventType.SPLIT,
        100,
        2,
    )
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2019, 6, 30),
        EventType.SELL,
        -200,
        3,
        Decimal("12"),
    )
    _seed_benchmark(session, import_batch, date(2019, 1, 2), "10000")
    _seed_benchmark(session, import_batch, date(2019, 6, 30), "10500")
    session.flush()

    build_episodes(session)
    summary = analyze_closed_episodes(session)
    performance = session.scalar(select(EpisodePerformance))

    assert summary.cash_flow_rows == 2
    assert performance is not None
    assert performance.total_invested == Decimal("1000")
    assert performance.total_sale_proceeds == Decimal("2400")
