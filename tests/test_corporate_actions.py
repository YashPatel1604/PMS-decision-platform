"""Corporate action and position tests."""

from datetime import date

import pytest

from helpers import add_transaction
from pms_platform.episodes.builder import build_episodes
from pms_platform.models.enums import DecisionType, EventType


def test_split_adjustment(session, import_batch, sample_security) -> None:
    """Split adjustments increase quantity without counting as a buy."""
    add_transaction(
        session, import_batch, sample_security.security_id, date(2025, 1, 1), EventType.BUY, 1065, 1
    )
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2026, 6, 5),
        EventType.SPLIT,
        9585,
        2,
    )
    session.commit()

    episodes, events = build_episodes(session)
    session.commit()

    assert episodes[0].final_quantity == 10650
    assert episodes[0].number_of_buys == 1
    assert episodes[0].corporate_action_quantity == 9585
    assert events[-1].decision_type == DecisionType.CORPORATE_ACTION.value


def test_bonus_issue(session, import_batch, sample_security) -> None:
    """Bonus issues are corporate actions, not buys."""
    add_transaction(
        session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 100, 1
    )
    add_transaction(
        session, import_batch, sample_security.security_id, date(2021, 1, 1), EventType.BONUS, 50, 2
    )
    session.commit()

    episodes, events = build_episodes(session)
    session.commit()

    assert episodes[0].final_quantity == 150
    assert episodes[0].number_of_buys == 1
    assert episodes[0].corporate_action_quantity == 50


def test_rights_issue(session, import_batch, sample_security) -> None:
    """Rights issues increase quantity as corporate actions."""
    add_transaction(
        session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 1000, 1
    )
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2023, 1, 20),
        EventType.RIGHTS,
        3372,
        2,
    )
    session.commit()

    episodes, events = build_episodes(session)
    session.commit()

    assert episodes[0].final_quantity == 4372
    assert events[-1].decision_type == DecisionType.CORPORATE_ACTION.value


def test_demerger_opens_episode(session, import_batch, sample_security) -> None:
    """A demerger can open an episode when shares are received from zero."""
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2022, 8, 30),
        EventType.DEMERGER,
        2540,
        1,
    )
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2022, 11, 21),
        EventType.SELL,
        -2540,
        2,
    )
    session.commit()

    episodes, events = build_episodes(session)
    session.commit()

    assert len(episodes) == 1
    assert episodes[0].status == "CLOSED"
    assert episodes[0].initial_quantity == 2540
    assert episodes[0].number_of_buys == 0
    assert episodes[0].corporate_action_quantity == 2540
    assert episodes[0].final_quantity == 0
    assert [event.decision_type for event in events] == [
        DecisionType.CORPORATE_ACTION.value,
        DecisionType.EXIT.value,
    ]


def test_demerger(session, import_batch, sample_security) -> None:
    """Demerger events are treated as corporate actions."""
    add_transaction(
        session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 500, 1
    )
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2022, 1, 1),
        EventType.DEMERGER,
        200,
        2,
    )
    session.commit()

    episodes, events = build_episodes(session)
    session.commit()

    assert episodes[0].final_quantity == 700
    assert events[-1].decision_type == DecisionType.CORPORATE_ACTION.value


def test_corporate_action_outside_episode_raises(session, import_batch, sample_security) -> None:
    """Corporate actions outside an active episode raise an error."""
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2020, 1, 1),
        EventType.SPLIT,
        100,
        1,
    )
    session.commit()

    with pytest.raises(ValueError, match="outside active episode"):
        build_episodes(session)
