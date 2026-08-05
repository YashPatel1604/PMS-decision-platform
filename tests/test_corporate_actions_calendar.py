"""Corporate-action calendar unit tests."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from pms_platform.analytics.price_units import normalize_transaction_price
from pms_platform.market_data.corporate_actions import (
    CorporateAction,
    series_unit_factor_after,
    write_corporate_actions_csv,
)


def test_series_unit_factor_after_multiplies_subsequent_splits() -> None:
    actions = [
        CorporateAction(
            security_id="SEC017",
            portfolio_name="Eicher Motors",
            action_date=date(2020, 8, 24),
            action_type="Split",
            split_ratio="10:1",
            numerator=Decimal(10),
            denominator=Decimal(1),
            share_multiplier=Decimal(10),
            yahoo_ticker="EICHERMOT.NS",
            source="YAHOO_FINANCE",
            in_transaction_ledger=False,
            held_through=False,
            pre_qty=0,
            quantity_delta=0,
            notes="test",
        )
    ]
    assert series_unit_factor_after("SEC017", date(2013, 5, 2), actions=actions) == Decimal("0.1")
    assert series_unit_factor_after("SEC017", date(2021, 1, 1), actions=actions) == Decimal(1)


def test_normalize_prefers_calendar_factor(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "corporate_actions.csv"
    write_corporate_actions_csv(
        path,
        [
            CorporateAction(
                security_id="SEC017",
                portfolio_name="Eicher Motors",
                action_date=date(2020, 8, 24),
                action_type="Split",
                split_ratio="10:1",
                numerator=Decimal(10),
                denominator=Decimal(1),
                share_multiplier=Decimal(10),
                yahoo_ticker="EICHERMOT.NS",
                source="YAHOO_FINANCE",
                in_transaction_ledger=False,
                held_through=False,
                pre_qty=0,
                quantity_delta=0,
                notes="test",
            )
        ],
    )
    monkeypatch.setattr(
        "pms_platform.analytics.price_units.series_unit_factor_after",
        lambda security_id, as_of, actions=None: Decimal("0.1"),
    )
    result = normalize_transaction_price(
        Decimal("2958"),
        Decimal("306.2"),
        security_id="SEC017",
        as_of=date(2013, 5, 2),
    )
    assert result is not None
    assert result.status == "OK"
    assert result.factor_source == "CORPORATE_ACTIONS_CSV"
    assert result.inferred_factor == Decimal("0.1")
