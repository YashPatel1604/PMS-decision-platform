"""Reconstruct liquid holdings on any historical date."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import LiquidTransaction
from pms_platform.models.enums import EventType
from pms_platform.portfolio.types import LiquidPosition


def _liquid_amount(transaction: LiquidTransaction) -> Decimal:
    """Return the monetary value associated with a liquid transaction."""
    if transaction.amount is not None:
        return abs(Decimal(transaction.amount))
    if transaction.price is not None:
        return abs(Decimal(transaction.price) * Decimal(transaction.quantity))
    return Decimal(0)


def liquid_on(session: Session, as_of_date: date) -> LiquidPosition | None:
    """Reconstruct the liquid holding balance on a specific date."""
    transactions = list(
        session.scalars(
            select(LiquidTransaction)
            .where(LiquidTransaction.event_date <= as_of_date)
            .order_by(LiquidTransaction.event_date, LiquidTransaction.source_row)
        )
    )
    if not transactions:
        return None

    quantity = 0
    cost_basis = Decimal(0)
    for transaction in transactions:
        event_type = EventType.from_workbook(transaction.event_type)
        if event_type == EventType.BUY:
            quantity += transaction.quantity
            cost_basis += _liquid_amount(transaction)
        elif event_type == EventType.SELL:
            if quantity <= 0:
                quantity += transaction.quantity
                continue
            sell_quantity = abs(transaction.quantity)
            removed_cost = (Decimal(sell_quantity) / Decimal(quantity)) * cost_basis
            quantity -= sell_quantity
            cost_basis -= removed_cost
        else:
            quantity += transaction.quantity

    if quantity == 0:
        return None

    return LiquidPosition(
        quantity=quantity,
        cost_basis=cost_basis if cost_basis > 0 else None,
        market_price=None,
        market_value=None,
    )
