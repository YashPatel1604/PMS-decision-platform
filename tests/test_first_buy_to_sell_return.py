"""First-buy → sell-mark return helper checks."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from pms_platform.analytics.episode_performance import first_buy_to_sell_return_pct


def _event(
    decision_type: str,
    price: str,
    qty: int,
    day: date,
    event_id: int,
) -> SimpleNamespace:
    return SimpleNamespace(
        decision_type=decision_type,
        price=Decimal(price),
        quantity_change=qty,
        event_date=day,
        decision_event_id=event_id,
    )


def test_uses_last_sell_when_above_avg() -> None:
    # avg sell = 130, last = 150 → mark 150 → 50%
    events = [
        _event("INITIATE", "100", 10, date(2020, 1, 2), 1),
        _event("REDUCE", "120", -4, date(2020, 3, 1), 2),
        _event("EXIT", "150", -6, date(2020, 4, 1), 3),
    ]
    assert first_buy_to_sell_return_pct(events) == Decimal("50")


def test_uses_avg_sell_when_last_not_higher() -> None:
    # avg sell = (140*5 + 120*5)/10 = 130, last = 120 → mark 130 → 30%
    events = [
        _event("INITIATE", "100", 10, date(2020, 1, 2), 1),
        _event("REDUCE", "140", -5, date(2020, 3, 1), 2),
        _event("EXIT", "120", -5, date(2020, 4, 1), 3),
    ]
    assert first_buy_to_sell_return_pct(events) == Decimal("30")
