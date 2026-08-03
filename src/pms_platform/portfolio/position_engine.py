"""Reconstruct equity holdings on any historical date."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import Security, Transaction
from pms_platform.models.enums import EventType
from pms_platform.portfolio.types import PortfolioPosition
from pms_platform.portfolio.valuation import apply_snapshot_prices

_ONE = Decimal("1")
_SPLIT_BONUS = frozenset({EventType.SPLIT, EventType.BONUS})


def _transaction_amount(transaction: Transaction) -> Decimal:
    """Return the monetary value associated with a transaction."""
    if transaction.amount is not None:
        return abs(Decimal(transaction.amount))
    if transaction.price is not None:
        return abs(Decimal(transaction.price) * Decimal(transaction.quantity))
    return Decimal(0)


def compute_quantities_as_of(session: Session, as_of_date: date) -> dict[str, int]:
    """Compute running equity quantities for every security on a date."""
    transactions = list(
        session.scalars(
            select(Transaction)
            .where(Transaction.event_date <= as_of_date)
            .order_by(Transaction.security_id, Transaction.event_date, Transaction.source_row)
        )
    )

    quantities: dict[str, int] = {}
    for transaction in transactions:
        quantities[transaction.security_id] = (
            quantities.get(transaction.security_id, 0) + transaction.quantity
        )
    return {security_id: qty for security_id, qty in quantities.items() if qty != 0}


def cumulative_split_bonus_factor_after(
    session: Session,
    security_id: str,
    as_of_date: date,
) -> Decimal:
    """Scale factor so ledger qty pairs with split-/bonus-adjusted closes.

    Vendor adjusted prices already reflect splits/bonuses that occur after
    ``as_of_date``. Our quantity ledger only applies those CAs on their event
    date, so pre-CA quantities must be multiplied by later SPLIT/BONUS ratios
    when valuing with adjusted closes (e.g. E2E 10:1 on 2026-06-05).
    """
    transactions = list(
        session.scalars(
            select(Transaction)
            .where(Transaction.security_id == security_id)
            .order_by(Transaction.event_date, Transaction.source_row, Transaction.transaction_id)
        )
    )
    quantity = 0
    factor = _ONE
    for transaction in transactions:
        event_type = EventType.from_workbook(transaction.event_type)
        if transaction.event_date <= as_of_date:
            quantity += transaction.quantity
            continue
        if event_type in _SPLIT_BONUS and quantity > 0 and transaction.quantity:
            post = quantity + transaction.quantity
            factor *= Decimal(post) / Decimal(quantity)
        quantity += transaction.quantity
    return factor


def cumulative_split_bonus_factors_after(
    session: Session,
    as_of_date: date,
    security_ids: set[str] | None = None,
) -> dict[str, Decimal]:
    """Batch version of :func:`cumulative_split_bonus_factor_after`."""
    ca_security_ids = set(
        session.scalars(
            select(Transaction.security_id)
            .where(
                Transaction.event_date > as_of_date,
                Transaction.event_type.in_([EventType.SPLIT.value, EventType.BONUS.value]),
            )
            .distinct()
        ).all()
    )
    if security_ids is not None:
        ca_security_ids &= security_ids
    return {
        security_id: cumulative_split_bonus_factor_after(session, security_id, as_of_date)
        for security_id in ca_security_ids
    }


def compute_cost_basis_as_of(session: Session, as_of_date: date) -> dict[str, Decimal]:
    """Compute average-cost basis per security on a date."""
    transactions = list(
        session.scalars(
            select(Transaction)
            .where(Transaction.event_date <= as_of_date)
            .order_by(Transaction.security_id, Transaction.event_date, Transaction.source_row)
        )
    )

    quantities: dict[str, int] = {}
    cost_basis: dict[str, Decimal] = {}

    for transaction in transactions:
        security_id = transaction.security_id
        position_before = quantities.get(security_id, 0)
        event_type = EventType.from_workbook(transaction.event_type)

        if event_type == EventType.BUY:
            quantities[security_id] = position_before + transaction.quantity
            cost_basis[security_id] = cost_basis.get(security_id, Decimal(0)) + _transaction_amount(
                transaction
            )
        elif event_type == EventType.SELL:
            if position_before <= 0:
                quantities[security_id] = position_before + transaction.quantity
                continue
            sell_quantity = abs(transaction.quantity)
            remaining = position_before - sell_quantity
            current_cost = cost_basis.get(security_id, Decimal(0))
            removed_cost = (Decimal(sell_quantity) / Decimal(position_before)) * current_cost
            quantities[security_id] = remaining
            cost_basis[security_id] = current_cost - removed_cost
        elif event_type in EventType.corporate_actions():
            quantities[security_id] = position_before + transaction.quantity
        else:
            quantities[security_id] = position_before + transaction.quantity

        if quantities.get(security_id, 0) == 0:
            cost_basis.pop(security_id, None)

    return {
        security_id: basis
        for security_id, basis in cost_basis.items()
        if quantities.get(security_id, 0) != 0
    }


def portfolio_on(session: Session, as_of_date: date) -> list[PortfolioPosition]:
    """Reconstruct the equity portfolio on a specific date."""
    quantities = compute_quantities_as_of(session, as_of_date)
    cost_basis = compute_cost_basis_as_of(session, as_of_date)
    securities = {
        security.security_id: security for security in session.scalars(select(Security)).all()
    }

    positions = [
        PortfolioPosition(
            security_id=security_id,
            portfolio_name=securities[security_id].portfolio_name,
            quantity=quantity,
            cost_basis=cost_basis.get(security_id),
            market_price=None,
            market_value=None,
            portfolio_weight=None,
        )
        for security_id, quantity in sorted(quantities.items())
        if security_id in securities
    ]
    return apply_snapshot_prices(session, as_of_date, positions)
