"""Portfolio valuation helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import PortfolioSnapshotRecord
from pms_platform.portfolio.types import PortfolioPosition


def _snapshot_prices_for_date(
    session: Session,
    as_of_date: date,
) -> dict[str, tuple[Decimal | None, Decimal | None, Decimal | None]]:
    """Return snapshot price/value/weight keyed by security ID for a date."""
    rows = session.scalars(
        select(PortfolioSnapshotRecord).where(
            PortfolioSnapshotRecord.snapshot_date == as_of_date,
            PortfolioSnapshotRecord.security_id.is_not(None),
        )
    ).all()

    prices: dict[str, tuple[Decimal | None, Decimal | None, Decimal | None]] = {}
    for row in rows:
        if row.security_id is None:
            continue
        prices[row.security_id] = (row.market_price, row.market_value, row.portfolio_weight)
    return prices


def apply_snapshot_prices(
    session: Session,
    as_of_date: date,
    positions: list[PortfolioPosition],
) -> list[PortfolioPosition]:
    """Attach snapshot market prices and weights when available."""
    snapshot_prices = _snapshot_prices_for_date(session, as_of_date)
    if not snapshot_prices:
        return positions

    enriched: list[PortfolioPosition] = []
    total_market_value = Decimal(0)

    for position in positions:
        price_tuple = snapshot_prices.get(position.security_id)
        if price_tuple is None:
            enriched.append(position)
            continue

        market_price, snapshot_market_value, snapshot_weight = price_tuple
        market_value = snapshot_market_value
        if market_value is None and market_price is not None:
            market_value = Decimal(market_price) * Decimal(position.quantity)
        if market_value is not None:
            total_market_value += market_value

        enriched.append(
            PortfolioPosition(
                security_id=position.security_id,
                portfolio_name=position.portfolio_name,
                quantity=position.quantity,
                cost_basis=position.cost_basis,
                market_price=market_price,
                market_value=market_value,
                portfolio_weight=snapshot_weight,
            )
        )

    if total_market_value <= 0:
        return enriched

    return [
        PortfolioPosition(
            security_id=position.security_id,
            portfolio_name=position.portfolio_name,
            quantity=position.quantity,
            cost_basis=position.cost_basis,
            market_price=position.market_price,
            market_value=position.market_value,
            portfolio_weight=(
                position.portfolio_weight
                if position.portfolio_weight is not None
                else (
                    (position.market_value / total_market_value)
                    if position.market_value is not None
                    else None
                )
            ),
        )
        for position in enriched
    ]
