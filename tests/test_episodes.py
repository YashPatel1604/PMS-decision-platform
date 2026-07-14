"""Episode and decision event tests."""

from datetime import date
from decimal import Decimal

from helpers import add_transaction
from pms_platform.episodes.builder import build_episodes
from pms_platform.models.enums import DecisionType, EpisodeStatus, EventType


def test_single_buy_and_full_exit(session, import_batch, sample_security) -> None:
    """One buy followed by a full exit closes a single episode at zero."""
    add_transaction(session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 100, 1, Decimal("10"))
    add_transaction(
        session, import_batch, sample_security.security_id, date(2021, 1, 1), EventType.SELL, -100, 2, Decimal("20")
    )
    session.commit()

    episodes, events = build_episodes(session)
    session.commit()

    assert len(episodes) == 1
    assert episodes[0].status == EpisodeStatus.CLOSED.value
    assert episodes[0].final_quantity == 0
    assert episodes[0].number_of_buys == 1
    assert episodes[0].number_of_sells == 1
    assert [event.decision_type for event in events] == [
        DecisionType.INITIATE.value,
        DecisionType.EXIT.value,
    ]


def test_multiple_buys_and_partial_sell(session, import_batch, sample_security) -> None:
    """Multiple buys and a partial sell stay in one open episode."""
    add_transaction(session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 100, 1)
    add_transaction(session, import_batch, sample_security.security_id, date(2020, 6, 1), EventType.BUY, 50, 2)
    add_transaction(session, import_batch, sample_security.security_id, date(2021, 1, 1), EventType.SELL, -75, 3)
    session.commit()

    episodes, events = build_episodes(session)
    session.commit()

    assert len(episodes) == 1
    assert episodes[0].status == EpisodeStatus.OPEN.value
    assert episodes[0].final_quantity == 75
    assert episodes[0].number_of_buys == 2
    assert episodes[0].number_of_sells == 1
    assert [event.decision_type for event in events] == [
        DecisionType.INITIATE.value,
        DecisionType.ADD.value,
        DecisionType.REDUCE.value,
    ]


def test_reentry_after_exit(session, import_batch, sample_security) -> None:
    """A later purchase after a full exit starts a new episode."""
    add_transaction(session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 100, 1)
    add_transaction(session, import_batch, sample_security.security_id, date(2021, 1, 1), EventType.SELL, -100, 2)
    add_transaction(session, import_batch, sample_security.security_id, date(2022, 1, 1), EventType.BUY, 40, 3)
    session.commit()

    episodes, events = build_episodes(session)
    session.commit()

    assert len(episodes) == 2
    assert episodes[0].episode_number == 1
    assert episodes[1].episode_number == 2
    assert episodes[1].status == EpisodeStatus.OPEN.value
    assert events[-1].decision_type == DecisionType.INITIATE.value


def test_same_day_multiple_transactions(session, import_batch, sample_security) -> None:
    """Same-day transactions are processed in source row order."""
    add_transaction(session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 100, 1)
    add_transaction(session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 50, 2)
    add_transaction(session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.SELL, -30, 3)
    session.commit()

    episodes, events = build_episodes(session)
    session.commit()

    assert episodes[0].final_quantity == 120
    assert [event.decision_type for event in events] == [
        DecisionType.INITIATE.value,
        DecisionType.ADD.value,
        DecisionType.REDUCE.value,
    ]
