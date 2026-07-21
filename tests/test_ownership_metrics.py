"""Ownership-loss threshold tests."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from pms_platform.analytics import ownership_metrics


def test_adds_do_not_change_first_buy_loss_threshold(monkeypatch) -> None:
    monkeypatch.setattr(
        ownership_metrics,
        "lookup_daily_price",
        lambda *_args: SimpleNamespace(
            close=Decimal("100"),
            adjusted_close=Decimal("10"),
        ),
    )
    events = [
        SimpleNamespace(
            event_date=date(2020, 1, 1),
            decision_type="INITIATE",
            price=Decimal("100"),
            quantity_change=10,
            position_after=10,
        ),
        SimpleNamespace(
            event_date=date(2020, 6, 1),
            decision_type="ADD",
            price=Decimal("300"),
            quantity_change=10,
            position_after=20,
        ),
    ]

    states = ownership_metrics._episode_first_buy_states(
        SimpleNamespace(),
        "SEC1",
        events,
    )

    assert states[date(2020, 1, 1)].first_buy_price == Decimal("10")
    assert states[date(2020, 6, 1)].first_buy_price == Decimal("10")
